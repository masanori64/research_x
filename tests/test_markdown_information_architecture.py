from __future__ import annotations

from pathlib import Path

PROJECT = Path("PROJECT.md")
README_CODEX = Path("README.codex.md")
MEMORY_V2 = Path("docs/memory-pipeline-v2.md")
X_GPT_DIR = Path(".codex/chatgpt-control/x-url-analysis-20260622")


def _line_count(path: Path) -> int:
    return len(path.read_text(encoding="utf-8").splitlines())


def test_project_and_readme_are_thin_pointer_first_surfaces() -> None:
    project = PROJECT.read_text(encoding="utf-8")
    readme = README_CODEX.read_text(encoding="utf-8")

    assert _line_count(PROJECT) <= 100
    assert _line_count(README_CODEX) <= 180
    assert "tools/wbs_viewer/projects/research-x-work-state.json" in project
    assert ".codex/route_memory/route-memory.json" in readme
    assert ".codex/context_offloads/pointer-map.json" in readme
    assert "docs/pdg/*.pdg" in readme
    assert "Completed Milestones" not in project
    assert "Current Gates" not in project
    assert "Post-V1 Work Boundaries" not in project
    assert "Main CLI Surfaces" not in readme
    assert "tools/wbs_viewer/projects/research-x-visual-context-offload.json" not in readme
    assert "tools/pdgkit_canary/canaries/visual-context-offload-lane.pdg" not in readme


def test_readme_reduced_read_path_is_pointer_before_state_and_structure() -> None:
    text = README_CODEX.read_text(encoding="utf-8")

    route_memory = text.index(".codex/route_memory/route-memory.json")
    pointer = text.index(".codex/context_offloads/pointer-map.json")
    wbs = text.index("tools/wbs_viewer/projects/research-x-work-state.json")
    pdg = text.index("docs/pdg/*.pdg")
    memory = text.index("docs/memory-pipeline-v2.md")

    assert route_memory < pointer < wbs < pdg < memory


def test_memory_pipeline_v2_keeps_evidence_contract_not_task_database() -> None:
    text = MEMORY_V2.read_text(encoding="utf-8")

    assert _line_count(MEMORY_V2) <= 260
    assert "raw source != searchable document" in text
    assert "WBS JSON" in text
    assert "PDG source" in text
    assert "Pointer entries" in text
    assert ".codex/route_memory/route-memory.json" in text
    assert "Completed Milestones" not in text
    assert "Current active decisions" not in text
    assert "Post-V1 Implementation Boundaries" not in text
    assert "Place / Restaurant Recall" not in text
    assert "Stock / Company Event" not in text


def test_x_gpt_folder_has_thin_active_index_and_historical_markdown_notices() -> None:
    index = X_GPT_DIR / "README.md"
    text = index.read_text(encoding="utf-8")

    assert _line_count(index) <= 60
    assert "historical ChatGPT/GPT Pro control capture" in text
    assert "tools/wbs_viewer/projects/research-x-work-state.json" in text
    assert "docs/pdg/source-intake-gate-flow.pdg" in text
    assert ".codex/context_offloads/pointer-map.json" in text

    for path in X_GPT_DIR.glob("*.md"):
        if path.name == "README.md":
            continue
        head = path.read_text(encoding="utf-8")[:500]
        assert "Historical consultation capture. Active path:" in head, path.name
        assert "Not evidence" in head, path.name
