from __future__ import annotations

from pathlib import Path

from research_x.research_intake.pipeline import (
    LOCAL_SOURCE_TYPES,
    PROVIDER_SOURCE_TYPES,
    load_registry,
    validate_registry,
)


def test_source_registry_keeps_provider_sources_disabled() -> None:
    registry = load_registry(Path(".codex/research_intake/source_registry.toml"))

    provider_sources = [
        source for source in registry.sources if source.source_type in PROVIDER_SOURCE_TYPES
    ]

    assert provider_sources
    assert all(source.enabled_when == "disabled" for source in provider_sources)
    assert validate_registry(registry) == []


def test_source_registry_local_sources_are_metadata_only() -> None:
    registry = load_registry(Path(".codex/research_intake/source_registry.toml"))
    local_sources = [
        source for source in registry.sources if source.source_type in LOCAL_SOURCE_TYPES
    ]

    assert local_sources
    for source in local_sources:
        assert source.policy.fetch_mode == "metadata_only"
        assert source.policy.allow_network is False
        assert source.policy.allow_provider is False
        assert source.quality_hint in {"official", "high", "medium", "unknown", "low"}


def test_research_intake_policy_doc_locks_discovery_not_evidence() -> None:
    policy = Path("docs/research-intake.md").read_text(encoding="utf-8")

    assert "candidate locator != fetched source != source bundle" in policy
    assert "allow_network` must be false" in policy
    assert "Provider-backed sources must stay disabled" in policy
