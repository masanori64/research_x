from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from research_x.adoption_registry import adoption_candidates

WBS_PATH = Path("tools/wbs_viewer/projects/research-x-work-state.json")
ADOPTION_REGISTRY = Path("control/adoption_registry.toml")
CODEX_WORK_STATE = Path("C:/Users/maasa/.codex/foundation/work_state")
CODEX_FOUNDATION_WORK_STATE = (
    CODEX_WORK_STATE / "research-x-codex-foundation-adjuncts.json"
)
PRE_LAYER_WBS_ARCHIVE = (
    CODEX_WORK_STATE / "research-x-pre-layer-wbs-archive-20260625.json"
)

EXPECTED_GROUPS = [
    "Source Layer",
    "Evidence Layer",
    "Retrieval-Eval Layer",
    "Tool Interface Layer",
]

REQUIRED_META_FIELDS = {
    "owner_plane",
    "runtime_layer",
    "artifact_layer",
    "decision_band",
    "gate",
    "status",
    "artifact_pointer",
    "owner_doc",
    "evidence_status",
    "answer_support_allowed",
    "stop_condition",
    "next_action",
}

ALLOWED_STATUS = {"complete", "active", "blocked", "provider_gated", "staging"}
ALLOWED_EVIDENCE_STATUS = {
    "not_evidence",
    "source_candidate",
    "source_restored",
    "citation_ready",
}
ALLOWED_RUNTIME_LAYERS = {"source", "evidence", "retrieval_eval", "tool_interface"}


def _leaf_tasks(tasks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    leaves: list[dict[str, Any]] = []
    for task in tasks:
        children = task.get("children")
        if children:
            leaves.extend(_leaf_tasks(children))
        else:
            leaves.append(task)
    return leaves


def _project() -> dict[str, Any]:
    return json.loads(WBS_PATH.read_text(encoding="utf-8"))["projects"][0]


def _root() -> dict[str, Any]:
    return json.loads(WBS_PATH.read_text(encoding="utf-8"))


def test_current_wbs_is_runtime_layer_work_state_only() -> None:
    project = _project()

    assert project["name"] == "research_x Runtime Work State"
    assert [task["name"] for task in project["tasks"]] == EXPECTED_GROUPS
    assert len(project["milestones"]) == 1


def test_current_wbs_holidays_are_viewer_config_only() -> None:
    root = _root()
    holidays = root["holidays"]

    assert len(holidays) == 18
    assert holidays[0] == {"date": "2026-01-01", "name": "元日"}
    assert holidays[-1] == {"date": "2026-11-23", "name": "勤労感謝の日"}
    assert all(set(item) == {"date", "name"} for item in holidays)
    assert "holidays" not in json.dumps(_project(), ensure_ascii=False)


def test_wbs_leaf_tasks_have_current_research_x_metadata_without_history() -> None:
    leaves = _leaf_tasks(_project()["tasks"])
    serialized = json.dumps(_project(), ensure_ascii=False)
    banned_fragments = (
        "X/GPT 35-item intake",
        "Visual context offload lane",
        "Future local hardening",
        "Boundary governance and control artifacts",
        "source_candidate_url",
        "https://x.com/",
        "C:/Users/maasa/.codex/foundation/project_reviews",
        "C:/Users/maasa/.codex/route_memory",
        "pdgkit",
    )

    assert leaves
    assert all(fragment not in serialized for fragment in banned_fragments)
    for leaf in leaves:
        meta = leaf.get("_research_x", {})
        assert set(meta) >= REQUIRED_META_FIELDS, leaf["name"]
        assert "item" not in meta
        assert "source_items" not in meta
        assert meta["owner_plane"] == "wbs"
        assert meta["runtime_layer"] in ALLOWED_RUNTIME_LAYERS
        assert meta["status"] in ALLOWED_STATUS
        assert meta["evidence_status"] in ALLOWED_EVIDENCE_STATUS
        assert meta["answer_support_allowed"] is False
        assert meta["artifact_pointer"]
        assert meta["owner_doc"]
        assert meta["stop_condition"]
        assert meta["next_action"]
        assert len(leaf.get("note", "")) <= 240


def test_wbs_leaf_text_fields_stay_bounded_control_state() -> None:
    leaves = _leaf_tasks(_project()["tasks"])
    banned_fragments = (
        "http://",
        "https://",
        "project_reviews",
        "positive_triggers",
        "known_failed_routes",
        "pointer-map.json",
        "raw visible ChatGPT",
        "source_candidate_url",
    )

    for leaf in leaves:
        meta = leaf["_research_x"]
        assert leaf["id"]
        assert leaf["name"]
        assert len(meta["next_action"]) <= 180
        assert len(meta["stop_condition"]) <= 180
        for field in ("next_action", "stop_condition"):
            text = str(meta[field])
            assert "\n" not in text
            assert all(fragment not in text for fragment in banned_fragments)


def test_wbs_and_adoption_registry_gate_states_stay_aligned() -> None:
    candidates = adoption_candidates(ADOPTION_REGISTRY)
    leaves = _leaf_tasks(_project()["tasks"])
    by_artifact_layer = {leaf["_research_x"]["artifact_layer"]: leaf for leaf in leaves}

    provider_candidates = [item for item in candidates if item.provider_or_quota]
    staging_candidates = [item for item in candidates if item.adoption_shape == "staging"]
    historical = next(item for item in candidates if item.name == "pdgkit")
    codex_bridge = next(
        item for item in candidates if item.name == "codex_foundation_registry_bridge"
    )

    assert provider_candidates
    assert staging_candidates
    external_provider = by_artifact_layer["external_source_candidate"]["_research_x"]
    local_eval = by_artifact_layer["retrieval_quality_local_fixture_gate"]["_research_x"]
    real_model_eval = by_artifact_layer[
        "retrieval_quality_real_model_provider_quality_gate"
    ]["_research_x"]
    media_preparation = by_artifact_layer["ocr_media_preparation"]["_research_x"]
    provider_retrieval = by_artifact_layer["provider_retrieval_rerank_llm"]["_research_x"]
    assert external_provider["status"] == "provider_gated"
    assert local_eval["status"] == "complete"
    assert local_eval["gate"] == "local_fixture_not_model_quality"
    assert real_model_eval["status"] == "provider_gated"
    assert "provider" in real_model_eval["gate"]
    assert provider_retrieval["status"] == "provider_gated"
    assert media_preparation["status"] in {"staging", "provider_gated"}
    assert "provider" in (
        media_preparation["gate"] + " " + media_preparation["stop_condition"]
    )
    assert all(item.enabled is False for item in provider_candidates)
    assert all(item.status == "staged" and item.enabled is False for item in staging_candidates)
    assert historical.owner_surface == "historical"
    assert historical.enabled is False
    assert codex_bridge.owner_surface == "codex_foundation"
    assert codex_bridge.adoption_shape == "bridge"
    assert codex_bridge.enabled is False


def test_active_status_is_reserved_for_concrete_local_next_tasks() -> None:
    leaves = _leaf_tasks(_project()["tasks"])
    active = [leaf for leaf in leaves if leaf["_research_x"]["status"] == "active"]

    for leaf in active:
        meta = leaf["_research_x"]
        text = " ".join(
            [
                leaf["name"],
                meta["gate"],
                meta["stop_condition"],
                meta["next_action"],
            ]
        ).lower()
        assert "provider" not in text
        assert "api" not in text
        assert "install" not in text
        assert "model download" not in text


def test_gated_statuses_are_explicitly_separated_from_active_work() -> None:
    leaves = _leaf_tasks(_project()["tasks"])
    provider_gated = [leaf for leaf in leaves if leaf["_research_x"]["status"] == "provider_gated"]
    staging = [leaf for leaf in leaves if leaf["_research_x"]["status"] == "staging"]

    assert provider_gated
    assert staging
    for leaf in provider_gated:
        meta = leaf["_research_x"]
        assert "provider" in meta["gate"] or "quota" in meta["gate"]
        assert "Stop before any" in meta["stop_condition"]
    for leaf in staging:
        meta = leaf["_research_x"]
        assert any(
            word in (meta["gate"] + " " + meta["stop_condition"])
            for word in ("dependency", "fixture", "model", "runtime")
        )


def test_media_ocr_wbs_lane_is_not_complete_or_answer_evidence() -> None:
    leaves = _leaf_tasks(_project()["tasks"])
    media = next(
        leaf["_research_x"]
        for leaf in leaves
        if leaf["_research_x"]["artifact_layer"] == "ocr_media_preparation"
    )

    assert media["status"] == "staging"
    assert media["evidence_status"] == "not_evidence"
    assert media["answer_support_allowed"] is False
    assert "dependency install" in media["stop_condition"]
    assert "model download" in media["stop_condition"]
    assert "provider OCR" in media["stop_condition"]
    assert "media embedding calls" in media["stop_condition"]


def test_codex_contact_in_current_wbs_is_only_the_thin_local_bridge() -> None:
    leaves = _leaf_tasks(_project()["tasks"])
    codex_leaves = [leaf for leaf in leaves if "Codex" in leaf["name"]]

    assert [leaf["name"] for leaf in codex_leaves] == ["Thin Codex bridge contract"]
    bridge = codex_leaves[0]["_research_x"]
    assert bridge["runtime_layer"] == "tool_interface"
    assert bridge["artifact_pointer"] == "src/research_x/tool_interface/codex_bridge.py"
    assert bridge["gate"] == "no_codex_foundation_ownership"
    assert bridge["answer_support_allowed"] is False


def test_historical_wbs_and_codex_foundation_state_are_externalized() -> None:
    if not PRE_LAYER_WBS_ARCHIVE.exists() or not CODEX_FOUNDATION_WORK_STATE.exists():
        pytest.skip("Codex foundation work-state archives are outside the portable repository")

    archive = json.loads(PRE_LAYER_WBS_ARCHIVE.read_text(encoding="utf-8"))
    foundation = json.loads(CODEX_FOUNDATION_WORK_STATE.read_text(encoding="utf-8"))
    archive_text = json.dumps(archive, ensure_ascii=False)

    assert archive["owner"] == "maasa/.codex"
    assert archive["not_evidence"] is True
    assert "X/GPT 35-item intake" in archive_text
    assert "Visual context offload lane" in archive_text
    assert foundation["owner"] == "maasa/.codex"
    assert foundation["not_evidence"] is True
    assert {task["name"] for task in foundation["moved_tasks"]} >= {
        "ImprovementSignal local pipeline",
        "Skill lifecycle input gate",
        "Over-implementation guard canary",
        "Route Memory Registry and Preflight",
    }
