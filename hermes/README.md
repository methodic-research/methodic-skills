# Hermes Agent

These skills run in [Hermes Agent](https://github.com/NousResearch/hermes-agent)
**unmodified** — there is no Hermes-specific copy of any `SKILL.md` in this repo,
and there shouldn't be one. Hermes reads the same format Claude Code and Codex
do, so all 39 skills load from a checkout as-is.

## Why no second copy is needed

Hermes' skill loader requires exactly two frontmatter fields, `name` and
`description` — and `name` falls back to the containing directory name when it's
absent (`agent/skill_utils.py`). Everything else Hermes understands (`version`,
`author`, `license`, `platforms`, `metadata.hermes.*`) is optional, and unknown
keys are ignored: the frontmatter is parsed as a plain YAML mapping. Discovery is
a recursive scan for `SKILL.md`, so this repo's flat `skills/<name>/SKILL.md`
layout works without the category directories Hermes' own bundled skills use.

The one behavioral difference worth knowing: Hermes caps a description at 1024
characters and **truncates** past that rather than rejecting the skill
(`tools/skills_tool.py`). Four skills exceed it today —
`chronicle-import-repo` (1142), `synthesis` (1088), `literature-review` (1037),
and `evaluate-results` (1034) — so the tail of their trigger text is clipped in
Hermes' skill index. They still load and still work; if trigger precision on
those four matters to you, tighten the descriptions rather than forking them.

## Install

```bash
python3 hermes/install.py
```

This edits `$HERMES_HOME/config.yaml` (default `~/.hermes/config.yaml`, or
`%LOCALAPPDATA%\hermes` on Windows) to add:

- `skills.external_dirs` → this checkout's `skills/` and `research-plugin/skills/`
- `mcp_servers.chronicle` → `sh <checkout>/mcp/launch.sh`

It is idempotent, backs the config up before writing, and resolves paths the way
Hermes does, so re-running after a `git pull` is a no-op. Flags:

| Flag | Effect |
| --- | --- |
| `--print` | Print the YAML and exit — change nothing |
| `--no-mcp` | Register the skills only, leave `mcp_servers` alone |

Comments in your `config.yaml` survive when `ruamel.yaml` is importable (Hermes
depends on it, so run the installer with Hermes' own interpreter to be sure). Under
a bare `python3` with only PyYAML the rewrite drops comments — the script warns and
keeps a timestamped backup. Use `--print` and paste by hand if that matters.

Restart Hermes afterwards, then confirm:

```bash
hermes skills list        # 39 chronicle-* / research skills appear
```

## Or configure it by hand

```yaml
skills:
  external_dirs:
    - /path/to/skills/skills
    - /path/to/skills/research-plugin/skills

mcp_servers:
  chronicle:
    command: sh
    args: ["/path/to/skills/mcp/launch.sh"]
```

Relative `external_dirs` entries resolve against `$HERMES_HOME` (not the cwd), and
`~` plus `${VAR}` are expanded.

## The `tap` alternative (copies into `~/.hermes/skills/`)

Hermes can also install skills from a GitHub repo, which **copies** them into
`~/.hermes/skills/` — no duplication in this repo, but the copies on disk go stale
until `hermes skills update`:

```bash
hermes skills tap add methodic-research/skills
hermes skills search chronicle
hermes skills install methodic-research/skills/skills/chronicle-status
```

A tap is one repo plus one base path, defaulting to `skills/`, and
`tap add` refuses a second entry for the same repo — so a tap reaches the 35
chronicle skills under `skills/` but **not** the four research skills under
`research-plugin/skills/`. Adding a second entry for the same repo with
`"path": "research-plugin/skills/"` by hand in `~/.hermes/skills/.hub/taps.json`
works (the reader doesn't dedupe), but `external_dirs` is the cleaner route and
the one this repo supports.

## Credentials and the MCP server

Unchanged from the Claude Code path: the launcher reads
`~/.methodic/credentials.yaml` and proxies to your Chronicle server. Create the
key first (see the root [README](../README.md)). The launcher probes for `node`
≥18, then `bun`, then `python3` ≥3.8 — a Python-only workstation needs nothing
extra. It requires a POSIX `sh`, so on bare Windows use WSL or point Hermes at the
remote HTTP MCP server instead.
