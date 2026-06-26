from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import Any

from research_x.memory.answer import MemoryAnswer
from research_x.memory.context import CitationAnnotation
from research_x.memory.evidence_invariants import (
    citation_block_reasons,
    citation_is_citation_ready,
    citation_is_not_evidence,
    citation_is_stale,
    citation_marks_conflict,
)
from research_x.memory.workflow import MemoryWorkflow
from research_x.tool_interface.codex_bridge import bridge_trace_contract

CONTRACT_VERSION = "research-x-ai-tool-v1"
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
    "context_chunk",
    "citation_ready",
}


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


def workflow_tool_output(workflow: MemoryWorkflow) -> ToolOutput:
    """Build the stable AI-facing output contract for a memory workflow."""

    status = _workflow_status(workflow)
    citations = _tool_citations(workflow)
    evidence_level = _workflow_evidence_level(workflow, status=status, citations=citations)
    answer_text = workflow.answer.answer_text if workflow.answer is not None else None
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


def workflow_tool_output_json(workflow: MemoryWorkflow) -> str:
    return json.dumps(
        workflow_tool_output(workflow).as_dict(),
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
    return errors


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
    if not workflow.answer.citation_annotations:
        return "citation_missing"
    if workflow.answer.status == "ok" and all(
        _citation_ready(citation) for citation in workflow.answer.citation_annotations
    ):
        return "answer"
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
            return "source_bundle"
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
        "provider_gate": {
            "required": status == "provider_gated",
            "no_quota_default": True,
            "provider_like_parameters": _provider_like_parameters(parameters),
        },
        "budget": {
            "max_steps": parameters.get("max_steps"),
            "step_count": len(workflow.steps),
            "stop_condition_audit": stop_audit,
        },
        "eval_warnings": eval_warnings,
        "route_plan": route_plan,
        "codex_bridge": bridge_trace_contract(),
    }


def _tool_citations(workflow: MemoryWorkflow) -> tuple[ToolCitation, ...]:
    raw_citations, context_run_id = _raw_citations_with_context_run_id(workflow)
    return tuple(
        _tool_citation(citation, context_run_id=context_run_id)
        for citation in raw_citations
    )


def _raw_citations(workflow: MemoryWorkflow) -> tuple[CitationAnnotation, ...]:
    raw_citations, _context_run_id = _raw_citations_with_context_run_id(workflow)
    return raw_citations


def _raw_citations_with_context_run_id(
    workflow: MemoryWorkflow,
) -> tuple[tuple[CitationAnnotation, ...], str | None]:
    if workflow.answer is not None:
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
            "source_anchor": citation.metadata.get("tweet_id")
            or citation.metadata.get("source_context_citation_id")
            or citation.source_id,
        },
    )


def _citation_ready(citation: CitationAnnotation) -> bool:
    return citation_is_citation_ready(citation)


def _provider_gate_required(workflow: MemoryWorkflow) -> bool:
    if workflow.stop_reason == "external_context_needed":
        return True
    parameters = workflow.metadata.get("parameters") or {}
    if not isinstance(parameters, dict):
        return False
    provider_like = _provider_like_parameters(parameters)
    return any(item["provider_gated"] and item["enabled"] for item in provider_like)


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


def _answerability_status(answer: MemoryAnswer) -> str | None:
    payload = answer.structured.get("answerability")
    if not isinstance(payload, dict):
        return None
    status = payload.get("status")
    return str(status) if status else None
