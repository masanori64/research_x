from __future__ import annotations

from dataclasses import replace

from research_x.memory.context import CitationAnnotation
from research_x.memory.evidence_invariants import (
    citation_block_reasons,
    citation_is_citation_ready,
)

CREATED_AT = "2026-06-27T00:00:00Z"
READY_METADATA = {
    "source_doc_hash": "hash-1",
    "embedding_text_hash": "embedding-hash-1",
    "retrieval_text_hash": "retrieval-hash-1",
    "retrieval_text_profile": "full_text",
    "retrieval_profile_kind": "full_text",
    "retrieval_text_profile_id": "profile-1",
    "source_bundle_id": "bundle-1",
    "lineage_status": "restored",
    "restored_at": CREATED_AT,
    "marker_found": True,
}


def test_local_x_db_citation_ready_requires_restored_lineage() -> None:
    citation = _citation()

    assert citation_is_citation_ready(citation)
    assert citation_block_reasons(citation) == ()


def test_local_x_db_citation_accepts_source_restore_id_without_bundle_id() -> None:
    citation = _citation(
        metadata={
            "source_bundle_id": None,
            "source_restore_id": "restore-1",
        }
    )

    assert citation_is_citation_ready(citation)
    assert citation_block_reasons(citation) == ()


def test_local_x_db_citation_requires_a_compatible_lineage_identifier() -> None:
    citation = _citation(
        metadata={
            "source_bundle_id": None,
            "source_restore_id": None,
        }
    )

    assert not citation_is_citation_ready(citation)
    assert "missing_source_lineage_id" in citation_block_reasons(citation)


def test_local_x_db_citation_missing_lineage_is_not_citation_ready() -> None:
    citation = _citation(metadata={"source_doc_hash": None})

    assert not citation_is_citation_ready(citation)
    assert "missing_source_doc_hash" in citation_block_reasons(citation)


def test_local_x_db_citation_requires_retrieval_text_lineage() -> None:
    citation = _citation(
        metadata={
            "retrieval_text_hash": None,
            "retrieval_text_profile_id": None,
        }
    )

    assert not citation_is_citation_ready(citation)
    assert "missing_retrieval_text_lineage" in citation_block_reasons(citation)


def test_local_x_db_citation_requires_restored_lineage_status() -> None:
    citation = _citation(metadata={"lineage_status": "metadata_only"})

    assert not citation_is_citation_ready(citation)
    assert "source_not_restored" in citation_block_reasons(citation)


def test_non_local_citation_keeps_payload_only_requirement() -> None:
    citation = replace(
        _citation(metadata={}),
        source_kind="external_web",
        source_id="https://example.test/source",
        source_url="https://example.test/source",
        metadata={"marker_found": True},
    )

    assert citation_is_citation_ready(citation)


def _citation(metadata: dict[str, object] | None = None) -> CitationAnnotation:
    resolved = dict(READY_METADATA)
    if metadata:
        resolved.update(metadata)
    return CitationAnnotation(
        citation_id="citation-1",
        answer_id="answer-1",
        chunk_id="chunk-1",
        source_kind="local_x_db",
        source_id="tweet:1",
        source_url="https://x.com/example/status/1",
        title="fixture",
        field_path="context_chunks[0]",
        support_type="supports_answer",
        evidence_status="fact",
        confidence=1.0,
        created_at=CREATED_AT,
        metadata=resolved,
    )
