from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from research_x.memory.document_hashes import memory_document_source_hash
from research_x.memory.objective_routes import ObjectiveRoutePlan, plan_objective_routes
from research_x.memory.query import build_query_plan
from research_x.memory.schema import ensure_memory_schema
from research_x.memory.search import strong_anchor_terms_for_query

FINAL_SKELETON_PREFLIGHT_VERSION = "final-skeleton-preflight-v1"
DEFAULT_EVAL_GATES = (
    "route_eval",
    "retrieval_eval",
    "context_eval",
    "citation_eval",
    "answer_eval",
    "abstention_eval",
)


@dataclass(frozen=True)
class FinalSkeletonPreflightReport:
    preflight_id: str
    query: str
    stored: bool
    route_plan: dict[str, Any]
    query_transforms: int
    retrieval_text_profiles: int
    eval_gates: int
    projection_generations: int
    index_memberships: int
    security_boundaries: int
    visual_recall_evidence: int
    user_ranking_signals: int
    provider_quota_blocked: bool
    next_paid_gate: str
    notes: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            **asdict(self),
            "notes": list(self.notes),
        }


def run_final_skeleton_preflight(
    db_path: str | Path,
    query: str,
    *,
    route: str = "auto",
    limit: int = 10,
    store: bool = True,
) -> FinalSkeletonPreflightReport:
    path = Path(db_path)
    if not path.exists():
        raise FileNotFoundError(f"database not found: {path}")

    plan = plan_objective_routes(query, requested_route=route)
    query_plan = build_query_plan(query)
    now = _utc_now()
    preflight_id = _stable_id("final-skeleton-preflight", query, now)
    parent_query_id = _stable_id("query", query)

    with sqlite3.connect(path, timeout=60) as conn:
        conn.row_factory = sqlite3.Row
        ensure_memory_schema(conn)
        doc_rows = _document_rows(conn, limit=limit)
        media_rows = _media_rows(conn, limit=limit)
        bookmark_rows = _bookmark_signal_rows(conn, limit=limit)

        query_transforms = _query_transform_rows(
            preflight_id=preflight_id,
            parent_query_id=parent_query_id,
            query=query,
            plan=plan,
            query_plan=query_plan,
            now=now,
        )
        retrieval_profiles = _retrieval_text_profile_rows(doc_rows, now=now)
        generation_id, projection_row, membership_rows = _projection_rows(
            preflight_id=preflight_id,
            query=query,
            plan=plan,
            doc_rows=doc_rows,
            now=now,
        )
        boundary_rows = _security_boundary_rows(
            preflight_id=preflight_id,
            query_transform_rows=query_transforms,
            retrieval_profile_rows=retrieval_profiles,
            media_rows=media_rows,
            now=now,
        )
        visual_rows = _visual_recall_rows(media_rows, now=now)
        user_signal_rows = _user_ranking_signal_rows(bookmark_rows, now=now)
        eval_rows = _eval_gate_rows(
            preflight_id=preflight_id,
            query=query,
            plan=plan,
            doc_rows=doc_rows,
            media_rows=media_rows,
            now=now,
        )

        if store:
            _insert_many(
                conn,
                "memory_query_transforms",
                query_transforms,
            )
            _insert_retrieval_text_profiles(conn, retrieval_profiles)
            _insert_many(
                conn,
                "memory_projection_generations",
                (projection_row,),
            )
            _insert_many(conn, "memory_index_membership", membership_rows)
            _insert_many(conn, "memory_security_boundaries", boundary_rows)
            _insert_many(conn, "memory_visual_recall_evidence", visual_rows)
            _insert_many(conn, "memory_user_ranking_signals", user_signal_rows)
            _insert_many(conn, "memory_eval_gate_results", eval_rows)
            conn.commit()

    notes = [
        "provider quota remains blocked; this preflight only writes no-spend artifacts",
        "query transforms and retrieval text profiles are citation_excluded",
        "user ranking signals are hints, not evidence",
        (
            "visual recall evidence is not media_content_evidence until region/page chunks are "
            "promoted"
        ),
    ]
    if not doc_rows:
        notes.append(
            "no memory_documents rows found; build the memory corpus before retrieval eval"
        )
    if not media_rows:
        notes.append("no media rows found; visual recall evidence surface has no candidates")

    return FinalSkeletonPreflightReport(
        preflight_id=preflight_id,
        query=query,
        stored=store,
        route_plan=plan.as_dict(),
        query_transforms=len(query_transforms),
        retrieval_text_profiles=len(retrieval_profiles),
        eval_gates=len(eval_rows),
        projection_generations=1,
        index_memberships=len(membership_rows),
        security_boundaries=len(boundary_rows),
        visual_recall_evidence=len(visual_rows),
        user_ranking_signals=len(user_signal_rows),
        provider_quota_blocked=True,
        next_paid_gate=(
            "provider-backed semantic/rerank/reader/OCR/media build remains blocked until explicit "
            "quota permission"
        ),
        notes=tuple(notes),
    )


def final_skeleton_preflight_json(report: FinalSkeletonPreflightReport) -> str:
    return json.dumps(report.as_dict(), ensure_ascii=False, indent=2, sort_keys=True)


def format_final_skeleton_preflight(report: FinalSkeletonPreflightReport) -> str:
    lines = [
        f"final_skeleton_preflight: {report.preflight_id}",
        f"query: {report.query}",
        f"stored: {report.stored}",
        f"primary_route: {report.route_plan.get('primary_route')}",
        f"query_transforms: {report.query_transforms}",
        f"retrieval_text_profiles: {report.retrieval_text_profiles}",
        f"eval_gates: {report.eval_gates}",
        f"projection_generations: {report.projection_generations}",
        f"index_memberships: {report.index_memberships}",
        f"security_boundaries: {report.security_boundaries}",
        f"visual_recall_evidence: {report.visual_recall_evidence}",
        f"user_ranking_signals: {report.user_ranking_signals}",
        f"provider_quota_blocked: {report.provider_quota_blocked}",
        f"next_paid_gate: {report.next_paid_gate}",
    ]
    lines.extend(f"note: {note}" for note in report.notes)
    return "\n".join(lines)


def _query_transform_rows(
    *,
    preflight_id: str,
    parent_query_id: str,
    query: str,
    plan: ObjectiveRoutePlan,
    query_plan: Any,
    now: str,
) -> tuple[dict[str, Any], ...]:
    anchors = tuple(str(term) for term in strong_anchor_terms_for_query(query))
    exact_terms = tuple(str(term) for term in getattr(query_plan, "exact_terms", ()) or ())
    search_terms = tuple(str(term) for term in getattr(query_plan, "search_terms", ()) or ())
    media_needed = bool(getattr(query_plan, "requires_media_context", False))

    candidates: list[tuple[str, str, tuple[str, ...], tuple[str, ...]]] = [
        (
            "original_query",
            query,
            anchors or exact_terms,
            (plan.primary_route, *plan.fallback_routes),
        ),
    ]
    if exact_terms:
        candidates.append(
            (
                "exact_anchor_query",
                " ".join(exact_terms),
                exact_terms,
                ("exact_metadata_social", "candidate_a_current_baseline"),
            )
        )
    if search_terms:
        candidates.append(
            (
                "lexical_recall_query",
                " ".join(search_terms[:8]),
                tuple(term for term in search_terms[:8] if term in exact_terms or term in anchors),
                ("exact_metadata_social", "semantic_embedding_portfolio"),
            )
        )
    if media_needed:
        candidates.append(
            (
                "media_grounded_query",
                f"{query} media image OCR visual evidence",
                anchors or exact_terms,
                ("media_evidence", "semantic_embedding_portfolio"),
            )
        )

    rows: list[dict[str, Any]] = []
    for index, (kind, generated_text, preserved, routes) in enumerate(candidates):
        drift_flags = []
        if not preserved and kind != "original_query":
            drift_flags.append("no_preserved_anchor")
        if kind in {"media_grounded_query", "lexical_recall_query"}:
            drift_flags.append("generated_search_text")
        rows.append(
            {
                "transform_id": _stable_id(preflight_id, "query-transform", index, kind),
                "parent_query_id": parent_query_id,
                "query": query,
                "transform_kind": kind,
                "generated_text": generated_text,
                "preserved_anchors_json": _json(preserved),
                "allowed_routes_json": _json(routes),
                "drift_flags_json": _json(drift_flags),
                "citation_excluded": 1,
                "created_at": now,
                "metadata_json": _json(
                    {
                        "preflight_id": preflight_id,
                        "contract": "query_transform_is_search_artifact_not_evidence",
                    }
                ),
            }
        )
    return tuple(rows)


def _retrieval_text_profile_rows(
    rows: tuple[sqlite3.Row, ...],
    *,
    now: str,
) -> tuple[dict[str, Any], ...]:
    output: list[dict[str, Any]] = []
    for row in rows:
        doc = dict(row)
        source_hash = doc.get("source_doc_hash") or memory_document_source_hash(doc)
        compact = str(doc.get("compact_text") or doc.get("body") or "")
        contextual = " | ".join(
            part
            for part in (
                f"title: {doc.get('title')}" if doc.get("title") else "",
                f"author: {doc.get('author_screen_name')}" if doc.get("author_screen_name") else "",
                f"type: {doc.get('doc_type')}" if doc.get("doc_type") else "",
                f"text: {compact}",
            )
            if part
        )
        for profile, text in (
            ("raw_compact", compact),
            ("contextual_bm25", contextual),
        ):
            if not text:
                continue
            output.append(
                {
                    "profile_id": _stable_id(doc["doc_id"], profile, source_hash),
                    "doc_id": doc["doc_id"],
                    "retrieval_text_profile": profile,
                    "retrieval_text": text,
                    "source_doc_hash": source_hash,
                    "citation_excluded": 1,
                    "created_at": now,
                    "metadata_json": _json(
                        {
                            "contract": "retrieval_text_profile_is_projection_not_source",
                            "doc_type": doc.get("doc_type"),
                        }
                    ),
                }
            )
    return tuple(output)


def _projection_rows(
    *,
    preflight_id: str,
    query: str,
    plan: ObjectiveRoutePlan,
    doc_rows: tuple[sqlite3.Row, ...],
    now: str,
) -> tuple[str, dict[str, Any], tuple[dict[str, Any], ...]]:
    generation_id = _stable_id(preflight_id, "projection", "final_skeleton")
    projection = {
        "generation_id": generation_id,
        "projection_kind": "final_skeleton_no_spend_surface",
        "source_scope": "memory_documents",
        "builder_version": FINAL_SKELETON_PREFLIGHT_VERSION,
        "input_manifest_json": _json(
            {
                "query": query,
                "primary_route": plan.primary_route,
                "fallback_routes": list(plan.fallback_routes),
            }
        ),
        "status": "ready",
        "coverage_json": _json(
            {
                "sampled_documents": len(doc_rows),
                "provider_quota_blocked": True,
            }
        ),
        "created_at": now,
        "metadata_json": _json({"preflight_id": preflight_id}),
    }
    memberships = []
    for row in doc_rows:
        source_hash = row["source_doc_hash"] or memory_document_source_hash(dict(row))
        memberships.append(
            {
                "membership_id": _stable_id(generation_id, row["doc_id"], source_hash),
                "generation_id": generation_id,
                "artifact_kind": "memory_document",
                "artifact_id": row["doc_id"],
                "source_id": row["source_tweet_id"] or row["doc_id"],
                "source_hash": source_hash,
                "membership_status": "active",
                "created_at": now,
                "metadata_json": _json({"doc_type": row["doc_type"]}),
            }
        )
    return generation_id, projection, tuple(memberships)


def _security_boundary_rows(
    *,
    preflight_id: str,
    query_transform_rows: tuple[dict[str, Any], ...],
    retrieval_profile_rows: tuple[dict[str, Any], ...],
    media_rows: tuple[sqlite3.Row, ...],
    now: str,
) -> tuple[dict[str, Any], ...]:
    rows: list[dict[str, Any]] = []
    for transform in query_transform_rows:
        rows.append(
            _security_boundary_row(
                preflight_id=preflight_id,
                artifact_kind="query_transform",
                artifact_id=str(transform["transform_id"]),
                source_kind="user_query_generated",
                trust_boundary="trusted_user_query_to_generated_search_text",
                taint_flags=("generated_text", "citation_excluded"),
                source_visibility="local_private",
                account_scope=None,
                allowed_sinks=("local_search", "route_trace"),
                now=now,
            )
        )
    for profile in retrieval_profile_rows:
        rows.append(
            _security_boundary_row(
                preflight_id=preflight_id,
                artifact_kind="retrieval_text_profile",
                artifact_id=str(profile["profile_id"]),
                source_kind="local_x_db",
                trust_boundary="local_user_generated_content",
                taint_flags=("untrusted_text", "citation_excluded"),
                source_visibility="account_scoped",
                account_scope=None,
                allowed_sinks=("local_search", "candidate_generation"),
                now=now,
            )
        )
    for media in media_rows:
        rows.append(
            _security_boundary_row(
                preflight_id=preflight_id,
                artifact_kind="media",
                artifact_id=str(media["media_id"]),
                source_kind="local_x_media",
                trust_boundary="local_media_untrusted_content",
                taint_flags=("untrusted_media", "ocr_or_visual_required_for_content_claim"),
                source_visibility="account_scoped",
                account_scope=None,
                allowed_sinks=("media_source_evidence", "ocr_quality_pipeline", "visual_recall"),
                now=now,
            )
        )
    return tuple(rows)


def _security_boundary_row(
    *,
    preflight_id: str,
    artifact_kind: str,
    artifact_id: str,
    source_kind: str,
    trust_boundary: str,
    taint_flags: tuple[str, ...],
    source_visibility: str,
    account_scope: str | None,
    allowed_sinks: tuple[str, ...],
    now: str,
) -> dict[str, Any]:
    return {
        "boundary_id": _stable_id(preflight_id, "security", artifact_kind, artifact_id),
        "run_id": preflight_id,
        "artifact_kind": artifact_kind,
        "artifact_id": artifact_id,
        "source_kind": source_kind,
        "trust_boundary": trust_boundary,
        "taint_flags_json": _json(taint_flags),
        "data_classification": "private_x_memory",
        "source_visibility": source_visibility,
        "account_scope": account_scope,
        "allowed_sinks_json": _json(allowed_sinks),
        "created_at": now,
        "metadata_json": _json({"preflight_id": preflight_id}),
    }


def _visual_recall_rows(rows: tuple[sqlite3.Row, ...], *, now: str) -> tuple[dict[str, Any], ...]:
    output = []
    for row in rows:
        metadata = {
            "media_url": row["url"],
            "local_path": row["local_path"],
            "download_status": row["download_status"],
            "content_type": row["content_type"],
            "contract": "visual_recall_candidate_not_media_content_evidence",
        }
        output.append(
            {
                "visual_evidence_id": _stable_id("visual-recall", row["media_id"], row["tweet_id"]),
                "media_id": row["media_id"],
                "source_tweet_id": row["tweet_id"],
                "evidence_level": "visual_recall_evidence",
                "page_index": 0,
                "region_index": 0,
                "pixel_bbox_json": _json({}),
                "normalized_bbox_json": _json({}),
                "citation_ready": 0,
                "source_image_hash": None,
                "provider": "local_preflight",
                "model": "none",
                "created_at": now,
                "metadata_json": _json(metadata),
            }
        )
    return tuple(output)


def _user_ranking_signal_rows(
    rows: tuple[sqlite3.Row, ...],
    *,
    now: str,
) -> tuple[dict[str, Any], ...]:
    output = []
    for row in rows:
        output.append(
            {
                "signal_id": _stable_id("user-signal", row["account_id"], row["tweet_id"]),
                "subject_kind": "tweet",
                "subject_id": row["tweet_id"],
                "signal_type": "bookmarked_by_account",
                "signal_value": 1.0,
                "confidence": 0.8,
                "route_scope": "refinding,subjective_preference,exploratory_learning",
                "evidence_status": "ranking_hint_not_evidence",
                "created_at": now,
                "metadata_json": _json(
                    {
                        "account_id": row["account_id"],
                        "observed_at": row["observed_at"],
                        "bookmark_index": row["bookmark_index"],
                    }
                ),
            }
        )
    return tuple(output)


def _eval_gate_rows(
    *,
    preflight_id: str,
    query: str,
    plan: ObjectiveRoutePlan,
    doc_rows: tuple[sqlite3.Row, ...],
    media_rows: tuple[sqlite3.Row, ...],
    now: str,
) -> tuple[dict[str, Any], ...]:
    statuses = {
        "route_eval": "ready" if plan.primary_route else "needs_review",
        "retrieval_eval": "ready" if doc_rows else "needs_corpus",
        "context_eval": "ready" if doc_rows else "needs_corpus",
        "citation_eval": "ready" if doc_rows else "needs_corpus",
        "answer_eval": "blocked_before_provider_answer",
        "abstention_eval": "ready",
    }
    rows = []
    for gate in DEFAULT_EVAL_GATES:
        status = statuses[gate]
        rows.append(
            {
                "gate_result_id": _stable_id(preflight_id, "eval-gate", gate),
                "route_run_id": preflight_id,
                "workflow_id": None,
                "answer_id": None,
                "query": query,
                "gate_name": gate,
                "status": status,
                "score": None,
                "evaluator_kind": "deterministic_preflight",
                "evidence_json": _json(
                    {
                        "primary_route": plan.primary_route,
                        "document_candidates": len(doc_rows),
                        "media_candidates": len(media_rows),
                        "provider_quota_blocked": True,
                    }
                ),
                "created_at": now,
                "metadata_json": _json(
                    {
                        "contract": "gate_result_is_preflight_not_promotion",
                    }
                ),
            }
        )
    return tuple(rows)


def _document_rows(conn: sqlite3.Connection, *, limit: int) -> tuple[sqlite3.Row, ...]:
    return tuple(
        conn.execute(
            """
            SELECT
                doc_id, doc_type, source_tweet_id, account_id, author_screen_name,
                title, body, compact_text, metadata_json, source_doc_hash
            FROM memory_documents
            ORDER BY updated_at DESC, doc_id
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    )


def _media_rows(conn: sqlite3.Connection, *, limit: int) -> tuple[sqlite3.Row, ...]:
    if not _table_exists(conn, "media"):
        return ()
    return tuple(
        conn.execute(
            """
            SELECT media_id, tweet_id, url, local_path, download_status, content_type
            FROM media
            ORDER BY media_id
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    )


def _bookmark_signal_rows(conn: sqlite3.Connection, *, limit: int) -> tuple[sqlite3.Row, ...]:
    if not _table_exists(conn, "account_bookmarks"):
        return ()
    return tuple(
        conn.execute(
            """
            SELECT account_id, tweet_id, bookmark_index, observed_at
            FROM account_bookmarks
            ORDER BY observed_at DESC, account_id, tweet_id
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    )


def _insert_many(
    conn: sqlite3.Connection,
    table: str,
    rows: tuple[dict[str, Any], ...],
) -> None:
    if not rows:
        return
    columns = tuple(rows[0].keys())
    placeholders = ", ".join("?" for _ in columns)
    sql = (
        f"INSERT OR REPLACE INTO {table} "
        f"({', '.join(columns)}) VALUES ({placeholders})"
    )
    conn.executemany(sql, [tuple(row[column] for column in columns) for row in rows])


def _insert_retrieval_text_profiles(
    conn: sqlite3.Connection,
    rows: tuple[dict[str, Any], ...],
) -> None:
    if not rows:
        return
    _insert_many(conn, "memory_retrieval_text_profiles", rows)
    conn.executemany(
        "DELETE FROM memory_retrieval_text_fts WHERE profile_id = ?",
        [(row["profile_id"],) for row in rows],
    )
    conn.executemany(
        """
        INSERT INTO memory_retrieval_text_fts (
            profile_id, doc_id, retrieval_text_profile, retrieval_text
        )
        VALUES (?, ?, ?, ?)
        """,
        [
            (
                row["profile_id"],
                row["doc_id"],
                row["retrieval_text_profile"],
                row["retrieval_text"],
            )
            for row in rows
        ],
    )


def _table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table_name,),
    ).fetchone()
    return row is not None


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _stable_id(*parts: object) -> str:
    raw = "\0".join(str(part) for part in parts).encode()
    return hashlib.sha256(raw).hexdigest()[:24]


def _utc_now() -> str:
    return datetime.now(tz=UTC).isoformat()
