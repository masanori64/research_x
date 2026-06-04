# AI-Callable Memory Search Pipeline V2

This document is the implementation-facing target architecture for the active memory-search work in
`research_x`.
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
- real API embedding provider support as optional recall arms, with `local_hash` only as diagnostic
  wiring;
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
  -> Evidence Relations / Source Bundles
  -> Corpus2Skill / Skill Navigation Hints
  -> Workflow-Gated Adaptive Portfolio
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
- `docs/memory-pipeline-archive.md` stores historical decision notes. Use its index to find and read
  only relevant old sections when a current decision needs prior research or rejected alternatives.
- `PROJECT.md` is only the implementation milestone tracker.
- `README.md` is only the short repository reference.
- `AGENTS.md` tells coding agents which file to read; it must not duplicate the architecture.
- Do not add another memory-architecture Markdown file unless the user explicitly asks.
- When changing the design, update this file first, then adjust `PROJECT.md` only if the milestone
  order changed.
- Prefer appending a short decision note here over scattering partial plans through new files.

Decision discipline:

- do not accept a design just because one source, benchmark, or implementation path looks plausible;
- inspect the current repo and existing decisions before changing direction;
- when a material uncertainty remains, search primary sources first and secondary/community sources
  when primary sources are incomplete;
- treat search results as inputs to judgment, not as the answer itself;
- compare alternatives against the user's goal, local X data shape, provenance, token efficiency,
  cost, operational reliability, and failure modes;
- if that evaluation reveals another unresolved question, repeat the search/evaluation loop before
  recording a decision.

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

## Active Decision Record

Historical decision notes and source-review logs are archived in
docs/memory-pipeline-archive.md. During normal implementation, use this active file first. When a
current decision needs prior research, inspect the archive index and read only the relevant archived
section.

Current active decisions:

- Evidence/Skill/Workflow first: raw evidence, derived views, relations, source bundles,
  Corpus2Skill navigation hints, and bounded workflows are the system center.
- Real API embeddings are optional recall arms inside a workflow-gated portfolio; local_hash is
  diagnostic only.
- Multiple embedding providers or profiles are separate candidate engines. Never mix their vectors
  into one shared distance space or average raw scores across providers.
- Candidate results must be restored to source bundles before context chunking, citation, reranking,
  answer generation, or promotion.
- Corpus2Skill is a navigation map and route hint, not citation-ready evidence.
- Architecture decisions must follow the decision-quality loop in AGENTS.md: inspect repo state,
  search primary then secondary sources when needed, treat sources as inputs, evaluate alternatives,
  and loop when new uncertainty appears.

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
9. Domain-specific embeddings are added only when evaluation shows that evidence-first routing and
   the broad real API semantic arm, when built, are insufficient.
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
- `topic_thread`: multi-post learning/research thread for a technical, academic, finance, media, or
  recurring interest area.
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
- real API semantic recall arms: OpenAI/Gemini/Voyage/Cohere/Mistral/Jina/OpenAI-compatible
  providers when enabled by a workflow route or explicit eval;
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
- derived cards such as `place_card`, `author_profile`, `ticker_event`, and `topic_thread`;
- Corpus2Skill route hints.

External context chunk sources:

- Brave LLM Context snippets;
- Jina Reader / Firecrawl / Tavily / Exa extracted snippets;
- official docs or pages fetched for saved URLs.

Recommended future table shape:

```text
context_chunks
  chunk_id TEXT PRIMARY KEY
  source_kind TEXT              -- local_x_db, official, secondary, user_generated
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

## Evidence / Skill / Workflow First Retrieval Policy

Initial production policy:

1. Preserve raw evidence, derived document views, exact/FTS/metadata search, relations, source
   bundles, Corpus2Skill navigation hints, and bounded workflow traces as the top-level system.
2. Use real API embeddings as optional recall arms inside a workflow-gated adaptive portfolio.
   `local_hash` is diagnostic wiring only and is never a production or promotion candidate.
   Rerank, reader/extract, OCR, and managed-RAG references are separate provider lanes, not
   embedding substitutes.
3. Route exact, date, URL, account, bookmark, ticker, place, quote, and media-expansion questions
   through non-vector evidence first.
4. Allow ambiguous semantic, cross-lingual, learning-map, author-stance, and media-text routes to
   run real API embedding arms in parallel with non-vector engines when the workflow gate decides
   they are useful.
5. Never put OpenAI, Gemini, Voyage, Jina, Cohere, Mistral, or OpenAI-compatible vectors into one
   shared vector space. Treat each provider/model/profile/dimension as a separate candidate engine.
6. Fuse candidate lists with rank-level methods such as RRF, route weighting, or bounded reranking;
   do not average raw scores from unrelated engines.
7. Before context or answer generation, restore every candidate hit to its source bundle: original
   tweet, quoted tweet, media, author, bookmark ownership, external source, and relation metadata.
8. Corpus2Skill is a navigation map and skill-routing hint. It is not citation-ready evidence unless
   the workflow opens source documents and turns them into context chunks with citations.

The embedding spec includes:

```text
provider
model
dimensions
embedding_profile
text_template_version
source_doc_hash
```

Native media embeddings use a separate contract from text embeddings. Text embeddings index
`memory_documents` and are current only when `source_doc_hash` and `embedding_text_hash` match the
document row. Raw media embeddings index saved local media files and are current only when the
media file hash and media metadata hash match:

```text
media_id
doc_id = media:<media_id>
source_tweet_id
provider
model
dimensions
embedding_profile
input_template_version
mime_type
local_path
media_url
media_file_hash
media_metadata_hash
input_parts_json
```

The first native media embedding provider is Gemini `gemini-embedding-2`, with
`embedding_profile=native_multimodal_media`, `dimensions=1536`, and
`input_template_version=gemini-media-input-v1`. Initial media inputs are local image/PDF files only:
`image/jpeg`, `image/png`, `image/webp`, and `application/pdf`. Missing files, zero-byte files,
unsupported MIME types, and files over the configured byte limit are skipped and must appear in
coverage output.

Media evidence has three levels:

- `raw_media_match`: a vector match against a media file. This is a candidate signal only.
- `media_source_evidence`: the hit restored to `media_id`, source tweet, media URL/local path,
  bookmark account, author, quote relation, and source bundle metadata.
- `media_content_evidence`: OCR, caption, or VLM text exists as citation-ready context chunks and
  can support claims about image/PDF content.

Raw Gemini media embedding hits must default to `unconfirmed_media_match`. They cannot support
image-content claims until OCR/caption/VLM text is available as context chunks.

`task_prompt_version` is still a future extension for providers that expose prompt/task variants
that need versioned routing beyond the current document/query task type.

Candidate strategies:

- `baseline_hybrid_foundation`
- `corpus2skill_navigation`
- `bounded_workflow_orchestration`
- `contextual_bm25`
- `rerank_stage`
- `claim_citation_verification`
- `freshness_lineage`
- `api_embedding_portfolio`
- `general_memory`
- `jp_multilingual`
- `learning_long`
- `code_technical`
- `media_text_bridge`
- `exact_metadata_first` (non-embedding guard for places, tickers, dates, handles, URLs)

Current evaluation rule:

- Default strategy selection must start from evidence, skill navigation, source bundles, and bounded
  workflow routing, not from general_memory.
- `api_embedding_portfolio` expands real API semantic candidates only when explicitly requested in
  the current implementation. Automatic workflow-triggered semantic portfolio expansion is a later
  policy/implementation step, not current behavior.
- portfolio-eval compares lexical, relation/source-bundle, Corpus2Skill navigation hints,
  workflow routing, optional real API embedding arms, and explicit bounded rerank arms under the
  same route-level cases.
- local_hash remains diagnostic and must be blocked from promotion.
- Semantic arm quality requires real API embeddings; the whole evidence pipeline must not depend on
  an embedding index being present.

Current strategy classification:

- implemented baseline: `baseline_hybrid_foundation` with FTS, LIKE, metadata, semantic when
  explicitly configured, relation expansion, RRF metadata, and source-bundle restoration;
- workflow-first next candidates: `corpus2skill_navigation`, `bounded_workflow_orchestration`,
  source-bundle restoration, and route-gated portfolio selection;
- high-value evidence candidates: `contextual_bm25`, `rerank_stage`,
  `claim_citation_verification`, and `freshness_lineage`;
- real API embedding recall arms: `api_embedding_portfolio`, `general_memory`, `jp_multilingual`,
  `learning_long`, `code_technical`, and `media_text_bridge`;
- rerank arms: Voyage `rerank-2.5`, Cohere `rerank-v4.0-pro` /
  `rerank-v4.0-fast`, and Jina `jina-reranker-v3`, always after source-bundle restoration and
  never as a first-stage source of truth;
- reader/OCR/media arms: Jina Reader for URL/PDF extraction and Mistral `mistral-ocr-latest` for
  future media/PDF text extraction contracts;
- Japanese/cross-lingual recall: route-gated challengers such as Voyage/Jina/Gemini;
- long-form learning and concept maps: route-gated challengers such as Voyage, OpenAI large,
  Jina, Corpus2Skill maps, topic threads, and relation expansion;
- code/API/repository material: `code_technical` challengers such as Mistral or Voyage code
  embeddings, only for route-specific evals;
- media/OCR/caption routes: `media_text_bridge` challengers only after media docs expose
  citation-ready OCR, caption, alt text, or VLM text;
- Gemini text embedding uses `gemini-embedding-2` for runnable Gemini API text tests. It is
  confirmed as a Gemini API model, so `gemini-embedding-001` is legacy comparison only.
- Native Gemini Embedding 2 multimodal use is implemented through the separate
  `native_multimodal_media` contract, not `api_embedding_portfolio`. Vertex AI
  `multimodalembedding@001` remains a separate GCP auth/project/location reference.
- exact entities, dates, tickers, handles, and places: keep FTS/metadata/relations/derived cards as
  the guardrail before adding dense-provider complexity.

Use `memory retrieval-strategies` to inspect these profiles and
`memory portfolio-eval --strategy <id>` to add eligible candidate semantic or rerank arms to the
comparison gate.

Risk:

- scores across embedding profiles are not directly comparable;
- routing errors can hide good evidence;
- profile proliferation increases cost and rebuild complexity.
- workflow gates can under-call embeddings when semantic recall is needed, or over-call them when
  exact evidence is already enough.

Therefore portfolio routing and profile splitting must be evaluation-driven, not assumption-driven.

## API Budget Guard

All paid or quota-limited provider calls must pass through the local API budget guard before an
HTTP request is sent.

Guarded provider roles include:

- classifier;
- embedding;
- media embedding;
- reranker;
- answer engine;
- relation judge;
- external search / index provider;
- LLM-context provider;
- reader/extract provider when it uses a paid provider such as Jina;
- future OCR and managed-RAG providers.

The guard stores a local usage ledger in:

- `memory_api_budget_policies`;
- `memory_api_usage_events`;
- `memory_api_price_catalog`.

Default policy is intentionally conservative:

- run cap: 1 USD;
- day cap: 5 USD;
- month cap: 25 USD;
- unknown price action: block;
- kill switch: off by default, but when enabled it blocks the next paid API call before HTTP.

Unknown prices are not treated as free. A provider/model/operation/unit must have a price catalog
entry, or the command must explicitly pass `--allow-unpriced-api`; that override is recorded in the
ledger. Local/fake providers and diagnostic `local_hash` do not create billable events.

Use these commands before and during real API experiments:

```powershell
uv run python -m research_x memory api-budget status --db runs/x_data.sqlite3
uv run python -m research_x memory api-budget set --db runs/x_data.sqlite3 --max-run-usd 1
uv run python -m research_x memory api-usage --db runs/x_data.sqlite3 --today
uv run python -m research_x memory api-watch --db runs/x_data.sqlite3 --port 8767
```

The app also shows run/day/month budget status, recent events, and a kill-switch control. Provider
dashboards remain the billing source of truth; the local ledger is a pre-request safety guard and
operational monitor.

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

Implemented and near-term relation types:

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
- `obsolete_candidate`
- `supports` (future AI/judge-assisted)
- `contradicts` (future AI/judge-assisted)

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

Current implementation:

- `memory eval` runs the same bounded route planner as `memory workflow` in no-store mode.
- Eval output records route, expected route, stop reason, context chunk count, retrieval engines,
  source kinds, answer status, and answer citation count.
- Eval input can pin semantic provider, model, dimensions, profile, and template so production
  embedding quality can be compared against lexical/relation-only routing.
- Eval input can also come from a JSON/JSONL cases file, allowing the user's real recurring
  questions to become route-level regression tests.
- Eval runs can be persisted in `memory_eval_runs` / `memory_eval_results` when `--store` is used,
  so retrieval quality can be compared across corpus, relation, and embedding rebuilds.
- Freshness routes can use deterministic freshness edges and optional judged `supports` /
  `contradicts` edges, but generated relation judgments remain inference metadata until cited
  through context chunks and answer annotations.
- Route mismatches and missing compact evidence fail; weak or absent evidence remains visible as
  `needs_review` / `fail` instead of being hidden behind a successful command exit.

## Compatibility With Current Implementation

No current code needs to be deleted immediately.

Current implementation maps into V2 like this:

```text
memory_documents        -> Layer 1 searchable documents
memory_document_fts     -> Layer 2 lexical retrieval
memory_embeddings       -> Layer 2 semantic retrieval with profile/template/source-hash provenance
memory_relations        -> Layer 2 relation expansion / future graph base
memory judge-relations  -> optional support/contradiction relation judge over freshness candidates
memory_external_runs    -> Layer 3 external provider run metadata
memory_external_items   -> Layer 3 normalized external URL discovery results
memory_tool_calls       -> Layer 3/7 provider calls, including reader/extract
memory_search_runs      -> Layer 2/4 local query execution records
memory_context_chunks   -> Layer 4 LLM-ready context chunks
memory_citation_annotations -> Layer 5 citation-ready source metadata
memory_answer_runs      -> Layer 6 answer artifacts
memory_workflow_runs    -> Layer 7 bounded workflow traces
memory_workflow_steps   -> Layer 7 bounded workflow step logs
memory build-derived    -> Layer 1 derived cards for places/authors/ticker events/topic threads
memory evidence         -> legacy-compatible local hit bundle
memory context          -> Layer 4 chunks plus Layer 5 citation metadata
memory extract-url      -> Layer 3 reader/extract to Layer 4 external chunks
memory context --external-run-id -> combined local/external context bundle
memory answer           -> Layer 6 generated answer artifact plus answer citations
memory workflow         -> Layer 7 bounded workflow traces with optional LLM-context grounding
memory feedback/eval    -> Layer 7 feedback/eval
memory export-corpus2skill -> Corpus2Skill-compatible navigation-map input boundary
memory audit            -> rebuild/index health gate
```

What may need refactoring later:

- semantic recall-arm quality still needs real API provider indexes and route evals over the real
  DB; the overall evidence pipeline must remain useful without embeddings.
- `memory_documents` now includes derived cards from `memory build-derived`; future derived types
  should keep the same provenance and rebuild behavior.
- `memory evidence` remains a legacy-compatible hit bundle; new AI callers should prefer
  `memory context` for chunks and citation metadata.
- feedback scoring is query/intent-aware and can be route-aware when feedback records include a
  route, so judgments affect similar future searches more strongly than unrelated searches.
- external Web evidence is stored separately from local X evidence; URL discovery rows are not
  citation-ready until `reader/extract` or `llm-context` produces context chunks.
- combined context bundles can include `local_x_db`, `official`, `secondary`, and
  `user_generated` chunks; `external_web` is retained as `source_medium` metadata when useful.
- generated answers are stored in `memory_answer_runs`; answer-specific citation annotations must
  point back to context chunks with `answer_id` and answer text offsets.

What should not be deleted:

- acquisition providers;
- raw X DB tables;
- local app/bookmark/tweet acquisition flow;
- existing memory CLI commands, unless replaced by compatible wrappers.

## Remaining Implementation Order

The V2 foundation through schema, context chunks, citations, answers, workflow traces, route-level
evals, strategy defaults, Corpus2Skill export/navigation, and portfolio comparison is implemented.
Do not repeat those phases unless a verification step finds a regression.

Next work order:

1. Estimate real API embedding cost and coverage for explicit provider/profile candidates.
2. Build selected real API embedding arms only after the estimate is accepted.
3. Run route-level portfolio evals against evidence-first, source-bundle, workflow, and semantic
   arms.
4. Promote an embedding provider/profile only when route-level evals show improvement after
   source-bundle restoration and citation checks.
5. Add automatic workflow-triggered semantic portfolio expansion only as a separate policy and
   implementation change after explicit evals justify it.

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
- Real API embeddings add cost, provider drift, quota, and privacy constraints; they must be
  measured as recall arms rather than assumed to be the production center.
- Agentic workflows can spend tokens without improving answers; every workflow needs a stop reason
  and eval coverage.
