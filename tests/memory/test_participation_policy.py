from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from research_x.memory.participation import (
    evaluate_artifact_participation,
    evaluate_source_participation,
    rebuild_participation_decisions,
)
from research_x.memory.schema import ensure_memory_schema
from research_x.memory.search import search_memory
from research_x.tool_interface.mode_aware_search import search_results_tool_output_v2

CANON_ITEMS = ("P5", "P7")
PURPOSE = "Participation decisions are per-use and flow into mode-aware output."
pytestmark = [pytest.mark.canon(item) for item in CANON_ITEMS]


@pytest.mark.parametrize(
    (
        "artifact_role",
        "authority_level",
        "output_mode",
        "expected",
    ),
    (
        (
            "projection",
            "candidate",
            "explore",
            {"can_search": True, "can_explore": True, "can_use_in_answer": False},
        ),
        (
            "projection",
            "candidate",
            "evidence_package",
            {"can_use_as_evidence": False, "can_use_in_answer": False},
        ),
        (
            "working_note",
            "candidate",
            "working_note",
            {"can_use_in_working_note": True, "can_use_as_evidence": False},
        ),
        (
            "working_note",
            "candidate",
            "answer",
            {"can_use_as_evidence": False, "can_use_in_answer": False},
        ),
        (
            "evidence_view",
            "evidence_view",
            "evidence_package",
            {"can_use_as_evidence": True, "can_use_in_answer": False},
        ),
        (
            "evidence_view",
            "claim_supported",
            "answer",
            {"can_use_as_evidence": True, "can_use_in_answer": True},
        ),
        (
            "control_state",
            "navigation_signal",
            "answer",
            {"can_search": False, "can_use_as_evidence": False, "can_use_in_answer": False},
        ),
    ),
)
def test_role_based_participation_matrix(
    artifact_role: str,
    authority_level: str,
    output_mode: str,
    expected: dict[str, bool],
) -> None:
    decision = evaluate_artifact_participation(
        artifact_role=artifact_role,
        authority_level=authority_level,
        output_mode=output_mode,
        status="active",
    )

    for field, value in expected.items():
        assert getattr(decision, field) is value
    assert decision.can_trigger_external_fetch is False


def test_source_participation_never_grants_external_fetch() -> None:
    source = evaluate_source_participation(
        source_status="available",
        output_mode="explore",
    )

    assert source.can_search
    assert source.can_explore
    assert source.can_use_in_working_note
    assert source.can_use_as_evidence
    assert not source.can_use_in_answer
    assert not source.can_trigger_external_fetch


def test_rebuild_participation_decisions_writes_mode_rows(tmp_path: Path) -> None:
    db_path = tmp_path / "x.sqlite3"
    _seed_participation_subjects(db_path)

    summary = rebuild_participation_decisions(
        db_path,
        output_modes=("explore", "answer"),
        decided_at="2026-07-03T00:00:00Z",
    )

    assert summary.subjects == 3
    assert summary.decisions == 6
    assert summary.by_output_mode == {"answer": 3, "explore": 3}

    with sqlite3.connect(db_path) as conn:
        rows = {
            (row[0], row[1], row[2]): row[3:7]
            for row in conn.execute(
                """
                SELECT source_ref, artifact_id, output_mode,
                       can_search, can_use_as_evidence, can_use_in_answer,
                       can_trigger_external_fetch
                FROM memory_participation_decisions
                """
            )
        }

    assert rows[("x:tweet:tweet-1", None, "explore")] == (1, 1, 0, 0)
    assert rows[(None, "artifact-working-note", "answer")] == (1, 0, 0, 0)
    assert rows[(None, "artifact-evidence", "answer")] == (1, 1, 1, 0)

    with sqlite3.connect(db_path) as conn:
        metadata = {
            row[0]: row[1:]
            for row in conn.execute(
                """
                SELECT artifact_id, subject_kind, policy_version, severity,
                       decided_by, input_hash_json
                FROM memory_participation_decisions
                WHERE artifact_id IS NOT NULL
                """
            )
        }

    assert metadata["artifact-evidence"][:4] == (
        "artifact",
        "knowledgeops-v1",
        "info",
        "research_x.memory.participation",
    )
    assert "artifact-evidence" in metadata["artifact-evidence"][4]


def test_rebuild_participation_decisions_is_idempotent(tmp_path: Path) -> None:
    db_path = tmp_path / "x.sqlite3"
    _seed_participation_subjects(db_path)

    rebuild_participation_decisions(db_path, output_modes=("explore", "answer"))
    rebuild_participation_decisions(db_path, output_modes=("explore", "answer"))

    with sqlite3.connect(db_path) as conn:
        count = conn.execute(
            "SELECT COUNT(*) FROM memory_participation_decisions"
        ).fetchone()[0]

    assert count == 6


def test_search_results_include_db_participation_decisions(tmp_path: Path) -> None:
    db_path = tmp_path / "x.sqlite3"
    _seed_search_participation_subjects(db_path)

    results = search_memory(db_path, "policy", limit=10)
    by_ref = {result.source_refs[0]: result for result in results}

    assert by_ref["x:tweet:blocked"].participation_snapshot["policy_source"] == (
        "memory_participation_decisions"
    )
    assert by_ref["x:tweet:blocked"].participation_snapshot[
        "can_use_in_working_note"
    ] is False
    assert by_ref["x:tweet:allowed"].participation_snapshot[
        "can_use_in_working_note"
    ] is True

    output = search_results_tool_output_v2(
        query="policy",
        results=results,
        output_mode="working_note",
        working_note_id="note-1",
    )

    assert [item.source_refs[0] for item in output.items] == ["x:tweet:allowed"]
    assert output.trace["mode_aware_search"]["participation_filtered_count"] == 1


def _seed_participation_subjects(db_path: Path) -> None:
    with sqlite3.connect(db_path) as conn:
        ensure_memory_schema(conn)
        conn.execute(
            """
            INSERT INTO memory_sources (
                source_ref, source_kind, source_uri, source_title, source_owner,
                raw_hash, normalized_content_hash, relation_hash, media_hash,
                source_status, visibility, first_observed_at, last_observed_at,
                updated_at, metadata_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "x:tweet:tweet-1",
                "tweet",
                "https://x.example/status/tweet-1",
                "tweet",
                "author",
                "raw",
                "normalized",
                None,
                None,
                "available",
                "private",
                "2026-07-03T00:00:00Z",
                "2026-07-03T00:00:00Z",
                "2026-07-03T00:00:00Z",
                "{}",
            ),
        )

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
                "artifact-working-note",
                "working_note",
                "memory_working_note",
                '["x:tweet:tweet-1"]',
                "note-hash",
                "candidate",
                "working_note",
                "task",
                "active",
                "2026-07-03T00:00:00Z",
                "2026-07-03T00:00:00Z",
                "{}",
            ),
        )
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
                "artifact-evidence",
                "evidence_view",
                "memory_citation_annotation",
                '["x:tweet:tweet-1"]',
                "citation-hash",
                "claim_supported",
                "evidence_package",
                "evidence_lineage",
                "active",
                "2026-07-03T00:00:00Z",
                "2026-07-03T00:00:00Z",
                "{}",
            ),
        )


def _seed_search_participation_subjects(db_path: Path) -> None:
    now = "2026-07-04T00:00:00Z"
    docs = (
        ("doc-blocked", "x:tweet:blocked", "blocked policy note", False),
        ("doc-allowed", "x:tweet:allowed", "allowed policy note", True),
    )
    with sqlite3.connect(db_path) as conn:
        ensure_memory_schema(conn)
        for doc_id, source_ref, body, can_working_note in docs:
            conn.execute(
                """
                INSERT INTO memory_sources (
                    source_ref, source_kind, source_uri, source_title, source_owner,
                    raw_hash, normalized_content_hash, source_status, visibility,
                    first_observed_at, last_observed_at, updated_at, metadata_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    source_ref,
                    "x_tweet",
                    f"https://x.example/{source_ref}",
                    body,
                    "tester",
                    f"raw-{doc_id}",
                    f"norm-{doc_id}",
                    "available",
                    "private",
                    now,
                    now,
                    now,
                    "{}",
                ),
            )
            conn.execute(
                """
                INSERT INTO memory_documents (
                    doc_id, doc_type, source_tweet_id, account_id, author_screen_name,
                    title, body, compact_text, metadata_json, source_refs_json,
                    created_at, observed_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    doc_id,
                    "tweet_doc",
                    source_ref.removeprefix("x:tweet:"),
                    "acct",
                    "tester",
                    body,
                    body,
                    body,
                    "{}",
                    json.dumps([source_ref]),
                    now,
                    now,
                    now,
                ),
            )
            conn.execute(
                """
                INSERT INTO memory_document_fts (
                    doc_id, title, body, compact_text, author_screen_name, metadata_json
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (doc_id, body, body, body, "tester", "{}"),
            )
            conn.execute(
                """
                INSERT INTO memory_participation_decisions (
                    decision_id, subject_kind, source_ref, artifact_id, output_mode,
                    policy_version, severity, can_search, can_explore,
                    can_use_in_working_note, can_use_as_evidence, can_use_in_answer,
                    can_trigger_external_fetch, reason, decided_by, decided_at,
                    input_hash_json, metadata_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    f"decision-{doc_id}",
                    "source",
                    source_ref,
                    None,
                    "working_note",
                    "knowledgeops-v1",
                    "info",
                    1,
                    0,
                    int(can_working_note),
                    1,
                    0,
                    0,
                    "source_available" if can_working_note else "working_note_blocked",
                    "test",
                    now,
                    "{}",
                    "{}",
                ),
            )
