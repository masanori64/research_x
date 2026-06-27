from __future__ import annotations

from pathlib import Path

from research_x.memory.audit import audit_memory_db
from research_x.memory.embeddings import build_memory_embeddings
from research_x.memory.search import search_memory
from research_x.memory.vector_projection import benchmark_vector_backends


def test_local_hash_search_metadata_is_diagnostic_candidate_only(
    vector_db_path: Path,
) -> None:
    build_memory_embeddings(vector_db_path, provider="local_hash", dimensions=32)

    results = search_memory(
        vector_db_path,
        "robot paper",
        limit=2,
        semantic_provider="local_hash",
        semantic_dimensions=32,
    )

    semantic_metadata = [
        result.metadata["semantic"] for result in results if "semantic" in result.metadata
    ]
    semantic_contributions = [
        contribution
        for result in results
        for contribution in result.metadata["engine_contributions"]
        if contribution["engine"] in {"semantic", "semantic_rerank"}
    ]
    assert semantic_metadata
    assert semantic_contributions
    for row in (*semantic_metadata, *semantic_contributions):
        assert row["provider"] == "local_hash"
        assert row["diagnostic_only"] is True
        assert row["production_eligible"] is False
        assert row["evidence_role"] == "retrieval_candidate_signal"
        assert row["answer_support_allowed"] is False
        assert row["promotion_gate"] == "source_bundle_context_citation_required"


def test_local_hash_audit_and_benchmark_do_not_promote_vector_quality(
    vector_db_path: Path,
    tmp_path: Path,
) -> None:
    build_memory_embeddings(vector_db_path, provider="local_hash", dimensions=32)

    audit = audit_memory_db(vector_db_path)
    benchmark = benchmark_vector_backends(
        vector_db_path,
        provider="local_hash",
        dimensions=32,
        backends=("numpy",),
        queries=("robot paper",),
        out_dir=tmp_path / "vector-benchmark",
    )

    assert any("only local_hash embeddings" in warning for warning in audit.warnings)
    assert benchmark.metadata["diagnostic_only"] is True
    assert benchmark.metadata["production_eligible"] is False
    assert benchmark.metadata["answer_support_allowed"] is False
    assert benchmark.metadata["promotion_gate"] == "source_bundle_context_citation_required"
