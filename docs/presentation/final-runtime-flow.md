# research_x Final Runtime Flow

この文書は、`research_x` の最終実行フローを人間向けに固定する暫定正本です。
図解、実装順、周辺 Markdown の整理はこの流れを基準にする。

ただし、この文書自体は証拠、citation、provider 実行許可ではない。
回答の根拠は必ず source bundle、context chunk、citation から作る。

## 目的

最終案の `research_x` は、X の保存データを AI が呼び出せるローカル検索ツールにする。
検索ルートは広く持つが、検索候補・要約・スコア・図・provider 出力をそのまま根拠にしない。
どのルートから来た候補でも、回答に使うには AnswerAuthorityGatekeeper を通る。

```text
検索入口は広くする。
回答権限の戸口だけ狭くする。
```

## 実行時の原則

```text
Every route output is candidate-only by default.
No route has answer authority.
Only AnswerAuthorityGatekeeper can promote a candidate to answer support.
```

日本語では次の意味になる。

```text
すべての route output は初期状態では candidate-only。
どの route も answer authority を持たない。
候補は source bundle に復元され、context chunk 化され、citation annotation を受け、
answer claim と対応づけられた場合にのみ answer support へ昇格できる。
```

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
SearchLens / RetrievalPolicy
  - corpus scope
  - human bias
  - source weights
  - route preference
  - inference stance
  ※検索空間と重みを決める。回答権限は与えない
  ↓
ObjectiveRoutePolicy
  - query / objective / context budget に応じて候補ルートを選ぶ
  - provider-backed lane を識別する
  - answer authority は与えない
  - provider 実行許可も与えない
  ↓
Route Portfolio [wide]
  local lanes:
    - exact anchors
    - SQLite FTS / BM25
    - metadata search
    - relation expansion
    - retrieval-text projection
    - local semantic / local topic hints
    - Corpus2Skill navigation
    - local conversation-prep hints
    → candidates

  provider-backed / network / quota lanes:
    - real embeddings
    - native media embeddings
    - hosted rerankers
    - Reader extraction
    - OCR / VLM execution
    - classifiers
    - answer engines
    - relation judges
    - external search
    - LLM-context
    - managed RAG
    → ProviderApiBudgetGuard
    → candidates or provider_gated skip
  ↓
Search Results / Candidates
  - candidate_id
  - route_id
  - source_ref
  - restore_path
  - score / route_score
  - why_relevant
  - skip reason
  - lens_id
  - evidence_level = candidate
  - answer_authority = false
  ※まだ証拠ではない
  ↓
AnswerAuthorityGatekeeper [narrow]
  candidate -> source bundle?
    no: source_not_restored
    yes: continue

  source bundle -> bounded context chunk?
    no: needs_review
    yes: continue

  context chunk -> citation annotation?
    no: citation_missing
    yes: continue

  citation -> claim support?
    no: needs_review / hypothesis_only
    yes: answer_support
  ↓
Answer Boundary
  - answer only from answer_support
  - abstain
  - needs_review
  - source_not_restored
  - citation_missing
  - hypothesis_only
  - provider_gated
  - blocked
  ↓
Tool Interface Layer
  - stable AI-callable JSON
  - status
  - evidence_level
  - citations
  - trace
  - route choices
  - lens used
  - promotion failures
  - provider guard state
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

## Provider stop の扱い

Provider 系の停止は `Gate` ではなく `Guard` と呼ぶ。

```text
ProviderApiBudgetGuard
```

これは provider-backed、quota-consuming、network、hosted RAG の実行前 guard であり、
回答権限の門番ではない。

provider 系ルートは設計から消さない。最終案では候補ルートとして残したまま、
`ProviderApiBudgetGuard` で実行可否を止める。

no-quota freeze 中は、これらのルートは `provider_gated` として trace に残す。
fake / local / monkeypatched / offline estimate は、provider 送信をしない範囲だけ許可する。

## 複雑な会話・背景推定の扱い

会話予想や複雑な背景推定は、candidate-producing route として扱ってよい。
ただし、引用可能な local source に復元されない限り `hypothesis_only` とする。

```text
conversation-prep route -> hypothesis_candidate
hypothesis_candidate -> answer_support only if restored to source bundle and citation
```

ローカル復元済み source に存在しない背景知識は、次のどちらかで返す。

```text
not_supported_by_local_context
provider_required / provider_gated
```

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
context chunk、citation、AnswerAuthorityGatekeeper、Answer Boundary を通る。
