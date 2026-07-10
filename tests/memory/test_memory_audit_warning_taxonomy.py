from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent))

from test_operational_trace_persistence import _seed_memory_db

from research_x.memory.answer import build_memory_answer
from research_x.memory.audit import audit_memory_db
from research_x.memory.corpus import build_memory_corpus
from research_x.memory.embeddings import build_memory_embeddings, pack_embedding
from research_x.memory.relations import build_memory_relations
from research_x.memory.schema import ensure_memory_schema


def test_audit_taxonomy_treats_local_hash_as_expected_provider_gate(
    tmp_path: Path,
) -> None:
    db_path = _seed_ready_memory_db(tmp_path)
    build_memory_embeddings(db_path, provider="local_hash", dimensions=64)

    report = audit_memory_db(db_path)
    warning = _warning_by_code(report.structured_warnings, "local_hash_diagnostic_only")

    assert warning["severity"] == "expected"
    assert warning["category"] == "provider_gated_expected"
    assert warning["blocking_for_local_no_provider"] is False
    assert warning["blocking_for_provider_production"] is True
    assert report.readiness["local_no_provider_ready"] is True
    assert report.readiness["provider_production_ready"] is False
    assert report.readiness["blocking_issue_count"] == 0
    assert report.readiness["expected_gated_warning_count"] >= 1


def test_audit_taxonomy_treats_provider_rows_as_policy_required(
    tmp_path: Path,
) -> None:
    db_path = _seed_ready_memory_db(tmp_path)
    _insert_provider_embedding_row(
        db_path,
        provider="openai_compatible",
        model="custom-embedding",
        dimensions=3,
    )

    report = audit_memory_db(db_path)
    warning = _warning_by_code(
        report.structured_warnings,
        "provider_embedding_rows_quarantined",
    )

    assert warning["severity"] == "expected"
    assert warning["category"] == "provider_gated_expected"
    assert warning["gate"] == "provider_execution_policy"
    assert warning["blocking_for_local_no_provider"] is False
    assert warning["blocking_for_provider_production"] is True
    assert report.readiness["local_no_provider_ready"] is True
    assert report.readiness["provider_production_ready"] is False
    assert report.readiness["blocking_issue_count"] == 0


def test_audit_accepts_legacy_failed_eval_run_status(tmp_path: Path) -> None:
    db_path = _seed_ready_memory_db(tmp_path)
    with sqlite3.connect(db_path) as conn:
        ensure_memory_schema(conn)
        conn.execute(
            """
            INSERT INTO memory_eval_runs (
                run_id, cases_path, case_count, parameters_json, status,
                ok_count, needs_review_count, fail_count, started_at, finished_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "legacy-failed-eval-run",
                None,
                1,
                "{}",
                "failed",
                0,
                0,
                1,
                "2026-07-04T00:00:00+00:00",
                "2026-07-04T00:00:00+00:00",
            ),
        )

    report = audit_memory_db(db_path)

    assert "memory_eval_runs.status" not in report.invalid_enums_by_field


def test_schema_migrates_legacy_projection_generations_before_space_index(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "legacy-projection.sqlite3"
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE memory_projection_generations (
                generation_id TEXT PRIMARY KEY,
                projection_kind TEXT NOT NULL,
                source_scope TEXT NOT NULL,
                builder_version TEXT NOT NULL,
                input_manifest_json TEXT NOT NULL,
                status TEXT NOT NULL,
                coverage_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                metadata_json TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            INSERT INTO memory_projection_generations (
                generation_id, projection_kind, source_scope, builder_version,
                input_manifest_json, status, coverage_json, created_at, metadata_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "legacy-generation",
                "embedding_input_projection",
                "memory_documents",
                "legacy",
                "{}",
                "current",
                "{}",
                "2026-07-04T00:00:00+00:00",
                "{}",
            ),
        )

    with sqlite3.connect(db_path) as conn:
        ensure_memory_schema(conn)
        columns = {
            row[1]
            for row in conn.execute("PRAGMA table_info(memory_projection_generations)")
        }
        indexes = {
            row[1]
            for row in conn.execute("PRAGMA index_list(memory_projection_generations)")
        }

    assert "space_id" in columns
    assert "idx_memory_projection_generations_space" in indexes


def test_audit_taxonomy_marks_claim_citation_issue_blocking(
    tmp_path: Path,
) -> None:
    db_path = _seed_ready_memory_db(tmp_path)
    answer = build_memory_answer(
        db_path,
        "強化学習 ロボット",
        limit=1,
        answer_provider="fake",
    )

    with sqlite3.connect(db_path) as conn:
        ensure_memory_schema(conn)
        conn.execute(
            """
            UPDATE memory_answer_runs
            SET answer_text = ?
            WHERE answer_id = ?
            """,
            (
                "根拠に基づく回答です [2]\n"
                "これは追加された確認不能な事実説明です。",
                answer.answer_id,
            ),
        )

    report = audit_memory_db(db_path)
    warning = _warning_by_code(report.structured_warnings, "claim_citation_issues")

    assert warning["severity"] == "warning"
    assert warning["category"] == "blocking_issue"
    assert warning["gate"] == "citation_integrity"
    assert warning["blocking_for_local_no_provider"] is True
    assert warning["blocking_for_provider_production"] is True
    assert report.readiness["local_no_provider_ready"] is False
    assert report.readiness["provider_production_ready"] is False
    assert report.readiness["blocking_issue_count"] >= 1


def _seed_ready_memory_db(tmp_path: Path) -> Path:
    db_path = _seed_memory_db(tmp_path)
    build_memory_corpus(db_path)
    build_memory_relations(db_path)
    return db_path


def _warning_by_code(
    warnings: tuple[dict[str, object], ...],
    code: str,
) -> dict[str, object]:
    for warning in warnings:
        if warning["code"] == code:
            return warning
    raise AssertionError(f"missing warning code: {code}; got {[item['code'] for item in warnings]}")


def _insert_provider_embedding_row(
    db_path: Path,
    *,
    provider: str,
    model: str,
    dimensions: int,
) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        ensure_memory_schema(conn)
        row = conn.execute(
            """
            SELECT doc_id, source_doc_hash, embedding_text_hash
            FROM memory_documents
            ORDER BY doc_id
            LIMIT 1
            """
        ).fetchone()
        assert row is not None
        now = "2026-06-27T00:00:00+00:00"
        conn.execute(
            """
            INSERT INTO memory_embeddings (
                doc_id, provider, model, dimensions, embedding_profile,
                text_template_version, embedding, source_doc_hash,
                embedded_text_hash, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                row["doc_id"],
                provider,
                model,
                dimensions,
                "general_memory",
                "memory-doc-embedding-v1",
                pack_embedding(_fixture_embedding(dimensions)),
                row["source_doc_hash"],
                row["embedding_text_hash"],
                now,
                now,
            ),
        )


def _fixture_embedding(dimensions: int) -> list[float]:
    vector = [0.0] * dimensions
    vector[0] = 1.0
    return vector
