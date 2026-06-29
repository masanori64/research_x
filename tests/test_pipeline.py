import json

from research_x.config import parse_config
from research_x.contracts import (
    AcquisitionTarget,
    AdapterConfig,
    ExperimentConfig,
    FetchOutcome,
    OutcomeStatus,
    TargetKind,
    XItem,
    utc_now,
)
from research_x.pipeline import (
    _items_for_target,
    classify_outcome,
    provider_chain_for,
    run_pipeline,
)
from research_x.pipeline_contracts import PipelineStatus, ProviderFailureKind


def test_provider_chain_uses_role_order() -> None:
    chain = provider_chain_for(
        TargetKind.PROFILE,
        ("twikit", "playwright", "twscrape_raw", "scweet"),
    )

    assert chain == ("twscrape_raw", "scweet", "twikit", "playwright")


def test_bookmarks_chain_uses_non_official_cursor_providers_first() -> None:
    chain = provider_chain_for(
        TargetKind.BOOKMARKS,
        (
            "scrapy",
            "playwright",
            "twikit",
            "twscrape_raw",
            "x_web_graphql_bookmarks",
            "gallery_dl_bookmarks",
            "playwright_network_bookmarks",
            "camoufox",
            "patchright",
            "rebrowser_playwright",
            "rebrowser_patches",
        ),
    )

    assert chain == (
        "twscrape_raw",
        "twikit",
        "x_web_graphql_bookmarks",
        "gallery_dl_bookmarks",
        "playwright_network_bookmarks",
        "playwright",
        "camoufox",
        "patchright",
        "rebrowser_playwright",
        "rebrowser_patches",
        "scrapy",
    )


def test_explicit_security_gated_optional_provider_is_tried_after_defaults() -> None:
    chain = provider_chain_for(
        TargetKind.URL,
        ("playwright", "scrapling", "crawl4ai", "scrapy"),
    )

    assert chain == ("playwright", "scrapling", "scrapy", "crawl4ai")


def test_run_pipeline_with_synthetic_provider(tmp_path) -> None:
    config = parse_config(
        {
            "experiment": {"name": "pipeline-unit"},
            "targets": [{"kind": "search", "value": "hello", "limit": 2}],
            "adapters": [{"id": "synthetic", "enabled": True, "count": 20}],
        }
    )

    results = run_pipeline(
        config,
        tmp_path / "run",
        storage_state=tmp_path / "missing_state.json",
        min_successful_providers=1,
    )

    assert results[0].status == PipelineStatus.OK
    assert results[0].providers_used == ("synthetic",)
    assert len(results[0].items) == 2
    assert (tmp_path / "run" / "pipeline_report.json").exists()
    rows = (tmp_path / "run" / "items.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(rows) == 2
    assert json.loads(rows[0])["author"].startswith("synthetic")


def test_run_pipeline_can_stop_after_first_success_even_under_limit(tmp_path) -> None:
    config = parse_config(
        {
            "experiment": {"name": "pipeline-unit"},
            "targets": [{"kind": "search", "value": "hello", "limit": 100}],
            "adapters": [{"id": "synthetic", "enabled": True, "count": 20}],
        }
    )

    results = run_pipeline(
        config,
        tmp_path / "run",
        storage_state=tmp_path / "missing_state.json",
        min_successful_providers=1,
        stop_after_first_success=True,
        ok_with_any_items=True,
    )

    assert results[0].status == PipelineStatus.OK
    assert len(results[0].items) == 20


def test_run_pipeline_uses_target_level_max_concurrency(tmp_path) -> None:
    config = parse_config(
        {
            "experiment": {"name": "pipeline-concurrent-targets"},
            "run": {"max_concurrency": 2},
            "targets": [
                {"kind": "search", "value": "hello", "limit": 1},
                {"kind": "profile", "value": "@alice", "limit": 1},
            ],
            "adapters": [{"id": "synthetic", "enabled": True, "count": 2}],
        }
    )

    results = run_pipeline(
        config,
        tmp_path / "run",
        storage_state=tmp_path / "missing_state.json",
        min_successful_providers=1,
    )

    assert [result.target.value for result in results] == ["hello", "@alice"]
    assert [result.metadata["max_concurrency"] for result in results] == [2, 2]
    evidence_files = sorted((tmp_path / "run" / "evidence").glob("*.json"))
    assert len(evidence_files) == 2


def test_run_pipeline_treats_cursor_exhaustion_as_complete(tmp_path, monkeypatch) -> None:
    now = utc_now()

    class CursorExhaustedAdapter:
        adapter_id = "cursor"

        def __init__(self, _config: AdapterConfig) -> None:
            pass

        def fetch(self, target: AcquisitionTarget) -> FetchOutcome:
            return FetchOutcome(
                adapter_id=self.adapter_id,
                target=target,
                status=OutcomeStatus.OK,
                started_at=now,
                finished_at=utc_now(),
                items=(
                    XItem(
                        source_id="1",
                        url=None,
                        author=None,
                        text="only available item",
                        created_at=None,
                        observed_at=now,
                        raw={"bookmark_root": True},
                    ),
                ),
                metadata={"cursor_exhausted": True},
            )

    monkeypatch.setattr(
        "research_x.pipeline.build_adapter",
        lambda config: CursorExhaustedAdapter(config),
    )
    config = ExperimentConfig(
        name="cursor-complete",
        targets=(AcquisitionTarget(TargetKind.BOOKMARKS, "me", limit=1000),),
        adapters=(AdapterConfig("cursor"),),
    )

    results = run_pipeline(
        config,
        tmp_path / "run",
        storage_state=tmp_path / "missing_state.json",
        min_successful_providers=1,
    )

    assert results[0].status == PipelineStatus.OK
    assert results[0].metadata["provider_exhausted"] is True


def test_bookmark_pipeline_filters_non_root_items() -> None:
    root = parse_config(
        {
            "targets": [{"kind": "bookmarks", "value": "me"}],
            "adapters": [{"id": "synthetic"}],
        }
    ).targets[0]
    now = utc_now()
    items = (
        _item("1", {"bookmark_root": True}, now),
        _item("2", {"source_timeline": "bookmarks"}, now),
    )

    filtered = _items_for_target(root.kind, items)

    assert [item.source_id for item in filtered] == ["1"]


def test_classify_outcome() -> None:
    now = utc_now()
    timeout = FetchOutcome(
        adapter_id="x",
        target=parse_config(
            {
                "targets": [{"kind": "profile", "value": "@a"}],
                "adapters": [{"id": "synthetic"}],
            }
        ).targets[0],
        status=OutcomeStatus.ERROR,
        started_at=now,
        finished_at=now,
        error_type="TimeoutError",
        error_message="request timeout",
    )

    assert classify_outcome(timeout) == ProviderFailureKind.TIMEOUT


def _item(source_id, raw, now):
    from research_x.contracts import XItem

    return XItem(
        source_id=source_id,
        url=None,
        author=None,
        text=None,
        created_at=None,
        observed_at=now,
        raw=raw,
    )
