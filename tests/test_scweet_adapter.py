from research_x.adapters.scweet_adapter import _record_to_item, _screen_name
from research_x.config import parse_config
from research_x.contracts import PromotionStatus
from research_x.runner import run_experiment


def test_scweet_without_cookies_is_not_configured(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("RESEARCH_X_X_AUTH_TOKEN", raising=False)
    monkeypatch.delenv("RESEARCH_X_X_CT0", raising=False)
    config = parse_config(
        {
            "targets": [{"kind": "profile", "value": "@dogenzaka_pua", "limit": 1}],
            "adapters": [
                {
                    "id": "scweet",
                    "enabled": True,
                    "db_path": str(tmp_path / "scweet.db"),
                    "cookies_file": str(tmp_path / "missing_cookies.json"),
                }
            ],
        }
    )

    metrics = run_experiment(config, tmp_path / "run")

    assert metrics["scweet"].not_configured == 1
    assert metrics["scweet"].promotion_status == PromotionStatus.REJECTED


def test_scweet_record_normalization() -> None:
    item = _record_to_item(
        {
            "tweet_id": "123",
            "tweet_url": "https://x.com/example/status/123",
            "user": {"screen_name": "example"},
            "text": "hello",
            "timestamp": "2026-05-20T18:50:42+00:00",
        }
    )

    assert item.source_id == "123"
    assert item.author == "example"
    assert item.created_at is not None
    assert _screen_name("https://x.com/dogenzaka_pua") == "dogenzaka_pua"
