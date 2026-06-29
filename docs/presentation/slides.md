---
marp: true
theme: default
paginate: true
size: 16:9
style: |
  section {
    color: #1f2933;
    font-family: "Aptos", "Yu Gothic", "Meiryo", "Segoe UI", sans-serif;
    letter-spacing: 0;
    padding: 54px 72px;
  }
  h1 {
    color: #244766;
    font-size: 40px;
    margin-bottom: 22px;
  }
  h2 {
    color: #244766;
    font-size: 28px;
  }
  p, li {
    font-size: 21px;
    line-height: 1.34;
  }
  table {
    font-size: 16px;
  }
  th {
    background: #e8eef4;
  }
  code {
    font-size: 0.8em;
  }
  section.diagram img {
    display: block;
    margin: 22px auto 0;
    max-height: 410px;
    max-width: 100%;
  }
  .small {
    font-size: 17px;
  }
---

# research_x プロジェクト概要

下請けSI事業者向け 開発者説明資料

<!-- claim: claim-project-purpose -->

- 既存XコレクションDBを、AIエージェントがローカル検索できる memory/search system にする
- 重点は「検索できること」より、出典・文脈・引用可能性を壊さないこと
- 本資料は実装レビュー、見積もり、引き継ぎの前提共有を目的とする

---

# この資料で合わせたい理解

<!-- claim: claim-sier-context -->

SI事業者側に期待する理解は、画面や単体機能ではなく、責務境界です。

| 観点 | 見るべきこと |
| --- | --- |
| 取得 | Xデータをどのprovider chainで集めるか |
| 保存 | tweet/bookmark/media/edgeをどう正規化するか |
| 検索 | 検索結果をいつ証拠として扱えるか |
| 回答 | citation-readyでない場合にどう止めるか |
| 運用 | provider/API/secretsを誰が承認するか |
| 表現 | C4 Context/Containerまで。UMLクラス図・シーケンス図は出さない |

---

# C4 Context: システム境界

<!-- claim: claim-runtime-architecture -->
<!-- _class: diagram -->

![Runtime boundary](assets/runtime-boundary.svg)

<p class="small">research_xを中心に、利用者、AIエージェント、既存X SQLite、外部Provider/API承認ゲート、資料生成レーンを分けて見る。</p>

---

# C4 Container: 実装コンテナ

<!-- claim: claim-c4-container-boundary -->
<!-- _class: diagram -->

![C4 container](assets/c4-container.svg)

<p class="small">UML詳細図ではなく、SI事業者が見積もり・分担・レビューで使う主要実装単位に絞る。</p>

---

# 取得パイプライン

<!-- claim: claim-acquisition-chain -->

profile/search/url/bookmarks ごとに provider chain を切り替え、1つのproviderに依存しない構成です。

| target | chainの考え方 |
| --- | --- |
| profile | `twscrape_raw -> scweet -> twikit -> ... -> scrapy` |
| search | `scweet` を先頭にした検索向けchain |
| url | URL解決向けに `twscrape_raw/twikit` を優先 |
| bookmarks | private session前提でbookmark専用providerを含める |

失敗は `timeout`、`rate_limited`、`auth_failed`、`schema_drift`、`dom_drift` 等へ分類し、attemptごとに evidence JSON を残します。

---

# Bookmark と共有Store

<!-- claim: claim-bookmark-store -->

Bookmarkはログインユーザー固有のデータなので、通常tweet取得とは別の注意が必要です。

| 保存先 | 意味 |
| --- | --- |
| `tweets` | tweet本体のcanonical row |
| `account_bookmarks` | どのログインaccountがbookmarkしたか |
| `collection_items` | どの取得run/targetで観測したか |
| `tweet_edges` | quote/reply等の関係 |
| `media` / `media/` | media provenanceと保存済みlocal file |

同じtweetが通常取得とbookmark取得の両方で見つかっても、別物に増殖させない設計です。

---

# Evidence-first Memory Pipeline

<!-- claim: claim-evidence-invariant -->
<!-- _class: diagram -->

![Evidence pipeline](assets/memory-evidence-flow.svg)

<p class="small">検索結果は候補であり、source bundle復元とcitation checkを通るまで回答根拠ではない。</p>

---

# SQLite主要テーブル群

<!-- claim: claim-memory-schema -->

| グループ | 代表テーブル | 役割 |
| --- | --- | --- |
| 検索投影 | `memory_documents`, `memory_document_fts` | rebuildableな検索対象 |
| 証拠入力 | `memory_context_chunks`, `memory_citation_annotations` | 回答入力と引用注釈 |
| 実行追跡 | `memory_workflow_runs`, `memory_workflow_steps` | route/status/stop_reason |
| 評価 | `memory_eval_runs`, `memory_eval_results`, `memory_eval_gate_results` | local eval/audit |
| 予算 | `memory_api_budget_policies`, `memory_api_usage_events` | provider利用管理 |
| 統制 | `memory_governance_records`, `memory_security_boundaries` | governance/security境界 |

---

# Workflow 実行単位

<!-- claim: claim-workflow-execution -->

`run_memory_workflow()` は1回の問い合わせを、状態付きの実行単位として扱います。

1. `plan`: query plan / route plan / objective route plan を作る
2. `context`: local searchからsource-backed context bundleを作る
3. `llm_context`: 承認時のみ外部/LLM contextを追加
4. `answer`: 承認時のみ回答生成し、citation状態を記録
5. `finish`: `status` と `stop_reason` を保存

重要なのは、うまく答えられない場合も `needs_review`、`provider_gated`、`citation_missing` として止まれることです。

---

# Provider/API Gate

<!-- claim: claim-provider-gate -->

現時点のデフォルトは no-quota freeze です。

| 禁止または承認待ち | 理由 |
| --- | --- |
| real embedding / OCR / rerank / Reader | provider quota消費 |
| classifier / answer engine / external search | API Budget Guard前提 |
| free-tier / trial / zero-dollar quota | 「無料」でもquota消費 |
| model download / MCP / plugin / hook | 別の導入・運用リスク |

SI事業者の作業では、fake/local provider、静的検査、monkeypatch済みテスト、offline estimate を先に使います。

---

# 開発入口と作業境界

<!-- claim: claim-dev-entrypoints -->
<!-- claim: claim-sier-boundary -->

| 分類 | 最初に見るもの / 原則 |
| --- | --- |
| CLI | `uv run python -m research_x --help`, `uv run python -m research_x memory --help` |
| テスト | `uv run pytest ...`, `uv run python -m research_x test-diagnose ...` |
| 資料 | `presentation validate-facts/slides`, `npm run presentation:build` |
| 実行可 | local/fake provider、静的検査、deterministic test、互換性を明示したmigration |
| 要承認 | real API、secrets/session、model download、MCP/plugin/hook、破壊的DB変更 |

Python tooling は必ず `uv run ...` 経由。provider-backed command は承認なしに実行しません。

---

# 現状・未確定事項・次アクション

<!-- claim: claim-current-open-items -->
<!-- claim: claim-control-artifacts -->

| 区分 | 状態 |
| --- | --- |
| local architecture | evidence-first boundary とCLI入口は整理済み |
| presentation lane | D2/Marp build、facts/slides validator、PPTX生成済み |
| provider品質検証 | no-quota freeze中。実API評価は未実施 |
| SI事業者への委託範囲 | 契約スコープ、SLA、運用責任分界は別途決定 |
| 注意 | WBS、pointer map、diagram、PPTX、ChatGPT相談結果は証拠ではない |

次は、SI事業者に渡す作業範囲を local-only / provider-gated / secret-sensitive に分けて見積もることです。
