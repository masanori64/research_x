from __future__ import annotations

from pathlib import Path

from research_x.research_intake.pipeline import (
    discover_candidates,
    load_profile,
    load_registry,
    validate_run,
)


def test_default_discovery_records_zero_network_and_provider_calls() -> None:
    profile = load_profile(Path("control/research_intake/research_x_sources.profile.toml"))
    registry = load_registry(Path("control/research_intake/source_registry.toml"))

    run = discover_candidates(profile, registry, limit=10, created_at="2026-06-12T00:00:00Z")

    assert run.network_mode == "dry-run"
    assert run.network_calls_attempted == 0
    assert run.provider_calls_attempted == 0
    assert run.provider_freeze_compliant is True
    assert validate_run(run) == []
    assert all(candidate.citation_excluded for candidate in run.candidates)
    assert all(snapshot.fetch_method == "metadata_only_no_network" for snapshot in run.snapshots)
    assert all(snapshot.raw_content_path is None for snapshot in run.snapshots)


def test_research_brief_candidates_need_source_bundle_promotion() -> None:
    profile = load_profile(Path("control/research_intake/research_x_sources.profile.toml"))
    registry = load_registry(Path("control/research_intake/source_registry.toml"))

    run = discover_candidates(profile, registry, limit=3, created_at="2026-06-12T00:00:00Z")

    assert run.candidates
    assert {
        candidate.evidence_status for candidate in run.candidates
    } == {"not_evidence_until_fetched_and_chunked"}
    assert {
        snapshot.promotion_gate for snapshot in run.snapshots
    } == {"requires_fetch_extract_chunk_citation"}


def test_okf_metadata_discovery_is_serialized_without_fetch_or_provider_calls() -> None:
    profile = load_profile(Path("control/research_intake/research_x_sources.profile.toml"))
    registry = load_registry(Path("control/research_intake/source_registry.toml"))

    run = discover_candidates(profile, registry, limit=20, created_at="2026-07-01T00:00:00Z")
    okf_candidates = [
        candidate for candidate in run.candidates if candidate.source_id.startswith("manual_okf")
    ]
    snapshots_by_candidate = {snapshot.candidate_id: snapshot for snapshot in run.snapshots}

    assert run.network_calls_attempted == 0
    assert run.provider_calls_attempted == 0
    assert okf_candidates
    assert {"manual_okf_zenn", "manual_okf_google_cloud"} <= {
        candidate.source_id for candidate in okf_candidates
    }
    assert run.source_registry["okf_metadata_source_ids"] == [
        "manual_okf_zenn",
        "manual_okf_google_cloud",
    ]
    for candidate in okf_candidates:
        metadata = candidate.okf_source_metadata
        snapshot = snapshots_by_candidate[candidate.candidate_id]

        assert metadata is not None
        assert metadata.resource == candidate.canonical_url
        assert metadata.evidence_status == "not_evidence_until_fetched_and_chunked"
        assert metadata.answer_support_allowed is False
        assert candidate.citation_excluded is True
        assert snapshot.okf_source_metadata == metadata
        assert snapshot.fetch_method == "metadata_only_no_network"
        assert snapshot.raw_content_path is None
        assert snapshot.source_bundle_ref is None
        assert validate_run(run) == []
