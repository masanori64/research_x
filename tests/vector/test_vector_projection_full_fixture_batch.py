from __future__ import annotations

import sqlite3
from pathlib import Path

from research_x.memory.embeddings import build_memory_embeddings
from research_x.memory.vector_projection import (
    VectorBackendBenchmarkThresholds,
    benchmark_vector_backends,
    build_vector_projection,
    vector_projection_coverage,
)


def test_local_hash_projection_batch_is_ok_but_diagnostic_only(
    vector_db_path: Path,
    tmp_path: Path,
) -> None:
    build_memory_embeddings(vector_db_path, provider="local_hash", dimensions=32)
    summary = build_vector_projection(
        vector_db_path,
        provider="local_hash",
        dimensions=32,
        out_dir=tmp_path / "vector-projection",
    )

    coverage = vector_projection_coverage(
        vector_db_path,
        generation_id=summary.generation_id,
    )
    benchmark = benchmark_vector_backends(
        vector_db_path,
        provider="local_hash",
        dimensions=32,
        backends=("numpy",),
        queries=("robot paper",),
        out_dir=tmp_path / "vector-benchmark",
    )

    assert coverage.status == "ok"
    assert coverage.current_memberships == coverage.expected_documents
    assert coverage.stale_memberships == 0
    assert coverage.missing_memberships == 0
    assert coverage.index_exists is True
    assert benchmark.metadata["diagnostic_only"] is True
    assert benchmark.metadata["production_eligible"] is False
    assert benchmark.metadata["evidence_role"] == "retrieval_candidate_signal"
    assert benchmark.metadata["answer_support_allowed"] is False


def test_vector_projection_missing_membership_is_stale(
    vector_db_path: Path,
    tmp_path: Path,
) -> None:
    build_memory_embeddings(vector_db_path, provider="local_hash", dimensions=32)
    summary = build_vector_projection(
        vector_db_path,
        provider="local_hash",
        dimensions=32,
        out_dir=tmp_path / "vector-projection",
    )
    with sqlite3.connect(vector_db_path) as conn:
        conn.execute(
            """
            DELETE FROM memory_index_membership
            WHERE generation_id = ?
              AND source_id = (
                  SELECT source_id
                  FROM memory_index_membership
                  WHERE generation_id = ?
                  ORDER BY source_id
                  LIMIT 1
              )
            """,
            (summary.generation_id, summary.generation_id),
        )

    coverage = vector_projection_coverage(
        vector_db_path,
        generation_id=summary.generation_id,
    )

    assert coverage.status == "stale"
    assert coverage.missing_memberships == 1
    assert coverage.current_memberships == coverage.expected_documents - 1


def test_vector_backend_cold_start_threshold_marks_needs_review(
    vector_db_path: Path,
    tmp_path: Path,
) -> None:
    build_memory_embeddings(vector_db_path, provider="local_hash", dimensions=32)

    report = benchmark_vector_backends(
        vector_db_path,
        provider="local_hash",
        dimensions=32,
        backends=("numpy",),
        queries=("robot paper",),
        out_dir=tmp_path / "vector-benchmark",
        thresholds=VectorBackendBenchmarkThresholds(max_cold_start_seconds=0.0),
    )

    assert report.status == "needs_review"
    assert report.results[0].status == "needs_review"
    assert "cold_start_seconds_exceeds_threshold" in report.results[0].notes
