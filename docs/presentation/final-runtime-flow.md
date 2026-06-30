# research_x Final Runtime Flow

この文書は、`docs/memory-pipeline-v2.md` を人間が読みやすい実行順に並べた
派生ビューです。source of truth、証拠、citation、provider 実行許可ではありません。

## 目的

最終案の `research_x` は、X の保存データを AI が呼び出せるローカル検索ツールにする。
ただし、検索候補・要約・スコア・図・provider 出力をそのまま根拠にしない。
すべての回答は source bundle、context chunk、citation を通ってから返す。

## 全体の流れ

```text
Codex / AI / ユーザー
  ↓
query / objective / context budget / reviewed source candidate を research_x に渡す
  ↓
Source Layer
  - X 取得済み DB
  - tweets
  - account_bookmarks
  - collection_items
  - tweet_edges
  - media
  - raw_payloads
  - accounts
  - provider_runs
  - 外部 source candidate
  ↓
Searchable Document Projection
  - memory_documents
  - retrieval text
  - labels
  - summaries
  - OCR text
  - VLM observations
  - embeddings
  - query transforms
  - index projections
  ※再生成可能な検索用ビュー。証拠ではない
  ↓
Route And Retrieval
  - exact anchors
  - SQLite FTS / BM25
  - metadata search
  - relation expansion
  - retrieval-text projection
  - semantic vectors
  - sparse / late-interaction / rerank candidates
  - OCR / media preparation
  - Corpus2Skill navigation
  - graph / topic hints
  - external Web candidates
  - managed-reference / managed RAG candidates
  ↓
Provider / API Budget Gate
  - real embeddings
  - native media embeddings
  - rerankers
  - Reader extraction
  - OCR
  - classifiers
  - answer engines
  - relation judges
  - external search
  - LLM-context
  - managed RAG
  ※no-quota freeze 中は provider_gated で止める
  ↓
Search Results
  - 候補一覧
  - score
  - route
  - why_relevant
  - skip reason
  ※まだ証拠ではない
  ↓
Source Bundle Restoration
  - tweet
  - quote relation
  - media relation
  - author
  - bookmark account
  - URL
  - timestamp
  - source hash
  - provider / run metadata
  ↓
Source Bundles
  ※元に戻せる根拠単位
  ↓
Context Chunk Generation
  - 回答に入れられる範囲へ切る
  - unsupported chunk を見える状態で残す
  - stale projection を見える状態で残す
  - missing media provenance を見える状態で残す
  - untrusted tool text を見える状態で残す
  ↓
Citation Annotation
  - context chunk と source ID を結びつける
  - generated label / summary / diagram / pointer map は citation にしない
  ↓
ObjectiveRoutePolicy / Workflow
  - route choice
  - fallback
  - provider skip
  - evidence level
  - citation support
  - budget / offload state
  - OCR / media status
  - failure state
  - stop reason
  ↓
Answer Boundary
  - answer
  - abstain
  - needs_review
  - source_not_restored
  - citation_missing
  - provider_gated
  - blocked
  ↓
Tool Interface Layer
  - stable AI-callable JSON
  - status
  - evidence_level
  - citations
  - trace
  ↓
Eval / Audit / Feedback
  - answerability
  - relevance
  - citation coverage
  - restoration rate
  - route gaps
  - provider-gated lanes
  - feedback
  ↓
必要なら Rebuild / Re-eval
```

## API stop の扱い

API stop は、provider 系ルートを設計から消すためのものではない。
最終案では、provider 系ルートを候補として残したまま、
`Provider / API Budget Gate` で止める。

停止対象は real embeddings、native media embeddings、rerankers、Reader extraction、
OCR、classifiers、answer engines、relation judges、external search、LLM-context、
managed RAG など。

no-quota freeze 中は、これらのルートは `provider_gated` として trace に残す。
fake / local / monkeypatched / offline estimate は、provider 送信をしない範囲だけ許可する。

## 重要な不変条件

```text
raw source
!= searchable document
!= search result
!= source bundle
!= context chunk
!= citation
!= answer
```

この不変条件が崩れると、検索候補や生成物が根拠に見えてしまう。
最終案では、候補ルートをどれだけ増やしても、回答は必ず source bundle、
context chunk、citation、answer boundary を通る。
