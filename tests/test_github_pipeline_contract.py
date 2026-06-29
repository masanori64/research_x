from __future__ import annotations

from pathlib import Path

WORKFLOWS = Path(".github/workflows")
DEPENDABOT = Path(".github/dependabot.yml")


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_product_ci_is_separate_from_codex_control_artifact_ci() -> None:
    product_ci = _read(WORKFLOWS / "research-x-ci.yml")
    control_ci = _read(WORKFLOWS / "codex-ci.yml")

    assert "name: Research X Product CI" in product_ci
    assert "control_artifact=true" not in product_ci
    assert "not_research_evidence=true" not in product_ci
    assert "Codex Control Artifact CI" in control_ci
    assert "control_artifact=true" in control_ci
    assert "not_research_evidence=true" in control_ci


def test_product_ci_covers_lint_tests_local_e2e_boundary_and_build() -> None:
    workflow = _read(WORKFLOWS / "research-x-ci.yml")
    readme = _read(Path("README.codex.md"))

    for expected in (
        'python-version: "3.11"',
        "uv sync --locked --group dev",
        "uv run ruff check",
        "tools/make_project_context_diff_zip.py",
        "tools/audit_context_pointers.py",
        "review-package-gates:",
        "tests/test_pytest_lane_markers.py",
        "tests/test_review_context_zip.py",
        "tests/provider_gate/test_static_network_send_guard.py",
        "uv run pytest --cov=research_x --cov-report=term-missing --cov-report=xml",
        "tests/cli/test_memory_tool_json_db_restoration.py",
        "tests/tool_interface/test_db_backed_tool_restoration.py",
        "tests/tool_interface/test_memory_tool_contract_strictness.py",
        "tests/tool_interface/test_preview_cannot_be_citation.py",
        "tests/memory/test_retrieval_quality_eval.py",
        "uv run python -m research_x adoption audit",
        "uv run python -m mypy",
        "src/research_x/tool_interface/codex_bridge.py",
        "uv build",
    ):
        assert expected in workflow

    assert "persist-credentials: false" in workflow
    assert "python-version-file: pyproject.toml" not in workflow
    assert "provider_api" not in workflow.lower()
    assert "OPENAI_API_KEY" not in workflow
    assert "GEMINI_API_KEY" not in workflow
    readme_words = " ".join(readme.split())
    assert "boundary type check" in readme_words
    assert "Full-source type coverage is a ratchet target" in readme_words


def test_build_artifact_workflow_does_not_publish_or_deploy() -> None:
    workflow = _read(WORKFLOWS / "research-x-build-artifacts.yml")

    assert "name: Research X Build Artifacts" in workflow
    assert "uv build" in workflow
    assert "actions/upload-artifact@v7" in workflow
    assert "contents: write" not in workflow
    assert "id-token: write" not in workflow
    assert "pypi" not in workflow.lower()
    assert "deploy" not in workflow.lower()


def test_security_workflows_and_dependabot_cover_current_dependency_surfaces() -> None:
    dependency_review = _read(WORKFLOWS / "research-x-dependency-review.yml")
    codeql = _read(WORKFLOWS / "research-x-codeql.yml")
    dependabot = _read(DEPENDABOT)

    assert "actions/dependency-review-action@v5" in dependency_review
    assert "fail-on-severity: high" in dependency_review
    assert "comment-summary-in-pr: never" in dependency_review
    assert "pull-requests: write" not in dependency_review
    assert "github/codeql-action/init@v4" in codeql
    assert "github/codeql-action/analyze@v4" in codeql
    assert "security-events: write" in codeql
    for ecosystem in ("github-actions", "uv", "npm"):
        assert f"package-ecosystem: {ecosystem}" in dependabot
    assert "package-ecosystem: pip" not in dependabot


def test_trusted_pr_auto_merge_is_limited_to_same_repo_codex_and_dependabot_prs() -> None:
    workflow = _read(WORKFLOWS / "trusted-pr-auto-merge.yml")

    assert "name: Trusted PR Auto Merge" in workflow
    assert "pull_request_target:" in workflow
    assert "contents: write" in workflow
    assert "pull-requests: write" in workflow
    assert "github.event.pull_request.head.repo.full_name == github.repository" in workflow
    assert "startsWith(github.event.pull_request.head.ref, 'codex/')" in workflow
    assert "startsWith(github.event.pull_request.head.ref, 'dependabot/')" in workflow
    assert 'gh pr merge "$PR_URL" --auto --squash --delete-branch' in workflow
    assert "actions/checkout" not in workflow
