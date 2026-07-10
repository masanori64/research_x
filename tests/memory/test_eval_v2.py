from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from research_x.memory.evals_v2 import (
    EvalCaseV2,
    _metric_values,
    eval_case_v2_from_dict,
    load_eval_cases_v2,
    metrics_for_output_mode,
    run_eval_cases_v2,
    validate_eval_case_v2,
)
from research_x.memory.schema import ensure_memory_schema

CANON_ITEMS = ("P12", "L4")
PURPOSE = "Eval v2 records mode metrics and diagnostic fake/local output without promotion."
pytestmark = [pytest.mark.canon(item) for item in CANON_ITEMS]


def test_eval_v2_loads_mode_specific_case_fields(tmp_path: Path) -> None:
    cases_path = tmp_path / "cases.jsonl"
    cases_path.write_text(json.dumps(_case().as_dict(), sort_keys=True) + "\n", encoding="utf-8")

    cases = load_eval_cases_v2(cases_path)

    assert len(cases) == 1
    assert cases[0].output_mode == "explore"
    assert cases[0].expected_artifact_roles == ("projection",)
    assert validate_eval_case_v2(cases[0]) == []


def test_eval_v2_validation_and_metrics_are_mode_specific() -> None:
    answer_case = _case(
        output_mode="answer",
        expected_artifact_roles=("evidence_view",),
        expected_authority_level="claim_supported",
    )
    evidence_case = _case(
        output_mode="evidence_package",
        expected_artifact_roles=("projection",),
        expected_authority_level="candidate",
    )

    assert any(
        "answer eval requires answer_assertion" in error
        for error in validate_eval_case_v2(answer_case)
    )
    assert any(
        "evidence_package eval requires evidence_view" in error
        for error in validate_eval_case_v2(evidence_case)
    )
    assert "negative_hit_rate" in metrics_for_output_mode("explore")
    assert "answer_assertion_support_rate" in metrics_for_output_mode("answer")


def test_eval_v2_explore_metrics_penalize_negative_hits() -> None:
    case = _case(
        expected_source_refs=("x:tweet:expected",),
        negative_source_refs=("x:tweet:bad",),
    )

    metrics = _metric_values(
        case,
        (
            {"source_ref": "x:tweet:expected", "artifact_role": "projection", "score": 1.0},
            {"source_ref": "x:tweet:bad", "artifact_role": "projection", "score": 0.5},
        ),
    )

    assert metrics["expected_source_recall_at_k"] == 1.0
    assert metrics["negative_hit_rate"] == 1.0


def test_eval_v2_fake_local_answer_is_diagnostic_only_and_does_not_promote_route(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "memory.sqlite3"
    cases_path = tmp_path / "cases.jsonl"
    _seed_evidence_view(db_path)
    cases_path.write_text(
        json.dumps(
            _case(
                query="robot",
                output_mode="answer",
                expected_source_refs=("x:tweet:tweet-1",),
                expected_artifact_roles=("evidence_view",),
                expected_authority_level="answer_assertion",
            ).as_dict(),
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    summary = run_eval_cases_v2(
        db_path,
        cases_path=cases_path,
        run_id="eval-run-answer",
        started_at="2026-07-03T00:00:00Z",
    )

    assert summary.status == "ok"
    with sqlite3.connect(db_path) as conn:
        metadata = json.loads(
            conn.execute(
                """
                SELECT metadata_json
                FROM memory_eval_results
                WHERE run_id = 'eval-run-answer'
                """
            ).fetchone()[0]
        )
        route_promotion_count = conn.execute(
            "SELECT COUNT(*) FROM memory_route_promotion_decisions"
        ).fetchone()[0]

    assert metadata["strict_output_status"] == "passed"
    assert metadata["output"]["trace"]["eval_v2_answer_provider"] == "fake_local_answer_provider"
    assert metadata["output"]["trace"]["diagnostic_only"] is True
    assert metadata["output"]["trace"]["eval_v2_answer_quality_proof"] is False
    assert route_promotion_count == 0


def test_eval_v2_smoke_can_need_review_without_failing_whole_run(tmp_path: Path) -> None:
    db_path = tmp_path / "memory.sqlite3"
    cases_path = tmp_path / "cases.jsonl"
    _seed_memory_document(db_path)
    cases = [
        _case(case_id="ok-case", query="robot", expected_source_refs=("x:tweet:tweet-1",)),
        _case(case_id="review-case", query="", expected_source_refs=()),
    ]
    cases_path.write_text(
        "".join(json.dumps(case.as_dict(), sort_keys=True) + "\n" for case in cases),
        encoding="utf-8",
    )

    summary = run_eval_cases_v2(
        db_path,
        cases_path=cases_path,
        run_id="eval-smoke",
        started_at="2026-07-03T00:00:00Z",
    )

    assert summary.case_count == 2
    assert summary.ok_count == 1
    assert summary.needs_review_count == 1
    assert summary.fail_count == 0


def _case(**overrides: object) -> EvalCaseV2:
    payload = {
        "case_id": "case-1",
        "query": "robot",
        "output_mode": "explore",
        "objective": "find candidates",
        "source_scope": "x",
        "expected_source_refs": ["x:tweet:1"],
        "acceptable_source_refs": [],
        "negative_source_refs": [],
        "expected_artifact_roles": ["projection"],
        "expected_authority_level": "candidate",
        "required_relation_types": [],
        "provider_policy": "no_real_provider_calls",
        "context_budget": 1000,
        "noise_budget": 0.1,
        "expected_status": "ok",
        "notes": "",
    }
    payload.update(overrides)
    return eval_case_v2_from_dict(payload)


def _seed_memory_document(db_path: Path) -> None:
    with sqlite3.connect(db_path) as conn:
        ensure_memory_schema(conn)
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
                "doc-1",
                "tweet",
                "tweet-1",
                "account-1",
                "author",
                "Robot source",
                "robot evidence text",
                "robot evidence text",
                "{}",
                '["x:tweet:tweet-1"]',
                "2026-07-03T00:00:00Z",
                "2026-07-03T00:00:00Z",
                "2026-07-03T00:00:00Z",
            ),
        )


def _seed_evidence_view(db_path: Path) -> None:
    with sqlite3.connect(db_path) as conn:
        ensure_memory_schema(conn)
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
                "evidence-view:robot-1",
                "evidence_view",
                "memory_citation_annotation",
                '["x:tweet:tweet-1"]',
                "hash-evidence-view",
                "evidence_view",
                "evidence_package",
                "test",
                "active",
                "2026-07-03T00:00:00Z",
                "2026-07-03T00:00:00Z",
                "{}",
            ),
        )
