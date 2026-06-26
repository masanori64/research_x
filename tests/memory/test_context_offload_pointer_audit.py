from __future__ import annotations

import json
from pathlib import Path

from research_x.memory.context_budget import (
    ContextBudgetPolicy,
    budget_json_payload,
    verify_offload_pointer,
)


def test_context_offload_pointer_has_contract_fields_and_verifies(
    tmp_path: Path,
) -> None:
    payload = _payload()
    original_text = payload["context_chunks"][0]["chunk_text"]
    policy = ContextBudgetPolicy(
        max_output_chars=500,
        max_inline_chunk_chars=80,
        preview_chars=40,
        offload_dir=tmp_path / "offloads",
    )

    budgeted = budget_json_payload(payload, policy=policy, payload_kind="memory_context")
    chunk = budgeted.payload["context_chunks"][0]
    pointer = chunk["metadata"]["offload_pointer"]
    artifact = json.loads(Path(pointer["artifact_path"]).read_text(encoding="utf-8"))
    result = verify_offload_pointer(pointer)

    assert pointer["artifact_kind"] == "context_offload"
    assert pointer["owner_plane"] == "research_x_runtime"
    assert pointer["not_evidence"] is True
    assert "not citations or answer evidence" in pointer["restore_hint"]
    assert artifact["artifact_kind"] == pointer["artifact_kind"]
    assert artifact["owner_plane"] == pointer["owner_plane"]
    assert artifact["not_evidence"] is True
    assert artifact["content"] == original_text
    assert chunk["metadata"]["not_evidence"] is True
    assert chunk["metadata"]["answer_support_allowed"] is False
    assert chunk["metadata"]["evidence_status"] == "preview_only"
    assert chunk["metadata"]["preview_kind"] == "context_offload_preview"
    assert "preview_only_not_evidence: true" in chunk["chunk_text"]
    assert result.status == "usable_pointer"
    assert result.issues == ()
    assert result.sha256_match is True
    assert result.char_count_match is True
    assert result.byte_count_match is True


def test_context_offload_pointer_detects_stale_artifact_content(
    tmp_path: Path,
) -> None:
    pointer = _budgeted_pointer(tmp_path)
    artifact_path = Path(pointer["artifact_path"])
    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
    artifact["content"] += " drift"
    artifact_path.write_text(
        json.dumps(artifact, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    result = verify_offload_pointer(pointer)

    assert result.status == "stale_hash"
    assert "stale_hash" in result.issues
    assert "stale_char_count" in result.issues
    assert "stale_byte_count" in result.issues


def test_context_offload_pointer_detects_not_evidence_violation(
    tmp_path: Path,
) -> None:
    pointer = dict(_budgeted_pointer(tmp_path))
    pointer["not_evidence"] = False

    result = verify_offload_pointer(pointer)

    assert result.status == "not_evidence_violation"
    assert "not_evidence_violation" in result.issues


def test_context_offload_pointer_detects_missing_and_unsupported_targets(
    tmp_path: Path,
) -> None:
    pointer = dict(_budgeted_pointer(tmp_path))
    missing_pointer = dict(pointer)
    missing_pointer["artifact_path"] = str(tmp_path / "missing.json")
    bad_kind_pointer = dict(pointer)
    bad_kind_pointer["artifact_kind"] = "answer_evidence"

    missing = verify_offload_pointer(missing_pointer)
    bad_kind = verify_offload_pointer(bad_kind_pointer)

    assert missing.status == "missing_artifact"
    assert "missing_artifact" in missing.issues
    assert bad_kind.status == "unsupported_artifact_kind"
    assert "unsupported_artifact_kind:answer_evidence" in bad_kind.issues


def _budgeted_pointer(tmp_path: Path) -> dict[str, object]:
    policy = ContextBudgetPolicy(
        max_output_chars=500,
        max_inline_chunk_chars=80,
        preview_chars=40,
        offload_dir=tmp_path / "offloads",
    )
    budgeted = budget_json_payload(_payload(), policy=policy, payload_kind="memory_context")
    return budgeted.payload["context_chunks"][0]["metadata"]["offload_pointer"]


def _payload() -> dict[str, object]:
    return {
        "run_id": "pointer-audit-test",
        "context_chunks": [
            {
                "chunk_id": "chunk-1",
                "source_kind": "local_x_db",
                "source_id": "tweet-1",
                "source_url": "https://x.com/example/status/1",
                "chunk_text": "source-backed context " * 120,
                "metadata": {},
            }
        ],
        "citation_annotations": [
            {
                "citation_id": "citation-1",
                "chunk_id": "chunk-1",
                "source_kind": "local_x_db",
                "source_id": "tweet-1",
                "source_url": "https://x.com/example/status/1",
                "field_path": "context_chunks[0]",
                "evidence_status": "fact",
            }
        ],
    }
