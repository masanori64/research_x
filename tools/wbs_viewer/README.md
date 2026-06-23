# WBS Viewer Tool

This folder contains the item 11 WBS Viewer body-adoption canary for the X/GPT
35-item implementation flow.

## Upstream Copy

The upstream viewer is vendored unchanged under:

- `tools/wbs_viewer/vendor/single-file-wbs-v1.2.0/`

Pinned source:

- Repository: `https://github.com/piguo45/single-file-wbs`
- Tag: `v1.2.0`
- Commit: `322895a23f49028b53ae8c8a1710d6db45cdf726`
- License: MIT

See `UPSTREAM.md` for the source review and adoption gate.

## Canary Data

The first `research_x` WBS canary data file is:

- `.codex/chatgpt-control/x-url-analysis-20260622/wbs-35-item-flow.json`

Open `vendor/single-file-wbs-v1.2.0/wbs_viewer.html` in Chrome or another Chromium browser, then
load the JSON file through the viewer's file picker.

Generated visuals are planning/review artifacts only. The Markdown and source files remain the
decision records.
