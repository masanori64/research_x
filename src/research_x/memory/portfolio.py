from __future__ import annotations

import json
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any

from research_x.memory.context import build_context_bundle
from research_x.memory.embeddings import (
    LoadedSemanticIndex,
    load_semantic_index,
    semantic_search_loaded_index,
    semantic_search_memory,
)
from research_x.memory.evals import DEFAULT_EVAL_CASES, EvalCase
from research_x.memory.evidence import (
    build_evidence_bundle,
    build_evidence_hits_for_doc_ids,
    build_evidence_hits_from_results,
)
from research_x.memory.query import build_query_plan
from research_x.memory.rerank import rerank_hits
from research_x.memory.search import (
    search_memory_fts_only,
    strong_anchor_terms_for_query,
    text_matches_any_anchor,
)
from research_x.memory.workflow import plan_workflow_route, run_memory_workflow

DIAGNOSTIC_EMBEDDING_PROVIDERS = {"local_hash"}
BASELINE_ARM_NAMES = {
    "fts_only",
    "local_hybrid",
    "lexical",
    "corpus2skill_navigation",
    "source_bundle_context",
    "workflow_route",
}


@dataclass(frozen=True)
class PortfolioSemanticSpec:
    provider: str
    mode: str = "semantic_only"
    name: str | None = None
    model: str | None = None
    dimensions: int | None = None
    embedding_profile: str | None = None
    text_template_version: str | None = None
    api_key_env: str | None = None
    base_url: str | None = None
    weight: float = 1.0
    candidates: int = 80


@dataclass(frozen=True)
class PortfolioRerankerSpec:
    provider: str
    name: str | None = None
    model: str | None = None
    top_n: int = 5
    candidate_limit: int = 20
    api_key_env: str | None = None
    base_url: str | None = None
    weight: float = 1.0


@dataclass(frozen=True)
class PortfolioArmResult:
    name: str
    status: str
    mode: str
    provider: str | None
    model: str | None
    dimensions: int | None
    embedding_profile: str | None
    text_template_version: str | None
    weight: float
    hit_count: int
    top_doc_ids: tuple[str, ...]
    top_bundle_keys: tuple[str, ...]
    error: str | None
    case_status: str | None = None
    case_notes: tuple[str, ...] = ()
    required_terms_found: bool = False
    preferred_doc_type_found: bool = False
    required_feature_found: bool = False


@dataclass(frozen=True)
class PortfolioArmSummary:
    name: str
    mode: str | None
    provider: str | None
    model: str | None
    dimensions: int | None
    case_count: int
    ok: int
    needs_review: int
    fail: int
    error: int


@dataclass(frozen=True)
class PortfolioPromotionVerdict:
    status: str
    promotable: bool
    reason: str
    baseline_arm: str | None
    best_single_arm: str | None
    fused_ok: int
    fused_needs_review: int
    fused_fail: int
    best_single_ok: int
    best_single_needs_review: int
    best_single_fail: int
    blockers: tuple[str, ...]


@dataclass(frozen=True)
class PortfolioHit:
    rank: int
    bundle_key: str
    doc_id: str
    doc_type: str
    tweet_id: str | None
    score: float
    title: str
    compact_text: str
    contributions: tuple[dict[str, Any], ...]
    metadata: dict[str, Any]


@dataclass(frozen=True)
class PortfolioCaseResult:
    query: str
    question_type: str
    status: str
    notes: tuple[str, ...]
    best_arm_name: str | None
    best_arm_status: str | None
    fusion_improved: bool
    fusion_regressed: bool
    arms: tuple[PortfolioArmResult, ...]
    fused_hits: tuple[PortfolioHit, ...]
    required_terms_found: bool
    preferred_doc_type_found: bool
    required_feature_found: bool


@dataclass(frozen=True)
class PortfolioEvalReport:
    cases: tuple[PortfolioCaseResult, ...]
    arm_summaries: tuple[PortfolioArmSummary, ...]
    verdict: PortfolioPromotionVerdict
    parameters: dict[str, Any]


def parse_portfolio_semantic_spec(value: str) -> PortfolioSemanticSpec:
    fields = _parse_fields(value)
    raw_provider = fields.pop("provider", None)
    if not raw_provider:
        raise ValueError("portfolio semantic spec requires provider=...")
    provider = _resolve_provider(raw_provider)
    aliases = {
        "profile": "embedding_profile",
        "template": "text_template_version",
        "template_version": "text_template_version",
        "api_key": "api_key_env",
        "key_env": "api_key_env",
        "url": "base_url",
        "arm_mode": "mode",
    }
    normalized = {aliases.get(key, key): raw for key, raw in fields.items()}
    allowed = {
        "mode",
        "name",
        "model",
        "dimensions",
        "embedding_profile",
        "text_template_version",
        "api_key_env",
        "base_url",
        "weight",
        "candidates",
    }
    unknown = sorted(set(normalized) - allowed)
    if unknown:
        raise ValueError(f"unknown portfolio semantic spec field(s): {', '.join(unknown)}")
    return PortfolioSemanticSpec(
        provider=provider,
        mode=_resolve_arm_mode(normalized.get("mode")),
        name=normalized.get("name"),
        model=normalized.get("model"),
        dimensions=_optional_int(normalized.get("dimensions"), name="dimensions"),
        embedding_profile=normalized.get("embedding_profile"),
        text_template_version=normalized.get("text_template_version"),
        api_key_env=normalized.get("api_key_env"),
        base_url=normalized.get("base_url"),
        weight=_optional_float(normalized.get("weight"), name="weight") or 1.0,
        candidates=_optional_int(normalized.get("candidates"), name="candidates") or 80,
    )


def parse_portfolio_semantic_specs(
    values: list[str] | tuple[str, ...] | None,
) -> tuple[PortfolioSemanticSpec, ...]:
    if not values:
        return ()
    return tuple(parse_portfolio_semantic_spec(value) for value in values)


def parse_portfolio_reranker_spec(value: str) -> PortfolioRerankerSpec:
    fields = _parse_fields(value)
    raw_provider = fields.pop("provider", None)
    if not raw_provider:
        raise ValueError("portfolio reranker spec requires provider=...")
    provider = _resolve_provider(raw_provider)
    aliases = {
        "api_key": "api_key_env",
        "key_env": "api_key_env",
        "url": "base_url",
        "limit": "candidate_limit",
        "candidates": "candidate_limit",
    }
    normalized = {aliases.get(key, key): raw for key, raw in fields.items()}
    allowed = {
        "name",
        "model",
        "top_n",
        "candidate_limit",
        "api_key_env",
        "base_url",
        "weight",
    }
    unknown = sorted(set(normalized) - allowed)
    if unknown:
        raise ValueError(f"unknown portfolio reranker spec field(s): {', '.join(unknown)}")
    return PortfolioRerankerSpec(
        provider=provider,
        name=normalized.get("name"),
        model=normalized.get("model"),
        top_n=_optional_int(normalized.get("top_n"), name="top_n") or 5,
        candidate_limit=_optional_int(
            normalized.get("candidate_limit"), name="candidate_limit"
        )
        or 20,
        api_key_env=normalized.get("api_key_env"),
        base_url=normalized.get("base_url"),
        weight=_optional_float(normalized.get("weight"), name="weight") or 1.0,
    )


def parse_portfolio_reranker_specs(
    values: list[str] | tuple[str, ...] | None,
) -> tuple[PortfolioRerankerSpec, ...]:
    if not values:
        return ()
    return tuple(parse_portfolio_reranker_spec(value) for value in values)


def run_portfolio_eval(
    db_path: str | Path,
    *,
    cases: tuple[EvalCase, ...] | None = None,
    semantic_specs: tuple[PortfolioSemanticSpec, ...] = (),
    reranker_specs: tuple[PortfolioRerankerSpec, ...] = (),
    limit: int = 5,
    arm_limit: int = 20,
    rrf_k: float = 60.0,
    fusion_mode: str = "guarded_rrf",
    min_agreement: int = 2,
) -> PortfolioEvalReport:
    resolved_cases = cases or DEFAULT_EVAL_CASES
    resolved_fusion_mode = _resolve_fusion_mode(fusion_mode)
    semantic_index_cache = _load_semantic_indexes(db_path, semantic_specs)
    parameters = {
        "limit": max(1, limit),
        "arm_limit": max(1, arm_limit),
        "rrf_k": float(rrf_k),
        "fusion_mode": resolved_fusion_mode,
        "min_agreement": max(1, min_agreement),
        "semantic_specs": [asdict(spec) for spec in semantic_specs],
        "reranker_specs": [asdict(spec) for spec in reranker_specs],
    }
    results = tuple(
        _run_case(
            db_path,
            case=case,
            semantic_specs=semantic_specs,
            reranker_specs=reranker_specs,
            limit=max(1, limit),
            arm_limit=max(1, arm_limit),
            rrf_k=max(1.0, float(rrf_k)),
            fusion_mode=resolved_fusion_mode,
            min_agreement=max(1, min_agreement),
            semantic_index_cache=semantic_index_cache,
        )
        for case in resolved_cases
    )
    arm_summaries = _arm_summaries(results)
    return PortfolioEvalReport(
        cases=results,
        arm_summaries=arm_summaries,
        verdict=_promotion_verdict(results, arm_summaries, semantic_specs, reranker_specs),
        parameters=parameters,
    )


def portfolio_eval_json(report: PortfolioEvalReport) -> str:
    return json.dumps(asdict(report), ensure_ascii=False, indent=2, sort_keys=True)


def format_portfolio_eval(report: PortfolioEvalReport) -> str:
    lines = [
        "portfolio-eval: "
        f"cases={len(report.cases)} "
        f"semantic_specs={len(report.parameters['semantic_specs'])} "
        f"reranker_specs={len(report.parameters.get('reranker_specs', []))}"
    ]
    lines.append(
        "verdict: "
        f"{report.verdict.status} promotable={report.verdict.promotable} "
        f"reason={report.verdict.reason}"
    )
    for blocker in report.verdict.blockers:
        lines.append(f"  blocker: {blocker}")
    if report.arm_summaries:
        lines.append("arm summaries:")
        for summary in report.arm_summaries:
            lines.append(
                "  "
                f"{summary.name}: mode={summary.mode or '-'} "
                f"ok={summary.ok} review={summary.needs_review} "
                f"fail={summary.fail} error={summary.error}"
            )
    for case in report.cases:
        top = case.fused_hits[0].doc_id if case.fused_hits else "-"
        arm_statuses = ",".join(
            f"{arm.name}:{arm.case_status or arm.status}" for arm in case.arms
        )
        comparison = ""
        if case.fusion_regressed:
            comparison = f" regressed_from={case.best_arm_name}:{case.best_arm_status}"
        elif case.fusion_improved:
            comparison = f" improved_over={case.best_arm_name}:{case.best_arm_status}"
        lines.append(
            " ".join(
                [
                    f"[{case.status}]",
                    f"type={case.question_type}",
                    f"top={top}",
                    f"arms={len(case.arms)}",
                    f"arm_status={arm_statuses}",
                    f"query={case.query}{comparison}",
                ]
            )
        )
        for note in case.notes:
            lines.append(f"  note: {note}")
    return "\n".join(lines)


def _load_semantic_indexes(
    db_path: str | Path,
    semantic_specs: tuple[PortfolioSemanticSpec, ...],
) -> dict[str, LoadedSemanticIndex | str]:
    indexes: dict[str, LoadedSemanticIndex | str] = {}
    for index, spec in enumerate(semantic_specs, start=1):
        if spec.mode != "semantic_only":
            continue
        name = spec.name or _semantic_arm_name(spec, index=index)
        try:
            indexes[name] = load_semantic_index(
                db_path,
                provider=None if spec.provider == "auto" else spec.provider,
                model=spec.model,
                dimensions=spec.dimensions,
                embedding_profile=spec.embedding_profile,
                text_template_version=spec.text_template_version,
                api_key_env=spec.api_key_env,
                base_url=spec.base_url,
            )
        except (FileNotFoundError, RuntimeError, ValueError) as exc:
            indexes[name] = _compact_error(str(exc))
    return indexes


def _run_case(
    db_path: str | Path,
    *,
    case: EvalCase,
    semantic_specs: tuple[PortfolioSemanticSpec, ...],
    reranker_specs: tuple[PortfolioRerankerSpec, ...],
    limit: int,
    arm_limit: int,
    rrf_k: float,
    fusion_mode: str,
    min_agreement: int,
    semantic_index_cache: dict[str, LoadedSemanticIndex | str],
) -> PortfolioCaseResult:
    arm_payloads: list[tuple[PortfolioArmResult, list[dict[str, Any]]]] = []
    arm_payloads.append(_run_fts_only_arm(db_path, case.query, limit=arm_limit))
    arm_payloads.append(
        _run_corpus2skill_navigation_arm(db_path, case.query, limit=arm_limit)
    )
    arm_payloads.append(_run_source_bundle_context_arm(db_path, case.query, limit=arm_limit))
    arm_payloads.append(_run_workflow_route_arm(db_path, case.query, limit=arm_limit))
    arm_payloads.append(
        _run_arm(db_path, case.query, name="local_hybrid", spec=None, limit=arm_limit)
    )
    for index, spec in enumerate(semantic_specs, start=1):
        name = spec.name or _semantic_arm_name(spec, index=index)
        arm_payloads.append(
            _run_arm(
                db_path,
                case.query,
                name=name,
                spec=spec,
                limit=arm_limit,
                semantic_index_cache=semantic_index_cache,
            )
        )
    for index, spec in enumerate(reranker_specs, start=1):
        arm_payloads.append(
            _run_reranker_arm(
                case.query,
                arm_payloads,
                name=spec.name or _reranker_arm_name(spec, index=index),
                spec=spec,
                limit=limit,
                rrf_k=rrf_k,
                fusion_mode=fusion_mode,
                min_agreement=min_agreement,
            )
        )
    arm_payloads = _evaluate_arms(case, arm_payloads, limit=limit)
    fused_hits = _fuse_hits(
        arm_payloads,
        limit=limit,
        rrf_k=rrf_k,
        fusion_mode=fusion_mode,
        min_agreement=min_agreement,
    )
    notes = _case_notes(case, fused_hits)
    status = _case_status(case, notes, fused_hits)
    best_arm = _best_case_arm(tuple(arm for arm, _hits in arm_payloads))
    best_arm_status = best_arm.case_status if best_arm else None
    fusion_improved = _status_strength(status) > _status_strength(best_arm_status)
    fusion_regressed = _status_strength(status) < _status_strength(best_arm_status)
    return PortfolioCaseResult(
        query=case.query,
        question_type=case.question_type,
        status=status,
        notes=tuple(notes),
        best_arm_name=best_arm.name if best_arm else None,
        best_arm_status=best_arm_status,
        fusion_improved=fusion_improved,
        fusion_regressed=fusion_regressed,
        arms=tuple(arm for arm, _hits in arm_payloads),
        fused_hits=tuple(fused_hits),
        required_terms_found=_required_terms_found(case, fused_hits),
        preferred_doc_type_found=_preferred_doc_type_found(case, fused_hits),
        required_feature_found=_feature_found(case.required_feature, fused_hits),
    )


def _run_arm(
    db_path: str | Path,
    query: str,
    *,
    name: str,
    spec: PortfolioSemanticSpec | None,
    limit: int,
    semantic_index_cache: dict[str, LoadedSemanticIndex | str] | None = None,
) -> tuple[PortfolioArmResult, list[dict[str, Any]]]:
    try:
        if spec and spec.mode == "semantic_only":
            cached = (semantic_index_cache or {}).get(name)
            if isinstance(cached, str):
                raise RuntimeError(cached)
            return _run_semantic_only_arm(
                db_path,
                query,
                name=name,
                spec=spec,
                limit=limit,
                index=cached if isinstance(cached, LoadedSemanticIndex) else None,
            )
        bundle = build_evidence_bundle(
            db_path,
            query,
            limit=limit,
            semantic_provider=spec.provider if spec else None,
            semantic_model=spec.model if spec else None,
            semantic_dimensions=spec.dimensions if spec else None,
            semantic_profile=spec.embedding_profile if spec else None,
            semantic_template_version=spec.text_template_version if spec else None,
            semantic_api_key_env=spec.api_key_env if spec else None,
            semantic_base_url=spec.base_url if spec else None,
            semantic_candidates=spec.candidates if spec else 80,
        )
        hits = list(bundle["hits"])
        arm = PortfolioArmResult(
            name=name,
            status="ok",
            mode=spec.mode if spec else "local_hybrid",
            provider=spec.provider if spec else None,
            model=spec.model if spec else None,
            dimensions=spec.dimensions if spec else None,
            embedding_profile=spec.embedding_profile if spec else None,
            text_template_version=spec.text_template_version if spec else None,
            weight=spec.weight if spec else 1.0,
            hit_count=len(hits),
            top_doc_ids=tuple(str(hit.get("doc_id") or "") for hit in hits[:5]),
            top_bundle_keys=tuple(_bundle_key(hit) for hit in hits[:5]),
            error=None,
        )
        return arm, hits
    except (FileNotFoundError, RuntimeError, ValueError) as exc:
        arm = PortfolioArmResult(
            name=name,
            status="error",
            mode=spec.mode if spec else "local_hybrid",
            provider=spec.provider if spec else None,
            model=spec.model if spec else None,
            dimensions=spec.dimensions if spec else None,
            embedding_profile=spec.embedding_profile if spec else None,
            text_template_version=spec.text_template_version if spec else None,
            weight=spec.weight if spec else 1.0,
            hit_count=0,
            top_doc_ids=(),
            top_bundle_keys=(),
            error=_compact_error(str(exc)),
        )
        return arm, []


def _run_reranker_arm(
    query: str,
    arm_payloads: list[tuple[PortfolioArmResult, list[dict[str, Any]]]],
    *,
    name: str,
    spec: PortfolioRerankerSpec,
    limit: int,
    rrf_k: float,
    fusion_mode: str,
    min_agreement: int,
) -> tuple[PortfolioArmResult, list[dict[str, Any]]]:
    try:
        candidate_hits = _raw_hits_from_portfolio_hits(
            _fuse_hits(
                arm_payloads,
                limit=max(limit, spec.candidate_limit),
                rrf_k=rrf_k,
                fusion_mode=fusion_mode,
                min_agreement=min_agreement,
            )
        )
        report = rerank_hits(
            query,
            candidate_hits[: max(1, spec.candidate_limit)],
            provider=spec.provider,
            model=spec.model,
            top_n=spec.top_n,
            api_key_env=spec.api_key_env,
            base_url=spec.base_url,
        )
        by_bundle = {
            hit.get("portfolio_bundle_key") or _bundle_key(hit): hit
            for hit in candidate_hits
        }
        reranked_hits = []
        for result in report.results:
            hit = dict(by_bundle.get(result.bundle_key) or {})
            if not hit:
                continue
            metadata = dict(hit.get("metadata") or {})
            metadata["rerank"] = result.as_dict()
            hit["metadata"] = metadata
            hit["score"] = float(result.score)
            score_components = dict(hit.get("score_components") or {})
            score_components[f"rerank:{spec.provider}"] = float(result.score)
            hit["score_components"] = score_components
            reranked_hits.append(hit)
        arm = PortfolioArmResult(
            name=name,
            status="ok",
            mode="rerank",
            provider=spec.provider,
            model=report.model,
            dimensions=None,
            embedding_profile=None,
            text_template_version=None,
            weight=spec.weight,
            hit_count=len(reranked_hits),
            top_doc_ids=tuple(str(hit.get("doc_id") or "") for hit in reranked_hits[:5]),
            top_bundle_keys=tuple(_bundle_key(hit) for hit in reranked_hits[:5]),
            error=None,
        )
        return arm, reranked_hits
    except (RuntimeError, ValueError) as exc:
        arm = PortfolioArmResult(
            name=name,
            status="error",
            mode="rerank",
            provider=spec.provider,
            model=spec.model,
            dimensions=None,
            embedding_profile=None,
            text_template_version=None,
            weight=spec.weight,
            hit_count=0,
            top_doc_ids=(),
            top_bundle_keys=(),
            error=_compact_error(str(exc)),
        )
        return arm, []


def _run_fts_only_arm(
    db_path: str | Path,
    query: str,
    *,
    limit: int,
) -> tuple[PortfolioArmResult, list[dict[str, Any]]]:
    try:
        results = search_memory_fts_only(db_path, query, limit=limit)
        hits = build_evidence_hits_from_results(db_path, query, results)
        arm = PortfolioArmResult(
            name="fts_only",
            status="ok",
            mode="fts_only",
            provider=None,
            model=None,
            dimensions=None,
            embedding_profile=None,
            text_template_version=None,
            weight=1.0,
            hit_count=len(hits),
            top_doc_ids=tuple(str(hit.get("doc_id") or "") for hit in hits[:5]),
            top_bundle_keys=tuple(_bundle_key(hit) for hit in hits[:5]),
            error=None,
        )
        return arm, hits
    except (FileNotFoundError, RuntimeError, ValueError) as exc:
        arm = PortfolioArmResult(
            name="fts_only",
            status="error",
            mode="fts_only",
            provider=None,
            model=None,
            dimensions=None,
            embedding_profile=None,
            text_template_version=None,
            weight=1.0,
            hit_count=0,
            top_doc_ids=(),
            top_bundle_keys=(),
            error=_compact_error(str(exc)),
        )
        return arm, []


def _run_corpus2skill_navigation_arm(
    db_path: str | Path,
    query: str,
    *,
    limit: int,
) -> tuple[PortfolioArmResult, list[dict[str, Any]]]:
    try:
        route_plan = plan_workflow_route(build_query_plan(query))
        hits: list[dict[str, Any]] = []
        for doc_type in route_plan.recommended_doc_types:
            bundle = build_evidence_bundle(
                db_path,
                query,
                limit=limit,
                doc_type=doc_type,
            )
            hits.extend(bundle["hits"])
        hits = _annotate_hits(
            _dedupe_raw_hits(hits),
            {
                "portfolio_non_vector_arm": "corpus2skill_navigation",
                "workflow_route": route_plan.route,
                "recommended_doc_types": list(route_plan.recommended_doc_types),
                "navigation_source": "corpus2skill_export_boundary",
            },
        )
        return (
            _arm_from_hits(
                "corpus2skill_navigation",
                hits,
                mode="navigation_map",
                weight=0.85,
            ),
            hits,
        )
    except (FileNotFoundError, RuntimeError, ValueError) as exc:
        return _errored_nonsemantic_arm(
            "corpus2skill_navigation",
            mode="navigation_map",
            error=str(exc),
            weight=0.85,
        )


def _run_source_bundle_context_arm(
    db_path: str | Path,
    query: str,
    *,
    limit: int,
) -> tuple[PortfolioArmResult, list[dict[str, Any]]]:
    try:
        bundle = build_context_bundle(db_path, query, limit=limit, store=False)
        hits = _annotate_hits(
            list(bundle.retrieved_hits),
            {
                "portfolio_non_vector_arm": "source_bundle_context",
                "context_run_id": bundle.run_id,
                "context_chunk_count": len(bundle.context_chunks),
                "citation_count": len(bundle.citation_annotations),
            },
        )
        return (
            _arm_from_hits(
                "source_bundle_context",
                hits,
                mode="source_bundle_context",
                weight=1.05,
            ),
            hits,
        )
    except (FileNotFoundError, RuntimeError, ValueError) as exc:
        return _errored_nonsemantic_arm(
            "source_bundle_context",
            mode="source_bundle_context",
            error=str(exc),
            weight=1.05,
        )


def _run_workflow_route_arm(
    db_path: str | Path,
    query: str,
    *,
    limit: int,
) -> tuple[PortfolioArmResult, list[dict[str, Any]]]:
    try:
        workflow = run_memory_workflow(db_path, query, limit=limit, max_steps=2, store=False)
        hits = list(workflow.context_bundle.retrieved_hits) if workflow.context_bundle else []
        hits = _annotate_hits(
            hits,
            {
                "portfolio_non_vector_arm": "workflow_route",
                "workflow_id": workflow.workflow_id,
                "workflow_route": workflow.route,
                "workflow_status": workflow.status,
                "workflow_stop_reason": workflow.stop_reason,
                "workflow_step_count": len(workflow.steps),
            },
        )
        status = "ok" if workflow.context_bundle is not None else workflow.status
        return (
            _arm_from_hits(
                "workflow_route",
                hits,
                mode="bounded_workflow",
                status=status,
                error=None if status != "error" else workflow.stop_reason,
                weight=1.05,
            ),
            hits,
        )
    except (FileNotFoundError, RuntimeError, ValueError) as exc:
        return _errored_nonsemantic_arm(
            "workflow_route",
            mode="bounded_workflow",
            error=str(exc),
            weight=1.05,
        )


def _arm_from_hits(
    name: str,
    hits: list[dict[str, Any]],
    *,
    mode: str,
    status: str = "ok",
    error: str | None = None,
    weight: float = 1.0,
) -> PortfolioArmResult:
    return PortfolioArmResult(
        name=name,
        status=status,
        mode=mode,
        provider=None,
        model=None,
        dimensions=None,
        embedding_profile=None,
        text_template_version=None,
        weight=weight,
        hit_count=len(hits),
        top_doc_ids=tuple(str(hit.get("doc_id") or "") for hit in hits[:5]),
        top_bundle_keys=tuple(_bundle_key(hit) for hit in hits[:5]),
        error=_compact_error(error) if error else None,
    )


def _errored_nonsemantic_arm(
    name: str,
    *,
    mode: str,
    error: str,
    weight: float,
) -> tuple[PortfolioArmResult, list[dict[str, Any]]]:
    return (
        PortfolioArmResult(
            name=name,
            status="error",
            mode=mode,
            provider=None,
            model=None,
            dimensions=None,
            embedding_profile=None,
            text_template_version=None,
            weight=weight,
            hit_count=0,
            top_doc_ids=(),
            top_bundle_keys=(),
            error=_compact_error(error),
        ),
        [],
    )


def _dedupe_raw_hits(hits: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    deduped: list[dict[str, Any]] = []
    for hit in hits:
        key = _bundle_key(hit)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(hit)
    return deduped


def _annotate_hits(
    hits: list[dict[str, Any]],
    metadata: dict[str, Any],
) -> list[dict[str, Any]]:
    annotated: list[dict[str, Any]] = []
    for hit in hits:
        item = dict(hit)
        item_metadata = dict(item.get("metadata") or {})
        item_metadata.update(metadata)
        item["metadata"] = item_metadata
        annotated.append(item)
    return annotated


def _run_semantic_only_arm(
    db_path: str | Path,
    query: str,
    *,
    name: str,
    spec: PortfolioSemanticSpec,
    limit: int,
    index: LoadedSemanticIndex | None = None,
) -> tuple[PortfolioArmResult, list[dict[str, Any]]]:
    if index is not None:
        semantic_hits = semantic_search_loaded_index(index, query, limit=limit)
    else:
        semantic_hits = semantic_search_memory(
            db_path,
            query,
            provider=None if spec.provider == "auto" else spec.provider,
            model=spec.model,
            dimensions=spec.dimensions,
            embedding_profile=spec.embedding_profile,
            text_template_version=spec.text_template_version,
            api_key_env=spec.api_key_env,
            base_url=spec.base_url,
            limit=limit,
        )
    metadata_by_doc_id = {
        hit.doc_id: {
            "retrieval_method": "semantic_only",
            "semantic": {
                "provider": hit.provider,
                "model": hit.model,
                "dimensions": hit.dimensions,
                "embedding_profile": hit.embedding_profile,
                "text_template_version": hit.text_template_version,
                "similarity": hit.similarity,
            },
            "rank_score_components": {"semantic": hit.similarity},
            "engine_contributions": [
                {
                    "engine": "semantic",
                    "rank": rank,
                    "raw_score": hit.similarity,
                    "route_weight": 1.0,
                    "rrf": round(1.0 / (60.0 + rank), 8),
                    "provider": hit.provider,
                    "model": hit.model,
                    "dimensions": hit.dimensions,
                    "embedding_profile": hit.embedding_profile,
                    "text_template_version": hit.text_template_version,
                }
            ],
        }
        for rank, hit in enumerate(semantic_hits, start=1)
    }
    hits = build_evidence_hits_for_doc_ids(
        db_path,
        query,
        tuple(hit.doc_id for hit in semantic_hits),
        score_by_doc_id={hit.doc_id: hit.similarity for hit in semantic_hits},
        metadata_by_doc_id=metadata_by_doc_id,
    )
    hits = _filter_raw_hits_by_query_anchors(query, hits)
    arm = PortfolioArmResult(
        name=name,
        status="ok",
        mode=spec.mode,
        provider=spec.provider,
        model=spec.model,
        dimensions=spec.dimensions,
        embedding_profile=spec.embedding_profile,
        text_template_version=spec.text_template_version,
        weight=spec.weight,
        hit_count=len(hits),
        top_doc_ids=tuple(str(hit.get("doc_id") or "") for hit in hits[:5]),
        top_bundle_keys=tuple(_bundle_key(hit) for hit in hits[:5]),
        error=None,
    )
    return arm, hits


def _filter_raw_hits_by_query_anchors(
    query: str,
    hits: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    anchors = strong_anchor_terms_for_query(query)
    if not anchors:
        return hits
    return [hit for hit in hits if _raw_hit_matches_anchors(hit, anchors)]


def _raw_hit_matches_anchors(hit: dict[str, Any], anchors: tuple[str, ...]) -> bool:
    return text_matches_any_anchor(
        anchors,
        hit.get("doc_id"),
        hit.get("tweet_id"),
        hit.get("title"),
        hit.get("compact_text"),
        json.dumps(hit.get("matched_terms") or (), ensure_ascii=False, sort_keys=True),
        json.dumps(hit.get("metadata") or {}, ensure_ascii=False, sort_keys=True),
        json.dumps(hit.get("evidence") or {}, ensure_ascii=False, sort_keys=True),
    )


def _evaluate_arms(
    case: EvalCase,
    arm_payloads: list[tuple[PortfolioArmResult, list[dict[str, Any]]]],
    *,
    limit: int,
) -> list[tuple[PortfolioArmResult, list[dict[str, Any]]]]:
    evaluated: list[tuple[PortfolioArmResult, list[dict[str, Any]]]] = []
    for arm, hits in arm_payloads:
        if arm.status != "ok":
            note = arm.error or "arm failed"
            evaluated.append(
                (
                    replace(
                        arm,
                        case_status="error",
                        case_notes=(note,),
                    ),
                    hits,
                )
            )
            continue
        arm_hits = _portfolio_hits_from_raw_hits(hits, limit=limit)
        notes = _case_notes(case, arm_hits)
        evaluated.append(
            (
                replace(
                    arm,
                    case_status=_case_status(case, notes, arm_hits),
                    case_notes=tuple(notes),
                    required_terms_found=_required_terms_found(case, arm_hits),
                    preferred_doc_type_found=_preferred_doc_type_found(case, arm_hits),
                    required_feature_found=_feature_found(case.required_feature, arm_hits),
                ),
                hits,
            )
        )
    return evaluated


def _portfolio_hits_from_raw_hits(
    hits: list[dict[str, Any]],
    *,
    limit: int,
) -> list[PortfolioHit]:
    portfolio_hits = []
    for index, raw in enumerate(hits[:limit], start=1):
        hit = dict(raw)
        bundle_key = _bundle_key(hit)
        metadata = dict(hit.get("metadata") or {})
        metadata["evidence"] = hit.get("evidence") or {}
        metadata["rank_score_components"] = hit.get("score_components") or {}
        metadata["portfolio_bundle_key"] = bundle_key
        portfolio_hits.append(
            PortfolioHit(
                rank=index,
                bundle_key=bundle_key,
                doc_id=str(hit.get("doc_id") or ""),
                doc_type=str(hit.get("doc_type") or ""),
                tweet_id=_string_or_none(hit.get("tweet_id")),
                score=float(hit.get("score") or 0.0),
                title=str(hit.get("title") or ""),
                compact_text=str(hit.get("compact_text") or ""),
                contributions=(),
                metadata=metadata,
            )
        )
    return portfolio_hits


def _raw_hits_from_portfolio_hits(hits: list[PortfolioHit]) -> list[dict[str, Any]]:
    raw_hits = []
    for hit in hits:
        metadata = dict(hit.metadata)
        evidence = metadata.get("evidence") if isinstance(metadata.get("evidence"), dict) else {}
        raw_hits.append(
            {
                "doc_id": hit.doc_id,
                "doc_type": hit.doc_type,
                "tweet_id": hit.tweet_id,
                "score": hit.score,
                "title": hit.title,
                "compact_text": hit.compact_text,
                "metadata": metadata,
                "evidence": evidence,
                "score_components": metadata.get("rank_score_components") or {},
                "portfolio_bundle_key": hit.bundle_key,
            }
        )
    return raw_hits


def _fuse_hits(
    arm_payloads: list[tuple[PortfolioArmResult, list[dict[str, Any]]]],
    *,
    limit: int,
    rrf_k: float,
    fusion_mode: str = "guarded_rrf",
    min_agreement: int = 2,
) -> list[PortfolioHit]:
    buckets: dict[str, dict[str, Any]] = {}
    for arm, hits in arm_payloads:
        if arm.status != "ok":
            continue
        for rank, hit in enumerate(hits, start=1):
            key = _bundle_key(hit)
            contribution = {
                "arm": arm.name,
                "rank": rank,
                "rrf": round(float(arm.weight) / (rrf_k + rank), 8),
                "provider": arm.provider,
                "model": arm.model,
                "dimensions": arm.dimensions,
                "embedding_profile": arm.embedding_profile,
                "text_template_version": arm.text_template_version,
            }
            bucket = buckets.setdefault(
                key,
                {
                    "hit": hit,
                    "score": 0.0,
                    "best_rank": rank,
                    "contributions": [],
                    "doc_ids": set(),
                    "doc_types": set(),
                },
            )
            bucket["score"] = float(bucket["score"]) + float(contribution["rrf"])
            bucket["contributions"].append(contribution)
            bucket["doc_ids"].add(str(hit.get("doc_id") or ""))
            bucket["doc_types"].add(str(hit.get("doc_type") or ""))
            if _prefer_representative(hit, dict(bucket["hit"]), rank, int(bucket["best_rank"])):
                bucket["hit"] = hit
                bucket["best_rank"] = rank
    ranked = sorted(
        buckets.items(),
        key=lambda item: (float(item[1]["score"]), -int(item[1]["best_rank"])),
        reverse=True,
    )
    ranked = _apply_fusion_guard(
        ranked,
        fusion_mode=fusion_mode,
        min_agreement=max(1, min_agreement),
    )
    fused = []
    for index, (bundle_key, bucket) in enumerate(ranked[:limit], start=1):
        hit = dict(bucket["hit"])
        metadata = dict(hit.get("metadata") or {})
        metadata["evidence"] = hit.get("evidence") or {}
        metadata["rank_score_components"] = hit.get("score_components") or {}
        metadata["portfolio_bundle_key"] = bundle_key
        metadata["portfolio_contributions"] = bucket["contributions"]
        metadata["portfolio_doc_ids"] = sorted(value for value in bucket["doc_ids"] if value)
        metadata["portfolio_doc_types"] = sorted(value for value in bucket["doc_types"] if value)
        fused.append(
            PortfolioHit(
                rank=index,
                bundle_key=bundle_key,
                doc_id=str(hit.get("doc_id") or ""),
                doc_type=str(hit.get("doc_type") or ""),
                tweet_id=_string_or_none(hit.get("tweet_id")),
                score=round(float(bucket["score"]), 8),
                title=str(hit.get("title") or ""),
                compact_text=str(hit.get("compact_text") or ""),
                contributions=tuple(bucket["contributions"]),
                metadata=metadata,
            )
        )
    return fused


def _apply_fusion_guard(
    ranked: list[tuple[str, dict[str, Any]]],
    *,
    fusion_mode: str,
    min_agreement: int,
) -> list[tuple[str, dict[str, Any]]]:
    if fusion_mode == "rrf":
        return ranked
    if fusion_mode != "guarded_rrf":
        raise ValueError(f"unknown portfolio fusion mode: {fusion_mode}")
    lexical_backed: list[tuple[str, dict[str, Any]]] = []
    agreed: list[tuple[str, dict[str, Any]]] = []
    deferred: list[tuple[str, dict[str, Any]]] = []
    for item in ranked:
        _bundle_key, bucket = item
        if _baseline_contribution_rank(bucket) is not None:
            lexical_backed.append(item)
        elif _passes_guard(bucket, min_agreement=min_agreement):
            agreed.append(item)
        else:
            deferred.append(item)
    lexical_backed.sort(key=lambda item: _baseline_contribution_rank(item[1]) or 10**9)
    return lexical_backed + agreed + deferred


def _passes_guard(bucket: dict[str, Any], *, min_agreement: int) -> bool:
    contributions = bucket.get("contributions") or ()
    arm_names = {
        str(contribution.get("arm") or "")
        for contribution in contributions
        if isinstance(contribution, dict)
    }
    return bool(arm_names.intersection(BASELINE_ARM_NAMES)) or len(arm_names) >= min_agreement


def _baseline_contribution_rank(bucket: dict[str, Any]) -> int | None:
    ranks = [
        int(contribution.get("rank") or 10**9)
        for contribution in bucket.get("contributions") or ()
        if isinstance(contribution, dict) and contribution.get("arm") in BASELINE_ARM_NAMES
    ]
    return min(ranks) if ranks else None


def _resolve_fusion_mode(value: str) -> str:
    normalized = (value or "guarded_rrf").strip().lower().replace("-", "_")
    if normalized not in {"rrf", "guarded_rrf"}:
        raise ValueError("portfolio fusion mode must be 'rrf' or 'guarded_rrf'")
    return normalized


def _resolve_arm_mode(value: str | None) -> str:
    normalized = (value or "semantic_only").strip().lower().replace("-", "_")
    if normalized not in {"semantic_only", "hybrid"}:
        raise ValueError("portfolio semantic arm mode must be 'semantic_only' or 'hybrid'")
    return normalized


def _resolve_provider(value: str) -> str:
    return value.strip().lower().replace("-", "_")


def _case_notes(case: EvalCase, hits: list[PortfolioHit]) -> list[str]:
    notes: list[str] = []
    if not hits:
        if _case_allows_no_hits(case):
            return ["expected no local evidence"]
        return ["no hits"]
    if case.required_any_terms and not _required_terms_found(case, hits):
        notes.append("required term family missing")
    if case.preferred_doc_types and not _preferred_doc_type_found(case, hits):
        notes.append(f"preferred doc type missing: {', '.join(case.preferred_doc_types)}")
    if case.required_feature and not _feature_found(case.required_feature, hits):
        notes.append(f"required feature missing: {case.required_feature}")
    return notes


def _case_status(case: EvalCase, notes: list[str], hits: list[PortfolioHit]) -> str:
    if not hits:
        return "ok" if _case_allows_no_hits(case) else "fail"
    if "required term family missing" in notes and not _case_allows_evidence_gap(case):
        return "fail"
    return "ok" if not notes else "needs_review"


def _case_allows_no_hits(case: EvalCase) -> bool:
    return case.min_hit_score <= 0.0 and "no_local_evidence" in case.expected_stop_reasons


def _case_allows_evidence_gap(case: EvalCase) -> bool:
    return any(
        reason in case.expected_stop_reasons
        for reason in ("no_local_evidence", "external_context_needed")
    )


def _best_case_arm(arms: tuple[PortfolioArmResult, ...]) -> PortfolioArmResult | None:
    if not arms:
        return None
    return max(arms, key=lambda arm: _status_strength(arm.case_status or arm.status))


def _status_strength(status: str | None) -> int:
    return {
        "ok": 3,
        "needs_review": 2,
        "fail": 1,
        "error": 0,
    }.get(status or "", -1)


def _arm_summaries(cases: tuple[PortfolioCaseResult, ...]) -> tuple[PortfolioArmSummary, ...]:
    buckets: dict[str, dict[str, Any]] = {}
    for case in cases:
        for arm in case.arms:
            bucket = buckets.setdefault(
                arm.name,
                {
                    "name": arm.name,
                    "mode": arm.mode,
                    "provider": arm.provider,
                    "model": arm.model,
                    "dimensions": arm.dimensions,
                    "case_count": 0,
                    "ok": 0,
                    "needs_review": 0,
                    "fail": 0,
                    "error": 0,
                },
            )
            bucket["case_count"] += 1
            status = arm.case_status or arm.status
            if status in {"ok", "needs_review", "fail", "error"}:
                bucket[status] += 1
            else:
                bucket["error"] += 1
    return tuple(
        PortfolioArmSummary(
            name=str(bucket["name"]),
            mode=_string_or_none(bucket["mode"]),
            provider=_string_or_none(bucket["provider"]),
            model=_string_or_none(bucket["model"]),
            dimensions=(
                int(bucket["dimensions"]) if bucket["dimensions"] is not None else None
            ),
            case_count=int(bucket["case_count"]),
            ok=int(bucket["ok"]),
            needs_review=int(bucket["needs_review"]),
            fail=int(bucket["fail"]),
            error=int(bucket["error"]),
        )
        for bucket in buckets.values()
    )


def _promotion_verdict(
    cases: tuple[PortfolioCaseResult, ...],
    arm_summaries: tuple[PortfolioArmSummary, ...],
    semantic_specs: tuple[PortfolioSemanticSpec, ...],
    reranker_specs: tuple[PortfolioRerankerSpec, ...],
) -> PortfolioPromotionVerdict:
    fused_counts = _case_status_counts(case.status for case in cases)
    baseline = _summary_by_name(arm_summaries, "local_hybrid")
    best_single = _best_single_arm(arm_summaries)
    blockers: list[str] = []
    if not semantic_specs and not reranker_specs:
        blockers.append("no candidate semantic or reranker arms were configured")
    diagnostic_specs = [
        spec.provider for spec in semantic_specs if spec.provider in DIAGNOSTIC_EMBEDDING_PROVIDERS
    ]
    if diagnostic_specs:
        blockers.append(
            "diagnostic embedding providers cannot be promoted: "
            + ", ".join(sorted(set(diagnostic_specs)))
        )
    hybrid_specs = [spec.name or spec.provider for spec in semantic_specs if spec.mode == "hybrid"]
    if hybrid_specs:
        blockers.append(
            "hybrid semantic arms are comparison-only until provider score calibration "
            "is explicit: "
            + ", ".join(sorted(set(hybrid_specs)))
        )
    if not cases:
        blockers.append("no eval cases were run")
    if fused_counts["fail"]:
        blockers.append(f"fused result has {fused_counts['fail']} failing case(s)")
    regressed_cases = sum(1 for case in cases if case.fusion_regressed)
    if regressed_cases:
        blockers.append(
            f"fused result regressed on {regressed_cases} case(s) against the best arm"
        )
    if any(summary.error for summary in arm_summaries):
        errored = ", ".join(
            f"{summary.name}:{summary.error}" for summary in arm_summaries if summary.error
        )
        blockers.append(f"candidate arm errors present: {errored}")
    if best_single and not _fused_beats_single(fused_counts, best_single):
        blockers.append(f"fused result does not beat best single arm: {best_single.name}")
    promotable = not blockers
    if not semantic_specs and not reranker_specs:
        status = "insufficient_candidate_arms"
        reason = "configure at least one candidate semantic or reranker arm before promotion"
    elif promotable:
        status = "promote_candidate"
        reason = "fused portfolio beats the strongest single arm with no blockers"
    else:
        status = "hold"
        reason = "portfolio did not clear promotion gates"
    return PortfolioPromotionVerdict(
        status=status,
        promotable=promotable,
        reason=reason,
        baseline_arm=baseline.name if baseline else None,
        best_single_arm=best_single.name if best_single else None,
        fused_ok=fused_counts["ok"],
        fused_needs_review=fused_counts["needs_review"],
        fused_fail=fused_counts["fail"],
        best_single_ok=best_single.ok if best_single else 0,
        best_single_needs_review=best_single.needs_review if best_single else 0,
        best_single_fail=best_single.fail if best_single else 0,
        blockers=tuple(blockers),
    )


def _case_status_counts(statuses: Any) -> dict[str, int]:
    counts = {"ok": 0, "needs_review": 0, "fail": 0}
    for status in statuses:
        if status in counts:
            counts[status] += 1
    return counts


def _summary_by_name(
    summaries: tuple[PortfolioArmSummary, ...],
    name: str,
) -> PortfolioArmSummary | None:
    return next((summary for summary in summaries if summary.name == name), None)


def _best_single_arm(
    summaries: tuple[PortfolioArmSummary, ...],
) -> PortfolioArmSummary | None:
    if not summaries:
        return None
    return max(summaries, key=_arm_strength_key)


def _arm_strength_key(summary: PortfolioArmSummary) -> tuple[int, int, int, int]:
    return (
        summary.ok,
        -summary.fail,
        -summary.needs_review,
        -summary.error,
    )


def _fused_beats_single(
    fused_counts: dict[str, int],
    best_single: PortfolioArmSummary,
) -> bool:
    fused_key = (
        fused_counts["ok"],
        -fused_counts["fail"],
        -fused_counts["needs_review"],
        0,
    )
    return fused_key > _arm_strength_key(best_single)


def _required_terms_found(case: EvalCase, hits: list[PortfolioHit]) -> bool:
    if not case.required_any_terms:
        return True
    return any(_term_matches(term, hit) for term in case.required_any_terms for hit in hits)


def _preferred_doc_type_found(case: EvalCase, hits: list[PortfolioHit]) -> bool:
    if not case.preferred_doc_types:
        return True
    preferred = set(case.preferred_doc_types)
    for hit in hits:
        if hit.doc_type in preferred:
            return True
        doc_types = hit.metadata.get("portfolio_doc_types")
        if isinstance(doc_types, list) and any(str(value) in preferred for value in doc_types):
            return True
    return False


def _feature_found(feature: str | None, hits: list[PortfolioHit]) -> bool:
    if feature is None:
        return True
    for hit in hits:
        if feature == "bookmark_context" and hit.doc_type == "bookmark_doc":
            return True
        if feature == "quote_context" and _metadata_has_evidence(hit, "quoted_tweets"):
            return True
        if feature == "media_context" and _metadata_has_evidence(hit, "media"):
            return True
        if feature == "cross_account" and int(hit.metadata.get("bookmark_account_count") or 0) > 1:
            return True
        if feature == "event_dates" and _term_matches("202", hit):
            return True
        if feature == "recent" and hit.metadata.get("freshness") == "recent":
            return True
        if feature == "freshness":
            score = float((hit.metadata.get("rank_score_components") or {}).get("freshness") or 0.0)
            if abs(score) > 0.0001:
                return True
    return False


def _metadata_has_evidence(hit: PortfolioHit, key: str) -> bool:
    evidence = hit.metadata.get("evidence")
    if isinstance(evidence, dict):
        return bool(evidence.get(key))
    return False


def _term_matches(term: str, hit: PortfolioHit) -> bool:
    needle = term.casefold()
    haystack = "\n".join(
        [
            hit.title,
            hit.compact_text,
            hit.doc_type,
            json.dumps(hit.metadata, ensure_ascii=False),
        ]
    ).casefold()
    return needle in haystack


def _bundle_key(hit: dict[str, Any]) -> str:
    tweet_id = _string_or_none(hit.get("tweet_id"))
    if tweet_id:
        return f"tweet:{tweet_id}"
    evidence = hit.get("evidence") if isinstance(hit.get("evidence"), dict) else {}
    derived = evidence.get("derived") if isinstance(evidence.get("derived"), dict) else {}
    source_tweet_ids = [str(value) for value in derived.get("source_tweet_ids") or () if value]
    if source_tweet_ids:
        return "source_tweets:" + ",".join(sorted(source_tweet_ids)[:8])
    doc_id = str(hit.get("doc_id") or "")
    return f"doc:{doc_id}"


def _semantic_arm_name(spec: PortfolioSemanticSpec, *, index: int) -> str:
    parts = [f"semantic{index}", spec.mode, spec.provider]
    if spec.model:
        parts.append(spec.model)
    if spec.embedding_profile:
        parts.append(spec.embedding_profile)
    if spec.dimensions:
        parts.append(str(spec.dimensions))
    return ":".join(parts)


def _reranker_arm_name(spec: PortfolioRerankerSpec, *, index: int) -> str:
    parts = [f"rerank{index}", spec.provider]
    if spec.model:
        parts.append(spec.model)
    return ":".join(parts)


def _prefer_representative(
    candidate: dict[str, Any],
    current: dict[str, Any],
    candidate_rank: int,
    current_rank: int,
) -> bool:
    candidate_priority = _doc_type_context_priority(str(candidate.get("doc_type") or ""))
    current_priority = _doc_type_context_priority(str(current.get("doc_type") or ""))
    if candidate_priority != current_priority:
        return candidate_priority > current_priority
    return candidate_rank < current_rank


def _doc_type_context_priority(doc_type: str) -> int:
    return {
        "quote_tree_doc": 70,
        "bookmark_doc": 60,
        "media_doc": 55,
        "place_card": 50,
        "ticker_event": 50,
        "author_profile": 45,
        "topic_thread": 45,
        "tweet_doc": 30,
    }.get(doc_type, 10)


def _parse_fields(value: str) -> dict[str, str]:
    parts = [part.strip() for part in value.split(",") if part.strip()]
    if not parts:
        raise ValueError("portfolio semantic spec must not be empty")
    fields: dict[str, str] = {}
    for part in parts:
        if "=" not in part:
            if "provider" in fields:
                raise ValueError(f"portfolio semantic spec field must use key=value: {part}")
            fields["provider"] = part
            continue
        key, raw = part.split("=", 1)
        key = key.strip().replace("-", "_")
        raw = raw.strip()
        if not key or raw == "":
            raise ValueError(f"portfolio semantic spec field must use non-empty key=value: {part}")
        fields[key] = raw
    return fields


def _optional_int(value: str | None, *, name: str) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc


def _optional_float(value: str | None, *, name: str) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except ValueError as exc:
        raise ValueError(f"{name} must be a number") from exc


def _string_or_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _compact_error(value: str, *, limit: int = 500) -> str:
    text = " ".join(value.split())
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 3)].rstrip() + "..."
