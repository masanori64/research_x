from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Protocol


class TargetKind(StrEnum):
    SEARCH = "search"
    PROFILE = "profile"
    URL = "url"
    BOOKMARKS = "bookmarks"


class OutcomeStatus(StrEnum):
    OK = "ok"
    PARTIAL = "partial"
    EMPTY = "empty"
    NOT_CONFIGURED = "not_configured"
    UNSUPPORTED = "unsupported"
    ERROR = "error"


class PromotionStatus(StrEnum):
    PROMOTED = "promoted"
    CANDIDATE = "candidate"
    REJECTED = "rejected"


@dataclass(frozen=True)
class AcquisitionTarget:
    kind: TargetKind
    value: str
    limit: int = 20


@dataclass(frozen=True)
class AdapterConfig:
    adapter_id: str
    enabled: bool = True
    options: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ExperimentConfig:
    name: str
    targets: tuple[AcquisitionTarget, ...]
    adapters: tuple[AdapterConfig, ...]
    timeout_seconds: float = 30.0
    max_concurrency: int = 2
    scoring_weights: dict[str, float] = field(default_factory=dict)
    promotion_thresholds: dict[str, float] = field(default_factory=dict)


@dataclass(frozen=True)
class XItem:
    source_id: str
    url: str | None
    author: str | None
    text: str | None
    created_at: datetime | None
    observed_at: datetime
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class FetchOutcome:
    adapter_id: str
    target: AcquisitionTarget
    status: OutcomeStatus
    started_at: datetime
    finished_at: datetime
    items: tuple[XItem, ...] = ()
    error_type: str | None = None
    error_message: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def latency_ms(self) -> float:
        return (self.finished_at - self.started_at).total_seconds() * 1000


class XAdapter(Protocol):
    adapter_id: str

    def fetch(self, target: AcquisitionTarget) -> FetchOutcome:
        """Fetch normalized X items for one target."""


def utc_now() -> datetime:
    return datetime.now(tz=UTC)
