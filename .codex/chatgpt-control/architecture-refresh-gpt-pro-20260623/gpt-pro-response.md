# GPT Pro Response

Source URL: https://chatgpt.com/c/6a3a9bd4-f154-83ee-9c47-00cc93320c68
Captured: 2026-06-23T14:56:51.380Z
Length: 22165

---

1. 結論

research_x は、Markdownを「全部入りの作業台」として使う構成をやめるべきです。刷新後の正本は次の4層に分けます。

Markdown = 判断理由・境界・不変条件
WBS JSON = 作業状態・候補・進捗・残件・gate・artifact pointer
PDG source = route・状態遷移・実装境界・判断フロー
Pointer / ContextBudget = 詳細文脈を復元するための path/hash/size/restore hint

現在の CURRENT_CODEX_PLAN.md は方向性としては正しいですが、まだ「11/35を補助的に足す」構造が残っています。刷新案では、PROJECT.md、docs/memory-pipeline-v2.md、README.codex.md、.codex/chatgpt-control/x-url-analysis-20260622/*.md が重複して抱えている 状態一覧・長い候補表・phase進行・Mermaid的な流れ・残件一覧 をWBS/PDGへ移し、Markdown側は大幅に薄くします。

ただし、絶対条件として、WBS/PDG/SVG/スクリーンショット/Pointer Map は evidence ではありません。回答根拠は引き続き次の既存 pipeline を通します。

raw source -> searchable document -> search result -> source bundle
-> context chunk -> citation -> answer

実装上の中心変更は、tools/wbs_viewer/projects/research-x-visual-context-offload.json を狭いレーン用WBSのままにせず、より広い research_x 作業状態正本へ昇格させることです。あわせて、tools/pdgkit_canary/canaries/visual-context-offload-lane.pdg を単なる canary ではなく、構造フロー正本の雛形として昇格させます。tools/pdgkit_canary/ 自体は依存隔離用のままにし、pdgkit-mcp、provider/API、hook、browser編集の常用化は導入しません。

2. 現状の構造問題

現状の問題は、Markdownファイルが役割境界を破っていることです。

docs/memory-pipeline-v2.md は本来、AI-callable evidence pipeline の詳細アーキテクチャ正本です。しかし現在は、Evidence/Source Bundle First の不変条件だけでなく、Active Decision Record、Visual Context Offload Lane、Research Control Artifacts、API Budget Guard、Post-V1 boundaries、compatibility notes、provider research notes まで保持しています。1250行規模になっており、実装者が「現在の不変条件」と「過去の判断経緯」と「作業状態」を同じ文脈として読まされます。

PROJECT.md は「short implementation tracker」と書かれていますが、実際には completed milestones、current gates、provider gate、local dependency gate、post-v1 boundaries まで持っています。これはWBSが担うべき状態情報です。特に Completed Milestones の長いリストと Current Gates は、今後も増え続けるとPROJECT自体が第2の設計書になります。

README.codex.md は compact reference のはずですが、CLI surface、context/output budget、visual context offload、governance、PromptContract、research intake、Skill一覧まで持っています。日常導線として必要な情報と、必要時だけ読めばよい参照情報が混在しています。

.codex/chatgpt-control/x-url-analysis-20260622/ は最も肥大化しています。classification.md、project-usability-review.md、implementation-priority-flow.md、phase-gate-report.md、current-decision-summary.md、implementation-plan-11-35.md、visual-context-offload-refresh.md がそれぞれ「これは正本ではない」と断っているにもかかわらず、実際には次に何を読むか、何が残っているか、どの候補がどのbandか、どのgateを通ったかを保持しています。これはMarkdownが作業DB化している状態です。

11/WBS Viewer と 35/pdgkit の導入意図は、この問題の対症療法ではなく、情報アーキテクチャの再分割に使うべきです。現在の wbs-35-item-flow.json と visual-context-offload-lane.pdg は canary としては成功していますが、まだプロジェクト全体の正本にはなっていません。

3. 新しい情報アーキテクチャ

刷新後は、research_x の情報を6つの面に分けます。

A. Evidence Plane

対象は既存の memory evidence pipeline です。

主な所有物は、tweets、account_bookmarks、collection_items、tweet_edges、media、raw_payloads、memory_documents、source bundle、context chunk、citation annotation、answer run、workflow trace です。

ここはWBS/PDGに移してはいけません。WBSやPDGは、せいぜい「どのartifactを見ればよいか」を指すだけです。source_url がWBSに入っていても、それは source candidate pointer であり、citation-ready evidence ではありません。

B. Decision Plane

Markdownが担当します。

対象ファイルは以下です。

docs/memory-pipeline-v2.md
docs/pipeline.md
AGENTS.md
README.codex.md
PROJECT.md
tools/wbs_viewer/UPSTREAM.md
tools/pdgkit_canary/UPSTREAM.md
.codex/vendor_sources.lock.md
.codex/skill_manifest.lock

Markdownが持つべき内容は、判断理由、非採用理由、境界、停止条件、不変条件、ソースレビュー結果です。作業状態や長い候補一覧は持たせません。

C. Work-State Plane

WBS JSONが担当します。

現行の2つのWBSを統合・昇格します。

.codex/chatgpt-control/x-url-analysis-20260622/wbs-35-item-flow.json
tools/wbs_viewer/projects/research-x-visual-context-offload.json

刷新後の推奨正本は次です。

tools/wbs_viewer/projects/research-x-work-state.json

ここに、35-item flow、visual context offload lane、post-v1 work boundaries、provider gates、local dependency gates、active residual candidates、planned/actual、complete/blocked/closed、artifact pointer を入れます。

D. Structure Plane

PDG sourceが担当します。

現行のPDG canaryは次です。

tools/pdgkit_canary/canaries/item-11-35-flow.pdg
tools/pdgkit_canary/canaries/visual-context-offload-lane.pdg

刷新後は、tools/pdgkit_canary/ を依存隔離・実行環境として残し、プロジェクト所有の構造sourceを canary から分けます。

推奨配置は次です。

docs/pdg/memory-evidence-pipeline.pdg
docs/pdg/objective-route-policy.pdg
docs/pdg/source-intake-gate-flow.pdg
docs/pdg/visual-context-offload-lane.pdg
docs/pdg/out/*.svg

docs/pdg/*.pdg は route、状態遷移、判断フロー、実装境界の正本です。SVGは review artifact です。

E. Pointer / ContextBudget Plane

Pointer Mapが担当します。

現行のMarkdown pointer map は次です。

.codex/context_offloads/visual-context-offload-map.md

これを小規模のうちは使えますが、今後ポインタが増えるならMarkdown tableが再び肥大化します。したがって、刷新後の正本はJSONにします。

.codex/context_offloads/pointer-map.json
.codex/context_offloads/visual-context-offload-map.md  # generated/thin human index

pointer-map.json には、pointer_id、artifact_path、sha256、char_count、byte_count、restore_hint、artifact_kind、owner_plane、not_evidence: true を持たせます。

既存 ContextBudgetPolicy は runtime の context/workflow/answer JSON offload 用です。これを設計文書の証拠代替にしてはいけません。今回の .codex/context_offloads/ は、Codex作業文脈を復元する control-plane pointer として扱います。

F. Archive Plane

履歴だけを担当します。

docs/memory-pipeline-archive.md は、現在すでに historical decision archive として機能しています。今後ここに入れるのは「将来の判断に必要な過去の理由」だけです。

一方、.codex/chatgpt-control/x-url-analysis-20260622/ の長いMarkdown群は、全部をactive treeに残す必要はありません。重要な判断はWBS/PDG/lock/tool docsへ移し、残りはGit履歴に任せる方がよいです。ここで「念のため全部archiveする」と、結局また読まれる巨大Markdown面が残ります。

4. Markdown削減方針

Markdownは次の4種だけを持つべきです。

1. 不変条件
2. 判断理由
3. 停止条件
4. 構造artifactへのpointer

削るべきものは明確です。

現在Markdownが持っているもの	移行先
35候補の一覧、decision band、gate、残件	tools/wbs_viewer/projects/research-x-work-state.json
Phase 1-8の進行表、GO/NO-GO、次phase	WBS JSON
planned/actual日付、進捗、complete/blocked/closed	WBS JSON
Mermaidの実装優先フロー	docs/pdg/source-intake-gate-flow.pdg
ObjectiveRoutePolicyやevidence pipelineの流れ	docs/pdg/memory-evidence-pipeline.pdg, docs/pdg/objective-route-policy.pdg
Visual context offload の手順	docs/pdg/visual-context-offload-lane.pdg
artifact path/hash/restore hint	.codex/context_offloads/pointer-map.json
「次に何を読むか」の長い説明	README.codex.md の短い reduced read path
source review結果	tools/*/UPSTREAM.md, .codex/vendor_sources.lock.md
provider/API禁止、MCP禁止、hook禁止	AGENTS.md, .codex/vendor_sources.lock.md, docs/memory-pipeline-v2.md の短い境界節

docs/memory-pipeline-v2.md は、現在のまま増やしてはいけません。ここは「詳細正本」ではありますが、詳細の種類を絞る必要があります。保持するのは evidence contract と decision rationale です。route edge、作業状態、candidate lifecycle は外に出します。

PROJECT.md は最も削るべきです。現行の completed milestones と current gates は、WBSに移せます。PROJECT.md は80行未満を目標にし、次だけを持たせます。

- project goal
- current canonical WBS pointer
- current architecture pointer
- current evidence invariant
- active stop gatesへのpointer

README.codex.md は、日常導線として残します。ただし、現在のようにCLI一覧やSkill一覧を大量に持つ必要はありません。CLIは uv run python -m research_x memory --help に逃がし、Skill一覧は .codex/skill_manifest.lock に逃がします。READMEには「最初に何を読むか」「何を読まないか」を書くべきです。

5. WBS/PDG/Pointer Map の役割分担
WBSが担うもの

WBSは「状態DB」です。

対象は次です。

candidate list
decision band
status: active / complete / blocked / closed / archived
planned start/end
actual start/end
gate
next_action
owner surface
artifact pointer
source candidate URL
evidence_status
stop condition

現行の wbs-35-item-flow.json は、35 item の分類をすでに持っています。これは current-decision-summary.md の長い表を置き換えられます。

現行の research-x-visual-context-offload.json は、visual context offload の状態だけを持っています。刷新後は、これを単独レーンではなく、research-x-work-state.json の一部に統合します。

WBSに入れてはいけないものは次です。

長い判断理由
source evidenceそのもの
citation-ready claim
source bundleの代替
context chunk本文
answer support
provider/API実行許可
PDGが担うもの

PDGは「構造DB」です。

対象は次です。

route flow
state machine
implementation boundary
source-intake gate flow
evidence pipeline transition
visual context offload procedure
provider/dependency/MCP stop transition

現行の visual-context-offload-lane.pdg は、すでに次の流れを表しています。

text context too large?
-> classify context shape
-> WBS or PDG
-> validate structured sources
-> write pointer map
-> evidence claim needed?
-> restore source bundle/context chunks/citations

これは良い雛形です。ただし、tools/pdgkit_canary/canaries/ 配下に置いたままだと「canary」扱いから抜けません。刷新後は project-owned PDG として docs/pdg/visual-context-offload-lane.pdg へ移すべきです。

PDGに入れてはいけないものは次です。

なぜその判断にしたかの長文
candidateの進捗状態
planned/actual
source review本文
evidence本文
citation
answer
Pointer Map / ContextBudget が担うもの

Pointer Mapは「復元索引」です。

対象は次です。

pointer_id
artifact_path
sha256
char_count
byte_count
restore_hint
owner_plane
artifact_kind
not_evidence
supersedes

現行の .codex/context_offloads/visual-context-offload-map.md は小さいうちは十分ですが、今後増えるとまたMarkdown table化します。したがって、JSON正本を作り、Markdownは薄い人間向け表示にします。

ContextBudgetPolicyとの境界は明確にします。

ContextBudgetPolicy:
  runtime outputの巨大context/workflow/answer JSONをpreview + hash + file pointerへ逃がす

Pointer Map:
  Codex作業・設計・WBS/PDG artifactをpath/hash/restore hintで復元する

どちらも evidence ではありません。

6. 既存ファイル別の扱い
ファイル	新しい扱い
docs/memory-pipeline-v2.md	evidence pipeline の薄い憲法に再編集。保持するのは invariant、layer責務、evidence boundary、WBS/PDG非evidence境界、provider/API gateの短縮版。route/flowはPDGへ、状態はWBSへ、長いprovider research noteはarchiveへ移す。
docs/memory-pipeline-archive.md	historical decision archiveとして維持。active read pathから外す。古いprovider researchや過去の代替案だけ入れる。X/GPTの全Markdownをここへ丸ごと移すのは禁止。
docs/pipeline.md	X acquisition/auth/provider chain の正本として維持。memory architectureの重複説明は削る。provider chainの作業状態はWBSへ移す。
PROJECT.md	80行未満の tracker に縮小。Completed Milestones、Current Gates、Post-V1 Work Boundaries の詳細は research-x-work-state.json へ移す。
README.codex.md	first-read導線に縮小。AGENTS.md -> README.codex.md -> pointer-map -> WBS/PDG as needed に変更。長いCLI一覧とSkill一覧は --help と .codex/skill_manifest.lock へ逃がす。
AGENTS.md	常時ルールだけ維持。WBS/PDGの詳細は持たせない。長いSkill catalog重複は将来的に .codex/skill_manifest.lock 参照へ寄せる。
.codex/vendor_sources.lock.md	third-party source/tool lock として維持。WBS Viewer と pdgkit の禁止事項、pin、no MCP/no hook/no provider/no evidence をここで保持。
.codex/skill_manifest.lock	Skill正本として維持。README/PROJECT/AGENTSでSkill一覧を重複しない。
.codex/chatgpt-control/architecture-refresh-gpt-pro-20260623/CURRENT_CODEX_PLAN.md	この刷新作業の入力資料。実装後はactive read pathから外す。内容は docs/memory-pipeline-v2.md、WBS、PDG、Pointer Mapへ分解して吸収する。
.codex/chatgpt-control/x-url-analysis-20260622/current-decision-summary.md	35 item のdecision band/status/gateをWBSへ移した後、削除またはactive path外へ退避。今後更新しない。
.codex/chatgpt-control/x-url-analysis-20260622/phase-gate-report.md	Phase 1-8の状態・検証はWBSへ移す。長いrepair loopはGit履歴で十分。必要なdurable conclusionだけ docs/memory-pipeline-v2.md かarchiveに短く残す。
.codex/chatgpt-control/x-url-analysis-20260622/implementation-priority-flow.md	Mermaid flowと実装順はPDG/WBSへ移す。Markdownとしては削除候補。
.codex/chatgpt-control/x-url-analysis-20260622/implementation-plan-11-35.md	11/35のcanary計画は tools/wbs_viewer/UPSTREAM.md、tools/pdgkit_canary/UPSTREAM.md、WBS、PDGへ分解済みにする。削除候補。
.codex/chatgpt-control/x-url-analysis-20260622/visual-context-offload-refresh.md	内容は docs/memory-pipeline-v2.md の短い境界節、PDG、WBS、Pointer Mapへ吸収する。吸収後は削除候補。
.codex/chatgpt-control/x-url-analysis-20260622/classification.md	初期分類。decision bandはWBSへ、source-reviewが必要なものは vendor lock / archiveへ。active pathから削除。
.codex/chatgpt-control/x-url-analysis-20260622/project-usability-review.md	長いproject-use review。durable conclusionだけWBS/Markdownへ移し、active pathから削除。
.codex/chatgpt-control/x-url-analysis-20260622/chatgpt-visible-output.txt などraw consultation	evidenceではない。原則active treeから外す。保持する場合も README.codex.md のread pathには入れない。
.codex/chatgpt-control/x-url-analysis-20260622/wbs-35-item-flow.json	research-x-work-state.json へ統合。単体ファイルはhistorical canaryとして残すか削除。更新対象にはしない。
.codex/chatgpt-control/x-url-analysis-20260622/wbs-35-item-flow-screenshot.png	review artifactのみ。active pointerから外す。必要なら再生成。削除候補。
tools/wbs_viewer/README.md	WBS Viewerの使い方だけに絞る。正本WBS pathを research-x-work-state.json に更新。
tools/wbs_viewer/UPSTREAM.md	source review正本として維持。ここにlicense/pin/runtime constraintsを残す。
tools/wbs_viewer/projects/research-x-visual-context-offload.json	research-x-work-state.json へ統合。旧ファイルは互換用に一時残してもよいが、更新対象から外す。
tools/pdgkit_canary/README.md	pdgkit isolated tool の実行説明に絞る。project PDG sourceは docs/pdg/*.pdg を指す。
tools/pdgkit_canary/UPSTREAM.md	pdgkit source/dependency review正本として維持。no MCP/no provider/no root dependency/no evidence を保持。
tools/pdgkit_canary/canaries/item-11-35-flow.pdg	canary fixtureとして維持。architecture正本にはしない。
tools/pdgkit_canary/canaries/visual-context-offload-lane.pdg	docs/pdg/visual-context-offload-lane.pdg へ昇格・移動。旧pathは削除または互換用に短期維持。
tools/pdgkit_canary/out/*.svg	generated review artifact。PDG sourceから再生成可能なものとして扱う。
tests/test_visual_context_offload_lane.py	新しい WBS/PDG/Pointer paths に更新。Pointer hash一致、no-evidence境界、PDG validate/render前提を確認する。
tests/test_wbs_viewer_canary.py	item 11 canary testとして維持。ただし正本WBS testは別途追加。
tests/test_pdgkit_canary.py	pdgkit package/canary isolation testとして維持。project PDG testは別途追加。
7. 移行ステップ
Step 1: canonical WBSを作る

新規作成します。

tools/wbs_viewer/projects/research-x-work-state.json

統合元は次です。

PROJECT.md
.codex/chatgpt-control/x-url-analysis-20260622/wbs-35-item-flow.json
tools/wbs_viewer/projects/research-x-visual-context-offload.json
.codex/chatgpt-control/x-url-analysis-20260622/current-decision-summary.md
.codex/chatgpt-control/x-url-analysis-20260622/phase-gate-report.md

WBSのトップレベルは次のように分けます。

1. Memory no-spend foundation
2. Provider-quota gate
3. Local dependency gate
4. Codex foundation adjuncts
5. X/GPT 35-item intake
6. Visual context offload lane
7. Future local hardening

各leafには最低限次を持たせます。

JSON
"_research_x": {
  "owner_plane": "wbs",
  "artifact_layer": "operational_state",
  "decision_band": "...",
  "gate": "...",
  "status": "complete|active|blocked|closed|archived",
  "artifact_pointer": "...",
  "owner_doc": "...",
  "evidence_status": "not_evidence|source_candidate|source_restored|citation_ready",
  "answer_support_allowed": false
}
Step 2: project PDG sourcesを作る

新規作成します。

docs/pdg/memory-evidence-pipeline.pdg
docs/pdg/objective-route-policy.pdg
docs/pdg/source-intake-gate-flow.pdg
docs/pdg/visual-context-offload-lane.pdg

移行元は次です。

docs/memory-pipeline-v2.md の skeleton / layers / query routes
.codex/chatgpt-control/x-url-analysis-20260622/implementation-priority-flow.md
.codex/chatgpt-control/x-url-analysis-20260622/implementation-plan-11-35.md
tools/pdgkit_canary/canaries/visual-context-offload-lane.pdg

pdgkit validate と pdgkit render は tools/pdgkit_canary/ から実行します。pdgkit-mcp は使いません。

Step 3: pointer mapをJSON正本にする

新規作成します。

.codex/context_offloads/pointer-map.json

既存の以下は薄いhuman indexへ変更します。

.codex/context_offloads/visual-context-offload-map.md

pointer entriesには、WBS、PDG source、SVG、必要なarchive pointerだけを登録します。長い説明は入れません。

Step 4: Markdownを薄くする

最初に PROJECT.md を削ります。ここが一番状態を抱えています。

PROJECT.md の新構成は次で十分です。

# Memory Search Project Plan

- Goal
- Current architecture pointer
- Current work-state pointer
- Evidence invariant
- Active gates pointer
- Implementation rules

次に README.codex.md を削ります。first-readは次にします。

1. AGENTS.md
2. README.codex.md
3. .codex/context_offloads/pointer-map.json
4. tools/wbs_viewer/projects/research-x-work-state.json only if state is needed
5. docs/pdg/*.pdg only if structure is needed
6. docs/memory-pipeline-v2.md only if architecture/evidence contract changes
7. docs/memory-pipeline-archive.md only if historical rationale is needed

次に docs/memory-pipeline-v2.md を削ります。保持するのは以下です。

- Executive Decision
- Core invariant
- Evidence layer responsibilities
- Non-evidence artifacts
- WBS/PDG/Pointer boundary
- Provider/API budget gate summary
- ContextBudgetPolicy boundary
- Deletion/rewrite policy
- Open risks

移すものは以下です。

route flow -> docs/pdg/objective-route-policy.pdg
layer transition -> docs/pdg/memory-evidence-pipeline.pdg
candidate/state/gate -> research-x-work-state.json
long provider research note -> docs/memory-pipeline-archive.md
Step 5: .codex/chatgpt-control/x-url-analysis-20260622/ を整理する

このフォルダは現状、実質的にMarkdown DBです。刷新後は active read path に残しません。

残すなら、1つだけ薄い index を置きます。

.codex/chatgpt-control/x-url-analysis-20260622/README.md

内容は次だけです。

- This folder was a consultation/control capture.
- It is not evidence.
- Current state is in tools/wbs_viewer/projects/research-x-work-state.json.
- Current structure is in docs/pdg/source-intake-gate-flow.pdg.
- Tool source reviews are in tools/*/UPSTREAM.md and .codex/vendor_sources.lock.md.

それ以外の長いMarkdownは、必要情報を移した後に削除候補です。Git履歴で復元できるため、active treeに長大な「非正本」を残す必要は薄いです。

Step 6: tools docsを正本境界に合わせる

tools/wbs_viewer/README.md は、正本WBS pathを research-x-work-state.json に更新します。

tools/pdgkit_canary/README.md は、canaryとproject PDG sourceを分けます。

Canary fixtures:
  tools/pdgkit_canary/canaries/*.pdg

Project-owned PDG sources:
  docs/pdg/*.pdg
8. テスト/検証計画

最低限、以下を追加・更新します。

WBS tests

新規または更新対象:

tests/test_research_x_work_state_wbs.py

検証内容:

- tools/wbs_viewer/projects/research-x-work-state.json がparseできる
- top-level groupが expected set を満たす
- leaf taskが status / gate / owner_doc / artifact_pointer / evidence_status を持つ
- X/GPT 35-item intake が35 leafを保持する
- item 11と35が completed canary として記録される
- WBS上の answer_support_allowed が false
- WBSに citation-ready evidence本文が入っていない

既存 tests/test_wbs_viewer_canary.py は、vendored viewerと旧canaryの確認として残します。

PDG tests

新規または更新対象:

tests/test_project_pdg_sources.py

検証内容:

- docs/pdg/*.pdg が存在する
- 各 .pdg が "#! kind: flow" で始まる
- memory-evidence-pipeline.pdg に source bundle / context chunks / citations / answer がある
- visual-context-offload-lane.pdg に WBS / PDG / pointer map / evidence restoration gate がある
- source-intake-gate-flow.pdg に provider / dependency / MCP / hook stop gate がある

手動またはCI対象コマンド:

PowerShell
cd tools\pdgkit_canary
npx pdgkit validate ..\..\docs\pdg\memory-evidence-pipeline.pdg --lang en
npx pdgkit render ..\..\docs\pdg\memory-evidence-pipeline.pdg --lang en -o ..\..\docs\pdg\out\memory-evidence-pipeline.svg

同様に他の .pdg も validate/render します。

Pointer tests

更新対象:

tests/test_visual_context_offload_lane.py

または新規:

tests/test_context_offload_pointer_map.py

検証内容:

- .codex/context_offloads/pointer-map.json がparseできる
- WBS/PDG/SVGの path が存在する
- sha256 / char_count / byte_count が現物と一致する
- not_evidence が true
- restore_hint が空でない
- visual-context-offload-map.md はJSON正本と矛盾しない
Markdown thinness / drift tests

新規:

tests/test_markdown_information_architecture.py

検証内容:

- PROJECT.md が長いphase tableや35-item listを持たない
- README.codex.md が WBS/PDG/Pointer reduced read path を含む
- docs/memory-pipeline-v2.md が WBS-owned task state や PDG-owned edge list を重複しない
- .codex/chatgpt-control/x-url-analysis-20260622/ の active Markdown が README.md だけ、またはsuperseded扱いである

行数上限を雑に入れるなら、まずは次が現実的です。

PROJECT.md <= 100 lines
README.codex.md <= 180 lines
.codex/chatgpt-control/x-url-analysis-20260622/README.md <= 60 lines

docs/memory-pipeline-v2.md は一気に厳しい上限を置くより、まず構造・状態の重複禁止をテストする方が安全です。

Existing evidence regression

既存の no-provider 境界を維持します。

PowerShell
uv run pytest tests/test_visual_context_offload_lane.py tests/test_wbs_viewer_canary.py tests/test_pdgkit_canary.py
uv run pytest tests/skills/test_vendor_sources_lock.py
uv run ruff check tests/test_visual_context_offload_lane.py tests/test_wbs_viewer_canary.py tests/test_pdgkit_canary.py tests/skills/test_vendor_sources_lock.py
git diff --check

フルrepoなら最後に通常チェックを走らせます。

PowerShell
uv run ruff check src\research_x tests
uv run pytest
9. リスクと停止条件
リスク1: WBSが新しい長文DBになる

WBSの note に長い判断理由を書き始めると、Markdown肥大化がJSON肥大化に移るだけです。

停止条件:

WBSのnoteが判断理由本文・source review本文・長い説明を持ち始めたら停止。
判断理由はMarkdown、状態はWBSに戻す。
リスク2: PDGが無理に全構造を抱える

PDGはflow/state/routeには向いていますが、すべての仕様説明に向くわけではありません。

停止条件:

PDGが読みにくい巨大グラフになり、Markdown要約なしでは意味が取れない場合は停止。
PDGを複数小ファイルへ分割する。
リスク3: WBS/PDGがevidence扱いされる

これは最重要リスクです。

停止条件:

WBS/PDG/SVG/screenshot/pointer map を citation, answer support, source quality evidence として使う変更が出たら停止。
必ず source bundle -> context chunk -> citation -> answer に戻す。
リスク4: Pointer hashが古くなる

Pointer Mapがhash不一致のまま残ると、復元索引として信用できません。

停止条件:

pointer-map.json の sha256 / byte_count / char_count が現物と一致しない場合は停止。
hash更新なしでMarkdownやWBSから参照しない。
リスク5: canaryと正本が混ざる

tools/pdgkit_canary/canaries/ にproject正本を置き続けると、canaryなのか採用済みlaneなのか曖昧になります。

停止条件:

project-owned PDG source と canary fixture の境界が曖昧なまま次の構造図を増やす場合は停止。
先に docs/pdg/ へ分離する。
リスク6: 削減で判断理由が消える

状態やflowを移しても、なぜそう判断したかは残す必要があります。

停止条件:

Markdown削減後に、WBS/PDGだけ見ても「なぜ採用/非採用か」が復元できず、Markdownにも短い理由がない場合は停止。
10. まず実装すべき最小変更セット

最小でも、以下は同時に実装すべきです。これより小さくすると、また「WBS/PDGを少し足しただけ」になります。

変更1: canonical WBSを作る

作成:

tools/wbs_viewer/projects/research-x-work-state.json

統合:

.codex/chatgpt-control/x-url-analysis-20260622/wbs-35-item-flow.json
tools/wbs_viewer/projects/research-x-visual-context-offload.json
PROJECT.md の completed/current gate/post-v1 state
current-decision-summary.md の residual 35-item state

旧WBSは更新対象から外します。

変更2: project PDGをcanaryから分離する

作成:

docs/pdg/visual-context-offload-lane.pdg
docs/pdg/source-intake-gate-flow.pdg
docs/pdg/memory-evidence-pipeline.pdg

tools/pdgkit_canary/ は validate/render 実行環境として残します。

変更3: pointer-map JSONを作る

作成:

.codex/context_offloads/pointer-map.json

更新:

.codex/context_offloads/visual-context-offload-map.md

Markdown側はJSON正本への薄い案内にします。

変更4: PROJECT.md を大幅に削る

PROJECT.md から以下をWBSへ移します。

Completed Milestones の詳細
Current Gates の詳細
Post-V1 Work Boundaries の詳細状態
Visual context offload lane の詳細

残すのは goal、invariant、WBS pointer、architecture pointer、implementation rules だけです。

変更5: README.codex.md の first-read を変える

現在の「まずPROJECTとmemory-pipelineを読む」導線を弱め、長い作業では pointer-first にします。

推奨:

AGENTS.md
README.codex.md
.codex/context_offloads/pointer-map.json
WBS only if state is needed
PDG only if structure is needed
docs/memory-pipeline-v2.md only if architecture changes
変更6: .codex/chatgpt-control/x-url-analysis-20260622/ をactive pathから外す

作成するなら薄いindexのみです。

.codex/chatgpt-control/x-url-analysis-20260622/README.md

以下は移行後、削除またはactive path外にします。

classification.md
project-usability-review.md
implementation-priority-flow.md
phase-gate-report.md
current-decision-summary.md
implementation-plan-11-35.md
visual-context-offload-refresh.md
wbs-viewer-canary-report.md
pdgkit-canary-report.md

これは削りすぎではありません。これらは自分で「not evidence」「not durable architecture decision」と名乗っており、今後の状態・構造・判断理由を別正本へ移せば、active treeに長文として残す必要はありません。

変更7: testsを追加して逆戻りを防ぐ

追加・更新:

tests/test_research_x_work_state_wbs.py
tests/test_project_pdg_sources.py
tests/test_context_offload_pointer_map.py
tests/test_markdown_information_architecture.py
tests/test_visual_context_offload_lane.py

この最小セットで、Markdownを薄くするだけでなく、WBS/PDG/Pointerへ逃がした内容が検証可能になります。特に PROJECT.md と .codex/chatgpt-control/x-url-analysis-20260622/ を削らない限り、今回の刷新は実質的には失敗です。
