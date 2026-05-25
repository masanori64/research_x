from research_x.config import parse_config
from research_x.contracts import TargetKind


def test_parse_config() -> None:
    config = parse_config(
        {
            "experiment": {"name": "unit"},
            "targets": [{"kind": "search", "value": "hello", "limit": 2}],
            "adapters": [{"id": "synthetic", "enabled": True, "count": 1}],
            "run": {"timeout_seconds": 5, "max_concurrency": 1},
        }
    )

    assert config.name == "unit"
    assert config.targets[0].kind == TargetKind.SEARCH
    assert config.adapters[0].adapter_id == "synthetic"
    assert config.adapters[0].options == {"count": 1}


def test_parse_bookmarks_target_kind() -> None:
    config = parse_config(
        {
            "targets": [{"kind": "bookmarks", "value": "me", "limit": 10}],
            "adapters": [{"id": "playwright", "enabled": True}],
        }
    )

    assert config.targets[0].kind == TargetKind.BOOKMARKS
