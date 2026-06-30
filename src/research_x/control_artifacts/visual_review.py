from __future__ import annotations

from typing import Any

VISUAL_REVIEW_REQUIRED_GATES = (
    ("blank_render_check", "Rendered output is not blank or empty."),
    ("missing_asset_check", "Referenced images, fonts, diagrams, and media are present."),
    ("overlap_check", "Text, controls, diagrams, and media do not overlap."),
    ("readability_check", "Text remains readable at target desktop and mobile sizes."),
    ("frame_check", "Primary content is fully inside the expected viewport or slide frame."),
    ("non_evidence_check", "Visual artifact is review-only and cannot support answers."),
)


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
