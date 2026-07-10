from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from research_x.memory.output_modes import OutputMode, normalize_output_mode
from research_x.memory.query import QueryPlan, build_query_plan
from research_x.memory.research_artifacts import build_pre_execution_artifacts
from research_x.memory.schema import ensure_memory_schema
from research_x.memory.workflow import WorkflowRoute, plan_workflow_route

OBJECTIVE_ROUTE_VERSION = "objective-route-v1"
ROUTE_AWARE_RETRIEVAL_VERSION = "route-aware-typed-retrieval-v1"
ROUTE_AWARE_LOCAL_BASELINE_ENGINES = (
    "fts",
    "like",
    "metadata",
    "retrieval_text",
    "relation_expansion",
)
CANONICAL_RETRIEVAL_ROUTE_TAGS = (
    "general_semantic",
    "japanese_or_crosslingual",
    "technical_or_code",
    "relation_heavy",
    "media_content",
    "time_sensitive",
    "external_needed",
    "exact_identifier",
    "account_specific",
    "conflict_sensitive",
)
_JP_RE = re.compile(r"[\u3040-\u30ff\u3400-\u9fff]")
_EXACT_IDENTIFIER_RE = re.compile(
    r"(?i)(https?://|x\.com/.+/status/\d+|tweet[:\s_-]*\d+|"
    r"\b(?:tweet_id|media_id|doc_id|url)[:=]\S+|@[A-Za-z0-9_]{2,})"
)


@dataclass(frozen=True)
class RouteAwareEngineChoice:
    engine_run_id: str
    engine: str
    route_role: str
    candidate_only: bool
    evidence_role: str
    answer_support_allowed: bool
    raw_score_fusion_allowed: bool
    score_space: str
    semantic_space_id: str | None = None
    embedding_profile: str | None = None
    provider_role: str | None = None
    provider_gated: bool = False
    local_execution: str = "available"
    notes: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RouteAwareRetrievalPlan:
    query: str
    route_version: str
    requested_route: str
    route_tag: str
    engine_choices: tuple[RouteAwareEngineChoice, ...]
    query_plan: QueryPlan
    reasoning: dict[str, Any]

    @property
    def semantic_engine_choices(self) -> tuple[RouteAwareEngineChoice, ...]:
        return tuple(choice for choice in self.engine_choices if choice.semantic_space_id)

    @property
    def executable_semantic_engine_choices(self) -> tuple[RouteAwareEngineChoice, ...]:
        return tuple(
            choice
            for choice in self.semantic_engine_choices
            if _choice_is_locally_executable(choice)
        )

    @property
    def semantic_space_ids(self) -> tuple[str, ...]:
        return tuple(
            choice.semantic_space_id
            for choice in self.semantic_engine_choices
            if choice.semantic_space_id
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "query": self.query,
            "route_version": self.route_version,
            "requested_route": self.requested_route,
            "route_tag": self.route_tag,
            "canonical_route_tags": CANONICAL_RETRIEVAL_ROUTE_TAGS,
            "engine_choices": [choice.as_dict() for choice in self.engine_choices],
            "engine_choices_role": "advisory_route_choices_not_an_execution_log",
            "semantic_space_ids": self.semantic_space_ids,
            "executable_semantic_space_ids": self.executable_semantic_space_ids,
            "query_plan": self.query_plan.as_dict(),
            "reasoning": self.reasoning,
            "search_execution_contract": {
                "local_baseline_engines": ROUTE_AWARE_LOCAL_BASELINE_ENGINES,
                "local_baseline_execution": "always_run_for_broad_recall",
                "route_engine_choices": "advisory_for_route_selection_and_reporting",
                "semantic_execution": "only_available_non_provider_gated_single_space",
            },
            "fusion_contract": {
                "method": "separate_engine_runs_plus_rank_metadata",
                "raw_score_fusion_allowed": False,
                "multiple_semantic_spaces": "separate_engine_runs_only",
                "candidate_promotion_gate": "source_bundle_context_citation_required",
            },
            "typed_vector_candidate_policy": {
                "evidence_role": "retrieval_candidate_signal",
                "answer_support_allowed": False,
                "candidate_only_until": "source_bundle_context_citation_required",
            },
        }

    def compact_search_metadata(self) -> dict[str, Any]:
        return {
            "route_version": self.route_version,
            "route_tag": self.route_tag,
            "engine_choices": [choice.as_dict() for choice in self.engine_choices],
            "engine_choices_role": "advisory_route_choices_not_an_execution_log",
            "semantic_space_ids": self.semantic_space_ids,
            "executable_semantic_space_ids": self.executable_semantic_space_ids,
            "local_baseline_engines": ROUTE_AWARE_LOCAL_BASELINE_ENGINES,
            "local_baseline_execution": "always_run_for_broad_recall",
            "raw_score_fusion_allowed": False,
            "multiple_semantic_spaces": "separate_engine_runs_only",
            "candidate_promotion_gate": "source_bundle_context_citation_required",
        }

    @property
    def executable_semantic_space_ids(self) -> tuple[str, ...]:
        return tuple(
            choice.semantic_space_id
            for choice in self.executable_semantic_engine_choices
            if choice.semantic_space_id
        )


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
    output_mode: str
    workflow_route: WorkflowRoute
    query_plan: QueryPlan
    reasoning: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["workflow_route"] = self.workflow_route.as_dict()
        payload["query_plan"] = self.query_plan.as_dict()
        payload.update(build_pre_execution_artifacts(self))
        return payload


def plan_route_aware_retrieval(
    query: str,
    *,
    requested_route: str = "auto",
) -> RouteAwareRetrievalPlan:
    query_plan = build_query_plan(query)
    requested = _normalise_route_tag(requested_route)
    if requested == "auto":
        route_tag, reason = _auto_route_tag(query_plan)
    else:
        if requested not in CANONICAL_RETRIEVAL_ROUTE_TAGS:
            raise ValueError(f"unknown retrieval route tag: {requested_route}")
        route_tag = requested
        reason = "explicit_route_tag"
    choices = _route_engine_choices(route_tag)
    return RouteAwareRetrievalPlan(
        query=query,
        route_version=ROUTE_AWARE_RETRIEVAL_VERSION,
        requested_route=requested,
        route_tag=route_tag,
        engine_choices=choices,
        query_plan=query_plan,
        reasoning={
            "selection": reason,
            "intents": tuple(sorted(query_plan.intents)),
            "provider_free_execution": True,
            "route_outputs_are_candidates": True,
        },
    )


def _normalise_route_tag(value: str | None) -> str:
    return (value or "auto").strip().lower().replace("-", "_")


def _auto_route_tag(query_plan: QueryPlan) -> tuple[str, str]:
    intents = set(query_plan.intents)
    normalized = query_plan.normalized_query
    if _looks_like_conflict_sensitive(query_plan):
        return "conflict_sensitive", "conflict_or_contradiction_signal"
    if query_plan.author_terms or "author" in intents:
        return "account_specific", "author_or_account_signal"
    if _EXACT_IDENTIFIER_RE.search(normalized):
        return "exact_identifier", "identifier_or_url_anchor"
    if query_plan.requires_media_context or "media" in intents:
        return "media_content", "media_intent"
    if _looks_external_needed(query_plan):
        return "external_needed", "current_or_external_grounding_signal"
    if query_plan.prefers_recent or query_plan.excludes_old or query_plan.wants_event_dates:
        return "time_sensitive", "freshness_or_event_signal"
    if query_plan.requires_quote_context or query_plan.wants_cross_account:
        return "relation_heavy", "quote_or_cross_account_signal"
    if intents.intersection({"technology", "science"}):
        return "technical_or_code", "technical_or_science_signal"
    if _JP_RE.search(normalized):
        return "japanese_or_crosslingual", "japanese_text_signal"
    return "general_semantic", "default_general_semantic"


def _looks_conflict_term(value: str) -> bool:
    return any(
        token in value.casefold()
        for token in (
            "矛盾",
            "反対意見",
            "反対",
            "同じ話",
            "contradict",
            "contradiction",
            "conflict",
            "support",
        )
    )


def _looks_like_conflict_sensitive(query_plan: QueryPlan) -> bool:
    return _looks_conflict_term(query_plan.normalized_query)


def _looks_external_needed(query_plan: QueryPlan) -> bool:
    text = query_plan.normalized_query.casefold()
    return any(
        token in text
        for token in (
            "web",
            "external",
            "外部",
            "検索して",
            "調べて",
            "最新",
            "現在",
            "現時点",
            "今も",
        )
    )


def _route_engine_choices(route_tag: str) -> tuple[RouteAwareEngineChoice, ...]:
    if route_tag == "general_semantic":
        return (
            _engine("fts", "lexical_candidate_generation"),
            _engine("retrieval_text", "search_projection_candidate_generation"),
            _semantic("text.general_memory.v1", "general_memory", "broad_text_semantic"),
        )
    if route_tag == "japanese_or_crosslingual":
        return (
            _engine("fts", "lexical_candidate_generation"),
            _engine("retrieval_text", "search_projection_candidate_generation"),
            _semantic("text.general_memory.v1", "general_memory", "broad_text_semantic"),
            _semantic(
                "text.jp_multilingual.v1",
                "jp_multilingual",
                "japanese_crosslingual_semantic",
            ),
        )
    if route_tag == "technical_or_code":
        return (
            _engine("fts", "exact_terms_and_code_tokens"),
            _engine("retrieval_text", "technical_projection_candidate_generation"),
            _semantic("text.code_technical.v1", "code_technical", "technical_semantic"),
        )
    if route_tag == "relation_heavy":
        return (
            _engine("fts", "lexical_seed_candidates"),
            _engine("relation_expansion", "quote_reply_thread_expansion"),
            _semantic("text.relation_context.v1", "relation_context", "relation_semantic"),
        )
    if route_tag == "media_content":
        return (
            _engine("metadata", "media_source_candidate_filter"),
            _engine("retrieval_text", "ocr_caption_alt_text_projection"),
            _semantic("media.text_bridge.v1", "media_text_bridge", "media_text_bridge"),
            _semantic(
                "media.native_multimodal.v1",
                "native_multimodal_media",
                "native_media_candidate_signal",
                provider_role="media_embedding",
                provider_gated=True,
                local_execution="provider_gated_metadata_only",
            ),
        )
    if route_tag == "time_sensitive":
        return (
            _engine("metadata", "date_and_observed_at_filter"),
            _engine("relation_expansion", "freshness_lineage_expansion"),
            _semantic("text.temporal_event.v1", "temporal_event", "temporal_semantic"),
        )
    if route_tag == "external_needed":
        return (
            _engine("metadata", "local_precheck_before_external"),
            _semantic(
                "external.fetch_text.v1",
                "external_fetch_text",
                "approved_fetch_artifact_semantic",
                provider_gated=True,
                local_execution="provider_gated_metadata_only",
            ),
            _engine(
                "external_web_context",
                "external_candidate_discovery",
                provider_gated=True,
                local_execution="provider_gated_metadata_only",
            ),
        )
    if route_tag == "exact_identifier":
        return (
            _engine("exact_anchor", "tweet_url_doc_or_media_identifier"),
            _engine("metadata", "identifier_metadata_lookup"),
            _engine("fts", "quoted_identifier_fallback"),
        )
    if route_tag == "account_specific":
        return (
            _engine("metadata", "account_author_bookmark_filter"),
            _engine("relation_expansion", "same_account_and_bookmark_context"),
            _semantic("text.relation_context.v1", "relation_context", "account_context_semantic"),
        )
    if route_tag == "conflict_sensitive":
        return (
            _engine("metadata", "source_and_date_preserving_filter"),
            _engine("relation_expansion", "supports_contradicts_lineage"),
            _semantic("text.temporal_event.v1", "temporal_event", "temporal_semantic"),
            _semantic("text.relation_context.v1", "relation_context", "conflict_relation_semantic"),
        )
    raise ValueError(f"unknown retrieval route tag: {route_tag}")


def _engine(
    engine: str,
    route_role: str,
    *,
    provider_gated: bool = False,
    local_execution: str = "available",
) -> RouteAwareEngineChoice:
    return RouteAwareEngineChoice(
        engine_run_id=f"{engine}:{route_role}",
        engine=engine,
        route_role=route_role,
        candidate_only=True,
        evidence_role="retrieval_candidate_signal",
        answer_support_allowed=False,
        raw_score_fusion_allowed=False,
        score_space=engine,
        provider_gated=provider_gated,
        local_execution=local_execution,
        notes=("source_bundle_context_citation_required",),
    )


def _semantic(
    semantic_space_id: str,
    embedding_profile: str,
    route_role: str,
    *,
    provider_role: str = "text_embedding",
    provider_gated: bool = False,
    local_execution: str = "available",
) -> RouteAwareEngineChoice:
    return RouteAwareEngineChoice(
        engine_run_id=f"semantic:{semantic_space_id}",
        engine="semantic",
        route_role=route_role,
        candidate_only=True,
        evidence_role="retrieval_candidate_signal",
        answer_support_allowed=False,
        raw_score_fusion_allowed=False,
        score_space=f"semantic:{semantic_space_id}",
        semantic_space_id=semantic_space_id,
        embedding_profile=embedding_profile,
        provider_role=provider_role,
        provider_gated=provider_gated,
        local_execution=local_execution,
        notes=(
            "semantic_scores_are_not_cross_space_additive",
            "source_bundle_context_citation_required",
        ),
    )


def _choice_is_locally_executable(choice: RouteAwareEngineChoice) -> bool:
    return (
        choice.semantic_space_id is not None
        and choice.provider_role == "text_embedding"
        and not choice.provider_gated
        and choice.local_execution == "available"
    )


def plan_objective_routes(
    query: str,
    *,
    requested_route: str = "auto",
    budget_policy: str = "default",
    output_mode: str | OutputMode = OutputMode.EXPLORE,
) -> ObjectiveRoutePlan:
    mode = normalize_output_mode(output_mode)
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
                "source_restore_restore",
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
                "no_restorable_media_source_restore",
            ),
            budget_policy=budget_policy,
            planned_provider_roles=(
                "index_provider",
                "media_embedding",
                "ocr",
                "context_builder",
            ),
            output_mode=mode,
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
            must_run_guards=("source_restore_restore", "citation_required", "api_budget_guard"),
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
            output_mode=mode,
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
            must_run_guards=("source_restore_restore", "citation_required", "freshness_lineage"),
            escalation_triggers=(
                "needs_current_external_grounding",
                "contradiction_or_obsolete_signal",
            ),
            stop_conditions=("freshness_supported", "external_context_needed", "budget_exhausted"),
            budget_policy=budget_policy,
            planned_provider_roles=("index_provider", "fetch_agent", "llm_context_provider"),
            output_mode=mode,
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
            must_run_guards=("source_restore_restore", "map_is_not_evidence", "citation_required"),
            escalation_triggers=(
                "map_has_unsupported_claim",
                "missing_topic_cluster",
                "low_citation_coverage",
            ),
            stop_conditions=("map_with_cited_sources", "no_local_evidence", "budget_exhausted"),
            budget_policy=budget_policy,
            planned_provider_roles=("index_provider", "context_builder", "reranker"),
            output_mode=mode,
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
        must_run_guards=("source_restore_restore", "citation_required", "api_budget_guard"),
        escalation_triggers=(
            "low_citation_precision",
            "ambiguous_context",
            "missing_required_relation",
        ),
        stop_conditions=("enough_cited_evidence", "no_local_evidence", "budget_exhausted"),
        budget_policy=budget_policy,
        planned_provider_roles=("index_provider", "context_builder", "reranker"),
        output_mode=mode,
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
            f"output_mode: {plan.output_mode}",
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
    output_mode: str | OutputMode,
    reasoning: dict[str, Any],
) -> ObjectiveRoutePlan:
    mode = normalize_output_mode(output_mode)
    return ObjectiveRoutePlan(
        query=query,
        objective_route_version=OBJECTIVE_ROUTE_VERSION,
        eval_question_type=eval_question_type,
        primary_route=primary_route,
        fallback_routes=fallback_routes,
        must_run_guards=_guards_for_output_mode(must_run_guards, mode),
        escalation_triggers=escalation_triggers,
        stop_conditions=stop_conditions,
        budget_policy=budget_policy,
        planned_provider_roles=planned_provider_roles,
        output_mode=mode.value,
        workflow_route=workflow_route,
        query_plan=query_plan,
        reasoning=reasoning,
    )


def _guards_for_output_mode(
    route_guards: tuple[str, ...],
    output_mode: OutputMode,
) -> tuple[str, ...]:
    mode_specific = {"source_restore_restore", "citation_required"}
    guards = [guard for guard in route_guards if guard not in mode_specific]
    guards.extend(("artifact_role_preserved", "output_mode_authority_enforced"))
    if output_mode in {
        OutputMode.EXPLORE,
        OutputMode.COLLECT,
        OutputMode.WORKING_NOTE,
        OutputMode.SYNTHESIZE,
    }:
        guards.append("no_answer_assertion")
    else:
        guards.extend(("source_restoration_required", "citation_required"))
    if output_mode is OutputMode.ANSWER:
        guards.extend(("evidence_package_required", "claim_support_required"))
    return tuple(dict.fromkeys(guards))


def _route_run_id(query: str, primary_route: str) -> str:
    raw = f"{query}\0{primary_route}\0{_utc_now()}".encode()
    import hashlib

    return f"route-{hashlib.sha256(raw).hexdigest()[:16]}"


def _utc_now() -> str:
    return datetime.now(tz=UTC).isoformat()
