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

The final system is no longer "current workflow only" or "router first". The current skeleton is:

```text
User Query
  -> ObjectiveRoutePolicy
  -> QueryTransform / QueryVariants
  -> Candidate Arms
       exact / FTS / metadata / relation
       user-profile ranking hints
       semantic embeddings
       sparse / late interaction / rerank
       media OCR / visual retrieval
       Corpus2Skill / graph navigation
       external web / managed reference
  -> Source Bundle Restoration
  -> Guarded Fusion / Rerank
  -> Context Chunk Construction
  -> Citation Verification
  -> Answer or Abstain
  -> Eval Gates
  -> Workflow Trace / Feedback / Rebuild
```

The central invariant:

```text
raw source != searchable document != search result != context chunk != citation != answer
```

Each object must be traceable backward to its source and forward to the answer or workflow that used
it.

## Final Skeleton Decision

The active skeleton is:

```text
Evidence / Source Bundle First
+ ObjectiveRoutePolicy
+ Evaluation First
+ Security Boundary
+ Continuous Projection / Temporal Ops
```

This decision was made after treating the older Evidence/Skill/Workflow-first design as a candidate,
not as an unquestioned premise, and comparing it with router-first, graph-first, vector-first,
agent-first, skill-map-first, multimodal-first, and evaluation-first materials.

Final classification:

- Must be part of the skeleton:
  - Evidence / Source Bundle First.
  - ObjectiveRoutePolicy.
  - route, retrieval, context, citation, answer, and abstention evaluation gates.
  - QueryTransform and RetrievalTextProfile as non-evidence artifacts.
  - media evidence levels from raw media match to citation-ready content evidence.
  - user model and personalization as ranking policy, not evidence.
  - projection generation, index membership, source state, temporal validity, and backfill records.
  - source-sink security policy, trust boundaries, taint flags, and allowed sinks.
- Permanent candidate lanes, not unconditional default execution:
  - exact / FTS / metadata / relation search;
  - semantic embedding portfolio;
  - learned sparse / sparse lexical arms;
  - late interaction / ColBERT-style stages;
  - rerank cascades;
  - OCR / visual retrieval;
  - Corpus2Skill navigation;
  - graph/topic navigation;
  - external Web context;
  - long-context route;
  - managed RAG references.
- Useful hints, never citation-ready evidence:
  - AI labels;
  - user profile and implicit feedback;
  - generated query expansions, HyDE text, and subqueries;
  - Corpus2Skill summaries;
  - graph/community summaries;
  - VLM observations;
  - router confidence;
  - embedding or reranker scores.
- Avoid in the final architecture:
  - hard router selection that keeps only one entry point without measured recall loss;
  - using a vector DB as the source of truth;
  - using graph/ontology data as the source of truth instead of a projection;
  - treating VLM/OCR output as evidence without chunk/citation promotion;
  - always-on personal boosting for all queries;
  - accepting correct-looking answers without provenance;
  - treating external Web, OCR, tweet text, or tool output as trusted instructions.

## Scope Hygiene

Keep the design surface small.

- This file is the single detailed architecture source.
- `docs/memory-pipeline-archive.md` stores historical decision notes. Use its index to find and read
  only relevant old sections when a current decision needs prior research or rejected alternatives.
- `PROJECT.md` is only the implementation milestone tracker.
- `README.codex.md` is the compact Codex repository reference.
- `README.md` is the human/GitHub repository entry point.
- `AGENTS.md` tells coding agents which file to read; it must not duplicate the architecture.
- Do not add another memory-architecture Markdown file unless the user explicitly asks.
- When changing the design, update this file first, then adjust `PROJECT.md` only if the milestone
  order changed.
- Prefer appending a short decision note here over scattering partial plans through new files.
- When Plan Mode or the user provides a concrete implementation plan, record the durable design
  contract here before code. The implementation may then change the code, README, and PROJECT to
  match this file.

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

Archived source-review detail lives in `docs/memory-pipeline-archive.md`. This active file keeps only
durable current conclusions so agents do not spend context on historical source summaries.

Current durable conclusions:

- Web/search systems are useful mainly because they separate discovery, extraction, context chunks,
  citations, and answer synthesis.
- Corpus2Skill, graph summaries, labels, query transforms, and VLM observations are navigation or
  interpretation artifacts, not source evidence.
- Agentic search is useful only as a bounded workflow with logs, stop reasons, source-bundle
  restoration, citation gates, and budget/security guards.

## Active Decision Record

Historical decision notes and source-review logs are archived in
docs/memory-pipeline-archive.md. During normal implementation, use this active file first. When a
current decision needs prior research, inspect the archive index and read only the relevant archived
section.

Current active decisions:

- Evidence / Source Bundle First remains the evidence center after re-evaluation. ObjectiveRoutePolicy
  controls execution, but does not replace source bundles, context chunks, citation verification, or
  workflow traces.
- External discovery, subquery fan-out, browser-history hints, sub-agent notes, SERP rank, snippets,
  provider summaries, and AI-generated exploration notes are search-control artifacts. They can
  widen recall and explain why a route was tried, but they are not evidence until fetched or restored
  into source bundles, context chunks, and citation annotations.
- Real API embeddings are optional recall arms inside a workflow-gated portfolio; local_hash is
  diagnostic only.
- Multiple embedding providers or profiles are separate candidate engines. Never mix their vectors
  into one shared distance space or average raw scores across providers.
- Text embedding and OCR use small limits for different reasons. A text embedding limit is a
  technical canary or evaluation slice before provider/profile promotion; a promoted text embedding
  arm must eventually cover its full selected document scope. OCR limits are calibration or
  candidate-set controls because OCR is per-media evidence preparation and full-media OCR is not the
  default target.
- Candidate results must be restored to source bundles before context chunking, citation, reranking,
  answer generation, or promotion.
- Corpus2Skill is a navigation map and route hint, not citation-ready evidence.
- QueryTransform, HyDE, subqueries, contextual retrieval text, SPLADE/doc expansion text, and
  RetrievalTextProfile rows are search artifacts. They must be traceable and auditable, but are not
  source evidence.
- User models, personal preference signals, implicit feedback, and active-learning labels are
  route-aware ranking policies or review signals. They must not become answer citations.
- Rebuildable indexes are projections. Track source hashes, projection generations, index
  membership, stale/tombstone status, backfills, and temporal validity.
- External Web text, OCR output, tweet text, media text, and tool output are untrusted data. Before
  they can affect tools, provider calls, writes, external fetches, or answers, they must pass the
  relevant source-sink policy and citation/evidence gate.
- Architecture decisions must follow the decision-quality loop in AGENTS.md: inspect repo state,
  search primary then secondary sources when needed, treat sources as inputs, evaluate alternatives,
  and loop when new uncertainty appears.

### 2026-06-10: Codex Inbox Design Placement

The `_codex_inbox` design package is an input review package, not a new source of truth and not an
active execution prompt. Durable memory/search decisions from it belong in this file; fetch,
snapshot, auth, and network-provider policy belongs in `docs/pipeline.md`; bulky source-review
history belongs in `docs/memory-pipeline-archive.md`; short implementation status belongs in
`PROJECT.md`.

Already implemented from the inbox direction:

- Evidence/source-bundle first invariants, context chunks, citation annotations, answer artifacts,
  workflow traces, eval persistence, and audit checks.
- ObjectiveRoutePolicy execution, research-control artifacts, no-spend route execution, and
  CLI/app inspection surfaces for research runs.
- External discovery, Reader/extract, LLM-context, embedding, rerank, OCR/media, and managed
  reference contracts as fake/local or provider-gated lanes.
- API Budget Guard, provider role separation, price/usage ledger, kill switch, and no-quota freeze.
- Corpus2Skill export/navigation as an advisory map, not citation-ready evidence.
- Native repo Skill metadata for recurring `research_x` workflows, without a project-local prompt
  router.
- Dry-run research intake contracts for `InterestProfile`, `SourceRegistry`, normalized
  `ResearchCandidate` rows, metadata-only snapshots, deterministic scoring, and `ResearchBrief`
  review artifacts. These are review/control artifacts only; they do not become evidence until a
  later fetch/extract path restores source bundles and context chunks.
- `ContextBudgetPolicy` for output-time context/workflow/answer JSON budgeting with local
  offload-pointer artifacts. It may replace oversized inline `context_chunks[*].chunk_text` fields
  in CLI/output payloads with previews plus hashes and file pointers, but it must not mutate stored
  context chunks, citation annotations, source-bundle restoration data, raw payload hashes, or
  answer-generation inputs.
- Source-backed memory governance records for profile hints, contradiction notes, retention
  policies, forgetting requests, and tombstones. Each governance record must carry a source anchor
  and source hash/reference. Active tombstones suppress matching `memory_document` or source-tweet
  artifacts from search results, but v1 does not physically delete source rows, rewrite citations,
  or create cross-project personal memory.
- PromptContract/MNP deterministic checks for read-only memory routing and allowed/forbidden tool
  boundaries. They validate local prompt contracts and virtual endpoint manifests without calling an
  LLM or provider, and they are guardrail tests around code-owned tools rather than runtime
  authority.

Residual design that may be implemented later, if a scoped task justifies it:

- Automatic budget policy for additional bulky tool outputs beyond context/workflow/answer JSON.
  Any future expansion must keep restore pointers, hashes, source references, and citation anchors
  visible in the inline payload.
- Networked research intake beyond the dry-run/manual/local path: public fetches, hosted search,
  Reader/extract, LLM summaries, provider rerank, and automatic promotion into evidence. Discovery
  hints remain non-evidence until fetched/restored into source bundles and context chunks.
- Proposal-only `ImprovementSignal` capture for repeated Codex failures, route misses, doc drift,
  provider-gate violations, and eval failures. It may produce candidate reports or PRs, but must not
  auto-merge `AGENTS.md`, repo Skills, provider policy, or architecture docs.
  The v1 implementation is local-only: JSONL signal capture, deterministic triage, proposal-only
  candidate reports, rejected-edit buffers, schema validation, and no-provider tests. It must not
  call LLMs, external search, hosted memory, provider APIs, or connector tools.
- Physical deletion workflows and cross-project personal memory sync for source-backed governance.
  They remain opt-in only and require explicit source restoration, deletion audit, tombstone, and
  retention semantics before use.
- Real-model PromptContract/MNP validation, Prompt-as-Server runtime behavior, or use of MNP as a
  backend authority. Those remain out of scope until provider, auth, DB-write, transaction, and
  source-restoration boundaries are explicitly reviewed.
- Skill/source manifest review for any third-party Skill or plugin considered for this repo. It is a
  security/governance surface, not a memory-search source object.

Not adopted into `research_x` from the inbox package:

- hosted Supermemory or cross-project personal memory by default;
- Webshare/proxy scraping defaults;
- unofficial ChatGPT backend APIs;
- bulk global installation of third-party Skill catalogs;
- Prompt-as-Server as a backend replacement;
- the broad `12_codex_execution_prompt.md` as an instruction for this repository.

## Research Control Artifacts

AI-callable search needs a control plane that prevents external discovery from becoming a flattened
generic Web answer. The following artifacts are part of ObjectiveRoutePolicy and workflow traces:

- `ResearchTaskFrame`: the pre-search statement of what the user is asking, what counts as enough
  evidence, whether the local X DB is primary, where personalization may influence ranking, and when
  the workflow should abstain or ask for review.
- `SearchPlanGraph`: the planned route arms, query variants, provider roles, fallback order, and
  escalation edges. It records why a route may run; it does not make any route result factual.
- `SearchEpisodeTrace`: the executed route arms, provider skips, stop conditions, and escalation
  events for a single run. It explains what actually happened, but it is still not evidence.
- `ProviderCapabilityMatrix`: the allowed role of each provider or local arm. For example, Serper is
  `index_provider` URL discovery; Reader/Jina is extraction; Brave LLM Context is external grounding;
  browser history is a weak personal recall hint; local X DB is the primary source bundle surface.
- `ResultCoverageMap`: route/document/source/provider coverage after execution, including skipped
  provider arms and source-bundle restoration failures.
- `EvidenceGap`: missing evidence, missing citations, provider-quota blocks, weak source coverage,
  or media-content gaps that prevent answer promotion.
- `SourceQualitySignal`: source-kind and provider-role classification such as local X DB, official,
  primary, secondary, community observation, affiliate/leadgen, AI-suspected, or unknown. This is a
  ranking and review signal, not a citation by itself.
- `ReaderQualityProfile`: whether fetched or reader-produced content has enough text, source URL,
  content hash, and source-kind information to be considered for context chunking.
- `SERP Flattening Audit`: a check that rank, snippet, AI summary, and fixed source quotas did not
  become evidence or create a false sense of coverage.
- `ClaimSupportCheck`: a deterministic support summary for whether the produced context and
  citations can support answer claims. Semantic claim judging remains a provider or human gate.
- `PersonalizationPolicy` and `UserSignal`: user-specific ranking hints such as bookmarks, accounts,
  refinding, or preference signals. They influence route weighting only and must never become answer
  citations.
- `ResearchBrief`: the post-execution summary of routes tried, evidence found, gaps, and next
  actions. It is an output artifact, not source evidence.

Implementation boundary:

- Store these artifacts in existing route/workflow metadata and step outputs before adding new
  tables.
- Treat the first-class inspection surface as part of the contract. If `ResearchTaskFrame`,
  `SearchPlanGraph`, `EvidenceGap`, `SourceQualitySignal`, `ClaimSupportCheck`, or `ResearchBrief`
  exist only in JSON that users cannot inspect from CLI/app flows, the workflow is still too
  black-box to promote.
- Expose the same run inspection in the local app, not only in CLI. The app may stay read-only for
  this surface, but route choices, evidence gaps, source quality, claim-support state, context
  chunks, and citations must be inspectable from the browser UI before the workflow is treated as
  operationally usable.
- Keep generated or provider-produced exploration artifacts `citation_excluded`.
- Serper rank, snippets, browser history, sub-agent notes, and AI summaries must pass through
  fetch/reader/source-bundle restoration before they can produce context chunks or citations.
- If the artifacts reveal only weak or generic external evidence, the workflow must return
  `needs_review` or `insufficient_evidence` rather than smoothing the answer.

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
11. Generated query text, generated retrieval text, labels, summaries, profile scores, router
    confidence, and model scores are hints. They are never direct evidence.
12. Personalization is route-scoped ranking policy. It must be gated by intent and evaluation, not
    applied globally.
13. OCR-free visual retrieval and VLM observations are recall or interpretation candidates. They
    become citation-ready only after source-bundle restoration and region/page/chunk promotion.
14. Every provider/tool surface must preserve trust boundary, source visibility, account scope,
    data classification, and allowed sink metadata.
15. Media role classification is a route policy and annotation layer, not evidence. It may decide
    whether an image needs no-op, caption, OCR, layout OCR, chart/visual reasoning, or hybrid
    OCR/VLM handling, but it cannot support answer claims by itself.
16. Codex or VLM image readings are user/session-conditioned observations. Store them as derived
    annotations with provenance and source hashes; use them for recall, ranking, or inference only
    unless citation-ready OCR/caption/VLM chunks explicitly support the claim.

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

Active policy summary:

- Evidence / Source Bundle First remains the center. Retrieval arms, route policy, embeddings, OCR,
  Corpus2Skill, graph summaries, labels, query transforms, media roles, observations, and scores are
  candidate or navigation signals until restored into source bundles and citation-ready context.
- ObjectiveRoutePolicy selects primary, fallback, and escalation routes. It is a workflow control
  layer, not evidence and not a replacement for source-bundle restoration.
- Real provider embeddings, rerankers, Reader/OCR, external search, classifiers, answer engines,
  relation judges, and managed-RAG references remain behind provider gates and API Budget Guard.
- `local_hash` and fake providers are diagnostic wiring checks only.
- QueryTransform, HyDE/subqueries, RetrievalTextProfile, Corpus2Skill summaries, graph/community
  summaries, VLM observations, router confidence, embedding scores, and reranker scores are hints.
  They must not be used as answer citations by themselves.
- Personalization is route-scoped ranking policy. It must be gated by intent and evaluation, not
  applied as a global boost.
- Search indexes and projections must track source hashes, projection generation, index membership,
  stale/tombstone status, backfills, and temporal validity.
- External Web text, OCR output, tweet text, media text, and tool output are untrusted data until the
  relevant source-sink, evidence, and citation gates pass.

Operational rule:

```text
query
  -> ObjectiveRoutePolicy
  -> candidate arms
  -> Source Bundle Restoration
  -> guarded fusion / rerank
  -> Context Chunk Construction
  -> Citation Verification
  -> Answer or Abstain
  -> Eval / feedback / rebuild
```

Detailed historical notes for this policy were moved to
`docs/memory-pipeline-archive.md` section `2026-06-08: Retrieval Policy Detail Archived From Active V2`.

## API Budget Guard

Current execution policy:

- External provider API calls are frozen until the user explicitly lifts the no-quota freeze in the
  current conversation.
- The freeze covers paid usage, free-tier usage, trial credits, and any zero-dollar quota
  consumption. "Free" provider calls are still real quota consumption and are not allowed.
- While frozen, run only local/fake providers, read-only estimates that do not contact providers,
  coverage reports, and tests that monkeypatch provider HTTP.
- Do not run real embedding, OCR, rerank, classifier, answer, reader, external-search,
  LLM-context, or managed-RAG calls. Do not use `--allow-unpriced-api`.
- If the freeze is lifted, offline estimates and budget status must be checked before the first
  request, the smallest useful limit must be used first, and the next provider call must be stopped
  when pricing, quota, or budget evidence is unclear.

All paid, free-tier, trial-credit, or otherwise quota-limited provider calls must pass through the
local API budget guard before an HTTP request is sent. While the no-quota freeze is active, this is
a future safety contract only; it is not permission to call providers.

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

Default policy for future provider-call experiments is intentionally conservative:

- run cap: 1 USD;
- day cap: 5 USD;
- month cap: 25 USD;
- unknown price action: block;
- kill switch: off by default, but when enabled it blocks the next provider API call before HTTP.

Unknown prices are not treated as free. During the no-quota freeze, neither price catalog rows nor
`--allow-unpriced-api` override the provider-call prohibition. If the freeze is later lifted, a
provider/model/operation/unit must have a price catalog entry unless the user explicitly permits an
unpriced override in that same conversation. Local/fake providers and diagnostic `local_hash` do not
create billable events.

Use these commands for offline preflight and future monitoring. They do not by themselves authorize
provider HTTP requests:

```powershell
uv run python -m research_x memory api-budget status --db runs/x_data.sqlite3
uv run python -m research_x memory api-budget set --db runs/x_data.sqlite3 --max-run-usd 1
uv run python -m research_x memory api-budget seed-default-prices --db runs/x_data.sqlite3
uv run python -m research_x memory api-lane-estimate --db runs/x_data.sqlite3 --ocr-scope sample
uv run python -m research_x memory api-usage --db runs/x_data.sqlite3 --today
uv run python -m research_x memory api-watch --db runs/x_data.sqlite3 --port 8767
```

The app also shows run/day/month budget status, recent events, and a kill-switch control. Provider
dashboards remain the billing source of truth; the local ledger is a pre-request safety guard and
operational monitor.

Pricing confidence:

- primary-priced rows use explicit provider pricing pages or model documents;
- secondary-priced rows, currently Cohere `embed-v4.0` and Rerank v4 search units, are included in
  estimates only because Cohere primary docs confirm the billing basis while LiteLLM/price-index
  sources provide matching unit prices;
- unknown or dashboard-only prices remain blocked by default in future provider execution. During
  the no-quota freeze, even explicit price rows and `--allow-unpriced-api` do not authorize provider
  calls.

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
memory vector-projection -> Layer 2 acceleration projection over one current embedding scope
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
memory research-runs/show-run -> Layer 7 inspection surface for search/context/workflow/objective traces
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

`memory export-corpus2skill` may optionally include an `agents/openai.yaml` metadata file and an
inert hook advisory note inside the exported bundle. These files are navigation hints for Codex-like
agents only. The generated OpenAI metadata disables implicit invocation; explicit use can still
point an agent at the bundle as a navigation map. These files do not install hooks, do not autoload
skills, do not call providers, and are not evidence. Any answer still has to return through
source-bundle restoration, context chunks, and citations.

Repository recurring workflows use Codex native Skill discovery rather than a project-local prompt
router. The active repo Skills live under `.agents/skills/`, each has trigger-oriented frontmatter,
and each includes `agents/openai.yaml` with implicit invocation enabled. This keeps automatic
workflow selection on Codex's own Skill mechanism while leaving hooks out of the normal path.

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

No-spend residuals from the 2026-06-10 inbox triage should be scoped before provider work when they
directly improve the current evidence pipeline:

1. Add `ContextBudgetPolicy` / offload-pointer contracts only after checking current context
   assembly and inspection surfaces.
2. Extend research intake beyond the implemented dry-run/manual/local/fake path only after defining
   fetch policy, source-bundle restoration, and provider-gate review.
3. Extend PromptContract/MNP beyond the implemented deterministic local checks only after a
   provider/security review defines model, auth, DB-write, and source-restoration boundaries.
4. Add source-backed profile/contradiction/forgetting objects only after defining deletion,
   tombstone, and source-restoration semantics.

Provider-gated next work order:

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
