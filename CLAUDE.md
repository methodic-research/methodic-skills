# Working in this repo

Skills here are consumed by four harnesses (Claude Code, Codex, Claude Desktop,
Hermes Agent) from **five** places. Most of the rules below exist because a
change that updates only one of them ships a skill that is silently stale — or
missing — for somebody.

## Adding, renaming, or removing a skill

Do all of these in the same change:

1. **Update both copies.** Every skill exists twice: `skills/` +
   `research-plugin/skills/` (Claude Code) and the `plugins/` mirrors (Codex).
   The `mcp/` server is duplicated into `plugins/chronicle/mcp/` the same way.
   Nothing generates one side from the other.
   → `python3 e2e/check_plugin_sync.py` (CI job `sync`) fails on drift.

2. **Regenerate the Hermes publishing artifacts.** They are derived from the
   skills themselves, so a new or renamed skill that isn't republished is a
   skill nobody can install from `methodiclabs.ai`.

   ```bash
   python3 scripts/gen_wellknown_index.py
   ```

   → `--check` runs in CI (job `lint`) and fails when either artifact is stale.

3. **Republish the website block if it changed.** If step 2 modified
   `.well-known/skills/cloudflare-redirects.txt`, that block must also land in
   `methodic-research/methodic` → `chronicle-web/home/public/_redirects`,
   between the `BEGIN/END generated:` markers. **This is the one step no CI in
   this repo can catch** — the file lives in another repo. A push to `main` that
   changes the fragment opens a tracking issue automatically
   (`.github/workflows/republish-wellknown.yml`); close it with the companion PR.

4. **Mind the name.** A skill's frontmatter `name` — not its directory — is its
   identity in every harness *and* its install identifier in Hermes' shared hub.
   Keep the `chronicle-` / `methodic-` prefixes: they're what keeps these from
   colliding with other publishers' skills. The generator rejects duplicates.

## Editing an existing skill

Only rule 1 applies (both copies), unless you changed the frontmatter `name` or
`description` — those feed the Hermes index, so rerun step 2.

## Before pushing

```bash
python3 e2e/lint_skills.py                  # frontmatter + no stale API surface
python3 scripts/gen_wellknown_index.py --check
python3 e2e/check_plugin_sync.py            # zero model calls when the trees match
```

`e2e/run_skills_e2e.py` needs secrets and runs against deployed ci; leave it to
CI unless you're changing the flow it drives.

## Conventions

- **Skills are single-file** (`SKILL.md`) today. Support files under
  `references/` / `scripts/` are supported end to end — the Hermes index and
  redirect table enumerate them — but nothing here uses them yet.
- **Descriptions are trigger text**, not summaries: lead with the phrases a user
  would actually say. Hermes truncates at 1024 characters, so front-load.
- See [`.well-known/README.md`](.well-known/README.md) for how the Hermes
  publishing path works and why the site hosts no skill content.
