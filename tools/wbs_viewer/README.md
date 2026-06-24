# WBS Viewer Tool

This folder vendors the WBS Viewer reviewed during the X/GPT item 11 canary and
provides a local review surface for the `research_x` canonical work-state JSON.
Item 11 is historical intake state, not the general name of this WBS lane.

## Upstream Copy

The upstream viewer is vendored unchanged under:

- `tools/wbs_viewer/vendor/single-file-wbs-v1.2.0/`

Pinned source:

- Repository: `https://github.com/piguo45/single-file-wbs`
- Tag: `v1.2.0`
- Commit: `322895a23f49028b53ae8c8a1710d6db45cdf726`
- License: MIT

See `UPSTREAM.md` for source review and adoption gates.

## Canonical Work State

The current project-owned WBS source is:

```text
tools/wbs_viewer/projects/research-x-work-state.json
```

Open `vendor/single-file-wbs-v1.2.0/wbs_viewer.html` in Chrome or another Chromium
browser, then load the JSON file through the viewer's file picker.

Historical or compatibility WBS files may remain in other folders, but they are not
the update target unless a task explicitly says so.

## Boundary

WBS owns operational state:

- candidate and phase queues;
- planned/actual dates;
- gate, decision band, status, next action, and artifact pointers;
- completed, blocked, closed, archived, or active work.

WBS must not carry long rationale, source review prose, context chunks, citations,
answer support, or provider execution permission. Codex edits the JSON source;
browser editing remains optional human review.
