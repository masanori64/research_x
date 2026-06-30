from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

CONTROL_ARTIFACT_KINDS = {
    "chatgpt_consultation",
    "codex_review_capture",
    "compressed_summary",
    "context_offload_preview",
    "context_preview",
    "d2_source",
    "diagram_review",
    "generated_diagram",
    "generated_spec",
    "gpt_pro_plan",
    "html_review",
    "html_structure_view",
    "playwright_visual_snapshot",
    "pointer_map",
    "ppt_master_deck",
    "presentation_svg",
    "query_plan_visualization",
    "reverse_spec",
    "review_artifact",
    "search_plan_graph",
    "slidev_deck",
    "slidev_rendered_view",
    "svg_review",
    "wbs_json",
    "wbs_rendered_view",
    "x_url",
}
CONTROL_ARTIFACT_KIND_MARKERS = (
    "chatgpt",
    "codex_review",
    "compressed_summary",
    "control_artifact",
    "diagram",
    "gpt",
    "html_review",
    "html_structure",
    "pointer_map",
    "preview",
    "query_plan",
    "rendered_view",
    "review_artifact",
    "search_plan",
    "structure_view",
    "summary",
    "wbs",
)
EVIDENCE_CLAIM_FIELDS = {
    "answer_support",
    "citation",
    "citations",
    "context_chunk",
    "evidence",
    "source_bundle",
}
EVIDENCE_ROLES = {
    "answer_support",
    "citation",
    "citation_ready",
    "evidence",
    "source_bundle",
    "source_restored",
}
REVIEW_VIEW_KINDS = {
    "diagram_review",
    "guard_report",
    "lifecycle_report",
    "query_plan_review",
    "structure_view",
}
DIAGRAM_KINDS_NEEDING_REFS = {"architecture", "workflow"}


@dataclass(frozen=True)
class SourceArtifact:
    artifact_id: str
    artifact_path: str
    artifact_kind: str
    not_evidence: bool
    answer_support_allowed: bool
    evidence_role: str = "control"
    evidence_status: str = "not_evidence"


@dataclass(frozen=True)
class ControlArtifactSection:
    heading: str
    body: str = ""
    items: tuple[str, ...] = ()


@dataclass(frozen=True)
class ControlArtifactGate:
    gate_id: str
    label: str
    status: str = "active"


@dataclass(frozen=True)
class ControlArtifactView:
    view_id: str
    view_kind: str
    title: str
    generated_at: str
    owner_plane: str
    source_artifacts: tuple[SourceArtifact, ...]
    sections: tuple[ControlArtifactSection, ...]
    gates: tuple[ControlArtifactGate, ...]
    not_evidence: bool
    answer_support_allowed: bool
    diagram_kind: str = ""
    source_of_structure: str = ""
    consistency_refs: tuple[str, ...] = ()


def validate_control_artifact_payload(payload: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    if not isinstance(payload, Mapping):
        return ["payload must be an object"]
    required = {
        "view_id",
        "view_kind",
        "title",
        "generated_at",
        "owner_plane",
        "source_artifacts",
        "sections",
        "gates",
        "not_evidence",
        "answer_support_allowed",
    }
    missing = sorted(required - set(payload))
    if missing:
        return [f"missing fields: {', '.join(missing)}"]
    view_id = str(payload.get("view_id", "<unknown>"))
    if payload["view_kind"] not in REVIEW_VIEW_KINDS:
        errors.append(f"{view_id}: invalid view_kind {payload['view_kind']!r}")
    if payload["not_evidence"] is not True:
        errors.append(f"{view_id}: not_evidence must be true")
    if payload["answer_support_allowed"] is not False:
        errors.append(f"{view_id}: answer_support_allowed must be false")
    for field in sorted(EVIDENCE_CLAIM_FIELDS & set(payload)):
        errors.append(f"{view_id}: control artifact must not carry {field!r}")
    errors.extend(_validate_source_artifacts(view_id, payload["source_artifacts"]))
    errors.extend(_validate_sections(view_id, payload["sections"]))
    errors.extend(_validate_gates(view_id, payload["gates"]))
    if payload["view_kind"] == "diagram_review":
        errors.extend(_validate_diagram_fields(view_id, payload))
    return errors


def load_control_artifact_view(payload: Mapping[str, Any]) -> ControlArtifactView:
    errors = validate_control_artifact_payload(payload)
    if errors:
        raise ValueError("; ".join(errors))
    return ControlArtifactView(
        view_id=str(payload["view_id"]),
        view_kind=str(payload["view_kind"]),
        title=str(payload["title"]),
        generated_at=str(payload["generated_at"]),
        owner_plane=str(payload["owner_plane"]),
        source_artifacts=tuple(_source_artifact(item) for item in payload["source_artifacts"]),
        sections=tuple(_section(item) for item in payload["sections"]),
        gates=tuple(_gate(item) for item in payload["gates"]),
        not_evidence=bool(payload["not_evidence"]),
        answer_support_allowed=bool(payload["answer_support_allowed"]),
        diagram_kind=str(payload.get("diagram_kind", "")),
        source_of_structure=str(payload.get("source_of_structure", "")),
        consistency_refs=tuple(str(item) for item in payload.get("consistency_refs", ())),
    )


def control_artifact_review_status(payload: Mapping[str, Any]) -> str:
    if validate_control_artifact_payload(payload):
        return "rejected"
    if (
        payload.get("view_kind") == "diagram_review"
        and payload.get("diagram_kind") in DIAGRAM_KINDS_NEEDING_REFS
        and not payload.get("consistency_refs")
    ):
        return "needs_review"
    return "ready"


def _validate_source_artifacts(view_id: str, value: object) -> list[str]:
    if not isinstance(value, list) or not value:
        return [f"{view_id}: source_artifacts must be a non-empty list"]
    errors: list[str] = []
    required = {"artifact_id", "artifact_path", "artifact_kind", "not_evidence"}
    for index, item in enumerate(value, start=1):
        if not isinstance(item, Mapping):
            errors.append(f"{view_id}: source_artifacts[{index}] must be an object")
            continue
        missing = sorted(required - set(item))
        if missing:
            errors.append(
                f"{view_id}: source_artifacts[{index}] missing fields: {', '.join(missing)}"
            )
            continue
        prefix = f"{view_id}: source_artifacts[{index}]"
        if item["not_evidence"] is not True:
            errors.append(f"{prefix}: not_evidence must be true")
        if item.get("answer_support_allowed", False) is not False:
            errors.append(f"{prefix}: answer_support_allowed must be false")
        artifact_kind = str(item["artifact_kind"])
        evidence_role = str(item.get("evidence_role", "control"))
        evidence_status = str(item.get("evidence_status", "not_evidence"))
        if _is_control_artifact_kind(artifact_kind) and (
            evidence_role in EVIDENCE_ROLES or evidence_status in EVIDENCE_ROLES
        ):
            errors.append(
                f"{prefix}: {artifact_kind} cannot be evidence, citation, or answer support"
            )
        path = str(item["artifact_path"])
        if path.startswith(("http://", "https://", "//")):
            errors.append(f"{prefix}: remote artifact paths are not renderable control inputs")
    return errors


def _is_control_artifact_kind(artifact_kind: str) -> bool:
    normalized = artifact_kind.strip().casefold().replace("-", "_").replace(" ", "_")
    return artifact_kind in CONTROL_ARTIFACT_KINDS or any(
        marker in normalized for marker in CONTROL_ARTIFACT_KIND_MARKERS
    )


def _validate_sections(view_id: str, value: object) -> list[str]:
    if not isinstance(value, list) or not value:
        return [f"{view_id}: sections must be a non-empty list"]
    errors: list[str] = []
    for index, item in enumerate(value, start=1):
        if not isinstance(item, Mapping):
            errors.append(f"{view_id}: sections[{index}] must be an object")
            continue
        if not str(item.get("heading", "")).strip():
            errors.append(f"{view_id}: sections[{index}].heading is required")
        if "items" in item and not isinstance(item["items"], list):
            errors.append(f"{view_id}: sections[{index}].items must be a list")
    return errors


def _validate_gates(view_id: str, value: object) -> list[str]:
    if not isinstance(value, list) or not value:
        return [f"{view_id}: gates must be a non-empty list"]
    errors: list[str] = []
    for index, item in enumerate(value, start=1):
        if not isinstance(item, Mapping):
            errors.append(f"{view_id}: gates[{index}] must be an object")
            continue
        if not str(item.get("gate_id", "")).strip():
            errors.append(f"{view_id}: gates[{index}].gate_id is required")
        if not str(item.get("label", "")).strip():
            errors.append(f"{view_id}: gates[{index}].label is required")
    return errors


def _validate_diagram_fields(view_id: str, payload: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    if not str(payload.get("diagram_kind", "")).strip():
        errors.append(f"{view_id}: diagram_kind is required for diagram_review")
    if not str(payload.get("source_of_structure", "")).strip():
        errors.append(f"{view_id}: source_of_structure is required for diagram_review")
    refs = payload.get("consistency_refs", [])
    if refs is not None and not isinstance(refs, list):
        errors.append(f"{view_id}: consistency_refs must be a list")
    return errors


def _source_artifact(item: Mapping[str, Any]) -> SourceArtifact:
    return SourceArtifact(
        artifact_id=str(item["artifact_id"]),
        artifact_path=str(item["artifact_path"]),
        artifact_kind=str(item["artifact_kind"]),
        not_evidence=bool(item["not_evidence"]),
        answer_support_allowed=bool(item.get("answer_support_allowed", False)),
        evidence_role=str(item.get("evidence_role", "control")),
        evidence_status=str(item.get("evidence_status", "not_evidence")),
    )


def _section(item: Mapping[str, Any]) -> ControlArtifactSection:
    return ControlArtifactSection(
        heading=str(item["heading"]),
        body=str(item.get("body", "")),
        items=tuple(str(value) for value in item.get("items", ())),
    )


def _gate(item: Mapping[str, Any]) -> ControlArtifactGate:
    return ControlArtifactGate(
        gate_id=str(item["gate_id"]),
        label=str(item["label"]),
        status=str(item.get("status", "active")),
    )
