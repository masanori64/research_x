from __future__ import annotations

from dataclasses import replace
from typing import Any

from research_x.memory.answer import MemoryAnswer
from research_x.memory.context import CitationAnnotation, ContextBundle, ContextChunk
from research_x.memory.workflow import MemoryWorkflow
from research_x.tool_interface.memory_tool_contract import (
    validate_tool_output,
    workflow_tool_output,
)

CREATED_AT = "2026-06-27T00:00:00Z"
LINEAGE_METADATA = {
    "source_doc_hash": "hash-1",
    "embedding_text_hash": "embedding-hash-1",
    "retrieval_text_hash": "retrieval-hash-1",
    "retrieval_text_profile": "full_text",
    "retrieval_profile_kind": "full_text",
    "retrieval_text_profile_id": "profile-1",
    "source_bundle_id": "bundle-1",
    "lineage_status": "restored",
    "restored_at": CREATED_AT,
}


def test_stale_conflict_and_preview_citations_block_answer_status() -> None:
    cases = (
        (
            _workflow(citation_metadata={"freshness_status": "stale"}),
            "stale_evidence_count",
        ),
        (
            _workflow(support_type="contradicts"),
            "conflict_evidence_count",
        ),
        (
            _workflow(
                citation_metadata={
                    "not_evidence": True,
                    "answer_support_allowed": False,
                    "preview_kind": "context_offload_preview",
                    "artifact_kind": "context_offload_preview",
                    "restore_hint_status": "requires_pointer_verification",
                }
            ),
            "not_evidence_count",
        ),
    )

    for workflow, trace_counter in cases:
        output = workflow_tool_output(workflow)

        assert validate_tool_output(output) == []
        assert output.status == "needs_review"
        assert output.evidence_level == "context_chunk"
        assert output.citations[0].citation_ready is False
        assert output.trace["citation_quality"][trace_counter] == 1
        assert output.trace["citation_restoration"]["status"] == "not_restored"

    preview_trace = workflow_tool_output(cases[-1][0]).trace
    assert preview_trace["pointer_offload_verification"]["status"] == "blocked"
    assert preview_trace["pointer_offload_verification"]["blocked_count"] == 1


def test_provider_gated_output_strips_completed_answer_text() -> None:
    workflow = _workflow(stop_reason="external_context_needed")

    output = workflow_tool_output(workflow)

    assert validate_tool_output(output) == []
    assert output.status == "provider_gated"
    assert output.answer_text is None
    assert output.evidence_level == "context_chunk"
    assert output.trace["provider_gate"]["required"] is True


def test_validate_tool_output_requires_restored_ready_citations_for_answer() -> None:
    payload = workflow_tool_output(_workflow()).as_dict()
    payload["citations"][0]["restore"]["context_chunk_restored"] = False

    errors = validate_tool_output(payload)

    assert any("answer status requires restored citations" in error for error in errors)


def test_validate_tool_output_rejects_provider_gated_completed_answer_text() -> None:
    payload = workflow_tool_output(_workflow(stop_reason="external_context_needed")).as_dict()
    payload["answer_text"] = "This must not be treated as a completed answer."

    errors = validate_tool_output(payload)

    assert any(
        "provider_gated status must not include completed answer_text" in error
        for error in errors
    )


def test_answer_trace_reports_restoration_and_fixture_limitation() -> None:
    payload = workflow_tool_output(_workflow()).as_dict()

    assert validate_tool_output(payload) == []
    assert payload["status"] == "answer"
    assert payload["trace"]["citation_restoration"]["status"] == "restored"
    assert payload["trace"]["citation_restoration"]["restored_count"] == 1
    assert payload["trace"]["pointer_offload_verification"]["status"] == "no_pointer_artifacts"
    assert payload["trace"]["fixture_limitations"]["provider_free_fixture"] is True
    assert (
        payload["trace"]["fixture_limitations"]["quality_scope"]
        == "boundary_wiring_not_model_quality"
    )
    rag_governance = payload["trace"]["rag_governance"]
    assert rag_governance["evidence_role"] == "control_plane_not_answer_evidence"
    assert rag_governance["answer_support_allowed"] is False
    assert rag_governance["provider_free_fixture_scope"] == {
        "provider_free_fixture": True,
        "quality_scope": "boundary_wiring_not_model_quality",
        "allowed_quality_scope": "boundary_wiring_not_model_quality",
        "model_quality_verified": False,
    }
    agent_safety = payload["trace"]["agent_safety"]
    assert agent_safety["tool_boundary"] == "research_x_memory_search_only"
    assert agent_safety["prompt_only_guardrails"] is False
    assert agent_safety["does_not_grant_permission"] is True
    assert "provider_gate" in agent_safety["system_side_guards"]
    assert "api_budget_guard" in agent_safety["system_side_guards"]
    assert "install_dependency_or_tool" in agent_safety["forbidden_external_actions"]
    assert (
        "source_promotion_from_snippet_search_result_or_review_artifact"
        in agent_safety["forbidden_external_actions"]
    )
    assert agent_safety["loop_control"] == {
        "max_steps": None,
        "step_count": 0,
        "within_configured_limit": True,
        "stop_reason": "enough_evidence",
    }
    assert "db_backed_restoration_validation_for_ai_output" in agent_safety[
        "answer_support_requires"
    ]


def test_validate_tool_output_requires_agent_safety_trace() -> None:
    payload = workflow_tool_output(_workflow()).as_dict()
    del payload["trace"]["agent_safety"]

    errors = validate_tool_output(payload)

    assert any("trace missing fields: agent_safety" in error for error in errors)


def test_relation_traversal_trace_is_candidate_only_not_promotion() -> None:
    relation = {
        "relation_id": "relation:supports:1",
        "relation_type": "supports",
        "source_doc_id": "tweet:1",
        "target_doc_id": "tweet:2",
        "strength": 0.91,
        "status": "active",
    }
    output = workflow_tool_output(
        _workflow(
            citation_metadata={
                "artifact_kind": "typed_relation_edge",
                "relation_role": "relation_traversal_hint",
                "relation_type": "supports",
                "relations": [relation],
            },
            retrieved_hits=[
                {
                    "doc_id": "tweet:1",
                    "evidence": {
                        "url": "https://x.com/example/status/1",
                        "relations": [relation],
                    },
                    "metadata": {"relation_counts": {"supports": 1}},
                }
            ],
        )
    )

    trace = output.trace["relation_traversal"]

    assert validate_tool_output(output) == []
    assert output.status == "needs_review"
    assert output.evidence_level == "context_chunk"
    assert output.citations[0].citation_ready is False
    assert trace["status"] == "visible"
    assert trace["candidate_only"] is True
    assert trace["promotion_requires_restored_citation"] is True
    assert trace["relation_counts"]["supports"] >= 1
    assert trace["relations"][0]["candidate_only"] is True
    assert trace["relations"][0]["promotion_requires_restored_citation"] is True


def _workflow(
    *,
    citation_metadata: dict[str, Any] | None = None,
    retrieved_hits: list[dict[str, Any]] | None = None,
    support_type: str = "supports_answer",
    stop_reason: str = "enough_evidence",
) -> MemoryWorkflow:
    chunk = _chunk(metadata=citation_metadata or {})
    citation = _citation(
        metadata=citation_metadata or {},
        support_type=support_type,
        chunk=chunk,
    )
    bundle = ContextBundle(
        run_id="context-run",
        query="fixture question",
        query_plan={"query": "fixture question"},
        parameters={"limit": 1},
        retrieved_hits=retrieved_hits
        or [{"doc_id": "tweet:1", "evidence": {"url": chunk.source_url}}],
        context_chunks=(chunk,),
        citation_annotations=(citation,),
    )
    answer = MemoryAnswer(
        answer_id="answer-1",
        question="fixture question",
        workflow_id="workflow-1",
        context_run_id=bundle.run_id,
        provider="fake",
        provider_role="answer_provider",
        model="fake-model",
        prompt_version="memory-answer-v1",
        retrieval_config={"fixture": True},
        answer_text="Grounded answer [1]",
        structured={
            "answerability": {"status": "answerable"},
            "mode": "deterministic_fake",
        },
        status="ok",
        created_at=CREATED_AT,
        citation_annotations=(replace(citation, answer_id="answer-1"),),
        context_bundle=bundle,
        selected_context_chunks=(chunk,),
    )
    return MemoryWorkflow(
        workflow_id="workflow-1",
        query="fixture question",
        route="local_memory_search",
        status="ok",
        stop_reason=stop_reason,
        started_at=CREATED_AT,
        finished_at=CREATED_AT,
        metadata={
            "parameters": {"answer_provider": "fake", "llm_context_provider": "none"},
            "stop_condition_audit": {"has_local_context": True},
            "route_plan": {"route": "local_memory_search"},
        },
        steps=(),
        context_bundle=bundle,
        answer=answer,
    )


def _chunk(*, metadata: dict[str, Any]) -> ContextChunk:
    return ContextChunk(
        chunk_id="chunk-1",
        run_id="context-run",
        source_kind="local_x_db",
        source_id="tweet:1",
        source_url="https://x.com/example/status/1",
        provider="fixture",
        provider_role="context_builder",
        chunk_text="Source-backed context.",
        chunk_index=0,
        token_count=4,
        relevance_score=1.0,
        extractor_version="fixture",
        created_at=CREATED_AT,
        metadata={
            **LINEAGE_METADATA,
            **metadata,
        },
    )


def _citation(
    *,
    metadata: dict[str, Any],
    support_type: str,
    chunk: ContextChunk,
) -> CitationAnnotation:
    return CitationAnnotation(
        citation_id="citation-1",
        answer_id=None,
        chunk_id=chunk.chunk_id,
        source_kind=chunk.source_kind,
        source_id=chunk.source_id,
        source_url=chunk.source_url,
        title="fixture",
        field_path="context_chunks[0]",
        support_type=support_type,
        evidence_status="fact",
        confidence=1.0,
        created_at=CREATED_AT,
        metadata={
            **LINEAGE_METADATA,
            "marker_found": True,
            **metadata,
        },
    )
