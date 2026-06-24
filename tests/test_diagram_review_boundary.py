from __future__ import annotations

from pathlib import Path

from research_x.control_artifacts import (
    control_artifact_review_status,
    render_control_artifact_html,
    validate_control_artifact_payload,
)

MANIFEST = Path(".codex/skill_manifest.lock")


def _diagram_payload() -> dict[str, object]:
    return {
        "view_id": "diagram-boundary-unit",
        "view_kind": "diagram_review",
        "title": "Diagram Boundary Review",
        "generated_at": "2026-06-24T00:00:00+00:00",
        "owner_plane": "structure_review",
        "source_artifacts": [
            {
                "artifact_id": "pdg",
                "artifact_path": "docs/pdg/control-artifact-structure-view.pdg",
                "artifact_kind": "pdg_source",
                "not_evidence": True,
                "answer_support_allowed": False,
                "evidence_role": "control",
                "evidence_status": "not_evidence",
            }
        ],
        "sections": [{"heading": "Diagram", "body": "Review-only structure aid."}],
        "gates": [{"gate_id": "not_evidence", "label": "Diagram cannot support answers."}],
        "diagram_kind": "workflow",
        "source_of_structure": "pdg",
        "consistency_refs": ["docs/pdg/control-artifact-structure-view.pdg"],
        "not_evidence": True,
        "answer_support_allowed": False,
    }


def test_diagram_review_artifact_is_review_only_and_renderable() -> None:
    payload = _diagram_payload()

    assert validate_control_artifact_payload(payload) == []
    assert control_artifact_review_status(payload) == "ready"

    html = render_control_artifact_html(payload)
    assert "Not evidence / Review artifact only" in html
    assert "Diagram Boundary Review" in html


def test_diagram_with_answer_support_is_rejected() -> None:
    payload = _diagram_payload()
    payload["answer_support_allowed"] = True

    assert control_artifact_review_status(payload) == "rejected"


def test_workflow_diagram_without_consistency_refs_needs_review() -> None:
    payload = _diagram_payload()
    payload["consistency_refs"] = []

    assert validate_control_artifact_payload(payload) == []
    assert control_artifact_review_status(payload) == "needs_review"


def test_archify_is_not_enabled_as_skill_plugin_hook_or_mcp() -> None:
    text = MANIFEST.read_text(encoding="utf-8").casefold()

    assert "archify" not in text
