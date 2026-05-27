from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from research_x.memory.embeddings import (
    SemanticHit,
    SemanticScore,
    semantic_scores_for_doc_ids,
    semantic_search_memory,
)
from research_x.memory.query import QueryPlan, build_query_plan
from research_x.memory.relations import relation_summary_for_docs
from research_x.memory.schema import ensure_memory_schema, memory_document_count


@dataclass(frozen=True)
class MemorySearchResult:
    doc_id: str
    doc_type: str
    source_tweet_id: str | None
    account_id: str | None
    author_screen_name: str | None
    title: str
    compact_text: str
    score: float
    match_method: str
    matched_terms: tuple[str, ...]
    score_components: dict[str, float]
    metadata: dict[str, Any]


def search_memory(
    db_path: str | Path,
    query: str,
    *,
    limit: int = 10,
    doc_type: str | None = None,
    account: str | None = None,
    semantic_provider: str | None = None,
    semantic_model: str | None = None,
    semantic_dimensions: int | None = None,
    semantic_api_key_env: str | None = None,
    semantic_base_url: str | None = None,
    semantic_weight: float = 3.0,
    semantic_candidates: int = 80,
) -> tuple[MemorySearchResult, ...]:
    path = Path(db_path)
    if not path.exists():
        raise FileNotFoundError(f"database not found: {path}")
    resolved_limit = max(1, limit)
    plan = build_query_plan(query)
    pool_limit = max(resolved_limit * 8, 50)

    semantic_hits: tuple[SemanticHit, ...] = ()
    with sqlite3.connect(path, timeout=60) as conn:
        conn.row_factory = sqlite3.Row
        ensure_memory_schema(conn)
        if memory_document_count(conn) == 0:
            raise RuntimeError("memory_documents is empty; run memory build-corpus first")

        raw_rows: list[dict[str, Any]] = []
        raw_rows.extend(
            _fts_search(
                conn,
                plan,
                limit=pool_limit,
                doc_type=doc_type,
                account=account,
            )
        )
        raw_rows.extend(
            _like_search(
                conn,
                plan,
                limit=pool_limit,
                doc_type=doc_type,
                account=account,
            )
        )
        raw_rows.extend(
            _metadata_search(
                conn,
                plan,
                limit=pool_limit,
                doc_type=doc_type,
                account=account,
            )
        )
        if semantic_provider:
            semantic_hits = semantic_search_memory(
                path,
                query,
                provider=None if semantic_provider == "auto" else semantic_provider,
                model=semantic_model,
                dimensions=semantic_dimensions,
                api_key_env=semantic_api_key_env,
                base_url=semantic_base_url,
                limit=semantic_candidates,
                doc_type=doc_type,
                account=account,
            )
            raw_rows.extend(_rows_by_doc_ids(conn, tuple(hit.doc_id for hit in semantic_hits)))
        candidates = _merge_candidates(raw_rows)
        doc_ids = tuple(candidate["doc_id"] for candidate in candidates)
        tweet_ids = tuple(
            str(candidate["source_tweet_id"])
            for candidate in candidates
            if candidate.get("source_tweet_id")
        )
        feedback = _feedback_scores(conn, doc_ids)
        account_counts = _bookmark_account_counts(conn, tweet_ids)
        relation_counts = relation_summary_for_docs(conn, doc_ids)
        latest_observed_at = _latest_observed_at(conn)

    semantic_by_doc = {hit.doc_id: hit for hit in semantic_hits}
    if semantic_provider:
        semantic_by_doc.update(
            semantic_scores_for_doc_ids(
                path,
                query,
                tuple(candidate["doc_id"] for candidate in candidates),
                provider=None if semantic_provider == "auto" else semantic_provider,
                model=semantic_model,
                dimensions=semantic_dimensions,
                api_key_env=semantic_api_key_env,
                base_url=semantic_base_url,
            )
        )
    results = [
        _result_from_candidate(
            candidate,
            plan=plan,
            feedback_score=feedback.get(candidate["doc_id"], 0.0),
            bookmark_account_count=account_counts.get(str(candidate.get("source_tweet_id")), 0),
            relation_counts=relation_counts.get(str(candidate["doc_id"]), {}),
            latest_observed_at=latest_observed_at,
            semantic_hit=semantic_by_doc.get(str(candidate["doc_id"])),
            semantic_weight=semantic_weight,
        )
        for candidate in candidates
    ]
    results.sort(key=lambda result: (result.score, _date_sort_value(result.metadata)), reverse=True)
    return tuple(results[:resolved_limit])


def results_as_dicts(results: tuple[MemorySearchResult, ...]) -> list[dict[str, Any]]:
    return [asdict(result) for result in results]


def format_search_results(
    results: tuple[MemorySearchResult, ...],
    *,
    json_output: bool = False,
) -> str:
    if json_output:
        return json.dumps(results_as_dicts(results), ensure_ascii=False, indent=2, sort_keys=True)
    if not results:
        return "(no memory search results)"
    blocks = []
    for index, result in enumerate(results, start=1):
        parts = [
            f"#{index}",
            f"score={result.score:.3f}",
            f"method={result.match_method}",
            f"type={result.doc_type}",
            f"id={result.doc_id}",
        ]
        if result.matched_terms:
            parts.append(f"matches={','.join(result.matched_terms[:6])}")
        if result.author_screen_name:
            parts.append(f"@{result.author_screen_name}")
        if result.account_id:
            parts.append(f"account={result.account_id}")
        blocks.append(
            "\n".join(
                [
                    " ".join(parts),
                    f"title: {result.title}",
                    f"text: {result.compact_text}",
                    f"tweet_id: {result.source_tweet_id or ''}",
                    f"url: {result.metadata.get('url') or ''}",
                    f"rank: {_components_text(result.score_components)}",
                ]
            )
        )
    return "\n\n".join(blocks)


def _fts_search(
    conn: sqlite3.Connection,
    plan: QueryPlan,
    *,
    limit: int,
    doc_type: str | None,
    account: str | None,
) -> list[dict[str, Any]]:
    fts_query = _fts_query(plan.search_terms)
    if not fts_query:
        return []
    filters, params = _filters(doc_type=doc_type, account=account)
    sql = f"""
        SELECT
            d.doc_id, d.doc_type, d.source_tweet_id, d.account_id,
            d.author_screen_name, d.title, d.body, d.compact_text, d.metadata_json,
            d.created_at, d.observed_at, d.updated_at,
            bm25(memory_document_fts) AS raw_score,
            'fts' AS match_method
        FROM memory_document_fts
        JOIN memory_documents d ON d.doc_id = memory_document_fts.doc_id
        WHERE memory_document_fts MATCH ?
        {filters}
        ORDER BY raw_score ASC, d.observed_at DESC
        LIMIT ?
    """
    try:
        return [dict(row) for row in conn.execute(sql, (fts_query, *params, limit)).fetchall()]
    except sqlite3.OperationalError as exc:
        raise RuntimeError(f"memory FTS query failed for query {fts_query!r}") from exc


def _like_search(
    conn: sqlite3.Connection,
    plan: QueryPlan,
    *,
    limit: int,
    doc_type: str | None,
    account: str | None,
) -> list[dict[str, Any]]:
    terms = plan.search_terms
    if not terms:
        return []
    filters, params = _filters(doc_type=doc_type, account=account)
    like_filters = []
    like_params: list[Any] = []
    for term in terms:
        pattern = f"%{term}%"
        like_filters.append(
            """
            (
                d.title LIKE ?
                OR d.body LIKE ?
                OR d.compact_text LIKE ?
                OR d.author_screen_name LIKE ?
                OR d.metadata_json LIKE ?
            )
            """
        )
        like_params.extend([pattern, pattern, pattern, pattern, pattern])
    sql = f"""
        SELECT
            d.doc_id, d.doc_type, d.source_tweet_id, d.account_id,
            d.author_screen_name, d.title, d.body, d.compact_text, d.metadata_json,
            d.created_at, d.observed_at, d.updated_at,
            0.0 AS raw_score,
            'like' AS match_method
        FROM memory_documents d
        WHERE ({' OR '.join(like_filters)})
        {filters}
        ORDER BY d.observed_at DESC, d.doc_id
        LIMIT ?
    """
    return [dict(row) for row in conn.execute(sql, (*like_params, *params, limit)).fetchall()]


def _metadata_search(
    conn: sqlite3.Connection,
    plan: QueryPlan,
    *,
    limit: int,
    doc_type: str | None,
    account: str | None,
) -> list[dict[str, Any]]:
    filters, params = _filters(doc_type=doc_type, account=account)
    clauses: list[str] = []
    if plan.requires_quote_context:
        clauses.append("d.doc_type = 'quote_tree_doc'")
    if plan.requires_media_context:
        clauses.append("d.doc_type = 'media_doc'")
    if plan.requires_bookmark_context:
        clauses.append("d.doc_type = 'bookmark_doc'")
    if plan.wants_cross_account:
        clauses.append(
            """
            d.source_tweet_id IN (
                SELECT tweet_id
                FROM account_bookmarks
                GROUP BY tweet_id
                HAVING COUNT(DISTINCT account_id) > 1
            )
            """
        )
    if plan.wants_event_dates:
        clauses.append(
            """
            (
                d.body LIKE '%202%'
                OR d.body LIKE '%開催%'
                OR d.body LIKE '%期限%'
                OR d.body LIKE '%予約%'
            )
            """
        )
    if not clauses:
        return []
    sql = f"""
        SELECT
            d.doc_id, d.doc_type, d.source_tweet_id, d.account_id,
            d.author_screen_name, d.title, d.body, d.compact_text, d.metadata_json,
            d.created_at, d.observed_at, d.updated_at,
            0.0 AS raw_score,
            'metadata' AS match_method
        FROM memory_documents d
        WHERE ({' OR '.join(clauses)})
        {filters}
        ORDER BY d.observed_at DESC, d.doc_id
        LIMIT ?
    """
    return [dict(row) for row in conn.execute(sql, (*params, limit)).fetchall()]


def _rows_by_doc_ids(
    conn: sqlite3.Connection,
    doc_ids: tuple[str, ...],
) -> list[dict[str, Any]]:
    if not doc_ids:
        return []
    placeholders = ",".join("?" for _ in doc_ids)
    rows = conn.execute(
        f"""
        SELECT
            d.doc_id, d.doc_type, d.source_tweet_id, d.account_id,
            d.author_screen_name, d.title, d.body, d.compact_text, d.metadata_json,
            d.created_at, d.observed_at, d.updated_at,
            0.0 AS raw_score,
            'semantic' AS match_method
        FROM memory_documents d
        WHERE d.doc_id IN ({placeholders})
        """,
        doc_ids,
    ).fetchall()
    return [dict(row) for row in rows]


def _merge_candidates(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for row in rows:
        doc_id = str(row["doc_id"])
        existing = merged.get(doc_id)
        if existing is None:
            row["_match_methods"] = {row["match_method"]}
            merged[doc_id] = row
            continue
        existing["_match_methods"].add(row["match_method"])
        if _method_priority(str(row["match_method"])) > _method_priority(
            str(existing["match_method"])
        ):
            row["_match_methods"] = existing["_match_methods"]
            merged[doc_id] = row
    return list(merged.values())


def _method_priority(method: str) -> int:
    return {"fts": 4, "semantic": 3, "like": 2, "metadata": 1}.get(method, 0)


def _result_from_candidate(
    row: dict[str, Any],
    *,
    plan: QueryPlan,
    feedback_score: float,
    bookmark_account_count: int,
    relation_counts: dict[str, int],
    latest_observed_at: datetime | None,
    semantic_hit: SemanticHit | SemanticScore | None,
    semantic_weight: float,
) -> MemorySearchResult:
    metadata = _loads_json(row.get("metadata_json"))
    body = str(row.get("body") or "")
    title = str(row.get("title") or "")
    compact = str(row.get("compact_text") or "")
    text_blob = _searchable_text(title, body, compact, str(row.get("author_screen_name") or ""))
    exact_terms = tuple(term for term in plan.exact_terms if _term_in_text(term, text_blob))
    matched_terms = tuple(term for term in plan.search_terms if _term_in_text(term, text_blob))
    expansion_matches = tuple(term for term in matched_terms if term not in exact_terms)
    methods = tuple(sorted(row.get("_match_methods", (str(row.get("match_method") or ""),))))

    components = {
        "lexical_exact": 2.0 * len(exact_terms),
        "lexical_expansion": 0.65 * len(expansion_matches),
        "retrieval_method": _method_score(methods),
        "doc_type": plan.doc_type_weights.get(str(row["doc_type"]), 0.0),
        "context": _context_score(plan, str(row["doc_type"]), body, metadata),
        "semantic": max(0.0, semantic_hit.similarity) * semantic_weight
        if semantic_hit
        else 0.0,
        "freshness": _freshness_score(
            row.get("observed_at") or row.get("created_at"),
            plan=plan,
            latest_observed_at=latest_observed_at,
        ),
        "cross_account": 1.5
        if plan.wants_cross_account and bookmark_account_count > 1
        else 0.0,
        "relations": _relation_score(plan, str(row["doc_type"]), relation_counts),
        "feedback": feedback_score,
    }
    score = round(sum(components.values()), 6)
    metadata = dict(metadata)
    metadata.update(
        {
            "rank_score_components": components,
            "matched_terms": matched_terms,
            "retrieval_methods": methods,
            "observed_at": row.get("observed_at"),
            "created_at": row.get("created_at"),
        }
    )
    if bookmark_account_count:
        metadata["bookmark_account_count"] = bookmark_account_count
    if relation_counts:
        metadata["relation_counts"] = relation_counts
    if semantic_hit:
        metadata["semantic"] = {
            "provider": semantic_hit.provider,
            "model": semantic_hit.model,
            "dimensions": semantic_hit.dimensions,
            "similarity": semantic_hit.similarity,
            "weight": semantic_weight,
        }
    if components["freshness"] > 0 and plan.prefers_recent:
        metadata["freshness"] = "recent"
    elif plan.excludes_old and components["freshness"] < 0:
        metadata["freshness"] = "possibly_stale"
    else:
        metadata.setdefault("freshness", "active")

    return MemorySearchResult(
        doc_id=str(row["doc_id"]),
        doc_type=str(row["doc_type"]),
        source_tweet_id=row.get("source_tweet_id"),
        account_id=row.get("account_id"),
        author_screen_name=row.get("author_screen_name"),
        title=title,
        compact_text=compact,
        score=score,
        match_method="+".join(methods),
        matched_terms=matched_terms,
        score_components=components,
        metadata=metadata,
    )


def _filters(*, doc_type: str | None, account: str | None) -> tuple[str, tuple[Any, ...]]:
    parts = []
    params: list[Any] = []
    if doc_type:
        parts.append("AND d.doc_type = ?")
        params.append(doc_type)
    if account:
        parts.append("AND d.account_id = ?")
        params.append(account)
    return "\n".join(parts), tuple(params)


def _fts_query(terms: tuple[str, ...]) -> str:
    terms = tuple(term.strip().replace('"', '""') for term in terms if term.strip())
    if not terms:
        return ""
    return " OR ".join(f'"{term}"' for term in terms)


def _loads_json(value: str | None) -> dict[str, Any]:
    if not value:
        return {}
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _searchable_text(*parts: str) -> str:
    return "\n".join(parts).casefold()


def _term_in_text(term: str, text_blob: str) -> bool:
    return term.casefold() in text_blob


def _method_score(methods: tuple[str, ...]) -> float:
    score = 0.0
    if "fts" in methods:
        score += 1.2
    if "semantic" in methods:
        score += 0.7
    if "like" in methods:
        score += 0.5
    if "metadata" in methods:
        score += 0.25
    if len(methods) > 1:
        score += 0.4
    return score


def _context_score(
    plan: QueryPlan,
    doc_type: str,
    body: str,
    metadata: dict[str, Any],
) -> float:
    score = 0.0
    if plan.requires_quote_context and doc_type == "quote_tree_doc":
        score += 2.0
    if plan.requires_media_context and doc_type == "media_doc":
        score += 1.8
    if plan.requires_bookmark_context and doc_type == "bookmark_doc":
        score += 1.2
    if plan.wants_event_dates and _contains_event_date(body):
        score += 1.0
    if metadata.get("media_count"):
        score += 0.2
    return score


def _relation_score(
    plan: QueryPlan,
    doc_type: str,
    relation_counts: dict[str, int],
) -> float:
    if not relation_counts:
        return 0.0
    score = 0.0
    if plan.requires_quote_context:
        score += min(1.2, 0.4 * relation_counts.get("quote_tree_includes", 0))
        score += min(0.8, 0.3 * relation_counts.get("has_quote_tree", 0))
        score += min(0.6, 0.2 * relation_counts.get("quotes", 0))
    if plan.requires_media_context:
        score += min(1.0, 0.25 * relation_counts.get("has_media", 0))
        if doc_type == "media_doc":
            score += min(0.6, 0.2 * relation_counts.get("incoming:has_media", 0))
    if plan.wants_cross_account:
        score += min(2.0, 0.5 * relation_counts.get("same_bookmarked_tweet", 0))
    if plan.excludes_old:
        score -= min(2.0, 0.6 * relation_counts.get("older_same_author_label", 0))
    if plan.prefers_recent:
        score += min(1.0, 0.4 * relation_counts.get("incoming:older_same_author_label", 0))
    return score


def _contains_event_date(text: str) -> bool:
    return any(token in text for token in ("202", "開催", "期限", "締切", "予約", "イベント"))


def _feedback_scores(conn: sqlite3.Connection, doc_ids: tuple[str, ...]) -> dict[str, float]:
    if not doc_ids:
        return {}
    placeholders = ",".join("?" for _ in doc_ids)
    rows = conn.execute(
        f"""
        SELECT doc_id, label, COUNT(*) AS count
        FROM memory_feedback
        WHERE doc_id IN ({placeholders})
        GROUP BY doc_id, label
        """,
        doc_ids,
    ).fetchall()
    weights = {
        "useful": 1.0,
        "good_for_skill": 0.8,
        "not_useful": -1.2,
        "wrong_topic": -1.8,
        "too_old": -1.0,
        "missing_context": -0.4,
        "bad_skill_route": -0.8,
    }
    result: dict[str, float] = {}
    for row in rows:
        result[str(row["doc_id"])] = result.get(str(row["doc_id"]), 0.0) + (
            weights.get(str(row["label"]), 0.0) * int(row["count"])
        )
    return result


def _bookmark_account_counts(
    conn: sqlite3.Connection,
    tweet_ids: tuple[str, ...],
) -> dict[str, int]:
    if not tweet_ids:
        return {}
    placeholders = ",".join("?" for _ in tweet_ids)
    rows = conn.execute(
        f"""
        SELECT tweet_id, COUNT(DISTINCT account_id) AS account_count
        FROM account_bookmarks
        WHERE tweet_id IN ({placeholders})
        GROUP BY tweet_id
        """,
        tweet_ids,
    ).fetchall()
    return {str(row["tweet_id"]): int(row["account_count"]) for row in rows}


def _latest_observed_at(conn: sqlite3.Connection) -> datetime | None:
    row = conn.execute("SELECT MAX(observed_at) FROM memory_documents").fetchone()
    if not row or not row[0]:
        return None
    return _parse_datetime(str(row[0]))


def _freshness_score(
    value: Any,
    *,
    plan: QueryPlan,
    latest_observed_at: datetime | None,
) -> float:
    if not (plan.prefers_recent or plan.excludes_old):
        return 0.0
    observed_at = _parse_datetime(str(value)) if value else None
    if observed_at is None:
        return -0.5 if plan.excludes_old else 0.0
    reference = latest_observed_at or datetime.now(tz=UTC)
    age_days = max(0.0, (reference - observed_at).total_seconds() / 86400.0)
    score = 0.0
    if plan.prefers_recent:
        if age_days <= 14:
            score += 2.0
        elif age_days <= 90:
            score += 1.0
        elif age_days <= 365:
            score += 0.25
    if plan.excludes_old:
        if age_days > 365:
            score -= 2.0
        elif age_days > 180:
            score -= 0.6
    return score


def _parse_datetime(value: str) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _date_sort_value(metadata: dict[str, Any]) -> str:
    return str(metadata.get("observed_at") or metadata.get("created_at") or "")


def _components_text(components: dict[str, float]) -> str:
    return ", ".join(
        f"{key}={value:.2f}" for key, value in components.items() if abs(value) > 0.0001
    )
