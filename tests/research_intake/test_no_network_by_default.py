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
