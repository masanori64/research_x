from __future__ import annotations

from dataclasses import replace
from typing import Any

import pytest

from research_x.memory.answer import MemoryAnswer
from research_x.memory.context import CitationAnnotation, ContextBundle, ContextChunk
from research_x.memory.workflow import MemoryWorkflow
from research_x.tool_interface.memory_tool_contract import (
    validate_tool_output,
    workflow_tool_output,
)

CREATED_AT = "2026-06-27T00:00:00Z"


@pytest.mark.parametrize(
    "artifact_kind",
    (
        "context_offload_preview",
        "diagram_review",
        "compressed_summary",
        "html_structure_view",
        "wbs_json",
        "wbs_rendered_view",
        "chatgpt_consultation",
        "gpt_pro_plan",
        "playwright_visual_snapshot",
        "ppt_master_deck",
        "reverse_spec",
        "slidev_deck",
        "slidev_rendered_view",
    ),
)
def test_not_evidence_artifact_workflow_stays_needs_review(
    artifact_kind: str,
) -> None:
    output = workflow_tool_output(_workflow(artifact_kind=artifact_kind))

    assert validate_tool_output(output) == []
    assert output.status == "needs_review"
    assert output.evidence_level == "context_chunk"
    assert output.citations[0].citation_ready is False
    assert output.citations[0].restore["artifact_kind"] == artifact_kind
    assert output.citations[0].restore["not_evidence"] is True
    assert output.trace["citation_quality"]["not_evidence_count"] == 1
    assert output.trace["non_evidence_artifacts"]["status"] == "blocked"
    assert output.trace["non_evidence_artifacts"]["artifact_count"] == 1


def test_validate_tool_output_rejects_answer_payload_with_preview_citation() -> None:
    payload = workflow_tool_output(_workflow(artifact_kind="diagram_review")).as_dict()
    payload["status"] = "answer"
    payload["evidence_level"] = "citation_ready"
    payload["answer_text"] = "This forged answer must still be rejected. [1]"
    payload["citations"][0]["citation_ready"] = True
    payload["citations"][0]["restore"]["citation_ready"] = True
    payload["citations"][0]["restore"]["context_chunk_restored"] = True
    payload["citations"][0]["restore"]["source_restored"] = True

    errors = validate_tool_output(payload)

    assert any(
        "answer status cannot cite not-evidence artifacts" in error for error in errors
    )


def _workflow(*, artifact_kind: str) -> MemoryWorkflow:
    metadata = {
        "artifact_kind": artifact_kind,
        "artifact_type": artifact_kind,
        "owner_plane": "control_artifact",
        "not_evidence": True,
        "answer_support_allowed": False,
        "evidence_status": "not_evidence",
        "citation_policy": "citation_excluded",
        "preview_kind": artifact_kind if "preview" in artifact_kind else None,
        "source_doc_hash": "hash-1",
        "source_bundle_id": "bundle-1",
    }
    chunk = _chunk(metadata=metadata)
    citation = _citation(metadata=metadata, chunk=chunk)
    bundle = ContextBundle(
        run_id="context-run",
        query="fixture preview",
        query_plan={"query": "fixture preview"},
        parameters={"limit": 1},
        retrieved_hits=[{"doc_id": "review:artifact", "evidence": {"url": chunk.source_url}}],
        context_chunks=(chunk,),
        citation_annotations=(citation,),
    )
    answer = MemoryAnswer(
        answer_id="answer-1",
        question="fixture preview",
        workflow_id="workflow-1",
        context_run_id=bundle.run_id,
        provider="fake",
        provider_role="answer_provider",
        model="fake-model",
        prompt_version="memory-answer-v1",
        retrieval_config={"fixture": True},
        answer_text="Unsupported preview answer [1]",
        structured={
            "answerability": {"status": "citation_missing"},
            "mode": "deterministic_fake",
        },
        status="needs_review",
        created_at=CREATED_AT,
        citation_annotations=(replace(citation, answer_id="answer-1"),),
        context_bundle=bundle,
        selected_context_chunks=(chunk,),
    )
    return MemoryWorkflow(
        workflow_id="workflow-1",
        query="fixture preview",
        route="local_memory_search",
        status="ok",
        stop_reason="enough_evidence",
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
        source_id="review:artifact",
        source_url="https://example.test/review-artifact",
        provider="fixture",
        provider_role="context_builder",
        chunk_text="Rendered review artifact, not source evidence.",
        chunk_index=0,
        token_count=6,
        relevance_score=1.0,
        extractor_version="fixture",
        created_at=CREATED_AT,
        metadata=metadata,
    )


def _citation(*, metadata: dict[str, Any], chunk: ContextChunk) -> CitationAnnotation:
    return CitationAnnotation(
        citation_id="citation-1",
        answer_id=None,
        chunk_id=chunk.chunk_id,
        source_kind=chunk.source_kind,
        source_id=chunk.source_id,
        source_url=chunk.source_url,
        title="review artifact",
        field_path="context_chunks[0]",
        support_type="background",
        evidence_status="fact",
        confidence=1.0,
        created_at=CREATED_AT,
        metadata={**metadata, "marker_found": True},
    )
