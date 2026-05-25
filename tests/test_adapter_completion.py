from research_x.adapters.base import NotConfiguredAdapter
from research_x.adapters.registry import build_adapter, known_adapter_ids
from research_x.adapters.url_tools import status_items_from_text, target_to_x_url
from research_x.contracts import AcquisitionTarget, AdapterConfig, OutcomeStatus, TargetKind


def test_registry_uses_concrete_adapters() -> None:
    for adapter_id in known_adapter_ids():
        adapter = build_adapter(AdapterConfig(adapter_id))

        assert not isinstance(adapter, NotConfiguredAdapter), adapter_id


def test_status_link_extraction_normalizes_x_items() -> None:
    target = AcquisitionTarget(TargetKind.PROFILE, "@alice", limit=2)
    items = status_items_from_text(
        'href="/alice/status/1234567890123456789" '
        "https://x.com/bob/status/2234567890123456789",
        target,
    )

    assert [item.source_id for item in items] == [
        "2234567890123456789",
        "1234567890123456789",
    ]
    assert items[0].author == "bob"


def test_target_to_x_url_handles_profile_search_and_url() -> None:
    assert target_to_x_url(AcquisitionTarget(TargetKind.PROFILE, "@doge")) == "https://x.com/doge"
    assert (
        target_to_x_url(AcquisitionTarget(TargetKind.SEARCH, "hello world"))
        == "https://x.com/search?q=hello%20world&src=typed_query&f=live"
    )
    assert (
        target_to_x_url(AcquisitionTarget(TargetKind.URL, "https://x.com/a/status/1"))
        == "https://x.com/a/status/1"
    )
    assert target_to_x_url(AcquisitionTarget(TargetKind.BOOKMARKS, "me")) == (
        "https://x.com/i/bookmarks"
    )


def test_masa_adapter_reports_missing_sidecar_without_stub() -> None:
    adapter = build_adapter(
        AdapterConfig("masa_twitter_scraper", options={"binary": "", "command": ""})
    )

    outcome = adapter.fetch(AcquisitionTarget(TargetKind.PROFILE, "@doge", limit=1))

    assert outcome.status == OutcomeStatus.NOT_CONFIGURED
    assert outcome.error_type == "MissingSidecar"
    assert "sidecar_contract" in outcome.metadata


def test_rebrowser_patches_is_explicit_patchset_marker() -> None:
    adapter = build_adapter(
        AdapterConfig("rebrowser_patches", options={"storage_state": "missing-state.json"})
    )

    outcome = adapter.fetch(AcquisitionTarget(TargetKind.PROFILE, "@doge", limit=1))

    assert outcome.status == OutcomeStatus.NOT_CONFIGURED
    assert outcome.metadata["delegated_runtime"] == "rebrowser_playwright"
