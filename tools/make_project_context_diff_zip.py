from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import tempfile
import zipfile
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REVIEW_ZIP_SCHEMA_VERSION = 1
REVIEW_ZIP_ARTIFACT_KIND = "research_x_gpt_review_context_zip"
COMMAND_MANIFEST_SCHEMA_VERSION = 1
COMMAND_MANIFEST_ARTIFACT_KIND = "research_x_review_command_manifest"
GIT_PROVENANCE_SCHEMA_VERSION = 1
GIT_PROVENANCE_ARTIFACT_KIND = "research_x_review_git_provenance"
API_BUDGET_EVENT_DELTA_SCHEMA_VERSION = 1
API_BUDGET_EVENT_DELTA_ARTIFACT_KIND = "research_x_api_budget_event_delta"

REQUIRED_PROJECT_CONTEXT_FILES = (
    "README.codex.md",
    "PROJECT.md",
    "control/adoption_registry.toml",
    "docs/memory-pipeline-v2.md",
    "docs/pipeline.md",
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
)

REQUIRED_REVIEW_ARTIFACTS = {
    "pytest_log": "attachments/logs/pytest.log",
    "ruff_log": "attachments/logs/ruff.log",
    "git_diff_check_log": "attachments/logs/git_diff_check.log",
    "git_status_log": "attachments/logs/git_status_short.log",
    "review_zip_verify_log": "attachments/logs/review_zip_verify.log",
    "command_manifest": "attachments/logs/command_manifest.json",
    "git_provenance": "attachments/logs/git_provenance.json",
    "memory_audit": "attachments/audits/memory_audit.json",
    "adoption_audit": "attachments/audits/adoption_audit.json",
    "pointer_map_audit": "attachments/audits/pointer_map_audit.json",
}
GENERATED_REVIEW_ARTIFACTS = frozenset({"git_provenance"})
ALLOW_EMPTY_REVIEW_ARTIFACTS = frozenset(
    {
        "git_diff_check_log",
        "git_status_log",
    }
)

CORE_MANIFEST_FILES = (
    "context.md",
    "attachment_manifest.md",
    "attachment_manifest.json",
)


@dataclass(frozen=True)
class ReviewZipBuildResult:
    zip_path: str
    manifest_path: str
    file_count: int
    verification_errors: tuple[str, ...]


def build_review_context_zip(
    project_root: str | Path,
    output_zip: str | Path,
    *,
    base_ref: str | None = None,
    head_ref: str = "HEAD",
    changed_files: tuple[str, ...] | None = None,
    extra_files: tuple[str, ...] = (),
    review_artifacts: dict[str, str | Path] | None = None,
    verify_manifest: bool = True,
) -> ReviewZipBuildResult:
    root = Path(project_root).resolve()
    output = Path(output_zip).resolve()
    resolved_changed_files = changed_files
    if resolved_changed_files is None:
        resolved_changed_files = (
            _git_changed_files(root, base_ref=base_ref, head_ref=head_ref)
            if base_ref
            else ()
        )
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        output.unlink()
    with tempfile.TemporaryDirectory(prefix="research_x_review_zip_") as temp_dir:
        staging = Path(temp_dir) / output.stem
        staging.mkdir(parents=True)
        files: list[dict[str, Any]] = []
        git_provenance = _git_provenance_payload(
            root,
            base_ref=base_ref,
            head_ref=head_ref,
            changed_files=tuple(dict.fromkeys(resolved_changed_files)),
        )
        _write_context(
            staging,
            root,
            base_ref=base_ref,
            head_ref=head_ref,
            git_provenance=git_provenance,
        )
        _write_manifest_markdown(staging)
        for zip_path in ("context.md", "attachment_manifest.md"):
            files.append(
                {
                    "role": "core",
                    "source_path": None,
                    "zip_path": zip_path,
                    "required": True,
                }
            )
        _copy_project_files(
            root,
            staging,
            files,
            REQUIRED_PROJECT_CONTEXT_FILES,
            role="project_context",
            required=True,
        )
        _copy_project_files(
            root,
            staging,
            files,
            tuple(dict.fromkeys(resolved_changed_files)),
            role="changed_file",
            required=False,
        )
        _copy_project_files(
            root,
            staging,
            files,
            tuple(dict.fromkeys(extra_files)),
            role="extra_context",
            required=False,
        )
        _copy_review_artifacts(
            root,
            staging,
            files,
            review_artifacts or {},
        )
        _write_git_provenance_artifact(staging, files, git_provenance)
        _write_git_artifacts(
            root,
            staging,
            files,
            base_ref=base_ref,
            head_ref=head_ref,
        )
        manifest = _manifest_payload(
            project_root=root,
            base_ref=base_ref,
            head_ref=head_ref,
            files=files,
        )
        manifest_path = staging / "attachment_manifest.json"
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        files.append(
            {
                "role": "core",
                "source_path": None,
                "zip_path": "attachment_manifest.json",
                "required": True,
            }
        )
        _rewrite_manifest_with_self_entry(manifest_path, manifest, files)
        _zip_directory(staging, output)
    errors = verify_review_zip(output) if verify_manifest else ()
    return ReviewZipBuildResult(
        zip_path=str(output),
        manifest_path="attachment_manifest.json",
        file_count=len(files),
        verification_errors=tuple(errors),
    )


def verify_review_zip(zip_path: str | Path) -> tuple[str, ...]:
    path = Path(zip_path)
    errors: list[str] = []
    if not path.exists():
        return (f"zip missing: {path}",)
    required_artifact_payloads: dict[str, bytes] = {}
    with zipfile.ZipFile(path) as archive:
        names = {name.replace("\\", "/") for name in archive.namelist()}
        if "attachment_manifest.json" not in names:
            return ("attachment_manifest.json missing from review ZIP",)
        try:
            manifest = json.loads(archive.read("attachment_manifest.json").decode("utf-8"))
        except (KeyError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            return (f"attachment_manifest.json unreadable: {exc}",)
        for artifact_id, zip_member in REQUIRED_REVIEW_ARTIFACTS.items():
            if zip_member in names:
                required_artifact_payloads[artifact_id] = archive.read(zip_member)
    if manifest.get("artifact_kind") != REVIEW_ZIP_ARTIFACT_KIND:
        errors.append(
            "manifest artifact_kind mismatch: "
            f"{manifest.get('artifact_kind')!r}"
        )
    if manifest.get("schema_version") != REVIEW_ZIP_SCHEMA_VERSION:
        errors.append(
            "manifest schema_version mismatch: "
            f"{manifest.get('schema_version')!r}"
        )
    files = manifest.get("files")
    if not isinstance(files, list):
        errors.append("manifest files must be a list")
        files = []
    required_source_paths = set(REQUIRED_PROJECT_CONTEXT_FILES)
    required_review_artifacts = set(REQUIRED_REVIEW_ARTIFACTS.values())
    seen_required_sources: set[str] = set()
    seen_required_review_artifacts: set[str] = set()
    for file_entry in files:
        if not isinstance(file_entry, dict):
            errors.append("manifest file entry is not an object")
            continue
        zip_member = str(file_entry.get("zip_path") or "").replace("\\", "/")
        source_path = str(file_entry.get("source_path") or "").replace("\\", "/")
        required = bool(file_entry.get("required"))
        if not zip_member:
            errors.append(f"manifest entry missing zip_path: {file_entry!r}")
            continue
        if required and zip_member not in names:
            errors.append(f"required manifest file missing from ZIP: {zip_member}")
        if required and source_path in required_source_paths:
            seen_required_sources.add(source_path)
        if required and zip_member in required_review_artifacts:
            seen_required_review_artifacts.add(zip_member)
    for core_file in CORE_MANIFEST_FILES:
        if core_file not in names:
            errors.append(f"core review ZIP file missing: {core_file}")
    missing_required_sources = sorted(required_source_paths - seen_required_sources)
    for source_path in missing_required_sources:
        errors.append(f"required project context source missing from manifest: {source_path}")
    missing_review_artifacts = sorted(required_review_artifacts - seen_required_review_artifacts)
    for zip_path in missing_review_artifacts:
        errors.append(f"required review artifact missing from manifest: {zip_path}")
    errors.extend(_validate_required_review_artifacts(required_artifact_payloads, zip_names=names))
    return tuple(errors)


def _validate_required_review_artifacts(
    payloads: dict[str, bytes],
    *,
    zip_names: set[str],
) -> tuple[str, ...]:
    errors: list[str] = []
    for artifact_id, zip_path in REQUIRED_REVIEW_ARTIFACTS.items():
        raw = payloads.get(artifact_id)
        if raw is None:
            continue
        if artifact_id not in ALLOW_EMPTY_REVIEW_ARTIFACTS and not raw.strip():
            errors.append(f"required review artifact is empty: {zip_path}")
    pointer_raw = payloads.get("pointer_map_audit")
    if pointer_raw is not None and pointer_raw.strip():
        errors.extend(_validate_pointer_map_audit(pointer_raw))
    memory_raw = payloads.get("memory_audit")
    if memory_raw is not None and memory_raw.strip():
        errors.extend(_validate_memory_audit(memory_raw))
    adoption_raw = payloads.get("adoption_audit")
    if adoption_raw is not None and adoption_raw.strip():
        errors.extend(_validate_adoption_audit(adoption_raw))
    command_manifest_raw = payloads.get("command_manifest")
    if command_manifest_raw is not None and command_manifest_raw.strip():
        errors.extend(_validate_command_manifest(command_manifest_raw, zip_names=zip_names))
    git_provenance_raw = payloads.get("git_provenance")
    if git_provenance_raw is not None and git_provenance_raw.strip():
        errors.extend(_validate_git_provenance(git_provenance_raw))
    return tuple(errors)


def _validate_command_manifest(raw: bytes, *, zip_names: set[str]) -> tuple[str, ...]:
    zip_path = REQUIRED_REVIEW_ARTIFACTS["command_manifest"]
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        return (f"command manifest artifact is not valid JSON: {zip_path}: {exc}",)
    if not isinstance(payload, dict):
        return (f"command manifest artifact must be a JSON object: {zip_path}",)
    errors: list[str] = []
    if payload.get("artifact_kind") != COMMAND_MANIFEST_ARTIFACT_KIND:
        errors.append(
            "command manifest artifact_kind must be "
            f"{COMMAND_MANIFEST_ARTIFACT_KIND!r}"
        )
    if payload.get("schema_version") != COMMAND_MANIFEST_SCHEMA_VERSION:
        errors.append(
            "command manifest schema_version must be "
            f"{COMMAND_MANIFEST_SCHEMA_VERSION}"
        )
    commands = payload.get("commands")
    if not isinstance(commands, list) or not commands:
        return tuple([*errors, "command manifest commands must be a non-empty list"])
    for index, command in enumerate(commands):
        errors.extend(_validate_command_manifest_entry(index, command, zip_names=zip_names))
    return tuple(errors)


def _validate_command_manifest_entry(
    index: int,
    command: Any,
    *,
    zip_names: set[str],
) -> tuple[str, ...]:
    label = f"command manifest commands[{index}]"
    if not isinstance(command, dict):
        return (f"{label} must be a JSON object",)
    errors: list[str] = []
    for key in ("phase", "name", "command", "log_path", "started_at", "finished_at"):
        value = command.get(key)
        if not isinstance(value, str) or not value.strip():
            errors.append(f"{label}.{key} must be a non-empty string")
    exit_code = command.get("exit_code")
    if isinstance(exit_code, bool) or not isinstance(exit_code, int):
        errors.append(f"{label}.exit_code must be an integer")
    elif exit_code != 0:
        errors.append(f"{label}.exit_code must be 0")
    if command.get("provider_requests_expected_zero") is not True:
        errors.append(f"{label}.provider_requests_expected_zero must be true")
    for key in (
        "provider_requests_observed",
        "provider_transport_sends_observed",
    ):
        value = command.get(key)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            errors.append(f"{label}.{key} must be a non-negative integer")
        elif value != 0:
            errors.append(f"{label}.{key} must be 0")
    delta = command.get("api_budget_event_delta")
    if not isinstance(delta, dict):
        errors.append(f"{label}.api_budget_event_delta must be a JSON object")
    else:
        if delta.get("artifact_kind") != API_BUDGET_EVENT_DELTA_ARTIFACT_KIND:
            errors.append(
                f"{label}.api_budget_event_delta.artifact_kind must be "
                f"{API_BUDGET_EVENT_DELTA_ARTIFACT_KIND!r}"
            )
        if delta.get("schema_version") != API_BUDGET_EVENT_DELTA_SCHEMA_VERSION:
            errors.append(
                f"{label}.api_budget_event_delta.schema_version must be "
                f"{API_BUDGET_EVENT_DELTA_SCHEMA_VERSION}"
            )
        for key in (
            "provider_requests_observed",
            "provider_requests_blocked_by_freeze",
            "provider_transport_sends_observed",
        ):
            value = delta.get(key)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                errors.append(
                    f"{label}.api_budget_event_delta.{key} must be a non-negative integer"
                )
            elif key in {
                "provider_requests_observed",
                "provider_transport_sends_observed",
            } and value != 0:
                errors.append(f"{label}.api_budget_event_delta.{key} must be 0")
        for key in (
            "provider_requests_observed",
            "provider_transport_sends_observed",
        ):
            if (
                isinstance(command.get(key), int)
                and isinstance(delta.get(key), int)
                and command.get(key) != delta.get(key)
            ):
                errors.append(
                    f"{label}.{key} must match api_budget_event_delta.{key}"
                )
        if delta.get("not_evidence") is not True:
            errors.append(f"{label}.api_budget_event_delta.not_evidence must be true")
    log_path = str(command.get("log_path") or "").replace("\\", "/")
    if log_path and log_path not in zip_names:
        errors.append(f"{label}.log_path missing from ZIP: {log_path}")
    for key in ("started_at", "finished_at"):
        value = command.get(key)
        if isinstance(value, str) and value.strip():
            try:
                datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError:
                errors.append(f"{label}.{key} must be an ISO 8601 timestamp")
    return tuple(errors)


def _validate_git_provenance(raw: bytes) -> tuple[str, ...]:
    zip_path = REQUIRED_REVIEW_ARTIFACTS["git_provenance"]
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        return (f"git provenance artifact is not valid JSON: {zip_path}: {exc}",)
    if not isinstance(payload, dict):
        return (f"git provenance artifact must be a JSON object: {zip_path}",)
    errors: list[str] = []
    if payload.get("artifact_kind") != GIT_PROVENANCE_ARTIFACT_KIND:
        errors.append(
            "git provenance artifact_kind must be "
            f"{GIT_PROVENANCE_ARTIFACT_KIND!r}"
        )
    if payload.get("schema_version") != GIT_PROVENANCE_SCHEMA_VERSION:
        errors.append(
            "git provenance schema_version must be "
            f"{GIT_PROVENANCE_SCHEMA_VERSION}"
        )
    if payload.get("not_evidence") is not True:
        errors.append("git provenance not_evidence must be true")
    if payload.get("git_available") is not True:
        errors.append("git provenance git_available must be true")
    head_commit = str(payload.get("head_commit") or "")
    if not re.fullmatch(r"[0-9a-f]{40}", head_commit):
        errors.append("git provenance head_commit must be a 40-character lowercase hex hash")
    head_short = str(payload.get("head_short_commit") or "")
    if head_short and head_commit and not head_commit.startswith(head_short):
        errors.append("git provenance head_short_commit must prefix head_commit")
    working_tree = payload.get("working_tree")
    if not isinstance(working_tree, dict):
        errors.append("git provenance working_tree must be a JSON object")
    else:
        if not isinstance(working_tree.get("status_short"), list):
            errors.append("git provenance working_tree.status_short must be a list")
        if not isinstance(working_tree.get("is_dirty"), bool):
            errors.append("git provenance working_tree.is_dirty must be boolean")
        if working_tree.get("is_dirty") is True and not str(
            working_tree.get("dirty_allowed_reason") or ""
        ).strip():
            errors.append(
                "git provenance dirty working tree requires dirty_allowed_reason"
            )
        policy = str(working_tree.get("policy") or "")
        if policy not in {
            "clean_required_satisfied",
            "dirty_allowed_for_review_package",
            "git_unavailable",
        }:
            errors.append(f"git provenance working_tree.policy is invalid: {policy!r}")
    diff = payload.get("diff")
    if not isinstance(diff, dict):
        errors.append("git provenance diff must be a JSON object")
    else:
        for key in ("base_to_head_name_status", "working_tree_name_status", "cached_name_status"):
            if not isinstance(diff.get(key), list):
                errors.append(f"git provenance diff.{key} must be a list")
    return tuple(errors)


def _validate_memory_audit(raw: bytes) -> tuple[str, ...]:
    zip_path = REQUIRED_REVIEW_ARTIFACTS["memory_audit"]
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        return (f"memory audit artifact is not valid JSON: {zip_path}: {exc}",)
    if not isinstance(payload, dict):
        return (f"memory audit artifact must be a JSON object: {zip_path}",)
    errors: list[str] = []
    readiness = payload.get("readiness")
    if not isinstance(readiness, dict):
        errors.append("memory audit readiness must be a JSON object")
    else:
        if readiness.get("local_no_provider_ready") is not True:
            errors.append("memory audit readiness.local_no_provider_ready must be true")
        if readiness.get("blocking_issue_count") != 0:
            errors.append("memory audit readiness.blocking_issue_count must be 0")
    for key in ("claim_citation_issues", "freshness_lineage_issues"):
        value = payload.get(key)
        if not isinstance(value, dict):
            errors.append(f"memory audit {key} must be a JSON object")
        elif value:
            errors.append(f"memory audit {key} must be empty")
    structured_warnings = payload.get("structured_warnings")
    if not isinstance(structured_warnings, list):
        errors.append("memory audit structured_warnings must be a list")
    return tuple(errors)


def _validate_adoption_audit(raw: bytes) -> tuple[str, ...]:
    zip_path = REQUIRED_REVIEW_ARTIFACTS["adoption_audit"]
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        return (f"adoption audit artifact is not valid JSON: {zip_path}: {exc}",)
    if not isinstance(payload, dict):
        return (f"adoption audit artifact must be a JSON object: {zip_path}",)
    errors: list[str] = []
    if payload.get("status") != "ok":
        errors.append("adoption audit status must be ok")
    if payload.get("errors") != []:
        errors.append("adoption audit errors must be empty")
    if not isinstance(payload.get("candidates"), list):
        errors.append("adoption audit candidates must be a list")
    return tuple(errors)


def _validate_pointer_map_audit(raw: bytes) -> tuple[str, ...]:
    zip_path = REQUIRED_REVIEW_ARTIFACTS["pointer_map_audit"]
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        return (f"pointer map audit artifact is not valid JSON: {zip_path}: {exc}",)
    if not isinstance(payload, dict):
        return (f"pointer map audit artifact must be a JSON object: {zip_path}",)
    errors: list[str] = []
    if payload.get("source_kind") != "pointer_map":
        errors.append(
            "pointer map audit source_kind must be 'pointer_map': "
            f"{payload.get('source_kind')!r}"
        )
    status = str(payload.get("status") or "")
    allowed_statuses = {"passed", "skipped_external_pointer_map_absent"}
    if status not in allowed_statuses:
        errors.append(
            "pointer map audit status must be passed or skipped_external_pointer_map_absent: "
            f"{status!r}"
        )
    for key in ("entry_count", "usable_count", "failed_count", "invalid_entry_count"):
        value = payload.get(key)
        if not isinstance(value, int) or value < 0:
            errors.append(f"pointer map audit {key} must be a non-negative integer")
    results = payload.get("results")
    if not isinstance(results, list):
        errors.append("pointer map audit results must be a list")
    if status == "passed":
        entry_count = payload.get("entry_count")
        usable_count = payload.get("usable_count")
        failed_count = payload.get("failed_count")
        if failed_count != 0:
            errors.append("pointer map audit passed status requires failed_count=0")
        if (
            isinstance(entry_count, int)
            and isinstance(usable_count, int)
            and isinstance(failed_count, int)
            and entry_count != usable_count + failed_count
        ):
            errors.append(
                "pointer map audit counts must satisfy "
                "entry_count == usable_count + failed_count"
            )
        if isinstance(results, list) and not results:
            errors.append("pointer map audit passed status requires result entries")
        if isinstance(results, list):
            errors.extend(_validate_passed_pointer_map_results(results))
    if (
        status == "skipped_external_pointer_map_absent"
        and payload.get("skipped_reason") != "pointer_map_absent"
    ):
        errors.append(
            "skipped pointer map audit requires skipped_reason='pointer_map_absent'"
        )
    return tuple(errors)


def _validate_passed_pointer_map_results(results: list[Any]) -> tuple[str, ...]:
    errors: list[str] = []
    for index, result in enumerate(results):
        label = f"pointer map audit results[{index}]"
        if not isinstance(result, dict):
            errors.append(f"{label} must be a JSON object")
            continue
        if result.get("status") != "usable_pointer":
            errors.append(f"{label}.status must be usable_pointer")
        if result.get("issues") != []:
            errors.append(f"{label}.issues must be empty")
        if result.get("not_evidence") is not True:
            errors.append(f"{label}.not_evidence must be true")
        for key in ("sha256_match", "byte_count_match", "char_count_match"):
            if key in result and result.get(key) is not True:
                errors.append(f"{label}.{key} must be true when present")
    return tuple(errors)


def _copy_project_files(
    root: Path,
    staging: Path,
    files: list[dict[str, Any]],
    source_paths: tuple[str, ...],
    *,
    role: str,
    required: bool,
) -> None:
    for source_path in source_paths:
        normalized = source_path.replace("\\", "/").strip("/")
        if not normalized:
            continue
        source = root / normalized
        if not source.exists():
            if required:
                files.append(
                    {
                        "role": role,
                        "source_path": normalized,
                        "zip_path": _zip_path_for_role(role, normalized),
                        "required": True,
                        "missing_source": True,
                    }
                )
            continue
        if not source.is_file():
            continue
        zip_path = _zip_path_for_role(role, normalized)
        destination = staging / zip_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        files.append(
            {
                "role": role,
                "source_path": normalized,
                "zip_path": zip_path,
                "required": required,
            }
        )


def _zip_path_for_role(role: str, source_path: str) -> str:
    if role == "project_context":
        return f"attachments/project_context/{source_path}"
    if role == "changed_file":
        return f"attachments/changed_files/{source_path}"
    return f"attachments/extra_context/{source_path}"


def _copy_review_artifacts(
    root: Path,
    staging: Path,
    files: list[dict[str, Any]],
    review_artifacts: dict[str, str | Path],
) -> None:
    for artifact_id, zip_path in REQUIRED_REVIEW_ARTIFACTS.items():
        if artifact_id in GENERATED_REVIEW_ARTIFACTS:
            continue
        raw_source = review_artifacts.get(artifact_id)
        source = _resolve_optional_source(root, raw_source)
        if source is None or not source.exists() or not source.is_file():
            files.append(
                {
                    "role": "review_artifact",
                    "artifact_id": artifact_id,
                    "source_path": _manifest_source_path(root, source) if source else None,
                    "zip_path": zip_path,
                    "required": True,
                    "missing_source": True,
                }
            )
            continue
        destination = staging / zip_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        files.append(
            {
                "role": "review_artifact",
                "artifact_id": artifact_id,
                "source_path": _manifest_source_path(root, source),
                "zip_path": zip_path,
                "required": True,
            }
        )


def _resolve_optional_source(root: Path, value: str | Path | None) -> Path | None:
    if value is None:
        return None
    path = Path(value)
    return path if path.is_absolute() else root / path


def _manifest_source_path(root: Path, source: Path | None) -> str | None:
    if source is None:
        return None
    try:
        return source.resolve().relative_to(root).as_posix()
    except ValueError:
        return str(source)


def _write_context(
    staging: Path,
    project_root: Path,
    *,
    base_ref: str | None,
    head_ref: str,
    git_provenance: dict[str, Any],
) -> None:
    working_tree = git_provenance.get("working_tree")
    if not isinstance(working_tree, dict):
        working_tree = {}
    lines = [
        "# research_x GPT Review Context",
        "",
        f"created_at: {datetime.now(tz=UTC).isoformat(timespec='seconds')}",
        f"project_root: {project_root}",
        f"base_ref: {base_ref or '-'}",
        f"head_ref: {head_ref}",
        f"head_commit: {git_provenance.get('head_commit') or '-'}",
        f"head_short_commit: {git_provenance.get('head_short_commit') or '-'}",
        f"base_commit: {git_provenance.get('base_commit') or '-'}",
        f"working_tree_policy: {working_tree.get('policy') or '-'}",
        f"working_tree_dirty: {working_tree.get('is_dirty')}",
        f"dirty_allowed_reason: {working_tree.get('dirty_allowed_reason') or '-'}",
        "",
        "This package is a control/review artifact, not answer evidence.",
        "Use source bundles, context chunks, and citations for answer support.",
        "",
        "Required project context is listed in attachment_manifest.json.",
        "Provider execution surface source files are included for no-quota gate review.",
    ]
    (staging / "context.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_manifest_markdown(staging: Path) -> None:
    lines = [
        "# Attachment Manifest",
        "",
        "Machine-readable manifest: `attachment_manifest.json`.",
        "",
        "The ZIP is valid only when `verify_review_zip()` reports no errors.",
    ]
    (staging / "attachment_manifest.md").write_text(
        "\n".join(lines) + "\n",
        encoding="utf-8",
    )


def _write_git_provenance_artifact(
    staging: Path,
    files: list[dict[str, Any]],
    payload: dict[str, Any],
) -> None:
    zip_path = REQUIRED_REVIEW_ARTIFACTS["git_provenance"]
    path = staging / zip_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    files.append(
        {
            "role": "review_artifact",
            "artifact_id": "git_provenance",
            "source_path": None,
            "zip_path": zip_path,
            "required": True,
            "generated": True,
        }
    )


def _write_git_artifacts(
    root: Path,
    staging: Path,
    files: list[dict[str, Any]],
    *,
    base_ref: str | None,
    head_ref: str,
) -> None:
    if not base_ref:
        return
    artifacts = {
        "attachments/git/commit_log.txt": ["git", "log", "--oneline", f"{base_ref}..{head_ref}"],
        "attachments/git/diff_stat.txt": ["git", "diff", "--stat", f"{base_ref}..{head_ref}"],
        "attachments/git/diff_name_status.txt": [
            "git",
            "diff",
            "--name-status",
            f"{base_ref}..{head_ref}",
        ],
        "attachments/git/diff.patch": ["git", "diff", "--no-ext-diff", f"{base_ref}..{head_ref}"],
        "attachments/git/status_short.txt": ["git", "status", "--short"],
    }
    for zip_path, command in artifacts.items():
        output = _run_git(root, command)
        path = staging / zip_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(output, encoding="utf-8")
        files.append(
            {
                "role": "git_artifact",
                "source_path": None,
                "zip_path": zip_path,
                "required": False,
            }
        )


def _git_provenance_payload(
    root: Path,
    *,
    base_ref: str | None,
    head_ref: str,
    changed_files: tuple[str, ...],
) -> dict[str, Any]:
    head_commit = _git_commit(root, head_ref)
    base_commit = _git_commit(root, base_ref) if base_ref else None
    status_short = _git_lines(root, ["git", "status", "--short"])
    working_tree_name_status = _git_lines(root, ["git", "diff", "--name-status"])
    cached_name_status = _git_lines(root, ["git", "diff", "--cached", "--name-status"])
    if base_ref:
        base_to_head = _git_lines(root, ["git", "diff", "--name-status", f"{base_ref}..{head_ref}"])
        merge_base = _run_git_optional(root, ["git", "merge-base", base_ref, head_ref])
    else:
        base_to_head = []
        merge_base = None
    is_dirty = bool(status_short)
    git_available = bool(head_commit)
    return {
        "artifact_kind": GIT_PROVENANCE_ARTIFACT_KIND,
        "schema_version": GIT_PROVENANCE_SCHEMA_VERSION,
        "created_at": datetime.now(tz=UTC).isoformat(timespec="seconds"),
        "project_root": str(root),
        "git_available": git_available,
        "head_ref": head_ref,
        "head_commit": head_commit,
        "head_short_commit": head_commit[:12] if head_commit else None,
        "head_oneline": _run_git_optional(root, ["git", "show", "-s", "--oneline", head_ref]),
        "head_stat": _run_git_optional(
            root,
            ["git", "show", "--stat", "--oneline", "--no-renames", head_ref],
        ),
        "base_ref": base_ref,
        "base_commit": base_commit,
        "base_short_commit": base_commit[:12] if base_commit else None,
        "merge_base_commit": merge_base.strip() if merge_base else None,
        "working_tree": {
            "is_dirty": is_dirty,
            "policy": (
                "git_unavailable"
                if not git_available
                else "dirty_allowed_for_review_package"
                if is_dirty
                else "clean_required_satisfied"
            ),
            "dirty_allowed_reason": (
                "review package captures current working tree status and changed file list"
                if is_dirty
                else None
            ),
            "status_short": status_short,
            "tracked_change_count": sum(1 for line in status_short if not line.startswith("??")),
            "untracked_count": sum(1 for line in status_short if line.startswith("??")),
            "unstaged_change_count": len(working_tree_name_status),
            "staged_change_count": len(cached_name_status),
        },
        "diff": {
            "base_to_head_name_status": base_to_head,
            "working_tree_name_status": working_tree_name_status,
            "cached_name_status": cached_name_status,
            "changed_files_requested": list(changed_files),
        },
        "not_evidence": True,
    }


def _manifest_payload(
    *,
    project_root: Path,
    base_ref: str | None,
    head_ref: str,
    files: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "artifact_kind": REVIEW_ZIP_ARTIFACT_KIND,
        "schema_version": REVIEW_ZIP_SCHEMA_VERSION,
        "created_at": datetime.now(tz=UTC).isoformat(timespec="seconds"),
        "project_root": str(project_root),
        "base_ref": base_ref,
        "head_ref": head_ref,
        "required_project_context_files": list(REQUIRED_PROJECT_CONTEXT_FILES),
        "required_review_artifacts": REQUIRED_REVIEW_ARTIFACTS,
        "files": files,
    }


def _rewrite_manifest_with_self_entry(
    manifest_path: Path,
    manifest: dict[str, Any],
    files: list[dict[str, Any]],
) -> None:
    manifest["files"] = files
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _zip_directory(source_dir: Path, output_zip: Path) -> None:
    with zipfile.ZipFile(output_zip, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(source_dir.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(source_dir).as_posix())


def _git_changed_files(root: Path, *, base_ref: str | None, head_ref: str) -> tuple[str, ...]:
    if not base_ref:
        return ()
    output = _run_git(root, ["git", "diff", "--name-only", f"{base_ref}..{head_ref}"])
    return tuple(line.strip() for line in output.splitlines() if line.strip())


def _run_git(root: Path, command: list[str]) -> str:
    completed = subprocess.run(
        command,
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return completed.stdout


def _run_git_optional(root: Path, command: list[str]) -> str | None:
    try:
        return _run_git(root, command).strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


def _git_commit(root: Path, ref: str | None) -> str | None:
    if not ref:
        return None
    return _run_git_optional(root, ["git", "rev-parse", ref])


def _git_lines(root: Path, command: list[str]) -> list[str]:
    output = _run_git_optional(root, command)
    if output is None:
        return []
    return [line.strip() for line in output.splitlines() if line.strip()]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build and verify a research_x GPT review context ZIP.",
    )
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--base-ref")
    parser.add_argument("--head-ref", default="HEAD")
    parser.add_argument("--changed-file", action="append", default=[])
    parser.add_argument("--extra-file", action="append", default=[])
    parser.add_argument("--pytest-log", type=Path)
    parser.add_argument("--ruff-log", type=Path)
    parser.add_argument("--git-diff-check-log", type=Path)
    parser.add_argument("--git-status-log", type=Path)
    parser.add_argument("--review-zip-verify-log", type=Path)
    parser.add_argument("--command-manifest", type=Path)
    parser.add_argument("--memory-audit", type=Path)
    parser.add_argument("--adoption-audit", type=Path)
    parser.add_argument("--pointer-map-audit", type=Path)
    parser.add_argument("--verify-manifest", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    review_artifacts = {
        "pytest_log": args.pytest_log,
        "ruff_log": args.ruff_log,
        "git_diff_check_log": args.git_diff_check_log,
        "git_status_log": args.git_status_log,
        "review_zip_verify_log": args.review_zip_verify_log,
        "command_manifest": args.command_manifest,
        "memory_audit": args.memory_audit,
        "adoption_audit": args.adoption_audit,
        "pointer_map_audit": args.pointer_map_audit,
    }
    result = build_review_context_zip(
        args.project_root,
        args.output,
        base_ref=args.base_ref,
        head_ref=args.head_ref,
        changed_files=tuple(args.changed_file) if args.changed_file else None,
        extra_files=tuple(args.extra_file),
        review_artifacts=review_artifacts,
        verify_manifest=args.verify_manifest,
    )
    payload = asdict(result)
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"zip: {result.zip_path}")
        print(f"files: {result.file_count}")
        if result.verification_errors:
            print("verification errors:")
            for error in result.verification_errors:
                print(f"  - {error}")
        else:
            print("verification: passed")
    return 2 if result.verification_errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
