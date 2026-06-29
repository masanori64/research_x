from __future__ import annotations

import importlib.util
import json
import sys
import zipfile
from pathlib import Path

SCRIPT_PATH = Path("tools/make_project_context_diff_zip.py")


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
    assert "attachments/audits/memory_audit.json" in names
    assert "attachments/audits/adoption_audit.json" in names
    assert "attachments/audits/pointer_map_audit.json" in names
    assert manifest["artifact_kind"] == module.REVIEW_ZIP_ARTIFACT_KIND
    assert "Provider execution surface source files are included" in context_text


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
        "command manifest commands[0].log_path missing from ZIP" in error
        for error in result.verification_errors
    )
    assert any(
        "command manifest commands[0].finished_at must be an ISO 8601 timestamp" in error
        for error in result.verification_errors
    )


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


def _write_required_review_artifacts(
    project_root: Path,
    artifacts: dict[str, str],
) -> dict[str, Path]:
    paths: dict[str, Path] = {}
    for artifact_id, zip_path in artifacts.items():
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
        return json.dumps(
            {
                "artifact_kind": "research_x_review_command_manifest",
                "schema_version": 1,
                "commands": [
                    {
                        "phase": "fixture",
                        "name": "pytest",
                        "command": "uv run pytest tests -q",
                        "exit_code": 0,
                        "log_path": "attachments/logs/pytest.log",
                        "started_at": "2026-06-27T00:00:00+00:00",
                        "finished_at": "2026-06-27T00:01:00+00:00",
                        "provider_requests_expected_zero": True,
                    },
                    {
                        "phase": "fixture",
                        "name": "ruff",
                        "command": "uv run ruff check src\\research_x tests",
                        "exit_code": 0,
                        "log_path": "attachments/logs/ruff.log",
                        "started_at": "2026-06-27T00:01:00+00:00",
                        "finished_at": "2026-06-27T00:01:10+00:00",
                        "provider_requests_expected_zero": True,
                    },
                ],
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ) + "\n"
    return f"fixture log for {artifact_id}\n"


def _write_file(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
