# pdgkit Upstream Review

Date: 2026-06-24

This review records the upstream source, package surface, local capability check,
and research_x adoption boundary for `@shibayama/pdgkit`. It deliberately
supersedes the narrower "SVG-only canary" framing. SVG remains the safest default
review target, but the upstream tool and local package support a wider
`validate -> render/refs` operating surface.

## Sources

- Candidate history: X/GPT item 35, pdgkit OSS.
- Related article history: X/GPT item 34, pdgkit note/article.
- Repository: https://github.com/shibayamalicht/pdgkit
- note article: https://note.com/nonoonenono/n/n0701699bbf3c
- npm package: `@shibayama/pdgkit`
- Pinned local version: `0.1.2`
- License: MIT
- Node requirement: `>=18`

Observed upstream Git refs during review:

- GitHub `main` HEAD: `0fd5ad5313808009787ad72103f008677245f825`
- Git tag observed: `pdgkit` -> `368e91740ce511f2278eb2bd0479bad2bd272300`

Observed npm integrity:

```text
sha512-MBY4ETouVJFRiPQkUP3I6uOzUQoUn2w7VUsCMY9XkgI1WbaPim9vQDsRa3Wi4Axn2ZK8vL3j8DvvD0kfmVpD7A==
```

## Upstream Intent

The upstream repository describes pdgkit as a browser-independent library, CLI,
and MCP server for PatentDSL `.pdg`. It converts `.pdg` into patent-style
figures and reference tables.

The note article explains the practical motivation:

- PatentDSL is sparse and mechanical enough that humans may not enjoy writing it
  by hand.
- That same sparseness is suitable for LLMs: few keywords, no coordinate choice,
  no color choice, no manual diagram type declaration in the ordinary source.
- Asking an AI to "draw" directly often produces a weak patent figure: missing
  or unstable reference numerals, language drift, unverifiable SVG/image logic,
  and poor relation to the written specification.
- The desired split is: AI writes `.pdg`; pdgkit validates and draws.

For research_x, the reusable upstream idea is therefore not "use SVG." The idea
is deterministic structure compilation:

```text
Codex/AI writes structure
-> pdgkit validates structure
-> pdgkit renders repeatable artifacts
-> humans inspect artifacts
```

## Repository Surface

The GitHub repository includes:

- `.github/workflows`
- `assets`
- `bin`
- `docs`
- `examples`
- `src`
- `tests`
- `LICENSE`
- `README.md`
- `package-lock.json`
- `package.json`
- `tsconfig.json`
- `tsup.config.ts`
- `vitest.config.ts`

The npm package installed locally includes the runtime distribution and user
documentation:

- `dist/core.*`
- `dist/index.*`
- `dist/pdgkit.*`
- `dist/pdgkit-mcp.*`
- `docs/ai-authoring-guide.md`
- `docs/spec.md`
- `examples/01-block.pdg` through `examples/09-handshake.pdg`
- font assets for export paths
- `README.md`
- `LICENSE`

The npm package is enough for local CLI/render work. It is not the same as
pinning and vendoring the full GitHub development source, tests, and CI.

## Package Surface

Observed package metadata and upstream README show:

- CLI binaries: `pdgkit`, `pdgkit-mcp`
- library import target: `@shibayama/pdgkit`
- command families: `render`, `validate`, `refs`, `guide`, `samples`, `version`,
  `help`
- input sources: file path, stdin, or built-in sample
- language modes: `ja`, `en`, `both`
- render formats: `svg`, `png`, `jpeg`, `pdf`, `pptx`
- editable PPTX mode: `--to pptx --editable`
- reference table formats: Markdown and CSV
- API concepts: parse, layout, render, validate, renderToSvg, renderToPng,
  renderToJpeg, renderToPdf, renderToPptx, refs, loadAuthoringGuide
- dependencies include MCP SDK and render/export packages such as resvg, jpeg,
  jsdom, jsPDF, and svg2pdf

The upstream architecture separates a pure core from Node-specific rendering and
export layers. SVG is the lowest-friction path. PDF/PPTX/raster paths can touch
heavier dependencies.

## Local Capability Check

Local package verification on 2026-06-24 used the pinned `0.1.2` package under
`tools/pdgkit_canary`.

Confirmed local commands against built-in sample input:

- `validate`
- `render --to svg`
- `render --to png`
- `render --to jpeg`
- `render --to pdf`
- `render --to pptx`
- `render --to pptx --editable`
- `refs --format md`
- `refs --format csv`

This confirms the local package can exercise the broader upstream surface. It
does not remove output-lane judgment: SVG remains the safest default, while
PNG/PDF/PPTX should be chosen when the task needs those formats and the rendered
artifact is inspected.

## Adoption Decision

State: `pinned_local_pdgkit_tool_lane`.

This replaces the older local framing:

```text
LIMITED local .pdg -> validate -> SVG artifact lane only
```

with:

```text
pinned local .pdg -> validate -> render/refs artifact lane
```

The dependency remains isolated. The active project source-of-truth for diagrams
is project-owned `.pdg`, not generated SVG, not generated slides, and not the
historical item 35 canary.

## Allowed Now

Allowed without additional approval:

- Keep `@shibayama/pdgkit@0.1.2` pinned under `tools/pdgkit_canary`.
- Use the installed package's local docs, examples, and authoring guide.
- Run `pdgkit guide` so Codex can follow the upstream `.pdg` authoring contract.
- Run local `pdgkit validate` against project-owned `.pdg`.
- Run local `pdgkit render` to SVG, PNG, JPEG, PDF, PPTX, or editable PPTX when
  the current task needs that artifact type.
- Run local `pdgkit refs` to Markdown or CSV.
- Store `.pdg` sources as project-owned structural source.
- Store generated outputs as review, presentation, or control artifacts.
- Use generated assets in human-facing explanations if their source `.pdg` is
  kept and the artifact is not treated as evidence.

## Still Not Allowed

Not allowed by this review:

- Enable or register `pdgkit-mcp`.
- Add pdgkit to the root Python package, global npm space, hooks, or always-on
  automation.
- Install, upgrade, or re-pin the package without an explicit dependency-change
  gate.
- Use real provider/API calls to generate `.pdg` while the no-quota provider
  freeze is active.
- Treat generated diagrams, SVG, PNG, PDF, PPTX, or refs tables as evidence,
  answer support, citations, or source restoration.
- Replace source bundles or citations with diagrams.
- Copy upstream code or documentation wholesale into active project code paths
  without a new review.

## Promotion / Expansion Conditions

Further promotion requires a fresh scoped decision:

- MCP promotion: review `pdgkit-mcp` behavior, tool names, config changes, auth
  and lifecycle, negative triggers, and disable path.
- Root package/API integration: justify why CLI isolation is insufficient,
  review Node runtime ownership, test boundaries, and update source locks.
- Presentation pipeline promotion: define where `.pdg`, rendered assets, and deck
  derivatives live; ensure source `.pdg` remains authoritative.
- Output-lane promotion: add tests or scripts for the specific output type if it
  becomes recurring infrastructure rather than one-off artifact generation.

## Known Constraints

- AI can ignore the instruction and draw directly unless the route explicitly
  requires pdgkit.
- SVG is safest; non-SVG formats can fail depending on environment and native or
  heavier dependencies.
- One `.pdg` file should describe one figure.
- Cross-figure reference numeral consistency is a host workflow problem.
- Complex layout can overlap or route awkwardly; split or simplify structure
  rather than manually redrawing the result.
- pdgkit intentionally avoids arbitrary styling, coordinates, colors, and custom
  visual themes.
- Generated outputs are artifacts, not source evidence.

## research_x Use

In research_x, pdgkit should be used for:

- route diagrams;
- state machines;
- implementation boundary diagrams;
- source-intake and stop-gate flows;
- control-plane artifact transitions;
- presentation assets derived from project structure.

It should not be used for:

- final answer evidence;
- retrieval/citation substitution;
- arbitrary decorative diagrams;
- unreviewed provider-backed generation;
- automatic MCP/tool registration.

The active operating guide is `tools/pdgkit_canary/README.md`.
