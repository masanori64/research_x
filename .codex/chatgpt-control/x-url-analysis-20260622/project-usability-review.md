# Project Usability Review

Date: 2026-06-22
Input classification: `.codex/chatgpt-control/x-url-analysis-20260622/classification.md`
ChatGPT thread: https://chatgpt.com/c/6a38f872-8fac-83ee-bb73-6e498f9f1862

## Status

This is a project-use review of the ChatGPT/X URL analysis, not citation-ready evidence and not a
durable architecture decision. No provider APIs, installs, plugin enables, MCP configuration
changes, or real external search providers were executed for verification.

The result should stay `source-intake-only` / `no-durable-surface` until a separate task restores
primary sources into the normal intake path or opens a scoped implementation/eval.

Sub-agent usage: four bounded read-only agents were used for retrieval/RAG, provider substrate,
Skill/harness, and local codebase mapping. All were closed after integration.

## Verdict Legend

- `use-now`: useful immediately as a checklist/eval lens against existing code; no new dependency.
- `use-now-narrow`: one narrow metric or rule is useful; the full method is not adopted.
- `source-intake-only`: keep as source candidate; no project behavior changes yet.
- `local-dependency`: plausible future local dependency/backend; requires install gate and benchmark.
- `provider-gated`: blocked by no-quota/provider policy unless the user explicitly lifts it.
- `codex-foundation-candidate`: useful for Codex Skill/governance work, not memory-search evidence.
- `reference-only`: useful idea or artifact pattern, but no direct adoption path now.
- `not-actionable`: insufficient source/context for a project decision.

## Executive Verdict

Use immediately, without new dependencies:

- LLM-Oriented IR as a denoising/retrieval review checklist.
- SAAS only as local stop-condition metrics: avoid redundant searches after enough evidence.
- VS Code/GitHub Copilot token-efficiency ideas as validation of existing context-budget and tool
  deferral patterns.

Evaluate later only behind gates:

- OCC-RAG as a local answerability/abstention canary after retrieval, not as a retriever.
- Zvec as a local vector/index backend candidate, benchmarked against current SQLite/FTS/relation
  and local vector projection baselines.

Best Codex-foundation candidates:

- SkillAdaptor is the strongest candidate: failed run -> fault step -> responsible Skill ->
  minimal candidate diff -> replay/qualifier -> human accept/reject.
- MUSE-Autoskill and Adaptive Auto-Harness support the same direction: lifecycle-managed Skills,
  harness branches, routing, and human steering. They should inform existing ImprovementSignal and
  Skill governance work, not be installed wholesale.

Do not adopt now:

- Firecrawl Keyless, Google Agentic RAG, Bedrock AgentCore, managed RAG, hosted Reader/search lanes,
  or free-credit services. Free credits are still quota/provider use in this repo.
- Archify, Ponytail, pdgkit, Agentmemory, and other third-party Skill/plugin candidates without
  source review, pinning, install approval, trigger review, and tests.
- Any interpretation that turns ChatGPT/X-derived summaries into evidence.

## Project Fit Matrix

| Candidate | Verdict | Project fit | Blockers / next gate |
|---|---:|---|---|
| LLM-Oriented IR / denoising-first retrieval | `use-now` | Directly matches Evidence/Source Bundle first, citation-ready yield, denoising gates, and source restoration. Use as a review checklist for `portfolio`, `workflow`, and eval reports. | No dependency. Do not create new docs unless it exposes a concrete missing eval. |
| SAAS over-search mitigation | `use-now-narrow` | Useful as route metrics: search count, stop reason, redundant search after sufficiency, evidence-enough before escalation. | Full RL stack is out of scope and likely provider/local-model heavy. |
| VS Code / Copilot token efficiency | `use-now` | Reinforces existing context budget, output offload, tool deferral, and local search of tool metadata. | No code change unless a concrete bulky-output regression appears. |
| OCC-RAG | `local-dependency` | Strong fit as optional post-retrieval answerability/abstention checker over citation-ready context chunks. It maps to `needs_review`, answer citation support, and insufficient-evidence behavior. | Model download/runtime/install, local eval set, answerable/unanswerable/conflicting evidence calibration. Not a retriever or full RAG stack. |
| Alibaba Zvec | `local-dependency` | Plausible local vector/index substrate for project/workspace memory. It maps to `vector_projection` backend work, not prompt/Skill rules. | New native dependency, source review, benchmark against SQLite/FTS/relation/local projection, source-bundle restoration, cold/warm cache behavior. |
| State-Aware RAG / reasoning with memory | `reference-only` | Conceptually supports explicit working memory, gap tracking, route state, and context sufficiency. Existing architecture already follows this direction. | Full method appears training/model/provider-heavy; no directly usable local package confirmed. |
| Google Agentic RAG / RAG Engine | `provider-gated` | Good architecture reference for planner, corpus routing, and sufficient-context loop. | Google Cloud, IAM, billing, model/parser/reranker/grounding charges, provider freeze. |
| Firecrawl Keyless | `provider-gated` | Future external discovery/fetch lane candidate only. Could produce source candidates, never evidence by itself. | Hosted service, credits/rate limits, ToS/storage-rights, source-bundle restoration. |
| Bedrock AgentCore | `provider-gated` | Architecture reference for managed runtime, memory, gateway, browser, code interpreter, observability, and policy. | AWS account/IAM/billing/data-retention/lock-in; provider freeze. |
| External hosted search/RAG providers | `provider-gated` | Current design already has provider roles and API Budget Guard for future lanes. | No real calls under freeze. SearXNG is the only plausible local exception, still a dependency/network gate. |
| JAMEL | `source-intake-only` | Interesting for GUI/browser exploration memory and novelty signals, not current memory-search evidence. | Training/benchmark/runtime heavy; needs a concrete GUI exploration objective before local work. |
| Stale observation masking | `source-intake-only` | Useful warning: context hiding is regime-dependent. It supports route-level eval before any masking/offload policy. | Do not apply universal stale-observation masking without eval by route/model/retriever. |
| RAG Knowledge Hub / multi-source RAG examples | `source-intake-only` | General alignment with multi-source ingestion and source restoration. | Some examples rely on mirrors/extraction choices that need legal/storage-rights review. |
| Agentmemory / persistent coding-agent memory | `skill-source-review-required` | Overlaps Basic Memory, context handoff, planning files, and this repo's local memory goals. | Plugin/MCP/hooks install, lifecycle hooks, data retention, trigger overlap; no install now. |
| Hanno-Lab relevance model / relevance classifier mention | `source-intake-only` | Could map to relevance/rerank/answer-support checks if primary source is restored. | Current source context is too thin. Treat as not actionable until restored. |
| Ontology mention | `not-actionable` | Could matter to relations/entity modeling, but the source context is missing. | Need original context or primary source. |
| WBS/progress visualization | `reference-only` / `future local hardening` | Existing `research-runs`, `show-run`, workflow traces, objective traces, and eval views own this area. | Add only the smallest missing status/trace field after a concrete observability failure. |
| AI code-review responsibility split | `reference-only` | Existing review stance and human-on-the-loop policy already separate local automation from design/architecture judgment. | No durable rule unless repeated review failure appears. |
| `/grill-me` and plan-interview workflows | `reference-only` | Existing decision-loop, goal-runner, human-on-the-loop, and oversight gates cover most of it. | No new Skill. Use only when design ambiguity is genuinely blocking. |
| Over-implementation / Ponytail | `skill-source-review-required` | The useful rule is already mostly present: check existing APIs, stdlib/native features, and current dependencies before adding code. | Ponytail plugin/hooks require source review and install approval; do not install. |
| YAML-to-HTML / structure-plus-renderer | `reference-only` | Good artifact pattern for reports/diagrams/WBS when repeatability matters. | Future renderer work must validate schema and keep evidence separate from presentation. |
| Archify | `reference-only` | Useful as a diagram/report aid for workflow and architecture review. | Generated diagrams are not evidence; install requires Skill/source review and validation against code/traces/docs. |
| pdgkit | `reference-only` | Strong example of deterministic DSL -> validate -> render. Low direct fit unless patent/diagram output becomes a scoped requirement. | Node/npm/MCP dependency and install gate. |
| Visual Skills / AutoVisualSkill | `reference-only` | Good future direction for UI/browser/media workflows where spatial evidence matters. | Requires screenshot storage, privacy boundaries, visual provenance, and verification contracts. Not memory evidence. |
| SkillAdaptor | `codex-foundation-candidate` | Strong fit for ImprovementSignal hardening: localize failure, attribute responsible Skill, propose minimal diff, replay, qualifier, human accept/reject. | Do not auto-edit Skills. Requires local replay/manifest tests and source review before adopting any code. |
| MUSE-Autoskill | `codex-foundation-candidate` | Useful lifecycle model: create/store/reuse/evaluate/refine Skills, with tests and failure cases. | Keep proposal-only. Avoid automatic Skill growth or always-visible metadata bloat. |
| Adaptive Auto-Harness | `codex-foundation-candidate` | Useful for harness tree, solve-time routing, and human steering hooks. | Do not import the harness runtime. Use as design input for existing repo Skills only. |

## Codex Foundation Split

Candidate for later Codex foundation hardening:

- SkillAdaptor-style qualifier loop for Skill updates.
- Skill lifecycle/test/revision-log ideas from MUSE-Autoskill.
- Harness tree/routing/human-steering concepts from Adaptive Auto-Harness.
- Answerability/abstention gate vocabulary from OCC-RAG.
- Structure-plus-renderer artifact pattern from Archify/pdgkit/YAML-to-HTML.

Already covered enough; no new global Skill now:

- Skill hygiene.
- Over-implementation guard.
- Human-on-the-loop oversight gates.
- Decision-loop review.
- Parallel review policy.
- Context handoff/offload and planning files.

Keep gated:

- Any Skill/plugin install.
- Any MCP/hook configuration.
- Any provider/search/Reader/managed-RAG call.
- Any automatic Skill rewrite.

## Original URL Number Mapping

| # | Topic after classification/addendum | Verdict |
|---:|---|---|
| 1 | Firecrawl Keyless | `provider-gated` |
| 2 | VS Code / GitHub Copilot token efficiency | `use-now` via existing context-budget/tool-deferral ideas |
| 3 | Harness overgrowth / decomposition | `reference-only`; already covered by repo Skill boundaries |
| 4 | Self-improving agents and local optimum | `codex-foundation-candidate`; covered by ImprovementSignal direction |
| 5 | YAML-to-HTML / structure-view split | `reference-only` artifact pattern |
| 6 | RAG Knowledge Hub | `source-intake-only` |
| 7 | OCC-RAG | `local-dependency` answerability canary |
| 8 | Stale observation masking | `source-intake-only`; no universal masking |
| 9 | Ontology mention | `not-actionable` |
| 10 | Archify | `reference-only` / source-review before install |
| 11 | WBS Viewer | `future local hardening` only after observability gap |
| 12 | Agentmemory | `skill-source-review-required`; overlap with existing memory/handoff surfaces |
| 13 | Adaptive Auto-Harness | `codex-foundation-candidate` |
| 14 | SkillAdaptor | `codex-foundation-candidate`; strongest |
| 15 | Devin/Manus mention | `not-actionable` |
| 16 | Alibaba Zvec | `local-dependency` backend benchmark candidate |
| 17 | SAAS over-search | `use-now-narrow` for stop-condition metrics |
| 18 | Amazon State-Aware RAG | `reference-only` |
| 19 | AI code-review responsibility split | `reference-only`; already covered |
| 20 | `/grill-me` | `reference-only`; no new Skill |
| 21 | grill-me + plan parallel review | `reference-only`; covered by decision/parallel review |
| 22 | Hanno-Lab relevance model mention | `source-intake-only` until restored |
| 23 | JAMEL | `source-intake-only` / future GUI exploration research |
| 24 | MUSE-Autoskill | `codex-foundation-candidate` |
| 25 | Internal Slack/RAG feedback loop on Bedrock | `provider-gated`; concept already covered |
| 26 | Google Agentic RAG | `provider-gated` plus architecture reference |
| 27 | Unknown | `not-actionable` |
| 28 | State separated from LLM | `reference-only`; same family as State-Aware RAG |
| 29 | Visual Skills | `reference-only`; future multimodal Skill governance |
| 30 | Decision rules as Markdown | `reference-only`; existing Skill/AGENTS surfaces own this |
| 31 | Bedrock AgentCore harness | `provider-gated` |
| 32 | LLM-Oriented IR | `use-now` checklist |
| 33 | Ponytail plugin | `skill-source-review-required`; no install |
| 34 | pdgkit article | `reference-only` |
| 35 | pdgkit OSS | `reference-only` |

## Existing `research_x` Anchors

- Evidence/source-bundle first and provider-gated architecture:
  `docs/memory-pipeline-v2.md`, `PROJECT.md`, `README.codex.md`.
- Denoising and citation-ready gates:
  `src/research_x/memory/portfolio.py`.
- Answer/citation/needs-review behavior:
  `src/research_x/memory/answer.py`, `src/research_x/memory/workflow.py`.
- Context budgeting:
  `src/research_x/memory/context_budget.py`,
  `tests/harness/test_context_budget_policy.py`.
- Provider budget and freeze enforcement:
  `src/research_x/memory/api_budget.py`, `tests/test_api_budget.py`,
  `src/research_x/research_intake/pipeline.py`.
- Local vector projection baseline:
  `src/research_x/memory/vector_projection.py` currently supports `numpy` and optional `turbovec`,
  not Zvec.
- Skill/source governance and proposal-only improvement:
  `.codex/vendor_sources.lock.md`, `.codex/skill_manifest.lock`,
  `scripts/validate_skill_manifest.py`,
  `src/research_x/codex_improvement/pipeline.py`,
  `tests/test_codex_improvement.py`.

## Source Index

Primary or near-primary sources checked during this review:

- OCC-RAG paper: https://arxiv.org/abs/2606.00683
- OCC-RAG repository: https://github.com/optimal-cognitive-core/OCC-RAG
- LLM-Oriented IR: https://arxiv.org/abs/2605.00505
- SAAS paper: https://arxiv.org/abs/2605.29796
- SAAS repository: https://github.com/XMUDeepLIT/SAAS
- Amazon State-Aware RAG: https://www.amazon.science/publications/reasoning-with-memory-adaptive-information-management-for-retrieval-augmented-generation
- Google Agentic RAG: https://research.google/blog/unlocking-dependable-responses-with-gemini-enterprise-agent-platforms-agentic-rag/
- Firecrawl Keyless: https://www.firecrawl.dev/blog/firecrawl-keyless-launch
- Firecrawl pricing: https://www.firecrawl.dev/pricing
- Bedrock AgentCore overview: https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/what-is-bedrock-agentcore.html
- Bedrock AgentCore pricing: https://aws.amazon.com/bedrock/agentcore/pricing/
- VS Code token efficiency: https://code.visualstudio.com/blogs/2026/06/17/improving-token-efficiency-in-github-copilot
- GitHub Copilot context handling: https://github.blog/ai-and-ml/github-copilot/getting-more-from-each-token-how-copilot-improves-context-handling-and-model-routing/
- Stale observation masking: https://arxiv.org/abs/2606.00408
- JAMEL paper: https://arxiv.org/html/2606.01528v1
- JAMEL repository: https://github.com/MobileLLM/JAMEL
- MUSE-Autoskill: https://arxiv.org/abs/2605.27366
- Adaptive Auto-Harness: https://arxiv.org/abs/2606.01770
- AdaptiveHarness repository: https://github.com/A-EVO-Lab/AdaptiveHarness
- SkillAdaptor paper/repository: https://arxiv.org/abs/2606.01311 and https://github.com/zjunlp/SkillAdaptor
- Alibaba Zvec: https://github.com/alibaba/zvec
- Archify: https://github.com/tt-a1i/archify
- Ponytail: https://github.com/DietrichGebert/ponytail
- Matt Pocock skills / grill-me: https://github.com/mattpocock/skills and https://www.aihero.dev/skills-grill-me
- pdgkit: https://github.com/shibayamalicht/pdgkit
- Visual Skills: https://arxiv.org/html/2606.01414v1
- Agentmemory: https://github.com/rohitg00/agentmemory

## GPT Pro Follow-Up On Opaque Deferrals

Raw follow-up output:
`.codex/chatgpt-control/x-url-analysis-20260622/chatgpt-opaque-deferred-followup.md`

This follow-up was sent once to the existing ChatGPT thread after the user explicitly requested
GPT Pro search on unresolved/opaque non-promotions. A temporary Wi-Fi interruption occurred while
GPT Pro was searching; after reconnection, the same thread was reopened and the original submitted
turn continued. No duplicate prompt was sent.

The follow-up clarified that most opaque deferrals now have transparent blockers or promotion
conditions:

- Strongest remaining promotion candidates: SkillAdaptor, OCC-RAG, Zvec, Hanno-Lab Bosun, and
  Agentmemory.
- Rule/eval absorption candidates: stale observation masking, YAML-to-HTML structure/view split,
  Ponytail-style over-implementation guard, and WBS/progress visualization patterns.
- Future limited-domain candidates: Visual Skills, Archify, pdgkit, and JAMEL.
- Still not actionable: ontology mention and Devin/Manus mention, because the original source
  context does not identify a concrete project-use candidate.
- RAG Knowledge Hub is now a transparent non-promotion: useful as a multi-source RAG example, but
  blocked by Freedium-style extraction, hosted Qdrant/API dependencies, HF Spaces/example status,
  and storage-rights/source-restoration concerns.

Updated intake priority from the follow-up:

1. SkillAdaptor: source intake for ImprovementSignal fault localization, responsible-Skill
   attribution, replay qualifier, and human accept/reject governance.
2. OCC-RAG: source intake for local answerability/abstention canary design after retrieval.
3. Zvec: source intake for a local backend benchmark gate against SQLite/FTS/current local vector
   projection and optional Turbovec.
4. Hanno-Lab Bosun: new local-eval candidate for relevance/judgment, citation support, dedup, and
   memory graph edge-warrant tests.
5. Agentmemory: source review candidate only, useful for comparing hook/MCP/auto-capture/decay and
   search/inject risks against the existing local memory approach.

The follow-up did not promote any external install, provider call, plugin enablement, MCP
configuration, or automatic Skill rewrite. Its output remains consultation material until sources
are restored and verified through the normal project intake path.

## Original Recommended Next Actions

Post Phase 1-8 update:

- The code-oriented first-wave actions below have been executed or gated through
  `.codex/chatgpt-control/x-url-analysis-20260622/phase-gate-report.md`.
- The current residual 35-item decision is now
  `.codex/chatgpt-control/x-url-analysis-20260622/current-decision-summary.md`.
- Do not treat this older next-action list as the active queue after Phase 1-8.

1. Do not implement or install anything from this list as part of this review.
2. If the next task is source intake, start with SkillAdaptor, OCC-RAG, Zvec, Hanno-Lab Bosun, and
   Agentmemory because the follow-up made their blockers and promotion gates the clearest.
3. If the next task is code, the smallest useful local changes would be tests/evals, not provider
   calls:
   - OCC-RAG-shaped answerable/unanswerable/conflicting-evidence fixture cases.
   - SAAS-shaped redundant-search/stop-condition audit cases.
   - SkillAdaptor-shaped ImprovementSignal fields for fault step, responsible artifact, replay, and
     qualifier result.
   - Hanno-Lab Bosun-shaped relevance/citation-support/dedup/conflict fixture cases.
   - Zvec benchmark harness stub that compares against existing local backends without making Zvec
     default.
4. Keep provider lanes frozen until the user explicitly opens a provider/quota experiment.
