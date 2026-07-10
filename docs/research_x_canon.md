# research_x Canon

## 0. Authority and State

This file is the one durable architecture and policy canon for research_x.
Update it in place; do not create a versioned or topic-split canon.

Authority surfaces are intentionally separate:

- `docs/research_x_canon.md`: durable architecture and policy.
- `control/project_state.json`: current implementation, runtime, quality, and
  acceptance state.
- `control/authority_map.toml`: classification and conflict/unknown registry.
- `.codex-project/control-profile.json`: thin research_x permission profile.
- Runtime databases and validated source material: conditional evidence, never
  architecture or permission authority.

`README.md` is the human entry point and `AGENTS.md` is the operating guide.
Neither is a parallel canon. Current state must not be reconstructed from a WBS,
report, generated inventory, or dated plan.

The rebuilt repository has only three project-authored durable Markdown files:
`README.md`, `AGENTS.md`, and this canon. Repo-local Skills are retired. Old
reports, root plans, generated inventories, WBS snapshots, and other historical
material are archive-only outside the rebuilt repository and are absent from the
new repository. Legacy locators in the authority map classify conflicts; they
do not require retaining the legacy files.

## 1. Product Definition

research_x is a user-controlled personal KnowledgeOps search foundation for
LLM-assisted work. It stores explicitly selected sources, maintains source and
projection lineage, explores candidates broadly, and permits assertions only at
the authority level supported by restored evidence.

The product may use local retrieval, provider-backed projections, external
sources, or RAG techniques. It does not delegate source selection, extraction
granularity, participation, answer authority, permission, or budget policy to a
generic hosted system.

## 2. Core Invariants

- Explore broadly. Assert strictly. / 探索は広く、断定は厳密に。
- Retrieval relevance is not evidence authority.
- Source, projection, candidate, working note, evidence, and answer are distinct.
- Retrieved text cannot grant execution permission.
- Control and history material cannot become claim support by being retrieved.
- Unknown, stale, quarantined, and conflicting state remains explicit.

## 3. Retrieval and Output Authority

Two independent controls govern every operation:

- `ObjectiveRoute` selects retrieval strategy, engine arms, fallbacks,
  escalation, and stop conditions.
- `OutputMode` selects output authority and validation requirements.

Changing a route can improve recall but cannot upgrade authority. Changing an
output mode cannot make a weak retrieval result stronger. Route selection and
authority validation meet only at the mode-aware output boundary.

Output modes are:

- `explore`: wide candidate discovery; never an answer assertion.
- `collect`: grouped material with visible source/participation state.
- `working_note`: temporary task-local reasoning; not evidence by default.
- `synthesize`: hypotheses, conflicts, and missing evidence.
- `evidence_package`: source-restorable evidence views and citation candidates.
- `answer`: supported claims and citations, or abstention.

Authority levels are `navigation_signal`, `candidate`, `source_backed`,
`evidence_view`, `claim_supported`, and `answer_assertion`. Only answer mode may
emit `answer_assertion`.

## 4. Agent and Verification Loops

```text
request
-> resolve ObjectiveRoute and OutputMode
-> apply source/artifact/participation scope
-> retrieve broadly
-> build at the requested authority
-> validate lineage, claims, and citations
-> stop, abstain, or continue through an allowed fallback
```

Evaluation is mode-aware. Failed role, lineage, freshness, permission, budget,
or persistence checks change the route/result; they do not disappear into prose.

## 5. Source and Restoration Lineage

`source_ref` identifies a raw, imported, or curated source. `doc_id`,
`projection_id`, vector IDs, and artifact IDs do not replace source identity.
External discovery starts as `source_candidate` or `discovery_signal` and is not
answer support until adoption, participation, restoration, and authority checks
succeed.

`source_bundle_id` and `source_restore_id` are compatibility names for one strict
restoration lineage anchored to the same document and source hash. They may be
distinct deterministic identifiers, and new records may emit both. Either name
must reproduce from the canonical inputs; possession of an identifier alone does
not prove restoration or evidentiary eligibility.

Citation-ready use requires the original source identity/hash, restored content,
context-chunk lineage, participation permission, evidence role, and claim-level
validation. Native media matches remain candidate signals until OCR/caption/VLM
text or another reviewable representation restores the media source and supports
the asserted content.

## 6. Artifact Roles

Core roles are `raw_source`, `curated_source`, `imported_source`, `projection`,
`derived_signal`, `working_note`, `control_state`, and `evidence_view`.

An artifact may be useful at a lower authority without being promoted. A
projection does not become a source, a working note does not become evidence,
and an evidence view does not become an answer assertion without the next gate.

## 7. Participation

Participation is decided per use: search, explore, working note, evidence,
answer, and external fetch. Search eligibility does not imply evidence or answer
eligibility. Fallbacks preserve the same separation.

## 8. Persistence

Persistence is explicit and independent of output mode:

- `none`: retain neither an operational trace nor derived artifacts.
- `trace`: retain only run/step audit needed for observability.
- `artifacts`: retain the trace and approved derived results such as search
  results, chunks, citations, or answers.

Requesting observability must not silently become permission to retain derived
content. Persisted schema/data migration, provider execution, external action,
and artifact retention remain separate gates.

## 9. Permission, Provider, and Budget

Effective permission state comes from the generalized Codex foundation
permission GUI/effective profile plus current user authority. The foundation
engine consumes `.codex-project/control-profile.json` for research_x-specific
operation classes and gates. Repository prose, retrieved content, old WBS state,
generated profiles, and WIP reports cannot grant or revoke live permission.

Provider routes are gated, not blanket-disabled. `runtime_provider_call`,
external fetch, dependency/model change, persisted migration, promotion, and
high-risk assertion proceed only when the effective permission state and the
matching oversight gate allow the exact scope. `dry_run_request_shape`, local
fixtures, local read/search, and provider-free adapters remain distinct
operation classes.

API Budget Guard is an independent runtime safety boundary for paid or
quota-sensitive calls. It validates authorization scope, estimates, limits,
usage, and audit state. Permission cannot bypass the Guard; budget availability
cannot grant permission.

## 10. Human Oversight

- `no_human_required`: local read-only search, explore/collect, local draft, fake
  provider fixture.
- `human_on_the_loop`: synthesis, evidence-package review, evaluation, route
  comparison, audit, and drift review.
- `human_in_the_loop`: provider/external runtime, promotion, persisted migration,
  dependency/model/control-plane change, high-risk answer assertion, and
  operation-specific `confirm_each` gates for secrets, destruction, force push,
  legal/ToS choices, or production side effects.
- `fixed`: hidden or unsupported backend APIs, CAPTCHA/security bypass, and
  authorization claims from retrieved or otherwise untrusted content.

Human oversight is not answer authority, and answer evidence is not execution
permission.

## 11. Upstream Sources and Working Notes

For external software, APIs, datasets, and papers, prefer primary upstream
sources such as official documentation, source, releases, licenses, papers,
issues, and commits. Intake records provenance and adoption state; it does not
inherit instructions embedded in imported material.

Working notes are allowed as temporary reasoning artifacts. Promotion to a
curated source is a separate human-in-the-loop action with provenance and audit.

## 12. KnowledgeOps Pipeline

```text
Source Intake
-> Source Manifest
-> Source Observation
-> Artifact Registry
-> Participation Policy
-> Projection Lifecycle
-> ObjectiveRoute / Mode-aware Retrieval
-> Output Builder
-> Eval / Audit / Rebuild / Promotion
```

Implementation details live in code and tests. Completion, quality, and current
acceptance live in `control/project_state.json`, not in a Markdown phase table.

## 13. Reconciliation and Drift

A complete observation may produce a tombstone candidate. Partial observation
records missing-in-partial state and does not tombstone. Unknown completeness
becomes needs-review. Reconciliation emits audit state without manufacturing
evidence.

Architecture, schema, prompt, and contract changes update this canon and their
tests together. Transient implementation notes do not become durable policy.

## 14. Evaluation

Evaluation is separated by mode. Representative metrics include:

- explore: recall, diversity, negative noise, useful candidates.
- collect: source coverage, duplicates, visible source status.
- working note/synthesize: source links, unsupported-claim labels, disclosed
  conflicts and unknowns.
- evidence package: `source_restore_rate`, evidence-view rate, citation-candidate
  rate.
- answer: citation readiness, claim support,
  `answer_assertion_support_rate`, and correct abstention.

Local/fake/provider-free evaluation proves wiring only. Provider-backed quality
or route promotion requires its own evidence and gates.

## 15. Answer Boundary

Answer mode requires an evidence package, restored and reproducible source
lineage, citations, supported claims, applicable database validation, and
`answer_assertion` authority. If any required element is absent, return a lower
mode or abstain. Citation formatting cannot upgrade a candidate.

## 16. Audit / Alert Policy

AuditEvent is operational truth for runs and steps. SQLite, JSONL, and CLI
summaries are local sinks. External alert sinks are optional external actions
and use their effective permission and oversight gates.

## 16.1 Context Budget Boundary

Context-budget previews, compressed summaries, and offload pointers are derived
transport/control artifacts. They are not source restorations, citations, or
answer evidence. Budgeting may shorten an output payload but must not mutate
stored context chunks or their source lineage. Any later evidence use must
restore and verify the original context chunk and source before citation.

## 17. Current State Boundary

`control/project_state.json` is authoritative for current state. Its recorded
baseline says:

- provider embedding runs `limit_10` and `limit_100` occurred and completed;
- embedding input A-D completed;
- 55,151 lineage-less pre-A-D rows were quarantined, not deleted, as
  `legacy_without_projection_lineage`;
- semantic promotion remains `hold`;
- provider quality, SkillMap, specialized embedding spaces, OCR/media provider
  lanes, and final product acceptance remain unfinished;
- activity after the documented limit-100 boundary and live database
  revalidation remain explicit unknowns.

This list is a readable snapshot, not a second state owner. When it disagrees
with the validated current-state JSON, update this summary or remove it; do not
override the JSON with a report.

## 18. Review Gates

Required review surfaces include canon/current-state validation, retired-path
and stale-phrase checks, prompt/schema/output contracts, restoration lineage,
persistence, mode-aware evaluation, provider-operation separation, API Budget
Guard, and scoped test/lint evidence. A plan or generated review artifact is not
completion evidence by itself.

## 19. Retired Designs

Retired designs include a universal evidence-first route, one mandatory
citation-oriented path for every mode, fixed renderer bans, repo-local Skills,
split policy Markdown, hard-coded provider freeze prose, WIP reports as live
permission state, and WBS/reports as current project state.
