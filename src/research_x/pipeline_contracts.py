from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any

from research_x.contracts import AcquisitionTarget, FetchOutcome, XItem


class PipelineStatus(StrEnum):
    OK = "ok"
    PARTIAL = "partial"
    FAILED = "failed"


class ProviderFailureKind(StrEnum):
    NONE = "none"
    AUTH_FAILED = "auth_failed"
    RATE_LIMITED = "rate_limited"
    SCHEMA_DRIFT = "schema_drift"
    TRANSACTION_FAILED = "transaction_failed"
    DOM_DRIFT = "dom_drift"
    TIMEOUT = "timeout"
    NOT_CONFIGURED = "not_configured"
    UNSUPPORTED = "unsupported"
    EMPTY = "empty"
    ERROR = "error"


@dataclass(frozen=True)
class SessionArtifacts:
    storage_state: Path
    twikit_cookies_file: Path
    scweet_cookies_file: Path
    masa_cookies_file: Path
    has_session: bool
    session_source: str = "unknown"
    cookie_names: tuple[str, ...] = ()
    twscrape_accounts_db: Path = Path(".secrets/twscrape_accounts.db")


@dataclass(frozen=True)
class ProviderAttempt:
    provider_id: str
    target: AcquisitionTarget
    outcome: FetchOutcome
    failure_kind: ProviderFailureKind
    evidence_path: Path | None = None


@dataclass(frozen=True)
class PipelineTargetResult:
    target: AcquisitionTarget
    status: PipelineStatus
    items: tuple[XItem, ...]
    attempts: tuple[ProviderAttempt, ...]
    providers_used: tuple[str, ...]
    metadata: dict[str, Any] = field(default_factory=dict)
