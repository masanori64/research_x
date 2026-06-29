# WBS Viewer Tool

This folder vendors the WBS Viewer reviewed during the X/GPT item 11 canary and
provides a local review surface for the `research_x` canonical work-state JSON.
Item 11 is historical intake state, not the general name of this WBS lane.

## Upstream Copy

The upstream viewer is vendored unchanged under:

- `tools/wbs_viewer/vendor/single-file-wbs-v1.3.0/`

Pinned source:

- Repository: `https://github.com/piguo45/single-file-wbs`
- Tag: `v1.3.0`
- Tag object: `06ab5981baa68a6a938f236691bc642ec7d670a9`
- Commit: `b1ef3d7e175dedfd9f4f34a9984437b174469c76`
- Release `wbs_viewer.html` SHA-256:
  `c92b71b83075d2c6ae1108166ccceb90590e901914e7b57ce9843a5c885bea97`
- License: MIT

See `UPSTREAM.md` for source review and adoption gates.

## Canonical Work State

The current project-owned WBS source is:

```text
tools/wbs_viewer/projects/research-x-work-state.json
```

Open `vendor/single-file-wbs-v1.3.0/wbs_viewer.html` in Chrome or another Chromium
browser, then load the JSON file through the viewer's file picker.

Historical or compatibility WBS files may remain in other folders, but they are not
the update target unless a task explicitly says so.

## Boundary

WBS owns operational state:

- candidate and phase queues;
- planned/actual dates;
- gate, decision band, status, next action, and artifact pointers;
- completed, blocked, closed, archived, or active work.
- viewer-only calendar display configuration such as top-level `holidays`.

WBS must not carry long rationale, source review prose, context chunks, citations,
answer support, legal/business-calendar authority, or provider execution permission.
Codex edits the JSON source; browser editing remains optional human review.
