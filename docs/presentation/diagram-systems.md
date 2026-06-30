# Diagram Systems

This file owns the `research_x` diagram creation-system routing. It classifies
diagram work by the system used to create it, not by an open-ended list of
possible diagram types.

Generated diagrams, WBS views, dashboards, slide decks, and screenshots are
control or review artifacts. They are not source bundles, context chunks,
citations, or answer evidence.

## Current Systems

| System | Repository surface | Official/upstream fit | Use in this repository |
| --- | --- | --- | --- |
| D2 | `docs/presentation/diagrams/*.d2`, rendered to `docs/presentation/assets/*.svg` | D2 is a text-to-diagram language for declarative diagramming. Its official docs include layout, containers, classes, sequence diagrams, and UML class diagrams. | Primary system for human-facing explanatory diagrams in the presentation lane. |
| Marp | `docs/presentation/slides.md`, built to `docs/presentation/dist/*.pptx` | Marp is the Markdown presentation ecosystem; Marp CLI converts Markdown slide decks into outputs such as HTML/PDF/PPTX. | Owns slide/deck assembly around D2 assets and claim markers. |
| Mermaid | `docs/control/codex/dashboard/mermaid/*.mmd`, `docs/presentation/mermaid/*.mmd` | Mermaid renders Markdown-inspired text definitions and officially supports multiple diagram types, including flowchart, sequence, class, state, ER, journey, Gantt, pie, requirement, Gitgraph, mindmap, timeline, quadrant, Sankey, XY chart, block, packet, architecture, Kanban, and radar diagrams. | Use for text-native Mermaid diagrams in dashboards and presentation review artifacts. It is not limited to dashboards as a tool; choose the Mermaid diagram type that matches the job. |
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

- Human-facing project explanation: use D2 diagrams inside the Marp presentation
  lane, and apply `docs/presentation/diagram-design-harness.md`.
- Slide/deck packaging: use Marp.
- Codex control-dashboard and presentation-review diagrams: Mermaid is allowed;
  choose a Mermaid diagram type that matches the official Mermaid diagram syntax
  instead of forcing all visuals into flowcharts.
- WBS, Gantt, progress-line, and work-state review: use WBS Viewer.
- Strict UML is not a current repository lane. If a future task needs strict UML,
  first choose and document an official/upstream UML-capable tool; do not infer
  one from habit or create a custom renderer.

## Official/Upstream Pointers

- D2 documentation: `https://d2lang.com/`
- Mermaid syntax documentation: `https://mermaid.js.org/syntax/`
- Marp documentation: `https://docs.marp.app/`
- WBS Viewer upstream: `tools/wbs_viewer/vendor/single-file-wbs-v1.3.0/README.en.md`
