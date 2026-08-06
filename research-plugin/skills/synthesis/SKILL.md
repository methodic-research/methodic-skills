---
name: synthesis
description: |
  Use this skill when the user wants the aggregate ideation workflow on a
  Chronicle experiment (or a research prompt / area) — deciding what to try
  next and queueing it — phrases like "what should we try next", "run a
  synthesis pass", "propose the next variations", "plan and queue the next
  round", "keep the research moving on experiment X". It grounds in the
  experiment record (lineage, variations, runs, lessons), invokes
  `evaluate-results` for the what-worked read and `literature-review` when
  external grounding is needed, then drafts pre-registered proposals
  (hypothesis + expected outcome required) and — only for the ones the user
  accepts — queues execution: `chronicle.propose_variation` for config-only
  changes, the variation-authoring skills first for code changes,
  `chronicle-propose-experiment` for a child experiment. The human is the
  approval gate — nothing is committed or queued without explicit
  acceptance. For the evaluation alone use `evaluate-results`; for a survey
  alone use `literature-review`; for turning one already-formed hypothesis
  into an experiment use `chronicle-propose-experiment` directly.
---

# Synthesis

The ideation workflow: ground in what's been tried and what the literature
says, then propose — and, on acceptance, queue — what to try next. This is
the user-side replacement for Chronicle's managed synthesis agent: **you**
(the local agent) do the grounding, evaluation, and proposal drafting, and
**the user** is the reviewer the old multi-agent proposal loop is replaced
by. Nothing is committed or queued without their explicit acceptance.

This skill composes rather than duplicates: the evaluation half is the
`evaluate-results` skill, the survey half is `literature-review`, and every
platform mechanic (experiment create, variation authoring, citation
registration) is a chronicle-plugin skill or `chronicle.*` MCP tool invoked
by name. If the chronicle plugin's skills/tools aren't available in this
session, stop and tell the user to install **both** plugins from the
`methodic` marketplace (`/plugin install chronicle`, `/plugin install
research`) — this skill cannot run without the mechanics layer.

## Inputs

- **`experiment_id`** — the anchor experiment. Resolve: explicit arg → the
  experiment the session is already working in → prompt. Alternatively a
  **research prompt / area** with no experiment yet — then the propose step
  routes through `chronicle-propose-experiment` instead of new variations.
- **`focus`** (optional) — a steer for this pass ("push on the
  regularization angle", "find why the wide runs plateau").
- **`survey`** (default: agent judgment) — whether to run the
  `literature-review` leg. Default to running it for a new area, a plateau,
  or baseline hunting; skip it when the record alone answers the question.

## Workflow

1. **Ground.** Load the experiment record: `chronicle-status` for the run
   snapshot, `chronicle-history-explorer` / `chronicle.get_lineage` for the
   lineage subgraph, and `chronicle.list_lessons` for the active research
   lessons (own + inherited). Lessons are corrected assumptions — a proposal
   that contradicts one without addressing it head-on is dead on arrival.

2. **Evaluate.** Invoke the **`evaluate-results`** skill for the
   what-worked / what-didn't / what's-unexplained read across the
   variations, judged against their pre-registered hypotheses. Its output
   is the evidence base for the proposals.

3. **Survey.** When external grounding is needed (per `survey` above),
   invoke the **`literature-review`** skill scoped to the gap the
   evaluation exposed. Citations it registers land on the anchor experiment
   as inputs; papers surfaced along the way that inform a proposal are
   registered via `chronicle.register_publication` + `chronicle.link_asset`
   (discovered-via-agent-search citations), not just named in prose.

4. **Propose.** Draft the next variations — or a child experiment, when the
   direction outgrows the current one — each with an explicit
   **hypothesis** and **expected outcome**. These pre-registration fields
   (`variations.hypothesis` / `expected_outcome`) are **required** on every
   proposal, exactly as the managed synthesis loop required them: a
   proposal states what it believes and what result would confirm or refute
   it *before* the run, so `evaluate-results` has something to judge
   against later. Present the proposals to the user as a compact list
   (change, hypothesis, expected outcome, cost/risk note) and **wait for
   their selection**. The human is the approval gate — act only on the
   proposals they accept; drop or park the rest.

5. **Queue** each accepted proposal (see "Queueing execution" below).
   New-experiment proposals route through `chronicle-propose-experiment`
   (which owns hypothesis_report + research-prompt mechanics).

6. **Report.** One `chronicle.report_activity` call for the pass —
   `{ "experiment_id": …, "title": "Synthesis: proposed N variations,
   queued M", "summary_md": <one-paragraph digest>, "asset_ids": [...] }` —
   so collaborators' feeds show what this local agent did. Milestones, not
   turns: one activity per pass, not a progress ticker. If
   `chronicle.report_activity` isn't in your tools list, the server
   predates activity reporting (it ships with the methodic#642
   chronicle-server release) — say the activity wasn't recorded and
   continue; never fail the pass over it.

## Queueing execution

Execution queuing is the **worker job queue**: a run on a
`menlo_park_persistent` experiment enqueues at creation and a menlo-park
daemon claims it; other runner types provision per run. There is no agent
in between anymore — which means **the caller (you) owns code capture**
before anything is queued:

- **Config-only change** (parent's code, new config): call
  **`chronicle.propose_variation`** with the inline `config_yaml` plus the
  proposal's `hypothesis` and `expected_outcome`. It is the single-call
  enqueue: creates the variation, **commits it**, and **creates its run** —
  the variation rides the parent/seed code ref, and the only thing between
  the proposal and a training worker is the queue itself.
- **Code change**: author the code first — `chronicle-author-variation`
  (agent applies the change in the managed repo), `chronicle-fork-variation`
  (fork a committed variation), or `chronicle-bundle-variation` (external
  code) — then commit and create the run (`chronicle-run-variation` for the
  BYO-execution path where this agent trains it itself). Never queue a
  variation whose code isn't captured: a variation must be committed (spec
  locked, code ref/bundle bound) before its run exists.

Commit here is the **variation** commit that queueing requires, done on an
explicitly accepted proposal — never commit the *experiment*, conclude
anything, or blanket-queue unaccepted proposals on your own initiative.

## After the skill completes

Tell the user:

1. The evaluation headline (one line per variation judged) and, if
   surveyed, the literature gap statement.
2. Each proposal with its hypothesis + expected outcome, marked
   accepted-and-queued / parked / dropped.
3. For queued work: variation index/name and run id per proposal, and that
   the runs are in the worker queue (or provisioning, per runner type).
4. The activity that was reported (or that the server doesn't support
   activity reporting yet).

## Failure modes

- **Chronicle plugin absent** (no `chronicle.*` tools, chronicle skills not
  installed): stop; tell the user to install both `chronicle` and
  `research` from the `methodic` marketplace.
- **`propose_variation` rejected — experiment not committed**: variations
  can only be committed once the experiment is; ask the user whether to
  commit the experiment (their call — never auto-commit) and retry after.
- **`propose_variation` rejected — missing hypothesis / expected outcome**:
  pre-registration is required; fill the fields from the proposal draft and
  retry — never stub them with placeholders.
- **Proposal contradicts an active lesson**: surface the lesson and either
  rework the proposal or (with the user) argue the evidence and retire the
  lesson via `chronicle.retire_lesson` — don't queue silently against it.
- **`report_activity` unavailable or 403**: non-fatal — the queued work
  stands; say the feed wasn't updated and continue.

## Requires

- The **chronicle plugin** installed alongside this one (its skills + the
  bundled `chronicle.*` MCP tools do every platform mechanic here).
- Credentials resolved from `~/.methodic` (or `CHRONICLE_API_KEY`
  exported).
- A configured literature MCP only if the `literature-review` leg runs —
  it degrades to internal-only without one.
