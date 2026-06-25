from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

WBS_PATH = Path("tools/wbs_viewer/projects/research-x-work-state.json")
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


def test_current_wbs_is_runtime_layer_work_state_only() -> None:
    project = _project()

    assert project["name"] == "research_x Runtime Work State"
    assert [task["name"] for task in project["tasks"]] == EXPECTED_GROUPS
    assert len(project["milestones"]) == 1


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
