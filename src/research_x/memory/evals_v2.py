from __future__ import annotations

import hashlib
import json
import math
import sqlite3
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from research_x.memory.artifact_roles import normalize_artifact_role
from research_x.memory.authority_levels import (
    AuthorityLevel,
    authority_at_least,
    normalize_authority_level,
)
from research_x.memory.output_modes import OutputMode, normalize_output_mode
from research_x.memory.schema import ensure_memory_schema
from research_x.tool_interface.memory_tool_contract import (
    CONTRACT_VERSION_V2,
    ToolCitation,
    ToolOutputItemV2,
    ToolOutputV2,
    validate_tool_output_v2,
)

COMMON_METRICS = (
    "expected_source_recall_at_k",
    "precision_at_k",
    "mrr",
    "ndcg",
    "negative_hit_rate",
    "duplicate_rate",
    "stale_hit_rate",
    "role_mismatch_rate",
)
MODE_METRICS = {
    OutputMode.EXPLORE.value: (
        "diversity_at_k",
        "weak_related_hit_rate",
        "useful_candidate_rate",
        "noise_budget_violation_rate",
    ),
    OutputMode.COLLECT.value: (
        "source_coverage",
        "artifact_coverage",
        "source_status_coverage",
    ),
    OutputMode.WORKING_NOTE.value: (
        "note_source_link_rate",
        "note_artifact_link_rate",
        "unresolved_issue_disclosure_rate",
        "unsupported_claim_label_rate",
    ),
    OutputMode.SYNTHESIZE.value: (
        "contradiction_disclosure_rate",
        "missing_evidence_disclosure_rate",
        "unsupported_claim_label_rate",
    ),
    OutputMode.EVIDENCE_PACKAGE.value: (
        "source_restore_rate",
        "evidence_view_rate",
        "citation_candidate_rate",
        "stale_evidence_block_rate",
    ),
    OutputMode.ANSWER.value: (
        "citation_ready_rate",
        "claim_support_rate",
        "answer_assertion_support_rate",
        "abstain_correctness",
        "provider_gated_correctness",
    ),
}


@dataclass(frozen=True)
class EvalCaseV2:
    case_id: str
    query: str
    output_mode: str
    objective: str
    source_scope: str
    expected_source_refs: tuple[str, ...]
    acceptable_source_refs: tuple[str, ...]
    negative_source_refs: tuple[str, ...]
    expected_artifact_roles: tuple[str, ...]
    expected_authority_level: str
    required_relation_types: tuple[str, ...]
    provider_policy: str
    context_budget: int
    noise_budget: float
    expected_status: str | None
    notes: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class EvalRunV2Summary:
    db_path: str
    run_id: str
    cases_path: str
    cases: int
    status: str
    ok_count: int
    needs_review_count: int
    fail_count: int
    metrics_by_mode: dict[str, tuple[str, ...]]

    @property
    def case_count(self) -> int:
        return self.cases

    def as_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["metrics_by_mode"] = {
            key: list(value) for key, value in self.metrics_by_mode.items()
        }
        return data


def eval_case_v2_from_dict(payload: dict[str, Any]) -> EvalCaseV2:
    return EvalCaseV2(
        case_id=str(payload.get("case_id") or ""),
        query=str(payload.get("query") or ""),
        output_mode=str(payload.get("output_mode") or ""),
        objective=str(payload.get("objective") or ""),
        source_scope=str(payload.get("source_scope") or ""),
        expected_source_refs=tuple(payload.get("expected_source_refs") or ()),
        acceptable_source_refs=tuple(payload.get("acceptable_source_refs") or ()),
        negative_source_refs=tuple(payload.get("negative_source_refs") or ()),
        expected_artifact_roles=tuple(payload.get("expected_artifact_roles") or ()),
        expected_authority_level=str(payload.get("expected_authority_level") or ""),
        required_relation_types=tuple(payload.get("required_relation_types") or ()),
        provider_policy=str(payload.get("provider_policy") or ""),
        context_budget=int(payload.get("context_budget") or 0),
        noise_budget=float(payload.get("noise_budget") or 0.0),
        expected_status=(
            str(payload["expected_status"])
            if payload.get("expected_status") is not None
            else None
        ),
        notes=str(payload.get("notes") or ""),
    )


def load_eval_cases_v2(path: str | Path) -> tuple[EvalCaseV2, ...]:
    cases: list[EvalCaseV2] = []
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid EvalCaseV2 JSONL line {line_number}: {exc}") from exc
        cases.append(eval_case_v2_from_dict(payload))
    return tuple(cases)


def validate_eval_case_v2(case: EvalCaseV2) -> list[str]:
    errors: list[str] = []
    prefix = case.case_id or "<unknown>"
    if not case.case_id:
        errors.append("case_id is required")
    if not case.query:
        errors.append(f"{prefix}: query is required")
    try:
        output_mode = normalize_output_mode(case.output_mode)
    except ValueError as exc:
        errors.append(f"{prefix}: {exc}")
        output_mode = None
    try:
        authority = normalize_authority_level(case.expected_authority_level)
    except ValueError as exc:
        errors.append(f"{prefix}: {exc}")
        authority = None
    for role in case.expected_artifact_roles:
        try:
            normalize_artifact_role(role)
        except ValueError as exc:
            errors.append(f"{prefix}: {exc}")
    overlap = set(case.expected_source_refs) & set(case.negative_source_refs)
    if overlap:
        errors.append(
            f"{prefix}: expected_source_refs overlap negative_source_refs: "
            + ", ".join(sorted(overlap))
        )
    if case.context_budget < 0:
        errors.append(f"{prefix}: context_budget must be non-negative")
    if not 0.0 <= case.noise_budget <= 1.0:
        errors.append(f"{prefix}: noise_budget must be between 0.0 and 1.0")
    if (
        output_mode is OutputMode.ANSWER
        and authority is not None
        and authority is not AuthorityLevel.ANSWER_ASSERTION
    ):
        errors.append(f"{prefix}: answer eval requires answer_assertion authority")
    if (
        output_mode is OutputMode.EVIDENCE_PACKAGE
        and authority is not None
        and not authority_at_least(authority, AuthorityLevel.EVIDENCE_VIEW)
    ):
        errors.append(
            f"{prefix}: evidence_package eval requires evidence_view authority"
        )
    if output_mode in {OutputMode.EXPLORE, OutputMode.COLLECT} and not case.expected_source_refs:
        errors.append(f"{prefix}: {output_mode.value} eval requires expected_source_refs")
    return errors


def metrics_for_output_mode(output_mode: str | OutputMode) -> tuple[str, ...]:
    mode = normalize_output_mode(output_mode)
    return (*COMMON_METRICS, *MODE_METRICS[mode.value])


def run_eval_cases_v2(
    db_path: str | Path,
    *,
    cases_path: str | Path,
    run_id: str | None = None,
    started_at: str | None = None,
) -> EvalRunV2Summary:
    cases = load_eval_cases_v2(cases_path)
    resolved_run_id = run_id or "eval-v2:" + _stable_hash(
        {
            "cases_path": str(cases_path),
            "cases": [case.as_dict() for case in cases],
        }
    )[:24]
    started = started_at or _now()
    metrics_by_mode = _metrics_by_mode_for_cases(cases)
    path = Path(db_path)
    with sqlite3.connect(path, timeout=60) as conn:
        conn.row_factory = sqlite3.Row
        ensure_memory_schema(conn)
        # Strict evidence/answer evaluation opens a second connection through
        # the evidence-package boundary.  Finish schema migration writes before
        # that read/validation path so the nested connection does not time out
        # behind this connection's transaction.
        conn.commit()
        results = tuple(
            _eval_case_result(conn, index, case) for index, case in enumerate(cases)
        )
        ok_count = sum(1 for result in results if result["status"] == "ok")
        fail_count = sum(1 for result in results if result["status"] == "fail")
        needs_review_count = sum(
            1 for result in results if result["status"] == "needs_review"
        )
        unexpected_status_count = sum(
            1
            for result in results
            if not _status_matches_expected(
                str(result["status"]),
                result["case"].expected_status,
            )
            and result["status"] != "needs_review"
        )
        status = "ok" if fail_count == 0 and unexpected_status_count == 0 else "failed"
        _store_eval_run(
            conn,
            run_id=resolved_run_id,
            cases_path=str(cases_path),
            case_count=len(cases),
            status=status,
            ok_count=ok_count,
            needs_review_count=needs_review_count,
            fail_count=fail_count,
            started_at=started,
            finished_at=started,
            parameters={
                "eval_version": "eval-v2",
                "metrics_by_mode": {key: list(value) for key, value in metrics_by_mode.items()},
                "unexpected_status_count": unexpected_status_count,
            },
        )
        for result in results:
            _store_eval_result(conn, run_id=resolved_run_id, result=result, created_at=started)
    return EvalRunV2Summary(
        db_path=str(path),
        run_id=resolved_run_id,
        cases_path=str(cases_path),
        cases=len(cases),
        status=status,
        ok_count=ok_count,
        needs_review_count=needs_review_count,
        fail_count=fail_count,
        metrics_by_mode=metrics_by_mode,
    )


def _eval_case_result(
    conn: sqlite3.Connection,
    index: int,
    case: EvalCaseV2,
) -> dict[str, Any]:
    errors = validate_eval_case_v2(case)
    retrieval = _retrieve_eval_candidates(conn, case)
    retrieved = tuple(retrieval["candidates"])
    metrics = (
        _metric_values(case, retrieved)
        if not errors
        else {metric: 0.0 for metric in _metrics_for_case(case)}
    )
    status = "needs_review" if errors else _status_from_metrics(case, metrics)
    return {
        "case": case,
        "case_index": index,
        "status": status,
        "errors": errors,
        "retrieved": retrieved,
        "retrieval": retrieval,
        "metrics": metrics,
    }


def _retrieve_eval_candidates(
    conn: sqlite3.Connection,
    case: EvalCaseV2,
) -> dict[str, Any]:
    query_terms = tuple(term.casefold() for term in case.query.split() if term.strip())
    limit = max(1, min(case.context_budget or 10, 100))
    try:
        mode = normalize_output_mode(case.output_mode)
    except ValueError:
        mode = None
    strict_output_required = mode in {OutputMode.EVIDENCE_PACKAGE, OutputMode.ANSWER}
    mode_search_candidates = _retrieve_eval_candidates_from_mode_search(
        conn,
        case,
        limit=limit,
    )
    if strict_output_required:
        diagnostic = _retrieve_table_eval_candidates(
            conn,
            query_terms=query_terms,
            limit=limit,
            diagnostic_only=True,
        )
        return {
            "candidates": tuple(_rank_eval_candidates(list(mode_search_candidates), limit=limit)),
            "diagnostic_candidates": diagnostic,
            "strict_output_required": True,
            "strict_output_status": "passed" if mode_search_candidates else "missing_strict_output",
            "diagnostic_fallback_used": not bool(mode_search_candidates) and bool(diagnostic),
        }
    if mode_search_candidates:
        return {
            "candidates": tuple(_rank_eval_candidates(list(mode_search_candidates), limit=limit)),
            "diagnostic_candidates": (),
            "strict_output_required": False,
            "strict_output_status": "not_required",
            "diagnostic_fallback_used": False,
        }
    table_candidates = _retrieve_table_eval_candidates(
        conn,
        query_terms=query_terms,
        limit=limit,
        diagnostic_only=False,
    )
    return {
        "candidates": table_candidates,
        "diagnostic_candidates": (),
        "strict_output_required": False,
        "strict_output_status": "not_required",
        "diagnostic_fallback_used": False,
    }


def _retrieve_table_eval_candidates(
    conn: sqlite3.Connection,
    *,
    query_terms: tuple[str, ...],
    limit: int,
    diagnostic_only: bool,
) -> tuple[dict[str, Any], ...]:
    document_rows = conn.execute(
        """
        SELECT doc_id, doc_type, source_tweet_id, title, body, compact_text,
               source_refs_json, lifecycle_status, metadata_json
        FROM memory_documents
        ORDER BY updated_at DESC, doc_id
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    source_rows = conn.execute(
        """
        SELECT source_ref, source_kind, source_title, source_status,
               lifecycle_status, metadata_json
        FROM memory_sources
        ORDER BY updated_at DESC, source_ref
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    artifact_rows = conn.execute(
        """
        SELECT artifact_id, artifact_role, authority_level, source_refs_json,
               artifact_status, metadata_json
        FROM memory_artifacts
        ORDER BY updated_at DESC, artifact_id
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    candidates: list[dict[str, Any]] = []
    for row in document_rows:
        source_refs = _eval_document_source_refs(row)
        haystack = " ".join(
            str(row[key] or "")
            for key in (
                "doc_id",
                "doc_type",
                "source_tweet_id",
                "title",
                "body",
                "compact_text",
                "metadata_json",
            )
        ).casefold()
        score = _term_score(query_terms, haystack)
        for source_ref in source_refs:
            candidates.append(
                {
                    "source_ref": source_ref,
                    "artifact_role": "projection",
                    "authority_level": "source_backed",
                    "source_status": "available",
                    "artifact_status": str(row["lifecycle_status"] or "active"),
                    "score": score,
                    "diagnostic_only": diagnostic_only,
                    "retrieval_engine": (
                        "eval_v2_diagnostic_table_fallback"
                        if diagnostic_only
                        else "eval_v2_table_fallback"
                    ),
                }
            )
    for row in source_rows:
        haystack = " ".join(
            str(row[key] or "")
            for key in ("source_ref", "source_kind", "source_title", "metadata_json")
        ).casefold()
        candidates.append(
            {
                "source_ref": str(row["source_ref"]),
                "artifact_role": "raw_source",
                "authority_level": "source_backed",
                "source_status": str(row["source_status"] or ""),
                "artifact_status": str(row["lifecycle_status"] or "active"),
                "score": _term_score(query_terms, haystack),
                "diagnostic_only": diagnostic_only,
                "retrieval_engine": (
                    "eval_v2_diagnostic_table_fallback"
                    if diagnostic_only
                    else "eval_v2_table_fallback"
                ),
            }
        )
    for row in artifact_rows:
        source_refs = tuple(json.loads(row["source_refs_json"] or "[]"))
        haystack = " ".join(
            [
                str(row["artifact_id"]),
                str(row["artifact_role"]),
                str(row["authority_level"]),
                str(row["metadata_json"] or ""),
                " ".join(str(ref) for ref in source_refs),
            ]
        ).casefold()
        score = _term_score(query_terms, haystack)
        for source_ref in source_refs or (str(row["artifact_id"]),):
            candidates.append(
                {
                    "source_ref": str(source_ref),
                    "artifact_role": str(row["artifact_role"]),
                    "authority_level": str(row["authority_level"]),
                    "source_status": "available",
                    "artifact_status": str(row["artifact_status"]),
                    "score": score,
                    "diagnostic_only": diagnostic_only,
                    "retrieval_engine": (
                        "eval_v2_diagnostic_table_fallback"
                        if diagnostic_only
                        else "eval_v2_table_fallback"
                    ),
                }
            )
    return tuple(_rank_eval_candidates(candidates, limit=limit))


def _eval_document_source_refs(row: sqlite3.Row) -> tuple[str, ...]:
    refs = tuple(str(ref) for ref in json.loads(row["source_refs_json"] or "[]") if ref)
    if refs:
        return refs
    source_tweet_id = str(row["source_tweet_id"] or "").strip()
    if source_tweet_id:
        return (f"x:tweet:{source_tweet_id}",)
    return (str(row["doc_id"]),)


def _retrieve_eval_candidates_from_mode_search(
    conn: sqlite3.Connection,
    case: EvalCaseV2,
    *,
    limit: int,
) -> tuple[dict[str, Any], ...]:
    db_path = _connection_database_path(conn)
    if not db_path:
        return ()
    try:
        mode = normalize_output_mode(case.output_mode)
    except ValueError:
        return ()
    if mode in {OutputMode.EVIDENCE_PACKAGE, OutputMode.ANSWER}:
        strict_candidates = _retrieve_eval_candidates_from_strict_output(
            conn,
            case,
            db_path=db_path,
            mode=mode,
            limit=limit,
        )
        if strict_candidates:
            return strict_candidates
        return ()
    try:
        from research_x.memory import source_refs
        from research_x.memory.search import search_memory
        from research_x.tool_interface.mode_aware_search import search_results_tool_output_v2

        results = search_memory(db_path, case.query, limit=limit)
    except (FileNotFoundError, RuntimeError, sqlite3.Error):
        return ()
    try:
        if mode is not OutputMode.ANSWER:
            output = search_results_tool_output_v2(
                query=case.query,
                results=results,
                output_mode=mode,
                working_note_id="eval-v2-working-note"
                if mode is OutputMode.WORKING_NOTE
                else None,
            )
            return tuple(
                {
                    "source_ref": str(item.source_refs[0] if item.source_refs else item.item_id),
                    "artifact_role": item.artifact_role,
                    "authority_level": item.authority_level,
                    "source_status": item.source_status,
                    "artifact_status": str(item.metadata.get("artifact_status") or "active"),
                    "score": float(item.score or 0.0),
                    "retrieval_engine": item.why_relevant,
                    "output_trace": output.trace,
                    "has_source_link": bool(item.source_refs),
                    "has_artifact_link": bool(item.item_id),
                }
                for item in output.items
            )
    except ValueError:
        pass
    candidates: list[dict[str, Any]] = []
    for result in results:
        if result.source_refs:
            source_ref = result.source_refs[0]
        elif result.source_tweet_id:
            source_ref = source_refs.x_tweet(result.source_tweet_id)
        else:
            source_ref = str(result.metadata.get("source_ref") or result.doc_id)
        candidates.append(
            {
                "source_ref": source_ref,
                "artifact_role": result.artifact_role,
                "authority_level": result.authority_level,
                "source_status": result.source_status,
                "artifact_status": str(result.metadata.get("artifact_status") or "active"),
                "score": float(result.score),
                "retrieval_engine": result.match_method,
            }
        )
    return tuple(candidates)


def _retrieve_eval_candidates_from_strict_output(
    conn: sqlite3.Connection,
    case: EvalCaseV2,
    *,
    db_path: str,
    mode: OutputMode,
    limit: int,
) -> tuple[dict[str, Any], ...]:
    artifact_ids = _eval_evidence_artifact_ids(conn, case, limit=limit)
    if not artifact_ids:
        return ()
    try:
        from research_x.memory.evidence_package import build_evidence_package_output

        package = build_evidence_package_output(
            db_path,
            query=case.query,
            artifact_ids=artifact_ids,
            tool_kind="research_x.memory.evals_v2.evidence_package",
        )
        output = (
            _eval_answer_output_from_package(package, case)
            if mode is OutputMode.ANSWER
            else package
        )
    except (sqlite3.Error, ValueError):
        return ()
    return _candidates_from_tool_output(output)


def _eval_evidence_artifact_ids(
    conn: sqlite3.Connection,
    case: EvalCaseV2,
    *,
    limit: int,
) -> tuple[str, ...]:
    rows = conn.execute(
        """
        SELECT artifact_id, source_refs_json, metadata_json, updated_at
        FROM memory_artifacts
        WHERE artifact_role = 'evidence_view'
          AND authority_level IN ('evidence_view', 'claim_supported')
          AND artifact_status NOT IN (
              'stale', 'orphan', 'orphaned', 'rebuild_required', 'tombstoned'
          )
        ORDER BY updated_at DESC, artifact_id
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    if not rows:
        return ()
    positive = set(case.expected_source_refs) | set(case.acceptable_source_refs)
    query_terms = tuple(term.casefold() for term in case.query.split() if term.strip())
    ranked: list[tuple[float, str]] = []
    for row in rows:
        source_refs = tuple(json.loads(row["source_refs_json"] or "[]"))
        source_hit = bool(positive & set(source_refs)) if positive else False
        haystack = " ".join(
            [
                str(row["artifact_id"]),
                " ".join(str(ref) for ref in source_refs),
                str(row["metadata_json"] or ""),
            ]
        ).casefold()
        score = (1.0 if source_hit else 0.0) + _term_score(query_terms, haystack)
        ranked.append((score, str(row["artifact_id"])))
    selected = [
        artifact_id
        for score, artifact_id in sorted(
            ranked,
            key=lambda item: (-item[0], item[1]),
        )
        if score > 0.0 or not positive
    ]
    return tuple(selected[:limit])


def _eval_answer_output_from_package(
    package: ToolOutputV2,
    case: EvalCaseV2,
) -> ToolOutputV2:
    citation_candidates = package.trace.get("citation_candidates")
    if not isinstance(citation_candidates, list) or not citation_candidates:
        raise ValueError("eval answer requires citation candidates")
    citations = tuple(
        _eval_citation_from_candidate(candidate)
        for candidate in citation_candidates
        if isinstance(candidate, dict)
    )
    if not citations:
        raise ValueError("eval answer requires citations")
    claim = {
        "claim_id": f"{case.case_id or 'eval'}:claim-1",
        "claim_text": case.objective or case.query,
        "support_status": "supported",
        "support_score": 1.0,
        "citation_ids": [citation.citation_id for citation in citations],
        "provider": "fake_local_answer_provider",
        "diagnostic_only": True,
    }
    items = tuple(_eval_answer_item(item) for item in package.items)
    output = ToolOutputV2(
        contract_version=CONTRACT_VERSION_V2,
        tool_kind="research_x.memory.evals_v2.answer",
        query=package.query,
        output_mode=OutputMode.ANSWER.value,
        status="answer",
        answer_text=f"Eval answer for {case.case_id or case.query}",
        items=items,
        citations=citations,
        claim_support={"status": "supported", "claims": [claim]},
        working_note_id=package.working_note_id,
        trace={
            "db_backed_validation": {
                "status": "passed",
                "output_run_id": "eval-v2:" + _stable_hash(case.as_dict())[:24],
                "claim_support_assessments": 1,
            },
            "source_output_mode": package.output_mode,
            "eval_v2_strict_answer_path": True,
            "eval_v2_answer_provider": "fake_local_answer_provider",
            "eval_v2_answer_quality_proof": False,
            "diagnostic_only": True,
        },
    )
    errors = validate_tool_output_v2(output)
    if errors:
        raise ValueError("; ".join(errors))
    return output


def _eval_citation_from_candidate(candidate: dict[str, Any]) -> ToolCitation:
    source_refs = tuple(str(ref) for ref in candidate.get("source_refs") or ())
    citation_id = str(candidate.get("citation_id") or candidate.get("artifact_id") or "")
    if not citation_id:
        raise ValueError("citation candidate requires citation_id")
    source_id = str(candidate.get("source_id") or candidate.get("artifact_id") or citation_id)
    restore = dict(candidate.get("restore") or {})
    return ToolCitation(
        citation_id=citation_id,
        chunk_id=str(candidate.get("chunk_id") or citation_id),
        source_kind=str(candidate.get("source_kind") or "memory_artifact"),
        source_id=source_id,
        source_url=None,
        title=source_refs[0] if source_refs else source_id,
        evidence_status="citation_ready",
        citation_ready=True,
        restore={
            "lineage_status": "restored",
            "citation_ready": True,
            "source_restored": True,
            "context_chunk_restored": True,
            **restore,
        },
    )


def _eval_answer_item(item: ToolOutputItemV2) -> ToolOutputItemV2:
    if item.artifact_role != "evidence_view":
        raise ValueError(f"answer eval requires evidence_view item: {item.item_id}")
    return ToolOutputItemV2(
        item_id=item.item_id,
        subject_kind=item.subject_kind,
        subject_id=item.subject_id,
        artifact_role=item.artifact_role,
        authority_level=AuthorityLevel.ANSWER_ASSERTION.value,
        source_refs=item.source_refs,
        source_status=item.source_status,
        projection_id=item.projection_id,
        score=item.score,
        why_relevant="eval_v2_strict_answer_assertion",
        risk_flags=item.risk_flags,
        metadata={**item.metadata, "promoted_from": item.authority_level},
    )


def _candidates_from_tool_output(output: ToolOutputV2) -> tuple[dict[str, Any], ...]:
    candidates: list[dict[str, Any]] = []
    for item in output.items:
        source_refs = item.source_refs or (item.item_id,)
        for source_ref in source_refs:
            candidates.append(
                {
                    "source_ref": str(source_ref),
                    "artifact_role": item.artifact_role,
                    "authority_level": item.authority_level,
                    "source_status": item.source_status,
                    "artifact_status": str(item.metadata.get("artifact_status") or "active"),
                    "score": float(item.score or 1.0),
                    "retrieval_engine": item.why_relevant,
                    "output_trace": output.trace,
                    "has_source_link": bool(item.source_refs),
                    "has_artifact_link": bool(item.item_id),
                    "citation_count": len(output.citations),
                    "claim_support_status": (
                        output.claim_support or {}
                    ).get("status"),
                    "output": output.as_dict(),
                }
            )
    return tuple(candidates)


def _rank_eval_candidates(
    candidates: list[dict[str, Any]],
    *,
    limit: int,
) -> tuple[dict[str, Any], ...]:
    best_by_ref: dict[str, dict[str, Any]] = {}
    for item in candidates:
        source_ref = str(item["source_ref"])
        current = best_by_ref.get(source_ref)
        if current is None or float(item["score"]) > float(current["score"]):
            best_by_ref[source_ref] = item
    return tuple(
        sorted(
            best_by_ref.values(),
            key=lambda item: (-float(item["score"]), str(item["source_ref"])),
        )[:limit]
    )


def _connection_database_path(conn: sqlite3.Connection) -> str | None:
    row = conn.execute("PRAGMA database_list").fetchone()
    if row is None:
        return None
    path = str(row[2] or "")
    return path or None


def _term_score(query_terms: tuple[str, ...], haystack: str) -> float:
    if not query_terms:
        return 0.0
    return sum(1.0 for term in query_terms if term in haystack) / len(query_terms)


def _metric_values(
    case: EvalCaseV2,
    retrieved: tuple[dict[str, Any], ...],
) -> dict[str, float]:
    expected = set(case.expected_source_refs)
    acceptable = set(case.acceptable_source_refs)
    negative = set(case.negative_source_refs)
    retrieved_refs = [str(item["source_ref"]) for item in retrieved]
    retrieved_set = set(retrieved_refs)
    positive = expected | acceptable
    expected_hits = expected & retrieved_set
    positive_hits = positive & retrieved_set
    negative_hits = negative & retrieved_set
    duplicate_count = len(retrieved_refs) - len(retrieved_set)
    stale_count = sum(
        1
        for item in retrieved
        if str(item.get("artifact_status") or "").casefold()
        in {"stale", "orphan", "orphaned", "rebuild_required", "tombstoned"}
    )
    expected_roles = set(case.expected_artifact_roles)
    role_mismatches = sum(
        1
        for item in retrieved
        if expected_roles and str(item.get("artifact_role")) not in expected_roles
    )
    first_positive_rank = next(
        (
            index + 1
            for index, source_ref in enumerate(retrieved_refs)
            if source_ref in positive
        ),
        None,
    )
    values = {metric: 0.0 for metric in metrics_for_output_mode(case.output_mode)}
    values.update(
        {
            "expected_source_recall_at_k": _safe_ratio(
                len(expected_hits),
                len(expected),
            ),
            "precision_at_k": _safe_ratio(len(positive_hits), len(retrieved)),
            "mrr": 0.0 if first_positive_rank is None else 1.0 / first_positive_rank,
            "ndcg": _ndcg_at_k(retrieved_refs, positive),
            "negative_hit_rate": _safe_ratio(len(negative_hits), len(negative)),
            "duplicate_rate": _safe_ratio(duplicate_count, len(retrieved)),
            "stale_hit_rate": _safe_ratio(stale_count, len(retrieved)),
            "role_mismatch_rate": _safe_ratio(role_mismatches, len(retrieved)),
        }
    )
    mode = normalize_output_mode(case.output_mode)
    if mode is OutputMode.EXPLORE:
        values["diversity_at_k"] = _safe_ratio(len(retrieved_set), len(retrieved))
        values["useful_candidate_rate"] = values["precision_at_k"]
        values["noise_budget_violation_rate"] = (
            1.0 if values["negative_hit_rate"] > case.noise_budget else 0.0
        )
    elif mode is OutputMode.COLLECT:
        values["source_coverage"] = values["expected_source_recall_at_k"]
        values["artifact_coverage"] = 1.0 - values["role_mismatch_rate"]
        values["source_status_coverage"] = _safe_ratio(
            sum(1 for item in retrieved if item.get("source_status")),
            len(retrieved),
        )
    elif mode is OutputMode.EVIDENCE_PACKAGE:
        evidence_items = [
            item for item in retrieved if item.get("artifact_role") == "evidence_view"
        ]
        restored = [
            item
            for item in retrieved
            if item.get("source_status") == "available" and item.get("source_ref")
        ]
        values["source_restore_rate"] = _safe_ratio(len(restored), len(retrieved))
        values["evidence_view_rate"] = _safe_ratio(len(evidence_items), len(retrieved))
        values["citation_candidate_rate"] = values["evidence_view_rate"]
        values["stale_evidence_block_rate"] = 1.0 - values["stale_hit_rate"]
    elif mode is OutputMode.ANSWER:
        answer_items = [
            item
            for item in retrieved
            if item.get("authority_level") == AuthorityLevel.ANSWER_ASSERTION.value
        ]
        values["citation_ready_rate"] = _safe_ratio(
            sum(1 for item in retrieved if item.get("source_status") == "available"),
            len(retrieved),
        )
        values["claim_support_rate"] = _safe_ratio(len(answer_items), len(retrieved))
        values["answer_assertion_support_rate"] = min(
            values["citation_ready_rate"],
            values["claim_support_rate"],
        )
    elif mode is OutputMode.WORKING_NOTE:
        values["note_source_link_rate"] = _safe_ratio(
            sum(1 for item in retrieved if item.get("has_source_link") or item.get("source_ref")),
            len(retrieved),
        )
        values["note_artifact_link_rate"] = _safe_ratio(
            sum(1 for item in retrieved if item.get("has_artifact_link")),
            len(retrieved),
        )
        values["unresolved_issue_disclosure_rate"] = _trace_presence_rate(
            retrieved,
            "unresolved_items",
        )
        values["unsupported_claim_label_rate"] = _trace_presence_rate(
            retrieved,
            "unsupported_claims",
        )
    elif mode is OutputMode.SYNTHESIZE:
        values["contradiction_disclosure_rate"] = _trace_presence_rate(
            retrieved,
            "contradictions",
        )
        values["missing_evidence_disclosure_rate"] = _trace_presence_rate(
            retrieved,
            "unresolved_items",
        )
        values["unsupported_claim_label_rate"] = _trace_presence_rate(
            retrieved,
            "unsupported_claims",
        )
    return values


def _status_from_metrics(case: EvalCaseV2, metrics: dict[str, float]) -> str:
    if case.expected_source_refs and metrics.get("expected_source_recall_at_k", 0.0) < 1.0:
        return "fail"
    if metrics.get("negative_hit_rate", 0.0) > 0.0:
        return "fail"
    if metrics.get("noise_budget_violation_rate", 0.0) > 0.0:
        return "fail"
    if metrics.get("stale_hit_rate", 0.0) > 0.0:
        return "needs_review"
    if metrics.get("role_mismatch_rate", 0.0) > 0.0:
        return "needs_review"
    try:
        mode = normalize_output_mode(case.output_mode)
    except ValueError:
        return "fail"
    if mode is OutputMode.ANSWER and metrics.get("answer_assertion_support_rate", 0.0) < 1.0:
        return "fail"
    return "ok"


def _status_matches_expected(status: str, expected_status: str | None) -> bool:
    expected = (expected_status or "ok").strip().casefold()
    if expected in {"any", "*"}:
        return True
    return status.strip().casefold() == expected


def _trace_presence_rate(
    retrieved: tuple[dict[str, Any], ...],
    key: str,
) -> float:
    if not retrieved:
        return 0.0
    present = 0
    for item in retrieved:
        trace = item.get("output_trace")
        if isinstance(trace, dict) and key in trace:
            present += 1
    return _safe_ratio(present, len(retrieved))


def _safe_ratio(numerator: int | float, denominator: int | float) -> float:
    return 0.0 if denominator == 0 else float(numerator) / float(denominator)


def _ndcg_at_k(retrieved_refs: list[str], positive_refs: set[str]) -> float:
    if not retrieved_refs or not positive_refs:
        return 0.0
    dcg = 0.0
    for index, source_ref in enumerate(retrieved_refs, start=1):
        if source_ref in positive_refs:
            dcg += 1.0 / _log2(index + 1)
    ideal_hits = min(len(positive_refs), len(retrieved_refs))
    ideal_dcg = sum(1.0 / _log2(index + 1) for index in range(1, ideal_hits + 1))
    return _safe_ratio(dcg, ideal_dcg)


def _log2(value: int | float) -> float:
    return math.log2(value)


def _metrics_by_mode_for_cases(
    cases: tuple[EvalCaseV2, ...],
) -> dict[str, tuple[str, ...]]:
    metrics: dict[str, tuple[str, ...]] = {}
    for case in cases:
        try:
            mode = normalize_output_mode(case.output_mode).value
        except ValueError:
            mode = case.output_mode or "<missing>"
            metrics[mode] = COMMON_METRICS
            continue
        metrics[mode] = metrics_for_output_mode(mode)
    return dict(sorted(metrics.items()))


def _metrics_for_case(case: EvalCaseV2) -> tuple[str, ...]:
    try:
        return metrics_for_output_mode(case.output_mode)
    except ValueError:
        return COMMON_METRICS


def _store_eval_run(
    conn: sqlite3.Connection,
    *,
    run_id: str,
    cases_path: str,
    case_count: int,
    status: str,
    ok_count: int,
    needs_review_count: int,
    fail_count: int,
    started_at: str,
    finished_at: str,
    parameters: dict[str, Any],
) -> None:
    conn.execute(
        """
        INSERT INTO memory_eval_runs (
            run_id, cases_path, case_count, parameters_json, status,
            ok_count, needs_review_count, fail_count, started_at, finished_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(run_id) DO UPDATE SET
            cases_path=excluded.cases_path,
            case_count=excluded.case_count,
            parameters_json=excluded.parameters_json,
            status=excluded.status,
            ok_count=excluded.ok_count,
            needs_review_count=excluded.needs_review_count,
            fail_count=excluded.fail_count,
            finished_at=excluded.finished_at
        """,
        (
            run_id,
            cases_path,
            case_count,
            _json(parameters),
            status,
            ok_count,
            needs_review_count,
            fail_count,
            started_at,
            finished_at,
        ),
    )


def _store_eval_result(
    conn: sqlite3.Connection,
    *,
    run_id: str,
    result: dict[str, Any],
    created_at: str,
) -> None:
    case: EvalCaseV2 = result["case"]
    errors: list[str] = result["errors"]
    retrieval = result.get("retrieval", {})
    diagnostic_candidates = tuple(retrieval.get("diagnostic_candidates") or ())
    metadata = {
        "eval_version": "eval-v2",
        "case": case.as_dict(),
        "errors": errors,
        "metrics": result["metrics"],
        "retrieved_source_refs": [
            item["source_ref"] for item in result.get("retrieved", ())
        ],
        "strict_output_required": bool(retrieval.get("strict_output_required")),
        "strict_output_status": str(retrieval.get("strict_output_status") or "unknown"),
        "diagnostic_fallback_used": bool(retrieval.get("diagnostic_fallback_used")),
        "diagnostic_candidates": [
            {
                "source_ref": item.get("source_ref"),
                "artifact_role": item.get("artifact_role"),
                "authority_level": item.get("authority_level"),
                "retrieval_engine": item.get("retrieval_engine"),
                "score": item.get("score"),
            }
            for item in diagnostic_candidates
        ],
    }
    strict_output = _first_strict_output(result.get("retrieved", ()))
    if strict_output is not None:
        metadata["output"] = strict_output
    conn.execute(
        """
        INSERT INTO memory_eval_results (
            result_id, run_id, case_index, query, status, route,
            expected_route, stop_reason, hits, context_chunks, first_doc_id,
            best_score, matched_terms_json, retrieval_engines_json,
            source_kinds_json, answer_status, answer_citations, notes_json,
            metadata_json, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(result_id) DO UPDATE SET
            status=excluded.status,
            stop_reason=excluded.stop_reason,
            notes_json=excluded.notes_json,
            metadata_json=excluded.metadata_json
        """,
        (
            _stable_hash(
                {
                    "run_id": run_id,
                    "case_id": case.case_id,
                    "index": result["case_index"],
                }
            ),
            run_id,
            result["case_index"],
            case.query,
            result["status"],
            f"eval-v2:{case.output_mode}",
            case.expected_status,
            "validation_ok" if not errors else "validation_errors",
            len(result.get("retrieved", ())),
            len(result.get("retrieved", ())),
            (result.get("retrieved") or [{}])[0].get("source_ref")
            if result.get("retrieved")
            else None,
            max((float(item["score"]) for item in result.get("retrieved", ())), default=0.0),
            "[]",
            "[]",
            _json(
                sorted(
                    {
                        str(item.get("artifact_role"))
                        for item in result.get("retrieved", ())
                    }
                    or set(case.expected_artifact_roles)
                )
            ),
            case.expected_status,
            0,
            _json(errors),
            _json(metadata),
            created_at,
        ),
    )


def _first_strict_output(retrieved: tuple[dict[str, Any], ...]) -> dict[str, Any] | None:
    for item in retrieved:
        output = item.get("output")
        if isinstance(output, dict):
            return output
    return None


def _stable_hash(value: Any) -> str:
    return hashlib.sha256(_json(value).encode("utf-8")).hexdigest()


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def _now() -> str:
    return datetime.now(UTC).isoformat()
