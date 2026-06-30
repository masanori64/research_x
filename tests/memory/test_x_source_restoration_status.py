from __future__ import annotations

import pytest

from research_x.memory.answer import assess_answerability
from research_x.memory.context import CitationAnnotation, ContextChunk
from research_x.memory.evidence_invariants import (
    chunk_is_not_evidence,
    citation_block_reasons,
    citation_is_citation_ready,
)

CREATED_AT = "2026-07-01T00:00:00Z"
READY_LINEAGE = {
    "source_doc_hash": "hash-restored",
    "embedding_text_hash": "embedding-restored",
    "retrieval_text_hash": "retrieval-restored",
    "retrieval_text_profile_id": "profile-restored",
    "source_bundle_id": "bundle-restored",
    "lineage_status": "restored",
    "marker_found": True,
}


@pytest.mark.parametrize(
    ("metadata_key", "status"),
    (
        ("source_restoration_status", "login_required"),
        ("source_restoration_status", "snippet_only"),
        ("source_restoration_status", "source_unavailable"),
        ("source_restoration_status", "source_not_restored"),
        ("source_restoration_status", "user_export_required"),
        ("privacy_status", "private_locator"),
        ("privacy_status", "private_collection"),
        ("fetch_status", "snippet_only"),
        ("access_status", "login_required"),
    ),
)
def test_x_restoration_status_blocks_citation_ready(
    metadata_key: str,
    status: str,
) -> None:
    chunk = _chunk(metadata={metadata_key: status})
    citation = _citation(metadata={metadata_key: status})

    assessment = assess_answerability(
        question="fixture private or unrestored X source",
        chunks=(chunk,),
        citations=(citation,),
    )

    assert chunk_is_not_evidence(chunk) is True
    assert citation_is_citation_ready(citation) is False
    assert status in citation_block_reasons(citation)
    assert "not_evidence" in citation_block_reasons(citation)
    assert assessment.status == "citation_missing"
    assert assessment.reason == "no_citation_ready_evidence"


def test_nested_x_restoration_status_blocks_citation_ready() -> None:
    metadata = {
        "source_restoration_status": {
            "url": "https://x.com/example/status/1",
            "status": "snippet_only",
        }
    }
    citation = _citation(metadata=metadata)

    assert citation_is_citation_ready(citation) is False
    assert "snippet_only" in citation_block_reasons(citation)


def _chunk(*, metadata: dict[str, object]) -> ContextChunk:
    resolved = {**READY_LINEAGE, **metadata}
    return ContextChunk(
        chunk_id="chunk:x-unrestored",
        run_id="run:x-unrestored",
        source_kind="local_x_db",
        source_id="tweet:unrestored",
        source_url="https://x.com/example/status/unrestored",
        provider="fixture",
        provider_role="context_builder",
        chunk_text="Snippet or private locator, not a restored source bundle.",
        chunk_index=0,
        token_count=8,
        relevance_score=1.0,
        extractor_version="x-source-restoration-status-fixture-v1",
        created_at=CREATED_AT,
        metadata=resolved,
    )


def _citation(*, metadata: dict[str, object]) -> CitationAnnotation:
    resolved = {**READY_LINEAGE, **metadata}
    return CitationAnnotation(
        citation_id="citation:x-unrestored",
        answer_id=None,
        chunk_id="chunk:x-unrestored",
        source_kind="local_x_db",
        source_id="tweet:unrestored",
        source_url="https://x.com/example/status/unrestored",
        title="unrestored X fixture",
        field_path="context_chunks[0]",
        support_type="supports_answer",
        evidence_status="fact",
        confidence=1.0,
        created_at=CREATED_AT,
        metadata=resolved,
    )
