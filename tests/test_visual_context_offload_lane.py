from __future__ import annotations

import json
from pathlib import Path
from typing import Any

WBS_SOURCE = Path("tools/wbs_viewer/projects/research-x-work-state.json")
PDG_SOURCE = Path("docs/pdg/visual-context-offload-lane.pdg")
PDG_SVG = Path("docs/pdg/out/visual-context-offload-lane.svg")
POINTER_MAP = Path(".codex/context_offloads/pointer-map.json")
ARCHITECTURE_DOC = Path("docs/memory-pipeline-v2.md")


def _leaf_tasks(tasks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    leaves: list[dict[str, Any]] = []
    for task in tasks:
        children = task.get("children")
        if children:
            leaves.extend(_leaf_tasks(children))
        else:
            leaves.append(task)
    return leaves


def test_visual_context_wbs_records_lane_boundaries() -> None:
    data = json.loads(WBS_SOURCE.read_text(encoding="utf-8"))
    project = data["projects"][0]
    leaves = _leaf_tasks(project["tasks"])
    visual = [
        leaf
        for leaf in leaves
        if leaf["_research_x"]["decision_band"] == "visual_context_offload"
    ]
    gates = {leaf["_research_x"]["gate"] for leaf in visual}
    layers = {leaf["_research_x"]["artifact_layer"] for leaf in visual}

    assert project["name"] == "research_x Canonical Work State"
    assert "not_evidence_not_citation" in gates
    assert "source_bundle_context_citation_required_for_claims" in gates
    assert {"operational_state", "structural_flow", "context_pointer"} <= layers


def test_visual_context_pdg_source_and_svg_are_recorded() -> None:
    source = PDG_SOURCE.read_text(encoding="utf-8")
    svg = PDG_SVG.read_text(encoding="utf-8")

    assert source.startswith("#! kind: flow")
    assert "S190 = Update pointer-map JSON" in source
    assert "S230 = Restore source bundle, context chunks, and citations" in source
    assert "<svg" in svg
    assert "Update pointer-map JSON" in svg


def test_visual_context_pointer_map_covers_current_artifacts() -> None:
    data = json.loads(POINTER_MAP.read_text(encoding="utf-8"))
    paths = {entry["artifact_path"] for entry in data["entries"]}

    assert WBS_SOURCE.as_posix() in paths
    assert PDG_SOURCE.as_posix() in paths
    assert PDG_SVG.as_posix() in paths
    assert "tools/wbs_viewer/projects/research-x-visual-context-offload.json" not in paths
    assert "tools/pdgkit_canary/canaries/visual-context-offload-lane.pdg" not in paths


def test_visual_context_offload_is_not_evidence_or_architecture_replacement() -> None:
    architecture = ARCHITECTURE_DOC.read_text(encoding="utf-8")
    pointer_map = POINTER_MAP.read_text(encoding="utf-8")

    assert "Non-Evidence Control Artifacts" in architecture
    assert "WBS JSON" in architecture
    assert "PDG source" in architecture
    assert "not evidence or answer support" in pointer_map
    assert "source bundle, context chunk, and citation support" in architecture
