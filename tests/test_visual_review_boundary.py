from __future__ import annotations

import pytest

from research_x.control_artifacts import (
    VISUAL_REVIEW_REQUIRED_GATES,
    build_visual_review_payload,
    render_control_artifact_html,
    validate_control_artifact_payload,
)
from research_x.control_artifacts.sanitize import validate_safe_review_html


@pytest.mark.parametrize(
    "artifact_kind",
    (
        "slidev_deck",
        "slidev_rendered_view",
        "playwright_visual_snapshot",
        "ppt_master_deck",
    ),
)
def test_visual_review_payload_is_renderable_review_only(artifact_kind: str) -> None:
    payload = build_visual_review_payload(
        artifact_id=f"fixture-{artifact_kind}",
        artifact_path=f"outputs/review/{artifact_kind}.html",
        artifact_kind=artifact_kind,
    )
    html = render_control_artifact_html(payload)

    assert validate_control_artifact_payload(payload) == []
    assert validate_safe_review_html(html) == []
    assert payload["view_kind"] == "visual_review"
    assert payload["not_evidence"] is True
    assert payload["answer_support_allowed"] is False
    assert payload["source_artifacts"][0]["not_evidence"] is True
    assert payload["source_artifacts"][0]["answer_support_allowed"] is False
    assert {gate["gate_id"] for gate in payload["gates"]} == {
        gate_id for gate_id, _label in VISUAL_REVIEW_REQUIRED_GATES
    }
    assert "Not evidence / Review artifact only" in html


def test_visual_review_payload_rejects_remote_artifact_path_and_answer_support() -> None:
    payload = build_visual_review_payload(
        artifact_id="fixture-remote",
        artifact_path="https://example.com/deck.html",
        artifact_kind="slidev_rendered_view",
    )
    payload["answer_support_allowed"] = True

    errors = validate_control_artifact_payload(payload)

    assert "visual-review-fixture-remote: answer_support_allowed must be false" in errors
    assert any("remote artifact paths" in error for error in errors)
