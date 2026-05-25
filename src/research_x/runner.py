from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from datetime import datetime
from pathlib import Path

from research_x.adapters import build_adapter
from research_x.contracts import ExperimentConfig, FetchOutcome, OutcomeStatus, utc_now
from research_x.scoring import AdapterMetrics, score_adapters


def run_experiment(config: ExperimentConfig, out_dir: str | Path) -> dict[str, AdapterMetrics]:
    output_path = Path(out_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    outcomes: list[FetchOutcome] = []
    for adapter_config in config.adapters:
        if not adapter_config.enabled:
            continue
        adapter = build_adapter(adapter_config)
        for target in config.targets:
            outcomes.append(_safe_fetch(adapter, target))
    _write_events(output_path / "events.jsonl", outcomes)
    metrics = score_adapters(
        outcomes,
        expected_targets=len(config.targets),
        weights=config.scoring_weights,
        thresholds=config.promotion_thresholds,
    )
    _write_report(output_path / "report.json", config, metrics)
    return metrics


def _safe_fetch(adapter, target) -> FetchOutcome:
    try:
        return adapter.fetch(target)
    except Exception as exc:  # noqa: BLE001 - experiment runner must isolate adapters.
        now = utc_now()
        return FetchOutcome(
            adapter_id=adapter.adapter_id,
            target=target,
            status=OutcomeStatus.ERROR,
            started_at=now,
            finished_at=utc_now(),
            error_type=type(exc).__name__,
            error_message=str(exc),
        )


def _write_events(path: Path, outcomes: list[FetchOutcome]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for outcome in outcomes:
            handle.write(json.dumps(_jsonable(outcome), ensure_ascii=False, sort_keys=True) + "\n")


def _write_report(
    path: Path,
    config: ExperimentConfig,
    metrics: dict[str, AdapterMetrics],
) -> None:
    payload = {
        "experiment": config.name,
        "generated_at": utc_now(),
        "adapters": list(metrics.values()),
        "promoted": [
            metric.adapter_id
            for metric in metrics.values()
            if metric.promotion_status.value == "promoted"
        ],
    }
    path.write_text(
        json.dumps(_jsonable(payload), ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def _jsonable(value):
    if isinstance(value, datetime):
        return value.isoformat()
    if is_dataclass(value) and not isinstance(value, type):
        return _jsonable(asdict(value))
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if hasattr(value, "value"):
        return value.value
    return value
