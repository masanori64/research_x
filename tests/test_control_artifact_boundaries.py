from __future__ import annotations

import json
from pathlib import Path

import pytest

WBS = Path("tools/wbs_viewer/projects/research-x-work-state.json")
CODEX_FOUNDATION_WORK_STATE = Path(
    "C:/Users/maasa/.codex/foundation/work_state/"
    "research-x-codex-foundation-adjuncts.json"
)


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

    source_items = {tuple(leaf["_research_x"]["source_items"]) for leaf in next_wave}

    assert source_items >= {
        (5,),
        (10,),
    }
    assert (24,) not in source_items
    assert (33,) not in source_items
    for leaf in next_wave:
        meta = leaf["_research_x"]
        assert "item" not in meta
        assert meta["answer_support_allowed"] is False
        assert meta["evidence_status"] == "not_evidence"


def test_codex_foundation_next_wave_items_are_externalized() -> None:
    if not CODEX_FOUNDATION_WORK_STATE.exists():
        pytest.skip("Codex foundation work-state archive is outside the portable repository")

    archive = json.loads(CODEX_FOUNDATION_WORK_STATE.read_text(encoding="utf-8"))
    moved_source_items = {
        tuple(task["_research_x"]["source_items"])
        for task in archive["moved_tasks"]
        if "source_items" in task["_research_x"]
    }

    assert moved_source_items >= {(24,), (33,)}
