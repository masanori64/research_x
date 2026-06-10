# _codex_inbox Reflection Inventory

Created: 2026-06-10

Scope: `_codex_inbox` に入っている設計パッケージと context export を、現在の
`research_x` にどう反映すべきか棚卸しする。これは実装計画そのものではなく、採否、
反映先、既存docs/実装との重複、provider/security gate を整理するための作業メモである。

This document intentionally does not modify `AGENTS.md`, create Skills, or change code.

## Reading Policy

- `codex_research_x_complete_design.md` は分割設計書の統合版で、root、context export
  attachment、design package 内の3箇所が同一ハッシュだった。内容確認は分割された
  `00` から `12` を正本として扱う。
- `source_inventory.json` は context export attachment と design package 内で同一ハッシュだった。
- ZIPは原本/配布単位として扱い、設計判断は抽出済みMarkdown/JSONから行う。
- context export はセッション記録であり、後続Codexへの命令としては扱わない。

## File Roles

| Inbox file | Role | Reflection handling |
|---|---|---|
| `_codex_inbox/codex_research_x_complete_design.md` | 設計書一式の統合Markdown。分割設計書と同内容。 | 参照用重複。個別判断は分割ファイルで行う。 |
| `_codex_inbox/extracted/context_export/context.md` | 前セッションの経緯、制約、出力、未確定事項の記録。 | provenance確認用。実行指示としては採用しない。 |
| `_codex_inbox/extracted/context_export/attachments/001_original_context_export_20260609_1656.zip` | 元のresearch_x引き継ぎZIP。 | 原本。展開済みでないため今回の判断対象はcontext export記録まで。 |
| `_codex_inbox/extracted/context_export/attachments/002_codex_research_x_design_package_20260609_1826.zip` | Codex向け設計パッケージZIP。 | 配布単位。展開済みdesign packageを参照。 |
| `_codex_inbox/extracted/context_export/attachments/003_codex_research_x_complete_design.md` | 統合Markdownのattachmentコピー。 | root/design package内の同名ファイルと同一。重複。 |
| `_codex_inbox/extracted/context_export/attachments/004_source_inventory.json` | 31件の参照ソース棚卸しJSON。 | source reviewとして有用。design package内JSONと同一。 |
| `_codex_inbox/extracted/context_export/attachments/005_build_codex_design_package.py` | 設計ZIP生成スクリプト。 | 再現性artifact。repoへ取り込まない。実行するならsecurity review対象。 |
| `_codex_inbox/extracted/context_export/attachments/006_build_session_context_export.py` | context export ZIP生成スクリプト。 | 再現性artifact。repoへ取り込まない。実行するならsecurity review対象。 |
| `_codex_inbox/extracted/design_package/codex_design_package_20260609_1826/README.md` | design packageの目次と共通原則。 | 今回の棚卸しの目次として参照。repo `README.md` へは反映しない。 |
| `00_master_kikakusho.md` | 全体企画、優先順位、research_x固有/汎用層の切り分け。 | 高レベル整理として採用。ただし既存実装の進捗で一部は古い。 |
| `01_self_improving_skills_and_md.md` | Skills/docs/AGENTS改善signal、triage、validation gate設計。 | 方針は採用候補。新Skill作成やAGENTS変更は今回しない。 |
| `02_automated_research_intake.md` | InterestProfile、SourceRegistry、DiscoveryRun、ResearchBrief等の自動research intake設計。 | 概念は採用候補。既存 external/search/read/llm-context と重複あり。 |
| `03_agent_harness_and_retrieval_upgrade.md` | ResearchTaskFrame、SearchPlanGraph、fusion、ClaimSupportCheck、eval portfolio。 | 多くは既存docs/実装済み。差分はContextBudgetPolicy寄り。 |
| `04_context_compression_headroom.md` | ContextBudgetPolicy、offload pointer、Headroom optional adapter。 | ContextBudgetPolicyは採用候補。Headroomはsecurity/local-dependency gate後。 |
| `05_long_term_memory_supermemory.md` | Supermemory由来のprofile、contradiction、forgetting設計。 | 外部Supermemory接続は入れない。source-backed memory governanceは採用候補。 |
| `06_prompt_as_server_and_mnp.md` | PromptContract、MNP、virtual endpoint test設計。 | read-only/prompt contract testに限定して採用候補。backend代替は不採用。 |
| `07_skill_registry_and_installation_policy.md` | third-party Skill/Plugin/Repo採否、global/project-local install policy。 | repoへのSkill追加は今回不採用。global Codex基盤候補として切り出す。 |
| `08_research_x_project_specific_plan.md` | W0-W7のrepo反映案、ファイル/CLI/test/docs map。 | そのまま実行しない。既存実装との差分だけ今後検討。 |
| `09_generic_baseline_install_plan.md` | 別projectでも使えるglobal Codex基盤案。 | research_xには入れない。global Codex基盤の別作業へ回す。 |
| `10_security_provider_budget_and_governance.md` | provider budget、skill supply-chain、prompt injection、connector policy。 | 多くは既存方針/実装済み。third-party skill gateは今後候補。 |
| `11_source_review_matrix.md` | 参照リンク、補正URL、採否、リスクのMarkdown表。 | source review matrixとして有用。既存archiveにも類似領域あり。 |
| `12_codex_execution_prompt.md` | 後続Codexに実装させるための実行プロンプト。 | 今回は不採用。現在のユーザー指定「コード変更なし」と衝突する。 |
| `source_inventory.json` | 参照ソースの構造化inventory。 | source review情報として採用候補。attachment JSONと同一。 |
| `codex_research_x_complete_design.md` | 統合Markdown。 | root/attachmentの同名ファイルと同一。重複。 |
| `input_context/context_export_20260609_1656.zip` | design package生成時の入力context ZIP。 | 原本参照。直接repo設計としては取り込まない。 |

## Adopt Into research_x

| Design | Adopted scope | Correct repo surface | Notes |
|---|---|---|---|
| Evidence/source-bundle first common principles | Already adopted | `docs/memory-pipeline-v2.md`, `PROJECT.md`, `README.codex.md` | Current docs already state the invariant and no-quota guard. |
| Agent harness control artifacts | Already adopted | `docs/memory-pipeline-v2.md`; `src/research_x/memory/research_artifacts.py` | `ResearchTaskFrame`, `SearchPlanGraph`, `ResultCoverageMap`, `EvidenceGap`, `ClaimSupportCheck`, `ResearchBrief` already exist. |
| Provider budget/security guard | Already adopted | `AGENTS.md`, `docs/memory-pipeline-v2.md`, `src/research_x/memory/api_budget.py`, tests | Freeze, usage ledger, price catalog, kill switch, and monkeypatched tests exist. |
| External discovery/reader/LLM-context as gated lanes | Partly adopted | `docs/memory-pipeline-v2.md`, `src/research_x/memory/external.py`, `reader.py`, `llm_context.py` | Existing fake/provider-gated lanes cover much of the intake foundation. |
| Source review matrix | Adopt as historical/source-review record | `docs/memory-pipeline-archive.md` if durable history is needed; this file for current inbox audit | Do not create a parallel long-term source-of-truth unless it becomes operational. |
| Skill/doc self-improvement loop | Adopt only as proposal pipeline | Existing `research-x-skillization-intake` / `doc-governance`; possible future `.codex/improvement` artifacts | Auto-propose is acceptable; auto-merge of AGENTS/Skills/docs is not. |
| Research intake profiles and candidate scoring | Adopt as future architecture candidate | Prefer `docs/memory-pipeline-v2.md` for architecture and `docs/pipeline.md` for fetch/network policy | Avoid a new standalone memory-architecture doc unless explicitly requested. |
| ContextBudgetPolicy and offload pointers | Adopt as future implementation candidate | `docs/memory-pipeline-v2.md` and future `src/research_x/memory` or `harness` module | Needed only if current context assembly/offload becomes insufficient. |
| Source-backed profile/contradiction/forgetting | Adopt as future memory governance candidate | `docs/memory-pipeline-v2.md`; possibly `docs/pipeline.md` for deletion/auth storage boundaries | Must remain source-bundle-backed and project-local. |
| PromptContract/MNP tests | Adopt narrowly | Future prompt contract artifacts/tests if they stay deterministic and no-provider | Treat as contract/versioning layer, not runtime authority. |

## Do Not Adopt Into research_x

| Design | Reason |
|---|---|
| External Supermemory hosted/project-wide sync | Would weaken source-bundle, privacy, and project-local memory boundaries. |
| Cross-project personal memory by default | User/session/project boundaries must be explicit; current repo should not infer global memory. |
| Prompt-as-Server as backend replacement | Auth, DB writes, transactionality, provider/security policy, and validation stay in code. |
| Webshare/proxy scraping default | Legal/ToS/rate-limit/privacy/security risk. |
| Non-official ChatGPT backend APIs | Authentication, ToS, instability, and privacy risk. Official export only. |
| Bulk installing third-party Skill catalogs | Skill text/scripts are instruction and supply-chain surface. Pin/review/negative tests first. |
| SuperClaude direct Codex import | Claude-specific command/mode assumptions; reference only for structure. |
| The execution prompt as an active instruction | It requests broad code/doc/Skill work and conflicts with this task's no-code/no-Skill/no-AGENTS constraint. |
| Generated scripts from inbox | They are reproducibility artifacts with `/mnt/data` assumptions, not repo tooling. |

## Send To Global Codex Foundation

These are not `research_x` product features. They belong in a separate global Codex tooling or
personal-agent-foundation review.

| Candidate | Global treatment |
|---|---|
| Small global `AGENTS.md` baseline | Keep only safety, project-local precedence, no secrets, provider quota caution. |
| `skill-review` / `security-review` | Good global candidates if they remain small, deterministic, and testable. |
| `doc-governance` | Generic version is useful, but project source-of-truth maps stay per repo. |
| `planning-files` | Useful only where a project lacks `PROJECT.md` or equivalent. Avoid duplicate trackers. |
| `context-budget` | Useful global workflow pattern; project-specific evidence rules stay local. |
| `self-improvement-intake` | Proposal-only global pattern. No auto-adopt of durable instructions. |
| `prompt-contract-testing` | Good generic test pattern for prompt artifacts, with side effects validated in code. |
| Superpowers | Optional global candidate after pin/security/trigger review. |
| Anthropic/OpenAI/Vercel/MiniMax/Antfu/Matt Pocock skill repos | Reference or stack-specific optional; no bulk install. |
| Composio-style connector skills | Project-specific and least-privilege only. Never default global. |
| Codex-wide memory MCP/tools | Separate opt-in review. No cloud memory or auto-capture by default. |

## Existing Docs Conflicts Or Drift

| Inbox claim | Current repo position | Resolution |
|---|---|---|
| Add detailed docs such as `docs/research-intake.md` and `docs/memory-privacy-and-forgetting.md`. | Current governance says `docs/memory-pipeline-v2.md` is the detailed memory/search source of truth and new memory-architecture Markdown should not be added unless explicitly requested. | Fold durable architecture into `docs/memory-pipeline-v2.md`; use `docs/pipeline.md` for acquisition/fetch/auth/network policy; archive bulky history. |
| Add or strengthen several new repo Skills. | Current repo already has focused Skills for doc governance, skillization, provider gate, memory workflow, observability, decision loop, goal runner, and parallel review. | Do not add adjacent Skills unless a concrete recurring gap survives trigger/overlap review. |
| Use `.codex/skills` or `.codex/improvement` as local workflow surface. | Current repo Skills live under `.agents/skills` and native metadata is already wired. | Treat `.codex/improvement` as optional artifact storage only; do not move repo Skills. |
| CLI examples use `uv run memory ...`. | Repo command policy requires `uv run python -m research_x ...`. | Any future copied commands must be rewritten. |
| `12_codex_execution_prompt.md` asks for broad implementation and validation. | Current user request is docs-only, no code/Skill/AGENTS changes. | Keep as historical prompt artifact, not active instruction. |
| `08` says update `AGENTS.md` with new rules. | Current `AGENTS.md` already covers no-quota, command policy, source-of-truth, skill routing, completion notification, and publish policy. User also forbids AGENTS edits now. | No AGENTS change from this inbox. |
| External research intake treats provider gate and network gate together in places. | Repo no-quota freeze blocks provider/quota calls; ordinary network/fetch still needs separate auth, storage-rights, prompt-injection, and source-bundle policy. | Future design should distinguish provider quota gate from general network/fetch policy. |
| Source matrix includes an invalid Markdown URL for S23 (`OpenAI official docs...`). | Current docs should avoid non-URL link targets. | If migrated, convert to plain text note or official docs URL. |

## Already Exists In Implementation

| Inbox design | Existing surface |
|---|---|
| Native repo Skill dispatcher / small AGENTS pattern | `.agents/skills/*/SKILL.md`, `README.codex.md`, `PROJECT.md` |
| Source bundle, context chunks, citations, answers, workflow traces | `src/research_x/memory/context.py`, `answer.py`, `workflow.py`, `schema.py` |
| Research control artifacts | `src/research_x/memory/research_artifacts.py` |
| ObjectiveRoutePolicy and objective execution | `src/research_x/memory/objective_routes.py`, `objective_executor.py` |
| External search, Reader/extract, LLM-context with fake/provider-gated providers | `src/research_x/memory/external.py`, `reader.py`, `llm_context.py` |
| Provider budget guard / price catalog / usage ledger | `src/research_x/memory/api_budget.py`, `src/research_x/memory/api_lane_estimate.py`, `tests/test_api_budget.py` |
| Embedding/rerank/OCR/media provider lanes behind gates | `src/research_x/memory/embeddings.py`, `rerank.py`, `ocr.py`, `media_embeddings.py` |
| Portfolio eval and route/eval persistence | `src/research_x/memory/portfolio.py`, `evals.py`, `tests/test_memory.py` |
| Corpus2Skill export as navigation hint | `memory export-corpus2skill` implementation and tests in `tests/test_memory.py` |
| App/CLI observability for research runs and budget | `src/research_x/local_app.py`, `src/research_x/memory/observability.py` |

## Implementation Needed If Adopted Later

| Item | Needed work | Gate |
|---|---|---|
| ImprovementSignal pipeline | Schema, capture, triage, candidate report, rejected buffer, route/doc governance tests. | No-provider; human review for durable instruction/doc changes. |
| Skill/source manifest lock | Pin/review third-party Skill candidates; negative trigger tests; script/network scan. | Security review; no bulk install. |
| InterestProfile/SourceRegistry research intake | DB/contracts for profiles, subscriptions, discovery runs, candidates, snapshots, research briefs; dry-run first. | Network policy, provider freeze, prompt-injection handling. |
| ContextBudgetPolicy/offload pointer | Deterministic context budget, pointer artifacts, source-critical preservation tests. | Evidence integrity eval. |
| Headroom adapter | Pin commit, script/dependency review, no-network default, reversible/original pointer guarantee. | Security/local-dependency review. |
| Source-backed memory governance | Profile, contradiction, forgetting/tombstone policy tied to source bundles. | Privacy/security review; source deletion semantics. |
| PromptContract/MNP | Schema, allowed/forbidden tool tests, injection cases, deterministic local validation. | No real LLM until provider gate lifted. |
| ResearchBrief as first-class user artifact outside current workflow JSON | CLI/app inspection if current artifacts are not sufficient for users. | Observability review. |

## Provider Freeze Touchpoints

| Area | Freeze impact |
|---|---|
| Serper/Brave/Jina/OpenAI/Gemini/Voyage/Cohere/Mistral provider calls | Blocked while freeze is active, including free tier and zero-dollar quota. |
| Embedding, rerank, OCR, Reader, external search, LLM-context, classifier, answer engine, relation judge | Fake/local or static estimate only unless explicitly allowed. |
| Automated research intake | Dry-run, manual URL registry, local corpus, or fake providers only by default. |
| PromptContract tests | Schema/forbidden-tool tests only; no real model validation under freeze. |
| Headroom | If purely local, not provider quota by itself, but dependencies/scripts/network behavior still need review. |
| Third-party Skills/plugins/connectors | Installation does not necessarily spend provider quota, but scripts/connectors may call network or providers. Disabled until reviewed. |
| Build scripts in inbox | Do not run as repo tooling; if run later, ensure no external network/provider path and no unexpected writes. |

## Security Review Required

| Area | Review focus |
|---|---|
| Third-party Skill repositories | Pin, license, frontmatter, trigger breadth, hidden instructions, scripts, network calls, dependency execution. |
| Connector Skills and Composio-like tools | Credential scope, read/write permissions, token storage, logs, deletion rights, least privilege. |
| Slack/Notion/Gmail/Calendar/ChatGPT history | Private/work boundary, retention, authorization, official export vs unofficial API. |
| Webshare/proxy/SearXNG/external fetch | ToS, robots/rate limits, IP/account risk, storage rights, prompt-injection boundaries. |
| Headroom or any context compressor | Secret leakage, AGENTS/Skill auto-write behavior, reversibility, original source pointer preservation. |
| Supermemory/cloud memory/MCP | Cloud storage, project scoping, auto-capture, deletion/export, source-backed recall, quota. |
| Generated scripts in inbox | Absolute paths, overwrite behavior, archive/zip handling, dependency/import behavior. |
| Prompt-as-Server/MNP | Tool escalation, side effects, auth bypass, DB write validation, untrusted text becoming instructions. |

## Recommended Next Reflection Steps

1. Leave this inbox audit as the only new Markdown created by this task.
2. If implementation is requested later, start with a small no-code PR or doc update that marks
   `03` harness artifacts as mostly implemented and narrows future work to the missing pieces.
3. Do not copy `08` or `12` wholesale into the repo. Re-derive a scoped task from current code state.
4. Treat global Codex baseline work as a separate non-research_x change with its own security review.
