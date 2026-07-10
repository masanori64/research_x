from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from research_x.memory.media_embeddings import (
    EXTERNAL_FETCH_TEXT_SPACE_ID,
    FIXTURE_MEDIA_PROVIDER,
    MEDIA_EXTERNAL_PROJECTION_READINESS_KIND,
    MEDIA_NATIVE_MULTIMODAL_SPACE_ID,
    MEDIA_TEXT_BRIDGE_SPACE_ID,
    build_media_embeddings,
    media_external_projection_readiness_report,
    search_media_embeddings,
    store_media_external_projection_readiness,
)
from research_x.memory.reader import extract_url_to_context
from research_x.memory.schema import ensure_memory_schema

CREATED_AT = "2026-07-08T00:00:00+00:00"


def test_media_external_projection_readiness_classifies_local_records(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "x.sqlite3"
    media_path = tmp_path / "image.jpg"
    media_path.write_bytes(b"fake-image")
    _seed_media_sources(db_path, media_path=media_path)
    _seed_media_text_rows(db_path)
    extract_url_to_context(
        db_path,
        "https://example.com/readiness",
        provider="fake",
        metadata={"storage_rights": "stored_for_user_research"},
    )
    _insert_blocked_fetch_artifact(db_path)

    report = store_media_external_projection_readiness(
        db_path,
        run_id="media-readiness-test",
    )
    spaces = {space.space_id: space for space in report.spaces}

    text_bridge = spaces[MEDIA_TEXT_BRIDGE_SPACE_ID]
    assert text_bridge.state == "eligible"
    assert text_bridge.eligible_records == 2
    assert text_bridge.blocked_reasons == {"media_text_source_not_restored": 1}
    assert text_bridge.answer_support_allowed is False
    assert text_bridge.citation_ready is False
    assert text_bridge.source_restoration_required is True

    native_media = spaces[MEDIA_NATIVE_MULTIMODAL_SPACE_ID]
    assert native_media.state == "eligible"
    assert native_media.eligible_records == 1
    assert native_media.skip_reasons == {"missing_local_path": 1}
    assert native_media.provider_gate == (
        "provider_authorization_required_before_native_media_embedding"
    )
    assert native_media.not_evidence_reason == (
        "native_media_vector_candidate_only_context_citation_required"
    )

    external_fetch = spaces[EXTERNAL_FETCH_TEXT_SPACE_ID]
    assert external_fetch.state == "eligible"
    assert external_fetch.eligible_records == 1
    assert external_fetch.blocked_reasons == {"prompt_injection_review_not_passed": 1}
    assert external_fetch.storage_rights_policy == "approved-fetch-artifact-text"
    assert report.status == "has_blocked_records"

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT space_id, status, source_count, projected_count, skipped_count,
                   coverage_json, metadata_json, run_id
            FROM memory_projection_generations
            WHERE projection_kind = ?
            ORDER BY space_id
            """,
            (MEDIA_EXTERNAL_PROJECTION_READINESS_KIND,),
        ).fetchall()

    assert {row["space_id"] for row in rows} == {
        MEDIA_TEXT_BRIDGE_SPACE_ID,
        MEDIA_NATIVE_MULTIMODAL_SPACE_ID,
        EXTERNAL_FETCH_TEXT_SPACE_ID,
    }
    assert {row["run_id"] for row in rows} == {"media-readiness-test"}
    external_row = next(row for row in rows if row["space_id"] == EXTERNAL_FETCH_TEXT_SPACE_ID)
    external_coverage = json.loads(external_row["coverage_json"])
    external_metadata = json.loads(external_row["metadata_json"])
    assert external_row["projected_count"] == 1
    assert external_coverage["blocked_records"] == 1
    assert external_metadata["not_evidence_reason"] == (
        "external_fetch_text_candidate_requires_context_citation"
    )


def test_media_external_projection_readiness_reports_explicit_skips(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "empty.sqlite3"
    with sqlite3.connect(db_path) as conn:
        ensure_memory_schema(conn)

    report = media_external_projection_readiness_report(db_path)
    spaces = {space.space_id: space for space in report.spaces}

    assert report.status == "all_skipped"
    assert spaces[MEDIA_TEXT_BRIDGE_SPACE_ID].skip_reasons == {
        "no_media_text_candidates": 1
    }
    assert spaces[MEDIA_NATIVE_MULTIMODAL_SPACE_ID].skip_reasons == {
        "no_media_source_tables": 1
    }
    assert spaces[EXTERNAL_FETCH_TEXT_SPACE_ID].skip_reasons == {
        "no_fetch_artifacts": 1
    }


def test_native_media_vector_hit_remains_candidate_not_citation_ready(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "x.sqlite3"
    media_path = tmp_path / "image.jpg"
    media_path.write_bytes(b"fake-image")
    _seed_media_sources(db_path, media_path=media_path)

    build_media_embeddings(
        db_path,
        provider=FIXTURE_MEDIA_PROVIDER,
        dimensions=3,
        limit=1,
    )
    hits = search_media_embeddings(
        db_path,
        "robot image",
        provider=FIXTURE_MEDIA_PROVIDER,
        dimensions=3,
        limit=1,
    )

    assert hits[0].media_id == "media-1"
    assert hits[0].evidence_level == "media_source_evidence"
    assert hits[0].evidence_status == "unconfirmed_media_match"
    assert hits[0].answer_support_allowed is False
    assert hits[0].citation_ready is False
    assert hits[0].bundle["restored"] is True
    assert hits[0].bundle["answer_support_allowed"] is False
    assert hits[0].bundle["citation_ready"] is False


def _seed_media_sources(db_path: Path, *, media_path: Path) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE tweets (
                tweet_id TEXT PRIMARY KEY,
                url TEXT,
                author_screen_name TEXT,
                text TEXT,
                created_at TEXT,
                first_observed_at TEXT,
                last_observed_at TEXT,
                role TEXT,
                collection_kind TEXT,
                providers_json TEXT,
                raw_json TEXT,
                updated_at TEXT
            );
            CREATE TABLE account_bookmarks (
                account_id TEXT,
                tweet_id TEXT,
                bookmark_index INTEGER,
                observed_at TEXT,
                providers_json TEXT,
                run_id TEXT,
                PRIMARY KEY(account_id, tweet_id)
            );
            CREATE TABLE tweet_edges (
                parent_tweet_id TEXT,
                child_tweet_id TEXT,
                relation TEXT,
                child_also_bookmarked INTEGER DEFAULT 0,
                PRIMARY KEY(parent_tweet_id, child_tweet_id, relation)
            );
            CREATE TABLE media (
                media_id TEXT PRIMARY KEY,
                tweet_id TEXT,
                type TEXT,
                url TEXT,
                alt_text TEXT,
                local_path TEXT,
                download_status TEXT,
                bytes INTEGER,
                content_type TEXT,
                download_error TEXT
            );
            """
        )
        conn.execute(
            """
            INSERT INTO tweets (
                tweet_id, url, author_screen_name, text, created_at,
                first_observed_at, last_observed_at, role, collection_kind,
                providers_json, raw_json, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "tweet-1",
                "https://x.com/example/status/tweet-1",
                "robotics",
                "robot screenshot with visible text",
                CREATED_AT,
                CREATED_AT,
                CREATED_AT,
                "bookmark_root",
                "bookmarks",
                "[]",
                "{}",
                CREATED_AT,
            ),
        )
        conn.execute(
            """
            INSERT INTO account_bookmarks (
                account_id, tweet_id, bookmark_index, observed_at, providers_json, run_id
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            ("acct", "tweet-1", 0, CREATED_AT, "[]", "run"),
        )
        conn.executemany(
            """
            INSERT INTO media (
                media_id, tweet_id, type, url, alt_text, local_path,
                download_status, bytes, content_type, download_error
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                (
                    "media-1",
                    "tweet-1",
                    "photo",
                    "https://example.test/image.jpg",
                    "robot screenshot UI with visible labels",
                    str(media_path),
                    "ok",
                    media_path.stat().st_size,
                    "image/jpeg",
                    None,
                ),
                (
                    "media-2",
                    "tweet-1",
                    "photo",
                    "https://example.test/missing.jpg",
                    "",
                    "",
                    "missing",
                    0,
                    "image/jpeg",
                    "not downloaded",
                ),
            ),
        )
        ensure_memory_schema(conn)


def _seed_media_text_rows(db_path: Path) -> None:
    with sqlite3.connect(db_path) as conn:
        ensure_memory_schema(conn)
        conn.executemany(
            """
            INSERT INTO memory_ocr_texts (
                text_id, ocr_run_id, region_id, media_id, provider, model,
                ocr_profile, text_profile, parent_text_id, raw_ocr_text,
                normalized_text, corrected_text, confidence, evidence_status,
                source_image_hash, region_hash, quality_flags_json,
                second_pass_status, second_pass_reason, created_at, metadata_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                (
                    "ocr-text-1",
                    "ocr-run",
                    "region-1",
                    "media-1",
                    "fake",
                    "fake-ocr",
                    "default",
                    "raw_ocr",
                    None,
                    "Visible robot label",
                    "Visible robot label",
                    None,
                    0.9,
                    "fact",
                    "source-image-hash",
                    "region-hash",
                    "{}",
                    "not_needed",
                    None,
                    CREATED_AT,
                    "{}",
                ),
                (
                    "ocr-text-orphan",
                    "ocr-run",
                    "region-missing",
                    "missing-media",
                    "fake",
                    "fake-ocr",
                    "default",
                    "raw_ocr",
                    None,
                    "Orphan text",
                    "Orphan text",
                    None,
                    0.8,
                    "fact",
                    "source-image-hash",
                    "region-hash-orphan",
                    "{}",
                    "not_needed",
                    None,
                    CREATED_AT,
                    "{}",
                ),
            ),
        )


def _insert_blocked_fetch_artifact(db_path: Path) -> None:
    with sqlite3.connect(db_path) as conn:
        ensure_memory_schema(conn)
        conn.execute(
            """
            INSERT INTO memory_fetch_artifacts (
                artifact_id, tool_call_id, run_id, requested_url, final_url,
                fetched_at, retrieved_at, content_type, status_code, response_hash,
                extracted_text_hash, raw_artifact_path, prompt_injection_review,
                prompt_injection_status, prompt_injection_flags_json, storage_rights,
                fetch_provider, metadata_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "fetch-blocked",
                "tool-blocked",
                "run-blocked",
                "https://example.com/injected",
                "https://example.com/injected",
                CREATED_AT,
                CREATED_AT,
                "text/html",
                200,
                "response-hash",
                "text-hash",
                "",
                "deterministic-prompt-injection-v1",
                "review_required",
                json.dumps(["ignore_previous_instructions"]),
                "stored_for_user_research",
                "fake",
                json.dumps(
                    {
                        "source_bundle_id": "source-bundle-blocked",
                        "lineage_status": "restored",
                    },
                    sort_keys=True,
                ),
            ),
        )
