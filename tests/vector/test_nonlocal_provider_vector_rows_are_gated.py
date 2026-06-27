from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

import pytest

from research_x.memory import embeddings
from research_x.memory.audit import audit_memory_db
from research_x.memory.embeddings import (
    DEFAULT_EMBEDDING_PROFILE,
    DEFAULT_TEXT_TEMPLATE_VERSION,
    EMBEDDING_PROVIDER_QUOTA_GATE_MESSAGE,
    pack_embedding,
    semantic_search_memory,
)
from research_x.memory.evals import EvalCase
from research_x.memory.portfolio import parse_portfolio_semantic_spec, run_portfolio_eval
from research_x.memory.search import search_memory
from research_x.memory.vector_projection import (
    benchmark_vector_backends,
    build_vector_projection,
    search_vector_projection,
)

OPENAI_MODEL = "text-embedding-3-small"


def test_nonlocal_semantic_rows_gate_query_embedding_before_provider_call(
    vector_db_path: Path,
    monkeypatch,
) -> None:
    _insert_provider_embeddings(vector_db_path)
    called = False

    def fail_post_json(*args: Any, **kwargs: Any) -> dict[str, Any]:
        nonlocal called
        called = True
        raise AssertionError("provider query embedding call should be gated")

    monkeypatch.setattr(embeddings, "_post_json", fail_post_json)

    with pytest.raises(RuntimeError) as direct_exc:
        semantic_search_memory(
            vector_db_path,
            "robot paper",
            provider="openai",
            model=OPENAI_MODEL,
            dimensions=3,
            limit=2,
        )
    _assert_embedding_gate(str(direct_exc.value))

    with pytest.raises(RuntimeError) as search_exc:
        search_memory(
            vector_db_path,
            "robot paper",
            limit=2,
            semantic_provider="openai",
            semantic_model=OPENAI_MODEL,
            semantic_dimensions=3,
        )
    _assert_embedding_gate(str(search_exc.value))
    assert called is False


def test_nonlocal_vector_projection_metadata_is_quarantined_and_search_gated(
    vector_db_path: Path,
    tmp_path: Path,
    monkeypatch,
) -> None:
    _insert_provider_embeddings(vector_db_path)
    called = False

    def fail_post_json(*args: Any, **kwargs: Any) -> dict[str, Any]:
        nonlocal called
        called = True
        raise AssertionError("projection query embedding call should be gated")

    monkeypatch.setattr(embeddings, "_post_json", fail_post_json)

    summary = build_vector_projection(
        vector_db_path,
        provider="openai",
        model=OPENAI_MODEL,
        dimensions=3,
        backend="numpy",
        out_dir=tmp_path / "vector-indexes",
    )
    metadata = _projection_metadata(vector_db_path, summary.generation_id)
    policy = metadata["embedding_provider_policy"]

    assert policy["provider_gated"] is True
    assert policy["quarantined"] is True
    assert policy["production_eligible"] is False
    assert policy["production_eligible_reason"] == "provider_gated_while_no_quota_freeze"

    with pytest.raises(RuntimeError) as excinfo:
        search_vector_projection(
            vector_db_path,
            "robot paper",
            generation_id=summary.generation_id,
            limit=2,
        )
    _assert_embedding_gate(str(excinfo.value))
    assert called is False


def test_nonlocal_provider_audit_and_benchmark_metadata_are_quarantined(
    vector_db_path: Path,
    tmp_path: Path,
) -> None:
    _insert_provider_embeddings(vector_db_path, doc_limit=1)

    audit = audit_memory_db(vector_db_path)
    openai_spec = next(spec for spec in audit.embedding_specs if spec["provider"] == "openai")
    benchmark = benchmark_vector_backends(
        vector_db_path,
        provider="openai",
        model=OPENAI_MODEL,
        dimensions=3,
        backends=("numpy",),
        queries=("robot paper",),
        out_dir=tmp_path / "benchmark",
    )

    assert openai_spec["provider_gated"] is True
    assert openai_spec["quarantined"] is True
    assert openai_spec["production_eligible"] is False
    assert any("provider embedding rows are quarantined" in item for item in audit.warnings)
    assert benchmark.metadata["provider_gated"] is True
    assert benchmark.metadata["quarantined"] is True
    assert benchmark.metadata["production_eligible"] is False
    assert benchmark.metadata["provider_policy"] == "no_quota_freeze_provider_gated"
    assert benchmark.results[0].status == "provider_gated"
    assert not (tmp_path / "benchmark").exists()


def test_nonlocal_semantic_only_portfolio_arm_is_provider_gated(
    vector_db_path: Path,
) -> None:
    _insert_provider_embeddings(vector_db_path)

    report = run_portfolio_eval(
        vector_db_path,
        cases=(
            EvalCase(
                query="robot paper",
                required_any_terms=("robot",),
            ),
        ),
        fast=True,
        semantic_specs=(
            parse_portfolio_semantic_spec(
                "provider=openai,model=text-embedding-3-small,dimensions=3,"
                "name=openai_semantic,mode=semantic_only"
            ),
        ),
        limit=2,
        arm_limit=2,
    )
    arm = next(item for item in report.cases[0].arms if item.name == "openai_semantic")

    assert arm.status == "provider_gated"
    _assert_embedding_gate(arm.error or "")


def _insert_provider_embeddings(
    db_path: Path,
    *,
    provider: str = "openai",
    model: str = OPENAI_MODEL,
    dimensions: int = 3,
    doc_limit: int | None = None,
) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT doc_id, source_doc_hash, embedding_text_hash
            FROM memory_documents
            ORDER BY doc_id
            """
        ).fetchall()
        if doc_limit is not None:
            rows = rows[:doc_limit]
        now = "2026-06-27T00:00:00+00:00"
        for index, row in enumerate(rows, start=1):
            vector = [float(index), float(index + 1), float(index + 2)]
            conn.execute(
                """
                INSERT INTO memory_embeddings (
                    doc_id, provider, model, dimensions,
                    embedding_profile, text_template_version,
                    embedding, source_doc_hash, embedded_text_hash, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    row["doc_id"],
                    provider,
                    model,
                    dimensions,
                    DEFAULT_EMBEDDING_PROFILE,
                    DEFAULT_TEXT_TEMPLATE_VERSION,
                    pack_embedding(vector),
                    row["source_doc_hash"],
                    row["embedding_text_hash"],
                    now,
                    now,
                ),
            )


def _projection_metadata(db_path: Path, generation_id: str) -> dict[str, Any]:
    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            """
            SELECT metadata_json
            FROM memory_projection_generations
            WHERE generation_id = ?
            """,
            (generation_id,),
        ).fetchone()
    assert row is not None
    return json.loads(row[0])


def _assert_embedding_gate(message: str) -> None:
    assert message == EMBEDDING_PROVIDER_QUOTA_GATE_MESSAGE
    for term in (
        "paid/free-tier",
        "trial-credit",
        "zero-dollar",
        "keyless",
        "provider_gated/quarantined",
        "API Budget Guard",
    ):
        assert term in message
