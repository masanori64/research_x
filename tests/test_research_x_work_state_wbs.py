from __future__ import annotations

import json
from pathlib import Path
from typing import Any

WBS_PATH = Path("tools/wbs_viewer/projects/research-x-work-state.json")

EXPECTED_GROUPS = [
    "Memory no-spend foundation",
    "Provider-quota gate",
    "Local dependency gate",
    "Codex foundation adjuncts",
    "X/GPT 35-item intake",
    "Visual context offload lane",
    "Future local hardening",
]

REQUIRED_META_FIELDS = {
    "owner_plane",
    "artifact_layer",
    "decision_band",
    "gate",
    "status",
    "artifact_pointer",
    "owner_doc",
    "evidence_status",
    "answer_support_allowed",
}

ALLOWED_STATUS = {"complete", "active", "blocked", "closed", "archived"}
ALLOWED_EVIDENCE_STATUS = {
    "not_evidence",
    "source_candidate",
    "source_restored",
    "citation_ready",
}


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


def test_canonical_wbs_has_expected_top_level_planes() -> None:
    project = _project()

    assert project["name"] == "research_x Canonical Work State"
    assert [task["name"] for task in project["tasks"]] == EXPECTED_GROUPS


def test_wbs_leaf_tasks_have_research_x_metadata_without_long_notes() -> None:
    leaves = _leaf_tasks(_project()["tasks"])

    assert leaves
    for leaf in leaves:
        meta = leaf.get("_research_x", {})
        assert set(meta) >= REQUIRED_META_FIELDS, leaf["name"]
        assert meta["owner_plane"] == "wbs"
        assert meta["status"] in ALLOWED_STATUS
        assert meta["evidence_status"] in ALLOWED_EVIDENCE_STATUS
        assert meta["answer_support_allowed"] is False
        assert meta["artifact_pointer"]
        assert meta["owner_doc"]
        assert len(leaf.get("note", "")) <= 240


def test_x_gpt_intake_keeps_all_35_items_without_becoming_evidence() -> None:
    leaves = _leaf_tasks(_project()["tasks"])
    x_items = [leaf for leaf in leaves if "item" in leaf.get("_research_x", {})]
    by_item = {leaf["_research_x"]["item"]: leaf for leaf in x_items}

    assert sorted(by_item) == list(range(1, 36))
    assert len(x_items) == 35

    for leaf in x_items:
        meta = leaf["_research_x"]
        assert meta["artifact_layer"] == "candidate_state"
        assert meta["evidence_status"] == "source_candidate"
        assert meta["answer_support_allowed"] is False
        assert meta["source_candidate_url"].startswith("https://x.com/")
        assert meta["artifact_pointer"] == WBS_PATH.as_posix()
        assert meta["owner_doc"] == ".codex/chatgpt-control/x-url-analysis-20260622/README.md"


def test_items_11_and_35_remain_item_specific_historical_records() -> None:
    leaves = _leaf_tasks(_project()["tasks"])
    by_item = {
        leaf["_research_x"]["item"]: leaf
        for leaf in leaves
        if "item" in leaf.get("_research_x", {})
    }

    for item in (11, 35):
        meta = by_item[item]["_research_x"]
        assert meta["decision_band"] == "second_wave_body_adoption"
        assert meta["status"] == "complete"
        assert by_item[item]["actual"]["start"] == "2026-06-23"
        assert by_item[item]["actual"]["end"] == "2026-06-23"


def test_visual_context_lane_points_to_canonical_artifacts() -> None:
    leaves = _leaf_tasks(_project()["tasks"])
    visual = [
        leaf
        for leaf in leaves
        if leaf["_research_x"]["decision_band"] == "visual_context_offload"
    ]
    pointers = {leaf["_research_x"]["artifact_pointer"] for leaf in visual}

    assert WBS_PATH.as_posix() in pointers
    assert "docs/pdg/visual-context-offload-lane.pdg" in pointers
    assert ".codex/context_offloads/pointer-map.json" in pointers
    assert "tools/wbs_viewer/projects/research-x-visual-context-offload.json" not in pointers
    assert "tools/pdgkit_canary/canaries/visual-context-offload-lane.pdg" not in pointers
    assert {leaf["name"] for leaf in visual} >= {
        "WBS operational state lane",
        "PDG structural flow lane",
    }
    assert "11 WBS operational state lane" not in {leaf["name"] for leaf in visual}
    assert "35 pdgkit structural flow lane" not in {leaf["name"] for leaf in visual}


def test_route_memory_preflight_is_codex_foundation_state_not_evidence() -> None:
    leaves = _leaf_tasks(_project()["tasks"])
    route_memory = next(
        leaf
        for leaf in leaves
        if leaf["name"] == "Route Memory Registry and Preflight"
    )
    meta = route_memory["_research_x"]

    assert route_memory["id"] == "4.6"
    assert meta["artifact_layer"] == "operation_route_memory"
    assert meta["decision_band"] == "project_state"
    assert meta["gate"] == "route_memory_preflight_no_provider_no_network_by_default"
    assert meta["status"] == "complete"
    assert meta["artifact_pointer"] == ".codex/route_memory/route-memory.json"
    assert meta["owner_doc"] == "AGENTS.md"
    assert meta["evidence_status"] == "not_evidence"
    assert meta["answer_support_allowed"] is False
