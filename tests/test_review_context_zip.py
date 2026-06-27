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
    assert "attachments/project_context/src/research_x/cli.py" in names
    assert "attachments/project_context/control/adoption_registry.toml" in names
    assert "attachments/changed_files/src/research_x/memory/audit.py" in names
    assert "attachments/logs/pytest.log" in names
    assert "attachments/logs/ruff.log" in names
    assert "attachments/logs/git_status_short.log" in names
    assert "attachments/audits/memory_audit.json" in names
    assert "attachments/audits/adoption_audit.json" in names
    assert "attachments/audits/pointer_map_audit.json" in names
    assert manifest["artifact_kind"] == module.REVIEW_ZIP_ARTIFACT_KIND


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
                "readiness": {"local_no_provider_ready": True},
                "structured_warnings": [],
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ) + "\n"
    if artifact_id == "adoption_audit":
        return json.dumps(
            {
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
                        "pointer_id": "fixture-pointer",
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
    return f"fixture log for {artifact_id}\n"


def _write_file(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
