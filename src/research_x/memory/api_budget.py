from __future__ import annotations

import contextlib
import hashlib
import html
import json
import sqlite3
import uuid
import webbrowser
from collections.abc import Iterator
from contextvars import ContextVar
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

DEFAULT_API_BUDGET_POLICY_ID = "default"
DEFAULT_MAX_RUN_USD = 1.0
DEFAULT_MAX_DAY_USD = 5.0
DEFAULT_MAX_MONTH_USD = 25.0
DEFAULT_UNKNOWN_PRICE_ACTION = "block"
DEFAULT_WARNING_FRACTION = 0.8
EXEMPT_PROVIDERS = {"fake", "local", "local_hash"}
EXEMPT_PROVIDER_PREFIXES = ("fixture_",)
BUDGET_EXHAUSTED_STATUS = "budget_exhausted"
PROVIDER_QUOTA_FREEZE_ACTIVE = True
NO_QUOTA_FREEZE_BLOCK_STATUS = "provider_gated_by_no_quota_freeze"
PROVIDER_QUOTA_APPROVAL_GATE_MESSAGE = (
    "provider quota execution requires a scoped provider quota approval object; "
    "--allow-provider-quota alone is not sufficient"
)
NO_QUOTA_FREEZE_BLOCK_MESSAGE = (
    "provider_gated_by_no_quota_freeze: provider API calls are blocked while the "
    "no-quota freeze is active; approval objects are dry-run inputs only"
)

_ACTIVE_CONTEXT: ContextVar[ApiBudgetContext | None] = ContextVar(
    "research_x_api_budget_context",
    default=None,
)


class ApiBudgetError(RuntimeError):
    pass


class ApiBudgetExceededError(ApiBudgetError):
    def __init__(self, message: str, *, event_id: str | None = None) -> None:
        super().__init__(message)
        self.event_id = event_id


@dataclass(frozen=True)
class ApiBudgetContext:
    db_path: str
    policy_id: str = DEFAULT_API_BUDGET_POLICY_ID
    run_id: str | None = None
    job_id: str | None = None
    max_run_usd_override: float | None = None
    allow_unpriced_api: bool = False
    metadata: dict[str, Any] | None = None
    provider_quota_approval: ProviderQuotaApproval | None = None
    provider_quota_current_scope: str | None = None
    no_quota_freeze_active: bool = PROVIDER_QUOTA_FREEZE_ACTIVE


@dataclass(frozen=True)
class ApiBudgetReservation:
    db_path: str
    event_id: str
    estimated_cost_usd: float


@dataclass(frozen=True)
class ProviderQuotaApproval:
    provider_quota_approval_id: str
    provider: str
    model: str
    operation: str
    max_calls: int
    max_cost_usd: float
    price_source: str
    approved_scope: str
    approved_at: str
    provider_role: str | None = None
    approved_by: str | None = None
    expires_at: str | None = None
    metadata: dict[str, Any] | None = None


@contextlib.contextmanager
def api_budget_context(
    *,
    db_path: str | Path,
    policy_id: str = DEFAULT_API_BUDGET_POLICY_ID,
    run_id: str | None = None,
    job_id: str | None = None,
    max_run_usd_override: float | None = None,
    allow_unpriced_api: bool = False,
    metadata: dict[str, Any] | None = None,
    provider_quota_approval: ProviderQuotaApproval | dict[str, Any] | None = None,
    provider_quota_current_scope: str | None = None,
    no_quota_freeze_active: bool = PROVIDER_QUOTA_FREEZE_ACTIVE,
) -> Iterator[ApiBudgetContext]:
    context = ApiBudgetContext(
        db_path=str(db_path),
        policy_id=policy_id,
        run_id=run_id or f"api-{datetime.now(tz=UTC).strftime('%Y%m%d')}-{uuid.uuid4().hex[:8]}",
        job_id=job_id,
        max_run_usd_override=max_run_usd_override,
        allow_unpriced_api=allow_unpriced_api,
        metadata=metadata,
        provider_quota_approval=_coerce_provider_quota_approval(provider_quota_approval),
        provider_quota_current_scope=provider_quota_current_scope,
        no_quota_freeze_active=no_quota_freeze_active,
    )
    token = _ACTIVE_CONTEXT.set(context)
    try:
        yield context
    finally:
        _ACTIVE_CONTEXT.reset(token)


def active_api_budget_context() -> ApiBudgetContext | None:
    return _ACTIVE_CONTEXT.get()


def provider_is_quota_exempt(provider: str) -> bool:
    return _is_exempt_provider(provider)


def require_provider_execution_allowed(
    *,
    provider: str,
    model: str | None = None,
    operation: str | None = None,
) -> None:
    del model, operation
    if _is_exempt_provider(provider):
        return
    context = active_api_budget_context()
    if context is None:
        if PROVIDER_QUOTA_FREEZE_ACTIVE:
            raise RuntimeError(NO_QUOTA_FREEZE_BLOCK_MESSAGE)
        raise RuntimeError(
            f"{PROVIDER_QUOTA_APPROVAL_GATE_MESSAGE}: active API budget context is required"
        )
    if context.no_quota_freeze_active:
        raise RuntimeError(NO_QUOTA_FREEZE_BLOCK_MESSAGE)


@contextlib.contextmanager
def budgeted_api_call(
    *,
    provider: str,
    model: str,
    provider_role: str,
    operation: str,
    units: dict[str, int | float] | None = None,
    request_payload: Any | None = None,
    metadata: dict[str, Any] | None = None,
) -> Iterator[ApiBudgetReservation | None]:
    if _is_exempt_provider(provider):
        yield None
        return
    context = active_api_budget_context()
    if context is None:
        require_provider_execution_allowed(provider=provider, model=model, operation=operation)
        raise AssertionError("unreachable provider execution gate state")
    reservation = reserve_api_budget(
        context,
        provider=provider,
        model=model,
        provider_role=provider_role,
        operation=operation,
        units=units or {"calls": 1},
        request_payload=request_payload,
        metadata=metadata,
    )
    try:
        yield reservation
    except Exception as exc:
        finish_api_budget_event(
            context.db_path,
            reservation.event_id,
            status="error",
            error=f"{type(exc).__name__}: {exc}",
        )
        raise
    else:
        finish_api_budget_event(
            context.db_path,
            reservation.event_id,
            status="ok",
            actual_cost_usd=reservation.estimated_cost_usd,
        )


def api_units(
    *,
    calls: int | float = 1,
    retries: int | float = 0,
    input_tokens: int | float = 0,
    output_tokens: int | float = 0,
    media_bytes: int | float = 0,
    documents: int | float = 0,
    pages: int | float = 0,
) -> dict[str, int | float]:
    raw = {
        "calls": calls,
        "retries": retries,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "media_bytes": media_bytes,
        "documents": documents,
        "pages": pages,
    }
    return {key: value for key, value in raw.items() if value}


def rough_text_tokens(value: Any) -> int:
    chars = _count_text_chars(value)
    if chars <= 0:
        return 0
    return max(1, (chars + 1) // 2)


def provider_quota_approval_as_dict(approval: ProviderQuotaApproval) -> dict[str, Any]:
    return asdict(approval)


def validate_provider_quota_approval(
    approval: ProviderQuotaApproval | dict[str, Any] | None,
    *,
    provider: str,
    model: str | None,
    operation: str,
    units: dict[str, int | float] | None = None,
    estimated_cost_usd: float | None = None,
    approved_scope: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    errors: list[str] = []
    try:
        resolved = _coerce_provider_quota_approval(approval)
    except (TypeError, ValueError) as exc:
        resolved = None
        errors.append(str(exc))
    normalized_units = _normalize_units(units or {"calls": 1})
    provider_id = _clean_id(provider)
    model_id = _clean_model(model or "")
    operation_id = _clean_id(operation)
    if resolved is None:
        errors.append("provider quota approval object is required")
        return _provider_quota_validation_payload(
            approval=None,
            errors=errors,
            units=normalized_units,
            estimated_cost_usd=estimated_cost_usd,
        )

    approval_provider = _clean_id(resolved.provider)
    approval_model = _clean_model(resolved.model)
    approval_operation = _clean_id(resolved.operation)
    if approval_provider != provider_id:
        errors.append(f"approval provider mismatch: {approval_provider} != {provider_id}")
    if model_id and approval_model != model_id:
        errors.append(f"approval model mismatch: {approval_model} != {model_id}")
    if approval_operation != operation_id:
        errors.append(f"approval operation mismatch: {approval_operation} != {operation_id}")
    if approved_scope and resolved.approved_scope not in {"*", approved_scope}:
        errors.append(
            f"approval scope mismatch: {resolved.approved_scope} does not cover {approved_scope}"
        )
    if not str(resolved.price_source).strip():
        errors.append("approval price_source is required")
    max_calls = int(resolved.max_calls)
    planned_calls = int(float(normalized_units.get("calls", 1) or 1))
    if max_calls <= 0:
        errors.append("approval max_calls must be positive")
    elif planned_calls > max_calls:
        errors.append(f"planned calls exceed approval max_calls: {planned_calls} > {max_calls}")
    max_cost_usd = float(resolved.max_cost_usd)
    if max_cost_usd < 0:
        errors.append("approval max_cost_usd must be non-negative")
    if estimated_cost_usd is not None and float(estimated_cost_usd) > max_cost_usd:
        errors.append(
            "estimated cost exceeds approval max_cost_usd: "
            f"{float(estimated_cost_usd):.8f} > {max_cost_usd:.8f}"
        )
    _validate_approval_timestamp("approved_at", resolved.approved_at, errors)
    if resolved.expires_at:
        expires_at = _validate_approval_timestamp("expires_at", resolved.expires_at, errors)
        current = now or datetime.now(tz=UTC)
        if expires_at is not None and expires_at < current:
            errors.append("approval expires_at is in the past")
    return _provider_quota_validation_payload(
        approval=resolved,
        errors=errors,
        units=normalized_units,
        estimated_cost_usd=estimated_cost_usd,
    )


def require_provider_quota_approval(
    *,
    provider: str,
    model: str | None,
    operation: str,
    units: dict[str, int | float] | None = None,
    estimated_cost_usd: float | None = None,
) -> None:
    if _is_exempt_provider(provider):
        return
    context = active_api_budget_context()
    require_provider_execution_allowed(provider=provider, model=model, operation=operation)
    approval = context.provider_quota_approval if context is not None else None
    approved_scope = context.provider_quota_current_scope if context is not None else None
    result = validate_provider_quota_approval(
        approval,
        provider=provider,
        model=model,
        operation=operation,
        units=units,
        estimated_cost_usd=estimated_cost_usd,
        approved_scope=approved_scope,
    )
    if not result["valid"]:
        details = "; ".join(result["errors"])
        raise RuntimeError(f"{PROVIDER_QUOTA_APPROVAL_GATE_MESSAGE}: {details}")


def provider_quota_preflight(
    db_path: str | Path,
    *,
    provider: str,
    model: str,
    operation: str,
    provider_role: str = "provider",
    units: dict[str, int | float] | None = None,
    approval: ProviderQuotaApproval | dict[str, Any] | None = None,
    policy_id: str = DEFAULT_API_BUDGET_POLICY_ID,
    run_id: str | None = None,
    approved_scope: str | None = None,
    max_run_usd_override: float | None = None,
    allow_unpriced_api: bool = False,
    freeze_active: bool = PROVIDER_QUOTA_FREEZE_ACTIVE,
) -> dict[str, Any]:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    provider_id = _clean_id(provider)
    model_id = _clean_model(model)
    operation_id = _clean_id(operation)
    normalized_units = _normalize_units(units or {"calls": 1})
    with sqlite3.connect(path, timeout=60) as conn:
        conn.row_factory = sqlite3.Row
        ensure_api_budget_schema(conn)
        policy = _policy_row(conn, policy_id)
        if policy is None:
            raise ApiBudgetError(f"API budget policy not found: {policy_id}")
        cost_result = _estimated_cost(
            conn,
            provider=provider_id,
            model=model_id,
            operation=operation_id,
            units=normalized_units,
            allow_unpriced=allow_unpriced_api,
            unknown_price_action=str(policy["unknown_price_action"] or "block"),
        )
        budget_block_reason = _policy_block_reason(policy)
        if budget_block_reason is None:
            budget_block_reason = _cap_block_reason(
                conn,
                policy,
                run_id=run_id,
                estimated_cost=float(cost_result["estimated_cost_usd"]),
                units=normalized_units,
                max_run_usd_override=max_run_usd_override,
            )
    approval_result = validate_provider_quota_approval(
        approval,
        provider=provider_id,
        model=model_id,
        operation=operation_id,
        units=normalized_units,
        estimated_cost_usd=float(cost_result["estimated_cost_usd"]),
        approved_scope=approved_scope,
    )
    if cost_result.get("unknown_price"):
        budget_status = "needs_price_evidence"
        budget_block_reason = str(cost_result["unknown_price"])
    elif budget_block_reason:
        budget_status = "blocked"
    else:
        budget_status = "passed"
    provider_call_allowed = (
        not freeze_active and approval_result["valid"] and budget_status == "passed"
    )
    if _is_exempt_provider(provider_id):
        status = "local_exempt"
    elif not approval_result["valid"]:
        status = "approval_required"
    elif budget_status != "passed":
        status = budget_status
    elif freeze_active:
        status = "provider_gated_by_no_quota_freeze"
    else:
        status = "approved_smallest_limit"
    return {
        "schema_version": 1,
        "preflight_kind": "provider_quota_approval",
        "dry_run": True,
        "status": status,
        "provider_call_allowed": provider_call_allowed,
        "provider_requests_sent": 0,
        "provider_quota_freeze_active": freeze_active,
        "db_path": str(path),
        "policy_id": policy_id,
        "run_id": run_id,
        "provider": provider_id,
        "model": model_id,
        "operation": operation_id,
        "provider_role": provider_role,
        "approved_scope": approved_scope,
        "units": normalized_units,
        "estimated_cost_usd": float(cost_result["estimated_cost_usd"]),
        "price_status": cost_result["metadata"].get("price_status"),
        "price_metadata": cost_result["metadata"],
        "budget_guard": {
            "status": budget_status,
            "block_reason": budget_block_reason,
        },
        "approval_contract": approval_result,
    }


def format_provider_quota_preflight(report: dict[str, Any]) -> str:
    approval = report["approval_contract"]
    budget = report["budget_guard"]
    lines = [
        f"status: {report['status']}",
        f"dry_run: {report['dry_run']}",
        f"provider_call_allowed: {report['provider_call_allowed']}",
        f"provider_requests_sent: {report['provider_requests_sent']}",
        (
            "target: "
            f"{report['provider']}/{report['model']} {report['operation']} "
            f"scope={report.get('approved_scope') or ''}"
        ),
        f"units: {json.dumps(report['units'], ensure_ascii=False, sort_keys=True)}",
        f"estimated_cost_usd: {report['estimated_cost_usd']:.8f}",
        f"budget_guard: {budget['status']} {budget.get('block_reason') or ''}".rstrip(),
        f"approval_contract: {'valid' if approval['valid'] else 'invalid'}",
    ]
    for error in approval["errors"]:
        lines.append(f"  approval_error: {error}")
    if report["provider_quota_freeze_active"]:
        lines.append("stop_condition: no_quota_provider_freeze")
    return "\n".join(lines)


def ensure_api_budget_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS memory_api_budget_policies (
            policy_id TEXT PRIMARY KEY,
            enabled INTEGER NOT NULL,
            max_run_usd REAL,
            max_day_usd REAL,
            max_month_usd REAL,
            max_run_calls INTEGER,
            max_day_calls INTEGER,
            max_run_input_tokens INTEGER,
            max_run_media_bytes INTEGER,
            unknown_price_action TEXT NOT NULL,
            kill_switch_enabled INTEGER NOT NULL,
            metadata_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS memory_api_usage_events (
            event_id TEXT PRIMARY KEY,
            run_id TEXT,
            job_id TEXT,
            policy_id TEXT NOT NULL,
            provider TEXT NOT NULL,
            model TEXT NOT NULL,
            provider_role TEXT NOT NULL,
            operation TEXT NOT NULL,
            status TEXT NOT NULL,
            units_json TEXT NOT NULL,
            estimated_cost_usd REAL NOT NULL,
            actual_cost_usd REAL,
            request_hash TEXT,
            started_at TEXT NOT NULL,
            finished_at TEXT,
            error TEXT,
            metadata_json TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS memory_api_price_catalog (
            provider TEXT NOT NULL,
            model TEXT NOT NULL,
            operation TEXT NOT NULL,
            unit TEXT NOT NULL,
            usd_per_unit REAL NOT NULL,
            source_url TEXT,
            checked_at TEXT NOT NULL,
            notes TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY(provider, model, operation, unit)
        );

        CREATE INDEX IF NOT EXISTS idx_memory_api_usage_run
            ON memory_api_usage_events(run_id, started_at);
        CREATE INDEX IF NOT EXISTS idx_memory_api_usage_provider
            ON memory_api_usage_events(provider, model, operation, started_at);
        CREATE INDEX IF NOT EXISTS idx_memory_api_usage_status
            ON memory_api_usage_events(status, started_at);
        """
    )
    ensure_default_api_budget_policy(conn)


def ensure_default_api_budget_policy(conn: sqlite3.Connection) -> None:
    now = _utc_now()
    conn.execute(
        """
        INSERT OR IGNORE INTO memory_api_budget_policies (
            policy_id, enabled, max_run_usd, max_day_usd, max_month_usd,
            max_run_calls, max_day_calls, max_run_input_tokens, max_run_media_bytes,
            unknown_price_action, kill_switch_enabled, metadata_json, created_at, updated_at
        )
        VALUES (?, 1, ?, ?, ?, NULL, NULL, NULL, NULL, ?, 0, ?, ?, ?)
        """,
        (
            DEFAULT_API_BUDGET_POLICY_ID,
            DEFAULT_MAX_RUN_USD,
            DEFAULT_MAX_DAY_USD,
            DEFAULT_MAX_MONTH_USD,
            DEFAULT_UNKNOWN_PRICE_ACTION,
            json.dumps({"warning_fraction": DEFAULT_WARNING_FRACTION}, sort_keys=True),
            now,
            now,
        ),
    )


def reserve_api_budget(
    context: ApiBudgetContext,
    *,
    provider: str,
    model: str,
    provider_role: str,
    operation: str,
    units: dict[str, int | float],
    request_payload: Any | None,
    metadata: dict[str, Any] | None = None,
) -> ApiBudgetReservation:
    db_path = Path(context.db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    provider_id = _clean_id(provider)
    model_id = _clean_model(model)
    operation_id = _clean_id(operation)
    units = _normalize_units(units)
    request_hash = _request_hash(request_payload)
    now = _utc_now()
    event_id = _event_id(
        context.run_id or "",
        provider_id,
        model_id,
        provider_role,
        operation_id,
        request_hash,
        now,
    )
    metadata_payload = {
        **(context.metadata or {}),
        **(metadata or {}),
        "allow_unpriced_api": context.allow_unpriced_api,
    }
    with sqlite3.connect(db_path, timeout=60, isolation_level=None) as conn:
        conn.row_factory = sqlite3.Row
        ensure_api_budget_schema(conn)
        conn.execute("BEGIN IMMEDIATE")
        try:
            policy = _policy_row(conn, context.policy_id)
            if policy is None:
                raise ApiBudgetError(f"API budget policy not found: {context.policy_id}")
            if context.no_quota_freeze_active and not _is_exempt_provider(provider_id):
                _insert_api_event(
                    conn,
                    event_id=event_id,
                    context=context,
                    provider=provider_id,
                    model=model_id,
                    provider_role=provider_role,
                    operation=operation_id,
                    status="blocked",
                    units=units,
                    estimated_cost_usd=0.0,
                    request_hash=request_hash,
                    started_at=now,
                    finished_at=now,
                    error=NO_QUOTA_FREEZE_BLOCK_MESSAGE,
                    metadata={
                        **metadata_payload,
                        "freeze_status": NO_QUOTA_FREEZE_BLOCK_STATUS,
                        "price_status": "not_checked_due_to_freeze",
                    },
                )
                conn.execute("COMMIT")
                raise ApiBudgetExceededError(
                    f"{BUDGET_EXHAUSTED_STATUS}: {NO_QUOTA_FREEZE_BLOCK_MESSAGE}",
                    event_id=event_id,
                )
            if not int(policy["enabled"]):
                conn.execute("COMMIT")
                return ApiBudgetReservation(str(db_path), event_id, 0.0)
            block_reason = _policy_block_reason(policy)
            cost_result = _estimated_cost(
                conn,
                provider=provider_id,
                model=model_id,
                operation=operation_id,
                units=units,
                allow_unpriced=context.allow_unpriced_api,
                unknown_price_action=str(policy["unknown_price_action"] or "block"),
            )
            if block_reason is None:
                block_reason = _cap_block_reason(
                    conn,
                    policy,
                    run_id=context.run_id,
                    estimated_cost=cost_result["estimated_cost_usd"],
                    units=units,
                    max_run_usd_override=context.max_run_usd_override,
                )
            if cost_result.get("unknown_price") and block_reason is None:
                block_reason = str(cost_result["unknown_price"])
            if block_reason is not None:
                _insert_api_event(
                    conn,
                    event_id=event_id,
                    context=context,
                    provider=provider_id,
                    model=model_id,
                    provider_role=provider_role,
                    operation=operation_id,
                    status="blocked",
                    units=units,
                    estimated_cost_usd=float(cost_result["estimated_cost_usd"]),
                    request_hash=request_hash,
                    started_at=now,
                    finished_at=now,
                    error=block_reason,
                    metadata={**metadata_payload, **cost_result["metadata"]},
                )
                conn.execute("COMMIT")
                raise ApiBudgetExceededError(
                    f"{BUDGET_EXHAUSTED_STATUS}: {block_reason}",
                    event_id=event_id,
                )
            _insert_api_event(
                conn,
                event_id=event_id,
                context=context,
                provider=provider_id,
                model=model_id,
                provider_role=provider_role,
                operation=operation_id,
                status="reserved",
                units=units,
                estimated_cost_usd=float(cost_result["estimated_cost_usd"]),
                request_hash=request_hash,
                started_at=now,
                finished_at=None,
                error=None,
                metadata={**metadata_payload, **cost_result["metadata"]},
            )
            conn.execute("COMMIT")
        except ApiBudgetExceededError:
            raise
        except Exception:
            conn.execute("ROLLBACK")
            raise
    return ApiBudgetReservation(
        db_path=str(db_path),
        event_id=event_id,
        estimated_cost_usd=float(cost_result["estimated_cost_usd"]),
    )


def finish_api_budget_event(
    db_path: str | Path,
    event_id: str,
    *,
    status: str,
    actual_cost_usd: float | None = None,
    error: str | None = None,
) -> None:
    with sqlite3.connect(db_path, timeout=60) as conn:
        ensure_api_budget_schema(conn)
        conn.execute(
            """
            UPDATE memory_api_usage_events
            SET status = ?, actual_cost_usd = ?, finished_at = ?, error = ?
            WHERE event_id = ?
            """,
            (status, actual_cost_usd, _utc_now(), error, event_id),
        )


def set_api_budget_policy(
    db_path: str | Path,
    *,
    policy_id: str = DEFAULT_API_BUDGET_POLICY_ID,
    enabled: bool | None = None,
    max_run_usd: float | None = None,
    max_day_usd: float | None = None,
    max_month_usd: float | None = None,
    max_run_calls: int | None = None,
    max_day_calls: int | None = None,
    max_run_input_tokens: int | None = None,
    max_run_media_bytes: int | None = None,
    unknown_price_action: str | None = None,
) -> dict[str, Any]:
    with sqlite3.connect(db_path, timeout=60) as conn:
        conn.row_factory = sqlite3.Row
        ensure_api_budget_schema(conn)
        row = _policy_row(conn, policy_id)
        if row is None:
            raise ApiBudgetError(f"API budget policy not found: {policy_id}")
        values = {
            "enabled": int(enabled) if enabled is not None else int(row["enabled"]),
            "max_run_usd": _coalesce(max_run_usd, row["max_run_usd"]),
            "max_day_usd": _coalesce(max_day_usd, row["max_day_usd"]),
            "max_month_usd": _coalesce(max_month_usd, row["max_month_usd"]),
            "max_run_calls": _coalesce(max_run_calls, row["max_run_calls"]),
            "max_day_calls": _coalesce(max_day_calls, row["max_day_calls"]),
            "max_run_input_tokens": _coalesce(
                max_run_input_tokens,
                row["max_run_input_tokens"],
            ),
            "max_run_media_bytes": _coalesce(
                max_run_media_bytes,
                row["max_run_media_bytes"],
            ),
            "unknown_price_action": unknown_price_action or row["unknown_price_action"],
        }
        if values["unknown_price_action"] not in {"block", "allow"}:
            raise ValueError("unknown_price_action must be block or allow")
        conn.execute(
            """
            UPDATE memory_api_budget_policies
            SET enabled = ?, max_run_usd = ?, max_day_usd = ?, max_month_usd = ?,
                max_run_calls = ?, max_day_calls = ?, max_run_input_tokens = ?,
                max_run_media_bytes = ?, unknown_price_action = ?, updated_at = ?
            WHERE policy_id = ?
            """,
            (
                values["enabled"],
                values["max_run_usd"],
                values["max_day_usd"],
                values["max_month_usd"],
                values["max_run_calls"],
                values["max_day_calls"],
                values["max_run_input_tokens"],
                values["max_run_media_bytes"],
                values["unknown_price_action"],
                _utc_now(),
                policy_id,
            ),
        )
    return api_budget_status(db_path, policy_id=policy_id)


def set_api_kill_switch(
    db_path: str | Path,
    *,
    policy_id: str = DEFAULT_API_BUDGET_POLICY_ID,
    enabled: bool,
) -> dict[str, Any]:
    with sqlite3.connect(db_path, timeout=60) as conn:
        ensure_api_budget_schema(conn)
        conn.execute(
            """
            UPDATE memory_api_budget_policies
            SET kill_switch_enabled = ?, updated_at = ?
            WHERE policy_id = ?
            """,
            (int(enabled), _utc_now(), policy_id),
        )
    return api_budget_status(db_path, policy_id=policy_id)


def upsert_api_price(
    db_path: str | Path,
    *,
    provider: str,
    model: str,
    operation: str,
    unit: str,
    usd_per_unit: float,
    source_url: str | None = None,
    checked_at: str | None = None,
    notes: str | None = None,
) -> None:
    if usd_per_unit < 0:
        raise ValueError("usd_per_unit must be non-negative")
    now = _utc_now()
    unit_id = _canonical_price_unit(unit)
    with sqlite3.connect(db_path, timeout=60) as conn:
        ensure_api_budget_schema(conn)
        conn.execute(
            """
            INSERT INTO memory_api_price_catalog (
                provider, model, operation, unit, usd_per_unit,
                source_url, checked_at, notes, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(provider, model, operation, unit) DO UPDATE SET
                usd_per_unit = excluded.usd_per_unit,
                source_url = excluded.source_url,
                checked_at = excluded.checked_at,
                notes = excluded.notes,
                updated_at = excluded.updated_at
            """,
            (
                _clean_id(provider),
                _clean_model(model),
                _clean_id(operation),
                unit_id,
                float(usd_per_unit),
                source_url,
                checked_at or now,
                notes,
                now,
                now,
            ),
        )


def api_budget_status(
    db_path: str | Path,
    *,
    policy_id: str = DEFAULT_API_BUDGET_POLICY_ID,
    run_id: str | None = None,
    recent_limit: int = 20,
) -> dict[str, Any]:
    path = Path(db_path)
    with sqlite3.connect(path, timeout=60) as conn:
        conn.row_factory = sqlite3.Row
        ensure_api_budget_schema(conn)
        policy = _policy_row(conn, policy_id)
        if policy is None:
            raise ApiBudgetError(f"API budget policy not found: {policy_id}")
        usage = {
            "run": _usage_for_window(conn, run_id=run_id),
            "day": _usage_for_window(conn, since=_day_start()),
            "month": _usage_for_window(conn, since=_month_start()),
        }
        provider_rows = _provider_usage(conn, since=_day_start())
        events = _recent_events(conn, limit=recent_limit)
        prices = _price_rows(conn)
    return {
        "db_path": str(path),
        "policy": _row_dict(policy),
        "run_id": run_id,
        "usage": usage,
        "provider_usage_today": provider_rows,
        "recent_events": events,
        "price_catalog": prices,
        "warnings": _budget_warnings(_row_dict(policy), usage),
    }


def api_usage_report(
    db_path: str | Path,
    *,
    run_id: str | None = None,
    today: bool = False,
    month: bool = False,
    limit: int = 100,
) -> dict[str, Any]:
    since = None
    if today:
        since = _day_start()
    if month:
        since = _month_start()
    with sqlite3.connect(db_path, timeout=60) as conn:
        conn.row_factory = sqlite3.Row
        ensure_api_budget_schema(conn)
        events = _recent_events(conn, run_id=run_id, since=since, limit=limit)
        usage = _usage_for_window(conn, run_id=run_id, since=since)
    return {"usage": usage, "events": events}


def format_api_budget_status(status: dict[str, Any]) -> str:
    policy = status["policy"]
    usage = status["usage"]
    lines = [
        f"db: {status['db_path']}",
        (
            "policy: "
            f"{policy['policy_id']} enabled={bool(policy['enabled'])} "
            f"kill_switch={bool(policy['kill_switch_enabled'])} "
            f"unknown_price={policy['unknown_price_action']}"
        ),
        _usage_line("run", usage["run"], policy.get("max_run_usd")),
        _usage_line("day", usage["day"], policy.get("max_day_usd")),
        _usage_line("month", usage["month"], policy.get("max_month_usd")),
    ]
    if status["warnings"]:
        lines.append("warnings: " + "; ".join(status["warnings"]))
    lines.append("provider/model today:")
    for row in status["provider_usage_today"][:20]:
        lines.append(
            "  "
            f"{row['provider']}/{row['model']} {row['operation']} "
            f"calls={row['calls']} cost=${row['estimated_cost_usd']:.6f}"
        )
    lines.append("recent events:")
    for row in status["recent_events"][:10]:
        lines.append(
            "  "
            f"{row['status']} {row['provider']}/{row['model']} {row['operation']} "
            f"cost=${row['estimated_cost_usd']:.6f} error={row.get('error') or ''}"
        )
    return "\n".join(lines)


def format_api_usage_report(report: dict[str, Any]) -> str:
    usage = report["usage"]
    lines = [
        (
            "usage: "
            f"calls={usage['calls']} "
            f"input_tokens={usage['input_tokens']} "
            f"media_bytes={usage['media_bytes']} "
            f"estimated=${usage['estimated_cost_usd']:.6f}"
        )
    ]
    for row in report["events"]:
        lines.append(
            f"{row['started_at']} {row['status']} {row['provider']}/{row['model']} "
            f"{row['operation']} cost=${row['estimated_cost_usd']:.6f} "
            f"units={json.dumps(row['units'], ensure_ascii=False, sort_keys=True)} "
            f"error={row.get('error') or ''}"
        )
    return "\n".join(lines)


def serve_api_watch(
    *,
    db_path: str | Path,
    host: str = "127.0.0.1",
    port: int = 8767,
    open_browser: bool = True,
) -> None:
    db_text = str(db_path)

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            if parsed.path == "/api/status":
                self._json(api_budget_status(db_text))
                return
            if parsed.path == "/":
                self._html(_watch_page(db_text))
                return
            self.send_error(404)

        def log_message(self, format: str, *args: Any) -> None:
            return

        def _html(self, body: str) -> None:
            payload = body.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def _json(self, value: dict[str, Any]) -> None:
            payload = json.dumps(value, ensure_ascii=False, sort_keys=True).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

    server = ThreadingHTTPServer((host, port), Handler)
    url = f"http://{host}:{port}"
    print(f"research_x api-watch: {url}")
    try:
        if open_browser:
            webbrowser.open(url)
        server.serve_forever()
    except KeyboardInterrupt:
        print("research_x api-watch: shutting down")
    finally:
        server.server_close()


def _watch_page(db_path: str) -> str:
    escaped_db = html.escape(db_path)
    return f"""<!doctype html>
<html lang="ja">
<head>
  <meta charset="utf-8">
  <title>research_x API budget</title>
  <style>
    body {{ font-family: system-ui, sans-serif; margin: 24px; }}
    .grid {{ display: grid; gap: 14px; max-width: 1100px; }}
    .bar {{ background: #e5e7eb; border-radius: 4px; height: 18px; overflow: hidden; }}
    .fill {{ background: #2563eb; height: 100%; width: 0%; }}
    .warn {{ background: #f59e0b; }}
    .bad {{ background: #dc2626; }}
    pre {{ background: #f3f4f6; padding: 12px; overflow: auto; }}
  </style>
</head>
<body>
  <h1>research_x API budget</h1>
  <p>db: {escaped_db}</p>
  <div id="budget" class="grid"></div>
  <pre id="events"></pre>
  <script>
    function pct(value, max) {{
      if (!max || max <= 0) return 0;
      return Math.max(0, Math.min(100, value / max * 100));
    }}
    function money(value) {{
      return "$" + Number(value || 0).toFixed(6);
    }}
    function renderWindow(name, usage, max) {{
      const p = pct(usage.estimated_cost_usd || 0, max);
      const cls = p >= 100 ? "bad" : p >= 80 ? "warn" : "";
      return `<section><strong>${{name}}</strong> ` +
        `${{money(usage.estimated_cost_usd)}} / ${{max == null ? "none" : money(max)}} ` +
        `calls=${{usage.calls || 0}} tokens=${{usage.input_tokens || 0}}` +
        `<div class="bar"><div class="fill ${{cls}}" style="width:${{p}}%"></div></div>` +
        `</section>`;
    }}
    async function poll() {{
      const response = await fetch("/api/status", {{cache: "no-store"}});
      const payload = await response.json();
      const policy = payload.policy || {{}};
      const usage = payload.usage || {{}};
      document.getElementById("budget").innerHTML = [
        `<section>policy=${{policy.policy_id}} enabled=${{Boolean(policy.enabled)}} ` +
        `kill_switch=${{Boolean(policy.kill_switch_enabled)}} ` +
        `unknown_price=${{policy.unknown_price_action}}</section>`,
        renderWindow("run", usage.run || {{}}, policy.max_run_usd),
        renderWindow("day", usage.day || {{}}, policy.max_day_usd),
        renderWindow("month", usage.month || {{}}, policy.max_month_usd),
        `<section>warnings: ${{(payload.warnings || []).join("; ")}}</section>`
      ].join("");
      document.getElementById("events").textContent =
        JSON.stringify(payload.recent_events || [], null, 2);
    }}
    setInterval(poll, 1000);
    poll();
  </script>
</body>
</html>"""


def _insert_api_event(
    conn: sqlite3.Connection,
    *,
    event_id: str,
    context: ApiBudgetContext,
    provider: str,
    model: str,
    provider_role: str,
    operation: str,
    status: str,
    units: dict[str, int | float],
    estimated_cost_usd: float,
    request_hash: str | None,
    started_at: str,
    finished_at: str | None,
    error: str | None,
    metadata: dict[str, Any],
) -> None:
    conn.execute(
        """
        INSERT INTO memory_api_usage_events (
            event_id, run_id, job_id, policy_id, provider, model, provider_role, operation,
            status, units_json, estimated_cost_usd, actual_cost_usd, request_hash,
            started_at, finished_at, error, metadata_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?, ?, ?, ?)
        """,
        (
            event_id,
            context.run_id,
            context.job_id,
            context.policy_id,
            provider,
            model,
            provider_role,
            operation,
            status,
            json.dumps(units, ensure_ascii=False, sort_keys=True),
            estimated_cost_usd,
            request_hash,
            started_at,
            finished_at,
            error,
            json.dumps(metadata, ensure_ascii=False, sort_keys=True),
        ),
    )


def _estimated_cost(
    conn: sqlite3.Connection,
    *,
    provider: str,
    model: str,
    operation: str,
    units: dict[str, int | float],
    allow_unpriced: bool,
    unknown_price_action: str,
) -> dict[str, Any]:
    price_rows = _matching_price_rows(conn, provider=provider, model=model, operation=operation)
    if not price_rows:
        unknown = f"price catalog missing for {provider}/{model} operation={operation}"
        if unknown_price_action == "block" and not allow_unpriced:
            return {
                "estimated_cost_usd": 0.0,
                "unknown_price": unknown,
                "metadata": {"price_status": "missing"},
            }
        return {
            "estimated_cost_usd": 0.0,
            "unknown_price": None,
            "metadata": {"price_status": "unpriced_override", "price_warning": unknown},
        }
    by_unit = {str(row["unit"]): float(row["usd_per_unit"]) for row in price_rows}
    total = 0.0
    matched_units: list[str] = []
    for unit, key in _price_unit_keys().items():
        amount = float(units.get(key, 0) or 0)
        if amount and unit in by_unit:
            matched_units.append(unit)
            total += amount * by_unit[unit]
    if not matched_units:
        unknown = (
            f"price catalog has no matching billable unit for {provider}/{model} "
            f"operation={operation}"
        )
        if unknown_price_action == "block" and not allow_unpriced:
            return {
                "estimated_cost_usd": 0.0,
                "unknown_price": unknown,
                "metadata": {
                    "price_status": "unit_mismatch",
                    "catalog_units": sorted(by_unit),
                },
            }
    return {
        "estimated_cost_usd": total,
        "unknown_price": None,
        "metadata": {
            "price_status": "priced" if matched_units else "unpriced_override",
            "priced_units": matched_units,
        },
    }


def _matching_price_rows(
    conn: sqlite3.Connection,
    *,
    provider: str,
    model: str,
    operation: str,
) -> list[sqlite3.Row]:
    rows = conn.execute(
        """
        SELECT provider, model, operation, unit, usd_per_unit
        FROM memory_api_price_catalog
        WHERE provider IN (?, '*')
          AND model IN (?, '*')
          AND operation IN (?, '*')
        ORDER BY
          CASE WHEN provider = ? THEN 0 ELSE 1 END,
          CASE WHEN model = ? THEN 0 ELSE 1 END,
          CASE WHEN operation = ? THEN 0 ELSE 1 END
        """,
        (provider, model, operation, provider, model, operation),
    ).fetchall()
    best: dict[str, sqlite3.Row] = {}
    for row in rows:
        best.setdefault(str(row["unit"]), row)
    return list(best.values())


def _cap_block_reason(
    conn: sqlite3.Connection,
    policy: sqlite3.Row,
    *,
    run_id: str | None,
    estimated_cost: float,
    units: dict[str, int | float],
    max_run_usd_override: float | None,
) -> str | None:
    run_usage = _usage_for_window(conn, run_id=run_id)
    day_usage = _usage_for_window(conn, since=_day_start())
    month_usage = _usage_for_window(conn, since=_month_start())
    run_max = max_run_usd_override if max_run_usd_override is not None else policy["max_run_usd"]
    checks = [
        ("run USD", run_usage["estimated_cost_usd"] + estimated_cost, run_max),
        ("day USD", day_usage["estimated_cost_usd"] + estimated_cost, policy["max_day_usd"]),
        (
            "month USD",
            month_usage["estimated_cost_usd"] + estimated_cost,
            policy["max_month_usd"],
        ),
        (
            "run calls",
            run_usage["calls"] + int(units.get("calls", 0) or 0),
            policy["max_run_calls"],
        ),
        (
            "day calls",
            day_usage["calls"] + int(units.get("calls", 0) or 0),
            policy["max_day_calls"],
        ),
        (
            "run input_tokens",
            run_usage["input_tokens"] + int(units.get("input_tokens", 0) or 0),
            policy["max_run_input_tokens"],
        ),
        (
            "run media_bytes",
            run_usage["media_bytes"] + int(units.get("media_bytes", 0) or 0),
            policy["max_run_media_bytes"],
        ),
    ]
    for label, value, limit in checks:
        if limit is not None and float(value) > float(limit):
            return f"{label} budget exceeded: {value} > {limit}"
    return None


def _usage_for_window(
    conn: sqlite3.Connection,
    *,
    run_id: str | None = None,
    since: str | None = None,
) -> dict[str, Any]:
    clauses = ["status IN ('reserved', 'ok', 'error')"]
    params: list[Any] = []
    if run_id:
        clauses.append("run_id = ?")
        params.append(run_id)
    if since:
        clauses.append("started_at >= ?")
        params.append(since)
    rows = conn.execute(
        f"""
        SELECT units_json, estimated_cost_usd
        FROM memory_api_usage_events
        WHERE {' AND '.join(clauses)}
        """,
        params,
    ).fetchall()
    usage = {
        "calls": 0,
        "retries": 0,
        "input_tokens": 0,
        "output_tokens": 0,
        "media_bytes": 0,
        "documents": 0,
        "pages": 0,
        "estimated_cost_usd": 0.0,
    }
    for row in rows:
        units = _loads_dict(row["units_json"])
        for key in tuple(usage):
            if key == "estimated_cost_usd":
                continue
            usage[key] += int(float(units.get(key, 0) or 0))
        usage["estimated_cost_usd"] += float(row["estimated_cost_usd"] or 0.0)
    return usage


def _provider_usage(conn: sqlite3.Connection, *, since: str | None = None) -> list[dict[str, Any]]:
    clauses = ["status IN ('reserved', 'ok', 'error')"]
    params: list[Any] = []
    if since:
        clauses.append("started_at >= ?")
        params.append(since)
    rows = conn.execute(
        f"""
        SELECT provider, model, operation, units_json, estimated_cost_usd
        FROM memory_api_usage_events
        WHERE {' AND '.join(clauses)}
        """,
        params,
    ).fetchall()
    grouped: dict[tuple[str, str, str], dict[str, Any]] = {}
    for row in rows:
        key = (row["provider"], row["model"], row["operation"])
        bucket = grouped.setdefault(
            key,
            {
                "provider": key[0],
                "model": key[1],
                "operation": key[2],
                "calls": 0,
                "input_tokens": 0,
                "media_bytes": 0,
                "estimated_cost_usd": 0.0,
            },
        )
        units = _loads_dict(row["units_json"])
        bucket["calls"] += int(float(units.get("calls", 0) or 0))
        bucket["input_tokens"] += int(float(units.get("input_tokens", 0) or 0))
        bucket["media_bytes"] += int(float(units.get("media_bytes", 0) or 0))
        bucket["estimated_cost_usd"] += float(row["estimated_cost_usd"] or 0.0)
    return sorted(grouped.values(), key=lambda item: item["estimated_cost_usd"], reverse=True)


def _recent_events(
    conn: sqlite3.Connection,
    *,
    run_id: str | None = None,
    since: str | None = None,
    limit: int = 20,
) -> list[dict[str, Any]]:
    clauses: list[str] = []
    params: list[Any] = []
    if run_id:
        clauses.append("run_id = ?")
        params.append(run_id)
    if since:
        clauses.append("started_at >= ?")
        params.append(since)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    rows = conn.execute(
        f"""
        SELECT *
        FROM memory_api_usage_events
        {where}
        ORDER BY started_at DESC
        LIMIT ?
        """,
        [*params, max(1, limit)],
    ).fetchall()
    result = []
    for row in rows:
        item = _row_dict(row)
        item["units"] = _loads_dict(item.pop("units_json", "{}"))
        item["metadata"] = _loads_dict(item.pop("metadata_json", "{}"))
        result.append(item)
    return result


def _price_rows(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT provider, model, operation, unit, usd_per_unit, source_url, checked_at, notes
        FROM memory_api_price_catalog
        ORDER BY provider, model, operation, unit
        """
    ).fetchall()
    return [_row_dict(row) for row in rows]


def _budget_warnings(policy: dict[str, Any], usage: dict[str, Any]) -> list[str]:
    warnings = []
    for label, key in (("run", "max_run_usd"), ("day", "max_day_usd"), ("month", "max_month_usd")):
        limit = policy.get(key)
        if limit is None:
            continue
        used = float(usage[label]["estimated_cost_usd"])
        if used >= float(limit):
            warnings.append(f"{label} budget exhausted")
        elif used >= float(limit) * DEFAULT_WARNING_FRACTION:
            warnings.append(f"{label} budget over {int(DEFAULT_WARNING_FRACTION * 100)}%")
    if policy.get("kill_switch_enabled"):
        warnings.append("kill switch enabled")
    return warnings


def _policy_row(conn: sqlite3.Connection, policy_id: str) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM memory_api_budget_policies WHERE policy_id = ?",
        (policy_id,),
    ).fetchone()


def _policy_block_reason(policy: sqlite3.Row) -> str | None:
    if int(policy["kill_switch_enabled"]):
        return "API budget kill switch is enabled"
    return None


def _price_unit_keys() -> dict[str, str]:
    return {
        "input_token": "input_tokens",
        "output_token": "output_tokens",
        "media_byte": "media_bytes",
        "document": "documents",
        "page": "pages",
        "call": "calls",
        "gb_day": "gb_day",
    }


def _canonical_price_unit(value: str) -> str:
    unit = _clean_id(value)
    aliases = {
        "input_tokens": "input_token",
        "output_tokens": "output_token",
        "media_bytes": "media_byte",
        "documents": "document",
        "pages": "page",
        "calls": "call",
        "gb_days": "gb_day",
    }
    return aliases.get(unit, unit)


def _normalize_units(units: dict[str, int | float]) -> dict[str, int | float]:
    normalized: dict[str, int | float] = {}
    for key, value in units.items():
        if value is None:
            continue
        number = float(value)
        if number <= 0:
            continue
        normalized[_clean_id(key)] = int(number) if number.is_integer() else number
    if "calls" not in normalized:
        normalized["calls"] = 1
    return normalized


def _coerce_provider_quota_approval(
    approval: ProviderQuotaApproval | dict[str, Any] | None,
) -> ProviderQuotaApproval | None:
    if approval is None:
        return None
    if isinstance(approval, ProviderQuotaApproval):
        return approval
    if not isinstance(approval, dict):
        raise TypeError("provider quota approval must be a mapping")
    required = (
        "provider_quota_approval_id",
        "provider",
        "model",
        "operation",
        "max_calls",
        "max_cost_usd",
        "price_source",
        "approved_scope",
        "approved_at",
    )
    missing = [key for key in required if approval.get(key) in (None, "")]
    if missing:
        raise ValueError("provider quota approval missing fields: " + ", ".join(missing))
    return ProviderQuotaApproval(
        provider_quota_approval_id=str(approval["provider_quota_approval_id"]),
        provider=str(approval["provider"]),
        model=str(approval["model"]),
        operation=str(approval["operation"]),
        max_calls=int(approval["max_calls"]),
        max_cost_usd=float(approval["max_cost_usd"]),
        price_source=str(approval["price_source"]),
        approved_scope=str(approval["approved_scope"]),
        approved_at=str(approval["approved_at"]),
        provider_role=_optional_str(approval.get("provider_role")),
        approved_by=_optional_str(approval.get("approved_by")),
        expires_at=_optional_str(approval.get("expires_at")),
        metadata=approval.get("metadata") if isinstance(approval.get("metadata"), dict) else None,
    )


def _provider_quota_validation_payload(
    *,
    approval: ProviderQuotaApproval | None,
    errors: list[str],
    units: dict[str, int | float],
    estimated_cost_usd: float | None,
) -> dict[str, Any]:
    return {
        "valid": not errors,
        "errors": errors,
        "approval": provider_quota_approval_as_dict(approval) if approval else None,
        "units": units,
        "estimated_cost_usd": estimated_cost_usd,
    }


def _validate_approval_timestamp(
    field_name: str,
    value: str,
    errors: list[str],
) -> datetime | None:
    text = str(value).strip()
    if not text:
        errors.append(f"approval {field_name} is required")
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        errors.append(f"approval {field_name} must be ISO-8601")
        return None
    if parsed.tzinfo is None:
        errors.append(f"approval {field_name} must include a timezone")
        return None
    return parsed


def _optional_str(value: Any) -> str | None:
    if value in (None, ""):
        return None
    return str(value)


def _count_text_chars(value: Any) -> int:
    if value is None:
        return 0
    if isinstance(value, str):
        return len(value)
    if isinstance(value, bytes):
        return len(value)
    if isinstance(value, dict):
        return sum(_count_text_chars(item) for item in value.values())
    if isinstance(value, (list, tuple, set)):
        return sum(_count_text_chars(item) for item in value)
    return len(str(value))


def _request_hash(value: Any | None) -> str | None:
    if value is None:
        return None
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()


def _event_id(*parts: object) -> str:
    payload = "|".join(str(part) for part in (*parts, uuid.uuid4().hex))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]


def _clean_id(value: str) -> str:
    return str(value or "").strip().lower() or "unknown"


def _clean_model(value: str) -> str:
    return str(value or "").strip() or "unknown"


def _is_exempt_provider(provider: str) -> bool:
    provider_id = _clean_id(provider)
    return provider_id in EXEMPT_PROVIDERS or provider_id.startswith(EXEMPT_PROVIDER_PREFIXES)


def _coalesce(value: Any, fallback: Any) -> Any:
    return fallback if value is None else value


def _loads_dict(value: str | None) -> dict[str, Any]:
    if not value:
        return {}
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _row_dict(row: sqlite3.Row) -> dict[str, Any]:
    keys = row.keys()
    return {key: row[key] for key in keys}


def _usage_line(label: str, usage: dict[str, Any], max_usd: Any) -> str:
    limit = "none" if max_usd is None else f"${float(max_usd):.6f}"
    return (
        f"{label}: ${usage['estimated_cost_usd']:.6f}/{limit} "
        f"calls={usage['calls']} input_tokens={usage['input_tokens']} "
        f"media_bytes={usage['media_bytes']}"
    )


def _utc_now() -> str:
    return datetime.now(tz=UTC).isoformat()


def _day_start() -> str:
    now = datetime.now(tz=UTC)
    return datetime(now.year, now.month, now.day, tzinfo=UTC).isoformat()


def _month_start() -> str:
    now = datetime.now(tz=UTC)
    return datetime(now.year, now.month, 1, tzinfo=UTC).isoformat()


def _unused_recent_start() -> str:
    return (datetime.now(tz=UTC) - timedelta(days=1)).isoformat()
