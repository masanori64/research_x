# pdgkit Operating Reference

This folder is the project-owned local execution environment for
`@shibayama/pdgkit`. It is not only an old item 35 SVG canary. The canary is the
history of adoption; the active tool contract is broader:

```text
natural language or project structure
-> Codex writes .pdg source
-> pdgkit validate
-> pdgkit render / refs
-> review artifact, document asset, or presentation asset
```

This document is an operational rewrite of the upstream GitHub README and note
article for Codex use. It is not a verbatim mirror. The point is to preserve the
usable information without narrowing the tool to a single SVG path.

Sources:

- GitHub: https://github.com/shibayamalicht/pdgkit
- note: https://note.com/nonoonenono/n/n0701699bbf3c
- npm package: `@shibayama/pdgkit@0.1.2`

## What pdgkit Is

pdgkit is a headless Node/CLI/MCP implementation around PatentDSL `.pdg`.
`.pdg` means Patent Diagram Grammar: a deliberately small language for patent
figures. It describes reference numerals, containment, and connections. pdgkit
then validates and renders the figure.

The upstream distinction matters:

- PatentDSL itself is a browser-oriented single HTML GUI.
- pdgkit exposes the same `.pdg` idea as a reusable Node library, command-line
  tool, and MCP server.
- The intended host can be a patent drafting tool, a code agent, a web chat with
  code execution, a local script, or an LLM API loop.

The core design is division of labor:

```text
AI: understand the description and write correct .pdg structure
pdgkit: deterministically validate, lay out, and draw the lines
```

Codex must not treat pdgkit as "AI draws a picture." Codex should treat it as a
structure compiler: Codex writes the source; pdgkit checks and renders it.

## Why The note Matters

The note article explains the reason pdgkit exists. PatentDSL is not especially
pleasant for humans to type by hand: the user writes sparse lines such as
definitions, containment, and arrows. That same sparseness is useful for LLMs.
There are few keywords, no manual coordinates, no color choice, and no diagram
type declaration in the ordinary source. The AI mostly converts a natural
language description into three sentence types.

The article's warning is directly relevant to Codex: if the user asks an AI to
"draw a patent diagram" without constraining the route, the AI may produce a
hand-made image, SVG, matplotlib chart, Mermaid-like sketch, or a decorative
diagram. That often misses the things patent figures need: stable reference
numerals, a figure-to-spec mapping, black-line convention, language control, and
reproducibility. The failure is not only visual quality; the AI is being asked to
think about the invention and draw the lines at the same time.

pdgkit separates those tasks. The AI writes `.pdg`; pdgkit draws. In this
repository, that means:

- Do not hand-code a replacement SVG, HTML diagram, PowerPoint shape diagram, or
  ad hoc canvas drawing when the task is to produce a pdgkit diagram.
- Do not skip `.pdg` because SVG output is "easy enough."
- Do not make a slide diagram by manually redrawing what should have been a
  pdgkit-rendered source unless the `.pdg` source remains the authoritative
  structure and the manual layer is clearly a presentation derivative.
- Prefer `guide -> .pdg -> validate -> render -> review` over a direct drawing
  shortcut.

## Local Package

Package state:

- npm package: `@shibayama/pdgkit`
- pinned version: `0.1.2`
- local package folder: `tools/pdgkit_canary/`
- local lockfile: `tools/pdgkit_canary/package-lock.json`
- CLI command: `pdgkit`
- MCP command present in package: `pdgkit-mcp`
- Node requirement from upstream: Node 18 or newer
- license: MIT

This package is intentionally isolated under this folder. Do not add pdgkit to
the root Python project, install it globally, upgrade it, or register its MCP
server without a separate source-review and configuration gate.

## Local Upstream Materials

The installed npm package includes the upstream documentation and examples:

```text
tools/pdgkit_canary/node_modules/@shibayama/pdgkit/README.md
tools/pdgkit_canary/node_modules/@shibayama/pdgkit/docs/ai-authoring-guide.md
tools/pdgkit_canary/node_modules/@shibayama/pdgkit/docs/spec.md
tools/pdgkit_canary/node_modules/@shibayama/pdgkit/examples/*.pdg
```

Use these files when the exact grammar, AI authoring contract, or examples are
needed. The local package documentation is authoritative for the installed
version. This README is the research_x operating contract around it.

## Canonical Codex Route

When a task asks Codex to create or update a project diagram and pdgkit is a fit,
use this route:

1. Work inside `tools/pdgkit_canary`.
2. Read or invoke the authoring guide before writing a non-trivial diagram.
3. Write or edit a `.pdg` source file.
4. Run `pdgkit validate` until the source is valid.
5. Render with pdgkit to the required output format.
6. Inspect the rendered artifact. If layout breaks, repair `.pdg` structure or
   split the diagram.
7. Keep the `.pdg` file as the source of truth.
8. Treat rendered output as review/presentation/control artifact, not evidence.

Preferred command form from this directory:

```powershell
cd tools\pdgkit_canary
npx --no-install pdgkit guide
npx --no-install pdgkit validate ..\..\docs\pdg\memory-evidence-pipeline.pdg --lang both
npx --no-install pdgkit render ..\..\docs\pdg\memory-evidence-pipeline.pdg --lang both -o ..\..\docs\pdg\out\memory-evidence-pipeline.svg
```

Direct Node invocation is also acceptable when `npx` behavior itself is the
thing being diagnosed:

```powershell
cd tools\pdgkit_canary
node .\node_modules\@shibayama\pdgkit\dist\pdgkit.js validate ..\..\docs\pdg\memory-evidence-pipeline.pdg --lang both
node .\node_modules\@shibayama\pdgkit\dist\pdgkit.js render ..\..\docs\pdg\memory-evidence-pipeline.pdg --lang both -o ..\..\docs\pdg\out\memory-evidence-pipeline.svg
```

Do not run `npm install` merely to use the already-pinned package. Use install or
upgrade commands only after the user explicitly approves a dependency change.

## The .pdg Mental Model

`.pdg` has three core statement types.

Definitions give a reference numeral or node ID a label:

```pdg
10 = 制御部 / controller
S100 = Start request / Start request
```

Containment says a parent contains children:

```pdg
100 : 10 20 30
```

Connections draw lines or arrows:

```pdg
10 -> 20 : 信号 / signal
20 <-> 30 : 通信 / communication
30 .> 40 : 無線 / wireless
```

The authoring guide frames the AI's job as translation, not invention. Extract
the entities, relationships, sequence, state transitions, or conditions from the
input; map them into definitions, containment, and connections; avoid adding
unstated entities unless needed to make the structure coherent.

## Diagram Kinds

pdgkit supports four diagram kinds:

- `block`: structure, containment, systems, components, internal/external blocks.
- `flow`: steps, process order, decisions, loops, retry paths.
- `state`: states and transitions, including initial/final `*`.
- `seq`: actors and message exchanges over time.

In normal `.pdg`, diagram kind is inferred from structure:

- any containment line makes a block diagram;
- a label ending in `?` indicates a flow decision;
- `*` indicates state diagram use;
- `<->` or request/response pairs can make a sequence diagram;
- otherwise simple directed steps usually become a flow.

For project-owned sources, keep the first line as a pdgkit kind assertion:

```pdg
#! kind: flow
```

This is a validation guard. If the structure implies a different diagram kind,
`validate` reports a mismatch instead of silently producing the wrong class of
figure.

## Language Handling

Labels can be Japanese-only, English-only, or bilingual. A bilingual label uses
` / ` with spaces around the slash:

```pdg
10 = 制御部 / controller
```

For human-facing project assets, prefer `--lang both` unless the target document
needs one language only. This keeps Japanese and English terms aligned without
duplicating the source diagram.

Render options:

```powershell
npx --no-install pdgkit render fig.pdg --lang ja -o fig-ja.svg
npx --no-install pdgkit render fig.pdg --lang en -o fig-en.svg
npx --no-install pdgkit render fig.pdg --lang both -o fig-both.svg
```

## Output Formats

Upstream and local verification support more than SVG:

- SVG: vector, safest default, no browser needed, dependency-light path.
- PNG: high-resolution raster with white background.
- JPEG: high-resolution raster with white background.
- PDF: A4 output, vector-preferred with raster fallback.
- PPTX: slide output with a high-resolution rendered image.
- editable PPTX: PowerPoint shapes/lines/text derived from the SVG structure.
- reference table Markdown: numeral/name table.
- reference table CSV: numeral/name table for spreadsheet or review use.

Examples:

```powershell
cd tools\pdgkit_canary
npx --no-install pdgkit render fig.pdg --to svg -o fig.svg
npx --no-install pdgkit render fig.pdg --to png -o fig.png
npx --no-install pdgkit render fig.pdg --to jpeg -o fig.jpg
npx --no-install pdgkit render fig.pdg --to pdf -o fig.pdf
npx --no-install pdgkit render fig.pdg --to pptx -o fig.pptx
npx --no-install pdgkit render fig.pdg --to pptx --editable -o fig-editable.pptx
npx --no-install pdgkit refs fig.pdg --format md -o refs.md
npx --no-install pdgkit refs fig.pdg --format csv -o refs.csv
```

Local check on 2026-06-24 confirmed `validate`, `render` to
`svg/png/jpeg/pdf/pptx`, editable PPTX, and `refs` to Markdown/CSV against the
installed `0.1.2` package. That confirms the local environment can use these
lanes. It does not make every output lane equally appropriate for every task.

## Output Selection

Use SVG when:

- the artifact is for code review;
- deterministic text diff/re-render discipline matters;
- the environment may not have native/render dependencies working;
- the diagram will be embedded into Markdown or inspected as a lightweight
  review artifact.

Use PNG/JPEG when:

- the target system needs raster images;
- the user explicitly asks for an image file;
- screenshot-style visual review is needed.

Use PDF when:

- the user asks for a document-like patent figure output;
- the artifact needs page formatting rather than web embedding.

Use PPTX or editable PPTX when:

- the diagram must be included in slides;
- the user needs PowerPoint output;
- a presentation is being created and pdgkit can provide the authoritative
  structure instead of a hand-drawn slide diagram.

Use `refs` when:

- reference numerals or node IDs need a table;
- reviewers need to check that every structural element has a label;
- a downstream doc should include the diagram's symbol table.

## Local Project Sources

Project-owned `.pdg` files live outside this canary folder:

```text
docs/pdg/control-artifact-structure-view.pdg
docs/pdg/memory-evidence-pipeline.pdg
docs/pdg/objective-route-policy.pdg
docs/pdg/route-memory-preflight.pdg
docs/pdg/skill-lifecycle-governance.pdg
docs/pdg/source-intake-gate-flow.pdg
docs/pdg/visual-context-offload-lane.pdg
```

Generated review SVGs live here:

```text
docs/pdg/out/*.svg
```

The historical item 35 canary remains here:

```text
tools/pdgkit_canary/canaries/item-11-35-flow.pdg
tools/pdgkit_canary/out/item-11-35-flow.svg
```

Do not put new project-owned route/state diagrams under `tools/pdgkit_canary`
unless they are specifically pdgkit canary fixtures. Active project diagrams
belong under `docs/pdg`.

## Relationship To WBS And Markdown

PDG is not a substitute for every document. Use each surface for its proper job:

- WBS JSON: operational state, candidate state, gates, completion, remaining work.
- PDG: route flow, state machine, control boundary, artifact transition.
- Markdown: durable reasoning, policies, source-of-truth explanations, pointers.
- Pointer map: path/hash/size/restore metadata for offloaded context.

pdgkit helps keep structural flow out of giant Markdown. It should reduce
textual sprawl by moving flow/state structure into `.pdg`, not create another
uncontrolled documentation surface.

## Presentation And Visual Material Rule

When preparing a deck, explanatory PNG, or visual brief from this project:

- Use pdgkit for route/state/boundary diagrams when the content is structural.
- Keep the `.pdg` source and generated render together in the project.
- Do not shrink important structure just because a single PNG is crowded.
- Split a large diagram into multiple `.pdg` files instead of deleting nodes.
- If a slide needs design polish, build it around pdgkit output or a clearly
  derived asset; do not replace the source diagram with an unverifiable redraw.
- If text overlaps or layout breaks, fix the `.pdg` source, split the graph, or
  choose a different output lane. Do not silently accept unreadable output.

This is the concrete lesson from the upstream note: the reusable value is the
structure-to-render loop, not a one-off pretty image.

## MCP Boundary

The package includes `pdgkit-mcp`, and upstream documents MCP as a way for
LLM-capable clients to call `pdg_render`/related tools directly. In this project,
that is not enabled by default.

Allowed now:

- read the upstream MCP documentation;
- note that the binary exists;
- evaluate whether MCP registration would help a future workflow.

Not allowed without a separate approval and source-review/configuration gate:

- registering `pdgkit-mcp`;
- adding it to global MCP config;
- enabling automatic diagram rendering tools through MCP;
- treating MCP availability as already granted.

## Library/API Boundary

Upstream exposes library functions such as parsing, validation, rendering, and
loading the AI authoring guide. The API pattern is useful for future integration:

```text
load authoring guide
-> ask an LLM/API to produce .pdg
-> validate()
-> if diagnostics, feed them back for repair
-> renderToSvg/renderToPng/renderToPdf/renderToPptx or refs
```

In this repository, the default lane remains local CLI use from the isolated
tool folder. Importing pdgkit into a new Node service, root package, hook, or MCP
surface is a separate design decision.

## Known Limitations

The upstream note and README are explicit about limitations:

- A generic AI may still ignore instructions and draw by itself. The prompt or
  Codex route must explicitly require pdgkit.
- SVG is the safest output. PNG/PDF/PPTX can depend on native or heavier runtime
  paths and may fail in some environments.
- Use one `.pdg` file per figure. Multiple figures in one source are out of
  scope.
- Cross-figure reference numeral consistency is not solved by pdgkit alone; the
  project or host workflow must manage it.
- Dense graphs, deep containment, many external devices, and complex paths can
  produce awkward routing or label overlap.
- pdgkit does not support arbitrary styling, colors, manual coordinates,
  custom shapes, swimlanes, or sequence extensions such as alt/loop/parallel.
- A rendered diagram is not evidence and cannot replace a source bundle,
  citation, or stored raw source.

## Failure Handling

If validation fails:

1. Read the diagnostic line and message.
2. Fix the `.pdg` source, not the rendered output.
3. Validate again.
4. Only render after validation passes.

If render succeeds but visual layout is bad:

1. Check whether the diagram is too dense for one figure.
2. Split the diagram into smaller `.pdg` sources if needed.
3. Reduce crossings by clarifying containment or step order.
4. Keep the source authoritative.
5. Re-render and inspect.

If a non-SVG output fails:

1. Confirm SVG still renders.
2. Treat the failure as an output-lane issue, not proof that the `.pdg` source is
   wrong.
3. Report the failing format and error.
4. Use SVG as the fallback review artifact unless the user specifically needs the
   failed format repaired.

## Allowed Current Use

Allowed in this repository without additional approval:

- use the pinned package already installed under `tools/pdgkit_canary`;
- run `guide`, `validate`, `render`, `refs`, `samples`, and `version` locally;
- render project-owned `.pdg` sources to SVG/PNG/JPEG/PDF/PPTX when the user task
  needs those artifacts;
- create Markdown/CSV reference tables from project-owned `.pdg`;
- use generated outputs as review, presentation, or control-plane artifacts;
- use `--lang ja`, `--lang en`, or `--lang both` as appropriate.

Still gated:

- package install, upgrade, or root dependency adoption;
- global CLI install;
- MCP registration or plugin/hook integration;
- provider/API generation of `.pdg` while the no-quota freeze is active;
- treating generated diagrams as evidence, answer support, or citation support;
- importing upstream source code into production paths without a new review.

## Quick Checks

Show CLI help:

```powershell
cd tools\pdgkit_canary
npx --no-install pdgkit help
```

Validate all project PDG sources:

```powershell
cd tools\pdgkit_canary
Get-ChildItem ..\..\docs\pdg\*.pdg | ForEach-Object {
  npx --no-install pdgkit validate $_.FullName --lang both
}
```

Render one project source:

```powershell
cd tools\pdgkit_canary
npx --no-install pdgkit render ..\..\docs\pdg\route-memory-preflight.pdg --lang both -o ..\..\docs\pdg\out\route-memory-preflight.svg
```

Generate a refs table:

```powershell
cd tools\pdgkit_canary
npx --no-install pdgkit refs ..\..\docs\pdg\route-memory-preflight.pdg --format md -o ..\..\docs\pdg\out\route-memory-preflight.refs.md
```
