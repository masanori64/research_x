from __future__ import annotations

from pathlib import Path

from research_x.adoption_registry import adoption_candidates
from research_x.research_intake.pipeline import (
    LOCAL_SOURCE_TYPES,
    PROVIDER_SOURCE_TYPES,
    SOURCE_CANDIDATE_EVIDENCE_STATUS,
    SourcePolicy,
    SourceRegistry,
    SourceSubscription,
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


def test_enabled_manual_urls_have_source_governance_owner_paths() -> None:
    registry = load_registry(Path("control/research_intake/source_registry.toml"))
    adoption_names = {
        candidate.name for candidate in adoption_candidates("control/adoption_registry.toml")
    }
    source_lock = Path("control/vendor_sources.lock.md").read_text(encoding="utf-8")
    enabled_manual_sources = [
        source
        for source in registry.sources
        if source.source_type == "manual_url" and source.enabled_when == "always"
    ]

    assert enabled_manual_sources
    for source in enabled_manual_sources:
        governance = source.source_governance

        assert governance is not None
        assert governance.evidence_status == SOURCE_CANDIDATE_EVIDENCE_STATUS
        assert governance.promotion_boundary
        assert "evidence" in governance.notes

        if governance.source_ref:
            assert f"| {governance.source_ref} |" in source_lock
        if governance.owner_status == "adoption_registry":
            assert governance.adoption_candidate in adoption_names
        elif governance.owner_status == "codex_foundation":
            assert governance.owner_surface == "codex_foundation"
            assert governance.adoption_candidate
        elif governance.owner_status == "source_registry_only":
            assert "not adopted" in governance.notes.casefold()
        else:
            assert governance.owner_status == "vendor_lock"


def test_enabled_manual_url_without_source_governance_is_rejected() -> None:
    registry = SourceRegistry(
        registry_id="missing_governance_registry",
        sources=(
            SourceSubscription(
                source_id="manual_without_governance",
                source_type="manual_url",
                locator="https://example.com/source",
                enabled_when="always",
                quality_hint="medium",
                policy=SourcePolicy(
                    fetch_mode="metadata_only",
                    allow_network=False,
                    allow_provider=False,
                    storage_rights="unfetched_public_candidate",
                ),
            ),
        ),
    )

    errors = validate_registry(registry)

    assert "manual_without_governance: enabled manual_url requires source_governance" in errors


def test_okf_source_metadata_shape_is_candidate_only() -> None:
    registry = load_registry(Path("control/research_intake/source_registry.toml"))
    sources = {source.source_id: source for source in registry.sources}

    for source_id in ("manual_okf_zenn", "manual_okf_google_cloud"):
        source = sources[source_id]
        metadata = source.okf_source_metadata

        assert metadata is not None
        assert metadata.as_dict().items() >= {
            "format": "okf_source_candidate_v1",
            "type": "article",
            "resource": source.locator,
            "owner": "research_x",
            "review_status": "candidate",
            "evidence_status": "not_evidence_until_fetched_and_chunked",
            "answer_support_allowed": False,
            "citation_excluded": True,
        }.items()
        assert metadata.tags
        assert source.policy.fetch_mode == "metadata_only"
        assert source.policy.allow_network is False
        assert source.policy.allow_provider is False

    assert validate_registry(registry) == []


def test_okf_source_metadata_rejects_invalid_review_status_and_timestamp(
    tmp_path: Path,
) -> None:
    registry_path = tmp_path / "source_registry.toml"
    registry_text = Path("control/research_intake/source_registry.toml").read_text(
        encoding="utf-8"
    )

    registry_path.write_text(
        registry_text.replace('review_status = "candidate"', 'review_status = "approved"', 1),
        encoding="utf-8",
    )
    review_errors = validate_registry(load_registry(registry_path))

    assert any(
        "manual_okf_zenn: okf_source_metadata.review_status must be one of" in error
        for error in review_errors
    )

    registry_path.write_text(
        registry_text.replace(
            'timestamp = "2026-07-01T00:00:00Z"',
            'timestamp = "not-a-timestamp"',
            1,
        ),
        encoding="utf-8",
    )
    timestamp_errors = validate_registry(load_registry(registry_path))

    assert any(
        "manual_okf_zenn: okf_source_metadata.timestamp must be ISO-8601" in error
        for error in timestamp_errors
    )


def test_f3_and_sqljoiner_sources_stay_disabled_metadata_only() -> None:
    registry = load_registry(Path("control/research_intake/source_registry.toml"))
    sources = {source.source_id: source for source in registry.sources}

    for source_id in ("manual_f3_repo", "manual_sqljoiner_repo"):
        source = sources[source_id]

        assert source.enabled_when == "disabled"
        assert source.source_type == "manual_url"
        assert source.policy.fetch_mode == "metadata_only"
        assert source.policy.allow_network is False
        assert source.policy.allow_provider is False


def test_cognee_source_stays_disabled_metadata_only() -> None:
    registry = load_registry(Path("control/research_intake/source_registry.toml"))
    sources = {source.source_id: source for source in registry.sources}
    source = sources["manual_cognee_repo"]

    assert source.enabled_when == "disabled"
    assert source.source_type == "manual_url"
    assert source.policy.fetch_mode == "metadata_only"
    assert source.policy.allow_network is False
    assert source.policy.allow_provider is False
    assert source.policy.storage_rights == "dependency_provider_review_before_fetch"
    assert "AI memory" in source.topics
    assert "provider gated" in source.topics
    assert source.source_governance is not None
    assert source.source_governance.source_ref == "S45"
    assert source.source_governance.owner_status == "adoption_registry"
    assert source.source_governance.adoption_candidate == "cognee_graph_memory_reference"
    assert (
        source.source_governance.promotion_boundary
        == "external_ai_memory_candidate_only_until_source_bundle_context_chunk_citation"
    )
    assert "candidate-only" in source.source_governance.notes


def test_slidev_visual_review_sources_are_metadata_only() -> None:
    registry = load_registry(Path("control/research_intake/source_registry.toml"))
    sources = {source.source_id: source for source in registry.sources}

    for source_id in (
        "manual_sios_marp_slidev",
        "manual_marp_official",
        "manual_slidev_official",
    ):
        source = sources[source_id]

        assert source.enabled_when == "always"
        assert source.policy.fetch_mode == "metadata_only"
        assert source.policy.allow_network is False
        assert source.policy.allow_provider is False
        assert source.source_governance is not None
        assert source.source_governance.source_ref == "S51"
        assert source.source_governance.adoption_candidate == "slidev_visual_review_lane"
        assert (
            source.source_governance.promotion_boundary
            == "presentation_visual_review_control_artifact_only"
        )
        assert "generated evidence" in source.source_governance.notes
        assert "citation" in source.source_governance.notes


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
