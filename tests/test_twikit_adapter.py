from research_x.adapters.twikit_adapter import _screen_name, _tweet_id
from research_x.config import parse_config
from research_x.contracts import PromotionStatus
from research_x.runner import run_experiment


def test_twikit_without_credentials_is_not_configured(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("RESEARCH_X_X_USERNAME", raising=False)
    monkeypatch.delenv("RESEARCH_X_X_EMAIL", raising=False)
    monkeypatch.delenv("RESEARCH_X_X_PASSWORD", raising=False)
    config = parse_config(
        {
            "targets": [{"kind": "profile", "value": "@dogenzaka_pua", "limit": 1}],
            "adapters": [
                {
                    "id": "twikit",
                    "enabled": True,
                    "cookies_file": str(tmp_path / "missing_cookies.json"),
                }
            ],
        }
    )

    metrics = run_experiment(config, tmp_path / "run")

    assert metrics["twikit"].not_configured == 1
    assert metrics["twikit"].promotion_status == PromotionStatus.REJECTED


def test_target_parsers() -> None:
    assert _screen_name("@dogenzaka_pua") == "dogenzaka_pua"
    assert _screen_name("https://x.com/dogenzaka_pua") == "dogenzaka_pua"
    assert _tweet_id("https://x.com/example/status/12345") == "12345"
    assert _tweet_id("12345") == "12345"
