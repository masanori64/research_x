# WBS Viewer Upstream Review

Date: 2026-06-29

## Source

- Candidate: item 11, WBS Viewer / `single-file-wbs`
- Repository: `https://github.com/piguo45/single-file-wbs`
- Pinned tag: `v1.3.0`
- Pinned tag object: `06ab5981baa68a6a938f236691bc642ec7d670a9`
- Pinned commit: `b1ef3d7e175dedfd9f4f34a9984437b174469c76`
- Release `wbs_viewer.html` SHA-256:
  `c92b71b83075d2c6ae1108166ccceb90590e901914e7b57ce9843a5c885bea97`
- License: MIT

## Vendored Files

Vendored unchanged under `tools/wbs_viewer/vendor/single-file-wbs-v1.3.0/`:

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

The `v1.3.0` release adds top-level `holidays` calendar display support, holiday-aware remaining
business day calculation, nested child task creation in edit mode, milestone GUI editing, and a
plain display toggle. In `research_x`, `holidays` is allowed only as viewer display configuration
inside the WBS JSON.

Known runtime constraints:

- Viewing is local-file friendly.
- Editing uses Chromium File System Access APIs.
- Chrome or another Chromium browser is the practical target.
- Firefox and Safari are not target browsers for editing.
- The viewer uses `localStorage` for UI preferences.
- Generated visuals are review artifacts, not project evidence.
- Holiday shading and remaining-business-day labels are planning/display aids, not legal or
  source-evidence authority.
- Current runtime/design authority remains in `docs/presentation/final-runtime-flow.md` and
  `docs/presentation/final-design-flow.md`; the WBS viewer only visualizes work state.

## Decision

State: `pinned_local_tool`.

Allowed now:

- Keep the pinned upstream copy.
- Load a project-owned WBS JSON canary manually in Chromium.
- Use the rendered view to inspect phase/progress status.
- Keep top-level `holidays` in project-owned WBS JSON for local calendar display.

Not allowed by this review:

- Treat WBS JSON or rendered visuals as architecture source of truth.
- Treat WBS JSON or rendered visuals as replacements for source bundles, context chunks,
  citations, `AnswerAuthorityGatekeeper`, or final-flow docs.
- Enable any plugin, MCP server, hook, provider, or external service.
- Modify upstream files in place for project-specific behavior.
- Store secrets, credentials, provider keys, or private tokens in WBS JSON.
- Treat holiday settings or rendered day counts as citation-ready evidence.

Promotion condition:

- If the canary proves useful and JSON custom fields are sufficient, keep the vendored viewer as a
  local tool.
- If first-class `research_x` columns or interactions are needed, fork into a project-owned viewer
  instead of editing the vendored upstream copy.
