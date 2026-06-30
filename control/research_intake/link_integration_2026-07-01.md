# Link Integration Intake Report - 2026-07-01

This is an active research-intake and adoption-planning artifact. It is not
evidence, not a source bundle, not citation support, and not permission to run
providers, install tools, configure MCP/plugins/connectors, operate logged-in
browsers, or call paid/free-tier APIs.

## Current Objective

User request: investigate the provided links group by group, keep scope broad,
avoid treating one interpretation as final, and introduce useful findings into
`research_x` or the Codex foundation where appropriate. The only hard execution
ban is quota/cost/provider consumption. This run still keeps the repository's
provider freeze active: no real provider/API/quota calls were made.

## Loop 1 Coverage

Sub-agent investigations covered these groups:

- AI agent control and safety.
- RAG, knowledge management, Graph RAG, and AI memory.
- AI-generated artifacts, slides, reverse specifications, and visual QA.
- DB, data formats, search backend, and reranking stability.
- Acquisition limits, login/private X, Edge Add-ons, and snippet-only X posts.

Resulting project records:

- Source locks added in `control/vendor_sources.lock.md`: `S44` through `S55`.
- Research intake source candidates added in
  `control/research_intake/source_registry.toml`.
- Research adoption candidates added in `control/adoption_registry.toml`.
- Codex foundation candidates added in
  `C:/Users/maasa/.codex/foundation/codex-foundation-registry.toml`.
- Codex foundation source locks added in
  `C:/Users/maasa/.codex/foundation/vendor_sources.lock.md`.

Correction after loop 2: `Edge Add-ons` is not a `research_x` source/adoption
candidate. It remains only in the Codex foundation as extension-governance
source material.

## Group 1 - Agent Control And Safety

Primary source state:

- `peerd`, `loop-engineering`: GitHub repository metadata/README level.
- Headroom, guardrails, `takt`, AI testing, Lighthouse Agentic Browsing:
  community or company tech articles.
- X posts about Codex session bloat and Lazy Codex: snippet-only or
  not-restored.

Project fit:

- Use guardrail and loop sources to strengthen local observability and
  provider/tool-boundary tests, not as active instructions.
- Treat `peerd` as a memory-tool/MCP security review source, not as a runtime
  memory layer. Memory CRUD results are candidates until restored through
  `source bundle -> context chunk -> citation`.
- Treat Lighthouse/agentic browsing as a control-plane audit pattern. Browser
  audit results are not evidence or answer support.

Codex foundation fit:

- `headroom-context-observability`, `loop-engineering`, `peerd`, and
  `lighthouse-agentic-browsing-audit` are staged/reference candidates.
- No new Skill was created. Existing owners remain `long-loop-executor`,
  `planning-files`, `context-budget`, `codex-fluent`, `route-memory`, and
  `skill-security-review`.

Open boundary for next loop:

- Compare the new agent-control candidates against existing Skill triggers to
  identify exact missing checks, not just broad inspiration.
- Verify whether the Headroom source URL in the existing foundation registry
  should be replaced or split from the newly added community article signal.

## Group 2 - RAG, Knowledge Ops, Graph RAG, AI Memory

Primary source state:

- `cognee`: OSS README-level source, provider/API/install/MCP surfaces present.
- Databricks RAG workflow: vendor official blog.
- OKF: Google Cloud article plus Japanese community explanation.
- KG puzzle, Knowledge Ops, Claude ontology: community articles.

Project fit:

- Adopt the idea of typed edges only where it improves answer authority:
  `supports`, `contradicts`, `supersedes`, `can_view`, and restoration lineage.
- OKF-style metadata can inform source-candidate metadata such as `type`,
  `resource`, `timestamp`, `owner`, and `review_status`, but metadata is not a
  source bundle.
- Knowledge Ops maps well to workflow trace fields: included, excluded, changed,
  stale, reflected, and search-hit.
- Databricks-style governance maps to retrieval precision, answer faithfulness,
  provenance, freshness, and context-budget eval separation.
- `cognee` remains provider-gated/reference. It overlaps with `research_x`
  memory architecture and can easily blur source evidence boundaries.

Codex foundation fit:

- OKF is a candidate for optional Basic Memory note metadata only.
- `cognee` is provider-gated for Codex memory, not an active replacement for
  Basic Memory or `research_x`.

Open boundary for next loop:

- Design a non-provider fixture set for typed edges and contradiction handling.
- Decide which metadata fields belong in source candidates versus source bundles
  versus context chunks.

## Group 3 - Generated Artifacts, Slides, Specs

Primary source state:

- `cc-rsg`: article plus GitHub README source.
- Marp/Slidev: article plus official surfaces.
- `ppt-master`: GitHub source identified through snippet-only X post.
- X posts about Slidev/Playwright and PowerPoint generation: snippet-only.

Project fit:

- Generated specs, slides, images, PDFs, and screenshots are presentation or
  review artifacts only.
- `cc-rsg` contributes a useful phase/reference/question-bank pattern, but no
  generated spec can become source truth without restored code/source references.
- Marp remains the current deck assembly lane. Slidev is staged only for
  componentized visual review if local render/visual QA proves useful.
- Playwright visual comparison is a candidate QA gate for layout overlap and
  broken outputs, not evidence quality.

Codex foundation fit:

- `cc-rsg`, `slidev-playwright-visual-review`, and `ppt-master` are foundation
  candidates.
- `ppt-master` is provider-gated because model/API/image-generation paths are
  plausible from its documented usage.

Open boundary for next loop:

- Inspect current `docs/presentation` generation and decide whether Slidev adds
  value over the existing D2/Marp/Mermaid boundaries.
- Define a visual QA checklist that checks layout without overclaiming factual
  correctness.

## Group 4 - Data Formats, Query Builders, Reranking Stability

Primary source state:

- `f3`: GitHub README reports a research prototype and production non-use.
- `SQLJoiner`: GitHub README, MySQL visual query builder, GPL-3.0, credential
  and SQL execution surfaces.
- LY embedding stabilization: official company tech blog/event article.

Project fit:

- F3 is reference-only for self-describing artifact manifests: schema, decoder,
  restore command, hashes, and source locator. Do not execute embedded Wasm.
- SQLJoiner is a UX reference for query-plan visualization. Do not import code,
  store credentials, or add SQL execution.
- LY embedding stabilization is useful for local synthetic drift/cold-start
  evals. Similarity improvements must be reported alongside restoration rate,
  citation coverage, and answerability.

Codex foundation fit:

- These mostly affect `research_x`; foundation relevance is limited to artifact
  portability, query visualization, and no-cost benchmark governance.

Open boundary for next loop:

- Identify existing local eval surfaces where synthetic embedding drift can be
  modeled without real embeddings.
- Check whether query-plan visualization belongs in the CLI, WBS, dashboard, or
  trace JSON.

## Group 5 - Acquisition Limits, X, Edge Add-ons

Primary source state:

- `x.com/i/bookmarks`: login-required private locator.
- Four X posts: snippet-only or not-restored.
- Edge Add-ons: official store surface and Microsoft docs.

Project fit:

- X bookmark locators need statuses such as `login_required`,
  `private_locator`, `user_export_required`, and `source_not_restored`.
- Snippet-only X posts cannot become citations. They stop at
  `source_not_restored`, not merely `citation_missing`.
- Edge Add-ons is an extension-governance source for the Codex foundation, not a
  `research_x` source candidate and not approval to install or trust any
  extension.

Codex foundation fit:

- `x-private-source-routing` is a route-memory candidate.
- `edge-addons-governance` is a staged extension-review checklist candidate.

Open boundary for next loop:

- Decide whether to add route-memory entries now or wait until repeated X
  restoration failures produce exact route fingerprints.
- Define private-source handling tests before any browser/export workflow.
- Keep Edge-specific extension review outside the project intake registry unless
  a concrete extension becomes a source-acquisition dependency for `research_x`.

## Cross-Group Adoption Matrix

Project candidates staged or gated:

| Candidate | Shape | Owner | First useful local check |
| --- | --- | --- | --- |
| `kg_typed_edge_authority` | staging | retrieval/eval | typed-edge and contradiction fixtures |
| `cognee_graph_memory_reference` | provider_gated | external source candidate | architecture comparison only |
| `okf_source_metadata_shape` | staging | intake metadata | metadata fixture and restoration tests |
| `rag_knowledge_ops_observability` | staging | workflow trace | coverage/freshness trace fields |
| `ontology_relation_traversal_eval` | staging | route policy | relation traversal vs semantic recall fixtures |
| `databricks_rag_governance_checklist` | staging | eval | precision vs faithfulness separation |
| `cc_rsg_reverse_spec_review` | staging | control artifact | generated-spec non-evidence test |
| `slidev_visual_review_lane` | staging | presentation | local render/visual QA comparison |
| `f3_self_describing_artifact_reference` | staging | artifact manifest | manifest fields, no Wasm execution |
| `sqljoiner_query_visualization_reference` | staging | control artifact | read-only query-plan fixture |
| `embedding_stabilization_eval` | staging | retrieval eval | synthetic drift/cold-start fixtures |
| `x_source_restoration_status` | staging | source restoration | login/snippet/private status fixtures |

Codex foundation candidates staged or gated:

| Candidate | Shape | Reason |
| --- | --- | --- |
| `headroom-context-observability` | staging | context/session visibility signal |
| `loop-engineering` | staging | phase/residual loop comparison |
| `peerd` | staging | MCP/local-memory governance review |
| `lighthouse-agentic-browsing-audit` | staging | browser/MCP audit checklist |
| `okf-metadata-notes` | staging | optional Basic Memory metadata comparison |
| `cognee` | provider_gated | graph memory platform with provider/API surfaces |
| `cc-rsg` | reference_only | generated-spec review pattern |
| `slidev-playwright-visual-review` | staging | presentation QA loop candidate |
| `ppt-master` | provider_gated | model/API-dependent slide generation candidate |
| `x-private-source-routing` | staging | private/snippet-only route-memory candidate |
| `edge-addons-governance` | staging | extension install/privacy review checklist |

## Loop 2 Review

Loop 2 intentionally excluded first-pass URL summaries and checked only
non-overlapping boundaries.

Registry and gate findings:

- `S56 edge-addons-store` belonged to the Codex foundation, not the project
  source lock. It was removed from project source intake and kept as
  `edge-addons-governance` in the Codex foundation.
- Multi-locator candidates need explicit source-candidate rows for official or
  primary surfaces. Added rows cover Google Cloud OKF, cc-rsg GitHub, Marp
  official docs, Slidev official docs, and X Help bookmarks.
- `rag_knowledge_ops_observability` and
  `databricks_rag_governance_checklist` needed stronger stop conditions for
  managed/cloud service execution. Those gates are now explicit.
- `control/adoption_registry.toml` now makes non-provider external action gates
  machine-readable through `external_action_requires_approval` and
  `install_mcp_connector_extension_gate`.
- `control/research_intake/source_registry.toml` remains metadata-only. Local
  validation now blocks enabled manual URLs whose storage-rights text signals
  provider, dependency, extension, license, private, user-export, not-restored,
  credential, MCP, plugin, or cloud risk.

Implementation-surface findings for future local fixtures:

- `kg_typed_edge_authority`: use `memory/relations.py`,
  `memory/evidence.py`, and `tests/memory/*` fixtures. Do not add a graph
  runtime or let typed edges bypass citations.
- `rag_knowledge_ops_observability`: use `memory/observability.py`,
  operational trace tests, and tool-interface trace checks. Do not add
  notifications, managed indexes, or cloud sync.
- `ontology_relation_traversal_eval`: use retrieval-strategy and retrieval
  quality fixtures where explicit, current, restorable relations beat semantic
  neighbors. Do not infer relations as a default route.
- `databricks_rag_governance_checklist`: map only vendor-neutral eval concepts
  into local fixtures. Keep retrieval quality separate from answer faithfulness.
- `embedding_stabilization_eval`: use local synthetic drift/cold-start fixtures
  around `local_hash`/vector projection diagnostics. Do not use real embedding
  providers or treat local_hash as model-quality evidence.
- `x_source_restoration_status`: add local statuses for `login_required`,
  `snippet_only`, `source_unavailable`, `source_not_restored`, and
  `user_export_required`. Do not use browser scraping, login bypass, or snippets
  as citations.

Codex foundation overlap findings:

- New Codex foundation candidates stay registry-only. They are not new Skills.
- `headroom-context-observability` overlaps `context-budget` and
  `codex-fluent`; it can only promote as report-only local metrics tied to
  repeated failures.
- `loop-engineering` overlaps `long-loop-executor`, `planning-files`, and the
  HOTL pipeline; it remains taxonomy/reference material.
- `peerd`, Lighthouse Agentic Browsing, Edge Add-ons, and X private-source
  routing are governance or route-memory checklist candidates, not executable
  setup instructions.
- `cognee` and `ppt-master` remain provider-gated; no Docker, MCP/plugin,
  LLM_API_KEY, image generation, model/API, or trace-capture execution is
  allowed under the current freeze.

Presentation boundary findings:

- Existing D2/Marp/Mermaid/WBS presentation boundaries are coherent and already
  block generated artifacts from evidence promotion.
- Slidev/Playwright can add value only as optional visual QA for layout,
  overlap, missing assets, blank renders, and unreadable scale. It should not
  replace the Marp deck lane or final flow docs.
- Future checks may add artifact kinds such as `slidev_rendered_view`,
  `slidev_deck`, `playwright_visual_snapshot`, `ppt_master_deck`, and
  `reverse_spec`, all with `not_evidence: true` and
  `answer_support_allowed: false`.

## Loop 3-5 Local Implementations

The next non-overlapping loops moved from registry-only intake to local,
provider-free implementation gates. These changes intentionally avoid provider
API calls, installs, browser login, extension setup, managed RAG services, and
new graph/vector dependencies.

Implemented source-restoration boundary:

- `x_source_restoration_status` is now implemented in
  `src/research_x/memory/evidence_invariants.py` with fixture coverage in
  `tests/memory/test_x_source_restoration_status.py`.
- `login_required`, `snippet_only`, `source_unavailable`,
  `source_not_restored`, `user_export_required`, `private_locator`, and
  `private_collection` block citation readiness even when other lineage fields
  look restored.
- This maps the X bookmark/private/snippet group into a local answer-authority
  invariant, not a browser/login/scraping route.

Implemented typed relation / ontology boundary:

- `kg_typed_edge_authority` and `ontology_relation_traversal_eval` are now
  represented as candidate-only relation trace and eval fixtures.
- `workflow_tool_output.trace.relation_traversal` exposes relation counts and
  relation rows with `candidate_only: true` and
  `promotion_requires_restored_citation: true`.
- Relation artifacts such as `typed_relation_edge`,
  `relation_traversal_hint`, `memory_relation`, `graph_edge`, and
  `ontology_relation` are blocked from citation-ready evidence.
- This preserves the useful Graph RAG idea, explicit typed edges, while
  refusing the unsafe shortcut where an edge itself becomes answer support.

Implemented Knowledge Ops / RAG governance boundary:

- `rag_knowledge_ops_observability` is now implemented as
  `knowledge_ops_trace` in workflow metadata and as
  `trace.rag_governance.knowledge_ops` in tool output.
- `databricks_rag_governance_checklist` is implemented as
  `eval_control_plane_summary`, covering source coverage, freshness,
  retrieval precision, answer faithfulness, provider-free fixture scope, and
  context-budget signals.
- Both surfaces explicitly use
  `evidence_role: control_plane_not_answer_evidence` and
  `answer_support_allowed: false`.
- This makes hidden RAG workflow state visible without adopting managed search,
  Databricks services, notification services, or cloud sync.

Implemented embedding stabilization / vector projection boundary:

- `embedding_stabilization_eval` is now implemented through local
  `local_hash`/vector-projection fixtures.
- `vector_projection_coverage` now requires `missing_memberships == 0` and
  `current_memberships == expected_documents` before returning `ok`.
- Provider-free tests cover an ok diagnostic projection, missing membership as
  `stale`, and cold-start threshold failures as `needs_review`.
- `local_hash` remains diagnostic-only and is still not production semantic
  evidence or answer support.

Verification completed for these loops:

- `uv run pytest tests\memory\test_x_source_restoration_status.py tests\memory\test_citation_ready_requires_lineage.py tests\memory\test_evidence_invariant_fixtures.py tests\tool_interface\test_preview_cannot_be_citation.py -q`
- `uv run pytest tests\tool_interface\test_memory_tool_contract_strictness.py tests\tool_interface\test_preview_cannot_be_citation.py tests\memory\test_evidence_invariant_fixtures.py tests\memory\test_retrieval_quality_eval.py tests\memory\test_retrieval_dedup_provenance.py -q`
- `uv run pytest tests\test_memory.py::test_memory_eval_records_route_level_fields tests\memory\test_operational_trace_persistence.py tests\tool_interface\test_memory_tool_contract_strictness.py tests\memory\test_retrieval_quality_eval.py -q`
- `uv run pytest tests\tool_interface -q`
- `uv run pytest tests\vector tests\test_memory.py::test_memory_vector_projection_backend_searches_existing_embeddings tests\test_memory.py::test_memory_vector_backend_benchmark_gates_candidate_dependency tests\test_memory.py::test_memory_vector_backend_benchmark_blocks_non_local_provider tests\test_memory.py::test_memory_vector_backend_benchmark_cli_reports_candidate_gate tests\test_memory.py::test_memory_vector_projection_coverage_detects_stale_source_hash tests\test_memory.py::test_memory_vector_projection_coverage_respects_doc_type_scope tests\test_memory.py::test_memory_portfolio_strict_blocks_diagnostic_provider tests\memory\test_memory_audit_warning_taxonomy.py::test_audit_taxonomy_treats_local_hash_as_expected_provider_gate -q`
- Targeted `ruff check` runs passed for every edited implementation/test
  surface.

Committed and pushed implementation checkpoints:

- `a532575` `Block unrestored X source citations`
- `7ec4be8` `Expose relation traversal as candidate trace`
- `d1a39ce` `Expose RAG governance control plane traces`
- `cd0fe7d` `Gate stale vector projection membership`

## Non-Overlap Scope For Loop 2

Loop 2 must not repeat the group summaries above. It should investigate only
these boundaries:

1. Registry validity and whether any new candidate violates source-lock,
   provider-gate, or Codex-foundation ownership rules.
2. Exact local fixture targets for the strongest research_x candidates:
   typed edges, Knowledge Ops trace fields, synthetic drift eval, and X
   restoration statuses.
3. Existing Codex foundation overlap: whether new staged candidates duplicate
   existing Skills closely enough to stay registry-only.
4. Route-memory decision: whether there is enough repeated route evidence to add
   X/Edge route entries now, or whether they remain deferred.
5. Presentation boundary: whether Slidev/ppt-master add anything beyond current
   D2/Marp/Mermaid/documents/presentations skills under no-provider constraints.

## Hard Gates Still Active

- No provider/API/quota calls, including free-tier, trial-credit, zero-dollar,
  or keyless external-network calls.
- No install, dependency addition, model download, MCP/plugin/connector/hook
  configuration, browser extension install, or logged-in browser operation.
- No promotion from URL/snippet/report to source bundle, context chunk,
  citation, or answer support.
- No automatic Skill edits or new Skill installation from this report.
