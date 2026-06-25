from __future__ import annotations

import json
from pathlib import Path

from research_x.research_intake.cli import main as intake_main
from research_x.research_intake.pipeline import (
    InterestProfile,
    SourcePolicy,
    SourceRegistry,
    SourceSubscription,
    discover_candidates,
    format_research_brief,
    load_profile,
    load_registry,
    validate_configuration,
    validate_run,
)


def test_default_research_intake_config_is_dry_run_only() -> None:
    profile = load_profile(Path("control/research_intake/codex_ai_tools.profile.toml"))
    registry = load_registry(Path("control/research_intake/source_registry.toml"))

    assert validate_configuration(profile, registry) == []

    run = discover_candidates(
        profile,
        registry,
        limit=5,
        created_at="2026-06-10T00:00:00Z",
    )

    assert run.provider_freeze_compliant is True
    assert run.network_calls_attempted == 0
    assert run.provider_calls_attempted == 0
    assert validate_run(run) == []
    assert {candidate.source_type for candidate in run.candidates} == {
        "manual_url",
        "local_note",
        "fake_search",
    }
    assert all(candidate.citation_excluded for candidate in run.candidates)
    assert all(
        candidate.evidence_status == "not_evidence_until_fetched_and_chunked"
        for candidate in run.candidates
    )
    assert all(snapshot.fetch_status == "not_fetched_dry_run" for snapshot in run.snapshots)
    assert all(snapshot.raw_content_path is None for snapshot in run.snapshots)
    assert all(snapshot.source_bundle_ref is None for snapshot in run.snapshots)


def test_enabled_provider_source_is_rejected() -> None:
    profile = InterestProfile(
        profile_id="provider_test",
        title="Provider test",
        include_topics=("Codex Skills",),
        preferred_sources=("provider_search",),
    )
    registry = SourceRegistry(
        registry_id="provider_registry",
        sources=(
            SourceSubscription(
                source_id="provider_search",
                source_type="serper",
                locator="codex skills",
                enabled_when="always",
                policy=SourcePolicy(allow_network=False, allow_provider=False),
            ),
        ),
    )

    errors = validate_configuration(profile, registry)

    assert any("provider-backed sources cannot be enabled" in error for error in errors)


def test_policy_network_or_provider_flags_are_rejected() -> None:
    profile = InterestProfile(
        profile_id="policy_test",
        title="Policy test",
        include_topics=("Codex Skills",),
        preferred_sources=("manual",),
    )
    registry = SourceRegistry(
        registry_id="policy_registry",
        sources=(
            SourceSubscription(
                source_id="manual",
                source_type="manual_url",
                locator="https://example.com/codex",
                quality_hint="medium",
                policy=SourcePolicy(allow_network=True, allow_provider=True),
            ),
        ),
    )

    errors = validate_configuration(profile, registry)

    assert "manual: policy.allow_network must be false" in errors
    assert "manual: policy.allow_provider must be false" in errors


def test_research_brief_keeps_candidates_out_of_evidence() -> None:
    profile = InterestProfile(
        profile_id="brief_test",
        title="Brief test",
        include_topics=("Codex Skills",),
        preferred_sources=("fake",),
    )
    registry = SourceRegistry(
        registry_id="brief_registry",
        sources=(
            SourceSubscription(
                source_id="fake",
                source_type="fake_search",
                locator="codex skills",
                quality_hint="unknown",
                topics=("Codex Skills",),
            ),
        ),
    )
    run = discover_candidates(profile, registry, created_at="2026-06-10T00:00:00Z")

    brief = format_research_brief(run, objective="Inspect dry-run intake")

    assert "Provider calls attempted: 0" in brief
    assert "Network calls attempted: 0" in brief
    assert "not citation-ready evidence" in brief
    assert "not_evidence_until_fetched_and_chunked" in brief


def test_cli_validate_discover_and_brief_round_trip(tmp_path: Path) -> None:
    run_path = tmp_path / "run.json"
    brief_path = tmp_path / "brief.md"

    assert intake_main(["validate"]) == 0
    assert (
        intake_main(
            [
                "discover",
                "--out",
                str(run_path),
                "--limit",
                "3",
                "--created-at",
                "2026-06-10T00:00:00Z",
            ]
        )
        == 0
    )
    assert intake_main(["brief", "--run", str(run_path), "--out", str(brief_path)]) == 0

    run = json.loads(run_path.read_text(encoding="utf-8"))
    brief = brief_path.read_text(encoding="utf-8")

    assert run["provider_calls_attempted"] == 0
    assert run["network_calls_attempted"] == 0
    assert len(run["candidates"]) == 3
    assert "Research Intake Brief" in brief
