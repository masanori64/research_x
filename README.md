# research_x

research_x は、ユーザーが選んだ情報源をローカルで管理し、LLMから使える形で
探索・整理・根拠確認する KnowledgeOps / personal search 基盤です。X/Twitter から
始まり、明示的に採用したノート、Web、動画 transcript、GitHub、公式文書、PDF
などへ拡張します。

設計原則は「探索は広く、断定は厳密に」です。候補を見つけることと、根拠付きで
答えることを同じ処理にしません。

## 正典と現在地

- Architecture / policy canon: `docs/research_x_canon.md`
- Current project state: `control/project_state.json`
- Authority classification: `control/authority_map.toml`
- Thin permission profile: `.codex-project/control-profile.json`
- Agent operating rules: `AGENTS.md`

現在状態はWBSや過去レポートではなく、`control/project_state.json` が保持します。
旧レポート、root plan、生成inventory、旧WBSはarchive/history扱いで、新repoへ
持ち込みません。repo-local Skillsも廃止済みです。

## 使い分け

- `ObjectiveRoute` はどの検索経路・fallbackを使うかを選びます。
- `OutputMode` はどこまでの権威で返せるかを選びます。
- `source_bundle_id` と `source_restore_id` は、同じ厳密な復元lineageを支える
  compatibility nameです。
- Persistence は `none` / `trace` / `artifacts` を明示し、監査traceだけを残す
  要求と、派生artifactも保存する要求を分けます。

## Providerと権限

Provider経路は一律無効ではありません。実効権限はCodex foundation側の汎用
permission GUI/effective profileと現在のユーザー指示から決まり、このrepoの薄い
profileがproject固有gateを提供します。API Budget Guardはそれとは独立して、
paid/quota requestの上限・見積り・usage/auditを検査します。

現在状態には、Gemini embeddingの`limit_10`と`limit_100`実行済み、embedding
input A-D完了、lineageのない旧行のquarantine、semantic promotionの`hold`が記録
されています。provider quality、SkillMap、specialized spaces、OCR/media provider
lane、最終acceptanceは未完了です。詳細と不明点はcurrent-state JSONを参照します。

## Development

```powershell
uv sync
uv run python -m research_x --help
uv run python -m research_x memory --help
uv run pytest -m fast -q
uv run ruff check src\research_x tests
```
