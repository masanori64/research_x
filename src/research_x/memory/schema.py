from __future__ import annotations

import hashlib
import sqlite3

from research_x.memory.document_hashes import (
    memory_document_embedding_text_hash,
    memory_document_source_hash,
)
from research_x.memory.embedding_spaces import (
    ensure_embedding_space_for_spec,
    ensure_final_embedding_spaces,
)


def ensure_memory_schema(conn: sqlite3.Connection) -> None:
    conn.execute("PRAGMA busy_timeout = 60000")
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
            source_kind TEXT NOT NULL DEFAULT '',
            source_subkind TEXT NOT NULL DEFAULT '',
            language TEXT NOT NULL DEFAULT '',
            modality TEXT NOT NULL DEFAULT '',
            privacy_class TEXT NOT NULL DEFAULT '',
            retention_class TEXT NOT NULL DEFAULT '',
            embedding_eligibility TEXT NOT NULL DEFAULT '',
            source_doc_hash TEXT,
            embedding_text_hash TEXT,
            source_refs_json TEXT,
            artifact_id TEXT,
            projection_id TEXT,
            projection_hash TEXT,
            projection_builder_version TEXT,
            restore_path_json TEXT,
            lifecycle_status TEXT,
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

        CREATE TABLE IF NOT EXISTS memory_eval_cases (
            eval_case_id TEXT PRIMARY KEY,
            suite TEXT NOT NULL,
            objective TEXT NOT NULL,
            expected_status TEXT,
            required_source_ids_json TEXT NOT NULL,
            forbidden_source_ids_json TEXT NOT NULL,
            route_tags_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            metadata_json TEXT NOT NULL
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
            workflow_id TEXT,
            context_run_id TEXT,
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

        CREATE TABLE IF NOT EXISTS memory_embedding_spaces (
            space_id TEXT PRIMARY KEY,
            provider TEXT NOT NULL,
            model TEXT NOT NULL,
            dimensions INTEGER NOT NULL,
            distance_metric TEXT NOT NULL,
            embedding_profile TEXT NOT NULL,
            text_template_version TEXT NOT NULL,
            modality TEXT NOT NULL,
            document_scope TEXT NOT NULL,
            source_kind_filter TEXT NOT NULL,
            language_filter TEXT NOT NULL,
            storage_rights_policy TEXT NOT NULL,
            provider_role TEXT NOT NULL,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL,
            created_by_run_id TEXT,
            notes TEXT NOT NULL
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
            embedding_id TEXT,
            space_id TEXT NOT NULL DEFAULT '',
            generation_id TEXT,
            projection_id TEXT,
            projection_policy_version TEXT,
            classification_version TEXT,
            target_space_id TEXT,
            chunk_id TEXT,
            media_id TEXT,
            fetch_artifact_id TEXT,
            embedded_input_hash TEXT,
            vector_ref TEXT,
            token_count INTEGER,
            provider_request_id TEXT,
            api_usage_event_id TEXT,
            stale_status TEXT NOT NULL DEFAULT 'current',
            PRIMARY KEY(
                doc_id, provider, model, dimensions,
                embedding_profile, text_template_version, space_id
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

        CREATE TABLE IF NOT EXISTS memory_fetch_artifacts (
            artifact_id TEXT PRIMARY KEY,
            tool_call_id TEXT NOT NULL,
            run_id TEXT,
            requested_url TEXT NOT NULL,
            final_url TEXT NOT NULL,
            fetched_at TEXT NOT NULL,
            retrieved_at TEXT NOT NULL,
            content_type TEXT,
            status_code INTEGER,
            response_hash TEXT NOT NULL,
            extracted_text_hash TEXT NOT NULL,
            raw_artifact_path TEXT,
            prompt_injection_review TEXT NOT NULL,
            prompt_injection_status TEXT NOT NULL,
            prompt_injection_flags_json TEXT NOT NULL,
            storage_rights TEXT NOT NULL,
            fetch_provider TEXT NOT NULL,
            metadata_json TEXT NOT NULL,
            FOREIGN KEY(tool_call_id) REFERENCES memory_tool_calls(tool_call_id)
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

        CREATE TABLE IF NOT EXISTS memory_provider_authorizations (
            authorization_id TEXT PRIMARY KEY,
            provider TEXT NOT NULL,
            model TEXT NOT NULL,
            operation TEXT NOT NULL,
            provider_role TEXT,
            allowed INTEGER NOT NULL,
            max_calls INTEGER,
            max_cost_usd REAL,
            max_input_tokens INTEGER,
            max_output_tokens INTEGER,
            max_media_bytes INTEGER,
            max_documents INTEGER,
            valid_from TEXT,
            valid_until TEXT,
            approved_by TEXT,
            approval_source TEXT,
            approved_scope TEXT,
            storage_rights TEXT,
            prompt_injection_required INTEGER,
            rollback_scope TEXT,
            metadata_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS memory_provider_execution_policies (
            policy_id TEXT PRIMARY KEY,
            authorization_id TEXT NOT NULL,
            provider TEXT NOT NULL,
            model TEXT NOT NULL,
            operation TEXT NOT NULL,
            provider_role TEXT,
            allowed INTEGER NOT NULL,
            max_calls INTEGER,
            max_cost_usd REAL,
            max_input_tokens INTEGER,
            max_output_tokens INTEGER,
            max_media_bytes INTEGER,
            max_documents INTEGER,
            valid_from TEXT,
            valid_until TEXT,
            approved_by TEXT,
            approval_source TEXT,
            approved_scope TEXT,
            storage_rights TEXT,
            prompt_injection_required INTEGER,
            rollback_scope TEXT,
            metadata_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS memory_provider_preflights (
            preflight_id TEXT PRIMARY KEY,
            run_id TEXT,
            policy_id TEXT NOT NULL,
            authorization_id TEXT,
            execution_policy_id TEXT,
            provider TEXT NOT NULL,
            model TEXT NOT NULL,
            operation TEXT NOT NULL,
            provider_role TEXT NOT NULL,
            status TEXT NOT NULL,
            provider_call_allowed INTEGER NOT NULL,
            provider_requests_sent INTEGER NOT NULL,
            provider_policy_required INTEGER NOT NULL,
            provider_policy_status TEXT NOT NULL,
            units_json TEXT NOT NULL,
            estimated_cost_usd REAL NOT NULL,
            price_status TEXT,
            budget_status TEXT NOT NULL,
            approval_valid INTEGER NOT NULL,
            execution_policy_valid INTEGER NOT NULL,
            report_json TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS memory_provider_transport_events (
            transport_event_id TEXT PRIMARY KEY,
            api_usage_event_id TEXT,
            run_id TEXT,
            job_id TEXT,
            authorization_id TEXT,
            execution_policy_id TEXT,
            provider TEXT NOT NULL,
            model TEXT NOT NULL,
            operation TEXT NOT NULL,
            provider_role TEXT NOT NULL,
            status TEXT NOT NULL,
            event_kind TEXT NOT NULL,
            started_at TEXT NOT NULL,
            finished_at TEXT,
            error TEXT,
            metadata_json TEXT NOT NULL
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

        CREATE VIRTUAL TABLE IF NOT EXISTS memory_retrieval_text_fts USING fts5(
            profile_id UNINDEXED,
            doc_id UNINDEXED,
            retrieval_text_profile UNINDEXED,
            retrieval_text
        );

        CREATE TABLE IF NOT EXISTS memory_document_taxonomy (
            doc_id TEXT NOT NULL,
            source_doc_hash TEXT,
            source_bundle_id TEXT,
            source_kind TEXT NOT NULL,
            ownership_kind TEXT NOT NULL,
            content_role TEXT NOT NULL,
            relation_role TEXT NOT NULL,
            modality_kind TEXT NOT NULL,
            temporal_scope TEXT NOT NULL,
            sensitivity_kind TEXT NOT NULL,
            account_id TEXT,
            viewer_account_id TEXT,
            author_id TEXT,
            bookmark_owner_account_id TEXT,
            tweet_id TEXT,
            conversation_id TEXT,
            replied_to_tweet_id TEXT,
            quoted_tweet_id TEXT,
            thread_id TEXT,
            media_id TEXT,
            external_artifact_id TEXT,
            collection_run_id TEXT,
            language TEXT NOT NULL DEFAULT 'unknown',
            detected_language_confidence REAL,
            created_at_source TEXT,
            observed_at TEXT,
            embedding_eligible INTEGER NOT NULL,
            embedding_exclusion_reason TEXT,
            answer_support_possible INTEGER NOT NULL,
            answer_support_block_reason TEXT,
            classification_version TEXT NOT NULL,
            classification_method TEXT NOT NULL,
            classification_confidence REAL NOT NULL,
            needs_review INTEGER NOT NULL DEFAULT 0,
            review_reason TEXT,
            source_restore_status TEXT NOT NULL,
            source_restore_path_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (doc_id, classification_version)
        );

        CREATE TABLE IF NOT EXISTS memory_embedding_template_policies (
            template_version TEXT PRIMARY KEY,
            projection_profile TEXT NOT NULL,
            target_space_id TEXT NOT NULL,
            source_kind_allowlist_json TEXT NOT NULL,
            ownership_allowlist_json TEXT NOT NULL,
            content_role_allowlist_json TEXT NOT NULL,
            template_body TEXT NOT NULL,
            max_input_chars INTEGER NOT NULL,
            field_policy_json TEXT NOT NULL,
            evidence_role TEXT NOT NULL,
            created_at TEXT NOT NULL,
            status TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS memory_embedding_template_examples (
            example_id TEXT PRIMARY KEY,
            template_version TEXT NOT NULL,
            doc_id TEXT NOT NULL,
            projection_profile TEXT NOT NULL,
            target_space_id TEXT NOT NULL,
            embedded_text TEXT NOT NULL,
            embedded_text_hash TEXT NOT NULL,
            included_fields_json TEXT NOT NULL,
            excluded_fields_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            metadata_json TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS memory_embedding_projections (
            projection_id TEXT PRIMARY KEY,
            doc_id TEXT NOT NULL,
            source_doc_hash TEXT,
            source_bundle_id TEXT,
            classification_version TEXT NOT NULL,
            projection_policy_version TEXT NOT NULL,
            projection_profile TEXT NOT NULL,
            target_space_id TEXT NOT NULL,
            text_template_version TEXT NOT NULL,
            embedded_text TEXT NOT NULL,
            embedded_text_hash TEXT NOT NULL,
            embedded_text_char_count INTEGER NOT NULL,
            estimated_input_tokens INTEGER,
            included_fields_json TEXT NOT NULL,
            excluded_fields_json TEXT NOT NULL,
            evidence_role TEXT NOT NULL,
            answer_support_allowed INTEGER NOT NULL DEFAULT 0,
            candidate_signal_type TEXT NOT NULL,
            source_restore_path_json TEXT NOT NULL,
            contributing_source_hashes_json TEXT NOT NULL,
            projection_status TEXT NOT NULL,
            stale_status TEXT NOT NULL,
            stale_reason TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(
                doc_id,
                source_doc_hash,
                projection_profile,
                target_space_id,
                text_template_version,
                projection_policy_version
            )
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
            space_id TEXT,
            projection_name TEXT,
            projection_version TEXT,
            selection_policy TEXT,
            source_query TEXT,
            source_scope TEXT NOT NULL,
            builder_version TEXT NOT NULL,
            input_manifest_json TEXT NOT NULL,
            status TEXT NOT NULL,
            coverage_json TEXT NOT NULL,
            source_count INTEGER NOT NULL DEFAULT 0,
            projected_count INTEGER NOT NULL DEFAULT 0,
            skipped_count INTEGER NOT NULL DEFAULT 0,
            stale_policy TEXT,
            code_commit TEXT,
            run_id TEXT,
            created_at TEXT NOT NULL,
            metadata_json TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS memory_vector_indexes (
            index_id TEXT PRIMARY KEY,
            space_id TEXT NOT NULL,
            backend TEXT NOT NULL,
            index_path TEXT NOT NULL,
            mapping_path TEXT NOT NULL,
            build_generation_id TEXT NOT NULL,
            vector_count INTEGER NOT NULL,
            coverage_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            status TEXT NOT NULL,
            metadata_json TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS memory_retrieval_engine_runs (
            engine_run_id TEXT PRIMARY KEY,
            query_id TEXT NOT NULL,
            engine_name TEXT NOT NULL,
            space_id TEXT,
            route_id TEXT,
            top_k INTEGER NOT NULL,
            filters_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            metadata_json TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS memory_retrieval_candidates (
            candidate_id TEXT PRIMARY KEY,
            engine_run_id TEXT NOT NULL,
            engine_name TEXT NOT NULL,
            space_id TEXT,
            doc_id TEXT,
            chunk_id TEXT,
            media_id TEXT,
            fetch_artifact_id TEXT,
            rank INTEGER NOT NULL,
            raw_score REAL,
            normalized_score REAL,
            fusion_score REAL,
            restoration_status TEXT NOT NULL,
            source_bundle_id TEXT,
            stale_status TEXT NOT NULL,
            not_evidence_reason TEXT,
            created_at TEXT NOT NULL,
            metadata_json TEXT NOT NULL,
            FOREIGN KEY(engine_run_id) REFERENCES memory_retrieval_engine_runs(engine_run_id)
        );

        CREATE TABLE IF NOT EXISTS memory_fusion_runs (
            fusion_run_id TEXT PRIMARY KEY,
            query_id TEXT NOT NULL,
            route_id TEXT,
            method TEXT NOT NULL,
            input_engine_runs_json TEXT NOT NULL,
            rrf_k REAL,
            engine_weights_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            metadata_json TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS memory_rerank_runs (
            rerank_run_id TEXT PRIMARY KEY,
            query_id TEXT NOT NULL,
            provider TEXT NOT NULL,
            model TEXT NOT NULL,
            authorization_id TEXT,
            input_candidate_count INTEGER NOT NULL,
            output_candidate_count INTEGER NOT NULL,
            usage_event_id TEXT,
            created_at TEXT NOT NULL,
            metadata_json TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS memory_restoration_attempts (
            restoration_attempt_id TEXT PRIMARY KEY,
            candidate_id TEXT NOT NULL,
            source_bundle_id TEXT,
            source_doc_hash TEXT,
            fetch_artifact_hash TEXT,
            media_lineage_id TEXT,
            status TEXT NOT NULL,
            not_evidence_reason TEXT,
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

        CREATE TABLE IF NOT EXISTS memory_sources (
            source_ref TEXT PRIMARY KEY,
            source_kind TEXT NOT NULL,
            source_type TEXT,
            source_uri TEXT,
            canonical_uri TEXT,
            source_title TEXT,
            source_owner TEXT,
            owner_scope TEXT,
            user_control_status TEXT,
            source_origin TEXT,
            lifecycle_status TEXT,
            upstream_ref TEXT,
            storage_ref_json TEXT,
            raw_hash TEXT,
            normalized_content_hash TEXT,
            relation_hash TEXT,
            media_hash TEXT,
            source_status TEXT NOT NULL,
            visibility TEXT NOT NULL,
            created_at TEXT,
            first_observed_at TEXT NOT NULL,
            last_observed_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            metadata_json TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS memory_source_observations (
            observation_id TEXT PRIMARY KEY,
            source_ref TEXT NOT NULL,
            observation_run_id TEXT NOT NULL,
            observation_kind TEXT NOT NULL,
            observation_completeness TEXT NOT NULL,
            provider_run_id TEXT,
            availability_status TEXT,
            raw_hash TEXT,
            normalized_content_hash TEXT,
            relation_hash TEXT,
            media_hash TEXT,
            fetched_at TEXT,
            observed_at TEXT NOT NULL,
            status TEXT NOT NULL,
            metadata_json TEXT NOT NULL,
            FOREIGN KEY(source_ref) REFERENCES memory_sources(source_ref)
        );

        CREATE TABLE IF NOT EXISTS memory_artifacts (
            artifact_id TEXT PRIMARY KEY,
            artifact_role TEXT NOT NULL,
            artifact_kind TEXT NOT NULL,
            artifact_scope TEXT,
            title TEXT,
            source_refs_json TEXT NOT NULL,
            content_ref TEXT,
            content_hash TEXT,
            authority_level TEXT NOT NULL,
            output_mode TEXT,
            retention_policy TEXT NOT NULL,
            artifact_status TEXT NOT NULL,
            created_by TEXT,
            builder_version TEXT,
            confidence REAL,
            expires_at TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            metadata_json TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS memory_artifact_links (
            link_id TEXT PRIMARY KEY,
            source_artifact_id TEXT NOT NULL,
            target_artifact_id TEXT NOT NULL,
            relation_type TEXT NOT NULL,
            link_status TEXT NOT NULL,
            created_at TEXT NOT NULL,
            metadata_json TEXT NOT NULL,
            FOREIGN KEY(source_artifact_id) REFERENCES memory_artifacts(artifact_id),
            FOREIGN KEY(target_artifact_id) REFERENCES memory_artifacts(artifact_id)
        );

        CREATE TABLE IF NOT EXISTS memory_participation_decisions (
            decision_id TEXT PRIMARY KEY,
            subject_kind TEXT NOT NULL DEFAULT '',
            source_ref TEXT,
            artifact_id TEXT,
            output_mode TEXT NOT NULL,
            policy_version TEXT NOT NULL DEFAULT 'knowledgeops-v1',
            severity TEXT NOT NULL DEFAULT 'info',
            can_search INTEGER NOT NULL,
            can_explore INTEGER NOT NULL,
            can_use_in_working_note INTEGER NOT NULL,
            can_use_as_evidence INTEGER NOT NULL,
            can_use_in_answer INTEGER NOT NULL,
            can_trigger_external_fetch INTEGER NOT NULL,
            reason TEXT NOT NULL,
            decided_by TEXT NOT NULL DEFAULT 'research_x.memory.participation',
            decided_at TEXT NOT NULL,
            input_hash_json TEXT NOT NULL DEFAULT '{}',
            metadata_json TEXT NOT NULL,
            FOREIGN KEY(source_ref) REFERENCES memory_sources(source_ref),
            FOREIGN KEY(artifact_id) REFERENCES memory_artifacts(artifact_id)
        );

        CREATE TABLE IF NOT EXISTS memory_projection_artifacts (
            projection_id TEXT PRIMARY KEY,
            projection_kind TEXT NOT NULL,
            artifact_id TEXT NOT NULL,
            source_refs_json TEXT NOT NULL,
            builder_version TEXT NOT NULL,
            input_hash_json TEXT NOT NULL,
            output_hash TEXT,
            projection_status TEXT NOT NULL,
            restore_path_json TEXT NOT NULL,
            generation_id TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            metadata_json TEXT NOT NULL,
            FOREIGN KEY(artifact_id) REFERENCES memory_artifacts(artifact_id),
            FOREIGN KEY(generation_id) REFERENCES memory_projection_generations(generation_id)
        );

        CREATE TABLE IF NOT EXISTS memory_reconciliation_runs (
            reconciliation_run_id TEXT PRIMARY KEY,
            reconciliation_scope TEXT NOT NULL,
            observation_completeness TEXT NOT NULL,
            status TEXT NOT NULL,
            started_at TEXT NOT NULL,
            finished_at TEXT,
            metadata_json TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS memory_reconciliation_items (
            reconciliation_item_id TEXT PRIMARY KEY,
            reconciliation_run_id TEXT NOT NULL,
            subject_kind TEXT NOT NULL,
            subject_id TEXT NOT NULL,
            action TEXT NOT NULL,
            reason TEXT NOT NULL,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL,
            metadata_json TEXT NOT NULL,
            FOREIGN KEY(reconciliation_run_id)
                REFERENCES memory_reconciliation_runs(reconciliation_run_id)
        );

        CREATE TABLE IF NOT EXISTS memory_working_notes (
            working_note_id TEXT PRIMARY KEY,
            task_scope TEXT NOT NULL,
            thread_scope TEXT,
            title TEXT NOT NULL,
            body TEXT NOT NULL,
            source_refs_json TEXT NOT NULL,
            artifact_refs_json TEXT NOT NULL,
            content_hash TEXT NOT NULL,
            retention_policy TEXT NOT NULL,
            note_status TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            expires_at TEXT,
            metadata_json TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS memory_audit_events (
            event_id TEXT PRIMARY KEY,
            event_type TEXT NOT NULL,
            subject_kind TEXT NOT NULL,
            subject_id TEXT NOT NULL,
            severity TEXT NOT NULL,
            message TEXT NOT NULL,
            created_at TEXT NOT NULL,
            metadata_json TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS memory_alert_sinks (
            sink_id TEXT PRIMARY KEY,
            sink_kind TEXT NOT NULL,
            sink_config_json TEXT NOT NULL,
            enabled INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            metadata_json TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS memory_alert_rules (
            rule_id TEXT PRIMARY KEY,
            event_type TEXT NOT NULL,
            sink_id TEXT NOT NULL,
            rule_status TEXT NOT NULL,
            threshold_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            metadata_json TEXT NOT NULL,
            FOREIGN KEY(sink_id) REFERENCES memory_alert_sinks(sink_id)
        );

        CREATE TABLE IF NOT EXISTS memory_alert_deliveries (
            delivery_id TEXT PRIMARY KEY,
            rule_id TEXT NOT NULL,
            sink_id TEXT NOT NULL,
            event_id TEXT NOT NULL,
            delivery_status TEXT NOT NULL,
            attempt_count INTEGER NOT NULL,
            last_error TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            metadata_json TEXT NOT NULL,
            FOREIGN KEY(rule_id) REFERENCES memory_alert_rules(rule_id),
            FOREIGN KEY(sink_id) REFERENCES memory_alert_sinks(sink_id),
            FOREIGN KEY(event_id) REFERENCES memory_audit_events(event_id)
        );

        CREATE TABLE IF NOT EXISTS memory_upstream_sources (
            upstream_source_id TEXT PRIMARY KEY,
            source_ref TEXT,
            upstream_kind TEXT NOT NULL,
            url TEXT NOT NULL,
            version TEXT,
            license TEXT,
            review_status TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            metadata_json TEXT NOT NULL,
            FOREIGN KEY(source_ref) REFERENCES memory_sources(source_ref)
        );

        CREATE TABLE IF NOT EXISTS memory_output_runs (
            output_run_id TEXT PRIMARY KEY,
            query TEXT NOT NULL,
            output_mode TEXT NOT NULL,
            status TEXT NOT NULL,
            started_at TEXT NOT NULL,
            finished_at TEXT,
            metadata_json TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS memory_output_items (
            output_item_id TEXT PRIMARY KEY,
            output_run_id TEXT NOT NULL,
            item_index INTEGER NOT NULL,
            artifact_id TEXT,
            artifact_role TEXT NOT NULL,
            authority_level TEXT NOT NULL,
            source_ref TEXT,
            text TEXT,
            created_at TEXT NOT NULL,
            metadata_json TEXT NOT NULL,
            FOREIGN KEY(output_run_id) REFERENCES memory_output_runs(output_run_id),
            FOREIGN KEY(artifact_id) REFERENCES memory_artifacts(artifact_id),
            FOREIGN KEY(source_ref) REFERENCES memory_sources(source_ref)
        );

        CREATE TABLE IF NOT EXISTS memory_claim_support_assessments (
            assessment_id TEXT PRIMARY KEY,
            output_run_id TEXT NOT NULL,
            claim_id TEXT NOT NULL,
            citation_id TEXT,
            support_status TEXT NOT NULL,
            support_score REAL,
            evidence_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            metadata_json TEXT NOT NULL,
            FOREIGN KEY(output_run_id) REFERENCES memory_output_runs(output_run_id)
        );

        CREATE TABLE IF NOT EXISTS memory_route_promotion_decisions (
            promotion_decision_id TEXT PRIMARY KEY,
            candidate_route_version TEXT NOT NULL,
            baseline_route_version TEXT,
            eval_run_ids_json TEXT NOT NULL,
            output_modes_json TEXT NOT NULL,
            status TEXT NOT NULL,
            thresholds_json TEXT NOT NULL,
            deltas_json TEXT NOT NULL,
            blocking_reasons_json TEXT NOT NULL,
            metadata_json TEXT NOT NULL,
            created_at TEXT NOT NULL
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

        CREATE TABLE IF NOT EXISTS memory_governance_records (
            record_id TEXT PRIMARY KEY,
            governance_type TEXT NOT NULL,
            subject_kind TEXT NOT NULL,
            subject_id TEXT NOT NULL,
            statement TEXT NOT NULL,
            status TEXT NOT NULL,
            confidence REAL NOT NULL,
            source_kind TEXT NOT NULL,
            source_id TEXT NOT NULL,
            source_url TEXT,
            source_hash TEXT,
            source_anchor_json TEXT NOT NULL,
            retention_policy TEXT NOT NULL,
            expires_at TEXT,
            supersedes_record_id TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
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
        CREATE INDEX IF NOT EXISTS idx_memory_eval_cases_suite
            ON memory_eval_cases(suite, created_at);
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
        CREATE INDEX IF NOT EXISTS idx_memory_fetch_artifacts_tool_call
            ON memory_fetch_artifacts(tool_call_id);
        CREATE INDEX IF NOT EXISTS idx_memory_fetch_artifacts_run
            ON memory_fetch_artifacts(run_id, fetched_at);
        CREATE INDEX IF NOT EXISTS idx_memory_fetch_artifacts_url
            ON memory_fetch_artifacts(final_url);
        CREATE INDEX IF NOT EXISTS idx_memory_fetch_artifacts_response_hash
            ON memory_fetch_artifacts(response_hash);
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
        CREATE INDEX IF NOT EXISTS idx_memory_provider_authorizations_scope
            ON memory_provider_authorizations(provider, model, operation, provider_role);
        CREATE INDEX IF NOT EXISTS idx_memory_provider_execution_scope
            ON memory_provider_execution_policies(provider, model, operation, provider_role);
        CREATE INDEX IF NOT EXISTS idx_memory_provider_preflights_run
            ON memory_provider_preflights(run_id, created_at);
        CREATE INDEX IF NOT EXISTS idx_memory_provider_transport_usage
            ON memory_provider_transport_events(api_usage_event_id);
        CREATE INDEX IF NOT EXISTS idx_memory_provider_transport_scope
            ON memory_provider_transport_events(provider, model, operation, started_at);
        CREATE INDEX IF NOT EXISTS idx_memory_query_transforms_parent
            ON memory_query_transforms(parent_query_id, transform_kind);
        CREATE INDEX IF NOT EXISTS idx_memory_retrieval_text_profiles_doc
            ON memory_retrieval_text_profiles(doc_id, retrieval_text_profile);
        CREATE INDEX IF NOT EXISTS idx_taxonomy_source_kind
            ON memory_document_taxonomy(source_kind);
        CREATE INDEX IF NOT EXISTS idx_taxonomy_ownership_kind
            ON memory_document_taxonomy(ownership_kind);
        CREATE INDEX IF NOT EXISTS idx_taxonomy_content_role
            ON memory_document_taxonomy(content_role);
        CREATE INDEX IF NOT EXISTS idx_taxonomy_relation_role
            ON memory_document_taxonomy(relation_role);
        CREATE INDEX IF NOT EXISTS idx_taxonomy_modality_kind
            ON memory_document_taxonomy(modality_kind);
        CREATE INDEX IF NOT EXISTS idx_taxonomy_sensitivity_kind
            ON memory_document_taxonomy(sensitivity_kind);
        CREATE INDEX IF NOT EXISTS idx_taxonomy_language
            ON memory_document_taxonomy(language);
        CREATE INDEX IF NOT EXISTS idx_taxonomy_author
            ON memory_document_taxonomy(author_id);
        CREATE INDEX IF NOT EXISTS idx_taxonomy_bookmark_owner
            ON memory_document_taxonomy(bookmark_owner_account_id);
        CREATE INDEX IF NOT EXISTS idx_taxonomy_tweet
            ON memory_document_taxonomy(tweet_id);
        CREATE INDEX IF NOT EXISTS idx_taxonomy_media
            ON memory_document_taxonomy(media_id);
        CREATE INDEX IF NOT EXISTS idx_taxonomy_embedding_eligible
            ON memory_document_taxonomy(embedding_eligible);
        CREATE INDEX IF NOT EXISTS idx_template_policies_profile
            ON memory_embedding_template_policies(projection_profile, target_space_id);
        CREATE INDEX IF NOT EXISTS idx_template_examples_doc
            ON memory_embedding_template_examples(doc_id, template_version);
        CREATE INDEX IF NOT EXISTS idx_projection_doc
            ON memory_embedding_projections(doc_id);
        CREATE INDEX IF NOT EXISTS idx_projection_profile
            ON memory_embedding_projections(projection_profile);
        CREATE INDEX IF NOT EXISTS idx_projection_target_space
            ON memory_embedding_projections(target_space_id);
        CREATE INDEX IF NOT EXISTS idx_projection_template_version
            ON memory_embedding_projections(text_template_version);
        CREATE INDEX IF NOT EXISTS idx_projection_source_hash
            ON memory_embedding_projections(source_doc_hash);
        CREATE INDEX IF NOT EXISTS idx_projection_embedded_text_hash
            ON memory_embedding_projections(embedded_text_hash);
        CREATE INDEX IF NOT EXISTS idx_projection_status
            ON memory_embedding_projections(projection_status);
        CREATE INDEX IF NOT EXISTS idx_projection_stale
            ON memory_embedding_projections(stale_status);
        CREATE INDEX IF NOT EXISTS idx_projection_readiness
            ON memory_embedding_projections(
                doc_id,
                classification_version,
                projection_status,
                stale_status
            );
        CREATE INDEX IF NOT EXISTS idx_memory_eval_gate_results_query
            ON memory_eval_gate_results(query, gate_name, created_at);
        CREATE INDEX IF NOT EXISTS idx_memory_projection_generations_kind
            ON memory_projection_generations(projection_kind, created_at);
        CREATE INDEX IF NOT EXISTS idx_memory_vector_indexes_space
            ON memory_vector_indexes(space_id, backend, created_at);
        CREATE INDEX IF NOT EXISTS idx_memory_retrieval_engine_runs_query
            ON memory_retrieval_engine_runs(query_id, engine_name, created_at);
        CREATE INDEX IF NOT EXISTS idx_memory_retrieval_candidates_engine
            ON memory_retrieval_candidates(engine_run_id, rank);
        CREATE INDEX IF NOT EXISTS idx_memory_retrieval_candidates_space
            ON memory_retrieval_candidates(space_id, restoration_status, stale_status);
        CREATE INDEX IF NOT EXISTS idx_memory_fusion_runs_query
            ON memory_fusion_runs(query_id, method, created_at);
        CREATE INDEX IF NOT EXISTS idx_memory_restoration_attempts_candidate
            ON memory_restoration_attempts(candidate_id, status);
        CREATE INDEX IF NOT EXISTS idx_memory_index_membership_generation
            ON memory_index_membership(generation_id, artifact_kind);
        CREATE INDEX IF NOT EXISTS idx_memory_sources_kind_status
            ON memory_sources(source_kind, source_status);
        CREATE INDEX IF NOT EXISTS idx_memory_sources_updated
            ON memory_sources(updated_at);
        CREATE INDEX IF NOT EXISTS idx_memory_source_observations_source
            ON memory_source_observations(source_ref, observed_at);
        CREATE INDEX IF NOT EXISTS idx_memory_source_observations_run
            ON memory_source_observations(observation_run_id, status);
        CREATE INDEX IF NOT EXISTS idx_memory_artifacts_role_kind
            ON memory_artifacts(artifact_role, artifact_kind);
        CREATE INDEX IF NOT EXISTS idx_memory_artifacts_output_mode
            ON memory_artifacts(output_mode, authority_level);
        CREATE INDEX IF NOT EXISTS idx_memory_artifact_links_source
            ON memory_artifact_links(source_artifact_id, relation_type);
        CREATE INDEX IF NOT EXISTS idx_memory_artifact_links_target
            ON memory_artifact_links(target_artifact_id, relation_type);
        CREATE INDEX IF NOT EXISTS idx_memory_participation_source
            ON memory_participation_decisions(source_ref, output_mode);
        CREATE INDEX IF NOT EXISTS idx_memory_participation_artifact
            ON memory_participation_decisions(artifact_id, output_mode);
        CREATE INDEX IF NOT EXISTS idx_memory_projection_artifacts_generation
            ON memory_projection_artifacts(generation_id, projection_kind);
        CREATE INDEX IF NOT EXISTS idx_memory_projection_artifacts_status
            ON memory_projection_artifacts(projection_status, updated_at);
        CREATE INDEX IF NOT EXISTS idx_memory_reconciliation_runs_status
            ON memory_reconciliation_runs(status, started_at);
        CREATE INDEX IF NOT EXISTS idx_memory_reconciliation_items_run
            ON memory_reconciliation_items(reconciliation_run_id, status);
        CREATE INDEX IF NOT EXISTS idx_memory_working_notes_scope
            ON memory_working_notes(task_scope, note_status);
        CREATE INDEX IF NOT EXISTS idx_memory_audit_events_type
            ON memory_audit_events(event_type, created_at);
        CREATE INDEX IF NOT EXISTS idx_memory_alert_rules_sink
            ON memory_alert_rules(sink_id, rule_status);
        CREATE INDEX IF NOT EXISTS idx_memory_alert_deliveries_status
            ON memory_alert_deliveries(delivery_status, updated_at);
        CREATE INDEX IF NOT EXISTS idx_memory_upstream_sources_ref
            ON memory_upstream_sources(source_ref, upstream_kind);
        CREATE INDEX IF NOT EXISTS idx_memory_output_runs_mode
            ON memory_output_runs(output_mode, started_at);
        CREATE INDEX IF NOT EXISTS idx_memory_output_items_run
            ON memory_output_items(output_run_id, item_index);
        CREATE INDEX IF NOT EXISTS idx_memory_output_items_source
            ON memory_output_items(source_ref, authority_level);
        CREATE INDEX IF NOT EXISTS idx_memory_claim_support_output
            ON memory_claim_support_assessments(output_run_id, support_status);
        CREATE INDEX IF NOT EXISTS idx_memory_route_promotion_status
            ON memory_route_promotion_decisions(status, created_at);
        CREATE INDEX IF NOT EXISTS idx_memory_route_promotion_candidate
            ON memory_route_promotion_decisions(candidate_route_version, status);
        CREATE INDEX IF NOT EXISTS idx_memory_security_boundaries_artifact
            ON memory_security_boundaries(artifact_kind, artifact_id);
        CREATE INDEX IF NOT EXISTS idx_memory_visual_recall_media
            ON memory_visual_recall_evidence(media_id, evidence_level);
        CREATE INDEX IF NOT EXISTS idx_memory_user_ranking_signals_subject
            ON memory_user_ranking_signals(subject_kind, subject_id, route_scope);
        CREATE INDEX IF NOT EXISTS idx_memory_governance_subject
            ON memory_governance_records(subject_kind, subject_id, status);
        CREATE INDEX IF NOT EXISTS idx_memory_governance_type_status
            ON memory_governance_records(governance_type, status, updated_at);
        CREATE INDEX IF NOT EXISTS idx_memory_governance_source
            ON memory_governance_records(source_kind, source_id);
        """
    )
    _migrate_memory_documents(conn)
    _ensure_memory_document_classification_trigger(conn)
    _backfill_memory_document_classification(conn)
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_memory_documents_classification
            ON memory_documents(
                source_kind, source_subkind, modality, embedding_eligibility
            )
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_memory_documents_embedding_filters
            ON memory_documents(embedding_eligibility, source_kind, language)
        """
    )
    _migrate_memory_feedback(conn)
    _migrate_memory_eval_results(conn)
    _migrate_memory_embeddings(conn)
    _migrate_memory_projection_generations(conn)
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_memory_projection_generations_space
            ON memory_projection_generations(space_id, projection_name, created_at)
        """
    )
    _migrate_memory_ocr(conn)
    _migrate_memory_fetch_artifacts(conn)
    _migrate_knowledgeops_schema(conn)
    _migrate_memory_participation_decisions(conn)
    _ensure_default_api_budget_policy(conn)
    _migrate_provider_preflights(conn)
    ensure_final_embedding_spaces(conn)
    _backfill_memory_embedding_space_ids(conn)
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
        CREATE INDEX IF NOT EXISTS idx_memory_embeddings_space
            ON memory_embeddings(space_id, generation_id, stale_status)
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_memory_embeddings_projection
            ON memory_embeddings(projection_id, projection_policy_version)
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
    classification_migrations = {
        "source_kind": (
            "ALTER TABLE memory_documents "
            "ADD COLUMN source_kind TEXT NOT NULL DEFAULT ''"
        ),
        "source_subkind": (
            "ALTER TABLE memory_documents "
            "ADD COLUMN source_subkind TEXT NOT NULL DEFAULT ''"
        ),
        "language": (
            "ALTER TABLE memory_documents "
            "ADD COLUMN language TEXT NOT NULL DEFAULT ''"
        ),
        "modality": (
            "ALTER TABLE memory_documents "
            "ADD COLUMN modality TEXT NOT NULL DEFAULT ''"
        ),
        "privacy_class": (
            "ALTER TABLE memory_documents "
            "ADD COLUMN privacy_class TEXT NOT NULL DEFAULT ''"
        ),
        "retention_class": (
            "ALTER TABLE memory_documents "
            "ADD COLUMN retention_class TEXT NOT NULL DEFAULT ''"
        ),
        "embedding_eligibility": (
            "ALTER TABLE memory_documents "
            "ADD COLUMN embedding_eligibility TEXT NOT NULL DEFAULT ''"
        ),
    }
    for column, sql in classification_migrations.items():
        if column not in columns:
            conn.execute(sql)
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


def _ensure_memory_document_classification_trigger(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TRIGGER IF NOT EXISTS trg_memory_documents_classification_defaults
        AFTER INSERT ON memory_documents
        BEGIN
            UPDATE memory_documents
            SET
                source_kind = CASE
                    WHEN NEW.source_kind IS NULL OR TRIM(NEW.source_kind) = ''
                    THEN CASE
                        WHEN NEW.doc_type = 'media_doc' THEN 'local_x_media'
                        WHEN NEW.doc_type IN (
                            'place_card',
                            'author_profile',
                            'ticker_event',
                            'topic_thread'
                        ) THEN 'local_derived'
                        ELSE 'local_x_db'
                    END
                    ELSE NEW.source_kind
                END,
                source_subkind = CASE
                    WHEN NEW.source_subkind IS NULL OR TRIM(NEW.source_subkind) = ''
                    THEN CASE NEW.doc_type
                        WHEN 'tweet_doc' THEN 'tweet_atomic'
                        WHEN 'bookmark_doc' THEN 'bookmark_context'
                        WHEN 'quote_tree_doc' THEN 'quote_relation'
                        WHEN 'media_doc' THEN 'media_caption_text'
                        WHEN 'ticker_event' THEN 'temporal_event_record'
                        WHEN 'topic_thread' THEN 'thread_context'
                        ELSE NEW.doc_type
                    END
                    ELSE NEW.source_subkind
                END,
                language = CASE
                    WHEN NEW.language IS NULL OR TRIM(NEW.language) = '' THEN 'und'
                    ELSE NEW.language
                END,
                modality = CASE
                    WHEN NEW.modality IS NULL OR TRIM(NEW.modality) = ''
                    THEN CASE
                        WHEN NEW.doc_type = 'media_doc' THEN 'text_from_media'
                        ELSE 'text'
                    END
                    ELSE NEW.modality
                END,
                privacy_class = CASE
                    WHEN NEW.privacy_class IS NULL OR TRIM(NEW.privacy_class) = ''
                    THEN 'user_private'
                    ELSE NEW.privacy_class
                END,
                retention_class = CASE
                    WHEN NEW.retention_class IS NULL OR TRIM(NEW.retention_class) = ''
                    THEN 'retain'
                    ELSE NEW.retention_class
                END,
                embedding_eligibility = CASE
                    WHEN NEW.embedding_eligibility IS NULL
                      OR TRIM(NEW.embedding_eligibility) = ''
                    THEN 'eligible'
                    ELSE NEW.embedding_eligibility
                END
            WHERE doc_id = NEW.doc_id;
        END;
        """
    )


def _backfill_memory_document_classification(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        UPDATE memory_documents
        SET
            source_kind = CASE
                WHEN source_kind IS NULL OR TRIM(source_kind) = ''
                THEN CASE
                    WHEN doc_type = 'media_doc' THEN 'local_x_media'
                    WHEN doc_type IN (
                        'place_card',
                        'author_profile',
                        'ticker_event',
                        'topic_thread'
                    ) THEN 'local_derived'
                    ELSE 'local_x_db'
                END
                ELSE source_kind
            END,
            source_subkind = CASE
                WHEN source_subkind IS NULL OR TRIM(source_subkind) = ''
                THEN CASE doc_type
                    WHEN 'tweet_doc' THEN 'tweet_atomic'
                    WHEN 'bookmark_doc' THEN 'bookmark_context'
                    WHEN 'quote_tree_doc' THEN 'quote_relation'
                    WHEN 'media_doc' THEN 'media_caption_text'
                    WHEN 'ticker_event' THEN 'temporal_event_record'
                    WHEN 'topic_thread' THEN 'thread_context'
                    ELSE doc_type
                END
                ELSE source_subkind
            END,
            language = CASE
                WHEN language IS NULL OR TRIM(language) = '' THEN 'und'
                ELSE language
            END,
            modality = CASE
                WHEN modality IS NULL OR TRIM(modality) = ''
                THEN CASE
                    WHEN doc_type = 'media_doc' THEN 'text_from_media'
                    ELSE 'text'
                END
                ELSE modality
            END,
            privacy_class = CASE
                WHEN privacy_class IS NULL OR TRIM(privacy_class) = ''
                THEN 'user_private'
                ELSE privacy_class
            END,
            retention_class = CASE
                WHEN retention_class IS NULL OR TRIM(retention_class) = ''
                THEN 'retain'
                ELSE retention_class
            END,
            embedding_eligibility = CASE
                WHEN embedding_eligibility IS NULL OR TRIM(embedding_eligibility) = ''
                THEN 'eligible'
                ELSE embedding_eligibility
            END
        WHERE source_kind IS NULL
           OR TRIM(source_kind) = ''
           OR source_subkind IS NULL
           OR TRIM(source_subkind) = ''
           OR language IS NULL
           OR TRIM(language) = ''
           OR modality IS NULL
           OR TRIM(modality) = ''
           OR privacy_class IS NULL
           OR TRIM(privacy_class) = ''
           OR retention_class IS NULL
           OR TRIM(retention_class) = ''
           OR embedding_eligibility IS NULL
           OR TRIM(embedding_eligibility) = ''
        """
    )


def _add_column_if_missing(
    conn: sqlite3.Connection,
    *,
    table: str,
    column: str,
    definition: str,
) -> None:
    columns = _column_names(conn, table)
    if column not in columns:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def _migrate_knowledgeops_schema(conn: sqlite3.Connection) -> None:
    additions = {
        "memory_documents": {
            "source_refs_json": "TEXT",
            "artifact_id": "TEXT",
            "projection_id": "TEXT",
            "projection_hash": "TEXT",
            "projection_builder_version": "TEXT",
            "restore_path_json": "TEXT",
            "lifecycle_status": "TEXT",
        },
        "memory_sources": {
            "source_type": "TEXT",
            "canonical_uri": "TEXT",
            "owner_scope": "TEXT",
            "user_control_status": "TEXT",
            "source_origin": "TEXT",
            "lifecycle_status": "TEXT",
            "upstream_ref": "TEXT",
            "storage_ref_json": "TEXT",
            "created_at": "TEXT",
        },
        "memory_source_observations": {
            "provider_run_id": "TEXT",
            "availability_status": "TEXT",
            "relation_hash": "TEXT",
            "media_hash": "TEXT",
            "fetched_at": "TEXT",
        },
        "memory_artifacts": {
            "artifact_scope": "TEXT",
            "title": "TEXT",
            "content_ref": "TEXT",
            "created_by": "TEXT",
            "builder_version": "TEXT",
            "confidence": "REAL",
            "expires_at": "TEXT",
        },
    }
    for table, columns in additions.items():
        for column, definition in columns.items():
            _add_column_if_missing(conn, table=table, column=column, definition=definition)
    if conn.in_transaction:
        conn.commit()


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


def _migrate_memory_eval_results(conn: sqlite3.Connection) -> None:
    columns = _column_names(conn, "memory_eval_results")
    migrations = {
        "workflow_id": "ALTER TABLE memory_eval_results ADD COLUMN workflow_id TEXT",
        "context_run_id": "ALTER TABLE memory_eval_results ADD COLUMN context_run_id TEXT",
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
        "space_id",
    ]
    if (
        {"embedding_profile", "text_template_version", "source_doc_hash"}.issubset(columns)
        and _primary_key_columns(conn, "memory_embeddings") == expected_pk
    ):
        _migrate_memory_embedding_final_columns(conn)
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
    space_id_expr = "COALESCE(space_id, '')" if "space_id" in columns else "''"

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
            embedding_id TEXT,
            space_id TEXT NOT NULL DEFAULT '',
            generation_id TEXT,
            projection_id TEXT,
            projection_policy_version TEXT,
            classification_version TEXT,
            target_space_id TEXT,
            chunk_id TEXT,
            media_id TEXT,
            fetch_artifact_id TEXT,
            embedded_input_hash TEXT,
            vector_ref TEXT,
            token_count INTEGER,
            provider_request_id TEXT,
            api_usage_event_id TEXT,
            stale_status TEXT NOT NULL DEFAULT 'current',
            PRIMARY KEY(
                doc_id, provider, model, dimensions,
                embedding_profile, text_template_version, space_id
            )
        );

        """
    )
    conn.execute(
        f"""
        INSERT OR REPLACE INTO memory_embeddings (
            doc_id, provider, model, dimensions, embedding_profile, text_template_version,
            embedding, source_doc_hash, embedded_text_hash, created_at, updated_at, space_id
        )
        SELECT
            doc_id, provider, model, dimensions,
            {embedding_profile_expr}, {text_template_expr},
            embedding, {source_doc_hash_expr}, embedded_text_hash, created_at, updated_at,
            {space_id_expr}
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
    _migrate_memory_embedding_final_columns(conn)


def _migrate_memory_embedding_final_columns(conn: sqlite3.Connection) -> None:
    columns = _column_names(conn, "memory_embeddings")
    migrations = {
        "embedding_id": "ALTER TABLE memory_embeddings ADD COLUMN embedding_id TEXT",
        "space_id": (
            "ALTER TABLE memory_embeddings "
            "ADD COLUMN space_id TEXT NOT NULL DEFAULT ''"
        ),
        "generation_id": "ALTER TABLE memory_embeddings ADD COLUMN generation_id TEXT",
        "projection_id": "ALTER TABLE memory_embeddings ADD COLUMN projection_id TEXT",
        "projection_policy_version": (
            "ALTER TABLE memory_embeddings ADD COLUMN projection_policy_version TEXT"
        ),
        "classification_version": (
            "ALTER TABLE memory_embeddings ADD COLUMN classification_version TEXT"
        ),
        "target_space_id": "ALTER TABLE memory_embeddings ADD COLUMN target_space_id TEXT",
        "chunk_id": "ALTER TABLE memory_embeddings ADD COLUMN chunk_id TEXT",
        "media_id": "ALTER TABLE memory_embeddings ADD COLUMN media_id TEXT",
        "fetch_artifact_id": "ALTER TABLE memory_embeddings ADD COLUMN fetch_artifact_id TEXT",
        "embedded_input_hash": "ALTER TABLE memory_embeddings ADD COLUMN embedded_input_hash TEXT",
        "vector_ref": "ALTER TABLE memory_embeddings ADD COLUMN vector_ref TEXT",
        "token_count": "ALTER TABLE memory_embeddings ADD COLUMN token_count INTEGER",
        "provider_request_id": (
            "ALTER TABLE memory_embeddings ADD COLUMN provider_request_id TEXT"
        ),
        "api_usage_event_id": (
            "ALTER TABLE memory_embeddings ADD COLUMN api_usage_event_id TEXT"
        ),
        "stale_status": (
            "ALTER TABLE memory_embeddings "
            "ADD COLUMN stale_status TEXT NOT NULL DEFAULT 'current'"
        ),
    }
    for column, sql in migrations.items():
        if column not in columns:
            conn.execute(sql)
    conn.execute(
        """
        UPDATE memory_embeddings
        SET embedded_input_hash = embedded_text_hash
        WHERE embedded_input_hash IS NULL
           OR TRIM(embedded_input_hash) = ''
        """
    )
    conn.execute(
        """
        UPDATE memory_embeddings
        SET stale_status = 'current'
        WHERE stale_status IS NULL
           OR TRIM(stale_status) = ''
        """
    )


def _migrate_memory_projection_generations(conn: sqlite3.Connection) -> None:
    columns = _column_names(conn, "memory_projection_generations")
    migrations = {
        "space_id": "ALTER TABLE memory_projection_generations ADD COLUMN space_id TEXT",
        "projection_name": (
            "ALTER TABLE memory_projection_generations ADD COLUMN projection_name TEXT"
        ),
        "projection_version": (
            "ALTER TABLE memory_projection_generations ADD COLUMN projection_version TEXT"
        ),
        "selection_policy": (
            "ALTER TABLE memory_projection_generations ADD COLUMN selection_policy TEXT"
        ),
        "source_query": "ALTER TABLE memory_projection_generations ADD COLUMN source_query TEXT",
        "source_count": (
            "ALTER TABLE memory_projection_generations "
            "ADD COLUMN source_count INTEGER NOT NULL DEFAULT 0"
        ),
        "projected_count": (
            "ALTER TABLE memory_projection_generations "
            "ADD COLUMN projected_count INTEGER NOT NULL DEFAULT 0"
        ),
        "skipped_count": (
            "ALTER TABLE memory_projection_generations "
            "ADD COLUMN skipped_count INTEGER NOT NULL DEFAULT 0"
        ),
        "stale_policy": "ALTER TABLE memory_projection_generations ADD COLUMN stale_policy TEXT",
        "code_commit": "ALTER TABLE memory_projection_generations ADD COLUMN code_commit TEXT",
        "run_id": "ALTER TABLE memory_projection_generations ADD COLUMN run_id TEXT",
    }
    for column, sql in migrations.items():
        if column not in columns:
            conn.execute(sql)


def _backfill_memory_embedding_space_ids(conn: sqlite3.Connection) -> None:
    rows = conn.execute(
        """
        SELECT
            doc_id, provider, model, dimensions, embedding_profile,
            text_template_version, embedded_text_hash, embedding_id,
            space_id, generation_id
        FROM memory_embeddings
        WHERE space_id IS NULL
           OR TRIM(space_id) = ''
           OR generation_id IS NULL
           OR TRIM(generation_id) = ''
           OR embedding_id IS NULL
           OR TRIM(embedding_id) = ''
        """
    ).fetchall()
    if not rows:
        return
    now = _utc_now_for_schema()
    by_space: dict[str, list[tuple[object, ...]]] = {}
    for row in rows:
        provider = str(row[1])
        model = str(row[2])
        dimensions = int(row[3])
        embedding_profile = str(row[4] or "general_memory")
        text_template_version = str(row[5] or "memory-doc-embedding-v1")
        space_id = str(row[8] or "").strip() or ensure_embedding_space_for_spec(
            conn,
            provider=provider,
            model=model,
            dimensions=dimensions,
            embedding_profile=embedding_profile,
            text_template_version=text_template_version,
            modality="text",
            document_scope="memory_documents",
            source_kind_filter="local_x_text",
            language_filter="any",
            storage_rights_policy="local-db-derived-text",
            provider_role="text_embedding",
            status="active",
            notes="Backfilled from existing memory_embeddings rows.",
        )
        by_space.setdefault(space_id, []).append(row)
    for space_id, space_rows in by_space.items():
        generation_id = f"embproj-backfill-{_stable_schema_id(space_id)}"
        conn.execute(
            """
            INSERT OR IGNORE INTO memory_projection_generations (
                generation_id, projection_kind, space_id, projection_name,
                projection_version, selection_policy, source_query, source_scope,
                builder_version, input_manifest_json, status, coverage_json,
                source_count, projected_count, skipped_count, stale_policy,
                code_commit, run_id, created_at, metadata_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                generation_id,
                "embedding_input_projection",
                space_id,
                "legacy_embedding_input",
                "backfill-v1",
                "existing_rows",
                None,
                "memory_documents",
                "schema-backfill-v1",
                "{}",
                "current",
                "{}",
                len(space_rows),
                len(space_rows),
                0,
                "source_or_input_hash_change_marks_stale",
                None,
                None,
                now,
                '{"contract":"backfilled_projection_for_existing_embedding_rows"}',
            ),
        )
        for row in space_rows:
            embedding_id = str(row[7] or "").strip() or _stable_schema_id(
                "embedding",
                row[0],
                row[1],
                row[2],
                row[3],
                row[4],
                row[5],
                space_id,
            )
            conn.execute(
                """
                UPDATE memory_embeddings
                SET
                    embedding_id = COALESCE(NULLIF(embedding_id, ''), ?),
                    space_id = COALESCE(NULLIF(space_id, ''), ?),
                    generation_id = COALESCE(NULLIF(generation_id, ''), ?),
                    embedded_input_hash = COALESCE(
                        NULLIF(embedded_input_hash, ''),
                        embedded_text_hash
                    ),
                    stale_status = COALESCE(NULLIF(stale_status, ''), 'current')
                WHERE doc_id = ?
                  AND provider = ?
                  AND model = ?
                  AND dimensions = ?
                  AND embedding_profile = ?
                  AND text_template_version = ?
                  AND COALESCE(NULLIF(space_id, ''), ?) = ?
                """,
                (
                    embedding_id,
                    space_id,
                    generation_id,
                    row[0],
                    row[1],
                    row[2],
                    row[3],
                    row[4],
                    row[5],
                    space_id,
                    space_id,
                ),
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


def _migrate_provider_preflights(conn: sqlite3.Connection) -> None:
    columns = _column_names(conn, "memory_provider_preflights")
    migrations = {
        "provider_policy_required": (
            "ALTER TABLE memory_provider_preflights "
            "ADD COLUMN provider_policy_required INTEGER NOT NULL DEFAULT 1"
        ),
        "provider_policy_status": (
            "ALTER TABLE memory_provider_preflights "
            "ADD COLUMN provider_policy_status TEXT NOT NULL "
            "DEFAULT 'provider_execution_policy_required'"
        ),
    }
    for column, sql in migrations.items():
        if column not in columns:
            conn.execute(sql)


def _migrate_memory_fetch_artifacts(conn: sqlite3.Connection) -> None:
    columns = _column_names(conn, "memory_fetch_artifacts")
    migrations = {
        "tool_call_id": (
            "ALTER TABLE memory_fetch_artifacts "
            "ADD COLUMN tool_call_id TEXT NOT NULL DEFAULT ''"
        ),
        "run_id": "ALTER TABLE memory_fetch_artifacts ADD COLUMN run_id TEXT",
        "requested_url": (
            "ALTER TABLE memory_fetch_artifacts "
            "ADD COLUMN requested_url TEXT NOT NULL DEFAULT ''"
        ),
        "final_url": (
            "ALTER TABLE memory_fetch_artifacts "
            "ADD COLUMN final_url TEXT NOT NULL DEFAULT ''"
        ),
        "fetched_at": (
            "ALTER TABLE memory_fetch_artifacts "
            "ADD COLUMN fetched_at TEXT NOT NULL DEFAULT ''"
        ),
        "retrieved_at": (
            "ALTER TABLE memory_fetch_artifacts "
            "ADD COLUMN retrieved_at TEXT NOT NULL DEFAULT ''"
        ),
        "content_type": "ALTER TABLE memory_fetch_artifacts ADD COLUMN content_type TEXT",
        "status_code": "ALTER TABLE memory_fetch_artifacts ADD COLUMN status_code INTEGER",
        "response_hash": (
            "ALTER TABLE memory_fetch_artifacts "
            "ADD COLUMN response_hash TEXT NOT NULL DEFAULT ''"
        ),
        "extracted_text_hash": (
            "ALTER TABLE memory_fetch_artifacts "
            "ADD COLUMN extracted_text_hash TEXT NOT NULL DEFAULT ''"
        ),
        "raw_artifact_path": "ALTER TABLE memory_fetch_artifacts ADD COLUMN raw_artifact_path TEXT",
        "prompt_injection_review": (
            "ALTER TABLE memory_fetch_artifacts "
            "ADD COLUMN prompt_injection_review TEXT NOT NULL DEFAULT 'deterministic-v1'"
        ),
        "prompt_injection_status": (
            "ALTER TABLE memory_fetch_artifacts "
            "ADD COLUMN prompt_injection_status TEXT NOT NULL DEFAULT 'not_reviewed'"
        ),
        "prompt_injection_flags_json": (
            "ALTER TABLE memory_fetch_artifacts "
            "ADD COLUMN prompt_injection_flags_json TEXT NOT NULL DEFAULT '[]'"
        ),
        "storage_rights": (
            "ALTER TABLE memory_fetch_artifacts "
            "ADD COLUMN storage_rights TEXT NOT NULL DEFAULT 'unknown'"
        ),
        "fetch_provider": (
            "ALTER TABLE memory_fetch_artifacts "
            "ADD COLUMN fetch_provider TEXT NOT NULL DEFAULT ''"
        ),
        "metadata_json": (
            "ALTER TABLE memory_fetch_artifacts "
            "ADD COLUMN metadata_json TEXT NOT NULL DEFAULT '{}'"
        ),
    }
    for column, sql in migrations.items():
        if column not in columns:
            conn.execute(sql)


def _migrate_memory_participation_decisions(conn: sqlite3.Connection) -> None:
    columns = _column_names(conn, "memory_participation_decisions")
    migrations = {
        "subject_kind": (
            "ALTER TABLE memory_participation_decisions "
            "ADD COLUMN subject_kind TEXT NOT NULL DEFAULT ''"
        ),
        "policy_version": (
            "ALTER TABLE memory_participation_decisions "
            "ADD COLUMN policy_version TEXT NOT NULL DEFAULT 'knowledgeops-v1'"
        ),
        "severity": (
            "ALTER TABLE memory_participation_decisions "
            "ADD COLUMN severity TEXT NOT NULL DEFAULT 'info'"
        ),
        "decided_by": (
            "ALTER TABLE memory_participation_decisions ADD COLUMN decided_by "
            "TEXT NOT NULL DEFAULT 'research_x.memory.participation'"
        ),
        "input_hash_json": (
            "ALTER TABLE memory_participation_decisions "
            "ADD COLUMN input_hash_json TEXT NOT NULL DEFAULT '{}'"
        ),
    }
    for column, sql in migrations.items():
        if column not in columns:
            conn.execute(sql)
    if conn.in_transaction:
        conn.commit()
    while True:
        rowids = [
            int(row[0])
            for row in conn.execute(
                """
                SELECT rowid
                FROM memory_participation_decisions
                WHERE subject_kind = ''
                LIMIT 500
                """
            ).fetchall()
        ]
        if not rowids:
            break
        placeholders = ",".join("?" for _ in rowids)
        conn.execute(
            f"""
            UPDATE memory_participation_decisions
            SET subject_kind = CASE
                WHEN source_ref IS NOT NULL THEN 'source'
                WHEN artifact_id IS NOT NULL THEN 'artifact'
                ELSE subject_kind
            END
            WHERE rowid IN ({placeholders})
            """,
            rowids,
        )
        if conn.in_transaction:
            conn.commit()


def _column_names(conn: sqlite3.Connection, table: str) -> set[str]:
    return {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def _primary_key_columns(conn: sqlite3.Connection, table: str) -> list[str]:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    keyed = [(int(row[5]), str(row[1])) for row in rows if int(row[5]) > 0]
    return [name for _, name in sorted(keyed)]


def _stable_schema_id(*parts: object) -> str:
    raw = "\0".join(str(part) for part in parts).encode()
    return hashlib.sha256(raw).hexdigest()[:24]


def _utc_now_for_schema() -> str:
    from datetime import UTC, datetime

    return datetime.now(tz=UTC).isoformat()


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
