from __future__ import annotations

from pathlib import Path

from research_x.memory.api_budget import api_budget_context, upsert_api_price
from research_x.memory.context import CitationAnnotation
from research_x.memory.evidence_invariants import (
    citation_block_reasons,
    citation_is_citation_ready,
)
from research_x.memory.media_embeddings import (
    build_media_embeddings,
    search_media_embeddings,
)

CREATED_AT = "2026-06-27T00:00:00+00:00"


def test_media_embedding_similarity_is_candidate_signal_not_citation(
    media_db_with_file: Path,
    monkeypatch,
) -> None:
    def fake_post_json(url, payload, *, headers, timeout_seconds, retries=3):
        return {"embeddings": [{"values": [0.1, 0.2, 0.3]}]}

    monkeypatch.setenv("GEMINI_API_KEY", "fake-key")
    monkeypatch.setattr("research_x.memory.media_embeddings._post_json", fake_post_json)
    upsert_api_price(
        media_db_with_file,
        provider="gemini",
        model="gemini-embedding-2",
        operation="media_embedding",
        unit="call",
        usd_per_unit=0.0,
        source_url="fixture://media-signal-not-citation",
        notes="provider-free monkeypatched fixture",
    )

    with api_budget_context(
        db_path=media_db_with_file,
        run_id="media-signal-fixture",
        provider_quota_approval=_provider_quota_approval(),
        no_quota_freeze_active=False,
    ):
        build_media_embeddings(
            media_db_with_file,
            dimensions=3,
            limit=1,
            allow_provider_quota=True,
        )
    with api_budget_context(
        db_path=media_db_with_file,
        run_id="media-signal-search-fixture",
        provider_quota_approval=_provider_quota_approval(),
        no_quota_freeze_active=False,
    ):
        hits = search_media_embeddings(
            media_db_with_file,
            "robot image",
            dimensions=3,
            limit=1,
            allow_provider_quota=True,
        )

    hit = hits[0]
    assert hit.evidence_status == "unconfirmed_media_match"
    assert hit.evidence_role == "media_source_candidate_signal"
    assert hit.answer_support_allowed is False
    assert hit.citation_ready is False
    assert hit.promotion_gate == "ocr_caption_vlm_context_chunk_citation_required"
    assert hit.quality_scope == "media_signal_boundary_not_model_quality"
    assert hit.bundle["media_signal_role"] == "raw_media_source_bundle"
    assert hit.bundle["answer_support_allowed"] is False
    assert hit.bundle["citation_ready"] is False
    assert hit.bundle["media_content_evidence"] is False

    citation = _citation_from_media_signal(hit.bundle)
    assert citation_is_citation_ready(citation) is False
    assert "not_evidence" in citation_block_reasons(citation)


def _provider_quota_approval() -> dict[str, object]:
    return {
        "provider_quota_approval_id": "fixture-approval",
        "provider": "gemini",
        "model": "gemini-embedding-2",
        "operation": "media_embedding",
        "max_calls": 3,
        "max_cost_usd": 0.0,
        "price_source": "fixture://media-signal-not-citation",
        "approved_scope": "*",
        "approved_at": CREATED_AT,
    }


def _citation_from_media_signal(metadata: dict[str, object]) -> CitationAnnotation:
    return CitationAnnotation(
        citation_id="media-signal-citation",
        answer_id="answer-media",
        chunk_id="media-signal-only",
        source_kind="local_x_db",
        source_id="media-1",
        source_url="https://example.test/image.jpg",
        title="media signal",
        field_path="media.embedding",
        support_type="supports_answer",
        evidence_status="fact",
        confidence=0.9,
        created_at=CREATED_AT,
        metadata=metadata,
    )
