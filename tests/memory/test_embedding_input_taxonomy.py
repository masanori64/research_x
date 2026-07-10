from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from research_x.memory.document_hashes import memory_document_source_hash
from research_x.memory.embedding_input import classify_embedding_inputs
from research_x.memory.schema import ensure_memory_schema

CREATED_AT = "2026-07-09T00:00:00+00:00"


def test_embedding_input_taxonomy_classifies_core_roles(tmp_path: Path) -> None:
    db_path = tmp_path / "taxonomy.sqlite3"
    _seed_taxonomy_db(db_path)

    report = classify_embedding_inputs(
        db_path,
        write=True,
        report_dir=tmp_path / "reports",
    )

    assert report["total_documents_seen"] == 8
    assert report["by_source_kind"]["x_authored_tweet"] == 1
    assert report["by_source_kind"]["x_bookmarked_tweet"] == 1
    assert report["by_source_kind"]["x_quote_comment"] == 1
    assert report["by_source_kind"]["x_media_ocr_text"] == 1
    assert report["by_source_kind"]["external_search_candidate"] == 1
    assert report["by_source_kind"]["external_fetch_text"] == 1
    assert report["by_source_kind"]["derived_author_profile"] == 1
    assert report["by_source_kind"]["operational_control_artifact"] == 1
    assert report["bookmark_documents"]["with_bookmark_owner"] == 1
    assert report["external_documents"]["candidates"] == 1
    assert report["external_documents"]["fetch_artifacts_embedding_eligible"] == 1
    assert report["operational_artifacts_excluded"] == 1

    with sqlite3.connect(db_path) as conn:
        rows = {
            row[0]: row[1:]
            for row in conn.execute(
                """
                SELECT doc_id, source_kind, ownership_kind, content_role,
                       relation_role, embedding_eligible,
                       answer_support_possible, sensitivity_kind
                FROM memory_document_taxonomy
                """
            )
        }

    assert rows["doc:bookmark"][:4] == (
        "x_bookmarked_tweet",
        "bookmarked_by_user",
        "preference_signal",
        "bookmark_target",
    )
    assert rows["doc:bookmark"][5] == 1
    assert rows["doc:external-candidate"][4:6] == (0, 0)
    assert rows["doc:derived"][5] == 0
    assert rows["doc:operational"][4:] == (0, 0, "operational_not_for_embedding")


def test_embedding_control_sidecars_require_artifact_persistence(tmp_path: Path) -> None:
    db_path = tmp_path / "taxonomy.sqlite3"
    _seed_taxonomy_db(db_path)
    none_dir = tmp_path / "none"
    trace_dir = tmp_path / "trace"
    artifact_dir = tmp_path / "artifacts"

    classify_embedding_inputs(db_path, report_dir=none_dir)
    classify_embedding_inputs(db_path, report_dir=trace_dir, persistence="trace")

    assert not none_dir.exists()
    assert not trace_dir.exists()

    classify_embedding_inputs(
        db_path,
        report_dir=artifact_dir,
        persistence="artifacts",
    )

    assert (artifact_dir / "embedding_input_taxonomy.json").is_file()
    assert (artifact_dir / "embedding_input_taxonomy.md").is_file()


def _seed_taxonomy_db(db_path: Path) -> None:
    with sqlite3.connect(db_path) as conn:
        ensure_memory_schema(conn)
        conn.executescript(
            """
            CREATE TABLE tweets (
                tweet_id TEXT PRIMARY KEY,
                author_screen_name TEXT,
                text TEXT,
                created_at TEXT
            );
            CREATE TABLE account_bookmarks (
                account_id TEXT,
                tweet_id TEXT,
                observed_at TEXT,
                run_id TEXT
            );
            CREATE TABLE media (
                media_id TEXT PRIMARY KEY,
                tweet_id TEXT,
                type TEXT,
                local_path TEXT
            );
            """
        )
        conn.executemany(
            """
            INSERT INTO tweets (tweet_id, author_screen_name, text, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (
                ("authored", "me", "I said embedding safety matters", CREATED_AT),
                ("bookmarked", "other", "Interesting embedding reference", CREATED_AT),
                ("quote", "me", "quote commentary", CREATED_AT),
                ("media", "artist", "media source", CREATED_AT),
            ),
        )
        conn.execute(
            "INSERT INTO account_bookmarks VALUES (?, ?, ?, ?)",
            ("user", "bookmarked", CREATED_AT, "run-1"),
        )
        conn.execute(
            "INSERT INTO media VALUES (?, ?, ?, ?)",
            ("media-1", "media", "photo", "x.png"),
        )
        docs = (
            _doc("doc:authored", "tweet_doc", "authored", "I said embedding safety matters", {}),
            _doc("doc:bookmark", "tweet_doc", "bookmarked", "Interesting embedding reference", {}),
            _doc(
                "doc:quote",
                "quote_tree_doc",
                "quote",
                "Commenting on a quoted source",
                {"quoted_tweet_id": "quoted"},
            ),
            _doc(
                "doc:media",
                "media_doc",
                "media",
                "OCR visible text",
                {"media_id": "media-1", "ocr_source": "ocr"},
            ),
            _doc(
                "doc:external-candidate",
                "external_search_candidate",
                "",
                "snippet only",
                {"requested_url": "https://example.com"},
            ),
            _doc(
                "doc:external-fetch",
                "external_fetch_section",
                "",
                "Fetched article",
                {
                    "requested_url": "https://example.com",
                    "final_url": "https://example.com",
                    "content_hash": "content",
                    "text_hash": "text",
                    "fetched_at": CREATED_AT,
                    "storage_rights": "stored_for_user_research",
                    "prompt_injection_review_state": "passed",
                },
            ),
            _doc("doc:derived", "author_profile", "", "Derived profile", {}),
            _doc(
                "doc:operational",
                "note",
                "",
                "Control note",
                {"artifact_kind": "operational_control_artifact"},
            ),
        )
        for doc in docs:
            conn.execute(
                """
                INSERT INTO memory_documents (
                    doc_id, doc_type, source_tweet_id, author_screen_name,
                    title, body, compact_text, metadata_json, source_doc_hash,
                    created_at, observed_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    doc["doc_id"],
                    doc["doc_type"],
                    doc["source_tweet_id"],
                    "tester",
                    doc["title"],
                    doc["body"],
                    doc["body"],
                    json.dumps(doc["metadata"], sort_keys=True),
                    memory_document_source_hash(
                        {
                            "doc_id": doc["doc_id"],
                            "title": doc["title"],
                            "body": doc["body"],
                            "compact_text": doc["body"],
                            "metadata_json": json.dumps(doc["metadata"], sort_keys=True),
                        }
                    ),
                    CREATED_AT,
                    CREATED_AT,
                    CREATED_AT,
                ),
            )


def _doc(
    doc_id: str,
    doc_type: str,
    source_tweet_id: str,
    body: str,
    metadata: dict[str, object],
) -> dict[str, object]:
    return {
        "doc_id": doc_id,
        "doc_type": doc_type,
        "source_tweet_id": source_tweet_id,
        "title": doc_id,
        "body": body,
        "metadata": metadata,
    }
