# Mermaid Redesign Diagrams

These are second-pass Mermaid presentation-review diagrams created from the
project requirements and repository source-of-truth documents, not from the
existing D2/SVG assets.

They are control and review artifacts. They are not source bundles, context
chunks, citations, answer support, or provider/API permission.

## Source Basis

- User requirement: create five human-readable Mermaid diagrams, then create two
  sets: current state and final completed state.
- `README.codex.md`: current mission, evidence invariant, Codex boundary, and
  runtime rules.
- `PROJECT.md`: canonical pointers, active gates, and top-level project goal.
- `docs/memory-pipeline-v2.md`: evidence architecture, runtime layers, provider
  gate, answer statuses, and control-artifact boundary.
- `docs/pipeline.md`: acquisition, auth, session, provider-chain, and source
  store boundaries.
- `tools/wbs_viewer/projects/research-x-work-state.json`: current layer status,
  gates, stop conditions, and next actions.
- `docs/presentation/diagram-design-harness.md`: human readability contract.

## Design Loop Record

Loop 1 separated the five diagram jobs:

- overall architecture: responsibility boundary only;
- evidence pipeline: promotion from candidate to citation only;
- one memory query: control flow for one request only;
- provider/quota gate: stop/allow decision only;
- WBS/roadmap: maturity and next actions only.

Loop 2 separated current and final sets:

- current diagrams show implemented baselines, staging lanes, provider gates, and
  review/control artifact boundaries;
- final diagrams show the intended complete operating model after gated provider,
  media, eval, feedback, and observability lanes are mature.

Loop 3 readability checks:

- each diagram keeps one primary direction;
- cross-links are avoided unless they mark a gate or feedback return;
- labels use Japanese for explanation and keep established names such as
  `research_x`, `Source Bundle`, `Citation`, `SQLite`, and `API Budget Guard`;
- file names, class names, and table names are avoided in the diagram labels;
- each diagram is sized as a slide-readable review artifact, not a code
  inventory.

## Files

Current-state set:

- `current/01-overall-architecture.mmd`
- `current/02-evidence-pipeline.mmd`
- `current/03-memory-query-sequence.mmd`
- `current/04-provider-quota-gate.mmd`
- `current/05-roadmap.mmd`

Final completed-state set:

- `final/01-overall-architecture.mmd`
- `final/02-evidence-pipeline.mmd`
- `final/03-memory-query-sequence.mmd`
- `final/04-provider-quota-gate.mmd`
- `final/05-roadmap.mmd`
