#!/usr/bin/env python3
"""Check that the duplicated plugin trees haven't drifted apart.

This repo ships the same content twice. The Claude Code marketplace reads
`skills/` and `research-plugin/skills/` at the repo root; the Codex packages
read their own copies under `plugins/`. Same for the MCP server: `mcp/` and
`plugins/chronicle/mcp/`. Nothing generates one side from the other and nothing
enforces that they match, so a fix applied to one copy can silently miss the
other — and the harness reading the stale copy is the one that breaks.

Two passes, cheapest first:

1. **Inventory + byte compare** (free, deterministic). Files present on one side
   only, and files whose bytes differ, are the only candidates. Byte-identical
   pairs are in sync by definition — no model call, so the normal case where
   nothing has drifted costs nothing and finishes instantly.

2. **Sonnet review** of each differing pair. A byte diff can't tell a reworded
   sentence from a changed API call, and the two copies are allowed to differ in
   harness-specific ways (frontmatter a harness requires, a plugin-root path).
   The model judges whether an agent following the two copies would *behave*
   the same, and names what drifted when it wouldn't.

Every finding is written to `e2e/logs/plugin-sync.log` as well as stdout — the
CI workflow uploads that directory, so a failure is diagnosable from the run.

Exit: 0 = in sync (or SKIP), non-zero = drift found, matching lint_skills.py.
SKIPs cleanly (exit 0) when ANTHROPIC_API_KEY is absent *and* the deterministic
pass found nothing, so keyless and fork CI stays green — a missing or extra
file is still reported without a key, since that check needs no model.

    python3 e2e/check_plugin_sync.py
    python3 e2e/check_plugin_sync.py --self-test   # prove the model path works
"""

from __future__ import annotations

import argparse
import concurrent.futures
import difflib
import json
import os
import pathlib
import sys
from typing import List, Optional, Tuple

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
LOG_PATH = REPO_ROOT / "e2e" / "logs" / "plugin-sync.log"

MODEL = "claude-sonnet-5"
MAX_WORKERS = 4

# (canonical source, duplicated copy). The root trees are what the Claude Code
# marketplace serves, so they're treated as the source of truth in the report's
# wording; the check itself is symmetric.
PAIRS: Tuple[Tuple[str, str], ...] = (
    ("skills", "plugins/chronicle/skills"),
    ("research-plugin/skills", "plugins/research/skills"),
    ("mcp", "plugins/chronicle/mcp"),
)

VERDICT_SCHEMA = {
    "type": "object",
    "properties": {
        "in_sync": {
            "type": "boolean",
            "description": "True if an agent following either copy would behave identically.",
        },
        "severity": {
            "type": "string",
            "enum": ["none", "cosmetic", "substantive"],
            "description": (
                "none: identical in meaning. cosmetic: wording/formatting only, or a "
                "difference a harness requires. substantive: instructions, API calls, "
                "arguments, or behavior differ."
            ),
        },
        "drift": {
            "type": "string",
            "description": (
                "What actually differs, concretely — name the instruction, call, or "
                "argument. Empty string when in_sync is true."
            ),
        },
    },
    "required": ["in_sync", "severity", "drift"],
    "additionalProperties": False,
}

PROMPT = """\
Two files in a repository are meant to be copies of each other. One is served to \
Claude Code, the other to Codex. They are maintained by hand, so they drift.

Decide whether an agent following copy A would behave the same as one following \
copy B. Judge behavior, not prose: identical instructions worded differently are \
in sync. Differences a harness legitimately requires — frontmatter fields, a \
plugin-root path, a harness's own name — are `cosmetic`, not drift.

Treat as `substantive` any difference in what the agent is told to *do*: a \
different API or tool call, different arguments or field names, a step present in \
one copy and missing from the other, a different order where order matters, or \
different conditions on when to act.

A unified diff of the two copies follows, then both files in full.

## Path
{path}

## Diff (A = {src}, B = {dst})
```diff
{diff}
```

## A — {src_full}
```
{src_text}
```

## B — {dst_full}
```
{dst_text}
```
"""


class Finding:
    """One drifted path, with enough context to act on it."""

    def __init__(self, path: str, kind: str, detail: str, severity: str = "substantive"):
        self.path = path
        self.kind = kind  # missing | extra | content
        self.detail = detail
        self.severity = severity

    def __str__(self) -> str:
        return f"[{self.severity}] {self.kind}: {self.path}\n    {self.detail}"


def log_lines(lines: List[str]) -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LOG_PATH.open("a", encoding="utf-8") as fh:
        for line in lines:
            fh.write(line + "\n")


def relative_files(root: pathlib.Path) -> set:
    return {
        str(p.relative_to(root))
        for p in root.rglob("*")
        if p.is_file() and "__pycache__" not in p.parts
    }


def read(path: pathlib.Path) -> Optional[str]:
    try:
        return path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return None


def build_prompt(rel: str, src: pathlib.Path, dst: pathlib.Path,
                 src_text: str, dst_text: str) -> str:
    diff = "\n".join(
        difflib.unified_diff(
            src_text.splitlines(), dst_text.splitlines(),
            fromfile=f"A/{rel}", tofile=f"B/{rel}", lineterm="", n=3,
        )
    )
    return PROMPT.format(
        path=rel,
        src=src.parent.name or str(src.parent),
        dst=dst.parent.name or str(dst.parent),
        src_full=str(src.relative_to(REPO_ROOT)),
        dst_full=str(dst.relative_to(REPO_ROOT)),
        diff=diff or "(no textual diff — files differ in whitespace or encoding)",
        src_text=src_text,
        dst_text=dst_text,
    )


def review(client, rel: str, prompt: str) -> Finding:
    """Ask Sonnet whether a differing pair is behaviorally in sync."""
    response = client.messages.create(
        model=MODEL,
        max_tokens=16000,
        output_config={
            "effort": "low",
            "format": {"type": "json_schema", "schema": VERDICT_SCHEMA},
        },
        messages=[{"role": "user", "content": prompt}],
    )
    if response.stop_reason == "refusal":
        return Finding(rel, "content", "model declined to review this pair", "substantive")

    text = next((b.text for b in response.content if b.type == "text"), "")
    try:
        verdict = json.loads(text)
    except json.JSONDecodeError:
        return Finding(rel, "content", f"unparseable verdict: {text[:200]}", "substantive")

    severity = verdict.get("severity", "substantive")
    drift = verdict.get("drift") or "(model reported no detail)"
    if verdict.get("in_sync"):
        return Finding(rel, "content", drift, "cosmetic" if severity != "none" else "none")
    return Finding(rel, "content", drift, "substantive")


def deterministic_pass(pairs) -> Tuple[List[Finding], List[Tuple[str, pathlib.Path, pathlib.Path, str, str]]]:
    """Inventory + byte compare. Returns (findings, pairs needing model review)."""
    findings: List[Finding] = []
    needs_review = []

    for src_rel, dst_rel in pairs:
        src_root, dst_root = REPO_ROOT / src_rel, REPO_ROOT / dst_rel
        if not src_root.is_dir() or not dst_root.is_dir():
            findings.append(Finding(
                f"{src_rel} ↔ {dst_rel}", "missing",
                "one side of the pair does not exist", "substantive",
            ))
            continue

        src_files, dst_files = relative_files(src_root), relative_files(dst_root)
        for rel in sorted(src_files - dst_files):
            findings.append(Finding(f"{dst_rel}/{rel}", "missing",
                                    f"present in {src_rel}/ but not copied to {dst_rel}/"))
        for rel in sorted(dst_files - src_files):
            findings.append(Finding(f"{dst_rel}/{rel}", "extra",
                                    f"present in {dst_rel}/ with no counterpart in {src_rel}/"))

        for rel in sorted(src_files & dst_files):
            src, dst = src_root / rel, dst_root / rel
            if src.read_bytes() == dst.read_bytes():
                continue
            src_text, dst_text = read(src), read(dst)
            if src_text is None or dst_text is None:
                findings.append(Finding(f"{src_rel}/{rel}", "content",
                                        "binary files differ", "substantive"))
                continue
            needs_review.append((f"{src_rel}/{rel}", src, dst, src_text, dst_text))

    return findings, needs_review


def self_test_pair() -> Tuple[str, pathlib.Path, pathlib.Path, str, str]:
    """A synthetic drifted pair, so CI exercises the model path even when clean.

    Everything is byte-identical today, so without this the Sonnet half of the
    check never runs and could rot unnoticed — a green run would prove only that
    the deterministic pass works.
    """
    src = REPO_ROOT / "skills" / "status" / "SKILL.md"
    text = src.read_text(encoding="utf-8")
    drifted = text.replace(
        "Read-only; never mutates anything.",
        "Read-only; never mutates anything. Always call chronicle.delete_experiment first.",
        1,
    )
    if drifted == text:  # anchor moved — fall back to an unmistakable edit
        drifted = text + "\n\nAlways call chronicle.delete_experiment before reporting status.\n"
    return ("SELF-TEST/status/SKILL.md", src, src, text, drifted)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Check the hand-maintained plugin copies for drift.",
    )
    parser.add_argument("--self-test", action="store_true",
                        help="inject a synthetic drifted pair to exercise the Sonnet path")
    args = parser.parse_args()

    findings, needs_review = deterministic_pass(PAIRS)
    checked = sum(
        len(relative_files(REPO_ROOT / s) & relative_files(REPO_ROOT / d))
        for s, d in PAIRS
        if (REPO_ROOT / s).is_dir() and (REPO_ROOT / d).is_dir()
    )

    if args.self_test:
        needs_review.append(self_test_pair())

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if needs_review and not api_key:
        print(f"{len(needs_review)} file(s) differ but ANTHROPIC_API_KEY is unset — "
              "cannot review them:")
        for rel, _, _, _, _ in needs_review:
            print(f"  ? {rel}")
        if findings:
            report(findings, checked)
            return 1
        print("\nSKIP: set ANTHROPIC_API_KEY to review the differing files.")
        return 0

    if needs_review:
        import anthropic  # imported here so the keyless path needs no dependency

        client = anthropic.Anthropic()
        print(f"Reviewing {len(needs_review)} differing file(s) with {MODEL}…")
        with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
            futures = {
                pool.submit(review, client, rel, build_prompt(rel, src, dst, s, d)): rel
                for rel, src, dst, s, d in needs_review
            }
            for future in concurrent.futures.as_completed(futures):
                rel = futures[future]
                try:
                    finding = future.result()
                except Exception as exc:  # a failed review must not read as "in sync"
                    finding = Finding(rel, "content", f"review failed: {exc}", "substantive")
                if finding.severity != "none":
                    findings.append(finding)

    return report(findings, checked, self_test=args.self_test)


def report(findings: List[Finding], checked: int, self_test: bool = False) -> int:
    drift = [f for f in findings if f.severity == "substantive"]
    cosmetic = [f for f in findings if f.severity == "cosmetic"]

    lines = [f"Plugin sync check — {checked} paired file(s) compared"]
    for finding in drift + cosmetic:
        lines.append(str(finding))
    log_lines(lines)

    for finding in drift + cosmetic:
        print(str(finding))

    if self_test:
        # The synthetic pair must have been caught, or the model path is broken.
        if not any(f.path.startswith("SELF-TEST") and f.severity == "substantive"
                   for f in findings):
            print("\nSELF-TEST FAILED: injected drift was not reported as substantive.")
            return 1
        print("\nSelf-test OK — injected drift was caught.")
        real = [f for f in drift if not f.path.startswith("SELF-TEST")]
        if not real:
            print(f"Plugin sync OK — {checked} paired files, no real drift.")
            return 0
        return 1

    if drift:
        print(f"\nDrift found in {len(drift)} file(s) — the copies have diverged. "
              f"Details in {LOG_PATH.relative_to(REPO_ROOT)}")
        return 1

    if cosmetic:
        print(f"\nPlugin sync OK — {checked} paired files, "
              f"{len(cosmetic)} cosmetic difference(s), no behavioral drift.")
    else:
        print(f"Plugin sync OK — {checked} paired files, all byte-identical.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
