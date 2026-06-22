from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

DEFAULT_BASE_DIR = Path(".codex") / "improvement"
DEFAULT_SIGNALS_PATH = DEFAULT_BASE_DIR / "signals.jsonl"
DEFAULT_TRIAGE_JSONL_PATH = DEFAULT_BASE_DIR / "triage.jsonl"
DEFAULT_TRIAGE_REPORT_PATH = DEFAULT_BASE_DIR / "triage_report.md"
DEFAULT_REJECTED_EDITS_PATH = DEFAULT_BASE_DIR / "rejected_edits.jsonl"
DEFAULT_CANDIDATES_DIR = DEFAULT_BASE_DIR / "candidates"

SOURCE_TYPES = {
    "user_feedback",
    "workflow_trace",
    "eval_failure",
    "test_failure",
    "codex_error",
    "doc_drift",
    "provider_gate_violation",
    "skill_route_miss",
    "security_review",
    "manual",
}
SEVERITIES = {"low", "medium", "high", "blocker"}
PROJECT_SCOPES = {"global", "research_x", "stack_specific"}
CHANGE_TYPES = {
    "skill_update",
    "agents_update",
    "docs_update",
    "eval_case",
    "code_change",
    "security_review",
    "provider_policy_update",
    "manifest_update",
    "no_change",
}
PRIVACY_LEVELS = {"public", "project_private", "sensitive_redacted"}
STATUSES = {
    "new",
    "triaged",
    "candidate_generated",
    "rejected",
    "accepted_for_pr",
    "merged",
}
TRIAGE_CATEGORIES = {
    "security_budget_blocker",
    "evidence_invariant_violation",
    "doc_governance_issue",
    "skill_route_issue",
    "evaluation_gap",
    "workflow_ergonomics",
    "no_change",
}
DISPOSITIONS = {"candidate_report", "rejected"}
RESULT_STATUSES = {"not_run", "passed", "failed", "blocked", "not_applicable"}
HUMAN_DECISIONS = {"pending", "accepted", "rejected", "deferred", "not_required"}

SECURITY_KEYWORDS = {
    "api key",
    "apikey",
    "token",
    "cookie",
    "credential",
    "secret",
    "provider",
    "quota",
    "network",
    "connector",
    "slack",
    "notion",
    "gmail",
    "serper",
    "brave",
    "openai",
    "gemini",
    "jina",
    "voyage",
    "cohere",
    "mistral",
    "webshare",
}
EVIDENCE_KEYWORDS = {
    "citation",
    "source bundle",
    "source-bundle",
    "evidence",
    "summary as evidence",
    "label as evidence",
    "context chunk",
}
DOC_KEYWORDS = {"agents.md", "project.md", "readme", "docs/", "doc drift", "source of truth"}
SKILL_KEYWORDS = {"skill", "trigger", "implicit invocation", "frontmatter", "route miss"}


@dataclass(frozen=True)
class ImprovementSignal:
    signal_id: str
    created_at: str
    source_type: str
    source_ref: str
    severity: str
    project_scope: str
    symptom: str
    root_cause_hypothesis: str
    affected_artifacts: tuple[str, ...]
    proposed_change_type: str
    evidence: tuple[dict[str, Any], ...]
    privacy_level: str
    status: str = "new"
    tags: tuple[str, ...] = field(default_factory=tuple)
    fault_step: str = ""
    responsible_artifact: str = ""
    candidate_diff_ref: str = ""
    replay_result: dict[str, Any] = field(default_factory=lambda: {"status": "not_run"})
    qualifier_result: dict[str, Any] = field(default_factory=lambda: {"status": "not_run"})
    human_decision: str = "pending"

    def as_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["affected_artifacts"] = list(self.affected_artifacts)
        data["evidence"] = list(self.evidence)
        data["tags"] = list(self.tags)
        return data


@dataclass(frozen=True)
class TriageDecision:
    signal_id: str
    triage_category: str
    priority: str
    proposed_change_type: str
    recommended_artifacts: tuple[str, ...]
    human_review_required: bool
    provider_freeze_touched: bool
    security_review_required: bool
    disposition: str
    fault_step: str
    responsible_artifact: str
    candidate_diff_ref: str
    replay_result: dict[str, Any]
    qualifier_result: dict[str, Any]
    human_decision: str
    rationale: str
    gates: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["recommended_artifacts"] = list(self.recommended_artifacts)
        data["gates"] = list(self.gates)
        return data


def capture_signal(
    *,
    source_type: str,
    source_ref: str,
    symptom: str,
    root_cause_hypothesis: str = "",
    severity: str = "medium",
    project_scope: str = "research_x",
    proposed_change_type: str = "no_change",
    privacy_level: str = "project_private",
    status: str = "new",
    affected_artifacts: tuple[str, ...] = (),
    evidence: tuple[dict[str, Any], ...] = (),
    tags: tuple[str, ...] = (),
    fault_step: str = "",
    responsible_artifact: str = "",
    candidate_diff_ref: str = "",
    replay_result: dict[str, Any] | None = None,
    qualifier_result: dict[str, Any] | None = None,
    human_decision: str = "pending",
    signal_id: str | None = None,
    created_at: str | None = None,
) -> ImprovementSignal:
    resolved_created_at = created_at or datetime.now(UTC).isoformat()
    resolved_signal_id = signal_id or _signal_id(
        resolved_created_at,
        source_type,
        source_ref,
        symptom,
    )
    return ImprovementSignal(
        signal_id=resolved_signal_id,
        created_at=resolved_created_at,
        source_type=source_type,
        source_ref=source_ref,
        severity=severity,
        project_scope=project_scope,
        symptom=symptom,
        root_cause_hypothesis=root_cause_hypothesis,
        affected_artifacts=tuple(affected_artifacts),
        proposed_change_type=proposed_change_type,
        evidence=tuple(evidence),
        privacy_level=privacy_level,
        status=status,
        tags=tuple(tags),
        fault_step=fault_step,
        responsible_artifact=responsible_artifact,
        candidate_diff_ref=candidate_diff_ref,
        replay_result=_result_or_default(replay_result),
        qualifier_result=_result_or_default(qualifier_result),
        human_decision=human_decision,
    )


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path}:{line_number}: invalid JSONL: {exc}") from exc
        if not isinstance(value, dict):
            raise ValueError(f"{path}:{line_number}: JSONL row must be an object")
        rows.append(value)
    return rows


def write_jsonl(path: Path, rows: list[dict[str, Any]], *, append: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    mode = "a" if append else "w"
    with path.open(mode, encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def write_triage_jsonl(path: Path, decisions: list[TriageDecision]) -> None:
    write_jsonl(path, [decision.as_dict() for decision in decisions])


def read_triage_jsonl(path: Path) -> list[TriageDecision]:
    return [
        TriageDecision(
            signal_id=str(row["signal_id"]),
            triage_category=str(row["triage_category"]),
            priority=str(row["priority"]),
            proposed_change_type=str(row["proposed_change_type"]),
            recommended_artifacts=tuple(str(item) for item in row["recommended_artifacts"]),
            human_review_required=bool(row["human_review_required"]),
            provider_freeze_touched=bool(row["provider_freeze_touched"]),
            security_review_required=bool(row["security_review_required"]),
            disposition=str(row["disposition"]),
            fault_step=str(row.get("fault_step", "")),
            responsible_artifact=str(row.get("responsible_artifact", "")),
            candidate_diff_ref=str(row.get("candidate_diff_ref", "")),
            replay_result=_result_or_default(row.get("replay_result")),
            qualifier_result=_result_or_default(row.get("qualifier_result")),
            human_decision=str(row.get("human_decision", "pending")),
            rationale=str(row["rationale"]),
            gates=tuple(str(item) for item in row["gates"]),
        )
        for row in read_jsonl(path)
    ]


def validate_signal(signal: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    required = {
        "signal_id",
        "created_at",
        "source_type",
        "source_ref",
        "severity",
        "project_scope",
        "symptom",
        "root_cause_hypothesis",
        "affected_artifacts",
        "proposed_change_type",
        "evidence",
        "privacy_level",
        "status",
    }
    missing = sorted(required - set(signal))
    if missing:
        return [f"{signal.get('signal_id', '<unknown>')}: missing fields: {', '.join(missing)}"]
    prefix = str(signal["signal_id"])
    if not prefix.startswith("sig_"):
        errors.append(f"{prefix}: signal_id must start with sig_")
    if signal["source_type"] not in SOURCE_TYPES:
        errors.append(f"{prefix}: invalid source_type {signal['source_type']!r}")
    if signal["severity"] not in SEVERITIES:
        errors.append(f"{prefix}: invalid severity {signal['severity']!r}")
    if signal["project_scope"] not in PROJECT_SCOPES:
        errors.append(f"{prefix}: invalid project_scope {signal['project_scope']!r}")
    if signal["proposed_change_type"] not in CHANGE_TYPES:
        errors.append(
            f"{prefix}: invalid proposed_change_type {signal['proposed_change_type']!r}"
        )
    if signal["privacy_level"] not in PRIVACY_LEVELS:
        errors.append(f"{prefix}: invalid privacy_level {signal['privacy_level']!r}")
    if signal["status"] not in STATUSES:
        errors.append(f"{prefix}: invalid status {signal['status']!r}")
    if not str(signal["source_ref"]).strip():
        errors.append(f"{prefix}: source_ref is required")
    if not str(signal["symptom"]).strip():
        errors.append(f"{prefix}: symptom is required")
    if not isinstance(signal["affected_artifacts"], list):
        errors.append(f"{prefix}: affected_artifacts must be a list")
    if not isinstance(signal["evidence"], list):
        errors.append(f"{prefix}: evidence must be a list")
    else:
        for index, item in enumerate(signal["evidence"], start=1):
            if not isinstance(item, dict):
                errors.append(f"{prefix}: evidence[{index}] must be an object")
                continue
            if not item.get("kind") or not item.get("ref"):
                errors.append(f"{prefix}: evidence[{index}] requires kind and ref")
    if "tags" in signal and not isinstance(signal["tags"], list):
        errors.append(f"{prefix}: tags must be a list")
    for key in ("fault_step", "responsible_artifact", "candidate_diff_ref"):
        if key in signal and not isinstance(signal[key], str):
            errors.append(f"{prefix}: {key} must be a string")
    _validate_result_object(errors, prefix, signal, "replay_result")
    _validate_result_object(errors, prefix, signal, "qualifier_result")
    if "human_decision" in signal and signal["human_decision"] not in HUMAN_DECISIONS:
        errors.append(f"{prefix}: invalid human_decision {signal['human_decision']!r}")
    return errors


def _validate_result_object(
    errors: list[str],
    prefix: str,
    record: dict[str, Any],
    key: str,
) -> None:
    if key not in record:
        return
    value = record[key]
    if not isinstance(value, dict):
        errors.append(f"{prefix}: {key} must be an object")
        return
    status = value.get("status")
    if status not in RESULT_STATUSES:
        errors.append(f"{prefix}: invalid {key}.status {status!r}")
    for item_key, item_value in value.items():
        if not isinstance(item_key, str):
            errors.append(f"{prefix}: {key} keys must be strings")
        if item_value is not None and not isinstance(
            item_value,
            str | int | float | bool | list | dict,
        ):
            errors.append(f"{prefix}: {key}.{item_key} has unsupported value type")


def validate_triage_record(record: dict[str, Any]) -> list[str]:
    errors = []
    required = {
        "signal_id",
        "triage_category",
        "priority",
        "proposed_change_type",
        "recommended_artifacts",
        "human_review_required",
        "provider_freeze_touched",
        "security_review_required",
        "disposition",
        "rationale",
        "gates",
    }
    missing = sorted(required - set(record))
    if missing:
        return [f"{record.get('signal_id', '<unknown>')}: missing fields: {', '.join(missing)}"]
    signal_id = str(record["signal_id"])
    if record["triage_category"] not in TRIAGE_CATEGORIES:
        errors.append(f"{signal_id}: invalid triage_category {record['triage_category']!r}")
    if record["priority"] not in SEVERITIES:
        errors.append(f"{signal_id}: invalid priority {record['priority']!r}")
    if record["proposed_change_type"] not in CHANGE_TYPES:
        errors.append(
            f"{signal_id}: invalid proposed_change_type {record['proposed_change_type']!r}"
        )
    if record["disposition"] not in DISPOSITIONS:
        errors.append(f"{signal_id}: invalid disposition {record['disposition']!r}")
    for key in ("recommended_artifacts", "gates"):
        if not isinstance(record[key], list):
            errors.append(f"{signal_id}: {key} must be a list")
    for key in (
        "human_review_required",
        "provider_freeze_touched",
        "security_review_required",
    ):
        if not isinstance(record[key], bool):
            errors.append(f"{signal_id}: {key} must be a boolean")
    for key in ("fault_step", "responsible_artifact", "candidate_diff_ref"):
        if key in record and not isinstance(record[key], str):
            errors.append(f"{signal_id}: {key} must be a string")
    _validate_result_object(errors, signal_id, record, "replay_result")
    _validate_result_object(errors, signal_id, record, "qualifier_result")
    if "human_decision" in record and record["human_decision"] not in HUMAN_DECISIONS:
        errors.append(f"{signal_id}: invalid human_decision {record['human_decision']!r}")
    return errors


def triage_signals(signals: list[dict[str, Any]]) -> list[TriageDecision]:
    decisions = []
    for signal in signals:
        decisions.append(_triage_signal(signal))
    return decisions


def format_triage_report(decisions: list[TriageDecision]) -> str:
    lines = [
        "# ImprovementSignal Triage Report",
        "",
        "This report is proposal-only. It does not apply patches, edit durable guidance, "
        "call providers, or enable third-party tools.",
        "",
        "| Signal | Category | Priority | Disposition | Human review | Security | "
        "Provider freeze | Qualifier |",
        "|---|---|---|---|---:|---:|---:|---|",
    ]
    for decision in decisions:
        human = str(decision.human_review_required).lower()
        security = str(decision.security_review_required).lower()
        provider = str(decision.provider_freeze_touched).lower()
        qualifier = _result_status(decision.qualifier_result)
        lines.append(
            f"| {decision.signal_id} | {decision.triage_category} | {decision.priority} | "
            f"{decision.disposition} | {human} | {security} | {provider} | {qualifier} |"
        )
    lines.extend(["", "## Details", ""])
    for decision in decisions:
        lines.extend(
            [
                f"### {decision.signal_id}",
                "",
                f"- Category: `{decision.triage_category}`",
                f"- Priority: `{decision.priority}`",
                f"- Proposed change type: `{decision.proposed_change_type}`",
                f"- Disposition: `{decision.disposition}`",
                f"- Human review required: `{str(decision.human_review_required).lower()}`",
                f"- Security review required: `{str(decision.security_review_required).lower()}`",
                f"- Provider freeze touched: `{str(decision.provider_freeze_touched).lower()}`",
                f"- Recommended artifacts: `{', '.join(decision.recommended_artifacts) or 'none'}`",
                f"- Fault step: `{decision.fault_step or 'none'}`",
                f"- Responsible artifact: `{decision.responsible_artifact or 'none'}`",
                f"- Candidate diff ref: `{decision.candidate_diff_ref or 'none'}`",
                f"- Replay result: `{_format_result_inline(decision.replay_result)}`",
                f"- Qualifier result: `{_format_result_inline(decision.qualifier_result)}`",
                f"- Human decision: `{decision.human_decision}`",
                f"- Gates: `{', '.join(decision.gates)}`",
                "",
                decision.rationale,
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def create_candidate_reports(
    decisions: list[TriageDecision],
    out_dir: Path,
) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for decision in decisions:
        if decision.disposition != "candidate_report":
            continue
        path = out_dir / f"{decision.signal_id}.md"
        write_text(path, _candidate_report(decision))
        paths.append(path)
    return paths


def validate_candidate_dir(path: Path) -> list[str]:
    if not path.exists():
        return [f"candidate dir missing: {path}"]
    errors = []
    for item in sorted(path.glob("*.md")):
        text = item.read_text(encoding="utf-8")
        required_phrases = [
            "Proposal Only",
            "Do not auto-apply",
            "Fault Localization",
            "Replay",
            "Qualifier",
            "Validation Gates",
            "Human Review",
        ]
        for phrase in required_phrases:
            if phrase not in text:
                errors.append(f"{item}: missing {phrase!r}")
    return errors


def _triage_signal(signal: dict[str, Any]) -> TriageDecision:
    text = _signal_text(signal)
    category = _category(signal, text)
    change_type = _change_type(signal, category)
    provider_freeze_touched = (
        category == "security_budget_blocker"
        and _contains_any(text, {"provider", "quota", "openai", "gemini", "serper", "brave"})
    )
    security_review_required = category == "security_budget_blocker" or _contains_any(
        text,
        {"token", "cookie", "credential", "secret", "connector", "proxy", "webshare"},
    )
    human_review_required = change_type in {
        "agents_update",
        "skill_update",
        "docs_update",
        "provider_policy_update",
        "security_review",
        "manifest_update",
    }
    disposition = "rejected" if category == "no_change" else "candidate_report"
    gates = _gates(category, change_type, security_review_required, provider_freeze_touched)
    artifacts = _recommended_artifacts(signal, category, change_type)
    fault_step = _fault_step(signal, category)
    responsible_artifact = _responsible_artifact(signal, artifacts)
    replay_result = _replay_result(signal, category)
    qualifier_result = _qualifier_result(signal, disposition, gates)
    return TriageDecision(
        signal_id=str(signal["signal_id"]),
        triage_category=category,
        priority=str(signal["severity"]),
        proposed_change_type=change_type,
        recommended_artifacts=artifacts,
        human_review_required=human_review_required,
        provider_freeze_touched=provider_freeze_touched,
        security_review_required=security_review_required,
        disposition=disposition,
        fault_step=fault_step,
        responsible_artifact=responsible_artifact,
        candidate_diff_ref=str(signal.get("candidate_diff_ref", "")).strip(),
        replay_result=replay_result,
        qualifier_result=qualifier_result,
        human_decision=_human_decision(signal),
        rationale=_rationale(signal, category),
        gates=gates,
    )


def _category(signal: dict[str, Any], text: str) -> str:
    source_type = str(signal["source_type"])
    change_type = str(signal["proposed_change_type"])
    if source_type == "provider_gate_violation" or _contains_any(text, SECURITY_KEYWORDS):
        return "security_budget_blocker"
    if _contains_any(text, EVIDENCE_KEYWORDS):
        return "evidence_invariant_violation"
    if source_type == "doc_drift" or change_type in {"agents_update", "docs_update"}:
        return "doc_governance_issue"
    if source_type == "skill_route_miss" or change_type == "skill_update":
        return "skill_route_issue"
    if source_type in {"eval_failure", "test_failure"} or change_type == "eval_case":
        return "evaluation_gap"
    if source_type in {"user_feedback", "codex_error", "workflow_trace", "manual"}:
        if change_type == "no_change":
            return "no_change"
        return "workflow_ergonomics"
    return "no_change"


def _change_type(signal: dict[str, Any], category: str) -> str:
    proposed = str(signal["proposed_change_type"])
    if proposed != "no_change":
        return proposed
    defaults = {
        "security_budget_blocker": "security_review",
        "evidence_invariant_violation": "eval_case",
        "doc_governance_issue": "docs_update",
        "skill_route_issue": "skill_update",
        "evaluation_gap": "eval_case",
        "workflow_ergonomics": "code_change",
        "no_change": "no_change",
    }
    return defaults[category]


def _recommended_artifacts(
    signal: dict[str, Any],
    category: str,
    change_type: str,
) -> tuple[str, ...]:
    affected = tuple(str(item) for item in signal.get("affected_artifacts", []))
    if affected:
        return affected
    if change_type == "agents_update":
        return ("AGENTS.md",)
    if change_type == "skill_update":
        return (".agents/skills", "tests/test_skill_manifest.py")
    if category == "doc_governance_issue":
        return ("docs/memory-pipeline-v2.md", "PROJECT.md")
    if category == "security_budget_blocker":
        return (".codex/skill_manifest.lock", "docs/pipeline.md")
    if category == "evidence_invariant_violation":
        return ("docs/memory-pipeline-v2.md", "tests/test_memory.py")
    if category == "evaluation_gap":
        return ("tests",)
    if category == "workflow_ergonomics":
        return ("src/research_x", "tests")
    return ()


def _gates(
    category: str,
    change_type: str,
    security_review_required: bool,
    provider_freeze_touched: bool,
) -> tuple[str, ...]:
    gates = ["schema_validation", "proposal_only_no_auto_apply"]
    if change_type in {"agents_update", "docs_update", "skill_update"}:
        gates.append("human_review_before_durable_guidance_change")
    if category in {"skill_route_issue", "doc_governance_issue"}:
        gates.append("route_or_doc_governance_regression_case")
    if category == "evidence_invariant_violation":
        gates.append("source_bundle_or_citation_regression_case")
    if category == "evaluation_gap":
        gates.append("failing_case_reproduced_before_fix")
    if security_review_required:
        gates.append("security_review")
    if provider_freeze_touched:
        gates.append("no_provider_calls")
    return tuple(gates)


def _rationale(signal: dict[str, Any], category: str) -> str:
    symptom = str(signal["symptom"]).strip()
    root = str(signal.get("root_cause_hypothesis", "")).strip()
    reason = f"Signal was classified as `{category}` from symptom: {symptom}"
    if root:
        reason += f" Root-cause hypothesis: {root}"
    return reason


def _fault_step(signal: dict[str, Any], category: str) -> str:
    explicit = _optional_text(signal.get("fault_step"))
    if explicit:
        return explicit
    defaults = {
        "security_budget_blocker": "verify provider/security gate before any external action",
        "evidence_invariant_violation": "restore source bundle and citation boundary",
        "doc_governance_issue": "locate the durable source of truth and drift point",
        "skill_route_issue": "compare request wording with Skill trigger and manifest routing",
        "evaluation_gap": "reproduce the failing local test or eval case",
        "workflow_ergonomics": "identify the first local workflow step that failed",
        "no_change": "no actionable fault step",
    }
    return defaults[category]


def _responsible_artifact(signal: dict[str, Any], artifacts: tuple[str, ...]) -> str:
    explicit = _optional_text(signal.get("responsible_artifact"))
    if explicit:
        return explicit
    return artifacts[0] if artifacts else ""


def _replay_result(signal: dict[str, Any], category: str) -> dict[str, Any]:
    explicit = _result_or_default(signal.get("replay_result"))
    if _result_status(explicit) != "not_run":
        return explicit
    if category == "no_change":
        return {
            "status": "not_applicable",
            "reason": "signal was rejected as no_change",
        }
    if category == "evaluation_gap":
        return {
            "status": "not_run",
            "reason": "failing case must be reproduced before implementation",
        }
    return {
        "status": "not_run",
        "reason": "no replay fixture has been run for this candidate yet",
    }


def _qualifier_result(
    signal: dict[str, Any],
    disposition: str,
    gates: tuple[str, ...],
) -> dict[str, Any]:
    explicit = _result_or_default(signal.get("qualifier_result"))
    if _result_status(explicit) != "not_run":
        return explicit
    if disposition == "rejected":
        return {
            "status": "not_applicable",
            "reason": "no candidate is promoted from this signal",
        }
    return {
        "status": "not_run",
        "required_gates": list(gates),
    }


def _result_or_default(value: object | None) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {"status": "not_run"}
    result = dict(value)
    if "status" not in result:
        result["status"] = "not_run"
    return result


def _result_status(value: dict[str, Any]) -> str:
    return str(value.get("status", "not_run"))


def _human_decision(signal: dict[str, Any]) -> str:
    decision = str(signal.get("human_decision", "pending"))
    if decision in HUMAN_DECISIONS:
        return decision
    return "pending"


def _optional_text(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def _format_result_inline(result: dict[str, Any]) -> str:
    status = _result_status(result)
    ref = _optional_text(result.get("ref"))
    if ref:
        return f"status={status}, ref={ref}"
    return f"status={status}"


def _format_result_block(result: dict[str, Any]) -> str:
    lines = [f"- Status: `{_result_status(result)}`"]
    for key in sorted(result):
        if key == "status":
            continue
        value = result[key]
        if isinstance(value, list | dict):
            formatted = json.dumps(value, ensure_ascii=False, sort_keys=True)
        else:
            formatted = str(value)
        lines.append(f"- {key.replace('_', ' ').title()}: `{formatted or 'none'}`")
    return "\n".join(lines)


def _candidate_report(decision: TriageDecision) -> str:
    replay_lines = _format_result_block(decision.replay_result)
    qualifier_lines = _format_result_block(decision.qualifier_result)
    return (
        f"# Improvement Candidate: {decision.signal_id}\n\n"
        "## Proposal Only\n\n"
        "Do not auto-apply this report. It is a review artifact for a future scoped change.\n\n"
        "## Classification\n\n"
        f"- Category: `{decision.triage_category}`\n"
        f"- Priority: `{decision.priority}`\n"
        f"- Proposed change type: `{decision.proposed_change_type}`\n"
        f"- Recommended artifacts: `{', '.join(decision.recommended_artifacts) or 'none'}`\n\n"
        "## Fault Localization\n\n"
        f"- First actionable fault step: `{decision.fault_step or 'none'}`\n"
        f"- Responsible artifact: `{decision.responsible_artifact or 'none'}`\n"
        f"- Candidate diff reference: `{decision.candidate_diff_ref or 'none'}`\n\n"
        "## Rationale\n\n"
        f"{decision.rationale}\n\n"
        "## Replay\n\n"
        f"{replay_lines}\n\n"
        "## Qualifier\n\n"
        f"{qualifier_lines}\n\n"
        "## Validation Gates\n\n"
        + "\n".join(f"- `{gate}`" for gate in decision.gates)
        + "\n\n"
        "## Human Review\n\n"
        f"- Required: `{str(decision.human_review_required).lower()}`\n"
        f"- Security review required: `{str(decision.security_review_required).lower()}`\n"
        f"- Provider freeze touched: `{str(decision.provider_freeze_touched).lower()}`\n"
        f"- Decision: `{decision.human_decision}`\n"
    )


def _signal_text(signal: dict[str, Any]) -> str:
    parts = [
        str(signal.get("source_type", "")),
        str(signal.get("source_ref", "")),
        str(signal.get("symptom", "")),
        str(signal.get("root_cause_hypothesis", "")),
        str(signal.get("proposed_change_type", "")),
        " ".join(str(item) for item in signal.get("affected_artifacts", [])),
        " ".join(str(item) for item in signal.get("tags", [])),
    ]
    return " ".join(parts).casefold()


def _contains_any(text: str, keywords: set[str]) -> bool:
    return any(keyword.casefold() in text for keyword in keywords)


def _signal_id(created_at: str, source_type: str, source_ref: str, symptom: str) -> str:
    digest = hashlib.sha256(
        "\n".join((created_at, source_type, source_ref, symptom)).encode("utf-8")
    ).hexdigest()[:16]
    return f"sig_{digest}"
