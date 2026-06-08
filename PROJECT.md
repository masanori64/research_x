# Memory Search Project Plan

This file is the short implementation tracker for the memory-search branch.

Detailed architecture source:

```text
docs/memory-pipeline-v2.md
```

Do not duplicate detailed architecture here. Keep this file small enough that an agent can quickly
see what is implemented, what is gated, and what comes next.

## Documentation Boundary

- `AGENTS.md`: always-read agent rules, command policy, completion notification, publish policy.
- `README.md`: human repository entry point and current CLI surface.
- `PROJECT.md`: short memory-search milestone tracker.
- `docs/memory-pipeline-v2.md`: detailed source of truth for the AI-callable evidence pipeline.
- `docs/memory-pipeline-archive.md`: indexed historical decision archive; inspect targeted sections
  only when prior research is needed.
- `docs/pipeline.md`: acquisition/auth/provider pipeline details.

Do not add new memory-architecture Markdown files unless the user explicitly asks.

## Goal

Build a local, user-specific search tool over the existing X collection DB. The tool should let an
AI agent search accumulated X bookmarks/tweets like a local web-research tool while preserving
provenance, account-specific bookmark ownership, quote/media context, and the user's subjective
interests.

Current top-level direction:

- Evidence / Source Bundle first.
- ObjectiveRoutePolicy chooses primary, fallback, and escalation routes; it is not evidence.
- Real API embeddings, rerankers, OCR, Reader, and managed-RAG are provider arms behind gates, not
  the system objective.
- Corpus2Skill is a navigation map and route hint, not citation-ready evidence.
- Generated labels, summaries, query transforms, media roles, and observations are derived hints
  unless promoted through explicit evidence contracts.

Core invariant:

```text
raw source != searchable document != search result != context chunk != citation != answer
```

## Current Canonical Data

Raw acquisition data remains canonical and must not be replaced by summaries or generated answers:

- `tweets`
- `account_bookmarks`
- `collection_items`
- `tweet_edges`
- `media`
- `raw_payloads`
- `ai_labels`
- `accounts`
- `provider_runs`

## Implemented Foundation

Implemented memory subsystems are grouped by behavior rather than file inventory:

- corpus/schema/search/context: rebuildable `memory_documents`, FTS, local search, context chunks,
  retrieval-text FTS projections, citation annotations, evidence bundles, and source-bundle
  restoration;
- derived/relations/freshness: place, author, ticker-event, topic-thread derived docs; quote,
  media, bookmark, duplicate, same-topic, stale/newer, and optional judged relation edges;
- external/reader/llm_context: fake/Serper URL discovery, fake/HTTP/Jina Reader contract, extracted
  external context chunks, and fake/Brave-style LLM context role;
- answer/workflow/eval: bounded workflows, answer artifacts, answer citations, route eval cases,
  stored eval runs, question-type coverage, and feedback records;
- portfolio/rerank/retrieval_strategy: evidence-first portfolio eval, guarded RRF, route strategy
  catalog, fake-first rerank contract, and real reranker entry points behind provider gates;
- embeddings/media_embeddings: real text embedding providers, diagnostic-only `local_hash`,
  provider/profile/source-hash coverage, Gemini Embedding 2 text and native media contracts, media
  search, native-media source-bundle restoration, and optional local vector projection acceleration
  over one current embedding scope;
- OCR/media_roles/observations: no-spend OCR quality profiling, region/crop contracts, engine
  routing, second-pass metadata, corrected-text profiles, OCR chunk promotion, media role
  annotations, candidate-set OCR, and Codex/VLM observation import as inference annotations;
- objective_routes/objective_executor/final_skeleton: ObjectiveRoutePlan, no-spend route execution,
  route fallback/escalation traces, provider-skip metadata, research-task/search-plan/coverage/gap
  artifacts, and final skeleton preflight up to the provider-quota gate;
- api_budget/api_lane_estimate/audit: local API budget policies, usage ledger, kill switch,
  monitoring commands, offline lane estimates, claim/citation and lineage audit checks, strict
  audit checks, and pytest diagnostics.

## Implemented Command Surface

Representative current commands:

```text
memory api-budget
memory api-usage
memory api-watch
memory api-lane-estimate
memory build-corpus
memory build-derived
memory audit
memory build-embeddings
memory embedding-estimate
memory embedding-specs
memory embedding-coverage
memory build-vector-projection
memory vector-projection-coverage
memory media-embedding-estimate
memory build-media-embeddings
memory media-embedding-coverage
memory media-search
memory ocr-estimate
memory media-role-estimate
memory media-role-build
memory media-role-coverage
memory build-ocr-evidence
memory ocr-coverage
memory ocr-promote-chunks
memory ocr-second-pass
memory media-observation-add
memory media-observation-import
memory media-observation-coverage
memory ocr-search
memory build-relations
memory relations
memory judge-relations
memory search
memory plan
memory evidence
memory context
memory answer
memory workflow
memory external-search
memory extract-url
memory llm-context
memory feedback
memory export-corpus2skill
memory eval
memory portfolio-eval
memory eval-runs
memory eval-show
memory question-types
memory objective-routes
memory objective-execute
memory final-skeleton-preflight
memory build-retrieval-text
memory retrieval-text-coverage
memory retrieval-strategies
memory rerank
```

Use `uv run python -m research_x memory --help` as the command surface check.

## Completed Milestones

### V2 Evidence Objects

- [x] Build corpus, derived docs, relations, search results, context chunks, citations, answers,
      workflow traces, feedback, eval cases, and audit checks over the canonical X store.
- [x] Add external URL discovery, reader/extract, LLM-context, and answer citation contracts without
      making external Web artifacts canonical truth.
- [x] Add Corpus2Skill export as a navigation-map boundary, not as source evidence.

### Evidence/Skill/Workflow Alignment

- [x] Realign strategy defaults so embeddings are optional recall arms rather than the production
      center.
- [x] Expose Corpus2Skill navigation, bounded workflow orchestration, API embedding portfolio,
      rerank stages, claim verification, freshness lineage, and media routes in one strategy
      catalog.
- [x] Keep diagnostic `local_hash` blocked from promotion.

### Provider Lane Preflight And Budget Guard

- [x] Split provider candidates into embedding, rerank, reader/OCR/media, external search,
      classifier, answer, relation judge, and managed-RAG reference lanes.
- [x] Keep strategy-catalog candidates and API-lane estimate rows aligned for the runnable provider
      arms, while leaving legacy, local-compatible, and auth-gated references explicitly gated.
- [x] Distinguish embedding technical canaries and eval slices from production-scope embedding
      builds; limited text embedding runs do not count as full search indexes.
- [x] Add no-spend `api-lane-estimate`, checked default price seeding, local API budget policy,
      usage ledger, kill switch, app/CLI monitoring, and guarded provider call sites.
- [x] Freeze paid, free-tier, trial-credit, and zero-dollar quota calls unless explicitly lifted in
      the current conversation.

### Objective-Fit Media Evidence

- [x] Add media embedding schema, media input resolution, Gemini Embedding 2 native media provider
      support, media embedding estimate/build/coverage/search commands, and media source-bundle
      restoration.
- [x] Add OCR Evidence Quality Pipeline storage and commands: quality profiling, deterministic
      region/crop contracts, reading order, engine routing, fake OCR, second-pass metadata,
      corrected-text profiles, chunk promotion, coverage, and OCR search.
- [x] Add media role classification and evidence actions as no-spend routing annotations.
- [x] Add Codex/VLM media observations as inference annotations that can help search without
      becoming raw facts.

### Final Skeleton Execution Surface

- [x] Add QueryTransform and RetrievalTextProfile artifacts so generated query/search text is not
      mistaken for evidence.
- [x] Split eval surfaces into route, retrieval, context, citation, answer, and abstention gates.
- [x] Add ObjectiveRoutePlan and no-spend ObjectiveRouteExecution with primary route, fallback
      routes, escalation triggers, provider-skip traces, candidate-set OCR, and source-bundle
      restoration failure metadata.
- [x] Add research-control artifacts so URL discovery, query fan-out, provider summaries, and
      personalization signals stay citation-excluded until restored into source bundles and context
      chunks.
- [x] Add projection generation, index membership, trust boundary, taint flags, account/source
      visibility, allowed sinks, and final-skeleton preflight.

## Current Gates

### Provider-Quota Gate

Do not run real provider API calls while the no-quota freeze is active. This includes paid usage,
free-tier usage, trial credits, and zero-dollar quota consumption.

Blocked until explicitly lifted in the current conversation:

- real text embedding builds;
- real native media embedding builds;
- real reranker calls;
- real Reader/Jina extraction calls;
- real OCR calls;
- real classifier, answer, relation judge, external-search, LLM-context, or managed-RAG calls.

Before the first provider call after the freeze is lifted:

1. run `memory api-budget status`;
2. run `memory api-lane-estimate`;
3. review estimated cost, coverage, price source, provider/model/profile, and smallest useful
   limit;
4. start with the smallest scoped build or eval, then expand only after coverage is correct.

### Local-Dependency Gate

These are not hidden future work, but they require explicit local dependency/model decisions:

- PaddleOCR / PaddleOCR-VL / manga OCR local providers;
- local or OpenAI-compatible Qwen embedding/rerank endpoints;
- running the OSS Corpus2Skill compiler over exported bundles.

The provider contracts and export boundaries exist; dependency installation and model execution are
separate gated steps.

## Next Work

No-spend closure state:

- strategy catalog statuses are classified as implemented/candidate, human gate, or reference-only;
- strict audit exposes hidden no-spend gaps if new `needs_*` statuses are introduced;
- exact-anchor, relation, and retrieval-text arms are visible in portfolio/eval;
- deterministic claim/citation and freshness/projection lineage checks are part of audit.

Remaining gates:

- provider-quota gate: real embedding, rerank, Reader, OCR, classifier, answer, relation judge,
  external-search, LLM-context, or managed-RAG calls;
- local-dependency gate: PaddleOCR/PaddleOCR-VL/manga OCR, local Qwen-style endpoints, and OSS
  Corpus2Skill compiler execution.

## Implementation Rules

- Use `uv run python ...`, `uv run pytest ...`, and
  `uv run ruff check src\research_x tests`.
- If pytest is slow or appears stuck, use `uv run python -m research_x test-diagnose ...` to
  isolate slow tests before changing behavior or dropping coverage.
- Update `docs/memory-pipeline-v2.md` before code when a design decision changes.
- Keep `PROJECT.md` as a tracker only; do not add research logs or detailed architecture here.
- Prefer SQLite tables and explicit contracts before adding frameworks.
- Never stage `.secrets/` or `runs/`.
- Commit and push completed scoped implementation work unless blocked by unrelated changes.
