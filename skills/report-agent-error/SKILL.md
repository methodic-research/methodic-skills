---
name: report-agent-error
description: |
  Use this skill when an agent got something wrong and it could recur —
  either the REASONING (a bad inference about the research) or the
  EXECUTION (a missing credential, an unset env var, steps in the wrong
  order, the right call against the wrong scope). Formerly
  report-reasoning-error; it now covers both kinds. PROACTIVELY, without
  being asked, in three situations. (1) The researcher identifies or
  confirms a mistake in your reasoning or your execution: record a research
  lesson AND file a report with user_confirmed. (2) You notice yourself or a
  peer making a generalizable mistake of either kind. (3) Something failed
  operationally and a check would have caught it — file it so the check gets
  written. Also on request ("report that"). NOT for platform bugs (use
  methodic-feedback) and NOT for a wrong assumption specific to one
  experiment's data (that is a research lesson).
---

# Report an agent error

Chronicle keeps **two** catalogs, because agents get two distinguishable
things wrong:

- the **failure-mode catalog** — ways an AI reasons badly about research
  (confounded comparisons, single-seed generalization, treating a crashed run
  as a refutation). It is what the platform's own evaluation checks findings
  against.
- the **operational catalog** — runnable checks distilled from execution
  failures ("verify CHRONICLE_API_KEY is exported before invoking"). It is
  what `chronicle.suggest_operational_checks` draws on.

Both only get better if the instances reach them.

## Which kind — one question

> **Would the conclusion have been wrong even with a perfect run?**
> Yes → `reasoning`. No — the run failed, or succeeded at the wrong thing,
> and better thinking wouldn't have helped → `operational`.

Examples that are **operational**: forgot to export the API key; committed
the variation before linking its inputs; ran against the wrong org; hit a
quota nobody checked for; used the flag that means the opposite.

Examples that are **reasoning**: credited the learning rate when three knobs
differed; generalized from one seed; called an approach dead from a run that
never converged.

**You will get this wrong sometimes, and that is expected.** File it with
your best guess rather than agonizing — the split is genuinely blurry at the
edges, and `chronicle.reasoning_errors.reclassify` (or the reclassify
endpoint) is the correction path. A report filed under the wrong kind is far
better than one not filed.

Reporting is deliberately cheap. The bar is "this looked wrong", the call
returns immediately, and validation runs behind it. **Do not** weigh whether a
report is worth filing — that judgment is what validation and human curation
are for, and an unfiled report teaches nobody.

## Which sink — the three-way split

| The thing that's wrong | Sink | Skill |
|---|---|---|
| How the agent *reasoned* — a pattern that could recur anywhere | `kind="reasoning"` | **this skill** |
| How the agent *executed* — a step another agent will repeat | `kind="operational"` | **this skill** |
| A wrong assumption about *this research* (this dataset, this eval set) | `research_lessons` | `research-lessons` |
| The *platform* (SDK/MCP/API gap or bug) | `feedback` | `methodic-feedback` |

The last row is the one that trips agents up: if the tool did the wrong thing,
that is a platform bug. If the tool did what you asked and what you asked was
wrong, that is operational — yours.

They are not exclusive: a user-confirmed mistake is usually **both** a lesson
(the local instance) and a report (the pattern). See Contract 2.

## Contract 0 — ask before you act

Before something risky or unfamiliar — a bulk upload, a first run against a
new org, anything touching credentials or quotas — ask what has already gone
wrong for other agents:

```python
plan = chronicle.operational_checks.suggest(
    "about to bulk-upload 400 assets to a new org",
    experiment_id=experiment_id,   # widens to this experiment's own checks
)
for c in plan["checks"]:
    ...  # run it, or hand the list to a sub-agent
```

An empty `checks` list is a real answer — the catalog has nothing relevant
and `unmatched` says so. It will not pad with generic advice, so an empty
result means proceed, not "the tool is broken".

MCP-native: `chronicle.suggest_operational_checks`.

## Contract 1 — read the catalog before you conclude

Before drawing conclusions or writing them up, list the catalog and check the
claims you are about to make against it:

```python
modes = chronicle.failure_modes.list()          # active, human-confirmed only
# or, MCP-native: chronicle.list_failure_modes
```

For operational work the equivalent is `chronicle.operational_checks.list(q=…)`
— search by the **symptom** you are seeing ("401 on the first call"), not by
a name you would have to already know.

Each entry says what the mode is, how it shows up, and what to do instead. A
claim that obviously trips one is worth fixing *before* it is recorded — that
is cheaper for everyone than a flagged finding the researcher has to
adjudicate.

## Contract 2 — report what the researcher confirms

When the **researcher identifies or confirms a mistake** — in your reasoning
or in how you ran something — a human has already done the validation, on a
real instance, in context. That is
the highest-quality signal this system gets and it must not evaporate when the
session ends. File **both**, without being asked:

```python
# 1. The local instance — always. (A lesson is per-experiment; it stays a
#    lesson whichever kind the report turns out to be.)
lesson = chronicle.experiments.record_lesson(
    experiment_id,
    title="A crashed run is not evidence against the hypothesis",
    body={                          # the four fields — see `research-lessons`
        "believed": "the v3 result refuted the hypothesis",
        "correction": "that run OOM'd at step 200; it never tested anything",
        "evidence": "run 1 exit 137, no eval past step 200",
        "instead": "check terminal status before reading a run as evidence",
    },
    origin="researcher_correction",
)

# 2. The pattern — when it could recur on a different experiment.
report = chronicle.reasoning_errors.report(
    "treated a crashed run as a refutation of the hypothesis",
    kind="reasoning",               # or "operational" — see "Which kind"
    description="v3 run 1 OOM'd at step 200; I recorded not_working from it",
    experiment_id=experiment_id,
    user_confirmed=True,            # a human confirmed the instance
    lesson_id=lesson["id"],
)
print(f"reported {report['kind']} error: treated a crashed run as a refutation ({report['id']})")
```

`user_confirmed=True` puts the report at a higher trust tier: a model may not
reject it, because a model does not get to overrule the researcher about what
happened. It can still decline to *generalize* it — that leaves the report for
a human curator, with the model's dissent recorded beside it.

**Only set `user_confirmed` when a human actually confirmed it.** Your own
unprompted self-assessment is a plain report; mislabelling it poisons the
signal the curator sorts on.

## Correcting the kind

If you (or the researcher) realize a report is filed under the wrong kind:

```python
chronicle.reasoning_errors.reclassify(
    report_id, kind="operational", reason="an execution slip, not an inference"
)
```

**The id does not change** — you already printed it to the researcher, and
that reference stays valid. The reason is required, because how often agents
misclassify is a signal about *these instructions*, and it is unreadable if
the corrections aren't recorded.

## When it is a pattern, and when it isn't

File it when the error could recur on a different experiment, in a different
field. Reasoning:

- "credited the learning rate when three config keys differed"
- "generalized from one seed without saying so"
- "declared an approach dead from a run that never converged"

Operational:

- "committed the variation before linking its input dataset"
- "pushed to the protected branch instead of the import branch"
- "ran a 12-hour job without a heartbeat and it was marked lost"

Do **not** file it — record a lesson instead — when the mistake is a fact
about this experiment's data or setup:

- "the boundary mask is inverted in *this* dataset"
- "eval-set X leaks past step 4200"

## Guardrails

- **At most one report per distinct mistake per session.** Never from a retry
  loop.
- **Say so in-band**: one line, `reported <kind> error: <one line> (<id>)`, so
  the researcher sees the correction land rather than discovering it later.
  Print the id — it is what a reclassification is addressed to.
- **Evidence is pointers, not content** — session shard, run, report ids.
- The report needs no experiment. Either kind is an observation about how AI
  works, not about anyone's data; file it globally when it did not happen
  inside one.
- **Failing is not the same as erring.** A training run that diverges, a
  hypothesis that turns out false, a search that finds nothing — those are
  results. File an operational report when the *agent* did something a check
  would have caught.

## MCP-native equivalents

```
chronicle.report_reasoning_error       # the report (takes kind)
chronicle.list_failure_modes           # the reasoning catalog
chronicle.suggest_operational_checks   # what to check before acting
chronicle.list_agent_errors            # what has already been reported
chronicle.record_lesson                # the local instance
```

## Requires

- Credentials from `~/.methodic` (or `CHRONICLE_API_KEY` exported).
- `Write` on the experiment only when the report names one; a global report
  needs no more than a valid key.
