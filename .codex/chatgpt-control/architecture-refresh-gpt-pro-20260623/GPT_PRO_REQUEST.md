# GPT Pro Request: research_x 全体構成刷新レビュー

このスレッドと添付ZIP内の情報だけを使ってください。外部の会話履歴、別スレッド、あなたの曖昧な記憶、一般論を優先しないでください。

## 依頼

`research_x` の現在の構成を、11/WBS Viewer と 35/pdgkit の導入意図を踏まえて、1から刷新する全体プランとして作り直してください。

保守的に「現状に少し足す」方向へ逃げないでください。主眼は、今のプロジェクトで増えすぎているMarkdown文字コンテキストを、WBS/PDG/ポインタへ逃がせる部分は大胆に逃がし、Markdownを薄くすることです。

## 重要な前提

- 11/WBS Viewer は、候補一覧、進捗、残件、gate、planned/actual、artifact pointer のような「作業状態」を外部化できる可能性があります。
- 35/pdgkit は、route、状態遷移、実装境界、判断フローのような「構造」を `.pdg -> validate -> render` で外部化できる可能性があります。
- 現在のMarkdown管理は、判断理由、状態一覧、構造説明、実装順、残件、証拠境界が混ざって肥大化しています。
- ただし、WBS/PDG/SVG/スクリーンショットは evidence ではありません。source bundle、context chunk、citation、answer support は既存の evidence pipeline を通す必要があります。
- `pdgkit-mcp`、provider/API、hook、browser編集の常用化は今回の前提にしないでください。

## やってほしいこと

1. ZIP内の現行設計、11/35正本、直近Codexプランを読んで、現状構成の問題を整理してください。
2. 「Markdownが担うべきもの」「WBSが担うべきもの」「PDGが担うべきもの」「ポインタ/ContextBudgetが担うべきもの」を再定義してください。
3. 現在の `docs/memory-pipeline-v2.md` / `PROJECT.md` / `README.codex.md` / `.codex/chatgpt-control/...` / `tools/...` の役割を刷新案として整理してください。
4. どのMarkdownを薄くできるか、どの内容をWBS/PDGへ移すべきか、具体的に分類してください。
5. 既存の memory evidence pipeline と矛盾しない、実装可能な移行計画を作ってください。
6. 保守的に既存資料を全部残す案ではなく、重複を減らす案にしてください。

## 出力してほしい形式

次の見出しで、実装に渡せる全体プランを出してください。

1. 結論
2. 現状の構造問題
3. 新しい情報アーキテクチャ
4. Markdown削減方針
5. WBS/PDG/Pointer Map の役割分担
6. 既存ファイル別の扱い
7. 移行ステップ
8. テスト/検証計画
9. リスクと停止条件
10. まず実装すべき最小変更セット

曖昧な一般論ではなく、添付内の具体ファイル名・役割・移行先に触れてください。
