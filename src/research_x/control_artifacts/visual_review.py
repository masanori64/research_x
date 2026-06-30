from __future__ import annotations

from pathlib import Path
from typing import Any

VISUAL_REVIEW_ARTIFACT_KINDS = {
    "slidev_deck",
    "slidev_rendered_view",
    "playwright_visual_snapshot",
    "ppt_master_deck",
}
VISUAL_REVIEW_REQUIRED_GATES = (
    ("blank_render_check", "Rendered output is not blank or empty."),
    ("missing_asset_check", "Referenced images, fonts, diagrams, and media are present."),
    ("overlap_check", "Text, controls, diagrams, and media do not overlap."),
    ("readability_check", "Text remains readable at target desktop and mobile sizes."),
    ("frame_check", "Primary content is fully inside the expected viewport or slide frame."),
    ("non_evidence_check", "Visual artifact is review-only and cannot support answers."),
)

VISUAL_REVIEW_GATE_STATUSES = {"pass", "fail", "needs_review"}

try:
    from PIL import Image, ImageStat
except ImportError:  # pragma: no cover - optional local image inspection.
    Image = None
    ImageStat = None


def build_visual_review_payload(
    *,
    artifact_id: str,
    artifact_path: str,
    artifact_kind: str,
    title: str = "Visual Review Checklist",
    generated_at: str = "review_pre_execution",
    owner_plane: str = "research_x_tool",
    target_surfaces: tuple[str, ...] = ("desktop", "mobile", "export"),
) -> dict[str, Any]:
    return {
        "view_id": f"visual-review-{artifact_id}",
        "view_kind": "visual_review",
        "title": title,
        "generated_at": generated_at,
        "owner_plane": owner_plane,
        "source_artifacts": [
            {
                "artifact_id": artifact_id,
                "artifact_path": artifact_path,
                "artifact_kind": artifact_kind,
                "not_evidence": True,
                "answer_support_allowed": False,
                "evidence_role": "control",
                "evidence_status": "not_evidence",
            }
        ],
        "sections": [
            {
                "heading": "Target Surfaces",
                "items": list(target_surfaces),
            },
            {
                "heading": "Visual Checks",
                "items": [label for _gate_id, label in VISUAL_REVIEW_REQUIRED_GATES],
            },
            {
                "heading": "Boundary",
                "body": (
                    "Generated slides, screenshots, rendered decks, and visual snapshots "
                    "are review artifacts only."
                ),
            },
        ],
        "gates": [
            {"gate_id": gate_id, "label": label, "status": "active"}
            for gate_id, label in VISUAL_REVIEW_REQUIRED_GATES
        ],
        "not_evidence": True,
        "answer_support_allowed": False,
    }


def validate_visual_review_payload(payload: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    view_id = str(payload.get("view_id") or "<unknown>")
    if payload.get("view_kind") != "visual_review":
        errors.append(f"{view_id}: view_kind must be visual_review")
    source_artifacts = payload.get("source_artifacts")
    if isinstance(source_artifacts, list) and source_artifacts:
        artifact = source_artifacts[0]
        if isinstance(artifact, dict):
            artifact_kind = str(artifact.get("artifact_kind") or "")
            if artifact_kind not in VISUAL_REVIEW_ARTIFACT_KINDS:
                errors.append(f"{view_id}: unsupported visual artifact kind {artifact_kind!r}")
            artifact_path = str(artifact.get("artifact_path") or "")
            if _is_remote_path(artifact_path):
                errors.append(f"{view_id}: remote artifact paths are not allowed")
            if artifact.get("not_evidence") is not True:
                errors.append(f"{view_id}: source artifact not_evidence must be true")
            if artifact.get("answer_support_allowed") is not False:
                errors.append(
                    f"{view_id}: source artifact answer_support_allowed must be false"
                )
    expected_gate_ids = {gate_id for gate_id, _label in VISUAL_REVIEW_REQUIRED_GATES}
    gates = payload.get("gates")
    evaluation = payload.get("evaluation")
    allowed_gate_statuses = (
        VISUAL_REVIEW_GATE_STATUSES
        if evaluation is not None
        else {*VISUAL_REVIEW_GATE_STATUSES, "active"}
    )
    if isinstance(gates, list):
        gate_ids = {str(gate.get("gate_id") or "") for gate in gates if isinstance(gate, dict)}
        if gate_ids != expected_gate_ids:
            errors.append(f"{view_id}: visual review gates do not match required gate set")
        for gate in gates:
            if not isinstance(gate, dict):
                continue
            status = str(gate.get("status") or "")
            if status not in allowed_gate_statuses:
                errors.append(f"{view_id}: invalid visual review gate status {status!r}")
    if evaluation is None:
        errors.append(f"{view_id}: visual review evaluation is required for ready status")
        return errors
    if not isinstance(evaluation, dict):
        errors.append(f"{view_id}: visual review evaluation must be an object")
        return errors
    if evaluation.get("not_evidence") is not True:
        errors.append(f"{view_id}: evaluation.not_evidence must be true")
    if evaluation.get("answer_support_allowed") is not False:
        errors.append(f"{view_id}: evaluation.answer_support_allowed must be false")
    status = str(evaluation.get("status") or "")
    if status not in VISUAL_REVIEW_GATE_STATUSES:
        errors.append(f"{view_id}: invalid visual review evaluation status {status!r}")
    snapshot_path = evaluation.get("snapshot_path")
    if isinstance(snapshot_path, str) and _is_remote_path(snapshot_path):
        errors.append(f"{view_id}: remote snapshot paths are not allowed")
    checks = evaluation.get("checks")
    if not isinstance(checks, list) or not checks:
        errors.append(f"{view_id}: visual review evaluation checks are required")
        return errors
    check_ids = {
        str(check.get("gate_id") or "") for check in checks if isinstance(check, dict)
    }
    if check_ids != expected_gate_ids:
        errors.append(f"{view_id}: visual review checks do not match required gate set")
    for check in checks:
        if not isinstance(check, dict):
            errors.append(f"{view_id}: visual review check must be an object")
            continue
        check_status = str(check.get("status") or "")
        if check_status not in VISUAL_REVIEW_GATE_STATUSES:
            errors.append(f"{view_id}: invalid visual review check status {check_status!r}")
        if not isinstance(check.get("issues", []), list):
            errors.append(f"{view_id}: visual review check issues must be a list")
    return errors


def evaluate_visual_review_snapshot(
    *,
    artifact_id: str,
    artifact_path: str,
    artifact_kind: str,
    snapshot_path: str | None,
    viewport_width: int,
    viewport_height: int,
    required_asset_paths: tuple[str, ...] = (),
    element_boxes: tuple[dict[str, Any], ...] = (),
    min_readable_font_px: float = 12.0,
    blank_stddev_threshold: float = 1.0,
    title: str = "Visual Review Evaluation",
    generated_at: str = "local_visual_review",
) -> dict[str, Any]:
    payload = build_visual_review_payload(
        artifact_id=artifact_id,
        artifact_path=artifact_path,
        artifact_kind=artifact_kind,
        title=title,
        generated_at=generated_at,
    )
    checks = [
        _blank_render_check(
            snapshot_path=snapshot_path,
            blank_stddev_threshold=blank_stddev_threshold,
        ),
        _missing_asset_check(required_asset_paths),
        _overlap_check(element_boxes),
        _readability_check(
            element_boxes=element_boxes,
            min_readable_font_px=min_readable_font_px,
        ),
        _frame_check(
            snapshot_path=snapshot_path,
            viewport_width=viewport_width,
            viewport_height=viewport_height,
            element_boxes=element_boxes,
        ),
        _non_evidence_check(),
    ]
    gate_status = {check["gate_id"]: check["status"] for check in checks}
    payload["gates"] = [
        {**gate, "status": gate_status.get(str(gate["gate_id"]), "needs_review")}
        for gate in payload["gates"]
    ]
    payload["evaluation"] = {
        "status": _overall_status(checks),
        "checks": checks,
        "snapshot_path": snapshot_path,
        "viewport": {"width": viewport_width, "height": viewport_height},
        "required_asset_count": len(required_asset_paths),
        "element_box_count": len(element_boxes),
        "not_evidence": True,
        "answer_support_allowed": False,
    }
    payload["sections"].append(
        {
            "heading": "Evaluation Result",
            "items": [
                f"{check['gate_id']}: {check['status']}"
                for check in checks
            ],
        }
    )
    return payload


def _blank_render_check(
    *,
    snapshot_path: str | None,
    blank_stddev_threshold: float,
) -> dict[str, Any]:
    if not snapshot_path:
        return _check("blank_render_check", "needs_review", ["snapshot_path_missing"])
    if _is_remote_path(snapshot_path):
        return _check("blank_render_check", "fail", ["remote_snapshot_path"])
    path = Path(snapshot_path)
    if not path.exists():
        return _check("blank_render_check", "fail", ["snapshot_missing"])
    if Image is None or ImageStat is None:
        return _check("blank_render_check", "needs_review", ["pillow_unavailable"])
    try:
        with Image.open(path) as image:
            converted = image.convert("RGB")
            stat = ImageStat.Stat(converted)
            max_stddev = max(float(value) for value in stat.stddev)
            dimensions = {"width": int(image.width), "height": int(image.height)}
    except OSError as exc:
        return _check("blank_render_check", "fail", [f"snapshot_unreadable:{exc}"])
    if dimensions["width"] <= 0 or dimensions["height"] <= 0:
        return _check("blank_render_check", "fail", ["snapshot_empty_dimensions"])
    if max_stddev < blank_stddev_threshold:
        return _check(
            "blank_render_check",
            "fail",
            ["snapshot_near_blank"],
            {"dimensions": dimensions, "max_stddev": max_stddev},
        )
    return _check(
        "blank_render_check",
        "pass",
        [],
        {"dimensions": dimensions, "max_stddev": max_stddev},
    )


def _missing_asset_check(required_asset_paths: tuple[str, ...]) -> dict[str, Any]:
    missing = []
    remote = []
    for raw_path in required_asset_paths:
        if _is_remote_path(raw_path):
            remote.append(raw_path)
        elif not Path(raw_path).exists():
            missing.append(raw_path)
    issues = [*(f"missing:{path}" for path in missing), *(f"remote:{path}" for path in remote)]
    return _check("missing_asset_check", "fail" if issues else "pass", issues)


def _overlap_check(element_boxes: tuple[dict[str, Any], ...]) -> dict[str, Any]:
    boxes, errors = _normalized_boxes(element_boxes)
    overlaps = []
    for left_index, left in enumerate(boxes):
        for right in boxes[left_index + 1 :]:
            if left.get("allow_overlap") is True or right.get("allow_overlap") is True:
                continue
            if _boxes_overlap(left, right):
                overlaps.append(f"{left['box_id']}:{right['box_id']}")
    issues = [
        *(f"invalid_box:{error}" for error in errors),
        *(f"overlap:{item}" for item in overlaps),
    ]
    if issues:
        return _check("overlap_check", "fail", issues)
    if not boxes:
        return _check("overlap_check", "needs_review", ["no_element_boxes"])
    return _check("overlap_check", "pass", [])


def _readability_check(
    *,
    element_boxes: tuple[dict[str, Any], ...],
    min_readable_font_px: float,
) -> dict[str, Any]:
    boxes, errors = _normalized_boxes(element_boxes)
    text_boxes = [
        box
        for box in boxes
        if str(box.get("kind") or "").casefold() == "text" or str(box.get("text") or "")
    ]
    unreadable = [
        f"{box['box_id']}:{box.get('font_size_px')}"
        for box in text_boxes
        if float(box.get("font_size_px") or 0.0) < min_readable_font_px
    ]
    issues = [
        *(f"invalid_box:{error}" for error in errors),
        *(f"unreadable:{item}" for item in unreadable),
    ]
    if issues:
        return _check("readability_check", "fail", issues)
    if not text_boxes:
        return _check("readability_check", "needs_review", ["no_text_boxes"])
    return _check(
        "readability_check",
        "pass",
        [],
        {"min_readable_font_px": min_readable_font_px},
    )


def _frame_check(
    *,
    snapshot_path: str | None,
    viewport_width: int,
    viewport_height: int,
    element_boxes: tuple[dict[str, Any], ...],
) -> dict[str, Any]:
    issues = []
    if viewport_width <= 0 or viewport_height <= 0:
        issues.append("invalid_viewport")
    boxes, errors = _normalized_boxes(element_boxes)
    issues.extend(f"invalid_box:{error}" for error in errors)
    for box in boxes:
        if (
            box["x"] < 0
            or box["y"] < 0
            or box["x"] + box["width"] > viewport_width
            or box["y"] + box["height"] > viewport_height
        ):
            issues.append(f"out_of_frame:{box['box_id']}")
    dimensions = _snapshot_dimensions(snapshot_path)
    if dimensions and (
        dimensions["width"] != viewport_width or dimensions["height"] != viewport_height
    ):
        issues.append("snapshot_dimensions_mismatch")
    return _check(
        "frame_check",
        "fail" if issues else "pass",
        issues,
        {"snapshot_dimensions": dimensions},
    )


def _non_evidence_check() -> dict[str, Any]:
    return _check(
        "non_evidence_check",
        "pass",
        [],
        {"not_evidence": True, "answer_support_allowed": False},
    )


def _check(
    gate_id: str,
    status: str,
    issues: list[str],
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if status not in VISUAL_REVIEW_GATE_STATUSES:
        raise ValueError(f"invalid visual review gate status: {status}")
    return {
        "gate_id": gate_id,
        "status": status,
        "issues": issues,
        "details": details or {},
    }


def _overall_status(checks: list[dict[str, Any]]) -> str:
    statuses = {str(check["status"]) for check in checks}
    if "fail" in statuses:
        return "fail"
    if "needs_review" in statuses:
        return "needs_review"
    return "pass"


def _normalized_boxes(
    element_boxes: tuple[dict[str, Any], ...],
) -> tuple[list[dict[str, Any]], list[str]]:
    boxes: list[dict[str, Any]] = []
    errors: list[str] = []
    for index, raw_box in enumerate(element_boxes, start=1):
        try:
            box = {
                **raw_box,
                "box_id": str(raw_box.get("box_id") or raw_box.get("id") or index),
                "x": float(raw_box["x"]),
                "y": float(raw_box["y"]),
                "width": float(raw_box["width"]),
                "height": float(raw_box["height"]),
                "font_size_px": (
                    float(raw_box["font_size_px"])
                    if raw_box.get("font_size_px") is not None
                    else None
                ),
            }
        except (KeyError, TypeError, ValueError) as exc:
            errors.append(f"{index}:{exc}")
            continue
        if box["width"] <= 0 or box["height"] <= 0:
            errors.append(f"{box['box_id']}:non_positive_size")
            continue
        boxes.append(box)
    return boxes, errors


def _boxes_overlap(left: dict[str, Any], right: dict[str, Any]) -> bool:
    return not (
        left["x"] + left["width"] <= right["x"]
        or right["x"] + right["width"] <= left["x"]
        or left["y"] + left["height"] <= right["y"]
        or right["y"] + right["height"] <= left["y"]
    )


def _snapshot_dimensions(snapshot_path: str | None) -> dict[str, int] | None:
    if not snapshot_path or _is_remote_path(snapshot_path) or Image is None:
        return None
    path = Path(snapshot_path)
    if not path.exists():
        return None
    try:
        with Image.open(path) as image:
            return {"width": int(image.width), "height": int(image.height)}
    except OSError:
        return None


def _is_remote_path(path: str) -> bool:
    return path.casefold().startswith(("http://", "https://", "//"))
