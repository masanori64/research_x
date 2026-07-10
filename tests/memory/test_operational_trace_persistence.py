from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from research_x.cli import main
from research_x.memory import context as memory_context
from research_x.memory.answer import build_memory_answer
from research_x.memory.context import (
    CitationAnnotation,
    ContextBundle,
    ContextChunk,
    build_context_bundle,
)
from research_x.memory.corpus import build_memory_corpus
from research_x.memory.evals import EvalCase, run_memory_eval
from research_x.memory.relations import build_memory_relations
from research_x.memory.retrieval_text import build_retrieval_text_profiles
from research_x.memory.schema import ensure_memory_schema
from research_x.memory.workflow import run_memory_workflow
from research_x.tool_interface.memory_tool_contract import (
    validate_tool_output,
    workflow_tool_output,
)

TRACE_TABLES = (
    "memory_search_runs",
    "memory_search_results",
    "memory_context_chunks",
    "memory_citation_annotations",
    "memory_answer_runs",
    "memory_workflow_runs",
    "memory_workflow_steps",
    "memory_tool_calls",
    "memory_external_runs",
    "memory_external_items",
)
CREATED_AT = "2026-06-27T00:00:00+00:00"


def test_operational_workflow_persists_source_restored_trace(tmp_path: Path) -> None:
    db_path = _seed_memory_db(tmp_path)
    before = _counts(db_path)

    workflow = run_memory_workflow(
        db_path,
        "強化学習 ロボット",
        limit=2,
        answer_provider="fake",
        store=True,
    )
    output = workflow_tool_output(workflow)
    after = _counts(db_path)

    assert validate_tool_output(output) == []
    assert output.status == "answer"
    assert output.evidence_level == "citation_ready"
    assert workflow.answer is not None
    assert after["memory_workflow_runs"] == before["memory_workflow_runs"] + 1
    assert after["memory_workflow_steps"] >= before["memory_workflow_steps"] + 3
    assert after["memory_search_runs"] == before["memory_search_runs"] + 1
    assert after["memory_search_results"] >= before["memory_search_results"] + 1
    assert after["memory_context_chunks"] >= before["memory_context_chunks"] + 1
    assert after["memory_citation_annotations"] >= before["memory_citation_annotations"] + 2
    assert after["memory_answer_runs"] == before["memory_answer_runs"] + 1
    assert after["memory_tool_calls"] == before["memory_tool_calls"] + 1
    assert after["memory_external_runs"] == before["memory_external_runs"]
    assert after["memory_external_items"] == before["memory_external_items"]

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        chunk = conn.execute(
            """
            SELECT chunk_id, source_kind, source_id, source_url, metadata_json
            FROM memory_context_chunks
            WHERE run_id = ?
            ORDER BY chunk_index
            LIMIT 1
            """,
            (workflow.context_bundle.run_id,),
        ).fetchone()
        context_citation = conn.execute(
            """
            SELECT chunk_id, source_kind, source_id, metadata_json
            FROM memory_citation_annotations
            WHERE answer_id IS NULL AND chunk_id = ?
            LIMIT 1
            """,
            (chunk["chunk_id"],),
        ).fetchone()
        answer_citation = conn.execute(
            """
            SELECT chunk_id, source_kind, source_id, metadata_json
            FROM memory_citation_annotations
            WHERE answer_id = ?
            LIMIT 1
            """,
            (workflow.answer.answer_id,),
        ).fetchone()
        workflow_row = conn.execute(
            """
            SELECT status, stop_reason, metadata_json
            FROM memory_workflow_runs
            WHERE workflow_id = ?
            """,
            (workflow.workflow_id,),
        ).fetchone()

    chunk_metadata = json.loads(chunk["metadata_json"])
    context_citation_metadata = json.loads(context_citation["metadata_json"])
    answer_citation_metadata = json.loads(answer_citation["metadata_json"])
    workflow_metadata = json.loads(workflow_row["metadata_json"])

    assert chunk["source_kind"] == "local_x_db"
    assert chunk_metadata["document_id"] == chunk["source_id"]
    assert chunk_metadata["source_id"] == chunk["source_id"]
    assert chunk_metadata["source_kind"] == chunk["source_kind"]
    assert chunk_metadata["source_url"] == chunk["source_url"]
    assert chunk_metadata["source_doc_hash"]
    assert chunk_metadata["embedding_text_hash"]
    assert chunk_metadata["retrieval_text_hash"]
    assert chunk_metadata["source_bundle_id"]
    assert chunk_metadata["freshness_status"] in {"active", "recent", "possibly_stale"}
    assert chunk_metadata["lineage_status"] == "restored"
    assert context_citation_metadata["source_doc_hash"] == chunk_metadata["source_doc_hash"]
    assert context_citation_metadata["source_bundle_id"] == chunk_metadata["source_bundle_id"]
    assert context_citation_metadata["lineage_status"] == "restored"
    assert answer_citation_metadata["source_doc_hash"] == chunk_metadata["source_doc_hash"]
    assert answer_citation_metadata["source_bundle_id"] == chunk_metadata["source_bundle_id"]
    assert answer_citation_metadata["lineage_status"] == "restored"
    assert workflow_row["status"] == "ok"
    assert workflow_row["stop_reason"] == "enough_evidence"
    assert workflow_metadata["stop_condition_audit"]["answer_status"] == "ok"
    assert workflow_metadata["stop_condition_audit"]["has_local_context"] is True


def test_store_false_eval_does_not_create_operational_trace(tmp_path: Path) -> None:
    db_path = _seed_memory_db(tmp_path)
    before = _counts(db_path)
    case = EvalCase(
        query="強化学習 ロボット",
        required_any_terms=("強化学習", "ロボット"),
        question_type="citation_required",
        min_hit_score=0.0,
    )

    results = run_memory_eval(db_path, cases=(case,), limit=2, answer_provider="fake")
    after = _counts(db_path)

    assert results[0].context_chunks > 0
    assert results[0].answer_citations > 0
    assert after == before


def test_trace_persistence_keeps_audit_without_derived_artifacts(tmp_path: Path) -> None:
    db_path = _seed_memory_db(tmp_path)
    before = _counts(db_path)

    workflow = run_memory_workflow(
        db_path,
        "強化学習 ロボット",
        limit=2,
        answer_provider="fake",
        persistence="trace",
    )
    after = _counts(db_path)

    assert workflow.answer is not None
    assert workflow.metadata["parameters"]["persistence"] == "trace"
    assert after["memory_workflow_runs"] == before["memory_workflow_runs"] + 1
    assert after["memory_workflow_steps"] >= before["memory_workflow_steps"] + 3
    for table in (
        "memory_search_runs",
        "memory_search_results",
        "memory_context_chunks",
        "memory_citation_annotations",
        "memory_answer_runs",
        "memory_tool_calls",
        "memory_external_runs",
        "memory_external_items",
    ):
        assert after[table] == before[table]


def test_semantic_credential_locator_is_not_hashed_or_persisted(
    tmp_path: Path,
    monkeypatch,
) -> None:
    db_path = _seed_memory_db(tmp_path)
    monkeypatch.setattr(memory_context, "_utc_now", lambda: CREATED_AT)

    first = build_context_bundle(
        db_path,
        "強化学習 ロボット",
        semantic_api_key_env="PRIVATE_PROVIDER_PASSWORD_A",
        store=True,
    )
    second = build_context_bundle(
        db_path,
        "強化学習 ロボット",
        semantic_api_key_env="PRIVATE_PROVIDER_PASSWORD_B",
        store=False,
    )

    assert first.run_id == second.run_id
    assert first.parameters["semantic_api_key_configured"] is True
    assert second.parameters["semantic_api_key_configured"] is True
    assert "semantic_api_key_env" not in first.parameters
    with sqlite3.connect(db_path) as conn:
        stored = conn.execute(
            "SELECT parameters_json FROM memory_search_runs WHERE run_id = ?",
            (first.run_id,),
        ).fetchone()[0]
    assert "PRIVATE_PROVIDER_PASSWORD" not in stored
    assert json.loads(stored)["semantic_api_key_configured"] is True


def test_workflow_trace_does_not_persist_semantic_credential_locator(tmp_path: Path) -> None:
    db_path = _seed_memory_db(tmp_path)
    locator = "PRIVATE_PROVIDER_PASSWORD"

    workflow = run_memory_workflow(
        db_path,
        "強化学習 ロボット",
        semantic_api_key_env=locator,
        answer_provider="fake",
        persistence="artifacts",
    )

    parameters = workflow.metadata["parameters"]
    assert parameters["semantic_api_key_configured"] is True
    assert "semantic_api_key_env" not in parameters
    with sqlite3.connect(db_path) as conn:
        stored = conn.execute(
            "SELECT metadata_json FROM memory_workflow_runs WHERE workflow_id = ?",
            (workflow.workflow_id,),
        ).fetchone()[0]
    assert locator not in stored
    assert json.loads(stored)["parameters"]["semantic_api_key_configured"] is True


def test_explicit_persistence_mode_overrides_legacy_store_flag(tmp_path: Path) -> None:
    db_path = _seed_memory_db(tmp_path)
    before = _counts(db_path)

    workflow = run_memory_workflow(
        db_path,
        "強化学習 ロボット",
        answer_provider="fake",
        store=False,
        persistence="artifacts",
    )
    after = _counts(db_path)

    assert workflow.metadata["parameters"]["persistence"] == "artifacts"
    assert after["memory_workflow_runs"] == before["memory_workflow_runs"] + 1
    assert after["memory_context_chunks"] > before["memory_context_chunks"]


def test_workflow_cli_exposes_trace_only_persistence(tmp_path: Path, capsys) -> None:
    db_path = _seed_memory_db(tmp_path)
    before = _counts(db_path)

    exit_code = main(
        [
            "memory",
            "workflow",
            "--db",
            str(db_path),
            "--query",
            "強化学習 ロボット",
            "--answer-provider",
            "fake",
            "--persistence",
            "trace",
            "--json",
        ]
    )
    after = _counts(db_path)

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["metadata"]["parameters"]["persistence"] == "trace"
    assert after["memory_workflow_runs"] == before["memory_workflow_runs"] + 1
    assert after["memory_context_chunks"] == before["memory_context_chunks"]
    assert after["memory_answer_runs"] == before["memory_answer_runs"]


def test_provider_gated_workflow_persists_stop_trace_without_external_runs(
    tmp_path: Path,
) -> None:
    db_path = _seed_memory_db(tmp_path)
    before = _counts(db_path)

    workflow = run_memory_workflow(
        db_path,
        "強化学習 ロボット 今も正しい？",
        limit=2,
        answer_provider="none",
        llm_context_provider="none",
        store=True,
    )
    output = workflow_tool_output(workflow)
    after = _counts(db_path)

    assert validate_tool_output(output) == []
    assert output.status == "provider_gated"
    assert output.answer_text is None
    assert workflow.stop_reason == "external_context_needed"
    assert after["memory_workflow_runs"] == before["memory_workflow_runs"] + 1
    assert after["memory_search_runs"] == before["memory_search_runs"] + 1
    assert after["memory_context_chunks"] >= before["memory_context_chunks"] + 1
    assert after["memory_answer_runs"] == before["memory_answer_runs"]
    assert after["memory_external_runs"] == before["memory_external_runs"]
    assert after["memory_external_items"] == before["memory_external_items"]
    assert output.trace["provider_gate"]["required"] is True
    assert output.trace["skip_reason"] == "external_context_needed"


def test_fake_answer_sanitizes_source_internal_citation_markers(tmp_path: Path) -> None:
    bundle = _manual_context_bundle(
        "Text: source_documents: [1] is source text, not an answer citation marker."
    )

    answer = build_memory_answer(
        tmp_path / "manual.sqlite3",
        "fixture internal markers",
        context_bundle=bundle,
        answer_provider="fake",
        store=False,
    )

    assert answer.answer_text.count("[1]") == 1
    assert "(source marker 1)" in answer.answer_text
    assert answer.citation_annotations[0].metadata["marker_found"] is True


def _seed_memory_db(tmp_path: Path) -> Path:
    db_path = tmp_path / "x.sqlite3"
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
            CREATE TABLE ai_labels (
                label_id TEXT PRIMARY KEY,
                account_id TEXT,
                tweet_id TEXT,
                label_scope TEXT,
                category_id TEXT,
                category_label TEXT,
                confidence REAL,
                tags_json TEXT,
                summary TEXT,
                rationale TEXT,
                model TEXT,
                run_id TEXT,
                generated_at TEXT
            );
            """
        )
        conn.executemany(
            """
            INSERT INTO tweets (
                tweet_id, url, author_screen_name, text, created_at,
                first_observed_at, last_observed_at, role, collection_kind,
                providers_json, raw_json, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    "tweet-1",
                    "https://x.com/a/status/tweet-1",
                    "a",
                    "強化学習とロボットの実験メモ。カフェで読む。",
                    "2026-05-26T00:00:00+00:00",
                    "2026-05-26T00:00:00+00:00",
                    "2026-05-26T00:00:00+00:00",
                    "bookmark_root",
                    "bookmarks",
                    "[]",
                    "{}",
                    "2026-05-26T00:00:00+00:00",
                ),
                (
                    "tweet-2",
                    "https://x.com/b/status/tweet-2",
                    "b",
                    "引用元のロボット論文リンク。",
                    "2026-05-25T00:00:00+00:00",
                    "2026-05-26T00:00:00+00:00",
                    "2026-05-26T00:00:00+00:00",
                    "quoted_tweet",
                    None,
                    "[]",
                    "{}",
                    "2026-05-26T00:00:00+00:00",
                ),
            ],
        )
        conn.execute(
            """
            INSERT INTO account_bookmarks (
                account_id, tweet_id, bookmark_index, observed_at, providers_json, run_id
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            ("acct", "tweet-1", 0, "2026-05-26T00:00:00+00:00", "[]", "run"),
        )
        conn.execute(
            """
            INSERT INTO tweet_edges (
                parent_tweet_id, child_tweet_id, relation, child_also_bookmarked
            )
            VALUES (?, ?, ?, ?)
            """,
            ("tweet-1", "tweet-2", "quote", 0),
        )
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
                "tweet-1",
                "photo",
                "https://example.test/image.jpg",
                "robot image",
                "runs/media/image.jpg",
                "ok",
                123,
                "image/jpeg",
                None,
            ),
        )
        conn.execute(
            """
            INSERT INTO ai_labels (
                label_id, account_id, tweet_id, label_scope, category_id,
                category_label, confidence, tags_json, summary, rationale,
                model, run_id, generated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "label-1",
                "acct",
                "tweet-1",
                "bookmarks",
                "tech",
                "Technology",
                0.9,
                '["強化学習", "ロボット"]',
                "summary",
                "rationale",
                "fake-model",
                "run",
                "2026-05-26T00:00:00+00:00",
            ),
        )
    build_memory_corpus(db_path)
    build_memory_relations(db_path)
    build_retrieval_text_profiles(db_path)
    return db_path


def _manual_context_bundle(chunk_text: str) -> ContextBundle:
    chunk = ContextChunk(
        chunk_id="manual:chunk:1",
        run_id="manual:run",
        source_kind="local_x_db",
        source_id="tweet:manual",
        source_url="https://x.com/example/status/manual",
        provider="fixture",
        provider_role="context_builder",
        chunk_text=chunk_text,
        chunk_index=0,
        token_count=12,
        relevance_score=1.0,
        extractor_version="manual-fixture-v1",
        created_at=CREATED_AT,
        metadata={
            "source_doc_hash": "hash-manual",
            "embedding_text_hash": "embedding-hash-manual",
            "retrieval_text_hash": "retrieval-hash-manual",
            "retrieval_text_profile": "full_text",
            "retrieval_profile_kind": "full_text",
            "retrieval_text_profile_id": "profile-manual",
            "source_bundle_id": "bundle-manual",
            "lineage_status": "restored",
            "restored_at": CREATED_AT,
        },
    )
    citation = CitationAnnotation(
        citation_id="manual:citation:1",
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
        metadata=chunk.metadata,
    )
    return ContextBundle(
        run_id="manual:run",
        query="fixture internal markers",
        query_plan={"fixture": "manual"},
        parameters={"fixture": "manual"},
        retrieved_hits=[],
        context_chunks=(chunk,),
        citation_annotations=(citation,),
    )


def _counts(db_path: Path) -> dict[str, int]:
    with sqlite3.connect(db_path) as conn:
        ensure_memory_schema(conn)
        return {
            table: int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
            for table in TRACE_TABLES
        }
