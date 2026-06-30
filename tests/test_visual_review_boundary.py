from __future__ import annotations

import pytest
from PIL import Image, ImageDraw

from research_x.control_artifacts import (
    VISUAL_REVIEW_REQUIRED_GATES,
    build_visual_review_payload,
    control_artifact_review_status,
    evaluate_visual_review_snapshot,
    render_control_artifact_html,
    validate_control_artifact_payload,
    validate_visual_review_payload,
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
    assert control_artifact_review_status(payload) == "rejected"


def test_visual_review_checklist_payload_stays_needs_review() -> None:
    payload = build_visual_review_payload(
        artifact_id="checklist",
        artifact_path="outputs/review/checklist.html",
        artifact_kind="slidev_deck",
    )

    assert validate_control_artifact_payload(payload) == []
    assert any(
        "visual review evaluation is required for ready status" in error
        for error in validate_visual_review_payload(payload)
    )
    assert control_artifact_review_status(payload) == "needs_review"


def test_visual_review_evaluator_passes_clean_local_snapshot(tmp_path) -> None:
    artifact = tmp_path / "deck.html"
    asset = tmp_path / "hero.png"
    snapshot = tmp_path / "snapshot.png"
    artifact.write_text("<main>deck</main>", encoding="utf-8")
    _write_snapshot(snapshot, blank=False)
    asset.write_bytes(b"asset")

    payload = evaluate_visual_review_snapshot(
        artifact_id="clean",
        artifact_path=str(artifact),
        artifact_kind="slidev_rendered_view",
        snapshot_path=str(snapshot),
        viewport_width=320,
        viewport_height=180,
        required_asset_paths=(str(asset),),
        element_boxes=(
            {
                "box_id": "title",
                "kind": "text",
                "x": 10,
                "y": 10,
                "width": 120,
                "height": 30,
                "font_size_px": 18,
            },
            {
                "box_id": "image",
                "kind": "image",
                "x": 150,
                "y": 30,
                "width": 120,
                "height": 90,
            },
        ),
    )

    assert validate_control_artifact_payload(payload) == []
    assert validate_visual_review_payload(payload) == []
    assert payload["evaluation"]["status"] == "pass"
    assert control_artifact_review_status(payload) == "ready"
    assert {gate["status"] for gate in payload["gates"]} == {"pass"}
    assert payload["evaluation"]["not_evidence"] is True
    assert payload["evaluation"]["answer_support_allowed"] is False


def test_visual_review_evaluator_fails_blank_snapshot(tmp_path) -> None:
    artifact = tmp_path / "deck.html"
    snapshot = tmp_path / "blank.png"
    artifact.write_text("<main>deck</main>", encoding="utf-8")
    _write_snapshot(snapshot, blank=True)

    payload = evaluate_visual_review_snapshot(
        artifact_id="blank",
        artifact_path=str(artifact),
        artifact_kind="playwright_visual_snapshot",
        snapshot_path=str(snapshot),
        viewport_width=320,
        viewport_height=180,
        element_boxes=(_text_box("title", x=10, y=10),),
    )

    assert payload["evaluation"]["status"] == "fail"
    assert control_artifact_review_status(payload) == "needs_review"
    blank_check = _check(payload, "blank_render_check")
    assert blank_check["status"] == "fail"
    assert "snapshot_near_blank" in blank_check["issues"]


def test_visual_review_evaluator_fails_missing_asset(tmp_path) -> None:
    artifact = tmp_path / "deck.html"
    snapshot = tmp_path / "snapshot.png"
    artifact.write_text("<main>deck</main>", encoding="utf-8")
    _write_snapshot(snapshot, blank=False)

    payload = evaluate_visual_review_snapshot(
        artifact_id="missing-asset",
        artifact_path=str(artifact),
        artifact_kind="slidev_deck",
        snapshot_path=str(snapshot),
        viewport_width=320,
        viewport_height=180,
        required_asset_paths=(
            str(tmp_path / "missing.png"),
            "HTTPS://example.com/remote.png",
        ),
        element_boxes=(_text_box("title", x=10, y=10),),
    )

    asset_check = _check(payload, "missing_asset_check")
    assert payload["evaluation"]["status"] == "fail"
    assert asset_check["status"] == "fail"
    assert any(issue.startswith("missing:") for issue in asset_check["issues"])
    assert any(issue.startswith("remote:") for issue in asset_check["issues"])


def test_visual_review_evaluator_fails_overlap_unreadable_and_frame(tmp_path) -> None:
    artifact = tmp_path / "deck.html"
    snapshot = tmp_path / "snapshot.png"
    artifact.write_text("<main>deck</main>", encoding="utf-8")
    _write_snapshot(snapshot, blank=False)

    payload = evaluate_visual_review_snapshot(
        artifact_id="geometry",
        artifact_path=str(artifact),
        artifact_kind="ppt_master_deck",
        snapshot_path=str(snapshot),
        viewport_width=320,
        viewport_height=180,
        element_boxes=(
            _text_box("title", x=10, y=10, font_size_px=9),
            _text_box("subtitle", x=20, y=20),
            _text_box("outside", x=280, y=150, width=80, height=40),
        ),
    )

    assert payload["evaluation"]["status"] == "fail"
    assert _check(payload, "overlap_check")["status"] == "fail"
    assert _check(payload, "readability_check")["status"] == "fail"
    assert _check(payload, "frame_check")["status"] == "fail"


def test_visual_review_validation_rejects_unsupported_kind_and_remote_snapshot(
    tmp_path,
) -> None:
    snapshot = tmp_path / "snapshot.png"
    _write_snapshot(snapshot, blank=False)
    payload = evaluate_visual_review_snapshot(
        artifact_id="unsupported",
        artifact_path="outputs/review/unsupported.html",
        artifact_kind="html_structure_view",
        snapshot_path=str(snapshot),
        viewport_width=320,
        viewport_height=180,
        element_boxes=(_text_box("title", x=10, y=10),),
    )
    payload["evaluation"]["snapshot_path"] = "https://example.com/snapshot.png"

    errors = validate_visual_review_payload(payload)

    assert any("unsupported visual artifact kind" in error for error in errors)
    assert any("remote snapshot paths are not allowed" in error for error in errors)
    assert control_artifact_review_status(payload) == "rejected"


def _write_snapshot(path, *, blank: bool) -> None:
    image = Image.new("RGB", (320, 180), "white")
    if not blank:
        draw = ImageDraw.Draw(image)
        draw.rectangle((10, 10, 140, 70), fill="black")
        draw.rectangle((170, 70, 300, 160), fill="steelblue")
    image.save(path)


def _text_box(
    box_id: str,
    *,
    x: int,
    y: int,
    width: int = 120,
    height: int = 30,
    font_size_px: int = 16,
) -> dict[str, object]:
    return {
        "box_id": box_id,
        "kind": "text",
        "x": x,
        "y": y,
        "width": width,
        "height": height,
        "font_size_px": font_size_px,
    }


def _check(payload: dict[str, object], gate_id: str) -> dict[str, object]:
    evaluation = payload["evaluation"]
    assert isinstance(evaluation, dict)
    checks = evaluation["checks"]
    assert isinstance(checks, list)
    return next(check for check in checks if check["gate_id"] == gate_id)
