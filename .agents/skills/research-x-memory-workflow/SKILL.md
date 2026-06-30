---
name: research-x-memory-workflow
description: "Use when implementing or reviewing research_x memory-search pipeline work: Evidence/Source Bundle First, SearchLens/RetrievalPolicy, ObjectiveRoutePolicy, AnswerAuthorityGatekeeper, source restoration, context chunks, citations, API lanes, OCR/media, evals, workflow traces, app observability, retrieval strategy, or AI-callable local search."
---

# research-x Memory Workflow

Evidence pipeline owner for `research_x`. This Skill governs source restoration,
context chunks, citations, retrieval/eval contracts, and AI-callable local search.
It does not own personal Basic Memory, provider approval, or UI visibility
implementation beyond requiring traceable evidence state.

## Purpose

- Keep the memory-search system Evidence/Source Bundle first.
- Preserve restoration from every retrieval signal back to raw source and
  citation-ready support.
- Prevent generated labels, summaries, scores, media observations, and local
  hashes from becoming evidence by accident.
- Keep AI-callable answers bounded by evidence status and citations.
- Keep wide candidate generation separate from narrow answer-authority promotion.

## Use When

- Work touches source bundles, context chunks, citations, retrieval strategy,
  OCR/media evidence preparation, evals, workflow traces, or AI-callable local
  search.
- Architecture changes could alter the evidence pipeline or restoration path.
- A result needs to move from candidate signal to citation-ready support.

## Do Not Use When

- The user asks to remember or recall personal Codex notes; use
  `basic-memory-cli`.
- The issue is provider/API/quota permission; use `research-x-provider-gate`.
- The issue is app/CLI/run-state visibility; use
  `research-x-observability-review`.
- The issue is prompt/tool-boundary text; use `research-x-prompt-contract`.
- The work is only visual output planning; use the `.codex` publishing
  illustration helper.

## Inputs

- Current architecture docs, especially `docs/presentation/final-runtime-flow.md`,
  `docs/presentation/final-design-flow.md`, and `docs/memory-pipeline-v2.md`.
- Source bundle, raw source, searchable document, context chunk, citation,
  workflow trace, eval, or retrieval-route artifacts.
- Current milestone state from `PROJECT.md` when prioritizing work.

## Outputs

- Code/doc/test changes that preserve evidence boundaries.
- Evidence status, citation-readiness, route/eval warnings, and restoration gaps.
- Handoff requirements for provider guard, observability, prompt contract, or
  publishing output when those owners are involved.

## Steps

1. Read the two final flow docs before changing runtime/design order; read
   `docs/memory-pipeline-v2.md` before changing evidence mechanics.
2. Check `PROJECT.md` for current milestone state and gates.
3. Keep source-bundle restoration central: every retrieval arm must return to
   tweet, quote, media, author, bookmark account, URL, relation, time, and source
   hash where applicable.
4. Keep `SearchLens / RetrievalPolicy`, `ObjectiveRoutePolicy`,
   `ProviderApiBudgetGuard`, and `AnswerAuthorityGatekeeper` distinct.
5. Route provider/API/quota permission to `research-x-provider-gate`; keep local
   verification fake-first unless that gate is explicitly opened.
6. Verify with explicit `uv` commands and scoped tests.

## Safety Gates

- Real provider APIs are owned by `research-x-provider-gate`; approved lanes
  still require `ProviderApiBudgetGuard`.
- Diagnostic `local_hash` embeddings are wiring checks only.
- OCR/caption/VLM text must stay separate from raw media and corrected text until
  promoted through citation-ready context chunks.
- Contradictions must keep both source bundles; do not silently overwrite one
  with another.
- Forgetting must distinguish raw source, derived document, search projection,
  context chunk, and tombstone policy.

## Negative Triggers

- "Search result" is not a citation.
- "Generated summary" is not source evidence.
- "Raw media vector match" is only a candidate signal.
- "Basic Memory found it" is not `research_x` evidence.
- "Provider answered it" is not citation-ready without source restoration.

## Verification

- Confirm `raw source != searchable document != search result != source bundle
  != context chunk != citation != answer`.
- Confirm retrieval/eval reports restoration rate, unsupported context chunks,
  route gaps, and provider-gated lanes separately.
- Confirm every promoted answer can return to source bundle and citation IDs.
- Confirm provider-backed tests are fake/local or explicitly approved.

## Boundaries

- `research-x-research-intake` hands over only candidates with provenance, risk
  flags, and a source-bundle restoration path.
- `research-x-provider-gate` owns provider/API/quota permission.
- `research-x-observability-review` owns app/CLI visibility of stored state.
- `research-x-prompt-contract` owns prompt/tool contract text.
- Global `context-budget` may receive source pointers, hashes, trace paths, and
  evidence-critical items, but not replace evidence stores.
- Global `research-x-publishing-illustration` may receive claim/source maps;
  generated visuals remain output artifacts, not evidence.
