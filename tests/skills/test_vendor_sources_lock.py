from __future__ import annotations

import tomllib
from pathlib import Path

UNPINNED_VALUES = {"", "TBD", "TBD_PINNED_COMMIT", "latest", "main", "master"}


def test_vendor_lock_keeps_external_sources_disabled_or_reference_only() -> None:
    manifest = tomllib.loads(Path(".codex/skill_manifest.lock").read_text(encoding="utf-8"))
    entries = manifest["entries"]
    external_entries = [entry for entry in entries if entry["entry_type"] != "repo_skill"]

    assert external_entries
    assert all(entry["enabled"] is False for entry in external_entries)
    assert all(entry["implicit_invocation"] is False for entry in external_entries)


def test_ian_xiaohei_is_creative_optional_not_evidence_or_enabled() -> None:
    manifest = tomllib.loads(Path(".codex/skill_manifest.lock").read_text(encoding="utf-8"))
    entry = next(
        entry for entry in manifest["entries"] if entry["name"] == "ian-xiaohei-illustrations"
    )
    vendor_lock = Path(".codex/vendor_sources.lock.md").read_text(encoding="utf-8")

    assert entry["enabled"] is False
    assert entry["scope"] == "creative_optional"
    assert entry["decision"] == "not_research_x_core"
    assert entry["review_status"] == "pinned_license_checked"
    assert entry["commit"] == "686575741a61e2c0be5e4c6d3615ebf6217dd322"
    assert "not research_x core or evidence" in vendor_lock
    assert "no image generation without gate" in vendor_lock
    assert "v1.0.0" in vendor_lock


def test_superpowers_is_pinned_but_disabled_until_full_review() -> None:
    manifest = tomllib.loads(Path(".codex/skill_manifest.lock").read_text(encoding="utf-8"))
    entry = next(entry for entry in manifest["entries"] if entry["name"] == "superpowers")
    vendor_lock = Path(".codex/vendor_sources.lock.md").read_text(encoding="utf-8")

    assert entry["enabled"] is False
    assert entry["implicit_invocation"] is False
    assert entry["review_status"] == "pinned_license_checked"
    assert entry["commit"] == "f2cbfbefebbfef77321e4c9abc9e949826bea9d7"
    assert entry["negative_trigger_tests"] == "required_before_enable"
    assert "no full source/script/hook audit yet" in vendor_lock


def test_agentmemory_is_pinned_but_disabled_until_hook_and_retention_review() -> None:
    manifest = tomllib.loads(Path(".codex/skill_manifest.lock").read_text(encoding="utf-8"))
    entry = next(entry for entry in manifest["entries"] if entry["name"] == "agentmemory")
    vendor_lock = Path(".codex/vendor_sources.lock.md").read_text(encoding="utf-8")

    assert entry["enabled"] is False
    assert entry["implicit_invocation"] is False
    assert entry["review_status"] == "pinned_license_surface_checked"
    assert entry["risk"] == "high"
    assert entry["commit"] == "25158519d5d68b9060a97ba5bdcccc3e1aba6d79"
    assert entry["allowed_scripts"] == "disabled"
    assert entry["negative_trigger_tests"] == "required_before_enable"
    assert "source-review-required" in vendor_lock
    assert "hook/MCP/auto-capture" in vendor_lock
    assert "no install now" in vendor_lock


def test_single_file_wbs_is_pinned_local_tool_canary_not_evidence() -> None:
    vendor_lock = Path(".codex/vendor_sources.lock.md").read_text(encoding="utf-8")

    assert "single-file-wbs" in vendor_lock
    assert "v1.2.0" in vendor_lock
    assert "322895a23f49028b53ae8c8a1710d6db45cdf726" in vendor_lock
    assert "Pinned local tool canary" in vendor_lock
    assert "No plugin, MCP, hook, provider, hosted service, or evidence promotion" in vendor_lock


def test_retired_diagram_tool_is_reference_only_after_decommission() -> None:
    vendor_lock = Path(".codex/vendor_sources.lock.md").read_text(encoding="utf-8")
    retired_name = "pdg" + "kit"

    assert retired_name in vendor_lock
    assert f"@shibayama/{retired_name}" in vendor_lock
    assert "0.1.2" in vendor_lock
    assert "Reference-only historical source" in vendor_lock
    assert "local tool lane has been decommissioned" in vendor_lock
    assert "Do not install, restore, invoke, register MCP" in vendor_lock
    assert "D2/Marp boundary" in vendor_lock


def test_unpinned_external_entries_are_not_enabled_or_approved() -> None:
    manifest = tomllib.loads(Path(".codex/skill_manifest.lock").read_text(encoding="utf-8"))
    entries = manifest["entries"]
    unpinned_external_entries = [
        entry
        for entry in entries
        if entry["entry_type"] != "repo_skill" and str(entry["commit"]) in UNPINNED_VALUES
    ]

    assert unpinned_external_entries
    for entry in unpinned_external_entries:
        assert entry["enabled"] is False, entry["name"]
        assert entry["implicit_invocation"] is False, entry["name"]
        assert entry["review_status"] != "approved", entry["name"]


def test_vendor_lock_is_not_install_permission() -> None:
    vendor_lock = Path(".codex/vendor_sources.lock.md").read_text(encoding="utf-8")

    assert "not permission to install, clone, enable, or call" in vendor_lock
    assert "Catalogs are reference-only and must never be bulk-installed" in vendor_lock
    assert "Provider-backed sources remain blocked by the no-quota freeze" in vendor_lock
    assert "`adopt`, `bridge`, `staging`, `provider_gated`, or `historical`" in vendor_lock
    assert "Codex foundation candidates belong to `maasa/.codex`" in vendor_lock
    assert ".codex/adoption_registry.toml" in vendor_lock
    assert "enable, install, clone, call, or promote" in vendor_lock
