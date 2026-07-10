from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from research_x.memory.schema import ensure_memory_schema

CANON_ITEMS = ("P2", "L1", "L2")
PURPOSE = "Schema migration is idempotent and guarded only on isolated DB fixtures."
pytestmark = [pytest.mark.canon(item) for item in CANON_ITEMS]

KNOWLEDGEOPS_TABLES = {
    "memory_sources",
    "memory_source_observations",
    "memory_artifacts",
    "memory_artifact_links",
    "memory_participation_decisions",
    "memory_projection_generations",
    "memory_index_membership",
    "memory_projection_artifacts",
    "memory_reconciliation_runs",
    "memory_reconciliation_items",
    "memory_working_notes",
    "memory_audit_events",
    "memory_output_runs",
    "memory_output_items",
    "memory_claim_support_assessments",
    "memory_route_promotion_decisions",
}


def test_ensure_memory_schema_is_idempotent_and_creates_knowledgeops_tables() -> None:
    conn = sqlite3.connect(":memory:")

    ensure_memory_schema(conn)
    ensure_memory_schema(conn)

    tables = {
        row[0]
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
    }
    indexes = {
        row[0]
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'index'")
    }

    assert tables >= KNOWLEDGEOPS_TABLES
    assert "idx_memory_sources_kind_status" in indexes
    assert "idx_memory_artifacts_output_mode" in indexes
    assert "idx_memory_output_items_run" in indexes


def test_schema_migration_does_not_delete_existing_rows(tmp_path: Path) -> None:
    db_path = tmp_path / "memory.sqlite3"
    with sqlite3.connect(db_path) as conn:
        ensure_memory_schema(conn)
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
                "x:tweet:1",
                "x_tweet",
                "https://x.example/status/1",
                "fixture",
                "tester",
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
        before = _table_counts(conn)

    with sqlite3.connect(db_path, timeout=60) as conn:
        ensure_memory_schema(conn)
        ensure_memory_schema(conn)
        after = _table_counts(conn)

    assert after["memory_sources"] == before["memory_sources"]
    for table, before_count in before.items():
        assert after[table] >= before_count, table


def test_legacy_schema_migrates_across_fresh_connections(tmp_path: Path) -> None:
    db_path = tmp_path / "legacy.sqlite3"
    with sqlite3.connect(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE memory_documents (
                doc_id TEXT PRIMARY KEY,
                doc_type TEXT NOT NULL,
                source_tweet_id TEXT,
                account_id TEXT,
                author_screen_name TEXT,
                title TEXT,
                body TEXT,
                compact_text TEXT,
                metadata_json TEXT,
                created_at TEXT,
                observed_at TEXT,
                updated_at TEXT
            );
            CREATE TABLE memory_participation_decisions (
                decision_id TEXT PRIMARY KEY,
                source_ref TEXT,
                artifact_id TEXT,
                output_mode TEXT NOT NULL,
                can_search INTEGER NOT NULL,
                can_explore INTEGER NOT NULL,
                can_use_in_working_note INTEGER NOT NULL,
                can_use_as_evidence INTEGER NOT NULL,
                can_use_in_answer INTEGER NOT NULL,
                can_trigger_external_fetch INTEGER NOT NULL,
                reason TEXT NOT NULL,
                decided_at TEXT NOT NULL,
                metadata_json TEXT NOT NULL
            );
            INSERT INTO memory_participation_decisions (
                decision_id, source_ref, artifact_id, output_mode, can_search,
                can_explore, can_use_in_working_note, can_use_as_evidence,
                can_use_in_answer, can_trigger_external_fetch, reason,
                decided_at, metadata_json
            )
            VALUES (
                'decision-1', 'x:tweet:1', NULL, 'explore', 1, 1, 1, 0,
                0, 0, 'legacy', '2026-07-03T00:00:00Z', '{}'
            );
            """
        )

    with sqlite3.connect(db_path, timeout=60) as conn:
        ensure_memory_schema(conn)
    with sqlite3.connect(db_path, timeout=60) as conn:
        ensure_memory_schema(conn)
        row = conn.execute(
            """
            SELECT subject_kind, policy_version, severity, decided_by,
                   input_hash_json
            FROM memory_participation_decisions
            WHERE decision_id = 'decision-1'
            """
        ).fetchone()

    assert row == (
        "source",
        "knowledgeops-v1",
        "info",
        "research_x.memory.participation",
        "{}",
    )


def _table_counts(conn: sqlite3.Connection) -> dict[str, int]:
    return {
        table: int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
        for table in KNOWLEDGEOPS_TABLES
    }
