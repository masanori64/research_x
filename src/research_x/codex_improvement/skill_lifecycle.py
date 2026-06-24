from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any

LIFECYCLE_ACTIONS = {"create", "reuse", "evaluate", "refine", "retire", "reject"}
LIFECYCLE_TRIGGERS = {
    "failed_run",
    "manifest_drift",
    "repeated_regression",
    "review_finding",
    "user_request",
}
HUMAN_DECISIONS = {"accepted", "pending", "rejected"}
RESULT_STATUSES = {"blocked", "failed", "not_applicable", "not_run", "passed"}
SOURCE_ORIGINS = {"repo_owned", "third_party", "unknown"}


@dataclass(frozen=True)
class SkillLifecycleInput:
    lifecycle_action: str
    trigger: str
    responsible_artifact: str
    candidate_diff_ref: str = ""
    examples_ref: str = ""
    tests_ref: str = ""
    replay_result: dict[str, Any] = field(default_factory=lambda: {"status": "not_run"})
    qualifier_result: dict[str, Any] = field(default_factory=lambda: {"status": "not_run"})
    human_decision: str = "pending"
    source_review_required: bool = False
    auto_apply_allowed: bool = False
    source_origin: str = "repo_owned"

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def validate_skill_lifecycle_input(record: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    required = {"lifecycle_action", "trigger", "responsible_artifact"}
    missing = sorted(required - set(record))
    if missing:
        return [f"missing fields: {', '.join(missing)}"]
    prefix = str(record.get("responsible_artifact") or "<unknown>")
    if record["lifecycle_action"] not in LIFECYCLE_ACTIONS:
        errors.append(f"{prefix}: invalid lifecycle_action {record['lifecycle_action']!r}")
    if record["trigger"] not in LIFECYCLE_TRIGGERS:
        errors.append(f"{prefix}: invalid trigger {record['trigger']!r}")
    if record.get("human_decision", "pending") not in HUMAN_DECISIONS:
        errors.append(f"{prefix}: invalid human_decision {record.get('human_decision')!r}")
    if record.get("source_origin", "repo_owned") not in SOURCE_ORIGINS:
        errors.append(f"{prefix}: invalid source_origin {record.get('source_origin')!r}")
    if record.get("auto_apply_allowed", False) is not False:
        errors.append(f"{prefix}: auto_apply_allowed must be false")
    if not isinstance(record.get("source_review_required", False), bool):
        errors.append(f"{prefix}: source_review_required must be a boolean")
    if (
        record.get("source_origin") == "third_party"
        and record.get("source_review_required") is not True
    ):
        errors.append(f"{prefix}: third_party source requires source_review_required true")
    _validate_result(errors, prefix, record, "replay_result")
    _validate_result(errors, prefix, record, "qualifier_result")
    return errors


def load_skill_lifecycle_input(record: dict[str, Any]) -> SkillLifecycleInput:
    errors = validate_skill_lifecycle_input(record)
    if errors:
        raise ValueError("; ".join(errors))
    return SkillLifecycleInput(
        lifecycle_action=str(record["lifecycle_action"]),
        trigger=str(record["trigger"]),
        responsible_artifact=str(record["responsible_artifact"]),
        candidate_diff_ref=str(record.get("candidate_diff_ref", "")),
        examples_ref=str(record.get("examples_ref", "")),
        tests_ref=str(record.get("tests_ref", "")),
        replay_result=_result_or_default(record.get("replay_result")),
        qualifier_result=_result_or_default(record.get("qualifier_result")),
        human_decision=str(record.get("human_decision", "pending")),
        source_review_required=bool(record.get("source_review_required", False)),
        auto_apply_allowed=False,
        source_origin=str(record.get("source_origin", "repo_owned")),
    )


def skill_lifecycle_gate_status(record: dict[str, Any] | SkillLifecycleInput) -> str:
    lifecycle = (
        record
        if isinstance(record, SkillLifecycleInput)
        else load_skill_lifecycle_input(record)
    )
    if lifecycle.source_review_required and lifecycle.source_origin != "repo_owned":
        return "pending_source_review"
    if _result_status(lifecycle.replay_result) != "passed":
        return "pending"
    if _result_status(lifecycle.qualifier_result) != "passed":
        return "pending"
    if lifecycle.human_decision == "pending":
        return "pending"
    return lifecycle.human_decision


def format_skill_lifecycle_report(record: dict[str, Any] | SkillLifecycleInput) -> str:
    lifecycle = (
        record
        if isinstance(record, SkillLifecycleInput)
        else load_skill_lifecycle_input(record)
    )
    data = lifecycle.as_dict()
    lines = [
        "# Skill Lifecycle Input",
        "",
        "Proposal Only. Do not auto-apply this report, edit Skill files, or update manifests.",
        "",
        f"- Lifecycle action: `{lifecycle.lifecycle_action}`",
        f"- Trigger: `{lifecycle.trigger}`",
        f"- Responsible artifact: `{lifecycle.responsible_artifact}`",
        f"- Source origin: `{lifecycle.source_origin}`",
        f"- Source review required: `{str(lifecycle.source_review_required).lower()}`",
        f"- Auto apply allowed: `{str(lifecycle.auto_apply_allowed).lower()}`",
        f"- Gate status: `{skill_lifecycle_gate_status(lifecycle)}`",
        "",
        "## Raw Input",
        "",
        "```json",
        json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True),
        "```",
    ]
    return "\n".join(lines) + "\n"


def _validate_result(
    errors: list[str],
    prefix: str,
    record: dict[str, Any],
    key: str,
) -> None:
    value = record.get(key, {"status": "not_run"})
    if not isinstance(value, dict):
        errors.append(f"{prefix}: {key} must be an object")
        return
    status = value.get("status", "not_run")
    if status not in RESULT_STATUSES:
        errors.append(f"{prefix}: invalid {key}.status {status!r}")


def _result_or_default(value: object | None) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {"status": "not_run"}
    result = dict(value)
    if "status" not in result:
        result["status"] = "not_run"
    return result


def _result_status(value: dict[str, Any]) -> str:
    return str(value.get("status", "not_run"))
