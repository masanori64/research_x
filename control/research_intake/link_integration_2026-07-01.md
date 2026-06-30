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

- `headroom-context-observability`, `peerd`, and
  `lighthouse-agentic-browsing-audit` are adopted only as foundation-owned
  report-only control artifacts.
- `loop-engineering` remains a staged/reference candidate.
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

- `x-private-source-routing` is an active negative route-memory entry.
- `edge-addons-governance` is a staged extension-review checklist candidate.

Open boundary for next loop:

- Continue watching for more exact X restoration failure fingerprints, but the
  first action is now route-memory classification, not browser/provider/search.
- Keep private-source handling tests ahead of any browser/export workflow.
- Keep Edge-specific extension review outside the project intake registry unless
  a concrete extension becomes a source-acquisition dependency for `research_x`.

## Cross-Group Adoption Matrix

Project candidates staged or gated:

| Candidate | Shape | Owner | First useful local check |
| --- | --- | --- | --- |
| `kg_typed_edge_authority` | adopt | retrieval/eval | typed-edge and contradiction fixtures |
| `cognee_graph_memory_reference` | provider_gated | external source candidate | local external AI-memory non-evidence invariant; runtime gated |
| `okf_source_metadata_shape` | adopt | intake metadata | candidate metadata fixture and non-evidence guards |
| `rag_knowledge_ops_observability` | adopt | workflow trace | coverage/freshness trace fields |
| `ontology_relation_traversal_eval` | adopt | route policy | relation traversal vs semantic recall fixtures |
| `databricks_rag_governance_checklist` | adopt | eval | precision vs faithfulness separation |
| `cc_rsg_reverse_spec_review` | adopt | control artifact | generated-spec non-evidence test |
| `slidev_visual_review_lane` | adopt | presentation | local visual QA evaluator; renderer/browser capture still gated |
| `f3_self_describing_artifact_reference` | staging | artifact manifest | inert manifest identity, no Wasm execution |
| `sqljoiner_query_visualization_reference` | staging | control artifact | owned read-only query-plan visualization |
| `embedding_stabilization_eval` | adopt | retrieval eval | synthetic drift/cold-start fixtures |
| `x_source_restoration_status` | adopt | source restoration | login/snippet/private status fixtures |
| `agent_control_source_ownership_coverage` | adopt | research intake | enabled manual URL ownership metadata |

Codex foundation candidates staged or gated:

| Candidate | Shape | Reason |
| --- | --- | --- |
| `headroom-context-observability` | adopt | foundation-owned report-only context headroom control artifact |
| `loop-engineering` | staging | phase/residual loop comparison |
| `peerd` | adopt | foundation-owned report-only agent-tool governance control artifact |
| `lighthouse-agentic-browsing-audit` | adopt | foundation-owned report-only agent-tool governance control artifact |
| `okf-metadata-notes` | staging | optional Basic Memory metadata comparison |
| `cognee` | provider_gated | graph memory platform with provider/API surfaces |
| `cc-rsg` | reference_only | generated-spec review pattern |
| `slidev-playwright-visual-review` | staging | presentation QA loop candidate |
| `ppt-master` | provider_gated | model/API-dependent slide generation candidate |
| `x-private-source-routing` | adopt | active private/snippet-only negative route-memory boundary |
| `edge-addons-governance` | adopt | foundation-owned extension governance control artifact |

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
- Local visual QA now evaluates already-rendered deck/snapshot artifacts for
  blank output, missing assets, overlap, readability, and frame fit, while
  Slidev runtime, Playwright capture, and ppt-master generation stay gated.

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

Implemented Cognee / external AI-memory evidence boundary:

- `cognee_graph_memory_reference` remains provider-gated and disabled, but
  `src/research_x/memory/evidence_invariants.py` now explicitly recognizes
  external AI-memory and graph-memory platform outputs as non-evidence.
- New markers include `external_ai_memory`, `external_graph_memory`,
  `ai_memory_platform_output`, `graph_memory_platform_output`,
  `cognee_graph_memory`, `cognee_memory_output`, and
  `memory_platform_snapshot`.
- Metadata keys such as `memory_platform_output`, `memory_platform_role`,
  `graph_memory_role`, `external_memory_status`, and
  `external_memory_source` are inspected even when the payload is copied into a
  local context chunk without the usual `not_evidence` marker.
- `src/research_x/tool_interface/memory_tool_contract.py` now carries the same
  marker vocabulary into AI-facing restore validation, so a forged
  `answer`/`citation_ready` JSON payload with `external_graph_memory` or
  `ai_memory_platform_output` is rejected as unrestored and non-evidence.
- `manual_cognee_repo` has `source_governance` tying the disabled source entry
  to `S45` and `cognee_graph_memory_reference`; the vendor lock explicitly
  states that external memory-platform output is not a source bundle, context
  chunk, citation, evidence, or answer support by itself.
- This adopts the useful Cognee lesson, external memory graph output must pass
  through restored source bundle, context chunk, citation, and answer-authority
  gates, without installing Cognee, using Docker/MCP/plugin setup, cloud, API
  keys, provider calls, or quota.

Implemented embedding stabilization / vector projection boundary:

- `embedding_stabilization_eval` is now implemented through local
  `local_hash`/vector-projection fixtures.
- `vector_projection_coverage` now requires `missing_memberships == 0` and
  `current_memberships == expected_documents` before returning `ok`.
- Provider-free tests cover an ok diagnostic projection, missing membership as
  `stale`, and cold-start threshold failures as `needs_review`.
- `local_hash` remains diagnostic-only and is still not production semantic
  evidence or answer support.

Implemented generated artifact / reverse-spec boundary:

- `cc_rsg_reverse_spec_review` is now implemented as a control-artifact
  boundary: `reverse_spec` and `generated_spec` cannot become evidence,
  citations, or answer support.
- Slidev/Playwright/ppt-master artifact kinds are explicitly blocked as
  non-evidence: `slidev_deck`, `slidev_rendered_view`,
  `playwright_visual_snapshot`, and `ppt_master_deck`.
- This does not adopt Slidev, Playwright MCP, ppt-master, or any model-based
  slide/spec generator. Local visual QA can evaluate already-rendered artifacts,
  but render/capture/generation runtime adoption remains gated.

Implemented OKF source-candidate metadata boundary:

- `okf_source_metadata_shape` is now implemented as
  `okf_source_metadata` on registry sources, dry-run candidates, and
  metadata-only snapshots.
- The shape records `type`, `title`, `resource`, `tags`, `timestamp`, `owner`,
  and `review_status`, plus explicit `citation_excluded`,
  `answer_support_allowed: false`, and
  `not_evidence_until_fetched_and_chunked`.
- `src/research_x/memory/evidence_invariants.py` independently blocks OKF
  metadata shapes from citation-ready evidence, even if copied without the
  usual `not_evidence` marker.
- The OKF links therefore widen source-candidate intake and restoration
  filtering without fetching remote content, creating source bundles, or
  promoting metadata into answer support.

Implemented local guards for F3 / SQLJoiner references:

- `f3_self_describing_artifact_reference` remains staged and disabled, but
  `src/research_x/memory/source_identity.py` now validates inert
  self-describing artifact manifests for source locator, content hash, schema,
  version, decoder-reference metadata, and review-only identity.
- The F3-inspired manifest validator rejects inline Wasm/base64 decoder fields,
  execution/import/subprocess hints, and any answer-support or evidence
  promotion. No F3 archive reader, dependency, or Wasm decoder is adopted.
- `sqljoiner_query_visualization_reference` remains staged and disabled, but
  `src/research_x/memory/research_artifacts.py` now emits an owned
  `query_plan_visualization` review payload derived from
  `ObjectiveRoutePlan.search_plan_graph`.
- The SQLJoiner-inspired payload redacts raw query text, rejects SQL/DSN/
  credential-shaped fields, rejects remote/script/mutation text, renders through
  the safe control-artifact HTML path, and does not import SQLJoiner code or
  create a database connection surface.

Implemented deferred-adoption transparency for non-promoted references:

- `src/research_x/adoption_registry.py` now emits a `deferred` section in the
  adoption audit for `staging`, `provider_gated`, and Codex-bridge entries.
- The audit distinguishes disabled candidates that already have a local boundary
  artifact from candidates that remain provider/quota-gated or externally owned.
- `f3_self_describing_artifact_reference` and
  `sqljoiner_query_visualization_reference` therefore show up as
  `local_boundary_without_runtime_adoption`: the local guards exist, but F3
  readers, Wasm decoders, SQLJoiner code, database connections, dependency
  installs, runtime imports, default-route promotion, and evidence promotion
  remain disabled.
- `cognee_graph_memory_reference` remains visible as
  `provider_or_quota_gate_active`; the local non-evidence invariant does not
  enable Cognee runtime, Docker, MCP/plugin setup, cloud use, API keys, provider
  calls, or quota.

Implemented Codex-foundation ownership audit for agent-control links:

- `headroom-context-observability`, `loop-engineering`, `peerd`,
  `lighthouse-agentic-browsing-audit`, `edge-addons-governance`, and
  `x-private-source-routing` are now covered by a project-side boundary test
  that reads the Codex foundation registry on the owner machine.
- The audit requires `loop-engineering` to remain staged and disabled, while
  `headroom-context-observability`, `peerd`,
  `lighthouse-agentic-browsing-audit`, `edge-addons-governance`, and
  `x-private-source-routing` may only be adopted as disabled governance or
  route-memory control surfaces in the Codex foundation registry.
- Source-lock coverage stays in the Codex foundation vendor lock.
- The same test checks they do not appear as `research_x` adoption candidates
  and do not create repo-local Skill surfaces under `.agents/skills`.
- This introduces the agent-control links as governance inputs while preserving
  existing owners: `context-budget`, `codex-fluent`, `long-loop-executor`,
  `planning-files`, route memory, and explicit browser/MCP/install gates.

Implemented agent-safety tool trace:

- `agent_safety_tool_trace` is now implemented in
  `src/research_x/tool_interface/memory_tool_contract.py`.
- AI-facing tool output must include `trace.agent_safety`, which exposes the
  local memory-search-only tool boundary, system-side guards, forbidden
  external actions, loop-control state, provider-like parameter validation, and
  answer-support prerequisites.
- This uses the guardrail and loop-control sources as contract visibility:
  safety is enforced by provider gates, API budget guards, citation/source
  restoration, DB-backed validation, and answer-authority checks, not by a
  prompt-only claim.
- The trace explicitly does not grant provider, network, browser, install,
  MCP/plugin/connector, destructive-action, or evidence-promotion permission.

Implemented generated-artifact visual review evaluator:

- `slidev_visual_review_lane` is now implemented as a local evaluator in
  `src/research_x/control_artifacts/visual_review.py`.
- The builder emits review-only `visual_review` control-artifact payloads for
  generated deck and snapshot artifacts such as `slidev_deck`,
  `slidev_rendered_view`, `playwright_visual_snapshot`, and `ppt_master_deck`.
- The evaluator accepts local artifact paths, an already-rendered local
  snapshot, local asset paths, viewport size, and element boxes. It checks blank
  render, missing assets, overlap, readability, viewport/frame fit, exact gate
  status, and non-evidence boundaries.
- Checklist-only payloads remain `needs_review`; a visual review is `ready`
  only when every local evaluator gate passes. Failed or ambiguous checks stay
  review-only and cannot become answer support.
- This does not install Slidev, run Playwright, use ppt-master, launch a
  browser, generate slides, or promote screenshots/decks as evidence. Renderer,
  capture, and deck-generation adoption remain staged behind explicit review.

Implemented X private/snippet route-memory boundary:

- `x-private-source-routing` is now active in
  `C:/Users/maasa/.codex/route_memory/route-memory.json` and source-locked in
  `C:/Users/maasa/.codex/foundation/codex-foundation-registry.toml`.
- The canonical first action is to classify X bookmarks, private collections,
  and snippet-only posts as metadata-only source candidates with
  `login_required`, `private_locator`, `user_export_required`, `snippet_only`,
  or `source_not_restored` before browser, provider, or search attempts.
- The route records failed paths explicitly: citation promotion from snippets,
  logged-in browser automation, hidden APIs, extension install, provider Reader,
  and source-bundle promotion without a local export or restored public source.
- This is Codex control-plane memory only. It is not evidence, not a citation,
  and not permission for browser login, scraping, installs, connectors, MCP,
  hidden APIs, provider calls, or quota use.

Implemented source-governance ownership coverage:

- Enabled `manual_url` entries in `control/research_intake/source_registry.toml`
  now require `source_governance`, and validation rejects enabled manual URLs
  that lack an owner path.
- The new `agent_control_source_ownership_coverage` candidate source-locks the
  previously under-owned agent-control and AI-test-quality URLs as `S57`.
- `source_governance` records owner surface, owner status, source ref,
  adoption candidate, evidence status, and promotion boundary. It is serialized
  into dry-run candidates and snapshots so downstream intake reports can see why
  a source is present without treating it as fetched evidence.
- This covers both project-owned candidates and Codex-foundation-owned
  references, while preserving the boundary that enabled source-registry entries
  are still unfetched, metadata-only, not evidence, not citations, not runtime
  permission, and not automatic adoption.

Implemented Edge extension governance control artifact:

- `edge-addons-governance` is now owned by the Codex foundation pipeline at
  `C:/Users/maasa/.codex/foundation/pipeline/engine/codex_pipeline/edge_addons_governance.py`
  with policy input at
  `C:/Users/maasa/.codex/foundation/pipeline/policies/browser-extension-policy.yml`.
- The artifact records extension ID, store URL, publisher, permissions,
  privacy/data-flow, update risk, local file access, browser session access,
  source-acquisition dependency, and install approval status as review checks.
- The foundation registry points to the local control artifact, but the
  candidate remains `enabled = false` because it is not a runnable extension
  surface.
- The artifact always carries control-artifact/non-evidence markers and grants
  no install, browser-session, MCP/connector, hidden API, scraping, source
  promotion, citation, or answer-support permission.
- `research_x` keeps only boundary assertions for this foundation-owned surface;
  it does not add an Edge source-registry entry, adoption candidate, Skill, or
  runtime path.

Implemented context/headroom observability control artifact:

- `headroom-context-observability` is now owned by the Codex foundation pipeline
  at
  `C:/Users/maasa/.codex/foundation/pipeline/engine/codex_pipeline/context_headroom.py`
  with policy input at
  `C:/Users/maasa/.codex/foundation/pipeline/policies/context-headroom-policy.yml`.
- The artifact records context window, estimated used/remaining tokens,
  consumption rate, subagent counts, active goal state, route-memory preflight,
  artifact queue count, risk band, and recommended mitigations.
- It routes mitigation recommendations through existing `context-budget`,
  `codex-fluent`, `planning-files`, `long-loop-executor`, and route-memory
  surfaces instead of creating a new Skill or automatic session policy.
- The artifact is report-only and grants no automatic compaction, session
  mutation, hook install, Skill creation, provider/quota use, citation, evidence,
  or answer-support permission.
- `research_x` keeps only boundary assertions for this foundation-owned surface;
  it does not add a project adoption candidate, source-registry entry, Skill, or
  runtime path.

Implemented agent-tool governance control artifact:

- `peerd` and `lighthouse-agentic-browsing-audit` are now owned by the Codex
  foundation pipeline at
  `C:/Users/maasa/.codex/foundation/pipeline/engine/codex_pipeline/agent_tool_governance.py`
  with policy input at
  `C:/Users/maasa/.codex/foundation/pipeline/policies/agent-tool-governance-policy.yml`.
- The artifact records tool identity, source-lock state, permission model,
  local memory CRUD, deletion and retention, memory injection, local file
  access, browser-session access, MCP/plugin/hook setup, source-acquisition
  dependency, external network, and install approval as review checks.
- The artifact is report-only and grants no install, MCP/plugin/hook setup,
  browser-session access, local file access, local memory injection, provider
  or quota use, hidden API use, source promotion, citation, or answer-support
  permission.
- `research_x` keeps only boundary assertions for this foundation-owned
  surface; it does not add a project adoption candidate, source-registry entry,
  Skill, runtime path, browser route, or memory layer.

Verification completed for these loops:

- `uv run pytest tests\memory\test_x_source_restoration_status.py tests\memory\test_citation_ready_requires_lineage.py tests\memory\test_evidence_invariant_fixtures.py tests\tool_interface\test_preview_cannot_be_citation.py -q`
- `uv run pytest tests\tool_interface\test_memory_tool_contract_strictness.py tests\tool_interface\test_preview_cannot_be_citation.py tests\memory\test_evidence_invariant_fixtures.py tests\memory\test_retrieval_quality_eval.py tests\memory\test_retrieval_dedup_provenance.py -q`
- `uv run pytest tests\test_memory.py::test_memory_eval_records_route_level_fields tests\memory\test_operational_trace_persistence.py tests\tool_interface\test_memory_tool_contract_strictness.py tests\memory\test_retrieval_quality_eval.py -q`
- `uv run pytest tests\tool_interface -q`
- `uv run pytest tests\vector tests\test_memory.py::test_memory_vector_projection_backend_searches_existing_embeddings tests\test_memory.py::test_memory_vector_backend_benchmark_gates_candidate_dependency tests\test_memory.py::test_memory_vector_backend_benchmark_blocks_non_local_provider tests\test_memory.py::test_memory_vector_backend_benchmark_cli_reports_candidate_gate tests\test_memory.py::test_memory_vector_projection_coverage_detects_stale_source_hash tests\test_memory.py::test_memory_vector_projection_coverage_respects_doc_type_scope tests\test_memory.py::test_memory_portfolio_strict_blocks_diagnostic_provider tests\memory\test_memory_audit_warning_taxonomy.py::test_audit_taxonomy_treats_local_hash_as_expected_provider_gate -q`
- `uv run pytest tests\memory\test_preview_not_evidence.py tests\tool_interface\test_preview_cannot_be_citation.py tests\test_control_artifact_structure_view.py tests\test_diagram_review_boundary.py -q`
- `uv run pytest tests\test_research_intake.py tests\research_intake\test_source_registry_policy.py tests\research_intake\test_no_network_by_default.py tests\memory\test_evidence_invariant_fixtures.py tests\test_adoption_registry.py -q`
- `uv run pytest tests\memory\test_source_identity_manifest.py tests\test_query_plan_visualization_boundary.py tests\test_control_artifact_structure_view.py tests\test_pytest_lane_markers.py tests\research_intake\test_source_registry_policy.py tests\test_adoption_registry.py -q`
- `uv run pytest tests\test_adoption_registry.py -q`
- `uv run pytest tests\test_codex_foundation_boundary.py tests\test_codex_bridge.py tests\test_agents_route_memory_preflight.py -q`
- `uv run pytest tests\tool_interface\test_memory_tool_contract_strictness.py tests\test_adoption_registry.py tests\skills\test_vendor_sources_lock.py -q`
- `uv run pytest tests\test_visual_review_boundary.py tests\test_control_artifact_structure_view.py tests\test_adoption_registry.py tests\test_pytest_lane_markers.py -q`
- `uv run pytest tests\test_agents_route_memory_preflight.py tests\test_codex_foundation_boundary.py tests\memory\test_x_source_restoration_status.py -q`
- `uv run pytest tests\research_intake\test_source_registry_policy.py tests\test_research_intake.py tests\test_adoption_registry.py -q`
- `uv run python -m research_x.research_intake.cli validate`
- `uv run python -m research_x adoption audit --json`
- `uv run pytest tests\test_codex_foundation_boundary.py tests\test_control_artifact_structure_view.py -q`
- `uv run pytest tests\test_edge_addons_governance.py tests\test_evidence_boundary.py tests\test_dashboard_renderer.py tests\test_foundation_manifest.py -q`
- `uv run pytest tests\test_context_headroom.py tests\test_edge_addons_governance.py tests\test_evidence_boundary.py tests\test_dashboard_renderer.py tests\test_foundation_manifest.py -q`
- `uv run pytest tests\test_agent_tool_governance.py tests\test_edge_addons_governance.py tests\test_context_headroom.py tests\test_evidence_boundary.py tests\test_dashboard_renderer.py tests\test_foundation_manifest.py -q`
- `uv run pytest tests\memory\test_evidence_invariant_fixtures.py tests\tool_interface\test_memory_tool_contract_strictness.py tests\tool_interface\test_preview_cannot_be_citation.py tests\research_intake\test_source_registry_policy.py tests\test_adoption_registry.py tests\skills\test_vendor_sources_lock.py -q`
- `uv run pytest tests\test_visual_review_boundary.py tests\test_control_artifact_structure_view.py tests\test_adoption_registry.py tests\research_intake\test_source_registry_policy.py tests\skills\test_vendor_sources_lock.py tests\test_presentation_stage1.py -q`
- Targeted `ruff check` runs passed for every edited implementation/test
  surface.

Committed and pushed implementation checkpoints:

- `a532575` `Block unrestored X source citations`
- `7ec4be8` `Expose relation traversal as candidate trace`
- `d1a39ce` `Expose RAG governance control plane traces`
- `cd0fe7d` `Gate stale vector projection membership`
- `c290f48` `Record link integration implementation loops`
- `2cd1c56` `Block generated review artifacts as evidence`

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
