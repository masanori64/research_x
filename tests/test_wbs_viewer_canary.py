from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

CODEX_PROJECT_REVIEWS = Path(
    "C:/Users/maasa/.codex/foundation/project_reviews/research_x_chatgpt_control"
)
WBS_JSON = CODEX_PROJECT_REVIEWS / "x-url-analysis-20260622" / "wbs-35-item-flow.json"
WBS_VIEWER = Path("tools/wbs_viewer/vendor/single-file-wbs-v1.3.0/wbs_viewer.html")
WBS_LICENSE = Path("tools/wbs_viewer/vendor/single-file-wbs-v1.3.0/LICENSE")


def _leaf_tasks(tasks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    leaves: list[dict[str, Any]] = []
    for task in tasks:
        children = task.get("children")
        if children:
            leaves.extend(_leaf_tasks(children))
        else:
            leaves.append(task)
    return leaves


def _load_owner_machine_wbs() -> dict[str, Any]:
    if not WBS_JSON.exists():
        pytest.skip("owner-machine WBS consultation capture is outside the portable repository")
    return json.loads(WBS_JSON.read_text(encoding="utf-8"))


def test_wbs_canary_contains_all_35_x_items() -> None:
    data = _load_owner_machine_wbs()
    project = data["projects"][0]
    leaves = _leaf_tasks(project["tasks"])

    assert project["name"] == "X/GPT 35-item adoption flow"
    assert len(project["tasks"]) == 6
    assert len(leaves) == 35
    assert len(project["milestones"]) == 3


def test_wbs_canary_marks_items_11_and_35_as_body_adoption_candidates() -> None:
    data = _load_owner_machine_wbs()
    leaves = _leaf_tasks(data["projects"][0]["tasks"])
    by_item = {leaf["_research_x"]["item"]: leaf for leaf in leaves}

    item_11 = by_item[11]
    item_35 = by_item[35]

    assert item_11["_research_x"]["decision_band"] == "second_wave_body_adoption"
    assert item_11["actual"]["start"] == "2026-06-23"
    assert item_11["actual"]["end"] == "2026-06-23"
    assert item_35["_research_x"]["decision_band"] == "second_wave_body_adoption"
    assert item_35["actual"]["start"] == "2026-06-23"
    assert item_35["actual"]["end"] == "2026-06-23"


def test_wbs_viewer_vendor_copy_is_pinned_and_local() -> None:
    html = WBS_VIEWER.read_text(encoding="utf-8")
    license_text = WBS_LICENSE.read_text(encoding="utf-8")

    assert "WBS Viewer" in html
    assert "v1.3.0" in html
    assert "holidays" in html
    assert "showOpenFilePicker" in html
    assert "MIT License" in license_text
