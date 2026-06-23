# WBS Viewer Upstream Review

Date: 2026-06-23

## Source

- Candidate: item 11, WBS Viewer / `single-file-wbs`
- Repository: `https://github.com/piguo45/single-file-wbs`
- Pinned tag: `v1.2.0`
- Pinned commit: `322895a23f49028b53ae8c8a1710d6db45cdf726`
- License: MIT

## Vendored Files

Vendored unchanged under `tools/wbs_viewer/vendor/single-file-wbs-v1.2.0/`:

- `wbs_viewer.html`
- `wbs_sample.json`
- `wbs_roadmap.json`
- `README.md`
- `README.en.md`
- `CLAUDE.md`
- `CLAUDE.en.md`
- `LICENSE`

## Review

WBS Viewer is a single local HTML viewer for WBS/Gantt/progress-line JSON files. It is appropriate
for the item 11 canary because it keeps the visual state separate from the JSON source and does not
require a server, build step, CDN, plugin, MCP server, provider API, or hosted service for viewing.

Known runtime constraints:

- Viewing is local-file friendly.
- Editing uses Chromium File System Access APIs.
- Chrome or another Chromium browser is the practical target.
- Firefox and Safari are not target browsers for editing.
- The viewer uses `localStorage` for UI preferences.
- Generated visuals are review artifacts, not project evidence.

## Decision

State: `pinned_local_tool_canary`.

Allowed now:

- Keep the pinned upstream copy.
- Load a project-owned WBS JSON canary manually in Chromium.
- Use the rendered view to inspect phase/progress status.

Not allowed by this review:

- Treat WBS JSON or rendered visuals as architecture source of truth.
- Enable any plugin, MCP server, hook, provider, or external service.
- Modify upstream files in place for project-specific behavior.
- Store secrets, credentials, provider keys, or private tokens in WBS JSON.

Promotion condition:

- If the canary proves useful and JSON custom fields are sufficient, keep the vendored viewer as a
  local tool.
- If first-class `research_x` columns or interactions are needed, fork into a project-owned viewer
  instead of editing the vendored upstream copy.
