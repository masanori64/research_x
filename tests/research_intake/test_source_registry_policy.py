from __future__ import annotations

from pathlib import Path

from research_x.research_intake.pipeline import (
    LOCAL_SOURCE_TYPES,
    PROVIDER_SOURCE_TYPES,
    load_registry,
    validate_registry,
)


def test_source_registry_keeps_provider_sources_disabled() -> None:
    registry = load_registry(Path("control/research_intake/source_registry.toml"))

    provider_sources = [
        source for source in registry.sources if source.source_type in PROVIDER_SOURCE_TYPES
    ]

    assert provider_sources
    assert all(source.enabled_when == "disabled" for source in provider_sources)
    assert validate_registry(registry) == []


def test_source_registry_names_external_provider_candidates_without_enabling_them() -> None:
    registry = load_registry(Path("control/research_intake/source_registry.toml"))
    sources = {source.source_id: source for source in registry.sources}
    expected = {
        "future_serper_external_search",
        "future_brave_llm_context",
        "future_jina_reader",
        "future_firecrawl",
        "future_tavily",
        "future_exa",
        "future_perplexity",
        "future_searxng_local",
    }

    assert set(sources) >= expected
    for source_id in expected:
        source = sources[source_id]
        assert source.enabled_when == "disabled"
        assert source.policy.fetch_mode == "metadata_only"
        assert source.policy.allow_network is False
        assert source.policy.allow_provider is False


def test_source_registry_has_no_codex_foundation_or_unresolved_source_lock_entries() -> None:
    text = Path("control/research_intake/source_registry.toml").read_text(encoding="utf-8")

    assert "source-lock-needed:" not in text
    assert "Codex Skills" not in text
    assert "codex ai tools" not in text
    assert "Edge Add-ons" not in text


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


def test_risky_manual_url_candidates_must_stay_disabled(tmp_path: Path) -> None:
    registry_path = tmp_path / "source_registry.toml"
    registry_text = Path("control/research_intake/source_registry.toml").read_text(
        encoding="utf-8"
    )
    registry_path.write_text(
        registry_text.replace(
            'source_id = "manual_cognee_repo"\n'
            'source_type = "manual_url"\n'
            'locator = "https://github.com/topoteretes/cognee"\n'
            'enabled_when = "disabled"',
            'source_id = "manual_cognee_repo"\n'
            'source_type = "manual_url"\n'
            'locator = "https://github.com/topoteretes/cognee"\n'
            'enabled_when = "always"',
        ),
        encoding="utf-8",
    )

    errors = validate_registry(load_registry(registry_path))

    assert any(
        "manual_cognee_repo: risky manual_url storage_rights requires disabled" in error
        for error in errors
    )


def test_research_intake_skill_locks_discovery_not_evidence() -> None:
    policy = Path(".agents/skills/research-x-research-intake/SKILL.md").read_text(
        encoding="utf-8"
    )

    assert "candidate locator != fetched source != source bundle" in policy
    assert "allow_network` must be false" in policy
    assert "Provider-backed sources must stay disabled" in policy
