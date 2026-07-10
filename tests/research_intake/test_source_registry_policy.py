from __future__ import annotations

from pathlib import Path

from research_x.research_intake.pipeline import (
    LOCAL_SOURCE_TYPES,
    POLICY_CONTROLLED_ENABLEMENT,
    PROVIDER_SOURCE_TYPES,
    load_registry,
    validate_registry,
)


def test_source_registry_keeps_provider_sources_policy_controlled() -> None:
    registry = load_registry(Path("control/research_intake/source_registry.toml"))

    provider_sources = [
        source for source in registry.sources if source.source_type in PROVIDER_SOURCE_TYPES
    ]

    assert provider_sources
    assert all(
        source.enabled_when in POLICY_CONTROLLED_ENABLEMENT
        for source in provider_sources
    )
    assert validate_registry(registry) == []


def test_source_registry_names_external_provider_candidates_with_policy_control() -> None:
    registry = load_registry(Path("control/research_intake/source_registry.toml"))
    sources = {source.source_id: source for source in registry.sources}
    provider_expected = {
        "future_serper_external_search",
        "future_brave_llm_context",
        "future_jina_reader",
        "future_firecrawl",
        "future_tavily",
        "future_exa",
        "future_perplexity",
        "future_searxng_local",
    }

    assert set(sources) >= provider_expected
    for source_id in provider_expected:
        source = sources[source_id]
        assert source.enabled_when in POLICY_CONTROLLED_ENABLEMENT
        assert source.policy.fetch_mode == "authorized_candidate_fetch"
        assert source.policy.allow_network is True
        assert source.policy.allow_provider is True


def test_source_registry_has_no_codex_foundation_or_unresolved_source_lock_entries() -> None:
    text = Path("control/research_intake/source_registry.toml").read_text(encoding="utf-8")

    assert "source-lock-needed:" not in text
    assert "Codex Skills" not in text
    assert "codex ai tools" not in text


def test_source_registry_local_sources_are_metadata_only() -> None:
    registry = load_registry(Path("control/research_intake/source_registry.toml"))
    local_sources = [
        source for source in registry.sources if source.source_type in LOCAL_SOURCE_TYPES
    ]

    assert local_sources
    for source in local_sources:
        assert source.policy.fetch_mode == "metadata_only"
        assert source.policy.allow_network is False
        assert source.policy.allow_provider is False
        assert source.quality_hint in {"official", "high", "medium", "unknown", "low"}


def test_research_intake_contract_is_owned_by_code_and_control_registry() -> None:
    registry = load_registry(Path("control/research_intake/source_registry.toml"))

    assert all(
        source.policy.fetch_mode == "metadata_only"
        for source in registry.sources
        if source.source_type in LOCAL_SOURCE_TYPES
    )
    assert all(
        source.enabled_when in POLICY_CONTROLLED_ENABLEMENT
        for source in registry.sources
        if source.source_type in PROVIDER_SOURCE_TYPES
    )
    assert not Path(".agents/skills").exists()
