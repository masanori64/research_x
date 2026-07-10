from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

import pytest

from research_x.memory import ocr


def test_local_ocr_provider_uses_no_provider_quota_or_http(
    media_db_with_file: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = {"quota": 0, "http": 0}

    def fail_provider_quota(*_args: Any, **_kwargs: Any) -> None:
        calls["quota"] += 1
        raise AssertionError("local OCR must not request provider quota approval")

    def fail_http(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        calls["http"] += 1
        raise AssertionError("local OCR must not send provider HTTP requests")

    monkeypatch.setattr(ocr, "require_provider_quota_approval", fail_provider_quota)
    monkeypatch.setattr(ocr, "_post_json", fail_http)

    summary = ocr.build_ocr_evidence(
        media_db_with_file,
        provider="local",
        model="local-metadata-ocr-v1",
        ocr_profile="local-ocr-test-profile",
        limit=1,
        promote_chunks=False,
    )

    assert calls == {"quota": 0, "http": 0}
    assert summary.provider == "local"
    assert summary.model == "local-metadata-ocr-v1"
    assert summary.ocr_profile == "local-ocr-test-profile"
    assert summary.processed == 1
    assert summary.promoted_chunks == 0

    with sqlite3.connect(media_db_with_file) as conn:
        conn.row_factory = sqlite3.Row
        run = conn.execute(
            """
            SELECT provider, model, ocr_profile
            FROM memory_ocr_runs
            LIMIT 1
            """
        ).fetchone()
        text = conn.execute(
            """
            SELECT provider, model, ocr_profile, text_profile, raw_ocr_text,
                   normalized_text, metadata_json
            FROM memory_ocr_texts
            LIMIT 1
            """
        ).fetchone()

    metadata = json.loads(str(text["metadata_json"]))
    assert tuple(run) == ("local", "local-metadata-ocr-v1", "local-ocr-test-profile")
    assert text["provider"] == "local"
    assert text["model"] == "local-metadata-ocr-v1"
    assert text["ocr_profile"] == "local-ocr-test-profile"
    assert text["text_profile"] == "raw_ocr"
    assert "robot screenshot UI with visible labels" in text["raw_ocr_text"]
    assert "Fake OCR text" not in text["raw_ocr_text"]
    assert metadata["provider_family"] == "local_ocr"
    assert metadata["local_only"] is True
    assert metadata["provider_quota_required"] is False
    assert metadata["fixture"] is False
    assert metadata["candidate_source"] == ["alt_text", "tweet_text"]
    assert metadata["answer_support_allowed"] is False
    assert metadata["citation_ready"] is False


def test_local_ocr_region_metadata_persists_dimensions_and_quality_flags(
    media_db_path: Path,
    tmp_path: Path,
) -> None:
    from PIL import Image

    image_path = tmp_path / "screen.png"
    Image.new("RGB", (640, 480), color="white").save(image_path)
    with sqlite3.connect(media_db_path) as conn:
        conn.execute(
            """
            UPDATE media
            SET local_path = ?, content_type = ?, alt_text = ?
            WHERE media_id = ?
            """,
            (str(image_path), "image/png", "スクショ 画面 文字", "media-1"),
        )

    summary = ocr.build_ocr_evidence(
        media_db_path,
        provider="local",
        limit=1,
        promote_chunks=False,
    )

    assert summary.provider == "local"
    assert summary.model == "local-metadata-ocr-v1"
    with sqlite3.connect(media_db_path) as conn:
        conn.row_factory = sqlite3.Row
        region = conn.execute(
            """
            SELECT source_tweet_id, bbox_json, mime_type, quality_flags_json, metadata_json
            FROM memory_ocr_regions
            LIMIT 1
            """
        ).fetchone()

    bbox = json.loads(str(region["bbox_json"]))
    quality_flags = json.loads(str(region["quality_flags_json"]))
    metadata = json.loads(str(region["metadata_json"]))
    assert region["source_tweet_id"] == "tweet-1"
    assert region["mime_type"] == "image/png"
    assert bbox["type"] == "top_band"
    assert quality_flags["image_width"] == 640
    assert quality_flags["image_height"] == 480
    assert quality_flags["text_likelihood"] == "high"
    assert quality_flags["estimated_text_density"] == "high"
    assert metadata["mime_type"] == "image/png"
    assert metadata["bbox"] == bbox
    assert metadata["dimensions"] == {"width": 640, "height": 480}
    assert metadata["text_likelihood"] == "high"
    assert metadata["estimated_text_density"] == "high"
    assert metadata["quality_flags"]["image_width"] == 640
    assert metadata["source_restoration"]["media_id"] == "media-1"
    assert metadata["source_restoration"]["tweet_id"] == "tweet-1"


def test_local_ocr_raw_candidate_until_promoted_and_corrected_profile_is_helper(
    media_db_path: Path,
    tmp_path: Path,
) -> None:
    from PIL import Image

    image_path = tmp_path / "screen.png"
    Image.new("RGB", (900, 900), color="white").save(image_path)
    with sqlite3.connect(media_db_path) as conn:
        conn.execute(
            """
            UPDATE media
            SET local_path = ?, content_type = ?, alt_text = ?
            WHERE media_id = ?
            """,
            (str(image_path), "image/png", "スクショ 画面 文字 ＯＣＲ", "media-1"),
        )

    summary = ocr.build_ocr_evidence(
        media_db_path,
        provider="local",
        limit=1,
        promote_chunks=False,
    )

    assert summary.promoted_chunks == 0
    with sqlite3.connect(media_db_path) as conn:
        raw_count = conn.execute(
            "SELECT COUNT(*) FROM memory_ocr_texts WHERE text_profile = 'raw_ocr'"
        ).fetchone()[0]
        chunk_count = conn.execute("SELECT COUNT(*) FROM memory_context_chunks").fetchone()[0]
        raw_metadata_json = conn.execute(
            """
            SELECT metadata_json
            FROM memory_ocr_texts
            WHERE text_profile = 'raw_ocr'
            LIMIT 1
            """
        ).fetchone()[0]

    raw_metadata = json.loads(str(raw_metadata_json))
    assert raw_count == 1
    assert chunk_count == 0
    assert raw_metadata["evidence_role"] == "media_text_candidate_signal"
    assert raw_metadata["answer_support_allowed"] is False
    assert raw_metadata["citation_ready"] is False

    second_pass = ocr.mark_ocr_second_pass_candidates(media_db_path)
    promotion = ocr.promote_ocr_chunks(
        media_db_path,
        include_profiles=("corrected_text",),
    )

    assert second_pass.candidates == 1
    assert second_pass.corrected_profiles == 1
    assert promotion.promoted_chunks == 1
    with sqlite3.connect(media_db_path) as conn:
        citation = conn.execute(
            """
            SELECT support_type, evidence_status, metadata_json
            FROM memory_citation_annotations
            WHERE field_path = 'media.ocr_text.corrected_text'
            LIMIT 1
            """
        ).fetchone()

    citation_metadata = json.loads(str(citation[2]))
    assert citation[:2] == ("supports_search_helper", "inference")
    assert citation_metadata["source_media_signal_role"] == "corrected_text"
    assert citation_metadata["answer_support_allowed"] is False
    assert citation_metadata["not_evidence"] is True
