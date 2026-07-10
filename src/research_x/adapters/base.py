from __future__ import annotations

from dataclasses import dataclass

from research_x.contracts import (
    AcquisitionTarget,
    AdapterConfig,
    FetchOutcome,
    OutcomeStatus,
    utc_now,
)


@dataclass
class NotConfiguredAdapter:
    adapter_id: str
    package_name: str
    setup_hint: str
    config: AdapterConfig

    def fetch(self, target: AcquisitionTarget) -> FetchOutcome:
        started_at = utc_now()
        return FetchOutcome(
            adapter_id=self.adapter_id,
            target=target,
            status=OutcomeStatus.NOT_CONFIGURED,
            started_at=started_at,
            finished_at=utc_now(),
            error_type="NotConfigured",
            error_message=(
                f"{self.adapter_id} requires {self.package_name}. {self.setup_hint}"
            ),
            metadata={"package": self.package_name},
        )
