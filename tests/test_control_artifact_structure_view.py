from __future__ import annotations

import json
from pathlib import Path

import pytest

from research_x.control_artifacts import (
    render_control_artifact_html,
    validate_control_artifact_payload,
)
from research_x.control_artifacts.sanitize import validate_safe_review_html

FIXTURE = Path("tests/fixtures/control_artifacts/structure_view.valid.json")


def _fixture() -> dict[str, object]:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_valid_structure_view_renders_deterministic_review_only_html() -> None:
    payload = _fixture()

    html = render_control_artifact_html(payload)

    assert html == render_control_artifact_html(payload)
    assert "Not evidence / Review artifact only" in html
    assert "control/project_state.json" in html
    assert validate_safe_review_html(html) == []
    assert "<script" not in html.casefold()
    assert "fetch(" not in html.casefold()
    assert "localstorage" not in html.casefold()


def test_control_artifact_rejects_answer_support() -> None:
    payload = _fixture()
    payload["answer_support_allowed"] = True

    errors = validate_control_artifact_payload(payload)

    assert "structure-view-unit: answer_support_allowed must be false" in errors
    with pytest.raises(ValueError, match="answer_support_allowed must be false"):
        render_control_artifact_html(payload)


def test_control_artifact_rejects_not_evidence_false() -> None:
    payload = _fixture()
    payload["not_evidence"] = False

    errors = validate_control_artifact_payload(payload)

    assert "structure-view-unit: not_evidence must be true" in errors


def test_control_artifact_rejects_wbs_or_pdg_as_citation_source() -> None:
    payload = _fixture()
    source = payload["source_artifacts"][0]
    assert isinstance(source, dict)
    source["evidence_role"] = "citation"

    errors = validate_control_artifact_payload(payload)

    assert any(
        "project_state_json cannot be evidence, citation, or answer support" in error
        for error in errors
    )


@pytest.mark.parametrize(
    "artifact_kind",
    (
        "diagram_review",
        "compressed_summary",
        "context_offload_preview",
        "html_structure_view",
        "wbs_rendered_view",
        "chatgpt_consultation",
        "gpt_pro_plan",
    ),
)
def test_control_artifact_rejects_non_evidence_artifact_kinds_as_citation_sources(
    artifact_kind: str,
) -> None:
    payload = _fixture()
    source = payload["source_artifacts"][0]
    assert isinstance(source, dict)
    source["artifact_kind"] = artifact_kind
    source["evidence_role"] = "citation"
    source["evidence_status"] = "citation_ready"

    errors = validate_control_artifact_payload(payload)

    assert any(
        f"{artifact_kind} cannot be evidence, citation, or answer support" in error
        for error in errors
    )


def test_control_artifact_rejects_source_answer_support() -> None:
    payload = _fixture()
    source = payload["source_artifacts"][0]
    assert isinstance(source, dict)
    source["answer_support_allowed"] = True

    errors = validate_control_artifact_payload(payload)

    assert (
        "structure-view-unit: source_artifacts[1]: "
        "answer_support_allowed must be false"
    ) in errors
    with pytest.raises(ValueError, match="answer_support_allowed must be false"):
        render_control_artifact_html(payload)


def test_control_artifact_rejects_top_level_citation_fields() -> None:
    payload = _fixture()
    payload["citation"] = "not allowed"

    errors = validate_control_artifact_payload(payload)

    assert "structure-view-unit: control artifact must not carry 'citation'" in errors
