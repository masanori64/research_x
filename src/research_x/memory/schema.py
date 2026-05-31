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

        CREATE TABLE IF NOT EXISTS memory_relations (
            relation_id TEXT PRIMARY KEY,
            source_doc_id TEXT NOT NULL,
            target_doc_id TEXT NOT NULL,
            relation_type TEXT NOT NULL,
            strength REAL NOT NULL,
            status TEXT NOT NULL,
            evidence_json TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS memory_external_runs (
            run_id TEXT PRIMARY KEY,
            provider TEXT NOT NULL,
            provider_role TEXT NOT NULL,
            query TEXT NOT NULL,
            endpoint TEXT NOT NULL,
            parameters_json TEXT NOT NULL,
            status TEXT NOT NULL,
            retrieved_at TEXT NOT NULL,
            raw_response_hash TEXT,
            retention_policy TEXT NOT NULL,
            error TEXT
        );

        CREATE TABLE IF NOT EXISTS memory_external_items (
            item_id TEXT PRIMARY KEY,
            run_id TEXT NOT NULL,
            position INTEGER NOT NULL,
            title TEXT,
            url TEXT NOT NULL,
            snippet TEXT,
            source TEXT,
            metadata_json TEXT,
            FOREIGN KEY(run_id) REFERENCES memory_external_runs(run_id)
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
        CREATE INDEX IF NOT EXISTS idx_memory_relations_source
            ON memory_relations(source_doc_id);
        CREATE INDEX IF NOT EXISTS idx_memory_relations_target
            ON memory_relations(target_doc_id);
        CREATE INDEX IF NOT EXISTS idx_memory_relations_type
            ON memory_relations(relation_type);
        CREATE INDEX IF NOT EXISTS idx_memory_external_runs_query_provider
            ON memory_external_runs(query, provider, provider_role);
        CREATE INDEX IF NOT EXISTS idx_memory_external_items_run
            ON memory_external_items(run_id, position);
        CREATE INDEX IF NOT EXISTS idx_memory_external_items_url
            ON memory_external_items(url);
        """
    )


def memory_document_count(conn: sqlite3.Connection) -> int:
    return int(conn.execute("SELECT COUNT(*) FROM memory_documents").fetchone()[0])
