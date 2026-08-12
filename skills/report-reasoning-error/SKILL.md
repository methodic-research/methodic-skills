---
name: report-reasoning-error
description: |
  Use this skill when an AI's *reasoning about research* went wrong — yours
  or another agent's — and the mistake looks like it could recur elsewhere.
  PROACTIVELY, without being asked, in two situations. (1) The researcher
  identifies or confirms a mistake in your reasoning ("no — that run
  crashed, it isn't evidence against the hypothesis", or a redirect that
  only makes sense if your premise was wrong): record a research lesson AND
  file a reasoning-error report with user_confirmed. (2) You notice yourself
  or a peer making a generalizable reasoning error: file the report. Also on
  request ("report that as a reasoning error"). NOT for platform bugs (use
  methodic-feedback) and NOT for a wrong assumption specific to one
  experiment's data (that is a research lesson).
---

# Report a reasoning error

Chronicle keeps a **failure-mode catalog**: the shared vocabulary for ways an
AI reasons badly about research — confounded comparisons, single-seed
generalization, treating a crashed run as a refutation. It is what the
platform's own evaluation checks findings against, and it only gets better if
the instances reach it.

Reporting is deliberately cheap. The bar is "this looked wrong", the call
returns immediately, and validation runs behind it. **Do not** weigh whether a
report is worth filing — that judgment is what validation and human curation
are for, and an unfiled report teaches nobody.

## Which sink — the three-way split

| The thing that's wrong | Sink | Skill |
|---|---|---|
| How the *reasoning* went (a pattern that could recur anywhere) | `reasoning_errors` | **this skill** |
| A wrong assumption about *this research* (this dataset, this eval set) | `research_lessons` | `research-lessons` |
| The *platform* (SDK/MCP/API gap or bug) | `feedback` | `methodic-feedback` |

They are not exclusive: a user-confirmed mistake is usually **both** a lesson
(the local instance) and a reasoning error (the pattern). See Contract 2.

## Contract 1 — read the catalog before you conclude

Before drawing conclusions or writing them up, list the catalog and check the
claims you are about to make against it:

```python
modes = chronicle.failure_modes.list()          # active, human-confirmed only
# or, MCP-native: chronicle.list_failure_modes
```

Each entry says what the mode is, how it shows up, and what to do instead. A
claim that obviously trips one is worth fixing *before* it is recorded — that
is cheaper for everyone than a flagged finding the researcher has to
adjudicate.

## Contract 2 — report what the researcher confirms

When the **researcher identifies or confirms a mistake in your reasoning**, a
human has already done the validation, on a real instance, in context. That is
the highest-quality signal this system gets and it must not evaporate when the
session ends. File **both**, without being asked:

```python
# 1. The local instance — always.
lesson = chronicle.experiments.record_lesson(
    experiment_id,
    title="A crashed run is not evidence against the hypothesis",
    body_md="...wrong assumption, correction, evidence, what to do instead...",
    origin="researcher_correction",
)

# 2. The pattern — when it could recur on a different experiment.
report = chronicle.reasoning_errors.report(
    "treated a crashed run as a refutation of the hypothesis",
    description="v3 run 1 OOM'd at step 200; I recorded not_working from it",
    experiment_id=experiment_id,
    user_confirmed=True,            # a human confirmed the instance
    lesson_id=lesson["id"],
)
print(f"reported reasoning error: treated a crashed run as a refutation ({report['id']})")
```

`user_confirmed=True` puts the report at a higher trust tier: a model may not
reject it, because a model does not get to overrule the researcher about what
happened. It can still decline to *generalize* it — that leaves the report for
a human curator, with the model's dissent recorded beside it.

**Only set `user_confirmed` when a human actually confirmed it.** Your own
unprompted self-assessment is a plain report; mislabelling it poisons the
signal the curator sorts on.

## When it is a pattern, and when it isn't

File it when the error could recur on a different experiment, in a different
field:

- "credited the learning rate when three config keys differed"
- "generalized from one seed without saying so"
- "declared an approach dead from a run that never converged"

Do **not** file it — record a lesson instead — when the mistake is a fact
about this experiment's data or setup:

- "the boundary mask is inverted in *this* dataset"
- "eval-set X leaks past step 4200"

## Guardrails

- **At most one report per distinct mistake per session.** Never from a retry
  loop.
- **Say so in-band**: one line, `reported reasoning error: <one line> (<id>)`,
  so the researcher sees the correction land rather than discovering it later.
- **Evidence is pointers, not content** — session shard, run, report ids.
- The report needs no experiment. A reasoning error is an observation about
  how AI reasons, not about anyone's data; file it globally when it did not
  happen inside one.

## MCP-native equivalents

```
chronicle.report_reasoning_error   # the report
chronicle.list_failure_modes       # the catalog
chronicle.record_lesson            # the local instance
```

## Requires

- Credentials from `~/.methodic` (or `CHRONICLE_API_KEY` exported).
- `Write` on the experiment only when the report names one; a global report
  needs no more than a valid key.
