# GPT Pro Request: Codex Operation Pipeline / Route Memory Review

このスレッドと添付ZIP内の情報だけを使ってください。別スレッド、ほかのChatGPT会話、過去会話、あなたの曖昧な記憶、一般論、外部に残っているかもしれない文脈は一切参照しないでください。

この依頼では、添付ZIPに入っていない文脈は存在しないものとして扱ってください。過去に似た相談を受けた記憶があっても、それを前提に判断しないでください。

## 依頼の背景

research_x では、Codex が過去に探索して成功・失敗した手順を次回に活かせず、同じ問題を 0 から探索し直すことがありました。

具体例:

- ChatGPT/GPT Pro に project context ZIP を送る作業で、以前は Codex in-app browser の clipboard attachment route で成功していた。
- しかし次回、Codex が通常の `askWithFiles` / file chooser 系から再探索し始め、ユーザーが「内部ブラウザで以前成功してるよね。なんでその通りにやらないの」と指摘した。
- その後、`codex-chatgpt-control` Skill 側には ZIP upload fallback として、in-app browser clipboard attachment route が canonical success path として明記された。

ユーザーが検証したい論点は2つです。

1. 過去の探索、成功例、失敗例があるなら、Codex は走り始める前にそれを参照すべき。
2. 未知の問題に当たった時は、Codex が闇雲に試行錯誤するだけでなく、メイン作業を止めずに、現在状況・目的・直面している問題・そのタスクで優先する制約や成功条件をサブエージェントや外部調査へ渡して、世界中の探索結果を参照できるようにしたい。

ユーザーが求める分類:

- 1つ目は「過去の自分を参照する」。
- 2つ目は「世界中の人が探索したものを参照する」。
- これを個別Skillとして低いレイヤーに置くのではなく、Codex運用パイプラインの標準動作として常用したい。

## ユーザーの反証

Codex は当初、常用フル稼働には以下のデメリットがあると述べました。

- 過去の成功ルートが古くなると、逆に間違った初手になる。
- タスクの指紋判定を誤ると、似ているだけの別問題に古い手順を当ててしまう。
- 小さい作業にも毎回重い事前確認が走ると、かえって遅くなる。
- サブエージェントの調査結果がノイズや競合判断を増やす可能性がある。
- 外部検索やGPT Pro相談は、ネットワーク、プライバシー、プロバイダ、ToS、コストのゲートを持つ。

ユーザーの反証:

1. 1つ目と2つ目について、今の Markdown / WBS / PDG / Pointer Map 構成で本当にそれが起きるのか、実ファイルに基づいて検証してほしい。
2. 4つ目について、サブエージェント調査結果はあくまで事実情報・行動補助・Codexが参照できるコンテキスト幅を広げる材料として扱うので問題ない。現状の弱い仕組みでもそうなっているはず。
3. 3つ目は4つ目の扱いで解決できないか。
4. 5つ目も、現在のゲート運用なら問題なく動けるのではないか。
5. ユーザーは常用フル稼働を希望している。
6. ただし「標準パイプライン」と言われても、また発火しないものになりそうなので検証してほしい。

## Codex xhigh 側の暫定判断

以下は判断材料です。正しい前提として扱わず、添付ZIP内の実ファイルに照らして妥当性を検証してください。

Codex は最初、次のように判断しました。

- AGENTS.md には Skill Router Preflight、停滞時の並行検索、サブエージェント探索の骨格がある。
- `research-x-parallel-review` と `search-quality-contract` / `evidence-workflow-quality-contract` は、サブエージェント出力を最終判断ではなく候補/ヒントとして扱い、親Codexが統合判断する設計になっている。
- WBS/PDG/Pointer Map/Markdown の分担は、古いGPT出力や歴史的Markdownを証拠・active trackerとして誤用しないためにはかなり強い。
- Pointer Map は hash/size/restore hint を持ち、テストで現物一致を確認している。
- X/GPT historical Markdown は active path から外されている。

ただし Codex は一度、AGENTS.md側の既存実装を過小評価して、次のように述べました。

> Route Memoryそのものはまだ欠けています。

その後、ユーザーから「AGENTS.md見てないの？」と指摘され、Codex は次のように訂正しました。

> AGENTS.mdには、常用パイプラインの骨格はすでにある。
> 足りない可能性があるのは、AGENTS.mdではなく、そこから参照される過去成功/失敗ルートの構造化レジストリ。
> 今回の ChatGPT ZIP に関しては、codex-chatgpt-control 側に canonical ZIP upload fallback まで入っているので、個別例としては「もう成功ルートを選べる状態」にかなり近い。

## 添付ZIPで特に見てほしいファイル

- `AGENTS.md`
- `README.codex.md`
- `PROJECT.md`
- `docs/memory-pipeline-v2.md`
- `docs/pipeline.md`
- `.agents/skills/research-x-skillization-intake/SKILL.md`
- `.agents/skills/research-x-parallel-review/SKILL.md`
- `.agents/skills/research-x-context-budget/SKILL.md`
- `.agents/skill-references/search-quality-contract.md`
- `.agents/skill-references/evidence-workflow-quality-contract.md`
- `.agents/skill-references/governance-quality-contract.md`
- `tools/wbs_viewer/projects/research-x-work-state.json`
- `.codex/context_offloads/pointer-map.json`
- `tests/test_markdown_information_architecture.py`
- `tests/test_context_offload_pointer_map.py`
- `tests/test_research_x_work_state_wbs.py`
- `external/codex-chatgpt-control/SKILL.md`
- `external/codex-chatgpt-control/references/chatgpt-zip-upload.md`
- `external/chatgpt-control-router/SKILL.md`

## GPT Proに判断してほしいこと

1. ユーザーの反証は、添付内の現在の構成を見たうえでどこまで正しいか。
2. Codex xhigh の訂正後判断は妥当か。妥当でない部分があれば具体的に指摘してほしい。
3. 「AGENTS.mdには常用パイプラインの骨格がある」という評価は正しいか。
4. それでもなお足りないものがあるとすれば、それは何か。
   - AGENTS.mdの追記か
   - WBS leaf か
   - Pointer Map entry か
   - PDG flow か
   - Skill更新か
   - hook/plugin/MCP/automationか
   - 別の route-memory registry か
5. 常用フル稼働にする場合、どこまでを常時ONにして、どこからを条件付きONにすべきか。
6. 今回の ChatGPT ZIP upload 具体例では、次回 Codex が成功ルートを選ぶために、今の状態で十分か。不十分なら最小ではなく、確実に発火する設計を提案してほしい。
7. 「過去の自分を参照する」レーンと「世界中の人の探索を参照する」レーンを、Codex運用パイプラインにどう統合すべきか。
8. 必要な変更範囲を過度に縮小せず、ただし既存の no-quota / provider / evidence / source-of-truth 境界は壊さない実装方針を提案してほしい。

## 出力してほしい形式

以下の見出しで、実装判断に使える詳細な回答をください。

1. 結論
2. ユーザー反証の検証
3. Codex xhigh判断の妥当性
4. 現行AGENTS.md / Skill / WBS / PDG / Pointer Mapで既に解決していること
5. まだ欠けていること
6. 常用フル稼働にする場合の推奨パイプライン
7. 具体例: ChatGPT ZIP uploadで次回成功ルートを選ぶ設計
8. 実装候補の配置先比較
9. 推奨実装順
10. 逆にやってはいけないこと

曖昧な一般論ではなく、添付内の具体ファイル名、既存ルール、既存テスト、既存Skillに触れて判断してください。
