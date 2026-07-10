from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from test_embedding_input_taxonomy import _seed_taxonomy_db

from research_x.memory.embedding_input import (
    build_embedding_projections,
    classify_embedding_inputs,
    old_embedding_lineage_report,
    quarantine_legacy_embedding_lineage,
)
from research_x.memory.embeddings import (
    build_memory_embeddings,
    estimate_memory_embedding_build,
)


def test_embedding_projection_dry_run_does_not_mutate_db(tmp_path: Path) -> None:
    db_path = tmp_path / "projection-dry-run.sqlite3"
    _seed_taxonomy_db(db_path)

    coverage = build_embedding_projections(
        db_path,
        write=False,
        report_dir=tmp_path / "reports",
    )

    assert coverage["total_classified_documents"] == 8
    assert coverage["embedding_eligible_documents"] == 6
    assert coverage["active_projections"] >= 6
    assert coverage["documents_without_required_projection"] == []
    with sqlite3.connect(db_path) as conn:
        taxonomy_count = conn.execute(
            "SELECT COUNT(*) FROM memory_document_taxonomy"
        ).fetchone()[0]
        projection_count = conn.execute(
            "SELECT COUNT(*) FROM memory_embedding_projections"
        ).fetchone()[0]
    assert taxonomy_count == 0
    assert projection_count == 0


def test_projection_rows_feed_embedding_estimate_and_local_hash_build(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "projection-build.sqlite3"
    _seed_taxonomy_db(db_path)
    classify_embedding_inputs(db_path, write=True, report_dir=tmp_path / "reports")
    build_embedding_projections(db_path, write=True, report_dir=tmp_path / "reports")

    estimate = estimate_memory_embedding_build(
        db_path,
        provider="local_hash",
        dimensions=32,
        projection_profile="general_memory",
        require_projections=True,
    )
    summary = build_memory_embeddings(
        db_path,
        provider="local_hash",
        dimensions=32,
        projection_profile="general_memory",
        require_projections=True,
    )

    assert estimate.uses_projection_rows is True
    assert estimate.selected_projections == 3
    assert estimate.provider_requests_made == 0
    assert summary.uses_projection_rows is True
    assert summary.embedded == estimate.selected_projections
    assert summary.provider_requests_made == 0
    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            """
            SELECT COUNT(*), COUNT(projection_id), COUNT(classification_version)
            FROM memory_embeddings
            WHERE stale_status = 'current'
            """
        ).fetchone()
    assert row == (summary.embedded, summary.embedded, summary.embedded)
    assert old_embedding_lineage_report(db_path)["status"] == "lineage_complete"


def test_raw_eval_or_production_embedding_requires_projection_rows(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "raw-eval-block.sqlite3"
    _seed_taxonomy_db(db_path)

    with pytest.raises(RuntimeError, match="require memory_embedding_projections"):
        estimate_memory_embedding_build(
            db_path,
            provider="gemini",
            dimensions=768,
            limit=3,
            execution_stage="eval-slice",
        )
    with pytest.raises(RuntimeError, match="require memory_embedding_projections"):
        build_memory_embeddings(
            db_path,
            provider="local_hash",
            dimensions=32,
            execution_stage="production-scope",
        )


def test_legacy_embedding_rows_can_be_quarantined_from_readiness(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "legacy-quarantine.sqlite3"
    _seed_taxonomy_db(db_path)
    build_memory_embeddings(db_path, provider="local_hash", dimensions=32)

    before = old_embedding_lineage_report(db_path)
    quarantine = quarantine_legacy_embedding_lineage(db_path)
    after = old_embedding_lineage_report(db_path)

    assert before["status"] == "blocked_existing_embeddings_without_projection_lineage"
    assert quarantine["quarantined_rows"] == before["current_without_projection_id"]
    assert after["status"] == "lineage_complete"
    assert after["quarantined_without_projection_id"] == before["without_projection_id"]
