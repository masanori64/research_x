# Mermaid Redesign Diagrams

These Mermaid diagrams are created from the project requirements and repository
source-of-truth documents, not from the existing D2/SVG assets.

They are control and review artifacts. They are not source bundles, context
chunks, citations, answer support, or provider/API permission.

## Source Basis

Primary sources:

- user requirement: create two sets of five human-readable Mermaid diagrams;
- `docs/presentation/diagram-design-harness.md`: fixed Mermaid harness and
  readability rules;
- `README.codex.md` and `PROJECT.md`: project goal, active gates, and core
  invariant;
- `docs/memory-pipeline-v2.md`: request-to-answer evidence architecture;
- `docs/pipeline.md`: acquisition, auth, and provider boundaries;
- `tools/wbs_viewer/projects/research-x-work-state.json`: current status and
  gates.

## Design Loop Record

Question: what should the reader understand first?

Answer: `research_x` is a memory-search tool. The core story is not every
component. The core story is how a request becomes a cited answer, a review
state, or a provider-gated stop.

Self-review loop:

- Finding: the previous diagrams gave equal weight to source intake, provider
  gates, WBS, audit, and answer flow.
  Decision: every diagram must keep the request-to-result path visually central.
- Finding: component lists are accurate but not explanatory.
  Decision: labels describe roles in Japanese; established names such as
  `research_x`, `Source Bundle`, `Citation`, `SQLite`, and `API Budget Guard`
  are kept only where they anchor the reader.
- Finding: the same nodes appeared in multiple diagrams with the same purpose.
  Decision: each diagram owns one question and omits details owned by another
  diagram.
- Finding: long horizontal flows and deep vertical inventories force zooming.
  Decision: keep each diagram to a small main path plus a few supporting boxes.
- Finding: provider and auth details are important but are not the main story of
  most diagrams.
  Decision: show them as external-design or gate surfaces except in the gate
  diagram.
- Finding: final-state diagrams should not simply add more features.
  Decision: final-state diagrams show a matured version of the same path:
  route, restore, cite, answer or abstain, observe, and improve.
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
