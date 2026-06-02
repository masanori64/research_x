from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from research_x.memory.evals import DEFAULT_EVAL_CASES, EvalCase
from research_x.memory.evidence import build_evidence_bundle


@dataclass(frozen=True)
class PortfolioSemanticSpec:
    provider: str
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
class PortfolioArmResult:
    name: str
    status: str
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
    arms: tuple[PortfolioArmResult, ...]
    fused_hits: tuple[PortfolioHit, ...]
    required_terms_found: bool
    preferred_doc_type_found: bool
    required_feature_found: bool


@dataclass(frozen=True)
class PortfolioEvalReport:
    cases: tuple[PortfolioCaseResult, ...]
    parameters: dict[str, Any]


def parse_portfolio_semantic_spec(value: str) -> PortfolioSemanticSpec:
    fields = _parse_fields(value)
    provider = fields.pop("provider", None)
    if not provider:
        raise ValueError("portfolio semantic spec requires provider=...")
    aliases = {
        "profile": "embedding_profile",
        "template": "text_template_version",
        "template_version": "text_template_version",
        "api_key": "api_key_env",
        "key_env": "api_key_env",
        "url": "base_url",
    }
    normalized = {aliases.get(key, key): raw for key, raw in fields.items()}
    allowed = {
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


def run_portfolio_eval(
    db_path: str | Path,
    *,
    cases: tuple[EvalCase, ...] | None = None,
    semantic_specs: tuple[PortfolioSemanticSpec, ...] = (),
    limit: int = 5,
    arm_limit: int = 20,
    rrf_k: float = 60.0,
) -> PortfolioEvalReport:
    resolved_cases = cases or DEFAULT_EVAL_CASES
    parameters = {
        "limit": max(1, limit),
        "arm_limit": max(1, arm_limit),
        "rrf_k": float(rrf_k),
        "semantic_specs": [asdict(spec) for spec in semantic_specs],
    }
    results = tuple(
        _run_case(
            db_path,
            case=case,
            semantic_specs=semantic_specs,
            limit=max(1, limit),
            arm_limit=max(1, arm_limit),
            rrf_k=max(1.0, float(rrf_k)),
        )
        for case in resolved_cases
    )
    return PortfolioEvalReport(cases=results, parameters=parameters)


def portfolio_eval_json(report: PortfolioEvalReport) -> str:
    return json.dumps(asdict(report), ensure_ascii=False, indent=2, sort_keys=True)


def format_portfolio_eval(report: PortfolioEvalReport) -> str:
    lines = [
        "portfolio-eval: "
        f"cases={len(report.cases)} semantic_specs={len(report.parameters['semantic_specs'])}"
    ]
    for case in report.cases:
        top = case.fused_hits[0].doc_id if case.fused_hits else "-"
        lines.append(
            " ".join(
                [
                    f"[{case.status}]",
                    f"type={case.question_type}",
                    f"top={top}",
                    f"arms={len(case.arms)}",
                    f"query={case.query}",
                ]
            )
        )
        for note in case.notes:
            lines.append(f"  note: {note}")
    return "\n".join(lines)


def _run_case(
    db_path: str | Path,
    *,
    case: EvalCase,
    semantic_specs: tuple[PortfolioSemanticSpec, ...],
    limit: int,
    arm_limit: int,
    rrf_k: float,
) -> PortfolioCaseResult:
    arm_payloads: list[tuple[PortfolioArmResult, list[dict[str, Any]]]] = []
    arm_payloads.append(_run_arm(db_path, case.query, name="lexical", spec=None, limit=arm_limit))
    for index, spec in enumerate(semantic_specs, start=1):
        name = spec.name or _semantic_arm_name(spec, index=index)
        arm_payloads.append(_run_arm(db_path, case.query, name=name, spec=spec, limit=arm_limit))
    fused_hits = _fuse_hits(arm_payloads, limit=limit, rrf_k=rrf_k)
    notes = _case_notes(case, fused_hits)
    status = "ok" if not notes else "needs_review"
    if not fused_hits or "required term family missing" in notes:
        status = "fail"
    return PortfolioCaseResult(
        query=case.query,
        question_type=case.question_type,
        status=status,
        notes=tuple(notes),
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
) -> tuple[PortfolioArmResult, list[dict[str, Any]]]:
    try:
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


def _fuse_hits(
    arm_payloads: list[tuple[PortfolioArmResult, list[dict[str, Any]]]],
    *,
    limit: int,
    rrf_k: float,
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
                },
            )
            bucket["score"] = float(bucket["score"]) + float(contribution["rrf"])
            bucket["contributions"].append(contribution)
            if _prefer_representative(hit, dict(bucket["hit"]), rank, int(bucket["best_rank"])):
                bucket["hit"] = hit
                bucket["best_rank"] = rank
    ranked = sorted(
        buckets.items(),
        key=lambda item: (float(item[1]["score"]), -int(item[1]["best_rank"])),
        reverse=True,
    )
    fused = []
    for index, (bundle_key, bucket) in enumerate(ranked[:limit], start=1):
        hit = dict(bucket["hit"])
        metadata = dict(hit.get("metadata") or {})
        metadata["evidence"] = hit.get("evidence") or {}
        metadata["rank_score_components"] = hit.get("score_components") or {}
        metadata["portfolio_bundle_key"] = bundle_key
        metadata["portfolio_contributions"] = bucket["contributions"]
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


def _case_notes(case: EvalCase, hits: list[PortfolioHit]) -> list[str]:
    notes: list[str] = []
    if not hits:
        return ["no fused hits"]
    if case.required_any_terms and not _required_terms_found(case, hits):
        notes.append("required term family missing")
    if case.preferred_doc_types and not _preferred_doc_type_found(case, hits):
        notes.append(f"preferred doc type missing: {', '.join(case.preferred_doc_types)}")
    if case.required_feature and not _feature_found(case.required_feature, hits):
        notes.append(f"required feature missing: {case.required_feature}")
    return notes


def _required_terms_found(case: EvalCase, hits: list[PortfolioHit]) -> bool:
    if not case.required_any_terms:
        return True
    return any(_term_matches(term, hit) for term in case.required_any_terms for hit in hits)


def _preferred_doc_type_found(case: EvalCase, hits: list[PortfolioHit]) -> bool:
    if not case.preferred_doc_types:
        return True
    return any(hit.doc_type in case.preferred_doc_types for hit in hits)


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
    parts = [f"semantic{index}", spec.provider]
    if spec.model:
        parts.append(spec.model)
    if spec.embedding_profile:
        parts.append(spec.embedding_profile)
    if spec.dimensions:
        parts.append(str(spec.dimensions))
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
