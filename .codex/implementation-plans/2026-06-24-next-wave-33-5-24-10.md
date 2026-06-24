# research_x next wave 33/5/24/10 implementation plan

Date: 2026-06-24
Source: ChatGPT Pro visible web consultation
Thread: https://chatgpt.com/c/6a3b2a94-aba8-83ee-abf2-908a28cce179
Evidence status: not_evidence; planning/control artifact only.

research_x 次 wave 候補 33 / 5 / 24 / 10 実装計画書

詳細版の Markdown も作成しました。保存用はこちらです。
research_x_next_wave_33_5_24_10_plan.md

1. 結論

候補 33 / 5 / 24 / 10 は、外部候補をそのまま導入するのではなく、research_x の現行正本である WBS operational state / PDG structural flow / Pointer Map / thin Markdown に引き直して扱うべきです。

item	候補	判定	実装方針
5	YAML-to-HTML structure-view split	今すぐ実装	third-party plugin ではなく、repo-owned の構造化 artifact schema + deterministic safe HTML renderer として実装する。
24	MUSE-Autoskill lifecycle input	今すぐ実装	automatic Skill growth ではなく、proposal-only の Skill lifecycle input / replay / qualifier / human decision gate として実装する。
33	Ponytail over-implementation guard	local eval/canary	Ponytail plugin/hook は入れない。repo-owned の over-implementation guard canary として、実装前 review/eval にする。
10	Archify workflow diagram aid	reference only	Archify は導入しない。diagram は review artifact に固定し、PDG / renderer / consistency check の boundary hardening にだけ使う。

これは「保守寄りに逃げる」判断ではありません。むしろ、外部 plugin / Skill / hook / MCP を入れずに、使える設計だけを research_x の正本構造へ吸収する実装方針です。

2. 固定する前提

維持する evidence chain は以下です。

raw source -> searchable document -> search result -> source bundle
-> context chunk -> citation -> answer

WBS、PDG、SVG、Pointer Map、HTML view、ChatGPT/GPT Pro output、X URL は evidence ではありません。これらは control / planning / review artifact です。

また、no-quota provider freeze 中なので、以下は実装対象に入れてもすべて stop gate 扱いです。

provider/API/search/Reader/OCR/LLM/model calls
dependency install
plugin install
MCP enablement
hook enablement
third-party Skill install
automatic Skill growth
generated diagram as evidence
3. 情報アーキテクチャへの組み込み
WBS

既存の X/GPT 35-item intake 配下の item 5 / 10 / 24 / 33 は、source candidate 履歴として残します。これらを一般 workflow 名には昇格しません。

実装作業は別 leaf として追加します。

推奨追加先:

tools/wbs_viewer/projects/research-x-work-state.json

Codex foundation adjuncts
  - Structure-view split local renderer        source_items: [5]
  - Skill lifecycle input gate                 source_items: [24]
  - Over-implementation guard canary           source_items: [33]

Visual context offload lane / Future local hardening
  - Diagram review boundary hardening          source_items: [10]

新規 implementation leaf は item を持たせず、source_items で元候補を指します。item は 35-item intake の履歴識別子としてのみ維持します。

各 leaf は最低限、以下を満たします。

JSON
{
  "owner_plane": "wbs",
  "artifact_layer": "artifact_renderer | codex_foundation | guard_canary | structure_review",
  "decision_band": "local_implementation | local_eval_canary | reference_only_boundary",
  "gate": "local_artifact_schema_renderer | codex_foundation_design_only | no_plugin_no_hook | source_review_before_install",
  "status": "active | complete | blocked | closed | archived",
  "evidence_status": "not_evidence",
  "answer_support_allowed": false,
  "source_items": [5],
  "stop_condition": "WBS/PDG/Pointer/HTML/SVG を evidence または answer support として使う変更が出たら停止。"
}
PDG

追加する project-owned PDG は多くても2つに絞ります。

docs/pdg/control-artifact-structure-view.pdg
docs/pdg/skill-lifecycle-governance.pdg

control-artifact-structure-view.pdg は、structured control data から safe HTML review artifact までの流れを持ちます。

structured control data
-> schema validate
-> render safe HTML
-> update pointer map
-> review-only output
-> stop if evidence claim / external script / fetch / storage

skill-lifecycle-governance.pdg は、MUSE-Autoskill と Ponytail の有用部分をまとめます。

failed run / user request / review finding
-> lifecycle input
-> ImprovementSignal
-> replay / qualifier
-> human accept / reject
-> manifest validation
-> stop if automatic Skill growth / hook / plugin / MCP / provider

Archify 専用 PDG は作りません。item 10 は diagram boundary として control-artifact-structure-view.pdg と既存 source-intake-gate-flow.pdg に吸収します。

Pointer Map

.codex/context_offloads/pointer-map.json には、新規 artifact をすべて not_evidence: true で登録します。

対象:

docs/pdg/control-artifact-structure-view.pdg
docs/pdg/out/control-artifact-structure-view.svg
docs/pdg/skill-lifecycle-governance.pdg
docs/pdg/out/skill-lifecycle-governance.svg
src/research_x/control_artifacts/renderer.py
src/research_x/codex_improvement/skill_lifecycle.py
src/research_x/codex_improvement/overimplementation_guard.py

hash / char_count / byte_count が不一致なら、その pointer は使いません。

Markdown

PROJECT.md と README.codex.md は肥大化させません。今回 docs/memory-pipeline-v2.md を変更する必要もありません。evidence architecture の変更ではなく、control artifact と Codex foundation の hardening だからです。

この実装計画を repo に保存する場合は、active tracker にせず、例えば以下に保存します。

.codex/implementation-plans/2026-06-24-next-wave-33-5-24-10.md

そのうえで Pointer Map に not_evidence: true で登録します。

4. Phase 0: 共通 boundary lock
owner surface
tools/wbs_viewer/projects/research-x-work-state.json
.codex/context_offloads/pointer-map.json
docs/pdg/*.pdg
tests/test_research_x_work_state_wbs.py
tests/test_markdown_information_architecture.py
実装するファイル種別

JSON、PDG、Python tests。Markdown は原則追加しません。

test

追加または更新:

tests/test_research_x_work_state_wbs.py
tests/test_pointer_map_not_evidence.py
tests/test_control_artifact_boundaries.py

検査内容:

- implementation leaf は item ではなく source_items を持つ
- WBS leaf は answer_support_allowed: false
- Pointer entries は not_evidence: true
- WBS/PDG/SVG/HTML/Pointer を citation にできない
- Markdown thinness を維持
stop gate
WBS note に長い判断理由を書く
WBS/PDG/SVG/HTML/Pointer を evidence 扱いする
pdgkit validate/render のために install しようとする
done criteria
WBS / PDG / Pointer / Markdown の役割分離が test で固定されている
provider/install/hook/MCP なしで test が通る
5. Phase 1: item 5 — Structure-view split local renderer
判定

今すぐ実装。

YAML-to-HTML plugin は入れません。repo-owned の ControlArtifactView schema と safe HTML renderer を実装します。

owner surface
src/research_x/control_artifacts/model.py
src/research_x/control_artifacts/renderer.py
src/research_x/control_artifacts/sanitize.py
tests/fixtures/control_artifacts/
tests/test_control_artifact_structure_view.py
docs/pdg/control-artifact-structure-view.pdg
tools/wbs_viewer/projects/research-x-work-state.json
.codex/context_offloads/pointer-map.json
実装内容

ControlArtifactView schema を定義します。

必須 field:

view_id
view_kind
title
generated_at
owner_plane
source_artifacts
sections
gates
not_evidence
answer_support_allowed

renderer は self-contained HTML を返します。

禁止:

<script>
fetch
XMLHttpRequest
localStorage
sessionStorage
external CSS/JS
remote URL fetch

HTML の先頭には必ず以下の趣旨の banner を出します。

Not evidence / Review artifact only

YAML parser は Python stdlib にないため、Codex は最初に pyproject.toml / uv.lock を確認します。既存依存に YAML parser がある場合だけ YAML input を有効化します。なければ canonical input は JSON とし、YAML front-end は dependency gate 付き backlog にします。

test
tests/test_control_artifact_structure_view.py

検査内容:

valid fixture から deterministic HTML を生成できる
output に Not evidence banner がある
output に script/fetch/storage/external URL がない
answer_support_allowed: true の input を reject する
WBS/PDG/Pointer/SVG/HTML を citation/evidence として渡す input を reject する
stop gate
HTML を evidence / citation / source bundle の代替にする
YAML support のために dependency install する
third-party YAML-to-HTML plugin を入れる
external script/network/storage を使う
done criteria
safe HTML review view が deterministic に生成できる
evidence chain に触れない
WBS/PDG/Pointer の review surface としてのみ使われる
6. Phase 2: item 24 — MUSE-Autoskill lifecycle input
判定

今すぐ実装。

ただし automatic Skill growth ではありません。proposal-only lifecycle input として実装します。

owner surface
src/research_x/codex_improvement/pipeline.py
src/research_x/codex_improvement/skill_lifecycle.py
tests/test_codex_improvement.py
tests/test_skill_lifecycle_input.py
.agents/skills/research-x-skillization-intake/SKILL.md
.agents/skills/research-x-skill-source-review/SKILL.md

Skill Markdown は、必要な場合だけ短い guard 更新に限定します。README.codex.md や PROJECT.md に lifecycle prose を増やしません。

実装内容

SkillLifecycleInput を追加します。

field:

lifecycle_action: create | reuse | evaluate | refine | retire | reject
trigger: user_request | failed_run | review_finding | manifest_drift | repeated_regression
responsible_artifact
candidate_diff_ref
examples_ref
tests_ref
replay_result
qualifier_result
human_decision: pending | accepted | rejected
source_review_required: bool
auto_apply_allowed: always false

third-party source 由来なら source_review_required: true を強制します。

repo-owned Skill の refine でも、replay / qualifier / human decision が未完なら pending に留めます。

test
tests/test_skill_lifecycle_input.py
tests/test_codex_improvement.py

検査内容:

lifecycle_action enum validation
third-party source は source_review_required: true
auto_apply_allowed を true にできない
replay/qualifier/human_decision 未完の refine は pending
report 生成は Skill file / manifest を書き換えない

manifest または Skill file を触る場合だけ:

PowerShell
uv run python scripts\validate_skill_manifest.py
uv run pytest tests\test_skill_manifest.py
stop gate
Skill file を自動変更する path ができる
manifest を自動変更する
MUSE-Autoskill 由来の third-party code/Skill を import/install する
lifecycle metadata で README/PROJECT を肥大化させる
done criteria
Skill lifecycle を proposal-only artifact として記録できる
replay / qualifier / human accept-reject が明示される
third-party source は自動採用されない
Phase 1 renderer で lifecycle report を review できる
7. Phase 3: item 33 — Over-implementation guard canary
判定

local eval/canary。

Ponytail plugin は source review first ですが、今回 plugin は入れません。使うのは「過剰実装を防ぐ」考え方だけです。

owner surface
src/research_x/codex_improvement/overimplementation_guard.py
src/research_x/codex_improvement/pipeline.py
tests/test_overimplementation_guard.py
tests/fixtures/codex_improvement/overimplementation/*.json
docs/pdg/skill-lifecycle-governance.pdg
tools/wbs_viewer/projects/research-x-work-state.json
実装内容

OverImplementationGuardInput を定義します。

field:

requested_change
existing_surfaces_checked
stdlib_or_native_checked
existing_dependency_checked
delete_or_simplify_option
why_new_code_is_needed
risk_exception: security | accessibility | data_integrity | migration | performance | none
decision: reuse_existing | simplify | implement_new | needs_review | blocked

判定ルール:

existing surface 未確認で implement_new は needs_review
stdlib/native/既存 dependency 未確認で新規 dependency 提案は blocked
plugin/hook/MCP 導入を含む plan は blocked
security/a11y/data_integrity は YAGNI を理由に削れない

Phase 2 の lifecycle report に guard 結果を接続し、Phase 1 の renderer で見えるようにします。

test
tests/test_overimplementation_guard.py

検査内容:

既存 API 未確認の新規 module 提案は needs_review
新規 dependency/install を含む提案は blocked
plugin/hook/MCP を含む提案は blocked
security/a11y/data_integrity 例外は過剰実装扱いで削れない
既存 renderer/schema 再利用案は reuse_existing または simplify
stop gate
Ponytail plugin/hook を入れる
guard を hook として自動実行・自動ブロックする
YAGNI を根拠に security/a11y/data integrity/migration を削る
done criteria
report-only guard canary が local fixture で動く
over-implementation と under-engineering の両方を検出できる
Skill lifecycle / structure-view と連動する
plugin/hook なしで完了する
8. Phase 4: item 10 — Archify reference-only diagram boundary
判定

reference only。

Archify は導入しません。diagram aid としての考え方だけを、PDG / renderer / consistency check の boundary hardening に使います。

owner surface
docs/pdg/control-artifact-structure-view.pdg
docs/pdg/visual-context-offload-lane.pdg
src/research_x/control_artifacts/renderer.py
tests/test_control_artifact_structure_view.py
tests/test_diagram_review_boundary.py
tools/wbs_viewer/projects/research-x-work-state.json
実装内容

DiagramReviewArtifact fixture を Phase 1 の schema に追加します。

field:

diagram_kind: architecture | workflow | sequence | data_flow | lifecycle
source_of_structure: pdg | wbs | pointer_map | reviewed_markdown | code_trace
consistency_refs
not_evidence: true

diagram は review artifact であり、citation / answer support を持てません。workflow / architecture diagram は consistency_refs がない場合 needs_review にします。

test
tests/test_diagram_review_boundary.py

検査内容:

diagram artifact は not_evidence: true 必須
citation / answer_support fields を持つ diagram artifact は rejected
consistency_refs なしの architecture/workflow diagram は needs_review
Archify / plugin / hook / MCP manifest entry が enabled になっていない
stop gate
Archify install
Skill enablement
MCP/hook
export image pipeline を正本化する
diagram から factual answer を作る
code/trace/doc/pointer consistency なしの diagram を正本化する
done criteria
diagram aid は review-only artifact として schema/test で固定される
Archify は source candidate/reference のまま
既存 PDG lane と renderer lane の境界が強化される
9. 依存順序
Phase 0 boundary lock
-> item 5 structure-view schema + safe HTML renderer
-> item 24 Skill lifecycle input
-> item 33 over-implementation guard canary
-> item 10 diagram review boundary
-> final verification

理由:

item 5 の renderer が先にあると、item 24 / 33 の lifecycle / guard report を安全に inspect できます。item 24 の lifecycle input があると、item 33 の guard 結果を Skill/refinement proposal に接続できます。item 10 は外部導入しないため、item 5 の schema / renderer と PDG boundary ができてから reference-only constraint として固定します。

10. やらないこと
禁止事項	防止策
plugin install	WBS gate と manifest test で external enabled entry を拒否。
hook enablement	source-intake PDG と guard test で hook/MCP/plugin を blocked にする。
MCP enablement	pdgkit は既存 isolated CLI/render lane のみ。MCP は不可。
provider/API/search/Reader/OCR/LLM/model calls	no-quota freeze 維持。test は fake/local/stdlib のみ。
generated diagram/HTML/SVG as evidence	schema validation、renderer banner、Pointer not_evidence: true、WBS answer_support_allowed: false。
automatic Skill growth	auto_apply_allowed は常に false。human decision なしに Skill file / manifest を書き換えない。
Markdown 再肥大化	状態は WBS、構造は PDG、hash/pointer は Pointer Map、理由だけ Markdown。
source candidate の evidence 昇格	X/GPT item leaf は source_candidate のまま維持。source bundle/context/citation を経ない answer support は禁止。
11. 推奨実装順

Phase 0: 共通 boundary lock

Phase 1: item 5 structure-view split local renderer

Phase 2: item 24 Skill lifecycle input gate

Phase 3: item 33 over-implementation guard canary

Phase 4: item 10 diagram review boundary hardening

Phase 5: 総合検証

12. 最初に着手すべき1つ目の実装単位

最初は item 5: ControlArtifactView schema + safe HTML renderer + tests です。

最初の PR / commit の粒度:

追加: src/research_x/control_artifacts/model.py
追加: src/research_x/control_artifacts/renderer.py
追加: tests/fixtures/control_artifacts/structure_view.valid.json
追加: tests/test_control_artifact_structure_view.py
更新: tools/wbs_viewer/projects/research-x-work-state.json
更新: .codex/context_offloads/pointer-map.json

完了条件:

valid fixture から deterministic HTML が生成される
HTML に script/network/storage が含まれない
Not evidence banner がある
source artifact pointer を表示する
answer_support_allowed: true の input を拒否する
not_evidence: false の control artifact input を拒否する

この単位が終われば、MUSE lifecycle report、Ponytail guard report、Archify-style diagram boundary を同じ安全な artifact lane に載せられます。
