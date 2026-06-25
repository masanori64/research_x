# Memory Search Project Plan

This file is the short tracker for the `research_x` memory-search branch.
It is not the state database and not the architecture archive.

## Goal

Build a local, user-specific search tool over the existing X collection DB that an AI
agent can call as an external research tool while preserving provenance,
account-specific bookmark ownership, quote/media context, and the user's subjective
interests.

`research_x` is not the Codex foundation. Codex-wide Skills, self-improvement,
session memory, retrospectives, Skill/Plugin/MCP governance, and external Codex
foundation candidates belong in `maasa/.codex`. This project keeps only the thin
bridge needed for AI tool use: query/objective/context-budget/source-candidate in,
evidence status, citations, answer/abstain/provider-gated state, and audit trace out.

## Canonical Pointers

- Current evidence architecture: `docs/memory-pipeline-v2.md`
- Current work state: `tools/wbs_viewer/projects/research-x-work-state.json`
- Context/offload pointer index: `.codex/context_offloads/pointer-map.json`
- Presentation generation flow:
  `.codex/implementation-plans/2026-06-24-presentation-generation-flow.md`
- Acquisition/auth/provider pipeline: `docs/pipeline.md`
- Historical rationale archive: `docs/memory-pipeline-archive.md`

## Evidence Invariant

```text
raw source != searchable document != search result != source bundle
!= context chunk != citation != answer
```

WBS JSON, generated diagrams, screenshots, pointer maps, consultation captures,
rendered HTML views, and compressed summaries are control or review artifacts.
They are not evidence, citations, answer support, or provider execution
permission.

## Active Gates

- No real provider API, free-tier, trial-credit, or zero-dollar quota use while the
  no-quota freeze is active.
- Provider, Reader, external search, OCR, rerank, classifier, answer, embedding,
  managed-RAG, and real-model prompt checks require explicit approval plus the API
  Budget Guard preflight.
- Dependency installs, model downloads, plugins, MCP servers, hooks, browser-edit
  defaults, connector changes, and third-party Skill enablement are separate gates.
- Source candidates from X/GPT/ChatGPT/community material remain source candidates
  until restored into source bundles, context chunks, and citation annotations.
- Automatic Skill growth is not allowed; lifecycle inputs stay proposal-only until
  replay, qualifier, and human accept/reject gates are explicit. The owning surface
  for that lifecycle is `maasa/.codex`; `research_x` may emit search-quality bridge
  signals only.
- External candidates are classified by adoption shape: `adopt`, `bridge`,
  `staging`, `provider_gated`, or `historical`. Hook/MCP/plugin/dependency risk is
  staged, not treated as a permanent rejection; provider/API quota remains gated.
- The current machine-readable adoption boundary is `.codex/adoption_registry.toml`.
  It is the registry for what this project owns, what it only bridges to
  `maasa/.codex`, and what remains provider-gated or historical.

## Current Tracker Rule

Operational state, candidate bands, completed/blocked/closed status, planned and
actual dates, artifact pointers, and remaining local gates live in:

```text
tools/wbs_viewer/projects/research-x-work-state.json
```

Do not mirror that task state back into this file. If a gate, candidate, or phase
state changes, update the WBS and only adjust this file when a top-level boundary or
canonical pointer changes.

## Implementation Rules

- Use `uv run python ...`, `uv run pytest ...`, and explicit
  `uv run ruff check <targets>` commands.
- If pytest is slow or appears stuck, use
  `uv run python -m research_x test-diagnose ...` before narrowing coverage by hand.
- Update `docs/memory-pipeline-v2.md` before code only when the evidence contract or
  architecture boundary changes.
- Keep `PROJECT.md` under 100 lines and free of phase tables, 35-item lists, and
  historical progress logs.
- Never stage `.secrets/` or `runs/`.
- Commit and push completed scoped implementation work when separable and clear.
