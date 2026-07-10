from __future__ import annotations

from pathlib import Path

from research_x.memory.embeddings import build_memory_embeddings
from research_x.memory.evals import EvalCase
from research_x.memory.portfolio import parse_portfolio_reranker_spec, run_portfolio_eval
from research_x.memory.retrieval_text import build_retrieval_text_profiles
from research_x.memory.search import search_memory
from research_x.memory.vector_projection import build_vector_projection
from research_x.memory.workflow import run_memory_workflow
from research_x.tool_interface.memory_tool_contract import (
    validate_tool_output,
    workflow_tool_output,
)


def test_vector_projection_search_remains_candidate_metadata(
    vector_db_path: Path,
    tmp_path: Path,
) -> None:
    build_memory_embeddings(vector_db_path, provider="local_hash", dimensions=32)
    build_vector_projection(
        vector_db_path,
        provider="local_hash",
        dimensions=32,
        backend="numpy",
        out_dir=tmp_path / "vector-indexes",
    )

    results = search_memory(
        vector_db_path,
        "robot paper",
        limit=2,
        semantic_provider="local_hash",
        semantic_dimensions=32,
        semantic_backend="projection",
    )

    assert results
    semantic = results[0].metadata["semantic"]
    assert semantic["diagnostic_only"] is True
    assert semantic["evidence_role"] == "retrieval_candidate_signal"
    assert semantic["answer_support_allowed"] is False
    assert semantic["source_doc_hash"]
    assert semantic["embedded_text_hash"]
    assert semantic["profile"] == semantic["embedding_profile"]
    assert semantic["generated_at"]
    assert semantic["provider"] == "local_hash"
    assert semantic["model"]
    assert semantic["stale_status"] == "current"
    assert semantic["projection_generation_id"]
    assert semantic["projection_hash"]
    assert semantic["projection_status"] == "current"
    assert "citation_ready" not in semantic
    assert "source_bundle_id" not in semantic


def test_vector_projection_workflow_does_not_create_citation_ready_answer(
    vector_db_path: Path,
    tmp_path: Path,
) -> None:
    build_retrieval_text_profiles(vector_db_path)
    build_memory_embeddings(vector_db_path, provider="local_hash", dimensions=32)
    build_vector_projection(
        vector_db_path,
        provider="local_hash",
        dimensions=32,
        backend="numpy",
        out_dir=tmp_path / "vector-indexes",
    )

    workflow = run_memory_workflow(
        vector_db_path,
        "robot paper",
        limit=1,
        semantic_provider="local_hash",
        semantic_dimensions=32,
        semantic_backend="projection",
        answer_provider="none",
    )
    output = workflow_tool_output(workflow)

    assert validate_tool_output(output) == []
    assert output.status == "needs_review"
    assert output.evidence_level == "context_chunk"
    assert output.answer_text is None
    assert workflow.context_bundle is not None
    semantic = workflow.context_bundle.retrieved_hits[0]["metadata"]["semantic"]
    assert semantic["diagnostic_only"] is True
    assert semantic["answer_support_allowed"] is False


def test_fake_rerank_score_is_candidate_metadata_not_answer_support(
    vector_db_path: Path,
) -> None:
    report = run_portfolio_eval(
        vector_db_path,
        cases=(
            EvalCase(
                query="robot paper",
                required_any_terms=("robot",),
            ),
        ),
        fast=True,
        reranker_specs=(
            parse_portfolio_reranker_spec(
                "provider=fake,name=fake_rerank,candidate_limit=5,top_n=3"
            ),
        ),
        limit=3,
        arm_limit=3,
    )

    case = report.cases[0]
    reranked = [
        hit.metadata["rerank"]
        for hit in case.fused_hits
        if "rerank" in hit.metadata
    ]

    assert reranked
    for metadata in reranked:
        assert metadata["evidence_role"] == "ranking_candidate_signal"
        assert metadata["answer_support_allowed"] is False
        assert metadata["not_evidence"] is True
        assert metadata["citation_ready"] is False
        assert metadata["promotion_gate"] == "source_bundle_context_citation_required"
