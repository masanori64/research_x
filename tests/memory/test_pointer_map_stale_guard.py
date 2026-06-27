from __future__ import annotations

import hashlib
import importlib.util
import json
from collections.abc import Callable
from pathlib import Path

from research_x.memory.context import CitationAnnotation
from research_x.memory.context_budget import verify_pointer_map
from research_x.memory.evidence_invariants import citation_block_reasons


def test_pointer_map_verifies_existing_control_pointer(tmp_path: Path) -> None:
    artifact = tmp_path / "plan.md"
    text = "control plan only\nnot evidence\n"
    artifact.write_text(text, encoding="utf-8")
    artifact_bytes = artifact.read_bytes()
    artifact_text = artifact_bytes.decode("utf-8").replace("\r\n", "\n").replace("\r", "\n")
    pointer_map = tmp_path / "pointer-map.json"
    pointer_map.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "entries": [
                    {
                        "pointer_id": "plan",
                        "artifact_path": "plan.md",
                        "artifact_kind": "implementation_plan",
                        "owner_plane": "decision_input",
                        "restore_hint": "Read for control-plane context only; not evidence.",
                        "sha256": hashlib.sha256(artifact_bytes).hexdigest(),
                        "char_count": len(artifact_text),
                        "byte_count": len(artifact_bytes),
                        "not_evidence": True,
                    }
                ],
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    report = verify_pointer_map(pointer_map, base_dir=tmp_path)

    assert report.status == "passed"
    assert report.entry_count == 1
    assert report.invalid_entry_count == 0
    assert report.usable_count == 1
    assert report.failed_count == 0
    assert report.results[0].status == "usable_pointer"


def test_pointer_map_resolves_relative_paths_from_map_directory(
    tmp_path: Path,
) -> None:
    pointer_map = _write_control_pointer_map(tmp_path / "nested")

    report = verify_pointer_map(pointer_map)

    assert report.status == "passed"
    assert report.results[0].artifact_path == str(pointer_map.parent / "plan.md")


def test_pointer_map_fails_non_dict_entries_and_reports_counts(
    tmp_path: Path,
) -> None:
    pointer_map = _write_control_pointer_map(tmp_path)
    payload = json.loads(pointer_map.read_text(encoding="utf-8"))
    payload["entries"].extend(["broken-entry", None])
    pointer_map.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    report = verify_pointer_map(pointer_map)

    assert report.status == "failed"
    assert report.entry_count == 3
    assert report.invalid_entry_count == 2
    assert report.usable_count == 1
    assert report.failed_count == 2
    assert {result.status for result in report.results} == {
        "usable_pointer",
        "invalid_pointer_map_entry",
    }


def test_audit_context_pointers_writes_json_output(
    tmp_path: Path,
    capsys: object,
) -> None:
    pointer_map = _write_control_pointer_map(tmp_path)
    output_path = tmp_path / "audit" / "pointer-report.json"
    audit_context_pointers_main = _audit_context_pointers_main()

    exit_code = audit_context_pointers_main(
        [
            "--pointer-map",
            str(pointer_map),
            "--json",
            "--output",
            str(output_path),
        ]
    )

    captured = capsys.readouterr()
    report = json.loads(output_path.read_text(encoding="utf-8"))
    assert exit_code == 0
    assert captured.out == ""
    assert report["status"] == "passed"
    assert report["entry_count"] == 1
    assert report["usable_count"] == 1


def test_pointer_map_detects_stale_hash_size_and_not_evidence_violation(
    tmp_path: Path,
) -> None:
    artifact = tmp_path / "plan.md"
    artifact.write_text("new content\n", encoding="utf-8")
    pointer_map = tmp_path / "pointer-map.json"
    pointer_map.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "entries": [
                    {
                        "pointer_id": "stale-plan",
                        "artifact_path": "plan.md",
                        "artifact_kind": "implementation_plan",
                        "owner_plane": "decision_input",
                        "restore_hint": "Read for control-plane context only; not evidence.",
                        "sha256": hashlib.sha256(b"older content\n").hexdigest(),
                        "char_count": len("older content\n"),
                        "byte_count": len(b"older content\n"),
                        "not_evidence": False,
                    }
                ],
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    report = verify_pointer_map(pointer_map, base_dir=tmp_path)
    result = report.results[0]

    assert report.status == "failed"
    assert result.status == "not_evidence_violation"
    assert "not_evidence_violation" in result.issues
    assert "stale_hash" in result.issues
    assert "stale_char_count" in result.issues
    assert "stale_byte_count" in result.issues


def test_missing_external_pointer_map_is_skipped_not_passed(tmp_path: Path) -> None:
    report = verify_pointer_map(tmp_path / "missing-pointer-map.json")

    assert report.status == "skipped_external_pointer_map_absent"
    assert report.skipped_reason == "pointer_map_absent"
    assert report.results == ()


def test_preview_restore_hint_metadata_cannot_be_citation_ready() -> None:
    citation = CitationAnnotation(
        citation_id="citation-preview",
        answer_id="answer-preview",
        chunk_id="chunk-preview",
        source_kind="local_x_db",
        source_id="tweet-1",
        source_url="https://x.com/example/status/1",
        title="preview",
        field_path="context_chunks[0]",
        support_type="supports_answer",
        evidence_status="fact",
        confidence=1.0,
        created_at="2026-06-27T00:00:00Z",
        metadata={
            "not_evidence": True,
            "answer_support_allowed": False,
            "preview_kind": "context_offload_preview",
            "restore_hint_status": "requires_pointer_verification",
            "citation_policy": "not_citation_restore_pointer_and_source_chunk_first",
        },
    )

    reasons = citation_block_reasons(citation)

    assert "not_evidence" in reasons


def _audit_context_pointers_main() -> Callable[[list[str] | None], int]:
    script = Path("tools/audit_context_pointers.py")
    spec = importlib.util.spec_from_file_location("audit_context_pointers", script)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.main


def _write_control_pointer_map(directory: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    artifact = directory / "plan.md"
    text = "control plan only\nnot evidence\n"
    artifact.write_text(text, encoding="utf-8")
    artifact_bytes = artifact.read_bytes()
    artifact_text = artifact_bytes.decode("utf-8").replace("\r\n", "\n").replace("\r", "\n")
    pointer_map = directory / "pointer-map.json"
    pointer_map.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "entries": [
                    {
                        "pointer_id": "plan",
                        "artifact_path": "plan.md",
                        "artifact_kind": "implementation_plan",
                        "owner_plane": "decision_input",
                        "restore_hint": "Read for control-plane context only; not evidence.",
                        "sha256": hashlib.sha256(artifact_bytes).hexdigest(),
                        "char_count": len(artifact_text),
                        "byte_count": len(artifact_bytes),
                        "not_evidence": True,
                    }
                ],
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return pointer_map
