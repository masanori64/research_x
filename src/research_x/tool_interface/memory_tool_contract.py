from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any

from research_x.memory.answer import MemoryAnswer
from research_x.memory.artifact_roles import (
    artifact_role_allows_answer_support,
    normalize_artifact_role,
)
from research_x.memory.authority_levels import (
    AuthorityLevel,
    authority_at_least,
    normalize_authority_level,
)
from research_x.memory.context import CitationAnnotation
from research_x.memory.document_hashes import memory_document_source_hash, text_hash
from research_x.memory.evidence_invariants import (
    citation_block_reasons,
    citation_is_citation_ready,
    citation_is_not_evidence,
    citation_is_stale,
    citation_marks_conflict,
)
from research_x.memory.output_modes import (
    OutputMode,
    normalize_output_mode,
    output_mode_accepts_authority,
)
from research_x.memory.schema import ensure_memory_schema
from research_x.memory.source_identity import (
    source_bundle_id as canonical_source_bundle_id,
)
from research_x.memory.source_identity import (
    source_restore_id as canonical_source_restore_id,
)
from research_x.memory.workflow import MemoryWorkflow
from research_x.tool_interface.codex_bridge import bridge_trace_contract

CONTRACT_VERSION = "research-x-ai-tool-v1"
CONTRACT_VERSION_V2 = "research-x-ai-tool-v2"
LOCAL_X_DB = "local_x_db"
TOOL_OUTPUT_STATUSES = {
    "answer",
    "abstain",
    "needs_review",
    "source_not_restored",
    "citation_missing",
    "provider_gated",
    "blocked",
}
EVIDENCE_LEVELS = {
    "raw",
    "candidate",
    "source_bundle",
    "source_restore",
    "context_chunk",
    "citation_ready",
}
TOOL_OUTPUT_V2_STATUSES = {
    "ok",
    "answer",
    "abstain",
    "needs_review",
    "source_not_restored",
    "citation_missing",
    "claim_support_missing",
    "hypothesis_only",
    "provider_gated",
    "blocked",
    "working_note_written",
    "evidence_package",
}
LEGACY_NON_EVIDENCE_POLICY_MARKERS = {
    "not_answer_support",
    "not_citation",
    "not_evidence",
}
LEGACY_RESTORE_COMPAT_KEYS = (
    "artifact_kind",
    "artifact_type",
    "preview_kind",
)


@dataclass(frozen=True)
class ToolCitation:
    citation_id: str
    chunk_id: str
    source_kind: str
    source_id: str
    source_url: str | None
    title: str
    evidence_status: str
    citation_ready: bool
    restore: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ToolOutput:
    contract_version: str
    tool_kind: str
    query: str
    status: str
    evidence_level: str
    answer_text: str | None
    citations: tuple[ToolCitation, ...]
    trace: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["citations"] = [citation.as_dict() for citation in self.citations]
        return data


@dataclass(frozen=True)
class ToolOutputItemV2:
    item_id: str
    subject_kind: str
    subject_id: str
    artifact_role: str
    authority_level: str
    source_refs: tuple[str, ...]
    source_status: str
    projection_id: str | None
    score: float | None
    why_relevant: str | None
    risk_flags: tuple[str, ...]
    metadata: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["source_refs"] = list(self.source_refs)
        data["risk_flags"] = list(self.risk_flags)
        return data


@dataclass(frozen=True)
class ToolOutputV2:
    contract_version: str
    tool_kind: str
    query: str
    output_mode: str
    status: str
    answer_text: str | None
    items: tuple[ToolOutputItemV2, ...]
    citations: tuple[ToolCitation, ...]
    claim_support: dict[str, Any] | None
    working_note_id: str | None
    trace: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["items"] = [item.as_dict() for item in self.items]
        data["citations"] = [citation.as_dict() for citation in self.citations]
        return data


def workflow_tool_output(workflow: MemoryWorkflow) -> ToolOutput:
    """Build the raw stable tool output contract for a memory workflow."""

    status = _workflow_status(workflow)
    citations = _tool_citations(workflow)
    evidence_level = _workflow_evidence_level(workflow, status=status, citations=citations)
    answer_text = (
        workflow.answer.answer_text
        if workflow.answer is not None and status != "provider_gated"
        else None
    )
    return ToolOutput(
        contract_version=CONTRACT_VERSION,
        tool_kind="research_x.memory.workflow",
        query=workflow.query,
        status=status,
        evidence_level=evidence_level,
        answer_text=answer_text,
        citations=citations,
        trace=_workflow_trace(workflow, status=status),
    )


def workflow_tool_output_for_ai(
    workflow: MemoryWorkflow,
    *,
    db_path: str | Path | None = None,
) -> ToolOutput:
    """Build AI-facing output with DB-backed restoration required for answers."""

    output = workflow_tool_output(workflow)
    if db_path is None:
        if output.status == "answer":
            return _downgrade_missing_db_backed_validation(output)
        return _with_db_backed_validation_trace(
            output,
            status="not_required",
            errors=(),
        )
    errors = validate_tool_output_against_db(output, db_path)
    if not errors:
        return _with_db_backed_validation_trace(output, status="passed", errors=())
    if output.status != "answer":
        return _with_db_backed_validation_trace(output, status="failed", errors=errors)
    return _downgrade_unrestored_answer(output, errors=errors)


def workflow_tool_output_json(
    workflow: MemoryWorkflow,
    *,
    db_path: str | Path | None = None,
) -> str:
    return json.dumps(
        workflow_tool_output_for_ai(workflow, db_path=db_path).as_dict(),
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    )


def validate_tool_output(payload: dict[str, Any] | ToolOutput) -> list[str]:
    data = payload.as_dict() if isinstance(payload, ToolOutput) else payload
    errors: list[str] = []
    prefix = str(data.get("tool_kind") or "<unknown>")
    if data.get("contract_version") != CONTRACT_VERSION:
        errors.append(f"{prefix}: invalid contract_version {data.get('contract_version')!r}")
    if data.get("status") not in TOOL_OUTPUT_STATUSES:
        errors.append(f"{prefix}: invalid status {data.get('status')!r}")
    if data.get("evidence_level") not in EVIDENCE_LEVELS:
        errors.append(f"{prefix}: invalid evidence_level {data.get('evidence_level')!r}")
    citations = data.get("citations")
    if not isinstance(citations, list):
        errors.append(f"{prefix}: citations must be a list")
        citations = []
    if data.get("status") == "answer":
        if data.get("evidence_level") != "citation_ready":
            errors.append(f"{prefix}: answer status requires citation_ready evidence_level")
        if not str(data.get("answer_text") or "").strip():
            errors.append(f"{prefix}: answer status requires answer_text")
        if not citations:
            errors.append(f"{prefix}: answer status requires citations")
        not_restored = _payload_citations_with_restore_issues(citations)
        if not_restored:
            errors.append(
                f"{prefix}: answer status requires restored citations: "
                + ", ".join(not_restored)
            )
        not_evidence = _payload_citations_with_not_evidence_support(citations)
        if not_evidence:
            errors.append(
                f"{prefix}: answer status cannot cite not-evidence artifacts: "
                + ", ".join(not_evidence)
            )
    if data.get("status") == "provider_gated" and str(data.get("answer_text") or "").strip():
        errors.append(f"{prefix}: provider_gated status must not include completed answer_text")
    if data.get("status") != "answer" and data.get("evidence_level") == "citation_ready":
        errors.append(f"{prefix}: citation_ready evidence_level is only valid for answer status")
    if data.get("evidence_level") == "citation_ready":
        not_ready = [
            str(item.get("citation_id") or "<unknown>")
            for item in citations
            if not isinstance(item, dict) or item.get("citation_ready") is not True
        ]
        if not_ready:
            errors.append(
                f"{prefix}: citation_ready evidence has non-ready citations: "
                + ", ".join(not_ready)
            )
    trace = data.get("trace")
    if not isinstance(trace, dict):
        errors.append(f"{prefix}: trace must be an object")
    elif "codex_transcript_included" in trace:
        errors.append(f"{prefix}: trace must not include Codex transcript material")
    elif missing_trace_fields := sorted(
        {
            "answerability_status",
            "stop_reason",
            "provider_gate",
            "citation_quality",
            "citation_restoration",
            "pointer_offload_verification",
            "fixture_limitations",
        }
        - set(trace)
    ):
        errors.append(f"{prefix}: trace missing fields: " + ", ".join(missing_trace_fields))
    return errors


def validate_tool_output_v2(payload: dict[str, Any] | ToolOutputV2) -> list[str]:
    data = payload.as_dict() if isinstance(payload, ToolOutputV2) else payload
    errors: list[str] = []
    prefix = str(data.get("tool_kind") or "<unknown>")
    if data.get("contract_version") != CONTRACT_VERSION_V2:
        errors.append(f"{prefix}: invalid contract_version {data.get('contract_version')!r}")
    try:
        mode = normalize_output_mode(str(data.get("output_mode") or ""))
    except ValueError as exc:
        errors.append(f"{prefix}: {exc}")
        mode = None
    if data.get("status") not in TOOL_OUTPUT_V2_STATUSES:
        errors.append(f"{prefix}: invalid status {data.get('status')!r}")

    raw_items = data.get("items")
    if not isinstance(raw_items, list):
        errors.append(f"{prefix}: items must be a list")
        raw_items = []
    item_errors = _validate_tool_output_v2_items(prefix, raw_items)
    errors.extend(item_errors)

    citations = data.get("citations")
    if not isinstance(citations, list):
        errors.append(f"{prefix}: citations must be a list")
        citations = []
    trace = data.get("trace")
    if not isinstance(trace, dict):
        errors.append(f"{prefix}: trace must be an object")
        trace = {}

    if mode is not None:
        errors.extend(
            _validate_tool_output_v2_answer_text_for_mode(
                prefix,
                mode,
                data.get("answer_text"),
            )
        )
        if mode is not OutputMode.ANSWER:
            answer_assertion_items = [
                str(item.get("item_id") or "<unknown>")
                for item in raw_items
                if isinstance(item, dict)
                and item.get("authority_level") == "answer_assertion"
            ]
            if answer_assertion_items:
                errors.append(
                    f"{prefix}: {mode.value} items cannot be answer_assertion: "
                    + ", ".join(answer_assertion_items)
                )

    if mode is OutputMode.EXPLORE:
        if not raw_items:
            errors.append(f"{prefix}: explore output requires items")
    elif mode is OutputMode.COLLECT:
        if not raw_items:
            errors.append(f"{prefix}: collect output requires items")
        missing_source_status = [
            str(item.get("item_id") or "<unknown>")
            for item in raw_items
            if isinstance(item, dict) and not item.get("source_status")
        ]
        if missing_source_status:
            errors.append(
                f"{prefix}: collect items require source_status: "
                + ", ".join(missing_source_status)
            )
    elif mode is OutputMode.WORKING_NOTE:
        if not data.get("working_note_id"):
            errors.append(f"{prefix}: working_note output requires working_note_id")
        if not raw_items:
            errors.append(f"{prefix}: working_note output requires items")
    elif mode is OutputMode.SYNTHESIZE:
        if "unsupported_claims" not in trace or "unresolved_items" not in trace:
            errors.append(
                f"{prefix}: synthesize output requires unsupported_claims "
                "and unresolved_items trace"
            )
    elif mode is OutputMode.EVIDENCE_PACKAGE:
        if not raw_items:
            errors.append(f"{prefix}: evidence_package output requires items")
        weak_items = [
            str(item.get("item_id") or "<unknown>")
            for item in raw_items
            if isinstance(item, dict)
            and not _tool_output_v2_item_accepts_authority(
                OutputMode.EVIDENCE_PACKAGE,
                item,
            )
        ]
        if weak_items:
            errors.append(
                f"{prefix}: evidence_package items require evidence_view authority: "
                + ", ".join(weak_items)
            )
        if not citations and "citation_candidates" not in trace:
            errors.append(
                f"{prefix}: evidence_package requires citations or citation_candidates"
            )
    elif mode is OutputMode.ANSWER:
        if not citations:
            errors.append(f"{prefix}: answer output requires citations")
        citation_errors = _validate_tool_output_v2_answer_citations(prefix, citations)
        errors.extend(citation_errors)
        claim_support = data.get("claim_support")
        if not claim_support:
            errors.append(f"{prefix}: answer output requires claim_support")
        else:
            errors.extend(
                _validate_tool_output_v2_claim_support(
                    prefix,
                    claim_support,
                    citations,
                )
            )
        db_validation = trace.get("db_backed_validation")
        if not isinstance(db_validation, dict) or db_validation.get("status") != "passed":
            errors.append(f"{prefix}: answer output requires passed db_backed_validation")
        weak_roles = [
            str(item.get("item_id") or "<unknown>")
            for item in raw_items
            if isinstance(item, dict) and item.get("artifact_role") != "evidence_view"
        ]
        if weak_roles:
            errors.append(
                f"{prefix}: answer items require evidence_view artifact_role: "
                + ", ".join(weak_roles)
            )
        weak_items = [
            str(item.get("item_id") or "<unknown>")
            for item in raw_items
            if isinstance(item, dict)
            and not _tool_output_v2_item_accepts_authority(OutputMode.ANSWER, item)
        ]
        if weak_items:
            errors.append(
                f"{prefix}: answer items require answer_assertion authority: "
                + ", ".join(weak_items)
            )
    return errors


def _validate_tool_output_v2_answer_text_for_mode(
    prefix: str,
    mode: OutputMode,
    value: Any,
) -> list[str]:
    has_text = bool(str(value or "").strip())
    if mode is OutputMode.ANSWER:
        return [] if has_text else [f"{prefix}: answer output requires answer_text"]
    if has_text:
        return [f"{prefix}: {mode.value} output must not include answer_text"]
    return []


def _validate_tool_output_v2_answer_citations(
    prefix: str,
    citations: list[Any],
) -> list[str]:
    errors: list[str] = []
    not_ready = []
    missing_restore = []
    for citation in citations:
        if not isinstance(citation, dict):
            not_ready.append("<unknown>")
            continue
        citation_id = str(citation.get("citation_id") or "<unknown>")
        if (
            citation.get("citation_ready") is not True
            or citation.get("evidence_status") != "citation_ready"
        ):
            not_ready.append(citation_id)
        restore = citation.get("restore")
        if not isinstance(restore, dict) or not restore:
            missing_restore.append(citation_id)
    if not_ready:
        errors.append(
            f"{prefix}: answer citations must be citation_ready: "
            + ", ".join(not_ready)
        )
    if missing_restore:
        errors.append(
            f"{prefix}: answer citations require restore metadata: "
            + ", ".join(missing_restore)
        )
    return errors


def _validate_tool_output_v2_claim_support(
    prefix: str,
    claim_support: Any,
    citations: list[Any],
) -> list[str]:
    if not isinstance(claim_support, dict):
        return [f"{prefix}: answer claim_support must be an object"]
    errors: list[str] = []
    status = _support_status(claim_support)
    if status not in {"supported", "claim_supported", "passed"}:
        errors.append(f"{prefix}: answer claim_support status must be supported")
    claims = claim_support.get("claims")
    if not isinstance(claims, list) or not claims:
        errors.append(f"{prefix}: answer claim_support requires claims")
        return errors
    citation_ids = {
        str(citation.get("citation_id"))
        for citation in citations
        if isinstance(citation, dict) and citation.get("citation_id")
    }
    unsupported_claims: list[str] = []
    missing_citations: list[str] = []
    unknown_citations: list[str] = []
    for index, claim in enumerate(claims):
        if not isinstance(claim, dict):
            unsupported_claims.append(f"claim[{index}]")
            continue
        claim_id = str(claim.get("claim_id") or f"claim[{index}]")
        claim_status = _support_status(claim) or status
        if claim_status not in {"supported", "claim_supported", "passed"}:
            unsupported_claims.append(claim_id)
        claim_citations = _claim_citation_ids(claim)
        if not claim_citations:
            missing_citations.append(claim_id)
            continue
        for citation_id in claim_citations:
            if citation_id not in citation_ids:
                unknown_citations.append(f"{claim_id}:{citation_id}")
    if unsupported_claims:
        errors.append(
            f"{prefix}: answer claims must be supported: "
            + ", ".join(unsupported_claims)
        )
    if missing_citations:
        errors.append(
            f"{prefix}: answer claims require citation_ids: "
            + ", ".join(missing_citations)
        )
    if unknown_citations:
        errors.append(
            f"{prefix}: answer claim_support references unknown citations: "
            + ", ".join(unknown_citations)
        )
    return errors


def _support_status(payload: dict[str, Any]) -> str:
    return str(
        payload.get("support_status")
        or payload.get("status")
        or ""
    ).strip().casefold()


def _claim_citation_ids(claim: dict[str, Any]) -> tuple[str, ...]:
    citation_ids = claim.get("citation_ids")
    if isinstance(citation_ids, list):
        return tuple(str(item) for item in citation_ids if str(item).strip())
    citation_id = claim.get("citation_id")
    if citation_id:
        return (str(citation_id),)
    return ()


def _validate_tool_output_v2_items(
    prefix: str,
    items: list[Any],
) -> list[str]:
    errors: list[str] = []
    for index, item in enumerate(items):
        label = f"item[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{prefix}: {label} must be an object")
            continue
        item_id = str(item.get("item_id") or label)
        try:
            normalize_artifact_role(str(item.get("artifact_role") or ""))
        except ValueError as exc:
            errors.append(f"{prefix}: {item_id}: {exc}")
        authority_level = str(item.get("authority_level") or "")
        if not authority_level:
            errors.append(f"{prefix}: {item_id}: authority_level is required")
        else:
            try:
                normalize_authority_level(authority_level)
            except ValueError as exc:
                errors.append(f"{prefix}: {item_id}: {exc}")
        source_refs = item.get("source_refs")
        if not isinstance(source_refs, list):
            errors.append(f"{prefix}: {item_id}: source_refs must be a list")
        risk_flags = item.get("risk_flags")
        if not isinstance(risk_flags, list):
            errors.append(f"{prefix}: {item_id}: risk_flags must be a list")
        metadata = item.get("metadata")
        if not isinstance(metadata, dict):
            errors.append(f"{prefix}: {item_id}: metadata must be an object")
    return errors


def _tool_output_v2_item_accepts_authority(
    output_mode: OutputMode,
    item: dict[str, Any],
) -> bool:
    try:
        return output_mode_accepts_authority(
            output_mode,
            str(item.get("authority_level") or ""),
        )
    except ValueError:
        return False


def validate_tool_output_against_db(
    payload: dict[str, Any] | ToolOutput,
    db_path: str | Path,
) -> list[str]:
    """Validate an AI-facing payload against stored local source lineage."""

    data = payload.as_dict() if isinstance(payload, ToolOutput) else payload
    errors = validate_tool_output(data)
    if data.get("status") != "answer":
        return errors
    citations = data.get("citations")
    if not isinstance(citations, list):
        return errors
    path = Path(db_path)
    prefix = str(data.get("tool_kind") or "<unknown>")
    with sqlite3.connect(path, timeout=60) as conn:
        conn.row_factory = sqlite3.Row
        ensure_memory_schema(conn)
        for item in citations:
            errors.extend(_validate_citation_against_db(conn, prefix=prefix, item=item))
    return errors


def _with_db_backed_validation_trace(
    output: ToolOutput,
    *,
    status: str,
    errors: tuple[str, ...] | list[str],
) -> ToolOutput:
    trace = dict(output.trace)
    trace["db_backed_restoration_validation"] = {
        "status": status,
        "required_for_answer": output.status == "answer",
        "error_count": len(errors),
        "errors": list(errors),
    }
    return replace(output, trace=trace)


def _downgrade_unrestored_answer(output: ToolOutput, *, errors: list[str]) -> ToolOutput:
    downgraded = _with_db_backed_validation_trace(output, status="failed", errors=errors)
    return replace(
        downgraded,
        status=_db_validation_failure_status(errors),
        evidence_level="context_chunk" if output.citations else "candidate",
        answer_text=None,
    )


def _downgrade_missing_db_backed_validation(output: ToolOutput) -> ToolOutput:
    errors = [
        (
            "research_x.memory.workflow: answer status requires DB-backed "
            "restoration validation"
        )
    ]
    downgraded = _with_db_backed_validation_trace(
        output,
        status="missing_db_path",
        errors=errors,
    )
    return replace(
        downgraded,
        status="source_not_restored",
        evidence_level="context_chunk" if output.citations else "candidate",
        answer_text=None,
    )


def _db_validation_failure_status(errors: list[str]) -> str:
    joined = " ".join(errors)
    if any(
        marker in joined
        for marker in (
            "context chunk",
            "chunk",
            "source document",
            "source_doc_hash",
            "source_bundle_id",
            "source_restore_id",
            "retrieval_text",
            "lineage",
            "restore",
        )
    ):
        return "source_not_restored"
    if "citation" in joined:
        return "citation_missing"
    return "needs_review"


def _workflow_status(workflow: MemoryWorkflow) -> str:
    if workflow.status == "error":
        if _provider_gate_required(workflow):
            return "provider_gated"
        return "blocked"
    if _provider_gate_required(workflow):
        return "provider_gated"
    if workflow.context_bundle is None or not workflow.context_bundle.context_chunks:
        return "source_not_restored"
    if workflow.answer is None:
        return "needs_review"
    answerability = _answerability_status(workflow.answer)
    if answerability == "unanswerable":
        return "abstain"
    if (
        not workflow.answer.citation_annotations
        and any(citation_is_not_evidence(citation) for citation in _raw_citations(workflow))
    ):
        return "needs_review"
    if not workflow.answer.citation_annotations:
        return "citation_missing"
    if workflow.answer.status == "ok" and all(
        _citation_ready(citation) for citation in workflow.answer.citation_annotations
    ):
        return "answer"
    if any(citation_is_not_evidence(citation) for citation in workflow.answer.citation_annotations):
        return "needs_review"
    if any(
        citation.metadata.get("marker_found") is False
        for citation in workflow.answer.citation_annotations
    ):
        return "citation_missing"
    return "needs_review"


def _workflow_evidence_level(
    workflow: MemoryWorkflow,
    *,
    status: str,
    citations: tuple[ToolCitation, ...],
) -> str:
    if status == "answer" and citations and all(citation.citation_ready for citation in citations):
        return "citation_ready"
    if workflow.context_bundle is not None and workflow.context_bundle.context_chunks:
        return "context_chunk"
    if workflow.context_bundle is not None and workflow.context_bundle.retrieved_hits:
        if any(
            isinstance(hit.get("evidence"), dict)
            for hit in workflow.context_bundle.retrieved_hits
        ):
            return "source_restore"
        return "candidate"
    if workflow.steps:
        return "candidate"
    return "raw"


def _workflow_trace(workflow: MemoryWorkflow, *, status: str) -> dict[str, Any]:
    stop_audit = workflow.metadata.get("stop_condition_audit") or {}
    route_plan = workflow.metadata.get("route_plan") or {}
    parameters = workflow.metadata.get("parameters") or {}
    answerability = (
        workflow.answer.structured.get("answerability")
        if workflow.answer is not None and isinstance(workflow.answer.structured, dict)
        else None
    )
    eval_warnings: list[str] = []
    if isinstance(stop_audit, dict) and stop_audit.get("searched_after_sufficient_evidence"):
        eval_warnings.append("searched_after_sufficient_evidence")
    if isinstance(answerability, dict) and answerability.get("status") == "conflicting":
        eval_warnings.append("conflicting_evidence")
    raw_citations = _raw_citations(workflow)
    stale_count = sum(1 for citation in raw_citations if citation_is_stale(citation))
    conflict_count = sum(1 for citation in raw_citations if citation_marks_conflict(citation))
    not_evidence_count = sum(
        1 for citation in raw_citations if citation_is_not_evidence(citation)
    )
    if stale_count:
        eval_warnings.append("stale_evidence")
    if not_evidence_count:
        eval_warnings.append("not_evidence_citation")
    citation_restoration = _citation_restoration_trace(
        workflow,
        raw_citations=raw_citations,
    )
    pointer_offload = _pointer_offload_verification(raw_citations)
    fixture_limitations = _fixture_limitations(parameters, workflow=workflow)
    return {
        "route": workflow.route,
        "workflow_id": workflow.workflow_id,
        "stop_reason": workflow.stop_reason,
        "skip_reason": None if workflow.stop_reason == "enough_evidence" else workflow.stop_reason,
        "answerability_status": (
            answerability.get("status") if isinstance(answerability, dict) else None
        ),
        "citation_quality": {
            "citation_count": len(raw_citations),
            "citation_ready_count": sum(
                1 for citation in raw_citations if _citation_ready(citation)
            ),
            "stale_evidence_count": stale_count,
            "conflict_evidence_count": conflict_count,
            "not_evidence_count": not_evidence_count,
            "blockers": {
                citation.citation_id: list(citation_block_reasons(citation))
                for citation in raw_citations
                if citation_block_reasons(citation)
            },
        },
        "citation_restoration": citation_restoration,
        "pointer_offload_verification": pointer_offload,
        "non_evidence_artifacts": _non_evidence_artifact_trace(raw_citations),
        "provider_gate": {
            "required": status == "provider_gated",
            "provider_policy_default": True,
            "provider_like_parameters": _provider_like_parameters(parameters),
        },
        "fixture_limitations": fixture_limitations,
        "retrieval_filter_audit": _retrieval_filter_audit(workflow, parameters=parameters),
        "budget": {
            "max_steps": parameters.get("max_steps"),
            "step_count": len(workflow.steps),
            "stop_condition_audit": stop_audit,
        },
        "eval_warnings": eval_warnings,
        "route_plan": route_plan,
        "codex_bridge": bridge_trace_contract(),
    }


def _retrieval_filter_audit(
    workflow: MemoryWorkflow,
    *,
    parameters: dict[str, Any],
) -> dict[str, Any]:
    explanations: list[dict[str, Any]] = []
    taxonomy_counts: dict[str, dict[str, int]] = {
        "source_kind": {},
        "ownership_kind": {},
    }
    if workflow.context_bundle is not None:
        for hit in workflow.context_bundle.retrieved_hits:
            metadata = hit.get("metadata") if isinstance(hit, dict) else None
            if not isinstance(metadata, dict):
                continue
            explanation = metadata.get("embedding_filter_explanation")
            if isinstance(explanation, dict):
                explanations.append(explanation)
            taxonomy = metadata.get("embedding_input_taxonomy")
            if isinstance(taxonomy, dict):
                for key in ("source_kind", "ownership_kind"):
                    value = str(taxonomy.get(key) or "")
                    if value:
                        bucket = taxonomy_counts[key]
                        bucket[value] = bucket.get(value, 0) + 1
    first = explanations[0] if explanations else {}
    return {
        "intent": first.get("intent") or parameters.get("intent"),
        "applied_filters": first.get("applied_filters")
        or {
            key: parameters.get(key)
            for key in (
                "author_id",
                "bookmark_owner_account_id",
                "source_kind",
                "ownership_kind",
                "content_role",
                "relation_role",
                "language",
                "modality_kind",
                "sensitivity_kind",
                "projection_profile",
                "filter_space_id",
                "require_projections",
            )
            if parameters.get(key) not in {None, False}
        },
        "excluded_candidate_counts": first.get("excluded_candidate_counts", {}),
        "candidate_counts_before_filter": first.get("candidate_counts_before_filter", {}),
        "candidate_counts_after_filter": first.get("candidate_counts_after_filter", {}),
        "candidate_counts_by_source_kind": taxonomy_counts["source_kind"],
        "candidate_counts_by_ownership_kind": taxonomy_counts["ownership_kind"],
        "warnings": first.get("warnings", []),
        "not_evidence": True,
    }


def _tool_citations(workflow: MemoryWorkflow) -> tuple[ToolCitation, ...]:
    raw_citations, context_run_id = _raw_citations_with_context_run_id(workflow)
    return tuple(
        _tool_citation(citation, context_run_id=context_run_id)
        for citation in raw_citations
    )


def _citation_restoration_trace(
    workflow: MemoryWorkflow,
    *,
    raw_citations: tuple[CitationAnnotation, ...],
) -> dict[str, Any]:
    _raw, context_run_id = _raw_citations_with_context_run_id(workflow)
    rows = []
    for citation in raw_citations:
        context_chunk_restored = bool(context_run_id and citation.chunk_id)
        source_restored = _citation_source_restored(citation)
        rows.append(
            {
                "citation_id": citation.citation_id,
                "context_run_id": context_run_id,
                "chunk_id": citation.chunk_id,
                "source_kind": citation.source_kind,
                "source_id": citation.source_id,
                "context_chunk_restored": context_chunk_restored,
                "source_restored": source_restored,
                "citation_ready": _citation_ready(citation),
                "block_reasons": list(citation_block_reasons(citation)),
            }
        )
    restored_count = sum(
        1
        for row in rows
        if row["context_chunk_restored"] and row["source_restored"] and row["citation_ready"]
    )
    return {
        "status": (
            "restored" if rows and restored_count == len(rows) else "not_restored"
        )
        if rows
        else "no_citations",
        "citation_count": len(rows),
        "restored_count": restored_count,
        "results": rows,
    }


def _pointer_offload_verification(
    raw_citations: tuple[CitationAnnotation, ...],
) -> dict[str, Any]:
    results = []
    for citation in raw_citations:
        metadata = citation.metadata
        pointer_status = metadata.get("pointer_status")
        restore_hint_status = metadata.get("restore_hint_status")
        preview_kind = metadata.get("preview_kind")
        artifact_kind = metadata.get("artifact_kind")
        artifact_role = metadata.get("artifact_role")
        authority_level = metadata.get("authority_level")
        legacy_pointer_kind = (
            metadata.get("legacy_metadata_compat") is True
            and artifact_kind in {"context_offload", "context_offload_preview", "pointer_map"}
        )
        has_pointer = bool(
            metadata.get("offload_pointer")
            or pointer_status
            or restore_hint_status
            or legacy_pointer_kind
        )
        if not has_pointer:
            continue
        status = str(pointer_status or restore_hint_status or "not_verified")
        blocked = status not in {"usable_pointer", "verified", "current"}
        if metadata.get("not_evidence") is True or metadata.get("answer_support_allowed") is False:
            blocked = True
        results.append(
            {
                "citation_id": citation.citation_id,
                "status": status,
                "blocked": blocked,
                "preview_kind": preview_kind,
                "artifact_kind": artifact_kind if legacy_pointer_kind else None,
                "artifact_role": artifact_role,
                "authority_level": authority_level,
                "not_evidence": metadata.get("not_evidence"),
            }
        )
    blocked_count = sum(1 for result in results if result["blocked"])
    return {
        "status": (
            "blocked" if blocked_count else "verified"
        )
        if results
        else "no_pointer_artifacts",
        "pointer_count": len(results),
        "blocked_count": blocked_count,
        "results": results,
    }


def _non_evidence_artifact_trace(
    raw_citations: tuple[CitationAnnotation, ...],
) -> dict[str, Any]:
    results = []
    for citation in raw_citations:
        metadata = citation.metadata
        if not citation_is_not_evidence(citation):
            continue
        results.append(
            {
                "citation_id": citation.citation_id,
                "blocked": True,
                "artifact_kind": metadata.get("artifact_kind"),
                "artifact_type": metadata.get("artifact_type"),
                "owner_plane": metadata.get("owner_plane"),
                "preview_kind": metadata.get("preview_kind"),
                "citation_policy": metadata.get("citation_policy"),
                "not_evidence": metadata.get("not_evidence"),
                "answer_support_allowed": metadata.get("answer_support_allowed"),
            }
        )
    return {
        "status": "blocked" if results else "no_not_evidence_artifacts",
        "artifact_count": len(results),
        "results": results,
    }


def _raw_citations(workflow: MemoryWorkflow) -> tuple[CitationAnnotation, ...]:
    raw_citations, _context_run_id = _raw_citations_with_context_run_id(workflow)
    return raw_citations


def _raw_citations_with_context_run_id(
    workflow: MemoryWorkflow,
) -> tuple[tuple[CitationAnnotation, ...], str | None]:
    if workflow.answer is not None:
        if (
            not workflow.answer.citation_annotations
            and workflow.context_bundle is not None
        ):
            return (
                workflow.context_bundle.citation_annotations,
                workflow.context_bundle.run_id,
            )
        return workflow.answer.citation_annotations, workflow.answer.context_run_id
    if workflow.context_bundle is not None:
        return workflow.context_bundle.citation_annotations, workflow.context_bundle.run_id
    return (), None


def _tool_citation(citation: CitationAnnotation, *, context_run_id: str | None) -> ToolCitation:
    return ToolCitation(
        citation_id=citation.citation_id,
        chunk_id=citation.chunk_id,
        source_kind=citation.source_kind,
        source_id=citation.source_id,
        source_url=citation.source_url,
        title=citation.title,
        evidence_status=citation.evidence_status,
        citation_ready=_citation_ready(citation),
        restore={
            "context_run_id": context_run_id,
            "chunk_id": citation.chunk_id,
            "source_kind": citation.source_kind,
            "source_id": citation.source_id,
            "source_url": citation.source_url,
            "field_path": citation.field_path,
            "context_chunk_restored": bool(context_run_id and citation.chunk_id),
            "source_restored": _citation_source_restored(citation),
            "citation_ready": _citation_ready(citation),
            "block_reasons": list(citation_block_reasons(citation)),
            "answer_id": citation.answer_id,
            "source_context_citation_id": citation.metadata.get(
                "source_context_citation_id"
            ),
            "document_id": citation.metadata.get("document_id"),
            "lineage_status": citation.metadata.get("lineage_status"),
            "source_doc_hash": citation.metadata.get("source_doc_hash"),
            "embedding_text_hash": citation.metadata.get("embedding_text_hash"),
            "retrieval_text_hash": citation.metadata.get("retrieval_text_hash"),
            "retrieval_text_profile": citation.metadata.get("retrieval_text_profile"),
            "retrieval_profile_kind": citation.metadata.get("retrieval_profile_kind"),
            "retrieval_text_profile_id": citation.metadata.get(
                "retrieval_text_profile_id"
            ),
            "source_bundle_id": _restore_value(citation.metadata, "source_bundle_id"),
            "source_restore_id": _restore_value(citation.metadata, "source_restore_id"),
            "source_anchor": citation.metadata.get("tweet_id")
            or citation.metadata.get("source_context_citation_id")
            or citation.source_id,
            "artifact_kind": citation.metadata.get("artifact_kind"),
            "artifact_type": citation.metadata.get("artifact_type"),
            "artifact_role": citation.metadata.get("artifact_role"),
            "authority_level": citation.metadata.get("authority_level"),
            "output_mode": citation.metadata.get("output_mode"),
            "participation_decision": citation.metadata.get("participation_decision"),
            "participation_snapshot": citation.metadata.get("participation_snapshot"),
            "owner_plane": citation.metadata.get("owner_plane"),
            "preview_kind": citation.metadata.get("preview_kind"),
            "citation_policy": citation.metadata.get("citation_policy"),
            "legacy_metadata_compat": citation.metadata.get("legacy_metadata_compat"),
            "not_evidence": citation.metadata.get("not_evidence"),
            "answer_support_allowed": citation.metadata.get("answer_support_allowed"),
            "primary_evidence_identity": citation.metadata.get("primary_evidence_identity"),
            "primary_evidence_key": citation.metadata.get("primary_evidence_key"),
            "primary_evidence_source_id": citation.metadata.get(
                "primary_evidence_source_id"
            ),
            "primary_evidence_hash": citation.metadata.get("primary_evidence_hash"),
            "lineage_variants": citation.metadata.get("lineage_variants") or [],
            "lineage_variant_count": citation.metadata.get("lineage_variant_count") or 0,
            "lineage_variant_warning": citation.metadata.get("lineage_variant_warning"),
            "source_hash_variant_count": citation.metadata.get("source_hash_variant_count")
            or 0,
            "source_doc_hash_status": citation.metadata.get("source_doc_hash_status"),
            "freshness_variants": citation.metadata.get("freshness_variants") or [],
            "stale_lineage_variant_present": citation.metadata.get(
                "stale_lineage_variant_present"
            )
            is True,
            "conflict_lineage_variant_present": citation.metadata.get(
                "conflict_lineage_variant_present"
            )
            is True,
            "duplicate_sources": citation.metadata.get("duplicate_sources") or [],
            "provenance_sources": citation.metadata.get("provenance_sources") or [],
            "bookmark_accounts": citation.metadata.get("bookmark_accounts") or [],
            "source_accounts": citation.metadata.get("source_accounts") or [],
            "duplicate_support_suppressed_count": citation.metadata.get(
                "duplicate_support_suppressed_count"
            )
            or 0,
            "dedup_lineage_policy": citation.metadata.get("dedup_lineage_policy"),
            "dedup_lineage_policy_scope": citation.metadata.get(
                "dedup_lineage_policy_scope"
            ),
            "dedup_lineage_source_hash_variant_policy": citation.metadata.get(
                "dedup_lineage_source_hash_variant_policy"
            ),
            "dedup_lineage_stale_variant_policy": citation.metadata.get(
                "dedup_lineage_stale_variant_policy"
            ),
            "dedup_lineage_conflict_variant_policy": citation.metadata.get(
                "dedup_lineage_conflict_variant_policy"
            ),
            "dedup_lineage_policy_action": citation.metadata.get(
                "dedup_lineage_policy_action"
            ),
        },
    )


def _citation_ready(citation: CitationAnnotation) -> bool:
    return citation_is_citation_ready(citation)


def _citation_source_restored(citation: CitationAnnotation) -> bool:
    if str(citation.source_kind or "").strip() != LOCAL_X_DB:
        return bool(citation.source_kind and citation.source_id)
    metadata = citation.metadata
    return (
        bool(str(citation.source_id or "").strip())
        and _restore_value(metadata, "source_doc_hash") is not None
        and _has_compatible_source_lineage_id(metadata)
        and _restore_value(metadata, "lineage_status") == "restored"
        and (
            _restore_value(metadata, "retrieval_text_hash") is not None
            or _restore_value(metadata, "retrieval_text_profile_id") is not None
        )
    )


def _validate_citation_against_db(
    conn: sqlite3.Connection,
    *,
    prefix: str,
    item: Any,
) -> list[str]:
    if not isinstance(item, dict):
        return [f"{prefix}: answer citation is not an object"]
    restore = item.get("restore")
    if not isinstance(restore, dict):
        return [f"{prefix}: answer citation lacks restore metadata"]
    source_kind = str(restore.get("source_kind") or item.get("source_kind") or "").strip()
    if source_kind != LOCAL_X_DB:
        return []

    citation_id = str(item.get("citation_id") or "").strip()
    chunk_id = str(restore.get("chunk_id") or item.get("chunk_id") or "").strip()
    source_id = str(restore.get("source_id") or item.get("source_id") or "").strip()
    label = citation_id or chunk_id or "<unknown>"
    errors: list[str] = []
    if not citation_id:
        errors.append(f"{prefix}: citation <unknown> missing citation_id")
    if not chunk_id:
        errors.append(f"{prefix}: citation {label} missing chunk_id")
    if not source_id:
        errors.append(f"{prefix}: citation {label} missing source_id")
    if errors:
        return errors

    citation_row = _stored_citation_row(conn, citation_id, restore)
    if citation_row is None:
        errors.append(f"{prefix}: citation {label} is not stored in memory_citation_annotations")
    elif citation_block_reasons(_citation_from_row(citation_row)):
        reasons = ", ".join(citation_block_reasons(_citation_from_row(citation_row)))
        errors.append(f"{prefix}: citation {label} stored row is not citation-ready: {reasons}")

    chunk_row = conn.execute(
        """
        SELECT chunk_id, source_kind, source_id, source_url, metadata_json
        FROM memory_context_chunks
        WHERE chunk_id = ?
        """,
        (chunk_id,),
    ).fetchone()
    if chunk_row is None:
        errors.append(f"{prefix}: citation {label} chunk {chunk_id} is not stored")
        return errors
    if str(chunk_row["source_kind"] or "") != source_kind:
        errors.append(f"{prefix}: citation {label} chunk source_kind mismatch")
    if str(chunk_row["source_id"] or "") != source_id:
        errors.append(f"{prefix}: citation {label} chunk source_id mismatch")

    chunk_metadata = _loads_json(chunk_row["metadata_json"])
    restore_source_hash = str(restore.get("source_doc_hash") or "").strip()
    chunk_source_hash = str(chunk_metadata.get("source_doc_hash") or "").strip()
    if not restore_source_hash:
        errors.append(f"{prefix}: citation {label} missing restore source_doc_hash")
    if not chunk_source_hash:
        errors.append(f"{prefix}: citation {label} chunk missing source_doc_hash")
    if restore_source_hash and chunk_source_hash and restore_source_hash != chunk_source_hash:
        errors.append(f"{prefix}: citation {label} restore source_doc_hash mismatches chunk")
    if str(restore.get("lineage_status") or "").strip() != "restored":
        errors.append(f"{prefix}: citation {label} lineage_status is not restored")
    if str(chunk_metadata.get("lineage_status") or "").strip() != "restored":
        errors.append(f"{prefix}: citation {label} chunk lineage_status is not restored")

    doc_row = conn.execute(
        """
        SELECT doc_id, title, body, compact_text, metadata_json, source_doc_hash
        FROM memory_documents
        WHERE doc_id = ?
        """,
        (source_id,),
    ).fetchone()
    if doc_row is None:
        errors.append(f"{prefix}: citation {label} source document {source_id} is missing")
        return errors
    current_source_hash = memory_document_source_hash(doc_row)
    stored_source_hash = str(doc_row["source_doc_hash"] or "").strip()
    if stored_source_hash != current_source_hash:
        errors.append(f"{prefix}: citation {label} source document hash is stale")
    if restore_source_hash and restore_source_hash != current_source_hash:
        errors.append(f"{prefix}: citation {label} restore source_doc_hash is stale")

    errors.extend(
        _source_lineage_id_errors(
            restore,
            prefix=prefix,
            label=label,
            source_id=source_id,
            source_hash=current_source_hash,
            location="restore",
        )
    )
    errors.extend(
        _source_lineage_id_errors(
            chunk_metadata,
            prefix=prefix,
            label=label,
            source_id=source_id,
            source_hash=current_source_hash,
            location="chunk",
        )
    )

    errors.extend(
        _validate_retrieval_lineage(
            conn,
            prefix=prefix,
            label=label,
            source_id=source_id,
            source_hash=current_source_hash,
            restore=restore,
        )
    )
    return errors


def _stored_citation_row(
    conn: sqlite3.Connection,
    citation_id: str,
    restore: dict[str, Any],
) -> sqlite3.Row | None:
    row = conn.execute(
        """
        SELECT
            citation_id, answer_id, chunk_id, source_kind, source_id, source_url,
            title, field_path, support_type, evidence_status, confidence, created_at,
            metadata_json
        FROM memory_citation_annotations
        WHERE citation_id = ?
        """,
        (citation_id,),
    ).fetchone()
    if row is not None:
        return row
    source_context_citation_id = str(restore.get("source_context_citation_id") or "").strip()
    if not source_context_citation_id:
        return None
    return conn.execute(
        """
        SELECT
            citation_id, answer_id, chunk_id, source_kind, source_id, source_url,
            title, field_path, support_type, evidence_status, confidence, created_at,
            metadata_json
        FROM memory_citation_annotations
        WHERE citation_id = ?
        """,
        (source_context_citation_id,),
    ).fetchone()


def _citation_from_row(row: sqlite3.Row) -> CitationAnnotation:
    return CitationAnnotation(
        citation_id=str(row["citation_id"] or ""),
        answer_id=str(row["answer_id"]) if row["answer_id"] is not None else None,
        chunk_id=str(row["chunk_id"] or ""),
        source_kind=str(row["source_kind"] or ""),
        source_id=str(row["source_id"] or ""),
        source_url=row["source_url"],
        title=str(row["title"] or ""),
        field_path=str(row["field_path"] or ""),
        support_type=str(row["support_type"] or ""),
        evidence_status=str(row["evidence_status"] or ""),
        confidence=float(row["confidence"] or 0.0),
        created_at=str(row["created_at"] or ""),
        metadata=_loads_json(row["metadata_json"]),
    )


def _validate_retrieval_lineage(
    conn: sqlite3.Connection,
    *,
    prefix: str,
    label: str,
    source_id: str,
    source_hash: str,
    restore: dict[str, Any],
) -> list[str]:
    profile_id = str(restore.get("retrieval_text_profile_id") or "").strip()
    retrieval_hash = str(restore.get("retrieval_text_hash") or "").strip()
    if not profile_id and not retrieval_hash:
        return [f"{prefix}: citation {label} missing retrieval-text lineage"]
    if profile_id:
        row = conn.execute(
            """
            SELECT profile_id, doc_id, retrieval_text, source_doc_hash
            FROM memory_retrieval_text_profiles
            WHERE profile_id = ?
            """,
            (profile_id,),
        ).fetchone()
        if row is None:
            return [f"{prefix}: citation {label} retrieval_text_profile_id is missing"]
        errors = []
        if str(row["doc_id"] or "") != source_id:
            errors.append(f"{prefix}: citation {label} retrieval_text_profile doc mismatch")
        if str(row["source_doc_hash"] or "") != source_hash:
            errors.append(f"{prefix}: citation {label} retrieval_text_profile hash mismatch")
        row_hash = text_hash(str(row["retrieval_text"] or ""))
        if retrieval_hash and retrieval_hash != row_hash:
            errors.append(f"{prefix}: citation {label} retrieval_text_hash mismatch")
        return errors

    rows = conn.execute(
        """
        SELECT retrieval_text
        FROM memory_retrieval_text_profiles
        WHERE doc_id = ?
          AND source_doc_hash = ?
        """,
        (source_id, source_hash),
    ).fetchall()
    if not any(text_hash(str(row["retrieval_text"] or "")) == retrieval_hash for row in rows):
        return [f"{prefix}: citation {label} retrieval_text_hash is not restorable"]
    return []


def _restore_value(metadata: dict[str, Any], key: str) -> str | None:
    value = metadata.get(key)
    if value is None:
        lineage = metadata.get("source_lineage")
        if isinstance(lineage, dict):
            value = lineage.get(key)
    text = str(value or "").strip()
    return text or None


def _has_compatible_source_lineage_id(metadata: dict[str, Any]) -> bool:
    return bool(
        _restore_value(metadata, "source_bundle_id")
        or _restore_value(metadata, "source_restore_id")
    )


def _source_lineage_id_errors(
    metadata: dict[str, Any],
    *,
    prefix: str,
    label: str,
    source_id: str,
    source_hash: str,
    location: str,
) -> list[str]:
    values = {
        "source_bundle_id": _restore_value(metadata, "source_bundle_id"),
        "source_restore_id": _restore_value(metadata, "source_restore_id"),
    }
    present = {key: value for key, value in values.items() if value is not None}
    location_prefix = "" if location == "restore" else f"{location} "
    if not present:
        return [
            f"{prefix}: citation {label} {location_prefix}missing compatible "
            "source lineage identifier (source_bundle_id or source_restore_id)"
        ]
    expected = {
        "source_bundle_id": canonical_source_bundle_id(source_id, source_hash),
        "source_restore_id": canonical_source_restore_id(source_id, source_hash),
    }
    return [
        f"{prefix}: citation {label} {location_prefix}{key} is not reproducible"
        for key, value in present.items()
        if value != expected[key]
    ]


def _loads_json(value: str | None) -> dict[str, Any]:
    if not value:
        return {}
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _provider_gate_required(workflow: MemoryWorkflow) -> bool:
    if workflow.stop_reason == "external_context_needed":
        return True
    parameters = workflow.metadata.get("parameters") or {}
    if not isinstance(parameters, dict):
        return False
    provider_like = _provider_like_parameters(parameters)
    return any(item["provider_gated"] and item["enabled"] for item in provider_like)


def _fixture_limitations(
    parameters: dict[str, Any],
    *,
    workflow: MemoryWorkflow,
) -> dict[str, Any]:
    providers: list[dict[str, Any]] = []
    specs = (
        ("semantic_provider", {"local_hash"}),
        ("llm_context_provider", {"fake"}),
        ("answer_provider", {"fake"}),
        ("external_reader_provider", {"fake"}),
    )
    for key, fixture_values in specs:
        value = parameters.get(key)
        normalized = str(value).strip().lower() if value is not None else ""
        if normalized in fixture_values:
            providers.append({"parameter": key, "value": value})
    if workflow.answer is not None:
        structured = workflow.answer.structured
        if isinstance(structured, dict) and structured.get("mode") == "deterministic_fake":
            providers.append({"parameter": "answer.structured.mode", "value": "deterministic_fake"})
    provider_free_fixture = bool(providers)
    return {
        "provider_free_fixture": provider_free_fixture,
        "providers": providers,
        "quality_scope": (
            "boundary_wiring_not_model_quality"
            if provider_free_fixture
            else "runtime_provider_quality_not_asserted"
        ),
    }


def _provider_like_parameters(parameters: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    specs = (
        ("semantic_provider", {"local_hash", "", None}),
        ("llm_context_provider", {"none", "fake", "", None}),
        ("answer_provider", {"none", "fake", "", None}),
        ("external_reader_provider", {"fake", "", None}),
    )
    for key, safe_values in specs:
        value = parameters.get(key)
        normalized = str(value).strip().lower() if value is not None else None
        enabled = normalized not in {None, "", "none"}
        if key == "external_reader_provider" and not parameters.get("external_run_id"):
            enabled = False
        rows.append(
            {
                "parameter": key,
                "value": value,
                "enabled": enabled,
                "provider_gated": enabled and value not in safe_values,
            }
        )
    return rows


def _payload_citations_with_restore_issues(citations: list[Any]) -> list[str]:
    broken: list[str] = []
    for item in citations:
        if not isinstance(item, dict):
            broken.append("<unknown>")
            continue
        citation_id = str(item.get("citation_id") or "<unknown>")
        restore = item.get("restore")
        if not isinstance(restore, dict):
            broken.append(citation_id)
            continue
        if (
            restore.get("context_chunk_restored") is not True
            or restore.get("source_restored") is not True
            or restore.get("citation_ready") is not True
            or _payload_local_x_db_restore_issue(item, restore)
        ):
            broken.append(citation_id)
    return broken


def _payload_local_x_db_restore_issue(
    item: dict[str, Any],
    restore: dict[str, Any],
) -> bool:
    source_kind = str(
        restore.get("source_kind")
        or item.get("source_kind")
        or ""
    ).strip()
    if source_kind != LOCAL_X_DB:
        return False
    if not str(restore.get("source_doc_hash") or "").strip():
        return True
    if not (
        str(restore.get("source_bundle_id") or "").strip()
        or str(restore.get("source_restore_id") or "").strip()
    ):
        return True
    if str(restore.get("lineage_status") or "").strip() != "restored":
        return True
    return not (
        str(restore.get("retrieval_text_hash") or "").strip()
        or str(restore.get("retrieval_text_profile_id") or "").strip()
    )


def _payload_citations_with_not_evidence_support(citations: list[Any]) -> list[str]:
    broken: list[str] = []
    for item in citations:
        if not isinstance(item, dict):
            broken.append("<unknown>")
            continue
        citation_id = str(item.get("citation_id") or "<unknown>")
        restore = item.get("restore")
        if not isinstance(restore, dict):
            continue
        if _restore_marks_not_evidence(restore):
            broken.append(citation_id)
    return broken


def _restore_marks_not_evidence(restore: dict[str, Any]) -> bool:
    if restore.get("not_evidence") is True:
        return True
    if restore.get("answer_support_allowed") is False:
        return True
    if _restore_structured_fields_block_answer_support(restore):
        return True
    for key in ("owner_plane", "citation_policy"):
        value = restore.get(key)
        if value is not None and _not_evidence_restore_value(value):
            return True
    if restore.get("legacy_metadata_compat") is True:
        for key in LEGACY_RESTORE_COMPAT_KEYS:
            value = restore.get(key)
            if value is not None and _not_evidence_restore_value(value):
                return True
    return False


def _restore_structured_fields_block_answer_support(restore: dict[str, Any]) -> bool:
    artifact_role = restore.get("artifact_role")
    if artifact_role not in {None, ""}:
        try:
            if not artifact_role_allows_answer_support(str(artifact_role)):
                return True
        except ValueError:
            return True

    authority_level = restore.get("authority_level")
    if authority_level not in {None, ""}:
        try:
            if not authority_at_least(str(authority_level), AuthorityLevel.EVIDENCE_VIEW):
                return True
        except ValueError:
            return True

    output_mode = restore.get("output_mode")
    if output_mode not in {None, ""}:
        try:
            mode = normalize_output_mode(str(output_mode))
        except ValueError:
            return True
        if mode not in {OutputMode.EVIDENCE_PACKAGE, OutputMode.ANSWER}:
            return True

    for key in ("participation_decision", "participation_snapshot"):
        participation = restore.get(key)
        if not isinstance(participation, dict):
            continue
        if participation.get("can_use_as_evidence") is False:
            return True
        if participation.get("can_use_in_answer") is False:
            return True
    return False


def _not_evidence_restore_value(value: Any) -> bool:
    if isinstance(value, list | tuple | set):
        return any(_not_evidence_restore_value(item) for item in value)
    if isinstance(value, dict):
        return any(_not_evidence_restore_value(item) for item in value.values())
    normalized = str(value).strip().casefold().replace("-", "_").replace(" ", "_")
    return normalized in LEGACY_NON_EVIDENCE_POLICY_MARKERS


def _answerability_status(answer: MemoryAnswer) -> str | None:
    payload = answer.structured.get("answerability")
    if not isinstance(payload, dict):
        return None
    status = payload.get("status")
    return str(status) if status else None
