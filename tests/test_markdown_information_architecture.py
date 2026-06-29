from __future__ import annotations

from pathlib import Path

from research_x.control_artifacts.doc_budget import (
    CODEX_CONTEXT_OFFLOADS,
    DOC_BUDGET_REVIEW_MARKER,
    DOC_ROLE_CONTRACTS,
    MEMORY_V2,
    PRESENTATION_PLAN,
    PROJECT,
    README_CODEX,
    assert_ordered_fragments,
    markdown_headings,
    retired_canary,
    retired_docs,
    retired_tool,
)


def _line_count(path: Path) -> int:
    return len(path.read_text(encoding="utf-8").splitlines())


def _assert_line_budget(path: Path, text: str) -> None:
    contract = DOC_ROLE_CONTRACTS[path]
    line_count = _line_count(path)
    assert line_count <= contract.hard_ceiling_lines
    if line_count > contract.target_lines:
        assert DOC_BUDGET_REVIEW_MARKER in text


def test_markdown_role_contract_manifest_is_complete() -> None:
    assert set(DOC_ROLE_CONTRACTS) == {PROJECT, README_CODEX, MEMORY_V2}
    for contract in DOC_ROLE_CONTRACTS.values():
        assert contract.role
        assert contract.target_lines < contract.hard_ceiling_lines
        assert contract.required_sections
        assert contract.required_terms


def test_markdown_documents_obey_role_contracts() -> None:
    for contract in DOC_ROLE_CONTRACTS.values():
        text = contract.path.read_text(encoding="utf-8")
        headings = set(markdown_headings(text))

        _assert_line_budget(contract.path, text)
        assert set(contract.required_sections) <= headings
        assert headings.isdisjoint(contract.forbidden_sections)
        for term in contract.required_terms:
            assert term in text
        for fragment in contract.banned_fragments:
            assert fragment not in text
        if contract.ordered_fragments:
            assert_ordered_fragments(text, contract.ordered_fragments)


def test_project_and_readme_are_thin_pointer_first_surfaces() -> None:
    project = PROJECT.read_text(encoding="utf-8")
    readme = README_CODEX.read_text(encoding="utf-8")

    assert _line_count(PROJECT) <= DOC_ROLE_CONTRACTS[PROJECT].hard_ceiling_lines
    assert _line_count(README_CODEX) <= DOC_ROLE_CONTRACTS[README_CODEX].hard_ceiling_lines
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

    assert_ordered_fragments(text, DOC_ROLE_CONTRACTS[README_CODEX].ordered_fragments)


def test_memory_pipeline_v2_keeps_evidence_contract_not_task_database() -> None:
    text = MEMORY_V2.read_text(encoding="utf-8")

    assert _line_count(MEMORY_V2) <= DOC_ROLE_CONTRACTS[MEMORY_V2].hard_ceiling_lines
    assert "raw source != searchable document" in text
    assert "WBS JSON" in text
    assert "generated diagram sources and rendered assets" in text
    assert "D2 + Marp" in text
    assert "Pointer entries" in text
    assert "C:/Users/maasa/.codex/route_memory/route-memory.json" in text
    assert "holidays" not in text
    for gate_term in ("free-tier", "trial-credit", "zero-dollar", "keyless"):
        assert gate_term in text
    assert "`store=True` workflow runs may persist operational trace rows" in text
    assert retired_docs not in text
    assert "Completed Milestones" not in text
    assert "Current active decisions" not in text
    assert "Post-V1 Implementation Boundaries" not in text
    assert "Place / Restaurant Recall" not in text
    assert "Stock / Company Event" not in text
