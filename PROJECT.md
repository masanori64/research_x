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

Current repo skills:

- `research-x-skillization-intake`: route new recurring Codex behavior to the right instruction
  surface.
- `research-x-decision-loop`: detailed research, review, audit, and loop-stop mechanics.
- `research-x-doc-governance`: Markdown placement, archival, and drift checks.
- `research-x-goal-runner`: long goal phase loop and human-intervention gates.
- `research-x-memory-workflow`: memory-search architecture and implementation invariants.
- `research-x-observability-review`: app/CLI/workflow state visibility review.
- `research-x-parallel-review`: sub-agent role design and integration when permitted or required
  for exploration.
- `research-x-provider-gate`: no-quota and provider-facing lane checks.

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

## Implemented Foundation

Current foundation is implemented through the no-spend/provider-gated boundary:

- canonical X store, normalized memory documents, derived cards, relations, and source bundles;
- search/evidence/context/citation/answer/workflow/eval surfaces;
- external discovery, Reader, LLM-context, rerank, embedding, OCR/media, and managed-reference
  contracts behind fake/local or provider gates;
- ObjectiveRoutePolicy execution traces, research-control artifacts, projection lineage, API budget
  guard, strict audit, and pytest diagnostics.

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

## Current Gates

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

## Next Work

No-spend closure state:

- strategy catalog statuses are classified as implemented/candidate, human gate, or reference-only;
- strict audit exposes hidden no-spend gaps if new `needs_*` statuses are introduced;
- exact-anchor, relation, and retrieval-text arms are visible in portfolio/eval;
- deterministic claim/citation and freshness/projection lineage checks are part of audit.

Remaining gates:

- provider-quota gate: real embedding, rerank, Reader, OCR, classifier, answer, relation judge,
  external-search, LLM-context, or managed-RAG calls;
- local-dependency gate: PaddleOCR/PaddleOCR-VL/manga OCR, local Qwen-style endpoints, and OSS
  Corpus2Skill compiler execution.

Scoped no-spend residuals from the inbox design, before any provider work:

- ContextBudgetPolicy / offload-pointer contracts for long tool/search/workflow outputs;
- automated research-intake profiles, subscriptions, snapshots, scoring, and ResearchBrief
  artifacts, starting with dry-run or local/manual URL flows;
- proposal-only ImprovementSignal capture for recurring Codex failures, route misses, doc drift,
  provider-gate violations, and eval failures;
- source-backed profile, contradiction, tombstone, forgetting, and retention semantics;
- deterministic PromptContract/MNP tests for read-only routing and allowed/forbidden tools;
- Skill/source manifest review updates only if third-party Skills or plugins are considered later.

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
- Commit and push completed scoped implementation work unless blocked by unrelated changes.
