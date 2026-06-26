from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from test_operational_trace_persistence import _seed_memory_db

from research_x.memory.answer import build_memory_answer
from research_x.memory.context import CitationAnnotation, build_context_bundle
from research_x.memory.corpus import build_memory_corpus
from research_x.memory.evals import load_eval_cases
from research_x.memory.evidence_invariants import (
    citation_evidence_key,
    duplicate_evidence_count,
    unique_evidence_count,
)
from research_x.memory.relations import build_memory_relations
from research_x.memory.retrieval_text import build_retrieval_text_profiles
from research_x.memory.search import search_memory
from research_x.memory.workflow import MemoryWorkflow
from research_x.tool_interface.memory_tool_contract import (
    validate_tool_output,
    workflow_tool_output,
)

CREATED_AT = "2026-06-27T00:00:00+00:00"
DEDUP_FIXTURE = Path("tests/fixtures/memory_eval_quality/dedup.jsonl")


def test_search_dedupes_same_tweet_without_losing_bookmark_provenance(
    tmp_path: Path,
) -> None:
    db_path = _seed_cross_account_memory_db(tmp_path)

    results = search_memory(db_path, "強化学習 ロボット", limit=10)

    same_tweet = [
        result
        for result in results
        if result.metadata.get("primary_evidence_source_id") == "tweet-1"
    ]
    assert len(same_tweet) == 1
    metadata = same_tweet[0].metadata
    assert metadata["primary_evidence_identity"]["identity_kind"] == "tweet"
    assert metadata["primary_evidence_key"] == "local_x_db|tweet|tweet-1"
    assert set(metadata["bookmark_accounts"]) == {"acct", "acct-b"}
    assert {"bookmark:acct:tweet-1", "bookmark:acct-b:tweet-1"} <= set(
        metadata["source_doc_ids"]
    )
    assert metadata["duplicate_support_suppressed_count"] >= 1
    assert len(metadata["provenance_sources"]) >= 2


def test_context_citation_and_tool_output_preserve_dedup_provenance(
    tmp_path: Path,
) -> None:
    db_path = _seed_cross_account_memory_db(tmp_path)
    query = "強化学習 ロボット"

    bundle = build_context_bundle(db_path, query, limit=1, store=True)
    assert len(bundle.context_chunks) == 1
    assert len(bundle.citation_annotations) == 1
    chunk = bundle.context_chunks[0]
    citation = bundle.citation_annotations[0]

    for metadata in (chunk.metadata, citation.metadata):
        assert metadata["primary_evidence_source_id"] == "tweet-1"
        assert metadata["primary_evidence_hash"]
        assert set(metadata["bookmark_accounts"]) == {"acct", "acct-b"}
        assert metadata["duplicate_support_suppressed_count"] >= 1
        assert len(metadata["provenance_sources"]) >= 2

    assert unique_evidence_count((citation,)) == 1
    assert duplicate_evidence_count((citation,)) == 0

    answer = build_memory_answer(db_path, query, context_bundle=bundle, store=False)
    workflow = _workflow(query=query, bundle=bundle, answer=answer)
    output = workflow_tool_output(workflow)

    assert validate_tool_output(output) == []
    assert output.status == "answer"
    restore = output.citations[0].restore
    assert restore["primary_evidence_key"] == "local_x_db|tweet|tweet-1"
    assert set(restore["bookmark_accounts"]) == {"acct", "acct-b"}
    assert restore["duplicate_support_suppressed_count"] >= 1
    assert len(restore["provenance_sources"]) >= 2


def test_distinct_conflicting_sources_are_not_deduped_by_text_similarity() -> None:
    first = _citation_for_identity(
        "citation-a",
        source_id="tweet-a",
        identity_hash="identity-a",
        support_type="supports_answer",
    )
    second = _citation_for_identity(
        "citation-b",
        source_id="tweet-b",
        identity_hash="identity-b",
        support_type="contradicts",
    )

    assert citation_evidence_key(first) != citation_evidence_key(second)
    assert unique_evidence_count((first, second)) == 2
    assert duplicate_evidence_count((first, second)) == 0


def test_dedup_fixture_file_declares_identity_and_conflict_boundaries() -> None:
    cases = load_eval_cases(DEDUP_FIXTURE)

    by_family = {case.fixture_family: case for case in cases}
    same_source = by_family["dedup_same_source"]
    distinct_conflict = by_family["dedup_distinct_conflict"]

    assert same_source.expected_unique_evidence_count == 1
    assert same_source.max_duplicate_support_count == 0
    assert same_source.require_provenance_preserved is True
    assert same_source.forbid_duplicate_citation_support is True
    assert distinct_conflict.expected_unique_evidence_count == 2
    assert distinct_conflict.expected_answerability_status == "conflicting"


def _seed_cross_account_memory_db(tmp_path: Path) -> Path:
    db_path = _seed_memory_db(tmp_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO account_bookmarks (
                account_id, tweet_id, bookmark_index, observed_at, providers_json, run_id
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            ("acct-b", "tweet-1", 1, "2026-05-27T00:00:00+00:00", "[]", "run-b"),
        )
    build_memory_corpus(db_path)
    build_memory_relations(db_path)
    build_retrieval_text_profiles(db_path)
    return db_path


def _workflow(*, query: str, bundle: Any, answer: Any) -> MemoryWorkflow:
    return MemoryWorkflow(
        workflow_id="workflow-dedup-provenance",
        query=query,
        route="local_memory_search",
        status="ok",
        stop_reason="enough_evidence",
        started_at=CREATED_AT,
        finished_at=CREATED_AT,
        metadata={
            "parameters": {"answer_provider": "fake", "llm_context_provider": "none"},
            "stop_condition_audit": {"has_local_context": True},
            "route_plan": {"route": "local_memory_search"},
        },
        steps=(),
        context_bundle=bundle,
        answer=answer,
    )


def _citation_for_identity(
    citation_id: str,
    *,
    source_id: str,
    identity_hash: str,
    support_type: str,
) -> CitationAnnotation:
    metadata = {
        "source_doc_hash": "same-normalized-text-hash",
        "source_bundle_id": f"bundle-{source_id}",
        "marker_found": True,
        "primary_evidence_identity": {
            "source_kind": "local_x_db",
            "identity_kind": "tweet",
            "source_id": source_id,
            "identity_key": f"local_x_db|tweet|{source_id}",
            "identity_hash": identity_hash,
        },
        "primary_evidence_key": f"local_x_db|tweet|{source_id}",
        "primary_evidence_source_id": source_id,
        "primary_evidence_hash": identity_hash,
        "provenance_sources": [{"doc_id": f"tweet:{source_id}", "source_tweet_id": source_id}],
    }
    return CitationAnnotation(
        citation_id=citation_id,
        answer_id=None,
        chunk_id=f"chunk-{source_id}",
        source_kind="local_x_db",
        source_id=f"tweet:{source_id}",
        source_url=f"https://x.com/example/status/{source_id}",
        title="same normalized claim",
        field_path="context_chunks[0]",
        support_type=support_type,
        evidence_status="fact",
        confidence=1.0,
        created_at=CREATED_AT,
        metadata=metadata,
    )
