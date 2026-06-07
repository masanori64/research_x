from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from contextlib import suppress
from dataclasses import asdict, dataclass
from typing import Any

RESEARCH_CONTROL_VERSION = "research-control-v1"


@dataclass(frozen=True)
class ResearchTaskFrame:
    version: str
    query: str
    objective_type: str
    primary_goal: str
    local_x_db_primary: bool
    adequacy_criteria: tuple[str, ...]
    abstention_conditions: tuple[str, ...]
    evidence_policy: dict[str, Any]
    personalization_policy: dict[str, Any]
    quota_policy: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_pre_execution_artifacts(plan: Any) -> dict[str, Any]:
    """Build citation-excluded control artifacts for an objective route plan."""

    task_frame = _research_task_frame(plan)
    graph = _search_plan_graph(plan)
    return {
        "research_task_frame": task_frame.as_dict(),
        "search_plan_graph": graph,
        "provider_capability_matrix": _provider_capability_matrix(plan),
        "personalization_policy": task_frame.personalization_policy,
        "user_signal_policy": _user_signal_policy(plan),
    }


def build_execution_artifacts(
    plan: Any,
    arm_results: Iterable[Any],
    *,
    selected_routes: Iterable[str],
    status: str,
    stop_reason: str,
) -> dict[str, Any]:
    """Summarize post-execution research quality without creating evidence."""

    results = tuple(arm_results)
    coverage = _result_coverage_map(results, selected_routes=tuple(selected_routes))
    gaps = _evidence_gap(plan, results, coverage=coverage, status=status, stop_reason=stop_reason)
    source_signals = _source_quality_signals(results)
    claim_support = _claim_support_check(results, coverage=coverage, gaps=gaps)
    brief = _research_brief(
        plan,
        status=status,
        stop_reason=stop_reason,
        coverage=coverage,
        gaps=gaps,
        claim_support=claim_support,
    )
    return {
        "result_coverage_map": coverage,
        "search_episode_trace": _search_episode_trace(results, stop_reason=stop_reason),
        "evidence_gap": gaps,
        "source_quality_signals": source_signals,
        "reader_quality_profile": _reader_quality_profile(results),
        "serp_flattening_audit": _serp_flattening_audit(results),
        "claim_support_check": claim_support,
        "research_brief": brief,
    }


def _research_task_frame(plan: Any) -> ResearchTaskFrame:
    question_type = str(getattr(plan, "eval_question_type", "citation_required"))
    return ResearchTaskFrame(
        version=RESEARCH_CONTROL_VERSION,
        query=str(getattr(plan, "query", "")),
        objective_type=question_type,
        primary_goal=_primary_goal(question_type),
        local_x_db_primary=True,
        adequacy_criteria=_adequacy_criteria(plan),
        abstention_conditions=(
            "no_restorable_source_bundle",
            "no_citation_ready_context",
            "only_snippet_or_rank_available",
            "provider_quota_gate_blocks_required_external_context",
            "claim_support_check_needs_review",
        ),
        evidence_policy={
            "snippet_rank_ai_summary_are_evidence": False,
            "generated_query_text_is_evidence": False,
            "browser_history_is_evidence": False,
            "subagent_notes_are_evidence": False,
            "requires_source_bundle_restoration": True,
            "requires_context_chunk_before_citation": True,
        },
        personalization_policy=_personalization_policy(plan),
        quota_policy={
            "no_quota_freeze_active": True,
            "real_provider_calls_allowed": False,
            "allowed_verification": ("local", "fake", "offline_estimate", "coverage"),
        },
    )


def _search_plan_graph(plan: Any) -> dict[str, Any]:
    primary = str(getattr(plan, "primary_route", "candidate_a_current_baseline"))
    fallbacks = tuple(str(route) for route in getattr(plan, "fallback_routes", ()) or ())
    route_order = _dedupe((primary, *fallbacks))
    query_plan = getattr(plan, "query_plan", None)
    search_terms = tuple(str(term) for term in getattr(query_plan, "search_terms", ()) or ())
    exact_terms = tuple(str(term) for term in getattr(query_plan, "exact_terms", ()) or ())

    nodes = []
    for index, route in enumerate(route_order):
        nodes.append(
            {
                "node_id": f"route:{route}",
                "node_kind": "route_arm",
                "route_arm": route,
                "order": index,
                "provider_roles": _provider_roles_for_route(route),
                "citation_policy": _citation_policy_for_route(route),
                "quota_policy": "local_or_fake_only"
                if route not in _PROVIDER_BACKED_ROUTES
                else "provider_quota_gate",
            }
        )
    query_variants = [
        {
            "variant_id": "original_query",
            "text": str(getattr(plan, "query", "")),
            "citation_excluded": True,
            "purpose": "preserve user wording and anchors",
        }
    ]
    if exact_terms:
        query_variants.append(
            {
                "variant_id": "exact_anchor_query",
                "text": " ".join(exact_terms),
                "citation_excluded": True,
                "purpose": "exact metadata and entity recall",
            }
        )
    if search_terms:
        query_variants.append(
            {
                "variant_id": "lexical_recall_query",
                "text": " ".join(search_terms[:8]),
                "citation_excluded": True,
                "purpose": "broad lexical recall; not evidence",
            }
        )

    return {
        "version": RESEARCH_CONTROL_VERSION,
        "nodes": nodes,
        "edges": [
            {
                "from": f"route:{route_order[index]}",
                "to": f"route:{route_order[index + 1]}",
                "edge_kind": "fallback_if_gap_or_guard_fails",
            }
            for index in range(max(0, len(route_order) - 1))
        ],
        "query_variants": query_variants,
        "escalation_triggers": list(getattr(plan, "escalation_triggers", ()) or ()),
        "stop_conditions": list(getattr(plan, "stop_conditions", ()) or ()),
        "contract": "plan_graph_controls_search_but_is_not_evidence",
    }


def _provider_capability_matrix(plan: Any) -> dict[str, Any]:
    rows = [
        _capability(
            "local_x_db",
            "index_provider,context_builder",
            "primary source-bundle surface",
            "citation_ready_after_context_chunk",
            quota_policy="local_no_quota",
            status="available",
        ),
        _capability(
            "serper",
            "index_provider",
            "URL discovery and SERP inventory only",
            "not_evidence_until_fetched_and_chunked",
            quota_policy="provider_quota_gate",
            status="gated",
        ),
        _capability(
            "searxng",
            "index_provider",
            "optional self-hosted URL discovery experiment",
            "not_evidence_until_fetched_and_chunked",
            quota_policy="local_or_external_config_gate",
            status="optional",
        ),
        _capability(
            "browser_history",
            "personal_recall_hint",
            "weak personal memory signal for refinding URLs",
            "citation_excluded_until_url_refetched",
            quota_policy="local_opt_in",
            status="optional",
        ),
        _capability(
            "http_reader",
            "fetch_agent",
            "URL fetch and text extraction",
            "citation_candidate_after_content_hash",
            quota_policy="network_policy_gate",
            status="available_if_network_allowed",
        ),
        _capability(
            "jina_reader",
            "fetch_agent",
            "Reader/API extraction of URL or PDF content",
            "citation_candidate_after_content_hash",
            quota_policy="provider_quota_gate",
            status="gated",
        ),
        _capability(
            "brave_llm_context",
            "llm_context_provider",
            "pre-extracted external grounding context",
            "unconfirmed_external_context_until_checked",
            quota_policy="provider_quota_gate",
            status="gated",
        ),
        _capability(
            "semantic_embedding_portfolio",
            "index_provider",
            "recall arm over already-restorable documents",
            "score_is_not_evidence",
            quota_policy="provider_quota_gate",
            status="gated",
        ),
        _capability(
            "rerank_after_bundle",
            "reranker",
            "post-restoration candidate ordering",
            "score_is_not_evidence",
            quota_policy="provider_quota_gate",
            status="gated",
        ),
        _capability(
            "subagent_or_deep_research_notes",
            "exploration_note",
            "planning, critique, and coverage hints",
            "citation_excluded_until_source_recovered",
            quota_policy="conversation_context_only",
            status="available_as_note",
        ),
    ]
    planned_roles = set(str(role) for role in getattr(plan, "planned_provider_roles", ()) or ())
    return {
        "version": RESEARCH_CONTROL_VERSION,
        "planned_provider_roles": sorted(planned_roles),
        "rows": rows,
        "contract": "provider_output_role_must_match_allowed_evidence_policy",
    }


def _result_coverage_map(
    results: tuple[Any, ...],
    *,
    selected_routes: tuple[str, ...],
) -> dict[str, Any]:
    status_counts: Counter[str] = Counter()
    doc_type_counts: Counter[str] = Counter()
    provider_skipped = []
    route_rows = []
    evidence_total = 0
    citation_total = 0
    restoration_failures = 0
    for result in results:
        route = str(getattr(result, "route_arm", "unknown"))
        status = str(getattr(result, "status", "unknown"))
        output = _dict(getattr(result, "output", {}))
        status_counts[status] += 1
        evidence_count = int(getattr(result, "evidence_count", 0) or 0)
        citation_count = int(getattr(result, "citation_count", 0) or 0)
        evidence_total += evidence_count
        citation_total += citation_count
        if bool(getattr(result, "provider_quota_skipped", False)):
            provider_skipped.append(route)
        for doc_type, count in _dict(output.get("doc_types")).items():
            try:
                doc_type_counts[str(doc_type)] += int(count or 0)
            except (TypeError, ValueError):
                continue
        with suppress(TypeError, ValueError):
            restoration_failures += int(output.get("source_bundle_restoration_failures") or 0)
        route_rows.append(
            {
                "route_arm": route,
                "status": status,
                "evidence_count": evidence_count,
                "citation_count": citation_count,
                "provider_quota_skipped": bool(getattr(result, "provider_quota_skipped", False)),
                "stop_condition": getattr(result, "stop_condition", None),
                "escalation_trigger": getattr(result, "escalation_trigger", None),
                "doc_types": _dict(output.get("doc_types")),
            }
        )
    return {
        "version": RESEARCH_CONTROL_VERSION,
        "selected_routes": list(selected_routes),
        "executed_routes": [row["route_arm"] for row in route_rows],
        "status_counts": dict(sorted(status_counts.items())),
        "doc_type_counts": dict(sorted(doc_type_counts.items())),
        "evidence_total": evidence_total,
        "citation_total": citation_total,
        "provider_quota_skipped_routes": provider_skipped,
        "source_bundle_restoration_failures": restoration_failures,
        "route_rows": route_rows,
    }


def _evidence_gap(
    plan: Any,
    results: tuple[Any, ...],
    *,
    coverage: dict[str, Any],
    status: str,
    stop_reason: str,
) -> dict[str, Any]:
    gaps: list[dict[str, Any]] = []
    if int(coverage.get("evidence_total") or 0) <= 0:
        gaps.append(_gap("no_candidate_evidence", "No route returned local evidence candidates."))
    if int(coverage.get("citation_total") or 0) <= 0:
        gaps.append(
            _gap(
                "no_citation_ready_context",
                "No citation-ready context chunks were found.",
            )
        )
    if coverage.get("provider_quota_skipped_routes"):
        gaps.append(
            _gap(
                "provider_quota_gate",
                "Provider-backed route arms were skipped by the no-quota freeze.",
                routes=coverage["provider_quota_skipped_routes"],
            )
        )
    failures = int(coverage.get("source_bundle_restoration_failures") or 0)
    if failures:
        gaps.append(
            _gap(
                "source_bundle_restoration_failure",
                "Some candidates could not be restored to source bundles.",
                count=failures,
            )
        )
    if str(getattr(plan, "primary_route", "")) == "media_evidence":
        content_hits = sum(
            int(_dict(getattr(result, "output", {})).get("media_content_hits") or 0)
            for result in results
        )
        if content_hits <= 0:
            gaps.append(
                _gap(
                    "media_content_evidence_missing",
                    (
                        "Media candidates exist only as source candidates unless "
                        "OCR/caption chunks exist."
                    ),
                )
            )
    if status != "ok":
        gaps.append(
            _gap(
                "workflow_not_promoted",
                f"Execution status is {status}.",
                stop_reason=stop_reason,
            )
        )
    return {
        "version": RESEARCH_CONTROL_VERSION,
        "status": "ok" if not gaps else "needs_review",
        "gap_count": len(gaps),
        "gaps": gaps,
    }


def _source_quality_signals(results: tuple[Any, ...]) -> list[dict[str, Any]]:
    signals: list[dict[str, Any]] = []
    for result in results:
        route = str(getattr(result, "route_arm", "unknown"))
        if route in {
            "candidate_a_current_baseline",
            "exact_metadata_social",
            "skill_map",
            "graph_sensemaking",
        }:
            signals.append(
                {
                    "route_arm": route,
                    "source_kind": "local_x_db",
                    "quality_class": "primary_personal_archive",
                    "evidence_status": "candidate_until_context_chunk",
                    "risk_flags": [],
                    "citation_policy": "allowed_after_source_bundle_restoration",
                }
            )
        elif route == "media_evidence":
            signals.append(
                {
                    "route_arm": route,
                    "source_kind": "local_x_media",
                    "quality_class": "media_source_candidate",
                    "evidence_status": "unconfirmed_media_match_until_content_chunk",
                    "risk_flags": [
                        "visual_content_claim_requires_ocr_caption_or_observation_chunk"
                    ],
                    "citation_policy": "source_only_until_media_content_evidence",
                }
            )
        elif route == "external_web_context":
            signals.append(
                {
                    "route_arm": route,
                    "source_kind": "external_web",
                    "quality_class": "unknown_until_reader_quality_profile",
                    "evidence_status": "unconfirmed",
                    "risk_flags": ["serp_flattening", "snippet_not_evidence"],
                    "citation_policy": "blocked_until_fetch_extract_hash_and_chunk",
                }
            )
        else:
            signals.append(
                {
                    "route_arm": route,
                    "source_kind": "derived_or_provider_signal",
                    "quality_class": "ranking_or_planning_signal",
                    "evidence_status": "not_evidence",
                    "risk_flags": ["score_or_summary_not_citation"],
                    "citation_policy": "citation_excluded",
                }
            )
    return signals


def _search_episode_trace(results: tuple[Any, ...], *, stop_reason: str) -> dict[str, Any]:
    events = []
    for index, result in enumerate(results):
        output = _dict(getattr(result, "output", {}))
        events.append(
            {
                "step_index": index,
                "route_arm": str(getattr(result, "route_arm", "unknown")),
                "status": str(getattr(result, "status", "unknown")),
                "evidence_count": int(getattr(result, "evidence_count", 0) or 0),
                "citation_count": int(getattr(result, "citation_count", 0) or 0),
                "stop_condition": getattr(result, "stop_condition", None),
                "escalation_trigger": getattr(result, "escalation_trigger", None),
                "provider_quota_skipped": bool(
                    getattr(result, "provider_quota_skipped", False)
                ),
                "output_keys": sorted(str(key) for key in output),
            }
        )
    return {
        "version": RESEARCH_CONTROL_VERSION,
        "events": events,
        "stop_reason": stop_reason,
        "citation_excluded_artifacts": (
            "query_variants",
            "serp_rank",
            "snippet",
            "browser_history",
            "subagent_notes",
            "router_confidence",
            "provider_score",
        ),
        "contract": "episode_trace_explains_execution_but_is_not_source_evidence",
    }


def _reader_quality_profile(results: tuple[Any, ...]) -> dict[str, Any]:
    external_routes = [
        result
        for result in results
        if str(getattr(result, "route_arm", "")) == "external_web_context"
    ]
    if not external_routes:
        status = "not_requested"
    elif any(bool(getattr(result, "provider_quota_skipped", False)) for result in external_routes):
        status = "blocked_by_provider_quota_gate"
    else:
        status = "needs_review"
    return {
        "version": RESEARCH_CONTROL_VERSION,
        "status": status,
        "checks": {
            "url_discovery_is_not_reader_quality": True,
            "requires_source_url": True,
            "requires_content_hash_or_raw_response_hash": True,
            "requires_context_chunk_before_citation": True,
        },
        "external_route_count": len(external_routes),
        "contract": "reader_quality_profiles_extracted_content_not_serp_items",
    }


def _serp_flattening_audit(results: tuple[Any, ...]) -> dict[str, Any]:
    external_routes = [
        result
        for result in results
        if str(getattr(result, "route_arm", "")) == "external_web_context"
    ]
    return {
        "version": RESEARCH_CONTROL_VERSION,
        "status": "ok" if not external_routes else "needs_reader_or_source_review",
        "checks": {
            "rank_used_as_evidence": False,
            "snippet_used_as_evidence": False,
            "ai_summary_used_as_evidence": False,
            "fixed_quota_false_balance": False,
            "requires_discovery_to_reader_step": True,
        },
        "external_route_count": len(external_routes),
        "provider_quota_skipped": any(
            bool(getattr(result, "provider_quota_skipped", False))
            for result in external_routes
        ),
        "contract": "serp_inventory_must_not_be_flattened_into_answer_evidence",
    }


def _claim_support_check(
    results: tuple[Any, ...],
    *,
    coverage: dict[str, Any],
    gaps: dict[str, Any],
) -> dict[str, Any]:
    citation_total = int(coverage.get("citation_total") or 0)
    evidence_total = int(coverage.get("evidence_total") or 0)
    return {
        "version": RESEARCH_CONTROL_VERSION,
        "status": "ready" if citation_total > 0 and gaps.get("status") == "ok" else "needs_review",
        "deterministic_checks": {
            "citation_ready_context_present": citation_total > 0,
            "candidate_evidence_present": evidence_total > 0,
            "snippet_or_rank_used_as_evidence": False,
            "generated_artifacts_citation_excluded": True,
            "semantic_claim_judge_required_for_promotion": True,
        },
        "citation_count": citation_total,
        "evidence_count": evidence_total,
        "limitations": (
            "This deterministic check verifies artifact boundaries only.",
            "Semantic claim support still requires provider or human review.",
        ),
    }


def _research_brief(
    plan: Any,
    *,
    status: str,
    stop_reason: str,
    coverage: dict[str, Any],
    gaps: dict[str, Any],
    claim_support: dict[str, Any],
) -> dict[str, Any]:
    return {
        "version": RESEARCH_CONTROL_VERSION,
        "query": str(getattr(plan, "query", "")),
        "status": status,
        "stop_reason": stop_reason,
        "primary_route": str(getattr(plan, "primary_route", "")),
        "selected_routes": coverage.get("executed_routes", []),
        "evidence_total": coverage.get("evidence_total", 0),
        "citation_total": coverage.get("citation_total", 0),
        "gap_count": gaps.get("gap_count", 0),
        "claim_support_status": claim_support.get("status"),
        "next_actions": _next_actions(gaps, coverage),
        "citation_policy": "brief_is_not_evidence",
    }


def _primary_goal(question_type: str) -> str:
    goals = {
        "media_grounded": (
            "Find restorable media/tweet candidates without unsupported image claims."
        ),
        "temporal_freshness": (
            "Separate local saved evidence from current external grounding needs."
        ),
        "exploratory_map": "Build a navigation map that returns to cited source bundles.",
        "multi_hop_evidence": "Recover linked quote/relation evidence and preserve provenance.",
        "comparison": "Compare source-backed positions without treating summaries as proof.",
        "single_fact_conditioned": "Recover exact local facts from the user archive.",
    }
    return goals.get(question_type, "Recover citation-ready local evidence or abstain.")


def _adequacy_criteria(plan: Any) -> tuple[str, ...]:
    criteria = [
        "answerable claims must cite context chunks",
        "candidates must restore to source bundles",
        "SERP rank, snippet, browser history, and sub-agent notes are not evidence",
        "external Web is auxiliary unless the question asks for current grounding",
    ]
    if str(getattr(plan, "primary_route", "")) == "media_evidence":
        criteria.append("image-content claims require OCR/caption/VLM-derived context chunks")
    if "external_web_context" in tuple(getattr(plan, "fallback_routes", ()) or ()):
        criteria.append("external discovery must be fetched/extracted before citation")
    return tuple(criteria)


def _personalization_policy(plan: Any) -> dict[str, Any]:
    question_type = str(getattr(plan, "eval_question_type", "citation_required"))
    if question_type in {"personal_preference", "set_recall", "exploratory_map"}:
        mode = "route_scoped_boost"
    elif question_type in {"temporal_freshness", "citation_required"}:
        mode = "neutral_until_source_supported"
    else:
        mode = "weak_ranking_hint"
    return {
        "mode": mode,
        "allowed_uses": ("ranking", "route_hint", "refinding"),
        "disallowed_uses": ("citation", "fact_claim", "source_replacement"),
        "always_on_personal_boost": False,
    }


def _user_signal_policy(plan: Any) -> dict[str, Any]:
    return {
        "signals": ("bookmark_account", "duplicate_bookmark", "feedback", "media_observation"),
        "route_scope": str(getattr(plan, "primary_route", "auto")),
        "evidence_status": "ranking_hint_not_evidence",
        "requires_source_bundle_for_answer_use": True,
    }


def _provider_roles_for_route(route: str) -> tuple[str, ...]:
    mapping = {
        "candidate_a_current_baseline": ("index_provider", "context_builder"),
        "exact_metadata_social": ("index_provider", "context_builder"),
        "semantic_embedding_portfolio": ("index_provider",),
        "rerank_after_bundle": ("reranker",),
        "media_evidence": ("media_embedding", "ocr", "context_builder"),
        "external_web_context": ("index_provider", "fetch_agent", "llm_context_provider"),
        "bounded_agentic_workflow": ("workflow_orchestrator",),
        "skill_map": ("navigation_map", "context_builder"),
        "graph_sensemaking": ("graph_navigation", "context_builder"),
    }
    return mapping.get(route, ("route_arm",))


def _citation_policy_for_route(route: str) -> str:
    if route in {"semantic_embedding_portfolio", "rerank_after_bundle"}:
        return "score_not_evidence_restore_bundle_first"
    if route == "external_web_context":
        return "fetch_extract_hash_context_chunk_required"
    if route == "media_evidence":
        return "media_source_only_until_content_chunk"
    if route in {"skill_map", "graph_sensemaking"}:
        return "map_hint_not_evidence_restore_source_first"
    return "citation_allowed_after_context_chunk"


def _capability(
    provider: str,
    provider_role: str,
    capability: str,
    evidence_policy: str,
    *,
    quota_policy: str,
    status: str,
) -> dict[str, Any]:
    return {
        "provider": provider,
        "provider_role": provider_role,
        "capability": capability,
        "evidence_policy": evidence_policy,
        "quota_policy": quota_policy,
        "status": status,
    }


def _next_actions(gaps: dict[str, Any], coverage: dict[str, Any]) -> list[str]:
    actions: list[str] = []
    gap_ids = {
        str(gap.get("gap_id"))
        for gap in gaps.get("gaps", [])
        if isinstance(gap, dict)
    }
    if "no_citation_ready_context" in gap_ids:
        actions.append("build_or_extract_context_chunks")
    if "provider_quota_gate" in gap_ids:
        actions.append("run_offline_estimate_before_provider_gate")
    if "media_content_evidence_missing" in gap_ids:
        actions.append("run_local_ocr_or_media_observation_flow")
    if "source_bundle_restoration_failure" in gap_ids:
        actions.append("repair_source_bundle_restoration")
    if not actions and int(coverage.get("citation_total") or 0) > 0:
        actions.append("eligible_for_answer_or_eval_gate")
    if not actions:
        actions.append("needs_review")
    return actions


def _gap(gap_id: str, message: str, **metadata: Any) -> dict[str, Any]:
    return {"gap_id": gap_id, "message": message, "metadata": metadata}


def _dedupe(values: tuple[str, ...]) -> tuple[str, ...]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        out.append(value)
    return tuple(out)


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


_PROVIDER_BACKED_ROUTES = {
    "semantic_embedding_portfolio",
    "rerank_after_bundle",
    "external_web_context",
    "managed_rag_reference",
    "bounded_agentic_workflow",
}
