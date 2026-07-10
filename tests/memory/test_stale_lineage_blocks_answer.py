from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest
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


def test_stored_ok_answer_missing_source_doc_hash_is_audit_issue(
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
        _rewrite_chunk_lineage_metadata(
            conn,
            chunk_id=chunk_id,
            remove_keys=("source_doc_hash",),
        )

    report = audit_memory_db(db_path)

    assert report.claim_citation_issues["ok_answer_citation_missing_source_lineage"] == 1
    assert any("claim/citation verification issues" in warning for warning in report.warnings)


@pytest.mark.parametrize(
    ("retained_key", "location"),
    (
        pytest.param("source_bundle_id", "top_level", id="bundle-only-top-level"),
        pytest.param("source_restore_id", "source_lineage", id="restore-only-nested"),
    ),
)
def test_stored_ok_answer_accepts_either_compatible_lineage_identifier(
    tmp_path: Path,
    retained_key: str,
    location: str,
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
        _rewrite_chunk_lineage_metadata(
            conn,
            chunk_id=chunk_id,
            remove_keys=("source_bundle_id", "source_restore_id"),
            retained_key=retained_key,
            retained_location=location,
        )

    report = audit_memory_db(db_path)

    assert "ok_answer_citation_missing_source_lineage" not in report.claim_citation_issues
    assert "ok_answer_cites_non_ready_evidence" not in report.claim_citation_issues


def test_stored_ok_answer_missing_both_lineage_identifiers_is_audit_issue(
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
        _rewrite_chunk_lineage_metadata(
            conn,
            chunk_id=chunk_id,
            remove_keys=("source_bundle_id", "source_restore_id"),
        )

    report = audit_memory_db(db_path)

    assert report.claim_citation_issues["ok_answer_citation_missing_source_lineage"] == 1
    assert report.readiness["local_no_provider_ready"] is False


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
        _rewrite_chunk_lineage_metadata(
            conn,
            chunk_id=chunk_id,
            remove_keys=("retrieval_text_hash", "retrieval_text_profile_id"),
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


def _rewrite_chunk_lineage_metadata(
    conn: sqlite3.Connection,
    *,
    chunk_id: str,
    remove_keys: tuple[str, ...],
    retained_key: str | None = None,
    retained_location: str | None = None,
) -> None:
    metadata = _chunk_metadata(conn, chunk_id)
    source_lineage = metadata.get("source_lineage")
    assert isinstance(source_lineage, dict)
    retained_value = None
    if retained_key is not None:
        retained_value = metadata.get(retained_key) or source_lineage.get(retained_key)
        assert retained_value
    for key in remove_keys:
        metadata.pop(key, None)
        source_lineage.pop(key, None)
    if retained_key is not None:
        if retained_location == "top_level":
            metadata[retained_key] = retained_value
        elif retained_location == "source_lineage":
            source_lineage[retained_key] = retained_value
        else:
            raise AssertionError(f"unsupported retained location: {retained_location}")
    conn.execute(
        """
        UPDATE memory_context_chunks
        SET metadata_json = ?
        WHERE chunk_id = ?
        """,
        (json.dumps(metadata, ensure_ascii=False, sort_keys=True), chunk_id),
    )
