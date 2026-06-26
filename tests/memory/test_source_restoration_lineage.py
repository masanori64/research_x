from __future__ import annotations

import json
from pathlib import Path

from test_operational_trace_persistence import _seed_memory_db

from research_x.cli import main
from research_x.memory.context import build_context_bundle


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
