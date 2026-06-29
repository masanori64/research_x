from __future__ import annotations

import json
from pathlib import Path

import pytest

WBS = Path("tools/wbs_viewer/projects/research-x-work-state.json")
CODEX_FOUNDATION_WORK_STATE = Path(
    "C:/Users/maasa/.codex/foundation/work_state/"
    "research-x-codex-foundation-adjuncts.json"
)
PRE_LAYER_WBS_ARCHIVE = Path(
    "C:/Users/maasa/.codex/foundation/work_state/"
    "research-x-pre-layer-wbs-archive-20260625.json"
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


def test_current_wbs_contains_no_historical_source_item_fields() -> None:
    project = json.loads(WBS.read_text(encoding="utf-8"))["projects"][0]
    leaves = _leaf_tasks(project["tasks"])

    assert leaves
    for leaf in leaves:
        meta = leaf["_research_x"]
        assert "item" not in meta
        assert "source_items" not in meta
        assert "source_candidate_url" not in meta
        assert meta["answer_support_allowed"] is False
        assert meta["evidence_status"] == "not_evidence"


def test_current_wbs_display_config_stays_out_of_runtime_leaves() -> None:
    root = json.loads(WBS.read_text(encoding="utf-8"))
    project = root["projects"][0]
    project_text = json.dumps(project, ensure_ascii=False)

    assert "holidays" in root
    assert "holidays" not in project_text
    for leaf in _leaf_tasks(project["tasks"]):
        meta_text = json.dumps(leaf["_research_x"], ensure_ascii=False)
        assert "holidays" not in meta_text


def test_historical_candidate_and_codex_items_are_externalized() -> None:
    if not PRE_LAYER_WBS_ARCHIVE.exists() or not CODEX_FOUNDATION_WORK_STATE.exists():
        pytest.skip("Codex foundation work-state archives are outside the portable repository")

    wbs_archive = json.loads(PRE_LAYER_WBS_ARCHIVE.read_text(encoding="utf-8"))
    foundation_archive = json.loads(CODEX_FOUNDATION_WORK_STATE.read_text(encoding="utf-8"))
    wbs_archive_text = json.dumps(wbs_archive, ensure_ascii=False)
    moved_source_items = {
        tuple(task["_research_x"]["source_items"])
        for task in foundation_archive["moved_tasks"]
        if "source_items" in task["_research_x"]
    }

    assert "X/GPT 35-item intake" in wbs_archive_text
    assert "source_candidate_url" in wbs_archive_text
    assert moved_source_items >= {(24,), (33,)}
