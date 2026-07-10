from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from research_x.memory import source_refs
from research_x.memory.reconciliation import reconcile_source_observation
from research_x.memory.schema import ensure_memory_schema
from research_x.memory.source_manifest import sync_x_source_manifest

CANON_ITEMS = ("P3", "L3")
PURPOSE = "Source identity and observation completeness stay separate from projections."
pytestmark = [pytest.mark.canon(item) for item in CANON_ITEMS]


def test_source_ref_formats_reject_projection_or_document_identity() -> None:
    parsed = source_refs.parse_source_ref(source_refs.x_tweet("tweet-1"))

    assert parsed.namespace == "x"
    assert parsed.kind == "tweet"
    assert source_refs.github_file("owner", "repo", "README.md", "abc").startswith(
        "github:file:owner/repo:"
    )
    with pytest.raises(ValueError):
        source_refs.parse_source_ref("doc-1")


@pytest.mark.parametrize("completeness", ("complete", "partial", "unknown"))
def test_source_manifest_records_observation_completeness(
    tmp_path: Path,
    completeness: str,
) -> None:
    db_path = tmp_path / "x.sqlite3"
    _seed_tweet_table(db_path)

    sync_x_source_manifest(
        db_path,
        observation_run_id=f"run-{completeness}",
        observation_completeness=completeness,
        observed_at="2026-07-03T00:00:00Z",
    )

    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            """
            SELECT source_ref, observation_completeness, status
            FROM memory_source_observations
            WHERE observation_run_id = ?
            """,
            (f"run-{completeness}",),
        ).fetchone()

    assert row == ("x:tweet:tweet-1", completeness, "observed")


def test_partial_observation_does_not_auto_tombstone_missing_source(tmp_path: Path) -> None:
    db_path = tmp_path / "x.sqlite3"
    _seed_sources(db_path)

    summary = reconcile_source_observation(
        db_path,
        observed_source_refs=("x:tweet:tweet-1",),
        observation_completeness="partial",
        reconciliation_run_id="run-partial",
        started_at="2026-07-03T00:00:00Z",
    )

    assert summary.by_status == {"missing_in_partial_observation": 1, "unchanged": 1}
    assert _reconciliation_status(db_path, "x:tweet:tweet-2") == (
        "source_missing_partial",
        "missing_in_partial_observation",
    )


def _seed_tweet_table(db_path: Path) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE tweets (
                tweet_id TEXT PRIMARY KEY,
                url TEXT,
                author_screen_name TEXT,
                text TEXT,
                created_at TEXT,
                first_observed_at TEXT,
                last_observed_at TEXT,
                role TEXT,
                collection_kind TEXT,
                providers_json TEXT,
                raw_json TEXT,
                updated_at TEXT
            );
            """
        )
        conn.execute(
            """
            INSERT INTO tweets (
                tweet_id, url, author_screen_name, text, created_at,
                first_observed_at, last_observed_at, role, collection_kind,
                providers_json, raw_json, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "tweet-1",
                "https://x.example/status/tweet-1",
                "author",
                "KnowledgeOps source tweet",
                "2026-07-02T00:00:00Z",
                "2026-07-03T00:00:00Z",
                "2026-07-03T00:00:00Z",
                "bookmark_root",
                "bookmarks",
                "[]",
                "{}",
                "2026-07-03T00:00:00Z",
            ),
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


def _reconciliation_status(db_path: Path, subject_id: str) -> tuple[str, str]:
    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            """
            SELECT action, status
            FROM memory_reconciliation_items
            WHERE subject_id = ?
            """,
            (subject_id,),
        ).fetchone()
    assert row is not None
    return row
