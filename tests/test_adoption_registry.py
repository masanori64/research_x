from __future__ import annotations

import json
import shutil
from pathlib import Path

from research_x.adoption_registry import (
    adoption_audit,
    adoption_candidates,
    validate_adoption_registry,
)
from research_x.cli import main

REGISTRY = Path("control/adoption_registry.toml")


def test_research_x_adoption_registry_is_valid() -> None:
    assert validate_adoption_registry(REGISTRY) == []

    audit = adoption_audit(REGISTRY)
    assert audit["status"] == "ok"
    assert audit["counts"]["research_x_tool:adopt"] >= 3
    assert audit["counts"]["research_x_tool:approved_experimental"] >= 5
    assert audit["counts"]["codex_foundation:bridge"] == 1


def test_research_x_registry_covers_plan_candidate_families() -> None:
    text = REGISTRY.read_text(encoding="utf-8").casefold()
    required_names = {
        "firecrawl",
        "jina",
        "brave",
        "serper",
        "searxng",
        "tavily",
        "exa",
        "perplexity",
        "occ-rag",
        "saas",
        "bosun",
        "warrantbench",
        "zvec",
        "turbovec",
        "paddleocr",
        "mistral",
        "manga",
        "gemini",
        "d2",
        "marp",
        "archify",
        "yaml",
        "pdgkit",
    }

    missing = sorted(name for name in required_names if name not in text)
    assert missing == []


def test_research_x_registry_has_no_unresolved_source_locks() -> None:
    text = REGISTRY.read_text(encoding="utf-8")

    assert "needs_source_lock" not in text
    assert "source-lock-needed:" not in text


def test_adoption_candidates_have_stop_conditions() -> None:
    candidates = adoption_candidates(REGISTRY)

    assert candidates
    assert all(item.stop_condition.strip() for item in candidates)
    provider_entries = [item for item in candidates if item.provider_or_quota]
    assert all("provider" in item.stop_condition.lower() for item in provider_entries)


def test_adoption_registry_source_refs_must_exist_in_vendor_lock(tmp_path: Path) -> None:
    registry = tmp_path / "adoption_registry.toml"
    source_lock = tmp_path / "vendor_sources.lock.toml"
    shutil.copy2(REGISTRY, registry)
    shutil.copy2(Path("control/vendor_sources.lock.toml"), source_lock)

    source_lock.write_text(
        source_lock.read_text(encoding="utf-8").replace(
            'ref = "S39"',
            'ref = "S99"',
        ),
        encoding="utf-8",
    )

    errors = validate_adoption_registry(registry, source_lock_path=source_lock)

    assert "source lock missing row for S39" in errors


def test_codex_foundation_entries_are_bridge_only_in_research_x() -> None:
    candidates = adoption_candidates(REGISTRY)
    codex_entries = [item for item in candidates if item.owner_surface == "codex_foundation"]

    assert [item.name for item in codex_entries] == ["codex_foundation_registry_bridge"]
    assert all(item.adoption_shape == "bridge" for item in codex_entries)
    assert all(item.enabled is False for item in codex_entries)
    assert all(
        item.source_url == "${CODEX_HOME}/foundation/codex-foundation-registry.toml"
        for item in codex_entries
    )


def test_provider_candidates_are_policy_controlled_and_not_runtime_enabled() -> None:
    candidates = adoption_candidates(REGISTRY)
    provider_entries = [item for item in candidates if item.provider_or_quota]

    assert provider_entries
    assert all(item.adoption_shape == "approved_experimental" for item in provider_entries)
    assert all(item.status == "active_implementation" for item in provider_entries)
    assert all(item.enabled is False for item in provider_entries)
    assert all(
        "effective runtime control state" in item.stop_condition for item in provider_entries
    )
    assert all("API Budget Guard" in item.stop_condition for item in provider_entries)
    assert all("source restoration" in item.stop_condition for item in provider_entries)
    assert all(
        any(
            token in item.first_local_step.casefold()
            for token in ("policy", "fake", "source-candidate", "provider")
        )
        for item in provider_entries
    )


def test_provider_policy_condition_tokens_are_validation_errors(tmp_path: Path) -> None:
    registry = tmp_path / "adoption_registry.toml"
    shutil.copy2(REGISTRY, registry)
    text = registry.read_text(encoding="utf-8")
    registry.write_text(
        text.replace("effective runtime control state", "runtime state", 1),
        encoding="utf-8",
    )

    errors = validate_adoption_registry(registry, source_lock_path=None)

    assert any(
        "provider policy condition missing: effective runtime control state" in error
        for error in errors
    )


def test_staging_candidates_stay_disabled_and_unimplemented() -> None:
    candidates = adoption_candidates(REGISTRY)
    staging = [item for item in candidates if item.adoption_shape == "staging"]

    assert staging
    assert all(item.status == "staged" for item in staging)
    assert all(item.enabled is False for item in staging)
    assert all("evidence promotion" in item.stop_condition for item in staging)


def test_media_ocr_provider_and_install_lanes_stay_gated() -> None:
    candidates = {item.name: item for item in adoption_candidates(REGISTRY)}

    for name in ("paddleocr", "paddleocr_vl", "manga_ocr"):
        item = candidates[name]
        assert item.status == "staged"
        assert item.enabled is False
        assert item.provider_or_quota is False
        assert "dependency install" in item.stop_condition
        assert "model download" in item.stop_condition
        assert "evidence promotion" in item.stop_condition

    for name in ("mistral_ocr", "gemini_media_embedding"):
        item = candidates[name]
        assert item.status == "active_implementation"
        assert item.enabled is False
        assert item.provider_or_quota is True
        assert "effective runtime control state" in item.stop_condition
        assert "API Budget Guard" in item.stop_condition


def test_adopted_research_x_artifacts_exist_and_pdgkit_is_historical() -> None:
    candidates = adoption_candidates(REGISTRY)
    adopted = [
        item
        for item in candidates
        if item.owner_surface == "research_x_tool" and item.adoption_shape == "adopt"
    ]
    pdgkit = next(item for item in candidates if item.name == "pdgkit")

    assert adopted
    assert all(Path(item.active_artifact).exists() for item in adopted)
    assert pdgkit.owner_surface == "historical"
    assert pdgkit.adoption_shape == "historical"
    assert pdgkit.enabled is False


def test_adoption_audit_cli_emits_json(capsys) -> None:
    assert main(["adoption", "audit", "--json"]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "ok"
    assert payload["counts"]["research_x_tool:staging"] >= 8
