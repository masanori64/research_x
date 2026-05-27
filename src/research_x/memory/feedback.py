from __future__ import annotations

import hashlib
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

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


def add_feedback(
    db_path: str | Path,
    *,
    query: str,
    doc_id: str,
    label: str,
    note: str | None = None,
) -> str:
    if label not in FEEDBACK_LABELS:
        raise ValueError(f"label must be one of {', '.join(FEEDBACK_LABELS)}")
    created_at = datetime.now(tz=UTC).isoformat()
    feedback_id = hashlib.sha1(
        "|".join([query, doc_id, label, created_at, note or ""]).encode("utf-8")
    ).hexdigest()
    with sqlite3.connect(Path(db_path), timeout=60) as conn:
        ensure_memory_schema(conn)
        conn.execute(
            """
            INSERT INTO memory_feedback (
                feedback_id, query, doc_id, label, note, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (feedback_id, query, doc_id, label, note, created_at),
        )
    return feedback_id
