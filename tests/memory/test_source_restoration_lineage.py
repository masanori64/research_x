from __future__ import annotations

import json
from pathlib import Path

from test_operational_trace_persistence import _seed_memory_db

from research_x.cli import main
from research_x.memory.context import _source_lineage_metadata, build_context_bundle
from research_x.memory.evidence import build_evidence_hits_for_doc_ids
from research_x.memory.source_identity import source_bundle_id, source_restore_id

CREATED_AT = "2026-06-27T00:00:00+00:00"


def test_context_and_citation_store_generation_time_lineage_snapshot(
    tmp_path: Path,
) -> None:
    db_path = _seed_memory_db(tmp_path)

    bundle = build_context_bundle(
        db_path,
        "強化学習 ロボット",
        limit=1,
        doc_type="bookmark_doc",
        store=False,
    )
    chunk = bundle.context_chunks[0]
    citation = bundle.citation_annotations[0]

    for metadata in (chunk.metadata, citation.metadata):
        assert metadata["source_doc_hash"]
        assert metadata["embedding_text_hash"]
        assert metadata["retrieval_text_hash"]
        assert metadata["retrieval_text_profile"]
        assert metadata["retrieval_profile_kind"] == metadata["retrieval_text_profile"]
        assert metadata["source_bundle_id"]
        assert metadata["source_updated_at"] == metadata["document_updated_at"]
        assert metadata["restored_at"]
        assert metadata["lineage_status"] == "restored"
        assert metadata["source_bundle_id"] == source_bundle_id(
            metadata["document_id"],
            metadata["source_doc_hash"],
        )
        assert metadata["source_restore_id"] == source_restore_id(
            metadata["document_id"],
            metadata["source_doc_hash"],
        )


def test_context_fallback_lineage_uses_canonical_source_bundle_id() -> None:
    metadata = _source_lineage_metadata(
        hit={},
        evidence={"source_doc_hash": "source-hash-1"},
        source_kind="local_x_db",
        source_id="tweet:1",
        source_url="https://x.com/example/status/1",
        restored_at=CREATED_AT,
    )

    assert metadata["source_bundle_id"] == source_bundle_id("tweet:1", "source-hash-1")
    assert metadata["source_restore_id"] == source_restore_id("tweet:1", "source-hash-1")


def test_evidence_hits_emit_both_compatible_lineage_ids(tmp_path: Path) -> None:
    db_path = _seed_memory_db(tmp_path)

    hits = build_evidence_hits_for_doc_ids(
        db_path,
        "強化学習 ロボット",
        ("bookmark:acct:tweet-1",),
    )

    assert len(hits) == 1
    for lineage in (
        hits[0]["evidence"]["source_lineage"],
        hits[0]["metadata"]["source_lineage"],
    ):
        assert lineage["source_bundle_id"] == source_bundle_id(
            lineage["document_id"], lineage["source_doc_hash"]
        )
        assert lineage["source_restore_id"] == source_restore_id(
            lineage["document_id"], lineage["source_doc_hash"]
        )
        assert lineage["lineage_status"] == "restored"


def test_memory_audit_json_cli_emits_review_artifact_payload(
    tmp_path: Path,
    capsys,
) -> None:
    db_path = _seed_memory_db(tmp_path)

    assert main(["memory", "audit", "--db", str(db_path), "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["db_path"] == str(db_path)
    assert "claim_citation_issues" in payload
    assert "freshness_lineage_issues" in payload
    assert "warnings" in payload
