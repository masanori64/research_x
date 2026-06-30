from __future__ import annotations

from research_x.memory.answer import assess_answerability
from research_x.memory.context import CitationAnnotation, ContextChunk
from research_x.memory.evidence_invariants import (
    chunk_is_not_evidence,
    citation_block_reasons,
    citation_is_citation_ready,
)

CREATED_AT = "2026-06-27T00:00:00+00:00"


def test_search_result_only_context_is_not_answerable_evidence() -> None:
    chunk = _chunk(
        source_kind="search_result",
        metadata={
            "not_evidence": True,
            "artifact_kind": "search_result_snippet",
            "citation_policy": "citation_excluded_until_source_recovered",
        },
    )
    citation = _citation(
        chunk,
        metadata={
            "not_evidence": True,
            "artifact_kind": "search_result_snippet",
            "citation_policy": "citation_excluded_until_source_recovered",
        },
    )

    assessment = assess_answerability(
        question="fixture search result only",
        chunks=(chunk,),
        citations=(citation,),
    )

    assert chunk_is_not_evidence(chunk) is True
    assert citation_is_citation_ready(citation) is False
    assert "not_evidence" in citation_block_reasons(citation)
    assert assessment.status == "citation_missing"
    assert assessment.reason == "no_citation_ready_evidence"


def test_typed_relation_hint_is_not_answerable_evidence() -> None:
    relation_metadata = {
        "artifact_kind": "typed_relation_edge",
        "relation_role": "relation_traversal_hint",
        "relation_type": "supports",
        "relations": [
            {
                "relation_type": "supports",
                "source_doc_id": "tweet:newer",
                "target_doc_id": "tweet:older",
                "strength": 0.92,
            }
        ],
    }
    chunk = _chunk(
        source_kind="memory_relation",
        metadata=relation_metadata,
    )
    citation = _citation(
        chunk,
        metadata=relation_metadata,
    )

    assessment = assess_answerability(
        question="fixture relation traversal only",
        chunks=(chunk,),
        citations=(citation,),
    )

    assert chunk_is_not_evidence(chunk) is True
    assert citation_is_citation_ready(citation) is False
    assert "not_evidence" in citation_block_reasons(citation)
    assert assessment.status == "citation_missing"
    assert assessment.reason == "no_citation_ready_evidence"


def test_okf_source_metadata_shape_is_not_answerable_evidence() -> None:
    okf_metadata = {
        "type": "article",
        "title": "Open Knowledge Format article",
        "resource": "https://example.com/okf",
        "tags": ["knowledge format", "metadata"],
        "timestamp": "2026-07-01T00:00:00Z",
        "owner": "research_x",
        "review_status": "candidate",
    }
    chunk = _chunk(metadata=okf_metadata)
    citation = _citation(chunk, metadata={"okf_source_metadata": okf_metadata})

    assessment = assess_answerability(
        question="fixture OKF metadata only",
        chunks=(chunk,),
        citations=(citation,),
    )

    assert chunk_is_not_evidence(chunk) is True
    assert citation_is_citation_ready(citation) is False
    assert "not_evidence" in citation_block_reasons(citation)
    assert assessment.status == "citation_missing"
    assert assessment.reason == "no_citation_ready_evidence"


def test_stale_restore_hint_and_pointer_metadata_block_citation_ready() -> None:
    chunk = _chunk(
        metadata={
            "freshness_status": "current",
            "restore_hint_status": "stale",
            "pointer_status": "stale",
        }
    )
    citation = _citation(
        chunk,
        metadata={
            "freshness_status": "current",
            "restore_hint_status": "stale",
            "pointer_status": "stale",
        },
    )

    assessment = assess_answerability(
        question="fixture stale pointer",
        chunks=(chunk,),
        citations=(citation,),
    )

    assert citation_is_citation_ready(citation) is False
    assert "stale_evidence" in citation_block_reasons(citation)
    assert assessment.status == "stale_only"
    assert assessment.reason == "only_stale_evidence"


def test_partial_stale_context_requires_review_instead_of_answerable() -> None:
    fresh = _chunk(chunk_id="chunk:fresh", metadata={"freshness_status": "current"})
    stale = _chunk(chunk_id="chunk:stale", metadata={"freshness_status": "stale"})
    fresh_citation = _citation(fresh, citation_id="citation:fresh")
    stale_citation = _citation(
        stale,
        citation_id="citation:stale",
        metadata={"freshness_status": "stale"},
    )

    assessment = assess_answerability(
        question="fixture partial stale",
        chunks=(fresh, stale),
        citations=(fresh_citation, stale_citation),
    )

    assert assessment.status == "partially_supported"
    assert assessment.reason == "selected_context_contains_stale_evidence"
    assert assessment.answerable_chunk_ids == ("chunk:fresh",)
    assert assessment.missing == ("current_evidence:chunk:stale",)


def _chunk(
    *,
    chunk_id: str = "chunk:1",
    source_kind: str = "local_x_db",
    metadata: dict[str, object] | None = None,
) -> ContextChunk:
    return ContextChunk(
        chunk_id=chunk_id,
        run_id="fixture:invariants",
        source_kind=source_kind,
        source_id="tweet:fixture",
        source_url="https://x.com/example/status/fixture",
        provider="fixture",
        provider_role="context_builder",
        chunk_text="Text: fixture evidence.",
        chunk_index=0,
        token_count=8,
        relevance_score=1.0,
        extractor_version="evidence-invariant-fixture-v1",
        created_at=CREATED_AT,
        metadata=metadata or {},
    )


def _citation(
    chunk: ContextChunk,
    *,
    citation_id: str = "citation:1",
    metadata: dict[str, object] | None = None,
) -> CitationAnnotation:
    return CitationAnnotation(
        citation_id=citation_id,
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
        metadata=metadata or {},
    )
