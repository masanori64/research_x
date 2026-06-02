from __future__ import annotations

import sqlite3

from research_x.memory.document_hashes import (
    memory_document_embedding_text_hash,
    memory_document_source_hash,
)


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
            source_doc_hash TEXT,
            embedding_text_hash TEXT,
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
            route TEXT,
            query_terms_json TEXT,
            intents_json TEXT,
            note TEXT,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS memory_eval_queries (
            query_id TEXT PRIMARY KEY,
            query TEXT NOT NULL,
            intent TEXT,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS memory_eval_runs (
            run_id TEXT PRIMARY KEY,
            cases_path TEXT,
            case_count INTEGER NOT NULL,
            parameters_json TEXT NOT NULL,
            status TEXT NOT NULL,
            ok_count INTEGER NOT NULL,
            needs_review_count INTEGER NOT NULL,
            fail_count INTEGER NOT NULL,
            started_at TEXT NOT NULL,
            finished_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS memory_eval_results (
            result_id TEXT PRIMARY KEY,
            run_id TEXT NOT NULL,
            case_index INTEGER NOT NULL,
            query TEXT NOT NULL,
            status TEXT NOT NULL,
            route TEXT NOT NULL,
            expected_route TEXT,
            stop_reason TEXT NOT NULL,
            hits INTEGER NOT NULL,
            context_chunks INTEGER NOT NULL,
            first_doc_id TEXT,
            best_score REAL NOT NULL,
            matched_terms_json TEXT NOT NULL,
            retrieval_engines_json TEXT NOT NULL,
            source_kinds_json TEXT NOT NULL,
            answer_status TEXT,
            answer_citations INTEGER NOT NULL,
            notes_json TEXT NOT NULL,
            metadata_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(run_id) REFERENCES memory_eval_runs(run_id)
        );

        CREATE TABLE IF NOT EXISTS memory_embeddings (
            doc_id TEXT NOT NULL,
            provider TEXT NOT NULL,
            model TEXT NOT NULL,
            dimensions INTEGER NOT NULL,
            embedding_profile TEXT NOT NULL DEFAULT 'general_memory',
            text_template_version TEXT NOT NULL DEFAULT 'memory-doc-embedding-v1',
            embedding BLOB NOT NULL,
            source_doc_hash TEXT,
            embedded_text_hash TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY(
                doc_id, provider, model, dimensions,
                embedding_profile, text_template_version
            )
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

        CREATE TABLE IF NOT EXISTS memory_search_runs (
            run_id TEXT PRIMARY KEY,
            query TEXT NOT NULL,
            query_plan_json TEXT NOT NULL,
            parameters_json TEXT NOT NULL,
            status TEXT NOT NULL,
            result_count INTEGER NOT NULL,
            started_at TEXT NOT NULL,
            finished_at TEXT NOT NULL,
            error TEXT
        );

        CREATE TABLE IF NOT EXISTS memory_search_results (
            result_id TEXT PRIMARY KEY,
            run_id TEXT NOT NULL,
            rank INTEGER NOT NULL,
            doc_id TEXT NOT NULL,
            doc_type TEXT,
            source_kind TEXT NOT NULL,
            source_id TEXT,
            source_url TEXT,
            score REAL NOT NULL,
            snippet TEXT,
            provider TEXT NOT NULL,
            provider_role TEXT NOT NULL,
            match_method TEXT,
            evidence_status TEXT NOT NULL,
            metadata_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(run_id) REFERENCES memory_search_runs(run_id)
        );

        CREATE TABLE IF NOT EXISTS memory_tool_calls (
            tool_call_id TEXT PRIMARY KEY,
            run_id TEXT,
            provider TEXT NOT NULL,
            provider_role TEXT NOT NULL,
            action TEXT NOT NULL,
            input_json TEXT NOT NULL,
            output_json TEXT,
            status TEXT NOT NULL,
            error TEXT,
            started_at TEXT NOT NULL,
            finished_at TEXT
        );

        CREATE TABLE IF NOT EXISTS memory_context_chunks (
            chunk_id TEXT PRIMARY KEY,
            run_id TEXT,
            source_kind TEXT NOT NULL,
            source_id TEXT NOT NULL,
            source_url TEXT,
            provider TEXT,
            provider_role TEXT,
            chunk_text TEXT NOT NULL,
            chunk_index INTEGER NOT NULL,
            offset_start INTEGER,
            offset_end INTEGER,
            token_count INTEGER,
            relevance_score REAL,
            extractor_version TEXT NOT NULL,
            created_at TEXT NOT NULL,
            metadata_json TEXT NOT NULL,
            FOREIGN KEY(run_id) REFERENCES memory_search_runs(run_id)
        );

        CREATE TABLE IF NOT EXISTS memory_citation_annotations (
            citation_id TEXT PRIMARY KEY,
            answer_id TEXT,
            chunk_id TEXT NOT NULL,
            source_kind TEXT NOT NULL,
            source_id TEXT NOT NULL,
            source_url TEXT,
            title TEXT,
            answer_start_index INTEGER,
            answer_end_index INTEGER,
            field_path TEXT,
            support_type TEXT NOT NULL,
            evidence_status TEXT NOT NULL,
            confidence REAL,
            created_at TEXT NOT NULL,
            metadata_json TEXT NOT NULL,
            FOREIGN KEY(chunk_id) REFERENCES memory_context_chunks(chunk_id)
        );

        CREATE TABLE IF NOT EXISTS memory_answer_runs (
            answer_id TEXT PRIMARY KEY,
            question TEXT NOT NULL,
            workflow_id TEXT,
            model TEXT,
            prompt_version TEXT,
            retrieval_config_json TEXT NOT NULL,
            answer_text TEXT,
            structured_json TEXT,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS memory_workflow_runs (
            workflow_id TEXT PRIMARY KEY,
            query TEXT NOT NULL,
            route TEXT NOT NULL,
            status TEXT NOT NULL,
            stop_reason TEXT,
            started_at TEXT NOT NULL,
            finished_at TEXT,
            metadata_json TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS memory_workflow_steps (
            step_id TEXT PRIMARY KEY,
            workflow_id TEXT NOT NULL,
            step_index INTEGER NOT NULL,
            action TEXT NOT NULL,
            input_json TEXT NOT NULL,
            output_json TEXT,
            status TEXT NOT NULL,
            error TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY(workflow_id) REFERENCES memory_workflow_runs(workflow_id)
        );

        CREATE INDEX IF NOT EXISTS idx_memory_documents_doc_type
            ON memory_documents(doc_type);
        CREATE INDEX IF NOT EXISTS idx_memory_documents_source_tweet
            ON memory_documents(source_tweet_id);
        CREATE INDEX IF NOT EXISTS idx_memory_documents_account
            ON memory_documents(account_id);
        CREATE INDEX IF NOT EXISTS idx_memory_feedback_doc
            ON memory_feedback(doc_id);
        CREATE INDEX IF NOT EXISTS idx_memory_feedback_doc_label
            ON memory_feedback(doc_id, label);
        CREATE INDEX IF NOT EXISTS idx_memory_eval_runs_status
            ON memory_eval_runs(status, finished_at);
        CREATE INDEX IF NOT EXISTS idx_memory_eval_results_run
            ON memory_eval_results(run_id, case_index);
        CREATE INDEX IF NOT EXISTS idx_memory_eval_results_status
            ON memory_eval_results(status);
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
        CREATE INDEX IF NOT EXISTS idx_memory_search_runs_query
            ON memory_search_runs(query, started_at);
        CREATE INDEX IF NOT EXISTS idx_memory_search_results_run
            ON memory_search_results(run_id, rank);
        CREATE INDEX IF NOT EXISTS idx_memory_search_results_doc
            ON memory_search_results(doc_id);
        CREATE INDEX IF NOT EXISTS idx_memory_tool_calls_run
            ON memory_tool_calls(run_id);
        CREATE INDEX IF NOT EXISTS idx_memory_context_chunks_run
            ON memory_context_chunks(run_id, chunk_index);
        CREATE INDEX IF NOT EXISTS idx_memory_context_chunks_source
            ON memory_context_chunks(source_kind, source_id);
        CREATE INDEX IF NOT EXISTS idx_memory_citation_annotations_chunk
            ON memory_citation_annotations(chunk_id);
        CREATE INDEX IF NOT EXISTS idx_memory_answer_runs_question
            ON memory_answer_runs(question, created_at);
        CREATE INDEX IF NOT EXISTS idx_memory_workflow_runs_query
            ON memory_workflow_runs(query, started_at);
        CREATE INDEX IF NOT EXISTS idx_memory_workflow_steps_workflow
            ON memory_workflow_steps(workflow_id, step_index);
        """
    )
    _migrate_memory_documents(conn)
    _migrate_memory_feedback(conn)
    _migrate_memory_embeddings(conn)
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_memory_embeddings_provider_model
            ON memory_embeddings(
                provider, model, dimensions, embedding_profile, text_template_version
            )
        """
    )


def memory_document_count(conn: sqlite3.Connection) -> int:
    return int(conn.execute("SELECT COUNT(*) FROM memory_documents").fetchone()[0])


def _migrate_memory_documents(conn: sqlite3.Connection) -> None:
    columns = _column_names(conn, "memory_documents")
    if "source_doc_hash" not in columns:
        conn.execute("ALTER TABLE memory_documents ADD COLUMN source_doc_hash TEXT")
    if "embedding_text_hash" not in columns:
        conn.execute("ALTER TABLE memory_documents ADD COLUMN embedding_text_hash TEXT")
    rows = conn.execute(
        """
        SELECT
            doc_id, title, body, compact_text, metadata_json,
            source_doc_hash, embedding_text_hash
        FROM memory_documents
        WHERE source_doc_hash IS NULL
           OR embedding_text_hash IS NULL
        """
    ).fetchall()
    for row in rows:
        doc = {
            "doc_id": row[0],
            "title": row[1],
            "body": row[2],
            "compact_text": row[3],
            "metadata_json": row[4],
        }
        conn.execute(
            """
            UPDATE memory_documents
            SET source_doc_hash = ?, embedding_text_hash = ?
            WHERE doc_id = ?
            """,
            (
                memory_document_source_hash(doc),
                memory_document_embedding_text_hash(doc),
                doc["doc_id"],
            ),
        )


def _migrate_memory_feedback(conn: sqlite3.Connection) -> None:
    columns = _column_names(conn, "memory_feedback")
    migrations = {
        "route": "ALTER TABLE memory_feedback ADD COLUMN route TEXT",
        "query_terms_json": "ALTER TABLE memory_feedback ADD COLUMN query_terms_json TEXT",
        "intents_json": "ALTER TABLE memory_feedback ADD COLUMN intents_json TEXT",
    }
    for column, sql in migrations.items():
        if column not in columns:
            conn.execute(sql)


def _migrate_memory_embeddings(conn: sqlite3.Connection) -> None:
    columns = _column_names(conn, "memory_embeddings")
    expected_pk = [
        "doc_id",
        "provider",
        "model",
        "dimensions",
        "embedding_profile",
        "text_template_version",
    ]
    if (
        {"embedding_profile", "text_template_version", "source_doc_hash"}.issubset(columns)
        and _primary_key_columns(conn, "memory_embeddings") == expected_pk
    ):
        return

    embedding_profile_expr = (
        "COALESCE(embedding_profile, 'general_memory')"
        if "embedding_profile" in columns
        else "'general_memory'"
    )
    text_template_expr = (
        "COALESCE(text_template_version, 'memory-doc-embedding-v1')"
        if "text_template_version" in columns
        else "'memory-doc-embedding-v1'"
    )
    source_doc_hash_expr = "source_doc_hash" if "source_doc_hash" in columns else "NULL"

    conn.executescript(
        """
        DROP INDEX IF EXISTS idx_memory_embeddings_provider_model;

        ALTER TABLE memory_embeddings RENAME TO memory_embeddings_old;

        CREATE TABLE memory_embeddings (
            doc_id TEXT NOT NULL,
            provider TEXT NOT NULL,
            model TEXT NOT NULL,
            dimensions INTEGER NOT NULL,
            embedding_profile TEXT NOT NULL DEFAULT 'general_memory',
            text_template_version TEXT NOT NULL DEFAULT 'memory-doc-embedding-v1',
            embedding BLOB NOT NULL,
            source_doc_hash TEXT,
            embedded_text_hash TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY(
                doc_id, provider, model, dimensions,
                embedding_profile, text_template_version
            )
        );

        """
    )
    conn.execute(
        f"""
        INSERT OR REPLACE INTO memory_embeddings (
            doc_id, provider, model, dimensions, embedding_profile, text_template_version,
            embedding, source_doc_hash, embedded_text_hash, created_at, updated_at
        )
        SELECT
            doc_id, provider, model, dimensions,
            {embedding_profile_expr}, {text_template_expr},
            embedding, {source_doc_hash_expr}, embedded_text_hash, created_at, updated_at
        FROM memory_embeddings_old;
        """
    )
    conn.executescript(
        """

        DROP TABLE memory_embeddings_old;

        CREATE INDEX IF NOT EXISTS idx_memory_embeddings_provider_model
            ON memory_embeddings(
                provider, model, dimensions, embedding_profile, text_template_version
            );
        """
    )


def _column_names(conn: sqlite3.Connection, table: str) -> set[str]:
    return {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def _primary_key_columns(conn: sqlite3.Connection, table: str) -> list[str]:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    keyed = [(int(row[5]), str(row[1])) for row in rows if int(row[5]) > 0]
    return [name for _, name in sorted(keyed)]
