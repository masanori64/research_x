from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from research_x.memory.query import QueryPlan, build_query_plan
from research_x.memory.research_artifacts import build_pre_execution_artifacts
from research_x.memory.schema import ensure_memory_schema
from research_x.memory.workflow import WorkflowRoute, plan_workflow_route

OBJECTIVE_ROUTE_VERSION = "objective-route-v1"


@dataclass(frozen=True)
class ObjectiveRoutePlan:
    query: str
    objective_route_version: str
    eval_question_type: str
    primary_route: str
    fallback_routes: tuple[str, ...]
    must_run_guards: tuple[str, ...]
    escalation_triggers: tuple[str, ...]
    stop_conditions: tuple[str, ...]
    budget_policy: str
    planned_provider_roles: tuple[str, ...]
    workflow_route: WorkflowRoute
    query_plan: QueryPlan
    reasoning: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["workflow_route"] = self.workflow_route.as_dict()
        payload["query_plan"] = self.query_plan.as_dict()
        payload.update(build_pre_execution_artifacts(self))
        return payload


def plan_objective_routes(
    query: str,
    *,
    requested_route: str = "auto",
    budget_policy: str = "default",
) -> ObjectiveRoutePlan:
    query_plan = build_query_plan(query)
    workflow_route = plan_workflow_route(query_plan, requested_route=requested_route)
    route_id = workflow_route.route
    intents = set(query_plan.intents)

    if route_id == "media_context" or "media" in intents:
        return _objective_plan(
            query=query,
            query_plan=query_plan,
            workflow_route=workflow_route,
            eval_question_type="media_grounded",
            primary_route="media_evidence",
            fallback_routes=(
                "exact_metadata_social",
                "semantic_embedding_portfolio",
                "candidate_a_current_baseline",
            ),
            must_run_guards=(
                "source_bundle_restore",
                "citation_required",
                "no_unsupported_media_content_claims",
                "api_budget_guard",
            ),
            escalation_triggers=(
                "ocr_quality_pipeline",
                "media_hit_without_media_content_evidence",
                "tweet_text_insufficient_for_visual_claim",
                "ocr_empty_but_text_density_high",
                "ocr_low_confidence",
                "route_eval_missing_media_grounded_answer",
            ),
            stop_conditions=(
                "media_content_evidence_with_citation_ready_chunk",
                "media_source_only_candidate_returned_without_visual_claim",
                "budget_exhausted",
                "no_restorable_media_source_bundle",
            ),
            budget_policy=budget_policy,
            planned_provider_roles=(
                "index_provider",
                "media_embedding",
                "ocr",
                "context_builder",
            ),
            reasoning={
                "selection": "media route requires OCR Evidence Quality Pipeline escalation",
                "route_source": route_id,
                "intents": tuple(sorted(intents)),
            },
        )

    if route_id in {"place_recall", "event_recall", "cross_account"}:
        return _objective_plan(
            query=query,
            query_plan=query_plan,
            workflow_route=workflow_route,
            eval_question_type="single_fact_conditioned",
            primary_route="exact_metadata_social",
            fallback_routes=("candidate_a_current_baseline", "semantic_embedding_portfolio"),
            must_run_guards=("source_bundle_restore", "citation_required", "api_budget_guard"),
            escalation_triggers=(
                "no_exact_or_metadata_hit",
                "low_result_count",
                "ambiguous_entity_or_place",
            ),
            stop_conditions=(
                "enough_cited_exact_evidence",
                "no_local_evidence",
                "budget_exhausted",
            ),
            budget_policy=budget_policy,
            planned_provider_roles=("index_provider", "context_builder"),
            reasoning={
                "selection": "exact anchors should run before dense recall",
                "route_source": route_id,
            },
        )

    if route_id == "current_fact_check":
        return _objective_plan(
            query=query,
            query_plan=query_plan,
            workflow_route=workflow_route,
            eval_question_type="temporal_freshness",
            primary_route="candidate_a_current_baseline",
            fallback_routes=("external_web_context", "bounded_agentic_workflow"),
            must_run_guards=("source_bundle_restore", "citation_required", "freshness_lineage"),
            escalation_triggers=(
                "needs_current_external_grounding",
                "contradiction_or_obsolete_signal",
            ),
            stop_conditions=("freshness_supported", "external_context_needed", "budget_exhausted"),
            budget_policy=budget_policy,
            planned_provider_roles=("index_provider", "fetch_agent", "llm_context_provider"),
            reasoning={"selection": "freshness needs local evidence plus external grounding"},
        )

    if route_id == "learning_map":
        return _objective_plan(
            query=query,
            query_plan=query_plan,
            workflow_route=workflow_route,
            eval_question_type="exploratory_map",
            primary_route="skill_map",
            fallback_routes=("graph_sensemaking", "semantic_embedding_portfolio"),
            must_run_guards=("source_bundle_restore", "map_is_not_evidence", "citation_required"),
            escalation_triggers=(
                "map_has_unsupported_claim",
                "missing_topic_cluster",
                "low_citation_coverage",
            ),
            stop_conditions=("map_with_cited_sources", "no_local_evidence", "budget_exhausted"),
            budget_policy=budget_policy,
            planned_provider_roles=("index_provider", "context_builder", "reranker"),
            reasoning={"selection": "exploratory routes use maps for navigation, not proof"},
        )

    if route_id == "quote_context":
        eval_type = "multi_hop_evidence"
    elif route_id == "author_stance":
        eval_type = "comparison"
    else:
        eval_type = "citation_required"
    return _objective_plan(
        query=query,
        query_plan=query_plan,
        workflow_route=workflow_route,
        eval_question_type=eval_type,
        primary_route="candidate_a_current_baseline",
        fallback_routes=("rerank_after_bundle", "semantic_embedding_portfolio"),
        must_run_guards=("source_bundle_restore", "citation_required", "api_budget_guard"),
        escalation_triggers=(
            "low_citation_precision",
            "ambiguous_context",
            "missing_required_relation",
        ),
        stop_conditions=("enough_cited_evidence", "no_local_evidence", "budget_exhausted"),
        budget_policy=budget_policy,
        planned_provider_roles=("index_provider", "context_builder", "reranker"),
        reasoning={"selection": "default objective plan preserves current baseline with fallbacks"},
    )


def store_objective_route_plan(db_path: str | Path, plan: ObjectiveRoutePlan) -> str:
    route_run_id = _route_run_id(plan.query, plan.primary_route)
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
                json.dumps((plan.primary_route,), ensure_ascii=False),
                None,
                "planned",
                now,
                now,
                json.dumps(plan.as_dict(), ensure_ascii=False, sort_keys=True),
            ),
        )
        conn.commit()
    return route_run_id


def objective_route_plan_json(plan: ObjectiveRoutePlan) -> str:
    return json.dumps(plan.as_dict(), ensure_ascii=False, indent=2, sort_keys=True)


def format_objective_route_plan(plan: ObjectiveRoutePlan) -> str:
    return "\n".join(
        (
            f"query: {plan.query}",
            f"question_type: {plan.eval_question_type}",
            f"primary_route: {plan.primary_route}",
            f"fallback_routes: {', '.join(plan.fallback_routes) or '-'}",
            f"must_run_guards: {', '.join(plan.must_run_guards) or '-'}",
            f"escalation_triggers: {', '.join(plan.escalation_triggers) or '-'}",
            f"stop_conditions: {', '.join(plan.stop_conditions) or '-'}",
            f"provider_roles: {', '.join(plan.planned_provider_roles) or '-'}",
            f"legacy_workflow_route: {plan.workflow_route.route}",
        )
    )


def _objective_plan(
    *,
    query: str,
    query_plan: QueryPlan,
    workflow_route: WorkflowRoute,
    eval_question_type: str,
    primary_route: str,
    fallback_routes: tuple[str, ...],
    must_run_guards: tuple[str, ...],
    escalation_triggers: tuple[str, ...],
    stop_conditions: tuple[str, ...],
    budget_policy: str,
    planned_provider_roles: tuple[str, ...],
    reasoning: dict[str, Any],
) -> ObjectiveRoutePlan:
    return ObjectiveRoutePlan(
        query=query,
        objective_route_version=OBJECTIVE_ROUTE_VERSION,
        eval_question_type=eval_question_type,
        primary_route=primary_route,
        fallback_routes=fallback_routes,
        must_run_guards=must_run_guards,
        escalation_triggers=escalation_triggers,
        stop_conditions=stop_conditions,
        budget_policy=budget_policy,
        planned_provider_roles=planned_provider_roles,
        workflow_route=workflow_route,
        query_plan=query_plan,
        reasoning=reasoning,
    )


def _route_run_id(query: str, primary_route: str) -> str:
    raw = f"{query}\0{primary_route}\0{_utc_now()}".encode()
    import hashlib

    return f"route-{hashlib.sha256(raw).hexdigest()[:16]}"


def _utc_now() -> str:
    return datetime.now(tz=UTC).isoformat()
