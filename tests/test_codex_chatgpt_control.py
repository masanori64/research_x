from __future__ import annotations

import json
from pathlib import Path

import research_x.codex_chatgpt_control as chatgpt_control
from research_x.cli import main
from research_x.codex_chatgpt_control import (
    SCHEMA_VERSION,
    build_control_plan,
    execute_control_plan,
    local_capabilities,
    render_invocation,
)


def test_build_control_plan_redacts_prompt_and_records_workflow(tmp_path: Path) -> None:
    plan, plan_path = build_control_plan(
        prompt="review this architecture",
        task_kind="review",
        workflow="ask_with_files",
        out_dir=tmp_path,
        files=("missing.txt",),
    )

    saved = json.loads(plan_path.read_text("utf-8"))
    assert saved["schema_version"] == SCHEMA_VERSION
    assert saved["prompt"] is None
    assert saved["prompt_storage_policy"] == "redacted"
    assert saved["workflow"]["name"] == "ask_with_files"
    assert saved["workflow"]["backend_command"] == "askWithFiles"
    assert saved["files"][0]["content_not_read"] is True
    assert saved["evidence_policy"]["citation_excluded"] is True
    assert plan["backend_protocol"]["capability_commands"]


def test_render_node_includes_file_workflow_and_visible_prefix(tmp_path: Path) -> None:
    plan, _ = build_control_plan(
        prompt="inspect",
        task_kind="review",
        workflow="ask_with_files",
        out_dir=tmp_path,
        files=("README.md",),
        instructions="Visible instruction.",
        include_prompt=True,
    )

    rendered = render_invocation(plan, language="node")

    assert "createChatGPT" in rendered
    assert "chatgpt.askWithFiles" in rendered
    assert "Visible instruction." in rendered
    assert "README.md" in rendered


def test_metadata_only_does_not_send_agent_instructions(tmp_path: Path) -> None:
    plan, _ = build_control_plan(
        prompt="inspect",
        task_kind="review",
        workflow="runner_run",
        out_dir=tmp_path,
        instructions="Do not send as visible or runner instruction.",
        instructions_mode="metadata_only",
        include_prompt=True,
    )

    rendered = render_invocation(plan, language="python")

    assert "instructions=''" in rendered
    assert "Do not send as visible or runner instruction." not in rendered


def test_run_plan_blocks_without_visible_chatgpt_permission(tmp_path: Path) -> None:
    plan, _ = build_control_plan(
        prompt="inspect",
        task_kind="review",
        workflow="ask",
        out_dir=tmp_path,
    )

    result = execute_control_plan(plan)

    assert result["ok"] is False
    assert result["status"] == "blocked"
    assert result["stop_reason"] == "visible_chatgpt_not_confirmed"


def test_run_plan_blocks_npx_package_without_explicit_permission(
    tmp_path: Path,
    monkeypatch,
) -> None:
    plan, _ = build_control_plan(
        prompt="inspect",
        task_kind="review",
        workflow="ask",
        out_dir=tmp_path,
        include_prompt=True,
    )

    monkeypatch.setattr(chatgpt_control.shutil, "which", lambda _name: None)

    result = execute_control_plan(
        plan,
        allow_visible_chatgpt=True,
    )

    assert result["ok"] is False
    assert result["status"] == "blocked"
    assert result["stop_reason"] in {
        "backend_runtime_unavailable",
        "python_sdk_unavailable",
    }


def test_local_capabilities_are_contract_inventory() -> None:
    payload = local_capabilities()

    assert payload["mode"] == "local_contract_inventory"
    assert payload["ordinary_shell_expected_blocker"] == "browser_bridge_unavailable"
    assert payload["evidence_policy"]["citation_excluded"] is True
    assert "askWithFiles" in payload["upstream_command_surface"]
    assert "responses_create" in payload["supported_workflows"]
    assert "download_latest" in payload["supported_workflows"]


def test_render_extended_upstream_workflows(tmp_path: Path) -> None:
    responses_plan, _ = build_control_plan(
        prompt="compare",
        task_kind="review",
        workflow="responses_create",
        out_dir=tmp_path / "responses",
        include_prompt=True,
    )
    download_plan, _ = build_control_plan(
        prompt="",
        task_kind="download",
        workflow="download_latest",
        out_dir=tmp_path / "download",
        download_dir=tmp_path / "downloads",
    )

    assert "chatgpt.responses.create" in render_invocation(responses_plan, language="node")
    rendered_download = render_invocation(download_plan, language="node")
    assert "chatgpt.downloadLatest" in rendered_download
    assert "downloads" in rendered_download


def test_cli_plan_render_and_blocked_run(tmp_path: Path, capsys) -> None:
    out_dir = tmp_path / "plans"
    rc = main(
        [
            "codex-chatgpt-control",
            "plan",
            "--prompt",
            "inspect",
            "--workflow",
            "ask",
            "--out",
            str(out_dir),
            "--json",
        ]
    )
    assert rc == 0
    plan_payload = json.loads(capsys.readouterr().out)
    plan_path = plan_payload["plan_path"]

    rc = main(["codex-chatgpt-control", "render", "--plan", plan_path, "--language", "node"])
    assert rc == 0
    assert "chatgpt.ask" in capsys.readouterr().out

    rc = main(["codex-chatgpt-control", "run-plan", "--plan", plan_path, "--json"])
    assert rc == 2
    result_payload = json.loads(capsys.readouterr().out)
    assert result_payload["stop_reason"] == "visible_chatgpt_not_confirmed"
