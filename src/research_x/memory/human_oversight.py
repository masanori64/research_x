from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import StrEnum
from typing import Any

from research_x.memory.api_budget import (
    ProviderOperationClass,
    classify_provider_operation,
    provider_operation_class_policy,
)


class HumanOversightLevel(StrEnum):
    NO_HUMAN_REQUIRED = "no_human_required"
    HUMAN_ON_THE_LOOP = "human_on_the_loop"
    HUMAN_IN_THE_LOOP = "human_in_the_loop"
    HARD_STOP = "hard_stop"


@dataclass(frozen=True)
class HumanOversightDecision:
    operation: str
    operation_class: str
    oversight_level: HumanOversightLevel
    requires_explicit_approval: bool
    api_budget_guard_required: bool
    separate_gate: str | None
    hard_stop_reasons: tuple[str, ...]
    notes: str

    def as_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["oversight_level"] = self.oversight_level.value
        return data


HARD_STOP_FLAGS = frozenset(
    {
        "secret",
        "credential",
        "cookie",
        "hidden_backend_api",
        "captcha_bypass",
        "security_challenge_bypass",
        "destructive_unbounded",
        "untrusted_text_tool_authorization",
    }
)

_NO_HUMAN_REQUIRED_OPERATIONS = frozenset(
    {
        "local_read_only_search",
        "explore",
        "collect",
        "working_note_create",
        "working_note_draft",
        "fake_provider_test",
        "local_fake_provider_test",
    }
)

_HUMAN_ON_THE_LOOP_OPERATIONS = frozenset(
    {
        "synthesize",
        "evidence_package_review",
        "eval_review",
        "route_comparison",
        "audit_review",
        "post_hoc_drift_review",
    }
)

_HUMAN_IN_THE_LOOP_OPERATIONS = frozenset(
    {
        "external_fetch_beyond_explicit_source",
        "external_alert_delivery",
        "external_alert_sink_enablement",
        "working_note_promote",
        "working_note_to_curated_source",
        "route_promotion",
        "schema_migration_persisted_data",
        "answer_assertion_high_risk",
    }
)


def classify_human_oversight(
    operation: str,
    *,
    risk_flags: tuple[str, ...] = (),
) -> HumanOversightDecision:
    operation_id = _clean_id(operation)
    normalized_risk_flags = tuple(
        str(flag).strip().casefold() for flag in risk_flags if str(flag).strip()
    )
    hard_stop_reasons = tuple(
        flag for flag in normalized_risk_flags if flag in HARD_STOP_FLAGS
    )
    operation_class = classify_provider_operation(operation)
    provider_policy = provider_operation_class_policy(operation_class)
    if hard_stop_reasons:
        return HumanOversightDecision(
            operation=operation,
            operation_class=operation_class.value,
            oversight_level=HumanOversightLevel.HARD_STOP,
            requires_explicit_approval=True,
            api_budget_guard_required=provider_policy.api_budget_guard_required,
            separate_gate=provider_policy.separate_gate,
            hard_stop_reasons=hard_stop_reasons,
            notes="hard stop risk flag requires redesign or explicit manual handling",
        )
    if operation_id in _NO_HUMAN_REQUIRED_OPERATIONS:
        return _local_decision(
            operation=operation,
            operation_class=operation_id,
            oversight_level=HumanOversightLevel.NO_HUMAN_REQUIRED,
            requires_explicit_approval=False,
            notes="local non-destructive operation",
        )
    if operation_id in _HUMAN_ON_THE_LOOP_OPERATIONS:
        return _local_decision(
            operation=operation,
            operation_class=operation_id,
            oversight_level=HumanOversightLevel.HUMAN_ON_THE_LOOP,
            requires_explicit_approval=False,
            notes="human review can monitor or revise after local output",
        )
    if operation_id in _HUMAN_IN_THE_LOOP_OPERATIONS:
        return _local_decision(
            operation=operation,
            operation_class=operation_id,
            oversight_level=HumanOversightLevel.HUMAN_IN_THE_LOOP,
            requires_explicit_approval=True,
            notes="operation changes external, promotion, schema, or high-risk assertion state",
        )
    if operation_class in {
        ProviderOperationClass.RUNTIME_PROVIDER_CALL,
        ProviderOperationClass.QUOTA_CONSUMING_RUNTIME,
    } or provider_policy.separate_gate is not None:
        oversight_level = HumanOversightLevel.HUMAN_IN_THE_LOOP
    elif operation_class is ProviderOperationClass.UPSTREAM_REVIEW:
        oversight_level = HumanOversightLevel.HUMAN_ON_THE_LOOP
    else:
        oversight_level = HumanOversightLevel.NO_HUMAN_REQUIRED
    return HumanOversightDecision(
        operation=operation,
        operation_class=operation_class.value,
        oversight_level=oversight_level,
        requires_explicit_approval=provider_policy.explicit_approval_required,
        api_budget_guard_required=provider_policy.api_budget_guard_required,
        separate_gate=provider_policy.separate_gate,
        hard_stop_reasons=(),
        notes=provider_policy.notes,
    )


def _local_decision(
    *,
    operation: str,
    operation_class: str,
    oversight_level: HumanOversightLevel,
    requires_explicit_approval: bool,
    notes: str,
) -> HumanOversightDecision:
    return HumanOversightDecision(
        operation=operation,
        operation_class=operation_class,
        oversight_level=oversight_level,
        requires_explicit_approval=requires_explicit_approval,
        api_budget_guard_required=False,
        separate_gate=None,
        hard_stop_reasons=(),
        notes=notes,
    )


def _clean_id(value: str) -> str:
    return str(value).strip().casefold().replace("-", "_").replace(" ", "_")
