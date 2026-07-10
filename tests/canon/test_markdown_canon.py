from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

CANON_ITEMS = ("P0", "P18")
PURPOSE = "Guard the single durable Markdown canon and retired-policy absence."
pytestmark = [pytest.mark.canon(item) for item in CANON_ITEMS]

ROOT = Path(__file__).resolve().parents[2]

ALLOWED_PROJECT_MARKDOWN = {
    "README.md",
    "AGENTS.md",
    "docs/research_x_canon.md",
}
ALLOWED_VENDOR_MARKDOWN_PREFIXES: tuple[str, ...] = ()
IGNORED_MARKDOWN_PREFIXES = (
    ".git/",
    ".pytest_cache/",
    ".ruff_cache/",
    ".mypy_cache/",
    ".secrets/",
    ".venv/",
    "node_modules/",
    "dist/",
    "build/",
    "outputs/",
    "runs/",
    "docs/control/codex/test-audits/",
)
RETIRED_MARKDOWN_PATHS = {
    "README.codex.md",
    "PROJECT.md",
    "research_x_pipeline_context.md",
    "docs/memory-pipeline-v2.md",
    "docs/memory-pipeline-v3.md",
    "docs/memory-pipeline-archive.md",
    "docs/product_goal.md",
    "docs/non_goals.md",
    "docs/artifact_roles.md",
    "docs/output_modes.md",
    "docs/provider_execution_policy.md",
    "docs/research_intake_policy.md",
    "docs/upstream_source_policy.md",
    "docs/pipeline.md",
    "docs/control/codex/README.md",
    "docs/presentation/diagram-design-harness.md",
    "docs/presentation/diagram-systems.md",
    "docs/presentation/final-design-flow.md",
    "docs/presentation/final-runtime-flow.md",
    "docs/presentation/mermaid/redesign/README.md",
    "docs/presentation/slides.md",
    "control/vendor_sources.lock.md",
    "tools/wbs_viewer/README.md",
    "tools/wbs_viewer/UPSTREAM.md",
}
OLD_POLICY_PHRASES = {
    "source-bundle-first",
    "evidence-first memory/search",
    "custom SVG generator",
    "AnswerAuthorityGatekeeper universal",
    "generated artifacts are not evidence",
    "No-quota provider freeze",
    "The forbidden default is runtime provider execution",
    "implemented_static_verified",
    "Current implementation order and status",
}

REQUIRED_CANON_CONTRACTS = (
    "This file is the one durable architecture and policy canon",
    "control/project_state.json: current implementation, runtime, quality, and acceptance state",
    "Repo-local Skills are retired",
    "are archive-only outside the rebuilt repository and are absent from the new repository",
    "ObjectiveRoute selects retrieval strategy",
    "OutputMode selects output authority",
    "Explore broadly. Assert strictly.",
    (
        "source_bundle_id and source_restore_id are compatibility names for "
        "one strict restoration lineage"
    ),
    "none: retain neither an operational trace nor derived artifacts",
    "trace: retain only run/step audit needed for observability",
    "artifacts: retain the trace and approved derived results",
    (
        "Effective permission state comes from the generalized Codex foundation "
        "permission GUI/effective profile"
    ),
    "Provider routes are gated, not blanket-disabled",
    "API Budget Guard is an independent runtime safety boundary",
    "provider embedding runs limit_10 and limit_100 occurred and completed",
    "embedding input A-D completed",
    "semantic promotion remains hold",
    "## 16.1 Context Budget Boundary",
)


def test_durable_markdown_is_collapsed_to_three_project_files() -> None:
    markdown_paths = {
        rel_path
        for path in ROOT.rglob("*.md")
        if is_project_authored_markdown(rel_path := normalize_path(path.relative_to(ROOT)))
    }

    unexpected = sorted(
        path
        for path in markdown_paths
        if path not in ALLOWED_PROJECT_MARKDOWN
        and not any(path.startswith(prefix) for prefix in ALLOWED_VENDOR_MARKDOWN_PREFIXES)
    )

    assert unexpected == []


def normalize_path(path: Path) -> str:
    return path.as_posix()


def is_ignored_markdown(path: str) -> bool:
    return path.startswith(IGNORED_MARKDOWN_PREFIXES)


def is_vendor_markdown(path: str) -> bool:
    return path.startswith(ALLOWED_VENDOR_MARKDOWN_PREFIXES)


def is_project_authored_markdown(path: str) -> bool:
    return path.endswith(".md") and not is_ignored_markdown(path) and not is_vendor_markdown(path)


def test_retired_markdown_paths_and_repo_local_skills_do_not_return() -> None:
    for path in RETIRED_MARKDOWN_PATHS:
        assert not (ROOT / path).exists(), path

    assert not (ROOT / ".agents" / "skill-references").exists()
    assert not (ROOT / ".agents" / "skills").exists()


def test_old_route_policy_phrases_are_absent_from_project_markdown() -> None:
    combined = "\n".join(
        (ROOT / path).read_text(encoding="utf-8") for path in sorted(ALLOWED_PROJECT_MARKDOWN)
    )

    for phrase in OLD_POLICY_PHRASES:
        assert phrase not in combined


def test_canon_owns_current_control_contract_without_stale_freeze() -> None:
    canon = normalized_markdown(ROOT / "docs/research_x_canon.md")

    for contract in REQUIRED_CANON_CONTRACTS:
        assert normalize_text(contract) in canon, contract

    agents = normalized_markdown(ROOT / "AGENTS.md")
    readme = normalized_markdown(ROOT / "README.md")
    assert "generalized Codex foundation GUI and effective profile" in agents
    assert "Provider work is gated, not blanket-disabled" in agents
    assert "control/project_state.json" in readme
    assert "Provider経路は一律無効ではありません" in readme


def test_markdown_canon_audit_reports_no_retired_or_unexpected_paths() -> None:
    audit = _markdown_audit()

    assert audit["retired_existing"] == []
    assert audit["unexpected_markdown"] == []
    assert audit["old_phrase_hits"] == []
    assert audit["retired_reference_hits"] == []


def _markdown_audit() -> dict[str, object]:
    module_path = ROOT / "tools" / "audit_markdown_canon.py"
    spec = importlib.util.spec_from_file_location("audit_markdown_canon", module_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.build_markdown_canon_audit(ROOT)


def normalized_markdown(path: Path) -> str:
    return normalize_text(path.read_text(encoding="utf-8"))


def normalize_text(value: str) -> str:
    return " ".join(value.replace("`", "").split())
