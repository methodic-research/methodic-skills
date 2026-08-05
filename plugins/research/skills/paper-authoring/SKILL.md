---
name: paper-authoring
description: |
  Use this skill when the user wants a paper written from a Chronicle
  experiment's record — phrases like "draft the paper", "write this up as
  a LaTeX paper", "turn the experiment into a paper", "attach the paper to
  the experiment", "revise the paper with the new results", "get this
  ready for Overleaf / arXiv". It gathers the approved record (takeaways +
  variation reports, figure image assets, lessons, linked citations),
  authors the LaTeX locally in the researcher's own working tree /
  template, and attaches the source via
  `POST /v1/experiments/{id}/papers` so Chronicle compiles it
  (chronicle-tex) into an `imported_report` on the experiment — re-attach
  on meaningful revisions; each attach is a recorded snapshot. Publishing
  (Overleaf, arXiv, a journal) is the researcher's own git remotes —
  Chronicle holds the record, not the venue. For the in-app Markdown
  write-up use `chronicle-write-report`; for the cross-variation synthesis
  that feeds the paper use `evaluate-results` / `chronicle-distill`.
---

# Paper authoring

The publication workflow: author a LaTeX paper from what the experiment
record actually says, and put the source on the record so Chronicle
compiles and preserves it. This is the user-side replacement for the
managed paper agent and its Overleaf tab: the paper is written **locally**,
in the researcher's own working tree and template, by this session — and
published wherever the researcher publishes, with their own credentials.

Chronicle's role is the **record**: the experiment supplies the substance
(approved reports, figures, lessons, citations), and the finished source
goes back as an attached snapshot the platform compiles. If the chronicle
plugin's skills/tools aren't available in this session, stop and tell the
user to install **both** plugins from the `methodic` marketplace.

## Inputs

- **`experiment_id`** — the experiment the paper reports. Resolve:
  explicit arg → the experiment the session is working in → prompt.
- **`template` / working tree** (optional) — the user's LaTeX template or
  an existing paper directory to work in; otherwise start a clean
  conventional layout (`main.tex`, `refs.bib`, `figures/`).
- **`venue` conventions** (optional) — target style (page limit, class
  file); shapes the draft, not the workflow.

## Workflow

1. **Gather the record.** `chronicle.get_experiment` for the hypothesis +
   state, `chronicle.list_outputs` + `chronicle.load_asset` for the
   **approved** reports (the takeaways report and variation reports are
   the substance — a takeaways report still pending review is a draft, not
   record; tell the user if the paper would lean on one), figures (image
   assets — download the **PDF or SVG** rendition of each figure for LaTeX,
   not the PNG preview), `chronicle.list_lessons` for the corrected
   assumptions the paper must not contradict, and the linked citations
   (`chronicle.search_publications` + the experiment's linked publication
   inputs) for the bibliography.

2. **Author locally — the central step.** Write the LaTeX in the working
   tree, under the same source conventions the managed paper agent held:
   - **Cite registered publications** — every `\cite` resolves to a
     publication registered on the experiment; a source worth citing that
     isn't registered yet goes through `chronicle-publications`
     (`chronicle.register_publication` + `chronicle.link_asset`) so the
     bibliography and the experiment's citation record agree.
   - **Reference figures by asset** — use the downloaded renditions of the
     experiment's figure assets; note each figure's asset id in a comment
     (`% chronicle-asset: <id>`) so provenance survives the source.
   - **State negative results plainly** — what didn't work is part of the
     contribution, exactly as in the reports the paper draws from; don't
     launder it out.
   - **Numbers come from the record** — metrics quoted in the paper trace
     to the reports/W&B pulls, never from memory. `evaluate-results` is
     the skill to run first if the record hasn't been judged yet.
   Show the user the draft (or the diff, on a revision) — the paper is
   theirs; iterate here until they're happy.

3. **Record — attach the source.** With the user's go-ahead, snapshot the
   source onto the experiment:
   1. Zip the paper directory (relative paths preserved; a single
      self-contained `main.tex` can skip the zip) and upload it via
      `chronicle.upload_asset` with `asset_type: "latex_source"`.
   2. `POST /v1/experiments/{id}/papers` `{ "source_asset_id": "<the
      latex_source id>", "main_file": "main.tex" }` (main_file when the
      archive holds several `.tex`). Chronicle compiles it async
      (chronicle-tex) into an **`imported_report`** linked to the
      experiment — extracted and searchable like any imported paper. If no
      MCP/SDK wrapper for the papers endpoint is available in this
      session, call the endpoint directly with the standard `~/.methodic`
      credentials — and file the missing wrapper via `methodic-feedback`.
   3. **Re-attach on meaningful revisions** — each attach is a recorded
      snapshot, compiled and kept; the record of the paper evolves with
      the paper. Don't attach every typo fix; do attach every version the
      user would want to be able to point at.

4. **Publish wherever — outside Chronicle.** Overleaf is just a git remote
   the researcher holds credentials for: if they want it there, push the
   working tree with plain `git` to their Overleaf project's remote (they
   supply the URL/credentials; never ask them to paste secrets into chat —
   git's own credential handling does this). Same for arXiv or a journal
   submission — Chronicle records the paper; it is not the venue and has
   no platform integration to configure.

5. **Report the milestone.** `chronicle.report_activity`
   `{ "experiment_id": …, "title": "Paper draft attached (v<N>)",
   "summary_md": <one-line scope of the revision>, "asset_ids":
   ["<imported_report id>"] }` — one activity per attached draft, not per
   editing turn. If `chronicle.report_activity` isn't in your tools list,
   the server predates activity reporting (it ships with the methodic#642
   chronicle-server release) — say so and continue.

## After the skill completes

Tell the user:

1. Where the source lives locally (path) and what was drafted/revised.
2. The `latex_source` asset id and the `imported_report` the attach
   created — with compile pending async; where to see it on the
   experiment once compiled (and the compile-failure retry path: fix the
   source, re-attach).
3. The citation ledger: which `\cite` keys map to which registered
   publications, and any sources cited in prose that still need
   registering.
4. If pushed to Overleaf/elsewhere: the remote it went to. If the
   takeaways report was still pending review, repeat that the paper leans
   on an unapproved draft.

## Failure modes

- **Chronicle plugin absent**: stop; tell the user to install both
  `chronicle` and `research` from the `methodic` marketplace.
- **No approved takeaways report** (or none at all): the paper would be
  built on unreviewed material — say so; offer `evaluate-results` /
  `chronicle-distill` first, and let the user decide whether to draft
  anyway from the raw record.
- **Papers endpoint 404** (`POST /v1/experiments/{id}/papers` not on this
  server): the server predates the attach path — deliver the paper locally,
  say the snapshot couldn't be recorded, and suggest a server upgrade.
- **Compile failure on the attach** (asset abandoned with
  `compile_error`): surface the log tail, fix the source, re-attach — the
  retry is a fresh attach, not a mutation.
- **Figure asset has no PDF/SVG rendition**: use the best rendition that
  exists and flag the print-quality gap rather than silently embedding a
  low-res preview.
- **Overleaf push rejected**: credentials/remote are the researcher's own;
  surface git's error verbatim and leave publishing to them — never work
  around it by asking for their credentials in chat.

## Requires

- The **chronicle plugin** installed alongside this one (the `chronicle.*`
  MCP tools; `chronicle-publications` for late citations).
- Credentials resolved from `~/.methodic` (or `CHRONICLE_API_KEY`
  exported).
- A local LaTeX toolchain is **optional** (Chronicle compiles the attached
  source server-side); handy for local preview iterations.
- `git` only if the user wants the tree pushed to their own
  Overleaf/remote.
