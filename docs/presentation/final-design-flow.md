# research_x Final Design Flow

この文書は、`research_x` の最終設計フローを設計名ベースで固定する暫定正本です。
図解、説明、周辺 Markdown の整理はこの設計名と順序を基準にする。

ただし、この文書自体は証拠、citation、provider 実行許可ではない。
回答の根拠は必ず source bundle、context chunk、citation から作る。

## 設計判断

最終案は vector-first、router-first、provider-first、diagram-first ではない。
evidence-first の設計である。

ただし evidence-first は、検索入口を狭くするという意味ではない。

```text
wide candidate generation
  → narrow evidence / answer-authority promotion
  → citation-backed answer or explicit abstention
```

## 分離する4つの概念

```text
SearchLens / RetrievalPolicy       = human bias and retrieval preference
ObjectiveRoutePolicy               = route planning
ProviderApiBudgetGuard             = provider / quota / network execution guard
AnswerAuthorityGatekeeper          = candidate-to-answer-support promotion gatekeeper
```

この4つを混ぜない。

- SearchLens / RetrievalPolicy は検索空間、重み、bias を決める。
- ObjectiveRoutePolicy は候補ルートを選ぶ。
- ProviderApiBudgetGuard は provider / quota / network 実行を止める。
- AnswerAuthorityGatekeeper は候補を answer support に昇格してよいかを見る。

## 設計名に乗せた全体の流れ

```text
Narrow Codex Bridge
  ↓
Source Layer
  ↓
Searchable Documents / Retrieval Projections
  ↓
SearchLens / RetrievalPolicy
  ↓
ObjectiveRoutePolicy
  ↓
Retrieval And Route Portfolio [wide]
  ├─ local lanes
  └─ provider-backed / network / quota lanes
       ↓
       ProviderApiBudgetGuard
       ↓
       candidate result or provider_gated skip
  ↓
Search Results / Candidates
  ↓
AnswerAuthorityGatekeeper [narrow]
  ↓
Answer Boundary
  ↓
Tool Interface Layer
  ↓
Eval / Audit / Feedback Loop
  ↓
Rebuild / Route Promotion / Guard Review

Workflow Trace Sidecar:
  route choice / fallback / provider skip / evidence level / citation support
  / budget-offload state / OCR-media status / failure state / stop reason
```

## 各層の役割

### Narrow Codex Bridge

Codex から `research_x` に渡すものを狭くする境界。
入力は query、objective、context budget、reviewed source candidate。
出力は evidence status、citation-ready answer または abstention、
provider_gated state、audit trace。

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

### SearchLens / RetrievalPolicy

人間側の関心、bias、探索方針を明示する層。
selected corpus、trusted / ignored accounts、bookmark and collection weights、
topic weights、allowed inference stance、desired diversity / contradiction policy を扱う。

これは gate ではない。検索空間と重みを決めるだけで、候補に回答権限を与えない。

### ObjectiveRoutePolicy

query / objective / context budget に応じて候補ルートを選ぶ。
置き場所は retrieval 前、または Route Portfolio の入口。

ObjectiveRoutePolicy は source bundle、citation verification、answer abstention、
workflow trace、eval gate を置き換えない。
provider 実行許可も answer authority も与えない。

### Retrieval And Route Portfolio

質問に対して候補を出すルート群。
ここは広く持つ。

- exact anchors
- SQLite FTS / BM25
- metadata search
- relation expansion
- retrieval-text projection
- semantic vector candidates
- sparse / late-interaction / rerank candidates
- OCR / media preparation candidates
- Corpus2Skill navigation
- graph / topic hints
- external Web candidates
- Reader extraction candidates
- LLM-context candidates
- managed-reference / managed RAG candidates
- conversation-prep / hypothesis candidates

FTS、BM25、metadata、exact、relation はローカル中核ルート。
semantic vectors、OCR、rerank、Reader、external Web、LLM-context、managed RAG は
provider または追加 guard の対象になりやすい。

Corpus2Skill は navigation / route hint。citation-ready evidence ではない。
Agentic RAG / managed RAG は orchestration または managed-reference candidate。
source bundle と citation を置き換えない。

### ProviderApiBudgetGuard

provider、quota、network 送信を止める実行前 guard。
no-quota freeze 中は、free-tier、trial-credit、zero-dollar quota も止める。

停止対象は real embeddings、native media embeddings、rerankers、Reader extraction、
OCR、classifiers、answer engines、relation judges、external search、LLM-context、
managed RAG、real-model prompt-contract validation。

これは回答権限の門番ではない。
provider が許可された場合でも、API Budget Guard preflight、offline estimate、
approval fields、max calls / max USD、price source、scope、approved time、
stop condition が必要。

### Search Results / Candidates

検索ルートから出た候補。
score、route、why_relevant、skip reason を持つ。
ただし、source bundle に戻るまでは証拠ではない。

すべての route output は初期状態では `candidate-only`。
どの route も answer authority を持たない。

### AnswerAuthorityGatekeeper

候補を answer support に昇格してよいかを見る狭い門番。
検索入口ではなく、候補が回答権限を得る出口に置く。

確認することは次の4つ。

- source bundle に復元できるか
- bounded context chunk を作れるか
- citation annotation を付けられるか
- citation が specific answer claim を支えるか

ここを通れない候補は、navigation hint、hypothesis、needs_review、
source_not_restored、citation_missing のいずれかに止める。

### Answer Boundary

回答できるか、止めるかを決める境界。
status は answer、abstain、needs_review、source_not_restored、
citation_missing、hypothesis_only、provider_gated、blocked。

正しそうな文章でも、citation-ready support がなければ完成回答ではない。

### Tool Interface Layer

AI が呼び出す安定した JSON 契約。
内部 workflow JSON が変わっても、この層の契約は安定させる。

返すものは status、evidence_level、citations、trace、route choices、
lens used、promotion failures、provider guard state。

### Workflow Trace Sidecar

Workflow Trace は直列ステップではなく sidecar として扱う。

route choice、fallback、provider skip、evidence level、citation support、
budget / offload state、OCR / media status、failure state、stop reason を記録する。

`store=True` の workflow run は operational trace row を保存できるが、
raw source、governance、feedback、provider、answer support の mutation を許可しない。

### Eval / Audit / Feedback Loop

answerability、relevance、citation coverage、restoration rate、route gaps、
provider-gated lanes、feedback を見る。

品質改善は、検索ルートの追加だけではなく、source restoration、
context chunk、citation、AnswerAuthorityGatekeeper、Answer Boundary の失敗理由を見て進める。

### Rebuild / Route Promotion / Guard Review

検索 projection は再生成できる。
ルート昇格は eval / audit / feedback を通す。
provider 系ルートは guard review と budget evidence が揃うまで昇格しない。

## 図解ルール

図は2つの幅を明確に見せる。

```text
wide:  route discovery / candidate generation
narrow: evidence promotion / answer authority
```

やってはいけない描き方:

- 回答権限の判定を候補生成前の検索フィルタとして描く
- ProviderApiBudgetGuard を全検索の main gate として描く
- ObjectiveRoutePolicy を citation 後に置く
- Workflow Trace を直列ステップとして描く
- Evidence Layer を単独の工程として描き、source bundle / context chunk / citation の境界をぼかす

## 最終案の読み方

BM25、semantic search、Corpus2Skill、Agentic RAG、OCR、Reader、rerank、
external search、LLM-context は全部候補ルートとして入る。
しかし、どのルートで候補を出しても、最後は source bundle、context chunk、
citation、AnswerAuthorityGatekeeper、Answer Boundary を通す。
