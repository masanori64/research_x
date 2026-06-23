<!-- Historical consultation capture. Active path: README.md, tools/wbs_viewer/projects/research-x-work-state.json, docs/pdg/*.pdg, and .codex/context_offloads/pointer-map.json. Not evidence; do not update as an active tracker. -->

# Phase Gate Report

Date: 2026-06-22

Status: current execution record for the X/GPT implementation-priority flow. This is a gate and
handoff report, not an architecture source of truth and not permission to install dependencies,
enable plugins/MCP/hooks, call providers, or promote third-party tools.

Primary plan:

- `.codex/chatgpt-control/x-url-analysis-20260622/implementation-priority-flow.md`

Routine context pointers:

- `PROJECT.md`
- `README.codex.md`
- `docs/memory-pipeline-v2.md`

## Gate Protocol

For every phase:

1. Re-read the current repo state, `PROJECT.md`, and the applicable repo Skill before changing the
   next surface.
2. Identify hard stop gates: provider/API calls, model downloads, dependency installs,
   plugin/MCP/hook enablement, third-party Skill installation, automatic Skill edits, and
   architecture promotion without source restoration.
3. Treat review findings, failing tests, weak gates, missing report fields, and Skill-boundary
   drift as `NO-GO`.
4. Repair locally, rerun targeted checks, then broaden verification when the surface is shared.
5. Record the `GO` or `NO-GO` reason before moving to the next phase.

## Current Phase Summary

| Phase | Plan item | Gate result | Next-phase decision |
|---|---|---|---|
| 1 | P1-A SkillAdaptor pattern into `ImprovementSignal` | GO after repair/verification | Proceeded to Phase 2 |
| 2 | P2-A OCC-RAG-shaped answerability fixtures | GO after verification | Proceeded to Phase 3 |
| 3 | P2-B Hanno/Bosun-shaped relevance/support fixtures | GO after verification | Proceeded to Phase 4 |
| 4 | P3-A SAAS stop-condition audit | GO after verification | Proceeded to Phase 5 |
| 5 | P3-B stale-observation context-policy eval | GO after verification | Proceeded to Phase 6 |
| 6 | P4-A Zvec benchmark stub | GO after provider-gate repair/verification | Proceeded to Phase 7 |
| 7 | P5-A Agentmemory source review | GO after raw-output correction and lock validation | Proceeded to Phase 8 gate |
| 8 | P6 renderer/observability pattern | NO-GO for implementation; gate complete | Stop this flow until a concrete gap appears |

## Phase 1: ImprovementSignal Qualifier Fields

Plan item: P1-A SkillAdaptor pattern into `ImprovementSignal`.

Owner surfaces:

- `src/research_x/codex_improvement/pipeline.py`
- `src/research_x/codex_improvement/cli.py`
- `prompt_contracts/research_x_improvement_triage_v1.yaml`
- `tests/test_codex_improvement.py`
- `PROJECT.md`

Commit: `61e04d8 Add ImprovementSignal qualifier fields`

NO-GO checks applied:

- Do not install or import SkillAdaptor.
- Do not auto-edit repo Skills or global Codex behavior.
- Do not allow generated improvement records to bypass replay, qualifier, or human decision fields.
- Do not accept invalid replay/qualifier/human-decision statuses.

Repair loop:

- Added explicit proposal-only fields: `fault_step`, `responsible_artifact`,
  `candidate_diff_ref`, `replay_result`, `qualifier_result`, and `human_decision`.
- Added validation and tests rejecting invalid replay/qualifier/human decision values.
- Kept candidate reports and CLI output as review artifacts, not an auto-apply path.

Verification evidence:

- `tests/test_codex_improvement.py::test_qualifier_fields_roundtrip_into_triage_and_candidate_report`
- `tests/test_codex_improvement.py::test_invalid_qualifier_fields_are_rejected`
- Full `uv run ruff check src\research_x tests` and `uv run pytest` passed before phase commit.

GO decision:

- GO was issued because the phase added only local proposal/validation/report surfaces and preserved
  the no-auto-apply boundary.

## Phase 2: Answerability Fixture Lane

Plan item: P2-A OCC-RAG-shaped answerability fixtures.

Owner surfaces:

- `src/research_x/memory/answer.py`
- `src/research_x/memory/evals.py`
- `src/research_x/memory/workflow.py`
- `tests/test_memory.py`
- `docs/memory-pipeline-v2.md`
- `PROJECT.md`

Commit: `4492013 Add memory answerability fixtures`

NO-GO checks applied:

- Do not download or run OCC-RAG or any reader model.
- Do not treat generated answer text as evidence.
- Do not merge answerability into retrieval success; it must remain a separate status.
- Do not hide unanswerable or conflicting evidence behind successful command exits.

Repair loop:

- Added `AnswerabilityAssessment` and answerable, unanswerable, and conflicting local fixtures.
- Added `MemoryAnswer.structured["answerability"]` and eval/workflow fields separate from answer
  status and retrieval status.
- Ensured unanswerable/conflicting cases return `needs_review` behavior instead of false certainty.

Verification evidence:

- `tests/test_memory.py::test_memory_answer_records_answerability_fixture_outcomes`
- Eval route assertions for `answerability_status` in `tests/test_memory.py`
- Full `uv run ruff check src\research_x tests` and `uv run pytest` passed before phase commit.

GO decision:

- GO was issued because answerability became a local/fake acceptance gate without model download,
  provider usage, or evidence-boundary collapse.

## Phase 3: Relevance And Support Fixture Lane

Plan item: P2-B Hanno-Lab Bosun-shaped relevance/support fixtures.

Owner surfaces:

- `src/research_x/memory/relevance.py`
- `tests/test_memory.py`
- `docs/memory-pipeline-v2.md`
- `PROJECT.md`

Commit: `d251aaa Add local relevance fixture gate`

NO-GO checks applied:

- Do not download or run Bosun or any local relevance model.
- Do not name the interface after one candidate model before local fixture value is proven.
- Do not conflate relevance, duplicate, conflict, and claim-support labels.

Repair loop:

- Added deterministic `local_judge_candidate` as the generic baseline slot.
- Added fixture classes for relevant, irrelevant, duplicate, conflict, supports-claim, and
  does-not-support-claim cases.
- Added rejection behavior for unknown fixture labels.

Verification evidence:

- `tests/test_memory.py::test_memory_relevance_support_fixture_lane_is_deterministic`
- `tests/test_memory.py::test_memory_relevance_fixture_rejects_unknown_labels`
- Full `uv run ruff check src\research_x tests` and `uv run pytest` passed before phase commit.

GO decision:

- GO was issued because the phase produced a deterministic local baseline and kept model adoption
  behind a later dependency/source review.

## Phase 4: Stop-Condition Audit

Plan item: P3-A SAAS-style stop-condition audit.

Owner surfaces:

- `src/research_x/memory/workflow.py`
- `src/research_x/memory/evals.py`
- `tests/test_memory.py`
- `docs/memory-pipeline-v2.md`
- `PROJECT.md`

Commit: `4c34450 Add workflow stop condition audit`

NO-GO checks applied:

- Do not import a full RL/search policy stack.
- Do not let redundant search after sufficient evidence remain invisible.
- Do not treat route success as sufficient when stop-condition metadata is missing.

Repair loop:

- Added `stop_condition_audit` metadata with `local_evidence_sufficient`,
  `searched_after_sufficient_evidence`, `redundant_search_count`, and `stop_reason`.
- Added workflow/eval formatting so redundant-search state is visible.
- Added tests for redundant search after sufficient local evidence.

Verification evidence:

- `tests/test_memory.py::test_memory_workflow_flags_redundant_search_after_sufficient_evidence`
- Eval result assertions for `searched_after_sufficient_evidence` and `redundant_search_count`
- Full `uv run ruff check src\research_x tests` and `uv run pytest` passed before phase commit.

GO decision:

- GO was issued because the phase added narrow route metrics, not a new policy runtime.

## Phase 5: Stale-Observation Context Policy Fixture

Plan item: P3-B stale observation masking route eval.

Owner surfaces:

- `src/research_x/memory/context_policy.py`
- `tests/test_memory.py`
- `docs/memory-pipeline-v2.md`
- `PROJECT.md`

Commit: `2c7d2b8 Add stale observation context policy fixture`

NO-GO checks applied:

- Do not enable global stale-observation masking.
- Do not treat masking as generally beneficial without route/model/retriever evidence.
- Do not drop full-history, summary, or offload variants from the comparison.

Repair loop:

- Added route-level variants: full history, summary history, offloaded history, and masked history.
- Set `global_masking_allowed=False`; masked output remains only a route-specific candidate.
- Added fixture report fields for citation-ready yield, unsupported context, and answer status.

Verification evidence:

- `tests/test_memory.py::test_route_context_policy_compares_stale_observation_variants`
- Full `uv run ruff check src\research_x tests` and `uv run pytest` passed before phase commit.

GO decision:

- GO was issued because masking remained an eval warning and did not become a global context policy.

## Phase Boundary Skill Routing Check

This is not one of the numbered implementation phases, but it is part of the requested phase-crossing
discipline.

Commit: `b18f714 Add phase-boundary skill routing check`

Purpose:

- Add explicit Skill Router Preflight guidance for boundary crossings such as router, gate, intake,
  evidence, execution, observability, and transformation groups.
- Require the next phase to re-check whether a newly relevant Skill or contract applies.

GO decision:

- GO was issued to continue the phase sequence because the repo now has an explicit boundary
  checkpoint in `README.codex.md` and `research-x-skillization-intake`.

## Phase 6: Zvec Benchmark Stub

Plan item: P4-A Zvec benchmark stub over existing local backends.

Owner surfaces:

- `src/research_x/memory/vector_projection.py`
- `src/research_x/cli.py`
- `tests/test_memory.py`
- `README.codex.md`
- `docs/memory-pipeline-v2.md`
- `PROJECT.md`

Commit: `ad96bc9 Add vector backend benchmark gate`

NO-GO checks applied:

- Do not install, import, or default to Zvec.
- Do not treat Zvec as a managed vector DB replacement.
- Do not run non-local query embeddings while the no-quota provider freeze is active.
- Do not omit required acceptance axes: build time, search time, cold start, recall, update/delete,
  disk footprint, memory footprint, and source restoration.

Repair loop:

- Initial benchmark implementation needed stronger phase-gate coverage for cold start, memory, and
  update/delete support. Added those fields to thresholds and reports.
- A side review identified that benchmark query embedding could call non-local providers if CLI
  choices allowed them. Repaired by limiting CLI benchmark provider choices to `local_hash` and
  returning `provider_gated` for non-local providers in the library path.
- Kept `zvec` in benchmark choices only as `dependency_review_required`; no import/install path was
  added.

Verification evidence:

- `tests/test_memory.py::test_memory_vector_backend_benchmark_gates_candidate_dependency`
- `tests/test_memory.py::test_memory_vector_backend_benchmark_blocks_non_local_provider`
- `tests/test_memory.py::test_memory_vector_backend_benchmark_cli_reports_candidate_gate`
- `uv run pytest tests\test_memory.py -k "vector_backend_benchmark or vector_projection_backend"`
- Full `uv run ruff check src\research_x tests` and `uv run pytest` passed before phase commit.

GO decision:

- GO was issued only after the provider gate repair and full verification. The phase ended with a
  benchmark skeleton and dependency-review gate, not backend adoption.

## Phase 7: Agentmemory Source Review

Plan item: P5-A Agentmemory source review.

Owner surfaces:

- `.codex/vendor_sources.lock.md`
- `.codex/skill_manifest.lock`
- `tests/skills/test_vendor_sources_lock.py`
- `.codex/chatgpt-control/x-url-analysis-20260622/implementation-priority-flow.md`
- `PROJECT.md`

Commit: `c01f7ad Lock agentmemory as disabled source candidate`

NO-GO checks applied:

- Do not install Agentmemory.
- Do not enable plugin, MCP, hook, local server, or Skill behavior.
- Do not treat a source-lock entry as permission to install or connect.
- Do not ignore GPT Pro raw/follow-up output when it already contains the candidate judgment.

Repair loop:

- Initial source review was leaning too much on live primary-source inspection and not enough on the
  captured GPT Pro raw/official project review material.
- After correction, re-read:
  - `.codex/chatgpt-control/x-url-analysis-20260622/chatgpt-visible-output.txt`
  - `.codex/chatgpt-control/x-url-analysis-20260622/chatgpt-opaque-deferred-followup.md`
  - `.codex/chatgpt-control/x-url-analysis-20260622/project-usability-review.md`
  - `.codex/chatgpt-control/x-url-analysis-20260622/current-decision-summary.md`
- Recorded Agentmemory as disabled/source-review-required with Apache-2.0 `v0.9.27` peeled commit
  `25158519d5d68b9060a97ba5bdcccc3e1aba6d79`.
- Captured blockers: plugin/MCP/hook enablement, prompt/tool-output capture, retention/deletion,
  redaction, version drift, provider/key surfaces, local server behavior, and overlap with Basic
  Memory/context handoff/planning files/research_x memory surfaces.

Verification evidence:

- `uv run python scripts\validate_skill_manifest.py`
- `uv run pytest tests\test_skill_manifest.py tests\skills\test_vendor_sources_lock.py`
- `tests/skills/test_vendor_sources_lock.py::test_agentmemory_is_pinned_but_disabled_until_hook_and_retention_review`
- Full `uv run ruff check src\research_x tests` and `uv run pytest` passed before phase commit.

GO decision:

- GO was issued to proceed to the Phase 8 gate because Agentmemory remained disabled, pinned,
  documented, and covered by lock tests. No install or enablement occurred.

## Phase 8: Renderer And Observability Pattern Gate

Plan item: P6 renderer/observability pattern only if a concrete UI/report gap appears.

Owner surfaces if this later becomes active:

- A project-owned schema and deterministic renderer, not a third-party plugin first.
- Relevant observability or output tests.
- `PROJECT.md` and `docs/memory-pipeline-v2.md` only if an accepted design change occurs.

Current decision: NO-GO for implementation.

NO-GO checks applied:

- No concrete UI/report/trace gap was found during phases 1-7.
- Existing workflow/eval/context/source-lock surfaces were sufficient for the implemented gates.
- Archify, pdgkit, YAML-to-HTML plugins, and WBS tools remain reference/local-pattern candidates,
  not install or MCP candidates.
- Generated diagrams or renderers are not evidence.

Repair loop:

- No code repair was needed because this was a gate decision, not a failed implementation.
- The correct action was to stop this flow at the gate and leave the promotion condition explicit.

Verification evidence:

- `.codex/chatgpt-control/x-url-analysis-20260622/implementation-priority-flow.md` states P6 should
  run only after a concrete observability or artifact problem appears.
- `PROJECT.md` future local hardening keeps CLI/app review polish conditional on real missing
  visibility.
- Full repo checks passed after phases 6 and 7, so there is no uncovered implementation failure
  requiring a renderer.

NO-GO decision:

- No go sign was issued for renderer implementation. This is the intended Phase 8 outcome until a
  user or local workflow exposes a concrete observability/output gap.

End-of-flow decision:

- GO to stop this implementation flow here.
- Next work must start from a new concrete gap, provider/dependency gate, or user-requested phase.
- Residual 35-item handling after this stop decision is recorded in
  `.codex/chatgpt-control/x-url-analysis-20260622/current-decision-summary.md`.

## Latest Verification Snapshot

Most recent verification before this report:

- `uv run ruff check src\research_x tests`
- `uv run pytest`
- `uv run python scripts\validate_skill_manifest.py`
- `uv run pytest tests\test_skill_manifest.py tests\skills\test_vendor_sources_lock.py`
- `git diff --check`

Most recent pushed commits for this flow:

- `61e04d8 Add ImprovementSignal qualifier fields`
- `4492013 Add memory answerability fixtures`
- `d251aaa Add local relevance fixture gate`
- `b18f714 Add phase-boundary skill routing check`
- `4c34450 Add workflow stop condition audit`
- `2c7d2b8 Add stale observation context policy fixture`
- `ad96bc9 Add vector backend benchmark gate`
- `c01f7ad Lock agentmemory as disabled source candidate`

## Resume Instructions For Future Codex

Before continuing this flow:

1. Read this file, `implementation-priority-flow.md`, `PROJECT.md`, `README.codex.md`, and the
   applicable repo Skill.
2. Do not reopen phases 1-7 unless a regression, failed test, or source drift contradicts this
   report.
3. Do not implement Phase 8 unless there is a concrete observability/output gap. If one appears,
   start with a project-owned schema, deterministic local renderer, validation/golden tests, and
   source/evidence separation.
4. For any new phase, append a new gate section here before moving on. Include:
   - plan item;
   - owner surfaces;
   - no-go checks;
   - repair loop;
   - verification evidence;
   - go/no-go decision;
   - next-phase rationale.
5. Keep provider calls, model downloads, dependency installs, plugin/MCP/hook enablement,
   third-party Skill installation, and automatic Skill edits behind explicit gates.
