from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from research_x.memory.context import ContextBundle, build_context_bundle
from research_x.memory.media_roles import estimate_media_roles
from research_x.memory.objective_routes import ObjectiveRoutePlan, plan_objective_routes
from research_x.memory.ocr import build_ocr_evidence, estimate_ocr_evidence, ocr_search
from research_x.memory.schema import ensure_memory_schema
from research_x.memory.workflow import MemoryWorkflow, run_memory_workflow

OBJECTIVE_EXECUTION_VERSION = "objective-route-execution-v1"
PROVIDER_FROZEN_ARMS = {
    "semantic_embedding_portfolio",
    "rerank_after_bundle",
    "external_web_context",
    "managed_rag_reference",
    "bounded_agentic_workflow",
}


@dataclass(frozen=True)
class ObjectiveRouteArmResult:
    route_arm: str
    status: str
    evidence_count: int
    citation_count: int
    stop_condition: str | None
    escalation_trigger: str | None
    provider_quota_skipped: bool
    output: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ObjectiveRouteExecution:
    route_run_id: str
    query: str
    status: str
    stop_reason: str
    selected_routes: tuple[str, ...]
    plan: ObjectiveRoutePlan
    arm_results: tuple[ObjectiveRouteArmResult, ...]
    metadata: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {
            "route_run_id": self.route_run_id,
            "query": self.query,
            "status": self.status,
            "stop_reason": self.stop_reason,
            "selected_routes": list(self.selected_routes),
            "plan": self.plan.as_dict(),
            "arm_results": [result.as_dict() for result in self.arm_results],
            "metadata": self.metadata,
        }


def run_objective_route_execution(
    db_path: str | Path,
    query: str,
    *,
    route: str = "auto",
    budget_policy: str = "default",
    limit: int = 5,
    account: str | None = None,
    max_route_arms: int = 4,
    ocr_mode: str = "stored",
    ocr_limit: int = 10,
    ocr_sample_policy: str = "candidate_set",
    ocr_max_file_bytes: int = 20 * 1024 * 1024,
    store: bool = True,
) -> ObjectiveRouteExecution:
    path = Path(db_path)
    if not path.exists():
        raise FileNotFoundError(f"database not found: {path}")
    plan = plan_objective_routes(
        query,
        requested_route=route,
        budget_policy=budget_policy,
    )
    route_run_id = _route_run_id(query, plan.primary_route)
    selected_routes = _route_order(plan, max_route_arms=max_route_arms)
    if store:
        _insert_route_run(path, route_run_id=route_run_id, plan=plan)

    results: list[ObjectiveRouteArmResult] = []
    stop_reason = "no_local_evidence"
    status = "needs_review"
    for index, route_arm in enumerate(selected_routes):
        result = _execute_arm(
            path,
            plan,
            route_arm,
            limit=limit,
            account=account,
            store=store,
            ocr_mode=ocr_mode,
            ocr_limit=ocr_limit,
            ocr_sample_policy=ocr_sample_policy,
            ocr_max_file_bytes=ocr_max_file_bytes,
        )
        results.append(result)
        if store:
            _store_route_step(path, route_run_id=route_run_id, step_index=index, result=result)
        if _should_stop(plan, result):
            stop_reason = result.stop_condition or "enough_cited_evidence"
            status = "ok" if result.citation_count > 0 else "needs_review"
            break
        if result.escalation_trigger and result.escalation_trigger not in selected_routes:
            # The trigger is recorded as an audit signal. We do not mutate the route order here
            # because provider-backed escalations are blocked by the no-quota policy.
            stop_reason = result.escalation_trigger

    if results and status != "ok":
        best = max(results, key=lambda item: (item.citation_count, item.evidence_count))
        if best.evidence_count > 0:
            stop_reason = best.stop_condition or best.escalation_trigger or "needs_review"

    skipped_provider_roles = [
        result.route_arm for result in results if result.provider_quota_skipped
    ]
    fallback_routes_used = [
        result.route_arm for result in results if result.route_arm != plan.primary_route
    ]
    source_bundle_restoration_failures = sum(
        int(result.output.get("source_bundle_restoration_failures", 0))
        for result in results
    )
    metadata = {
        "execution_version": OBJECTIVE_EXECUTION_VERSION,
        "provider_quota_frozen": True,
        "no_quota_policy": "provider arms are skipped unless local/fake",
        "evaluated_route_count": len(results),
        "guarded_fusion": {
            "candidate_routes": list(selected_routes),
            "executed_routes": [result.route_arm for result in results],
            "fusion_scope": "source_bundle_restored_local_arms",
            "raw_score_averaging": False,
        },
        "fallback_routes_used": fallback_routes_used,
        "skipped_provider_roles": skipped_provider_roles,
        "source_bundle_restoration_failures": source_bundle_restoration_failures,
    }
    execution = ObjectiveRouteExecution(
        route_run_id=route_run_id,
        query=query,
        status=status,
        stop_reason=stop_reason,
        selected_routes=selected_routes[: len(results)],
        plan=plan,
        arm_results=tuple(results),
        metadata=metadata,
    )
    if store:
        _finish_route_run(path, execution)
    return execution


def objective_route_execution_json(execution: ObjectiveRouteExecution) -> str:
    return json.dumps(execution.as_dict(), ensure_ascii=False, indent=2, sort_keys=True)


def format_objective_route_execution(execution: ObjectiveRouteExecution) -> str:
    lines = [
        (
            f"objective_execution: {execution.route_run_id} status={execution.status} "
            f"stop={execution.stop_reason}"
        ),
        f"primary_route: {execution.plan.primary_route}",
        f"selected_routes: {', '.join(execution.selected_routes) or '-'}",
    ]
    for index, result in enumerate(execution.arm_results):
        quota = " quota_skipped" if result.provider_quota_skipped else ""
        lines.append(
            f"arm {index}: {result.route_arm} status={result.status} "
            f"evidence={result.evidence_count} citations={result.citation_count} "
            f"stop={result.stop_condition or '-'} escalation={result.escalation_trigger or '-'}"
            f"{quota}"
        )
    return "\n".join(lines)


def _execute_arm(
    db_path: Path,
    plan: ObjectiveRoutePlan,
    route_arm: str,
    *,
    limit: int,
    account: str | None,
    store: bool,
    ocr_mode: str,
    ocr_limit: int,
    ocr_sample_policy: str,
    ocr_max_file_bytes: int,
) -> ObjectiveRouteArmResult:
    if route_arm == "candidate_a_current_baseline":
        return _execute_current_baseline(db_path, plan, limit=limit, account=account, store=store)
    if route_arm == "exact_metadata_social":
        return _execute_context_arm(
            db_path,
            plan,
            route_arm=route_arm,
            limit=limit,
            account=account,
            doc_type=None,
            store=store,
        )
    if route_arm == "media_evidence":
        return _execute_media_arm(
            db_path,
            plan,
            limit=limit,
            account=account,
            store=store,
            ocr_mode=ocr_mode,
            ocr_limit=ocr_limit,
            ocr_sample_policy=ocr_sample_policy,
            ocr_max_file_bytes=ocr_max_file_bytes,
        )
    if route_arm == "skill_map":
        return _execute_context_arm(
            db_path,
            plan,
            route_arm=route_arm,
            limit=limit,
            account=account,
            doc_type="topic_thread",
            store=store,
        )
    if route_arm == "graph_sensemaking":
        return _execute_context_arm(
            db_path,
            plan,
            route_arm=route_arm,
            limit=limit,
            account=account,
            doc_type=None,
            store=store,
        )
    if route_arm in PROVIDER_FROZEN_ARMS:
        return _skipped_arm(route_arm, reason="no_quota_provider_freeze")
    return _skipped_arm(route_arm, reason="unknown_or_unimplemented_route_arm")


def _execute_current_baseline(
    db_path: Path,
    plan: ObjectiveRoutePlan,
    *,
    limit: int,
    account: str | None,
    store: bool,
) -> ObjectiveRouteArmResult:
    workflow = run_memory_workflow(
        db_path,
        plan.query,
        route=plan.workflow_route.route,
        limit=limit,
        account=account,
        semantic_provider=None,
        llm_context_provider="none",
        answer_provider="none",
        external_reader_provider="fake",
        max_steps=3,
        store=store,
    )
    return _result_from_workflow("candidate_a_current_baseline", workflow)


def _execute_context_arm(
    db_path: Path,
    plan: ObjectiveRoutePlan,
    *,
    route_arm: str,
    limit: int,
    account: str | None,
    doc_type: str | None,
    store: bool,
) -> ObjectiveRouteArmResult:
    try:
        bundle = build_context_bundle(
            db_path,
            plan.query,
            limit=limit,
            doc_type=doc_type,
            account=account,
            semantic_provider=None,
            external_reader_provider="fake",
            store=store,
        )
    except RuntimeError as exc:
        return ObjectiveRouteArmResult(
            route_arm=route_arm,
            status="error",
            evidence_count=0,
            citation_count=0,
            stop_condition="no_local_evidence",
            escalation_trigger=None,
            provider_quota_skipped=False,
            output={"error": str(exc)},
        )
    return _result_from_context_bundle(route_arm, bundle)


def _execute_media_arm(
    db_path: Path,
    plan: ObjectiveRoutePlan,
    *,
    limit: int,
    account: str | None,
    store: bool,
    ocr_mode: str,
    ocr_limit: int,
    ocr_sample_policy: str,
    ocr_max_file_bytes: int,
) -> ObjectiveRouteArmResult:
    try:
        bundle = build_context_bundle(
            db_path,
            plan.query,
            limit=limit,
            doc_type="media_doc",
            account=account,
            semantic_provider=None,
            external_reader_provider="fake",
            store=store,
        )
    except RuntimeError as exc:
        return ObjectiveRouteArmResult(
            route_arm="media_evidence",
            status="error",
            evidence_count=0,
            citation_count=0,
            stop_condition="no_local_evidence",
            escalation_trigger=None,
            provider_quota_skipped=False,
            output={"error": str(exc)},
        )
    context_result = _result_from_context_bundle("media_evidence", bundle)
    candidate_media_ids = _media_ids_from_hits(bundle.retrieved_hits, limit=ocr_limit)
    ocr_hits = ocr_search(db_path, plan.query, limit=limit)
    content_hits = tuple(
        hit for hit in ocr_hits if hit.get("bundle", {}).get("media_content_evidence")
    )
    if content_hits:
        output = {
            **context_result.output,
            "ocr_hits": len(ocr_hits),
            "media_content_hits": len(content_hits),
        }
        return ObjectiveRouteArmResult(
            route_arm="media_evidence",
            status="ok",
            evidence_count=context_result.evidence_count + len(content_hits),
            citation_count=context_result.citation_count + len(content_hits),
            stop_condition="media_content_evidence_with_citation_ready_chunk",
            escalation_trigger=None,
            provider_quota_skipped=False,
            output=output,
        )
    ocr_build: dict[str, Any] | None = None
    if ocr_mode == "fake" and candidate_media_ids and store:
        summary = build_ocr_evidence(
            db_path,
            provider="fake",
            sample_policy=ocr_sample_policy,
            limit=ocr_limit,
            max_file_bytes=ocr_max_file_bytes,
            media_ids=candidate_media_ids,
        )
        ocr_build = summary.as_dict()
        ocr_hits = ocr_search(db_path, plan.query, limit=limit)
        content_hits = tuple(
            hit for hit in ocr_hits if hit.get("bundle", {}).get("media_content_evidence")
        )
        if content_hits:
            output = {
                **context_result.output,
                "candidate_media_ids": list(candidate_media_ids),
                "ocr_mode": ocr_mode,
                "ocr_build": ocr_build,
                "ocr_hits": len(ocr_hits),
                "media_content_hits": len(content_hits),
            }
            return ObjectiveRouteArmResult(
                route_arm="media_evidence",
                status="ok",
                evidence_count=context_result.evidence_count + len(content_hits),
                citation_count=context_result.citation_count + len(content_hits),
                stop_condition="media_content_evidence_with_citation_ready_chunk",
                escalation_trigger=None,
                provider_quota_skipped=False,
                output=output,
            )
    estimate = estimate_ocr_evidence(
        db_path,
        sample_policy=ocr_sample_policy if candidate_media_ids else "stratified",
        limit=max(limit, 10),
        max_file_bytes=ocr_max_file_bytes,
        media_ids=candidate_media_ids,
    )
    role_estimate = estimate_media_roles(db_path, limit=max(limit, 10))
    output = {
        **context_result.output,
        "candidate_media_ids": list(candidate_media_ids),
        "ocr_mode": ocr_mode,
        "ocr_build": ocr_build,
        "ocr_hits": len(ocr_hits),
        "media_content_hits": 0,
        "ocr_estimate": estimate.as_dict(),
        "media_role_estimate": role_estimate.as_dict(),
    }
    if ocr_mode == "fake" and candidate_media_ids and not store:
        output["ocr_build_skipped"] = "store_false_prevents_fixture_mutation"
    evidence_count = context_result.evidence_count + len(ocr_hits)
    return ObjectiveRouteArmResult(
        route_arm="media_evidence",
        status="needs_escalation" if evidence_count else "needs_review",
        evidence_count=evidence_count,
        citation_count=context_result.citation_count,
        stop_condition=(
            "media_source_only_candidate_returned_without_visual_claim"
            if evidence_count
            else "no_local_evidence"
        ),
        escalation_trigger="ocr_quality_pipeline",
        provider_quota_skipped=False,
        output=output,
    )


def _media_ids_from_hits(hits: list[dict[str, Any]], *, limit: int) -> tuple[str, ...]:
    media_ids: list[str] = []
    for hit in hits:
        doc_id = str(hit.get("doc_id") or "")
        if doc_id.startswith("media:"):
            media_id = doc_id.split(":", 1)[1]
            if media_id and media_id not in media_ids:
                media_ids.append(media_id)
        if len(media_ids) >= max(0, limit):
            break
    return tuple(media_ids)


def _result_from_workflow(route_arm: str, workflow: MemoryWorkflow) -> ObjectiveRouteArmResult:
    bundle = workflow.context_bundle
    evidence_count = len(bundle.context_chunks) if bundle else 0
    citation_count = len(bundle.citation_annotations) if bundle else 0
    return ObjectiveRouteArmResult(
        route_arm=route_arm,
        status=workflow.status,
        evidence_count=evidence_count,
        citation_count=citation_count,
        stop_condition=workflow.stop_reason,
        escalation_trigger=None,
        provider_quota_skipped=False,
        output={
            "workflow_id": workflow.workflow_id,
            "route": workflow.route,
            "status": workflow.status,
            "stop_reason": workflow.stop_reason,
            "context_chunks": evidence_count,
            "citations": citation_count,
        },
    )


def _result_from_context_bundle(
    route_arm: str,
    bundle: ContextBundle,
) -> ObjectiveRouteArmResult:
    evidence_count = len(bundle.context_chunks)
    citation_count = len(bundle.citation_annotations)
    return ObjectiveRouteArmResult(
        route_arm=route_arm,
        status="ok" if evidence_count else "needs_review",
        evidence_count=evidence_count,
        citation_count=citation_count,
        stop_condition="enough_cited_evidence" if citation_count else "no_local_evidence",
        escalation_trigger=None if citation_count else "low_citation_precision",
        provider_quota_skipped=False,
        output={
            "context_run_id": bundle.run_id,
            "hits": len(bundle.retrieved_hits),
            "context_chunks": evidence_count,
            "citations": citation_count,
            "doc_types": _doc_types_from_hits(bundle.retrieved_hits),
            "source_bundle_restoration_failures": _source_bundle_restoration_failures(
                bundle.retrieved_hits
            ),
        },
    )


def _source_bundle_restoration_failures(hits: list[dict[str, Any]]) -> int:
    failures = 0
    for hit in hits:
        if not hit.get("doc_id"):
            failures += 1
            continue
        metadata = hit.get("metadata") or {}
        if isinstance(metadata, dict) and metadata.get("source_bundle_error"):
            failures += 1
    return failures


def _skipped_arm(route_arm: str, *, reason: str) -> ObjectiveRouteArmResult:
    return ObjectiveRouteArmResult(
        route_arm=route_arm,
        status="skipped",
        evidence_count=0,
        citation_count=0,
        stop_condition=None,
        escalation_trigger=reason,
        provider_quota_skipped=reason == "no_quota_provider_freeze",
        output={"reason": reason},
    )


def _should_stop(plan: ObjectiveRoutePlan, result: ObjectiveRouteArmResult) -> bool:
    if result.provider_quota_skipped:
        return False
    if result.stop_condition == "budget_exhausted":
        return True
    if result.stop_condition == "external_context_needed":
        return False
    if result.citation_count <= 0:
        return False
    if result.stop_condition in plan.stop_conditions:
        return True
    return result.stop_condition in {
        "enough_cited_evidence",
        "enough_evidence",
        "enough_cited_exact_evidence",
        "media_content_evidence_with_citation_ready_chunk",
        "map_with_cited_sources",
    }


def _route_order(plan: ObjectiveRoutePlan, *, max_route_arms: int) -> tuple[str, ...]:
    routes: list[str] = []
    for route in (plan.primary_route, *plan.fallback_routes):
        if route not in routes:
            routes.append(route)
    return tuple(routes[: max(1, max_route_arms)])


def _insert_route_run(db_path: Path, *, route_run_id: str, plan: ObjectiveRoutePlan) -> None:
    now = _utc_now()
    with sqlite3.connect(db_path, timeout=60) as conn:
        ensure_memory_schema(conn)
        conn.execute(
            """
            INSERT INTO memory_objective_route_runs (
                route_run_id, query, objective_route_version, eval_question_type,
                primary_route, fallback_routes_json, must_run_guards_json,
                escalation_triggers_json, stop_conditions_json, budget_policy,
                planned_provider_roles_json, selected_routes_json, stop_reason,
                status, created_at, updated_at, metadata_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                route_run_id,
                plan.query,
                plan.objective_route_version,
                plan.eval_question_type,
                plan.primary_route,
                json.dumps(plan.fallback_routes, ensure_ascii=False),
                json.dumps(plan.must_run_guards, ensure_ascii=False),
                json.dumps(plan.escalation_triggers, ensure_ascii=False),
                json.dumps(plan.stop_conditions, ensure_ascii=False),
                plan.budget_policy,
                json.dumps(plan.planned_provider_roles, ensure_ascii=False),
                json.dumps((), ensure_ascii=False),
                None,
                "running",
                now,
                now,
                json.dumps(plan.as_dict(), ensure_ascii=False, sort_keys=True),
            ),
        )
        conn.commit()


def _store_route_step(
    db_path: Path,
    *,
    route_run_id: str,
    step_index: int,
    result: ObjectiveRouteArmResult,
) -> None:
    with sqlite3.connect(db_path, timeout=60) as conn:
        ensure_memory_schema(conn)
        conn.execute(
            """
            INSERT INTO memory_objective_route_steps (
                route_step_id, route_run_id, step_index, route_arm, status,
                evidence_count, citation_count, stop_condition, escalation_trigger,
                provider_quota_skipped, output_json, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                _route_step_id(route_run_id, step_index, result.route_arm),
                route_run_id,
                step_index,
                result.route_arm,
                result.status,
                result.evidence_count,
                result.citation_count,
                result.stop_condition,
                result.escalation_trigger,
                int(result.provider_quota_skipped),
                json.dumps(result.output, ensure_ascii=False, sort_keys=True),
                _utc_now(),
            ),
        )
        conn.commit()


def _finish_route_run(db_path: Path, execution: ObjectiveRouteExecution) -> None:
    with sqlite3.connect(db_path, timeout=60) as conn:
        ensure_memory_schema(conn)
        conn.execute(
            """
            UPDATE memory_objective_route_runs
            SET status = ?, stop_reason = ?, selected_routes_json = ?, updated_at = ?,
                metadata_json = ?
            WHERE route_run_id = ?
            """,
            (
                execution.status,
                execution.stop_reason,
                json.dumps(execution.selected_routes, ensure_ascii=False),
                _utc_now(),
                json.dumps(execution.as_dict(), ensure_ascii=False, sort_keys=True),
                execution.route_run_id,
            ),
        )
        conn.commit()


def _doc_types_from_hits(hits: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for hit in hits:
        doc_type = str(hit.get("doc_type") or "unknown")
        counts[doc_type] = counts.get(doc_type, 0) + 1
    return counts


def _route_run_id(query: str, primary_route: str) -> str:
    raw = f"{query}\0{primary_route}\0{_utc_now()}".encode()
    return f"objective-{hashlib.sha256(raw).hexdigest()[:16]}"


def _route_step_id(route_run_id: str, step_index: int, route_arm: str) -> str:
    raw = f"{route_run_id}\0{step_index}\0{route_arm}".encode()
    return f"objective-step-{hashlib.sha256(raw).hexdigest()[:16]}"


def _utc_now() -> str:
    return datetime.now(tz=UTC).isoformat()
