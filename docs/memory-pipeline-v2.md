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
- PDG source;
- generated SVGs;
- screenshots;
- `.codex/context_offloads/pointer-map.json`;
- ChatGPT/GPT Pro consultation captures;
- sub-agent notes;
- compressed summaries and previews.

They may point to source material or explain workflow structure. They must not be
used as citation-ready evidence, answer support, source-quality evidence, or
permission to call providers.

## WBS / PDG / Pointer Boundary

Work state belongs in:

```text
tools/wbs_viewer/projects/research-x-work-state.json
```

WBS owns candidate lists, decision bands, `complete|active|blocked|closed|archived`
status, planned/actual dates, gates, next actions, owner surfaces, source candidate
URLs, and artifact pointers. WBS notes must stay short and must not become source
review prose or answer evidence.

Structure belongs in:

```text
docs/pdg/*.pdg
```

PDG owns route flows, state transitions, implementation boundaries, source-intake
gates, evidence pipeline transitions, visual context offload procedure, and
provider/dependency/MCP stop transitions. Generated SVGs in `docs/pdg/out/*.svg`
are review artifacts generated from PDG source.

Restore pointers belong in:

```text
.codex/context_offloads/pointer-map.json
```

Pointer entries must keep `pointer_id`, `artifact_path`, `sha256`, `char_count`,
`byte_count`, `restore_hint`, `artifact_kind`, `owner_plane`, and
`not_evidence: true`. Hash and size must match the current file before the pointer
is trusted for context restoration.

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
- Long task state belongs in WBS, long route/state flow belongs in PDG, and long
  restore pointers belong in Pointer Map.

## Open Risks

- WBS can become another long prose database if notes are allowed to hold rationale
  or source review text.
- PDG can become unreadable if a single graph tries to carry every specification.
- Pointer Map loses value if hashes, byte counts, or restore hints are stale.
- Provider-free local fixtures can prove wiring and boundaries, but not real model
  quality.
- Visual and compressed artifacts can look authoritative; every answer claim must
  still return to source bundle, context chunk, and citation support.
