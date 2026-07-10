from __future__ import annotations

import sqlite3

from research_x.memory.schema import ensure_memory_schema

CLASSIFICATION_COLUMNS = (
    "source_kind",
    "source_subkind",
    "language",
    "modality",
    "privacy_class",
    "retention_class",
    "embedding_eligibility",
)


def test_fresh_memory_documents_schema_sets_typed_classification_defaults() -> None:
    with sqlite3.connect(":memory:") as conn:
        ensure_memory_schema(conn)

        columns = _column_names(conn)
        indexes = _index_names(conn)
        for column in CLASSIFICATION_COLUMNS:
            assert column in columns
        assert "idx_memory_documents_classification" in indexes
        assert "idx_memory_documents_embedding_filters" in indexes

        _insert_legacy_document(conn, doc_id="tweet:1", doc_type="tweet_doc")
        _insert_legacy_document(conn, doc_id="media:1", doc_type="media_doc")

        assert _classification(conn, "tweet:1") == (
            "local_x_db",
            "tweet_atomic",
            "und",
            "text",
            "user_private",
            "retain",
            "eligible",
        )
        assert _classification(conn, "media:1") == (
            "local_x_media",
            "media_caption_text",
            "und",
            "text_from_media",
            "user_private",
            "retain",
            "eligible",
        )


def test_memory_documents_migration_backfills_classification_idempotently() -> None:
    with sqlite3.connect(":memory:") as conn:
        _create_legacy_memory_documents_table(conn)
        _insert_legacy_document(conn, doc_id="ticker_event:1", doc_type="ticker_event")

        ensure_memory_schema(conn)
        ensure_memory_schema(conn)

        assert _classification(conn, "ticker_event:1") == (
            "local_derived",
            "temporal_event_record",
            "und",
            "text",
            "user_private",
            "retain",
            "eligible",
        )
        source_hash, embedding_hash = conn.execute(
            """
            SELECT source_doc_hash, embedding_text_hash
            FROM memory_documents
            WHERE doc_id = 'ticker_event:1'
            """
        ).fetchone()
        assert source_hash
        assert embedding_hash


def test_memory_document_classification_preserves_explicit_values() -> None:
    with sqlite3.connect(":memory:") as conn:
        ensure_memory_schema(conn)
        conn.execute(
            """
            INSERT INTO memory_documents (
                doc_id, doc_type, title, body, compact_text, metadata_json,
                source_kind, source_subkind, language, modality, privacy_class,
                retention_class, embedding_eligibility
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "external:1",
                "external_fetch_section",
                "External section",
                "body",
                "body",
                "{}",
                "external_fetch",
                "external_fetch_section",
                "ja",
                "text",
                "public_reference",
                "reviewed_archive",
                "not_eligible",
            ),
        )

        ensure_memory_schema(conn)

        assert _classification(conn, "external:1") == (
            "external_fetch",
            "external_fetch_section",
            "ja",
            "text",
            "public_reference",
            "reviewed_archive",
            "not_eligible",
        )


def _create_legacy_memory_documents_table(conn: sqlite3.Connection) -> None:
    conn.execute(
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
        )
        """
    )


def _insert_legacy_document(
    conn: sqlite3.Connection,
    *,
    doc_id: str,
    doc_type: str,
) -> None:
    conn.execute(
        """
        INSERT INTO memory_documents (
            doc_id, doc_type, title, body, compact_text, metadata_json,
            created_at, observed_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            doc_id,
            doc_type,
            f"title {doc_id}",
            f"body {doc_id}",
            f"compact {doc_id}",
            "{}",
            "2026-07-08T00:00:00+00:00",
            "2026-07-08T00:00:00+00:00",
            "2026-07-08T00:00:00+00:00",
        ),
    )


def _classification(conn: sqlite3.Connection, doc_id: str) -> tuple[str, ...]:
    row = conn.execute(
        f"""
        SELECT {", ".join(CLASSIFICATION_COLUMNS)}
        FROM memory_documents
        WHERE doc_id = ?
        """,
        (doc_id,),
    ).fetchone()
    assert row is not None
    return tuple(str(value) for value in row)


def _column_names(conn: sqlite3.Connection) -> set[str]:
    return {
        str(row[1])
        for row in conn.execute("PRAGMA table_info(memory_documents)").fetchall()
    }


def _index_names(conn: sqlite3.Connection) -> set[str]:
    return {
        str(row[1])
        for row in conn.execute("PRAGMA index_list(memory_documents)").fetchall()
    }
