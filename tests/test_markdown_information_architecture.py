from __future__ import annotations

from pathlib import Path

PROJECT = Path("PROJECT.md")
README_CODEX = Path("README.codex.md")
MEMORY_V2 = Path("docs/memory-pipeline-v2.md")
CODEX_PROJECT_REVIEWS = Path(
    "C:/Users/maasa/.codex/foundation/project_reviews/research_x_chatgpt_control"
)
X_GPT_DIR = CODEX_PROJECT_REVIEWS / "x-url-analysis-20260622"
CODEX_CONTEXT_OFFLOADS = "C:/Users/maasa/.codex/foundation/context_offloads/research_x"
CODEX_PROJECT_PLANS = "C:/Users/maasa/.codex/foundation/project_plans/research_x"
PRESENTATION_PLAN = CODEX_PROJECT_PLANS + "/2026-06-24-presentation-generation-flow.md"


def _line_count(path: Path) -> int:
    return len(path.read_text(encoding="utf-8").splitlines())


def test_project_and_readme_are_thin_pointer_first_surfaces() -> None:
    project = PROJECT.read_text(encoding="utf-8")
    readme = README_CODEX.read_text(encoding="utf-8")
    retired_docs = "docs/" + "pdg"
    retired_tool = "tools/" + "pdg" + "kit_canary"
    retired_canary = retired_tool + "/canaries/visual-context-offload-lane." + "pdg"

    assert _line_count(PROJECT) <= 100
    assert _line_count(README_CODEX) <= 180
    assert "tools/wbs_viewer/projects/research-x-work-state.json" in project
    assert "C:/Users/maasa/.codex/route_memory/route-memory.json" in readme
    assert CODEX_CONTEXT_OFFLOADS + "/pointer-map.json" in readme
    assert PRESENTATION_PLAN in readme
    assert "D2 + Marp" in readme
    assert retired_docs not in readme
    assert retired_tool not in readme
    assert "Completed Milestones" not in project
    assert "Current Gates" not in project
    assert "Post-V1 Work Boundaries" not in project
    assert "Main CLI Surfaces" not in readme
    assert "tools/wbs_viewer/projects/research-x-visual-context-offload.json" not in readme
    assert retired_canary not in readme


def test_readme_reduced_read_path_is_pointer_before_state_and_structure() -> None:
    text = README_CODEX.read_text(encoding="utf-8")

    route_memory = text.index("C:/Users/maasa/.codex/route_memory/route-memory.json")
    pointer = text.index(CODEX_CONTEXT_OFFLOADS + "/pointer-map.json")
    wbs = text.index("tools/wbs_viewer/projects/research-x-work-state.json")
    memory = text.index("docs/memory-pipeline-v2.md")

    assert route_memory < pointer < wbs < memory


def test_memory_pipeline_v2_keeps_evidence_contract_not_task_database() -> None:
    text = MEMORY_V2.read_text(encoding="utf-8")
    retired_docs = "docs/" + "pdg"

    assert _line_count(MEMORY_V2) <= 260
    assert "raw source != searchable document" in text
    assert "WBS JSON" in text
    assert "generated diagram sources and rendered assets" in text
    assert "D2 + Marp" in text
    assert "Pointer entries" in text
    assert "C:/Users/maasa/.codex/route_memory/route-memory.json" in text
    assert retired_docs not in text
    assert "Completed Milestones" not in text
    assert "Current active decisions" not in text
    assert "Post-V1 Implementation Boundaries" not in text
    assert "Place / Restaurant Recall" not in text
    assert "Stock / Company Event" not in text


def test_x_gpt_folder_has_thin_active_index_and_historical_markdown_notices() -> None:
    index = X_GPT_DIR / "README.md"
    text = index.read_text(encoding="utf-8")
    retired_docs = "docs/" + "pdg"
    retired_tool = "tools/" + "pdg" + "kit_canary"

    assert _line_count(index) <= 60
    assert "historical ChatGPT/GPT Pro control capture" in text
    assert "tools/wbs_viewer/projects/research-x-work-state.json" in text
    assert CODEX_CONTEXT_OFFLOADS + "/pointer-map.json" in text
    assert PRESENTATION_PLAN in text
    assert retired_docs not in text
    assert retired_tool not in text

    for path in X_GPT_DIR.glob("*.md"):
        if path.name == "README.md":
            continue
        head = path.read_text(encoding="utf-8")[:500]
        assert "Historical consultation capture. Active path:" in head, path.name
        assert "Retired diagram-tool notes inside are closed/reference-only" in head, path.name
        assert retired_docs not in head, path.name
        assert "Not evidence" in head, path.name
