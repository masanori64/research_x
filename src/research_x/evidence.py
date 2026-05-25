from __future__ import annotations

import json
import re
from dataclasses import asdict, is_dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from research_x.contracts import FetchOutcome


class EvidenceStore:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def write_attempt(self, index: int, outcome: FetchOutcome) -> Path:
        target_slug = _slug(f"{outcome.target.kind}-{outcome.target.value}")
        path = self.root / f"{index:03d}_{outcome.adapter_id}_{target_slug}.json"
        payload = {
            "adapter_id": outcome.adapter_id,
            "target": outcome.target,
            "status": outcome.status,
            "latency_ms": outcome.latency_ms,
            "item_count": len(outcome.items),
            "error_type": outcome.error_type,
            "error_message": outcome.error_message,
            "metadata": outcome.metadata,
            "items": outcome.items,
        }
        path.write_text(
            json.dumps(_jsonable(payload), ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        return path


def _slug(value: str) -> str:
    value = re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("_")
    return value[:120] or "target"


def _jsonable(value: Any):
    if isinstance(value, Path):
        return str(value)
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
