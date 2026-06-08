---
name: research-x-memory-workflow
description: Use when implementing or reviewing research_x memory-search pipeline changes, including Evidence/Source Bundle First, ObjectiveRoutePolicy, source restoration, context chunks, citations, API lanes, OCR/media, evals, workflow traces, or app observability.
---

# research-x Memory Workflow

Use this skill for memory-search architecture or implementation work.

## Source Files

- Read `docs/memory-pipeline-v2.md` for current architecture.
- Read `PROJECT.md` for current milestone state and gates.
- Read `README.md` only when public command surface or user-facing usage changes.

## Invariants

- Evidence / Source Bundle first.
- ObjectiveRoutePolicy controls routes; it is not evidence.
- Generated labels, summaries, query transforms, media roles, observations, and scores are hints
  until promoted through evidence contracts.
- `raw source != searchable document != search result != context chunk != citation != answer`.
- Real provider APIs are gated by no-quota freeze and API Budget Guard.
- Diagnostic `local_hash` embeddings are wiring checks only.

## Workflow

1. Update the relevant Markdown source of truth before code when changing architecture.
2. Keep source-bundle restoration central: every retrieval arm must return to tweet, quote, media,
   author, bookmark account, URL, relation, time, and source hash where applicable.
3. Preserve no-spend/fake-first verification unless the user explicitly lifts the provider freeze.
4. Expose hidden run state through CLI/app traces when the user reports black-box behavior.
5. Verify with explicit `uv` commands and commit/push scoped changes.
