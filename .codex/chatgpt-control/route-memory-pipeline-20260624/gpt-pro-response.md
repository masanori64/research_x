---
source: GPT Pro visible ChatGPT
url: https://chatgpt.com/c/6a3b3cfd-2fc0-83ee-8ea3-cd481647723c
title: "Codex運用パイプライン検証"
assistant_count: 3
selected_assistant_index: 2
captured_at_jst: 2026-06-24
---
1. 結論

現行構成は、Codex運用パイプラインの骨格としてはかなり強いです。特に AGENTS.md には、Skill Router Preflight、フェーズ境界でのSkill再確認、停滞時の探索、サブエージェント許可ポリシー、no-quota/provider/browser/network/MCP/connector/install等の停止ゲートが既に入っています。これは「標準パイプラインの骨格がある」という評価を支持します。

ただし、Route Memoryを常用フル稼働させるにはまだ足りません。足りないのは主に AGENTS.md の長文追記ではなく、次の3点です。

過去成功/失敗ルートを構造化して検索・選択する route-memory registry

起動直後にそのregistryを必ず見る、軽量で常時ONの Route Memory Preflight

「成功ルートを初手にする」ことを静的テストで守る回帰防止

ChatGPT ZIP uploadの個別例では、external/codex-chatgpt-control/SKILL.md と external/codex-chatgpt-control/references/chatgpt-zip-upload.md に、in-app browser clipboard attachment route が canonical success path として明記されています。したがって「個別例としては成功ルートを選べる状態にかなり近い」というCodex xhighの訂正後判断は概ね妥当です。

しかし、現状の文言はまだ “normal askWithFiles / file chooser が失敗したときの fallback” と読めます。つまり次回Codexがまた通常アップロードから始める余地が残っています。ユーザーの問題意識どおり、ここは fallbackではなく、Codex Desktopでlocal ZIP/context bundleをChatGPTへ送る場合のprimary canonical route として昇格させるべきです。

また、ZIP内には docs/pdg/*.pdg 本体が含まれていません。README.codex.md、PROJECT.md、WBS、Pointer Map、テスト上ではPDGの存在と役割は確認できますが、PDGソースそのものの内容はこのZIPだけでは検証できません。

2. ユーザー反証の検証
2.1 「古い成功ルートが誤った初手になる」リスク

ユーザー反証は 半分正しい です。

現行の Markdown / WBS / Pointer Map 構成は、古いGPT出力や歴史的Markdownを active tracker や evidence として誤用しないためにはかなり強いです。

根拠は次の通りです。

README.codex.md は、CodexのReduced Read Pathとして AGENTS.md、README.codex.md、.codex/context_offloads/pointer-map.json、WBS、PDG、docs/memory-pipeline-v2.md の順を指定し、.codex/chatgpt-control/x-url-analysis-20260622/*.md は historical consultation capture であり active plan/evidence source ではないと明記しています（README.codex.md:6-25）。

docs/memory-pipeline-v2.md は、WBS JSON、PDG source、generated SVG、screenshots、Pointer Map、ChatGPT/GPT Pro consultation captures、sub-agent notes、compressed summaries/previews を “Non-Evidence Control Artifacts” と分類し、citation-ready evidence や answer support に使ってはいけないとしています（docs/memory-pipeline-v2.md:82-97）。

WBSのleaf metadataは evidence_status と answer_support_allowed: false を必須にしており、テストでも全leafに対して answer_support_allowed is False を検査しています（tests/test_research_x_work_state_wbs.py:19-37, tests/test_research_x_work_state_wbs.py:62-75）。

そのため、「古いGPT Markdownが勝手に現行判断へ昇格する」リスクはかなり抑えられています。

一方で、Route Memory固有の stale / fingerprint 誤判定リスクはまだ十分には潰れていません。
ZIP内を検索しても、過去成功/失敗ルートを次のような構造で管理する汎用registryは見当たりません。

task fingerprint

applies_when

do_not_use_when

known_failed_routes

canonical_success_route

first_action

verification_signal

freshness / invalidation signal

owner Skill

gate requirements

last_verified_at

source pointer

not_evidence

Pointer Mapは artifact path / hash / restore hint を持ちますが、これは「ファイル復元の信頼性」を担保するものであって、「このタスクではこの成功ルートを初手にする」という行動選択のregistryではありません（.codex/context_offloads/pointer-map.json:1-15, docs/memory-pipeline-v2.md:123-132）。

したがって、ユーザー反証のうち、既存構成が古い情報のevidence昇格を防いでいるという点は正しいです。
しかし、既存構成だけでRoute Memoryのstale/fingerprint問題まで解決済みとは言えません。

2.2 「似ているだけの別問題に古い手順を当てる」リスク

これも 部分的に残っています。

research-x-skillization-intake には Skill Router Preflight があり、request/contextからSkill候補を出し、さらに各Skillの Use When / Do Not Use / safety gate / negative trigger を逆照合する設計になっています（.agents/skills/research-x-skillization-intake/SKILL.md:43-86）。これは誤ルーティングをかなり減らします。

ただし、Skill Router Preflightは Skill選択の仕組み であって、個別操作ルート、たとえば「ChatGPTへlocal ZIPを送るなら askWithFiles ではなく clipboard attachment route を初手にする」という粒度のroute selection registryではありません。

つまり、現行構成は Skillレベルの誤判定には強い が、同じSkill内の成功/失敗操作ルートの選択にはまだ弱い です。

2.3 「小さい作業にも重い事前確認が走ると遅くなる」問題

これは、設計次第でほぼ解消できます。

現行構成でも AGENTS.md は “Use this section as a small dispatcher, not as a full algorithm” とし、詳細手順はSkill側に持たせる方針です（AGENTS.md:59-67）。research-x-skillization-intake も、フェーズ境界チェックは毎tool call後の全Skill再読込ではなく、近傍Skillだけを見る軽量チェックとしています（.agents/skills/research-x-skillization-intake/SKILL.md:88-113）。

したがって、Route Memoryも同じ設計にすべきです。

常時ONにするのは、重い探索ではなく、次の程度の軽量処理です。

selected Skill / task surface / requested artifact / blocked route keywords
-> route-memory indexを軽く照合
-> exact matchがあれば詳細route entryを読む
-> matchしなければ none として通常進行

これなら小さい作業のコストは低いです。
一方、サブエージェント、外部検索、ChatGPT Pro相談、browser操作は条件付きONにすべきです。

2.4 「サブエージェント調査結果は候補/ヒントなのでノイズ問題は大きくない」

この反証は 現行ファイル上ほぼ正しい です。

research-x-parallel-review は、親Codexをcritical pathに残し、sub-agentには狭いrole、ownership/read-only scope、expected output、edit可否を渡し、最終判断は親が統合するとしています（.agents/skills/research-x-parallel-review/SKILL.md:17-38）。

search-quality-contract は、primary/official/secondary/community/local DB/generated summary/sub-agent note を分離し、community reports や generated summaries は proof ではなく failure-mode/review signal としています（.agents/skill-references/search-quality-contract.md:20-33）。

evidence-workflow-quality-contract も、sub-agent notes を evidence として引用してはいけないと明記しています（.agents/skill-references/evidence-workflow-quality-contract.md:51-58）。

したがって、サブエージェント結果を「事実情報・行動補助・コンテキスト幅拡張」として扱う境界は既にあります。問題は、サブエージェントを いつ必ず使うか と、結果をどのtraceに残すか です。

2.5 「network / privacy / provider / ToS / cost gate は今の運用なら問題なく動ける」

これは 方向性として正しいが、無条件ではない です。

AGENTS.md は no-quota provider freeze を明確に置き、Gemini/OpenAI/Voyage/Jina/Cohere/Mistral/Serper/Brave等へのprovider HTTP requestを禁止しています（AGENTS.md:6-31）。また provider/API/quota、network/browser、MCP、connector、install 等が必要なら停止して明示承認を求めるとしています（AGENTS.md:103-105, AGENTS.md:114-118）。

WBSにも Provider-quota gate があり、No-quota provider freeze は blocked、stop_condition は “Stop before real provider API calls until explicitly lifted in current conversation.” です（tools/wbs_viewer/projects/research-x-work-state.json:140-170）。

したがって、ゲート設計は強いです。
ただし、それは「問題なく何でも動ける」という意味ではなく、許可されていない外部行動を止められる という意味です。

常用フル稼働にする場合も、外部検索、ChatGPT Pro相談、browser操作、provider API、MCP/plugin/hookは同列ではありません。
常時ONにできるのは local registry lookup / local Skill routing / local gate check / local trace までです。

2.6 「標準パイプラインと言ってもまた発火しないのでは」

この懸念は かなり正しい です。

AGENTS.md には標準パイプラインの骨格がありますが、Route Memoryを必ず発火させる明示的な一文、registry、テストがありません。

また、README.codex.md は .codex/skill_manifest.lock によりRepo Skillsがenabledになると書いていますが、今回のZIPには .codex/skill_manifest.lock が含まれていません（README.codex.md:96-104）。したがって、このZIPだけでは native Skill enablement の実体は検証できません。

AGENTS.md は、native Skillがloadされていなくても task が workflow に明確に一致するなら SKILL.md を直接読むように書いています（AGENTS.md:59-64）。これはfallbackとして有効ですが、Route Memoryのような標準動作は、「Skillがたまたま呼ばれる」だけに依存するとまた発火漏れします。

3. Codex xhigh判断の妥当性
3.1 「AGENTS.mdにはSkill Router Preflight、停滞時の並行検索、サブエージェント探索の骨格がある」

妥当です。

AGENTS.md は、start of each request でSkill descriptionsを見てrepo Skill適用を判断し、native Skillがloadされなくても明確に該当するなら SKILL.md を直接読むとしています（AGENTS.md:59-64）。

短い継続指示では、README.codex.md、active plan/review Markdown、git/worktree state、recent project contextから現在タスクを推定し、Skill Router Preflightを実行するとしています（AGENTS.md:69-105）。

停滞時には、同じ失敗を繰り返さず、task/gatesが許せば local diagnosis と並行して exact error/tool/surface/community/issue signal の targeted search を走らせる、としています（AGENTS.md:124-129）。

サブエージェントについても、最新の明示ユーザー指示を使い、許可/要求がある場合には research-x-parallel-review を使うとされています（AGENTS.md:267-282）。

したがって「骨格がある」は正しいです。

3.2 「parallel-review と quality contracts はsub-agent出力を候補/ヒントとして扱う」

妥当です。

research-x-parallel-review は、sub-agentに最終判断を持たせず、親agentが統合する設計です（.agents/skills/research-x-parallel-review/SKILL.md:28-38）。

search-quality-contract は、sub-agent notesやsearch hitsを candidate/hint とし、evidence workflowを通るまでproofにしないとしています（.agents/skill-references/search-quality-contract.md:20-40）。

evidence-workflow-quality-contract は、sub-agent notesをevidenceとして引用しないとしています（.agents/skill-references/evidence-workflow-quality-contract.md:51-58）。

これはCodex xhighの判断を支持します。

3.3 「WBS/PDG/Pointer Map/Markdown の分担は古いGPT出力や歴史的Markdownの誤用防止に強い」

概ね妥当です。

README.codex.md は WBS / PDG / Pointer Map / Markdown の役割分担を明記しています。WBSはphase/candidate/gate/status、PDGはroute/state-machine/boundary flow、Pointer Mapはpath/hash/size/restore hint、Markdownはdurable reasons/invariants/stop conditions/pointersです（README.codex.md:84-94）。

docs/memory-pipeline-v2.md も、WBS owns candidate lists/status/gates、PDG owns route flows/state transitions、Pointer entries must keep hash/size/restore hints と定義しています（docs/memory-pipeline-v2.md:99-132）。

ただし、今回のZIPには docs/pdg/*.pdg 本体が入っていません。したがって、PDGの実内容までは検証不能です。Pointer Mapとテスト上ではPDGがある前提になっていますが、ZIP内現物としては確認できません。

3.4 「Pointer Map は hash/size/restore hint を持ち、テストで現物一致を確認している」

設計としては妥当です。

Pointer Mapの各entryには pointer_id, artifact_path, sha256, char_count, byte_count, restore_hint, artifact_kind, owner_plane, not_evidence が入っています（.codex/context_offloads/pointer-map.json:1-15 以降）。

tests/test_context_offload_pointer_map.py は、各entryのpath存在、not_evidence is True、restore_hint、artifact_kind、owner_plane、sha256、char_count、byte_countの一致を検査しています（tests/test_context_offload_pointer_map.py:11-29）。

ただし、今回のZIPにはPointer Mapが指す多くのartifact、たとえば .codex/context_offloads/visual-context-offload-map.md や docs/pdg/*.pdg が含まれていません。したがって、このZIPだけで「全entryの現物一致」を再実行確認することはできません。

ZIP内に存在する tools/wbs_viewer/projects/research-x-work-state.json については、Pointer Map上のhash/char_count/byte_countと一致していました。

3.5 「X/GPT historical Markdown は active path から外されている」

妥当です。

README.codex.md は .codex/chatgpt-control/x-url-analysis-20260622/*.md を routine read しないようにし、そのfolderは historical consultation capture であって active plan/evidence source ではないとしています（README.codex.md:24-25）。

WBSにも “Move X/GPT folder out of active path” が complete として記録され、state moved to WBS とされています（tools/wbs_viewer/projects/research-x-work-state.json:442-466）。

テストも、X/GPT folderにはthin active indexとhistorical noticesがあること、各Markdown先頭に “Historical consultation capture. Active path:” と “Not evidence” があることを要求しています（tests/test_markdown_information_architecture.py:58-73）。

ただし、今回のZIPには .codex/chatgpt-control/x-url-analysis-20260622/README.md や当該historical Markdown本体は含まれていません。テスト仕様としては確認できますが、ファイル現物の中身までは検証できません。

3.6 「Route Memoryそのものはまだ欠けています」→訂正後判断

訂正後判断は かなり妥当 です。

ただし、厳密にはこう整理すべきです。

AGENTS.mdには、常用パイプラインの骨格はある。
しかし、汎用Route Memory registryと、そのregistryを必ず初手で照合する実装/テストはまだない。
ChatGPT ZIP uploadという個別ケースでは、external codex-chatgpt-control Skillにcanonical routeが既に入っている。
ただし、fallback扱いの文言が残っているため、次回の初手選択を確実化するには追加修正が必要。
4. 現行AGENTS.md / Skill / WBS / PDG / Pointer Mapで既に解決していること
領域	既にあるもの	根拠	評価
Skill選択	start of each requestでSkill descriptionsを使う。未loadでも明確に該当すれば SKILL.md を直接読む	AGENTS.md:59-64	強い
短い継続指示の復元	README.codex.md、active plan/review Markdown、git/worktree state、recent contextから推定	AGENTS.md:69-105	強い
route line可視化	route: <selected skill(s)>; external actions: <none / needs approval> を作業前に出す	AGENTS.md:90-105, .agents/skills/research-x-skillization-intake/SKILL.md:66-82	強い
フェーズ境界再確認	planning/implementation/verification/docs/publish/review/gate出現時にSkill再確認	.agents/skills/research-x-skillization-intake/SKILL.md:88-113	強い
停滞時の探索	同じ失敗を繰り返さず、許可されていればlocal diagnosisと並行してtargeted search	AGENTS.md:124-129	中〜強
サブエージェント統合	親Codexがcritical pathと最終判断を保持	.agents/skills/research-x-parallel-review/SKILL.md:17-38	強い
sub-agent結果の扱い	notes/search hits/community reportsはcandidate/hintであってproofではない	.agents/skill-references/search-quality-contract.md:20-40, .agents/skill-references/evidence-workflow-quality-contract.md:51-58	強い
no-quota/provider gate	real provider API, external search provider, LLM-context等をfreeze	AGENTS.md:6-31, PROJECT.md:34-46, WBS 2.1	強い
WBS/PDG/Pointer/Markdown分離	WBSはstate、PDGはflow、Pointer Mapはrestore pointer、Markdownはdurable reasons/invariants	README.codex.md:84-94, docs/memory-pipeline-v2.md:99-132	強い
Pointer Mapの仕様	hash/size/restore hint/not_evidenceを要求	.codex/context_offloads/pointer-map.json:1-15, tests/test_context_offload_pointer_map.py:11-29	設計は強い。ZIP内では全現物検証不可
ChatGPT ZIP upload個別route	in-app browser clipboard application/zip attachment route がcanonical success pathとして記載	external/codex-chatgpt-control/SKILL.md:84-91, external/codex-chatgpt-control/references/chatgpt-zip-upload.md:7-41, external/chatgpt-control-router/SKILL.md:118-126	個別には強いが、primary化が必要
5. まだ欠けていること
5.1 route-memory registry

最大の欠落はこれです。

現行のPointer Mapは、offloaded context artifact の復元indexです。
WBSは operational state / gate / candidate band のtrackerです。
Skillは repeatable workflow の手順です。
PDGは route/state-machine/boundary flow です。

しかし、過去成功/失敗ルートをタスク指紋に基づいて照合し、次回の初手行動を決めるregistry は見当たりません。

必要なregistryは、少なくとも次のような構造を持つべきです。

JSON
{
  "route_id": "chatgpt.visible_web.local_zip_upload.codex_desktop.clipboard_attachment.v1",
  "owner_skill": "codex-chatgpt-control",
  "task_family": "visible_chatgpt_file_upload",
  "positive_triggers": [
    "local ZIP",
    "context bundle",
    "send/upload to ChatGPT",
    "Codex Desktop",
    "visible ChatGPT"
  ],
  "negative_triggers": [
    "download ZIP generated by ChatGPT",
    "latest ZIP download",
    "non-ZIP arbitrary file download",
    "OpenAI API"
  ],
  "applies_when": [
    "Codex can use in-app browser clipboard attachment route",
    "user wants to attach a local ZIP/context bundle to ChatGPT"
  ],
  "do_not_use_when": [
    "user asks to download a ChatGPT-generated ZIP",
    "user explicitly requests PC Chrome download route",
    "clipboard attachment route is unavailable"
  ],
  "canonical_first_action": "write application/zip clipboard item in Codex in-app browser, paste, verify visible ZIP chip, then submit once",
  "known_failed_routes": [
    "askWithFiles / file chooser after red Something went wrong banner",
    "Chrome extension chooser.setFiles Not allowed",
    "raw CDP upload",
    "Markdown-wrapped base64 clipboard payload"
  ],
  "success_verification": [
    "visible Zip アーカイブ chip",
    "prompt submitted exactly once",
    "visible completion before capture"
  ],
  "gates": [
    "visible ChatGPT/browser approval",
    "no hidden endpoint",
    "not provider evidence",
    "not citation-ready evidence"
  ],
  "last_verified_at": "2026-06-24",
  "source_pointers": [
    "external/codex-chatgpt-control/references/chatgpt-zip-upload.md"
  ],
  "not_evidence": true
}
5.2 AGENTS.md側の軽量発火点

AGENTS.mdにはSkill Router Preflightはありますが、Route Memory Preflightはありません。

追加するなら長文手順ではなく、次のような短いdispatcherで十分です。

Before choosing an operation route for browser, upload/download, provider, external search,
tool bridge, recurring blocker, or previously seen failure class, run Route Memory Preflight:
check the local route-memory registry for exact positive/negative trigger matches, known
failed routes, canonical first action, and gates. If an entry matches, prefer its canonical
first action over rediscovery. If no entry matches, continue with the selected Skill.

詳細手順は registry / Skill / PDG / tests 側に置くべきです。これは AGENTS.md をdispatcherに保つ既存方針と一致します（AGENTS.md:66-67, .agents/skills/research-x-skillization-intake/SKILL.md:21-33, .agents/skill-references/governance-quality-contract.md:19-23）。

5.3 WBS leaf

WBSには Future local hardening として Additional bulky-output offload coverage、CLI/app review polish、Additional deterministic evals がactiveであります（tools/wbs_viewer/projects/research-x-work-state.json:2007-2094）。しかし、Route MemoryそのもののWBS leafはありません。

実装するなら、Codex foundation adjuncts 配下に新leafを置くのが妥当です。Future local hardening ではなく、常用パイプラインに昇格させるなら foundation adjunct です。

例:

4.6 Route Memory Registry and Preflight
decision_band: project_state
gate: route_memory_preflight_no_provider_no_network_by_default
status: active -> complete
artifact_pointer: .codex/route_memory/route-memory.json
owner_doc: AGENTS.md
evidence_status: not_evidence
answer_support_allowed: false
stop_condition: Stop if route-memory entries are used as evidence, provider permission, or external-action approval.
5.4 Pointer Map entry

registryを作るなら、.codex/context_offloads/pointer-map.json にentryが必要です。
ただしPointer Mapは選択ロジック本体ではなく、registry artifactのhash/size/restore hintを保証するため に使うべきです。

5.5 PDG flow

README.codex.md と docs/memory-pipeline-v2.md はPDGの役割を route/state-machine/boundary flow としています（README.codex.md:17-18, README.codex.md:92-94, docs/memory-pipeline-v2.md:112-121）。

したがって Route Memory Preflight はPDG向きです。

必要なflowは例えば次です。

Request
-> Skill Router Preflight
-> Route Memory Index Lookup
-> Exact match?
   yes -> Gate check -> Canonical first action -> Verification signal -> Continue / stop
   no  -> Selected Skill normal workflow
-> Unknown blocker?
   yes -> Local diagnosis + conditional world lane / sidecar
-> Phase boundary Skill check
-> Final route/evidence/gate check

ただし、今回のZIPには docs/pdg/*.pdg 本体がないため、既存PDGとの統合差分はここでは検証できません。

5.6 Skill更新

必要なSkill更新は2系統です。

1つ目は research-x-skillization-intake。
Routing Tableに “recurring operation route / route memory / known failure class” を追加し、Route Memory Registryをどのsurfaceに置くかを明確化するべきです。

2つ目は external/codex-chatgpt-control と external/chatgpt-control-router。
ChatGPT ZIP uploadについて、現在の fallback 文言を primary canonical route に変えるべきです。

現状:

external/codex-chatgpt-control/SKILL.md は「normal askWithFiles / file chooser upload fails のとき canonical upload fallback を使う」と読めます（external/codex-chatgpt-control/SKILL.md:84-91）。

external/codex-chatgpt-control/references/chatgpt-zip-upload.md も “Use this path when a normal file chooser / askWithFiles upload is blocked” としています（external/codex-chatgpt-control/references/chatgpt-zip-upload.md:7-10）。

external/chatgpt-control-router/SKILL.md も “If normal askWithFiles or file chooser upload fails” としています（external/chatgpt-control-router/SKILL.md:118-126）。

これでは、次回また通常routeを1回試してからfallbackする余地があります。

5.7 tests

Route Memoryを「標準パイプライン」にするなら、テストが必要です。

最低限:

tests/test_route_memory_registry.py

registry schema

every entry has not_evidence: true

every entry has positive/negative triggers

every entry has canonical_first_action / known_failed_routes / gate / verification_signal

source pointer exists

tests/test_chatgpt_zip_upload_route_memory.py

local ZIP/context bundle upload to visible ChatGPT matches clipboard route

ZIP download does not match upload route

askWithFiles / file chooser are not first action for the known Codex Desktop ZIP upload case

tests/test_agents_route_memory_dispatcher.py

AGENTS.md contains Route Memory Preflight dispatcher

dispatcher does not grant provider/network/browser permissions by itself

tests/test_route_memory_not_evidence.py

registry entries cannot be answer support

Pointer Map marks registry as not_evidence

6. 常用フル稼働にする場合の推奨パイプライン

「常用フル稼働」は、全部を毎回重く実行する ではなく、軽い制御面は毎回ON、重い探索面は条件付きON と定義すべきです。

6.1 常時ONにするもの
A. Skill Router Preflight

既存の AGENTS.md / research-x-skillization-intake のまま常時ONでよいです。

request/context -> candidate Skill

candidate Skill -> reverse-check

primary/secondary/not_selected分類

route: ...; external actions: ... を出す

B. Route Memory Preflight

新設すべきです。これはlocal JSON lookupであり、ネットワークもproviderも使いません。

処理は次です。

1. selected Skill / task family / requested artifact / environment surface を抽出
2. route-memory registry を軽く照合
3. exact positive match かつ negative triggerなしなら canonical_first_action を採用
4. matchが stale / partial / gated なら route_memory=needs_review とする
5. matchなしなら route_memory=none として通常Skillへ

作業前の出力例:

route: codex-chatgpt-control; external actions: needs approval
route detail: primary=codex-chatgpt-control; secondary=route-memory-preflight, provider/browser gate
route memory: selected=chatgpt.visible_web.local_zip_upload.codex_desktop.clipboard_attachment.v1; first_action=clipboard_zip_attachment; skipped_known_failed=askWithFiles,file_chooser
C. Gate Matrix Check

既存のno-quota/provider/browser/network/MCP/connector/install/secrets/destructive gatesは常時ONでよいです。

特にRoute Memoryは 外部行動の許可を与えるものではない と明記すべきです。

route-memory entry != provider permission
route-memory entry != browser approval
route-memory entry != evidence
route-memory entry != citation
D. Phase-Boundary Skill Check

既存の research-x-skillization-intake のフェーズ境界チェックを維持すべきです（.agents/skills/research-x-skillization-intake/SKILL.md:88-113）。

Route Memoryもフェーズ境界で再確認します。

例:

upload task -> answer capture task

text-only consultation -> artifact download

local diagnosis -> external search

provider-free local path -> provider/API path

6.2 条件付きONにするもの
A. detailed route record read

Route Memory indexにmatchしたときだけ詳細entryを読む。
毎回全entryを読む必要はありません。

B. サブエージェント

AGENTS.mdの現行方針どおり、最新の明示ユーザー指示で許可/要求されている場合に使うべきです（AGENTS.md:267-282）。

常時ONにするのは「サブエージェント使用可否の判定」であり、「毎回spawn」ではありません。

推奨条件:

non-trivial exploration / research

unknown blocker

repeated failure pattern

independent read-only/code-inspection taskに分割可能

active user policy permits/requires sub-agents

C. 世界中の探索結果を参照するレーン

これは常時ONではなく、条件付きで必ず検討ON にします。

発火条件:

current external factsが必要

tool/browser/provider surfaceのdrift疑い

unknown error / selector drift / permission blocker

local diagnosisだけでは判断できない

user has permitted network/browser/search or current task already implies it

no-quota provider freezeに触れない検索手段である

AGENTS.mdは、停滞時に targeted search を local diagnosis と並行して行う方針を既に持っています（AGENTS.md:124-129）。これをRoute Memoryと統合し、unknown blocker時には次を渡します。

current situation
objective
exact blocker/error/surface
already attempted routes
known failed routes from route-memory
gates and forbidden actions
success condition
D. ChatGPT Pro / visible ChatGPT相談

これはユーザーが明示的に求めたとき、または現在タスク内で許可されているときのみです。
codex-chatgpt-control は visible ChatGPT web control であり、OpenAI APIやhidden endpointではありませんが、browser/visible ChatGPT actionなのでゲートは必要です（external/codex-chatgpt-control/SKILL.md:12-27, external/codex-chatgpt-control/SKILL.md:40-43）。

6.3 常時OFFにするもの

provider API call

paid/free-tier/trial/zero-dollar quota call

hidden ChatGPT endpoint

ad hoc Playwright/CDP mainline

MCP/plugin/hook install or enablement

automatic Skill growth

source/evidence promotion from GPT/sub-agent/summary output

long reasoning hook

research-x-skillization-intake は hooks を short deterministic checks or notifications に限定し、long reasoning workflowsをhookでsilently forceするなとしています（.agents/skills/research-x-skillization-intake/SKILL.md:199-210）。これは維持すべきです。

7. 具体例: ChatGPT ZIP uploadで次回成功ルートを選ぶ設計
7.1 現行状態の評価

現行の外部Skillには十分重要な情報が入っています。

external/codex-chatgpt-control/SKILL.md は、local ZIP/context bundleをChatGPTへ送る場合、normal askWithFiles / file chooser uploadが失敗したら references/chatgpt-zip-upload.md のcanonical upload fallbackを使い、Codex Desktopで実証済みのpathは in-app browser、tab.clipboard.write(...)、application/zip clipboard item、paste、visible Zip アーカイブ chip確認、promptを1回だけsubmit、と書いています（external/codex-chatgpt-control/SKILL.md:84-91）。

external/codex-chatgpt-control/references/chatgpt-zip-upload.md は、Canonical Success Pathとして、ZIP bytesをdiskから読み、Markdown-wrapped .b64.txt ではなくraw ZIP bytes base64をclipboard itemにし、composerへpasteし、ZIP chipを確認してからpromptを入れ、submit once、visible completionを待つ、としています（external/codex-chatgpt-control/references/chatgpt-zip-upload.md:7-41）。

同referenceは、observed failure pathsとして次を列挙しています。

Codex in-app browser file chooser uploadは chooser.setFiles(...) 成功後にもChatGPT red Something went wrong bannerになり得る

Chrome extension file chooser uploadは Not allowed

direct #upload-files はambiguous / runtime resetの危険

raw CDP upload / Runtime.evaluate はcanonical routeではない

Markdown headers / code fences入りbase64 clipboard payloadは失敗する

（external/codex-chatgpt-control/references/chatgpt-zip-upload.md:43-64）

さらにStop Ruleとして、同じfailed upload routeをloopせず、clear blockerに達したらcanonical clipboard ZIP pathへ切り替えるか、そのpathが不可ならblocker報告する、としています（external/codex-chatgpt-control/references/chatgpt-zip-upload.md:66-71）。

7.2 不十分な点

問題は、このrouteが fallback として記載されていることです。

次回Codexが「local ZIP/context bundleをChatGPTに送る」と判断しても、文言上はまだこう動けます。

askWithFiles / file chooser を試す
-> 失敗する
-> そこで clipboard attachment route に切り替える

ユーザーが問題にしているのは、まさにこの「一度失敗してから思い出す」挙動です。

したがって、確実に発火させるには、次のように変更する必要があります。

7.3 推奨変更: fallbackからprimary canonical routeへ昇格

external/codex-chatgpt-control/SKILL.md の該当箇所は、意味として次のように変えるべきです。

For sending a local ZIP or project context bundle into visible ChatGPT from Codex Desktop,
use the Codex in-app browser clipboard attachment route as the primary canonical path.
Do not start with normal askWithFiles, file chooser, Chrome extension setFiles, direct
#upload-files, raw CDP, or Runtime.evaluate for this known ZIP upload class unless the
user explicitly requests that route or clipboard attachment is unavailable.

external/codex-chatgpt-control/references/chatgpt-zip-upload.md の冒頭も、次の意味に変えるべきです。

Use this path as the primary route for Codex Desktop local ZIP/context-bundle uploads
to visible ChatGPT. The normal file chooser / askWithFiles route is a non-primary route
for this known class because prior observed blockers include ChatGPT red-banner failure
and bridge permission failure.

external/chatgpt-control-router/SKILL.md の ZIP Uploads section も、If normal askWithFiles or file chooser upload fails ではなく、次の意味に変えるべきです。

When the user wants Codex to send a local ZIP/context bundle into ChatGPT for review,
route to the plugin Skill's primary ZIP upload route: Codex in-app browser clipboard
attachment. Do not confuse this with ZIP download.
7.4 Route Memory registry entry

上記Skill更新だけでも改善しますが、標準パイプラインとして確実化するには registry entry が必要です。

推奨entry:

route_id:
  chatgpt.visible_web.local_zip_upload.codex_desktop.clipboard_attachment.v1

task_family:
  visible_chatgpt_file_upload

owner_skill:
  codex-chatgpt-control

applies_when:
  - user wants Codex to send/upload/attach a local ZIP or project context bundle
  - target is visible ChatGPT web / GPT Pro consultation
  - environment is Codex Desktop or compatible in-app browser clipboard route

negative_triggers:
  - user wants to download a ZIP generated by ChatGPT
  - user asks for latest ZIP/image/file from ChatGPT Library
  - user wants OpenAI API call
  - user wants arbitrary non-ZIP file download

canonical_first_action:
  - use Codex in-app browser
  - write application/zip clipboard item from raw ZIP bytes
  - paste into composer
  - verify visible ZIP chip / Zip アーカイブ
  - fill prompt after chip is visible
  - submit exactly once
  - wait for visible completion

known_failed_routes:
  - askWithFiles/file chooser after red Something went wrong banner
  - Chrome extension chooser.setFiles Not allowed
  - direct #upload-files click
  - raw CDP upload / Runtime.evaluate
  - Markdown-wrapped base64 payload

verification_signal:
  - visible ZIP chip
  - one submitted prompt
  - stable final assistant response before capture

gates:
  - visible ChatGPT/browser action approval
  - no hidden endpoints
  - ChatGPT output is consultation, not project evidence
  - no provider API permission implied

not_evidence:
  true
7.5 発火確認テスト

追加すべきテストは次です。

Given:
  task_family = visible_chatgpt_file_upload
  artifact = local .zip / context bundle
  target = ChatGPT / GPT Pro
  environment = Codex Desktop

Expect:
  selected route_id = chatgpt.visible_web.local_zip_upload.codex_desktop.clipboard_attachment.v1
  first action = clipboard application/zip attachment
  not first action = askWithFiles / file chooser / CDP / Chrome extension setFiles

また、ZIP downloadとの混同防止も必須です。

Given:
  user asks for latest ZIP generated by ChatGPT

Expect:
  route = visible PC Chrome Library download route
  not route = in-app browser clipboard upload

この区別は既に external/chatgpt-control-router/SKILL.md にあります。ZIP downloadでは Library start、visible PC Chrome route、download event/saveAs、saved file verificationを使うとされています（external/chatgpt-control-router/SKILL.md:81-116）。この既存境界は壊してはいけません。

8. 実装候補の配置先比較
配置先	何を置くべきか	置くべきでないもの	判断
AGENTS.md	Route Memory Preflightを必ず見る、という短いdispatcher。外部行動ゲートを破らないこと	route registry本体、長い個別手順、全失敗ログ	必須。ただし短く
.codex/route_memory/route-memory.json など新registry	過去成功/失敗route、task fingerprint、positive/negative trigger、canonical first action、known failed routes、verification signal、gates	evidence、citation、provider permission	最重要
WBS leaf	Route Memory pipelineのstatus/gate/artifact pointer/stop condition	詳細手順、長い失敗ログ	必須。operational stateとして
Pointer Map entry	registry artifactのpath/hash/size/restore hint/not_evidence	route選択ロジックそのもの	必須。復元保証として
PDG flow	Route Memory Preflightの状態遷移、gate、fallback、world lane分岐	route entryの全データ	推奨。ZIP内ではPDG本体未確認
research-x-skillization-intake	Route Memoryをどのsurfaceに置くか、routing ambiguity時にどう扱うか	ChatGPT ZIPの具体手順	推奨
external/codex-chatgpt-control	ChatGPT ZIP uploadのprimary canonical path、stop rule、known failure route	research_x固有のWBS/Pointer policy	必須
external/chatgpt-control-router	ChatGPT/GPT自然言語依頼をplugin Skillへroute。ZIP upload/downloadの分岐	個別ブラウザscript	必須
research-x-parallel-review	unknown blocker時のsidecar role設計、親統合	provider/browser許可の自動付与	既存で概ね十分
search-quality-contract	world lane / external research / sidecar結果をcandidate/hint扱いにする	source-of-truthやevidence promotion	既存で概ね十分
hook/plugin	registry schema lint、route-memory static validation、notification程度	毎回browser/GPT/sub-agentを勝手に起動する長いworkflow	後回し。原則不要
MCP/automation	live external dataやscheduled monitorが必要になった場合のみ	Route Memoryの基本選択	今回は不要
9. 推奨実装順
Step 1: Route Memory registryを新設

推奨場所:

.codex/route_memory/route-memory.json

必要ならschemaも追加します。

.codex/route_memory/route-memory.schema.json

これは evidence ではなく control-plane artifact です。

Step 2: ChatGPT ZIP upload entryを最初のrouteとして登録

最初のentryは、今回の具体例だけでよいです。

chatgpt.visible_web.local_zip_upload.codex_desktop.clipboard_attachment.v1

このentryには known_failed_routes を必ず入れます。
ここがないと、次回Codexが「念のためfile chooserから」と再探索します。

Step 3: external Skillをfallbackからprimaryへ修正

対象:

external/codex-chatgpt-control/SKILL.md
external/codex-chatgpt-control/references/chatgpt-zip-upload.md
external/chatgpt-control-router/SKILL.md

修正方針:

local ZIP/context bundle upload to visible ChatGPT from Codex Desktop
= clipboard attachment route is primary canonical path

askWithFiles / file chooser は、この既知classでは初手にしない。

Step 4: AGENTS.md に短い Route Memory Preflight dispatcher を追加

Native Skill Invocation または Auto Skill Routing の近くに短く入れるのがよいです。

内容は次だけです。

Before selecting an operation route for recurring browser/upload/download/tool-bridge/provider/search blockers, check the local route-memory registry for exact match, known failed routes, canonical first action, and gates. Prefer a matching canonical first action over rediscovery. This does not grant external-action, provider, network, browser, MCP, connector, install, or evidence permission.

長い個別手順は入れない。

Step 5: WBS leafを追加

Codex foundation adjuncts 配下が妥当です。

理由は、これはfuture hardeningではなく、Codex運用の常用基盤だからです。

Step 6: Pointer Map entryを追加

route-memory.json をPointer Mapに入れます。

必須:

pointer_id

artifact_path

artifact_kind: route_memory_registry

owner_plane: operation_route_memory

restore_hint

sha256

char_count

byte_count

not_evidence: true

Step 7: PDG flowを追加

推奨:

docs/pdg/route-memory-preflight.pdg
docs/pdg/out/route-memory-preflight.svg

ただし、今回のZIPには docs/pdg 本体がないため、既存PDG命名規則やrender環境との整合は実repo側で確認が必要です。

Step 8: testsを追加

最低限:

tests/test_route_memory_registry.py
tests/test_chatgpt_zip_upload_route_memory.py
tests/test_agents_route_memory_preflight.py

既存テスト設計に合わせるなら、次を検査します。

registry entries are not evidence

registry path is covered by Pointer Map

local ZIP upload selects clipboard route

ZIP download does not select upload route

known failed routes are not selected as first action

AGENTS dispatcher exists and does not grant external/provider permission

Step 9: hook/pluginは最後

hook/pluginは、registry schema lintやstatic validationに限定するなら有効です。
ただし、browser/GPT/sub-agent/world searchをhookで自動起動するのはやめるべきです。

research-x-skillization-intake も、hooks are for short deterministic checks or notifications としており、長いreasoning workflowをhookでsilent forceするなとしています（.agents/skills/research-x-skillization-intake/SKILL.md:199-210）。

10. 逆にやってはいけないこと

AGENTS.mdにChatGPT ZIP uploadの長い手順を丸ごと入れること
AGENTS.md はdispatcherです。詳細はSkill/reference/registry/PDG/testsに分けるべきです。

Route MemoryをPointer Mapだけで代用すること
Pointer Mapはhash/restore indexです。route selection registryではありません。

WBS leafを成功/失敗ログ本文の置き場にすること
WBSはoperational stateです。既存テストもnotesを短く保つことを要求しています（tests/test_research_x_work_state_wbs.py:62-75）。

PDGをroute registryにすること
PDGはflow/state-machine/boundaryです。routeごとのpositive/negative triggerやknown failure listはregistryのほうが向いています。

sub-agentや外部検索を毎回無条件spawnすること
常時ONにすべきなのは「使うべきか判定する制御面」です。spawn/search/browser/GPTは条件付きです。

Route Memory entryを外部行動の承認として扱うこと
registryに成功routeがあることは、browser/network/provider/GPT/MCP/connector/install承認を意味しません。

ChatGPT/GPT Pro出力をresearch_xのevidenceにすること
既存契約ではChatGPT captures、sub-agent notes、compressed summariesはnot evidenceです（docs/memory-pipeline-v2.md:82-97）。

ChatGPT ZIP uploadとZIP downloadを混同すること
Uploadはin-app browser clipboard attachment route。
Downloadはvisible PC Chrome / Library / download event route。
この分岐は external/chatgpt-control-router/SKILL.md:66-126 で既に明確です。

known failed routeを「念のため」もう一度初手にすること
今回の核心です。askWithFiles / file chooser / Chrome extension setFiles / raw CDP upload は、今回のknown failure classでは初手にしてはいけません。

Skillの発火漏れを日本語triggerの羅列だけで解決しようとすること
research-x-skillization-intake は、AGENTS.mdに日本語synonymを詰め込むのではなく、小さなdispatcherとSkill-owned trigger descriptionsを使えとしています（.agents/skills/research-x-skillization-intake/SKILL.md:78-86）。

総合判断としては、ユーザーの主張はかなり妥当です。ただし、「今の構成だけで完全に解決済み」ではありません。既存のAGENTS/Skill/WBS/Pointer設計は土台として良いですが、Route Memoryを常用フル稼働にするには、構造化registry + AGENTS軽量preflight + ChatGPT ZIP routeのprimary化 + 回帰テスト が必要です。
