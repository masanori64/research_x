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
  evidence.py
  feedback.py
  embeddings.py
  relations.py
  audit.py
  query.py
  evals.py
```

Implemented commands:

```text
research_x memory build-corpus
research_x memory audit
research_x memory build-embeddings
research_x memory embedding-specs
research_x memory build-relations
research_x memory relations
research_x memory plan
research_x memory search
research_x memory evidence
research_x memory export-corpus2skill
research_x memory feedback
research_x memory eval
```

Implemented behavior:

- rebuildable `memory_documents` and FTS index over the canonical X store;
- compact evidence bundles for local search results;
- deterministic query planning and local hybrid ranking;
- feedback capture;
- OpenAI/Gemini production embedding providers;
- explicit diagnostic-only `local_hash` embeddings;
- relation edges for bookmarks, media, quotes, duplicate bookmarks, and weak stale candidates;
- strict audit/eval gates for missing indexes, orphan rows, diagnostic-only embeddings, partial
  semantic indexes, and weak retrieval behavior.

Known limitation:

- current evidence output still mixes retrieved hit data and citation-ready context more than the
  V2 architecture allows;
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

- [ ] Add schema for search/tool runs, context chunks, citations, answer runs, and workflow traces.
- [ ] Keep all existing memory commands working while adding the new tables.
- [ ] Split `memory evidence` output into retrieved hits, context chunks, and citation-ready source
      metadata.
- [ ] Add route-level eval cases for place recall, ticker/company events, author stance, stale fact
      checks, quote context, duplicate bookmarks, and broad learning maps.
- [ ] Add derived document builders for `place_card`, `author_profile`, and `ticker_event`.
- [ ] Add an external evidence provider interface with a no-network fake provider first.
- [ ] Add Brave-style `llm_context` only after rate limits, storage rights, and retention policy are
      explicit.
- [ ] Add OpenAI-style citation annotations for generated answers.
- [ ] Add bounded workflow routing with logged stop reasons.

Future command candidates:

```text
research_x memory build-derived
research_x memory context
research_x memory cite
research_x memory external-search
research_x memory workflow
research_x memory answer
```

## Later Milestones

- Add production embedding rebuild/eval for the chosen provider and template.
- Add `embedding_profile`, `text_template_version`, and source hash tracking if profile-specific
  embeddings become necessary.
- Strengthen freshness relations: `same_url`, `same_topic`, `newer_than`, `supports`,
  `contradicts`, `obsolete_candidate`.
- Integrate Corpus2Skill OSS as a navigation map, not as the source of final evidence.
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
