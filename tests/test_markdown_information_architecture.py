from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

PROJECT = Path("PROJECT.md")
README_CODEX = Path("README.codex.md")
MEMORY_V2 = Path("docs/memory-pipeline-v2.md")
CODEX_CONTEXT_OFFLOADS = "C:/Users/maasa/.codex/foundation/context_offloads/research_x"
CODEX_PROJECT_PLANS = "C:/Users/maasa/.codex/foundation/project_plans/research_x"
PRESENTATION_PLAN = CODEX_PROJECT_PLANS + "/2026-06-24-presentation-generation-flow.md"
DOC_BUDGET_REVIEW_MARKER = "doc-budget-reviewed:"
HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$", flags=re.MULTILINE)


@dataclass(frozen=True)
class MarkdownRoleContract:
    path: Path
    role: str
    target_lines: int
    hard_ceiling_lines: int
    required_sections: tuple[str, ...]
    forbidden_sections: tuple[str, ...] = ()
    required_terms: tuple[str, ...] = ()
    banned_fragments: tuple[str, ...] = ()
    ordered_fragments: tuple[str, ...] = ()


retired_docs = "docs/" + "pdg"
retired_tool = "tools/" + "pdg" + "kit_canary"
retired_canary = retired_tool + "/canaries/visual-context-offload-lane." + "pdg"

DOC_ROLE_CONTRACTS = {
    PROJECT: MarkdownRoleContract(
        path=PROJECT,
        role="short_project_tracker",
        target_lines=100,
        hard_ceiling_lines=120,
        required_sections=(
            "Goal",
            "Canonical Pointers",
            "Evidence Invariant",
            "Active Gates",
            "Current Tracker Rule",
            "Implementation Rules",
        ),
        forbidden_sections=(
            "Completed Milestones",
            "Current Gates",
            "Post-V1 Work Boundaries",
        ),
        required_terms=(
            "short tracker",
            "not the state database",
            "tools/wbs_viewer/projects/research-x-work-state.json",
            "control/adoption_registry.toml",
            "no-quota freeze",
            "source bundle",
            "context chunk",
            "citation",
            "not evidence, citations, answer support",
        ),
        banned_fragments=(
            "Current active decisions",
            "Main CLI Surfaces",
            "source_candidate_url",
            retired_docs,
            retired_tool,
        ),
    ),
    README_CODEX: MarkdownRoleContract(
        path=README_CODEX,
        role="codex_orientation",
        target_lines=180,
        hard_ceiling_lines=220,
        required_sections=(
            "Reduced Read Path",
            "Current Mission",
            "Codex Foundation Boundary",
            "Mandatory Runtime Rules",
            "Command Discovery",
            "Work-State And Structure",
            "Repo Skills",
            "Verification",
        ),
        forbidden_sections=(
            "Completed Milestones",
            "Current Gates",
            "Post-V1 Work Boundaries",
            "Main CLI Surfaces",
        ),
        required_terms=(
            "C:/Users/maasa/.codex/route_memory/route-memory.json",
            CODEX_CONTEXT_OFFLOADS + "/pointer-map.json",
            "tools/wbs_viewer/projects/research-x-work-state.json",
            "docs/memory-pipeline-v2.md",
            "no-quota freeze",
            "provider-free fixtures real model-quality evidence",
            "not evidence or answer support",
            "source bundles",
            "context chunks",
            "citations",
            "uv run",
            "GitHub workflow ownership",
        ),
        banned_fragments=(
            "tools/wbs_viewer/projects/research-x-visual-context-offload.json",
            "source_candidate_url",
            retired_docs,
            retired_tool,
            retired_canary,
        ),
        ordered_fragments=(
            "C:/Users/maasa/.codex/route_memory/route-memory.json",
            CODEX_CONTEXT_OFFLOADS + "/pointer-map.json",
            "tools/wbs_viewer/projects/research-x-work-state.json",
            "docs/memory-pipeline-v2.md",
        ),
    ),
    MEMORY_V2: MarkdownRoleContract(
        path=MEMORY_V2,
        role="evidence_architecture_contract",
        target_lines=260,
        hard_ceiling_lines=320,
        required_sections=(
            "Executive Decision",
            "Ownership Boundary",
            "Ideal Runtime Layers",
            "Core Invariant",
            "Evidence Layer Responsibilities",
            "Non-Evidence Control Artifacts",
            "WBS / Presentation / Pointer Boundary",
            "Route And Retrieval Contract",
            "Provider / API Budget Gate",
            "ContextBudgetPolicy Boundary",
            "Deletion / Rewrite Policy",
            "Open Risks",
        ),
        forbidden_sections=(
            "Completed Milestones",
            "Current active decisions",
            "Post-V1 Implementation Boundaries",
            "Place / Restaurant Recall",
            "Stock / Company Event",
        ),
        required_terms=(
            "raw source != searchable document",
            "source bundle",
            "context chunks",
            "citations",
            "not citations",
            "WBS JSON",
            "generated diagram sources and rendered assets",
            "D2 + Marp",
            "Pointer entries",
            "C:/Users/maasa/.codex/route_memory/route-memory.json",
            "free-tier",
            "trial-credit",
            "zero-dollar",
            "keyless",
            "`store=True` workflow runs may persist operational trace rows",
        ),
        banned_fragments=(
            "holidays",
            retired_docs,
        ),
    ),
}


def _line_count(path: Path) -> int:
    return len(path.read_text(encoding="utf-8").splitlines())


def _headings(text: str) -> tuple[str, ...]:
    return tuple(match.group(2).strip() for match in HEADING_RE.finditer(text))


def _assert_line_budget(contract: MarkdownRoleContract, text: str) -> None:
    line_count = _line_count(contract.path)
    assert line_count <= contract.hard_ceiling_lines
    if line_count > contract.target_lines:
        assert DOC_BUDGET_REVIEW_MARKER in text


def _assert_ordered_fragments(text: str, fragments: tuple[str, ...]) -> None:
    positions = [text.index(fragment) for fragment in fragments]
    assert positions == sorted(positions)


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
        headings = set(_headings(text))

        _assert_line_budget(contract, text)
        assert set(contract.required_sections) <= headings
        assert headings.isdisjoint(contract.forbidden_sections)
        for term in contract.required_terms:
            assert term in text
        for fragment in contract.banned_fragments:
            assert fragment not in text
        if contract.ordered_fragments:
            _assert_ordered_fragments(text, contract.ordered_fragments)


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

    _assert_ordered_fragments(text, DOC_ROLE_CONTRACTS[README_CODEX].ordered_fragments)


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
