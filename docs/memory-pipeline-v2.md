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

## Decision Notes

### 2026-05-31: External Search And Codex-Customization Candidates

Decision:

- Add an external evidence provider interface before binding to any real network API.
- Treat Serper.dev as an optional `web-search` / `index_provider` candidate, not as
  `reader/extract`, `llm-context`, or `answers`.
- Prefer Brave Search API for first-class agent/RAG web grounding when an external provider needs
  LLM-context-style output. Use Serper only when Google SERP coverage is specifically needed.
- Keep SearXNG as an optional private/self-hosted experiment, not the default. It requires JSON
  output to be enabled in `settings.yml`, and public instances often disable API formats.
- Do not use Webshare or rotating residential proxies as the standard way to avoid search-engine
  blocking. The operational, ToS, and safety costs are too high for the main pipeline.
- Keep browser history outside the V2 core for now. If added, it is a local opt-in weak memory
  signal: it proves that a URL was visited, not that the page content is evidence.
- Do not bulk-install `majiayu000/spellbook`. Its `codex-retrospective` and `codex-fluent` skills
  are useful patterns, but this repo should use small project-specific adaptations only.
- Do not adopt Tencent/WeKnora as the `research_x` RAG backend. Extract only design ideas:
  parent-child context, provider registry, sync logs, stable CLI contracts, and retrieval/debug
  traces.

Implementation impact:

- First implement a no-network fake provider and stable storage/JSON contract.
- Store external search payloads separately from local X evidence, with provider role, query,
  parameters, source URLs, retrieved time, raw hash, and retention policy.
- URL discovery is not citation-ready evidence until a reader/extract or LLM-context provider
  produces grounded chunks.
- Browser history, if implemented later, should default to query-string stripping, local-only
  storage, explicit opt-in, and separate `source_kind=local_browser_history`.
- Codex operation notes belong in `AGENTS.md`; memory architecture decisions stay in this file.

Primary sources checked:

- Serper.dev: https://serper.dev/
- Serper terms/privacy: https://serper.dev/terms and https://serper.dev/privacy
- Brave Search API: https://brave.com/search/api/
- SearXNG Search API: https://docs.searxng.org/dev/search_api.html
- SearXNG outgoing proxy settings: https://docs.searxng.org/admin/settings/settings_outgoing.html
- Chrome history API: https://developer.chrome.com/docs/extensions/reference/api/history
- SQLite backup/WAL: https://www.sqlite.org/backup.html and https://www.sqlite.org/wal.html
- Spellbook: https://github.com/majiayu000/spellbook
- Tencent/WeKnora: https://github.com/Tencent/WeKnora

### 2026-06-01: Remove Diagnostic Shrinking From Production Paths

Decision:

- Preserve unmatched Japanese entity/place/date tokens in query plans instead of only using broad
  intent expansions.
- Treat `memory_relations` as a retrieval expansion source, not only as a post-retrieval scoring
  boost.
- Keep derived-card bodies compact, but retain all source document IDs, tweet IDs, URLs, and
  `derived_from_source` relations in metadata/provenance.
- Flag stored fake/fixture external/search/reader/answer artifacts in `memory audit --strict`.
- Require explicit CLI opt-in before stored fake/fixture provider rows are written; dry wiring
  checks can use `--no-store`.
- When answer context is truncated, create answer-specific subchunk IDs and mark missing citation
  markers as `needs_review` instead of silently treating them as supporting citations.
- Add a bounded `memory workflow` command that logs route planning, context construction, optional
  answer generation, and a stop reason instead of running open-ended agent loops.

Rationale:

- A broad intent route such as food or finance must not drop exact user signals like `北千住`,
  `5/29`, or `キオクシア`.
- Relations are part of the evidence graph; a quote, source tweet, duplicate bookmark, or derived
  source can be relevant even when its text does not match the original query.
- Diagnostic fake providers are useful for test coverage, but they must be visible and fail strict
  production audit gates.

Implementation impact:

- `memory search` now includes relation-expanded candidates in the returned result set.
- `memory context` carries derived provenance and omitted relation/media/quote counts.
- `memory answer` records context selection metadata, omitted chunk IDs, truncated chunk IDs, and
  missing citation markers. Answer-specific truncated subchunks are persisted as context chunks so
  citation rows never point to a non-existent chunk.
- `memory audit` reports `fixture_artifacts` and answer artifact status counts.
- `memory build-relations` rebuilds known builder relation types while preserving manual or
  future AI-generated relation types such as `supports`, `contradicts`, and `obsolete_candidate`.
- `memory workflow` writes `memory_workflow_runs` / `memory_workflow_steps`, links generated
  answers through `answer_runs.workflow_id`, and defaults to context-only execution unless an answer
  provider is explicitly selected.
- `memory llm-context` adds a pre-extracted external Web context role. The Brave provider calls
  Brave Search LLM Context with explicit token/URL/snippet limits, stores source URLs and extracted
  snippets as context chunks, and records `extracted_context_with_source_urls` retention metadata.
- `memory_search_results` stores the ranked local candidate list separately from context chunks, so
  a search run can be audited without treating LLM-ready snippets as the original ranking output.
- `memory workflow --llm-context-provider` attaches LLM-context chunks to the same local context run
  before optional answer generation. Current fact-check routes still require local X evidence;
  external Web context is auxiliary grounding, not a replacement for the user's saved source.
- `memory audit` checks V2 search/context/citation/answer/workflow rows for orphaned references,
  invalid JSON payloads, invalid source kinds, invalid provider roles, and invalid evidence/status
  values.
- Strict audit warns when stored answer artifacts are still `needs_review` or `error`.

### 2026-06-01: Embedding Provenance Becomes First-Class

Decision:

- Treat an embedding row as a provider/model/dimensions/profile/template artifact, not just a
  vector attached to a document.
- Store `source_doc_hash` beside `embedded_text_hash` so audits can distinguish a stale source view
  from a stale embedding text template.
- Keep `general_memory` and `memory-doc-embedding-v1` as the default broad semantic profile/template
  when a real API embedding arm is explicitly built. Do not make that arm the default top-level
  workflow route without eval evidence.

Implementation impact:

- `memory_embeddings` now keys rows by provider, model, dimensions, embedding profile, and text
  template version.
- Native candidate embedding providers include OpenAI, Gemini, Voyage, Cohere, Mistral, Jina, and
  OpenAI-compatible endpoints. They are production-capable provider adapters, but only evaluation
  can promote a provider/profile into the default retrieval path.
- `openai_compatible` embedding providers are production-capable when a full embeddings endpoint,
  model, dimensions, and API-key env var are supplied explicitly; they are not auto-guessed unless
  `OPENAI_COMPATIBLE_API_KEY` and `OPENAI_COMPATIBLE_EMBEDDINGS_URL` are both set.
- `memory build-embeddings`, `memory search`, `memory evidence`, `memory context`,
  `memory answer`, and `memory workflow` can select a semantic profile/template explicitly.
- `memory embedding-estimate` gives the selected document count, approximate input-token volume,
  API batch count, and optional input-cost estimate before a cloud build is started.
- `memory embedding-specs`, `memory embedding-coverage`, and `memory audit` expose
  profile/template metadata and missing/stale index coverage.
- `memory eval` can run route-level checks against a specific semantic provider/profile/template.
- `memory audit --strict` warns when embedding rows lack source hashes, because that means the
  index predates the V2 provenance contract.

### 2026-06-01: Deterministic Freshness Relations First

Decision:

- Build deterministic `same_url`, `same_topic`, `newer_than`, `older_than`, and
  `obsolete_candidate` edges before adding AI-generated support/contradiction judgments.
- Treat `obsolete_candidate` as a candidate relation only. It marks an older same-author/same-topic
  neighbor separated by a large time gap, not proof that the older content is false.
- Add support/contradiction judging as a separate pass over candidate freshness edges, not as part
  of the deterministic relation rebuild.

Implementation impact:

- `memory build-relations` now adds URL, topic, and newer/older neighbor edges from
  `memory_documents` metadata.
- `memory search` uses these relation counts for freshness-aware ranking while keeping the raw
  X rows and derived documents unchanged.
- `memory judge-relations` can add `supports` / `contradicts` edges from evidence documents to
  assessed documents. It stores judge/provider/prompt metadata in `memory_relations.evidence_json`
  and writes a tool-call audit row when stored.
- `supports` / `contradicts` edges are reviewed derived artifacts; they are not inferred solely
  from date ordering and they do not replace raw X evidence.
- `memory build-corpus` preserves non-builder relations that still point to existing documents,
  instead of wiping future manual or AI-generated support/contradiction edges.

### 2026-06-01: Corpus2Skill Boundary Stays Explicit

Decision:

- Do not reimplement Corpus2Skill under another name inside `research_x`.
- Export a clean Corpus2Skill-compatible corpus bundle from `memory_documents`, then run the OSS
  compiler outside the core memory DB when needed.
- Keep Corpus2Skill output as a navigation map. Final evidence still comes from local X documents,
  context chunks, citations, and optional external grounding.

Implementation impact:

- `memory export-corpus2skill --bundle-dir` writes `corpus.jsonl` with `id` / `contents` plus
  trace metadata and a `manifest.json` containing the compile hint. `--doc-type` filters can create
  narrower map-oriented bundles without removing the full export path.
- The bundle is an integration boundary, not a replacement for search/context/citation tables.

### 2026-06-01: Multiple Embeddings Stay Candidate Engines

Decision:

- Interpret Corpus2Skill's "no embeddings/vector DB at serve time" claim narrowly. The compiler still
  embeds and clusters documents offline; the serve-time change is that the agent navigates files and
  fetches documents by ID instead of querying a live vector index.
- Keep one broad `general_memory` embedding profile as the default broad semantic arm when a real API
  embedding index is built. Add route/domain profiles only when evals show that evidence-first
  retrieval, derived views, relations, Corpus2Skill navigation, and the broad semantic arm miss
  relevant evidence.
- When multiple embedding profiles or retrieval engines are active, treat them as separate candidate
  engines. Combine ranked lists with explicit engine names, component ranks/scores, route weights,
  and rank-level fusion such as RRF; do not directly compare raw cosine, BM25, or model-specific
  scores as if they shared a scale.
- Use Corpus2Skill as a navigation hint, relations as context expansion, and GraphRAG-style summaries
  only for broad sensemaking. Final evidence must still come from local/external context chunks with
  citations back to source records.
- Keep Agentic RAG as bounded orchestration with step logs and stop reasons, not the main retrieval
  primitive.

Rationale:

- Corpus2Skill reports gains for curated, single-domain, atomic-document corpora, but also describes
  regimes where flat retrieval remains preferable: open-domain pools, long extractive documents, and
  homogeneous/tabular corpora where clustering provides little signal.
- A personal X memory DB is heterogeneous and often exact-signal-heavy: author, date, URL, bookmark
  ownership, quote/media context, freshness, and subjective interest signals matter as much as
  semantic similarity.
- Hybrid-search systems commonly use rank fusion because individual rankers produce incompatible
  score ranges. Multiple named/multivector representations are useful, but every new profile adds
  cost, coverage, staleness, and routing risk.
- GraphRAG shows how entity relations and community summaries help global, corpus-level questions.
  This project should first exploit explicit `memory_relations` for quote, URL, bookmark, media, same
  topic, and freshness stitching before adopting a heavier graph framework.
- ADW-style orchestration is useful as contract discipline: parse/retrieve/reason/act boundaries,
  typed handoffs, audit logs, and human review. It should not imply broad autonomous mutation of the
  local evidence store.

Rejected alternatives:

- Replacing FTS/exact/relation retrieval with Corpus2Skill navigation.
- Building many route-specific embedding indexes upfront.
- Averaging or directly comparing scores from unrelated embedding providers/profiles.
- Making an open-ended Agentic RAG loop the default query path.
- Adding a graph database before relation-table evals show that it improves real routes.

Implementation impact:

- Keep `general_memory` / `memory-doc-embedding-v1` as the normal broad semantic arm, not as the
  top-level pipeline center.
- If a route-specific profile is proposed, add route evals that prove recall or ranking improvement
  and report coverage/staleness by provider, model, dimensions, profile, and template.
- Persist per-engine contributions in search/workflow artifacts so a fused result can be audited.
- Prefer RRF or another rank-level fusion for candidate merging, followed by optional bounded
  reranking/judging over a small candidate set.
- Corpus2Skill outputs and GraphRAG/community summaries are not citation-ready unless selected
  context chunks still link back to raw local or extracted external sources.

Primary sources checked:

- Corpus2Skill README: https://github.com/dukesun99/Corpus2Skill
- Corpus2Skill paper: https://arxiv.org/abs/2604.14572
- Azure AI Search hybrid/RRF: https://learn.microsoft.com/en-us/azure/search/hybrid-search-ranking
  and https://learn.microsoft.com/en-us/azure/search/hybrid-search-how-to-query
- Qdrant hybrid and multi-vector docs: https://qdrant.tech/documentation/search/hybrid-queries/,
  https://qdrant.tech/documentation/manage-data/points/, and
  https://qdrant.tech/documentation/tutorials-search-engineering/using-multivector-representations/
- Microsoft GraphRAG paper/docs: https://arxiv.org/abs/2404.16130,
  https://microsoft.github.io/graphrag/query/overview/, and
  https://microsoft.github.io/graphrag/index/overview/
- LlamaIndex Agentic RAG / ADW / workflow docs:
  https://developers.llamaindex.ai/python/framework/optimizing/agentic_strategies/agentic_strategies/,
  https://www.llamaindex.ai/blog/introducing-agentic-document-workflows,
  https://www.llamaindex.ai/blog/beyond-chatbots-adopting-agentic-document-workflows-for-enterprises,
  and https://www.llamaindex.ai/blog/introducing-workflows-beta-a-new-way-to-create-complex-ai-applications-with-llamaindex

### 2026-06-01: Question-Type Coverage Before More Retrieval Changes

Decision:

- Add a machine-readable question-type catalog before widening retrieval fusion or adding more
  retrieval providers or real API embedding recall arms.
- Treat the user's concrete examples as seed cases, not as the full task surface.
- Keep the current route planner/eval behavior intact while tagging eval cases with question types.

Rationale:

- RAG and IR benchmarks separate tasks such as simple recall, set recall, aggregation, comparison,
  multi-hop reasoning, temporal/freshness, false-premise abstention, citation/provenance,
  multilingual retrieval, multimodal grounding, personalization, and exploratory mapping.
- A personal X memory database needs all of these entry points eventually. Optimizing only for the
  first few user examples would overfit the route planner and make later retrieval changes brittle.
- This phase is deliberately safer than changing scoring: it records the target surface and exposes
  current readiness/risks without altering ranking behavior.

Implementation impact:

- `memory question-types` lists the catalog.
- Eval cases can carry `question_type`; stored eval metadata preserves it.
- The next retrieval-fusion work should prove improvements per question type, not only per route.

Sources used:

- BEIR, MTEB, MIRACL, HotpotQA, MuSiQue, 2WikiMultiHopQA, CRAG, FRAMES, LongMemEval, RAGAS, ARES,
  DeepEval, and multimodal retrieval benchmark patterns.

### 2026-06-02: Adaptive Evidence Portfolio Beats Naive Multi-Provider Embeddings

Decision:

- Do not implement "run every embedding provider and fuse everything" as the production default.
- Keep evidence-first retrieval, source-bundle restoration, FTS, metadata, relations, derived
  documents, and a broad semantic arm when built as the baseline that any multi-provider design must
  beat.
- Treat multiple providers as an `Adaptive Evidence Portfolio`: provider-specific embeddings are
  challenger or specialist retrieval engines, selected by route and eval evidence, not a permanent
  fanout.
- Fuse candidates at the source-bundle level whenever practical. A hit on a quote child, media doc,
  bookmark doc, derived card, or semantic provider result must canonicalize back to the root evidence
  bundle before final context selection.
- Use provider diversity only when it adds a distinct failure-mode advantage: Japanese short text,
  cross-lingual aliases, technical jargon, multimodal/media evidence, or exploratory topic mapping.
- Keep raw provider scores out of cross-provider ranking. Fusion may use rank-level signals, route
  weights, bundle-level evidence features, and bounded reranking after source restoration.

Rationale:

- Primary systems such as Qdrant and Azure AI Search support multi-query / multi-vector retrieval
  with RRF, but they also expose the need for candidate depth, separate score ranges, weighting, and
  debug traces.
- Production-style RAG-Fusion evidence shows that higher raw recall can be neutralized by reranking
  and truncation budgets. This means more providers can create more noise without improving the final
  answer.
- Financial/text-table retrieval benchmarks show that BM25 can outperform dense retrieval for exact
  or numeric domains, and that hybrid plus reranking can be strong only after the corpus and route are
  shaped correctly.
- A personal X memory DB is not one semantic task. It mixes exact entity recall, subjective bookmark
  ownership, quote/media reconstruction, author history, temporal freshness, and broad learning maps.
  Multi-representation is required; multi-provider is optional.

Rejected alternatives:

- Always querying OpenAI, Gemini, Voyage, Jina, Cohere, and Mistral at runtime.
- Declaring multi-provider embeddings superior before an evidence-first baseline and at least one
  real API semantic arm are measured.
- Treating provider agreement as truth. Agreement is a ranking signal only; final evidence still
  comes from context chunks and citations.
- Treating provider disagreement as an automatic answer-expansion signal. Disagreement should first
  trigger bundle restoration and eval logging.
- Adding multimodal or domain-specific providers before media/OCR/derived source contracts can cite
  the restored local source.

Implementation impact:

- `memory portfolio-eval` is the experimental portfolio/eval contract. It compares lexical-only and
  candidate semantic arms under the same eval cases, reports per-arm case verdicts and summaries,
  detects fusion regressions against the strongest case-level arm, applies a conservative promotion
  verdict, then reports source-bundle-level RRF fusion without changing the production
  `memory search` ranking path.
- Portfolio semantic arms default to `mode=semantic_only`, so provider candidates are tested as
  independent retrieval engines before fusion. Use `mode=hybrid` when the experiment is specifically
  about the existing local hybrid search with one provider added.
- Candidate engines need stable names, provider/model/profile/template metadata, route weights,
  rank positions, and bundle restoration metadata.
- Eval must compare at least: lexical-only, lexical+relations+derived, one production provider,
  candidate multi-provider RRF, and source-bundle-restored context.
- Go only if multi-provider retrieval improves measured route-level evidence quality over the
  single-provider baseline without degrading exact-token, citation, abstention, quote/media, or
  freshness routes.
- If the eval gain is only from more raw recall but not from final context/citation quality, improve
  document views, relations, query routing, or reranking before adding provider complexity.
- `guarded_rrf` is the default portfolio fusion mode. Raw RRF is still available for comparison,
  but semantic-only candidates are deferred unless lexical retrieval also found the bundle or enough
  independent arms agree. Lexical-backed bundles keep lexical-arm order, so semantic providers can
  add coverage without silently reordering exact/metadata hits. This preserves entry breadth while
  making fusion regressions visible.
- The implemented portfolio arms are separated as `fts_only`, `local_hybrid`, `semantic_only`, and
  optional `hybrid`. `local_hash` is diagnostic-only after provider-name normalization and can never
  clear promotion gates, even if it wins sample cases.
- Semantic-only candidates must pass strong machine-anchor filters when a query contains a hard
  identifier such as a URL, handle, long tweet/user id, or unknown synthetic token. Date-like terms
  such as `5/29`, `2026年5月29日`, or `2026.05.29` stay as search/ranking terms, not hard filters,
  because hard date matching can destroy recall across source formats.
- False-premise cases with explicit `no_local_evidence` expectations can succeed with no hits. If
  weak evidence appears instead, the case is reviewable unless it is an answerable route that should
  have matched required terms.
- Semantic indexes are current only when the embedding row still matches both the source document
  hash and the embedding-text hash. Stale rows are excluded from semantic search/eval instead of
  being treated as fallback candidates.

Sources checked:

- Qdrant Hybrid Queries: https://qdrant.tech/documentation/search/hybrid-queries/
- Azure AI Search RRF scoring: https://learn.microsoft.com/en-us/azure/search/hybrid-search-ranking
- RAG-Fusion deployment study: https://arxiv.org/abs/2603.02153
- Text/table retrieval benchmark: https://arxiv.org/abs/2604.01733
- Anthropic Contextual Retrieval: https://www.anthropic.com/engineering/contextual-retrieval
- RAGRouter-Bench: https://arxiv.org/abs/2602.00296
- Voyage embeddings API: https://docs.voyageai.com/reference/embeddings-api-1
- Cohere Embed API v2: https://docs.cohere.com/v2/reference/embed
- Mistral embeddings API: https://docs.mistral.ai/api/endpoint/embeddings
- Jina Embeddings API: https://jina.ai/en-US/embeddings/

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

2026-06-03 decision note:

Decision:

- restore the top-level architecture to Evidence/Skill/Workflow first;
- keep real API embeddings, including multi-provider embeddings, as candidate recall arms rather
  than the system center;
- use a workflow-gated adaptive portfolio instead of a blanket "non-vector first" rule or a blanket
  "run every embedding provider" rule;
- route exact/structured questions through FTS, metadata, relations, derived cards, and source
  bundles first;
- allow semantic, cross-lingual, learning-map, author-stance, and media-text questions to run real
  API embedding arms in parallel when the route planner predicts they add recall;
- keep Corpus2Skill as a navigation/skill map and Agentic RAG as bounded orchestration with logs and
  stop reasons;
- require every fused result to return to source bundles and citation-ready context chunks before
  answer generation.

Rationale:

- Corpus2Skill's strength is navigation, not replacing exact evidence lookup in a heterogeneous
  personal X database;
- Azure/Qdrant-style hybrid retrieval supports parallel candidate engines and rank-level fusion,
  but also confirms that raw scores from different engines are not directly comparable;
- AgenticRAG-style orchestration reduces dependence on a fixed single-shot candidate set, but the
  reliability risks require bounded workflows, typed steps, and stop reasons;
- the user's data contains exact author/date/URL/bookmark/media signals that dense retrieval can
  hide, so non-vector evidence remains a first-class path;
- the user's learning and cross-lingual questions can benefit from real API embeddings, so
  embeddings should not be removed or delayed globally.

Rejected shortcuts:

- treating a single broad embedding index as the production objective;
- treating Corpus2Skill as a complete replacement for retrieval, context chunks, or citations;
- running every provider on every query by default;
- mixing vectors from different providers or profiles into one distance space;
- using generated navigation summaries, labels, or answers as source truth.

Implementation impact:

- strategy registries should default to evidence/skill/workflow routes, not `general_memory`;
- `api_embedding_portfolio` should expand real API semantic candidates only when explicitly
  requested or when a workflow route calls for semantic recall;
- `portfolio-eval` should compare lexical, relation/source-bundle, Corpus2Skill navigation hints,
  workflow routing, and real API embedding arms under the same route-level cases;
- `local_hash` remains diagnostic and must be blocked from promotion;
- docs and runbooks should say "semantic arm quality requires real API embeddings" rather than
  "the whole production pipeline requires an embedding index."

2026-06-02 decision note:

Decision:

- do not frame the next design as "single embedding vs multiple embedding spaces";
- compare provider/model strengths, fielded FTS, exact-anchor engines, relation engines,
  contextual BM25, source-bundle restoration, rerankers, claim-level citation verification,
  freshness/version lineage, learned sparse retrieval, late interaction, and native multimodal
  retrieval as peer design inputs;
- keep the current production bias toward local evidence, exact/FTS/metadata search, relations,
  source-bundle restoration, and bounded workflows; real API embedding arms must prove their value
  through route-level evals;
- preserve wider entry points by recording candidate kind, modality, route role, adoption status,
  document scope, provider/model/dimension, and promotion/rejection gates;
- pass only current text-search-compatible semantic candidates to `portfolio-eval`; non-semantic
  candidates remain visible as design/eval targets until their execution arms are implemented;
- keep native multimodal candidates visible but deferred until media input and citation restoration
  contracts exist.

Rationale:

- primary sources support named vectors, multiple vector fields, multimodal vectors, sparse+dense
  hybrid search, RRF-style fusion, reranking, and contextual retrieval, but they also show that each
  extra representation must be queried, fused, and audited explicitly;
- model/provider score scales are not directly comparable, so final ranking must preserve
  contribution metadata and use rank fusion or a reranker instead of raw score averaging;
- SQLite FTS5 still has underused headroom through field weighting and exact-anchor behavior, so
  dense-provider complexity should not be used to cover exact lookup defects;
- reranking over a restored evidence bundle is often a higher-value next test than adding another
  persistent vector space, because it can improve context precision without fragmenting indexes;
- contextual BM25/doc2query-style hints can improve lexical recall, but generated retrieval text
  must stay search-only and cannot become evidence;
- citation presence does not prove claim support, so answer-time claim verification is a separate
  evidence-quality layer;
- dynamic X/Web evidence needs version/freshness lineage, not only semantic similarity;
- benchmark papers and practitioner reports do not show a universal winner across domains, so
  local route-level eval is the promotion gate.

Rejected shortcuts:

- revive the old static "model X is best for category Y" table as a production rule;
- run every provider/profile on every query by default;
- embed images natively before media hits can be restored to tweet/media citations;
- solve exact entity/date/place misses by adding dense providers before fixing FTS, metadata,
  derived cards, and relations.
- let a single source, benchmark, blog post, or model claim determine the architecture without
  checking local query types, context budgets, and citation behavior.
- add GraphRAG, RAPTOR, Corpus2Skill, or provider answer engines as citation-ready evidence.

Implementation impact:

- `memory retrieval-strategies` is the candidate-space registry and recommendation view;
- `memory embedding-strategies` is only a compatibility alias;
- `memory portfolio-eval --strategy <id>` adds only portfolio-eligible semantic candidates from
  a broader retrieval/evidence strategy;
- production `memory search/context/workflow` still uses explicit provider/profile inputs until
  strategy-specific routing and context/citation evals are implemented;
- native multimodal, rerank, contextual BM25, claim verification, and lineage candidates stay
  documented with status/preconditions instead of being silently dropped.

Decision process:

1. check the current proposal against primary and secondary sources, including counterarguments;
2. check provider/model strengths and weaknesses as reusable design inputs, not as fixed winners;
3. compare the gathered material against additional local design options such as document views,
   lexical/hybrid retrieval, reranking, relations, context bundles, and native multimodal routing;
4. implement only the part that survives that comparison;
5. audit, test, and loop until no narrowed entry point or unsupported shortcut remains for the
   current milestone.

Primary/secondary references:

- Milvus multi-vector hybrid search:
  <https://milvus.io/docs/multi-vector-search.md>
- Qdrant named vectors:
  <https://qdrant.tech/documentation/manage-data/points/>
- Weaviate named vectors and hybrid search:
  <https://docs.weaviate.io/weaviate/concepts/search/vector-search>
- Azure AI Search RRF scoring:
  <https://learn.microsoft.com/en-us/azure/search/hybrid-search-ranking>
- Elasticsearch RRF:
  <https://www.elastic.co/docs/reference/elasticsearch/rest-apis/reciprocal-rank-fusion/>
- SQLite FTS5:
  <https://www.sqlite.org/fts5.html>
- Anthropic Contextual Retrieval:
  <https://www.anthropic.com/engineering/contextual-retrieval>
- OpenAI embeddings:
  <https://platform.openai.com/docs/guides/embeddings>
- Gemini API embeddings:
  <https://ai.google.dev/gemini-api/docs/embeddings>
- Voyage embeddings:
  <https://docs.voyageai.com/docs/embeddings>
- Voyage rerankers:
  <https://docs.voyageai.com/docs/reranker>
- Cohere Embed v4:
  <https://docs.cohere.com/docs/cohere-embed>
- Cohere rerankers:
  <https://docs.cohere.com/docs/reranking>
- Jina embeddings v5 text:
  <https://jina.ai/models/jina-embeddings-v5-text-small>
- Qwen3 Embedding:
  <https://github.com/QwenLM/Qwen3-Embedding>
- FActScore:
  <https://arxiv.org/abs/2305.14251>
- VersionRAG:
  <https://arxiv.org/abs/2510.08109>
- FRESCO:
  <https://arxiv.org/abs/2604.14227>
- MTEB:
  <https://arxiv.org/abs/2210.07316>
- BEIR:
  <https://arxiv.org/abs/2104.08663>

Current strategy classification:

- implemented baseline: `baseline_hybrid_foundation` with FTS, LIKE, metadata, semantic when
  explicitly configured, relation expansion, RRF metadata, and source-bundle restoration;
- workflow-first next candidates: `corpus2skill_navigation`, `bounded_workflow_orchestration`,
  source-bundle restoration, and route-gated portfolio selection;
- high-value evidence candidates: `contextual_bm25`, `rerank_stage`,
  `claim_citation_verification`, and `freshness_lineage`;
- real API embedding recall arms: `api_embedding_portfolio`, `general_memory`, `jp_multilingual`,
  `learning_long`, `code_technical`, and `media_text_bridge`;
- Japanese/cross-lingual recall: route-gated challengers such as Voyage/Jina/Gemini;
- long-form learning and concept maps: route-gated challengers such as Voyage, OpenAI large,
  Jina, Corpus2Skill maps, topic threads, and relation expansion;
- code/API/repository material: `code_technical` challengers such as Mistral or Voyage code
  embeddings, only for route-specific evals;
- media/OCR/caption routes: `media_text_bridge` challengers only after media docs expose
  citation-ready OCR, caption, alt text, or VLM text;
- exact entities, dates, tickers, handles, and places: keep FTS/metadata/relations/derived cards as
  the guardrail before adding dense-provider complexity.

Use `memory retrieval-strategies` to inspect these profiles and
`memory portfolio-eval --strategy <id>` to add the candidate semantic arms to the comparison gate.

Risk:

- scores across embedding profiles are not directly comparable;
- routing errors can hide good evidence;
- profile proliferation increases cost and rebuild complexity.
- workflow gates can under-call embeddings when semantic recall is needed, or over-call them when
  exact evidence is already enough.

Therefore portfolio routing and profile splitting must be evaluation-driven, not assumption-driven.

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

## Implementation Order

1. Document this V2 design and keep existing code stable.
2. Add schema for tool/search runs, context chunks, citations, and answer runs.
3. Refactor evidence output so local hits and citations are explicit.
4. Add derived view builders for `place_card`, `author_profile`, `ticker_event`, and
   `topic_thread`.
5. Add external evidence provider interface, initially with a no-network fake/test provider.
6. Add reader/extract providers and normalize extracted URL text into context chunks.
7. Add Brave LLM Context provider only after storage/retention/rate-limit handling is explicit.
8. Add answer artifacts and answer-specific citation annotations.
9. Add workflow routing and workflow traces.
10. Expand evals to route-level cases.
11. Align strategy defaults with Evidence/Skill/Workflow first so `general_memory` is not selected
    merely because a query exists.
12. Integrate Corpus2Skill OSS export/navigation as a map and route hint, not as citation-ready
    evidence.
13. Add and evaluate real API embedding recall arms as separate candidate engines.
14. Promote an embedding provider/profile only when route-level evals show improvement after
    source-bundle restoration and citation checks.

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
