<!-- Historical consultation capture. Active path: README.md, tools/wbs_viewer/projects/research-x-work-state.json, docs/pdg/*.pdg, and .codex/context_offloads/pointer-map.json. Not evidence; do not update as an active tracker. -->

# WBS Viewer Canary Report

Date: 2026-06-23

## Scope

Item 11 WBS Viewer body-adoption canary for the X/GPT 35-item implementation flow.

## Inputs

- Plan: `.codex/chatgpt-control/x-url-analysis-20260622/implementation-plan-11-35.md`
- Decision summary: `.codex/chatgpt-control/x-url-analysis-20260622/current-decision-summary.md`
- Upstream review: `tools/wbs_viewer/UPSTREAM.md`
- Vendored viewer: `tools/wbs_viewer/vendor/single-file-wbs-v1.2.0/wbs_viewer.html`
- WBS data: `.codex/chatgpt-control/x-url-analysis-20260622/wbs-35-item-flow.json`

## Verification

Local checks completed:

- JSON parses successfully.
- WBS project count: 1.
- WBS group count: 6.
- WBS leaf task count: 35.
- Milestone count: 3.
- Playwright loaded the vendored HTML locally and selected `wbs-35-item-flow.json` through the
  fallback file input.
- Rendered page contained:
  - `X/GPT 35-item adoption flow`
  - `11 WBS Viewer body adoption`
  - `35 pdgkit body adoption`

Generated screenshot:

- `.codex/chatgpt-control/x-url-analysis-20260622/wbs-35-item-flow-screenshot.png`

## Decision

Item 11 result: `keep vendored viewer`.

Reason:

- The pinned upstream copy rendered the 35-item flow without modification.
- JSON custom fields were enough for item number, source URL, decision band, gate, and artifact
  links.
- No fork/customization is needed for this canary.

Limits:

- The viewer is a local visual review surface only.
- Markdown files and source locks remain the decision records.
- Generated screenshots and rendered WBS views are not evidence.
- Browser editing is not required for Codex; Codex should update the JSON source directly.

Next boundary:

- Move to item 35 pdgkit source/dependency review and body-adoption canary.
