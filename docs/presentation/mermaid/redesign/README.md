# Mermaid Redesign Diagrams

These Mermaid diagrams are review artifacts that must follow the final flow docs
and project requirements, not existing D2/SVG assets.

This redesign set is exactly two groups of five diagrams:

- `current/`: current-state explanation;
- `final/`: completed-state explanation.

Do not mix in the older root `docs/presentation/mermaid/*.mmd` review set when
showing this redesign set.

They are control and review artifacts. They are not source bundles, context
chunks, citations, answer support, or provider/API permission.

## Source Basis

Primary sources:

- user requirement: create two sets of five human-readable Mermaid diagrams;
- `docs/presentation/final-runtime-flow.md`: provisional final runtime flow;
- `docs/presentation/final-design-flow.md`: provisional final design flow;
- `docs/presentation/diagram-design-harness.md`: fixed Mermaid harness and
  readability rules;
- `README.codex.md` and `PROJECT.md`: project goal, active gates, and core
  invariant;
- `docs/memory-pipeline-v2.md`: request-to-answer evidence architecture;
- `docs/pipeline.md`: acquisition, auth, and provider boundaries;
- `tools/wbs_viewer/projects/research-x-work-state.json`: current status and
  gates.

The existing Mermaid diagrams are review artifacts and must be checked against
the two provisional final flow docs before reuse.

Visual style:

- use monochrome Mermaid styling only;
- do not use chromatic color to encode meaning;
- distinguish gate, stop, support, and main-path nodes with labels, grouping,
  stroke weight, and layout instead of red/yellow/green/blue fills.

## Design Loop Record

Question: what should the reader understand first?

Answer: `research_x` is a memory-search tool. The core story is not every
component. The core story is how broad candidate generation narrows into source
bundle restoration, context chunks, citations, answer authority, Answer Boundary,
and then a Tool Interface status such as cited answer, review state,
hypothesis_only, provider_gated, or blocked.

Self-review loop:

- Finding: the previous diagrams gave equal weight to source intake, provider
  gates, WBS, audit, and answer flow.
  Decision: every diagram must keep the request-to-result path visually central.
- Finding: D2/SVG assets can pull Mermaid work into a renderer refactor instead
  of a design pass.
  Decision: Mermaid diagrams start from the final flow docs and user purpose,
  not from existing D2/SVG files.
- Finding: component lists are accurate but not explanatory.
  Decision: labels describe roles in Japanese; established names such as
  `research_x`, `Source Bundle`, `Citation`, `SQLite`, and `ProviderApiBudgetGuard`
  are kept only where they anchor the reader.
- Finding: the same nodes appeared in multiple diagrams with the same purpose.
  Decision: each diagram owns one question and omits details owned by another
  diagram.
- Finding: long horizontal flows and deep vertical inventories force zooming.
  Decision: keep each diagram to a small main path plus a few supporting boxes.
- Finding: showing the older root Mermaid set together with `current` and
  `final` creates three categories when the requested shape is 2 x 5.
  Decision: preview and review this redesign as exactly `current` five diagrams
  plus `final` five diagrams.
- Finding: colored fills can make the diagram look like status decoration rather
  than a human explanation.
  Decision: use monochrome styling and make meaning come from labels, grouping,
  line weight, and reading order.
- Finding: provider and auth details are important but are not the main story of
  most diagrams.
  Decision: show provider lanes as guarded candidate branches except in the
  guard diagram.
- Finding: final-state diagrams should not simply add more features.
  Decision: final-state diagrams show a matured version of the same path:
  choose routes, branch guarded provider lanes, restore, chunk, cite, check
  answer authority, cross Answer Boundary, observe, and improve.
- Finding: no remaining issue changes the diagram purpose, node set, or reading
  order without creating a different diagram.
  Decision: write the diagrams.

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
