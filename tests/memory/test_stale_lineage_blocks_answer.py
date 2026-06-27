from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from test_operational_trace_persistence import _seed_memory_db

from research_x.memory.answer import build_memory_answer
from research_x.memory.audit import audit_memory_db
from research_x.memory.schema import ensure_memory_schema


def test_stored_ok_answer_with_stale_chunk_source_hash_is_audit_issue(
    tmp_path: Path,
) -> None:
    db_path = _seed_memory_db(tmp_path)
    answer = build_memory_answer(
        db_path,
        "強化学習 ロボット",
        limit=1,
        answer_provider="fake",
    )
    chunk_id = answer.selected_context_chunks[0].chunk_id

    with sqlite3.connect(db_path) as conn:
        ensure_memory_schema(conn)
        metadata = _chunk_metadata(conn, chunk_id)
        metadata["source_doc_hash"] = "stale"
        conn.execute(
            """
            UPDATE memory_context_chunks
            SET metadata_json = ?
            WHERE chunk_id = ?
            """,
            (json.dumps(metadata, ensure_ascii=False, sort_keys=True), chunk_id),
        )

    report = audit_memory_db(db_path)

    assert report.claim_citation_issues["ok_answer_citation_source_hash_drift"] == 1
    assert any("claim/citation verification issues" in warning for warning in report.warnings)


def test_stored_ok_answer_missing_source_lineage_is_audit_issue(
    tmp_path: Path,
) -> None:
    db_path = _seed_memory_db(tmp_path)
    answer = build_memory_answer(
        db_path,
        "強化学習 ロボット",
        limit=1,
        answer_provider="fake",
    )
    chunk_id = answer.selected_context_chunks[0].chunk_id

    with sqlite3.connect(db_path) as conn:
        ensure_memory_schema(conn)
        metadata = _chunk_metadata(conn, chunk_id)
        metadata.pop("source_doc_hash", None)
        metadata.pop("source_bundle_id", None)
        conn.execute(
            """
            UPDATE memory_context_chunks
            SET metadata_json = ?
            WHERE chunk_id = ?
            """,
            (json.dumps(metadata, ensure_ascii=False, sort_keys=True), chunk_id),
        )

    report = audit_memory_db(db_path)

    assert report.claim_citation_issues["ok_answer_citation_missing_source_lineage"] == 1
    assert any("claim/citation verification issues" in warning for warning in report.warnings)


def test_stored_ok_answer_missing_retrieval_lineage_is_audit_issue(
    tmp_path: Path,
) -> None:
    db_path = _seed_memory_db(tmp_path)
    answer = build_memory_answer(
        db_path,
        "強化学習 ロボット",
        limit=1,
        answer_provider="fake",
    )
    chunk_id = answer.selected_context_chunks[0].chunk_id

    with sqlite3.connect(db_path) as conn:
        ensure_memory_schema(conn)
        metadata = _chunk_metadata(conn, chunk_id)
        metadata.pop("retrieval_text_hash", None)
        metadata.pop("retrieval_text_profile_id", None)
        conn.execute(
            """
            UPDATE memory_context_chunks
            SET metadata_json = ?
            WHERE chunk_id = ?
            """,
            (json.dumps(metadata, ensure_ascii=False, sort_keys=True), chunk_id),
        )

    report = audit_memory_db(db_path)

    assert report.claim_citation_issues["ok_answer_citation_missing_source_lineage"] == 1
    assert any("claim/citation verification issues" in warning for warning in report.warnings)


def _chunk_metadata(conn: sqlite3.Connection, chunk_id: str) -> dict[str, object]:
    row = conn.execute(
        """
        SELECT metadata_json
        FROM memory_context_chunks
        WHERE chunk_id = ?
        """,
        (chunk_id,),
    ).fetchone()
    assert row is not None
    metadata = json.loads(row[0])
    assert isinstance(metadata, dict)
    return metadata
