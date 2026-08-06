---
name: literature-review
description: |
  Use this skill when the user wants a literature review as part of their
  research workflow — phrases like "do a literature review on X", "review
  the literature before we go further", "what does the field say about Y",
  "ground this in prior art", "find and cite the relevant papers", "what's
  known internally and externally about Z". Built on
  `chronicle-research-survey` (Chronicle's internal corpus via
  `chronicle.search` + external literature via the configured literature
  MCP) plus `chronicle-publications` for registering and citing what's
  worth keeping. Adds the research-workflow framing: scope the question,
  run both sources, synthesize prior art + gaps, register the publications
  worth citing, optionally persist a `research_report`, and report the
  activity. No experiment required — "read for yourself" is first-class;
  in an experiment context it links citations as inputs. For the
  mechanics-only two-source search use `chronicle-research-survey`
  directly; for turning the gap into an experiment use
  `chronicle-propose-experiment` (or the aggregate `synthesis` skill).
---

# Literature review

The survey workflow: scope a research question, read what's been tried
internally and what the field has published, synthesize prior art and the
gap, and make the load-bearing sources durable — registered publications
and citations, not just names in prose. This is the context-gathering half
the managed synthesis agent used to do, run in your own session.

This skill composes the chronicle plugin rather than duplicating it: the
two-source search mechanics live in **`chronicle-research-survey`**
(internal corpus + external literature MCP, with its documented fallbacks)
and the registration/citation mechanics in **`chronicle-publications`** —
both invoked by name. What this skill adds is the workflow around them. If
the chronicle plugin's skills/tools aren't available in this session, stop
and tell the user to install **both** plugins from the `methodic`
marketplace.

**No experiment required.** "Read for yourself" is a first-class use: a
review can run against a bare topic with nothing to attach to, ending at
the synthesis presented in-session. Registration still works
experiment-less (publications are shared, public reference records); only
the *citation links* and the persisted report need an experiment.

## Inputs

- **`topic`** — the research question. Sharpen a vague one with the user
  before searching ("diffusion models" → which aspect, for what decision).
- **`anchor_experiment_id`** (optional) — the experiment this review
  serves. Default to the experiment the session is working in, if any;
  omit entirely for a standalone read.
- **`purpose`** (optional but shaping) — what decision the review feeds
  (baseline hunting, sanity-checking a hypothesis, escaping a plateau).
  State it in the synthesis so the gap analysis answers it.
- **`save_as_report`** (default `False`) — persist the synthesis as a
  `research_report`. Only on explicit request, and only with an anchor
  experiment to attach it to.

## Workflow

1. **Scope.** Turn the topic + purpose into the concrete questions the
   review must answer. Three is plenty; name them so the synthesis can be
   checked against them.

2. **Run the survey.** Invoke **`chronicle-research-survey`** with the
   scoped topic (and the anchor experiment's lineage as internal context
   when one exists). It owns the mechanics: internal corpus via
   `chronicle.search` + lineage + experiment listings, external literature
   via the configured literature MCP, and the graceful degradations (no
   literature MCP → internal-only, stated plainly; never fabricated
   citations).

3. **Deepen where it matters.** A workflow review reads more than search
   snippets: for the handful of load-bearing sources, pull the substance —
   `chronicle.load_asset` for internal reports, the literature MCP's
   fetch/detail tools for external papers — enough to characterize methods
   and results, not just titles. Depth on five beats breadth on fifty.

4. **Register + cite what's worth keeping.** Via the
   `chronicle-publications` mechanics: `chronicle.register_publication`
   (`{ "doi": … }` / `{ "arxiv": … }` / BibTeX; dedup is automatic) for
   each external work that materially informs the synthesis, then — when
   there's an anchor experiment — cite it with `chronicle.link_asset`
   `{ "experiment_id": …, "asset_id": …, "link": "input" }`. Internal
   prior work: cite the load-bearing report assets the same way
   (`"propagate_acl": false` for ones you don't administer). Citation
   types stay linkable on a **committed** experiment (they lock only at
   conclusion), so citing mid-research is normal. Cite what shaped the
   synthesis, not every hit; with no anchor experiment, register without
   linking and say so.

5. **Synthesize** — in-context, no server LLM call. Answer the scoped
   questions: what's been tried internally (experiment ids + report
   titles, conclusions, retractions), what the field has published (titles
   + identifiers), and **the gap** — what neither corpus resolves, i.e.
   what new work would actually add. Flag contradictions between internal
   findings and published results explicitly; those are research leads.

6. **Optionally persist.** When `save_as_report` and an anchor experiment
   exist: `chronicle.write_report` `{ "experiment_id": …, "kind":
   "research_report", "title": "Literature review: <topic>", "body":
   <synthesis markdown> }`.

7. **Report the milestone.** With an anchor experiment:
   `chronicle.report_activity` `{ "experiment_id": …, "title":
   "Literature review: <topic> (N sources, M cited)", "summary_md": <gap
   statement>, "asset_ids": [<research_report, if saved>] }`. One activity
   per review. If `chronicle.report_activity` isn't in your tools list,
   the server predates activity reporting (it ships with the methodic#642
   chronicle-server release) — say so and continue. Skip the step entirely
   for an experiment-less read (activities hang off an experiment).

## After the skill completes

Present the synthesis in the survey's three-section shape — tried
internally / published literature / the gap — answering the scoped
questions, then: which publications were registered and (if anchored) how
many citations were linked, the `research_report` asset id if saved, and
whether the activity was reported. If the literature MCP was absent, say
the external half wasn't surveyed rather than letting the synthesis imply
it was.

## Failure modes

- **Chronicle plugin absent**: stop; tell the user to install both
  `chronicle` and `research` from the `methodic` marketplace.
- **No literature MCP configured / internal search 503**: inherited from
  `chronicle-research-survey` — degrade as it documents, and carry the
  degradation into the synthesis text explicitly.
- **`save_as_report` with no anchor experiment**: present the synthesis
  inline and point at `chronicle-propose-experiment` (a report needs an
  experiment to attach to).
- **Citation link 403** (`link_propagation_denied` or plain denial): the
  publication is registered regardless; report which links failed and
  continue.

## Requires

- The **chronicle plugin** installed alongside this one
  (`chronicle-research-survey`, `chronicle-publications`, and the
  `chronicle.*` MCP tools they use).
- Credentials resolved from `~/.methodic` (or `CHRONICLE_API_KEY`
  exported).
- A configured literature MCP (e.g. Paperclip) for the external half —
  optional; degrades to internal-only.
