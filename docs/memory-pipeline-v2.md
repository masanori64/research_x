# AI-Callable Memory Search Pipeline V2

This is the active evidence-architecture contract for `research_x`.
It is not the work-state database, not the structural-flow database, and not a
historical research log.

## Executive Decision

Keep the current lower retrieval foundation:

- raw X acquisition tables as source of truth;
- `memory_documents` as rebuildable searchable projections;
- SQLite FTS, metadata, exact-anchor, relation, and local/fake routes;
- optional provider recall arms behind explicit gates;
- source-bundle restoration, context chunks, citations, answers, workflows, evals,
  audit checks, and feedback.

The final system is evidence-first, not vector-first, router-first, or diagram-first.
ObjectiveRoutePolicy chooses candidate routes, but it does not replace source
bundles, citation verification, answer abstention, workflow traces, or eval gates.

## Ownership Boundary

`research_x` is the canonical project for the AI-callable X memory-search tool,
not the canonical project for Codex self-improvement.

- `maasa/research_x` owns X acquisition state, source restoration, retrieval,
  context chunks, citations, answer boundaries, evals, workflow traces, provider
  gates, and local tool output contracts.
- `maasa/.codex` owns Codex-wide Skills, self-improvement, session memory,
  retrospectives, handoffs, Skill/Plugin/MCP governance, and external Codex
  foundation candidates.
- The bridge is intentionally narrow. Codex may pass a query, objective, context
  budget, and reviewed source candidate into `research_x`. `research_x` returns
  evidence status, citation-ready answer or abstention, provider-gated state, and
  audit trace.
- Codex transcripts, automatic Skill edit permission, provider execution
  permission, and root instructions are not inputs to the `research_x` evidence
  pipeline.

This split is not conservative minimalism. External candidates are kept alive by
adoption shape: `adopt`, `bridge`, `staging`, `provider_gated`, or `historical`.
Only paid/quota provider execution is a hard execution block. Hooks, MCP,
plugins, native dependencies, and local model candidates enter through isolated
staging, dry-run, dependency review, and manual promotion rather than permanent
rejection.

Boundary registry: `control/adoption_registry.toml`; validate with
`research-x adoption audit`. Codex-foundation ownership stays in `.codex`.

## Ideal Runtime Layers

`research_x` is organized as four runtime layers:

1. Source Layer: raw X tables, media, raw payloads, account/bookmark ownership,
   and external source candidates.
2. Evidence Layer: source bundles, context chunks, citation annotations, answer
   support, and source-backed governance records.
3. Retrieval/Eval Layer: FTS, metadata, relations, vector projections, OCR/media,
   rerank, answerability, relevance, stop-condition, and backend benchmark gates.
4. Tool Interface Layer: stable AI-callable JSON, CLI/API surfaces, observability,
   budget reporting, and audit traces.

The Tool Interface Layer must present a stable contract even when internal
workflow JSON changes. The current AI-callable output contract is implemented as
`research_x.tool_interface.memory_tool_contract` and exposes:

- `status`: `answer`, `abstain`, `needs_review`, `source_not_restored`,
  `citation_missing`, `provider_gated`, or `blocked`;
- `evidence_level`: `raw`, `candidate`, `source_bundle`, `context_chunk`, or
  `citation_ready`;
- `citations`: restore pointers back to context chunks and source IDs;
- `trace`: route, stop/skip reason, provider gate, budget state, eval warnings,
  and the narrow Codex bridge boundary.

## Core Invariant

```text
raw source != searchable document != search result != source bundle
!= context chunk != citation != answer
```

Every promoted object must be traceable backward to raw source state and forward to
the workflow, citation, or answer that used it.

## Evidence Layer Responsibilities

### Raw Sources

Raw source objects include `tweets`, `account_bookmarks`, `collection_items`,
`tweet_edges`, `media`, `raw_payloads`, `accounts`, provider run artifacts, and
saved local media when available. These are the provenance base.

### Searchable Documents

Searchable documents, retrieval text, embeddings, labels, summaries, OCR text, VLM
observations, query transforms, and index projections are rebuildable views or
candidate signals. They must keep source IDs, source hashes, projection generation,
stale/tombstone state, and restore paths.

### Search Results

Search results are candidates. Exact/FTS/metadata/relation/vector/media/provider
hits cannot support claims until they restore a source bundle.

### Source Bundles

A source bundle restores the tweet, quote relation, media relation, author,
bookmark account, URL, timestamp, source hash, and any relevant provider/run
metadata needed to evaluate provenance.

### Context Chunks

Context chunks are bounded answer inputs created from restored source bundles.
Unsupported chunks, stale projections, missing media provenance, or untrusted tool
text must be visible in workflow state and eval output.

### Citations

Citations annotate context chunks with source-backed support. Generated labels,
route scores, summaries, diagrams, pointer maps, compressed previews, and
consultation captures are not citations.

### Answers

Answer behavior is `answer`, `abstain`, `needs_review`, `citation_missing`,
`source_not_restored`, `provider_gated`, or `blocked` when support is incomplete.
Correct-looking text without citation-ready support is not a completed answer.

### Workflow Traces

Workflow traces expose route choice, fallback, provider skip, evidence level,
citation support, budget/offload state, OCR/media status, failure state, and stop
reason when a task depends on those states.

## Non-Evidence Control Artifacts

The following artifacts are control, planning, review, or restore-index surfaces:

- WBS JSON;
- generated diagram sources and rendered assets;
- screenshots;
- `C:/Users/maasa/.codex/foundation/context_offloads/research_x/pointer-map.json`;
- `C:/Users/maasa/.codex/route_memory/route-memory.json`;
- ChatGPT/GPT Pro consultation captures;
- sub-agent notes;
- compressed summaries and previews.

They may point to source material or explain workflow structure. They must not be
used as citation-ready evidence, answer support, source-quality evidence, or
permission to call providers.

## WBS / Presentation / Pointer Boundary

Work state belongs in `tools/wbs_viewer/projects/research-x-work-state.json`.
WBS owns only current Source, Evidence, Retrieval-Eval, and Tool Interface layer
work state: status, gates, owner surfaces, artifact pointers, stop conditions, and
next actions. It must not hold historical 35-item consultation lists, source-review
prose, candidate inventories, or Codex foundation tasks. Historical mixed WBS state
is archived outside the repo at
`C:/Users/maasa/.codex/foundation/work_state/research-x-pre-layer-wbs-archive-20260625.json`;
Codex foundation work state lives at
`C:/Users/maasa/.codex/foundation/work_state/research-x-codex-foundation-adjuncts.json`.

Presentation diagram and deck generation belongs to the D2 + Marp build-tool
boundary described in
`C:/Users/maasa/.codex/foundation/project_plans/research_x/2026-06-24-presentation-generation-flow.md`.

Deck-specific diagram sources should be derived from reviewed repository facts,
validated through the selected local D2 lane, and rendered only as
review/presentation assets. Route, state-machine, and implementation-boundary
truth should remain in code, tests, or the narrow owning Markdown section unless a
presentation artifact is explicitly being built.

Restore pointers belong in:

```text
C:/Users/maasa/.codex/foundation/context_offloads/research_x/pointer-map.json
```

Pointer entries must keep `pointer_id`, `artifact_path`, `sha256`, `char_count`,
`byte_count`, `restore_hint`, `artifact_kind`, `owner_plane`, and
`not_evidence: true`. Hash and size must match the current file before the pointer
is trusted for context restoration.

Operation route memory belongs in:

```text
C:/Users/maasa/.codex/route_memory/route-memory.json
```

Route Memory owns recurring operation-route fingerprints, positive and negative
triggers, canonical first actions, known failed routes, verification signals, and
local gates. It is a control-plane preflight input only. It must not be used as
provider/API approval, browser/ChatGPT approval, source evidence, citation support,
or permission to enable hooks, plugins, MCP servers, connectors, or installs.

## Route And Retrieval Contract

Candidate routes include exact anchors, FTS, metadata, relation expansion,
retrieval-text projections, semantic vectors, sparse/late-interaction/rerank
candidates, OCR/media preparation, Corpus2Skill navigation, graph/topic hints,
external Web candidates, and managed-reference candidates.

All route outputs remain candidates until restored into source bundles and checked
against citation/eval gates. Provider-backed, hosted, or model-dependent routes are
disabled unless the current conversation explicitly lifts the no-quota freeze and
the API Budget Guard passes.

## Provider / API Budget Gate

Real provider calls are blocked while the no-quota freeze is active, including
free-tier, trial-credit, and zero-dollar quota usage.

Blocked lanes include real embeddings, native media embeddings, rerankers, Reader
extraction, OCR, classifiers, answer engines, relation judges, external search,
LLM-context, managed RAG, and real-model prompt-contract validation.

Before the first approved provider call:

1. run `memory api-budget status`;
2. run the relevant offline estimate;
3. review price source, provider/model/profile, projected cost, coverage, and the
   smallest useful limit;
4. stop again before execution if pricing, quota, or budget evidence is unclear.

## ContextBudgetPolicy Boundary

Runtime ContextBudgetPolicy may offload large context/workflow/answer JSON outputs
to previews plus file pointers and hashes. It must not mutate stored context
chunks, citation anchors, answer inputs, or raw source state.

Context previews and offload pointers are retrieval aids, not source bundles,
citations, or answer evidence.

## Deletion / Rewrite Policy

- Do not delete raw sources, provider runs, source bundles, citations, workflow
  traces, or audit artifacts to save prompt context.
- Do not replace stored sources with summaries, diagrams, labels, embeddings, or
  answers.
- Obsolete decision history belongs in `docs/memory-pipeline-archive.md` only when
  future decisions need the rationale; otherwise Git history is sufficient.
- Current task state belongs in WBS and long restore pointers belong in Pointer
  Map. Historical candidate lists and mixed work logs belong in external archives.
  Presentation diagrams must stay reproducible through the D2/Marp boundary and
  must not become evidence or architecture source of truth by themselves.

## Open Risks

- WBS can become another long prose database if notes are allowed to hold rationale
  or source review text.
- Pointer Map loses value if hashes, byte counts, or restore hints are stale.
- Provider-free local fixtures can prove wiring and boundaries, but not real model
  quality.
- Visual and compressed artifacts can look authoritative; every answer claim must
  still return to source bundle, context chunk, and citation support.
