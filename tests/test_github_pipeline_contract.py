from __future__ import annotations

from pathlib import Path

WORKFLOWS = Path(".github/workflows")
DEPENDABOT = Path(".github/dependabot.yml")


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_workflow_surface_contains_only_product_and_security_lanes() -> None:
    assert {path.name for path in WORKFLOWS.glob("*.yml")} == {
        "research-x-build-artifacts.yml",
        "research-x-ci.yml",
        "research-x-codeql.yml",
        "research-x-dependency-review.yml",
        "research-x-provider-smoke.yml",
    }


def test_product_ci_covers_lint_tests_local_e2e_boundary_and_build() -> None:
    workflow = _read(WORKFLOWS / "research-x-ci.yml")

    for expected in (
        'python-version: "3.11"',
        "uv sync --locked --group dev",
        "uv run ruff check src/research_x tests",
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


def test_build_artifact_workflow_does_not_publish_or_deploy() -> None:
    workflow = _read(WORKFLOWS / "research-x-build-artifacts.yml")

    assert "name: Research X Build Artifacts" in workflow
    assert "uv build" in workflow
    assert "actions/upload-artifact@v7" in workflow
    assert "research_x_release_control_artifact_bundle" in workflow
    assert "contains_raw_provider_data" in workflow
    assert "contains_runs_directory" in workflow
    assert "cli-help/research-x-memory-api-budget.txt" in workflow
    assert "schema/schema-surfaces.json" in workflow
    assert "audits/memory-audit-local-empty-db.json" in workflow
    assert "contents: write" not in workflow
    assert "id-token: write" not in workflow
    assert "pypi" not in workflow.lower()
    assert "deploy" not in workflow.lower()
    assert "runs/" in workflow


def test_provider_smoke_workflow_is_manual_dry_run_guard_only() -> None:
    workflow = _read(WORKFLOWS / "research-x-provider-smoke.yml")

    assert "name: Research X Provider Smoke Guard" in workflow
    assert "workflow_dispatch:" in workflow
    assert "pull_request:" not in workflow
    assert "push:" not in workflow
    assert "provider_requests_sent" in workflow
    assert "provider_requests_sent\") != 0" in workflow
    assert "real_provider_http_performed" in workflow
    assert "secret_values_read\": False" in workflow
    assert "raw_provider_data_written\": False" in workflow
    assert "stop-before-provider-http" in workflow
    assert "The next step would require a real provider HTTP request" in workflow
    assert "secrets." not in workflow
    assert "OPENAI_API_KEY" not in workflow
    assert "GEMINI_API_KEY" not in workflow
    assert "curl " not in workflow
    assert "wget " not in workflow
    assert "provider-preflight.raw.json" in workflow
    assert "raw_path.unlink()" in workflow
    assert ".sqlite3" not in _provider_smoke_upload_paths(workflow)


def test_product_ci_keeps_provider_and_optional_lanes_out_of_default_path() -> None:
    workflow = _read(WORKFLOWS / "research-x-ci.yml")

    assert "RESEARCH_X_CI_PROVIDER_MODE: local-only" in workflow
    assert "run_optional_dependency_checks" in workflow
    assert (
        "github.event_name == 'workflow_dispatch' && inputs.run_optional_dependency_checks"
        in workflow
    )
    assert "optional-local-vector" in workflow
    assert "optional-local-media-ocr" in workflow
    assert "optional-browser-presentation" in workflow
    assert "tests/provider_gate/test_provider_execution_policy_blocks_provider_paths.py" in workflow
    assert "OPENAI_API_KEY" not in workflow
    assert "GEMINI_API_KEY" not in workflow
    assert "provider-smoke" not in workflow


def test_security_workflows_and_dependabot_cover_current_dependency_surfaces() -> None:
    dependency_review = _read(WORKFLOWS / "research-x-dependency-review.yml")
    codeql = _read(WORKFLOWS / "research-x-codeql.yml")
    dependabot = _read(DEPENDABOT)

    assert "actions/dependency-review-action@v5" in dependency_review
    assert "fail-on-severity: high" in dependency_review
    assert "fail-on-scopes: runtime" in dependency_review
    assert "license-check: true" in dependency_review
    assert "vulnerability-check: true" in dependency_review
    assert "comment-summary-in-pr: never" in dependency_review
    assert "pull-requests: write" not in dependency_review
    assert "github/codeql-action/init@v4" in codeql
    assert "github/codeql-action/analyze@v4" in codeql
    assert "security-events: write" in codeql
    for ecosystem in ("github-actions", "uv", "npm"):
        assert f"package-ecosystem: {ecosystem}" in dependabot
    assert "package-ecosystem: pip" not in dependabot


def _provider_smoke_upload_paths(workflow: str) -> str:
    marker = "Upload provider-smoke guard artifacts"
    _, _separator, tail = workflow.partition(marker)
    return tail
