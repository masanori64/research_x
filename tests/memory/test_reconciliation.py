from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from research_x.memory.reconciliation import reconcile_source_observation
from research_x.memory.schema import ensure_memory_schema

CANON_ITEMS = ("P11", "P13")
PURPOSE = "Reconciliation records operational audit state without becoming evidence."
pytestmark = [pytest.mark.canon(item) for item in CANON_ITEMS]


@pytest.mark.parametrize(
    ("completeness", "expected"),
    (
        ("complete", ("source_missing_complete", "tombstone_candidate")),
        ("partial", ("source_missing_partial", "missing_in_partial_observation")),
        ("unknown", ("needs_review", "needs_review")),
    ),
)
def test_missing_source_action_depends_on_observation_completeness(
    tmp_path: Path,
    completeness: str,
    expected: tuple[str, str],
) -> None:
    db_path = tmp_path / "x.sqlite3"
    _seed_sources(db_path)

    reconcile_source_observation(
        db_path,
        observed_source_refs=("x:tweet:tweet-1",),
        observation_completeness=completeness,
        reconciliation_run_id=f"run-{completeness}",
        started_at="2026-07-03T00:00:00Z",
    )

    assert _status_for(db_path, f"run-{completeness}", "x:tweet:tweet-2") == expected


def test_reconciliation_audit_event_is_control_state_not_evidence(tmp_path: Path) -> None:
    db_path = tmp_path / "x.sqlite3"
    _seed_sources(db_path)

    reconcile_source_observation(
        db_path,
        observed_source_refs=("x:tweet:tweet-1",),
        observation_completeness="partial",
        reconciliation_run_id="run-audit",
        started_at="2026-07-03T00:00:00Z",
    )

    with sqlite3.connect(db_path) as conn:
        event = conn.execute(
            """
            SELECT event_type, subject_kind, subject_id, metadata_json
            FROM memory_audit_events
            WHERE subject_id = 'run-audit'
            """
        ).fetchone()

    assert event[:3] == (
        "source_reconciliation_completed",
        "reconciliation_run",
        "run-audit",
    )
    metadata = json.loads(event[3])
    assert metadata["artifact_role"] == "control_state"
    assert metadata["authority_level"] == "navigation_signal"
    assert metadata["not_evidence"] is True


def test_reconciliation_marks_artifact_role_mismatch_for_review(tmp_path: Path) -> None:
    db_path = tmp_path / "x.sqlite3"
    with sqlite3.connect(db_path) as conn:
        ensure_memory_schema(conn)
        _insert_artifact(
            conn,
            artifact_id="artifact-answer-spoof",
            artifact_role="projection",
            authority_level="answer_assertion",
            output_mode="answer",
        )

    summary = reconcile_source_observation(
        db_path,
        observed_source_refs=(),
        observation_completeness="complete",
        reconciliation_run_id="run-role-mismatch",
        started_at="2026-07-03T00:00:00Z",
    )

    assert summary.by_status == {"needs_review": 1}
    assert _status_for(db_path, "run-role-mismatch", "artifact-answer-spoof") == (
        "artifact_role_mismatch",
        "needs_review",
    )


def _seed_sources(db_path: Path) -> None:
    with sqlite3.connect(db_path) as conn:
        ensure_memory_schema(conn)
        for source_ref in ("x:tweet:tweet-1", "x:tweet:tweet-2"):
            conn.execute(
                """
                INSERT INTO memory_sources (
                    source_ref, source_kind, source_uri, source_title,
                    source_owner, raw_hash, normalized_content_hash,
                    source_status, visibility, first_observed_at,
                    last_observed_at, updated_at, metadata_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    source_ref,
                    "x_tweet",
                    None,
                    source_ref,
                    None,
                    "raw",
                    "normalized",
                    "available",
                    "private",
                    "2026-07-03T00:00:00Z",
                    "2026-07-03T00:00:00Z",
                    "2026-07-03T00:00:00Z",
                    "{}",
                ),
            )


def _insert_artifact(
    conn: sqlite3.Connection,
    *,
    artifact_id: str,
    artifact_role: str,
    authority_level: str,
    output_mode: str,
) -> None:
    conn.execute(
        """
        INSERT INTO memory_artifacts (
            artifact_id, artifact_role, artifact_kind, source_refs_json,
            content_hash, authority_level, output_mode, retention_policy,
            artifact_status, created_at, updated_at, metadata_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            artifact_id,
            artifact_role,
            "test_artifact",
            "[]",
            "hash",
            authority_level,
            output_mode,
            "test",
            "active",
            "2026-07-03T00:00:00Z",
            "2026-07-03T00:00:00Z",
            "{}",
        ),
    )


def _status_for(
    db_path: Path,
    reconciliation_run_id: str,
    subject_id: str,
) -> tuple[str, str]:
    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            """
            SELECT action, status
            FROM memory_reconciliation_items
            WHERE reconciliation_run_id = ? AND subject_id = ?
            """,
            (reconciliation_run_id, subject_id),
        ).fetchone()
    assert row is not None
    return row
