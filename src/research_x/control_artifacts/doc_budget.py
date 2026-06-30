from __future__ import annotations

import json
import re
from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ARTIFACT_KIND = "research_x_doc_budget_audit"
SCHEMA_VERSION = 1
DOC_BUDGET_REVIEW_MARKER = "doc-budget-reviewed:"

PROJECT = Path("PROJECT.md")
README_CODEX = Path("README.codex.md")
MEMORY_V2 = Path("docs/memory-pipeline-v2.md")
WBS_PATH = Path("tools/wbs_viewer/projects/research-x-work-state.json")

CODEX_CONTEXT_OFFLOADS = "C:/Users/maasa/.codex/foundation/context_offloads/research_x"
CODEX_PROJECT_PLANS = "C:/Users/maasa/.codex/foundation/project_plans/research_x"
PRESENTATION_PLAN = CODEX_PROJECT_PLANS + "/2026-06-24-presentation-generation-flow.md"
HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$", flags=re.MULTILINE)

WBS_ACTION_CATEGORIES = (
    "local_audit",
    "local_test",
    "review_package",
    "provider_gate_review",
    "install_gate_review",
    "docs_contract_update",
    "no_action_local_complete",
)


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
        target_lines=120,
        hard_ceiling_lines=150,
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
        target_lines=220,
        hard_ceiling_lines=280,
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
            "docs/presentation/final-runtime-flow.md",
            "docs/presentation/final-design-flow.md",
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
        target_lines=480,
        hard_ceiling_lines=560,
        required_sections=(
            "Executive Decision",
            "Current Final Flow Authority",
            "Ownership Boundary",
            "Core Invariant",
            "Authority Model",
            "Runtime Flow Contract",
            "Evidence Layer Responsibilities",
            "ProviderApiBudgetGuard",
            "Workflow Trace Sidecar",
            "Tool Interface Layer",
            "Eval / Audit / Feedback",
            "ContextBudgetPolicy Boundary",
            "Non-Evidence Control Artifacts",
            "WBS / Presentation / Pointer Boundary",
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
            "docs/presentation/final-runtime-flow.md",
            "docs/presentation/final-design-flow.md",
            "raw source != searchable document",
            "SearchLens / RetrievalPolicy",
            "ObjectiveRoutePolicy",
            "ProviderApiBudgetGuard",
            "AnswerAuthorityGatekeeper",
            "source bundle",
            "context chunks",
            "citations",
            "claim-level support mapping",
            "hypothesis_only",
            "provider_gated",
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

ALLOWED_WBS_OWNER_DOCS = frozenset(
    {
        "README.codex.md",
        "control/adoption_registry.toml",
        "control/research_intake/research_x_sources.profile.toml",
        "control/vendor_sources.lock.md",
        "docs/memory-pipeline-v2.md",
        "docs/pipeline.md",
        "src/research_x/memory/retrieval_strategy.py",
        "src/research_x/tool_interface/memory_tool_contract.py",
    }
)

ALLOWED_WBS_ARTIFACT_PREFIXES = (
    "control/",
    "docs/",
    "prompt_contracts/",
    "src/research_x/",
    "tools/wbs_viewer/",
)


def build_doc_budget_audit(project_root: str | Path = ".") -> dict[str, Any]:
    root = Path(project_root)
    documents = [document_budget_report(contract, project_root=root) for contract in _contracts()]
    wbs = wbs_budget_report(project_root=root)
    return {
        "artifact_kind": ARTIFACT_KIND,
        "schema_version": SCHEMA_VERSION,
        "not_evidence": True,
        "not_citation": True,
        "not_answer_support": True,
        "documents": documents,
        "wbs": wbs,
        "summary": {
            "document_count": len(documents),
            "document_hard_ceiling_violation_count": sum(
                len(item["hard_ceiling_violations"]) for item in documents
            ),
            "document_missing_required_section_count": sum(
                len(item["missing_required_sections"]) for item in documents
            ),
            "document_forbidden_section_count": sum(
                len(item["forbidden_sections_present"]) for item in documents
            ),
            "document_missing_required_term_count": sum(
                len(item["missing_required_terms"]) for item in documents
            ),
            "document_banned_fragment_count": sum(
                len(item["banned_fragments_present"]) for item in documents
            ),
            "document_ordered_fragment_violation_count": sum(
                len(item["ordered_fragment_violations"]) for item in documents
            ),
            "document_target_review_marker_missing_count": sum(
                1 for item in documents if item["target_review_marker_missing"]
            ),
            "wbs_semantic_violation_count": wbs["semantic_violation_count"],
        },
    }


def doc_budget_audit_json(project_root: str | Path = ".") -> str:
    return json.dumps(
        build_doc_budget_audit(project_root),
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    ) + "\n"


def document_budget_report(
    contract: MarkdownRoleContract,
    *,
    project_root: str | Path = ".",
) -> dict[str, Any]:
    root = Path(project_root)
    path = root / contract.path
    if not path.exists():
        return {
            "path": contract.path.as_posix(),
            "role": contract.role,
            "exists": False,
            "line_count": 0,
            "target_lines": contract.target_lines,
            "hard_ceiling_lines": contract.hard_ceiling_lines,
            "over_target": False,
            "budget_review_marker_present": False,
            "target_review_marker_missing": False,
            "hard_ceiling_violations": [f"missing document: {contract.path.as_posix()}"],
            "missing_required_sections": list(contract.required_sections),
            "forbidden_sections_present": [],
            "missing_required_terms": list(contract.required_terms),
            "banned_fragments_present": [],
            "ordered_fragment_violations": [],
        }
    text = path.read_text(encoding="utf-8")
    headings = set(markdown_headings(text))
    line_count = len(text.splitlines())
    over_target = line_count > contract.target_lines
    marker_present = DOC_BUDGET_REVIEW_MARKER in text
    return {
        "path": contract.path.as_posix(),
        "role": contract.role,
        "exists": True,
        "line_count": line_count,
        "target_lines": contract.target_lines,
        "hard_ceiling_lines": contract.hard_ceiling_lines,
        "over_target": over_target,
        "budget_review_marker_present": marker_present,
        "target_review_marker_missing": over_target and not marker_present,
        "hard_ceiling_violations": (
            [f"{contract.path.as_posix()} has {line_count} lines"]
            if line_count > contract.hard_ceiling_lines
            else []
        ),
        "missing_required_sections": sorted(set(contract.required_sections) - headings),
        "forbidden_sections_present": sorted(headings & set(contract.forbidden_sections)),
        "missing_required_terms": [term for term in contract.required_terms if term not in text],
        "banned_fragments_present": [
            fragment for fragment in contract.banned_fragments if fragment in text
        ],
        "ordered_fragment_violations": _ordered_fragment_violations(
            text,
            contract.ordered_fragments,
        ),
    }


def markdown_headings(text: str) -> tuple[str, ...]:
    return tuple(match.group(2).strip() for match in HEADING_RE.finditer(text))


def assert_ordered_fragments(text: str, fragments: tuple[str, ...]) -> None:
    positions = [text.index(fragment) for fragment in fragments]
    assert positions == sorted(positions)


def wbs_budget_report(project_root: str | Path = ".") -> dict[str, Any]:
    root = Path(project_root)
    path = root / WBS_PATH
    payload = json.loads(path.read_text(encoding="utf-8"))
    leaves = list(iter_wbs_leaf_tasks(payload))
    category_counts: Counter[str] = Counter({category: 0 for category in WBS_ACTION_CATEGORIES})
    max_field_lengths = {"note": 0, "next_action": 0, "stop_condition": 0}
    violations: list[dict[str, str]] = []
    provider_gated_count = 0
    install_gated_count = 0
    not_evidence_violation_count = 0
    answer_support_allowed_violation_count = 0

    for leaf in leaves:
        meta = _meta(leaf)
        category = classify_wbs_next_action(meta)
        category_counts[category] += 1
        if meta.get("status") == "provider_gated":
            provider_gated_count += 1
        if category == "install_gate_review":
            install_gated_count += 1
        note = str(leaf.get("note", ""))
        max_field_lengths["note"] = max(max_field_lengths["note"], len(note))
        for field in ("next_action", "stop_condition"):
            max_field_lengths[field] = max(
                max_field_lengths[field],
                len(str(meta.get(field, ""))),
            )
        leaf_violations = _wbs_leaf_semantic_violations(leaf, category)
        violations.extend(leaf_violations)
        if meta.get("evidence_status") != "not_evidence":
            not_evidence_violation_count += 1
        if meta.get("answer_support_allowed") is not False:
            answer_support_allowed_violation_count += 1

    return {
        "path": WBS_PATH.as_posix(),
        "task_count": _task_count(payload),
        "leaf_count": len(leaves),
        "semantic_category_counts": dict(sorted(category_counts.items())),
        "provider_gated_count": provider_gated_count,
        "install_gated_count": install_gated_count,
        "max_field_lengths": max_field_lengths,
        "not_evidence_violation_count": not_evidence_violation_count,
        "answer_support_allowed_violation_count": answer_support_allowed_violation_count,
        "semantic_violation_count": len(violations),
        "semantic_violations": violations,
    }


def iter_wbs_leaf_tasks(payload: Mapping[str, Any]) -> Iterable[Mapping[str, Any]]:
    projects = payload.get("projects")
    if not isinstance(projects, list) or not projects:
        return
    tasks = projects[0].get("tasks")
    if not isinstance(tasks, list):
        return
    yield from _iter_leaf_tasks(tasks)


def classify_wbs_next_action(meta: Mapping[str, Any]) -> str:
    next_action = str(meta.get("next_action", ""))
    status = str(meta.get("status", ""))
    gate = str(meta.get("gate", ""))
    stop_condition = str(meta.get("stop_condition", ""))
    combined = " ".join([next_action, gate, stop_condition]).lower()
    if status == "provider_gated":
        return "provider_gate_review"
    if status == "staging" or any(
        fragment in combined
        for fragment in (
            "dependency install",
            "dependency_review",
            "model download",
            "fake/local fixtures",
        )
    ):
        return "install_gate_review"
    if any(fragment in combined for fragment in ("review zip", "adoption audit", "source locks")):
        return "review_package"
    if any(fragment in combined for fragment in ("pytest", "marker", "fixture", "tests green")):
        return "local_test"
    if any(fragment in combined for fragment in ("markdown", "docs", "doc contract")):
        return "docs_contract_update"
    if not next_action.strip() and status == "complete":
        return "no_action_local_complete"
    return "local_audit"


def _contracts() -> tuple[MarkdownRoleContract, ...]:
    return tuple(DOC_ROLE_CONTRACTS.values())


def _ordered_fragment_violations(text: str, fragments: tuple[str, ...]) -> list[str]:
    if not fragments:
        return []
    missing = [fragment for fragment in fragments if fragment not in text]
    if missing:
        return [f"missing ordered fragment: {fragment}" for fragment in missing]
    positions = [text.index(fragment) for fragment in fragments]
    if positions != sorted(positions):
        return ["ordered fragments are out of order"]
    return []


def _iter_leaf_tasks(tasks: list[Mapping[str, Any]]) -> Iterable[Mapping[str, Any]]:
    for task in tasks:
        children = task.get("children")
        if isinstance(children, list) and children:
            yield from _iter_leaf_tasks(children)
        else:
            yield task


def _task_count(payload: Mapping[str, Any]) -> int:
    projects = payload.get("projects")
    if not isinstance(projects, list) or not projects:
        return 0
    tasks = projects[0].get("tasks")
    if not isinstance(tasks, list):
        return 0
    return sum(1 for _ in _iter_tasks(tasks))


def _iter_tasks(tasks: list[Mapping[str, Any]]) -> Iterable[Mapping[str, Any]]:
    for task in tasks:
        yield task
        children = task.get("children")
        if isinstance(children, list) and children:
            yield from _iter_tasks(children)


def _meta(leaf: Mapping[str, Any]) -> Mapping[str, Any]:
    meta = leaf.get("_research_x")
    return meta if isinstance(meta, Mapping) else {}


def _wbs_leaf_semantic_violations(
    leaf: Mapping[str, Any],
    category: str,
) -> list[dict[str, str]]:
    meta = _meta(leaf)
    violations: list[dict[str, str]] = []
    task_id = str(leaf.get("id", "<unknown>"))
    artifact_layer = str(meta.get("artifact_layer", "<unknown>"))
    status = str(meta.get("status", ""))
    gate = str(meta.get("gate", ""))
    stop_condition = str(meta.get("stop_condition", ""))
    next_action = str(meta.get("next_action", ""))

    def add(field: str, message: str) -> None:
        violations.append(
            {
                "task_id": task_id,
                "artifact_layer": artifact_layer,
                "field": field,
                "message": message,
            }
        )

    if meta.get("evidence_status") != "not_evidence":
        add("evidence_status", "WBS leaf must stay not_evidence")
    if meta.get("answer_support_allowed") is not False:
        add("answer_support_allowed", "WBS leaf must not allow answer support")
    if str(meta.get("owner_doc", "")) not in ALLOWED_WBS_OWNER_DOCS:
        add("owner_doc", "owner_doc is outside approved source-of-truth surfaces")
    artifact_pointer = str(meta.get("artifact_pointer", ""))
    if not artifact_pointer.startswith(ALLOWED_WBS_ARTIFACT_PREFIXES):
        add("artifact_pointer", "artifact_pointer is outside approved project surfaces")
    if not stop_condition.startswith("Stop "):
        add("stop_condition", "stop_condition must be an explicit Stop condition")
    if not any(token in stop_condition for token in (" if ", " before ", "if ", "before ")):
        add("stop_condition", "stop_condition must name a concrete stopping boundary")
    if status == "provider_gated":
        if category != "provider_gate_review":
            add("next_action", "provider_gated work must classify as provider_gate_review")
        if "provider" not in gate and "quota" not in gate:
            add("gate", "provider_gated work must name provider or quota gate")
        if not any(
            token in (stop_condition + " " + next_action).lower()
            for token in ("explicit approval", "approved provider", "before any", "budget guard")
        ):
            add("next_action", "provider_gated next action must stay approval or review oriented")
        if re.search(r"\b(call|execute|invoke|send)\b.*\b(provider|api)\b", next_action.lower()):
            add("next_action", "provider_gated next action must not execute provider/API calls")
    if status == "staging" and category != "install_gate_review":
        add("next_action", "staging work must classify as install_gate_review")
    if "control_artifact" in gate and not _mentions_non_evidence_boundary(stop_condition):
        add("stop_condition", "control artifacts must name evidence/citation/answer boundary")
    return violations


def _mentions_non_evidence_boundary(text: str) -> bool:
    normalized = text.lower()
    return (
        "evidence" in normalized
        or "citation" in normalized
        or "answer support" in normalized
    )
