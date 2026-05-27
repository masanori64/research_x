from __future__ import annotations

import sqlite3


def ensure_memory_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS memory_documents (
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

        CREATE VIRTUAL TABLE IF NOT EXISTS memory_document_fts USING fts5(
            doc_id UNINDEXED,
            title,
            body,
            compact_text,
            author_screen_name,
            metadata_json
        );

        CREATE TABLE IF NOT EXISTS memory_feedback (
            feedback_id TEXT PRIMARY KEY,
            query TEXT NOT NULL,
            doc_id TEXT NOT NULL,
            label TEXT NOT NULL,
            note TEXT,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS memory_eval_queries (
            query_id TEXT PRIMARY KEY,
            query TEXT NOT NULL,
            intent TEXT,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS memory_embeddings (
            doc_id TEXT NOT NULL,
            provider TEXT NOT NULL,
            model TEXT NOT NULL,
            dimensions INTEGER NOT NULL,
            embedding BLOB NOT NULL,
            embedded_text_hash TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY(doc_id, provider, model, dimensions)
        );

        CREATE INDEX IF NOT EXISTS idx_memory_documents_doc_type
            ON memory_documents(doc_type);
        CREATE INDEX IF NOT EXISTS idx_memory_documents_source_tweet
            ON memory_documents(source_tweet_id);
        CREATE INDEX IF NOT EXISTS idx_memory_documents_account
            ON memory_documents(account_id);
        CREATE INDEX IF NOT EXISTS idx_memory_feedback_doc
            ON memory_feedback(doc_id);
        CREATE INDEX IF NOT EXISTS idx_memory_embeddings_provider_model
            ON memory_embeddings(provider, model, dimensions);
        """
    )


def memory_document_count(conn: sqlite3.Connection) -> int:
    try:
        return int(conn.execute("SELECT COUNT(*) FROM memory_documents").fetchone()[0])
    except sqlite3.OperationalError:
        return 0
