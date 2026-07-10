from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from research_x.memory.context import CitationAnnotation
from research_x.memory.evidence_invariants import (
    citation_block_reasons,
    citation_is_citation_ready,
)
from research_x.memory.ocr import add_media_observation, build_ocr_evidence

CREATED_AT = "2026-06-27T00:00:00+00:00"


def test_raw_ocr_source_text_is_not_direct_answer_evidence(
    media_db_with_file: Path,
) -> None:
    build_ocr_evidence(media_db_with_file, provider="fake", limit=1, promote_chunks=False)

    with sqlite3.connect(media_db_with_file) as conn:
        row = conn.execute(
            """
            SELECT text_profile, evidence_status, metadata_json
            FROM memory_ocr_texts
            WHERE text_profile = 'raw_ocr'
            LIMIT 1
            """
        ).fetchone()

    metadata = json.loads(row[2])
    assert row[:2] == ("raw_ocr", "fact")
    assert metadata["media_signal_role"] == "raw_ocr"
    assert metadata["evidence_role"] == "media_text_candidate_signal"
    assert metadata["not_evidence"] is True
    assert metadata["answer_support_allowed"] is False
    assert metadata["citation_ready"] is False
    assert metadata["promotion_gate"] == "context_chunk_citation_annotation_required"


def test_vlm_observation_promotes_only_as_search_helper_not_answer_support(
    media_db_with_file: Path,
) -> None:
    add_media_observation(
        media_db_with_file,
        media_id="media-1",
        observation_text="Codex observation: robot diagram labels are visible.",
        observation_kind="codex_interpretation",
        provider="codex_interactive",
        model="test-vlm",
        promote_chunks=True,
    )

    with sqlite3.connect(media_db_with_file) as conn:
        text_row = conn.execute(
            """
            SELECT text_profile, evidence_status, metadata_json
            FROM memory_ocr_texts
            WHERE text_profile = 'codex_observation'
            LIMIT 1
            """
        ).fetchone()
        visual_row = conn.execute(
            """
            SELECT evidence_level, citation_ready, metadata_json
            FROM memory_visual_recall_evidence
            LIMIT 1
            """
        ).fetchone()
        citation_row = conn.execute(
            """
            SELECT citation_id, chunk_id, source_kind, source_id, source_url, title,
                   field_path, support_type, evidence_status, confidence,
                   created_at, metadata_json
            FROM memory_citation_annotations
            WHERE field_path = 'media.ocr_text.codex_observation'
            LIMIT 1
            """
        ).fetchone()

    text_metadata = json.loads(text_row[2])
    visual_metadata = json.loads(visual_row[2])
    citation = _citation_from_row(citation_row)

    assert text_row[:2] == ("codex_observation", "inference")
    assert text_metadata["not_evidence"] is True
    assert text_metadata["answer_support_allowed"] is False
    assert visual_row[:2] == ("codex_observation", 0)
    assert visual_metadata["answer_support_allowed"] is False
    assert visual_metadata["citation_ready"] is False
    assert citation.support_type == "supports_search_helper"
    assert citation.evidence_status == "inference"
    assert citation.metadata["not_evidence"] is True
    assert citation.metadata["answer_support_allowed"] is False
    assert citation_is_citation_ready(citation) is False
    assert "not_evidence" in citation_block_reasons(citation)


def test_caption_vlm_and_corrected_profiles_stay_search_helpers() -> None:
    for profile in ("corrected_text", "caption", "vlm_caption", "codex_observation"):
        citation = CitationAnnotation(
            citation_id=f"citation-{profile}",
            answer_id="answer-media",
            chunk_id=f"chunk-{profile}",
            source_kind="local_x_db",
            source_id="media-1",
            source_url="https://example.test/image.jpg",
            title=profile,
            field_path=f"media.ocr_text.{profile}",
            support_type="supports_search_helper",
            evidence_status="inference",
            confidence=0.5,
            created_at=CREATED_AT,
            metadata={
                "media_signal_role": "promoted_context_chunk",
                "source_media_signal_role": profile,
                "evidence_role": "context_chunk_from_media_text",
                "answer_support_allowed": False,
                "not_evidence": True,
                "promotion_gate": "context_chunk_citation_annotation_created",
            },
        )

        assert citation_is_citation_ready(citation) is False
        assert "unsupported_support_type:supports_search_helper" in citation_block_reasons(
            citation
        )
        assert "not_evidence" in citation_block_reasons(citation)


def _citation_from_row(row: sqlite3.Row | tuple[object, ...]) -> CitationAnnotation:
    return CitationAnnotation(
        citation_id=str(row[0]),
        answer_id=None,
        chunk_id=str(row[1]),
        source_kind=str(row[2]),
        source_id=str(row[3]),
        source_url=str(row[4]) if row[4] else None,
        title=str(row[5]),
        field_path=str(row[6]),
        support_type=str(row[7]),
        evidence_status=str(row[8]),
        confidence=float(row[9] or 0.0),
        created_at=str(row[10]),
        metadata=json.loads(str(row[11] or "{}")),
    )
