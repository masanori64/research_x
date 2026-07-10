from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1] / "memory"))

from test_operational_trace_persistence import _seed_memory_db

from research_x.memory.source_identity import source_bundle_id, source_restore_id
from research_x.memory.workflow import run_memory_workflow
from research_x.tool_interface.memory_tool_contract import (
    validate_tool_output,
    validate_tool_output_against_db,
    workflow_tool_output,
    workflow_tool_output_for_ai,
)


def test_tool_output_answer_validates_against_stored_lineage(tmp_path: Path) -> None:
    db_path = _seed_memory_db(tmp_path)

    workflow = run_memory_workflow(
        db_path,
        "強化学習 ロボット",
        limit=2,
        answer_provider="fake",
        store=True,
    )
    output = workflow_tool_output(workflow)

    assert validate_tool_output(output) == []
    assert validate_tool_output_against_db(output, db_path) == []

    restore = output.citations[0].restore
    assert restore["source_bundle_id"] == source_bundle_id(
        output.citations[0].source_id,
        restore["source_doc_hash"],
    )
    assert restore["source_restore_id"] == source_restore_id(
        output.citations[0].source_id,
        restore["source_doc_hash"],
    )


def test_db_validator_accepts_either_compatible_lineage_identifier(
    tmp_path: Path,
) -> None:
    db_path = _seed_memory_db(tmp_path)
    workflow = run_memory_workflow(
        db_path,
        "強化学習 ロボット",
        limit=1,
        answer_provider="fake",
        store=True,
    )
    output = workflow_tool_output(workflow)
    restore = output.citations[0].restore

    for omitted_key in ("source_bundle_id", "source_restore_id"):
        omitted_value = restore.pop(omitted_key)
        assert validate_tool_output(output) == []
        assert validate_tool_output_against_db(output, db_path) == []
        restore[omitted_key] = omitted_value


def test_db_validator_rejects_a_forged_identifier_when_both_are_present(
    tmp_path: Path,
) -> None:
    db_path = _seed_memory_db(tmp_path)
    workflow = run_memory_workflow(
        db_path,
        "強化学習 ロボット",
        limit=1,
        answer_provider="fake",
        store=True,
    )
    output = workflow_tool_output(workflow)
    output.citations[0].restore["source_bundle_id"] = "forged-bundle-id"

    errors = validate_tool_output_against_db(output, db_path)

    assert any("source_bundle_id is not reproducible" in error for error in errors)


def test_payload_only_validator_rejects_forged_local_x_db_lineage() -> None:
    payload = _stored_output_payload_without_db_mutation()
    payload["citations"][0]["restore"]["source_doc_hash"] = ""
    payload["citations"][0]["restore"]["source_restored"] = True
    payload["citations"][0]["restore"]["citation_ready"] = True

    errors = validate_tool_output(payload)

    assert any("answer status requires restored citations" in error for error in errors)


def test_db_validator_rejects_missing_context_chunk_lineage(tmp_path: Path) -> None:
    db_path = _seed_memory_db(tmp_path)
    workflow = run_memory_workflow(
        db_path,
        "強化学習 ロボット",
        limit=1,
        answer_provider="fake",
        store=True,
    )
    output = workflow_tool_output(workflow)
    chunk_id = output.citations[0].chunk_id

    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            "SELECT metadata_json FROM memory_context_chunks WHERE chunk_id = ?",
            (chunk_id,),
        ).fetchone()
        assert row is not None
        metadata = json.loads(row[0])
        metadata.pop("source_doc_hash", None)
        metadata.pop("source_bundle_id", None)
        metadata.pop("source_restore_id", None)
        source_lineage = metadata.get("source_lineage")
        if isinstance(source_lineage, dict):
            source_lineage.pop("source_doc_hash", None)
            source_lineage.pop("source_bundle_id", None)
            source_lineage.pop("source_restore_id", None)
        conn.execute(
            "UPDATE memory_context_chunks SET metadata_json = ? WHERE chunk_id = ?",
            (json.dumps(metadata, ensure_ascii=False, sort_keys=True), chunk_id),
        )

    errors = validate_tool_output_against_db(output, db_path)

    assert any("chunk missing source_doc_hash" in error for error in errors)
    assert any(
        "chunk missing compatible source lineage identifier" in error
        for error in errors
    )


def test_ai_tool_output_downgrades_answer_when_db_restoration_fails(
    tmp_path: Path,
) -> None:
    db_path = _seed_memory_db(tmp_path)
    workflow = run_memory_workflow(
        db_path,
        "強化学習 ロボット",
        limit=1,
        answer_provider="fake",
        store=True,
    )

    with sqlite3.connect(db_path) as conn:
        conn.execute("DELETE FROM memory_context_chunks")

    output = workflow_tool_output_for_ai(workflow, db_path=db_path)

    assert validate_tool_output(output) == []
    assert output.status == "source_not_restored"
    assert output.evidence_level == "context_chunk"
    assert output.answer_text is None
    assert output.trace["db_backed_restoration_validation"]["status"] == "failed"
    assert output.trace["db_backed_restoration_validation"]["required_for_answer"] is True


def test_ai_tool_output_without_db_path_does_not_emit_answer(
    tmp_path: Path,
) -> None:
    db_path = _seed_memory_db(tmp_path)
    workflow = run_memory_workflow(
        db_path,
        "強化学習 ロボット",
        limit=1,
        answer_provider="fake",
        store=True,
    )

    output = workflow_tool_output_for_ai(workflow)

    assert validate_tool_output(output) == []
    assert output.status == "source_not_restored"
    assert output.evidence_level == "context_chunk"
    assert output.answer_text is None
    assert output.trace["db_backed_restoration_validation"] == {
        "status": "missing_db_path",
        "required_for_answer": True,
        "error_count": 1,
        "errors": [
            (
                "research_x.memory.workflow: answer status requires DB-backed "
                "restoration validation"
            )
        ],
    }


def test_db_validator_rejects_stale_source_doc_hash(tmp_path: Path) -> None:
    db_path = _seed_memory_db(tmp_path)
    workflow = run_memory_workflow(
        db_path,
        "強化学習 ロボット",
        limit=1,
        answer_provider="fake",
        store=True,
    )
    output = workflow_tool_output(workflow)
    source_id = output.citations[0].source_id

    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "UPDATE memory_documents SET compact_text = ? WHERE doc_id = ?",
            ("changed text after answer generation", source_id),
        )

    errors = validate_tool_output_against_db(output, db_path)

    assert any("source document hash is stale" in error for error in errors)
    assert any("restore source_doc_hash is stale" in error for error in errors)


def _stored_output_payload_without_db_mutation() -> dict[str, object]:
    metadata = {
        "source_doc_hash": "hash-1",
        "embedding_text_hash": "embedding-hash-1",
        "retrieval_text_hash": "retrieval-hash-1",
        "retrieval_text_profile": "full_text",
        "retrieval_profile_kind": "full_text",
        "retrieval_text_profile_id": "profile-1",
        "source_bundle_id": "bundle-1",
        "lineage_status": "restored",
        "marker_found": True,
    }
    return {
        "contract_version": "research-x-ai-tool-v1",
        "tool_kind": "research_x.memory.workflow",
        "query": "fixture",
        "status": "answer",
        "evidence_level": "citation_ready",
        "answer_text": "answer [1]",
        "citations": [
            {
                "citation_id": "citation-1",
                "chunk_id": "chunk-1",
                "source_kind": "local_x_db",
                "source_id": "tweet:1",
                "source_url": "https://x.com/example/status/1",
                "title": "fixture",
                "evidence_status": "fact",
                "citation_ready": True,
                "restore": {
                    "context_run_id": "context-run",
                    "chunk_id": "chunk-1",
                    "source_kind": "local_x_db",
                    "source_id": "tweet:1",
                    "source_url": "https://x.com/example/status/1",
                    "field_path": "context_chunks[0]",
                    "context_chunk_restored": True,
                    "source_restored": True,
                    "citation_ready": True,
                    "block_reasons": [],
                    **metadata,
                },
            }
        ],
        "trace": {
            "answerability_status": "answerable",
            "stop_reason": "enough_evidence",
            "provider_gate": {"required": False},
            "citation_quality": {"citation_count": 1},
            "citation_restoration": {"status": "restored"},
            "pointer_offload_verification": {"status": "no_pointer_artifacts"},
            "fixture_limitations": {"provider_free_fixture": True},
        },
    }
