from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from research_x.memory.schema import ensure_memory_schema
from research_x.memory.working_notes import (
    append_working_note,
    create_working_note,
    expire_working_note,
    link_working_note_to_artifacts,
    promote_working_note_to_curated_source,
    read_working_note,
)

CANON_ITEM = "P8"
PURPOSE = "Working notes are local notes until explicit human-approved promotion."
pytestmark = pytest.mark.canon(CANON_ITEM)


def test_working_note_lifecycle_does_not_auto_promote(tmp_path: Path) -> None:
    db_path = tmp_path / "x.sqlite3"
    _ensure_db(db_path)

    note = create_working_note(
        db_path,
        title="compare sources",
        body="initial hypothesis",
        task_scope="task-1",
        thread_scope="thread-1",
        source_refs=("x:tweet:tweet-1",),
        artifact_refs=("memory_document:doc-1",),
        created_at="2026-07-03T00:00:00Z",
    )
    note = append_working_note(
        db_path,
        note.working_note_id,
        "second line",
        updated_at="2026-07-03T00:01:00Z",
    )
    note = link_working_note_to_artifacts(
        db_path,
        note.working_note_id,
        source_refs=("x:tweet:tweet-2",),
        artifact_refs=("memory_document:doc-2",),
        updated_at="2026-07-03T00:02:00Z",
    )

    assert note.body == "initial hypothesis\nsecond line"
    assert note.source_refs == ("x:tweet:tweet-1", "x:tweet:tweet-2")
    assert note.artifact_refs == ("memory_document:doc-1", "memory_document:doc-2")
    assert note.note_status == "active"
    assert read_working_note(db_path, note.working_note_id) == note

    with sqlite3.connect(db_path) as conn:
        source_count = conn.execute("SELECT COUNT(*) FROM memory_sources").fetchone()[0]
        artifact_count = conn.execute("SELECT COUNT(*) FROM memory_artifacts").fetchone()[0]

    assert source_count == 0
    assert artifact_count == 0


def test_working_note_expire_marks_note_not_source(tmp_path: Path) -> None:
    db_path = tmp_path / "x.sqlite3"
    _ensure_db(db_path)
    note = create_working_note(
        db_path,
        title="temporary",
        body="temporary note",
        task_scope="task-1",
        created_at="2026-07-03T00:00:00Z",
    )

    expired = expire_working_note(
        db_path,
        note.working_note_id,
        expired_at="2026-07-03T01:00:00Z",
    )

    assert expired.note_status == "expired"
    assert expired.expires_at == "2026-07-03T01:00:00Z"


def test_promote_working_note_to_curated_source_is_explicit(tmp_path: Path) -> None:
    db_path = tmp_path / "x.sqlite3"
    _ensure_db(db_path)
    note = create_working_note(
        db_path,
        title="curated after review",
        body="reviewed note",
        task_scope="task-1",
        source_refs=("x:tweet:tweet-1",),
        created_at="2026-07-03T00:00:00Z",
    )

    with pytest.raises(ValueError, match="human-in-the-loop approval"):
        promote_working_note_to_curated_source(
            db_path,
            note.working_note_id,
            promoted_at="2026-07-03T01:00:00Z",
        )

    promotion = promote_working_note_to_curated_source(
        db_path,
        note.working_note_id,
        human_in_loop_approved=True,
        approved_by="human-reviewer",
        approval_note="reviewed for curated source promotion",
        promoted_at="2026-07-03T01:00:00Z",
    )

    with sqlite3.connect(db_path) as conn:
        source = conn.execute(
            """
            SELECT source_kind, source_status, metadata_json
            FROM memory_sources
            WHERE source_ref = ?
            """,
            (promotion.source_ref,),
        ).fetchone()
        artifact = conn.execute(
            """
            SELECT artifact_role, artifact_kind, authority_level
            FROM memory_artifacts
            WHERE artifact_id = ?
            """,
            (promotion.artifact_id,),
        ).fetchone()
        audit = conn.execute(
            """
            SELECT event_type, subject_kind, subject_id
            FROM memory_audit_events
            WHERE event_type = 'working_note_promoted'
            """
        ).fetchone()

    assert source[0:2] == ("working_note", "available")
    assert '"human_in_loop_approved":true' in source[2]
    assert '"approved_by":"human-reviewer"' in source[2]
    assert artifact == (
        "curated_source",
        "working_note_curated_source",
        "source_backed",
    )
    assert audit == (
        "working_note_promoted",
        "working_note",
        note.working_note_id,
    )


def _ensure_db(db_path: Path) -> None:
    with sqlite3.connect(db_path) as conn:
        ensure_memory_schema(conn)
