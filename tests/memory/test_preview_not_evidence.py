from __future__ import annotations

import pytest

from research_x.memory.answer import assess_answerability
from research_x.memory.context import CitationAnnotation, ContextChunk
from research_x.memory.evidence_invariants import (
    chunk_is_not_evidence,
    citation_block_reasons,
    citation_is_citation_ready,
    citation_is_not_evidence,
)

CREATED_AT = "2026-06-27T00:00:00+00:00"
NON_EVIDENCE_ARTIFACT_KINDS = (
    "context_offload_preview",
    "diagram_review",
    "compressed_summary",
    "html_structure_view",
    "wbs_json",
    "wbs_rendered_view",
    "chatgpt_consultation",
    "codex_review_capture",
    "gpt_pro_plan",
    "playwright_visual_snapshot",
    "ppt_master_deck",
    "reverse_spec",
    "slidev_deck",
    "slidev_rendered_view",
)


@pytest.mark.parametrize("artifact_kind", NON_EVIDENCE_ARTIFACT_KINDS)
def test_preview_and_review_artifacts_are_not_citation_ready(
    artifact_kind: str,
) -> None:
    metadata = _non_evidence_metadata(artifact_kind)
    chunk = _chunk(metadata=metadata)
    citation = _citation(chunk, metadata=metadata)

    assessment = assess_answerability(
        question="fixture review artifact",
        chunks=(chunk,),
        citations=(citation,),
    )

    assert chunk.metadata["not_evidence"] is True
    assert chunk.metadata["answer_support_allowed"] is False
    assert citation.metadata["not_evidence"] is True
    assert citation.metadata["answer_support_allowed"] is False
    assert chunk_is_not_evidence(chunk) is True
    assert citation_is_not_evidence(citation) is True
    assert citation_is_citation_ready(citation) is False
    assert "not_evidence" in citation_block_reasons(citation)
    assert assessment.status == "citation_missing"
    assert assessment.reason == "no_citation_ready_evidence"


def test_artifact_kind_marker_blocks_citation_even_if_flag_is_missing() -> None:
    metadata = {
        "artifact_kind": "chatgpt_consultation",
        "citation_policy": "citation_excluded",
        "evidence_status": "not_evidence",
    }
    chunk = _chunk(metadata=metadata)
    citation = _citation(chunk, metadata=metadata)

    assert chunk_is_not_evidence(chunk) is True
    assert citation_is_not_evidence(citation) is True
    assert "not_evidence" in citation_block_reasons(citation)


def _non_evidence_metadata(artifact_kind: str) -> dict[str, object]:
    return {
        "artifact_kind": artifact_kind,
        "artifact_type": artifact_kind,
        "owner_plane": "control_artifact",
        "not_evidence": True,
        "answer_support_allowed": False,
        "evidence_status": "not_evidence",
        "citation_policy": "citation_excluded",
        "preview_kind": artifact_kind if "preview" in artifact_kind else None,
    }


def _chunk(*, metadata: dict[str, object]) -> ContextChunk:
    return ContextChunk(
        chunk_id="chunk:preview",
        run_id="fixture:preview",
        source_kind="local_x_db",
        source_id="tweet:fixture",
        source_url="https://x.com/example/status/fixture",
        provider="fixture",
        provider_role="context_builder",
        chunk_text="This is a rendered preview, not restored source evidence.",
        chunk_index=0,
        token_count=10,
        relevance_score=1.0,
        extractor_version="preview-not-evidence-fixture-v1",
        created_at=CREATED_AT,
        metadata=metadata,
    )


def _citation(
    chunk: ContextChunk,
    *,
    metadata: dict[str, object],
) -> CitationAnnotation:
    return CitationAnnotation(
        citation_id="citation:preview",
        answer_id=None,
        chunk_id=chunk.chunk_id,
        source_kind=chunk.source_kind,
        source_id=chunk.source_id,
        source_url=chunk.source_url,
        title=chunk.source_id,
        field_path="context_chunks[0]",
        support_type="background",
        evidence_status="fact",
        confidence=1.0,
        created_at=CREATED_AT,
        metadata=metadata,
    )
