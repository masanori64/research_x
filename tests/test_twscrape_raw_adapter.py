from research_x.adapters.twscrape_raw_adapter import (
    _screen_name,
    _tweet_id,
    _with_bookmark_metadata,
)
from research_x.config import parse_config
from research_x.contracts import PromotionStatus, XItem, utc_now
from research_x.runner import run_experiment


def test_twscrape_without_bootstrap_or_active_account_is_not_configured(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.delenv("RESEARCH_X_X_USERNAME", raising=False)
    monkeypatch.delenv("RESEARCH_X_X_PASSWORD", raising=False)
    config = parse_config(
        {
            "targets": [{"kind": "profile", "value": "@target_user", "limit": 1}],
            "adapters": [
                {
                    "id": "twscrape_raw",
                    "enabled": True,
                    "accounts_db": str(tmp_path / "accounts.db"),
                    "bootstrap_account": False,
                }
            ],
        }
    )

    metrics = run_experiment(config, tmp_path / "run")

    assert metrics["twscrape_raw"].not_configured == 1
    assert metrics["twscrape_raw"].promotion_status == PromotionStatus.REJECTED


def test_twscrape_target_parsers() -> None:
    assert _screen_name("@target_user") == "target_user"
    assert _screen_name("https://x.com/target_user") == "target_user"
    assert _tweet_id("https://x.com/example/status/12345") == "12345"
    assert _tweet_id("12345") == "12345"


def test_twscrape_bookmark_metadata_marker() -> None:
    item = XItem(
        source_id="123",
        url="https://x.com/a/status/123",
        author="a",
        text="hello",
        created_at=None,
        observed_at=utc_now(),
        raw={},
    )

    marked = _with_bookmark_metadata(item, 2)

    assert marked.raw["source_timeline"] == "bookmarks"
    assert marked.raw["bookmark_index"] == 2
    assert marked.raw["source_api"] == "twscrape"
