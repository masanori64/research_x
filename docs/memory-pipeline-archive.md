# Memory Pipeline Decision Archive

This file stores historical decision notes and source-review logs moved out of
docs/memory-pipeline-v2.md so the active architecture source stays small.

The current source of truth remains docs/memory-pipeline-v2.md. During normal implementation, read
that file first. Use this archive like a private-stack catalogue: inspect the index below, then open
only the relevant section when a current decision needs historical context, rejected alternatives,
or old source links. Do not scan the whole archive by default.

## Archive Index

| Topic | Section |
| --- | --- |
| External search providers, Serper, Brave, SearXNG, browser history, Spellbook, WeKnora | 2026-05-31: External Search And Codex-Customization Candidates |
| Diagnostic shrinking, exact Japanese terms, fixture providers, bounded workflow | 2026-06-01: Remove Diagnostic Shrinking From Production Paths |
| Embedding provenance, provider/model/profile/template/source hashes | 2026-06-01: Embedding Provenance Becomes First-Class |
| Freshness relations, newer/older edges, support/contradiction judging | 2026-06-01: Deterministic Freshness Relations First |
| Corpus2Skill boundary and export bundle | 2026-06-01: Corpus2Skill Boundary Stays Explicit |
| Multiple embeddings as separate candidate engines, RRF, GraphRAG/ADW comparison | 2026-06-01: Multiple Embeddings Stay Candidate Engines |
| Question-type coverage and eval task variety | 2026-06-01: Question-Type Coverage Before More Retrieval Changes |
| Adaptive Evidence Portfolio, multi-provider embedding cautions, source-bundle fusion | 2026-06-02: Adaptive Evidence Portfolio Beats Naive Multi-Provider Embeddings |
| Evidence/Skill/Workflow first, API embedding portfolio, workflow-gated adaptive routing | Archived Retrieval Portfolio Decision Notes |
| Gemini Embedding 2 media evidence contract | Active source: docs/memory-pipeline-v2.md |

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

## Archived Retrieval Portfolio Decision Notes

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

### 2026-06-05: Active Research Inputs Compressed

The active architecture document previously carried detailed research-input notes about public Web
Search patterns, Brave LLM Context, Claude/Brave evidence, broader AI-search products, and
Corpus2Skill / Agentic RAG / GraphRAG. Those details were compressed in the active file to reduce
context load.

Durable conclusions retained in the active file:

- search systems should keep discovery, extraction, context chunks, citations, and answer synthesis
  separate;
- Corpus2Skill, graph summaries, labels, query transforms, and VLM observations are navigation or
  interpretation artifacts, not source evidence;
- agentic search must be bounded by logs, stop reasons, source-bundle restoration, citation gates,
  and budget/security guards.

Historical detailed notes:

- OpenAI public Web Search patterns separated `web_search_call` from final message content and used
  URL citations as annotations on answer text.
- Brave Search / LLM Context patterns separated ranked search results, query-conditioned extracted
  context, and final answer generation.
- Claude for Government's Web Search MCP connector explicitly used Brave Search API, while
  commercial Claude / Claude Code did not publicly guarantee a single built-in backend.
- Perplexity, Tavily, Exa, Firecrawl, Jina Reader, and Brave all separated at least some of
  search/discovery, URL extraction, context/chunks, and answer synthesis.
- Corpus2Skill was treated as a stable navigation map or skill tree, not exact evidence.
- Graph-like relations remained valuable only when backed by explicit relation tables and
  provenance.
