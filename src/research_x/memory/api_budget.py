from __future__ import annotations

import contextlib
import hashlib
import html
import json
import sqlite3
import uuid
import webbrowser
from collections.abc import Iterator, Mapping
from contextvars import ContextVar
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime, timedelta
from enum import StrEnum
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
EXEMPT_PROVIDERS = {"fake", "local", "local_hash", "fixture_media"}
BUDGET_EXHAUSTED_STATUS = "budget_exhausted"
LEGACY_NO_QUOTA_FREEZE_BLOCK_STATUS = "provider_gated_by_no_quota_freeze"
PROVIDER_EXECUTION_POLICY_REQUIRED = True
PROVIDER_EXECUTION_POLICY_REQUIRED_STATUS = "provider_execution_policy_required"
PROVIDER_QUOTA_APPROVAL_GATE_MESSAGE = (
    "provider quota execution requires a scoped provider quota approval object; "
    "--allow-provider-quota alone is not sufficient"
)
PROVIDER_EXECUTION_POLICY_GATE_MESSAGE = (
    "provider execution requires a scoped ProviderExecutionPolicy or "
    "ProviderQuotaApproval; repository default blocks provider execution"
)
PROVIDER_EXECUTION_POLICY_REQUIRED_MESSAGE = (
    "provider_execution_policy_required: provider API calls require a scoped "
    "ProviderExecutionPolicy or ProviderQuotaApproval plus API Budget Guard before transport"
)
PROVIDER_EXECUTION_AUTHORIZED_STATUS = "authorized_by_provider_policy"


class ProviderOperationClass(StrEnum):
    UPSTREAM_REVIEW = "upstream_review"
    ADAPTER_DEVELOPMENT = "adapter_development"
    DRY_RUN_REQUEST_SHAPE = "dry_run_request_shape"
    RUNTIME_PROVIDER_CALL = "runtime_provider_call"
    QUOTA_CONSUMING_RUNTIME = "quota_consuming_runtime"
    DEPENDENCY_INSTALL = "dependency_install"
    MODEL_DOWNLOAD = "model_download"
    BROWSER_AUTOMATION = "browser_automation"
    CONNECTOR_AUTH = "connector_auth"
    PLUGIN_ENABLEMENT = "plugin_enablement"
    MCP_ENABLEMENT = "mcp_enablement"
    HOOK_ENABLEMENT = "hook_enablement"


@dataclass(frozen=True)
class ProviderOperationClassPolicy:
    operation_class: ProviderOperationClass
    provider_budget_required: bool
    explicit_approval_required: bool
    api_budget_guard_required: bool
    separate_gate: str | None
    notes: str

    def as_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["operation_class"] = self.operation_class.value
        return data


_OPERATION_CLASS_ALIASES = {
    "adapter": ProviderOperationClass.ADAPTER_DEVELOPMENT,
    "adapter_development": ProviderOperationClass.ADAPTER_DEVELOPMENT,
    "api_spec_review": ProviderOperationClass.UPSTREAM_REVIEW,
    "browser": ProviderOperationClass.BROWSER_AUTOMATION,
    "browser_automation": ProviderOperationClass.BROWSER_AUTOMATION,
    "classifier": ProviderOperationClass.RUNTIME_PROVIDER_CALL,
    "connector_auth": ProviderOperationClass.CONNECTOR_AUTH,
    "dependency_install": ProviderOperationClass.DEPENDENCY_INSTALL,
    "dry_run": ProviderOperationClass.DRY_RUN_REQUEST_SHAPE,
    "dry_run_request_shape": ProviderOperationClass.DRY_RUN_REQUEST_SHAPE,
    "embedding": ProviderOperationClass.RUNTIME_PROVIDER_CALL,
    "external_search": ProviderOperationClass.RUNTIME_PROVIDER_CALL,
    "github_review": ProviderOperationClass.UPSTREAM_REVIEW,
    "license_review": ProviderOperationClass.UPSTREAM_REVIEW,
    "hook_enablement": ProviderOperationClass.HOOK_ENABLEMENT,
    "llm_context": ProviderOperationClass.RUNTIME_PROVIDER_CALL,
    "managed_rag": ProviderOperationClass.RUNTIME_PROVIDER_CALL,
    "mcp_enablement": ProviderOperationClass.MCP_ENABLEMENT,
    "model_download": ProviderOperationClass.MODEL_DOWNLOAD,
    "ocr": ProviderOperationClass.RUNTIME_PROVIDER_CALL,
    "official_docs_review": ProviderOperationClass.UPSTREAM_REVIEW,
    "plugin_enablement": ProviderOperationClass.PLUGIN_ENABLEMENT,
    "quota_consuming_runtime": ProviderOperationClass.QUOTA_CONSUMING_RUNTIME,
    "reader": ProviderOperationClass.RUNTIME_PROVIDER_CALL,
    "release_review": ProviderOperationClass.UPSTREAM_REVIEW,
    "rerank": ProviderOperationClass.RUNTIME_PROVIDER_CALL,
    "runtime_provider_call": ProviderOperationClass.RUNTIME_PROVIDER_CALL,
    "source_review": ProviderOperationClass.UPSTREAM_REVIEW,
    "upstream_review": ProviderOperationClass.UPSTREAM_REVIEW,
}

_ACTIVE_CONTEXT: ContextVar[ApiBudgetContext | None] = ContextVar(
    "research_x_api_budget_context",
    default=None,
)
_PROVIDER_TRANSPORT_SEND_ALLOWED: ContextVar[ProviderTransportSend | None] = ContextVar(
    "research_x_provider_transport_send_allowed",
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
    provider_execution_policy: ProviderExecutionPolicy | None = None
    provider_quota_current_scope: str | None = None
    provider_policy_required: bool = PROVIDER_EXECUTION_POLICY_REQUIRED


@dataclass(frozen=True)
class ApiBudgetReservation:
    db_path: str
    event_id: str
    estimated_cost_usd: float
    transport_event_id: str | None = None


@dataclass(frozen=True)
class ProviderTransportSend:
    provider: str
    model: str
    operation: str
    provider_role: str


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


@dataclass(frozen=True)
class ProviderExecutionPolicy:
    policy_id: str
    authorization_id: str
    provider: str
    model: str
    operation: str
    provider_role: str | None = None
    allowed: bool = True
    max_calls: int | None = None
    max_cost_usd: float | None = None
    max_input_tokens: int | None = None
    max_output_tokens: int | None = None
    max_media_bytes: int | None = None
    max_documents: int | None = None
    valid_from: str | None = None
    valid_until: str | None = None
    approved_by: str | None = None
    approval_source: str | None = None
    approved_scope: str | None = None
    storage_rights: str | None = None
    prompt_injection_required: bool | None = None
    rollback_scope: str | None = None
    metadata: dict[str, Any] | None = None
    source_kind: str | None = None


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
    provider_execution_policy: ProviderExecutionPolicy | dict[str, Any] | None = None,
    provider_quota_current_scope: str | None = None,
    provider_policy_required: bool = PROVIDER_EXECUTION_POLICY_REQUIRED,
) -> Iterator[ApiBudgetContext]:
    approval = _coerce_provider_quota_approval(provider_quota_approval)
    execution_policy = _coerce_provider_execution_policy(provider_execution_policy)
    if execution_policy is None:
        execution_policy = _provider_execution_policy_from_approval(approval)
    context = ApiBudgetContext(
        db_path=str(db_path),
        policy_id=policy_id,
        run_id=run_id or f"api-{datetime.now(tz=UTC).strftime('%Y%m%d')}-{uuid.uuid4().hex[:8]}",
        job_id=job_id,
        max_run_usd_override=max_run_usd_override,
        allow_unpriced_api=allow_unpriced_api,
        metadata=metadata,
        provider_quota_approval=approval,
        provider_execution_policy=execution_policy,
        provider_quota_current_scope=provider_quota_current_scope,
        provider_policy_required=provider_policy_required,
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


def classify_provider_operation(operation: str) -> ProviderOperationClass:
    operation_id = _clean_id(operation)
    return _OPERATION_CLASS_ALIASES.get(
        operation_id,
        ProviderOperationClass.RUNTIME_PROVIDER_CALL,
    )


def provider_operation_class_policy(
    operation: str | ProviderOperationClass,
) -> ProviderOperationClassPolicy:
    operation_class = (
        operation
        if isinstance(operation, ProviderOperationClass)
        else classify_provider_operation(operation)
    )
    if operation_class is ProviderOperationClass.UPSTREAM_REVIEW:
        return ProviderOperationClassPolicy(
            operation_class=operation_class,
            provider_budget_required=False,
            explicit_approval_required=False,
            api_budget_guard_required=False,
            separate_gate=None,
            notes="source review only; not a runtime provider call by itself",
        )
    if operation_class is ProviderOperationClass.ADAPTER_DEVELOPMENT:
        return ProviderOperationClassPolicy(
            operation_class=operation_class,
            provider_budget_required=False,
            explicit_approval_required=False,
            api_budget_guard_required=False,
            separate_gate=None,
            notes="implementation and fixture tests only; no external send",
        )
    if operation_class is ProviderOperationClass.DRY_RUN_REQUEST_SHAPE:
        return ProviderOperationClassPolicy(
            operation_class=operation_class,
            provider_budget_required=False,
            explicit_approval_required=False,
            api_budget_guard_required=False,
            separate_gate=None,
            notes="request JSON construction only; not model-quality proof",
        )
    if operation_class in {
        ProviderOperationClass.RUNTIME_PROVIDER_CALL,
        ProviderOperationClass.QUOTA_CONSUMING_RUNTIME,
    }:
        return ProviderOperationClassPolicy(
            operation_class=operation_class,
            provider_budget_required=True,
            explicit_approval_required=True,
            api_budget_guard_required=True,
            separate_gate=None,
            notes="runtime provider call requires approval and API Budget Guard",
        )
    return ProviderOperationClassPolicy(
        operation_class=operation_class,
        provider_budget_required=False,
        explicit_approval_required=True,
        api_budget_guard_required=False,
        separate_gate=operation_class.value,
        notes="separate non-provider-runtime gate",
    )


def require_provider_execution_allowed(
    *,
    provider: str,
    model: str | None = None,
    operation: str | None = None,
) -> None:
    if _is_exempt_provider(provider):
        return
    context = active_api_budget_context()
    if context is None:
        if PROVIDER_EXECUTION_POLICY_REQUIRED:
            raise RuntimeError(PROVIDER_EXECUTION_POLICY_REQUIRED_MESSAGE)
        raise RuntimeError(
            f"{PROVIDER_EXECUTION_POLICY_GATE_MESSAGE}: active API budget context is required"
        )
    result = validate_provider_execution_policy(
        context.provider_execution_policy,
        provider=provider,
        model=model,
        operation=operation or "",
        approved_scope=context.provider_quota_current_scope,
    )
    if not result["valid"]:
        details = "; ".join(result["errors"])
        raise RuntimeError(f"{PROVIDER_EXECUTION_POLICY_GATE_MESSAGE}: {details}")


def active_provider_transport_send() -> ProviderTransportSend | None:
    return _PROVIDER_TRANSPORT_SEND_ALLOWED.get()


def require_provider_transport_send_allowed(url: str) -> None:
    if _is_local_or_non_http_transport_url(url):
        return
    if active_provider_transport_send() is None:
        raise RuntimeError(
            "provider_transport_send_guard_required: provider HTTP sends must run inside "
            "budgeted_api_call after the provider policy and budget gate passes"
        )


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
    transport_token = _PROVIDER_TRANSPORT_SEND_ALLOWED.set(
        ProviderTransportSend(
            provider=_clean_id(provider),
            model=_clean_model(model),
            operation=_clean_id(operation),
            provider_role=_clean_id(provider_role),
        )
    )
    try:
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
    finally:
        _PROVIDER_TRANSPORT_SEND_ALLOWED.reset(transport_token)


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


def provider_execution_policy_as_dict(policy: ProviderExecutionPolicy) -> dict[str, Any]:
    return asdict(policy)


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


def validate_provider_execution_policy(
    policy: ProviderExecutionPolicy | dict[str, Any] | None,
    *,
    provider: str,
    model: str | None,
    operation: str,
    provider_role: str | None = None,
    units: dict[str, int | float] | None = None,
    estimated_cost_usd: float | None = None,
    approved_scope: str | None = None,
    current_usage: dict[str, Any] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    errors: list[str] = []
    try:
        resolved = _coerce_provider_execution_policy(policy)
    except (TypeError, ValueError) as exc:
        resolved = None
        errors.append(str(exc))
    normalized_units = _normalize_units(units or {"calls": 1})
    if resolved is None:
        errors.append("provider execution policy is required")
        return _provider_execution_policy_validation_payload(
            policy=None,
            errors=errors,
            units=normalized_units,
            estimated_cost_usd=estimated_cost_usd,
            current_usage=current_usage,
        )
    provider_id = _clean_id(provider)
    model_id = _clean_model(model or "")
    operation_id = _clean_id(operation)
    provider_role_id = _clean_id(provider_role or "")
    policy_provider = _clean_id(resolved.provider)
    policy_model = _clean_model(resolved.model)
    policy_operation = _clean_id(resolved.operation)
    policy_role = _clean_id(resolved.provider_role or "*")
    if not resolved.allowed:
        errors.append("provider execution policy allowed=false")
    if policy_provider not in {provider_id, "*"}:
        errors.append(f"policy provider mismatch: {policy_provider} does not cover {provider_id}")
    if model_id and policy_model not in {model_id, "*"}:
        errors.append(f"policy model mismatch: {policy_model} does not cover {model_id}")
    if policy_operation not in {operation_id, "*"}:
        errors.append(
            f"policy operation mismatch: {policy_operation} does not cover {operation_id}"
        )
    if provider_role_id and policy_role not in {provider_role_id, "*"}:
        errors.append(
            f"policy provider_role mismatch: {policy_role} does not cover {provider_role_id}"
        )
    if approved_scope and resolved.approved_scope not in {None, "*", approved_scope}:
        errors.append(
            f"policy scope mismatch: {resolved.approved_scope} does not cover {approved_scope}"
        )
    if _requires_saved_policy_governance_fields(resolved, provider=provider_id):
        if not _optional_str(resolved.storage_rights):
            errors.append("policy storage_rights is required for saved provider execution")
        if not _optional_str(resolved.rollback_scope):
            errors.append("policy rollback_scope is required for saved provider execution")
    current = now or datetime.now(tz=UTC)
    if resolved.valid_from:
        valid_from = _validate_policy_timestamp("valid_from", resolved.valid_from, errors)
        if valid_from is not None and valid_from > current:
            errors.append("policy valid_from is in the future")
    if resolved.valid_until:
        valid_until = _validate_policy_timestamp("valid_until", resolved.valid_until, errors)
        if valid_until is not None and valid_until < current:
            errors.append("policy valid_until is in the past")
    usage = current_usage or _empty_usage()
    _validate_policy_limit(
        errors,
        label="calls",
        planned=float(normalized_units.get("calls", 1) or 1),
        current=float(usage.get("calls", 0) or 0),
        limit=resolved.max_calls,
    )
    _validate_policy_limit(
        errors,
        label="estimated_cost_usd",
        planned=float(estimated_cost_usd or 0.0),
        current=float(usage.get("estimated_cost_usd", 0.0) or 0.0),
        limit=resolved.max_cost_usd,
    )
    for label, field, limit in (
        ("input_tokens", "input_tokens", resolved.max_input_tokens),
        ("output_tokens", "output_tokens", resolved.max_output_tokens),
        ("media_bytes", "media_bytes", resolved.max_media_bytes),
        ("documents", "documents", resolved.max_documents),
    ):
        _validate_policy_limit(
            errors,
            label=label,
            planned=float(normalized_units.get(field, 0) or 0),
            current=float(usage.get(field, 0) or 0),
            limit=limit,
        )
    return _provider_execution_policy_validation_payload(
        policy=resolved,
        errors=errors,
        units=normalized_units,
        estimated_cost_usd=estimated_cost_usd,
        current_usage=usage,
    )


def require_provider_quota_approval(
    *,
    provider: str,
    model: str | None,
    operation: str,
    provider_role: str | None = None,
    units: dict[str, int | float] | None = None,
    estimated_cost_usd: float | None = None,
) -> None:
    if _is_exempt_provider(provider):
        return
    context = active_api_budget_context()
    if context is None:
        require_provider_execution_allowed(provider=provider, model=model, operation=operation)
        return
    approval = context.provider_quota_approval
    approved_scope = context.provider_quota_current_scope
    if approval is not None:
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
    policy_result = validate_provider_execution_policy(
        context.provider_execution_policy,
        provider=provider,
        model=model,
        operation=operation,
        provider_role=provider_role,
        units=units,
        estimated_cost_usd=estimated_cost_usd,
        approved_scope=approved_scope,
    )
    if not policy_result["valid"]:
        details = "; ".join(policy_result["errors"])
        raise RuntimeError(f"{PROVIDER_EXECUTION_POLICY_GATE_MESSAGE}: {details}")


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
    provider_policy_required: bool = PROVIDER_EXECUTION_POLICY_REQUIRED,
    provider_authorization_id: str | None = None,
    provider_execution_policy_id: str | None = None,
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
        unknown_price_action = str(policy["unknown_price_action"] or "block")
        kill_switch_enabled = bool(policy["kill_switch_enabled"])
        cost_result = _estimated_cost(
            conn,
            provider=provider_id,
            model=model_id,
            operation=operation_id,
            units=normalized_units,
            allow_unpriced=allow_unpriced_api,
            unknown_price_action=unknown_price_action,
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
        loaded_execution_policy = (
            _load_provider_execution_policy_from_conn(
                conn,
                authorization_id=provider_authorization_id,
                policy_id=provider_execution_policy_id,
            )
            if provider_authorization_id or provider_execution_policy_id
            else None
        )
        loaded_authorization = (
            _load_provider_authorization_from_conn(
                conn,
                loaded_execution_policy.authorization_id
                if loaded_execution_policy is not None
                else provider_authorization_id,
            )
            if provider_authorization_id or loaded_execution_policy is not None
            else None
        )
        try:
            resolved_approval = _coerce_provider_quota_approval(approval)
        except (TypeError, ValueError):
            resolved_approval = None
        if resolved_approval is None:
            resolved_approval = (
                loaded_authorization
                or _provider_quota_approval_from_execution_policy(loaded_execution_policy)
            )
        execution_policy = loaded_execution_policy or _provider_execution_policy_from_approval(
            resolved_approval
        )
        authorization_usage = (
            _provider_authorization_usage(conn, execution_policy)
            if execution_policy is not None
            else _empty_usage()
        )
    approval_result = validate_provider_quota_approval(
        resolved_approval if resolved_approval is not None else approval,
        provider=provider_id,
        model=model_id,
        operation=operation_id,
        units=normalized_units,
        estimated_cost_usd=float(cost_result["estimated_cost_usd"]),
        approved_scope=approved_scope,
    )
    execution_result = validate_provider_execution_policy(
        execution_policy,
        provider=provider_id,
        model=model_id,
        operation=operation_id,
        provider_role=provider_role,
        units=normalized_units,
        estimated_cost_usd=float(cost_result["estimated_cost_usd"]),
        approved_scope=approved_scope,
        current_usage=authorization_usage,
    )
    if cost_result.get("unknown_price"):
        budget_status = "needs_price_evidence"
        budget_block_reason = str(cost_result["unknown_price"])
    elif budget_block_reason:
        budget_status = "blocked"
    else:
        budget_status = "passed"
    provider_call_allowed = (
        approval_result["valid"] and execution_result["valid"] and budget_status == "passed"
    )
    provider_policy_status = _provider_policy_status(
        provider_policy_required=provider_policy_required,
        provider_call_allowed=provider_call_allowed,
    )
    price_known = cost_result["metadata"].get("price_status") == "priced"
    scope_match = _provider_preflight_scope_match(
        approval=resolved_approval,
        execution_policy=execution_policy,
        current_scope=approved_scope,
    )
    if _is_exempt_provider(provider_id):
        status = "local_exempt"
    elif not approval_result["valid"]:
        status = "approval_required"
    elif not execution_result["valid"]:
        status = "execution_policy_required"
    elif budget_status != "passed":
        status = budget_status
    else:
        status = "approved_smallest_limit"
    report = {
        "schema_version": 1,
        "preflight_kind": "provider_quota_approval",
        "dry_run": True,
        "status": status,
        "provider_call_allowed": provider_call_allowed,
        "provider_requests_sent": 0,
        "authorization_loaded": loaded_authorization is not None,
        "execution_policy_loaded": loaded_execution_policy is not None,
        "price_known": price_known,
        "unknown_price_action": unknown_price_action,
        "scope_match": scope_match,
        "kill_switch": kill_switch_enabled,
        "provider_policy_required": provider_policy_required,
        "db_path": str(path),
        "policy_id": policy_id,
        "run_id": run_id,
        "provider": provider_id,
        "model": model_id,
        "operation": operation_id,
        "provider_role": provider_role,
        "approved_scope": approved_scope,
        "units": normalized_units,
        "estimated_calls": int(float(normalized_units.get("calls", 0) or 0)),
        "estimated_documents": int(float(normalized_units.get("documents", 0) or 0)),
        "estimated_cost_usd": float(cost_result["estimated_cost_usd"]),
        "price_status": cost_result["metadata"].get("price_status"),
        "price_metadata": cost_result["metadata"],
        "provider_policy_status": provider_policy_status,
        "budget_guard": {
            "status": budget_status,
            "block_reason": budget_block_reason,
        },
        "approval_contract": approval_result,
        "execution_policy_contract": execution_result,
    }
    _record_provider_preflight(path, report)
    return report


def api_budget_event_snapshot(
    db_path: str | Path,
    *,
    run_id: str | None = None,
) -> dict[str, Any]:
    path = Path(db_path)
    if not path.exists():
        return _api_budget_event_snapshot_payload(path, run_id=run_id, rows=[])
    with sqlite3.connect(path, timeout=60) as conn:
        conn.row_factory = sqlite3.Row
        ensure_api_budget_schema(conn)
        clauses: list[str] = []
        params: list[Any] = []
        if run_id:
            clauses.append("run_id = ?")
            params.append(run_id)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = conn.execute(
            f"""
            SELECT event_id, run_id, provider, model, provider_role, operation,
                   status, metadata_json, started_at, finished_at
            FROM memory_api_usage_events
            {where}
            ORDER BY started_at, event_id
            """,
            params,
        ).fetchall()
    return _api_budget_event_snapshot_payload(path, run_id=run_id, rows=rows)


def api_budget_event_delta(
    before: dict[str, Any],
    after: dict[str, Any],
) -> dict[str, Any]:
    before_counts = before.get("counts") if isinstance(before, dict) else {}
    after_counts = after.get("counts") if isinstance(after, dict) else {}
    if not isinstance(before_counts, dict):
        before_counts = {}
    if not isinstance(after_counts, dict):
        after_counts = {}
    keys = sorted(set(before_counts) | set(after_counts))
    counts = {
        key: int(after_counts.get(key) or 0) - int(before_counts.get(key) or 0)
        for key in keys
    }
    return {
        "artifact_kind": "research_x_api_budget_event_delta",
        "schema_version": 1,
        "count_basis": (
            "memory_api_usage_events delta; provider_transport_sends_observed counts "
            "non-exempt provider events that reached ok/error status after budget gate"
        ),
        "run_id": after.get("run_id") if isinstance(after, dict) else None,
        "before_total_events": int(before_counts.get("total_events") or 0),
        "after_total_events": int(after_counts.get("total_events") or 0),
        "counts": counts,
        "provider_requests_observed": counts.get("provider_requests_observed", 0),
        "provider_requests_blocked_by_freeze": counts.get(
            "provider_requests_blocked_by_freeze",
            0,
        ),
        "provider_transport_sends_observed": counts.get(
            "provider_transport_sends_observed",
            0,
        ),
        "not_evidence": True,
    }


def format_provider_quota_preflight(report: dict[str, Any]) -> str:
    approval = report["approval_contract"]
    budget = report["budget_guard"]
    lines = [
        f"status: {report['status']}",
        f"dry_run: {report['dry_run']}",
        f"provider_call_allowed: {report['provider_call_allowed']}",
        f"provider_requests_sent: {report['provider_requests_sent']}",
        f"authorization_loaded: {report.get('authorization_loaded', False)}",
        f"execution_policy_loaded: {report.get('execution_policy_loaded', False)}",
        f"price_known: {report.get('price_known', False)}",
        f"unknown_price_action: {report.get('unknown_price_action', 'block')}",
        f"scope_match: {report.get('scope_match', False)}",
        f"kill_switch: {report.get('kill_switch', False)}",
        (
            "target: "
            f"{report['provider']}/{report['model']} {report['operation']} "
            f"scope={report.get('approved_scope') or ''}"
        ),
        f"units: {json.dumps(report['units'], ensure_ascii=False, sort_keys=True)}",
        f"estimated_calls: {report.get('estimated_calls', 0)}",
        f"estimated_documents: {report.get('estimated_documents', 0)}",
        f"estimated_cost_usd: {report['estimated_cost_usd']:.8f}",
        f"budget_guard: {budget['status']} {budget.get('block_reason') or ''}".rstrip(),
        f"approval_contract: {'valid' if approval['valid'] else 'invalid'}",
        (
            "execution_policy_contract: "
            f"{'valid' if report['execution_policy_contract']['valid'] else 'invalid'}"
        ),
    ]
    for error in approval["errors"]:
        lines.append(f"  approval_error: {error}")
    for error in report["execution_policy_contract"]["errors"]:
        lines.append(f"  execution_policy_error: {error}")
    lines.append(f"provider_policy_status: {report['provider_policy_status']}")
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

        CREATE TABLE IF NOT EXISTS memory_provider_authorizations (
            authorization_id TEXT PRIMARY KEY,
            provider TEXT NOT NULL,
            model TEXT NOT NULL,
            operation TEXT NOT NULL,
            provider_role TEXT,
            allowed INTEGER NOT NULL,
            max_calls INTEGER,
            max_cost_usd REAL,
            max_input_tokens INTEGER,
            max_output_tokens INTEGER,
            max_media_bytes INTEGER,
            max_documents INTEGER,
            valid_from TEXT,
            valid_until TEXT,
            approved_by TEXT,
            approval_source TEXT,
            approved_scope TEXT,
            storage_rights TEXT,
            prompt_injection_required INTEGER,
            rollback_scope TEXT,
            metadata_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS memory_provider_execution_policies (
            policy_id TEXT PRIMARY KEY,
            authorization_id TEXT NOT NULL,
            provider TEXT NOT NULL,
            model TEXT NOT NULL,
            operation TEXT NOT NULL,
            provider_role TEXT,
            allowed INTEGER NOT NULL,
            max_calls INTEGER,
            max_cost_usd REAL,
            max_input_tokens INTEGER,
            max_output_tokens INTEGER,
            max_media_bytes INTEGER,
            max_documents INTEGER,
            valid_from TEXT,
            valid_until TEXT,
            approved_by TEXT,
            approval_source TEXT,
            approved_scope TEXT,
            storage_rights TEXT,
            prompt_injection_required INTEGER,
            rollback_scope TEXT,
            metadata_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS memory_provider_preflights (
            preflight_id TEXT PRIMARY KEY,
            run_id TEXT,
            policy_id TEXT NOT NULL,
            authorization_id TEXT,
            execution_policy_id TEXT,
            provider TEXT NOT NULL,
            model TEXT NOT NULL,
            operation TEXT NOT NULL,
            provider_role TEXT NOT NULL,
            status TEXT NOT NULL,
            provider_call_allowed INTEGER NOT NULL,
            provider_requests_sent INTEGER NOT NULL,
            provider_policy_required INTEGER NOT NULL,
            provider_policy_status TEXT NOT NULL,
            units_json TEXT NOT NULL,
            estimated_cost_usd REAL NOT NULL,
            price_status TEXT,
            budget_status TEXT NOT NULL,
            approval_valid INTEGER NOT NULL,
            execution_policy_valid INTEGER NOT NULL,
            report_json TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS memory_provider_transport_events (
            transport_event_id TEXT PRIMARY KEY,
            api_usage_event_id TEXT,
            run_id TEXT,
            job_id TEXT,
            authorization_id TEXT,
            execution_policy_id TEXT,
            provider TEXT NOT NULL,
            model TEXT NOT NULL,
            operation TEXT NOT NULL,
            provider_role TEXT NOT NULL,
            status TEXT NOT NULL,
            event_kind TEXT NOT NULL,
            started_at TEXT NOT NULL,
            finished_at TEXT,
            error TEXT,
            metadata_json TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_memory_api_usage_run
            ON memory_api_usage_events(run_id, started_at);
        CREATE INDEX IF NOT EXISTS idx_memory_api_usage_provider
            ON memory_api_usage_events(provider, model, operation, started_at);
        CREATE INDEX IF NOT EXISTS idx_memory_api_usage_status
            ON memory_api_usage_events(status, started_at);
        CREATE INDEX IF NOT EXISTS idx_memory_provider_authorizations_scope
            ON memory_provider_authorizations(provider, model, operation, provider_role);
        CREATE INDEX IF NOT EXISTS idx_memory_provider_execution_scope
            ON memory_provider_execution_policies(provider, model, operation, provider_role);
        CREATE INDEX IF NOT EXISTS idx_memory_provider_preflights_run
            ON memory_provider_preflights(run_id, created_at);
        CREATE INDEX IF NOT EXISTS idx_memory_provider_transport_usage
            ON memory_provider_transport_events(api_usage_event_id);
        CREATE INDEX IF NOT EXISTS idx_memory_provider_transport_scope
            ON memory_provider_transport_events(provider, model, operation, started_at);
        """
    )
    ensure_default_api_budget_policy(conn)
    _ensure_provider_preflight_policy_columns(conn)


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


def _ensure_provider_preflight_policy_columns(conn: sqlite3.Connection) -> None:
    columns = _table_columns(conn, "memory_provider_preflights")
    if not columns:
        return
    if "provider_policy_required" not in columns:
        conn.execute(
            """
            ALTER TABLE memory_provider_preflights
            ADD COLUMN provider_policy_required INTEGER NOT NULL DEFAULT 1
            """
        )
    if "provider_policy_status" not in columns:
        conn.execute(
            """
            ALTER TABLE memory_provider_preflights
            ADD COLUMN provider_policy_status TEXT NOT NULL
            DEFAULT 'provider_execution_policy_required'
            """
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
            execution_policy = context.provider_execution_policy
            if execution_policy is not None:
                _upsert_provider_execution_policy(conn, execution_policy)
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
            execution_result = validate_provider_execution_policy(
                execution_policy,
                provider=provider_id,
                model=model_id,
                operation=operation_id,
                provider_role=provider_role,
                units=units,
                estimated_cost_usd=float(cost_result["estimated_cost_usd"]),
                approved_scope=context.provider_quota_current_scope,
                current_usage=(
                    _provider_authorization_usage(conn, execution_policy)
                    if execution_policy is not None
                    else _empty_usage()
                ),
            )
            metadata_payload = {
                **metadata_payload,
                **_execution_policy_event_metadata(
                    execution_policy=execution_policy,
                    execution_result=execution_result,
                    provider_policy_required=context.provider_policy_required,
                ),
            }
            if not execution_result["valid"] and block_reason is None:
                block_reason = (
                    f"{PROVIDER_EXECUTION_POLICY_GATE_MESSAGE}: "
                    + "; ".join(execution_result["errors"])
                )
            if int(policy["enabled"]) and block_reason is None:
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
                transport_event_id = _event_id("provider-transport", event_id, "blocked", now)
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
                _insert_provider_transport_event(
                    conn,
                    transport_event_id=transport_event_id,
                    event_id=event_id,
                    context=context,
                    execution_policy=execution_policy,
                    provider=provider_id,
                    model=model_id,
                    provider_role=provider_role,
                    operation=operation_id,
                    status="blocked",
                    event_kind="budgeted_transport",
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
            transport_event_id = _event_id("provider-transport", event_id, "reserved", now)
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
            _insert_provider_transport_event(
                conn,
                transport_event_id=transport_event_id,
                event_id=event_id,
                context=context,
                execution_policy=execution_policy,
                provider=provider_id,
                model=model_id,
                provider_role=provider_role,
                operation=operation_id,
                status="reserved",
                event_kind="budgeted_transport",
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
        transport_event_id=transport_event_id,
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
        conn.execute(
            """
            UPDATE memory_provider_transport_events
            SET status = ?, finished_at = ?, error = ?
            WHERE api_usage_event_id = ?
            """,
            (status, _utc_now(), error, event_id),
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


def authorize_provider_execution(
    db_path: str | Path,
    *,
    authorization_id: str,
    provider: str,
    model: str,
    operation: str,
    max_calls: int,
    max_cost_usd: float,
    provider_role: str | None = None,
    policy_id: str | None = None,
    allowed: bool = True,
    approved_scope: str | None = None,
    approved_by: str | None = None,
    approval_source: str | None = None,
    approved_at: str | None = None,
    valid_until: str | None = None,
    max_input_tokens: int | None = None,
    max_output_tokens: int | None = None,
    max_media_bytes: int | None = None,
    max_documents: int | None = None,
    storage_rights: str | None = None,
    prompt_injection_required: bool | None = None,
    rollback_scope: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if max_calls <= 0:
        raise ValueError("max_calls must be positive")
    if max_cost_usd < 0:
        raise ValueError("max_cost_usd must be non-negative")
    approval_time = approved_at or _utc_now()
    approval = ProviderQuotaApproval(
        provider_quota_approval_id=authorization_id,
        provider=provider,
        model=model,
        operation=operation,
        max_calls=max_calls,
        max_cost_usd=max_cost_usd,
        price_source=approval_source or "manual",
        approved_scope=approved_scope or "*",
        approved_at=approval_time,
        provider_role=provider_role,
        approved_by=approved_by,
        expires_at=valid_until,
        metadata=metadata,
    )
    execution_policy = ProviderExecutionPolicy(
        policy_id=policy_id or f"approval:{authorization_id}",
        authorization_id=authorization_id,
        provider=provider,
        model=model,
        operation=operation,
        provider_role=provider_role,
        allowed=allowed,
        max_calls=max_calls,
        max_cost_usd=max_cost_usd,
        max_input_tokens=max_input_tokens,
        max_output_tokens=max_output_tokens,
        max_media_bytes=max_media_bytes,
        max_documents=max_documents,
        valid_from=approval_time,
        valid_until=valid_until,
        approved_by=approved_by,
        approval_source=approval_source or "manual",
        approved_scope=approved_scope or "*",
        storage_rights=storage_rights,
        prompt_injection_required=prompt_injection_required,
        rollback_scope=rollback_scope,
        metadata=metadata,
        source_kind="saved_policy",
    )
    approval_result = validate_provider_quota_approval(
        approval,
        provider=provider,
        model=model,
        operation=operation,
        units={"calls": 1},
        approved_scope=approved_scope,
    )
    policy_result = validate_provider_execution_policy(
        execution_policy,
        provider=provider,
        model=model,
        operation=operation,
        provider_role=provider_role,
        units={"calls": 1},
        approved_scope=approved_scope,
    )
    if not approval_result["valid"]:
        raise ValueError("; ".join(approval_result["errors"]))
    if not policy_result["valid"]:
        raise ValueError("; ".join(policy_result["errors"]))
    with sqlite3.connect(db_path, timeout=60) as conn:
        conn.row_factory = sqlite3.Row
        ensure_api_budget_schema(conn)
        _upsert_provider_execution_policy(conn, execution_policy)
    return {
        "schema_version": 1,
        "status": "authorized" if allowed else "recorded_disabled",
        "authorization": provider_quota_approval_as_dict(approval),
        "execution_policy": provider_execution_policy_as_dict(execution_policy),
    }


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
        provider_rows = _provider_usage(conn, run_id=run_id)
        provider_rows_today = _provider_usage(conn, run_id=run_id, since=_day_start())
        events = _recent_events(conn, run_id=run_id, limit=recent_limit)
        active_exposure = _active_exposure(conn, run_id=run_id)
        prices = _price_rows(conn)
        authorizations = _provider_authorization_rows(conn)
        execution_policies = _provider_execution_policy_rows(conn)
        preflights = _provider_preflight_rows(conn, run_id=run_id, limit=recent_limit)
        transport_events = _provider_transport_event_rows(conn, run_id=run_id, limit=recent_limit)
        provider_control_summary = _provider_control_summary(conn)
        price_catalog_coverage = _price_catalog_coverage(conn, run_id=run_id)
    return {
        "db_path": str(path),
        "generated_at": _utc_now(),
        "policy": _row_dict(policy),
        "run_id": run_id,
        "usage": usage,
        "provider_usage": provider_rows,
        "provider_usage_today": provider_rows_today,
        "active_exposure": active_exposure,
        "recent_events": events,
        "price_catalog": prices,
        "price_catalog_coverage": price_catalog_coverage,
        "provider_control_summary": provider_control_summary,
        "provider_authorizations": authorizations,
        "provider_execution_policies": execution_policies,
        "recent_provider_preflights": preflights,
        "recent_provider_transport_events": transport_events,
        "warnings": _budget_warnings(_row_dict(policy), usage),
    }


def load_provider_execution_policy(
    db_path: str | Path,
    *,
    authorization_id: str | None = None,
    policy_id: str | None = None,
) -> ProviderExecutionPolicy:
    if not authorization_id and not policy_id:
        raise ValueError("authorization_id or policy_id is required")
    with sqlite3.connect(db_path, timeout=60) as conn:
        conn.row_factory = sqlite3.Row
        ensure_api_budget_schema(conn)
        return _load_provider_execution_policy_from_conn(
            conn,
            authorization_id=authorization_id,
            policy_id=policy_id,
        )


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
    lines.append("provider execution policies:")
    for row in status.get("provider_execution_policies", [])[:20]:
        lines.append(
            "  "
            f"{row['policy_id']} auth={row['authorization_id']} "
            f"{row['provider']}/{row['model']} {row['operation']} "
            f"allowed={bool(row['allowed'])} max_calls={row.get('max_calls')}"
        )
    lines.append("provider/model usage:")
    for row in status.get("provider_usage", status["provider_usage_today"])[:20]:
        lines.append(
            "  "
            f"{row['provider']}/{row['model']} {row['operation']} "
            f"calls={row['calls']} retries={row['retries']} "
            f"input_tokens={row['input_tokens']} output_tokens={row['output_tokens']} "
            f"media_bytes={row['media_bytes']} documents={row['documents']} "
            f"pages={row['pages']} cost=${row['estimated_cost_usd']:.6f} "
            f"statuses={json.dumps(row.get('status_counts', {}), sort_keys=True)}"
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
    policy_id: str = DEFAULT_API_BUDGET_POLICY_ID,
    run_id: str | None = None,
    recent_limit: int = 20,
    command_name: str = "api-watch",
) -> None:
    db_text = str(db_path)

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            if parsed.path == "/api/status":
                self._json(
                    api_budget_status(
                        db_text,
                        policy_id=policy_id,
                        run_id=run_id,
                        recent_limit=recent_limit,
                    )
                )
                return
            if parsed.path == "/":
                self._html(
                    _watch_page(
                        db_text,
                        policy_id=policy_id,
                        run_id=run_id,
                        recent_limit=recent_limit,
                    )
                )
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
    print(f"research_x {command_name}: {url}")
    try:
        if open_browser:
            webbrowser.open(url)
        server.serve_forever()
    except KeyboardInterrupt:
        print(f"research_x {command_name}: shutting down")
    finally:
        server.server_close()


def _watch_page(
    db_path: str,
    *,
    policy_id: str = DEFAULT_API_BUDGET_POLICY_ID,
    run_id: str | None = None,
    recent_limit: int = 20,
) -> str:
    escaped_db = html.escape(db_path)
    escaped_policy = html.escape(policy_id)
    escaped_run = html.escape(run_id or "all")
    escaped_limit = html.escape(str(recent_limit))
    page = """<!doctype html>
<html lang="ja">
<head>
  <meta charset="utf-8">
  <title>research_x API dashboard</title>
  <style>
    :root {
      color-scheme: light;
      --border: #d7dde5;
      --ink: #162033;
      --muted: #5f6b7a;
      --band: #f6f8fa;
      --good: #0f766e;
      --warn: #b45309;
      --bad: #b91c1c;
      --fill: #2563eb;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      color: var(--ink);
      background: #ffffff;
      font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }
    header {
      border-bottom: 1px solid var(--border);
      padding: 18px 24px;
    }
    main {
      display: grid;
      gap: 22px;
      padding: 20px 24px 32px;
      max-width: 1480px;
    }
    h1 { margin: 0 0 6px; font-size: 24px; font-weight: 700; }
    h2 { margin: 0 0 10px; font-size: 16px; font-weight: 700; }
    p { margin: 0; color: var(--muted); }
    section {
      border-top: 1px solid var(--border);
      padding-top: 14px;
    }
    .summary {
      display: grid;
      gap: 10px;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
    }
    .metric {
      border: 1px solid var(--border);
      border-radius: 6px;
      min-width: 0;
      padding: 10px;
    }
    .metric strong { display: block; margin-bottom: 6px; }
    .meta { color: var(--muted); font-size: 13px; overflow-wrap: anywhere; }
    .bar { background: #e8edf3; border-radius: 4px; height: 12px; overflow: hidden; }
    .fill { background: var(--fill); height: 100%; width: 0%; }
    .warn { background: var(--warn); }
    .bad { background: var(--bad); }
    .table-wrap { border: 1px solid var(--border); border-radius: 6px; overflow-x: auto; }
    .scroll-panel .table-wrap {
      height: 320px;
      overflow: auto;
    }
    table { border-collapse: collapse; min-width: 880px; width: 100%; }
    th, td {
      border-bottom: 1px solid var(--border);
      font-size: 13px;
      padding: 7px 8px;
      text-align: left;
      vertical-align: top;
    }
    th { background: var(--band); color: #344054; font-weight: 700; }
    .scroll-panel th {
      position: sticky;
      top: 0;
      z-index: 1;
    }
    tr:last-child td { border-bottom: 0; }
    code {
      background: var(--band);
      border: 1px solid var(--border);
      border-radius: 4px;
      padding: 1px 4px;
      white-space: nowrap;
    }
    .empty {
      border: 1px solid var(--border);
      border-radius: 6px;
      color: var(--muted);
      padding: 10px;
    }
    .status-ok { color: var(--good); font-weight: 700; }
    .status-error, .status-blocked { color: var(--bad); font-weight: 700; }
    .status-reserved { color: var(--warn); font-weight: 700; }
  </style>
</head>
<body>
  <header>
    <h1>research_x API dashboard</h1>
    <p>
      db: <code>__DB_PATH__</code>
      policy: <code>__POLICY_ID__</code>
      run: <code>__RUN_ID__</code>
      recent limit: <code>__RECENT_LIMIT__</code>
    </p>
  </header>
  <main>
    <section>
      <h2>Policy / Kill Switch / Warnings / Last Update</h2>
      <div id="policy" class="summary"></div>
    </section>
    <section>
      <h2>Run / Day / Month Budget Usage</h2>
      <div id="budget" class="summary"></div>
    </section>
    <section>
      <h2>Active API Exposure</h2>
      <div id="active-exposure" class="summary"></div>
      <div id="active-events" class="scroll-panel"></div>
    </section>
    <section>
      <h2>All API Usage</h2>
      <div id="usage"></div>
    </section>
    <section>
      <h2>Recent Usage Events</h2>
      <div id="events" class="scroll-panel"></div>
    </section>
    <section>
      <h2>Provider Preflights</h2>
      <div id="preflights" class="scroll-panel"></div>
    </section>
    <section>
      <h2>Provider Transport Events</h2>
      <div id="transport"></div>
    </section>
    <section>
      <h2>Saved Authorizations / Execution Policies / Price Catalog Coverage</h2>
      <div id="controls" class="summary"></div>
    </section>
  </main>
  <script>
    const POLL_INTERVAL_MS = 1000;
    const tableRenderKeys = {};
    const tableStates = {};
    const htmlRenderKeys = {};
    let pollTimer = null;
    let pollInFlight = false;

    function escapeHtml(value) {
      return String(value ?? "").replace(/[&<>"']/g, (ch) => ({
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
        "'": "&#39;"
      })[ch]);
    }
    function pct(value, max) {
      if (!max || max <= 0) return 0;
      return Math.max(0, Math.min(100, value / max * 100));
    }
    function money(value) {
      return "$" + Number(value || 0).toFixed(6);
    }
    function number(value) {
      return Number(value || 0).toLocaleString();
    }
    function duration(seconds) {
      const value = Math.max(0, Number(seconds || 0));
      const minutes = Math.floor(value / 60);
      const remainder = Math.floor(value % 60);
      return `${minutes}m ${remainder}s`;
    }
    function tokyoTime(value) {
      if (!value) return "";
      const date = new Date(value);
      if (Number.isNaN(date.getTime())) return String(value);
      return new Intl.DateTimeFormat("ja-JP", {
        timeZone: "Asia/Tokyo",
        year: "numeric",
        month: "2-digit",
        day: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
        hour12: false
      }).format(date).replaceAll("/", "-") + " JST";
    }
    function unitsText(units) {
      const u = units || {};
      return [
        `calls=${number(u.calls)}`,
        `retries=${number(u.retries)}`,
        `in=${number(u.input_tokens)}`,
        `out=${number(u.output_tokens)}`,
        `media=${number(u.media_bytes)}`,
        `docs=${number(u.documents)}`,
        `pages=${number(u.pages)}`
      ].join(" ");
    }
    function statusClass(status) {
      const value = String(status || "").toLowerCase();
      if (value === "ok") return "status-ok";
      if (value === "error" || value === "blocked") return "status-error";
      if (value === "reserved") return "status-reserved";
      return "";
    }
    function statusCounts(row) {
      const counts = row.status_counts || {};
      return Object.keys(counts).sort().map((key) => `${key}:${counts[key]}`).join(" ");
    }
    function renderWindow(name, usage, max) {
      const p = pct(usage.estimated_cost_usd || 0, max);
      const cls = p >= 100 ? "bad" : p >= 80 ? "warn" : "";
      return `<div class="metric"><strong>${escapeHtml(name)}</strong>` +
        `<div>${money(usage.estimated_cost_usd)} / ${max == null ? "none" : money(max)}</div>` +
        `<div class="meta">${escapeHtml(unitsText(usage))}</div>` +
        `<div class="bar"><div class="fill ${cls}" style="width:${p}%"></div></div>` +
        `</div>`;
    }
    function setHtmlIfChanged(targetId, html) {
      if (htmlRenderKeys[targetId] === html) {
        return;
      }
      htmlRenderKeys[targetId] = html;
      document.getElementById(targetId).innerHTML = html;
    }
    function renderTable(targetId, headers, rows, cells, keyForRow) {
      const target = document.getElementById(targetId);
      const renderKey = JSON.stringify(rows || []);
      if (tableRenderKeys[targetId] === renderKey) {
        return;
      }
      tableRenderKeys[targetId] = renderKey;
      const existingWrap = target.querySelector(".table-wrap");
      const scrollTop = existingWrap ? existingWrap.scrollTop : 0;
      const scrollLeft = existingWrap ? existingWrap.scrollLeft : 0;
      if (!rows || rows.length === 0) {
        target.innerHTML = `<div class="empty">No rows</div>`;
        return;
      }
      const head = headers.map((item) => `<th>${escapeHtml(item)}</th>`).join("");
      const headerKey = JSON.stringify(headers);
      let state = tableStates[targetId] || {};
      if (state.headerKey !== headerKey || !target.querySelector("tbody")) {
        target.innerHTML = `<div class="table-wrap"><table><thead><tr>${head}</tr></thead>` +
          `<tbody></tbody></table></div>`;
        state = {headerKey, rowHashes: {}, rowNodes: {}, orderKey: ""};
        tableStates[targetId] = state;
      }
      const nextWrap = target.querySelector(".table-wrap");
      if (nextWrap) {
        nextWrap.scrollTop = scrollTop;
        nextWrap.scrollLeft = scrollLeft;
      }
      const tbody = target.querySelector("tbody");
      if (!tbody) return;
      const nextKeys = [];
      const nextKeySet = new Set();
      const orderedNodes = [];
      rows.forEach((row, index) => {
        const rowKey = String(keyForRow(row, index));
        nextKeys.push(rowKey);
        nextKeySet.add(rowKey);
        let rowNode = state.rowNodes[rowKey];
        if (!rowNode) {
          rowNode = document.createElement("tr");
          rowNode.dataset.rowKey = rowKey;
          state.rowNodes[rowKey] = rowNode;
        }
        const cellHtml = cells(row).map((item) => `<td>${item}</td>`).join("");
        if (state.rowHashes[rowKey] !== cellHtml) {
          rowNode.innerHTML = cellHtml;
          state.rowHashes[rowKey] = cellHtml;
        }
        orderedNodes.push(rowNode);
      });
      Object.keys(state.rowNodes).forEach((rowKey) => {
        if (!nextKeySet.has(rowKey)) {
          const rowNode = state.rowNodes[rowKey];
          if (rowNode.parentNode) rowNode.parentNode.removeChild(rowNode);
          delete state.rowNodes[rowKey];
          delete state.rowHashes[rowKey];
        }
      });
      const orderKey = nextKeys.join("\u001f");
      if (state.orderKey !== orderKey) {
        const fragment = document.createDocumentFragment();
        orderedNodes.forEach((rowNode) => fragment.appendChild(rowNode));
        tbody.appendChild(fragment);
        state.orderKey = orderKey;
      }
    }
    function renderPolicy(payload) {
      const policy = payload.policy || {};
      const warnings = payload.warnings || [];
      setHtmlIfChanged("policy", [
        `<div class="metric"><strong>Policy</strong><div>${escapeHtml(policy.policy_id)}</div>` +
          `<div class="meta">enabled=${Boolean(policy.enabled)} ` +
          `unknown_price=${escapeHtml(policy.unknown_price_action)}</div></div>`,
        `<div class="metric"><strong>Kill Switch</strong>` +
          `<div>${Boolean(policy.kill_switch_enabled) ? "enabled" : "disabled"}</div></div>`,
        `<div class="metric"><strong>Warnings</strong>` +
          `<div>${escapeHtml(warnings.join("; ") || "none")}</div></div>`,
        `<div class="metric"><strong>Last Update</strong>` +
          `<div>${escapeHtml(tokyoTime(payload.generated_at))}</div>` +
          `<div class="meta">Asia/Tokyo (UTC+9)</div></div>`
      ].join(""));
    }
    function renderControls(payload) {
      const summary = payload.provider_control_summary || {};
      const coverage = payload.price_catalog_coverage || {};
      const missing = (coverage.missing_price_api_keys || [])
        .map((item) => `${item.provider}/${item.model} ${item.operation}`)
        .slice(0, 8)
        .join("; ");
      setHtmlIfChanged("controls", [
        `<div class="metric"><strong>Saved Authorizations</strong>` +
          `<div>${number(summary.authorizations)}</div>` +
          `<div class="meta">allowed=${number(summary.allowed_authorizations)} ` +
          `disabled=${number(summary.disabled_authorizations)}</div></div>`,
        `<div class="metric"><strong>Execution Policies</strong>` +
          `<div>${number(summary.execution_policies)}</div>` +
          `<div class="meta">allowed=${number(summary.allowed_execution_policies)} ` +
          `disabled=${number(summary.disabled_execution_policies)}</div></div>`,
        `<div class="metric"><strong>Price Catalog Coverage</strong>` +
          `<div>${number(coverage.priced_observed_api_count)} / ` +
          `${number(coverage.observed_api_count)}</div>` +
          `<div class="meta">price rows=${number(coverage.price_rows)} ` +
          `missing=${escapeHtml(missing || "none")}</div></div>`
      ].join(""));
    }
    function renderActiveExposure(payload) {
      const active = payload.active_exposure || {};
      const policy = payload.policy || {};
      const usage = payload.usage || {};
      const maxRun = policy.max_run_usd;
      const runUsed = Number((usage.run || {}).estimated_cost_usd || 0);
      const remaining = maxRun == null ? null : Math.max(0, Number(maxRun) - runUsed);
      setHtmlIfChanged("active-exposure", [
        `<div class="metric"><strong>Active Requests</strong>` +
          `<div>${number(active.active_count)}</div>` +
          `<div class="meta">unfinished reserved API events</div></div>`,
        `<div class="metric"><strong>Reserved Exposure</strong>` +
          `<div>${money(active.estimated_cost_usd)}</div>` +
          `<div class="meta">${escapeHtml(unitsText(active.units))}</div></div>`,
        `<div class="metric"><strong>Oldest Active</strong>` +
          `<div>${escapeHtml(duration(active.oldest_age_seconds))}</div>` +
          `<div class="meta">age since reservation</div></div>`,
        `<div class="metric"><strong>Run Remaining</strong>` +
          `<div>${remaining == null ? "none" : money(remaining)}</div>` +
          `<div class="meta">after current reservations</div></div>`
      ].join(""));
      renderTable(
        "active-events",
        ["started", "age", "provider", "operation", "units", "reserved", "event"],
        active.events || [],
        (row) => [
          escapeHtml(tokyoTime(row.started_at)),
          escapeHtml(duration(row.age_seconds)),
          escapeHtml(`${row.provider}/${row.model}`),
          escapeHtml(row.operation),
          escapeHtml(unitsText(row.units)),
          escapeHtml(money(row.estimated_cost_usd)),
          escapeHtml(row.event_id || "")
        ],
        (row, index) => row.event_id || `${row.started_at}\u001f${index}`
      );
    }
    function schedulePoll() {
      clearTimeout(pollTimer);
      if (!document.hidden) {
        pollTimer = setTimeout(poll, POLL_INTERVAL_MS);
      }
    }
    async function poll() {
      if (pollInFlight || document.hidden) {
        schedulePoll();
        return;
      }
      pollInFlight = true;
      try {
        const response = await fetch("/api/status", {cache: "no-store"});
        const payload = await response.json();
        const policy = payload.policy || {};
        const usage = payload.usage || {};
        renderPolicy(payload);
        setHtmlIfChanged("budget", [
          renderWindow("run", usage.run || {}, policy.max_run_usd),
          renderWindow("day", usage.day || {}, policy.max_day_usd),
          renderWindow("month", usage.month || {}, policy.max_month_usd)
        ].join(""));
        renderActiveExposure(payload);
        renderTable(
          "usage",
          ["provider", "model", "operation", "units", "estimated", "events"],
          payload.provider_usage || [],
          (row) => [
            escapeHtml(row.provider),
            escapeHtml(row.model),
            escapeHtml(row.operation),
            escapeHtml(unitsText(row)),
            escapeHtml(money(row.estimated_cost_usd)),
            escapeHtml(statusCounts(row))
          ],
          (row) => `${row.provider}\u001f${row.model}\u001f${row.operation}`
        );
        renderTable(
          "events",
          ["started", "status", "provider", "operation", "units", "estimated", "error"],
          payload.recent_events || [],
          (row) => [
            escapeHtml(tokyoTime(row.started_at)),
            `<span class="${statusClass(row.status)}">${escapeHtml(row.status)}</span>`,
            escapeHtml(`${row.provider}/${row.model}`),
            escapeHtml(row.operation),
            escapeHtml(unitsText(row.units)),
            escapeHtml(money(row.estimated_cost_usd)),
            escapeHtml(row.error || "")
          ],
          (row, index) => row.event_id || `${row.started_at}\u001f${index}`
        );
        renderTable(
          "preflights",
          ["created", "status", "policy status", "provider", "operation", "units", "allowed"],
          payload.recent_provider_preflights || [],
          (row) => [
            escapeHtml(tokyoTime(row.created_at)),
            `<span class="${statusClass(row.status)}">${escapeHtml(row.status)}</span>`,
            escapeHtml(row.provider_policy_status),
            escapeHtml(`${row.provider}/${row.model}`),
            escapeHtml(row.operation),
            escapeHtml(unitsText(row.units)),
            escapeHtml(Boolean(row.provider_call_allowed))
          ],
          (row, index) => row.preflight_id || `${row.created_at}\u001f${index}`
        );
        renderTable(
          "transport",
          ["started", "status", "event kind", "provider", "operation", "error"],
          payload.recent_provider_transport_events || [],
          (row) => [
            escapeHtml(tokyoTime(row.started_at)),
            `<span class="${statusClass(row.status)}">${escapeHtml(row.status)}</span>`,
            escapeHtml(row.event_kind),
            escapeHtml(`${row.provider}/${row.model}`),
            escapeHtml(row.operation),
            escapeHtml(row.error || "")
          ],
          (row, index) => row.transport_event_id || `${row.started_at}\u001f${index}`
        );
        renderControls(payload);
      } catch (error) {
        console.error("api dashboard poll failed", error);
      } finally {
        pollInFlight = false;
        schedulePoll();
      }
    }
    document.addEventListener("visibilitychange", () => {
      if (document.hidden) {
        clearTimeout(pollTimer);
      } else {
        poll();
      }
    });
    poll();
  </script>
</body>
</html>"""
    return (
        page.replace("__DB_PATH__", escaped_db)
        .replace("__POLICY_ID__", escaped_policy)
        .replace("__RUN_ID__", escaped_run)
        .replace("__RECENT_LIMIT__", escaped_limit)
    )


def _record_provider_preflight(db_path: Path, report: dict[str, Any]) -> None:
    now = _utc_now()
    preflight_id = _event_id(
        "provider-preflight",
        report.get("run_id") or "",
        report["provider"],
        report["model"],
        report["operation"],
        now,
    )
    report["preflight_id"] = preflight_id
    approval = report["approval_contract"].get("approval") or {}
    execution_policy = report["execution_policy_contract"].get("policy") or {}
    authorization_id = (
        execution_policy.get("authorization_id") or approval.get("provider_quota_approval_id")
    )
    with sqlite3.connect(db_path, timeout=60) as conn:
        ensure_api_budget_schema(conn)
        columns = [
            "preflight_id",
            "run_id",
            "policy_id",
            "authorization_id",
            "execution_policy_id",
            "provider",
            "model",
            "operation",
            "provider_role",
            "status",
            "provider_call_allowed",
            "provider_requests_sent",
            "provider_policy_required",
            "provider_policy_status",
            "units_json",
            "estimated_cost_usd",
            "price_status",
            "budget_status",
            "approval_valid",
            "execution_policy_valid",
            "report_json",
            "created_at",
        ]
        values: list[Any] = [
            preflight_id,
            report.get("run_id"),
            report["policy_id"],
            authorization_id,
            execution_policy.get("policy_id"),
            report["provider"],
            report["model"],
            report["operation"],
            report["provider_role"],
            report["status"],
            int(bool(report["provider_call_allowed"])),
            int(report["provider_requests_sent"]),
            int(bool(report["provider_policy_required"])),
            report["provider_policy_status"],
            json.dumps(report["units"], ensure_ascii=False, sort_keys=True),
            float(report["estimated_cost_usd"]),
            report.get("price_status"),
            report["budget_guard"]["status"],
            int(bool(report["approval_contract"]["valid"])),
            int(bool(report["execution_policy_contract"]["valid"])),
            json.dumps(report, ensure_ascii=False, sort_keys=True),
            now,
        ]
        table_columns = _table_columns(conn, "memory_provider_preflights")
        for column, value in _legacy_provider_preflight_policy_values(report, table_columns):
            columns.append(column)
            values.append(value)
        placeholders = ", ".join("?" for _ in columns)
        conn.execute(
            f"""
            INSERT INTO memory_provider_preflights ({", ".join(columns)})
            VALUES ({placeholders})
            """,
            values,
        )


def _upsert_provider_execution_policy(
    conn: sqlite3.Connection,
    policy: ProviderExecutionPolicy,
) -> None:
    now = _utc_now()
    metadata_json = json.dumps(policy.metadata or {}, ensure_ascii=False, sort_keys=True)
    values = (
        policy.authorization_id,
        _clean_id(policy.provider),
        _clean_model(policy.model),
        _clean_id(policy.operation),
        _clean_id(policy.provider_role) if policy.provider_role else None,
        int(bool(policy.allowed)),
        policy.max_calls,
        policy.max_cost_usd,
        policy.max_input_tokens,
        policy.max_output_tokens,
        policy.max_media_bytes,
        policy.max_documents,
        policy.valid_from,
        policy.valid_until,
        policy.approved_by,
        policy.approval_source,
        policy.approved_scope,
        policy.storage_rights,
        None if policy.prompt_injection_required is None else int(policy.prompt_injection_required),
        policy.rollback_scope,
        metadata_json,
        now,
        now,
    )
    conn.execute(
        """
        INSERT INTO memory_provider_authorizations (
            authorization_id, provider, model, operation, provider_role, allowed,
            max_calls, max_cost_usd, max_input_tokens, max_output_tokens, max_media_bytes,
            max_documents, valid_from, valid_until, approved_by, approval_source,
            approved_scope, storage_rights, prompt_injection_required, rollback_scope,
            metadata_json, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(authorization_id) DO UPDATE SET
            provider = excluded.provider,
            model = excluded.model,
            operation = excluded.operation,
            provider_role = excluded.provider_role,
            allowed = excluded.allowed,
            max_calls = excluded.max_calls,
            max_cost_usd = excluded.max_cost_usd,
            max_input_tokens = excluded.max_input_tokens,
            max_output_tokens = excluded.max_output_tokens,
            max_media_bytes = excluded.max_media_bytes,
            max_documents = excluded.max_documents,
            valid_from = excluded.valid_from,
            valid_until = excluded.valid_until,
            approved_by = excluded.approved_by,
            approval_source = excluded.approval_source,
            approved_scope = excluded.approved_scope,
            storage_rights = excluded.storage_rights,
            prompt_injection_required = excluded.prompt_injection_required,
            rollback_scope = excluded.rollback_scope,
            metadata_json = excluded.metadata_json,
            updated_at = excluded.updated_at
        """,
        values,
    )
    conn.execute(
        """
        INSERT INTO memory_provider_execution_policies (
            policy_id, authorization_id, provider, model, operation, provider_role, allowed,
            max_calls, max_cost_usd, max_input_tokens, max_output_tokens, max_media_bytes,
            max_documents, valid_from, valid_until, approved_by, approval_source,
            approved_scope, storage_rights, prompt_injection_required, rollback_scope,
            metadata_json, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(policy_id) DO UPDATE SET
            authorization_id = excluded.authorization_id,
            provider = excluded.provider,
            model = excluded.model,
            operation = excluded.operation,
            provider_role = excluded.provider_role,
            allowed = excluded.allowed,
            max_calls = excluded.max_calls,
            max_cost_usd = excluded.max_cost_usd,
            max_input_tokens = excluded.max_input_tokens,
            max_output_tokens = excluded.max_output_tokens,
            max_media_bytes = excluded.max_media_bytes,
            max_documents = excluded.max_documents,
            valid_from = excluded.valid_from,
            valid_until = excluded.valid_until,
            approved_by = excluded.approved_by,
            approval_source = excluded.approval_source,
            approved_scope = excluded.approved_scope,
            storage_rights = excluded.storage_rights,
            prompt_injection_required = excluded.prompt_injection_required,
            rollback_scope = excluded.rollback_scope,
            metadata_json = excluded.metadata_json,
            updated_at = excluded.updated_at
        """,
        (policy.policy_id, *values),
    )


def _insert_provider_transport_event(
    conn: sqlite3.Connection,
    *,
    transport_event_id: str,
    event_id: str,
    context: ApiBudgetContext,
    execution_policy: ProviderExecutionPolicy | None,
    provider: str,
    model: str,
    provider_role: str,
    operation: str,
    status: str,
    event_kind: str,
    started_at: str,
    finished_at: str | None,
    error: str | None,
    metadata: dict[str, Any],
) -> None:
    conn.execute(
        """
        INSERT INTO memory_provider_transport_events (
            transport_event_id, api_usage_event_id, run_id, job_id,
            authorization_id, execution_policy_id, provider, model, operation,
            provider_role, status, event_kind, started_at, finished_at, error,
            metadata_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            transport_event_id,
            event_id,
            context.run_id,
            context.job_id,
            execution_policy.authorization_id if execution_policy else None,
            execution_policy.policy_id if execution_policy else None,
            provider,
            model,
            operation,
            provider_role,
            status,
            event_kind,
            started_at,
            finished_at,
            error,
            json.dumps(metadata, ensure_ascii=False, sort_keys=True),
        ),
    )


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


def _active_exposure(
    conn: sqlite3.Connection,
    *,
    run_id: str | None = None,
) -> dict[str, Any]:
    clauses = ["status = 'reserved'", "finished_at IS NULL"]
    params: list[Any] = []
    if run_id:
        clauses.append("run_id = ?")
        params.append(run_id)
    rows = conn.execute(
        f"""
        SELECT *
        FROM memory_api_usage_events
        WHERE {' AND '.join(clauses)}
        ORDER BY started_at DESC
        """,
        params,
    ).fetchall()
    usage = _empty_usage()
    events: list[dict[str, Any]] = []
    now = datetime.now(UTC)
    max_age_seconds = 0
    for row in rows:
        item = _row_dict(row)
        units = _loads_dict(item.pop("units_json", "{}"))
        item["units"] = units
        item["metadata"] = _loads_dict(item.pop("metadata_json", "{}"))
        _add_units_to_usage(usage, units)
        usage["estimated_cost_usd"] += float(item.get("estimated_cost_usd") or 0.0)
        started_at = str(item.get("started_at") or "")
        age_seconds = _age_seconds(started_at, now)
        item["age_seconds"] = age_seconds
        max_age_seconds = max(max_age_seconds, age_seconds)
        events.append(item)
    estimated_cost = float(usage["estimated_cost_usd"] or 0.0)
    return {
        "active_count": len(events),
        "oldest_age_seconds": max_age_seconds,
        "estimated_cost_usd": estimated_cost,
        "estimated_cost_per_minute_usd": (
            estimated_cost / max(max_age_seconds, 1) * 60 if events else 0.0
        ),
        "units": usage,
        "events": events,
    }


def _age_seconds(value: str, now: datetime) -> int:
    if not value:
        return 0
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return 0
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return max(0, int((now - parsed.astimezone(UTC)).total_seconds()))


def _provider_usage(
    conn: sqlite3.Connection,
    *,
    run_id: str | None = None,
    since: str | None = None,
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
        SELECT provider, model, operation, status, units_json, estimated_cost_usd, actual_cost_usd
        FROM memory_api_usage_events
        {where}
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
                "retries": 0,
                "input_tokens": 0,
                "output_tokens": 0,
                "media_bytes": 0,
                "documents": 0,
                "pages": 0,
                "estimated_cost_usd": 0.0,
                "actual_cost_usd": 0.0,
                "event_count": 0,
                "status_counts": {},
                "reserved_events": 0,
                "ok_events": 0,
                "error_events": 0,
                "blocked_events": 0,
                "other_events": 0,
            },
        )
        status = str(row["status"] or "unknown")
        bucket["event_count"] += 1
        bucket["status_counts"][status] = int(bucket["status_counts"].get(status, 0)) + 1
        status_key = f"{status}_events"
        if status_key in bucket:
            bucket[status_key] += 1
        else:
            bucket["other_events"] += 1
        if status not in {"reserved", "ok", "error"}:
            continue
        units = _loads_dict(row["units_json"])
        _add_units_to_usage(bucket, units)
        bucket["estimated_cost_usd"] += float(row["estimated_cost_usd"] or 0.0)
        bucket["actual_cost_usd"] += float(row["actual_cost_usd"] or 0.0)
    return sorted(
        grouped.values(),
        key=lambda item: (item["estimated_cost_usd"], item["event_count"]),
        reverse=True,
    )


def _api_budget_event_snapshot_payload(
    path: Path,
    *,
    run_id: str | None,
    rows: list[sqlite3.Row],
) -> dict[str, Any]:
    counts = {
        "total_events": 0,
        "exempt_provider_events": 0,
        "non_exempt_provider_events": 0,
        "provider_requests_observed": 0,
        "provider_requests_blocked_by_freeze": 0,
        "provider_transport_sends_observed": 0,
        "blocked_events": 0,
        "reserved_events": 0,
        "ok_events": 0,
        "error_events": 0,
    }
    providers: dict[str, int] = {}
    for row in rows:
        provider = _clean_id(row["provider"])
        status = _clean_id(row["status"])
        metadata = _loads_dict(row["metadata_json"])
        counts["total_events"] += 1
        if status in {"blocked", "reserved", "ok", "error"}:
            counts[f"{status}_events"] += 1
        providers[provider] = providers.get(provider, 0) + 1
        if _is_exempt_provider(provider):
            counts["exempt_provider_events"] += 1
            continue
        counts["non_exempt_provider_events"] += 1
        counts["provider_requests_observed"] += 1
        if (
            status == "blocked"
            and metadata.get("freeze_status") == LEGACY_NO_QUOTA_FREEZE_BLOCK_STATUS
        ):
            counts["provider_requests_blocked_by_freeze"] += 1
        if status in {"ok", "error"}:
            counts["provider_transport_sends_observed"] += 1
    return {
        "artifact_kind": "research_x_api_budget_event_snapshot",
        "schema_version": 1,
        "db_path": str(path),
        "run_id": run_id,
        "captured_at": _utc_now(),
        "counts": counts,
        "providers": dict(sorted(providers.items())),
        "not_evidence": True,
    }


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


def _provider_control_summary(conn: sqlite3.Connection) -> dict[str, Any]:
    authorization = conn.execute(
        """
        SELECT
            COUNT(*) AS total,
            SUM(CASE WHEN allowed THEN 1 ELSE 0 END) AS allowed,
            SUM(CASE WHEN allowed THEN 0 ELSE 1 END) AS disabled
        FROM memory_provider_authorizations
        """
    ).fetchone()
    execution_policy = conn.execute(
        """
        SELECT
            COUNT(*) AS total,
            SUM(CASE WHEN allowed THEN 1 ELSE 0 END) AS allowed,
            SUM(CASE WHEN allowed THEN 0 ELSE 1 END) AS disabled
        FROM memory_provider_execution_policies
        """
    ).fetchone()
    return {
        "authorizations": int(authorization["total"] or 0),
        "allowed_authorizations": int(authorization["allowed"] or 0),
        "disabled_authorizations": int(authorization["disabled"] or 0),
        "execution_policies": int(execution_policy["total"] or 0),
        "allowed_execution_policies": int(execution_policy["allowed"] or 0),
        "disabled_execution_policies": int(execution_policy["disabled"] or 0),
    }


def _price_catalog_coverage(
    conn: sqlite3.Connection,
    *,
    run_id: str | None = None,
) -> dict[str, Any]:
    observed_keys, observed_by_source = _observed_api_keys(conn, run_id=run_id)
    price_rows = conn.execute(
        """
        SELECT provider, model, operation, unit
        FROM memory_api_price_catalog
        """
    ).fetchall()
    price_keys = {
        (str(row["provider"]), str(row["model"]), str(row["operation"])) for row in price_rows
    }
    priced_keys = {
        key
        for key in observed_keys
        if any(_price_key_covers(price_key, key) for price_key in price_keys)
    }
    missing_keys = sorted(observed_keys - priced_keys)
    return {
        "observed_api_count": len(observed_keys),
        "priced_observed_api_count": len(priced_keys),
        "unpriced_observed_api_count": len(missing_keys),
        "price_rows": len(price_rows),
        "priced_api_keys": [
            _api_key_payload(provider, model, operation)
            for provider, model, operation in sorted(priced_keys)
        ],
        "missing_price_api_keys": [
            _api_key_payload(provider, model, operation)
            for provider, model, operation in missing_keys
        ],
        "observed_by_source": observed_by_source,
    }


def _observed_api_keys(
    conn: sqlite3.Connection,
    *,
    run_id: str | None = None,
) -> tuple[set[tuple[str, str, str]], dict[str, int]]:
    table_specs = (
        ("memory_api_usage_events", "run_id", "usage_events"),
        ("memory_provider_preflights", "run_id", "provider_preflights"),
        ("memory_provider_transport_events", "run_id", "provider_transport_events"),
        ("memory_provider_authorizations", None, "provider_authorizations"),
        ("memory_provider_execution_policies", None, "provider_execution_policies"),
    )
    observed: set[tuple[str, str, str]] = set()
    by_source: dict[str, int] = {}
    for table_name, run_column, source_name in table_specs:
        clauses: list[str] = []
        params: list[Any] = []
        if run_id and run_column:
            clauses.append(f"{run_column} = ?")
            params.append(run_id)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = conn.execute(
            f"""
            SELECT provider, model, operation
            FROM {table_name}
            {where}
            """,
            params,
        ).fetchall()
        by_source[source_name] = len(rows)
        for row in rows:
            observed.add((str(row["provider"]), str(row["model"]), str(row["operation"])))
    return observed, by_source


def _price_key_covers(
    price_key: tuple[str, str, str],
    api_key: tuple[str, str, str],
) -> bool:
    return all(
        price_value in {api_value, "*"}
        for price_value, api_value in zip(price_key, api_key, strict=True)
    )


def _api_key_payload(provider: str, model: str, operation: str) -> dict[str, str]:
    return {"provider": provider, "model": model, "operation": operation}


def _provider_authorization_rows(
    conn: sqlite3.Connection,
    *,
    limit: int = 20,
) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT *
        FROM memory_provider_authorizations
        ORDER BY updated_at DESC
        LIMIT ?
        """,
        (max(1, limit),),
    ).fetchall()
    return [_provider_policy_row_dict(row) for row in rows]


def _provider_execution_policy_rows(
    conn: sqlite3.Connection,
    *,
    limit: int = 20,
) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT *
        FROM memory_provider_execution_policies
        ORDER BY updated_at DESC
        LIMIT ?
        """,
        (max(1, limit),),
    ).fetchall()
    return [_provider_policy_row_dict(row) for row in rows]


def _load_provider_execution_policy_from_conn(
    conn: sqlite3.Connection,
    *,
    authorization_id: str | None = None,
    policy_id: str | None = None,
) -> ProviderExecutionPolicy:
    if not authorization_id and not policy_id:
        raise ValueError("authorization_id or policy_id is required")
    if policy_id:
        row = conn.execute(
            """
            SELECT *
            FROM memory_provider_execution_policies
            WHERE policy_id = ?
            """,
            (policy_id,),
        ).fetchone()
        if row is None:
            raise ApiBudgetError(f"ProviderExecutionPolicy not found: {policy_id}")
        payload = _provider_policy_row_dict(row)
        if authorization_id and payload["authorization_id"] != authorization_id:
            raise ApiBudgetError(
                "ProviderExecutionPolicy authorization mismatch: "
                f"{payload['authorization_id']} != {authorization_id}"
            )
        return _loaded_provider_execution_policy(payload)

    rows = conn.execute(
        """
        SELECT *
        FROM memory_provider_execution_policies
        WHERE authorization_id = ?
        ORDER BY updated_at DESC, policy_id DESC
        """,
        (authorization_id,),
    ).fetchall()
    if not rows:
        raise ApiBudgetError(
            f"ProviderExecutionPolicy not found for authorization: {authorization_id}"
        )
    return _loaded_provider_execution_policy(_provider_policy_row_dict(rows[0]))


def _load_provider_authorization_from_conn(
    conn: sqlite3.Connection,
    authorization_id: str | None,
) -> ProviderQuotaApproval | None:
    if not authorization_id:
        return None
    row = conn.execute(
        """
        SELECT *
        FROM memory_provider_authorizations
        WHERE authorization_id = ?
        """,
        (authorization_id,),
    ).fetchone()
    if row is None:
        return None
    return _provider_quota_approval_from_authorization_payload(_provider_policy_row_dict(row))


def _provider_preflight_rows(
    conn: sqlite3.Connection,
    *,
    run_id: str | None = None,
    limit: int,
) -> list[dict[str, Any]]:
    clauses: list[str] = []
    params: list[Any] = []
    if run_id:
        clauses.append("run_id = ?")
        params.append(run_id)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    rows = conn.execute(
        f"""
        SELECT
            preflight_id, run_id, policy_id, authorization_id, execution_policy_id,
            provider, model, operation, provider_role, status, provider_call_allowed,
            provider_requests_sent, provider_policy_required, provider_policy_status, units_json,
            estimated_cost_usd, price_status, budget_status, approval_valid,
            execution_policy_valid, created_at
        FROM memory_provider_preflights
        {where}
        ORDER BY created_at DESC
        LIMIT ?
        """,
        [*params, max(1, limit)],
    ).fetchall()
    result = []
    for row in rows:
        item = _row_dict(row)
        item["units"] = _loads_dict(item.pop("units_json", "{}"))
        result.append(item)
    return result


def _legacy_provider_preflight_policy_values(
    report: Mapping[str, Any],
    table_columns: set[str],
) -> list[tuple[str, Any]]:
    legacy_required_column = "fre" + "eze_active"
    legacy_status_column = "fre" + "eze_status"
    values: list[tuple[str, Any]] = []
    if legacy_required_column in table_columns:
        values.append((legacy_required_column, int(bool(report["provider_policy_required"]))))
    if legacy_status_column in table_columns:
        values.append((legacy_status_column, report["provider_policy_status"]))
    return values


def _provider_transport_event_rows(
    conn: sqlite3.Connection,
    *,
    run_id: str | None = None,
    limit: int,
) -> list[dict[str, Any]]:
    clauses: list[str] = []
    params: list[Any] = []
    if run_id:
        clauses.append("run_id = ?")
        params.append(run_id)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    rows = conn.execute(
        f"""
        SELECT *
        FROM memory_provider_transport_events
        {where}
        ORDER BY started_at DESC
        LIMIT ?
        """,
        [*params, max(1, limit)],
    ).fetchall()
    result = []
    for row in rows:
        item = _row_dict(row)
        item["metadata"] = _loads_dict(item.pop("metadata_json", "{}"))
        result.append(item)
    return result


def _provider_authorization_usage(
    conn: sqlite3.Connection,
    policy: ProviderExecutionPolicy | None,
) -> dict[str, Any]:
    usage = _empty_usage()
    if policy is None:
        return usage
    rows = conn.execute(
        """
        SELECT units_json, estimated_cost_usd, metadata_json
        FROM memory_api_usage_events
        WHERE status IN ('reserved', 'ok', 'error')
        """
    ).fetchall()
    for row in rows:
        metadata = _loads_dict(row["metadata_json"])
        if not (
            metadata.get("provider_authorization_id") == policy.authorization_id
            or metadata.get("provider_execution_policy_id") == policy.policy_id
        ):
            continue
        units = _loads_dict(row["units_json"])
        _add_units_to_usage(usage, units)
        usage["estimated_cost_usd"] += float(row["estimated_cost_usd"] or 0.0)
    return usage


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


def _provider_execution_policy_from_approval(
    approval: ProviderQuotaApproval | None,
) -> ProviderExecutionPolicy | None:
    if approval is None:
        return None
    return ProviderExecutionPolicy(
        policy_id=f"approval:{approval.provider_quota_approval_id}",
        authorization_id=approval.provider_quota_approval_id,
        provider=approval.provider,
        model=approval.model,
        operation=approval.operation,
        provider_role=approval.provider_role,
        allowed=True,
        max_calls=approval.max_calls,
        max_cost_usd=approval.max_cost_usd,
        valid_from=approval.approved_at,
        valid_until=approval.expires_at,
        approved_by=approval.approved_by,
        approval_source=approval.price_source,
        approved_scope=approval.approved_scope,
        metadata=approval.metadata,
        source_kind="quota_approval",
    )


def _provider_quota_approval_from_authorization_payload(
    payload: Mapping[str, Any],
) -> ProviderQuotaApproval | None:
    if payload.get("max_calls") is None or payload.get("max_cost_usd") is None:
        return None
    return ProviderQuotaApproval(
        provider_quota_approval_id=str(payload["authorization_id"]),
        provider=str(payload["provider"]),
        model=str(payload["model"]),
        operation=str(payload["operation"]),
        max_calls=int(payload["max_calls"]),
        max_cost_usd=float(payload["max_cost_usd"]),
        price_source=str(payload.get("approval_source") or "saved_authorization"),
        approved_scope=str(payload.get("approved_scope") or "*"),
        approved_at=str(payload.get("valid_from") or payload.get("created_at") or _utc_now()),
        provider_role=_optional_str(payload.get("provider_role")),
        approved_by=_optional_str(payload.get("approved_by")),
        expires_at=_optional_str(payload.get("valid_until")),
        metadata=payload.get("metadata") if isinstance(payload.get("metadata"), dict) else None,
    )


def _provider_quota_approval_from_execution_policy(
    policy: ProviderExecutionPolicy | None,
) -> ProviderQuotaApproval | None:
    if policy is None or policy.max_calls is None or policy.max_cost_usd is None:
        return None
    return ProviderQuotaApproval(
        provider_quota_approval_id=policy.authorization_id,
        provider=policy.provider,
        model=policy.model,
        operation=policy.operation,
        max_calls=policy.max_calls,
        max_cost_usd=policy.max_cost_usd,
        price_source=policy.approval_source or "saved_execution_policy",
        approved_scope=policy.approved_scope or "*",
        approved_at=policy.valid_from or _utc_now(),
        provider_role=policy.provider_role,
        approved_by=policy.approved_by,
        expires_at=policy.valid_until,
        metadata=policy.metadata,
    )


def _coerce_provider_execution_policy(
    policy: ProviderExecutionPolicy | dict[str, Any] | None,
) -> ProviderExecutionPolicy | None:
    if policy is None:
        return None
    if isinstance(policy, ProviderExecutionPolicy):
        return policy
    if not isinstance(policy, dict):
        raise TypeError("provider execution policy must be a mapping")
    required = ("policy_id", "authorization_id", "provider", "model", "operation")
    missing = [key for key in required if policy.get(key) in (None, "")]
    if missing:
        raise ValueError("provider execution policy missing fields: " + ", ".join(missing))
    return ProviderExecutionPolicy(
        policy_id=str(policy["policy_id"]),
        authorization_id=str(policy["authorization_id"]),
        provider=str(policy["provider"]),
        model=str(policy["model"]),
        operation=str(policy["operation"]),
        provider_role=_optional_str(policy.get("provider_role")),
        allowed=_bool_value(policy.get("allowed", True)),
        max_calls=_optional_int(policy.get("max_calls")),
        max_cost_usd=_optional_float(policy.get("max_cost_usd")),
        max_input_tokens=_optional_int(policy.get("max_input_tokens")),
        max_output_tokens=_optional_int(policy.get("max_output_tokens")),
        max_media_bytes=_optional_int(policy.get("max_media_bytes")),
        max_documents=_optional_int(policy.get("max_documents")),
        valid_from=_optional_str(policy.get("valid_from")),
        valid_until=_optional_str(policy.get("valid_until")),
        approved_by=_optional_str(policy.get("approved_by")),
        approval_source=_optional_str(policy.get("approval_source")),
        approved_scope=_optional_str(policy.get("approved_scope")),
        storage_rights=_optional_str(policy.get("storage_rights")),
        prompt_injection_required=_optional_bool(policy.get("prompt_injection_required")),
        rollback_scope=_optional_str(policy.get("rollback_scope")),
        metadata=policy.get("metadata") if isinstance(policy.get("metadata"), dict) else None,
        source_kind=_optional_str(policy.get("source_kind")),
    )


def _loaded_provider_execution_policy(payload: dict[str, Any]) -> ProviderExecutionPolicy:
    policy = _coerce_provider_execution_policy(payload)
    if policy is None:
        raise ApiBudgetError("ProviderExecutionPolicy row could not be loaded")
    return replace(policy, source_kind="saved_policy")


def _requires_saved_policy_governance_fields(
    policy: ProviderExecutionPolicy,
    *,
    provider: str,
) -> bool:
    return policy.source_kind == "saved_policy" and not _is_exempt_provider(provider)


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


def _provider_execution_policy_validation_payload(
    *,
    policy: ProviderExecutionPolicy | None,
    errors: list[str],
    units: dict[str, int | float],
    estimated_cost_usd: float | None,
    current_usage: dict[str, Any] | None,
) -> dict[str, Any]:
    return {
        "valid": not errors,
        "errors": errors,
        "policy": provider_execution_policy_as_dict(policy) if policy else None,
        "units": units,
        "estimated_cost_usd": estimated_cost_usd,
        "current_usage": current_usage or _empty_usage(),
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


def _validate_policy_timestamp(
    field_name: str,
    value: str,
    errors: list[str],
) -> datetime | None:
    text = str(value).strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        errors.append(f"policy {field_name} must be ISO-8601")
        return None
    if parsed.tzinfo is None:
        errors.append(f"policy {field_name} must include a timezone")
        return None
    return parsed


def _validate_policy_limit(
    errors: list[str],
    *,
    label: str,
    planned: float,
    current: float,
    limit: int | float | None,
) -> None:
    if limit is None:
        return
    if float(limit) < 0:
        errors.append(f"policy {label} limit must be non-negative")
        return
    if current + planned > float(limit):
        errors.append(
            f"policy {label} limit exceeded: {current + planned:g} > {float(limit):g}"
        )


def _optional_str(value: Any) -> str | None:
    if value in (None, ""):
        return None
    return str(value)


def _optional_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    return int(value)


def _optional_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    return float(value)


def _optional_bool(value: Any) -> bool | None:
    if value in (None, ""):
        return None
    return _bool_value(value)


def _bool_value(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return bool(value)
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"expected boolean value, got {value!r}")


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
    material = _request_fingerprint_material(value)
    payload = json.dumps(material, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    return hashlib.blake2b(payload, digest_size=32).hexdigest()


def _event_id(*parts: object) -> str:
    payload = "|".join(str(part) for part in (*parts, uuid.uuid4().hex))
    return hashlib.blake2b(payload.encode("utf-8"), digest_size=16).hexdigest()


def _request_fingerprint_material(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float)):
        return {"type": type(value).__name__}
    if isinstance(value, str):
        return {"type": "str", "length": len(value)}
    if isinstance(value, bytes):
        return {"type": "bytes", "length": len(value)}
    if isinstance(value, dict):
        return {
            "type": "dict",
            "length": len(value),
            "items": _request_fingerprint_dict_items(value),
        }
    if isinstance(value, (list, tuple, set)):
        items = list(value)
        return {
            "type": type(value).__name__,
            "length": len(items),
            "items": [_request_fingerprint_material(item) for item in items[:20]],
        }
    return {"type": type(value).__name__, "repr_length": len(str(value))}


def _request_fingerprint_dict_items(value: dict[Any, Any]) -> list[dict[str, Any]]:
    items = [
        {
            "key": {"type": type(key).__name__, "length": len(str(key))},
            "value": _request_fingerprint_material(item),
        }
        for key, item in value.items()
    ]
    return sorted(
        items,
        key=lambda item: json.dumps(item, ensure_ascii=False, sort_keys=True, default=str),
    )


def _clean_id(value: str) -> str:
    return str(value or "").strip().lower() or "unknown"


def _clean_model(value: str) -> str:
    return str(value or "").strip() or "unknown"


def _is_exempt_provider(provider: str) -> bool:
    provider_id = _clean_id(provider)
    return provider_id in EXEMPT_PROVIDERS


def _is_local_or_non_http_transport_url(url: str) -> bool:
    parsed = urlparse(str(url or ""))
    if parsed.scheme not in {"http", "https"}:
        return True
    hostname = (parsed.hostname or "").strip().lower()
    return hostname in {"localhost", "127.0.0.1", "::1"} or hostname.endswith(".localhost")


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


def _table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def _provider_policy_row_dict(row: sqlite3.Row) -> dict[str, Any]:
    item = _row_dict(row)
    item["metadata"] = _loads_dict(item.pop("metadata_json", "{}"))
    return item


def _empty_usage() -> dict[str, Any]:
    return {
        "calls": 0,
        "retries": 0,
        "input_tokens": 0,
        "output_tokens": 0,
        "media_bytes": 0,
        "documents": 0,
        "pages": 0,
        "estimated_cost_usd": 0.0,
    }


def _add_units_to_usage(usage: dict[str, Any], units: dict[str, Any]) -> None:
    for key in (
        "calls",
        "retries",
        "input_tokens",
        "output_tokens",
        "media_bytes",
        "documents",
        "pages",
    ):
        usage[key] += int(float(units.get(key, 0) or 0))


def _execution_policy_event_metadata(
    *,
    execution_policy: ProviderExecutionPolicy | None,
    execution_result: dict[str, Any],
    provider_policy_required: bool,
) -> dict[str, Any]:
    valid = bool(execution_result.get("valid"))
    provider_policy_status = _provider_policy_status(
        provider_policy_required=provider_policy_required,
        provider_call_allowed=valid,
    )
    metadata = {
        "provider_execution_policy_valid": valid,
        "provider_execution_policy_errors": execution_result.get("errors", []),
        "provider_policy_required": provider_policy_required,
        "provider_policy_status": provider_policy_status,
    }
    if execution_policy is not None:
        metadata.update(
            {
                "provider_authorization_id": execution_policy.authorization_id,
                "provider_execution_policy_id": execution_policy.policy_id,
                "provider_execution_allowed": execution_policy.allowed,
            }
        )
    return metadata


def _provider_policy_status(
    *,
    provider_policy_required: bool,
    provider_call_allowed: bool,
) -> str:
    if provider_policy_required and provider_call_allowed:
        return PROVIDER_EXECUTION_AUTHORIZED_STATUS
    if provider_policy_required:
        return PROVIDER_EXECUTION_POLICY_REQUIRED_STATUS
    return "provider_policy_not_required"


def _provider_preflight_scope_match(
    *,
    approval: ProviderQuotaApproval | None,
    execution_policy: ProviderExecutionPolicy | None,
    current_scope: str | None,
) -> bool:
    if not current_scope:
        return True
    scopes: list[str | None] = []
    if approval is not None:
        scopes.append(approval.approved_scope)
    if execution_policy is not None:
        scopes.append(execution_policy.approved_scope)
    if not scopes:
        return False
    return all(scope in {None, "*", current_scope} for scope in scopes)


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
