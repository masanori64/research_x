# Memory Search Project Plan

This file is the implementation-facing plan for turning the existing `research-x` X/Twitter
collection database into an AI-callable local memory search tool.

The main `README.md` is the high-level AI-oriented project reference. This file is the more
operational spec for the next branch.

## Goal

Build a local, user-specific search tool over the existing X collection DB. The tool should let an
AI agent search the user's accumulated X bookmarks/tweets in a way similar to web research, while
preserving the user's own subjective interests and keeping token use low.

The system should support:

- exact search over names, URLs, authors, dates, and labels,
- semantic search over vague remembered concepts,
- compact evidence bundles for AI context,
- quote/media/URL/author expansion only when needed,
- Corpus2Skill navigation for stable interest areas,
- feedback and evaluation loops,
- freshness/obsolete weighting without deleting raw data.

## Non-Goals

- Do not replace the current acquisition pipeline.
- Do not delete or rewrite raw X records as summaries.
- Do not treat AI labels as canonical truth.
- Do not start by installing a large RAG framework.
- Do not build a UI-first feature before the CLI/search contract works.

## Current Base

The current DB is the source of truth:

- `tweets`
- `account_bookmarks`
- `collection_items`
- `tweet_edges`
- `media`
- `raw_payloads`
- `ai_labels`
- `accounts`
- `provider_runs`

The first memory-search implementation must be additive. It can add tables and modules, but it
must not break acquisition, app, labeling, or DB viewing.

## Target Architecture

```text
Raw X DB
  -> Living Corpus Layer
  -> Hybrid Retrieval Core
  -> Temporal / Obsolescence Layer
  -> Corpus2Skill Navigation Layer
  -> Evidence Bundle API
  -> Lightweight Agentic Search Tool
  -> Feedback / Eval / Rebuild Loop
```

## Module Plan

Create a new package:

```text
src/research_x/memory/
  __init__.py
  corpus.py          # canonical/living document generation
  schema.py          # memory tables and migrations
  search.py          # FTS and later hybrid search
  evidence.py        # compact AI evidence bundles
  feedback.py        # feedback capture and scoring signals
  skills.py          # Corpus2Skill export/navigation adapters
  freshness.py       # stale/superseded weighting
  evals.py           # fixed evaluation queries and metrics
```

Add one CLI namespace:

```text
research_x memory build-corpus
research_x memory search
research_x memory evidence
research_x memory feedback
research_x memory export-corpus2skill
research_x memory eval
```

## First Milestone

Build the smallest useful AI-callable search core with no external AI dependency.

Required commands:

```powershell
uv run python -m research_x memory build-corpus --db runs/x_data.sqlite3
uv run python -m research_x memory search --db runs/x_data.sqlite3 --query "カフェ" --limit 10
uv run python -m research_x memory evidence --db runs/x_data.sqlite3 --query "強化学習 ロボット" --limit 5
uv run python -m research_x memory eval --db runs/x_data.sqlite3
```

Required first tables:

```text
memory_documents
memory_document_fts
memory_feedback
memory_eval_queries
```

`memory_documents` should be rebuildable from the raw store.

Suggested columns:

```text
doc_id TEXT PRIMARY KEY
doc_type TEXT
source_tweet_id TEXT
account_id TEXT
author_screen_name TEXT
title TEXT
body TEXT
compact_text TEXT
metadata_json TEXT
created_at TEXT
observed_at TEXT
updated_at TEXT
```

Initial document types:

- `tweet_doc`: one tweet with minimal metadata.
- `bookmark_doc`: bookmarked root tweet plus bookmark account context.
- `quote_tree_doc`: root tweet plus quoted child tweet snippets.
- `media_doc`: tweet plus media metadata/local path hints.

Do not implement embeddings in milestone 1. Start with SQLite FTS5 and compact evidence.

## Evidence Bundle Contract

The AI-facing output should be compact and structured.

Example:

```json
{
  "query": "強化学習 ロボット",
  "hits": [
    {
      "doc_id": "bookmark:acct:123",
      "tweet_id": "123",
      "score": -4.21,
      "title": "@author 2026-05-27",
      "compact_text": "短い要約または本文抜粋",
      "why_relevant": "FTS match: 強化学習, ロボット",
      "freshness": "active",
      "evidence": {
        "url": "https://x.com/author/status/123",
        "author": "author",
        "account_id": "acct",
        "quoted_tweets": ["..."],
        "media": ["runs/.../media/file.jpg"]
      }
    }
  ]
}
```

Token rule:

1. return IDs, scores, titles, and compact snippets first,
2. include quote/media/URL context only when it is relevant,
3. avoid dumping raw JSON unless explicitly requested.

## Corpus2Skill Position

Use the existing OSS Corpus2Skill project as an integration target, not as the only search engine.

Rationale:

- Corpus2Skill is strong as a map/navigation layer over stable topic clusters.
- The X DB also needs exact lookup, date filtering, URL lookup, freshness checks, and quote/media
  expansion.
- Therefore the search core remains DB + retrieval; Corpus2Skill provides navigation and route
  hints.

Initial export command should write JSONL compatible with Corpus2Skill expectations:

```json
{"id": "doc_id", "contents": "document text and metadata"}
```

## Freshness and Obsolescence

Raw records must remain immutable. Freshness is a search weighting layer.

Future relation types:

- `same_topic`
- `newer_than`
- `older_than`
- `obsolete_by`
- `contradicts`
- `supports`
- `same_url`
- `same_author`

Do not add a graph engine before evidence/search works. Start with simple tables and score fields.

## Feedback

Feedback labels:

- `useful`
- `not_useful`
- `wrong_topic`
- `too_old`
- `missing_context`
- `good_for_skill`
- `bad_skill_route`

Feedback should be attached to query, doc id, timestamp, and optional note.

## Evaluation Queries

The first eval set should include:

- あとで行きたくて保存したカフェ系を出して
- 最近保存した強化学習とロボット系の情報を古いものを除いて出して
- 成人向け漫画の公式リンク誘導っぽいブクマを作品名つきで出して
- この作者をなぜ何度も保存しているか説明して
- 引用元を見ないと意味が変わる投稿を根拠付きで出して
- 同じテーマで古くなった情報と新しい情報を比較して
- 画像付きで保存した技術資料っぽい投稿を出して
- イベント系で日付が近いものだけ出して
- 複数アカウントで重複して保存しているテーマを出して
- DB 全体で最近増えている関心領域を出して

Milestone 1 evaluation started as a structural validity check:

- command exits successfully,
- returns JSON,
- returns no raw secrets,
- every hit has `doc_id`, `compact_text`, and at least one evidence URL or tweet id.

## Implementation Rules

- Use `uv run python ...`, `uv run pytest ...`, and `uv run ruff check src\research_x tests`.
- Keep acquisition modules stable unless a memory feature needs a clearly scoped read-only helper.
- Add tests next to each new memory module.
- Prefer SQLite features first; add external vector DBs only after the local contract is proven.
- Keep generated indexes in the same SQLite DB unless there is a clear reason to split.
- Never stage `.secrets/` or `runs/`.

## First Implementation Checklist

- [x] Add `src/research_x/memory/__init__.py`
- [x] Add memory schema creation
- [x] Add document builder from existing DB rows
- [x] Add SQLite FTS5 index population
- [x] Add search command
- [x] Add evidence command
- [x] Add feedback command
- [x] Add Corpus2Skill JSONL export command
- [x] Add initial eval command
- [x] Add tests with an in-memory/temp SQLite DB fixture
- [x] Run `uv run ruff check src\research_x tests`
- [x] Run `uv run pytest`

Milestone 1 was verified against `runs/x_data.sqlite3`:

```text
memory build-corpus -> 54,886 memory documents
memory search "カフェ" -> ranked local results
memory evidence "強化学習 ロボット" -> compact evidence JSON
memory eval --limit 1 -> 10/10 initial queries returned structurally valid hits
```

Important caveat: the eval pass is structural, not semantic relevance proof. The next milestone
should improve ranking quality with better query planning, embeddings, and reranking.

## Second Milestone

Improve the search contract before adding external embedding or RAG dependencies.

Required commands:

```powershell
uv run python -m research_x memory plan --query "画像付きで保存した技術資料っぽい投稿を出して"
uv run python -m research_x memory search --db runs/x_data.sqlite3 --query "引用元を見ないと意味が変わる投稿を根拠付きで出して" --limit 5
uv run python -m research_x memory evidence --db runs/x_data.sqlite3 --query "最近保存した強化学習とロボット系の情報を古いものを除いて出して" --limit 5
uv run python -m research_x memory eval --db runs/x_data.sqlite3 --limit 3
```

Implementation goals:

- [x] Add a query-planning layer that maps natural Japanese requests to search terms, intent flags,
      doc-type preferences, and freshness/context requirements.
- [x] Replace raw FTS ordering with local hybrid ranking from exact term matches, expanded term
      matches, retrieval method, document type, quote/media/bookmark context, freshness, duplicate
      account signals, and feedback.
- [x] Include `query_plan`, `matched_terms`, and `score_components` in evidence bundles so an AI
      caller can judge whether a result should be trusted.
- [x] Make eval stricter than structural checks: return `ok`, `needs_review`, or `fail`
      with notes instead
      of pretending every structurally valid hit is semantically correct.

Remaining after this milestone:

- [ ] Add embedding-backed semantic retrieval for vague concepts that do not share words with the
      tweet text.
- [ ] Add reranking or a small judge step for final evidence ordering.
- [ ] Add freshness/obsolete relation tables rather than only transient freshness scoring.
- [ ] Integrate Corpus2Skill OSS as a navigation sidecar after the DB search contract is stable.

## Third Milestone

Add an embedding-backed semantic layer without making the CLI dependent on paid APIs.

Required commands:

```powershell
uv run python -m research_x memory build-embeddings --db runs/x_data.sqlite3 --provider gemini --dimensions 768 --batch-size 100
uv run python -m research_x memory build-embeddings --db runs/x_data.sqlite3 --provider local_hash --dimensions 256 --batch-size 512  # explicit diagnostic mode
uv run python -m research_x memory embedding-specs --db runs/x_data.sqlite3
uv run python -m research_x memory search --db runs/x_data.sqlite3 --query "曖昧に覚えているロボットと学習の資料" --limit 5 --semantic-provider auto
uv run python -m research_x memory search --db runs/x_data.sqlite3 --query "診断用に配線だけ確認" --limit 5 --semantic-provider local_hash --semantic-dimensions 256
```

Implementation goals:

- [x] Add `memory_embeddings` as a rebuildable index table attached to `memory_documents`.
- [x] Add `local_hash` embeddings only as an explicit diagnostic mode so semantic plumbing can be
      tested without API keys or cost.
- [x] Add OpenAI and Gemini embedding providers behind the same contract.
- [x] Keep OpenAI default at `text-embedding-3-small`; keep Gemini default at `gemini-embedding-2`.
- [x] Use Gemini `embedContentConfig.outputDimensionality` and avoid `taskType` for
      `gemini-embedding-2`, where task intent should be represented in prompt text instead.
- [x] Let search combine lexical/context ranking with semantic similarity and expose the semantic
      score in `score_components`.
- [x] Require NumPy for local vector scans instead of silently falling back to slow pure Python.

Current limitation:

- `local_hash` is a deterministic no-cost diagnostic mode, not a real semantic model. Production
  semantic quality requires an OpenAI or Gemini embedding index. `--semantic-provider auto` must
  select a production index; it must not silently use `local_hash`.

## Fourth Milestone

Add rebuildable relation edges so the memory DB can expose context, duplicate saves, and freshness
signals without rewriting raw records.

Required commands:

```powershell
uv run python -m research_x memory build-relations --db runs/x_data.sqlite3
uv run python -m research_x memory relations --db runs/x_data.sqlite3 --doc-id tweet:1939691054728720590 --limit 10
uv run python -m research_x memory evidence --db runs/x_data.sqlite3 --query "引用元を見ないと意味が変わる投稿を根拠付きで出して" --limit 2
```

Implementation goals:

- [x] Add `memory_relations` as a rebuildable index table.
- [x] Add `bookmark_of_tweet`, `has_media`, `quotes`, `has_quote_tree`,
      `quote_tree_includes`, `same_bookmarked_tweet`, and `older_same_author_label`.
- [x] Use `tweet_doc` as the hub for bookmark/media/quote edges to avoid unnecessary all-pair
      relation growth.
- [x] Include relation summaries in search scoring for quote/media/cross-account/freshness queries.
- [x] Include top relation edges in evidence bundles so an AI caller can inspect why context was
      expanded.

Verified against `runs/x_data.sqlite3`:

```text
memory build-relations -> 43,799 relations
bookmark_of_tweet      -> 14,397
has_media              -> 21,901
has_quote_tree         -> 2,359
quote_tree_includes    -> 2,359
quotes                 -> 2,359
same_bookmarked_tweet  -> 421
older_same_author_label -> 3
```

Current limitation:

- `older_same_author_label` is only a weak stale candidate signal. It does not prove that older
  content is obsolete.

## Fifth Milestone

Remove silent quality downgrades and make index health visible.

Required commands:

```powershell
uv run python -m research_x memory audit --db runs/x_data.sqlite3
uv run python -m research_x memory audit --db runs/x_data.sqlite3 --json
uv run python -m research_x memory audit --db runs/x_data.sqlite3 --strict
```

Implementation goals:

- [x] Add `memory audit` to report document count, FTS coverage, relation coverage, embedding
      coverage, orphaned relation/embedding rows, and warnings.
- [x] Confirm relation count can be lower than document count because relations are edges, while
      relation-covered documents should match the document count.
- [x] Stop silently using `local_hash` when `build-embeddings` is run without a provider. `auto`
      now requires `GEMINI_API_KEY` or `OPENAI_API_KEY`; `local_hash` must be explicit.
- [x] Stop silently using `local_hash` when semantic search is run with `--semantic-provider auto`.
      Auto search now requires a production OpenAI/Gemini embedding index; diagnostic search must
      explicitly choose `local_hash`.
- [x] Stop semantic search from continuing when the requested scope has only partial embeddings.
- [x] Require NumPy for vector scan performance.
- [x] Validate provider vector dimensionality at embedding-build time.
- [x] Stop hiding FTS failures as empty result sets.
- [x] Clear stale relation edges and orphaned embedding rows when rebuilding `memory_documents`.
- [x] Stop search/relations/embedding commands from silently rebuilding an empty corpus. Run
      `memory build-corpus` explicitly before downstream indexes.
- [x] Add `memory audit --strict` so production-readiness warnings can fail automation instead of
      being ignored.
- [x] Add `memory eval --strict` so weak retrieval behavior can fail automation.
