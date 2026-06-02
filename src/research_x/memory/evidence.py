from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from research_x.memory.query import build_query_plan
from research_x.memory.search import MemorySearchResult, search_memory


def build_evidence_bundle(
    db_path: str | Path,
    query: str,
    *,
    limit: int = 5,
    doc_type: str | None = None,
    account: str | None = None,
    semantic_provider: str | None = None,
    semantic_model: str | None = None,
    semantic_dimensions: int | None = None,
    semantic_profile: str | None = None,
    semantic_template_version: str | None = None,
    semantic_api_key_env: str | None = None,
    semantic_base_url: str | None = None,
    semantic_weight: float = 3.0,
    semantic_candidates: int = 80,
) -> dict[str, Any]:
    path = Path(db_path)
    plan = build_query_plan(query)
    results = search_memory(
        path,
        query,
        limit=limit,
        doc_type=doc_type,
        account=account,
        semantic_provider=semantic_provider,
        semantic_model=semantic_model,
        semantic_dimensions=semantic_dimensions,
        semantic_profile=semantic_profile,
        semantic_template_version=semantic_template_version,
        semantic_api_key_env=semantic_api_key_env,
        semantic_base_url=semantic_base_url,
        semantic_weight=semantic_weight,
        semantic_candidates=semantic_candidates,
    )
    with sqlite3.connect(path, timeout=60) as conn:
        conn.row_factory = sqlite3.Row
        hits = [_hit(conn, query=query, result=result) for result in results]
    return {"query": query, "query_plan": plan.as_dict(), "hits": hits}


def build_evidence_hits_for_doc_ids(
    db_path: str | Path,
    query: str,
    doc_ids: tuple[str, ...],
    *,
    score_by_doc_id: dict[str, float] | None = None,
    metadata_by_doc_id: dict[str, dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    if not doc_ids:
        return []
    path = Path(db_path)
    placeholders = ",".join("?" for _ in doc_ids)
    order = {doc_id: index for index, doc_id in enumerate(doc_ids)}
    with sqlite3.connect(path, timeout=60) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            f"""
            SELECT
                doc_id, doc_type, source_tweet_id, account_id,
                author_screen_name, title, compact_text, metadata_json
            FROM memory_documents
            WHERE doc_id IN ({placeholders})
            """,
            doc_ids,
        ).fetchall()
        sorted_rows = sorted(rows, key=lambda row: order.get(str(row["doc_id"]), 10**9))
        return [
            _hit(
                conn,
                query=query,
                result=_memory_result_from_row(
                    row,
                    score_by_doc_id=score_by_doc_id or {},
                    metadata_by_doc_id=metadata_by_doc_id or {},
                ),
            )
            for row in sorted_rows
        ]


def build_evidence_hits_from_results(
    db_path: str | Path,
    query: str,
    results: tuple[MemorySearchResult, ...],
) -> list[dict[str, Any]]:
    if not results:
        return []
    path = Path(db_path)
    with sqlite3.connect(path, timeout=60) as conn:
        conn.row_factory = sqlite3.Row
        return [_hit(conn, query=query, result=result) for result in results]


def evidence_bundle_json(bundle: dict[str, Any]) -> str:
    return json.dumps(bundle, ensure_ascii=False, indent=2, sort_keys=True)


def _hit(conn: sqlite3.Connection, *, query: str, result: MemorySearchResult) -> dict[str, Any]:
    tweet_id = result.source_tweet_id
    tweet = _tweet(conn, tweet_id) if tweet_id else {}
    derived = _derived_evidence(result.metadata)
    return {
        "doc_id": result.doc_id,
        "doc_type": result.doc_type,
        "tweet_id": tweet_id,
        "score": result.score,
        "title": result.title,
        "compact_text": result.compact_text,
        "why_relevant": _why_relevant(query, result),
        "freshness": result.metadata.get("freshness", "active"),
        "matched_terms": list(result.matched_terms),
        "score_components": result.score_components,
        "metadata": _public_result_metadata(result.metadata),
        "bookmark_account_count": result.metadata.get("bookmark_account_count"),
        "evidence": {
            "url": result.metadata.get("url") or tweet.get("url"),
            "author": result.author_screen_name or tweet.get("author_screen_name"),
            "account_id": result.account_id,
            "quoted_tweets": _quoted_tweets(conn, tweet_id) if tweet_id else [],
            "media": _media(conn, tweet_id) if tweet_id else [],
            "relations": _relations(conn, result.doc_id),
            "derived": derived,
        },
    }


def _memory_result_from_row(
    row: sqlite3.Row,
    *,
    score_by_doc_id: dict[str, float],
    metadata_by_doc_id: dict[str, dict[str, Any]],
) -> MemorySearchResult:
    doc_id = str(row["doc_id"])
    metadata = _loads_json(row["metadata_json"])
    metadata.update(metadata_by_doc_id.get(doc_id, {}))
    return MemorySearchResult(
        doc_id=doc_id,
        doc_type=str(row["doc_type"]),
        source_tweet_id=row["source_tweet_id"],
        account_id=row["account_id"],
        author_screen_name=row["author_screen_name"],
        title=str(row["title"] or ""),
        compact_text=str(row["compact_text"] or ""),
        score=float(score_by_doc_id.get(doc_id, 0.0)),
        match_method=str(metadata.get("retrieval_method") or "semantic_only"),
        matched_terms=tuple(metadata.get("matched_terms") or ()),
        score_components=dict(metadata.get("rank_score_components") or {}),
        metadata=metadata,
    )


def _why_relevant(query: str, result: MemorySearchResult) -> str:
    terms = ", ".join(result.matched_terms[:6]) if result.matched_terms else query
    components = sorted(
        (
            (name, value)
            for name, value in result.score_components.items()
            if abs(value) > 0.0001
        ),
        key=lambda item: abs(item[1]),
        reverse=True,
    )
    component_text = ", ".join(f"{name}={value:.2f}" for name, value in components[:4])
    if component_text:
        return f"{result.match_method} match: {terms}; rank: {component_text}"
    return f"{result.match_method} match: {terms}"


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
            c.tweet_id, c.url, c.author_screen_name, c.text,
            e.child_also_bookmarked
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
            "child_also_bookmarked": bool(row["child_also_bookmarked"]),
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


def _relations(conn: sqlite3.Connection, doc_id: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT
            source_doc_id, target_doc_id, relation_type, strength, status, evidence_json
        FROM memory_relations
        WHERE source_doc_id = ? OR target_doc_id = ?
        ORDER BY strength DESC, relation_type, target_doc_id
        LIMIT 8
        """,
        (doc_id, doc_id),
    ).fetchall()
    return [
        {
            "source_doc_id": row["source_doc_id"],
            "target_doc_id": row["target_doc_id"],
            "relation_type": row["relation_type"],
            "strength": row["strength"],
            "status": row["status"],
            "evidence": _loads_json(row["evidence_json"]),
        }
        for row in rows
    ]


def _derived_evidence(metadata: dict[str, Any]) -> dict[str, Any] | None:
    derived_kind = metadata.get("derived_kind")
    if not derived_kind:
        return None
    return {
        "derived_kind": derived_kind,
        "source_doc_ids": metadata.get("source_doc_ids") or [],
        "source_tweet_ids": metadata.get("source_tweet_ids") or [],
        "source_urls": metadata.get("source_urls") or [],
        "source_doc_count": metadata.get("source_doc_count"),
        "display_source_doc_ids": metadata.get("display_source_doc_ids") or [],
    }


def _public_result_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "engine_contributions",
        "retrieval_methods",
        "semantic",
        "rrf_raw",
        "relation_counts",
        "bookmark_account_count",
        "observed_at",
        "created_at",
    )
    return {key: metadata[key] for key in keys if key in metadata}


def _loads_json(value: str | None) -> dict[str, Any]:
    if not value:
        return {}
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _compact(value: str, *, limit: int) -> str:
    text = " ".join(value.split())
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "..."
