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

Milestone 1 evaluation can be smoke-level:

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

- [ ] Add `src/research_x/memory/__init__.py`
- [ ] Add memory schema creation
- [ ] Add document builder from existing DB rows
- [ ] Add SQLite FTS5 index population
- [ ] Add search command
- [ ] Add evidence command
- [ ] Add eval smoke command
- [ ] Add tests with an in-memory/temp SQLite DB fixture
- [ ] Run `uv run ruff check src\research_x tests`
- [ ] Run `uv run pytest`
