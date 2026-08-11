#!/usr/bin/env python3
"""Point Hermes Agent at this checkout's skills — no copies, no forked headers.

Hermes discovers skills by recursively scanning every directory listed in
``skills.external_dirs`` (``$HERMES_HOME/config.yaml``) for ``SKILL.md`` files,
in addition to its own ``$HERMES_HOME/skills/``.  Because the SKILL.md format
this repo already uses is the one Hermes reads — ``name`` + ``description``
frontmatter, everything else optional — the skills load unmodified.  So instead
of installing *copies* into ``$HERMES_HOME/skills/``, this script registers the
checkout itself: one source of truth, and ``git pull`` is the update path.

It also registers the bundled Chronicle MCP server under ``mcp_servers`` so the
``chronicle.*`` tools the skills call are actually present.

Usage:
    python3 hermes/install.py            # register skills + MCP server
    python3 hermes/install.py --print    # show the YAML, change nothing
    python3 hermes/install.py --no-mcp   # skills only
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent
MCP_SERVER_NAME = "chronicle"

# Skill roots in this repo. Both are scanned recursively by Hermes, so listing
# the two parents is enough to reach all of the skills beneath them.
SKILL_DIR_CANDIDATES = (
    REPO_ROOT / "skills",                      # chronicle plugin
    REPO_ROOT / "research-plugin" / "skills",  # research plugin
)


def hermes_home() -> Path:
    """Resolve HERMES_HOME the same way hermes_constants.get_hermes_home() does."""
    env = os.environ.get("HERMES_HOME", "").strip()
    if env:
        return Path(os.path.expanduser(os.path.expandvars(env)))
    if sys.platform == "win32":
        local_appdata = os.environ.get("LOCALAPPDATA", "").strip()
        base = Path(local_appdata) if local_appdata else Path.home() / "AppData" / "Local"
        return base / "hermes"
    return Path.home() / ".hermes"


def load_yaml(path: Path) -> Tuple[Any, Any]:
    """Load config.yaml, preferring ruamel so comments survive the round-trip.

    Hermes itself depends on ruamel.yaml, so when this runs under the same
    interpreter as an installed Hermes the comment-preserving path is taken.
    A bare python3 usually has only PyYAML, which silently drops comments —
    hence the backup and the warning in main().
    """
    try:
        from ruamel.yaml import YAML  # type: ignore

        yaml = YAML()
        yaml.preserve_quotes = True
        # config.yaml nests deeply; keep Hermes' own indentation conventions.
        yaml.indent(mapping=2, sequence=4, offset=2)
        data = yaml.load(path.read_text(encoding="utf-8")) if path.exists() else None
        return (data if data is not None else {}), yaml
    except ImportError:
        pass

    try:
        import yaml as pyyaml  # type: ignore
    except ImportError:
        sys.exit(
            "error: need PyYAML or ruamel.yaml to edit config.yaml.\n"
            "       install one (`pip install pyyaml`), or run with --print and\n"
            "       paste the snippet into config.yaml by hand."
        )

    data = pyyaml.safe_load(path.read_text(encoding="utf-8")) if path.exists() else None
    return (data if data is not None else {}), None


def dump_yaml(data: Any, dumper: Any, path: Path) -> None:
    if dumper is not None:  # ruamel round-trip
        with path.open("w", encoding="utf-8") as fh:
            dumper.dump(data, fh)
        return
    import yaml as pyyaml  # type: ignore

    path.write_text(
        pyyaml.safe_dump(data, sort_keys=False, default_flow_style=False),
        encoding="utf-8",
    )


def existing_skill_dirs() -> List[Path]:
    dirs = [d for d in SKILL_DIR_CANDIDATES if d.is_dir()]
    if not dirs:
        sys.exit(f"error: no skill directories found under {REPO_ROOT}")
    return dirs


def plan_skill_dirs(config: Dict[str, Any], wanted: List[Path]) -> List[str]:
    """Return the skill dirs not already registered, comparing resolved paths."""
    skills_cfg = config.get("skills")
    current = skills_cfg.get("external_dirs") if isinstance(skills_cfg, dict) else None
    if isinstance(current, str):
        current = [current]
    if not isinstance(current, list):
        current = []

    def resolved(entry: Any) -> str:
        text = os.path.expanduser(os.path.expandvars(str(entry).strip()))
        # Hermes resolves relative entries against HERMES_HOME, not cwd.
        base = Path(text)
        if not base.is_absolute():
            base = hermes_home() / base
        try:
            return str(base.resolve())
        except OSError:
            return str(base)

    already = {resolved(entry) for entry in current}
    return [str(d) for d in wanted if str(d.resolve()) not in already]


def apply_skill_dirs(config: Dict[str, Any], additions: List[str]) -> None:
    skills_cfg = config.get("skills")
    if not isinstance(skills_cfg, dict):
        skills_cfg = {}
        config["skills"] = skills_cfg
    current = skills_cfg.get("external_dirs")
    if isinstance(current, str):
        current = [current]
    if not isinstance(current, list):
        current = []
        skills_cfg["external_dirs"] = current
    current.extend(additions)
    skills_cfg["external_dirs"] = current


def mcp_entry() -> Dict[str, Any]:
    """The Chronicle MCP server, as Hermes' mcp_servers schema wants it.

    launch.sh locates its own directory from $0 and picks a runtime
    (node → bun → python3), so an absolute path to it is the whole config.
    """
    return {"command": "sh", "args": [str(REPO_ROOT / "mcp" / "launch.sh")]}


def mcp_needs_update(config: Dict[str, Any]) -> bool:
    servers = config.get("mcp_servers")
    if not isinstance(servers, dict):
        return True
    current = servers.get(MCP_SERVER_NAME)
    if not isinstance(current, dict):
        return True
    want = mcp_entry()
    return (
        current.get("command") != want["command"]
        or [str(a) for a in (current.get("args") or [])] != want["args"]
    )


def apply_mcp(config: Dict[str, Any]) -> None:
    servers = config.get("mcp_servers")
    if not isinstance(servers, dict):
        servers = {}
        config["mcp_servers"] = servers
    servers[MCP_SERVER_NAME] = mcp_entry()


def snippet(skill_dirs: List[Path], with_mcp: bool) -> str:
    lines = ["skills:", "  external_dirs:"]
    lines += [f"    - {d}" for d in skill_dirs]
    if with_mcp:
        entry = mcp_entry()
        lines += [
            "mcp_servers:",
            f"  {MCP_SERVER_NAME}:",
            f"    command: {entry['command']}",
            f"    args: [\"{entry['args'][0]}\"]",
        ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Register this checkout's skills (and the Chronicle MCP server) with Hermes Agent.",
    )
    parser.add_argument("--print", dest="print_only", action="store_true",
                        help="print the config.yaml snippet and exit without writing")
    parser.add_argument("--no-mcp", action="store_true",
                        help="register skills only; leave mcp_servers alone")
    args = parser.parse_args()

    skill_dirs = existing_skill_dirs()
    with_mcp = not args.no_mcp

    if args.print_only:
        print(f"# add to {hermes_home() / 'config.yaml'}")
        print(snippet(skill_dirs, with_mcp))
        return 0

    home = hermes_home()
    config_path = home / "config.yaml"
    config, dumper = load_yaml(config_path)
    if not isinstance(config, dict):
        sys.exit(f"error: {config_path} is not a YAML mapping; fix or move it first.")

    pending_dirs = plan_skill_dirs(config, skill_dirs)
    pending_mcp = with_mcp and mcp_needs_update(config)

    if not pending_dirs and not pending_mcp:
        print(f"Already configured — {config_path} needs no changes.")
        print(f"  skills: {len(skill_dirs)} dir(s) from {REPO_ROOT}")
        return 0

    if config_path.exists():
        backup = config_path.with_suffix(f".yaml.bak-{time.strftime('%Y%m%d-%H%M%S')}")
        shutil.copy2(config_path, backup)
        print(f"Backed up {config_path} → {backup}")
        if dumper is None:
            print("  note: PyYAML fallback in use — comments in config.yaml are not preserved.")
            print("        Install ruamel.yaml, or use --print, to keep them.")
    else:
        home.mkdir(parents=True, exist_ok=True)

    if pending_dirs:
        apply_skill_dirs(config, pending_dirs)
    if pending_mcp:
        apply_mcp(config)

    dump_yaml(config, dumper, config_path)

    print(f"Updated {config_path}")
    for d in pending_dirs:
        print(f"  + skills.external_dirs: {d}")
    if pending_mcp:
        print(f"  + mcp_servers.{MCP_SERVER_NAME}")
    print("\nRestart Hermes, then run `hermes skills list` to see them.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
