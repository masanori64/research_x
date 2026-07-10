from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from research_x.memory.evidence_package import (
    build_citation_candidate,
    build_context_chunk,
    build_evidence_package_output,
    candidate_to_evidence_view,
    promote_candidate_to_evidence_package,
    promote_evidence_package_to_answer,
    validate_role,
    validate_source_restore,
    validate_staleness,
)
from research_x.memory.schema import ensure_memory_schema
from research_x.tool_interface.memory_tool_contract import validate_tool_output_v2

CANON_ITEMS = ("P9", "L6")
PURPOSE = "Evidence packages require restorable evidence views and cannot assert answers."
pytestmark = [pytest.mark.canon(item) for item in CANON_ITEMS]


def test_build_evidence_package_output_accepts_evidence_view(tmp_path: Path) -> None:
    db_path = tmp_path / "x.sqlite3"
    _seed_evidence_artifacts(db_path)

    output = build_evidence_package_output(
        db_path,
        query="package evidence",
        artifact_ids=("citation:citation-1",),
    )

    assert output.output_mode == "evidence_package"
    assert output.answer_text is None
    assert output.items[0].artifact_role == "evidence_view"
    assert output.items[0].authority_level == "evidence_view"
    assert output.trace["citation_candidates"] == [
        {
            "artifact_id": "citation:citation-1",
            "chunk_id": "citation:citation-1",
            "citation_id": "citation:citation-1",
            "restore": {
                "artifact_id": "citation:citation-1",
                "lineage_status": "restored",
            },
            "source_id": "citation:citation-1",
            "source_kind": "memory_artifact",
            "source_refs": ["x:tweet:tweet-1"],
            "status": "candidate",
        }
    ]
    assert validate_tool_output_v2(output) == []


def test_build_evidence_package_output_rejects_projection(tmp_path: Path) -> None:
    db_path = tmp_path / "x.sqlite3"
    _seed_evidence_artifacts(db_path)

    with pytest.raises(ValueError, match="accepts only evidence_view"):
        build_evidence_package_output(
            db_path,
            query="package evidence",
            artifact_ids=("memory_document:doc-1",),
        )


def test_build_evidence_package_output_rejects_participation_blocked_artifact(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "x.sqlite3"
    _seed_evidence_artifacts(db_path)
    with sqlite3.connect(db_path) as conn:
        _insert_participation_decision(
            conn,
            artifact_id="citation:citation-1",
            output_mode="evidence_package",
            can_use_as_evidence=False,
            can_use_in_answer=False,
        )

    with pytest.raises(ValueError, match="participation policy blocks evidence package"):
        build_evidence_package_output(
            db_path,
            query="package evidence",
            artifact_ids=("citation:citation-1",),
        )


def test_build_evidence_package_output_rejects_answer_assertion_authority(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "x.sqlite3"
    _seed_evidence_artifacts(db_path)
    with sqlite3.connect(db_path) as conn:
        _insert_artifact(
            conn,
            artifact_id="evidence-view:answer-assertion",
            artifact_role="evidence_view",
            artifact_kind="memory_citation_annotation",
            authority_level="answer_assertion",
            output_mode="answer",
        )

    with pytest.raises(ValueError, match="accepts only evidence_view"):
        build_evidence_package_output(
            db_path,
            query="package evidence",
            artifact_ids=("evidence-view:answer-assertion",),
        )


def test_promote_evidence_package_to_answer_persists_claim_support(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "x.sqlite3"
    _seed_evidence_artifacts(db_path)
    package = build_evidence_package_output(
        db_path,
        query="package evidence",
        artifact_ids=("citation:citation-1",),
    )

    answer = promote_evidence_package_to_answer(
        db_path,
        evidence_package=package,
        answer_text="Supported answer.",
        claims=(
            {
                "claim_id": "claim-1",
                "claim_text": "Supported answer.",
                "citation_ids": ["citation:citation-1"],
            },
        ),
        output_run_id="answer-run-1",
        created_at="2026-07-03T00:00:00Z",
    )

    assert answer.output_mode == "answer"
    assert answer.status == "answer"
    assert answer.items[0].authority_level == "answer_assertion"
    assert answer.claim_support == {
        "status": "supported",
        "claims": [
            {
                "claim_id": "claim-1",
                "claim_text": "Supported answer.",
                "support_status": "supported",
                "support_score": 1.0,
                "citation_ids": ["citation:citation-1"],
            }
        ],
    }
    assert answer.trace["db_backed_validation"]["status"] == "passed"
    assert validate_tool_output_v2(answer) == []

    with sqlite3.connect(db_path) as conn:
        output_run = conn.execute(
            """
            SELECT output_mode, status
            FROM memory_output_runs
            WHERE output_run_id = 'answer-run-1'
            """
        ).fetchone()
        item = conn.execute(
            """
            SELECT artifact_role, authority_level
            FROM memory_output_items
            WHERE output_run_id = 'answer-run-1'
            """
        ).fetchone()
        assessment = conn.execute(
            """
            SELECT claim_id, citation_id, support_status, support_score
            FROM memory_claim_support_assessments
            WHERE output_run_id = 'answer-run-1'
            """
        ).fetchone()

    assert output_run == ("answer", "answer")
    assert item == ("evidence_view", "answer_assertion")
    assert assessment == ("claim-1", "citation:citation-1", "supported", 1.0)


def test_promote_evidence_package_to_answer_rejects_unknown_citation(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "x.sqlite3"
    _seed_evidence_artifacts(db_path)
    package = build_evidence_package_output(
        db_path,
        query="package evidence",
        artifact_ids=("citation:citation-1",),
    )

    with pytest.raises(ValueError, match="unknown citations"):
        promote_evidence_package_to_answer(
            db_path,
            evidence_package=package,
            answer_text="Unsupported answer.",
            claims=(
                {
                    "claim_id": "claim-1",
                    "claim_text": "Unsupported answer.",
                    "citation_ids": ["missing-citation"],
                },
            ),
        )


def test_promote_evidence_package_to_answer_rejects_participation_blocked_answer(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "x.sqlite3"
    _seed_evidence_artifacts(db_path)
    package = build_evidence_package_output(
        db_path,
        query="package evidence",
        artifact_ids=("citation:citation-1",),
    )
    with sqlite3.connect(db_path) as conn:
        _insert_participation_decision(
            conn,
            artifact_id="citation:citation-1",
            output_mode="answer",
            can_use_as_evidence=True,
            can_use_in_answer=False,
        )

    with pytest.raises(ValueError, match="participation policy blocks answer"):
        promote_evidence_package_to_answer(
            db_path,
            evidence_package=package,
            answer_text="Supported answer.",
            claims=(
                {
                    "claim_id": "claim-1",
                    "claim_text": "Supported answer.",
                    "citation_ids": ["citation:citation-1"],
                },
            ),
        )


def test_promote_evidence_package_to_answer_rejects_unsupported_claim(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "x.sqlite3"
    _seed_evidence_artifacts(db_path)
    package = build_evidence_package_output(
        db_path,
        query="package evidence",
        artifact_ids=("citation:citation-1",),
    )

    with pytest.raises(ValueError, match="unsupported claims"):
        promote_evidence_package_to_answer(
            db_path,
            evidence_package=package,
            answer_text="Unsupported answer.",
            claims=(
                {
                    "claim_id": "claim-1",
                    "claim_text": "Unsupported answer.",
                    "support_status": "unsupported",
                    "citation_ids": ["citation:citation-1"],
                },
            ),
        )


def test_evidence_boundary_helpers_require_restore_and_valid_role() -> None:
    candidate = {
        "source_ref": "x:tweet:tweet-1",
        "restore_path": {"table": "tweets", "tweet_id": "tweet-1"},
        "context_range": {"start": 0, "end": 10},
        "artifact_status": "active",
    }

    evidence_view = candidate_to_evidence_view(candidate)
    chunk = build_context_chunk(
        source_ref="x:tweet:tweet-1",
        chunk_id="chunk-1",
        text="source text",
        restore_path={"table": "tweets", "tweet_id": "tweet-1"},
    )
    citation = build_citation_candidate(
        artifact_id="citation:citation-1",
        source_ref="x:tweet:tweet-1",
        chunk_id="chunk-1",
    )

    assert validate_source_restore(candidate)
    assert validate_staleness(candidate) == "active"
    assert evidence_view["artifact_role"] == "evidence_view"
    assert chunk["restore_path"]["tweet_id"] == "tweet-1"
    assert citation["status"] == "candidate"
    assert validate_role(artifact_role="evidence_view", authority_level="evidence_view")
    assert validate_role(artifact_role="evidence_view", authority_level="claim_supported")
    assert not validate_role(
        artifact_role="evidence_view",
        authority_level="answer_assertion",
    )
    assert not validate_role(artifact_role="projection", authority_level="source_backed")


def test_evidence_boundary_helpers_reject_missing_restore_or_stale_candidate() -> None:
    with pytest.raises(ValueError, match="source_ref"):
        candidate_to_evidence_view(
            {
                "restore_path": {"table": "tweets"},
                "context_range": {"chunk_id": "chunk-1", "start": 0, "end": 10},
            }
        )
    with pytest.raises(ValueError, match="source restore"):
        candidate_to_evidence_view({"source_ref": "x:tweet:tweet-1"})
    with pytest.raises(ValueError, match="context range"):
        candidate_to_evidence_view(
            {
                "source_ref": "x:tweet:tweet-1",
                "restore_path": {"table": "tweets"},
            }
        )
    with pytest.raises(ValueError, match="stale"):
        candidate_to_evidence_view(
            {
                "source_ref": "x:tweet:tweet-1",
                "restore_path": {"table": "tweets"},
                "context_range": {"chunk_id": "chunk-1", "start": 0, "end": 10},
                "artifact_status": "stale",
            }
        )


def test_promote_candidate_to_evidence_package_creates_citation_candidate(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "x.sqlite3"
    candidate = {
        "source_ref": "x:tweet:tweet-1",
        "restore_path": {"table": "tweets", "tweet_id": "tweet-1"},
        "context_range": {"chunk_id": "chunk-1", "start": 0, "end": 20},
        "artifact_status": "active",
        "confidence": 0.8,
    }

    package = promote_candidate_to_evidence_package(
        db_path,
        query="package candidate",
        candidate=candidate,
        artifact_id="evidence-view:candidate-1",
        created_at="2026-07-03T00:00:00Z",
    )

    assert package.output_mode == "evidence_package"
    assert package.items[0].artifact_role == "evidence_view"
    assert package.trace["citation_candidates"][0]["citation_id"] == (
        "evidence-view:candidate-1"
    )
    assert package.trace["citation_candidates"][0]["chunk_id"] == "chunk-1"


def _seed_evidence_artifacts(db_path: Path) -> None:
    with sqlite3.connect(db_path) as conn:
        ensure_memory_schema(conn)
        _insert_artifact(
            conn,
            artifact_id="citation:citation-1",
            artifact_role="evidence_view",
            artifact_kind="memory_citation_annotation",
            authority_level="evidence_view",
            output_mode="evidence_package",
        )
        _insert_artifact(
            conn,
            artifact_id="memory_document:doc-1",
            artifact_role="projection",
            artifact_kind="memory_document",
            authority_level="source_backed",
            output_mode="explore",
        )


def _insert_artifact(
    conn: sqlite3.Connection,
    *,
    artifact_id: str,
    artifact_role: str,
    artifact_kind: str,
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
            artifact_kind,
            '["x:tweet:tweet-1"]',
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


def _insert_participation_decision(
    conn: sqlite3.Connection,
    *,
    artifact_id: str,
    output_mode: str,
    can_use_as_evidence: bool,
    can_use_in_answer: bool,
) -> None:
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
            f"decision:{artifact_id}:{output_mode}",
            "artifact",
            None,
            artifact_id,
            output_mode,
            "knowledgeops-v1",
            "warning",
            1,
            1,
            1,
            int(can_use_as_evidence),
            int(can_use_in_answer),
            0,
            "fixture_policy_block",
            "test",
            "2026-07-03T00:00:00Z",
            "{}",
            "{}",
        ),
    )
