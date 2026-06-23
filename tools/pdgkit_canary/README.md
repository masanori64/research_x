# pdgkit Canary

This folder contains the item 35 pdgkit body-adoption canary for `research_x`.

## Package

- npm package: `@shibayama/pdgkit`
- pinned version: `0.1.2`
- command: `pdgkit`
- MCP command present but not enabled: `pdgkit-mcp`

The package is installed only inside this folder for the canary. `node_modules/` is ignored and is
not part of the repository state. `package-lock.json` is tracked to keep the canary reproducible.

## Canary

Source:

- `canaries/item-11-35-flow.pdg`

Generated output:

- `out/item-11-35-flow.svg`

Run locally:

```powershell
cd tools\pdgkit_canary
npm install
npx pdgkit validate canaries\item-11-35-flow.pdg --lang en
npx pdgkit render canaries\item-11-35-flow.pdg --lang en -o out\item-11-35-flow.svg
```

Generated SVG is a review artifact, not evidence. MCP registration remains out of scope for this
canary.
