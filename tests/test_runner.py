import json

from research_x.config import parse_config
from research_x.contracts import PromotionStatus
from research_x.runner import run_experiment


def test_run_experiment_writes_report(tmp_path) -> None:
    config = parse_config(
        {
            "experiment": {"name": "unit"},
            "targets": [{"kind": "search", "value": "hello", "limit": 2}],
            "adapters": [{"id": "synthetic", "enabled": True}],
            "promotion": {
                "min_score": 0.5,
                "min_success_rate": 1.0,
                "min_items": 2,
                "max_error_rate": 0.0,
            },
        }
    )

    metrics = run_experiment(config, tmp_path)

    assert metrics["synthetic"].promotion_status == PromotionStatus.PROMOTED
    assert (tmp_path / "events.jsonl").exists()
    report = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))
    assert report["promoted"] == ["synthetic"]


def test_not_configured_adapter_is_reported(tmp_path) -> None:
    config = parse_config(
        {
            "targets": [{"kind": "search", "value": "hello", "limit": 2}],
            "adapters": [
                {
                    "id": "masa_twitter_scraper",
                    "enabled": True,
                    "binary": "",
                    "command": "",
                }
            ],
        }
    )

    metrics = run_experiment(config, tmp_path)

    assert metrics["masa_twitter_scraper"].not_configured == 1
    assert metrics["masa_twitter_scraper"].promotion_status == PromotionStatus.REJECTED
