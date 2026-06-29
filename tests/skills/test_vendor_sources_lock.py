from __future__ import annotations

import tomllib
from pathlib import Path

UNPINNED_VALUES = {"", "TBD", "TBD_PINNED_COMMIT", "latest", "main", "master"}


def test_vendor_lock_keeps_external_sources_disabled_or_reference_only() -> None:
    manifest = tomllib.loads(Path(".codex/skill_manifest.lock").read_text(encoding="utf-8"))
    vendor_lock = Path("control/vendor_sources.lock.md").read_text(encoding="utf-8")

    assert all(entry["entry_type"] == "repo_skill" for entry in manifest["entries"])
    assert "Third-party Skills and tools are disabled" in vendor_lock
    assert "Reference-only" in vendor_lock


def test_single_file_wbs_is_pinned_local_tool_canary_not_evidence() -> None:
    vendor_lock = Path("control/vendor_sources.lock.md").read_text(encoding="utf-8")

    assert "single-file-wbs" in vendor_lock
    assert "v1.3.0" in vendor_lock
    assert "b1ef3d7e175dedfd9f4f34a9984437b174469c76" in vendor_lock
    assert "c92b71b83075d2c6ae1108166ccceb90590e901914e7b57ce9843a5c885bea97" in vendor_lock
    assert "Pinned local WBS/progress visualization tool" in vendor_lock
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


def test_codex_foundation_candidates_stay_out_of_research_x_vendor_lock() -> None:
    manifest = tomllib.loads(Path(".codex/skill_manifest.lock").read_text(encoding="utf-8"))
    vendor_lock = Path("control/vendor_sources.lock.md").read_text(encoding="utf-8")

    assert all(entry["entry_type"] == "repo_skill" for entry in manifest["entries"])
    assert "C:/Users/maasa/.codex/foundation/vendor_sources.lock.md" in vendor_lock
    for codex_candidate in (
        "superpowers",
        "superclaude-framework",
        "minimax-skills",
        "ian-xiaohei-illustrations",
        "agentmemory",
    ):
        assert codex_candidate not in vendor_lock


def test_vendor_lock_is_not_install_permission() -> None:
    vendor_lock = Path("control/vendor_sources.lock.md").read_text(encoding="utf-8")

    assert "not permission to install, clone, enable, or call" in vendor_lock
    assert "Catalogs are reference-only and must never be bulk-installed" in vendor_lock
    assert "Provider-backed sources remain blocked by the no-quota freeze" in vendor_lock
    assert "`adopt`, `bridge`, `staging`, `provider_gated`, or `historical`" in vendor_lock
    assert "Codex foundation candidates belong to `maasa/.codex`" in vendor_lock
    assert "C:/Users/maasa/.codex/foundation/vendor_sources.lock.md" in vendor_lock
