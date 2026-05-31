# AI-Callable Memory Search Pipeline V2

This document is the implementation-facing target architecture for the next phase of `research_x`.
It supersedes the older "single local memory search layer" framing in favor of a layered evidence
system.

The goal is not to build a generic RAG demo. The goal is to build a local, user-specific search
tool that an AI agent can call in the same spirit as web research, while preserving the user's own
X/Twitter collection, subjective interests, account-specific bookmarks, and provenance.

## Executive Decision

The current implementation should be kept as the lower retrieval foundation, not deleted.

Keep:

- the raw X acquisition database as the source of truth;
- `memory_documents` as a rebuildable searchable corpus;
- SQLite FTS and metadata search;
- production embedding support, with `local_hash` only as diagnostic wiring;
- `memory_relations` for quote/media/bookmark/freshness context;
- `memory evidence`, `memory audit`, `memory eval`, and feedback.

Change the final design:

- do not center the final system on "one vector DB over all tweets";
- do not treat generated labels or generated answers as truth;
- do not collapse search results, context chunks, citations, and answers into one table;
- do not assume Claude, Codex, OpenAI, Brave, or any hidden web backend provider unless a source or
  local configuration proves it.

The final system is:

```text
Raw Sources
  -> Normalized / Derived Views
  -> Retrieval Engines
  -> LLM-Ready Context Chunks
  -> Citation Metadata
  -> Bounded Workflows / Orchestrator
  -> Answer Artifacts
  -> Feedback / Eval / Audit / Rebuild
```

The central invariant:

```text
raw source != searchable document != search result != context chunk != citation != answer
```

Each object must be traceable backward to its source and forward to the answer or workflow that used
it.

## Scope Hygiene

Keep the design surface small.

- This file is the single detailed architecture source.
- `PROJECT.md` is only the implementation milestone tracker.
- `README.md` is only the short repository reference.
- `AGENTS.md` tells coding agents which file to read; it must not duplicate the architecture.
- Do not add another memory-architecture Markdown file unless the user explicitly asks.
- When changing the design, update this file first, then adjust `PROJECT.md` only if the milestone
  order changed.
- Prefer appending a short decision note here over scattering partial plans through new files.

## Research Inputs Behind This Design

OpenAI public Web Search patterns:

- `web_search_call` is separate from the final `message`.
- URL citations live as annotations on answer text.
- Live/cache-only and domain-filtering are tool configuration, not answer content.

Brave Search / LLM Context patterns:

- `web-search` discovers ranked URLs and snippets.
- `llm-context` returns query-conditioned, pre-extracted chunks for grounding.
- `answers` produces a final answer and should not be treated as canonical evidence.

Claude / Brave evidence:

- Claude for Government's Web Search MCP connector explicitly calls Brave Search API.
- Commercial Claude and Claude Code do not publicly guarantee that built-in web search always uses
  Brave.
- User-installed Brave MCP or Skills are separate from a model provider's built-in web search.

Broader AI-search products:

- Perplexity, Tavily, Exa, Firecrawl, Jina Reader, and Brave all separate at least some of:
  search/discovery, URL extraction, context/chunks, and answer synthesis.
- This separation is the useful pattern to copy.

Corpus2Skill / Agentic RAG / GraphRAG:

- Corpus2Skill is best treated as a stable navigation map or skill tree, not the sole source of
  exact evidence.
- Agentic search is useful for complex queries, but only as a bounded workflow with logs and stop
  reasons.
- Graph-like relations are valuable, but start with explicit relation tables and provenance before
  introducing a graph framework.

## Non-Negotiable Invariants

1. Raw X records are never replaced by summaries.
2. AI labels are hints, not truth.
3. Generated answers are reviewable artifacts, not evidence.
4. A citation must point to a source or context chunk, not just to a generated answer.
5. Search provider, fetch agent, LLM-context provider, image provider, and answer engine are
   separate roles.
6. External Web context is auxiliary. The user's local X DB remains primary for "what did I save or
   care about?" questions.
7. Every rebuildable index must be auditable for coverage, staleness, and diagnostic-only fallbacks.
8. Every agentic workflow must log steps, inputs, outputs, and stop reason.
9. Domain-specific embeddings are added only when evaluation shows that one broad production index
   plus document-view routing is insufficient.
10. Query answers must separate evidence-backed facts from model inference.

## Layer 0: Raw Sources

Existing raw sources:

- `tweets`
- `account_bookmarks`
- `collection_items`
- `tweet_edges`
- `media`
- `raw_payloads`
- `ai_labels`
- `accounts`
- `provider_runs`

Future raw or near-raw sources:

- external URL fetch metadata;
- external Web search provider payloads, if storage rights allow;
- URL content hashes;
- answer/tool-call raw JSON for reproducibility;
- workflow traces.

Raw records should be append-only or immutable where practical. If a record must be corrected, keep
enough metadata to know the old value, new value, reason, and time.

## Layer 1: Normalized and Derived Views

`memory_documents` remains the primary rebuildable view over the raw DB.

Existing document types:

- `tweet_doc`: one tweet with author/date/url metadata.
- `bookmark_doc`: bookmarked root tweet plus bookmark account context.
- `quote_tree_doc`: quote root plus quoted tweet snippets.
- `media_doc`: tweet plus media path/status metadata.

Add future document types only when they improve real workflows:

- `place_card`: restaurants, cafes, venues, local spots, map hints, related saved tweets.
- `author_profile`: author stance, recurring interests, saved-history summary, topic links.
- `ticker_event`: ticker/company/date event, saved posts, author opinions, stale/newer links.
- `topic_thread`: multi-post learning/research thread for a technical or academic area.
- `url_context_doc`: external URL title, source, extracted snippets, and source metadata.
- `claim_card`: a compact claim with supporting/contradicting sources and freshness status.

Design rule:

```text
Split document views before splitting vector spaces.
```

For example, "北千住のピザの店" should hit `place_card` and bookmark documents before needing a
special restaurant embedding space.

## Layer 2: Retrieval Engines

The retrieval layer can combine several engines, but each engine must expose its own contribution.

Required local engines:

- exact lookup: tweet IDs, URLs, author handles, dates, labels;
- FTS5 lexical search;
- metadata filters: account, bookmark/tweet kind, date range, author, doc type;
- production semantic search: OpenAI/Gemini or another production embedding provider;
- relation expansion: quotes, media, duplicate bookmarks, freshness candidates;
- feedback-aware ranking.

Optional future engines:

- Corpus2Skill navigation map;
- external Web search;
- external LLM-context provider;
- reranker or small judge;
- graph/community summaries.

Retrieval output is not an answer. It is a candidate list with:

- rank;
- scores and score components;
- query terms and matched fields;
- provider/run metadata;
- relation summaries;
- freshness/staleness signals;
- reason it was included.

## Layer 3: External Web Evidence

External Web evidence follows four roles.

```text
web-search      -> URL discovery and ranked snippets
reader/extract  -> clean text/markdown from known URLs
llm-context     -> query-conditioned chunks for grounding
answers         -> final generated response from an external answer engine
```

For `research_x`, `answers` should not be canonical. Prefer `web-search`, `reader/extract`, and
`llm-context` style data.

Brave integration, if added, should be shaped like this:

```text
local X evidence first
  -> if local evidence needs current external context:
       brave_llm_context or equivalent
  -> normalize into ExternalEvidenceBundle
  -> cite alongside local X evidence
```

Do not replace local X search with Brave. Brave is useful for:

- current state of URLs saved in tweets;
- current facts that the local DB cannot know;
- external grounding when a saved tweet is ambiguous;
- validating if an old saved claim has become stale.

External evidence records should store:

- `provider`: e.g. `brave`, `openai_web_search`, `jina_reader`, `firecrawl`, `manual`;
- `provider_role`: `index_provider`, `fetch_agent`, `llm_context_provider`, `answer_engine`;
- query;
- endpoint/action;
- parameters;
- source URLs;
- title/source metadata;
- snippets/chunks;
- fetch/cache/live status if known;
- retrieved_at;
- raw response hash;
- storage rights or retention policy if relevant.

## Layer 4: Context Chunks

Context chunks are what an AI agent should read. They are smaller than raw records and have explicit
provenance.

Local context chunk sources:

- `memory_documents.compact_text`;
- selected quote/media/URL relation expansion;
- derived cards such as `place_card`, `author_profile`, and `ticker_event`;
- Corpus2Skill route hints.

External context chunk sources:

- Brave LLM Context snippets;
- Jina Reader / Firecrawl / Tavily / Exa extracted snippets;
- official docs or pages fetched for saved URLs.

Recommended future table shape:

```text
context_chunks
  chunk_id TEXT PRIMARY KEY
  source_kind TEXT              -- local_x_db, external_web, official, secondary, user_generated
  source_id TEXT
  source_url TEXT
  provider TEXT
  provider_role TEXT
  query_id TEXT NULL
  chunk_text TEXT
  chunk_index INTEGER
  offset_start INTEGER NULL
  offset_end INTEGER NULL
  token_count INTEGER NULL
  relevance_score REAL NULL
  extractor_version TEXT
  created_at TEXT
  metadata_json TEXT
```

Chunks may be query-independent or query-conditioned. This distinction matters because
query-conditioned chunks should not be treated as a stable global summary of the source.

## Layer 5: Citations

Citations connect generated output back to context chunks and sources.

Recommended future shape:

```text
citation_annotations
  citation_id TEXT PRIMARY KEY
  answer_id TEXT
  chunk_id TEXT
  source_kind TEXT
  source_id TEXT
  source_url TEXT
  title TEXT
  answer_start_index INTEGER NULL
  answer_end_index INTEGER NULL
  field_path TEXT NULL
  support_type TEXT             -- supports, contradicts, background, example, weak_signal
  evidence_status TEXT          -- fact, inference, unconfirmed
  confidence REAL NULL
  created_at TEXT
```

Do not store only display citation numbers. Display citations are UI artifacts. The database must
store stable links to chunks and source records.

## Layer 6: Answers

Answers are generated artifacts:

```text
answer_runs
  answer_id TEXT PRIMARY KEY
  question TEXT
  workflow_id TEXT
  model TEXT
  prompt_version TEXT
  retrieval_config_json TEXT
  answer_text TEXT
  structured_json TEXT
  created_at TEXT
```

Use generated answers for:

- user-facing reports;
- review;
- caching;
- feedback;
- evaluation artifacts.

Do not use generated answers as the source of truth for future retrieval unless they are explicitly
indexed as `answer_artifact_doc` and clearly marked as derived.

## Layer 7: Workflow / Orchestration

Use bounded workflows. Do not run a fully autonomous agent for every query.

Workflow trace shape:

```text
workflow_runs
  workflow_id TEXT PRIMARY KEY
  query TEXT
  route TEXT
  status TEXT
  stop_reason TEXT
  started_at TEXT
  finished_at TEXT
  metadata_json TEXT

workflow_steps
  step_id TEXT PRIMARY KEY
  workflow_id TEXT
  step_index INTEGER
  action TEXT                  -- plan, search, open, find, expand, rerank, answer, audit
  input_json TEXT
  output_json TEXT
  status TEXT
  error TEXT NULL
  created_at TEXT
```

Stop reasons:

- `enough_evidence`
- `no_local_evidence`
- `external_context_needed`
- `stale_or_conflicting_evidence`
- `rate_limited`
- `provider_error`
- `needs_user_review`
- `budget_exhausted`

## Query Routes

### Place / Restaurant Recall

User intent:

> 北千住にある、ピザが食べられる店だったと思うんだけどどこ？

Route:

```text
place terms -> place_card + bookmark_doc search
  -> account/bookmark filter
  -> URL/media expansion
  -> optional external current place info
  -> evidence bundle
```

The answer must avoid generic restaurant suggestions unless explicitly asked. It should say "from
your saved data, the candidates are..."

### Stock / Company Event

User intent:

> 5/29のキオクシアの株価急騰について、保存している人たちの見方から分析して

Route:

```text
ticker/company/date extraction
  -> ticker_event docs
  -> author_profile and relevant saved posts
  -> freshness / newer-than / contradiction links
  -> external current price/news only if needed
  -> evidence-backed answer with inference separated
```

The answer must not be generic finance commentary. It should distinguish:

- what saved authors said;
- what the event/fact source says;
- what the model infers from those sources.

### Author Stance / Future Outlook

User intent:

> Aさんに対して2026年のAIの展望について教えて

Route:

```text
author identity -> author_profile
  -> topic_thread: AI
  -> saved posts over time
  -> quote/context expansion
  -> answer with "evidence" vs "likely inference"
```

### Learning / Research Map

User intent:

> 強化学習、ロボット、ネットワークあたりで後から勉強に使える情報を整理して

Route:

```text
Corpus2Skill/topic map
  -> local hybrid search
  -> relation expansion
  -> derived topic_thread candidates
  -> optional external docs for current state
  -> evidence bundle / study map
```

### Current Fact Check Over Saved Data

User intent:

> 昔保存したこの技術情報、今も正しい？

Route:

```text
local source lookup
  -> same_url / same_topic / newer_than relations
  -> external Web llm-context or reader extract
  -> contradiction/support relation
  -> answer with freshness status
```

## Embedding Policy

Initial production policy:

1. Build one broad production embedding index for the current `memory_documents`.
2. Keep FTS/exact/metadata/relation scoring active.
3. Improve document views and chunk text before adding many vector spaces.
4. Add profile-specific embeddings only after evals show the broad index is failing.

Future embedding spec should include:

```text
provider
model
dimensions
embedding_profile
text_template_version
task_prompt_version
source_doc_hash
```

Candidate profiles:

- `general_memory`
- `place_recall`
- `author_stance`
- `ticker_event`
- `technical_learning`
- `media_context`

Risk:

- scores across embedding profiles are not directly comparable;
- routing errors can hide good evidence;
- profile proliferation increases cost and rebuild complexity.

Therefore profile splitting must be evaluation-driven, not assumption-driven.

## Corpus2Skill Position

Corpus2Skill is useful as a stable navigation layer.

Use it for:

- broad topic maps;
- recurring interest areas;
- skill-like route hints;
- agent-readable "where should I search next?" guidance.

Do not use it as the only source for:

- exact tweet lookup;
- author/date/URL lookup;
- quote/media expansion;
- bookmark ownership;
- stale/newer evidence;
- final citations.

The local DB remains the evidence source. Corpus2Skill is a map.

## Graph / Relations Position

Do not introduce a heavy graph framework before the relation table is strong.

Near-term relation types:

- `bookmark_of_tweet`
- `has_media`
- `quotes`
- `has_quote_tree`
- `same_bookmarked_tweet`
- `same_url`
- `same_author`
- `same_topic`
- `newer_than`
- `older_than`
- `supports`
- `contradicts`
- `obsolete_candidate`

Relations must include:

- source and target doc ids;
- strength;
- status;
- evidence JSON;
- created/updated time;
- relation builder version.

## Evaluation Contract

The eval suite must test route correctness, not just search output shape.

Add or keep cases for:

- place recall from bookmarks, with no generic web suggestions;
- Kioxia/stock event analysis from saved author history;
- author stance over time;
- quote tweet parent/child context;
- duplicate bookmarks across accounts;
- stale vs newer information;
- adult/commercial media links without leaking unsafe content into summaries;
- image/media-bearing technical posts;
- current external fact check;
- broad topic-map navigation.

Each eval should record:

- route chosen;
- retrieval engines used;
- whether local evidence was enough;
- whether external context was used;
- top evidence ids;
- whether citations point to raw/local/external sources;
- answer status: `ok`, `needs_review`, or `fail`.

## Compatibility With Current Implementation

No current code needs to be deleted immediately.

Current implementation maps into V2 like this:

```text
memory_documents        -> Layer 1 searchable documents
memory_document_fts     -> Layer 2 lexical retrieval
memory_embeddings       -> Layer 2 semantic retrieval
memory_relations        -> Layer 2 relation expansion / future graph base
memory evidence         -> Layer 4 local context bundle, partial Layer 5 citations
memory feedback/eval    -> Layer 7 feedback/eval
memory audit            -> rebuild/index health gate
```

What may need refactoring later:

- `memory_embeddings` primary key may need `embedding_profile` and `text_template_version`.
- `memory_documents` may need more doc types or a separate derived-view builder.
- `memory evidence` may need to split "hit evidence" from "citation annotations".
- feedback scoring should eventually become query/route-aware.
- external Web evidence should be stored separately from local X evidence.

What should not be deleted:

- acquisition providers;
- raw X DB tables;
- local app/bookmark/tweet acquisition flow;
- existing memory CLI commands, unless replaced by compatible wrappers.

## Implementation Order

1. Document this V2 design and keep existing code stable.
2. Add schema for tool/search runs, context chunks, citations, and answer runs.
3. Refactor evidence output so local hits and citations are explicit.
4. Add derived view builders for `place_card`, `author_profile`, and `ticker_event`.
5. Add external evidence provider interface, initially with a no-network fake/test provider.
6. Add Brave LLM Context provider only after storage/retention/rate-limit handling is explicit.
7. Add workflow routing and workflow traces.
8. Expand evals to route-level cases.
9. Add production embedding rebuild for the selected provider.
10. Integrate Corpus2Skill OSS export/navigation as a map after evals show stable search behavior.

## Deletion / Rewrite Policy

Delete or rewrite only when a piece violates an invariant.

Safe to rewrite:

- derived document builders;
- evidence JSON shape;
- query planning heuristics;
- ranking weights;
- diagnostic-only embedding code if it hides production failures.

Not safe to rewrite without migration:

- raw X data;
- account/bookmark ownership mapping;
- media path mapping;
- provider run history;
- tests that protect acquisition behavior.

## Open Risks

- External API storage rights may restrict long-term storage of extracted Web context.
- Search provider behavior changes over time, so provider metadata and run timestamps are required.
- Generated summaries can create false stability; summaries must remain derived artifacts.
- Domain-specific vector profiles can improve recall but can also hide evidence if routing fails.
- Agentic workflows can spend tokens without improving answers; every workflow needs a stop reason
  and eval coverage.
