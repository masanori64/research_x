from __future__ import annotations

import sqlite3
from pathlib import Path

from test_embedding_input_taxonomy import _seed_taxonomy_db

from research_x.memory.embedding_input import classify_embedding_inputs
from research_x.memory.search import search_memory
from research_x.memory.workflow import run_memory_workflow
from research_x.tool_interface.memory_tool_contract import workflow_tool_output


def test_what_did_user_say_excludes_bookmark_only_candidates(tmp_path: Path) -> None:
    db_path = _seed_filter_db(tmp_path)

    results = search_memory(
        db_path,
        "embedding",
        limit=8,
        intent="what_did_user_say",
        explain_filters=True,
    )

    source_kinds = {
        result.metadata["embedding_input_taxonomy"]["source_kind"] for result in results
    }
    explanation = results[0].metadata["embedding_filter_explanation"]
    assert "x_bookmarked_tweet" not in source_kinds
    assert explanation["intent"] == "what_did_user_say"
    assert any(
        key.startswith("intent_source_kind_excluded:x_bookmarked_tweet")
        for key in explanation["excluded_candidate_counts"]
    )


def test_bookmark_interest_preserves_non_endorsement_warning(tmp_path: Path) -> None:
    db_path = _seed_filter_db(tmp_path)

    results = search_memory(
        db_path,
        "embedding",
        limit=8,
        intent="what_did_user_bookmark",
        explain_filters=True,
    )

    assert results
    assert {
        result.metadata["embedding_input_taxonomy"]["source_kind"] for result in results
    } == {"x_bookmarked_tweet"}
    explanation = results[0].metadata["embedding_filter_explanation"]
    assert "bookmark_interest_alone_is_not_endorsement" in explanation["warnings"]


def test_workflow_tool_trace_exposes_embedding_filter_audit(tmp_path: Path) -> None:
    db_path = _seed_filter_db(tmp_path)

    workflow = run_memory_workflow(
        db_path,
        "embedding",
        limit=8,
        answer_provider="none",
        intent="what_did_user_bookmark",
        explain_filters=True,
    )
    payload = workflow_tool_output(workflow).as_dict()
    audit = payload["trace"]["retrieval_filter_audit"]

    assert audit["intent"] == "what_did_user_bookmark"
    assert audit["not_evidence"] is True
    assert audit["candidate_counts_by_source_kind"] == {"x_bookmarked_tweet": 1}
    assert "bookmark_interest_alone_is_not_endorsement" in audit["warnings"]


def _seed_filter_db(tmp_path: Path) -> Path:
    db_path = tmp_path / "filters.sqlite3"
    _seed_taxonomy_db(db_path)
    classify_embedding_inputs(db_path, write=True, report_dir=tmp_path / "reports")
    with sqlite3.connect(db_path) as conn:
        conn.execute("ALTER TABLE account_bookmarks ADD COLUMN bookmark_index INTEGER")
        conn.execute("UPDATE account_bookmarks SET bookmark_index = 1")
        conn.execute("ALTER TABLE tweets ADD COLUMN url TEXT")
        conn.execute("ALTER TABLE tweets ADD COLUMN role TEXT")
        conn.execute("ALTER TABLE media ADD COLUMN url TEXT")
        conn.execute("ALTER TABLE media ADD COLUMN alt_text TEXT")
        conn.execute("ALTER TABLE media ADD COLUMN download_status TEXT")
        conn.execute(
            """
            CREATE TABLE tweet_edges (
                parent_tweet_id TEXT,
                child_tweet_id TEXT,
                relation TEXT,
                child_also_bookmarked INTEGER DEFAULT 0
            )
            """
        )
        conn.execute(
            """
            UPDATE tweets
            SET url = 'https://x.com/example/status/' || tweet_id,
                role = 'fixture'
            """
        )
        rows = conn.execute(
            """
            SELECT doc_id, title, body, compact_text, author_screen_name, metadata_json
            FROM memory_documents
            """
        ).fetchall()
        conn.executemany(
            """
            INSERT INTO memory_document_fts (
                doc_id, title, body, compact_text, author_screen_name, metadata_json
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
    return db_path
