# pdgkit Upstream Review

Date: 2026-06-23

## Source

- Candidate: item 35, pdgkit OSS
- Repository: `https://github.com/shibayamalicht/pdgkit`
- npm package: `@shibayama/pdgkit`
- Pinned package version: `0.1.2`
- License: MIT
- Node requirement: `>=18`

## Package Surface

Observed package metadata:

- CLI binaries: `pdgkit`, `pdgkit-mcp`
- Runtime dependencies include MCP SDK and render/export packages.
- `pdgkit validate` and SVG `pdgkit render` are sufficient for this canary.
- `pdgkit-mcp` is present but not enabled or registered.

## Review

pdgkit is appropriate for an item 35 body-adoption canary because it implements the actual
`DSL -> validate -> render` pipeline that the source item proposed. It is not only a pattern
reference. The canary uses the real CLI/library through a pinned npm dependency and keeps package
state isolated under `tools/pdgkit_canary/`.

Known constraints:

- The package has multiple Node dependencies even when the first canary uses only validate/SVG.
- MCP enablement is a separate trust and configuration gate.
- SVG output is the first target because README describes it as the reliable default path.
- PNG/PDF/PPTX output should be evaluated only after the SVG path is accepted.

## Decision

State: `pinned_body_adoption_canary`.

Allowed now:

- Keep `@shibayama/pdgkit@0.1.2` pinned in `tools/pdgkit_canary/package-lock.json`.
- Run local `pdgkit validate` and SVG `pdgkit render` against project-owned `.pdg` canaries.
- Record generated SVG as a review artifact.

Not allowed by this review:

- Enable or register `pdgkit-mcp`.
- Treat generated diagrams as evidence.
- Add pdgkit to the root Python package or global toolchain.
- Use provider/API calls to generate `.pdg`.
- Promote PNG/PDF/PPTX export until SVG canary is accepted.

Promotion condition:

- If `.pdg` sources validate reliably and SVG output is deterministic and reviewable, keep a
  limited project-owned `.pdg` artifact lane for selected spec diagrams.
