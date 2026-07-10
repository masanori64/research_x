from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from research_x.cli import main
from research_x.memory import portfolio as memory_portfolio
from research_x.memory.context import build_context_bundle
from research_x.memory.embedding_spaces import (
    DEFAULT_TEXT_DIMENSIONS,
    DEFAULT_TEXT_MODEL,
    DEFAULT_TEXT_PROVIDER,
    FINAL_EMBEDDING_SPACE_IDS,
    embedding_space_id_for_identity,
    ensure_embedding_space_for_spec,
    list_embedding_space_rows,
    plan_embedding_spaces,
)
from research_x.memory.embeddings import (
    DEFAULT_EMBEDDING_PROFILE,
    DEFAULT_TEXT_TEMPLATE_VERSION,
    LOCAL_HASH_MODEL,
    build_memory_embeddings,
    embedding_coverage_report,
    semantic_search_memory,
)
from research_x.memory.evals import EvalCase, run_memory_eval, store_memory_eval_results
from research_x.memory.schema import ensure_memory_schema
from research_x.memory.vector_projection import (
    build_vector_projection,
    search_vector_projection,
    vector_projection_coverage,
)


def test_final_embedding_spaces_register_and_cli_lists(
    vector_db_path: Path,
    capsys,
) -> None:
    with sqlite3.connect(vector_db_path) as conn:
        ensure_memory_schema(conn)

    report = plan_embedding_spaces(vector_db_path)
    rows = list_embedding_space_rows(vector_db_path)
    registered_ids = {row["space_id"] for row in rows}

    assert report.status == "ready"
    assert set(FINAL_EMBEDDING_SPACE_IDS).issubset(registered_ids)
    assert (
        main(
            [
                "memory",
                "embedding-spaces",
                "list",
                "--db",
                str(vector_db_path),
                "--json",
            ]
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)
    assert {row["space_id"] for row in payload}.issuperset(FINAL_EMBEDDING_SPACE_IDS)


def test_embedding_space_identity_changes_with_provider_model_dimension() -> None:
    base_identity = {
        "provider": DEFAULT_TEXT_PROVIDER,
        "model": DEFAULT_TEXT_MODEL,
        "dimensions": DEFAULT_TEXT_DIMENSIONS,
        "distance_metric": "cosine",
        "embedding_profile": "general_memory",
        "text_template_version": "memory-doc-embedding-v1",
        "modality": "text",
        "document_scope": "memory_documents",
        "source_kind_filter": "local_x_text",
        "language_filter": "any",
        "storage_rights_policy": "local-db-derived-text",
        "provider_role": "text_embedding",
    }
    changed_identity = {
        **base_identity,
        "provider": "local_hash",
        "model": "local-hash-v1",
        "dimensions": 32,
    }

    assert embedding_space_id_for_identity(base_identity) == "text.general_memory.v1"
    assert embedding_space_id_for_identity(changed_identity) != "text.general_memory.v1"


def test_build_embeddings_writes_space_and_generation_lineage(
    vector_db_path: Path,
) -> None:
    summary = build_memory_embeddings(vector_db_path, provider="local_hash", dimensions=32)
    coverage = embedding_coverage_report(
        vector_db_path,
        space_id=summary.space_id,
    )

    assert summary.space_id.startswith("text.general_memory.v1.space-")
    assert summary.generation_id
    assert coverage.space_id == summary.space_id
    with sqlite3.connect(vector_db_path) as conn:
        row = conn.execute(
            """
            SELECT
                COUNT(*),
                COUNT(DISTINCT space_id),
                COUNT(DISTINCT generation_id),
                SUM(CASE WHEN embedded_input_hash = embedded_text_hash THEN 1 ELSE 0 END),
                SUM(CASE WHEN stale_status = 'current' THEN 1 ELSE 0 END)
            FROM memory_embeddings
            WHERE space_id = ?
            """,
            (summary.space_id,),
        ).fetchone()

    assert row == (2, 1, 1, 2, 2)


def test_vector_index_build_records_space_registry(
    vector_db_path: Path,
    tmp_path: Path,
    capsys,
) -> None:
    embedding_summary = build_memory_embeddings(
        vector_db_path,
        provider="local_hash",
        dimensions=32,
    )
    assert (
        main(
            [
                "memory",
                "vector-index",
                "build",
                "--db",
                str(vector_db_path),
                "--space-id",
                embedding_summary.space_id,
                "--out-dir",
                str(tmp_path / "indexes"),
                "--json",
            ]
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)
    coverage = vector_projection_coverage(
        vector_db_path,
        space_id=embedding_summary.space_id,
    )

    assert payload["space_id"] == embedding_summary.space_id
    assert coverage.space_id == embedding_summary.space_id
    assert coverage.status == "ok"
    with sqlite3.connect(vector_db_path) as conn:
        row = conn.execute(
            """
            SELECT space_id, backend, vector_count, status
            FROM memory_vector_indexes
            WHERE build_generation_id = ?
            """,
            (payload["generation_id"],),
        ).fetchone()

    assert row == (embedding_summary.space_id, "numpy", 2, "current")


def test_build_vector_projection_allows_explicit_partial_stage_artifact(
    vector_db_path: Path,
    tmp_path: Path,
    capsys,
) -> None:
    embedding_summary = build_memory_embeddings(
        vector_db_path,
        provider="local_hash",
        dimensions=32,
        limit=1,
    )

    rejected = main(
        [
            "memory",
            "build-vector-projection",
            "--db",
            str(vector_db_path),
            "--space-id",
            embedding_summary.space_id,
            "--out-dir",
            str(tmp_path / "rejected-indexes"),
            "--json",
        ]
    )
    rejected_output = capsys.readouterr()

    assert rejected != 0
    assert "incomplete or stale embeddings: 1/2" in rejected_output.err

    assert (
        main(
            [
                "memory",
                "build-vector-projection",
                "--db",
                str(vector_db_path),
                "--space-id",
                embedding_summary.space_id,
                "--out-dir",
                str(tmp_path / "partial-indexes"),
                "--allow-partial",
                "--json",
            ]
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)
    coverage = vector_projection_coverage(
        vector_db_path,
        generation_id=payload["generation_id"],
    )

    assert payload["documents"] == 1
    assert payload["expected_documents"] == 2
    assert payload["missing_documents"] == 1
    assert payload["status"] == "partial"
    assert payload["production_eligible"] is False
    assert payload["not_evidence"] is True
    assert coverage.status == "partial"
    assert coverage.partial is True
    assert coverage.current_memberships == 1
    assert coverage.missing_memberships == 1
    assert coverage.production_eligible is False
    assert coverage.not_evidence is True
    with sqlite3.connect(vector_db_path) as conn:
        projection_row = conn.execute(
            """
            SELECT status, selection_policy, source_count, projected_count,
                   skipped_count, coverage_json, metadata_json
            FROM memory_projection_generations
            WHERE generation_id = ?
            """,
            (payload["generation_id"],),
        ).fetchone()
        index_row = conn.execute(
            """
            SELECT vector_count, status
            FROM memory_vector_indexes
            WHERE build_generation_id = ?
            """,
            (payload["generation_id"],),
        ).fetchone()

    metadata = json.loads(projection_row[6])
    coverage_json_payload = json.loads(projection_row[5])
    assert projection_row[:5] == (
        "partial",
        "partial_current_embeddings_explicit",
        2,
        1,
        1,
    )
    assert index_row == (1, "partial")
    assert metadata["partial"] is True
    assert metadata["production_eligible"] is False
    assert metadata["production_eligible_reason"] == "partial_projection"
    assert metadata["not_evidence"] is True
    assert metadata["evidence_role"] == "candidate_signal_not_evidence"
    assert coverage_json_payload["missing"] == 1
    assert coverage_json_payload["partial"] is True


def test_schema_backfills_missing_space_id_before_vector_projection(
    vector_db_path: Path,
    tmp_path: Path,
) -> None:
    summary = build_memory_embeddings(vector_db_path, provider="local_hash", dimensions=32)
    with sqlite3.connect(vector_db_path) as conn:
        conn.execute("UPDATE memory_embeddings SET space_id = ''")
        ensure_memory_schema(conn)
        count = conn.execute(
            """
            SELECT COUNT(*)
            FROM memory_embeddings
            WHERE space_id IS NULL OR TRIM(space_id) = ''
            """
        ).fetchone()[0]

    rebuilt = build_vector_projection(
        vector_db_path,
        space_id=summary.space_id,
        out_dir=tmp_path / "indexes",
    )

    assert count == 0
    assert rebuilt.space_id == summary.space_id


def test_semantic_search_requires_space_when_one_spec_has_multiple_spaces(
    vector_db_path: Path,
) -> None:
    summary = build_memory_embeddings(vector_db_path, provider="local_hash", dimensions=32)
    _copy_embeddings_into_alternate_space(vector_db_path, source_space_id=summary.space_id)

    with pytest.raises(RuntimeError, match="multiple embedding spaces"):
        semantic_search_memory(
            vector_db_path,
            "robot paper",
            provider="local_hash",
            dimensions=32,
        )

    hits = semantic_search_memory(
        vector_db_path,
        "robot paper",
        space_id=summary.space_id,
        provider="local_hash",
        dimensions=32,
    )

    assert hits
    assert {hit.space_id for hit in hits} == {summary.space_id}


def test_vector_projection_requires_space_when_one_spec_has_multiple_spaces(
    vector_db_path: Path,
    tmp_path: Path,
) -> None:
    summary = build_memory_embeddings(vector_db_path, provider="local_hash", dimensions=32)
    alt_space_id = _copy_embeddings_into_alternate_space(
        vector_db_path,
        source_space_id=summary.space_id,
    )
    first = build_vector_projection(
        vector_db_path,
        space_id=summary.space_id,
        out_dir=tmp_path / "first",
    )
    second = build_vector_projection(
        vector_db_path,
        space_id=alt_space_id,
        out_dir=tmp_path / "second",
    )

    with pytest.raises(RuntimeError, match="multiple embedding spaces"):
        search_vector_projection(
            vector_db_path,
            "robot paper",
            provider="local_hash",
            dimensions=32,
        )
    with pytest.raises(RuntimeError, match="not found"):
        search_vector_projection(
            vector_db_path,
            "robot paper",
            generation_id=second.generation_id,
            space_id=first.space_id,
        )


def test_schema_backfills_lineage_per_space_for_same_legacy_identity(
    vector_db_path: Path,
) -> None:
    summary = build_memory_embeddings(vector_db_path, provider="local_hash", dimensions=32)
    alt_space_id = _copy_embeddings_into_alternate_space(
        vector_db_path,
        source_space_id=summary.space_id,
    )
    with sqlite3.connect(vector_db_path) as conn:
        conn.execute(
            """
            UPDATE memory_embeddings
            SET generation_id = '', embedding_id = ''
            WHERE space_id IN (?, ?)
            """,
            (summary.space_id, alt_space_id),
        )
        ensure_memory_schema(conn)
        generations = conn.execute(
            """
            SELECT space_id, COUNT(DISTINCT generation_id)
            FROM memory_embeddings
            WHERE space_id IN (?, ?)
            GROUP BY space_id
            """,
            (summary.space_id, alt_space_id),
        ).fetchall()
        doc_lineage = conn.execute(
            """
            SELECT doc_id, COUNT(DISTINCT embedding_id), COUNT(DISTINCT generation_id)
            FROM memory_embeddings
            WHERE space_id IN (?, ?)
            GROUP BY doc_id
            """,
            (summary.space_id, alt_space_id),
        ).fetchall()

    assert dict(generations) == {summary.space_id: 1, alt_space_id: 1}
    assert all(row[1] == 2 and row[2] == 2 for row in doc_lineage)


def test_context_store_records_typed_retrieval_trace_rows(
    vector_db_path: Path,
) -> None:
    summary = build_memory_embeddings(vector_db_path, provider="local_hash", dimensions=32)
    bundle = build_context_bundle(
        vector_db_path,
        "robot paper",
        limit=2,
        semantic_provider="local_hash",
        semantic_space_id=summary.space_id,
        semantic_dimensions=32,
        store=True,
    )

    with sqlite3.connect(vector_db_path) as conn:
        semantic_candidate = conn.execute(
            """
            SELECT space_id, restoration_status, stale_status, not_evidence_reason
            FROM memory_retrieval_candidates
            WHERE space_id = ?
            LIMIT 1
            """,
            (summary.space_id,),
        ).fetchone()
        engine_runs = conn.execute(
            """
            SELECT COUNT(*)
            FROM memory_retrieval_engine_runs
            WHERE query_id = ?
            """,
            (bundle.run_id,),
        ).fetchone()[0]
        fusion_runs = conn.execute(
            """
            SELECT COUNT(*)
            FROM memory_fusion_runs
            WHERE query_id = ?
            """,
            (bundle.run_id,),
        ).fetchone()[0]
        fusion_method = conn.execute(
            """
            SELECT method
            FROM memory_fusion_runs
            WHERE query_id = ?
            """,
            (bundle.run_id,),
        ).fetchone()[0]
        restoration_attempts = conn.execute(
            """
            SELECT COUNT(*)
            FROM memory_restoration_attempts
            WHERE candidate_id IN (
                SELECT candidate_id
                FROM memory_retrieval_candidates
                WHERE engine_run_id IN (
                    SELECT engine_run_id
                    FROM memory_retrieval_engine_runs
                    WHERE query_id = ?
                )
            )
            """,
            (bundle.run_id,),
        ).fetchone()[0]

    assert semantic_candidate is not None
    assert semantic_candidate[0] == summary.space_id
    assert semantic_candidate[1] == "restored"
    assert semantic_candidate[2] == "current"
    assert semantic_candidate[3] == "source_bundle_context_citation_required"
    assert engine_runs >= 1
    assert fusion_runs == 1
    assert fusion_method == "hybrid_additive_rank_with_rrf"
    assert restoration_attempts >= 1


def test_stored_eval_links_to_typed_retrieval_trace_rows(
    vector_db_path: Path,
) -> None:
    summary = build_memory_embeddings(vector_db_path, provider="local_hash", dimensions=32)
    results = run_memory_eval(
        vector_db_path,
        cases=(EvalCase(query="robot paper", required_any_terms=("robot",)),),
        limit=2,
        semantic_provider="local_hash",
        semantic_space_id=summary.space_id,
        semantic_dimensions=32,
        answer_provider="none",
        store_workflows=True,
    )
    run_id = store_memory_eval_results(
        vector_db_path,
        results,
        parameters={
            "semantic_provider": "local_hash",
            "semantic_space_id": summary.space_id,
            "semantic_dimensions": 32,
        },
    )

    with sqlite3.connect(vector_db_path) as conn:
        row = conn.execute(
            """
            SELECT workflow_id, context_run_id
            FROM memory_eval_results
            WHERE run_id = ?
            """,
            (run_id,),
        ).fetchone()
        assert row is not None
        engine_runs = conn.execute(
            """
            SELECT COUNT(*)
            FROM memory_retrieval_engine_runs
            WHERE query_id = ?
            """,
            (row[1],),
        ).fetchone()[0]
        candidates = conn.execute(
            """
            SELECT COUNT(*)
            FROM memory_retrieval_candidates
            WHERE space_id = ?
            """,
            (summary.space_id,),
        ).fetchone()[0]

    assert row[0]
    assert row[1]
    assert engine_runs >= 1
    assert candidates >= 1


def test_portfolio_fusion_contributions_preserve_space_id() -> None:
    hit = {
        "doc_id": "doc-1",
        "doc_type": "tweet_doc",
        "tweet_id": "tweet-1",
        "score": 1.0,
        "title": "robot paper",
        "compact_text": "robot paper",
        "metadata": {},
        "evidence": {},
    }
    arm_a = _portfolio_arm("semantic-a", space_id="text.general_memory.v1")
    arm_b = _portfolio_arm("semantic-b", space_id="text.jp_multilingual.v1")

    fused = memory_portfolio._fuse_hits(  # noqa: SLF001
        [(arm_a, [hit]), (arm_b, [hit])],
        limit=1,
        rrf_k=60.0,
        fusion_mode="rrf",
    )

    assert {row["space_id"] for row in fused[0].contributions} == {
        "text.general_memory.v1",
        "text.jp_multilingual.v1",
    }


def _portfolio_arm(name: str, *, space_id: str) -> memory_portfolio.PortfolioArmResult:
    return memory_portfolio.PortfolioArmResult(
        name=name,
        status="ok",
        mode="semantic_only",
        provider="local_hash",
        model=LOCAL_HASH_MODEL,
        dimensions=32,
        embedding_profile=DEFAULT_EMBEDDING_PROFILE,
        text_template_version=DEFAULT_TEXT_TEMPLATE_VERSION,
        weight=1.0,
        hit_count=1,
        top_doc_ids=("doc-1",),
        top_bundle_keys=("tweet:tweet-1",),
        error=None,
        space_id=space_id,
    )


def _copy_embeddings_into_alternate_space(db_path: Path, *, source_space_id: str) -> str:
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        alt_space_id = ensure_embedding_space_for_spec(
            conn,
            provider="local_hash",
            model=LOCAL_HASH_MODEL,
            dimensions=32,
            embedding_profile=DEFAULT_EMBEDDING_PROFILE,
            text_template_version=DEFAULT_TEXT_TEMPLATE_VERSION,
            modality="text",
            document_scope="memory_documents",
            source_kind_filter="local_x_text",
            language_filter="ja",
            storage_rights_policy="local-db-derived-text",
            provider_role="text_embedding",
            status="active",
            notes="Test-only alternate text space with the same distance spec.",
        )
        rows = conn.execute(
            """
            SELECT
                doc_id, provider, model, dimensions,
                embedding_profile, text_template_version,
                embedding, source_doc_hash, embedded_text_hash, created_at, updated_at,
                generation_id, embedded_input_hash, token_count
            FROM memory_embeddings
            WHERE space_id = ?
            """,
            (source_space_id,),
        ).fetchall()
        for row in rows:
            conn.execute(
                """
                INSERT INTO memory_embeddings (
                    doc_id, provider, model, dimensions,
                    embedding_profile, text_template_version,
                    embedding, source_doc_hash, embedded_text_hash, created_at, updated_at,
                    embedding_id, space_id, generation_id, embedded_input_hash,
                    token_count, stale_status
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    row["doc_id"],
                    row["provider"],
                    row["model"],
                    row["dimensions"],
                    row["embedding_profile"],
                    row["text_template_version"],
                    row["embedding"],
                    row["source_doc_hash"],
                    row["embedded_text_hash"],
                    row["created_at"],
                    row["updated_at"],
                    f"test-alt-{row['doc_id']}",
                    alt_space_id,
                    row["generation_id"],
                    row["embedded_input_hash"],
                    row["token_count"],
                    "current",
                ),
            )
    return alt_space_id
