from __future__ import annotations

import tomllib
from pathlib import Path


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
    assert "not research_x core or evidence" in vendor_lock
    assert "no image generation without gate" in vendor_lock


def test_vendor_lock_is_not_install_permission() -> None:
    vendor_lock = Path(".codex/vendor_sources.lock.md").read_text(encoding="utf-8")

    assert "not permission to install, clone, enable, or call" in vendor_lock
    assert "Catalogs are reference-only and must never be bulk-installed" in vendor_lock
    assert "Provider-backed sources remain blocked by the no-quota freeze" in vendor_lock
