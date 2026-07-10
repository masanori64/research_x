from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from research_x.memory.document_hashes import (
    memory_document_embedding_text_hash,
    memory_document_source_hash,
)
from research_x.memory.embeddings import (
    _typed_text_projection,
    build_memory_embeddings,
    estimate_memory_embedding_build,
    resolve_embedding_spec,
    semantic_search_memory,
)
from research_x.memory.schema import ensure_memory_schema

CREATED_AT = "2026-07-08T00:00:00+00:00"


def test_typed_text_projection_builders_filter_and_template_by_profile(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "typed-projections.sqlite3"
    _seed_projection_docs(db_path)

    jp_estimate = estimate_memory_embedding_build(
        db_path,
        provider="local_hash",
        dimensions=32,
        embedding_profile="jp_multilingual",
    )
    code_summary = build_memory_embeddings(
        db_path,
        provider="local_hash",
        dimensions=32,
        embedding_profile="code_technical",
    )
    relation_estimate = estimate_memory_embedding_build(
        db_path,
        provider="local_hash",
        dimensions=32,
        embedding_profile="relation_context",
    )
    temporal_estimate = estimate_memory_embedding_build(
        db_path,
        provider="local_hash",
        dimensions=32,
        embedding_profile="temporal_event",
    )

    assert jp_estimate.selected == 1
    assert jp_estimate.skip_reasons["language_not_japanese_or_mixed"] == 4
    assert code_summary.selected == 1
    assert code_summary.eligible == 1
    assert code_summary.skip_reasons["not_technical_text"] == 4
    assert relation_estimate.selected == 1
    assert relation_estimate.skip_reasons["not_relation_context"] == 4
    assert temporal_estimate.selected == 1
    assert temporal_estimate.skip_reasons == {"missing_temporal_signal": 4}

    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            """
            SELECT
                e.doc_id, e.embedded_text_hash, d.embedding_text_hash,
                g.builder_version, g.input_manifest_json
            FROM memory_embeddings e
            JOIN memory_documents d ON d.doc_id = e.doc_id
            JOIN memory_projection_generations g ON g.generation_id = e.generation_id
            WHERE e.space_id = ?
            """,
            (code_summary.space_id,),
        ).fetchone()
        space_row = conn.execute(
            """
            SELECT document_scope, source_kind_filter
            FROM memory_embedding_spaces
            WHERE space_id = ?
            """,
            (code_summary.space_id,),
        ).fetchone()

    assert row[0] == "doc:code"
    assert row[1] != row[2]
    assert row[3] == "typed-text-projection-v1"
    assert json.loads(row[4])["builder_version"] == "typed-text-projection-v1"
    assert space_row == ("memory_documents", "technical_text")

    hits = semantic_search_memory(
        db_path,
        "pytest command error",
        space_id=code_summary.space_id,
        provider="local_hash",
        dimensions=32,
        embedding_profile="code_technical",
    )
    assert [hit.doc_id for hit in hits] == ["doc:code"]


def test_general_memory_projection_is_typed_not_legacy_passthrough(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "general-memory-projection.sqlite3"
    _seed_projection_docs(db_path)

    summary = build_memory_embeddings(
        db_path,
        provider="local_hash",
        dimensions=32,
        embedding_profile="general_memory",
    )

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        stored = conn.execute(
            """
            SELECT e.embedded_text_hash, d.embedding_text_hash
            FROM memory_embeddings e
            JOIN memory_documents d ON d.doc_id = e.doc_id
            WHERE e.space_id = ? AND e.doc_id = 'doc:plain'
            """,
            (summary.space_id,),
        ).fetchone()
        source_row = conn.execute(
            "SELECT * FROM memory_documents WHERE doc_id = 'doc:plain'"
        ).fetchone()

    projection, skip_reason = _typed_text_projection(
        source_row,
        spec=resolve_embedding_spec(
            provider="local_hash",
            dimensions=32,
            embedding_profile="general_memory",
        ),
    )

    assert stored["embedded_text_hash"] != stored["embedding_text_hash"]
    assert skip_reason is None
    assert projection.startswith("Template: text.general_memory.v1")
    assert "Source Kind:" in projection
    assert "Source Subkind:" in projection
    assert "Doc Type: tweet_doc" in projection
    assert "Author/Account: tester" in projection
    assert f"Date: {CREATED_AT}" in projection
    assert f"Observed Date: {CREATED_AT}" in projection
    assert "Language:" in projection
    assert "Main Text:" in projection
    assert "quiet cafe bookmark" in projection


def test_temporal_event_requires_meaningful_temporal_signal(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "temporal-signal.sqlite3"
    _seed_projection_docs(
        db_path,
        docs=(
            _doc("doc:evergreen", "tweet_doc", "quiet cafe", "quiet cafe bookmark", {}),
            _doc("doc:dated", "tweet_doc", "launch note", "launch happened on 2026-07-08", {}),
            {
                **_doc(
                    "doc:status",
                    "tweet_doc",
                    "status changed",
                    "status changed after review",
                    {"status": "ready"},
                ),
                "updated_at": "2026-07-09T00:00:00+00:00",
            },
        ),
    )

    estimate = estimate_memory_embedding_build(
        db_path,
        provider="local_hash",
        dimensions=32,
        embedding_profile="temporal_event",
    )

    assert estimate.selected == 2
    assert estimate.eligible == 2
    assert estimate.ineligible == 1
    assert estimate.skip_reasons == {"missing_temporal_signal": 1}


def test_text_bridge_and_external_fetch_profiles_share_typed_text_builder(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "bridge-projections.sqlite3"
    _seed_projection_docs(
        db_path,
        extra_docs=(
            _doc(
                "doc:media",
                "media_doc",
                "screenshot OCR",
                "OCR text from a saved screenshot",
                {"media_id": "media-1", "ocr_source": "local_ocr", "page": 1},
            ),
            _doc(
                "doc:external",
                "external_fetch_section",
                "fetched article",
                "Reader normalized article section",
                {
                    "requested_url": "https://example.com/source",
                    "final_url": "https://example.com/source",
                    "content_hash": "hash-content",
                    "prompt_injection_review_status": "reviewed",
                },
            ),
        ),
    )

    media_estimate = estimate_memory_embedding_build(
        db_path,
        provider="local_hash",
        dimensions=32,
        embedding_profile="media_text_bridge",
    )
    external_estimate = estimate_memory_embedding_build(
        db_path,
        provider="local_hash",
        dimensions=32,
        embedding_profile="external_fetch_text",
    )

    assert media_estimate.selected == 1
    assert media_estimate.skip_reasons["not_media_text"] == 6
    assert external_estimate.selected == 1
    assert external_estimate.skip_reasons["not_external_fetch_text"] == 6


def test_projection_builder_feature_detects_classification_columns(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "classification-columns.sqlite3"
    _seed_projection_docs(
        db_path,
        docs=(
            _doc("doc:classified", "tweet_doc", "English cue", "cross lingual note", {}),
            _doc("doc:blocked", "tweet_doc", "日本語メモ", "日本語の本文", {}),
        ),
    )
    with sqlite3.connect(db_path) as conn:
        _add_column_if_missing(conn, "language")
        _add_column_if_missing(conn, "embedding_eligibility")
        conn.execute("UPDATE memory_documents SET language = 'ja' WHERE doc_id = 'doc:classified'")
        conn.execute(
            """
            UPDATE memory_documents
            SET language = 'ja', embedding_eligibility = 'skip'
            WHERE doc_id = 'doc:blocked'
            """
        )

    estimate = estimate_memory_embedding_build(
        db_path,
        provider="local_hash",
        dimensions=32,
        embedding_profile="jp_multilingual",
    )

    assert estimate.selected == 1
    assert estimate.eligible == 1
    assert estimate.ineligible == 1
    assert estimate.skip_reasons == {"embedding_eligibility:skip": 1}


def _seed_projection_docs(
    db_path: Path,
    *,
    docs: tuple[dict[str, object], ...] | None = None,
    extra_docs: tuple[dict[str, object], ...] = (),
) -> None:
    documents = docs or (
        _doc("doc:ja", "tweet_doc", "日本語メモ", "日本語の検索メモ", {"language": "ja"}),
        _doc(
            "doc:code",
            "tweet_doc",
            "pytest failure",
            "uv run pytest tests --maxfail=1 raised HTTP 500 Error",
            {},
        ),
        _doc(
            "doc:relation",
            "quote_tree_doc",
            "quote chain",
            "quoted reply context for a bookmarked thread",
            {"parent_tweet_id": "root", "relation_labels": ["quote"]},
        ),
        _doc("doc:temporal", "tweet_doc", "status update", "changed status on 2026-07-08", {}),
        _doc("doc:plain", "tweet_doc", "quiet cafe", "quiet cafe bookmark", {}),
    )
    with sqlite3.connect(db_path) as conn:
        ensure_memory_schema(conn)
        for doc in (*documents, *extra_docs):
            _insert_memory_document(conn, doc)


def _doc(
    doc_id: str,
    doc_type: str,
    title: str,
    body: str,
    metadata: dict[str, object],
) -> dict[str, object]:
    return {
        "doc_id": doc_id,
        "doc_type": doc_type,
        "source_tweet_id": doc_id.removeprefix("doc:"),
        "account_id": None,
        "author_screen_name": "tester",
        "title": title,
        "body": body,
        "compact_text": body,
        "metadata_json": json.dumps(metadata, ensure_ascii=False, sort_keys=True),
        "created_at": CREATED_AT,
        "observed_at": CREATED_AT,
        "updated_at": CREATED_AT,
    }


def _insert_memory_document(conn: sqlite3.Connection, doc: dict[str, object]) -> None:
    source_doc_hash = memory_document_source_hash(doc)
    embedding_text_hash = memory_document_embedding_text_hash(doc)
    conn.execute(
        """
        INSERT INTO memory_documents (
            doc_id, doc_type, source_tweet_id, account_id, author_screen_name,
            title, body, compact_text, metadata_json,
            source_doc_hash, embedding_text_hash,
            created_at, observed_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            doc["doc_id"],
            doc["doc_type"],
            doc["source_tweet_id"],
            doc["account_id"],
            doc["author_screen_name"],
            doc["title"],
            doc["body"],
            doc["compact_text"],
            doc["metadata_json"],
            source_doc_hash,
            embedding_text_hash,
            doc["created_at"],
            doc["observed_at"],
            doc["updated_at"],
        ),
    )


def _add_column_if_missing(conn: sqlite3.Connection, column: str) -> None:
    columns = {str(row[1]) for row in conn.execute("PRAGMA table_info(memory_documents)")}
    if column not in columns:
        conn.execute(f"ALTER TABLE memory_documents ADD COLUMN {column} TEXT")
