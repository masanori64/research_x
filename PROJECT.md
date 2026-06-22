# Memory Search Project Plan

This file is the short implementation tracker for the memory-search branch.

Detailed architecture source:

```text
docs/memory-pipeline-v2.md
```

Do not duplicate detailed architecture here. Keep this file small enough that an agent can quickly
see what is implemented, what is gated, and what comes next.

## Documentation Boundary

- `AGENTS.md`: always-read agent rules, command policy, completion notification, publish policy.
- `README.codex.md`: compact Codex-facing repository reference. Use this for routine agent
  orientation instead of `README.md`.
- `README.md`: human/GitHub repository entry point only.
- `PROJECT.md`: short memory-search milestone tracker.
- `docs/memory-pipeline-v2.md`: detailed source of truth for the AI-callable evidence pipeline.
- `docs/memory-pipeline-archive.md`: indexed historical decision archive; inspect targeted sections
  only when prior research is needed.
- `docs/pipeline.md`: acquisition/auth/provider pipeline details.
- `.agents/skills`: repo-scoped Codex workflow playbooks. Skills hold repeatable procedures that
  would otherwise bloat `AGENTS.md`; they are not memory-architecture source files.

Do not add new memory-architecture Markdown files unless the user explicitly asks.

Cross-PC workspace policy: the desktop is the canonical `research_x` machine. Use VS Code Remote
SSH from other PCs; no repo Skill owns PC-to-PC local-state sync or migration.

Current repo skills:

- `research-x-skillization-intake`: route new recurring Codex behavior to the right instruction
  surface.
- `research-x-decision-loop`: detailed research, review, audit, and loop-stop mechanics.
- `research-x-doc-governance`: Markdown placement, archival, and drift checks.
- `research-x-goal-runner`: long goal phase loop and oversight gates.
- `research-x-memory-workflow`: memory-search architecture and implementation invariants.
- `research-x-observability-review`: app/CLI/workflow state visibility review.
- `research-x-parallel-review`: sub-agent role design and integration when permitted or required
  for exploration.
- `research-x-provider-gate`: no-quota and provider-facing lane checks.
- `research-x-implementation-plan-flow`: converts broad GPT/X/source-candidate reviews into gated,
  local-first implementation priority flows.

## Goal

Build a local, user-specific search tool over the existing X collection DB. The tool should let an
AI agent search accumulated X bookmarks/tweets like a local web-research tool while preserving
provenance, account-specific bookmark ownership, quote/media context, and the user's subjective
interests.

Current top-level direction:

- Evidence / Source Bundle first.
- ObjectiveRoutePolicy chooses primary, fallback, and escalation routes; it is not evidence.
- Real API embeddings, rerankers, OCR, Reader, and managed-RAG are provider arms behind gates, not
  the system objective.
- Corpus2Skill is a navigation map and route hint, not citation-ready evidence.
- Generated labels, summaries, query transforms, media roles, and observations are derived hints
  unless promoted through explicit evidence contracts.

Core invariant:

```text
raw source != searchable document != search result != context chunk != citation != answer
```

## Current Canonical Data

Raw acquisition data remains canonical and must not be replaced by summaries or generated answers:

- `tweets`
- `account_bookmarks`
- `collection_items`
- `tweet_edges`
- `media`
- `raw_payloads`
- `ai_labels`
- `accounts`
- `provider_runs`

## No-Spend Foundation V1

Pinned on 2026-06-10. Current foundation is complete through the no-spend/provider-gated boundary:

- canonical X store, normalized memory documents, derived cards, relations, and source bundles;
- search/evidence/context/citation/answer/workflow/eval surfaces;
- external discovery, Reader, LLM-context, rerank, embedding, OCR/media, and managed-reference
  contracts behind fake/local or provider gates;
- dry-run research intake with InterestProfile/SourceRegistry TOML, normalized candidates,
  metadata-only snapshots, deterministic scoring, ResearchBrief generation, and no-provider tests;
- ObjectiveRoutePolicy execution traces, research-control artifacts, projection lineage, API budget
  guard, strict audit, and pytest diagnostics;
- ContextBudgetPolicy/offload pointers for context/workflow/answer JSON outputs without mutating
  stored chunks, citation anchors, or answer inputs;
- source-backed memory governance for profile, contradiction, retention, forgetting, and tombstone
  records, with active tombstone suppression and restore visibility tests;
- PromptContract/MNP deterministic checks for read-only routing, allowed/forbidden tool boundaries,
  write-intent rejection, and direct tool/endpoint id detection.

Do not reopen these foundation phases unless a verification step finds a regression. New work should
be classified as future local hardening, provider-gated expansion, local-dependency execution, or a
separate Codex foundation task before implementation starts.

Use `docs/memory-pipeline-v2.md` for architecture detail and `uv run python -m research_x memory
--help` for the current command surface.

## Completed Milestones

- [x] V2 evidence objects, source-bundle restoration, context chunks, citations, answers, workflows,
      feedback, evals, and audit checks over the canonical X store.
- [x] Evidence/Skill/Workflow alignment: embeddings, Corpus2Skill, graph summaries, labels, query
      transforms, and VLM observations are route hints or recall arms, not source truth.
- [x] Provider-lane preflight and API Budget Guard: provider roles, offline estimates, price
      catalog, usage ledger, kill switch, app/CLI monitor, and no-quota freeze.
- [x] Objective-fit media evidence: media embeddings, OCR quality/evidence contracts, media roles,
      candidate-set OCR, and Codex/VLM observations as inference annotations.
- [x] Final skeleton execution surface: ObjectiveRoutePlan, no-spend route execution,
      research-control artifacts, projection lineage, trust boundaries, and final preflight.
- [x] Native Codex Skill metadata for recurring research_x workflows without a project-local
      prompt-routing layer.
- [x] Codex inbox design placement: implemented vs residual design from `_codex_inbox` is mapped to
      `docs/memory-pipeline-v2.md`, `docs/pipeline.md`, and the decision archive without new
      AGENTS.md, Skill, or code surfaces.
- [x] Skill/source manifest lock: `.codex/skill_manifest.lock` and
      `.codex/vendor_sources.lock.md` record enabled repo-local Skills and disabled third-party
      source candidates, with validation coverage.
- [x] ImprovementSignal pipeline: local-only capture, deterministic triage, proposal-only candidate
      reports, replay/qualifier/human-decision fields, rejected buffer, schema, and validation tests
      without provider calls.

## Current Gates

### Pre-API Local Preflight

Updated on 2026-06-12. No real provider API calls were made.

- `c697b60 Fix local memory preflight checks`: fixed local retrieval-text/FTS rebuild and
  coverage checks plus offline API lane estimate stability. Real DB local preflight reached
  `retrieval-text-coverage` full coverage and `memory audit --strict` only reports the expected
  provider-embedding gap.
- `514a31d Fix memory eval preflight routing`: fixed real-DB eval route/query gaps for
  contradiction, media+quote, and broad DB topic-map queries. `memory eval --strict` now passes all
  built-in cases with `--answer-provider none`.
- `memory portfolio-eval` now has `--case-limit` and `--fast` for bounded offline preflight before
  configuring provider candidate arms.
- Provider-cost preflight now includes wired external-search/LLM-context unit costs
  (`serper_external_search`, `brave_llm_context`) plus reference rows for OpenAI Web/File Search and
  Gemini Google Search/File Search so those waiting lanes are visible before any API quota is
  enabled. Model-dependent answer/classifier/relation-judge costs still require an explicit
  provider/model price row before real execution.
- 2026-06-14 provider research is captured in `docs/memory-pipeline-v2.md`: free-tier provider use
  is still quota use, local/open alternatives are the no-provider baseline, and paid lanes are most
  likely to matter for broad fresh Web discovery, anti-bot/dynamic extraction, complex OCR/VLM, and
  hard judge/answer tasks. No real provider APIs were called during the review.

Next API-facing step remains gated: run offline estimate/status first, then review the projected
cost and smallest useful scoped provider run before lifting the no-quota freeze.

### Provider-Quota Gate

Do not run real provider API calls while the no-quota freeze is active. This includes paid usage,
free-tier usage, trial credits, and zero-dollar quota consumption.

Blocked until explicitly lifted in the current conversation:

- real text embedding builds;
- real native media embedding builds;
- real reranker calls;
- real Reader/Jina extraction calls;
- real OCR calls;
- real classifier, answer, relation judge, external-search, LLM-context, or managed-RAG calls.

Before the first provider call after the freeze is lifted:

1. run `memory api-budget status`;
2. run `memory api-lane-estimate`;
3. review estimated cost, coverage, price source, provider/model/profile, and smallest useful
   limit;
4. start with the smallest scoped build or eval, then expand only after coverage is correct.

### Local-Dependency Gate

These are not hidden future work, but they require explicit local dependency/model decisions:

- PaddleOCR / PaddleOCR-VL / manga OCR local providers;
- local or OpenAI-compatible Qwen embedding/rerank endpoints;
- running the OSS Corpus2Skill compiler over exported bundles.

The provider contracts and export boundaries exist; dependency installation and model execution are
separate gated steps.

## Post-V1 Work Boundaries

Completed no-spend closure state:

- strategy catalog statuses are classified as implemented/candidate, oversight gate, or
  reference-only;
- strict audit exposes hidden no-spend gaps if new `needs_*` statuses are introduced;
- exact-anchor, relation, and retrieval-text arms are visible in portfolio/eval;
- lexical_exploration is visible as a direct-corpus portfolio arm, with denoising metrics for
  candidate count, filtered count, citation-ready yield, and unsupported context;
- deterministic claim/citation and freshness/projection lineage checks are part of audit.
- dry-run research intake is implemented for manual URL, local note, and fake search sources.
- ContextBudgetPolicy/offload pointers are implemented for context/workflow/answer JSON outputs
  without mutating stored context chunks or citation anchors.
- Source-backed memory governance is implemented for profile, contradiction, retention, forgetting,
  and tombstone records; active tombstones suppress matching local memory search artifacts.
- PromptContract/MNP deterministic checks are implemented for read-only routing and
  allowed/forbidden tool boundaries without LLM/provider validation.

Future local hardening:

- budget/offload coverage for additional bulky tool outputs beyond context/workflow/answer JSON;
- CLI/app review polish for existing trace, governance, intake, and prompt-contract inspection
  surfaces when real use exposes missing visibility;
- additional deterministic evals over existing fake/local lanes when they protect a concrete
  regression.

Provider-gated expansion:

- real embedding, rerank, Reader, OCR, classifier, answer, relation judge, external-search,
  LLM-context, or managed-RAG calls;
- networked research intake beyond dry-run/manual/local/fake discovery;
- real-model PromptContract/MNP validation or Prompt-as-Server runtime behavior after provider,
  auth, DB-write, transaction, and source-restoration review.

Local-dependency execution:

- PaddleOCR/PaddleOCR-VL/manga OCR local providers;
- local or OpenAI-compatible Qwen embedding/rerank endpoints;
- OSS Corpus2Skill compiler execution over exported bundles.

Separate Codex foundation:

- Skill/source manifest review updates if third-party Skills or plugins are considered later;
- ImprovementSignal changes that affect global Codex behavior, AGENTS.md, repo Skills, plugins,
  hooks, MCP, or connector policy;
- cross-project personal memory, hosted memory sync, or global source-backed memory governance.

Do not implement hosted Supermemory sync, cross-project personal memory by default, proxy scraping
defaults, unofficial ChatGPT backend APIs, bulk Skill installs, or Prompt-as-Server as backend
replacement in this repo.

## Implementation Rules

- Use `uv run python ...`, `uv run pytest ...`, and
  `uv run ruff check src\research_x tests`.
- If pytest is slow or appears stuck, use `uv run python -m research_x test-diagnose ...` to
  isolate slow tests before changing behavior or dropping coverage.
- Update `docs/memory-pipeline-v2.md` before code when a design decision changes.
- Keep `PROJECT.md` as a tracker only; do not add research logs or detailed architecture here.
- Prefer SQLite tables and explicit contracts before adding frameworks.
- Never stage `.secrets/` or `runs/`.
- Commit and push completed scoped implementation work every time unless blocked by unrelated
  changes, unclear scope, PR creation, force-push, branch rewrites, or cross-repo writes.
