from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import zipfile
from pathlib import Path

SCRIPT_PATH = Path("tools/make_project_context_diff_zip.py")
COMMAND_MANIFEST_FIXTURE_LOG_PATHS = (
    "attachments/logs/pytest.log",
    "attachments/logs/ruff.log",
    "attachments/logs/git_diff_check.log",
    "attachments/logs/git_status_short.log",
    "attachments/logs/review_zip_verify.log",
    "attachments/audits/memory_audit.json",
    "attachments/audits/adoption_audit.json",
    "attachments/audits/pointer_map_audit.json",
)


def test_review_context_zip_required_files_cover_gpt_review_surfaces() -> None:
    module = _load_module()

    assert {
        "control/adoption_registry.toml",
        "tools/wbs_viewer/projects/research-x-work-state.json",
        "prompt_contracts/research_x_memory_search_v1.yaml",
        "src/research_x/memory/api_budget.py",
        "src/research_x/memory/answer.py",
        "src/research_x/memory/rerank.py",
        "src/research_x/memory/llm_context.py",
        "src/research_x/memory/embeddings.py",
        "src/research_x/memory/media_embeddings.py",
        "src/research_x/memory/external.py",
        "src/research_x/memory/reader.py",
        "src/research_x/memory/ocr.py",
        "src/research_x/memory/judge_relations.py",
        "src/research_x/bookmark_classifier.py",
        "src/research_x/cli.py",
        "src/research_x/tool_interface/memory_tool_contract.py",
    } <= set(module.REQUIRED_PROJECT_CONTEXT_FILES)


def test_build_review_context_zip_includes_required_context_and_manifest(
    tmp_path: Path,
) -> None:
    module = _load_module()
    project_root = tmp_path / "project"
    _write_required_project_files(project_root, module.REQUIRED_PROJECT_CONTEXT_FILES)
    _write_file(project_root / "src/research_x/memory/audit.py", "audit = True\n")
    review_artifacts = _write_required_review_artifacts(
        project_root,
        module.REQUIRED_REVIEW_ARTIFACTS,
    )
    zip_path = tmp_path / "review.zip"

    result = module.build_review_context_zip(
        project_root,
        zip_path,
        changed_files=("src/research_x/memory/audit.py",),
        review_artifacts=review_artifacts,
        verify_manifest=True,
    )

    assert result.verification_errors == ()
    assert zip_path.exists()
    assert module.verify_review_zip(zip_path) == ()
    with zipfile.ZipFile(zip_path) as archive:
        names = set(archive.namelist())
        manifest = json.loads(archive.read("attachment_manifest.json").decode("utf-8"))
        context_text = archive.read("context.md").decode("utf-8")
        provenance = json.loads(
            archive.read("attachments/logs/git_provenance.json").decode("utf-8")
        )
    assert "context.md" in names
    assert "attachment_manifest.md" in names
    assert "attachment_manifest.json" in names
    assert (
        "attachments/project_context/tools/wbs_viewer/projects/"
        "research-x-work-state.json"
    ) in names
    assert (
        "attachments/project_context/prompt_contracts/"
        "research_x_memory_search_v1.yaml"
    ) in names
    assert "attachments/project_context/src/research_x/memory/api_budget.py" in names
    assert "attachments/project_context/src/research_x/memory/answer.py" in names
    assert "attachments/project_context/src/research_x/memory/rerank.py" in names
    assert "attachments/project_context/src/research_x/memory/llm_context.py" in names
    assert "attachments/project_context/src/research_x/memory/embeddings.py" in names
    assert "attachments/project_context/src/research_x/memory/media_embeddings.py" in names
    assert "attachments/project_context/src/research_x/memory/external.py" in names
    assert "attachments/project_context/src/research_x/memory/reader.py" in names
    assert "attachments/project_context/src/research_x/memory/ocr.py" in names
    assert "attachments/project_context/src/research_x/memory/judge_relations.py" in names
    assert "attachments/project_context/src/research_x/bookmark_classifier.py" in names
    assert "attachments/project_context/src/research_x/cli.py" in names
    assert "attachments/project_context/control/adoption_registry.toml" in names
    assert "attachments/changed_files/src/research_x/memory/audit.py" in names
    assert "attachments/logs/pytest.log" in names
    assert "attachments/logs/ruff.log" in names
    assert "attachments/logs/git_status_short.log" in names
    assert "attachments/logs/command_manifest.json" in names
    assert "attachments/logs/git_provenance.json" in names
    assert "attachments/audits/memory_audit.json" in names
    assert "attachments/audits/adoption_audit.json" in names
    assert "attachments/audits/pointer_map_audit.json" in names
    assert manifest["artifact_kind"] == module.REVIEW_ZIP_ARTIFACT_KIND
    assert manifest["head_ref"] == "HEAD"
    assert manifest["current_branch"] == provenance["current_branch"]
    assert manifest["detached_head"] == provenance["detached_head"]
    assert provenance["artifact_kind"] == module.GIT_PROVENANCE_ARTIFACT_KIND
    assert provenance["git_available"] is True
    assert provenance["current_branch"] == "fixture-main"
    assert provenance["head_branch"] == "fixture-main"
    assert provenance["detached_head"] is False
    assert provenance["branch_checked_by"]
    assert len(provenance["head_commit"]) == 40
    assert provenance["not_evidence"] is True
    assert "head_commit:" in context_text
    assert "branch: fixture-main" in context_text
    assert "detached_head: False" in context_text
    assert "Provider execution surface source files are included" in context_text


def test_review_context_zip_can_require_expected_branch(tmp_path: Path) -> None:
    module = _load_module()
    project_root = tmp_path / "project"
    _write_required_project_files(project_root, module.REQUIRED_PROJECT_CONTEXT_FILES)
    review_artifacts = _write_required_review_artifacts(
        project_root,
        module.REQUIRED_REVIEW_ARTIFACTS,
    )
    zip_path = tmp_path / "review.zip"

    result = module.build_review_context_zip(
        project_root,
        zip_path,
        review_artifacts=review_artifacts,
        expected_branch="fixture-main",
        verify_manifest=True,
    )

    assert result.verification_errors == ()
    with zipfile.ZipFile(zip_path) as archive:
        context_text = archive.read("context.md").decode("utf-8")
        provenance = json.loads(
            archive.read("attachments/logs/git_provenance.json").decode("utf-8")
        )
    assert provenance["expected_branch"] == "fixture-main"
    assert provenance["current_branch"] == "fixture-main"
    assert "expected_branch: fixture-main" in context_text

    mismatch_zip = tmp_path / "review-mismatch.zip"
    mismatch = module.build_review_context_zip(
        project_root,
        mismatch_zip,
        review_artifacts=review_artifacts,
        expected_branch="wrong-branch",
        verify_manifest=True,
    )

    assert any(
        "git provenance current_branch must match expected_branch" in error
        for error in mismatch.verification_errors
    )


def test_review_context_zip_can_include_optional_github_actions_status(
    tmp_path: Path,
) -> None:
    module = _load_module()
    project_root = tmp_path / "project"
    _write_required_project_files(project_root, module.REQUIRED_PROJECT_CONTEXT_FILES)
    review_artifacts = _write_required_review_artifacts(
        project_root,
        module.REQUIRED_REVIEW_ARTIFACTS,
    )
    review_artifacts["github_actions_status"] = project_root / "review_inputs" / (
        "github_actions_status.json"
    )
    review_artifacts["github_actions_status"].write_text(
        json.dumps(
            {
                "artifact_kind": module.GITHUB_ACTIONS_STATUS_ARTIFACT_KIND,
                "schema_version": module.GITHUB_ACTIONS_STATUS_SCHEMA_VERSION,
                "source": "github_actions_api",
                "status": "success",
                "workflow_runs": [
                    {
                        "workflow": "Research X Product CI",
                        "conclusion": "success",
                    }
                ],
                "not_answer_support": True,
                "not_citation": True,
                "not_evidence": True,
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    zip_path = tmp_path / "review.zip"

    result = module.build_review_context_zip(
        project_root,
        zip_path,
        review_artifacts=review_artifacts,
        verify_manifest=True,
    )

    assert result.verification_errors == ()
    with zipfile.ZipFile(zip_path) as archive:
        names = set(archive.namelist())
        manifest = json.loads(archive.read("attachment_manifest.json").decode("utf-8"))
    assert "attachments/logs/github_actions_status.json" in names
    assert (
        manifest["optional_review_artifacts"]["github_actions_status"]
        == "attachments/logs/github_actions_status.json"
    )
    github_status_entries = [
        entry
        for entry in manifest["files"]
        if entry.get("artifact_id") == "github_actions_status"
    ]
    assert github_status_entries == [
        {
            "artifact_id": "github_actions_status",
            "optional": True,
            "required": False,
            "role": "review_artifact",
            "source_path": "review_inputs/github_actions_status.json",
            "zip_path": "attachments/logs/github_actions_status.json",
        }
    ]


def test_review_context_zip_rejects_github_actions_status_as_evidence(
    tmp_path: Path,
) -> None:
    module = _load_module()
    project_root = tmp_path / "project"
    _write_required_project_files(project_root, module.REQUIRED_PROJECT_CONTEXT_FILES)
    review_artifacts = _write_required_review_artifacts(
        project_root,
        module.REQUIRED_REVIEW_ARTIFACTS,
    )
    review_artifacts["github_actions_status"] = project_root / "review_inputs" / (
        "github_actions_status.json"
    )
    review_artifacts["github_actions_status"].write_text(
        json.dumps(
            {
                "artifact_kind": module.GITHUB_ACTIONS_STATUS_ARTIFACT_KIND,
                "schema_version": module.GITHUB_ACTIONS_STATUS_SCHEMA_VERSION,
                "source": "github_actions_api",
                "status": "success",
                "not_answer_support": False,
                "not_citation": False,
                "not_evidence": False,
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    zip_path = tmp_path / "review.zip"

    result = module.build_review_context_zip(
        project_root,
        zip_path,
        review_artifacts=review_artifacts,
        verify_manifest=True,
    )

    assert any(
        "github actions status not_evidence must be true" in error
        for error in result.verification_errors
    )
    assert any(
        "github actions status not_citation must be true" in error
        for error in result.verification_errors
    )
    assert any(
        "github actions status not_answer_support must be true" in error
        for error in result.verification_errors
    )


def test_review_context_zip_can_include_optional_doc_budget_audit(
    tmp_path: Path,
) -> None:
    module = _load_module()
    project_root = tmp_path / "project"
    _write_required_project_files(project_root, module.REQUIRED_PROJECT_CONTEXT_FILES)
    review_artifacts = _write_required_review_artifacts(
        project_root,
        module.REQUIRED_REVIEW_ARTIFACTS,
    )
    review_artifacts["doc_budget_audit"] = project_root / "review_inputs" / (
        "doc_budget_audit.json"
    )
    review_artifacts["doc_budget_audit"].write_text(
        json.dumps(_valid_doc_budget_audit_payload(module), indent=2, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )
    zip_path = tmp_path / "review.zip"

    result = module.build_review_context_zip(
        project_root,
        zip_path,
        review_artifacts=review_artifacts,
        verify_manifest=True,
    )

    assert result.verification_errors == ()
    with zipfile.ZipFile(zip_path) as archive:
        names = set(archive.namelist())
        manifest = json.loads(archive.read("attachment_manifest.json").decode("utf-8"))
    assert "attachments/audits/doc_budget_audit.json" in names
    assert (
        manifest["optional_review_artifacts"]["doc_budget_audit"]
        == "attachments/audits/doc_budget_audit.json"
    )
    doc_budget_entries = [
        entry
        for entry in manifest["files"]
        if entry.get("artifact_id") == "doc_budget_audit"
    ]
    assert doc_budget_entries == [
        {
            "artifact_id": "doc_budget_audit",
            "optional": True,
            "required": False,
            "role": "review_artifact",
            "source_path": "review_inputs/doc_budget_audit.json",
            "zip_path": "attachments/audits/doc_budget_audit.json",
        }
    ]


def test_review_context_zip_rejects_doc_budget_audit_as_evidence_or_violating(
    tmp_path: Path,
) -> None:
    module = _load_module()
    project_root = tmp_path / "project"
    _write_required_project_files(project_root, module.REQUIRED_PROJECT_CONTEXT_FILES)
    review_artifacts = _write_required_review_artifacts(
        project_root,
        module.REQUIRED_REVIEW_ARTIFACTS,
    )
    payload = _valid_doc_budget_audit_payload(module)
    payload["not_evidence"] = False
    payload["not_citation"] = False
    payload["not_answer_support"] = False
    payload["documents"][0]["missing_required_sections"] = ["Evidence Invariant"]
    payload["wbs"]["semantic_violation_count"] = 1
    review_artifacts["doc_budget_audit"] = project_root / "review_inputs" / (
        "doc_budget_audit.json"
    )
    review_artifacts["doc_budget_audit"].write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    zip_path = tmp_path / "review.zip"

    result = module.build_review_context_zip(
        project_root,
        zip_path,
        review_artifacts=review_artifacts,
        verify_manifest=True,
    )

    assert any(
        "doc budget audit not_evidence must be true" in error
        for error in result.verification_errors
    )
    assert any(
        "doc budget audit not_citation must be true" in error
        for error in result.verification_errors
    )
    assert any(
        "doc budget audit not_answer_support must be true" in error
        for error in result.verification_errors
    )
    assert any(
        "doc budget audit PROJECT.md missing_required_sections must be empty" in error
        for error in result.verification_errors
    )
    assert any(
        "doc budget audit wbs semantic_violation_count must be 0" in error
        for error in result.verification_errors
    )


def test_verify_review_zip_detects_manifest_missing_required_file(
    tmp_path: Path,
) -> None:
    module = _load_module()
    zip_path = tmp_path / "broken.zip"
    manifest = {
        "artifact_kind": module.REVIEW_ZIP_ARTIFACT_KIND,
        "schema_version": module.REVIEW_ZIP_SCHEMA_VERSION,
        "files": [
            {
                "role": "project_context",
                "source_path": "README.codex.md",
                "zip_path": "attachments/project_context/README.codex.md",
                "required": True,
            }
        ],
    }
    with zipfile.ZipFile(zip_path, "w") as archive:
        archive.writestr("context.md", "# context\n")
        archive.writestr("attachment_manifest.md", "# manifest\n")
        archive.writestr("attachment_manifest.json", json.dumps(manifest))

    errors = module.verify_review_zip(zip_path)

    assert any(
        "required manifest file missing from ZIP: "
        "attachments/project_context/README.codex.md" in error
        for error in errors
    )
    assert any(
        "required project context source missing from manifest: "
        "src/research_x/memory/api_budget.py" in error
        for error in errors
    )
    assert any(
        "required review artifact missing from manifest: "
        "attachments/logs/pytest.log" in error
        for error in errors
    )


def test_verify_review_zip_detects_missing_required_review_artifact(
    tmp_path: Path,
) -> None:
    module = _load_module()
    project_root = tmp_path / "project"
    _write_required_project_files(project_root, module.REQUIRED_PROJECT_CONTEXT_FILES)
    zip_path = tmp_path / "review.zip"

    result = module.build_review_context_zip(
        project_root,
        zip_path,
        review_artifacts={},
        verify_manifest=True,
    )

    assert any(
        "required manifest file missing from ZIP: attachments/logs/pytest.log" in error
        for error in result.verification_errors
    )


def test_verify_review_zip_allows_empty_success_git_logs(
    tmp_path: Path,
) -> None:
    module = _load_module()
    project_root = tmp_path / "project"
    _write_required_project_files(project_root, module.REQUIRED_PROJECT_CONTEXT_FILES)
    review_artifacts = _write_required_review_artifacts(
        project_root,
        module.REQUIRED_REVIEW_ARTIFACTS,
    )
    review_artifacts["git_diff_check_log"].write_text("", encoding="utf-8")
    review_artifacts["git_status_log"].write_text("", encoding="utf-8")
    zip_path = tmp_path / "review.zip"

    result = module.build_review_context_zip(
        project_root,
        zip_path,
        review_artifacts=review_artifacts,
        verify_manifest=True,
    )

    assert result.verification_errors == ()


def test_verify_review_zip_rejects_failed_pointer_map_audit(
    tmp_path: Path,
) -> None:
    module = _load_module()
    project_root = tmp_path / "project"
    _write_required_project_files(project_root, module.REQUIRED_PROJECT_CONTEXT_FILES)
    review_artifacts = _write_required_review_artifacts(
        project_root,
        module.REQUIRED_REVIEW_ARTIFACTS,
    )
    review_artifacts["pointer_map_audit"].write_text(
        json.dumps(
            {
                "source_kind": "pointer_map",
                "status": "failed",
                "entry_count": 1,
                "usable_count": 0,
                "failed_count": 1,
                "invalid_entry_count": 0,
                "results": [
                    {
                        "pointer_id": "stale",
                        "status": "stale_pointer",
                        "issues": ["stale_hash"],
                    }
                ],
                "skipped_reason": None,
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    zip_path = tmp_path / "review.zip"

    result = module.build_review_context_zip(
        project_root,
        zip_path,
        review_artifacts=review_artifacts,
        verify_manifest=True,
    )

    assert any(
        "pointer map audit status must be passed or skipped_external_pointer_map_absent"
        in error
        for error in result.verification_errors
    )


def test_verify_review_zip_rejects_inconsistent_pointer_map_passed_audit(
    tmp_path: Path,
) -> None:
    module = _load_module()
    project_root = tmp_path / "project"
    _write_required_project_files(project_root, module.REQUIRED_PROJECT_CONTEXT_FILES)
    review_artifacts = _write_required_review_artifacts(
        project_root,
        module.REQUIRED_REVIEW_ARTIFACTS,
    )
    review_artifacts["pointer_map_audit"].write_text(
        json.dumps(
            {
                "source_kind": "pointer_map",
                "status": "passed",
                "entry_count": 1,
                "usable_count": 1,
                "failed_count": 0,
                "invalid_entry_count": 0,
                "results": [
                    {
                        "pointer_id": "stale",
                        "status": "stale_pointer",
                        "issues": ["stale_hash"],
                        "not_evidence": False,
                        "sha256_match": False,
                    }
                ],
                "skipped_reason": None,
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    zip_path = tmp_path / "review.zip"

    result = module.build_review_context_zip(
        project_root,
        zip_path,
        review_artifacts=review_artifacts,
        verify_manifest=True,
    )

    assert any(
        "pointer map audit results[0].status must be usable_pointer" in error
        for error in result.verification_errors
    )
    assert any(
        "pointer map audit results[0].not_evidence must be true" in error
        for error in result.verification_errors
    )
    assert any(
        "pointer map audit results[0].sha256_match must be true when present" in error
        for error in result.verification_errors
    )


def test_verify_review_zip_rejects_memory_audit_not_local_ready(
    tmp_path: Path,
) -> None:
    module = _load_module()
    project_root = tmp_path / "project"
    _write_required_project_files(project_root, module.REQUIRED_PROJECT_CONTEXT_FILES)
    review_artifacts = _write_required_review_artifacts(
        project_root,
        module.REQUIRED_REVIEW_ARTIFACTS,
    )
    review_artifacts["memory_audit"].write_text(
        json.dumps(
            {
                "claim_citation_issues": {},
                "freshness_lineage_issues": {},
                "readiness": {
                    "local_no_provider_ready": False,
                    "blocking_issue_count": 1,
                },
                "structured_warnings": [],
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    zip_path = tmp_path / "review.zip"

    result = module.build_review_context_zip(
        project_root,
        zip_path,
        review_artifacts=review_artifacts,
        verify_manifest=True,
    )

    assert any(
        "memory audit readiness.local_no_provider_ready must be true" in error
        for error in result.verification_errors
    )
    assert any(
        "memory audit readiness.blocking_issue_count must be 0" in error
        for error in result.verification_errors
    )


def test_verify_review_zip_rejects_failed_adoption_audit(
    tmp_path: Path,
) -> None:
    module = _load_module()
    project_root = tmp_path / "project"
    _write_required_project_files(project_root, module.REQUIRED_PROJECT_CONTEXT_FILES)
    review_artifacts = _write_required_review_artifacts(
        project_root,
        module.REQUIRED_REVIEW_ARTIFACTS,
    )
    review_artifacts["adoption_audit"].write_text(
        json.dumps(
            {
                "candidates": [],
                "errors": ["missing active artifact"],
                "status": "failed",
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    zip_path = tmp_path / "review.zip"

    result = module.build_review_context_zip(
        project_root,
        zip_path,
        review_artifacts=review_artifacts,
        verify_manifest=True,
    )

    assert any("adoption audit status must be ok" in error for error in result.verification_errors)
    assert any(
        "adoption audit errors must be empty" in error for error in result.verification_errors
    )


def test_verify_review_zip_rejects_failed_command_manifest(
    tmp_path: Path,
) -> None:
    module = _load_module()
    project_root = tmp_path / "project"
    _write_required_project_files(project_root, module.REQUIRED_PROJECT_CONTEXT_FILES)
    review_artifacts = _write_required_review_artifacts(
        project_root,
        module.REQUIRED_REVIEW_ARTIFACTS,
    )
    review_artifacts["command_manifest"].write_text(
        json.dumps(
            {
                "artifact_kind": module.COMMAND_MANIFEST_ARTIFACT_KIND,
                "schema_version": module.COMMAND_MANIFEST_SCHEMA_VERSION,
                "commands": [
                    {
                        "phase": "fixture",
                        "name": "pytest",
                        "command": "uv run pytest tests -q",
                        "exit_code": 1,
                        "log_path": "attachments/logs/missing.log",
                        "started_at": "2026-06-27T00:00:00+00:00",
                        "finished_at": "not-a-timestamp",
                        "provider_requests_expected_zero": False,
                        "provider_requests_observed": 1,
                        "provider_transport_sends_observed": 1,
                        "api_budget_event_delta": {
                            "provider_requests_observed": 1,
                            "provider_transport_sends_observed": 1,
                            "not_evidence": False,
                        },
                    }
                ],
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    zip_path = tmp_path / "review.zip"

    result = module.build_review_context_zip(
        project_root,
        zip_path,
        review_artifacts=review_artifacts,
        verify_manifest=True,
    )

    assert any(
        "command manifest commands[0].exit_code must be 0" in error
        for error in result.verification_errors
    )
    assert any(
        "command manifest commands[0].provider_requests_expected_zero must be true" in error
        for error in result.verification_errors
    )
    assert any(
        "command manifest commands[0].provider_requests_observed must be 0" in error
        for error in result.verification_errors
    )
    assert any(
        "command manifest commands[0].provider_transport_sends_observed must be 0" in error
        for error in result.verification_errors
    )
    assert any(
        "command manifest commands[0].api_budget_event_delta.provider_requests_observed must be 0"
        in error
        for error in result.verification_errors
    )
    assert any(
        "command manifest commands[0].api_budget_event_delta.not_evidence must be true" in error
        for error in result.verification_errors
    )
    assert any(
        "command manifest commands[0].log_path missing from ZIP" in error
        for error in result.verification_errors
    )
    assert any(
        "command manifest commands[0].finished_at must be an ISO 8601 timestamp" in error
        for error in result.verification_errors
    )


def test_verify_review_zip_rejects_command_manifest_missing_required_artifact_log(
    tmp_path: Path,
) -> None:
    module = _load_module()
    project_root = tmp_path / "project"
    _write_required_project_files(project_root, module.REQUIRED_PROJECT_CONTEXT_FILES)
    review_artifacts = _write_required_review_artifacts(
        project_root,
        module.REQUIRED_REVIEW_ARTIFACTS,
    )
    review_artifacts["command_manifest"].write_text(
        json.dumps(
            {
                "artifact_kind": module.COMMAND_MANIFEST_ARTIFACT_KIND,
                "schema_version": module.COMMAND_MANIFEST_SCHEMA_VERSION,
                "commands": [
                    _command_manifest_entry(
                        name="pytest",
                        command="uv run pytest tests -q",
                        log_path="attachments/logs/pytest.log",
                        index=0,
                    )
                ],
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    zip_path = tmp_path / "review.zip"

    result = module.build_review_context_zip(
        project_root,
        zip_path,
        review_artifacts=review_artifacts,
        verify_manifest=True,
    )

    assert any(
        "command manifest missing required artifact log_path: attachments/logs/ruff.log"
        in error
        for error in result.verification_errors
    )


def test_verify_review_zip_rejects_invalid_git_provenance(
    tmp_path: Path,
) -> None:
    module = _load_module()
    project_root = tmp_path / "project"
    _write_required_project_files(project_root, module.REQUIRED_PROJECT_CONTEXT_FILES)
    review_artifacts = _write_required_review_artifacts(
        project_root,
        module.REQUIRED_REVIEW_ARTIFACTS,
    )
    good_zip = tmp_path / "good.zip"
    bad_zip = tmp_path / "bad.zip"
    result = module.build_review_context_zip(
        project_root,
        good_zip,
        review_artifacts=review_artifacts,
        verify_manifest=True,
    )
    assert result.verification_errors == ()
    with zipfile.ZipFile(good_zip) as source, zipfile.ZipFile(bad_zip, "w") as target:
        for info in source.infolist():
            if info.filename == "attachments/logs/git_provenance.json":
                target.writestr(
                    info.filename,
                    json.dumps(
                        {
                            "artifact_kind": module.GIT_PROVENANCE_ARTIFACT_KIND,
                            "schema_version": module.GIT_PROVENANCE_SCHEMA_VERSION,
                            "git_available": False,
                            "head_commit": "not-a-hash",
                            "not_evidence": False,
                            "working_tree": {
                                "is_dirty": True,
                                "policy": "dirty_allowed_for_review_package",
                                "status_short": [],
                            },
                            "diff": {
                                "base_to_head_name_status": [],
                                "working_tree_name_status": [],
                                "cached_name_status": [],
                            },
                        }
                    ),
                )
            else:
                target.writestr(info, source.read(info.filename))

    errors = module.verify_review_zip(bad_zip)

    assert any("git provenance git_available must be true" in error for error in errors)
    assert any("git provenance not_evidence must be true" in error for error in errors)
    assert any("git provenance head_commit must be a 40-character" in error for error in errors)
    assert any("git provenance detached_head must be boolean" in error for error in errors)
    assert any("dirty working tree requires dirty_allowed_reason" in error for error in errors)


def _load_module():
    spec = importlib.util.spec_from_file_location("make_project_context_diff_zip", SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _write_required_project_files(project_root: Path, paths: tuple[str, ...]) -> None:
    for path in paths:
        _write_file(project_root / path, f"fixture for {path}\n")
    _init_git_repo(project_root)


def _write_required_review_artifacts(
    project_root: Path,
    artifacts: dict[str, str],
) -> dict[str, Path]:
    paths: dict[str, Path] = {}
    for artifact_id, zip_path in artifacts.items():
        if artifact_id == "git_provenance":
            continue
        source = project_root / "review_inputs" / zip_path.replace("/", "_")
        _write_file(source, _review_artifact_fixture(artifact_id))
        paths[artifact_id] = source
    return paths


def _review_artifact_fixture(artifact_id: str) -> str:
    if artifact_id == "memory_audit":
        return json.dumps(
            {
                "claim_citation_issues": {},
                "freshness_lineage_issues": {},
                "readiness": {
                    "local_no_provider_ready": True,
                    "blocking_issue_count": 0,
                },
                "structured_warnings": [],
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ) + "\n"
    if artifact_id == "adoption_audit":
        return json.dumps(
            {
                "candidates": [{"name": "fixture", "status": "implemented"}],
                "errors": [],
                "status": "ok",
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ) + "\n"
    if artifact_id == "pointer_map_audit":
        return json.dumps(
            {
                "source_kind": "pointer_map",
                "status": "passed",
                "entry_count": 1,
                "usable_count": 1,
                "failed_count": 0,
                "invalid_entry_count": 0,
                "results": [
                    {
                        "byte_count_match": True,
                        "char_count_match": True,
                        "not_evidence": True,
                        "pointer_id": "fixture-pointer",
                        "sha256_match": True,
                        "status": "usable_pointer",
                        "issues": [],
                    }
                ],
                "skipped_reason": None,
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ) + "\n"
    if artifact_id == "command_manifest":
        commands = [
            _command_manifest_entry(
                name=Path(log_path).stem,
                command=f"fixture command for {log_path}",
                log_path=log_path,
                index=index,
            )
            for index, log_path in enumerate(COMMAND_MANIFEST_FIXTURE_LOG_PATHS)
        ]
        return json.dumps(
            {
                "artifact_kind": "research_x_review_command_manifest",
                "schema_version": 1,
                "commands": commands,
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ) + "\n"
    return f"fixture log for {artifact_id}\n"


def _valid_doc_budget_audit_payload(module) -> dict[str, object]:
    empty_document = {
        "path": "PROJECT.md",
        "role": "short_project_tracker",
        "exists": True,
        "line_count": 80,
        "target_lines": 100,
        "hard_ceiling_lines": 120,
        "over_target": False,
        "budget_review_marker_present": False,
        "target_review_marker_missing": False,
        "hard_ceiling_violations": [],
        "missing_required_sections": [],
        "forbidden_sections_present": [],
        "missing_required_terms": [],
        "banned_fragments_present": [],
        "ordered_fragment_violations": [],
    }
    return {
        "artifact_kind": module.DOC_BUDGET_AUDIT_ARTIFACT_KIND,
        "schema_version": module.DOC_BUDGET_AUDIT_SCHEMA_VERSION,
        "not_answer_support": True,
        "not_citation": True,
        "not_evidence": True,
        "documents": [empty_document],
        "wbs": {
            "not_evidence_violation_count": 0,
            "answer_support_allowed_violation_count": 0,
            "semantic_violation_count": 0,
        },
    }


def _write_file(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _zero_api_budget_event_delta() -> dict[str, object]:
    return {
        "artifact_kind": "research_x_api_budget_event_delta",
        "schema_version": 1,
        "provider_requests_observed": 0,
        "provider_requests_blocked_by_freeze": 0,
        "provider_transport_sends_observed": 0,
        "counts": {
            "provider_requests_observed": 0,
            "provider_transport_sends_observed": 0,
        },
        "not_evidence": True,
    }


def _command_manifest_entry(
    *,
    name: str,
    command: str,
    log_path: str,
    index: int,
) -> dict[str, object]:
    return {
        "phase": "fixture",
        "name": name,
        "command": command,
        "exit_code": 0,
        "log_path": log_path,
        "started_at": f"2026-06-27T00:{index:02d}:00+00:00",
        "finished_at": f"2026-06-27T00:{index:02d}:30+00:00",
        "provider_requests_expected_zero": True,
        "provider_requests_observed": 0,
        "provider_transport_sends_observed": 0,
        "api_budget_event_delta": _zero_api_budget_event_delta(),
    }


def _init_git_repo(project_root: Path) -> None:
    if (project_root / ".git").exists():
        return
    subprocess.run(["git", "init"], cwd=project_root, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "fixture@example.test"],
        cwd=project_root,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Fixture"],
        cwd=project_root,
        check=True,
        capture_output=True,
    )
    subprocess.run(["git", "add", "."], cwd=project_root, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "fixture"],
        cwd=project_root,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "checkout", "-b", "fixture-main"],
        cwd=project_root,
        check=True,
        capture_output=True,
    )
