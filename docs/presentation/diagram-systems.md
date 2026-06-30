# Diagram Systems

This file owns the `research_x` diagram creation-system routing. It classifies
diagram work by the system used to create it, not by an open-ended list of
possible diagram types.

This file chooses the renderer/system only. It does not choose architecture
content. Final runtime/design content for human-facing diagrams comes from
`docs/presentation/final-runtime-flow.md` and
`docs/presentation/final-design-flow.md`.

Generated diagrams, WBS views, dashboards, slide decks, and screenshots are
control or review artifacts. They are not source bundles, context chunks,
citations, or answer evidence.

Local visual QA uses `src/research_x/control_artifacts/visual_review.py` to
evaluate already-rendered deck or snapshot artifacts for blank output, missing
assets, overlap, readability, and frame fit. It is a review gate only; it does
not install or run Slidev, Playwright, ppt-master, or any browser automation.

## Current Systems

| System | Repository surface | Official/upstream fit | Use in this repository |
| --- | --- | --- | --- |
| D2 | `docs/presentation/diagrams/*.d2`, rendered to `docs/presentation/assets/*.svg` | D2 is a text-to-diagram language for declarative diagramming. Its official docs include layout, containers, classes, sequence diagrams, and UML class diagrams. | Use when the requested output is the D2/Marp presentation lane. D2 source must be written from the final flow docs, not treated as the source for Mermaid rewrites. |
| Marp | `docs/presentation/slides.md`, built to `docs/presentation/dist/*.pptx` | Marp is the Markdown presentation ecosystem; Marp CLI converts Markdown slide decks into outputs such as HTML/PDF/PPTX. | Owns slide/deck assembly and claim markers. It does not own architecture content. |
| Mermaid | `docs/control/codex/dashboard/mermaid/*.mmd`, `docs/presentation/mermaid/**/*.mmd` | Mermaid renders Markdown-inspired text definitions and officially supports multiple diagram types, including flowchart, sequence, class, state, ER, journey, Gantt, pie, requirement, Gitgraph, mindmap, timeline, quadrant, Sankey, XY chart, block, packet, architecture, Kanban, and radar diagrams. Its class diagram syntax is UML-oriented, and sequence/state diagrams are first-class Mermaid diagram types. | Use when the requested output is text-native Mermaid, dashboard review, Mermaid presentation review, or Mermaid-backed UML. Mermaid source must be generated from the final flow docs, not by refactoring D2/SVG assets. Local preview/rendering uses the official Mermaid CLI package. |
| WBS Viewer | `tools/wbs_viewer/vendor/single-file-wbs-v1.3.0/wbs_viewer.html` plus `tools/wbs_viewer/projects/research-x-work-state.json` | The vendored upstream describes a dependency-free single-file WBS/Gantt viewer with a progress-axis view and progress line, opened locally in Chrome/Chromium. | Owns project work-state visualization only. Keep WBS as WBS; do not route architecture or evidence diagrams here. |

## Removed System

The previous custom UML lane was removed.

- Removed generator: `scripts/uml/build-research-x-uml.mjs`
- Removed generated assets: `docs/uml/`
- Removed asset contract test: `tests/test_uml_assets.py`

Reason: it was a hand-written SVG generator with no external tool semantics,
official diagram-language contract, or upstream usage model to align with.
Future diagrams must use an owned system above, or a separately reviewed
official/upstream tool adoption. Do not recreate a custom SVG generator as a
replacement.

## Routing Rules

- Human-facing project explanation: choose the requested system first, then apply
  `docs/presentation/diagram-design-harness.md`.
- Mermaid requests: generate Mermaid from the final flow docs and user diagram
  purpose. Do not use existing D2/SVG files as the source model.
- D2/Marp requests: generate D2 and slide content from the final flow docs and
  claim markers. Do not treat D2 assets as architecture truth.
- Slide/deck packaging: use Marp.
- Codex control-dashboard and presentation-review diagrams: Mermaid is allowed;
  choose a Mermaid diagram type that matches the official Mermaid diagram syntax
  instead of forcing all visuals into flowcharts.
- Mermaid UML requests: use real Mermaid UML-capable syntax. Use
  `sequenceDiagram` for interactions, `classDiagram` for structure and
  relationships, and `stateDiagram-v2` for lifecycle/status behavior. Do not
  call a `flowchart` UML.
- WBS, Gantt, progress-line, and work-state review: use WBS Viewer.
- Strict UML means the diagram source uses a real UML-capable diagram type, not
  just boxes and arrows that look similar. In this repository, Mermaid can own
  that lane when the requested UML type is supported by Mermaid.

## Official/Upstream Pointers

- D2 documentation: `https://d2lang.com/`
- Mermaid syntax documentation: `https://mermaid.js.org/syntax/`
- Marp documentation: `https://docs.marp.app/`
- WBS Viewer upstream: `tools/wbs_viewer/vendor/single-file-wbs-v1.3.0/README.en.md`
