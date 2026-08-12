---
name: evaluate-results
description: |
  Use this skill when the user wants a Chronicle experiment's results
  judged against what was pre-registered — phrases like "what do the
  results say", "did it work", "evaluate the runs", "what worked and what
  didn't", "judge the variations against their hypotheses", "read the
  results of experiment X for me". It enumerates the variations + runs,
  pulls the real metrics (`chronicle.wandb_*` mediation tools,
  `execution_log` assets, attached variation reports), judges each
  variation against its pre-registered hypothesis / expected outcome, and
  produces the what-worked / what-didn't / what's-unexplained read.
  Reading without persisting anything is first-class ("just tell me what
  the results say"); on request it persists findings
  (`chronicle.record_finding`), lessons (`chronicle.record_lesson`), and a
  durable report via `chronicle-distill` (review-gated takeaways) or
  `chronicle-write-report` (immediate single-scope write-up). For deciding
  what to try next use `synthesis`; for prior-art surveys use
  `literature-review`.
---

# Evaluate results

The results-evaluation workflow: what worked, what didn't, and what's
unexplained — judged against what each variation **pre-registered**, not
against vibes. This is the user-side replacement for the managed
distillation agent's evaluation half: you (the local agent) pull the real
numbers and do the judging in-context; the user decides whether anything
gets persisted.

**Reading is first-class.** "Just tell me what the results say" ends at the
presented read — persisting findings, lessons, or a report is a separate,
explicitly requested step. This skill composes the chronicle plugin rather
than duplicating it: report mechanics stay in `chronicle-distill` /
`chronicle-write-report`, invoked by name. If the chronicle plugin's
skills/tools aren't available in this session, stop and tell the user to
install **both** plugins from the `methodic` marketplace.

## Inputs

- **`experiment_id`** — resolve: explicit arg → the experiment the session
  is working in → prompt.
- **`scope`** (optional) — all variations (default), one variation (by
  index or name), or a filtered subset ("the lr sweep", "the failed ones").
- **`persist`** (default `none`) — what to write back: `none` (read-only),
  `findings` (+ lessons where warranted), `report` (findings + a durable
  report via `chronicle-distill` or `chronicle-write-report`). Only
  escalate past `none` when the user asks.

## Workflow

1. **Enumerate.** `chronicle.get_experiment` for the variations in scope —
   skip retracted ones — and each variation's runs and their statuses.
   Collect each variation's pre-registration (`hypothesis` /
   `expected_outcome`) — this is the yardstick everything is judged
   against.

2. **Pull the real metrics.** For each variation: the `chronicle.wandb_*`
   mediation tools against its linked W&B run
   (`wandb_fetch_run_summary` for finals, `wandb_fetch_run_scalars` for
   curves, `wandb_list_run_artifacts` / `wandb_fetch_run_artifact` when
   artifacts matter), `execution_log` assets for runs that crashed or never
   logged, and any variation reports already attached
   (`chronicle.list_outputs` + `chronicle.load_asset`). A variation with no
   metrics is still a finding ("no linked W&B run") — record the absence,
   never invent numbers.

3. **Judge — the central step, in-context.** For each variation, compare
   what the metrics show against its pre-registered hypothesis and expected
   outcome. Judge from the **metrics**, not the run's succeed/fail status —
   a run that finished cleanly can still refute its hypothesis, and a crash
   can still be informative. Classify each: **working** (confirmed /
   improved on baseline), **partial** (mixed or conditional),
   **not_working** (refuted, regressed, or cleanly ruled out). A variation
   with no pre-registration gets judged against the experiment's hypothesis
   and flagged as un-pre-registered. Then assemble the read:
   - **What worked** — with the numbers.
   - **What didn't work** — negative results are the point, not an
     afterthought; if there are none, say so explicitly.
   - **What's unexplained** — results neither hypothesis nor lessons
     account for; these are `synthesis` fodder.

4. **Check the read against the record** — the stage-3 support call
   (`chronicle.evaluation_support`). Pass the findings you are about to
   record (same shape as `chronicle.record_finding`) and/or the assembled
   text. Chronicle assembles what your session cannot see — the sibling
   variations' config differences, how many runs and seeds actually
   finished, whether the cited run crashed, each variation's
   pre-registration, the lineage's active lessons, the metrics as logged,
   and the failure-mode catalog — and returns a verdict per claim, the
   assumptions each rests on, matched failure modes, and what it could
   **not** check.

   It is advisory and nothing is blocked. Present the flags with the read
   and resolve them before persisting: fix the claim, or say why the flag
   is wrong. Consult `chronicle.list_failure_modes` for the kinds of claim
   you are about to make — a claim that obviously trips one is cheaper to
   fix now than to adjudicate later. An empty or unavailable response is
   never an error: continue, exactly as with a missing
   `chronicle.report_activity`.

   Recording a finding **also** triggers an evaluation on its own, so this
   call is for seeing the verdict *before* the judgment lands.

5. **Optionally persist** (per `persist`, user-requested):
   - **Findings** — one `chronicle.record_finding` per variation judged:
     `{ status: working | partial | not_working, summary: <the signal in a
     sentence>, evidence_variation: <index> }`. The server keeps one
     finding per variation (re-recording replaces), and they land on the
     experiment's running summary + feed.
   - **Lessons** — a wrong assumption this evaluation surfaced is a
     `chronicle.record_lesson` (list first to dedup; check existing lessons
     via `chronicle.list_lessons` before judging, too — contradicting one
     without addressing it is a factual blocker).
   - **Reasoning errors** — when the *researcher* corrects a mistake in your
     read, file the pattern as well as the lesson (`report-reasoning-error`,
     `user_confirmed: true`). A human validating an instance in context is
     the best signal the failure-mode catalog gets, and it evaporates when
     the session ends.
   - **The durable report** — invoke **`chronicle-distill`** for the
     cross-variation `takeaways_report` (review-gated: it sits pending
     until the owner approves, which is also what unblocks conclude) or
     **`chronicle-write-report`** for an immediate single-scope write-up.
     Those skills own the report mechanics; don't re-implement them here.
     Never conclude the experiment yourself — approval and conclude are the
     owner's calls.

6. **Report the milestone.** `chronicle.report_activity` —
   `{ "experiment_id": …, "title": "Evaluated results across N variations
   (M runs)", "summary_md": <the one-paragraph read>, "asset_ids":
   [<report asset, if one was written>] }`. One activity per evaluation
   pass, not per variation. If `chronicle.report_activity` isn't in your
   tools list, the server predates activity reporting (it ships with the
   methodic#642 chronicle-server release) — say so and continue; a
   read-only evaluation losing its feed row is never an error.

## After the skill completes

Present, in order:

1. The headline: one sentence on where the experiment stands against its
   hypothesis.
2. The per-variation table: variation (name or `v<index>`), what it
   pre-registered, what the metrics showed, judgment
   (working / partial / not_working).
3. What didn't work, and what's unexplained — called out even when the
   headline is a success.
4. Any verdicts the evaluation support returned — what it flagged, what it
   could not check, and how you resolved each. A flag you disagree with is
   worth stating rather than dropping.
5. What was persisted (finding count, lessons, reasoning errors, report
   asset id + that a distilled takeaways report is **pending owner
   review**), or that nothing was, by request.

## Failure modes

- **Chronicle plugin absent**: stop; tell the user to install both
  `chronicle` and `research` from the `methodic` marketplace.
- **W&B mediation unavailable for a variation** (no linked run, or the
  tools error): record "no metrics" for it and keep going — never fill the
  table with invented numbers.
- **No pre-registration anywhere** (legacy experiment): judge against the
  experiment-level hypothesis, say plainly that per-variation judgments are
  unanchored, and suggest pre-registering future variations (the
  `synthesis` skill enforces it).
- **`record_finding` / `record_lesson` 403 or unavailable**: non-fatal —
  the read stands; surface it and continue.
- **`chronicle.evaluation_support` unavailable** (older server) or a 503
  (no LLM resolved for this principal): non-fatal — say the read was not
  checked against the record and continue. Never present an unchecked read
  as a checked one.
- **Nothing in scope** (zero non-retracted variations, or no runs yet):
  say so rather than evaluating an empty record.

## Requires

- The **chronicle plugin** installed alongside this one (the `chronicle.*`
  MCP tools + the `chronicle-distill` / `chronicle-write-report` skills).
- Credentials resolved from `~/.methodic` (or `CHRONICLE_API_KEY`
  exported).
- No `git`, no local checkout — this skill reads the record and (only on
  request) writes findings/lessons/reports via the platform.
