# AI-Callable Memory Search Pipeline V2

This is the detailed evidence-architecture contract for `research_x`. The
current provisional final flow is owned by:

- `docs/presentation/final-runtime-flow.md`
- `docs/presentation/final-design-flow.md`

Those two files define the human-facing runtime/design order used by diagrams
and explanation. This file defines the lower evidence, provider, trace, tool
contract, and governance mechanics that make that final flow enforceable.

It is not the work-state database, structural-flow database, historical research
log, diagram asset, citation source, answer support, or provider permission.

## Executive Decision

Keep the local lower retrieval foundation, but make answer authority explicit.

Keep:

- raw X acquisition tables as source of truth;
- `memory_documents` as rebuildable searchable projections;
- SQLite FTS, BM25-style lexical ranking, metadata, exact-anchor, relation, and
  local/fake routes;
- optional provider-backed recall arms behind provider/quota/network guards;
- source bundle restoration, context chunks, citation annotations, answer
  boundary states, workflow traces, evals, audits, and feedback.

The final system is evidence-first, not vector-first, router-first,
provider-first, agent-first, or diagram-first. Search can become broad, but
answer authority stays narrow.

```text
wide candidate generation
  -> narrow AnswerAuthorityGatekeeper
  -> citation-backed answer or explicit abstention
```

## Current Final Flow Authority

The two final flow documents are the provisional source of truth for ordering:

- `final-runtime-flow.md`: request-to-tool-output execution order;
- `final-design-flow.md`: design names, concepts, and diagram rules.

This file must not reintroduce the old serial flow where local retrieval is
forced through provider approval, route planning happens after citations, or
Workflow Trace is drawn as a normal pipeline step.

## Ownership Boundary

`research_x` is the canonical project for the AI-callable X memory-search tool,
not the canonical project for Codex self-improvement.

- `maasa/research_x` owns X acquisition state, source restoration, retrieval,
  context chunks, citations, answer boundaries, evals, workflow traces, provider
  guards, and local tool output contracts.
- `maasa/.codex` owns Codex-wide Skills, self-improvement, session memory,
  retrospectives, handoffs, Skill/Plugin/MCP governance, and external Codex
  foundation candidates.
- The bridge is intentionally narrow. Codex may pass query, objective, context
  budget, and reviewed source candidate into `research_x`. `research_x` returns
  evidence status, citation-ready answer or abstention, provider_gated state, and
  audit trace.
- Codex transcripts, Skill auto-edit authority, provider execution permission,
  and root instructions are not evidence-pipeline inputs.

External candidates are kept alive by adoption shape: `adopt`, `bridge`,
`staging`, `provider_gated`, or `historical`. Provider/API execution is blocked
while the no-quota freeze is active, including free-tier, trial-credit,
zero-dollar, keyless, or otherwise quota-consuming calls. Hooks, MCP, plugins,
dependencies, and local model candidates use isolated staging and manual review.

Boundary registry: `control/adoption_registry.toml`; validate with
`research-x adoption audit`. Codex-foundation ownership stays in `.codex`.

## Core Invariant

```text
raw source != searchable document != search result != source bundle
!= context chunk != citation != answer
```

Every promoted object must be traceable backward to raw source state and forward
to the workflow, citation, answer claim, or tool output that used it.

Generated labels, summaries, route scores, diagrams, pointer maps, compressed
previews, provider answers, LLM-context text, and conversation predictions are
not citations or answer support by themselves.

## Authority Model

The architecture separates four concepts that were previously easy to conflate.

```text
SearchLens / RetrievalPolicy       = human bias and retrieval preference
ObjectiveRoutePolicy               = route planning
ProviderApiBudgetGuard             = provider / quota / network execution guard
AnswerAuthorityGatekeeper          = candidate-to-answer-support promotion gatekeeper
```

### SearchLens / RetrievalPolicy

SearchLens / RetrievalPolicy represents human-controlled retrieval preference:
corpus scope, account/source weights, trusted or ignored accounts, topic weights,
bookmark/collection weights, diversity and contradiction stance, and allowed
inference posture.

It is not a gate, not a provider approval surface, and not answer authority. It
shapes where to look and how to weight candidates.

### ObjectiveRoutePolicy

ObjectiveRoutePolicy runs before route execution. It chooses candidate routes
from the query, objective, context budget, SearchLens, source candidates, and
available indexes.

It may mark provider-backed lanes, fallback lanes, and stop reasons. It does not
replace source bundles, citation verification, answer abstention, workflow
traces, eval gates, or provider approval.

### ProviderApiBudgetGuard

ProviderApiBudgetGuard controls provider-backed, quota-consuming, network, or
hosted lanes. It is not the answer-authority gatekeeper and it is not a serial
gate for local retrieval lanes.

The external tool status remains `provider_gated` for compatibility with the
current tool contract.

### AnswerAuthorityGatekeeper

AnswerAuthorityGatekeeper is the narrow boundary from candidate to answer
support. It checks:

1. Can the candidate restore to a source bundle?
2. Can the restored source become a bounded context chunk?
3. Can the context chunk receive citation annotation?
4. Does the citation support the specific answer claim?

A candidate that fails these checks may remain useful as navigation, background,
review material, or `hypothesis_only`, but it cannot support an answer claim.

## Runtime Flow Contract

The detailed runtime follows the final flow documents:

```text
Narrow Codex Bridge
  -> Source Layer
  -> Searchable Documents / Retrieval Projections
  -> SearchLens / RetrievalPolicy
  -> ObjectiveRoutePolicy
  -> Retrieval And Route Portfolio
  -> Search Results / Candidates
  -> AnswerAuthorityGatekeeper
  -> Answer Boundary
  -> Tool Interface Layer
  -> Eval / Audit / Feedback
```

Provider-backed lanes branch through ProviderApiBudgetGuard before producing a
candidate or `provider_gated` skip. Workflow Trace records the whole path as a
sidecar, not as a serial step.

## Evidence Layer Responsibilities

This section defines object responsibilities. It is not a serial layer diagram.

### Raw Sources

Raw source objects include `tweets`, `account_bookmarks`, `collection_items`,
`tweet_edges`, `media`, `raw_payloads`, `accounts`, provider run artifacts, and
saved local media when available. These are the provenance base.

Raw records must not be replaced by summaries, embeddings, labels, diagrams, or
answers.

### Searchable Documents

Searchable documents, retrieval text, embeddings, labels, summaries, OCR text,
VLM observations, query transforms, and index projections are rebuildable views
or candidate signals. They must keep source IDs, source hashes, projection
generation, stale/tombstone state, and restore paths.

`memory_documents` is a searchable projection, not the canonical source.

### Candidate Routes

Candidate routes include:

- exact anchors;
- SQLite FTS / BM25;
- metadata search;
- relation expansion;
- retrieval-text projections;
- semantic vectors;
- sparse / late-interaction / rerank candidates;
- OCR / media preparation;
- Corpus2Skill navigation;
- graph / topic hints;
- external Web candidates;
- Reader extraction candidates;
- LLM-context candidates;
- managed-reference / managed RAG candidates;
- conversation-prep / hypothesis candidates.

Adding routes widens discovery, not answer authority. Route output is
candidate-only by default.

### Search Results / Candidates

Search results hold route output such as rank, score components, matched terms,
why_relevant, source_ref, restore_path, lens_id, provider/run metadata, relation
summaries, freshness/staleness signals, and skip reasons.

Search results cannot support claims until they restore a source bundle.

### Source Bundles

A source bundle restores the tweet, quote relation, media relation, author,
bookmark account, URL, timestamp, source hash, and any relevant provider/run
metadata needed to evaluate provenance.

Every retrieval arm that wants promotion must return to source bundle lineage.

### Context Chunks

Context chunks are bounded answer inputs created from restored source bundles.
Unsupported chunks, stale projections, missing media provenance, untrusted tool
text, and generated observations must stay visible in workflow state and eval
output.

OCR/caption/VLM text must stay separate from raw media and corrected text until
promoted through citation-ready context chunks.

### Citations

Citations annotate context chunks with source-backed support. A citation is not
enough unless it maps to the answer claim being made.

Generated labels, route scores, summaries, diagrams, pointer maps, compressed
previews, consultation captures, LLM-context outputs, and conversation
predictions are not citations.

### Answer Support

Answer behavior is `answer`, `abstain`, `needs_review`, `citation_missing`,
`source_not_restored`, `hypothesis_only`, `provider_gated`, or `blocked` when
support is incomplete. Correct-looking text without citation-ready support is
not a completed answer.

Stored `needs_review` answers must stay visible in memory audit triage by
answerability status, citation count, citation block reasons, and representative
answer IDs. Eval answerability distinguishes `answerable`, `unanswerable`,
`conflicting`, `partially_supported`, `stale_only`, and `citation_missing`;
required source kinds are checked against answer citations, not merely present
context chunks.

## ProviderApiBudgetGuard

Real provider calls are blocked while the no-quota freeze is active, including
free-tier, trial-credit, and zero-dollar quota usage. Blocked lanes include real
embeddings, native media embeddings, hosted rerankers, Reader extraction, OCR,
classifiers, answer engines, relation judges, external search, LLM-context,
managed RAG, and real-model prompt-contract validation.

Before the first approved provider call, run `memory api-budget status`, the
relevant offline estimate, and `memory api-budget preflight` with scoped
approval fields: id, provider, model, operation, max calls, max USD, price
source, scope, and approved time. `--allow-provider-quota` alone is insufficient;
preflight is dry-run and must report zero provider requests while the freeze is
active.

Hard block is enforced at `budgeted_api_call`: contextless non-exempt routes are
blocked, active-context freeze blocks are recorded, and only fake/local/local_hash
plus registered local fixture providers such as `fixture_media` are exempt.
Private provider HTTP helpers and direct external Reader fetches must pass the
transport-send guard before `urlopen` or equivalent network send; static scanner
tests cover new provider/network send surfaces.

Request-shape tests inspect builders only; they are not model-quality proof. GPT
review ZIPs must include provider source, git provenance, required-artifact
coverage, observed-zero API-budget deltas, and non-evidence control status.
Observed-zero means no non-exempt provider transport send was observed in the
local API-budget event delta, never a real provider smoke call while frozen.

## Workflow Trace Sidecar

Workflow traces expose route choice, SearchLens, ObjectiveRoutePolicy output,
fallback, provider skip, evidence level, citation support, promotion failures,
budget/offload state, OCR/media status, failure state, and stop reason.

`store=True` workflow runs may persist operational trace rows for auditability;
this does not permit raw source, governance, feedback, provider, or
answer-support mutation outside separate gates.

Workflow Trace is not a normal serial pipeline step. It records the path taken.

## Tool Interface Layer

The Tool Interface Layer presents stable AI-callable JSON even when internal
workflow JSON changes. The current contract is implemented under
`research_x.tool_interface.memory_tool_contract` and exposes:

- `status`: `answer`, `abstain`, `needs_review`, `source_not_restored`,
  `citation_missing`, `hypothesis_only`, `provider_gated`, or `blocked`;
- `evidence_level`: `raw`, `candidate`, `source_bundle`, `context_chunk`, or
  `citation_ready`;
- `citations`: restore pointers back to context chunks and source IDs;
- `trace`: route, stop/skip reason, provider guard, budget state, eval warnings,
  promotion failures, and the narrow Codex bridge boundary.

Tool output must make answer/abstain/review/hypothesis/provider_gated/blocked
states explicit.

## Eval / Audit / Feedback

Eval and audit must check route correctness, restoration, citation coverage, and
answerability, not just whether a search command returns JSON.

Required reporting includes restoration rate, unsupported context chunks,
citation coverage, route gaps, provider-gated lanes, diagnostic-only embeddings,
partial semantic indexes, stale projections, weak retrieval behavior, and stop
conditions.

Feedback improves retrieval and workflow behavior; it does not mutate raw
sources or promote generated answers into evidence.

## ContextBudgetPolicy Boundary

Runtime ContextBudgetPolicy may offload large context/workflow/answer JSON
outputs to previews plus file pointers and hashes. It must not mutate stored context
chunks, citation anchors, answer inputs, or raw source state.

Context previews and offload pointers are retrieval aids, not source bundles,
citations, or answer evidence.

## Non-Evidence Control Artifacts

The following artifacts are control, planning, review, or restore-index surfaces:

- WBS JSON;
- generated diagram sources and rendered assets, screenshots;
- `C:/Users/maasa/.codex/foundation/context_offloads/research_x/pointer-map.json`;
- `C:/Users/maasa/.codex/route_memory/route-memory.json`;
- ChatGPT/GPT Pro consultation captures;
- sub-agent notes;
- compressed summaries and previews.

They may point to source material or explain workflow structure. They must not
be used as citation-ready evidence, answer support, source-quality evidence, or
permission to call providers.

## WBS / Presentation / Pointer Boundary

Work state belongs in `tools/wbs_viewer/projects/research-x-work-state.json`.
WBS owns only current Source, Evidence, Retrieval-Eval, and Tool Interface layer
work state: status, gates, owner surfaces, artifact pointers, stop conditions,
and next actions. It must not hold historical 35-item lists, source-review
prose, candidate inventories, Codex foundation tasks, or viewer implementation
details.

Historical mixed WBS state is archived outside the repo at
`C:/Users/maasa/.codex/foundation/work_state/research-x-pre-layer-wbs-archive-20260625.json`;
Codex foundation work state lives at
`C:/Users/maasa/.codex/foundation/work_state/research-x-codex-foundation-adjuncts.json`.

Final runtime/design content for human diagrams comes from
`docs/presentation/final-runtime-flow.md` and
`docs/presentation/final-design-flow.md`. Diagram-system routing belongs in
`docs/presentation/diagram-systems.md`; the D2 + Marp build-tool boundary is
documented there and in `docs/presentation/diagram-design-harness.md`.

Rendered diagrams, screenshots, and decks are review/presentation assets. They
do not become evidence, provider execution permission, or replacement
architecture truth.

Restore pointers belong in
`C:/Users/maasa/.codex/foundation/context_offloads/research_x/pointer-map.json`.
Pointer entries must keep `pointer_id`, `artifact_path`, `sha256`, `char_count`,
`byte_count`, `restore_hint`, `artifact_kind`, `owner_plane`, and
`not_evidence: true`; runtime context offload pointers also keep `field_path`,
`chunk_id`, `preview_chars`, source anchors, and citation references. Hash and
size must match before restoration, and inline previews, restore hints, pointer
maps, and compressed context-budget output cannot serve as citations or answer
support.

Operation route memory belongs in:

```text
C:/Users/maasa/.codex/route_memory/route-memory.json
```

Route Memory owns recurring operation-route fingerprints, positive and negative
triggers, canonical first actions, known failed routes, verification signals, and
local gates. It is a control-plane preflight input only. It must not be used as
provider/API approval, browser/ChatGPT approval, source evidence, citation
support, or permission to enable hooks, plugins, MCP servers, connectors, or
installs.

## Deletion / Rewrite Policy

- Do not delete raw sources, provider runs, source bundles, citations, workflow
  traces, or audit artifacts to save prompt context.
- Do not replace stored sources with summaries, diagrams, labels, embeddings, or
  answers.
- Obsolete decision history belongs in `docs/memory-pipeline-archive.md` only
  when future decisions need the rationale; otherwise Git history is sufficient.
- Current task state belongs in WBS and long restore pointers belong in Pointer
  Map. Historical candidate lists and mixed work logs belong in external
  archives.
- Presentation diagrams must remain reproducible through the diagram build-tool
  boundary and must not become evidence or architecture source of truth by
  themselves.

## Open Risks

- Markdown can drift again if final flow docs and evidence-contract mechanics
  are treated as interchangeable.
- SearchLens / RetrievalPolicy can be mistaken for answer authority unless every
  route remains candidate-only by default.
- WBS can become another long prose database if notes are allowed to hold
  rationale or source review text.
- Pointer Map loses value if hashes, byte counts, or restore hints are stale.
- Provider-free local fixtures can prove wiring and boundaries, but not real
  model quality.
- Visual and compressed artifacts can look authoritative; every answer claim
  must still return to source bundle, context chunk, citation support, and
  claim-level support mapping.
