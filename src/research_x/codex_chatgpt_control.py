from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import uuid
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "research-x-codex-chatgpt-control-v1"
SOURCE_REPO = "https://github.com/adamallcock/codex-chatgpt-control"

STOP_REASONS = (
    "browser_bridge_unavailable",
    "login_required",
    "captcha",
    "permission",
    "selector_drift",
    "rate_limit",
    "ambiguous_confirmation",
    "upload_failed",
    "download_unavailable",
    "modal_or_interstitial",
    "timeout",
)

BACKEND_CAPABILITY_COMMANDS = (
    "backend.version",
    "backend.health",
    "backend.capabilities",
    "runner.plan",
    "runner.run",
    "runner.stream",
    "responses.create",
    "ask",
    "askInThread",
    "askWithFiles",
    "askAndDownload",
    "runMessages",
    "openThread",
    "readLatest",
    "copyLatest",
    "downloadLatest",
    "runPlan",
    "doctor",
    "reports.create",
    "reports.redact",
    "reports.summarize",
    "session.*",
    "threads.*",
    "messages.*",
    "files.*",
    "modes.*",
    "tools.*",
)

WORKFLOW_CATALOG: dict[str, dict[str, Any]] = {
    "runner_run": {
        "backend_command": "runner.run",
        "node_method": "runner.run",
        "prompt_required": True,
        "description": "Run an Agent through the SDK runner with visible ChatGPT browser control.",
        "risk": "visible_browser_execution",
    },
    "runner_plan": {
        "backend_command": "runner.plan",
        "node_method": "runner.plan",
        "prompt_required": True,
        "description": "Ask the SDK runner for a visible-session execution plan.",
        "risk": "visible_browser_execution_plan",
    },
    "runner_stream": {
        "backend_command": "runner.stream",
        "node_method": "runner.stream",
        "prompt_required": True,
        "description": "Run a streaming visible ChatGPT exchange through the SDK runner.",
        "risk": "visible_browser_execution_stream",
    },
    "responses_create": {
        "backend_command": "responses.create",
        "node_method": "responses.create",
        "prompt_required": True,
        "description": "Use the upstream Responses-like adapter for visible ChatGPT web control.",
        "risk": "visible_browser_execution_responses_adapter",
    },
    "ask": {
        "backend_command": "ask",
        "node_method": "ask",
        "prompt_required": True,
        "description": "Ask ChatGPT in a visible session and return a redacted report by default.",
        "risk": "visible_browser_execution",
    },
    "ask_in_thread": {
        "backend_command": "askInThread",
        "node_method": "askInThread",
        "prompt_required": True,
        "description": "Ask in an existing or newly opened ChatGPT thread.",
        "risk": "visible_browser_execution_thread_state",
    },
    "ask_with_files": {
        "backend_command": "askWithFiles",
        "node_method": "askWithFiles",
        "prompt_required": True,
        "description": "Ask ChatGPT with user-approved file uploads.",
        "risk": "visible_browser_execution_file_upload",
    },
    "ask_and_download": {
        "backend_command": "askAndDownload",
        "node_method": "askAndDownload",
        "prompt_required": True,
        "description": "Ask ChatGPT and download a generated artifact to an approved directory.",
        "risk": "visible_browser_execution_file_download",
    },
    "run_messages": {
        "backend_command": "runMessages",
        "node_method": "runMessages",
        "prompt_required": True,
        "description": "Run a bounded multi-message visible ChatGPT exchange.",
        "risk": "visible_browser_execution_multi_step",
    },
    "open_thread": {
        "backend_command": "openThread",
        "node_method": "openThread",
        "prompt_required": False,
        "description": "Open or attach to a visible ChatGPT thread without sending a prompt.",
        "risk": "visible_browser_thread_navigation",
    },
    "read_latest": {
        "backend_command": "readLatest",
        "node_method": "readLatest",
        "prompt_required": False,
        "description": "Read latest visible ChatGPT response from an approved thread.",
        "risk": "visible_browser_read",
    },
    "copy_latest": {
        "backend_command": "copyLatest",
        "node_method": "copyLatest",
        "prompt_required": False,
        "description": "Copy the latest visible ChatGPT response through the upstream workflow.",
        "risk": "visible_browser_clipboard",
    },
    "download_latest": {
        "backend_command": "downloadLatest",
        "node_method": "downloadLatest",
        "prompt_required": False,
        "description": "Download the latest visible ChatGPT artifact to an approved directory.",
        "risk": "visible_browser_file_download",
    },
    "doctor": {
        "backend_command": "doctor",
        "node_method": "doctor",
        "prompt_required": False,
        "description": "Run upstream bridge diagnostics.",
        "risk": "diagnostic",
    },
}

SUPPORTED_WORKFLOWS = tuple(WORKFLOW_CATALOG)


@dataclass(frozen=True)
class ToolCheck:
    name: str
    path: str | None
    version: str | None
    status: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class DoctorReport:
    schema_version: str
    status: str
    checks: tuple[ToolCheck, ...]
    browser_bridge: dict[str, Any]
    upstream_runtime: dict[str, Any]
    safety: dict[str, Any]
    next_actions: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["checks"] = [check.as_dict() for check in self.checks]
        return payload


def run_doctor(*, check_global_package: bool = True) -> DoctorReport:
    """Run local diagnostics without touching ChatGPT, browser state, or provider APIs."""

    checks = (
        _tool_check("node", "--version"),
        _tool_check("npm", "--version"),
    )
    package_status = "not_checked"
    if check_global_package and checks[1].status == "ok":
        package_status = _global_package_status("codex-chatgpt-control")

    status = (
        "ready_for_bridge_setup"
        if all(check.status == "ok" for check in checks)
        else "missing_runtime"
    )
    next_actions: list[str] = []
    if status == "missing_runtime":
        next_actions.append("install_node_20_or_newer_and_npm")
    if package_status != "present":
        next_actions.append("install_or_build_codex_chatgpt_control_runtime")
    next_actions.append("run only in a visible ChatGPT bridge host after explicit user approval")

    return DoctorReport(
        schema_version=SCHEMA_VERSION,
        status=status,
        checks=checks,
        browser_bridge={
            "status": "not_available_from_ordinary_shell",
            "expected_blocker": "browser_bridge_unavailable",
            "requires_globalThis_agent": True,
            "ordinary_cli_execution": "plan_and_render_only_by_default",
        },
        upstream_runtime={
            "package": "codex-chatgpt-control",
            "global_package_status": package_status,
            "backend_capability_commands": BACKEND_CAPABILITY_COMMANDS,
            "supported_research_x_workflows": SUPPORTED_WORKFLOWS,
        },
        safety=_safety_contract(),
        next_actions=tuple(next_actions),
    )


def local_capabilities_json() -> str:
    return json.dumps(local_capabilities(), ensure_ascii=False, indent=2, sort_keys=True)


def local_capabilities() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "source_basis": SOURCE_REPO,
        "mode": "local_contract_inventory",
        "note": "This does not contact ChatGPT, the upstream backend, or provider APIs.",
        "supported_workflows": {
            name: _workflow_row(name) for name in SUPPORTED_WORKFLOWS
        },
        "upstream_command_surface": BACKEND_CAPABILITY_COMMANDS,
        "safety": _safety_contract(),
        "evidence_policy": _evidence_policy(),
        "ordinary_shell_expected_blocker": "browser_bridge_unavailable",
    }


def format_local_capabilities(payload: dict[str, Any]) -> str:
    lines = [
        "codex-chatgpt-control capabilities",
        f"schema: {payload['schema_version']}",
        "mode: local contract inventory",
        "supported workflows:",
    ]
    for name, row in payload["supported_workflows"].items():
        lines.append(f"- {name}: command={row['backend_command']} risk={row['risk']}")
    lines.append("upstream command surface:")
    lines.extend(f"- {command}" for command in payload["upstream_command_surface"])
    lines.append("evidence: citation_excluded until research_x restores sources")
    return "\n".join(lines)


def doctor_report_json(report: DoctorReport) -> str:
    return json.dumps(report.as_dict(), ensure_ascii=False, indent=2, sort_keys=True)


def format_doctor_report(report: DoctorReport) -> str:
    lines = [
        f"codex-chatgpt-control doctor: {report.status}",
        f"schema: {report.schema_version}",
    ]
    for check in report.checks:
        version = f" version={check.version}" if check.version else ""
        path = f" path={check.path}" if check.path else ""
        lines.append(f"{check.name}: {check.status}{version}{path}")
    lines.append(
        "browser_bridge: "
        f"{report.browser_bridge['status']} "
        f"(expected={report.browser_bridge['expected_blocker']})"
    )
    lines.append(f"upstream_package: {report.upstream_runtime['global_package_status']}")
    lines.append(
        "workflows: " + ", ".join(report.upstream_runtime["supported_research_x_workflows"])
    )
    lines.append("safety: visible session only; ChatGPT output is citation-excluded")
    lines.append("next_actions:")
    lines.extend(f"- {action}" for action in report.next_actions)
    return "\n".join(lines)


def build_control_plan(
    *,
    prompt: str,
    task_kind: str,
    out_dir: str | Path,
    workflow: str = "runner_run",
    agent_name: str = "chatgpt-consultant",
    instructions: str | None = None,
    instructions_mode: str = "visible_prefix",
    thread_url: str | None = None,
    existing_tab: bool = False,
    files: tuple[str, ...] = (),
    download_dir: str | Path | None = None,
    response_format: str = "markdown",
    include_prompt: bool = False,
    include_report_content: bool = False,
    max_prompts_per_run: int = 1,
    max_threads_opened_per_run: int = 1,
    max_messages_read_per_run: int = 3,
    max_report_bytes_per_run: int = 2_000_000,
    request_id: str | None = None,
) -> tuple[dict[str, Any], Path]:
    """Create a local consultation plan artifact without sending any request."""

    if workflow not in WORKFLOW_CATALOG:
        raise ValueError(f"unsupported workflow {workflow!r}")
    if WORKFLOW_CATALOG[workflow]["prompt_required"] and not prompt.strip():
        raise ValueError("prompt must not be empty")

    request_id = request_id or _request_id()
    now = _utc_now()
    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    plan_path = out_path / f"{request_id}.json"
    file_rows = tuple(_file_row(path) for path in files)
    prompt_hash = _sha256_text(prompt)
    thread = _thread_policy(thread_url=thread_url, existing_tab=existing_tab)
    response = {"format": response_format}
    agent = {
        "name": agent_name,
        "instructions": instructions or _default_instructions(task_kind),
        "instructions_mode": instructions_mode,
    }
    report = {
        "enabled": True,
        "include_content": include_report_content,
        "includeContent": include_report_content,
        "redacted_by_default": not include_report_content,
        "max_report_bytes_per_run": max_report_bytes_per_run,
        "maxReportBytesPerRun": max_report_bytes_per_run,
    }

    plan = {
        "schema_version": SCHEMA_VERSION,
        "request_id": request_id,
        "created_at": now,
        "source_basis": {
            "repo": SOURCE_REPO,
            "upstream_contract": "visible_session_sdk_not_api_wrapper",
            "source_review_scope": "README_docs_contracts_node_python_skill",
        },
        "task_kind": task_kind,
        "workflow": _workflow_row(workflow),
        "prompt": prompt if include_prompt else None,
        "prompt_hash": prompt_hash,
        "prompt_preview": _preview(prompt),
        "prompt_storage_policy": "stored" if include_prompt else "redacted",
        "agent": agent,
        "thread": thread,
        "files": list(file_rows),
        "download": _download_policy(download_dir),
        "response": response,
        "report": report,
        "run_limits": {
            "max_prompts_per_run": max(0, max_prompts_per_run),
            "max_threads_opened_per_run": max(0, max_threads_opened_per_run),
            "max_messages_read_per_run": max(0, max_messages_read_per_run),
            "max_report_bytes_per_run": max(0, max_report_bytes_per_run),
        },
        "runtime_requirements": {
            "node": ">=20",
            "npm": True,
            "visible_chatgpt_session": True,
            "compatible_browser_bridge": "globalThis.agent",
            "ordinary_shell_allowed_modes": ("doctor", "plan", "render", "blocked-run"),
        },
        "expected_stop_reasons": STOP_REASONS,
        "safety": _safety_contract(),
        "evidence_policy": _evidence_policy(),
        "backend_protocol": {
            "transport": "stdio_ndjson",
            "capability_commands": BACKEND_CAPABILITY_COMMANDS,
            "selected_command": WORKFLOW_CATALOG[workflow]["backend_command"],
        },
        "sdk_payload": _sdk_payload(
            workflow=workflow,
            prompt=prompt if include_prompt else None,
            agent=agent,
            thread=thread,
            files=file_rows,
            download_dir=download_dir,
            response=response,
            report=report,
        ),
        "recommended_sdk_shape": {
            "node_import": 'import { createChatGPT } from "codex-chatgpt-control";',
            "python_import": (
                "from codex_chatgpt_control import BackendClient, StdioBackendTransport"
            ),
            "browser_required_call": "createChatGPT({ agent: globalThis.agent })",
            "ordinary_shell_expected_blocker": "browser_bridge_unavailable",
        },
    }
    plan_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2, sort_keys=True), "utf-8")
    return plan, plan_path


def load_control_plan(path: str | Path) -> dict[str, Any]:
    raw = Path(path).read_text("utf-8")
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise ValueError("control plan must be a JSON object")
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(f"unsupported control plan schema {payload.get('schema_version')!r}")
    workflow = payload.get("workflow", {})
    workflow_name = workflow.get("name") if isinstance(workflow, dict) else None
    if workflow_name not in WORKFLOW_CATALOG:
        raise ValueError(f"unsupported workflow in plan {workflow_name!r}")
    return payload


def control_plan_json(plan: dict[str, Any], *, plan_path: Path | None = None) -> str:
    payload = dict(plan)
    if plan_path is not None:
        payload["plan_path"] = str(plan_path)
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)


def format_control_plan(plan: dict[str, Any], *, plan_path: Path) -> str:
    file_count = len(plan.get("files") or [])
    missing_files = sum(1 for row in plan.get("files", []) if not row.get("exists"))
    workflow = plan["workflow"]
    return "\n".join(
        [
            f"codex-chatgpt-control plan: {plan['request_id']}",
            f"path: {plan_path}",
            f"workflow: {workflow['name']} command={workflow['backend_command']}",
            f"task_kind: {plan['task_kind']}",
            f"prompt: {plan['prompt_storage_policy']} hash={plan['prompt_hash'][:16]}",
            f"thread: {plan['thread']['type']} existing_tab={plan['thread']['existing_tab']}",
            f"files: {file_count} missing={missing_files}",
            "safety: visible session only; stop on blockers; reports redacted by default",
            "evidence: ChatGPT output is citation_excluded until sources are restored separately",
        ]
    )


def render_invocation(plan: dict[str, Any], *, language: str) -> str:
    if language == "node":
        return _render_node_invocation(plan)
    if language == "python":
        return _render_python_invocation(plan)
    raise ValueError(f"unsupported invocation language {language!r}")


def execute_control_plan(
    plan: dict[str, Any],
    *,
    prompt: str | None = None,
    backend_command: tuple[str, ...] | None = None,
    allow_visible_chatgpt: bool = False,
    allow_npx_package: bool = False,
    timeout_seconds: float | None = None,
) -> dict[str, Any]:
    """Execute a plan through codex-chatgpt-control if the visible-session gate is open."""

    if not allow_visible_chatgpt:
        return _blocked_result(
            "visible_chatgpt_not_confirmed",
            "Pass --allow-visible-chatgpt after the user explicitly approves visible ChatGPT use.",
            plan=plan,
        )

    workflow = _plan_workflow_name(plan)
    prompt_text = prompt or plan.get("prompt")
    if WORKFLOW_CATALOG[workflow]["prompt_required"] and (
        not isinstance(prompt_text, str) or not prompt_text.strip()
    ):
        return _blocked_result(
            "prompt_redacted",
            "The plan redacted the prompt. Pass --prompt or create the plan with --include-prompt.",
            plan=plan,
        )

    try:
        from codex_chatgpt_control import (  # type: ignore[import-not-found]
            Agent,
            BackendClient,
            Runner,
            StdioBackendTransport,
        )
    except ImportError as exc:
        return _blocked_result(
            "python_sdk_unavailable",
            (
                "Install the codex-chatgpt-control Python package or use render output "
                "in a bridge host."
            ),
            plan=plan,
            error=str(exc),
        )

    resolved_command = _resolve_backend_command(
        backend_command=backend_command,
        allow_npx_package=allow_npx_package,
    )
    if resolved_command is None:
        return _blocked_result(
            "backend_runtime_unavailable",
            "Install codex-chatgpt-control-backend, pass --backend-command, "
            "or explicitly pass --allow-npx-package.",
            plan=plan,
        )

    backend = BackendClient(StdioBackendTransport(command=list(resolved_command)))
    try:
        if workflow == "runner_run":
            payload = _execution_payload(
                plan,
                prompt_text=prompt_text,
                timeout_seconds=timeout_seconds,
            )
            transport_agent = _transport_agent(plan)
            result = Runner(backend).run_sync(
                Agent(
                    name=transport_agent["name"],
                    instructions=transport_agent["instructions"],
                ),
                payload,
            )
            return _runner_result(plan, result)

        command_name = str(plan["workflow"]["backend_command"])
        payload = _execution_payload(plan, prompt_text=prompt_text, timeout_seconds=timeout_seconds)
        result = backend.request(command_name, payload)
        return _backend_command_result(plan, command_name, result)
    except Exception as exc:  # noqa: BLE001 - SDK/browser blockers must be normalized here.
        return _sdk_exception_result(plan, exc)
    finally:
        close = getattr(backend, "close", None)
        if callable(close):
            close()


def execution_result_json(result: dict[str, Any]) -> str:
    return json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True, default=str)


def format_execution_result(result: dict[str, Any]) -> str:
    lines = [
        f"codex-chatgpt-control run: {result.get('status', 'unknown')}",
        f"request_id: {result.get('request_id')}",
        f"workflow: {result.get('workflow')}",
        f"ok: {result.get('ok')}",
    ]
    if result.get("stop_reason"):
        lines.append(f"stop_reason: {result['stop_reason']}")
    if result.get("message"):
        lines.append(f"message: {result['message']}")
    if result.get("output_text"):
        lines.append("output:")
        lines.append(str(result["output_text"]))
    if result.get("interruptions"):
        lines.append("interruptions:")
        lines.append(json.dumps(result["interruptions"], ensure_ascii=False, indent=2))
    if result.get("raw_result") is not None:
        lines.append("raw_result:")
        lines.append(json.dumps(result["raw_result"], ensure_ascii=False, indent=2, default=str))
    lines.append("evidence: citation_excluded until sources are restored separately")
    return "\n".join(lines)


def _workflow_row(workflow: str) -> dict[str, Any]:
    source = WORKFLOW_CATALOG[workflow]
    return {
        "name": workflow,
        "backend_command": source["backend_command"],
        "node_method": source["node_method"],
        "description": source["description"],
        "risk": source["risk"],
        "prompt_required": source["prompt_required"],
    }


def _tool_check(name: str, version_arg: str) -> ToolCheck:
    path = shutil.which(name)
    if path is None:
        return ToolCheck(name=name, path=None, version=None, status="missing")
    try:
        result = subprocess.run(
            [path, version_arg],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ToolCheck(name=name, path=path, version=None, status="error")
    output = (result.stdout or result.stderr).strip()
    version = output.splitlines()[0] if output else None
    return ToolCheck(
        name=name,
        path=path,
        version=version,
        status="ok" if result.returncode == 0 else "error",
    )


def _global_package_status(package: str) -> str:
    npm = shutil.which("npm")
    if npm is None:
        return "not_checked"
    try:
        result = subprocess.run(
            [npm, "list", "-g", package, "--depth=0", "--json"],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return "unknown"
    if result.returncode == 0:
        try:
            payload = json.loads(result.stdout or "{}")
        except json.JSONDecodeError:
            return "unknown"
        deps = payload.get("dependencies") if isinstance(payload, dict) else None
        if isinstance(deps, dict) and package in deps:
            return "present"
    return "missing"


def _thread_policy(*, thread_url: str | None, existing_tab: bool) -> dict[str, Any]:
    if thread_url:
        return {
            "type": "url",
            "url": thread_url,
            "existing_tab": existing_tab,
            "note": "existing_tab claims a user-visible tab instead of replacing it",
        }
    return {"type": "new", "url": None, "existing_tab": False}


def _download_policy(download_dir: str | Path | None) -> dict[str, Any]:
    if download_dir is None:
        return {"enabled": False, "directory": None}
    path = Path(download_dir).expanduser()
    return {
        "enabled": True,
        "directory": str(path.absolute()),
        "requires_explicit_user_approved_directory": True,
    }


def _file_row(raw_path: str) -> dict[str, Any]:
    path = Path(raw_path).expanduser()
    resolved = path.resolve() if path.exists() else path.absolute()
    return {
        "path": str(resolved),
        "exists": path.exists(),
        "approved_by_cli_arg": True,
        "content_not_read": True,
    }


def _safety_contract() -> dict[str, Any]:
    return {
        "visible_session_only": True,
        "hidden_endpoints_allowed": False,
        "bypass_login_or_captcha_allowed": False,
        "user_approved_prompts_and_files_only": True,
        "public_destructive_paid_or_account_actions_require_confirmation": True,
        "redact_reports_by_default": True,
        "chatgpt_output_is_model_judgment_not_verified_truth": True,
    }


def _evidence_policy() -> dict[str, Any]:
    return {
        "chatgpt_output_is_evidence": False,
        "citation_excluded": True,
        "sources_must_be_restored_separately": True,
        "answer_claims_require_research_x_context_chunks": True,
        "copy_from_chatgpt_requires_user_review": True,
    }


def _default_instructions(task_kind: str) -> str:
    return (
        "Assist Codex with a visible, user-directed ChatGPT web consultation. "
        f"Task kind: {task_kind}. Return concise Markdown with assumptions, risks, and citations "
        "only when you have actual source URLs."
    )


def _request_id() -> str:
    return "chatgpt-control-" + uuid.uuid4().hex[:12]


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _preview(text: str, *, limit: int = 160) -> str:
    compact = " ".join(text.split())
    return compact if len(compact) <= limit else compact[: limit - 1] + "..."


def _blocked_result(
    stop_reason: str,
    message: str,
    *,
    plan: dict[str, Any],
    error: str | None = None,
) -> dict[str, Any]:
    result = {
        "schema_version": SCHEMA_VERSION,
        "request_id": plan.get("request_id"),
        "workflow": _plan_workflow_name(plan),
        "status": "blocked",
        "ok": False,
        "stop_reason": stop_reason,
        "message": message,
        "evidence_policy": plan.get("evidence_policy"),
    }
    if error:
        result["error"] = error
    return result


def _resolve_backend_command(
    *,
    backend_command: tuple[str, ...] | None,
    allow_npx_package: bool,
) -> tuple[str, ...] | None:
    if backend_command:
        return backend_command
    backend = shutil.which("codex-chatgpt-control-backend")
    if backend:
        return (backend,)
    if not allow_npx_package:
        return None
    return (
        "npx",
        "--yes",
        "--package",
        "codex-chatgpt-control",
        "codex-chatgpt-control-backend",
    )


def _plan_workflow_name(plan: dict[str, Any]) -> str:
    workflow = plan.get("workflow")
    if isinstance(workflow, dict) and workflow.get("name") in WORKFLOW_CATALOG:
        return str(workflow["name"])
    return "runner_run"


def _sdk_thread(plan_or_thread: dict[str, Any]) -> dict[str, Any]:
    thread = plan_or_thread.get("thread") if "thread" in plan_or_thread else plan_or_thread
    if not isinstance(thread, dict):
        thread = {}
    if thread.get("type") == "url" and thread.get("url"):
        return {
            "type": "url",
            "url": thread["url"],
            "existing_tab": bool(thread.get("existing_tab")),
        }
    return {"type": "new"}


def _sdk_payload(
    *,
    workflow: str,
    prompt: str | None,
    agent: dict[str, Any],
    thread: dict[str, Any],
    files: tuple[dict[str, Any], ...],
    download_dir: str | Path | None,
    response: dict[str, Any],
    report: dict[str, Any],
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "workflow": workflow,
        "thread": _sdk_thread(thread),
        "response": response,
        "report": report,
    }
    if WORKFLOW_CATALOG[workflow]["prompt_required"]:
        payload["input"] = prompt
        payload["prompt_redacted"] = prompt is None
    if workflow.startswith("runner_"):
        payload["agent"] = _transport_agent_from_agent(agent)
    if workflow in {"ask_with_files", "ask_and_download"}:
        payload["files"] = [{"path": row["path"]} for row in files]
    if workflow in {"ask_and_download", "download_latest"}:
        payload["download"] = _download_policy(download_dir)
    if workflow == "run_messages":
        payload["messages"] = [{"role": "user", "content": prompt}]
    return payload


def _execution_payload(
    plan: dict[str, Any],
    *,
    prompt_text: Any,
    timeout_seconds: float | None,
) -> dict[str, Any]:
    workflow = _plan_workflow_name(plan)
    base = dict(plan.get("sdk_payload") or {})
    if WORKFLOW_CATALOG[workflow]["prompt_required"]:
        visible_prompt = _visible_prompt(plan, prompt_text)
        base["input"] = visible_prompt
        base["prompt"] = visible_prompt
    if workflow == "run_messages":
        base["messages"] = [{"role": "user", "content": _visible_prompt(plan, prompt_text)}]
    if timeout_seconds is not None:
        base["timeout_seconds"] = timeout_seconds
    base["evidence_policy"] = _evidence_policy()
    return base


def _transport_agent(plan: dict[str, Any]) -> dict[str, str]:
    agent = plan.get("agent") if isinstance(plan.get("agent"), dict) else {}
    return _transport_agent_from_agent(agent)


def _transport_agent_from_agent(agent: dict[str, Any]) -> dict[str, str]:
    mode = str(agent.get("instructions_mode") or "visible_prefix")
    instructions = (
        ""
        if mode in {"metadata_only", "visible_prefix"}
        else str(agent.get("instructions") or "")
    )
    return {
        "name": str(agent.get("name") or "chatgpt-consultant"),
        "instructions": instructions,
    }


def _visible_prompt(plan: dict[str, Any], prompt_text: Any) -> Any:
    if not isinstance(prompt_text, str):
        return prompt_text
    agent = plan.get("agent") if isinstance(plan.get("agent"), dict) else {}
    if agent.get("instructions_mode") != "visible_prefix":
        return prompt_text
    instructions = str(agent.get("instructions") or "").strip()
    if not instructions:
        return prompt_text
    return f"{instructions}\n\n---\n\n{prompt_text}"


def _runner_result(plan: dict[str, Any], result: Any) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "request_id": plan.get("request_id"),
        "workflow": _plan_workflow_name(plan),
        "status": getattr(result, "status", None),
        "ok": bool(getattr(result, "ok", False)),
        "output_text": getattr(result, "output_text", None),
        "interruptions": getattr(result, "interruptions", None),
        "evidence_policy": plan.get("evidence_policy"),
    }


def _backend_command_result(plan: dict[str, Any], command_name: str, result: Any) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "request_id": plan.get("request_id"),
        "workflow": _plan_workflow_name(plan),
        "backend_command": command_name,
        "status": "ok",
        "ok": True,
        "raw_result": result,
        "evidence_policy": plan.get("evidence_policy"),
    }


def _sdk_exception_result(plan: dict[str, Any], exc: Exception) -> dict[str, Any]:
    text = f"{type(exc).__name__}: {exc}"
    lowered = text.lower()
    if "captcha" in lowered:
        stop_reason = "captcha"
    elif "login" in lowered or "auth" in lowered:
        stop_reason = "login_required"
    elif "rate" in lowered or "quota" in lowered:
        stop_reason = "rate_limit"
    elif "permission" in lowered or "upload" in lowered:
        stop_reason = "permission"
    elif "selector" in lowered or "locator" in lowered:
        stop_reason = "selector_drift"
    elif "bridge" in lowered or "browser" in lowered or "globalthis.agent" in lowered:
        stop_reason = "browser_bridge_unavailable"
    else:
        stop_reason = "browser_bridge_unavailable"
    return _blocked_result(stop_reason, text, plan=plan)


def _render_node_invocation(plan: dict[str, Any]) -> str:
    workflow = _plan_workflow_name(plan)
    method = WORKFLOW_CATALOG[workflow]["node_method"]
    prompt_expr = (
        json.dumps(plan["prompt"], ensure_ascii=False)
        if isinstance(plan.get("prompt"), str)
        else 'process.env.RESEARCH_X_CHATGPT_PROMPT ?? ""'
    )
    payload = dict(plan.get("sdk_payload") or {})
    if WORKFLOW_CATALOG[workflow]["prompt_required"]:
        payload["input"] = "__PROMPT__"
    payload_json = json.dumps(payload, ensure_ascii=False, indent=2)
    payload_json = payload_json.replace(
        '"__PROMPT__"',
        _node_visible_prompt_expression(plan, prompt_expr),
    )
    lines = [
        'import { createChatGPT } from "codex-chatgpt-control";',
        "",
        "const chatgpt = createChatGPT({ agent: globalThis.agent });",
    ]
    if workflow.startswith("runner_"):
        transport_agent = _transport_agent(plan)
        lines.extend(
            [
                "const consultant = chatgpt.agent({",
                f"  name: {json.dumps(transport_agent['name'])},",
                f"  instructions: {json.dumps(transport_agent['instructions'])}",
                "});",
                f"const result = await chatgpt.{method}(consultant, {payload_json});",
            ]
        )
    else:
        lines.append(f"const result = await chatgpt.{method}({payload_json});")
    lines.extend(
        [
            "if (!result.ok) {",
            "  console.log(JSON.stringify(result.interruptions ?? result, null, 2));",
            "} else {",
            "  console.log(result.output_text ?? JSON.stringify(result, null, 2));",
            "}",
        ]
    )
    return "\n".join(lines)


def _render_python_invocation(plan: dict[str, Any]) -> str:
    workflow = _plan_workflow_name(plan)
    command_name = WORKFLOW_CATALOG[workflow]["backend_command"]
    prompt_expr = (
        repr(plan["prompt"])
        if isinstance(plan.get("prompt"), str)
        else 'os.environ.get("RESEARCH_X_CHATGPT_PROMPT", "")'
    )
    payload = dict(plan.get("sdk_payload") or {})
    if WORKFLOW_CATALOG[workflow]["prompt_required"]:
        payload["input"] = "__PROMPT__"
    command = ["codex-chatgpt-control-backend"]
    if workflow == "runner_run":
        agent = _transport_agent(plan)
        thread = _sdk_thread(plan)
        response = plan.get("response", {"format": "markdown"})
        return "\n".join(
            [
                "import os",
                (
                    "from codex_chatgpt_control import Agent, BackendClient, Runner, "
                    "StdioBackendTransport"
                ),
                "",
                f"backend = BackendClient(StdioBackendTransport(command={command!r}))",
                "try:",
                "    runner = Runner(backend)",
                "    result = runner.run_sync(",
                "        Agent(",
                f"            name={agent['name']!r},",
                f"            instructions={agent['instructions']!r},",
                "        ),",
                "        {",
                f"            'input': {_python_visible_prompt_expression(plan, prompt_expr)},",
                f"            'thread': {thread!r},",
                f"            'response': {response!r},",
                "        },",
                "    )",
                "finally:",
                "    backend.close()",
                "print(result.status)",
                "print(result.output_text)",
            ]
        )

    payload_repr = repr(payload).replace(
        "'__PROMPT__'",
        _python_visible_prompt_expression(plan, prompt_expr),
    )
    return "\n".join(
        [
            "import os",
            "from codex_chatgpt_control import BackendClient, StdioBackendTransport",
            "",
            f"backend = BackendClient(StdioBackendTransport(command={command!r}))",
            "try:",
            f"    result = backend.request({command_name!r}, {payload_repr})",
            "finally:",
            "    backend.close()",
            "print(result)",
        ]
    )


def _node_visible_prompt_expression(plan: dict[str, Any], prompt_expr: str) -> str:
    agent = plan.get("agent") if isinstance(plan.get("agent"), dict) else {}
    if agent.get("instructions_mode") != "visible_prefix":
        return prompt_expr
    instructions = str(agent.get("instructions") or "").strip()
    if not instructions:
        return prompt_expr
    prefix = json.dumps(instructions + "\n\n---\n\n", ensure_ascii=False)
    return f"({prefix} + {prompt_expr})"


def _python_visible_prompt_expression(plan: dict[str, Any], prompt_expr: str) -> str:
    agent = plan.get("agent") if isinstance(plan.get("agent"), dict) else {}
    if agent.get("instructions_mode") != "visible_prefix":
        return prompt_expr
    instructions = str(agent.get("instructions") or "").strip()
    if not instructions:
        return prompt_expr
    prefix = instructions + "\n\n---\n\n"
    return f"({prefix!r} + {prompt_expr})"
