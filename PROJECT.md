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
- `docs/pipeline.md`: acquisition/auth/provider pipeline details.

Do not add new memory-architecture Markdown files unless the user explicitly asks.

## Goal

Build a local, user-specific search tool over the existing X collection DB. The tool should let an
AI agent search the user's accumulated X bookmarks/tweets like a local web-research tool while
preserving provenance, account-specific bookmark ownership, quote/media context, and the user's
subjective interests.

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
```

Implemented commands:

```text
research_x memory build-corpus
research_x memory build-derived
research_x memory audit
research_x memory build-embeddings
research_x memory embedding-specs
research_x memory build-relations
research_x memory relations
research_x memory plan
research_x memory search
research_x memory evidence
research_x memory context
research_x memory external-search
research_x memory extract-url
research_x memory llm-context
research_x memory answer
research_x memory workflow
research_x memory export-corpus2skill
research_x memory feedback
research_x memory eval
```

Implemented behavior:

- rebuildable `memory_documents` and FTS index over the canonical X store;
- compact evidence bundles for local search results;
- deterministic query planning and local hybrid ranking;
- Japanese entity/date preservation in query plans and relation-expanded retrieval candidates;
- feedback capture;
- OpenAI/Gemini production embedding providers;
- explicit diagnostic-only `local_hash` embeddings;
- embedding indexes tracked by provider, model, dimensions, profile, text template, and source
  document hash;
- relation edges for bookmarks, media, quotes, duplicate bookmarks, same URL, same topic,
  newer/older neighbors, and obsolete candidates;
- relation rebuilds preserve non-builder relation types such as future `supports` and
  `contradicts` edges;
- corpus rebuilds delete rebuildable builder relations and orphaned edges, but preserve manual or
  future AI-generated relation types that still point to existing documents;
- external URL-discovery provider contract with no-network fake provider and optional Serper
  provider;
- normalized external discovery run/item storage in the SQLite DB;
- reader/extract provider contract with no-network fake provider and basic HTTP reader;
- CLI fixture-provider guard so fake external/search/reader/answer rows require explicit opt-in
  before being stored;
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
- `memory export-corpus2skill --bundle-dir` writes `corpus.jsonl` plus `manifest.json` for the
  official Corpus2Skill compiler boundary;
- `memory context` command that turns local retrieved hits into LLM-ready chunks and
  citation-ready metadata;
- `memory context --external-run-id` integration that combines local X chunks with extracted
  external Web chunks under one context bundle/run id;
- generated answer citations point to stored context chunks, including answer-specific truncated
  subchunks when the answer context budget is smaller than the original chunk;
- `memory build-derived` command that adds rebuildable `place_card`, `author_profile`, and
  `ticker_event` documents without replacing raw X records, while preserving full source
  provenance even when card bodies are compact;
- strict audit/eval gates for missing indexes, orphan rows, diagnostic-only embeddings, partial
  semantic indexes, missing embedding source hashes, V2 evidence graph orphans, invalid V2
  JSON/enums, stored fake/fixture artifacts, answer artifacts that need review, weak retrieval
  behavior, and no-store answer/citation wiring.

Known limitation:

- `memory evidence` remains legacy-compatible; use `memory context` and `memory extract-url` for
  chunk/citation objects;
- `older_same_author_label` is only a weak stale candidate, not proof of obsolescence;
- production semantic quality requires a real OpenAI/Gemini embedding index, not `local_hash`.

## Next Milestone: V2 Evidence Objects

Move from local retrieval output to the V2 evidence architecture without deleting the current memory
foundation.

First schema objects:

```text
search_runs
tool_calls
context_chunks
citation_annotations
answer_runs
workflow_runs
workflow_steps
```

Implementation checklist:

- [x] Add schema for search/tool runs, context chunks, citations, answer runs, and workflow traces.
- [x] Keep all existing memory commands working while adding the new tables.
- [x] Split local retrieved hits into `memory context` chunks and citation-ready source metadata.
- [x] Add route-level eval cases for place recall, ticker/company events, author stance, stale fact
      checks, quote context, duplicate bookmarks, and broad learning maps.
- [x] Add derived document builders for `place_card`, `author_profile`, and `ticker_event`.
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

- Run production embedding rebuild/eval for the chosen provider and template on the real DB.
- Add profile-specific embeddings only after route evals show the broad `general_memory` index is
  not enough.
- Add AI/judge-assisted `supports` and `contradicts` relations after the deterministic freshness
  graph is stable.
- Run the exported Corpus2Skill bundle through the OSS compiler and evaluate it as a navigation map,
  not as the source of final evidence.
- Add external Web evidence providers only behind explicit provider roles and audit logs.

## Implementation Rules

- Use `uv run python ...`, `uv run pytest ...`, and
  `uv run ruff check src\research_x tests`.
- Keep acquisition modules stable unless a memory feature needs a clearly scoped read-only helper.
- Add tests next to each new memory module.
- Prefer SQLite tables and explicit contracts before adding frameworks.
- Keep generated indexes in the same SQLite DB unless there is a clear reason to split.
- Never stage `.secrets/` or `runs/`.
- Do not create new Markdown design files for memory-search; update
  `docs/memory-pipeline-v2.md` instead.
