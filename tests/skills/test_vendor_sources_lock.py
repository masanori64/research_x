from __future__ import annotations

import tomllib
from pathlib import Path

import pytest

UNPINNED_VALUES = {"", "TBD", "TBD_PINNED_COMMIT", "latest", "main", "master"}
CODEX_VENDOR_LOCK = Path("C:/Users/maasa/.codex/foundation/vendor_sources.lock.md")


def _codex_vendor_lock_text() -> str:
    if not CODEX_VENDOR_LOCK.exists():
        pytest.skip("global .codex foundation vendor lock is outside the portable repository")
    return CODEX_VENDOR_LOCK.read_text(encoding="utf-8")


def test_vendor_lock_keeps_external_sources_disabled_or_reference_only() -> None:
    manifest = tomllib.loads(Path(".codex/skill_manifest.lock").read_text(encoding="utf-8"))
    vendor_lock = Path("control/vendor_sources.lock.md").read_text(encoding="utf-8")

    assert all(entry["entry_type"] == "repo_skill" for entry in manifest["entries"])
    assert "Third-party Skills and tools are disabled" in vendor_lock
    assert "Reference-only" in vendor_lock


def test_ian_xiaohei_is_creative_optional_not_evidence_or_enabled() -> None:
    vendor_lock = _codex_vendor_lock_text()

    assert "ian-xiaohei-illustrations" in vendor_lock
    assert "686575741a61e2c0be5e4c6d3615ebf6217dd322" in vendor_lock
    assert "Use only for explicit visual-planning requests" in vendor_lock
    assert "generated images are not evidence" in vendor_lock
    assert "v1.0.0" in vendor_lock


def test_superpowers_is_pinned_but_disabled_until_full_review() -> None:
    vendor_lock = _codex_vendor_lock_text()

    assert "superpowers" in vendor_lock
    assert "f2cbfbefebbfef77321e4c9abc9e949826bea9d7" in vendor_lock
    assert "Disabled; review then optional" in vendor_lock
    assert "no full source/script/hook audit yet" in vendor_lock


def test_agentmemory_is_pinned_but_disabled_until_hook_and_retention_review() -> None:
    vendor_lock = _codex_vendor_lock_text()

    assert "agentmemory" in vendor_lock
    assert "25158519d5d68b9060a97ba5bdcccc3e1aba6d79" in vendor_lock
    assert "source-review-required" in vendor_lock
    assert "hook/MCP/auto-capture" in vendor_lock
    assert "no install now" in vendor_lock


def test_single_file_wbs_is_pinned_local_tool_canary_not_evidence() -> None:
    vendor_lock = Path("control/vendor_sources.lock.md").read_text(encoding="utf-8")

    assert "single-file-wbs" in vendor_lock
    assert "v1.2.0" in vendor_lock
    assert "322895a23f49028b53ae8c8a1710d6db45cdf726" in vendor_lock
    assert "Pinned local tool canary" in vendor_lock
    assert "No plugin, MCP, hook, provider, hosted service, or evidence promotion" in vendor_lock


def test_retired_diagram_tool_is_reference_only_after_decommission() -> None:
    vendor_lock = Path("control/vendor_sources.lock.md").read_text(encoding="utf-8")
    retired_name = "pdg" + "kit"

    assert retired_name in vendor_lock
    assert f"@shibayama/{retired_name}" in vendor_lock
    assert "0.1.2" in vendor_lock
    assert "Reference-only historical source" in vendor_lock
    assert "local tool lane has been decommissioned" in vendor_lock
    assert "Do not install, restore, invoke, register MCP" in vendor_lock
    assert "D2/Marp boundary" in vendor_lock


def test_unpinned_external_candidates_stay_in_source_lock_not_manifest() -> None:
    manifest = tomllib.loads(Path(".codex/skill_manifest.lock").read_text(encoding="utf-8"))
    codex_vendor_lock = _codex_vendor_lock_text()

    assert all(entry["entry_type"] == "repo_skill" for entry in manifest["entries"])
    assert "superclaude-framework" in codex_vendor_lock
    assert "minimax-skills" in codex_vendor_lock
    assert "Reference only" in codex_vendor_lock or "Disabled" in codex_vendor_lock


def test_vendor_lock_is_not_install_permission() -> None:
    vendor_lock = Path("control/vendor_sources.lock.md").read_text(encoding="utf-8")

    assert "not permission to install, clone, enable, or call" in vendor_lock
    assert "Catalogs are reference-only and must never be bulk-installed" in vendor_lock
    assert "Provider-backed sources remain blocked by the no-quota freeze" in vendor_lock
    assert "`adopt`, `bridge`, `staging`, `provider_gated`, or `historical`" in vendor_lock
    assert "Codex foundation candidates belong to `maasa/.codex`" in vendor_lock
    assert "C:/Users/maasa/.codex/foundation/vendor_sources.lock.md" in vendor_lock
