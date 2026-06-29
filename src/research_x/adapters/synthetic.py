from __future__ import annotations

import hashlib
from datetime import timedelta

from research_x.contracts import (
    AcquisitionTarget,
    AdapterConfig,
    FetchOutcome,
    OutcomeStatus,
    XItem,
    utc_now,
)


class SyntheticAdapter:
    adapter_id = "synthetic"

    def __init__(self, config: AdapterConfig) -> None:
        self.config = config

    def fetch(self, target: AcquisitionTarget) -> FetchOutcome:
        started_at = utc_now()
        observed_at = utc_now()
        count = max(0, min(target.limit, int(self.config.options.get("count", target.limit))))
        items = tuple(
            XItem(
                source_id=_stable_id(target.value, index),
                url=f"https://x.example/{target.kind}/{_stable_id(target.value, index)}",
                author=f"synthetic_{index}",
                text=f"Synthetic {target.kind} item for {target.value} #{index}",
                created_at=observed_at - timedelta(minutes=index),
                observed_at=observed_at,
                raw={"target": target.value, "index": index},
            )
            for index in range(count)
        )
        status = OutcomeStatus.OK if items else OutcomeStatus.EMPTY
        return FetchOutcome(
            adapter_id=self.adapter_id,
            target=target,
            status=status,
            started_at=started_at,
            finished_at=utc_now(),
            items=items,
            metadata={"synthetic": True},
        )


def _stable_id(value: str, index: int) -> str:
    return hashlib.blake2b(f"{value}:{index}".encode(), digest_size=8).hexdigest()
