# research_x Current Savepoint

Purpose: quick reread for Codex and the user. This file summarizes the current completed and
unfinished state by implementation workflow so the project status does not have to be reconstructed
from scratch every time.

This is not the source of truth. If this conflicts with the owning docs, use the owning docs.

- Baseline pinned tag: `savepoint/no-spend-v1-20260617-pipeline`
- Branch: `codex/context-and-design-import-20260609`
- Current overlay: X/GPT source-candidate Phase 1-8 gates have been executed locally; residual
  candidate handling is recorded in the X/GPT decision summary.
- Update trigger: git milestone, project requirements milestone, provider gate decision, local
  dependency adoption, or a clear change to completion/gate status.
- Maintenance rule: replace this file at a milestone; do not append session history.

## Source Pointers

- `PROJECT.md`: completed milestones, current gates, post-v1 boundaries.
- `docs/memory-pipeline-v2.md`: active memory/search architecture and post-v1 implementation
  boundaries.
- `docs/memory-pipeline-archive.md`: historical decisions and implemented/residual split index.
- `docs/pipeline.md`: X acquisition, auth, provider, and external intake boundaries.
- `README.codex.md`: compact Codex orientation and command surface.
- `.codex/chatgpt-control/x-url-analysis-20260622/phase-gate-report.md`: local execution record
  for the first X/GPT source-candidate wave.
- `.codex/chatgpt-control/x-url-analysis-20260622/current-decision-summary.md`: current 35-item
  residual decision and second-wave candidate list.

## 0. Verification State

Baseline done:

- `uv run ruff check src\research_x tests` passed.
- `uv run pytest` passed with `273 passed`.
- Skill manifest checks passed.
- No tracked-file worktree diff at the baseline pinned savepoint.

Later local phase-gate done:

- X/GPT Phase 1-8 code-oriented gates were executed through local/fake-provider verification.
- First-wave verification reached `uv run pytest` with `284 passed`.
- Current residual handling is not a request to run provider/API calls or install dependencies.

Not done:

- No known v1 implementation stub remains. Remaining work is post-v1 gated work, not unfinished
  no-spend foundation work.

## 1. Core Architecture And Scope

Done:

- No-spend foundation v1 is pinned complete as of 2026-06-10.
- Current source of truth is `docs/memory-pipeline-v2.md`; historical detail is archived.
- The invariant is established: raw source, searchable document, search result, context chunk,
  citation, and answer are separate objects.

Not done:

- Do not reopen v1 unless verification finds a regression.
- New work must first be classified as future local hardening, provider-gated expansion,
  local-dependency execution, or separate Codex foundation work.

## 2. X Acquisition And Store

Done:

- X acquisition adapter chain, bookmark pipeline, quote edges, media preservation, shared SQLite
  store, account-aware session handling, and verified smoke expectations exist.
- `SessionBroker`, `auth auto`, and account-specific cookie/session paths are documented.

Not done:

- Proxy/Webshare defaults are rejected.
- New external fetch or provider-backed intake needs fetch policy, storage-rights notes,
  prompt-injection handling, and source restoration before evidence use.

## 3. Canonical Data And Source Bundles

Done:

- Canonical tables include `tweets`, `account_bookmarks`, `collection_items`, `tweet_edges`,
  `media`, `raw_payloads`, `ai_labels`, `accounts`, and `provider_runs`.
- Source-bundle restoration is part of the memory workflow boundary.

Not done:

- Physical deletion workflows are not part of v1. V1 suppresses active tombstones but does not
  rewrite source rows or prior citations.

## 4. Searchable Corpus And Local Retrieval

Done:

- `memory_documents`, derived cards, SQLite FTS, metadata/LIKE search, retrieval-text FTS,
  relation expansion, and local search commands are implemented.
- `local_hash` embeddings exist only as diagnostic wiring.

Not done:

- `local_hash` must not be promoted.
- Real semantic recall quality still requires real provider embeddings and route-level evals.

## 5. Evidence, Context, Citations, And Answers

Done:

- `memory evidence`, `memory context`, citation annotations, answer artifacts, and context chunks
  are implemented.
- Search results are separated from citation-ready context and answers.
- Unsupported context and citation misses remain visible instead of being hidden.

Not done:

- Semantic claim judging remains a provider or human gate.
- Generated answers are not source truth.

## 6. Objective Routes, Workflows, Eval, And Audit

Done:

- ObjectiveRoutePolicy, workflow traces, research-control artifacts, `memory workflow`,
  `memory objective-routes`, `memory objective-execute`, `memory eval`, `portfolio-eval`, preflight,
  and strict audit surfaces exist.
- Built-in no-provider eval/preflight issues were fixed before this savepoint.

Not done:

- Automatic workflow-triggered semantic portfolio expansion is not current behavior.
- Provider/profile arms remain explicit or strategy-gated until eval justifies promotion.

## 7. Retrieval Strategy, Portfolio, And Corpus2Skill

Done:

- `baseline_hybrid_foundation` is implemented.
- `contextual_bm25` exists as a non-evidence retrieval projection through RetrievalTextProfile and
  FTS.
- Claim/citation verification and freshness lineage are audit gates.
- Corpus2Skill export/navigation exists as an advisory map.

Not done:

- `rerank_stage` is a high-value candidate but remains behind provider/eval gates.
- Managed RAG is reference-only and must not replace local source bundles.
- Corpus2Skill is not citation-ready evidence.

## 8. Media, OCR, And Visual Evidence

Done:

- Media provenance, media evidence levels, media role estimates, OCR contracts, candidate-set OCR,
  fake/local OCR tests, and OCR estimate/promote surfaces exist.
- Native Gemini Embedding 2 media recall is separated from text embedding contracts.

Not done:

- Real Mistral OCR execution is blocked by the no-quota freeze.
- PaddleOCR, PaddleOCR-VL, manga OCR, and similar local providers require a local-dependency gate.
- Captions, VLM observations, and Codex observations are inference/search helpers unless promoted
  through an explicit evidence contract.
- Full OCR remains explicit-only.

## 9. Providers, API Budget, And External Search

Done:

- API Budget Guard, price catalog, usage ledger, kill switch, offline estimates, and provider-role
  boundaries exist.
- Serper, Brave LLM-context, OpenAI/Gemini reference rows, and provider-cost visibility are
  documented as gated lanes.
- No-quota freeze is active.

Not done:

- Real embeddings, native media embeddings, rerankers, Reader/Jina extraction, OCR, classifier,
  answer, relation judge, external search, LLM-context, and managed-RAG calls are not allowed.
- Free-tier, trial, and zero-dollar quota use is still provider quota and remains blocked.
- Before any provider call: run budget status, lane estimate, pricing review, smallest canary, and
  rollback/kill-switch review.

## 10. Research Intake And External Source Intake

Done:

- Dry-run research intake is implemented for InterestProfile, SourceRegistry, ResearchCandidate,
  metadata-only snapshots, deterministic scoring, and ResearchBrief artifacts.
- No-network-by-default tests exist.

Not done:

- Networked intake, URL fetch, Reader extraction, provider search, LLM summaries, and automatic
  evidence promotion are provider/policy gated.

## 11. Governance, Prompt Contracts, And Skills

Done:

- Source-backed memory governance exists for profile, contradiction, retention, forgetting, and
  tombstone records.
- PromptContract/MNP deterministic checks exist for local read-only routing and tool boundaries.
- Repo-local Skills, Skill/source manifest lock, vendor source lock, and ImprovementSignal pipeline
  exist.
- Savepoint routing is owned by `research-x-context-budget` plus `research-x-doc-governance`, not a
  new Skill.

Not done:

- Real-model PromptContract/MNP validation needs provider/security review.
- Prompt-as-Server runtime behavior is not adopted.
- Third-party Skill/plugin adoption remains separate security/governance work.

## 12. Codex And Environment Adjuncts

Done:

- Windows dev environment export/bootstrap scripts exist as Codex/environment adjunct work.
- Such environment logs are not memory pipeline completion criteria unless explicitly scoped.

Not done:

- Cross-project personal memory, hosted memory sync, and global source-backed governance are outside
  the research_x no-spend foundation v1 contract.

## 13. Explicit Non-Adoptions

Not adopted:

- Hosted Supermemory sync by default.
- Cross-project personal memory as part of v1.
- Proxy scraping defaults.
- Unofficial ChatGPT backend APIs.
- Bulk Skill catalog installs.
- Prompt-as-Server as backend replacement.

## Next Phase Order

1. Future local hardening only when a concrete regression or review gap appears.
2. Local-dependency execution only after explicit dependency/model decisions.
3. Provider-gated canaries only after the no-quota freeze is explicitly lifted and offline budget
   checks pass.
