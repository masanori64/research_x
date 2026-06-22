# X URL Analysis Current Decision Summary

Date: 2026-06-22
Scope: current project-use judgment after the initial ChatGPT Pro analysis, the 7/10/14/16 addendum,
and the opaque-deferred follow-up.

This file is a checkpoint summary, not citation-ready evidence and not a durable architecture
decision. The inputs are local consultation artifacts in this folder. Primary sources still need the
normal source-intake path before any evidence-bundle promotion, provider use, dependency install,
plugin/MCP enablement, or architecture change.

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
| 7 | OCC-RAG | Context-grounded QA reader/checker with answerable/unanswerable behavior. | Local dependency/eval candidate. Strong as an answerability canary after retrieval, not as a retriever or full RAG stack. |
| 8 | Stale observation masking | Hiding older observations from an agent context. | Promoted to use-now narrow as an eval warning. Do not apply universally; compare by route/model/retriever. |
| 9 | Ontology mention | Thin ontology-related signal. | Not actionable. Original context is too sparse. |
| 10 | Archify | Workflow/architecture diagram or report aid. | Reference only. Generated diagrams are review aids, not evidence; install would need source review. |
| 11 | WBS Viewer | Work breakdown/progress visualization. | Implementation deferred. Add only if a concrete observability gap appears. |
| 12 | Agentmemory | Persistent coding-agent memory with hooks/MCP/search/inject style behavior. | Source-review priority, no install now. Useful comparison target, but intrusive hooks, data retention, overlap, and redaction risks remain. |
| 13 | Adaptive Auto-Harness | Research on adaptive harness routing/steering. | Codex foundation candidate. Use as design input only, not runtime adoption. |
| 14 | SkillAdaptor | Failure-trajectory-based local Skill revision with qualifier checks. | Strongest Codex foundation candidate. Adopt the pattern of fault step, responsible Skill, minimal diff, replay, qualifier, and human decision. |
| 15 | Devin/Manus mention | Mention of external agent products. | Not actionable. No concrete source or design delta. |
| 16 | Alibaba Zvec | In-process vector/index database. | Local dependency candidate. Benchmark against SQLite/FTS/current local vector baselines before any backend decision. |
| 17 | SAAS over-search | Stop conditions for avoiding redundant search. | Use now narrow. Keep search count, stop reason, and evidence-enough metrics; do not adopt the full RL stack. |
| 18 | Amazon State-Aware RAG | State-aware RAG architecture/research. | Reference only. Concept aligns with explicit workflow state, but implementation/provider shape is heavy. |
| 19 | AI code-review responsibility split | Separating AI automation from human architecture/design responsibility. | Reference only. Existing review stance and human-on-the-loop policy cover it. |
| 20 | /grill-me | Plan/design interrogation workflow. | Reference only. Existing decision-loop workflow covers the useful part. |
| 21 | grill-me + parallel review | Plan review plus parallel critique pattern. | Reference only. Covered by decision-loop and parallel-review policy when subagents are allowed. |
| 22 | Hanno-Lab Bosun | Local relevance/judgment model candidate. | Promoted to local eval candidate. Test for citation support, dedup, conflict detection, and memory graph edge warranting. |
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
| 35 | pdgkit OSS | Deterministic diagram/document renderer with CLI/MCP shape. | Reference only. Node/MCP dependency and narrow output fit make it a future requirement-specific candidate. |

## Priority Order

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

## Do Not Promote Now

- No provider/API calls, free-credit usage, hosted search/RAG, or managed-RAG integration.
- No plugin, MCP, hook, or dependency installation from this URL set.
- No automatic Skill rewrite or self-improving loop without replay, qualifier, manifest validation,
  and human accept/reject.
- No source-bundle promotion from ChatGPT/X-derived summaries without primary source restoration.
- No new memory architecture Markdown file from this checkpoint.

Governance status: source-intake checkpoint plus no durable architecture decision.
