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
| Retrieval policy detailed notes moved out of active V2 | 2026-06-08: Retrieval Policy Detail Archived From Active V2 |
| Codex-wide external tools, memory MCP, retrospective/fluent, SkillOpt/Sleep | 2026-06-09: Codex-Wide External Tool Candidates |
| `_codex_inbox` design package placement, implemented/residual split | 2026-06-10: Codex Inbox Design Package Placement |

## Decision Notes

### 2026-06-10: Codex Inbox Design Package Placement

Scope:

- `_codex_inbox` contained a 2026-06-09 Codex design package, source inventory, context export, and
  reproducibility scripts.
- The package was reviewed as input material, not as an active instruction. Its broad execution
  prompt conflicted with the later docs-only/no-code/no-Skill/no-AGENTS request and is not adopted.

Placement decision:

- Active memory/search architecture and implementation residuals live in
  `docs/memory-pipeline-v2.md`.
- External research-intake fetching, snapshot, auth, storage-rights, proxy, and network/provider
  policy lives in `docs/pipeline.md`.
- Short implemented/residual state lives in `PROJECT.md`.
- Detailed file-by-file inbox inventory lives in `docs/codex-inbox-inventory.md`.
- Global Codex foundation ideas, such as generic skill review, security review, planning files,
  context budget, and self-improvement intake, are outside `research_x` unless separately requested.

Implemented overlap found:

- Source-bundle-first evidence objects, context chunks, citations, answers, workflows, evals, audit,
  ObjectiveRoutePolicy, research-control artifacts, provider budget guard, app/CLI inspection,
  external search/read/LLM-context fake/provider-gated lanes, Corpus2Skill export, and native repo
  Skill metadata already cover much of the inbox plan.

Residuals retained as scoped candidates:

- ContextBudgetPolicy/offload pointers;
- automated research intake profiles/subscriptions/snapshots/scoring/ResearchBrief artifacts;
- proposal-only ImprovementSignal capture and validation gates;
- source-backed profile/contradiction/tombstone/forgetting policy;
- deterministic PromptContract/MNP tests;
- Skill/source manifest review if third-party Skills/plugins are later considered.

Rejected or moved out of repo scope:

- hosted Supermemory sync, cross-project personal memory by default, Webshare/proxy defaults,
  unofficial ChatGPT backend APIs, bulk Skill catalog installs, Prompt-as-Server backend
  replacement, generated `/mnt/data` scripts as repo tooling, and the broad execution prompt as an
  active instruction.

### 2026-06-09: Codex-Wide External Tool Candidates

Scope:

- Treat these as Codex-wide external tools or skills, not as `research_x` product features.
- Do not install or call any hosted memory, search, optimization, or provider-backed API while the
  no-quota freeze is active.
- Prefer original upstream implementations and contracts over homemade substitutes.

Decision:

- Use Codex's official surface split:
  - Skill for repeatable procedure;
  - MCP for live memory/context/actions;
  - Plugin when bundling Skill + MCP + hooks/assets for distribution;
  - Hook only for deterministic lifecycle gates;
  - `AGENTS.md` only for short always-on policy.
- Do not bulk-install `majiayu000/spellbook`.
  - `codex-retrospective` is a copy-as-skill candidate only after adapting it to proposal-only
    output, tiny diffs, concrete session evidence, and human approval.
  - `codex-fluent` remains pattern-only until Codex local-state paths and archive safety are
    verified. Never delete; report, handoff, backup, then archive.
- Do not globally install Microsoft SkillOpt-Sleep yet.
  - It is the strongest current skill-optimization candidate because SkillOpt has Codex-harness
    evidence and validation-gated skill edits.
  - The checked Codex plugin still writes a custom prompt and user skill, while the engine retains
    Claude-oriented defaults such as `~/.claude`, `CLAUDE.md`, and global Python runner paths.
  - Use it only as staged/read-only research until adapted for Codex skill paths, `AGENTS.md`,
    `uv`-based execution, Codex session sources, and no-quota hard disable of real backends.
- Treat RPT as a diagnostic prompt-optimization pattern, not as the Codex skill optimizer.
- Treat EvoSkill as a material challenger because it has a Codex harness, but defer it under
  no-quota freeze. It should be a bounded benchmark experiment, not a Codex-wide install.
- Do not install Supermemory or Mem0 globally while the freeze is active.
  - Supermemory's hosted MCP is a viable Codex-compatible memory surface, but cloud memory,
    auto-capture, project scoping, and quota/privacy policy need explicit user approval.
  - Mem0 has clearer Codex plugin/MCP docs and lifecycle hooks, but the same auto-capture and
    quota risks are stronger.
  - Basic Memory is the strongest local/no-cloud counterweight found: local MCP plus Markdown
    project storage, less automatic but more auditable.

Implementation impact:

- For future Codex-wide memory, start with a disabled-by-default MCP profile, explicit tool
  approval, scoped project tags, and no auto-capture hooks unless the user explicitly opts in.
- Recalled memory is advisory. It must not override current repository files, explicit user
  instructions, or source-of-truth docs.
- For future Codex-wide self-improvement, use a staged proposal flow:
  transcript/task evidence -> proposed tiny Skill/AGENTS diff -> held-out or deterministic checks
  -> user approval -> backed-up adoption.
- Do not use auto-adopt, optimizer self-scoring, whole-skill rewrites, validation on training-only
  examples, or provider-backed smoke tests during provider freeze.

Follow-up community/deep-dive deltas:

- The strongest community signal is still persistent memory for Codex, not isolated prompt
  optimization. Recent Reddit/OpenAI Codex discussions repeatedly frame the problem as Markdown
  files becoming stale or unsearchable, while memory MCPs add structured durable facts, session FTS,
  and reusable skill/procedure storage. Treat this as a real user pain signal, but not as proof that
  any one memory vendor is safe to install.
- Add `mem-evolved`, `CORE`, `AutoMem`, `memories.sh`, `codex-memory`, `memoryOSS`, and
  `RecallWorks/Recall` to the watchlist.
  - `mem-evolved` is notable because it combines durable memory, full-text session search, and
    reusable skill storage in a local MCP-oriented package discussed in the Codex community.
  - `CORE` has the highest observed community discussion among the checked Codex memory examples
    and its temporal/provenance graph fits the user's preference for evolving personal context, but
    Reddit comments also raise packaging, documentation, and auditability concerns.
  - `AutoMem` and `memoryOSS` strengthen the graph+vector+trust-threshold direction, but they add
    more infrastructure or hidden policy surface than the current repo should adopt blindly.
  - `memories.sh` is important because it exposes lifecycle-aware local tools such as session start,
    checkpoint, snapshot, and consolidation. This maps directly to Codex handoff/compaction pain.
  - `codex-memory` is a lightweight local-first SQLite/FTS5 candidate with TOON prompt export; it is
    simpler than graph memory and may be useful as a low-risk benchmark/control.
- Long-running Codex harnesses are a separate axis from memory.
  - `Long Long Run` and long-horizon skill discussions reinforce the need for a durable mainline,
    intent-noise reduction, side-thread tolerance, and stop guards.
  - The useful design delta is not bulk-installing those skills; it is keeping exploration,
    promotion, failed-path checkpoints, and completion gates explicit.
- Skill evolution research moved forward after the earlier note.
  - `SkillGrad` adds an explicit gradient-like update pattern with momentum over recurring
    diagnostics.
  - `SkillSmith` argues that raw skill injection wastes tokens and proposes compiling skills into
    minimal runtime interfaces. This supports keeping `AGENTS.md` small and using progressive
    disclosure rather than loading large skill bodies by default.
- Updated staged adoption order for Codex-wide tools:
  1. fix native Skill discoverability and frontmatter correctness;
  2. keep Basic Memory/local Markdown as the first low-risk memory candidate;
  3. evaluate lightweight local memory candidates (`codex-memory`, `memories.sh`, `mem-evolved`) as
     controls before cloud memory;
  4. evaluate cloud/graph memory candidates (`Supermemory`, `Mem0`, `CORE`, `AutoMem`) only behind
     explicit opt-in, scoped projects, no auto-capture default, and source/audit review;
  5. evaluate SkillOpt-Sleep as a dry-run proposal engine only after runner paths, quota controls,
     and Codex skill-path handling are adapted.
- Additional high-community-signal deltas:
  - Prefer OpenAI's official plugin surface and role-specific plugin templates before third-party
    shims when the goal is general Codex augmentation. The official direction is plugin bundles
    containing skills, apps/connectors, MCP entries, assets, and workflows.
  - Add `agentmemory` as a serious but risky Codex-native memory candidate. Its value is broad
    Codex plugin/hook/MCP coverage; its risk is equally broad lifecycle hooks, auto-capture, version
    drift, and privileged memory writes.
  - Add `context-mode` and token-reduction workflows to the watchlist because part of the "memory"
    pain is actually context-output control and token-budget leakage, not missing recall alone.
  - Treat package-supply-chain attacks against Codex-adjacent tooling as a first-class install
    risk. A clean GitHub page is insufficient evidence; published artifacts, package names, pinned
    versions, and hook privileges must be checked before installation.
  - Skill directories and marketplace rankings are discovery aids only. Directory rank, stars, or
    install count can identify candidates, but cannot justify installation without source and
    behavior review.

Primary sources checked:

- Codex Skills/MCP/Plugins/Hooks manual sections: https://developers.openai.com/codex/skills,
  https://developers.openai.com/codex/mcp, https://developers.openai.com/codex/plugins,
  https://developers.openai.com/codex/plugins/build, https://developers.openai.com/codex/hooks
- Supermemory: https://github.com/supermemoryai/supermemory and
  https://supermemory.ai/docs/supermemory-mcp/mcp
- Mem0 Codex integration: https://docs.mem0.ai/integrations/codex
- Basic Memory Codex integration: https://docs.basicmemory.com/integrations/codex
- Spellbook retrospective/fluent:
  https://github.com/majiayu000/spellbook/tree/main/skills/codex-retrospective and
  https://github.com/majiayu000/spellbook/tree/main/skills/codex-fluent
- Claude Code self-improving loop:
  https://zenn.dev/sonicgarden/articles/claude-code-self-improving-loop
- Reflective Prompt Tuning: https://arxiv.org/abs/2605.21781
- SkillOpt and SkillOpt-Sleep: https://github.com/microsoft/SkillOpt and
  https://arxiv.org/html/2605.23904v2
- EvoSkill: https://github.com/sentient-agi/EvoSkill
- GEPA/TextGrad/Trace2Skill references:
  https://github.com/gepa-ai/gepa, https://github.com/zou-group/textgrad,
  https://github.com/Qwen-Applications/Trace2Skill
- Community/deep-dive follow-up references:
  https://www.reddit.com/r/OpenaiCodex/comments/1tq4hjb/codex_memory_across_sessions_i_extracted_hermes/,
  https://www.reddit.com/r/OpenaiCodex/comments/1nvce9p/gpt5codex_is_game_changer_with_memory_mcp/,
  https://github.com/RedPlanetHQ/core, https://automem.ai/,
  https://memories.sh/docs/mcp-server, https://alphaonedev.github.io/codex-memory/,
  https://memoryoss.com/, https://www.recall.works/,
  https://github.com/huahuadeliaoliao/long-long-run,
  https://arxiv.org/abs/2605.27760, https://arxiv.org/abs/2605.15215,
  https://openai.com/index/codex-for-every-role-tool-workflow/,
  https://help.openai.com/en/articles/20001256-plugins-in-codex/,
  https://github.com/rohitg00/agentmemory,
  https://www.reddit.com/r/codex/comments/1tyxkzj/how_i_cut_codex_token_use_from_138mday_to_20mday/,
  https://thehackernews.com/2026/06/openai-codex-authentication-tokens.html

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

### 2026-06-08: Retrieval Policy Detail Archived From Active V2

These notes were moved from `docs/memory-pipeline-v2.md` so the active architecture source keeps
only the current operational policy. Read this section only when changing retrieval policy details,
provider-lane strategy, OCR/media routing, or route/eval promotion criteria.

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

Text embedding execution stages are explicit:

- `technical_canary`: a small provider/API, output-dimension, DB persistence, coverage, and budget
  guard check. This is the default meaning of `--limit 1/10/100` when no stage is specified. It is
  not an index-quality claim.
- `eval_slice`: a bounded provider/profile comparison slice. It should use a stable representative
  selection policy such as doc-type round robin. It is not a production index.
- `production_scope`: the selected provider/profile scope intended for real search coverage. A
  production-scope build must not be silently limited by an arbitrary `--limit`; route-specific
  production arms cover their route-specific document scope, not just a smoke-test prefix.

This differs from OCR. OCR remains per-media evidence preparation and can be selective in production
because many media items do not need text extraction. Text embedding, once an arm is adopted for a
scope, must index that whole scope.

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

- implemented baseline: `baseline_hybrid_foundation` with FTS, LIKE, metadata, retrieval-text FTS,
  semantic when explicitly configured, exact-anchor visibility, relation expansion, RRF metadata,
  and source-bundle restoration;
- workflow-first next candidates: `corpus2skill_navigation`, `bounded_workflow_orchestration`,
  source-bundle restoration, and route-gated portfolio selection;
- implemented non-evidence retrieval projection: `contextual_bm25` through
  `RetrievalTextProfile` rows and FTS, with source-hash and citation-exclusion audit;
- high-value candidate stage: `rerank_stage`;
- implemented audit gates: `claim_citation_verification` and `freshness_lineage`;
- real API embedding recall arms are role-specific, not one generic text bucket:
  `embedding_general_memory`, `embedding_jp_multilingual`, `embedding_learning_long`,
  `embedding_contextual_learning`, `embedding_code_technical`, and
  `embedding_media_text_bridge`;
- rerank arms: Voyage `rerank-2.5`, Cohere `rerank-v4.0-pro` /
  `rerank-v4.0-fast`, and Jina `jina-reranker-v3`, always after source-bundle restoration and
  never as a first-stage source of truth;
- reader/OCR/media arms: Jina Reader for URL/PDF extraction; Mistral `mistral-ocr-2512` as the
  fixed OCR eval candidate; Mistral `mistral-ocr-latest` only as an explicit alias-tracking
  check, not the default production/eval model;
- Japanese/cross-lingual recall: route-gated challengers such as Voyage/Jina/Gemini;
- long-form learning and concept maps: route-gated challengers such as Voyage, OpenAI large,
  Jina, Corpus2Skill maps, topic threads, and relation expansion;
- code/API/repository material: `code_technical` challengers such as Mistral
  `codestral-embed-2505` and Voyage `voyage-code-3`, only for route-specific evals;
- media/OCR/caption routes: `media_text_bridge` challengers only after media docs expose
  citation-ready OCR, caption, alt text, or VLM text;
- Gemini text embedding uses `gemini-embedding-2` for runnable Gemini API text tests. It is
  confirmed as a Gemini API model, so `gemini-embedding-001` is legacy comparison only.
- Native Gemini Embedding 2 multimodal use is implemented through the separate
  `native_multimodal_media` contract, not `api_embedding_portfolio`. Vertex AI
  `multimodalembedding@001` remains a separate GCP auth/project/location reference.
- Voyage contextual chunks use `voyage-context-4` as the current candidate. Older
  `voyage-context-3` comparison rows are removed from the active catalog to avoid redundant
  provider lanes.
- Jina `jina-embeddings-v5-omni-small` can enter the text portfolio only as a text-only
  `media_text_bridge` candidate over OCR/caption/alt_text/VLM text. Native image/PDF URL or file
  ingestion remains a separate media evidence contract.
- OCR is not a recall arm. It is an evidence-preparation lane that turns image/PDF media into
  citation-ready text. Because all-media OCR can dominate cost, `api-lane-estimate` defaults to a
  stratified calibration scope and requires `--ocr-scope all` for full lower-bound pricing.
- API lane row names should match strategy candidate names where practical. If an estimate row needs
  an alias, the mapping must be clear in the row metadata or recommended plan so agents do not think
  a catalog candidate disappeared.
- Managed RAG systems such as OpenAI File Search and Gemini File Search are reference lanes only.
  They may compare UX and citation behavior but must not replace local raw X evidence, account
  ownership, or source-bundle restoration.
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

Objective-fit performance priority:

- The upper architecture is a constraint, not the scoring objective. The objective is performance:
  the correct, useful answer for the user's input with enough evidence and no unsupported claims.
  Quantitative metrics such as route recall, citation precision, answer usefulness, and abstention
  correctness are instruments for that objective, not the objective itself.
- Do not remove strong provider arms merely because a simpler local route exists. Keep strong arms
  as challengers, measure their contribution, and promote them when evals win.
- Do not run every strong arm by default merely because it might help. Choose arms by query route
  and answer objective, then expand only when evals or failure analysis show missing evidence.
- OCR should not be skipped for cost alone. Use native media recall and media-text retrieval to
  target OCR where it can improve media-grounded evidence, then expand OCR scope only when targeted
  OCR underperforms.
- `memory api-lane-estimate` exposes `objective_fit_router_baseline` as the first-pass plan and
  route expansions such as `jp_multilingual_route`, `learning_long_route`,
  `code_technical_route`, and `media_grounded_route`. It separates comparison/high-cost options
  such as older contextual embeddings, latest OCR alias tracking, and full OCR lower-bound pricing.

ObjectiveRoutePlan integration:

- The current single `WorkflowRoute` remains for compatibility, but the objective-fit path uses an
  `ObjectiveRoutePlan` with `primary_route`, `fallback_routes`, `must_run_guards`,
  `escalation_triggers`, `stop_conditions`, `budget_policy`, and `planned_provider_roles`.
- The router must not choose only one brittle route. It selects a primary route plus fallback routes
  and explicit escalation triggers.
- Current Evidence/Skill/Workflow is `candidate_a_current_baseline`: a strong default candidate,
  not an unquestioned final architecture.
- The router is not evidence. It is a policy/execution layer that decides which existing evidence
  components run first, which fallback arms may run, which escalation conditions are allowed, and
  where to stop.
- `ObjectiveRouteExecution` is the no-spend execution layer for this policy. It must call existing
  evidence components instead of replacing them:
  - `candidate_a_current_baseline` calls the existing bounded workflow without answer/provider
    calls;
  - `exact_metadata_social` calls local FTS/metadata/relation search and context creation;
  - `media_evidence` inspects restored media/OCR evidence and may escalate to local OCR estimate or
    existing stored OCR chunks, but does not create fake evidence implicitly;
  - `skill_map` and `graph_sensemaking` use existing derived documents/relations as navigation
    hints, not final evidence;
  - semantic, rerank, managed-RAG, external Web, and provider-backed agentic arms remain skipped
    while the no-quota provider freeze is active unless a local/fake implementation is explicitly
    selected.
- Route execution records a trace: selected route arm, fallback use, escalation triggers, stop
  condition, evidence counts, citation counts, and whether provider quota was skipped. This trace is
  an operational audit artifact, not evidence.
- Route examples:
  - `single_fact_conditioned`: primary `exact_metadata_social`, fallback
    `candidate_a_current_baseline` and `semantic_embedding_portfolio`;
  - `media_grounded`: primary `media_evidence`, fallback `exact_metadata_social`,
    `semantic_embedding_portfolio`, and `candidate_a_current_baseline`, escalation
    `ocr_quality_pipeline`;
  - `temporal_freshness`: primary `candidate_a_current_baseline`, fallback
    `external_web_context` and `bounded_agentic_workflow`;
  - `exploratory_map`: primary `skill_map`, fallback `graph_sensemaking` and
    `semantic_embedding_portfolio`.

QueryTransform and retrieval text policy:

- Query transforms are allowed when they improve recall or decomposition, but every transformed
  query must be recorded as a separate artifact with:
  - `parent_query_id`;
  - `transform_kind`;
  - generated text;
  - preserved anchors;
  - allowed routes;
  - drift flags;
  - `citation_excluded=true`.
- Retrieval-only text must not overwrite source text or context chunks. Store it under an explicit
  `retrieval_text_profile`, such as `raw_compact`, `contextual_bm25`, `learned_sparse`,
  `hypothetical_query`, or `doc_expansion`.
- HyDE text, query decomposition, RAG-Fusion variants, SPLADE/doc expansion terms, and contextual
  retrieval strings are search aids only. They may influence candidate discovery and route traces,
  but they cannot support answer claims directly.
- The current no-spend implementation stores deterministic `raw_compact` and `contextual_bm25`
  `RetrievalTextProfile` rows, mirrors them into an FTS projection, and exposes build/coverage
  commands. Search may use those rows as a retrieval arm, but citations must still point back to
  source bundles or context chunks.
- Retrieval-text audit should fail when a projection claims to be active/current/citation-ready
  while its source hash, citation-exclusion flag, or source document link is invalid. A missing
  optional projection is coverage debt, not source evidence failure.

Evaluation gate policy:

- Promotion is never decided by answer text alone. Evaluate at least these separable gates:
  - `route_eval`: did the route choose enough entry points and avoid unsafe narrowing?
  - `retrieval_eval`: did candidate arms retrieve the expected source bundles?
  - `context_eval`: did selected chunks contain relevant, non-noisy context?
  - `citation_eval`: does each claim cite the correct source/chunk/region?
  - `answer_eval`: is the answer useful and faithful to cited context?
  - `abstention_eval`: did the workflow refuse, defer, or ask for more context when evidence was
    absent, stale, contradictory, subjective, or underspecified?
- Failure analysis must separate retrieval failure, context selection failure, citation failure,
  answer-generation failure, and overconfident self-knowledge.
- Provider-based judges may be added only behind budget guard and calibration. A small human or
  deterministic validation set must remain the promotion reference when possible.

Personalization and exploration policy:

- A `user_model` is a ranking policy, not a fact source. Bookmark ownership, account history,
  implicit feedback, explicit feedback, profile cards, and active-learning labels can weight
  candidates, but must not become citations.
- Personalization should be route scoped. Known-item/refinding, subjective preference,
  exploratory learning, freshness check, and media-grounded routes may use different personal,
  neutral, diverse, and exploratory weights.
- Diversity and novelty may be explicit route goals, but should be evaluated separately from
  citation precision so exploratory results do not degrade grounded answers.

Projection and temporal operations policy:

- Search indexes, embeddings, sparse representations, retrieval text, Corpus2Skill maps, graph
  summaries, OCR chunks, and long-context layouts are projections over raw/source-bundle data.
- Projections must track source hashes, generation IDs, builder/template/provider versions,
  membership status, stale/tombstone/deferred state, and coverage.
- Backfills and rebuilds produce new projection generations. They must not rewrite past answer
  artifacts; past answers remain tied to the evidence and generation active at the time.
- Freshness and obsolescence are relations, not deletion. Prefer `newer_than`,
  `obsolete_candidate`, `supports`, `contradicts`, and temporal validity metadata over removing old
  evidence.

Local vector projection policy:

- Local vector indexes such as turbovec are acceleration projections, not evidence stores and not
  the source of truth. They may only return document/media identifiers that must be restored to
  source bundles before context, citation, answer, or eval use.
- The source of truth remains SQLite tables and local files: raw X data, `memory_documents`,
  `memory_embeddings`, media rows, relation rows, context chunks, and citation annotations.
- A local vector projection is valid only for one explicit embedding provider/model/dimension/
  profile/template scope. It must not mix vectors from different embedding spaces.
- Projection builds must use current `memory_embeddings` rows whose source and embedding text hashes
  still match `memory_documents`. Incomplete or stale scopes should fail before writing a usable
  projection.
- Projection membership must be recorded in `memory_projection_generations` and
  `memory_index_membership`, including stable artifact IDs, source hashes, backend name, bit width,
  index file path, and generation metadata.
- High-compression vector engines can broaden Codex's usable local memory by reducing RAM and search
  latency, but they do not solve evidence quality, query planning, OCR, labels, graph navigation,
  source quality, or claim support by themselves.
- Framework wrappers for young vector engines are optional convenience layers. Prefer direct
  projection contracts in this repository until duplicate-ID, upsert, and data-loss semantics are
  proven safe by local tests.

Security and source-sink policy:

- Retrieved tweet text, OCR text, external Web text, media-derived text, tool output, and generated
  retrieval text are untrusted data.
- Every chunk/tool call/provider request should carry trust boundary, taint flags, data
  classification, source visibility, account scope, and allowed sinks when the workflow can send or
  act on the data.
- The route planner must be driven by trusted user query, local configuration, and policy. Untrusted
  retrieved/OCR/external text must not directly choose tools, provider calls, writes, external
  fetches, or secret-adjacent operations.
- Prompt wrappers and provenance markers are useful, but not sufficient. Deterministic source-sink
  gates, allowlists, approval policy, and audit traces are the core defense.

OCR Evidence Quality Pipeline:

- OCR is the standard sub-workflow for `media_grounded` escalation, not a loose add-on.
- The current implementation target is no-spend completion: implement the local quality, region,
  routing, promotion, and test contracts without calling Mistral or any other provider. Provider OCR
  execution, including free-tier quota, remains blocked by the no-quota policy.
- The media route flow is:

```text
media_recall
  -> media_source_evidence
  -> media_quality_profile
  -> text_region_detection / crop contract
  -> engine_routing
  -> raw_ocr_storage
  -> confidence / quality gate
  -> second_pass when needed
  -> context_chunk + citation promotion
  -> media_content_evidence
```

- Initial OCR provider is Mistral `mistral-ocr-2512`; `fake` is the no-network test provider.
  Mistral docs use `mistral-ocr-latest` in examples, and community alias tables indicate it can
  point at `mistral-ocr-2512`, but alias movement is unsuitable for repeatable DB evidence evals.
  Therefore `2512` stays fixed by default and `latest` is only an explicit drift check.
  Qualitatively, Mistral OCR 3 is a practical document-OCR candidate, not an unusable experiment:
  official docs expose OCR, structured annotations, confidence scores, tables, and document QnA,
  and third-party/community reports treat it as a strong document parser. The production caveat is
  reliability and evidence granularity, not basic OCR capability. PDF/API paths can show intermittent
  service errors, and community reports still call out bbox/annotation limitations, so Mistral OCR
  must remain behind retry, fallback, confidence, bbox/region, and citation-promotion gates.
  PaddleOCR / PaddleOCR-VL / manga OCR remain optional local providers behind the same provider
  contract.
- Store raw OCR, corrected text, and caption/VLM text as separate profiles. Never overwrite raw OCR
  with normalized or LLM-corrected text.
- OCR source granularity is `media_id + page_index + region_index + bbox + source_image_hash`.
- `memory_context_chunks` and `memory_citation_annotations` are the promotion target. A media item
  becomes `media_content_evidence` only after OCR/caption/VLM text has been promoted into
  citation-ready chunks.
- OCR sampling is `stratified_calibration`, not a flat random 100. Default strata are
  `document_or_table`, `screenshot_or_ui`, `manga_or_vertical_text`,
  `general_japanese_image`, `alt_text_missing`, `media_recall_top_hit`, and
  `tweet_text_insufficient`.
- Full OCR remains explicit-only. Expand OCR scope only when targeted OCR fails answer-correctness
  evals for media-grounded questions.
- Local completion requirements while provider calls are frozen:
  - `ocr-estimate` must expose media quality flags, skipped reasons, strata, and engine routes
    without writing DB rows or calling providers.
  - Region detection must create citation-granular regions with `bbox`, `reading_order`,
    `region_hash`, and `source_image_hash`. The first local detector may use deterministic image
    heuristics and whole-media fallback; it must still persist region-level evidence.
  - Engine routing must classify `document_pdf_or_table`, `screenshot_or_ui_text`,
    `japanese_general_image`, `manga_or_vertical_text`, and `no_text_likely`.
  - Low confidence, empty OCR despite high text likelihood, direct media-query relevance, and
    important routes must be marked as second-pass candidates. The second-pass contract is local
    metadata and optional fake/local processing until provider quota is allowed.
  - `corrected_text` and caption/VLM text are separate profiles. Corrected text may be stored as a
    derived search helper, but raw OCR plus bbox citation remains the preferred answer evidence.
  - `ocr-promote-chunks` must be able to promote stored OCR rows into context chunks without
    rerunning OCR.
  - Local optional providers such as PaddleOCR/PaddleOCR-VL/manga OCR stay behind the same provider
    contract; adding their dependency or model execution is a separate local-provider step.

Media role and observation policy:

- Media processing starts from a local, no-spend role estimate before OCR. Roles are multi-label and
  include `photo_place_food`, `photo_product_object`, `photo_person_event`, `document_page`,
  `slide_or_presentation`, `screenshot_ui`, `code_or_error_screenshot`, `chart_or_graph`,
  `table_or_form`, `diagram_or_architecture`, `scientific_figure`, `map_or_location`,
  `meme_or_image_macro`, `manga_or_vertical_comic`, `illustration_or_art`,
  `decorative_or_reaction`, and `unknown_media`.
- Role estimates map to evidence actions: `none_source_only`, `caption_candidate`,
  `ocr_candidate`, `ocr_layout_candidate`, `chart_or_visual_reasoning_candidate`, and
  `hybrid_ocr_vlm_candidate`.
- Role estimates are stored as `memory_visual_recall_evidence.evidence_level =
  media_role_profile` with `citation_ready = 0`; they are routing annotations only.
- Candidate-set OCR is the default orchestration target. Objective execution may OCR only the
  restored candidate media IDs for the current route, not the whole media corpus. Full OCR remains
  explicit-only and must be justified by media-grounded eval failures.
- Codex or VLM observations are stored as `memory_ocr_texts.text_profile = codex_observation` or
  `vlm_caption` with `evidence_status = inference`. They preserve raw observation text,
  provider/model/session metadata, prompt or user intent when available, and source image hash.
- `raw_ocr` chunks can support image text claims as facts. `caption`, `vlm_caption`,
  `codex_observation`, and corrected OCR profiles support search helpers or inference only unless a
  later review explicitly promotes them under a stronger evidence contract.
