# pdgkit Canary

This folder contains the isolated `@shibayama/pdgkit` dependency used to validate
and render PDG sources. It is a tool environment, not the owner of project
architecture.

The X/GPT item 35 canary explains why this dependency entered the project, but
item 35 is historical intake state. The general project mechanism is PDG source
under `docs/pdg/*.pdg`.

## Package

- npm package: `@shibayama/pdgkit`
- pinned version: `0.1.2`
- command: `pdgkit`
- MCP command present but not enabled: `pdgkit-mcp`

The package is installed only inside this folder for canary and render work.
`node_modules/` is ignored. `package-lock.json` is tracked for reproducibility.

## Canary Fixtures

Canary source:

```text
tools/pdgkit_canary/canaries/item-11-35-flow.pdg
```

Canary generated output:

```text
tools/pdgkit_canary/out/item-11-35-flow.svg
```

## Project-Owned PDG Sources

Current structural sources live outside this canary folder:

```text
docs/pdg/memory-evidence-pipeline.pdg
docs/pdg/objective-route-policy.pdg
docs/pdg/source-intake-gate-flow.pdg
docs/pdg/visual-context-offload-lane.pdg
```

Generated review SVGs live in:

```text
docs/pdg/out/*.svg
```

Validate/render project sources from this folder with `npx --no-install`:

```powershell
cd tools\pdgkit_canary
npx --no-install pdgkit validate ..\..\docs\pdg\memory-evidence-pipeline.pdg --lang en
npx --no-install pdgkit render ..\..\docs\pdg\memory-evidence-pipeline.pdg --lang en -o ..\..\docs\pdg\out\memory-evidence-pipeline.svg
```

Repeat for each `docs/pdg/*.pdg`.

## Boundary

Use PDG for structural context: route diagrams, state machines, implementation
boundary flows, and artifact transitions.

Generated SVGs are review artifacts, not evidence. `pdgkit-mcp`, hooks, browser-edit
defaults, provider calls, root dependency adoption, and automatic project actions
remain out of scope unless separately approved.
