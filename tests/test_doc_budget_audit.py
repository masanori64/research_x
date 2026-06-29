from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

from research_x.control_artifacts.doc_budget import (
    ARTIFACT_KIND,
    DOC_ROLE_CONTRACTS,
    SCHEMA_VERSION,
    WBS_PATH,
    build_doc_budget_audit,
)

SCRIPT_PATH = Path("tools/doc_budget_audit.py")


def test_doc_budget_audit_current_repo_is_non_evidence_control_report() -> None:
    payload = build_doc_budget_audit()

    assert payload["artifact_kind"] == ARTIFACT_KIND
    assert payload["schema_version"] == SCHEMA_VERSION
    assert payload["not_evidence"] is True
    assert payload["not_citation"] is True
    assert payload["not_answer_support"] is True
    assert {item["path"] for item in payload["documents"]} == {
        path.as_posix() for path in DOC_ROLE_CONTRACTS
    }
    assert payload["summary"] == {
        "document_banned_fragment_count": 0,
        "document_count": len(DOC_ROLE_CONTRACTS),
        "document_forbidden_section_count": 0,
        "document_hard_ceiling_violation_count": 0,
        "document_missing_required_section_count": 0,
        "document_missing_required_term_count": 0,
        "document_ordered_fragment_violation_count": 0,
        "document_target_review_marker_missing_count": 0,
        "wbs_semantic_violation_count": 0,
    }
    assert payload["wbs"]["not_evidence_violation_count"] == 0
    assert payload["wbs"]["answer_support_allowed_violation_count"] == 0
    assert payload["wbs"]["semantic_violation_count"] == 0


def test_doc_budget_audit_cli_emits_json(capsys) -> None:
    module = _load_tool()

    exit_code = module.main(["--project-root", ".", "--json"])

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert exit_code == 0
    assert payload["artifact_kind"] == ARTIFACT_KIND
    assert payload["schema_version"] == SCHEMA_VERSION


def test_doc_budget_audit_detects_markdown_and_wbs_boundary_violations(
    tmp_path: Path,
) -> None:
    _copy_current_audit_inputs(tmp_path)
    project_path = tmp_path / "PROJECT.md"
    project_text = project_path.read_text(encoding="utf-8")
    overflow = "\n".join(f"overflow line {index}" for index in range(140))
    project_path.write_text(project_text + "\n" + overflow + "\n", encoding="utf-8")
    wbs_path = tmp_path / WBS_PATH
    payload = json.loads(wbs_path.read_text(encoding="utf-8"))
    first_leaf = payload["projects"][0]["tasks"][0]["children"][0]["_research_x"]
    first_leaf["evidence_status"] = "citation_ready"
    first_leaf["answer_support_allowed"] = True
    wbs_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    audit = build_doc_budget_audit(tmp_path)

    assert audit["summary"]["document_hard_ceiling_violation_count"] >= 1
    assert audit["summary"]["wbs_semantic_violation_count"] >= 2
    assert audit["wbs"]["not_evidence_violation_count"] == 1
    assert audit["wbs"]["answer_support_allowed_violation_count"] == 1


def _load_tool():
    spec = importlib.util.spec_from_file_location("doc_budget_audit", SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _copy_current_audit_inputs(root: Path) -> None:
    for contract in DOC_ROLE_CONTRACTS.values():
        source = contract.path
        destination = root / contract.path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
    destination = root / WBS_PATH
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(WBS_PATH.read_text(encoding="utf-8"), encoding="utf-8")
