from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from research_x.memory.query import QueryPlan, build_query_plan
from research_x.memory.schema import ensure_memory_schema

FEEDBACK_LABELS = (
    "useful",
    "not_useful",
    "wrong_topic",
    "too_old",
    "missing_context",
    "good_for_skill",
    "bad_skill_route",
)

FEEDBACK_WEIGHTS = {
    "useful": 1.0,
    "good_for_skill": 0.8,
    "not_useful": -1.2,
    "wrong_topic": -1.8,
    "too_old": -1.0,
    "missing_context": -0.4,
    "bad_skill_route": -0.8,
}


def add_feedback(
    db_path: str | Path,
    *,
    query: str,
    doc_id: str,
    label: str,
    route: str | None = None,
    query_terms: tuple[str, ...] | None = None,
    intents: tuple[str, ...] | None = None,
    note: str | None = None,
) -> str:
    if label not in FEEDBACK_LABELS:
        raise ValueError(f"label must be one of {', '.join(FEEDBACK_LABELS)}")
    plan = build_query_plan(query)
    resolved_terms = tuple(query_terms) if query_terms is not None else plan.search_terms
    resolved_intents = tuple(intents) if intents is not None else plan.intents
    created_at = datetime.now(tz=UTC).isoformat()
    feedback_id = hashlib.sha1(
        "|".join([query, doc_id, label, route or "", created_at, note or ""]).encode("utf-8")
    ).hexdigest()
    with sqlite3.connect(Path(db_path), timeout=60) as conn:
        ensure_memory_schema(conn)
        conn.execute(
            """
            INSERT INTO memory_feedback (
                feedback_id, query, doc_id, label, route,
                query_terms_json, intents_json, note, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                feedback_id,
                query,
                doc_id,
                label,
                route,
                _json_array(resolved_terms),
                _json_array(resolved_intents),
                note,
                created_at,
            ),
        )
    return feedback_id


def feedback_scores_for_docs(
    conn: sqlite3.Connection,
    doc_ids: tuple[str, ...],
    *,
    plan: QueryPlan,
    route: str | None = None,
) -> dict[str, float]:
    if not doc_ids:
        return {}
    placeholders = ",".join("?" for _ in doc_ids)
    rows = conn.execute(
        f"""
        SELECT doc_id, query, label, route, query_terms_json, intents_json
        FROM memory_feedback
        WHERE doc_id IN ({placeholders})
        """,
        doc_ids,
    ).fetchall()
    result: dict[str, float] = {}
    for row in rows:
        doc_id = str(row["doc_id"])
        weight = FEEDBACK_WEIGHTS.get(str(row["label"]), 0.0)
        if not weight:
            continue
        result[doc_id] = result.get(doc_id, 0.0) + (
            weight * _scope_multiplier(row, plan=plan, route=route)
        )
    return result


def _scope_multiplier(row: sqlite3.Row, *, plan: QueryPlan, route: str | None) -> float:
    stored_route = row["route"]
    route_match = bool(route and stored_route and route == stored_route)
    stored_terms = set(_json_array_from_db(row["query_terms_json"]))
    stored_intents = set(_json_array_from_db(row["intents_json"]))
    current_terms = set(plan.search_terms)
    current_intents = set(plan.intents)
    if build_query_plan(str(row["query"])).normalized_query == plan.normalized_query:
        return 1.6 if route_match else 1.4
    term_overlap = len(stored_terms & current_terms)
    intent_overlap = len(stored_intents & current_intents)
    if term_overlap or intent_overlap or route_match:
        term_ratio = term_overlap / max(1, len(stored_terms | current_terms))
        intent_bonus = min(0.3, 0.12 * intent_overlap)
        route_bonus = 0.2 if route_match else 0.0
        return min(1.3, 0.75 + term_ratio + intent_bonus + route_bonus)
    return 0.35


def _json_array(values: tuple[str, ...]) -> str:
    return json.dumps(list(values), ensure_ascii=False, sort_keys=True)


def _json_array_from_db(value: str | None) -> tuple[str, ...]:
    if not value:
        return ()
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return ()
    if not isinstance(parsed, list):
        return ()
    return tuple(str(item) for item in parsed if item is not None)
