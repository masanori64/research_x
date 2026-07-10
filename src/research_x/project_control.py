"""Load and validate the machine-readable research_x control plane."""

from __future__ import annotations

import ast
import hashlib
import json
import tomllib
from copy import deepcopy
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
AUTHORITY_MAP_PATH = Path("control/authority_map.toml")
PROJECT_STATE_PATH = Path("control/project_state.json")
CONTROL_PROFILE_PATH = Path(".codex-project/control-profile.json")

REQUIRED_CLASSIFICATIONS = {
    "canon",
    "current_state",
    "control",
    "evidence",
    "history",
    "generated",
}
REQUIRED_WORKSTREAMS = {
    "provider_quality",
    "skillmap",
    "specialized_embedding_spaces",
    "ocr_media_provider_lanes",
    "final_product_acceptance",
}
REQUIRED_GATES = {
    "research_x_external_fetch_beyond_scope",
    "research_x_working_note_promotion",
    "research_x_route_promotion",
    "research_x_persisted_schema_or_data_migration",
    "research_x_high_risk_answer_assertion",
}


def load_authority_map(project_root: Path | None = None) -> dict[str, Any]:
    """Load the authority map from *project_root*."""

    path = _root(project_root) / AUTHORITY_MAP_PATH
    with path.open("rb") as handle:
        return tomllib.load(handle)


def load_project_state(project_root: Path | None = None) -> dict[str, Any]:
    """Load the current project-state artifact from *project_root*."""

    path = _root(project_root) / PROJECT_STATE_PATH
    return json.loads(path.read_text(encoding="utf-8"))


def load_control_profile(project_root: Path | None = None) -> dict[str, Any]:
    """Load the thin permission profile from *project_root*."""

    path = _root(project_root) / CONTROL_PROFILE_PATH
    return json.loads(path.read_text(encoding="utf-8"))


def load_project_control(project_root: Path | None = None) -> dict[str, dict[str, Any]]:
    """Load all three current control-plane artifacts."""

    return {
        "authority_map": load_authority_map(project_root),
        "project_state": load_project_state(project_root),
        "control_profile": load_control_profile(project_root),
    }


def validate_project_control(project_root: Path | None = None) -> tuple[str, ...]:
    """Return deterministic validation errors for the on-disk control plane."""

    root = _root(project_root)
    control = load_project_control(root)
    errors = [
        *validate_authority_map(control["authority_map"], root),
        *validate_project_state(control["project_state"]),
        *validate_control_profile(control["control_profile"]),
    ]
    return tuple(sorted(errors))


def validate_authority_map(data: dict[str, Any], project_root: Path) -> tuple[str, ...]:
    """Validate authority classes, surfaces, conflicts, and unknowns."""

    errors: list[str] = []
    _require_header(data, "research_x_authority_map", errors)

    classifications = data.get("classifications")
    if not isinstance(classifications, dict):
        errors.append("authority_map.classifications must be an object")
        classifications = {}
    missing_classifications = REQUIRED_CLASSIFICATIONS - set(classifications)
    if missing_classifications:
        errors.append(
            "authority_map.classifications missing: " + ", ".join(sorted(missing_classifications))
        )

    surfaces = _objects(data.get("surfaces"), "authority_map.surfaces", errors)
    _require_unique_ids(surfaces, "authority_map.surfaces", errors)
    architecture_authorities: list[str] = []
    state_authorities: list[str] = []
    surface_ids: set[str] = set()
    for surface in surfaces:
        surface_id = str(surface.get("id", "<missing>"))
        surface_ids.add(surface_id)
        classification = surface.get("classification")
        if classification not in REQUIRED_CLASSIFICATIONS:
            errors.append(f"surface {surface_id} has invalid classification {classification!r}")
        if surface.get("current_architecture_authority") is True:
            architecture_authorities.append(surface_id)
            if classification != "canon":
                errors.append(f"surface {surface_id} is architecture authority but not canon")
        if surface.get("current_state_authority") is True:
            state_authorities.append(surface_id)
            if classification != "current_state":
                errors.append(f"surface {surface_id} is state authority but not current_state")
        if classification in {"history", "generated"} and (
            surface.get("current_architecture_authority") is True
            or surface.get("current_state_authority") is True
        ):
            errors.append(f"surface {surface_id} cannot make {classification} authoritative")
        if surface.get("required") is True and surface.get("locator_kind") == "file":
            relative_path = surface.get("path")
            if not isinstance(relative_path, str) or not (project_root / relative_path).is_file():
                errors.append(f"required surface {surface_id} does not resolve to a file")

    if architecture_authorities != ["architecture_canon"]:
        errors.append("architecture_canon must be the only architecture authority")
    if state_authorities != ["project_state"]:
        errors.append("project_state must be the only current-state authority")
    for required_surface in {"authority_map", "permission_profile"}:
        if required_surface not in surface_ids:
            errors.append(f"authority_map.surfaces missing control surface: {required_surface}")

    conflicts = _objects(data.get("conflicts"), "authority_map.conflicts", errors)
    unknowns = _objects(data.get("unknowns"), "authority_map.unknowns", errors)
    _require_unique_ids(conflicts, "authority_map.conflicts", errors)
    _require_unique_ids(unknowns, "authority_map.unknowns", errors)
    if not conflicts:
        errors.append("authority_map.conflicts must record known conflicts")
    if not unknowns:
        errors.append("authority_map.unknowns must record explicit unknowns")
    return tuple(errors)


def validate_project_state(data: dict[str, Any]) -> tuple[str, ...]:
    """Validate the documented run boundary and unfinished work."""

    errors: list[str] = []
    _require_header(data, "research_x_project_state", errors)
    if data.get("current_state_authority") is not True:
        errors.append("project_state.current_state_authority must be true")

    provider = data.get("provider_execution")
    if not isinstance(provider, dict):
        errors.append("project_state.provider_execution must be an object")
        provider = {}
    runs = _objects(provider.get("runs"), "project_state.provider_execution.runs", errors)
    _require_unique_ids(runs, "project_state.provider_execution.runs", errors)
    run_by_id = {run.get("id"): run for run in runs}
    for run_id, expected_documents in (("limit_10", 10), ("limit_100", 100)):
        run = run_by_id.get(run_id)
        if run is None:
            errors.append(f"project_state is missing documented run {run_id}")
            continue
        if run.get("status") != "completed":
            errors.append(f"documented run {run_id} must remain completed")
        if run.get("documented_documents") != expected_documents:
            errors.append(f"documented run {run_id} must record {expected_documents} documents")
    if provider.get("provider_runs_after_limit_100") != "unknown":
        errors.append("provider runs after limit_100 must remain explicit unknown until evidenced")
    if provider.get("quality_conclusion") != "not_established":
        errors.append("provider quality must not be promoted by run completion alone")

    abcd = data.get("embedding_input_abcd")
    if not isinstance(abcd, dict):
        errors.append("project_state.embedding_input_abcd must be an object")
        abcd = {}
    if abcd.get("status") != "completed":
        errors.append("embedding input A-D must record completed status")
    if abcd.get("lineage_disposition") != "lineage_less_pre_a_d_rows_quarantined_not_deleted":
        errors.append("pre-A-D lineage-less rows must remain quarantined, not deleted")
    if abcd.get("legacy_status") != "legacy_without_projection_lineage":
        errors.append("quarantined rows must retain legacy_without_projection_lineage status")

    promotion = data.get("semantic_promotion")
    if not isinstance(promotion, dict) or promotion.get("status") != "hold":
        errors.append("semantic promotion must remain on hold until new acceptance evidence")

    workstreams = _objects(data.get("workstreams"), "project_state.workstreams", errors)
    _require_unique_ids(workstreams, "project_state.workstreams", errors)
    workstream_by_id = {item.get("id"): item for item in workstreams}
    missing = REQUIRED_WORKSTREAMS - set(workstream_by_id)
    if missing:
        errors.append("project_state.workstreams missing: " + ", ".join(sorted(missing)))
    for workstream_id in sorted(REQUIRED_WORKSTREAMS & set(workstream_by_id)):
        if workstream_by_id[workstream_id].get("status") != "unfinished":
            errors.append(f"workstream {workstream_id} must remain unfinished until accepted")

    reports = data.get("reports_and_history")
    if not isinstance(reports, dict) or reports.get("authority") != "archive_only":
        errors.append("reports_and_history.authority must be archive_only")
    elif reports.get("current_state_authority") is not False:
        errors.append("reports_and_history cannot be current-state authority")
    if not data.get("known_conflicts"):
        errors.append("project_state.known_conflicts must not be empty")
    if not data.get("unknowns"):
        errors.append("project_state.unknowns must not be empty")
    return tuple(errors)


def validate_control_profile(data: dict[str, Any]) -> tuple[str, ...]:
    """Validate the project-specific permission profile without executing it."""

    errors: list[str] = []
    if data.get("schema_version") != 1:
        errors.append("control_profile.schema_version must be 1")
    if data.get("project_id") != "research_x":
        errors.append("control_profile.project_id must be research_x")
    unexpected = sorted(set(data) - {"schema_version", "project_id", "gates"})
    if unexpected:
        errors.append("control_profile has unknown fields: " + ", ".join(unexpected))

    gates = _objects(data.get("gates"), "control_profile.gates", errors)
    _require_unique_ids(gates, "control_profile.gates", errors, id_key="gate_id")
    gate_by_id = {gate.get("gate_id"): gate for gate in gates}
    missing = REQUIRED_GATES - set(gate_by_id)
    if missing:
        errors.append("control_profile.gates missing: " + ", ".join(sorted(missing)))
    for gate in gates:
        gate_id = str(gate.get("gate_id", "<missing>"))
        required_fields = {"gate_id", "label", "mode", "reason"}
        missing_fields = sorted(required_fields - set(gate))
        if missing_fields:
            errors.append(f"gate {gate_id} missing fields: {', '.join(missing_fields)}")
        if gate.get("mode") != "confirm_each":
            errors.append(f"project gate {gate_id} must use confirm_each")
        if not str(gate.get("label") or "").strip() or not str(gate.get("reason") or "").strip():
            errors.append(f"project gate {gate_id} requires label and reason")
    return tuple(errors)


def project_control_inventory(project_root: Path | None = None) -> dict[str, Any]:
    """Return a stable, compact inventory for CLI/UI adapters and reviews."""

    root = _root(project_root)
    control = load_project_control(root)
    authority = control["authority_map"]
    state = control["project_state"]
    profile = control["control_profile"]
    return {
        "classifications": sorted(authority["classifications"]),
        "architecture_authority": _authoritative_surface(
            authority["surfaces"], "current_architecture_authority"
        ),
        "current_state_authority": _authoritative_surface(
            authority["surfaces"], "current_state_authority"
        ),
        "documented_provider_runs": [
            {
                "id": run["id"],
                "status": run["status"],
                "documented_documents": run["documented_documents"],
            }
            for run in state["provider_execution"]["runs"]
        ],
        "semantic_promotion": state["semantic_promotion"]["status"],
        "unfinished_workstreams": sorted(
            item["id"] for item in state["workstreams"] if item["status"] == "unfinished"
        ),
        "gates": sorted(gate["gate_id"] for gate in profile["gates"]),
        "conflicts": sorted(item["id"] for item in authority["conflicts"]),
        "unknowns": sorted(item["id"] for item in authority["unknowns"]),
        "source_inventory": _source_inventory(root),
        "validation_errors": list(validate_project_control(root)),
    }


def mutable_project_control(project_root: Path | None = None) -> dict[str, dict[str, Any]]:
    """Return an isolated copy useful for policy simulation and tests."""

    return deepcopy(load_project_control(project_root))


def _root(project_root: Path | None) -> Path:
    return PROJECT_ROOT if project_root is None else Path(project_root)


def _require_header(data: dict[str, Any], artifact_kind: str, errors: list[str]) -> None:
    if data.get("schema_version") != 1:
        errors.append(f"{artifact_kind}.schema_version must be 1")
    if data.get("artifact_kind") != artifact_kind:
        errors.append(f"artifact_kind must be {artifact_kind}")
    if data.get("control_artifact") is not True:
        errors.append(f"{artifact_kind}.control_artifact must be true")
    if data.get("not_evidence") is not True:
        errors.append(f"{artifact_kind}.not_evidence must be true")


def _objects(value: Any, field: str, errors: list[str]) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        errors.append(f"{field} must be a list of objects")
        return []
    return value


def _require_unique_ids(
    items: list[dict[str, Any]],
    field: str,
    errors: list[str],
    *,
    id_key: str = "id",
) -> None:
    ids = [item.get(id_key) for item in items]
    if any(not isinstance(item_id, str) or not item_id for item_id in ids):
        errors.append(f"{field} entries must have non-empty string ids")
    if len(ids) != len(set(ids)):
        errors.append(f"{field} ids must be unique")


def _authoritative_surface(surfaces: list[dict[str, Any]], field: str) -> str:
    matches = [surface["path"] for surface in surfaces if surface.get(field) is True]
    if len(matches) != 1:
        raise ValueError(f"expected exactly one surface with {field}=true")
    return matches[0]


def _source_inventory(root: Path) -> dict[str, Any]:
    module_paths = sorted((root / "src" / "research_x").rglob("*.py"))
    test_paths = sorted((root / "tests").rglob("test_*.py"))
    prompt_paths = sorted((root / "prompt_contracts").glob("*.yaml"))
    control_paths = [
        root / AUTHORITY_MAP_PATH,
        root / PROJECT_STATE_PATH,
        root / CONTROL_PROFILE_PATH,
        root / "control" / "adoption_registry.toml",
        root / "control" / "vendor_sources.lock.toml",
    ]
    fingerprint = hashlib.sha256()
    for path in sorted({*module_paths, *test_paths, *prompt_paths, *control_paths}):
        if not path.is_file():
            continue
        relative = path.relative_to(root).as_posix()
        content = path.read_bytes()
        fingerprint.update(relative.encode("utf-8"))
        fingerprint.update(b"\0")
        fingerprint.update(content)
        fingerprint.update(b"\0")
    test_case_count = 0
    for path in test_paths:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        test_case_count += sum(
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name.startswith("test_")
            for node in ast.walk(tree)
        )
    return {
        "generated_on_read": True,
        "module_count": len(module_paths),
        "test_file_count": len(test_paths),
        "test_case_definition_count": test_case_count,
        "prompt_contract_count": len(prompt_paths),
        "source_fingerprint_sha256": fingerprint.hexdigest(),
    }
