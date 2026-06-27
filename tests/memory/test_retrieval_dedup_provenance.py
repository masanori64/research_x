from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from test_operational_trace_persistence import _seed_memory_db

from research_x.memory.answer import build_memory_answer
from research_x.memory.context import CitationAnnotation, build_context_bundle
from research_x.memory.corpus import build_memory_corpus
from research_x.memory.evals import load_eval_cases
from research_x.memory.evidence_invariants import (
    citation_block_reasons,
    citation_evidence_key,
    citation_marks_conflict,
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
    assert metadata["lineage_variant_count"] >= 2
    assert len(metadata["lineage_variants"]) >= 2
    assert metadata["source_hash_variant_count"] >= 1


def test_search_dedupes_same_tweet_same_hash_without_variant_warning(
    tmp_path: Path,
) -> None:
    db_path = _seed_cross_account_memory_db(tmp_path)
    _force_tweet_source_hash(db_path, "tweet-1", "same-source-hash")

    results = search_memory(db_path, "強化学習 ロボット", limit=10)

    same_tweet = [
        result
        for result in results
        if result.metadata.get("primary_evidence_source_id") == "tweet-1"
    ]
    assert len(same_tweet) == 1
    metadata = same_tweet[0].metadata
    assert metadata["source_doc_hashes"] == ["same-source-hash"]
    assert metadata["source_hash_variant_count"] == 1
    assert metadata["source_doc_hash_status"] == "consistent"
    assert metadata["freshness_variants"] == ["active"]
    assert metadata["stale_lineage_variant_present"] is False
    assert "lineage_variant_warning" not in metadata


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
    assert restore["lineage_variant_count"] >= 2
    assert len(restore["lineage_variants"]) >= 2


def test_stale_hash_variant_blocks_citation_ready_without_silent_collapse(
    tmp_path: Path,
) -> None:
    db_path = _seed_cross_account_memory_db(tmp_path)
    _mark_doc_lineage_variant(
        db_path,
        "tweet:tweet-1",
        source_doc_hash="stale-source-hash",
        metadata_updates={"freshness_status": "stale"},
    )
    query = "強化学習 ロボット"

    bundle = build_context_bundle(db_path, query, limit=1, store=True)
    citation = bundle.citation_annotations[0]
    metadata = citation.metadata

    assert metadata["primary_evidence_source_id"] == "tweet-1"
    assert metadata["stale_lineage_variant_present"] is True
    assert metadata["lineage_variant_warning"] == "stale"
    assert metadata["source_hash_variant_count"] > 1
    assert "stale" in metadata["freshness_variants"]
    assert "stale_evidence" in citation_block_reasons(citation)

    workflow = _workflow(query=query, bundle=bundle, answer=None)
    output = workflow_tool_output(workflow)

    assert output.status == "needs_review"
    assert output.citations[0].citation_ready is False
    restore = output.citations[0].restore
    assert restore["stale_lineage_variant_present"] is True
    assert restore["lineage_variant_warning"] == "stale"
    assert any(
        variant["representative_reason"] == "duplicate_stale_lineage_variant"
        for variant in restore["lineage_variants"]
    )


def test_conflicting_hash_variant_blocks_as_conflicting_evidence(
    tmp_path: Path,
) -> None:
    db_path = _seed_cross_account_memory_db(tmp_path)
    _mark_doc_lineage_variant(
        db_path,
        "tweet:tweet-1",
        source_doc_hash="conflict-source-hash",
        metadata_updates={"source_doc_hash_status": "conflict"},
    )

    bundle = build_context_bundle(db_path, "強化学習 ロボット", limit=1, store=True)
    citation = bundle.citation_annotations[0]
    metadata = citation.metadata

    assert metadata["conflict_lineage_variant_present"] is True
    assert metadata["lineage_variant_warning"] == "conflict"
    assert metadata["source_doc_hash_status"] == "conflict"
    assert citation_marks_conflict(citation) is True
    assert "conflicting_evidence" in citation_block_reasons(citation)


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
    same_hash = by_family["dedup_same_source_same_hash"]
    stale_variant = by_family["dedup_same_source_stale_hash_variant"]
    conflict_variant = by_family["dedup_same_source_conflict_hash_variant"]
    distinct_tweet_conflict = by_family["dedup_same_text_distinct_tweet_conflict"]

    assert same_source.expected_unique_evidence_count == 1
    assert same_source.max_duplicate_support_count == 0
    assert same_source.require_provenance_preserved is True
    assert same_source.forbid_duplicate_citation_support is True
    assert distinct_conflict.expected_unique_evidence_count == 2
    assert distinct_conflict.expected_answerability_status == "conflicting"
    assert same_hash.expected_unique_evidence_count == 1
    assert same_hash.require_provenance_preserved is True
    assert stale_variant.expected_answerability_status == "stale_only"
    assert stale_variant.forbid_stale_evidence_support is True
    assert conflict_variant.expected_answerability_status == "conflicting"
    assert distinct_tweet_conflict.expected_unique_evidence_count == 2


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


def _force_tweet_source_hash(db_path: Path, tweet_id: str, source_doc_hash: str) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            UPDATE memory_documents
            SET source_doc_hash = ?
            WHERE source_tweet_id = ?
            """,
            (source_doc_hash, tweet_id),
        )


def _mark_doc_lineage_variant(
    db_path: Path,
    doc_id: str,
    *,
    source_doc_hash: str,
    metadata_updates: dict[str, Any],
) -> None:
    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            "SELECT metadata_json FROM memory_documents WHERE doc_id = ?",
            (doc_id,),
        ).fetchone()
        assert row is not None
        metadata = json.loads(row[0] or "{}")
        metadata.update(metadata_updates)
        conn.execute(
            """
            UPDATE memory_documents
            SET source_doc_hash = ?, metadata_json = ?
            WHERE doc_id = ?
            """,
            (
                source_doc_hash,
                json.dumps(metadata, ensure_ascii=False, sort_keys=True),
                doc_id,
            ),
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
        "embedding_text_hash": f"embedding-{source_id}",
        "retrieval_text_hash": f"retrieval-{source_id}",
        "retrieval_text_profile": "full_text",
        "retrieval_profile_kind": "full_text",
        "retrieval_text_profile_id": f"profile-{source_id}",
        "source_bundle_id": f"bundle-{source_id}",
        "lineage_status": "restored",
        "restored_at": CREATED_AT,
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
