from __future__ import annotations

from dataclasses import replace

from research_x.adapters.browser_variant_adapters import RebrowserPlaywrightAdapter
from research_x.contracts import (
    AcquisitionTarget,
    AdapterConfig,
    FetchOutcome,
    OutcomeStatus,
    utc_now,
)


class RebrowserPatchesAdapter:
    adapter_id = "rebrowser_patches"

    def __init__(self, config: AdapterConfig) -> None:
        self.config = config

    def fetch(self, target: AcquisitionTarget) -> FetchOutcome:
        started_at = utc_now()
        delegate_options = dict(self.config.options)
        delegate_options.setdefault("storage_state", ".secrets/playwright_x_state.json")
        delegate_config = AdapterConfig(
            "rebrowser_playwright",
            enabled=self.config.enabled,
            options=delegate_options,
        )
        outcome = RebrowserPlaywrightAdapter(delegate_config).fetch(target)
        if outcome.status in (OutcomeStatus.OK, OutcomeStatus.PARTIAL):
            metadata = dict(outcome.metadata)
            metadata["patchset"] = "rebrowser_patches"
            metadata["delegated_runtime"] = "rebrowser_playwright"
            return replace(
                outcome,
                adapter_id=self.adapter_id,
                started_at=started_at,
                finished_at=utc_now(),
                metadata=metadata,
            )
        return FetchOutcome(
            adapter_id=self.adapter_id,
            target=target,
            status=outcome.status,
            started_at=started_at,
            finished_at=utc_now(),
            items=outcome.items,
            error_type=outcome.error_type or "PatchsetRuntimeFailure",
            error_message=(
                outcome.error_message
                or "rebrowser-patches delegated to rebrowser_playwright but did not acquire items."
            ),
            metadata={
                **outcome.metadata,
                "patchset": "rebrowser_patches",
                "delegated_runtime": "rebrowser_playwright",
            },
        )
