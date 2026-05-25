from research_x.adapters.playwright_adapter import (
    _author_from_href,
    _screen_name,
    _tweet_id,
    _with_bookmark_metadata,
)
from research_x.config import parse_config
from research_x.contracts import PromotionStatus, XItem, utc_now
from research_x.runner import run_experiment


def test_playwright_target_parsers() -> None:
    href = "/dogenzaka_pua/status/12345"

    assert _screen_name("@dogenzaka_pua") == "dogenzaka_pua"
    assert _screen_name("https://x.com/dogenzaka_pua") == "dogenzaka_pua"
    assert _tweet_id(href) == "12345"
    assert _author_from_href(href) == "dogenzaka_pua"


def test_playwright_bookmark_metadata_marker() -> None:
    item = XItem(
        source_id="1",
        url="https://x.com/a/status/1",
        author="a",
        text="hello",
        created_at=None,
        observed_at=utc_now(),
        raw={},
    )

    marked = _with_bookmark_metadata(item, 3)

    assert marked.raw["source_timeline"] == "bookmarks"
    assert marked.raw["bookmark_index"] == 3


def test_playwright_missing_storage_is_not_configured(tmp_path) -> None:
    config = parse_config(
        {
            "targets": [{"kind": "profile", "value": "@dogenzaka_pua", "limit": 1}],
            "adapters": [
                {
                    "id": "playwright",
                    "enabled": True,
                    "storage_state": str(tmp_path / "missing.json"),
                    "login": False,
                }
            ],
        }
    )

    metrics = run_experiment(config, tmp_path / "run")

    assert metrics["playwright"].not_configured == 1
    assert metrics["playwright"].promotion_status == PromotionStatus.REJECTED
