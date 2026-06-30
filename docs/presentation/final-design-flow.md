# research_x Final Design Flow

この文書は、`docs/memory-pipeline-v2.md` を設計名ベースで読み替えた派生ビューです。
source of truth、証拠、citation、provider 実行許可ではありません。

## 設計名に乗せた全体の流れ

```text
Narrow Codex Bridge
  ↓
Source Layer
  ↓
Searchable Documents / Retrieval Projections
  ↓
Retrieval And Route Portfolio
  ↓
Provider / API Budget Gate
  ↓
Search Results
  ↓
Source Bundle Restoration
  ↓
Evidence Layer
  ↓
Context Chunk Layer
  ↓
Citation Layer
  ↓
ObjectiveRoutePolicy
  ↓
Workflow Trace Layer
  ↓
Answer Boundary
  ↓
Tool Interface Layer
  ↓
Eval / Audit / Feedback Loop
  ↓
Rebuild / Route Promotion / Gate Review
```

## 各層の役割

### Narrow Codex Bridge

Codex から `research_x` に渡すものを狭くする境界。
入力は query、objective、context budget、reviewed source candidate。
出力は evidence status、citation-ready answer または abstention、
provider-gated state、audit trace。

Codex transcript、Skill 自動編集権限、provider 実行許可、root instructions は
`research_x` の証拠パイプラインに入れない。

### Source Layer

証拠の出発点。X 取得済み DB、media、raw payload、account / bookmark ownership、
provider run artifacts、外部 source candidate を持つ。

主な raw source は tweets、account_bookmarks、collection_items、tweet_edges、
media、raw_payloads、accounts、provider_runs。

### Searchable Documents / Retrieval Projections

検索しやすい形に直した再生成可能ビュー。
memory_documents、retrieval text、labels、summaries、OCR text、VLM observations、
embeddings、query transforms、index projections がここに入る。

ここは証拠ではない。source ID、source hash、projection generation、
stale / tombstone state、restore path を持つ必要がある。

### Retrieval And Route Portfolio

質問に対して候補を出すルート群。

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

FTS、BM25、metadata、exact、relation はローカル中核ルート。
semantic vectors、OCR、rerank、Reader、external Web、LLM-context、managed RAG は
provider または追加 gate の対象になりやすい。

Corpus2Skill は navigation / route hint。citation-ready evidence ではない。
Agentic RAG / managed RAG は orchestration または managed-reference candidate。
source bundle と citation を置き換えない。

### Provider / API Budget Gate

provider、quota、network 送信を止める境界。
no-quota freeze 中は、free-tier、trial-credit、zero-dollar quota も止める。

停止対象は real embeddings、native media embeddings、rerankers、Reader extraction、
OCR、classifiers、answer engines、relation judges、external search、LLM-context、
managed RAG、real-model prompt-contract validation。

provider が許可された場合でも、API Budget Guard、offline estimate、
smallest-limit canary、stop condition が必要。

### Search Results

検索ルートから出た候補。
score、route、why_relevant、skip reason を持つ。
ただし、source bundle に戻るまでは証拠ではない。

### Source Bundle Restoration

検索候補を raw source に戻す処理。
tweet、quote relation、media relation、author、bookmark account、URL、
timestamp、source hash、provider / run metadata を復元する。

### Evidence Layer

復元された source bundle、context chunk、citation annotation、answer support、
source-backed governance record を扱う層。

Evidence Layer は「検索で当たった」ことではなく、
「元情報に戻せて、回答入力や citation に使えるか」を扱う。

### Context Chunk Layer

回答に渡せる大きさと境界に切った入力。
unsupported chunk、stale projection、missing media provenance、
untrusted tool text は隠さず workflow state と eval output に残す。

### Citation Layer

context chunk と source ID を結びつける層。
generated labels、route scores、summaries、diagrams、pointer maps、
compressed previews、consultation captures は citation ではない。

### ObjectiveRoutePolicy

query / objective に応じて候補ルートを選ぶ。
ただし source bundle、citation verification、answer abstention、
workflow trace、eval gate を置き換えない。

### Workflow Trace Layer

route choice、fallback、provider skip、evidence level、citation support、
budget / offload state、OCR / media status、failure state、stop reason を記録する。

`store=True` の workflow run は operational trace row を保存できるが、
raw source、governance、feedback、provider、answer support の mutation を許可しない。

### Answer Boundary

回答できるか、止めるかを決める境界。
status は answer、abstain、needs_review、source_not_restored、
citation_missing、provider_gated、blocked。

正しそうな文章でも、citation-ready support がなければ完成回答ではない。

### Tool Interface Layer

AI が呼び出す安定した JSON 契約。
内部 workflow JSON が変わっても、この層の契約は安定させる。

返すものは status、evidence_level、citations、trace。

### Eval / Audit / Feedback Loop

answerability、relevance、citation coverage、restoration rate、route gaps、
provider-gated lanes、feedback を見る。

品質改善は、検索ルートの追加だけではなく、source restoration、
context chunk、citation、answer boundary の失敗理由を見て進める。

### Rebuild / Route Promotion / Gate Review

検索 projection は再生成できる。
ルート昇格は eval / audit / feedback を通す。
provider 系ルートは gate review と budget evidence が揃うまで昇格しない。

## 最終案の読み方

最終案は vector-first、router-first、diagram-first ではない。
evidence-first の設計。

BM25、semantic search、Corpus2Skill、Agentic RAG、OCR、Reader、rerank、
external search は全部候補ルートとして入る。
しかし、どのルートで候補を出しても、最後は source bundle、context chunk、
citation、answer boundary を通す。
