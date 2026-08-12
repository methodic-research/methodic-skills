---
name: chronicle-run-variation
description: |
  Use this skill when an agent/runner that brought its OWN training code wants
  to EXECUTE a committed Chronicle variation and record the run — phrases like
  "run this variation", "train variation 2 and report it", "execute the
  committed variation and log to W&B". It is training-AGNOSTIC: it drives the
  Chronicle run lifecycle (start → succeed/fail, with heartbeats) and, when W&B
  is available, links the run's W&B run so distillation can pull the metrics.
  The training itself — a tiny CPU fit or a huge multi-GPU architecture — is the
  caller's; this skill never writes or contains it. Create + commit the
  variation first with chronicle-author-variation, and distill the results
  afterward with chronicle-write-report. This is the BYO-agent (self-run)
  counterpart to Chronicle's managed Menlo Park workers: the agent runs the
  training, Chronicle records the run.
---

# Run variation

Execute one **committed** variation's run from your own runner and record it in
Chronicle. The end state is: the variation's run marked `running` → `succeeded`
(or `failed`), and — when W&B is in play — a `wandb_run` pointer linked to the
run so `chronicle-write-report` (or any distiller) can fetch the real metrics.

Before triggering, call the stage-2 support endpoint
(`chronicle.training_support`, or `chronicle.experiments.training_support`).
It currently returns an empty `advice_md` with `stub: true` — calling it
anyway is the point: the slot is reserved so config sanity against what this
lineage already ran, known-bad hyperparameter combinations, and cost/queue
reality can arrive later without this skill changing
(autoresearch-assist.md §6). An empty or unavailable response is never an
error.

Also ask what has already gone wrong here — `chronicle.suggest_operational_checks`
(SDK: `chronicle.operational_checks.suggest`) returns checks distilled from
other agents' execution failures on this experiment, team, org, and the
platform. Run them before `run.start`, not after the training has burned an
hour. An empty `checks` list means the catalog has nothing relevant, which is
a real answer: proceed.

**This skill owns two things only: triggering the run lifecycle, and linking
W&B if available.** It is deliberately agnostic to the training. Whatever your
code does — a five-step numpy fit or a week-long transformer pretrain — wraps
the same way; the skill never prescribes or contains it. (If you are NOT running
the training yourself and want Chronicle to dispatch it to a managed Menlo Park
worker, that is the provisioning path, not this skill.)

## Inputs

- **`experiment_id`** — the Chronicle experiment UUID. Resolve in order:
  explicit arg → `methodic` config (`~/.config/methodic/current_experiment`) →
  detect from cwd → prompt.
- **`variation`** — the committed variation index (or plaintext name) to run.
  Required. Resolve a name → index before the SDK calls. **Run only the
  variations you were asked to** — this is what keeps a driver's run-wait
  bounded when more variations exist than you intend to execute.
- **`train`** — the caller's training, as a callable/closure or an inline block
  the agent writes. Opaque to the skill. It should log its loss curve / metrics
  to the W&B run from step 2 (when W&B is available).
- **`run`** (optional) — the run number. A freshly committed variation has a
  pending **run 0** (created at commit); default to it. To re-execute a
  variation whose run 0 is already terminal, `variations.resume` returns a fresh
  run number.

## Workflow

```python
from methodic import Chronicle
import os

chronicle = Chronicle.from_env()  # CHRONICLE_SERVER_URL + CHRONICLE_API_KEY

# 0. Pre-flight: what has bitten other agents doing this? Cheap, and the
#    failures it catches (unset key, wrong scope, missing quota) are the ones
#    that otherwise surface an hour into training.
plan = chronicle.operational_checks.suggest(
    f"about to execute variation {variation} of experiment {experiment_id}",
    experiment_id=experiment_id,
)
for c in plan["checks"]:
    ...  # run it yourself, or hand the list to a sub-agent, before step 3

# 1. Resolve the run to execute. A just-committed variation has a pending run 0.
run_number = 0  # or: chronicle.variations.resume(experiment_id, variation).run

# 2. (If W&B is available) start the W&B run BEFORE Chronicle's run-start so we
#    can link it. `wandb` reads WANDB_API_KEY from the env. Use the experiment's
#    wandb_project when it set one. Skip this whole block if there's no W&B —
#    the run still gets triggered + marked, just without a metrics pointer.
wandb_link = {}
wb = None
if os.environ.get("WANDB_API_KEY"):
    import wandb
    exp = chronicle.experiments.get(experiment_id)
    wb = wandb.init(
        project=getattr(exp, "wandb_project", None) or f"methodic-{experiment_id}",
        name=f"{experiment_id}/v{variation}/r{run_number}",
        config={"experiment_id": experiment_id, "variation": variation},
    )
    wandb_link = {
        "wandb_run_id": wb.id,
        "wandb_entity": wb.entity,
        "wandb_project": wb.project,
        "wandb_dashboard_url": wb.url,
    }

# 3. Mark the run started, linking the W&B run (if any). Chronicle records the
#    wandb_run pointer (entity/project/run_id) so distillation can resolve it.
run = chronicle.run(experiment_id, variation, run_number)
run.start(**wandb_link)

# 4. *** THE CALLER'S OWN TRAINING RUNS HERE *** — opaque to this skill.
#    Log loss curves / metrics to `wb` as it trains; for long runs call
#    `run.heartbeat()` periodically so Chronicle doesn't mark it `lost`.
try:
    # ...the caller's training executes, e.g. each step:
    #     wb.log({"loss": loss, "step": step}); run.heartbeat()  # when wb/long
    if wb is not None:
        wb.finish()
    run.succeed()
    print(f"Ran variation {variation} run {run_number}: succeeded"
          + (f" (W&B {wb.url})" if wb is not None else " (no W&B)"))
except Exception as e:
    if wb is not None:
        wb.finish(exit_code=1)
    run.fail(reason=f"crash: {e}")
    # If it failed for an *execution* reason a check could have caught — a
    # missing credential, an unset env var, the wrong scope — file it so the
    # check gets written. Not for the training's own numerical failures:
    # a diverging loss is a result, not a mistake.
    chronicle.reasoning_errors.report(
        f"variation {variation} run {run_number} failed to execute",
        kind="operational",
        description=f"{type(e).__name__}: {e}",
        experiment_id=experiment_id,
        variation=variation,
    )
    raise
```

## W&B is optional, but it's how distillation gets numbers

If `WANDB_API_KEY` is set, link the W&B run at `run.start` (step 3). That
records a `wandb_run` pointer (entity / project / run_id + dashboard URL) on the
Chronicle run. `chronicle-write-report` reads that pointer and fetches the
metrics **directly from W&B with its own key** — so the loss curves you log here
are what the distillation writes up. With no W&B, the skill still triggers and
marks the run; there's just no metrics pointer to distill from.

## After the skill completes

Tell the user, per variation run:
1. `(experiment_id, variation, run)` and its terminal status.
2. The W&B run URL if one was linked (and that the metrics are fetchable for
   distillation).
3. The next step: `chronicle-write-report` to distill the run(s) into a
   `takeaways_report`.

## Failure modes

- **Variation not committed / no run 0** — a run can only start on a committed
  variation. Commit it (`chronicle-author-variation`) first; surface the
  Chronicle error verbatim.
- **`run.start` rejected** — the caller lacks `Trigger`/`Write`, or the run is
  already terminal. For a re-run use `variations.resume` to get a fresh run
  number rather than re-starting a terminal run.
- **Training raised** — always reach `run.fail(reason=...)` (and
  `wb.finish(exit_code=1)`) in the `except` so the run reaches a terminal state
  promptly instead of timing out as `lost`; then re-raise.
- **W&B unavailable** — no `WANDB_API_KEY`: skip the W&B block; the run is still
  triggered + marked (no metrics pointer). Do **not** pass empty/placeholder
  W&B ids — omit them so no half-linked pointer is recorded.
- **Long training** — without periodic `run.heartbeat()` Chronicle marks the run
  `lost` after the heartbeat timeout. Heartbeat from the training loop.
- **Any of the above bit you** — after recovering, file it with
  `report-agent-error` as `kind="operational"`. The catalog that
  `suggest_operational_checks` reads only knows what agents report; a failure
  you fixed silently will find the next agent too.

## Requires

- `pip install methodic-research` (≥ the `runs.start` W&B-link release)
- `CHRONICLE_API_KEY` exported (or `methodic auth login` already done)
- `WANDB_API_KEY` exported **only if** linking W&B (optional)
- No `git` — this skill records a run via the API; the training is yours to run.
