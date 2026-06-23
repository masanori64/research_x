# X URL Analysis Current Decision Summary

Date: 2026-06-22
Scope: current project-use judgment after the initial ChatGPT Pro analysis, the 7/10/14/16 addendum,
and the opaque-deferred follow-up.

This file is a checkpoint summary, not citation-ready evidence and not a durable architecture
decision. The inputs are local consultation artifacts in this folder. Primary sources still need the
normal source-intake path before any evidence-bundle promotion, provider use, dependency install,
plugin/MCP enablement, or architecture change.

## Document Roles And Precedence

Use the X/GPT Markdown files in this order:

1. `current-decision-summary.md`: current 35-item judgment and post Phase 1-8 residual decision.
   The second-wave implementation plan for items 11 and 35 is now recorded in
   `implementation-plan-11-35.md` and supersedes the older residual handling for those two items.
2. `phase-gate-report.md`: execution record for Phase 1-8, including GO/NO-GO decisions and
   verification.
3. `implementation-priority-flow.md`: original gate-first implementation plan; it is not the active
   queue after Phase 1-8.
4. `project-usability-review.md`: historical project-use review; its older next actions are
   superseded by this file and `phase-gate-report.md`.
5. `classification.md`: initial source-intake classification; useful for provenance, not current
   execution order.
6. `chatgpt-opaque-deferred-followup.md`, `chatgpt-visible-output.txt`, and addendum text files:
   consultation/raw capture material only.

Durable architecture and project state remain owned by `docs/memory-pipeline-v2.md` and
`PROJECT.md`. This folder records consultation, planning, gate execution, and residual judgment for
this X/GPT flow only.

## Current Reading

Many items are not "hold forever." They are prioritized implementation deferrals: useful enough to
keep, but gated by source restoration, local evals, benchmark fixtures, source review, provider
policy, or a concrete project gap.

## Decision Bands

- Use now: apply as checklist, metric, or local review lens without new dependency.
- Use now narrow: adopt only a small warning or metric, not the full method.
- Codex foundation candidate: useful for Codex Skill/governance design, but proposal-only until
  replay, validation, and human accept/reject gates exist.
- Local eval candidate: worth testing locally with fixtures before implementation.
- Local dependency candidate: possible future backend/model dependency; benchmark and install gate
  required.
- Source intake priority: restore primary sources and risks before any project behavior changes.
- Reference only: keep as an idea or artifact pattern; no current adoption path.
- Provider gated: blocked by no-quota/provider policy unless explicitly lifted.
- Not actionable: insufficient context for a project decision.

## Per-Item Current Judgment

| # | Target | What it is | Current judgment |
|---:|---|---|---|
| 1 | Firecrawl Keyless | Hosted web fetch/crawl service. | Provider gated. Not adopted because it involves external service, credits, ToS/storage-rights, and source-bundle restoration risk. |
| 2 | VS Code/Copilot token efficiency | Token budgeting, lazy loading, and tool-output deferral practice. | Use now. It reinforces existing context-budget/tool-deferral behavior with no new dependency. |
| 3 | Harness decomposition | Keeping agent harnesses small instead of one universal harness. | Reference only. Already mostly covered by Skill boundaries and role-scoped workflows. |
| 4 | Self-improving agents / local optimum | Evidence that naive self-improvement can peak early or degrade. | Codex foundation candidate. Use the lesson that improvement needs branching, eval, replay, and human gates. |
| 5 | YAML-to-HTML / structure-view split | Structured data plus renderer for repeatable artifacts. | Promoted to rule/local artifact pattern candidate. Useful for reports and views, but not as a third-party plugin install now. |
| 6 | RAG Knowledge Hub | Multi-source RAG example collection. | Source-intake/reference only. Useful as a source candidate, but external dependencies and mirrors keep it out of project-use promotion. |
| 7 | OCC-RAG | Context-grounded QA reader/checker with answerable/unanswerable behavior. | First-wave local gate implemented as answerability fixtures. OCC-RAG itself remains a later dependency/model candidate, not a retriever or full RAG stack. |
| 8 | Stale observation masking | Hiding older observations from an agent context. | First-wave local gate implemented as a route-level context-policy eval warning. Do not apply universally; compare by route/model/retriever. |
| 9 | Ontology mention | Thin ontology-related signal. | Not actionable. Original context is too sparse. |
| 10 | Archify | Workflow/architecture diagram or report aid. | Reference only. Generated diagrams are review aids, not evidence; install would need source review. |
| 11 | WBS Viewer | Work breakdown/progress visualization. | Canary passed. Pinned `single-file-wbs` v1.2.0 is vendored unchanged under `tools/wbs_viewer/`, and `wbs-35-item-flow.json` renders the full 35-item flow; see `wbs-viewer-canary-report.md`. |
| 12 | Agentmemory | Persistent coding-agent memory with hooks/MCP/search/inject style behavior. | Disabled source-lock decision completed. No install, plugin, MCP, hook, server, or Skill enablement; retention, redaction, overlap, and lifecycle risks remain. |
| 13 | Adaptive Auto-Harness | Research on adaptive harness routing/steering. | Codex foundation candidate. Use as design input only, not runtime adoption. |
| 14 | SkillAdaptor | Failure-trajectory-based local Skill revision with qualifier checks. | First-wave local pattern implemented in ImprovementSignal fields and validation. No external runtime, automatic Skill edit, or self-improving loop. |
| 15 | Devin/Manus mention | Mention of external agent products. | Not actionable. No concrete source or design delta. |
| 16 | Alibaba Zvec | In-process vector/index database. | First-wave benchmark gate implemented. Zvec remains dependency-review-only until it can beat current local baselines without breaking source restoration. |
| 17 | SAAS over-search | Stop conditions for avoiding redundant search. | First-wave narrow metric implemented as stop-condition audit fields. Do not adopt the full RL stack. |
| 18 | Amazon State-Aware RAG | State-aware RAG architecture/research. | Reference only. Concept aligns with explicit workflow state, but implementation/provider shape is heavy. |
| 19 | AI code-review responsibility split | Separating AI automation from human architecture/design responsibility. | Reference only. Existing review stance and human-on-the-loop policy cover it. |
| 20 | /grill-me | Plan/design interrogation workflow. | Reference only. Existing decision-loop workflow covers the useful part. |
| 21 | grill-me + parallel review | Plan review plus parallel critique pattern. | Reference only. Covered by decision-loop and parallel-review policy when subagents are allowed. |
| 22 | Hanno-Lab Bosun | Local relevance/judgment model candidate. | First-wave local relevance/support fixture lane implemented. Bosun itself remains a later dependency/model candidate. |
| 23 | JAMEL | GUI/browser exploration memory and novelty-signal research. | Source-intake only. Useful only if a GUI/browser exploration objective and coverage metrics are introduced. |
| 24 | MUSE-Autoskill | Skill creation, storage, reuse, evaluation, and refinement lifecycle research. | Codex foundation candidate. Use for Skill lifecycle, tests, examples, failure cases, and revision logs; no automatic Skill growth. |
| 25 | Slack/RAG loop on Bedrock | Internal feedback loop over AWS Bedrock/RAG. | Provider gated. Concept is mostly covered; AWS/IAM/billing/provider freeze block adoption. |
| 26 | Google Agentic RAG | Google Cloud/Vertex/Gemini RAG and agentic retrieval. | Provider gated plus architecture reference. No real calls or integration under the freeze. |
| 27 | Unknown | Unresolved item. | Not actionable. Classification failed or source context is missing. |
| 28 | State separated from LLM | Keeping state outside the LLM. | Reference only. Same direction as current workflow state and gap tracking. |
| 29 | Visual Skills | Visual/spatial Skill or multimodal workflow ideas. | Reference only. Needs privacy, screenshot provenance, region storage, and verification contracts first. |
| 30 | Decision rules as Markdown | Capturing decision rules in Markdown. | Reference only. Existing AGENTS and Skill surfaces already own this. |
| 31 | Bedrock AgentCore harness | AWS managed agent runtime/harness. | Provider gated. IAM, billing, provider freeze, data retention, and lock-in block adoption. |
| 32 | LLM-Oriented IR | LLM-facing retrieval/denoising design. | Use now. Apply as a retrieval review checklist for denoising and citation-ready yield. |
| 33 | Ponytail plugin | Over-implementation prevention plugin/hook. | Source-review required, no install now. Trigger overlap, hook behavior, and source risk need review. |
| 34 | pdgkit article | DSL -> validate -> render article/pattern. | Reference only. Good artifact pattern, but no current patent/diagram requirement. |
| 35 | pdgkit OSS | Deterministic diagram/document renderer with CLI/MCP shape. | Canary passed with LIMITED adoption. `@shibayama/pdgkit@0.1.2` is isolated under `tools/pdgkit_canary/`; real validate/render produced deterministic SVG. No MCP, provider, root dependency, or evidence promotion; see `pdgkit-canary-report.md`. |

## First-Wave Priority Order

This was the first-wave priority order before the phase-gated implementation pass. The implemented
or gated outcome for those items is recorded in
`.codex/chatgpt-control/x-url-analysis-20260622/phase-gate-report.md`.

1. SkillAdaptor: highest Codex foundation value. Start with ImprovementSignal fields and replay
   qualifier fixtures, not external runtime adoption.
2. OCC-RAG: high value for answerability/abstention fixtures after retrieval.
3. Zvec: worthwhile local backend benchmark candidate; no adoption without local corpus comparison.
4. Hanno-Lab Bosun: newly promoted local-eval candidate for relevance, citation support, dedup, and
   conflict/edge checks.
5. Agentmemory: source-review priority for comparing hook/MCP/auto-capture/retention risks against
   existing memory surfaces.

Secondary narrow-use items:

- Stale observation masking: use as an eval warning and route-specific test, not a universal rule.
- YAML-to-HTML / structure-view split: use as a local artifact-pattern candidate when reports need a
  repeatable structured renderer.
- SAAS over-search: keep stop-condition metrics only.

## Post Phase 1-8 Residual Decision

Phase 1-8 is complete for the first-wave gates. Items 7, 8, 12, 14, 16, 17, and 22 now have local
gate outcomes or source-lock outcomes. Item 8 ended as a route-level eval warning, and Phase 8
ended as an intentional `NO-GO` because no concrete renderer or observability gap was present.

Do not keep all remaining items in an undifferentiated hold bucket. After Phase 1-8, classify the
remaining 35-item set as follows.

### Second-Wave Candidates

Consider these only as a new scoped task, not as continuation of Phase 1-8:

| # | Target | Next handling |
|---:|---|---|
| 5 | YAML-to-HTML / structure-view split | Local artifact-pattern candidate. Reconsider when report, eval, or phase-gate artifacts become hard to inspect. Start with a project-owned schema and deterministic renderer, not a plugin. |
| 10 | Archify | Conditional workflow/architecture review aid. Generated diagrams are review artifacts, not evidence. Any install or external source use still needs source review. |
| 11 | WBS Viewer | Completed canary. Keep the vendored upstream viewer for local visual review; no fork/customization needed yet. |
| 35 | pdgkit OSS | Completed canary. Keep LIMITED local `.pdg -> validate -> SVG` lane for selected spec diagrams; do not enable MCP without a later gate. |
| 24 | MUSE-Autoskill | Codex foundation design input for Skill lifecycle, tests, examples, failure cases, and revision logs. No automatic Skill growth. |
| 33 | Ponytail plugin | Source-review-only candidate for over-implementation checks. Use the idea as a review lens before considering hooks or plugin install. |

### Absorbed Or No Standalone Task

These do not need separate follow-up tasks now because their useful part is already covered by
existing repo policy, implemented gates, or current Skills:

- 2 VS Code/Copilot token efficiency.
- 3 harness decomposition.
- 4 self-improving agents / local optimum.
- 13 Adaptive Auto-Harness.
- 18 Amazon State-Aware RAG.
- 19 AI code-review responsibility split.
- 20 `/grill-me`.
- 21 grill-me plus parallel review.
- 28 state separated from LLM.
- 30 decision rules as Markdown.
- 32 LLM-Oriented IR.

### Condition-Triggered Only

Keep these dormant until the named condition appears:

- 23 JAMEL: only for a GUI/browser exploration objective with coverage or novelty metrics.
- 29 Visual Skills: only for UI/browser/media work where spatial evidence is central, with
  screenshot provenance, privacy, region storage, and verification contracts first.
- 34 pdgkit article: only if a deterministic diagram/document renderer requirement appears.

### Provider-Gated Closed

Close these for the no-quota local flow. Reopen only if the user explicitly starts a provider or
managed-service evaluation:

- 1 Firecrawl Keyless.
- 25 Slack/RAG loop on Bedrock.
- 26 Google Agentic RAG.
- 31 Bedrock AgentCore.

### Closed Or Not Actionable

These should not consume more planning work from this URL set:

- 6 RAG Knowledge Hub: reference/source-intake only; blocked by hosted dependencies, mirror or
  extraction concerns, and source-restoration/storage-rights risk.
- 9 Ontology mention: not actionable without restored original context.
- 15 Devin/Manus mention: not actionable without a separate vendor/provider evaluation target.
- 27 Unknown: not actionable because the classification/source context is missing.

### Already Processed By Phase 1-8 Or Item 11 Canary

These are no longer residual candidates for this flow:

- 11 WBS Viewer: pinned local tool canary completed; vendored viewer renders the 35-item flow.
- 35 pdgkit OSS: pinned body-adoption canary completed; LIMITED local `.pdg -> validate -> SVG`
  lane only.
- 7 OCC-RAG: local answerability fixture lane implemented; model adoption remains a separate
  dependency/model gate.
- 8 stale observation masking: route-level context-policy eval warning implemented; no universal
  masking policy.
- 12 Agentmemory: disabled source-lock decision completed; no plugin, MCP, hook, server, or Skill
  enablement.
- 14 SkillAdaptor: local ImprovementSignal qualifier pattern implemented; no external runtime or
  automatic Skill edit path.
- 16 Alibaba Zvec: local benchmark gate implemented; Zvec remains dependency-review-only.
- 17 SAAS over-search: stop-condition audit fields implemented; no full RL/search-policy stack.
- 22 Hanno-Lab Bosun: local relevance/support fixture lane implemented; model adoption remains a
  later dependency/model gate.

Net decision: the only non-processed items worth active second-wave consideration are 5, 10, 24,
and 33. Items 11 and 35 are now processed by local canaries. Everything else is either absorbed,
condition-triggered, provider-gated, or closed.

## Do Not Promote Now

- No provider/API calls, free-credit usage, hosted search/RAG, or managed-RAG integration.
- No plugin, MCP, hook, or dependency installation from this URL set, except the completed isolated
  item-35 pdgkit body-adoption canary under `tools/pdgkit_canary/`.
- No automatic Skill rewrite or self-improving loop without replay, qualifier, manifest validation,
  and human accept/reject.
- No source-bundle promotion from ChatGPT/X-derived summaries without primary source restoration.
- No new memory architecture Markdown file from this checkpoint.

Governance status: source-intake checkpoint plus no durable architecture decision.
