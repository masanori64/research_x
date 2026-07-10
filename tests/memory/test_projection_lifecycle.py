from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from research_x.memory.embeddings import build_memory_embeddings
from research_x.memory.projection_lifecycle import (
    build_projection_lifecycle,
    plan_projection_lifecycle,
    projection_lifecycle_rows,
    register_projection_lifecycle,
)
from research_x.memory.schema import ensure_memory_schema

CANON_ITEMS = ("P6", "L5")
PURPOSE = "Projection lifecycle separates dry-run, registration-only, and local build dispatch."
pytestmark = [pytest.mark.canon(item) for item in CANON_ITEMS]


def test_projection_lifecycle_plan_is_dry_run(tmp_path: Path) -> None:
    db_path = tmp_path / "memory.sqlite3"
    _seed_projection_generation(db_path)
    before = _projection_counts(db_path)

    plan = plan_projection_lifecycle(db_path)
    after = _projection_counts(db_path)

    assert plan.status == "needs_build"
    assert plan.build_plan is not None
    assert plan.build_plan.build_semantics == "lifecycle_registration_only"
    assert plan.actions[2]["action"] == "projection_build_plan"
    assert before == after


def test_registration_only_creates_projection_artifact_and_audit(tmp_path: Path) -> None:
    db_path = tmp_path / "memory.sqlite3"
    _seed_projection_generation(db_path)

    summary = register_projection_lifecycle(db_path)

    assert summary.status == "ok"
    assert summary.build_plan is not None
    assert summary.build_plan.build_semantics == "lifecycle_registration_only"
    assert summary.projections_registered == 1

    rows = projection_lifecycle_rows(db_path)
    assert rows[0]["projection_id"] == "projection:generation-1"
    with sqlite3.connect(db_path) as conn:
        artifact = conn.execute(
            """
            SELECT artifact_role, authority_level, output_mode
            FROM memory_artifacts
            WHERE artifact_id = 'projection:generation-1'
            """
        ).fetchone()
        audit_count = conn.execute(
            """
            SELECT COUNT(*)
            FROM memory_audit_events
            WHERE event_type = 'projection_lifecycle_registered'
            """
        ).fetchone()[0]

    assert artifact == ("projection", "candidate", "explore")
    assert audit_count == 1


def test_local_vector_builder_dispatch_writes_projection_index_and_audit(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "memory.sqlite3"
    _seed_embedding_documents(db_path)
    build_memory_embeddings(db_path, provider="local_hash", dimensions=64)

    summary = build_projection_lifecycle(
        db_path,
        mode="full",
        projection_kind="local_vector_projection",
        builder_params={
            "provider": "local_hash",
            "dimensions": 64,
            "backend": "numpy",
            "out_dir": str(tmp_path / "vector-indexes"),
        },
    )

    assert summary.status == "ok"
    assert summary.builder_dispatches[0]["status"] == "built"
    assert summary.build_plan is not None
    assert summary.build_plan.build_semantics == "local_vector_builder_dispatch"
    assert summary.build_plan.builder_call_path == (
        "research_x.memory.vector_projection.build_vector_projection"
    )
    with sqlite3.connect(db_path) as conn:
        counts = {
            "memory_projection_generations": conn.execute(
                "SELECT COUNT(*) FROM memory_projection_generations"
            ).fetchone()[0],
            "memory_index_membership": conn.execute(
                "SELECT COUNT(*) FROM memory_index_membership"
            ).fetchone()[0],
            "memory_projection_artifacts": conn.execute(
                "SELECT COUNT(*) FROM memory_projection_artifacts"
            ).fetchone()[0],
        }
        projection_kinds = {
            row[0]
            for row in conn.execute(
                "SELECT projection_kind FROM memory_projection_artifacts"
            )
        }
        audit_events = {
            row[0]
            for row in conn.execute(
                """
                SELECT event_type
                FROM memory_audit_events
                WHERE event_type IN (
                  'projection_build_orchestrated',
                  'projection_built'
                )
                """
            )
        }

    assert counts["memory_projection_generations"] >= 1
    assert counts["memory_index_membership"] == 2
    assert counts["memory_projection_artifacts"] == 2
    assert projection_kinds == {
        "embedding_input_projection",
        "local_vector_projection",
    }
    assert audit_events == {"projection_build_orchestrated", "projection_built"}


def _seed_projection_generation(db_path: Path) -> None:
    with sqlite3.connect(db_path) as conn:
        ensure_memory_schema(conn)
        conn.execute(
            """
            INSERT INTO memory_documents (
                doc_id, doc_type, source_tweet_id, title, body, compact_text,
                metadata_json, source_doc_hash, embedding_text_hash,
                created_at, observed_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "doc-1",
                "tweet",
                "tweet-1",
                "Projection source",
                "projection text",
                "projection text",
                "{}",
                "source-hash-1",
                "embedding-text-hash-1",
                "2026-07-03T00:00:00Z",
                "2026-07-03T00:00:00Z",
                "2026-07-03T00:00:00Z",
            ),
        )
        conn.execute(
            """
            INSERT INTO memory_projection_generations (
                generation_id, projection_kind, source_scope, builder_version,
                input_manifest_json, status, coverage_json, created_at,
                metadata_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "generation-1",
                "local_vector_projection",
                "memory_documents",
                "local-vector-projection-v1",
                '{"documents":1}',
                "current",
                '{"documents":1,"current":1,"stale":0}',
                "2026-07-03T00:00:00Z",
                '{"index_path":"index.npz","mapping_path":"mapping.json"}',
            ),
        )
        conn.execute(
            """
            INSERT INTO memory_index_membership (
                membership_id, generation_id, artifact_kind, artifact_id,
                source_id, source_hash, membership_status, created_at,
                metadata_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "membership-1",
                "generation-1",
                "memory_document_embedding",
                "vector:1",
                "doc-1",
                "source-hash-1",
                "current",
                "2026-07-03T00:00:00Z",
                '{"vector_id":1}',
            ),
        )


def _seed_embedding_documents(db_path: Path) -> None:
    with sqlite3.connect(db_path) as conn:
        ensure_memory_schema(conn)
        conn.executemany(
            """
            INSERT INTO memory_documents (
                doc_id, doc_type, source_tweet_id, title, body, compact_text,
                metadata_json, source_doc_hash, embedding_text_hash,
                created_at, observed_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                (
                    "doc-1",
                    "tweet",
                    "tweet-1",
                    "Robot paper",
                    "robot paper projection text",
                    "robot paper projection text",
                    "{}",
                    None,
                    None,
                    "2026-07-03T00:00:00Z",
                    "2026-07-03T00:00:00Z",
                    "2026-07-03T00:00:00Z",
                ),
                (
                    "doc-2",
                    "tweet",
                    "tweet-2",
                    "Memory search",
                    "memory search projection text",
                    "memory search projection text",
                    "{}",
                    None,
                    None,
                    "2026-07-03T00:00:00Z",
                    "2026-07-03T00:00:00Z",
                    "2026-07-03T00:00:00Z",
                ),
            ),
        )


def _projection_counts(db_path: Path) -> dict[str, int]:
    with sqlite3.connect(db_path) as conn:
        return {
            table: int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
            for table in (
                "memory_projection_generations",
                "memory_index_membership",
                "memory_projection_artifacts",
                "memory_artifacts",
                "memory_audit_events",
            )
        }
