from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any

from research_x.memory.answer import MemoryAnswer
from research_x.memory.context import CitationAnnotation
from research_x.memory.document_hashes import memory_document_source_hash, text_hash
from research_x.memory.evidence_invariants import (
    citation_block_reasons,
    citation_is_citation_ready,
    citation_is_not_evidence,
    citation_is_stale,
    citation_marks_conflict,
)
from research_x.memory.schema import ensure_memory_schema
from research_x.memory.source_identity import source_bundle_id as canonical_source_bundle_id
from research_x.memory.workflow import MemoryWorkflow
from research_x.tool_interface.codex_bridge import bridge_trace_contract

CONTRACT_VERSION = "research-x-ai-tool-v1"
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
    "context_chunk",
    "citation_ready",
}
NON_EVIDENCE_RESTORE_MARKERS = {
    "chatgpt_consultation",
    "codex_review_capture",
    "compressed_summary",
    "context_offload_preview",
    "context_preview",
    "control_artifact",
    "diagram",
    "diagram_review",
    "gpt_pro_plan",
    "html_review",
    "html_structure_view",
    "not_citation",
    "not_evidence",
    "pointer_map",
    "preview",
    "review_artifact",
    "wbs",
    "wbs_rendered_view",
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
    output = workflow_tool_output(workflow)
    if db_path is None:
        return output
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
            "no_quota_default": True,
            "provider_like_parameters": _provider_like_parameters(parameters),
        },
        "fixture_limitations": fixture_limitations,
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
        has_pointer = bool(
            metadata.get("offload_pointer")
            or pointer_status
            or restore_hint_status
            or preview_kind
            or artifact_kind in {"context_offload", "context_offload_preview", "pointer_map"}
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
                "artifact_kind": artifact_kind,
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
            "source_bundle_id": citation.metadata.get("source_bundle_id"),
            "source_anchor": citation.metadata.get("tweet_id")
            or citation.metadata.get("source_context_citation_id")
            or citation.source_id,
            "artifact_kind": citation.metadata.get("artifact_kind"),
            "artifact_type": citation.metadata.get("artifact_type"),
            "owner_plane": citation.metadata.get("owner_plane"),
            "preview_kind": citation.metadata.get("preview_kind"),
            "citation_policy": citation.metadata.get("citation_policy"),
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
        and _restore_value(metadata, "source_bundle_id") is not None
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

    restore_bundle = str(restore.get("source_bundle_id") or "").strip()
    chunk_bundle = str(chunk_metadata.get("source_bundle_id") or "").strip()
    expected_bundle = canonical_source_bundle_id(source_id, current_source_hash)
    if not restore_bundle:
        errors.append(f"{prefix}: citation {label} missing source_bundle_id")
    if not chunk_bundle:
        errors.append(f"{prefix}: citation {label} chunk missing source_bundle_id")
    if restore_bundle and restore_bundle != expected_bundle:
        errors.append(f"{prefix}: citation {label} source_bundle_id is not reproducible")
    if chunk_bundle and chunk_bundle != restore_bundle:
        errors.append(f"{prefix}: citation {label} chunk source_bundle_id mismatch")

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
    if not str(restore.get("source_bundle_id") or "").strip():
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
    for key in (
        "artifact_kind",
        "artifact_type",
        "owner_plane",
        "preview_kind",
        "citation_policy",
    ):
        value = restore.get(key)
        if value is not None and _not_evidence_restore_value(value):
            return True
    return False


def _not_evidence_restore_value(value: Any) -> bool:
    if isinstance(value, list | tuple | set):
        return any(_not_evidence_restore_value(item) for item in value)
    if isinstance(value, dict):
        return any(_not_evidence_restore_value(item) for item in value.values())
    normalized = str(value).strip().casefold().replace("-", "_").replace(" ", "_")
    return any(marker in normalized for marker in NON_EVIDENCE_RESTORE_MARKERS)


def _answerability_status(answer: MemoryAnswer) -> str | None:
    payload = answer.structured.get("answerability")
    if not isinstance(payload, dict):
        return None
    status = payload.get("status")
    return str(status) if status else None
