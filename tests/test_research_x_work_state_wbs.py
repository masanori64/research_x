from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

WBS_PATH = Path("tools/wbs_viewer/projects/research-x-work-state.json")
CODEX_PROJECT_REVIEWS = (
    "C:/Users/maasa/.codex/foundation/project_reviews/research_x_chatgpt_control"
)
CODEX_CONTEXT_OFFLOADS = "C:/Users/maasa/.codex/foundation/context_offloads/research_x"
CODEX_PROJECT_PLANS = "C:/Users/maasa/.codex/foundation/project_plans/research_x"
PRESENTATION_PLAN = CODEX_PROJECT_PLANS + "/2026-06-24-presentation-generation-flow.md"
CODEX_FOUNDATION_WORK_STATE = (
    "C:/Users/maasa/.codex/foundation/work_state/"
    "research-x-codex-foundation-adjuncts.json"
)

EXPECTED_GROUPS = [
    "Memory no-spend foundation",
    "Provider-quota gate",
    "Local dependency gate",
    "Boundary governance and control artifacts",
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
        assert meta["owner_doc"] == (
            CODEX_PROJECT_REVIEWS + "/x-url-analysis-20260622/README.md"
        )


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
    serialized = json.dumps(visual, ensure_ascii=False)
    retired_docs = "docs/" + "pdg"
    retired_tool = "tools/" + "pdg" + "kit_canary"
    retired_ext = "." + "pdg"
    retired_upper = "P" + "DG"
    retired_name = "pdg" + "kit"

    assert WBS_PATH.as_posix() in pointers
    assert CODEX_CONTEXT_OFFLOADS + "/pointer-map.json" in pointers
    assert PRESENTATION_PLAN in pointers
    assert "tools/wbs_viewer/projects/research-x-visual-context-offload.json" not in pointers
    assert {leaf["name"] for leaf in visual} >= {
        "WBS operational state lane",
        "Presentation diagram build boundary",
    }
    assert "11 WBS operational state lane" not in {leaf["name"] for leaf in visual}
    assert retired_docs not in serialized
    assert retired_tool not in serialized
    assert retired_ext not in serialized
    assert retired_upper not in serialized
    assert retired_name not in serialized


def test_codex_foundation_operation_state_is_externalized_from_research_x_wbs() -> None:
    leaves = _leaf_tasks(_project()["tasks"])
    names = {leaf["name"] for leaf in leaves}
    serialized = json.dumps(_project(), ensure_ascii=False)

    assert "Codex foundation adjuncts" not in EXPECTED_GROUPS
    assert "ImprovementSignal local pipeline" not in names
    assert "Skill lifecycle input gate" not in names
    assert "Over-implementation guard canary" not in names
    assert "Route Memory Registry and Preflight" not in names
    assert "C:/Users/maasa/.codex/route_memory/route-memory.json" not in serialized
    assert "C:/Users/maasa/.codex/foundation/codex_improvement/skill_lifecycle.py" not in serialized
    assert (
        "C:/Users/maasa/.codex/foundation/codex_improvement/overimplementation_guard.py"
        not in serialized
    )


def test_codex_foundation_work_state_exists_on_owner_machine_and_is_not_evidence() -> None:
    path = Path(CODEX_FOUNDATION_WORK_STATE)
    if not path.exists():
        pytest.skip("Codex foundation work-state archive is outside the portable repository")

    archive = json.loads(path.read_text(encoding="utf-8"))
    moved = archive["moved_tasks"]
    names = {task["name"] for task in moved}

    assert archive["owner"] == "maasa/.codex"
    assert archive["source_wbs"] == WBS_PATH.as_posix()
    assert archive["not_evidence"] is True
    assert names >= {
        "ImprovementSignal local pipeline",
        "Skill lifecycle input gate",
        "Over-implementation guard canary",
        "Route Memory Registry and Preflight",
    }
    for task in moved:
        assert task["_research_x"]["evidence_status"] == "not_evidence"
        assert task["_research_x"]["answer_support_allowed"] is False
