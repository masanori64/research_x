<!-- Historical consultation capture. Active path: README.md, tools/wbs_viewer/projects/research-x-work-state.json, docs/pdg/*.pdg, and .codex/context_offloads/pointer-map.json. Not evidence; do not update as an active tracker. -->

# pdgkit Canary Report

Date: 2026-06-23

## Scope

Item 35 pdgkit body-adoption canary for the X/GPT 35-item implementation flow.

## Inputs

- Plan: `.codex/chatgpt-control/x-url-analysis-20260622/implementation-plan-11-35.md`
- Decision summary: `.codex/chatgpt-control/x-url-analysis-20260622/current-decision-summary.md`
- Upstream review: `tools/pdgkit_canary/UPSTREAM.md`
- Package definition: `tools/pdgkit_canary/package.json`
- Package lock: `tools/pdgkit_canary/package-lock.json`
- Canary source: `tools/pdgkit_canary/canaries/item-11-35-flow.pdg`

## Package

- npm package: `@shibayama/pdgkit`
- Version: `0.1.2`
- License: MIT
- Node requirement: `>=18`
- Local Node used: `v24.16.0`
- Local npm used: `11.13.0`
- Install scope: `tools/pdgkit_canary/`
- npm audit at install: 0 vulnerabilities

## Verification

Commands completed under `tools/pdgkit_canary/`:

- `npx pdgkit --help`
- `npx pdgkit samples`
- `npx pdgkit validate canaries\item-11-35-flow.pdg --lang en`
- `npx pdgkit render canaries\item-11-35-flow.pdg --lang en -o out\item-11-35-flow.svg`

Validation result:

- Kind: `flow`
- Diagnostics: 0 errors, 0 warnings, 0 info

Render result:

- Output: `tools/pdgkit_canary/out/item-11-35-flow.svg`
- Bytes: 9202
- SHA-256: `1023BB0031CC07D94150CCCAD13771A440C7F2094A430770E50FA65A4CB8B623`
- Determinism check: two renders from the same source produced the same SHA-256.

## Mermaid Comparison

Mermaid remains enough for lightweight Markdown-only flow diagrams. pdgkit is better only when the
project wants a checked source artifact with a real validation command and deterministic SVG output.

For this project, pdgkit should not replace all Mermaid diagrams. It should be used for selected
specification diagrams or review artifacts where validation and source preservation matter.

## Decision

Item 35 result: `LIMITED`.

Allowed now:

- Keep `@shibayama/pdgkit@0.1.2` as an isolated canary dependency in `tools/pdgkit_canary/`.
- Keep `.pdg` source files and generated SVG review artifacts for selected spec/flow diagrams.
- Use `pdgkit validate` before `pdgkit render`.

Not allowed now:

- No `pdgkit-mcp` registration.
- No provider/API use to generate `.pdg`.
- No PNG/PDF/PPTX promotion yet.
- No root project dependency or global install.
- No treating generated diagrams as evidence.

Next boundary:

- Reopen only for a scoped `.pdg` artifact lane or for explicit MCP/export-format evaluation.
