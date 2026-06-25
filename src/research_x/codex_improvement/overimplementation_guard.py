from __future__ import annotations

from dataclasses import asdict, dataclass

RISK_EXCEPTIONS = {
    "accessibility",
    "data_integrity",
    "migration",
    "none",
    "performance",
    "security",
}
DECISIONS = {
    "blocked",
    "implement_new",
    "needs_review",
    "reuse_existing",
    "simplify",
    "staging",
}
BLOCKED_TERMS = ("hook", "mcp", "plugin")
DEPENDENCY_TERMS = ("dependency", "install", "new package", "pip install", "uv add")


@dataclass(frozen=True)
class OverImplementationGuardInput:
    requested_change: str
    existing_surfaces_checked: bool
    stdlib_or_native_checked: bool
    existing_dependency_checked: bool
    delete_or_simplify_option: bool
    why_new_code_is_needed: str
    risk_exception: str = "none"
    decision: str = "needs_review"

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class OverImplementationGuardResult:
    decision: str
    reasons: tuple[str, ...]
    report_only: bool = True
    adoption_shape: str = "review"


def validate_overimplementation_guard_input(record: dict[str, object]) -> list[str]:
    required = {
        "requested_change",
        "existing_surfaces_checked",
        "stdlib_or_native_checked",
        "existing_dependency_checked",
        "delete_or_simplify_option",
        "why_new_code_is_needed",
        "decision",
    }
    missing = sorted(required - set(record))
    if missing:
        return [f"missing fields: {', '.join(missing)}"]
    errors: list[str] = []
    if record.get("risk_exception", "none") not in RISK_EXCEPTIONS:
        errors.append(f"invalid risk_exception {record.get('risk_exception')!r}")
    if record["decision"] not in DECISIONS:
        errors.append(f"invalid decision {record['decision']!r}")
    for key in (
        "existing_surfaces_checked",
        "stdlib_or_native_checked",
        "existing_dependency_checked",
        "delete_or_simplify_option",
    ):
        if not isinstance(record[key], bool):
            errors.append(f"{key} must be a boolean")
    return errors


def load_overimplementation_guard_input(record: dict[str, object]) -> OverImplementationGuardInput:
    errors = validate_overimplementation_guard_input(record)
    if errors:
        raise ValueError("; ".join(errors))
    return OverImplementationGuardInput(
        requested_change=str(record["requested_change"]),
        existing_surfaces_checked=bool(record["existing_surfaces_checked"]),
        stdlib_or_native_checked=bool(record["stdlib_or_native_checked"]),
        existing_dependency_checked=bool(record["existing_dependency_checked"]),
        delete_or_simplify_option=bool(record["delete_or_simplify_option"]),
        why_new_code_is_needed=str(record["why_new_code_is_needed"]),
        risk_exception=str(record.get("risk_exception", "none")),
        decision=str(record["decision"]),
    )


def evaluate_overimplementation_guard(
    record: dict[str, object] | OverImplementationGuardInput,
) -> OverImplementationGuardResult:
    guard = (
        record
        if isinstance(record, OverImplementationGuardInput)
        else load_overimplementation_guard_input(record)
    )
    text = f"{guard.requested_change} {guard.why_new_code_is_needed}".casefold()
    reasons: list[str] = []
    if any(term in text for term in BLOCKED_TERMS):
        reasons.append("plugin/hook/MCP adoption requires isolated staging and manual promotion")
        return OverImplementationGuardResult("staging", tuple(reasons), adoption_shape="staging")
    if any(term in text for term in DEPENDENCY_TERMS) and (
        not guard.stdlib_or_native_checked or not guard.existing_dependency_checked
    ):
        reasons.append(
            "new dependency/install proposal needs dependency-review staging before adoption"
        )
        return OverImplementationGuardResult("staging", tuple(reasons), adoption_shape="staging")
    if guard.risk_exception in {"security", "accessibility", "data_integrity", "migration"}:
        if guard.decision == "simplify":
            reasons.append("risk exception cannot be removed as YAGNI")
            return OverImplementationGuardResult(
                "needs_review",
                tuple(reasons),
                adoption_shape="review",
            )
        reasons.append("risk exception allows non-minimal implementation when justified")
        return OverImplementationGuardResult(
            guard.decision,
            tuple(reasons),
            adoption_shape=_adoption_shape_for_decision(guard.decision),
        )
    if guard.decision == "implement_new" and not guard.existing_surfaces_checked:
        reasons.append("existing surfaces were not checked before implement_new")
        return OverImplementationGuardResult(
            "needs_review",
            tuple(reasons),
            adoption_shape="review",
        )
    if guard.delete_or_simplify_option and guard.decision == "implement_new":
        reasons.append("delete_or_simplify option exists and must be reviewed before new code")
        return OverImplementationGuardResult(
            "needs_review",
            tuple(reasons),
            adoption_shape="review",
        )
    if guard.decision in {"reuse_existing", "simplify"}:
        reasons.append("existing or simpler surface is preferred")
    else:
        reasons.append("new code passed local guard inputs")
    return OverImplementationGuardResult(
        guard.decision,
        tuple(reasons),
        adoption_shape=_adoption_shape_for_decision(guard.decision),
    )


def _adoption_shape_for_decision(decision: str) -> str:
    if decision in {"implement_new", "reuse_existing", "simplify"}:
        return "adopt"
    if decision == "staging":
        return "staging"
    if decision == "blocked":
        return "blocked"
    return "review"
