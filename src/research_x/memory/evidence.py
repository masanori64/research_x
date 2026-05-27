from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from research_x.memory.search import MemorySearchResult, search_memory


def build_evidence_bundle(
    db_path: str | Path,
    query: str,
    *,
    limit: int = 5,
    doc_type: str | None = None,
    account: str | None = None,
) -> dict[str, Any]:
    path = Path(db_path)
    results = search_memory(path, query, limit=limit, doc_type=doc_type, account=account)
    with sqlite3.connect(path, timeout=60) as conn:
        conn.row_factory = sqlite3.Row
        hits = [_hit(conn, query=query, result=result) for result in results]
    return {"query": query, "hits": hits}


def evidence_bundle_json(bundle: dict[str, Any]) -> str:
    return json.dumps(bundle, ensure_ascii=False, indent=2, sort_keys=True)


def _hit(conn: sqlite3.Connection, *, query: str, result: MemorySearchResult) -> dict[str, Any]:
    tweet_id = result.source_tweet_id
    tweet = _tweet(conn, tweet_id) if tweet_id else {}
    return {
        "doc_id": result.doc_id,
        "doc_type": result.doc_type,
        "tweet_id": tweet_id,
        "score": result.score,
        "title": result.title,
        "compact_text": result.compact_text,
        "why_relevant": _why_relevant(query, result),
        "freshness": result.metadata.get("freshness", "active"),
        "evidence": {
            "url": result.metadata.get("url") or tweet.get("url"),
            "author": result.author_screen_name or tweet.get("author_screen_name"),
            "account_id": result.account_id,
            "quoted_tweets": _quoted_tweets(conn, tweet_id) if tweet_id else [],
            "media": _media(conn, tweet_id) if tweet_id else [],
        },
    }


def _why_relevant(query: str, result: MemorySearchResult) -> str:
    method = "full-text" if result.match_method == "fts" else "fallback substring"
    return f"{method} match for query: {query}"


def _tweet(conn: sqlite3.Connection, tweet_id: str | None) -> dict[str, Any]:
    if not tweet_id:
        return {}
    row = conn.execute(
        """
        SELECT tweet_id, url, author_screen_name, text, created_at, role
        FROM tweets
        WHERE tweet_id = ?
        """,
        (tweet_id,),
    ).fetchone()
    return dict(row) if row else {}


def _quoted_tweets(conn: sqlite3.Connection, tweet_id: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT
            c.tweet_id, c.url, c.author_screen_name, c.text
        FROM tweet_edges e
        JOIN tweets c ON c.tweet_id = e.child_tweet_id
        WHERE e.parent_tweet_id = ?
          AND e.relation = 'quote'
        ORDER BY c.created_at DESC, c.tweet_id
        LIMIT 5
        """,
        (tweet_id,),
    ).fetchall()
    return [
        {
            "tweet_id": row["tweet_id"],
            "url": row["url"],
            "author": row["author_screen_name"],
            "text": _compact(row["text"] or "", limit=240),
        }
        for row in rows
    ]


def _media(conn: sqlite3.Connection, tweet_id: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT media_id, type, url, alt_text, local_path, download_status
        FROM media
        WHERE tweet_id = ?
        ORDER BY media_id
        LIMIT 8
        """,
        (tweet_id,),
    ).fetchall()
    return [
        {
            "media_id": row["media_id"],
            "type": row["type"],
            "url": row["url"],
            "alt_text": row["alt_text"],
            "local_path": row["local_path"],
            "download_status": row["download_status"],
        }
        for row in rows
    ]


def _compact(value: str, *, limit: int) -> str:
    text = " ".join(value.split())
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "..."
