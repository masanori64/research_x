from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from research_x.cli import main
from research_x.memory import embeddings, media_embeddings
from research_x.memory.document_hashes import (
    memory_document_embedding_text_hash,
    memory_document_source_hash,
)
from research_x.memory.embedding_spaces import FINAL_EMBEDDING_SPACE_IDS
from research_x.memory.real_api_artifacts import (
    resolve_real_api_selection_policy_alias,
    write_offline_estimate_artifacts,
)
from research_x.memory.schema import ensure_memory_schema

CREATED_AT = "2026-07-08T00:00:00+00:00"


def test_offline_estimate_artifacts_write_final_space_package_without_provider_requests(
    tmp_path: Path,
    monkeypatch,
) -> None:
    db_path = _seed_estimate_db(tmp_path)
    _fail_provider_requests(monkeypatch)

    result = write_offline_estimate_artifacts(
        db_path,
        run_id="offline-estimate-test",
        output_root=tmp_path / "runs" / "real_api",
        selection_policy="all-eligible",
    )

    run_dir = Path(result.run_dir)
    manifest = _read_json(run_dir / "run_manifest.json")
    plan = _read_json(run_dir / "embedding_space_plan.json")
    estimate_paths = sorted(run_dir.glob("embedding_estimate_*.json"))

    assert result.provider_requests_made == 0
    assert manifest["provider_execution"]["provider_requests_allowed"] is False
    assert manifest["provider_execution"]["provider_requests_made"] == 0
    assert manifest["not_evidence"] is True
    assert (run_dir / "run_manifest.json").is_file()
    assert (run_dir / "embedding_space_plan.json").is_file()
    assert len(estimate_paths) == len(FINAL_EMBEDDING_SPACE_IDS)

    plan_space_ids = {space["space_id"] for space in plan["final_spaces"]}
    assert plan_space_ids == set(FINAL_EMBEDDING_SPACE_IDS)
    assert all(
        space["authorization"]["status"] == "not_authorized"
        for space in plan["final_spaces"]
    )
    assert all(
        space["authorization"]["provider_requests_allowed"] is False
        for space in plan["final_spaces"]
    )
    assert all(
        space["coverage"]["status"] == "offline_estimate_only"
        for space in plan["final_spaces"]
    )
    assert all(space["promotion"]["status"] == "not_promoted" for space in plan["final_spaces"])
    assert all(space["estimate"]["status"] == "written" for space in plan["final_spaces"])

    text_estimate = _read_json(run_dir / "embedding_estimate_text.general_memory.v1.json")
    media_estimate = _read_json(run_dir / "embedding_estimate_media.native_multimodal.v1.json")

    assert text_estimate["estimate_kind"] == "text_embedding"
    assert text_estimate["provider_execution"]["provider_requests_made"] == 0
    assert text_estimate["selection_policy"] == {
        "applies_to_media": True,
        "requested": "all-eligible",
        "resolved": "sequential",
    }
    assert text_estimate["estimate"]["selected"] >= 1
    assert media_estimate["estimate_kind"] == "media_embedding"
    assert media_estimate["provider_execution"]["provider_requests_made"] == 0
    assert media_estimate["estimate"]["selected"] == 1


def test_selection_policy_aliases_map_to_safe_estimator_policies(tmp_path: Path) -> None:
    db_path = _seed_estimate_db(tmp_path)

    assert resolve_real_api_selection_policy_alias("representative") == "doc_type_round_robin"
    assert resolve_real_api_selection_policy_alias("all-eligible") == "sequential"

    representative = write_offline_estimate_artifacts(
        db_path,
        run_id="representative-alias",
        output_root=tmp_path / "runs" / "real_api",
        space_ids=("text.general_memory.v1",),
        limit=3,
        execution_stage="eval-slice",
        selection_policy="representative",
    )
    representative_estimate = _read_json(
        Path(representative.run_dir) / "embedding_estimate_text.general_memory.v1.json"
    )

    assert representative_estimate["selection_policy"]["requested"] == "representative"
    assert representative_estimate["selection_policy"]["resolved"] == "doc_type_round_robin"
    assert representative_estimate["estimate"]["execution_stage"] == "eval_slice"
    assert representative_estimate["estimate"]["selection_policy"] == "doc_type_round_robin"

    all_eligible = write_offline_estimate_artifacts(
        db_path,
        run_id="all-eligible-alias",
        output_root=tmp_path / "runs" / "real_api",
        space_ids=("text.general_memory.v1",),
        selection_policy="all-eligible",
    )
    all_eligible_estimate = _read_json(
        Path(all_eligible.run_dir) / "embedding_estimate_text.general_memory.v1.json"
    )

    assert all_eligible_estimate["selection_policy"]["resolved"] == "sequential"
    assert all_eligible_estimate["estimate"]["selection_policy"] == "sequential"
    assert all_eligible_estimate["estimate"]["execution_stage"] == "production_scope"


def test_offline_estimate_artifacts_cli_writes_json_package_without_provider_requests(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    db_path = _seed_estimate_db(tmp_path)
    output_root = tmp_path / "runs" / "real_api"
    _fail_provider_requests(monkeypatch)

    assert (
        main(
            [
                "memory",
                "real-api-estimate-artifacts",
                "--db",
                str(db_path),
                "--run-id",
                "offline-estimate-cli",
                "--output-root",
                str(output_root),
                "--space-id",
                "text.general_memory.v1",
                "--selection-policy",
                "representative",
                "--execution-stage",
                "eval-slice",
                "--limit",
                "3",
                "--json",
            ]
        )
        == 0
    )

    payload = json.loads(capsys.readouterr().out)
    run_dir = Path(payload["run_dir"])
    manifest = _read_json(run_dir / "run_manifest.json")
    plan = _read_json(run_dir / "embedding_space_plan.json")
    estimate = _read_json(run_dir / "embedding_estimate_text.general_memory.v1.json")

    assert payload["provider_requests_made"] == 0
    assert manifest["provider_execution"]["provider_requests_allowed"] is False
    assert manifest["provider_requests_made"] == 0
    assert manifest["selected_final_space_ids"] == ["text.general_memory.v1"]
    assert plan["selection_policy"] == {
        "requested": "representative",
        "resolved": "doc_type_round_robin",
    }
    assert estimate["selection_policy"]["resolved"] == "doc_type_round_robin"
    assert estimate["estimate"]["execution_stage"] == "eval_slice"


def _fail_provider_requests(monkeypatch) -> None:
    def fail(*args: object, **kwargs: object) -> None:
        raise AssertionError("offline estimate artifact writer must not send provider requests")

    monkeypatch.setattr(embeddings, "_post_json", fail)
    monkeypatch.setattr(embeddings, "_post_json_budgeted", fail)
    monkeypatch.setattr(media_embeddings, "_post_json", fail)
    monkeypatch.setattr(media_embeddings, "_post_json_budgeted", fail)


def _seed_estimate_db(tmp_path: Path) -> Path:
    db_path = tmp_path / "estimate.sqlite3"
    media_path = tmp_path / "image.jpg"
    media_path.write_bytes(b"fake-image")
    with sqlite3.connect(db_path) as conn:
        ensure_memory_schema(conn)
        _create_source_tables(conn)
        _insert_tweet(conn, "tweet-media", "robot screenshot UI labels")
        conn.execute(
            """
            INSERT INTO media (
                media_id, tweet_id, type, url, alt_text, local_path,
                download_status, bytes, content_type, download_error
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "media-1",
                "tweet-media",
                "photo",
                "https://example.test/image.jpg",
                "robot screenshot UI labels",
                str(media_path),
                "ok",
                media_path.stat().st_size,
                "image/jpeg",
                None,
            ),
        )
        for doc in _estimate_docs():
            _insert_memory_document(conn, doc)
    return db_path


def _create_source_tables(conn: sqlite3.Connection) -> None:
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


def _insert_tweet(conn: sqlite3.Connection, tweet_id: str, text: str) -> None:
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
            tweet_id,
            f"https://x.com/example/status/{tweet_id}",
            "tester",
            text,
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


def _estimate_docs() -> tuple[dict[str, Any], ...]:
    return (
        _doc("doc:general", "tweet_doc", "quiet cafe", "quiet cafe bookmark", {}),
        _doc("doc:ja", "tweet_doc", "日本語メモ", "日本語の検索メモ", {}),
        _doc(
            "doc:code",
            "tweet_doc",
            "pytest failure",
            "uv run pytest tests --maxfail=1 raised HTTP 500 Error",
            {"source_kind": "technical_text"},
        ),
        _doc(
            "doc:relation",
            "quote_tree_doc",
            "quote chain",
            "quoted reply context for a bookmarked thread",
            {"parent_tweet_id": "root", "relation_labels": ["quote"]},
        ),
        _doc(
            "doc:temporal",
            "tweet_doc",
            "status update",
            "changed status on 2026-07-08",
            {},
        ),
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
                "requested_url": "https://example.test/source",
                "final_url": "https://example.test/source",
                "content_hash": "hash-content",
                "prompt_injection_review_status": "reviewed",
            },
        ),
    )


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


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))
