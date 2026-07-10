from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

from research_x.cli import main
from research_x.project_control import (
    load_project_control,
    project_control_inventory,
    validate_authority_map,
    validate_control_profile,
    validate_project_control,
    validate_project_state,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_project_control_surfaces_are_valid_and_have_single_authorities() -> None:
    assert validate_project_control(PROJECT_ROOT) == ()

    inventory = project_control_inventory(PROJECT_ROOT)
    assert inventory["architecture_authority"] == "docs/research_x_canon.md"
    assert inventory["current_state_authority"] == "control/project_state.json"
    assert inventory["validation_errors"] == []


def test_inventory_reports_run_boundary_hold_and_unfinished_work() -> None:
    inventory = project_control_inventory(PROJECT_ROOT)

    assert inventory["documented_provider_runs"] == [
        {"id": "limit_10", "status": "completed", "documented_documents": 10},
        {"id": "limit_100", "status": "completed", "documented_documents": 100},
    ]
    assert inventory["semantic_promotion"] == "hold"
    assert inventory["unfinished_workstreams"] == [
        "final_product_acceptance",
        "ocr_media_provider_lanes",
        "provider_quality",
        "skillmap",
        "specialized_embedding_spaces",
    ]


def test_history_or_generated_surface_cannot_become_current_authority() -> None:
    authority = deepcopy(load_project_control(PROJECT_ROOT)["authority_map"])
    legacy_wbs = next(item for item in authority["surfaces"] if item["id"] == "legacy_wbs")
    legacy_wbs["current_state_authority"] = True

    errors = validate_authority_map(authority, PROJECT_ROOT)

    assert "surface legacy_wbs cannot make history authoritative" in errors
    assert "project_state must be the only current-state authority" in errors


def test_documented_provider_runs_cannot_be_rewritten_as_pending() -> None:
    state = deepcopy(load_project_control(PROJECT_ROOT)["project_state"])
    limit_100 = next(
        item for item in state["provider_execution"]["runs"] if item["id"] == "limit_100"
    )
    limit_100["status"] = "pending"

    assert "documented run limit_100 must remain completed" in validate_project_state(state)


def test_provider_runtime_gate_cannot_be_implicitly_opened() -> None:
    profile = deepcopy(load_project_control(PROJECT_ROOT)["control_profile"])
    provider_gate = next(
        item for item in profile["gates"] if item["gate_id"] == "research_x_route_promotion"
    )
    provider_gate["mode"] = "toggle"

    errors = validate_control_profile(profile)

    assert "project gate research_x_route_promotion must use confirm_each" in errors


def test_thin_profile_uses_unique_gate_ids_and_inventory_reads_them() -> None:
    profile = deepcopy(load_project_control(PROJECT_ROOT)["control_profile"])
    profile["gates"].append(deepcopy(profile["gates"][0]))

    assert "control_profile.gates ids must be unique" in validate_control_profile(profile)
    assert project_control_inventory(PROJECT_ROOT)["gates"] == sorted(
        {
            "research_x_external_fetch_beyond_scope",
            "research_x_high_risk_answer_assertion",
            "research_x_persisted_schema_or_data_migration",
            "research_x_route_promotion",
            "research_x_working_note_promotion",
        }
    )


def test_project_control_cli_derives_current_inventory(capsys) -> None:
    assert main(["project-control", "status", "--json"]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "ok"
    assert payload["architecture_authority"] == "docs/research_x_canon.md"
    assert payload["current_state_authority"] == "control/project_state.json"
    assert payload["semantic_promotion"] == "hold"
    assert payload["source_inventory"]["generated_on_read"] is True
    assert payload["source_inventory"]["module_count"] > 0
    assert payload["source_inventory"]["test_case_definition_count"] > 0
    assert len(payload["source_inventory"]["source_fingerprint_sha256"]) == 64
    assert payload["validation_errors"] == []
