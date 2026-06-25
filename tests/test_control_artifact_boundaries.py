from __future__ import annotations

import json
from pathlib import Path

WBS = Path("tools/wbs_viewer/projects/research-x-work-state.json")
POINTER_MAP = Path(".codex/context_offloads/pointer-map.json")


def _leaf_tasks(tasks: list[dict[str, object]]) -> list[dict[str, object]]:
    leaves: list[dict[str, object]] = []
    for task in tasks:
        children = task.get("children")
        if children:
            assert isinstance(children, list)
            leaves.extend(_leaf_tasks(children))
        else:
            leaves.append(task)
    return leaves


def test_next_wave_implementation_leaves_point_to_source_items_not_new_items() -> None:
    project = json.loads(WBS.read_text(encoding="utf-8"))["projects"][0]
    leaves = _leaf_tasks(project["tasks"])
    next_wave = [
        leaf
        for leaf in leaves
        if leaf.get("_research_x", {}).get("decision_band")
        in {"local_implementation", "local_eval_canary", "reference_only_boundary"}
    ]

    assert {tuple(leaf["_research_x"]["source_items"]) for leaf in next_wave} >= {
        (5,),
        (10,),
        (24,),
        (33,),
    }
    for leaf in next_wave:
        meta = leaf["_research_x"]
        assert "item" not in meta
        assert meta["answer_support_allowed"] is False
        assert meta["evidence_status"] == "not_evidence"


def test_pointer_map_marks_next_wave_plan_and_artifacts_not_evidence() -> None:
    data = json.loads(POINTER_MAP.read_text(encoding="utf-8"))
    by_path = {entry["artifact_path"]: entry for entry in data["entries"]}

    for path in (
        ".codex/implementation-plans/2026-06-24-next-wave-33-5-24-10.md",
        "src/research_x/control_artifacts/renderer.py",
        "C:/Users/maasa/.codex/foundation/codex_improvement/skill_lifecycle.py",
        "C:/Users/maasa/.codex/foundation/codex_improvement/overimplementation_guard.py",
    ):
        assert by_path[path]["not_evidence"] is True
