from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any

from research_x.contracts import AcquisitionTarget, AdapterConfig, ExperimentConfig, TargetKind


def load_config(path: str | Path) -> ExperimentConfig:
    config_path = Path(path)
    with config_path.open("rb") as handle:
        raw = tomllib.load(handle)
    return parse_config(raw)


def parse_config(raw: dict[str, Any]) -> ExperimentConfig:
    experiment = raw.get("experiment", {})
    run = raw.get("run", {})
    targets = tuple(_parse_target(item) for item in raw.get("targets", []))
    adapters = tuple(_parse_adapter(item) for item in raw.get("adapters", []))
    if not targets:
        raise ValueError("config must include at least one [[targets]] entry")
    if not adapters:
        raise ValueError("config must include at least one [[adapters]] entry")
    return ExperimentConfig(
        name=str(experiment.get("name", "experiment")),
        targets=targets,
        adapters=adapters,
        timeout_seconds=float(run.get("timeout_seconds", 30)),
        max_concurrency=int(run.get("max_concurrency", 2)),
        scoring_weights={key: float(value) for key, value in raw.get("scoring", {}).items()},
        promotion_thresholds={key: float(value) for key, value in raw.get("promotion", {}).items()},
    )


def _parse_target(raw: dict[str, Any]) -> AcquisitionTarget:
    return AcquisitionTarget(
        kind=TargetKind(str(raw["kind"])),
        value=str(raw["value"]),
        limit=int(raw.get("limit", 20)),
    )


def _parse_adapter(raw: dict[str, Any]) -> AdapterConfig:
    known_keys = {"id", "enabled"}
    options = {key: value for key, value in raw.items() if key not in known_keys}
    return AdapterConfig(
        adapter_id=str(raw["id"]),
        enabled=bool(raw.get("enabled", True)),
        options=options,
    )
