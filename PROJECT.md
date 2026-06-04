# Memory Search Project Plan

This file is the implementation milestone tracker for the memory-search branch.

The detailed architecture source is:

```text
docs/memory-pipeline-v2.md
```

Do not duplicate the architecture here. Keep this file short enough that an agent can quickly see
what is done, what is next, and which commands are expected to work.

## Documentation Boundary

- `AGENTS.md`: always-read agent rules, command policy, completion notification.
- `README.md`: repository entry point and current CLI surface.
- `PROJECT.md`: memory-search implementation checklist.
- `docs/memory-pipeline-v2.md`: single detailed source of truth for the AI-callable evidence
  pipeline.
- `docs/memory-pipeline-archive.md`: indexed historical decision archive; read only targeted
  sections when prior research is needed.
- `docs/pipeline.md`: acquisition/auth/provider pipeline details.

Do not add new memory-architecture Markdown files unless the user explicitly asks.

## Goal

Build a local, user-specific search tool over the existing X collection DB. The tool should let an
AI agent search the user's accumulated X bookmarks/tweets like a local web-research tool while
preserving provenance, account-specific bookmark ownership, quote/media context, and the user's
subjective interests.

Top-level direction:

- Evidence/Skill/Workflow first.
- Real API embeddings are optional recall arms, not the production center.
- Corpus2Skill is a navigation map and route hint, not citation-ready evidence.
- Bounded workflows choose tools; open-ended agent loops are not the default path.

Core invariant:

```text
raw source != searchable document != search result != context chunk != citation != answer
```

## Current Source Of Truth

Raw acquisition data remains canonical:

- `tweets`
- `account_bookmarks`
- `collection_items`
- `tweet_edges`
- `media`
- `raw_payloads`
- `ai_labels`
- `accounts`
- `provider_runs`

Raw records must not be replaced by summaries or generated answers.

## Implemented Foundation

Current package:

```text
src/research_x/memory/
  corpus.py
  schema.py
  search.py
  context.py
  derived.py
  evidence.py
  external.py
  reader.py
  feedback.py
  embeddings.py
  relations.py
  audit.py
  query.py
  evals.py
  llm_context.py
  answer.py
  workflow.py
  portfolio.py
```

Implemented commands:

```text
research_x memory build-corpus
research_x memory build-derived
research_x memory audit
research_x memory build-embeddings
research_x memory embedding-estimate
research_x memory embedding-specs
research_x memory embedding-coverage
research_x memory build-relations
research_x memory relations
research_x memory judge-relations
research_x memory plan
research_x memory search
research_x memory evidence
research_x memory context
research_x memory external-search
research_x memory extract-url
research_x memory llm-context
research_x memory answer
research_x memory workflow
research_x memory portfolio-eval
research_x memory export-corpus2skill
research_x memory feedback
research_x memory eval
```

Implemented behavior:

- rebuildable `memory_documents` and FTS index over the canonical X store;
- compact evidence bundles for local search results;
- deterministic query planning and local hybrid ranking;
- Japanese entity/date preservation in query plans and relation-expanded retrieval candidates;
- query/intent-aware feedback capture and ranking influence;
- OpenAI/Gemini/Voyage/Cohere/Mistral/Jina/OpenAI-compatible real API embedding providers for
  optional recall arms;
- explicit diagnostic-only `local_hash` embeddings;
- embedding indexes tracked by provider, model, dimensions, profile, text template, and source
  document hash;
- embedding coverage reports by document type so newly added derived views cannot silently remain
  unindexed;
- embedding build estimates for selected documents, approximate input tokens, API batches, and
  optional input-token cost before cloud indexing;
- relation edges for bookmarks, media, quotes, duplicate bookmarks, same URL, same topic,
  newer/older neighbors, and obsolete candidates;
- relation rebuilds preserve non-builder relation types such as future `supports` and
  `contradicts` edges;
- optional relation-judge runs can derive `supports` / `contradicts` edges from freshness
  candidates with fake, Gemini, OpenAI chat, or OpenAI-compatible providers;
- corpus rebuilds delete rebuildable builder relations and orphaned edges, but preserve manual or
  future AI-generated relation types that still point to existing documents;
- external URL-discovery provider contract with no-network fake provider and optional Serper
  provider;
- normalized external discovery run/item storage in the SQLite DB;
- reader/extract provider contract with no-network fake provider and basic HTTP reader;
- CLI fixture-provider guard so fake external/search/reader/answer rows default to no-store and
  require explicit opt-in before being stored;
- X browser storage state and exported cookie files reject empty or expired session cookies before
  treating an account as usable;
- external URL extraction into tool call, context chunk, and citation annotation rows;
- V2 search run, tool call, context chunk, citation annotation, answer run, and workflow trace
  schema;
- ranked local search candidate rows in `memory_search_results`, separate from LLM-ready chunks;
- bounded `memory workflow` routing with step logs and stop reasons;
- `memory workflow --llm-context-provider` integration that adds Brave/fake LLM-context chunks to
  the same context run before optional answer generation;
- `memory eval` can run the same route cases with an explicit semantic provider/profile/template;
- `memory eval --cases` accepts user/project JSON or JSONL route cases instead of only the built-in
  checks;
- optional stored eval runs/results for comparing retrieval quality across rebuilds and embedding
  profiles;
- stored eval run listing/detail commands for post-run inspection;
- experimental `memory portfolio-eval` comparison for lexical-only and candidate semantic arms,
  with per-arm case verdicts, arm summaries, conservative promotion verdicts, and
  fusion-regression detection plus guarded/source-bundle-level RRF fusion metadata; candidate arms
  support `semantic_only` and `hybrid` modes without altering production search ranking;
- `memory portfolio-eval` also compares non-vector arms for Corpus2Skill-style navigation,
  source-bundle/context restoration, bounded workflow routing, and local hybrid retrieval before
  any real API embedding arm can be promoted;
- portfolio eval now separates `fts_only`, `local_hybrid`, `semantic_only`, and `hybrid` arms,
  normalizes provider names, blocks diagnostic `local_hash` from promotion, filters semantic-only
  false-premise noise through strong machine anchors, and keeps date-like terms out of hard anchor
  filters so recall is not narrowed by source-format differences;
- `memory retrieval-strategies` exposes route/retrieval/evidence/semantic candidate spaces with
  adoption, modality, implementation status, and portfolio-eligibility metadata. It keeps
  non-embedding candidates such as contextual BM25, reranking, claim verification, freshness
  lineage, exact anchors, and relation engines visible beside semantic provider arms;
- `memory portfolio-eval --strategy` can add the eligible semantic arms from those broader
  strategies without changing the production retrieval path;
- `memory portfolio-eval --strategy rerank_stage` can add eligible reranker arms as separate
  non-index candidates, keeping rerank scores as provider-specific contribution metadata rather
  than mixing them with embedding similarity scores;
- `memory rerank` provides a fake-first reranker contract and real-provider entry points for
  Voyage `rerank-2.5`, Cohere `rerank-v4.0-pro` / `rerank-v4.0-fast`, and Jina
  `jina-reranker-v3`;
- machine-readable question-type coverage targets so evals cover recall, set, aggregation,
  comparison, multi-hop, temporal, abstention, citation, multilingual, media, preference, and
  exploratory-map cases instead of only the first concrete examples;
- `memory export-corpus2skill --bundle-dir` writes `corpus.jsonl` plus `manifest.json` for the
  official Corpus2Skill compiler boundary, with optional `--doc-type` filters for narrower
  navigation-map exports;
- `memory context` command that turns local retrieved hits into LLM-ready chunks and
  citation-ready metadata;
- `memory context --external-run-id` integration that combines local X chunks with extracted
  external Web chunks under one context bundle/run id;
- generated answer citations point to stored context chunks, including answer-specific truncated
  subchunks when the answer context budget is smaller than the original chunk;
- `memory build-derived` command that adds rebuildable `place_card`, `author_profile`,
  `ticker_event`, and `topic_thread` documents without replacing raw X records, while preserving full source
  provenance even when card bodies are compact;
- strict audit/eval gates for required/configured index problems, orphan rows,
  diagnostic-only embeddings, partial semantic indexes, missing embedding source hashes, V2 evidence graph orphans, invalid V2
  JSON/enums, stored fake/fixture artifacts, answer artifacts that need review, weak retrieval
  behavior, and no-store answer/citation wiring.

Known limitation:

- `memory evidence` remains legacy-compatible; use `memory context` and `memory extract-url` for
  chunk/citation objects;
- `older_same_author_label` is only a weak stale candidate, not proof of obsolescence;
- semantic recall-arm quality requires real API embedding indexes, not `local_hash`;
- the overall evidence pipeline must remain useful through exact/FTS/metadata, relations,
  Corpus2Skill navigation, source bundles, and bounded workflows even when no embedding arm is
  active.

## Completed Milestone: Evidence/Skill/Workflow First Alignment

Realign the already-built V2 foundation so it does not drift into an embedding-centered pipeline.

Implementation checklist:

- [x] Update strategy defaults so `general_memory` is not always selected merely because a query
      exists.
- [x] Add or expose `corpus2skill_navigation`, `bounded_workflow_orchestration`, and
      `api_embedding_portfolio` as strategy concepts without treating generated maps as evidence.
- [x] Make `portfolio-eval` compare non-vector evidence paths, source-bundle restoration, workflow
      routing, and real API embedding arms under the same route-level cases.
- [x] Split real API candidates into embedding, rerank, and reader/OCR/media lanes before running
      paid API builds.
- [x] Add fake-first reranker provider wiring and keep real rerank providers behind explicit eval
      or command selection.
- [x] Keep `local_hash` diagnostic-only and blocked from promotion.
- [x] Stop before real API embedding estimates/builds until the workflow-gated strategy surface is
      aligned.

## Next Milestone: Gemini Embedding 2 Media Contract And Real API Evaluation

The workflow-gated strategy surface is aligned. The next implementation/evaluation phase is to add
the Gemini Embedding 2 media evidence contract first, then run real API embedding estimates/builds
for text and native media arms, run bounded rerank arms, and compare them against the
evidence-first baselines.

Implementation side status: complete. The remaining work in this milestone is real API execution:
estimate costs/coverage, run limited Gemini text/media builds, then evaluate text, media, and rerank
arms against the evidence-first baselines.

Implementation checklist:

- [x] Add `memory_media_embeddings` for raw media vectors without weakening the existing
      text-only `memory_embeddings` contract.
- [x] Add media input resolution for local image/PDF files with mime filtering, file hashes,
      metadata hashes, skipped reasons, and stale detection.
- [x] Add Gemini Embedding 2 native media provider support with inline media payloads and
      media-context text parts.
- [x] Add `media-embedding-estimate`, `build-media-embeddings`,
      `media-embedding-coverage`, and `media-search` commands.
- [x] Add source-bundle restoration for media vector hits and distinguish
      `raw_media_match`, `media_source_evidence`, and `media_content_evidence`.
- [x] Add `native_multimodal_media` strategy; keep `api_embedding_portfolio` text-only.
- [x] Keep Gemini Embedding 2 text embeddings in existing `build-embeddings` and improve
      profile-specific prefixing.
- [x] Add media-grounded eval cases and promotion gates before native media search can enter
      normal workflow routes.
- [x] Add local API budget policies, usage ledger, kill switch, CLI/app monitoring, and guarded
      real-provider call sites before full paid API evaluation.
- [x] Add `test-diagnose` so slow or hanging pytest units can be isolated without dropping
      coverage from the normal verification pipeline.

Stop condition before this milestone starts:

- API keys and target provider/profile choices must be explicit.
- Estimated cost and document coverage must be reviewed before writing real embedding rows.
- Native media build must start with `media-embedding-estimate`, then `--limit 1`, `--limit 10`,
  `--limit 100`, then full only after coverage looks correct.
- Rerank providers must run on restored bounded source bundles, not raw semantic hits.
- `api_embedding_portfolio` remains explicit; do not auto-expand it from normal workflow routes
  until a separate policy and implementation change is made.
- Raw media matches are candidate signals only. They must not become image-content claims unless
  OCR/caption/VLM text has been converted into citation-ready context chunks.

## Completed V2 Evidence Objects

- [x] Add schema for search/tool runs, context chunks, citations, answer runs, and workflow traces.
- [x] Keep all existing memory commands working while adding the new tables.
- [x] Split local retrieved hits into `memory context` chunks and citation-ready source metadata.
- [x] Add route-level eval cases for place recall, ticker/company events, author stance, stale fact
      checks, quote context, duplicate bookmarks, and broad learning maps.
- [x] Add a question-type catalog and attach question types to eval cases before changing retrieval
      fusion or real API embedding recall arms.
- [x] Add derived document builders for `place_card`, `author_profile`, `ticker_event`, and
      `topic_thread`.
- [x] Add an external evidence provider interface with a no-network fake provider first.
- [x] Add Serper as an optional Google SERP `web-search` / `index_provider`.
- [x] Add reader/extract provider interface with no-network fake provider first.
- [x] Add basic HTTP reader that extracts readable text into external context chunks.
- [x] Integrate extracted external Web chunks into `memory context` bundles.
- [x] Add Brave-style `llm_context` only after rate limits, storage rights, and retention policy are
      explicit.
- [x] Add OpenAI-style citation annotations for generated answers.
- [x] Add bounded workflow routing with logged stop reasons.
- [x] Integrate LLM-context chunks into bounded workflows before answer generation.

Future command candidates:

```text
research_x memory cite
```

## Later Milestones

- Run real API embedding rebuild/eval for selected provider/profile/template arms on the real DB.
- Add profile-specific or provider-specific embeddings only after route evals show that
  evidence-first retrieval, Corpus2Skill navigation, source bundles, relations, and the broad
  semantic arm are not enough.
- Run AI/judge-assisted `supports` and `contradicts` relation passes on the real DB, then evaluate
  whether the extra edges improve currentness/fact-check routes.
- Run the exported Corpus2Skill bundle through the OSS compiler and evaluate it as a navigation
  map/route hint, not as the source of final evidence.
- Add external Web evidence providers only behind explicit provider roles and audit logs.

## Implementation Rules

- Use `uv run python ...`, `uv run pytest ...`, and
  `uv run ruff check src\research_x tests`.
- If pytest is slow or appears stuck, use `uv run python -m research_x test-diagnose ...`
  to isolate the slow file/test before changing behavior or dropping coverage.
- Keep acquisition modules stable unless a memory feature needs a clearly scoped read-only helper.
- Add tests next to each new memory module.
- Prefer SQLite tables and explicit contracts before adding frameworks.
- Keep generated indexes in the same SQLite DB unless there is a clear reason to split.
- Never stage `.secrets/` or `runs/`.
- Do not create new Markdown design files for memory-search; update
  `docs/memory-pipeline-v2.md` instead.
- When a decision is not obvious, inspect the repo, search primary then secondary sources as needed,
  treat sources as evidence inputs, evaluate alternatives against the user's goal and local data
  shape, and loop until the decision is justified.
