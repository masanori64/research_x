---
name: research-x-memory-workflow
description: "Use when implementing or reviewing research_x memory-search pipeline work: Evidence/Source Bundle First, ObjectiveRoutePolicy, source restoration, context chunks, citations, API lanes, OCR/media, evals, workflow traces, app observability, retrieval strategy, or AI-callable local search."
---

# research-x Memory Workflow

Use this skill for memory-search architecture or implementation work.
`basic-memory-cli` handles the user's separate Basic Memory knowledge base; this skill governs the
`research_x` X evidence pipeline and citation-ready memory workflow.
For AI-callable local search, evidence review, or retrieval-quality outputs, also apply
`../../skill-references/evidence-workflow-quality-contract.md` before promoting results to answers
or durable decisions.

## Source Files

- Read `docs/memory-pipeline-v2.md` for current architecture.
- Read `PROJECT.md` for current milestone state and gates.
- Read `README.md` only when public command surface or user-facing usage changes.

## Invariants

- Evidence / Source Bundle first.
- ObjectiveRoutePolicy controls routes; it is not evidence.
- Generated labels, summaries, query transforms, media roles, observations, and scores are hints
  until promoted through evidence contracts.
- `raw source != searchable document != search result != context chunk != citation != answer`.
- Real provider APIs are gated by no-quota freeze and API Budget Guard.
- Diagnostic `local_hash` embeddings are wiring checks only.

## Workflow

1. Update the relevant Markdown source of truth before code when changing architecture.
2. Keep source-bundle restoration central: every retrieval arm must return to tweet, quote, media,
   author, bookmark account, URL, relation, time, and source hash where applicable.
3. Preserve no-spend/fake-first verification unless the user explicitly lifts the provider freeze.
4. Expose hidden run state through CLI/app traces when the user reports black-box behavior.
5. Verify with explicit `uv` commands and commit/push scoped changes.

## Harness And Retrieval Portfolio Eval

- Treat retrieval arms as candidates until eval shows source-bundle restoration and citation
  integrity.
- Portfolio eval must report restoration rate, unsupported context chunks, route gaps, and
  provider-gated lanes separately.
- Harness changes must expose route decisions and failure modes through traceable CLI/app surfaces.

## Contradiction, Forgetting, And Profile Governance

- Inferred profile, preference, or memory-governance facts require source references.
- Contradictions must keep both source bundles; do not silently overwrite one with another.
- Forgetting must distinguish raw source, derived document, search projection, context chunk, and
  tombstone policy.
- Hosted or cross-project memory runtimes are architecture references only unless a separate privacy
  and provider gate approves them.

## Handoffs

- From `research-x-research-intake`: accept only candidates with provenance, risk flags, and a
  source-bundle restoration path.
- To global `context-budget`: pass source pointers, hashes, trace paths, and evidence-critical
  items that must not be destructively compressed; keep runtime offload behavior in
  `ContextBudgetPolicy`.
- To `research-x-prompt-contract`: require explicit source-bundle, provider, allowed-tool, and
  forbidden-tool constraints for memory prompts.
- To global `research-x-publishing-illustration`: provide claim/source maps only; generated visuals
  are output artifacts, not evidence.
