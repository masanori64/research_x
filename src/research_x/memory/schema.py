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

        CREATE TABLE IF NOT EXISTS memory_media_embeddings (
            media_id TEXT NOT NULL,
            doc_id TEXT NOT NULL,
            source_tweet_id TEXT,
            provider TEXT NOT NULL,
            model TEXT NOT NULL,
            dimensions INTEGER NOT NULL,
            embedding_profile TEXT NOT NULL,
            input_template_version TEXT NOT NULL,
            embedding BLOB NOT NULL,
            mime_type TEXT NOT NULL,
            local_path TEXT NOT NULL,
            media_url TEXT,
            media_file_hash TEXT NOT NULL,
            media_metadata_hash TEXT NOT NULL,
            input_parts_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY(
                media_id, provider, model, dimensions,
                embedding_profile, input_template_version
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

        CREATE TABLE IF NOT EXISTS memory_objective_route_runs (
            route_run_id TEXT PRIMARY KEY,
            query TEXT NOT NULL,
            objective_route_version TEXT NOT NULL,
            eval_question_type TEXT NOT NULL,
            primary_route TEXT NOT NULL,
            fallback_routes_json TEXT NOT NULL,
            must_run_guards_json TEXT NOT NULL,
            escalation_triggers_json TEXT NOT NULL,
            stop_conditions_json TEXT NOT NULL,
            budget_policy TEXT NOT NULL,
            planned_provider_roles_json TEXT NOT NULL,
            selected_routes_json TEXT NOT NULL,
            stop_reason TEXT,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            metadata_json TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS memory_objective_route_steps (
            route_step_id TEXT PRIMARY KEY,
            route_run_id TEXT NOT NULL,
            step_index INTEGER NOT NULL,
            route_arm TEXT NOT NULL,
            status TEXT NOT NULL,
            evidence_count INTEGER NOT NULL,
            citation_count INTEGER NOT NULL,
            stop_condition TEXT,
            escalation_trigger TEXT,
            provider_quota_skipped INTEGER NOT NULL,
            output_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(route_run_id) REFERENCES memory_objective_route_runs(route_run_id)
        );

        CREATE TABLE IF NOT EXISTS memory_ocr_runs (
            ocr_run_id TEXT PRIMARY KEY,
            provider TEXT NOT NULL,
            model TEXT NOT NULL,
            ocr_profile TEXT NOT NULL,
            sample_policy TEXT NOT NULL,
            limit_count INTEGER,
            status TEXT NOT NULL,
            selected_regions INTEGER NOT NULL,
            processed_regions INTEGER NOT NULL,
            skipped_regions INTEGER NOT NULL,
            budget_event_id TEXT,
            started_at TEXT NOT NULL,
            finished_at TEXT,
            error TEXT,
            metadata_json TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS memory_ocr_regions (
            region_id TEXT PRIMARY KEY,
            ocr_run_id TEXT,
            media_id TEXT NOT NULL,
            source_tweet_id TEXT,
            page_index INTEGER NOT NULL,
            region_index INTEGER NOT NULL,
            reading_order INTEGER NOT NULL DEFAULT 0,
            bbox_json TEXT NOT NULL,
            region_hash TEXT NOT NULL,
            source_image_hash TEXT NOT NULL,
            local_path TEXT NOT NULL,
            crop_path TEXT NOT NULL DEFAULT '',
            mime_type TEXT NOT NULL,
            quality_flags_json TEXT NOT NULL,
            strata_json TEXT NOT NULL,
            engine_route TEXT NOT NULL,
            detector_version TEXT NOT NULL DEFAULT 'ocr-local-region-v1',
            status TEXT NOT NULL,
            created_at TEXT NOT NULL,
            metadata_json TEXT NOT NULL,
            FOREIGN KEY(ocr_run_id) REFERENCES memory_ocr_runs(ocr_run_id)
        );

        CREATE TABLE IF NOT EXISTS memory_ocr_texts (
            text_id TEXT PRIMARY KEY,
            ocr_run_id TEXT,
            region_id TEXT NOT NULL,
            media_id TEXT NOT NULL,
            provider TEXT NOT NULL,
            model TEXT NOT NULL,
            ocr_profile TEXT NOT NULL,
            text_profile TEXT NOT NULL DEFAULT 'raw_ocr',
            parent_text_id TEXT,
            raw_ocr_text TEXT NOT NULL,
            normalized_text TEXT NOT NULL,
            corrected_text TEXT,
            confidence REAL,
            evidence_status TEXT NOT NULL,
            source_image_hash TEXT NOT NULL,
            region_hash TEXT NOT NULL,
            quality_flags_json TEXT NOT NULL DEFAULT '{}',
            second_pass_status TEXT NOT NULL DEFAULT 'not_needed',
            second_pass_reason TEXT,
            created_at TEXT NOT NULL,
            metadata_json TEXT NOT NULL,
            FOREIGN KEY(ocr_run_id) REFERENCES memory_ocr_runs(ocr_run_id),
            FOREIGN KEY(region_id) REFERENCES memory_ocr_regions(region_id)
        );

        CREATE TABLE IF NOT EXISTS memory_api_budget_policies (
            policy_id TEXT PRIMARY KEY,
            enabled INTEGER NOT NULL,
            max_run_usd REAL,
            max_day_usd REAL,
            max_month_usd REAL,
            max_run_calls INTEGER,
            max_day_calls INTEGER,
            max_run_input_tokens INTEGER,
            max_run_media_bytes INTEGER,
            unknown_price_action TEXT NOT NULL,
            kill_switch_enabled INTEGER NOT NULL,
            metadata_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS memory_api_usage_events (
            event_id TEXT PRIMARY KEY,
            run_id TEXT,
            job_id TEXT,
            policy_id TEXT NOT NULL,
            provider TEXT NOT NULL,
            model TEXT NOT NULL,
            provider_role TEXT NOT NULL,
            operation TEXT NOT NULL,
            status TEXT NOT NULL,
            units_json TEXT NOT NULL,
            estimated_cost_usd REAL NOT NULL,
            actual_cost_usd REAL,
            request_hash TEXT,
            started_at TEXT NOT NULL,
            finished_at TEXT,
            error TEXT,
            metadata_json TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS memory_api_price_catalog (
            provider TEXT NOT NULL,
            model TEXT NOT NULL,
            operation TEXT NOT NULL,
            unit TEXT NOT NULL,
            usd_per_unit REAL NOT NULL,
            source_url TEXT,
            checked_at TEXT NOT NULL,
            notes TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY(provider, model, operation, unit)
        );

        CREATE TABLE IF NOT EXISTS memory_query_transforms (
            transform_id TEXT PRIMARY KEY,
            parent_query_id TEXT NOT NULL,
            query TEXT NOT NULL,
            transform_kind TEXT NOT NULL,
            generated_text TEXT NOT NULL,
            preserved_anchors_json TEXT NOT NULL,
            allowed_routes_json TEXT NOT NULL,
            drift_flags_json TEXT NOT NULL,
            citation_excluded INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            metadata_json TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS memory_retrieval_text_profiles (
            profile_id TEXT PRIMARY KEY,
            doc_id TEXT NOT NULL,
            retrieval_text_profile TEXT NOT NULL,
            retrieval_text TEXT NOT NULL,
            source_doc_hash TEXT,
            citation_excluded INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            metadata_json TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS memory_eval_gate_results (
            gate_result_id TEXT PRIMARY KEY,
            route_run_id TEXT,
            workflow_id TEXT,
            answer_id TEXT,
            query TEXT NOT NULL,
            gate_name TEXT NOT NULL,
            status TEXT NOT NULL,
            score REAL,
            evaluator_kind TEXT NOT NULL,
            evidence_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            metadata_json TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS memory_projection_generations (
            generation_id TEXT PRIMARY KEY,
            projection_kind TEXT NOT NULL,
            source_scope TEXT NOT NULL,
            builder_version TEXT NOT NULL,
            input_manifest_json TEXT NOT NULL,
            status TEXT NOT NULL,
            coverage_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            metadata_json TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS memory_index_membership (
            membership_id TEXT PRIMARY KEY,
            generation_id TEXT NOT NULL,
            artifact_kind TEXT NOT NULL,
            artifact_id TEXT NOT NULL,
            source_id TEXT,
            source_hash TEXT,
            membership_status TEXT NOT NULL,
            created_at TEXT NOT NULL,
            metadata_json TEXT NOT NULL,
            FOREIGN KEY(generation_id) REFERENCES memory_projection_generations(generation_id)
        );

        CREATE TABLE IF NOT EXISTS memory_security_boundaries (
            boundary_id TEXT PRIMARY KEY,
            run_id TEXT,
            artifact_kind TEXT NOT NULL,
            artifact_id TEXT NOT NULL,
            source_kind TEXT NOT NULL,
            trust_boundary TEXT NOT NULL,
            taint_flags_json TEXT NOT NULL,
            data_classification TEXT NOT NULL,
            source_visibility TEXT NOT NULL,
            account_scope TEXT,
            allowed_sinks_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            metadata_json TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS memory_visual_recall_evidence (
            visual_evidence_id TEXT PRIMARY KEY,
            media_id TEXT NOT NULL,
            source_tweet_id TEXT,
            evidence_level TEXT NOT NULL,
            page_index INTEGER NOT NULL,
            region_index INTEGER NOT NULL,
            pixel_bbox_json TEXT NOT NULL,
            normalized_bbox_json TEXT NOT NULL,
            citation_ready INTEGER NOT NULL,
            source_image_hash TEXT,
            provider TEXT,
            model TEXT,
            created_at TEXT NOT NULL,
            metadata_json TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS memory_user_ranking_signals (
            signal_id TEXT PRIMARY KEY,
            subject_kind TEXT NOT NULL,
            subject_id TEXT NOT NULL,
            signal_type TEXT NOT NULL,
            signal_value REAL NOT NULL,
            confidence REAL NOT NULL,
            route_scope TEXT NOT NULL,
            evidence_status TEXT NOT NULL,
            created_at TEXT NOT NULL,
            metadata_json TEXT NOT NULL
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
        CREATE INDEX IF NOT EXISTS idx_memory_media_embeddings_doc
            ON memory_media_embeddings(doc_id);
        CREATE INDEX IF NOT EXISTS idx_memory_media_embeddings_tweet
            ON memory_media_embeddings(source_tweet_id);
        CREATE INDEX IF NOT EXISTS idx_memory_answer_runs_question
            ON memory_answer_runs(question, created_at);
        CREATE INDEX IF NOT EXISTS idx_memory_workflow_runs_query
            ON memory_workflow_runs(query, started_at);
        CREATE INDEX IF NOT EXISTS idx_memory_workflow_steps_workflow
            ON memory_workflow_steps(workflow_id, step_index);
        CREATE INDEX IF NOT EXISTS idx_memory_objective_route_query
            ON memory_objective_route_runs(query, created_at);
        CREATE INDEX IF NOT EXISTS idx_memory_objective_route_steps_run
            ON memory_objective_route_steps(route_run_id, step_index);
        CREATE INDEX IF NOT EXISTS idx_memory_ocr_regions_media
            ON memory_ocr_regions(media_id, status);
        CREATE INDEX IF NOT EXISTS idx_memory_ocr_texts_media
            ON memory_ocr_texts(media_id, evidence_status);
        CREATE INDEX IF NOT EXISTS idx_memory_ocr_texts_region
            ON memory_ocr_texts(region_id);
        CREATE INDEX IF NOT EXISTS idx_memory_api_usage_run
            ON memory_api_usage_events(run_id, started_at);
        CREATE INDEX IF NOT EXISTS idx_memory_api_usage_provider
            ON memory_api_usage_events(provider, model, operation, started_at);
        CREATE INDEX IF NOT EXISTS idx_memory_api_usage_status
            ON memory_api_usage_events(status, started_at);
        CREATE INDEX IF NOT EXISTS idx_memory_query_transforms_parent
            ON memory_query_transforms(parent_query_id, transform_kind);
        CREATE INDEX IF NOT EXISTS idx_memory_retrieval_text_profiles_doc
            ON memory_retrieval_text_profiles(doc_id, retrieval_text_profile);
        CREATE INDEX IF NOT EXISTS idx_memory_eval_gate_results_query
            ON memory_eval_gate_results(query, gate_name, created_at);
        CREATE INDEX IF NOT EXISTS idx_memory_projection_generations_kind
            ON memory_projection_generations(projection_kind, created_at);
        CREATE INDEX IF NOT EXISTS idx_memory_index_membership_generation
            ON memory_index_membership(generation_id, artifact_kind);
        CREATE INDEX IF NOT EXISTS idx_memory_security_boundaries_artifact
            ON memory_security_boundaries(artifact_kind, artifact_id);
        CREATE INDEX IF NOT EXISTS idx_memory_visual_recall_media
            ON memory_visual_recall_evidence(media_id, evidence_level);
        CREATE INDEX IF NOT EXISTS idx_memory_user_ranking_signals_subject
            ON memory_user_ranking_signals(subject_kind, subject_id, route_scope);
        """
    )
    _migrate_memory_documents(conn)
    _migrate_memory_feedback(conn)
    _migrate_memory_embeddings(conn)
    _migrate_memory_ocr(conn)
    _ensure_default_api_budget_policy(conn)
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_memory_embeddings_provider_model
            ON memory_embeddings(
                provider, model, dimensions, embedding_profile, text_template_version
            )
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_memory_ocr_texts_profile
            ON memory_ocr_texts(text_profile, second_pass_status)
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


def _migrate_memory_ocr(conn: sqlite3.Connection) -> None:
    region_columns = _column_names(conn, "memory_ocr_regions")
    region_migrations = {
        "reading_order": (
            "ALTER TABLE memory_ocr_regions "
            "ADD COLUMN reading_order INTEGER NOT NULL DEFAULT 0"
        ),
        "crop_path": (
            "ALTER TABLE memory_ocr_regions "
            "ADD COLUMN crop_path TEXT NOT NULL DEFAULT ''"
        ),
        "detector_version": (
            "ALTER TABLE memory_ocr_regions "
            "ADD COLUMN detector_version TEXT NOT NULL DEFAULT 'ocr-local-region-v1'"
        ),
    }
    for column, sql in region_migrations.items():
        if column not in region_columns:
            conn.execute(sql)

    text_columns = _column_names(conn, "memory_ocr_texts")
    text_migrations = {
        "text_profile": (
            "ALTER TABLE memory_ocr_texts "
            "ADD COLUMN text_profile TEXT NOT NULL DEFAULT 'raw_ocr'"
        ),
        "parent_text_id": "ALTER TABLE memory_ocr_texts ADD COLUMN parent_text_id TEXT",
        "quality_flags_json": (
            "ALTER TABLE memory_ocr_texts "
            "ADD COLUMN quality_flags_json TEXT NOT NULL DEFAULT '{}'"
        ),
        "second_pass_status": (
            "ALTER TABLE memory_ocr_texts "
            "ADD COLUMN second_pass_status TEXT NOT NULL DEFAULT 'not_needed'"
        ),
        "second_pass_reason": (
            "ALTER TABLE memory_ocr_texts ADD COLUMN second_pass_reason TEXT"
        ),
    }
    for column, sql in text_migrations.items():
        if column not in text_columns:
            conn.execute(sql)


def _column_names(conn: sqlite3.Connection, table: str) -> set[str]:
    return {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def _primary_key_columns(conn: sqlite3.Connection, table: str) -> list[str]:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    keyed = [(int(row[5]), str(row[1])) for row in rows if int(row[5]) > 0]
    return [name for _, name in sorted(keyed)]


def _ensure_default_api_budget_policy(conn: sqlite3.Connection) -> None:
    import json
    from datetime import UTC, datetime

    exists = conn.execute(
        """
        SELECT 1
        FROM memory_api_budget_policies
        WHERE policy_id = 'default'
        LIMIT 1
        """
    ).fetchone()
    if exists:
        return
    now = datetime.now(tz=UTC).isoformat()
    conn.execute(
        """
        INSERT OR IGNORE INTO memory_api_budget_policies (
            policy_id, enabled, max_run_usd, max_day_usd, max_month_usd,
            max_run_calls, max_day_calls, max_run_input_tokens, max_run_media_bytes,
            unknown_price_action, kill_switch_enabled, metadata_json, created_at, updated_at
        )
        VALUES (
            'default', 1, 1.0, 5.0, 25.0,
            NULL, NULL, NULL, NULL,
            'block', 0, ?, ?, ?
        )
        """,
        (json.dumps({"warning_fraction": 0.8}, sort_keys=True), now, now),
    )
    if conn.in_transaction:
        conn.commit()
