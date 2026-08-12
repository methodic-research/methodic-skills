# `/.well-known/skills/` — publishing these skills to Hermes Agent

[Hermes Agent](https://github.com/NousResearch/hermes-agent) installs skills
from any domain exposing `/.well-known/skills/index.json`. This directory holds
the two generated artifacts that make **every** skill in this repo installable
that way, from `https://methodiclabs.ai`:

| File | What it is |
| --- | --- |
| `skills/index.json` | The index Hermes reads. Generated from the skills themselves. |
| `skills/cloudflare-redirects.txt` | The `_redirects` block the website needs. Paste into `chronicle-web`'s `home/public/_redirects`. |

Both are produced by `scripts/gen_wellknown_index.py`, and CI fails if either
is stale — a skill added or renamed without republishing is a skill nobody can
install.

```bash
python3 scripts/gen_wellknown_index.py           # regenerate after adding/renaming a skill
python3 scripts/gen_wellknown_index.py --check   # what CI runs
```

## Why this exists (and why not `hermes skills tap`)

A tap is **one repo plus one base path**, and `tap add` refuses a second entry
for the same repo. This repo keeps its skills in two roots — `skills/` and
`research-plugin/skills/` — so a tap reaches the chronicle skills and can never
reach the four research ones. The well-known index has no such limit: one index,
all of them.

## The site hosts no skill content

Hermes derives every fetch URL from the index URL — `{index_dir}/{name}/SKILL.md`
— and an index entry cannot name a different host (its `files` are validated as
relative paths). But Hermes' fetcher **follows redirects**, up to 5 hops, and
re-validates each one. So `methodiclabs.ai` publishes only redirects:

```
/.well-known/skills/index.json              → raw.githubusercontent.com/…/.well-known/skills/index.json
/.well-known/skills/chronicle-status/SKILL.md → raw.githubusercontent.com/…/skills/status/SKILL.md
```

The skills stay single-source in this repo; the website never holds a copy. The
index itself is served from here too, so it ships with the skills it describes
rather than drifting in a second repo.

One line per skill, not a wildcard: a skill's **name** is its frontmatter `name`
(`chronicle-status`), which is not its **directory** (`status`), and the mapping
isn't uniform (`methodic-feedback` → `feedback`, `sagemaker` → `sagemaker`). The
names are the install identifiers, so they stay as-is — they're what was checked
for collisions against Hermes' bundled and optional skills.

## Using it

```bash
hermes skills search https://methodiclabs.ai
hermes skills install https://methodiclabs.ai/.well-known/skills/chronicle-status
hermes skills install https://methodiclabs.ai/.well-known/skills/synthesis
```

Prefer `skills.external_dirs` if you have a checkout — it needs no publishing
step and `git pull` is the update path. The well-known route is for installing
without one.
