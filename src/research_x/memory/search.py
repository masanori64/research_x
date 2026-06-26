from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from research_x.memory.document_hashes import text_hash
from research_x.memory.embeddings import (
    SemanticHit,
    SemanticScore,
    semantic_scores_for_doc_ids,
    semantic_search_memory,
)
from research_x.memory.feedback import feedback_scores_for_docs
from research_x.memory.governance import active_tombstone_ids
from research_x.memory.query import QueryPlan, build_query_plan
from research_x.memory.relations import relation_summary_for_docs
from research_x.memory.schema import ensure_memory_schema, memory_document_count

SOURCE_EVIDENCE_DOC_TYPES = frozenset(
    {"tweet_doc", "bookmark_doc", "quote_tree_doc", "media_doc"}
)


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
    semantic_profile: str | None = None,
    semantic_template_version: str | None = None,
    semantic_api_key_env: str | None = None,
    semantic_base_url: str | None = None,
    semantic_weight: float = 3.0,
    semantic_candidates: int = 80,
    semantic_backend: str = "sqlite",
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
            _with_engine_contributions(
                _fts_search(
                    conn,
                    plan,
                    limit=pool_limit,
                    doc_type=doc_type,
                    account=account,
                ),
                "fts",
                plan=plan,
            )
        )
        raw_rows.extend(
            _with_engine_contributions(
                _like_search(
                    conn,
                    plan,
                    limit=pool_limit,
                    doc_type=doc_type,
                    account=account,
                ),
                "like",
                plan=plan,
            )
        )
        raw_rows.extend(
            _with_engine_contributions(
                _metadata_search(
                    conn,
                    plan,
                    limit=pool_limit,
                    doc_type=doc_type,
                    account=account,
                ),
                "metadata",
                plan=plan,
            )
        )
        raw_rows.extend(
            _with_engine_contributions(
                _retrieval_text_search(
                    conn,
                    plan,
                    limit=pool_limit,
                    doc_type=doc_type,
                    account=account,
                ),
                "retrieval_text",
                plan=plan,
            )
        )
        if semantic_provider:
            semantic_hits = _semantic_hits(
                path,
                query,
                provider=None if semantic_provider == "auto" else semantic_provider,
                model=semantic_model,
                dimensions=semantic_dimensions,
                embedding_profile=semantic_profile,
                text_template_version=semantic_template_version,
                api_key_env=semantic_api_key_env,
                base_url=semantic_base_url,
                limit=semantic_candidates,
                doc_type=doc_type,
                account=account,
                semantic_backend=semantic_backend,
            )
            raw_rows.extend(
                _with_semantic_contributions(
                    _rows_by_doc_ids(conn, tuple(hit.doc_id for hit in semantic_hits)),
                    semantic_hits,
                    plan=plan,
                )
            )
        seed_candidates = _filter_anchor_candidates(_merge_candidates(raw_rows), plan)
        raw_rows.extend(
            _with_engine_contributions(
                _relation_expansion_search(
                    conn,
                    tuple(candidate["doc_id"] for candidate in seed_candidates),
                    limit=pool_limit,
                    doc_type=doc_type,
                    account=account,
                ),
                "relation_expansion",
                plan=plan,
            )
        )
        candidates = _filter_governance_tombstones(
            conn,
            _filter_anchor_candidates(_merge_candidates(raw_rows), plan),
        )
        candidates = _dedupe_candidates_for_evidence_identity(conn, candidates, plan=plan)
        doc_ids = tuple(candidate["doc_id"] for candidate in candidates)
        tweet_ids = tuple(
            str(candidate["source_tweet_id"])
            for candidate in candidates
            if candidate.get("source_tweet_id")
        )
        feedback = feedback_scores_for_docs(
            conn,
            doc_ids,
            plan=plan,
            route=_feedback_route_scope(plan),
        )
        account_counts = _bookmark_account_counts(conn, tweet_ids)
        relation_counts = relation_summary_for_docs(conn, doc_ids)
        latest_observed_at = _latest_observed_at(conn)

    semantic_by_doc = {hit.doc_id: hit for hit in semantic_hits}
    if semantic_provider:
        semantic_by_doc.update(
            _semantic_scores(
                path,
                query,
                tuple(candidate["doc_id"] for candidate in candidates),
                provider=None if semantic_provider == "auto" else semantic_provider,
                model=semantic_model,
                dimensions=semantic_dimensions,
                embedding_profile=semantic_profile,
                text_template_version=semantic_template_version,
                api_key_env=semantic_api_key_env,
                base_url=semantic_base_url,
                semantic_backend=semantic_backend,
            )
        )
    semantic_rerank_ranks = _semantic_rerank_ranks(semantic_by_doc)
    results = [
        _result_from_candidate(
            candidate,
            plan=plan,
            feedback_score=feedback.get(candidate["doc_id"], 0.0),
            bookmark_account_count=account_counts.get(str(candidate.get("source_tweet_id")), 0),
            relation_counts=relation_counts.get(str(candidate["doc_id"]), {}),
            latest_observed_at=latest_observed_at,
            semantic_hit=semantic_by_doc.get(str(candidate["doc_id"])),
            semantic_rerank_rank=semantic_rerank_ranks.get(str(candidate["doc_id"])),
            semantic_weight=semantic_weight,
        )
        for candidate in candidates
    ]
    results.sort(key=lambda result: (result.score, _date_sort_value(result.metadata)), reverse=True)
    return tuple(results[:resolved_limit])


def search_memory_fts_only(
    db_path: str | Path,
    query: str,
    *,
    limit: int = 10,
    doc_type: str | None = None,
    account: str | None = None,
) -> tuple[MemorySearchResult, ...]:
    path = Path(db_path)
    if not path.exists():
        raise FileNotFoundError(f"database not found: {path}")
    resolved_limit = max(1, limit)
    plan = build_query_plan(query)
    with sqlite3.connect(path, timeout=60) as conn:
        conn.row_factory = sqlite3.Row
        ensure_memory_schema(conn)
        if memory_document_count(conn) == 0:
            raise RuntimeError("memory_documents is empty; run memory build-corpus first")
        candidates = _filter_governance_tombstones(
            conn,
            _filter_anchor_candidates(
                _merge_candidates(
                    _with_engine_contributions(
                        _fts_search(
                            conn,
                            plan,
                            limit=max(resolved_limit * 8, 50),
                            doc_type=doc_type,
                            account=account,
                        ),
                        "fts",
                        plan=plan,
                    )
                ),
                plan,
            ),
        )
        candidates = _dedupe_candidates_for_evidence_identity(conn, candidates, plan=plan)
        latest_observed_at = _latest_observed_at(conn)
    results = [
        _result_from_candidate(
            candidate,
            plan=plan,
            feedback_score=0.0,
            bookmark_account_count=0,
            relation_counts={},
            latest_observed_at=latest_observed_at,
            semantic_hit=None,
            semantic_rerank_rank=None,
            semantic_weight=0.0,
        )
        for candidate in candidates
    ]
    results.sort(key=lambda result: (result.score, _date_sort_value(result.metadata)), reverse=True)
    return tuple(results[:resolved_limit])


def search_memory_retrieval_text_only(
    db_path: str | Path,
    query: str,
    *,
    limit: int = 10,
    doc_type: str | None = None,
    account: str | None = None,
) -> tuple[MemorySearchResult, ...]:
    path = Path(db_path)
    if not path.exists():
        raise FileNotFoundError(f"database not found: {path}")
    resolved_limit = max(1, limit)
    plan = build_query_plan(query)
    with sqlite3.connect(path, timeout=60) as conn:
        conn.row_factory = sqlite3.Row
        ensure_memory_schema(conn)
        if memory_document_count(conn) == 0:
            raise RuntimeError("memory_documents is empty; run memory build-corpus first")
        candidates = _filter_governance_tombstones(
            conn,
            _filter_anchor_candidates(
                _merge_candidates(
                    _with_engine_contributions(
                        _retrieval_text_search(
                            conn,
                            plan,
                            limit=max(resolved_limit * 8, 50),
                            doc_type=doc_type,
                            account=account,
                        ),
                        "retrieval_text",
                        plan=plan,
                    )
                ),
                plan,
            ),
        )
        candidates = _dedupe_candidates_for_evidence_identity(conn, candidates, plan=plan)
        latest_observed_at = _latest_observed_at(conn)
    results = [
        _result_from_candidate(
            candidate,
            plan=plan,
            feedback_score=0.0,
            bookmark_account_count=0,
            relation_counts={},
            latest_observed_at=latest_observed_at,
            semantic_hit=None,
            semantic_rerank_rank=None,
            semantic_weight=0.0,
        )
        for candidate in candidates
    ]
    results.sort(key=lambda result: (result.score, _date_sort_value(result.metadata)), reverse=True)
    return tuple(results[:resolved_limit])

def results_as_dicts(results: tuple[MemorySearchResult, ...]) -> list[dict[str, Any]]:
    return [asdict(result) for result in results]


def _semantic_hits(
    db_path: Path,
    query: str,
    *,
    provider: str | None,
    model: str | None,
    dimensions: int | None,
    embedding_profile: str | None,
    text_template_version: str | None,
    api_key_env: str | None,
    base_url: str | None,
    limit: int,
    doc_type: str | None,
    account: str | None,
    semantic_backend: str,
) -> tuple[SemanticHit, ...]:
    resolved_backend = _resolve_semantic_backend(semantic_backend)
    if resolved_backend == "sqlite":
        return semantic_search_memory(
            db_path,
            query,
            provider=provider,
            model=model,
            dimensions=dimensions,
            embedding_profile=embedding_profile,
            text_template_version=text_template_version,
            api_key_env=api_key_env,
            base_url=base_url,
            limit=limit,
            doc_type=doc_type,
            account=account,
        )
    from research_x.memory.vector_projection import search_vector_projection

    return search_vector_projection(
        db_path,
        query,
        provider=provider,
        model=model,
        dimensions=dimensions,
        embedding_profile=embedding_profile,
        text_template_version=text_template_version,
        backend=None,
        limit=limit,
        doc_type=doc_type,
        account=account,
    )


def _semantic_scores(
    db_path: Path,
    query: str,
    doc_ids: tuple[str, ...],
    *,
    provider: str | None,
    model: str | None,
    dimensions: int | None,
    embedding_profile: str | None,
    text_template_version: str | None,
    api_key_env: str | None,
    base_url: str | None,
    semantic_backend: str,
) -> dict[str, SemanticScore]:
    if not doc_ids:
        return {}
    resolved_backend = _resolve_semantic_backend(semantic_backend)
    if resolved_backend == "sqlite":
        return semantic_scores_for_doc_ids(
            db_path,
            query,
            doc_ids,
            provider=provider,
            model=model,
            dimensions=dimensions,
            embedding_profile=embedding_profile,
            text_template_version=text_template_version,
            api_key_env=api_key_env,
            base_url=base_url,
        )
    from research_x.memory.vector_projection import search_vector_projection

    hits = search_vector_projection(
        db_path,
        query,
        provider=provider,
        model=model,
        dimensions=dimensions,
        embedding_profile=embedding_profile,
        text_template_version=text_template_version,
        backend=None,
        limit=len(set(doc_ids)),
        doc_ids=tuple(dict.fromkeys(doc_ids)),
    )
    by_doc = {
        hit.doc_id: SemanticScore(
            doc_id=hit.doc_id,
            similarity=hit.similarity,
            provider=hit.provider,
            model=hit.model,
            dimensions=hit.dimensions,
            embedding_profile=hit.embedding_profile,
            text_template_version=hit.text_template_version,
        )
        for hit in hits
    }
    missing = set(doc_ids) - set(by_doc)
    if missing:
        raise RuntimeError(
            "local vector projection is incomplete for the candidate set: "
            f"{len(by_doc)}/{len(set(doc_ids))} candidate documents indexed"
        )
    return by_doc


def _resolve_semantic_backend(semantic_backend: str) -> str:
    resolved = (semantic_backend or "sqlite").strip().lower()
    if resolved not in {"sqlite", "projection"}:
        raise ValueError(f"unknown semantic backend: {semantic_backend}")
    return resolved


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
                    f"engines: {_engine_contributions_text(result.metadata)}",
                    "evidence_policy: scores/ranks/snippets are ranking signals; "
                    "source bundle/context chunk required for citation",
                ]
            )
        )
    return "\n\n".join(blocks)


def strong_anchor_terms_for_query(query: str) -> tuple[str, ...]:
    return _strong_anchor_terms(build_query_plan(query))


def _engine_contributions_text(metadata: dict[str, Any]) -> str:
    contributions = metadata.get("engine_contributions")
    if not isinstance(contributions, list) or not contributions:
        return "-"
    parts = []
    for contribution in contributions[:6]:
        if not isinstance(contribution, dict):
            continue
        engine = str(contribution.get("engine") or "-")
        rank = contribution.get("rank")
        provider = contribution.get("provider")
        model = contribution.get("model")
        provider_text = f" {provider}/{model}" if provider or model else ""
        parts.append(f"{engine}#{rank}{provider_text}".strip())
    return "; ".join(parts) or "-"


def text_matches_any_anchor(anchors: tuple[str, ...], *values: Any) -> bool:
    if not anchors:
        return True
    text_blob = _searchable_text(*(str(value or "") for value in values))
    return any(_term_in_text(anchor, text_blob) for anchor in anchors)


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
            d.source_doc_hash,
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
            d.source_doc_hash,
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
            d.source_doc_hash,
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


def _retrieval_text_search(
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
    row = conn.execute(
        """
        SELECT 1
        FROM sqlite_master
        WHERE type = 'table'
          AND name = 'memory_retrieval_text_fts'
        LIMIT 1
        """
    ).fetchone()
    if row is None:
        return []
    filters, params = _filters(doc_type=doc_type, account=account)
    sql = f"""
        SELECT
            d.doc_id, d.doc_type, d.source_tweet_id, d.account_id,
            d.author_screen_name, d.title, d.body, d.compact_text, d.metadata_json,
            d.source_doc_hash,
            d.created_at, d.observed_at, d.updated_at,
            bm25(memory_retrieval_text_fts) AS raw_score,
            'retrieval_text' AS match_method
        FROM memory_retrieval_text_fts
        JOIN memory_retrieval_text_profiles p
          ON p.profile_id = memory_retrieval_text_fts.profile_id
         AND p.doc_id = memory_retrieval_text_fts.doc_id
        JOIN memory_documents d ON d.doc_id = memory_retrieval_text_fts.doc_id
        WHERE memory_retrieval_text_fts MATCH ?
          AND p.citation_excluded = 1
          AND p.source_doc_hash = d.source_doc_hash
        {filters}
        ORDER BY raw_score ASC, d.observed_at DESC
        LIMIT ?
    """
    try:
        return [dict(row) for row in conn.execute(sql, (fts_query, *params, limit)).fetchall()]
    except sqlite3.OperationalError as exc:
        raise RuntimeError(f"retrieval text FTS query failed for query {fts_query!r}") from exc


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
            d.source_doc_hash,
            d.created_at, d.observed_at, d.updated_at,
            0.0 AS raw_score,
            'semantic' AS match_method
        FROM memory_documents d
        WHERE d.doc_id IN ({placeholders})
        """,
        doc_ids,
    ).fetchall()
    return [dict(row) for row in rows]


def _relation_expansion_search(
    conn: sqlite3.Connection,
    doc_ids: tuple[str, ...],
    *,
    limit: int,
    doc_type: str | None,
    account: str | None,
) -> list[dict[str, Any]]:
    if not doc_ids:
        return []
    placeholders = ",".join("?" for _ in doc_ids)
    filters, params = _relation_expansion_filters(doc_type=doc_type, account=account)
    rows = conn.execute(
        f"""
        WITH related AS (
            SELECT
                CASE
                    WHEN source_doc_id IN ({placeholders}) THEN target_doc_id
                    ELSE source_doc_id
                END AS related_doc_id,
                MAX(strength) AS relation_strength
            FROM memory_relations
            WHERE source_doc_id IN ({placeholders})
               OR target_doc_id IN ({placeholders})
            GROUP BY related_doc_id
        )
        SELECT
            d.doc_id, d.doc_type, d.source_tweet_id, d.account_id,
            d.author_screen_name, d.title, d.body, d.compact_text, d.metadata_json,
            d.source_doc_hash,
            d.created_at, d.observed_at, d.updated_at,
            related.relation_strength AS raw_score,
            'relation_expansion' AS match_method
        FROM related
        JOIN memory_documents d ON d.doc_id = related.related_doc_id
        WHERE d.doc_id NOT IN ({placeholders})
        {filters}
        ORDER BY related.relation_strength DESC, d.observed_at DESC, d.doc_id
        LIMIT ?
        """,
        (*doc_ids, *doc_ids, *doc_ids, *doc_ids, *params, max(1, limit)),
    ).fetchall()
    return [dict(row) for row in rows]


def _merge_candidates(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for row in rows:
        doc_id = str(row["doc_id"])
        existing = merged.get(doc_id)
        if existing is None:
            row["_match_methods"] = {row["match_method"]}
            row["_engine_contributions"] = list(row.get("_engine_contributions") or [])
            merged[doc_id] = row
            continue
        existing["_match_methods"].add(row["match_method"])
        existing.setdefault("_engine_contributions", []).extend(
            row.get("_engine_contributions") or []
        )
        if _method_priority(str(row["match_method"])) > _method_priority(
            str(existing["match_method"])
        ):
            row["_match_methods"] = existing["_match_methods"]
            row["_engine_contributions"] = existing.get("_engine_contributions", [])
            merged[doc_id] = row
    return list(merged.values())


def _dedupe_candidates_for_evidence_identity(
    conn: sqlite3.Connection,
    candidates: list[dict[str, Any]],
    *,
    plan: QueryPlan,
) -> list[dict[str, Any]]:
    if not candidates:
        return []
    tweet_ids = tuple(
        dict.fromkeys(
            str(candidate["source_tweet_id"])
            for candidate in candidates
            if candidate.get("source_tweet_id")
        )
    )
    bookmark_accounts = _bookmark_accounts_by_tweet(conn, tweet_ids)
    groups: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for candidate in candidates:
        groups.setdefault(_candidate_evidence_identity(candidate), []).append(candidate)
    return [
        _merge_evidence_identity_group(
            identity,
            group,
            plan=plan,
            bookmark_accounts=bookmark_accounts,
        )
        for identity, group in groups.items()
    ]


def _candidate_evidence_identity(candidate: dict[str, Any]) -> tuple[str, str, str]:
    doc_type = str(candidate.get("doc_type") or "")
    tweet_id = str(candidate.get("source_tweet_id") or "").strip()
    if tweet_id and doc_type in SOURCE_EVIDENCE_DOC_TYPES:
        return ("local_x_db", "tweet", tweet_id)
    return ("local_x_db", "document", str(candidate.get("doc_id") or ""))


def _merge_evidence_identity_group(
    identity: tuple[str, str, str],
    group: list[dict[str, Any]],
    *,
    plan: QueryPlan,
    bookmark_accounts: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    representative = dict(
        max(group, key=lambda candidate: _representative_priority(candidate, plan))
    )
    methods: set[str] = set()
    contributions: list[dict[str, Any]] = []
    for candidate in group:
        candidate_methods = candidate.get("_match_methods") or (candidate.get("match_method"),)
        methods.update(str(method) for method in candidate_methods if method)
        contributions.extend(candidate.get("_engine_contributions") or [])
    representative["_match_methods"] = methods or {str(representative.get("match_method") or "")}
    representative["_engine_contributions"] = _dedupe_engine_contributions(contributions)

    metadata = _loads_json(representative.get("metadata_json"))
    identity_metadata = _evidence_identity_metadata(
        identity,
        group,
        representative_doc_id=str(representative.get("doc_id") or ""),
        bookmark_accounts=bookmark_accounts,
    )
    _preserve_existing_source_metadata(metadata, identity_metadata)
    metadata.update(identity_metadata)
    representative["metadata_json"] = json.dumps(
        metadata,
        ensure_ascii=False,
        sort_keys=True,
    )
    return representative


def _preserve_existing_source_metadata(
    metadata: dict[str, Any],
    identity_metadata: dict[str, Any],
) -> None:
    for key in ("source_doc_ids", "source_tweet_ids", "source_urls"):
        existing = metadata.get(key)
        if not existing:
            continue
        replacement = identity_metadata.pop(key, None)
        if replacement:
            identity_metadata[f"evidence_identity_{key}"] = replacement


def _representative_priority(candidate: dict[str, Any], plan: QueryPlan) -> tuple[int, int, str]:
    doc_type = str(candidate.get("doc_type") or "")
    method = str(candidate.get("match_method") or "")
    observed_at = str(candidate.get("observed_at") or candidate.get("created_at") or "")
    return (
        _representative_doc_type_priority(doc_type, plan),
        _method_priority(method),
        observed_at,
    )


def _representative_doc_type_priority(doc_type: str, plan: QueryPlan) -> int:
    if plan.requires_media_context:
        priority = {"media_doc": 6, "quote_tree_doc": 4, "bookmark_doc": 3, "tweet_doc": 2}
    elif plan.requires_quote_context:
        priority = {"quote_tree_doc": 6, "bookmark_doc": 4, "tweet_doc": 3, "media_doc": 2}
    elif plan.requires_bookmark_context or plan.wants_cross_account:
        priority = {"bookmark_doc": 6, "tweet_doc": 4, "quote_tree_doc": 3, "media_doc": 2}
    else:
        priority = {"bookmark_doc": 5, "tweet_doc": 4, "quote_tree_doc": 3, "media_doc": 2}
    return priority.get(doc_type, 1)


def _evidence_identity_metadata(
    identity: tuple[str, str, str],
    group: list[dict[str, Any]],
    *,
    representative_doc_id: str,
    bookmark_accounts: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    source_kind, identity_kind, identity_source_id = identity
    identity_key = "|".join(identity)
    identity_hash = text_hash(identity_key)
    source_tweet_ids = _unique_strings(candidate.get("source_tweet_id") for candidate in group)
    source_doc_ids = _unique_strings(candidate.get("doc_id") for candidate in group)
    source_doc_hashes = _unique_strings(candidate.get("source_doc_hash") for candidate in group)
    source_accounts = _unique_strings(candidate.get("account_id") for candidate in group)
    doc_types = _unique_strings(candidate.get("doc_type") for candidate in group)
    urls = _unique_strings(
        _loads_json(candidate.get("metadata_json")).get("url") for candidate in group
    )
    bookmark_rows: list[dict[str, Any]] = []
    for tweet_id in source_tweet_ids:
        bookmark_rows.extend(bookmark_accounts.get(tweet_id, ()))
    bookmark_account_ids = _unique_strings(row.get("account_id") for row in bookmark_rows)
    if bookmark_account_ids:
        source_accounts = _unique_strings((*source_accounts, *bookmark_account_ids))
    duplicate_sources = [doc_id for doc_id in source_doc_ids if doc_id != representative_doc_id]
    duplicate_count = len(duplicate_sources)
    provenance_sources = [
        {
            "doc_id": str(candidate.get("doc_id") or ""),
            "doc_type": str(candidate.get("doc_type") or ""),
            "source_tweet_id": _string_or_none(candidate.get("source_tweet_id")),
            "account_id": _string_or_none(candidate.get("account_id")),
            "source_doc_hash": _string_or_none(candidate.get("source_doc_hash")),
            "url": _string_or_none(_loads_json(candidate.get("metadata_json")).get("url")),
        }
        for candidate in group
    ]
    metadata: dict[str, Any] = {
        "primary_evidence_identity": {
            "source_kind": source_kind,
            "identity_kind": identity_kind,
            "source_id": identity_source_id,
            "identity_key": identity_key,
            "identity_hash": identity_hash,
        },
        "primary_evidence_key": identity_key,
        "primary_evidence_source_kind": source_kind,
        "primary_evidence_identity_kind": identity_kind,
        "primary_evidence_source_id": identity_source_id,
        "primary_evidence_hash": identity_hash,
        "source_doc_ids": source_doc_ids,
        "source_tweet_ids": source_tweet_ids,
        "source_doc_hashes": source_doc_hashes,
        "source_accounts": source_accounts,
        "source_doc_types": doc_types,
        "source_urls": urls,
        "provenance_sources": provenance_sources,
        "duplicate_sources": duplicate_sources,
        "duplicate_support_suppressed_count": duplicate_count,
        "duplicate_evidence_count": duplicate_count,
        "unique_evidence_count": 1,
        "dedup_reason": (
            "same_source_identity_preserve_provenance"
            if duplicate_count
            else "unique_source_identity"
        ),
    }
    if bookmark_account_ids:
        metadata["bookmark_accounts"] = bookmark_account_ids
        metadata["bookmark_provenance"] = bookmark_rows
    return metadata


def _filter_anchor_candidates(
    candidates: list[dict[str, Any]],
    plan: QueryPlan,
) -> list[dict[str, Any]]:
    anchors = _strong_anchor_terms(plan)
    if not anchors:
        return candidates
    return [candidate for candidate in candidates if _candidate_has_anchor(candidate, anchors)]


def _filter_governance_tombstones(
    conn: sqlite3.Connection,
    candidates: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if not candidates:
        return []
    doc_ids = tuple(str(candidate["doc_id"]) for candidate in candidates)
    tweet_ids = tuple(
        str(candidate["source_tweet_id"])
        for candidate in candidates
        if candidate.get("source_tweet_id")
    )
    tombstoned_docs = active_tombstone_ids(
        conn,
        artifact_kind="memory_document",
        artifact_ids=doc_ids,
    )
    tombstoned_tweets = active_tombstone_ids(
        conn,
        artifact_kind="tweet",
        artifact_ids=tweet_ids,
    )
    if not tombstoned_docs and not tombstoned_tweets:
        return candidates
    return [
        candidate
        for candidate in candidates
        if str(candidate["doc_id"]) not in tombstoned_docs
        and str(candidate.get("source_tweet_id") or "") not in tombstoned_tweets
    ]


def _strong_anchor_terms(plan: QueryPlan) -> tuple[str, ...]:
    anchors = []
    for term in plan.exact_terms:
        if _is_strong_anchor_term(term):
            anchors.append(term)
    return tuple(anchors)


def _is_strong_anchor_term(term: str) -> bool:
    cleaned = term.strip()
    folded = cleaned.casefold()
    if folded in {
        "反対",
        "反対意見",
        "矛盾",
        "同じ話",
        "contradict",
        "contradiction",
        "support",
    }:
        return True
    if cleaned.startswith(("@", "#")) and len(cleaned) >= 3:
        return True
    if "://" in cleaned or folded.startswith("www."):
        return True
    if cleaned.isdigit() and len(cleaned) >= 12:
        return True
    has_digit = any(char.isdigit() for char in cleaned)
    has_ascii_alpha = any("a" <= char <= "z" for char in folded)
    if len(cleaned) >= 6 and has_digit and has_ascii_alpha:
        return True
    return len(cleaned) >= 10 and has_ascii_alpha and any(
        char in folded for char in ("_", ".", ":")
    )


def _candidate_has_anchor(candidate: dict[str, Any], anchors: tuple[str, ...]) -> bool:
    text_blob = _searchable_text(
        str(candidate.get("title") or ""),
        str(candidate.get("body") or ""),
        str(candidate.get("compact_text") or ""),
        str(candidate.get("author_screen_name") or ""),
        str(candidate.get("metadata_json") or ""),
    )
    return any(_term_in_text(anchor, text_blob) for anchor in anchors)


def _method_priority(method: str) -> int:
    return {
        "fts": 5,
        "retrieval_text": 4,
        "semantic": 4,
        "like": 3,
        "metadata": 2,
        "relation_expansion": 1,
    }.get(method, 0)


def _with_engine_contributions(
    rows: list[dict[str, Any]],
    engine: str,
    *,
    plan: QueryPlan,
) -> list[dict[str, Any]]:
    weight = _engine_route_weight(engine, plan)
    for rank, row in enumerate(rows, start=1):
        row["_engine_contributions"] = [
            {
                "engine": engine,
                "rank": rank,
                "raw_score": _safe_float(row.get("raw_score")),
                "route_weight": weight,
                "rrf": round(weight / (60.0 + rank), 8),
            }
        ]
    return rows


def _with_semantic_contributions(
    rows: list[dict[str, Any]],
    hits: tuple[SemanticHit, ...],
    *,
    plan: QueryPlan,
) -> list[dict[str, Any]]:
    by_doc = {
        hit.doc_id: {
            "rank": rank,
            "similarity": hit.similarity,
            "provider": hit.provider,
            "model": hit.model,
            "dimensions": hit.dimensions,
            "embedding_profile": hit.embedding_profile,
            "text_template_version": hit.text_template_version,
        }
        for rank, hit in enumerate(hits, start=1)
    }
    weight = _engine_route_weight("semantic", plan)
    for row in rows:
        semantic = by_doc.get(str(row.get("doc_id")))
        if not semantic:
            continue
        rank = int(semantic["rank"])
        row["_engine_contributions"] = [
            {
                "engine": "semantic",
                "rank": rank,
                "raw_score": float(semantic["similarity"]),
                "route_weight": weight,
                "rrf": round(weight / (60.0 + rank), 8),
                "provider": semantic["provider"],
                "model": semantic["model"],
                "dimensions": semantic["dimensions"],
                "embedding_profile": semantic["embedding_profile"],
                "text_template_version": semantic["text_template_version"],
            }
        ]
    return rows


def _dedupe_engine_contributions(values: list[Any]) -> list[dict[str, Any]]:
    best: dict[tuple[str, str | None], dict[str, Any]] = {}
    for value in values:
        if not isinstance(value, dict):
            continue
        engine = str(value.get("engine") or "")
        if not engine:
            continue
        key = (
            engine,
            str(value.get("provider") or "") or None,
            str(value.get("model") or "") or None,
            str(value.get("dimensions") or "") or None,
            str(value.get("embedding_profile") or "") or None,
            str(value.get("text_template_version") or "") or None,
        )
        current = best.get(key)
        rank = int(value.get("rank") or 0)
        if current is None or rank < int(current.get("rank") or 10**9):
            best[key] = _normalise_engine_contribution(value)
    return sorted(
        best.values(),
        key=lambda item: (str(item.get("engine")), int(item.get("rank") or 0)),
    )


def _normalise_engine_contribution(value: dict[str, Any]) -> dict[str, Any]:
    normalised = dict(value)
    for key in ("rank", "dimensions"):
        if key in normalised and normalised[key] is not None:
            normalised[key] = int(normalised[key])
    for key in ("raw_score", "route_weight", "rrf"):
        if key in normalised:
            normalised[key] = _safe_float(normalised[key])
    return normalised


def _rrf_score(contributions: list[dict[str, Any]]) -> float:
    return round(sum(float(item.get("rrf") or 0.0) for item in contributions), 6)


def _rrf_rank_component(contributions: list[dict[str, Any]]) -> float:
    return round(_rrf_score(contributions) * 60.0, 6)


def _semantic_rerank_ranks(
    semantic_by_doc: dict[str, SemanticHit | SemanticScore],
) -> dict[str, int]:
    ranked = sorted(
        semantic_by_doc.items(),
        key=lambda item: item[1].similarity,
        reverse=True,
    )
    return {doc_id: rank for rank, (doc_id, _score) in enumerate(ranked, start=1)}


def _safe_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _engine_route_weight(engine: str, plan: QueryPlan) -> float:
    if engine == "fts":
        return 1.25 if plan.exact_terms else 1.0
    if engine == "retrieval_text":
        return 1.15 if "technology" in plan.intents or "science" in plan.intents else 0.95
    if engine == "semantic":
        return 1.2 if "technology" in plan.intents or "author" in plan.intents else 1.0
    if engine == "metadata":
        return 1.25 if plan.requires_bookmark_context or plan.requires_media_context else 1.0
    if engine == "relation_expansion":
        return 1.3 if plan.requires_quote_context or "freshness" in plan.intents else 1.0
    return 0.8


def _feedback_route_scope(plan: QueryPlan) -> str:
    if plan.requires_media_context:
        return "media_context"
    if plan.requires_quote_context:
        return "quote_context"
    if "food" in plan.intents or plan.wants_event_dates:
        return "place_recall"
    if "finance" in plan.intents or "freshness" in plan.intents:
        return "current_fact_check"
    if "author" in plan.intents:
        return "author_stance"
    if "technology" in plan.intents or "science" in plan.intents:
        return "learning_map"
    return "local_memory_search"


def _ensure_semantic_rerank_contribution(
    contributions: list[dict[str, Any]],
    *,
    semantic_hit: SemanticHit | SemanticScore,
    rank: int,
    plan: QueryPlan,
) -> list[dict[str, Any]]:
    existing = [
        item
        for item in contributions
        if item.get("engine") in {"semantic", "semantic_rerank"}
        and item.get("provider") == semantic_hit.provider
        and item.get("model") == semantic_hit.model
        and item.get("dimensions") == semantic_hit.dimensions
        and item.get("embedding_profile") == semantic_hit.embedding_profile
        and item.get("text_template_version") == semantic_hit.text_template_version
    ]
    if existing:
        return contributions
    weight = _engine_route_weight("semantic", plan)
    return [
        *contributions,
        {
            "engine": "semantic_rerank",
            "rank": rank,
            "raw_score": _safe_float(semantic_hit.similarity),
            "route_weight": weight,
            "rrf": round(weight / (60.0 + rank), 8),
            "provider": semantic_hit.provider,
            "model": semantic_hit.model,
            "dimensions": semantic_hit.dimensions,
            "embedding_profile": semantic_hit.embedding_profile,
            "text_template_version": semantic_hit.text_template_version,
        },
    ]


def _result_from_candidate(
    row: dict[str, Any],
    *,
    plan: QueryPlan,
    feedback_score: float,
    bookmark_account_count: int,
    relation_counts: dict[str, int],
    latest_observed_at: datetime | None,
    semantic_hit: SemanticHit | SemanticScore | None,
    semantic_rerank_rank: int | None,
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
    engine_contributions = _dedupe_engine_contributions(
        row.get("_engine_contributions") or [],
    )
    if semantic_hit and semantic_rerank_rank is not None:
        engine_contributions = _ensure_semantic_rerank_contribution(
            engine_contributions,
            semantic_hit=semantic_hit,
            rank=semantic_rerank_rank,
            plan=plan,
        )

    components = {
        "lexical_exact": 2.0 * len(exact_terms),
        "lexical_expansion": 0.65 * len(expansion_matches),
        "retrieval_method": _method_score(methods),
        "doc_type": plan.doc_type_weights.get(str(row["doc_type"]), 0.0),
        "context": _context_score(plan, str(row["doc_type"]), body, metadata),
        "semantic": max(0.0, _safe_float(semantic_hit.similarity)) * semantic_weight
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
        "feedback": _safe_float(feedback_score),
        "rrf": _rrf_rank_component(engine_contributions),
    }
    components = {key: float(value) for key, value in components.items()}
    score = float(round(sum(components.values()), 6))
    metadata = dict(metadata)
    metadata.update(
        {
            "rank_score_components": components,
            "matched_terms": matched_terms,
            "retrieval_methods": methods,
            "engine_contributions": engine_contributions,
            "rrf_raw": _rrf_score(engine_contributions),
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
            "embedding_profile": semantic_hit.embedding_profile,
            "text_template_version": semantic_hit.text_template_version,
            "similarity": _safe_float(semantic_hit.similarity),
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


def _relation_expansion_filters(
    *,
    doc_type: str | None,
    account: str | None,
) -> tuple[str, tuple[Any, ...]]:
    parts = []
    params: list[Any] = []
    if doc_type:
        parts.append("AND d.doc_type = ?")
        params.append(doc_type)
    if account:
        parts.append(
            """
            AND (
                d.account_id = ?
                OR d.account_id IS NULL
                OR d.source_tweet_id IN (
                    SELECT tweet_id
                    FROM account_bookmarks
                    WHERE account_id = ?
                )
            )
            """
        )
        params.extend([account, account])
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
    if "relation_expansion" in methods:
        score += 0.2
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
    if plan.intents:
        score += min(0.6, 0.15 * relation_counts.get("same_topic", 0))
        score += min(0.3, 0.1 * relation_counts.get("incoming:same_topic", 0))
    if plan.requires_bookmark_context or plan.requires_quote_context:
        score += min(0.4, 0.1 * relation_counts.get("same_url", 0))
        score += min(0.2, 0.1 * relation_counts.get("incoming:same_url", 0))
    if plan.excludes_old:
        score -= min(2.0, 0.6 * relation_counts.get("older_same_author_label", 0))
        score -= min(1.5, 0.5 * relation_counts.get("older_than", 0))
        score -= min(1.2, 0.4 * relation_counts.get("incoming:newer_than", 0))
        score -= min(1.0, 0.5 * relation_counts.get("obsolete_candidate", 0))
    if plan.prefers_recent:
        score += min(1.0, 0.4 * relation_counts.get("incoming:older_same_author_label", 0))
        score += min(1.4, 0.45 * relation_counts.get("newer_than", 0))
        score += min(1.0, 0.35 * relation_counts.get("incoming:older_than", 0))
    if "freshness" in plan.intents:
        score += min(1.0, 0.45 * relation_counts.get("supports", 0))
        score += min(1.2, 0.55 * relation_counts.get("contradicts", 0))
        score += min(0.7, 0.3 * relation_counts.get("incoming:supports", 0))
        score += min(0.9, 0.4 * relation_counts.get("incoming:contradicts", 0))
    return score


def _contains_event_date(text: str) -> bool:
    return any(token in text for token in ("202", "開催", "期限", "締切", "予約", "イベント"))


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


def _bookmark_accounts_by_tweet(
    conn: sqlite3.Connection,
    tweet_ids: tuple[str, ...],
) -> dict[str, list[dict[str, Any]]]:
    if not tweet_ids:
        return {}
    placeholders = ",".join("?" for _ in tweet_ids)
    rows = conn.execute(
        f"""
        SELECT tweet_id, account_id, bookmark_index, observed_at, run_id
        FROM account_bookmarks
        WHERE tweet_id IN ({placeholders})
        ORDER BY tweet_id, account_id, bookmark_index
        """,
        tweet_ids,
    ).fetchall()
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        grouped.setdefault(str(row["tweet_id"]), []).append(
            {
                "tweet_id": str(row["tweet_id"]),
                "account_id": str(row["account_id"]),
                "bookmark_index": row["bookmark_index"],
                "observed_at": row["observed_at"],
                "run_id": row["run_id"],
            }
        )
    return grouped


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


def _unique_strings(values: Any) -> list[str]:
    result: list[str] = []
    for value in values:
        text = _string_or_none(value)
        if text is not None and text not in result:
            result.append(text)
    return result


def _string_or_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _components_text(components: dict[str, float]) -> str:
    return ", ".join(
        f"{key}={value:.2f}" for key, value in components.items() if abs(value) > 0.0001
    )
