from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class ContextPolicyObservation:
    observation_id: str
    text: str
    citation_ready: bool
    stale: bool
    source_ref: str


@dataclass(frozen=True)
class ContextPolicyVariantResult:
    variant: str
    route: str
    observation_count: int
    citation_ready_count: int
    unsupported_context_count: int
    stale_observation_count: int
    citation_ready_yield: float
    answer_status: str
    source_refs_preserved: bool
    route_specific_masking_candidate: bool
    notes: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ContextPolicyEvalReport:
    route: str
    status: str
    baseline_variant: str
    recommended_variant: str
    global_masking_allowed: bool
    variants: tuple[ContextPolicyVariantResult, ...]
    metadata: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["variants"] = [variant.as_dict() for variant in self.variants]
        return data


def default_stale_observation_fixture() -> tuple[ContextPolicyObservation, ...]:
    return (
        ContextPolicyObservation(
            observation_id="current_cited",
            text="Current cited context says the saved robot note is still useful.",
            citation_ready=True,
            stale=False,
            source_ref="tweet:current",
        ),
        ContextPolicyObservation(
            observation_id="stale_cited",
            text="Older cited context has a stale setup detail.",
            citation_ready=True,
            stale=True,
            source_ref="tweet:stale",
        ),
        ContextPolicyObservation(
            observation_id="stale_uncited",
            text="Old observation without a citation anchor.",
            citation_ready=False,
            stale=True,
            source_ref="observation:stale-uncited",
        ),
    )


def evaluate_route_context_policy(
    observations: tuple[ContextPolicyObservation, ...] | None = None,
    *,
    route: str = "local_memory_search",
) -> ContextPolicyEvalReport:
    resolved = observations or default_stale_observation_fixture()
    variants = tuple(
        _evaluate_variant(name, route=route, observations=resolved)
        for name in ("full_history", "summary_history", "offloaded_history", "masked_history")
    )
    recommended = _best_variant(variants)
    return ContextPolicyEvalReport(
        route=route,
        status="ok" if recommended.answer_status == "ok" else "needs_review",
        baseline_variant="full_history",
        recommended_variant=recommended.variant,
        global_masking_allowed=False,
        variants=variants,
        metadata={
            "fixture": "stale_observation_context_policy",
            "variant_count": len(variants),
            "stale_observation_count": sum(1 for item in resolved if item.stale),
            "observation_count": len(resolved),
            "promotion_condition": (
                "masking can only be considered route-specific when it improves "
                "citation-ready yield or answer status without dropping source refs"
            ),
        },
    )


def context_policy_eval_json(report: ContextPolicyEvalReport) -> str:
    return json.dumps(report.as_dict(), ensure_ascii=False, indent=2, sort_keys=True)


def _evaluate_variant(
    variant: str,
    *,
    route: str,
    observations: tuple[ContextPolicyObservation, ...],
) -> ContextPolicyVariantResult:
    materialized = _materialize_variant(variant, observations)
    citation_ready_count = sum(1 for item in materialized if item.citation_ready)
    unsupported_context_count = sum(1 for item in materialized if not item.citation_ready)
    stale_count = sum(1 for item in materialized if item.stale)
    answer_status = "ok" if unsupported_context_count == 0 and stale_count == 0 else "needs_review"
    source_refs_preserved = all(bool(item.source_ref) for item in materialized)
    route_specific_masking_candidate = (
        variant == "masked_history"
        and answer_status == "ok"
        and source_refs_preserved
        and any(item.stale for item in observations)
    )
    return ContextPolicyVariantResult(
        variant=variant,
        route=route,
        observation_count=len(materialized),
        citation_ready_count=citation_ready_count,
        unsupported_context_count=unsupported_context_count,
        stale_observation_count=stale_count,
        citation_ready_yield=_ratio(citation_ready_count, len(materialized)),
        answer_status=answer_status,
        source_refs_preserved=source_refs_preserved,
        route_specific_masking_candidate=route_specific_masking_candidate,
        notes=_variant_notes(
            variant,
            unsupported_context_count=unsupported_context_count,
            stale_count=stale_count,
            source_refs_preserved=source_refs_preserved,
        ),
    )


def _materialize_variant(
    variant: str,
    observations: tuple[ContextPolicyObservation, ...],
) -> tuple[ContextPolicyObservation, ...]:
    if variant == "full_history":
        return observations
    if variant == "summary_history":
        return tuple(
            ContextPolicyObservation(
                observation_id=item.observation_id,
                text=f"Summary: {item.text}",
                citation_ready=item.citation_ready,
                stale=item.stale,
                source_ref=item.source_ref,
            )
            for item in observations
        )
    if variant == "offloaded_history":
        return tuple(
            ContextPolicyObservation(
                observation_id=item.observation_id,
                text=f"[offloaded pointer] {item.text[:80]}",
                citation_ready=item.citation_ready,
                stale=item.stale,
                source_ref=item.source_ref,
            )
            for item in observations
        )
    if variant == "masked_history":
        return tuple(item for item in observations if not item.stale)
    raise ValueError(f"unknown context policy variant: {variant}")


def _variant_notes(
    variant: str,
    *,
    unsupported_context_count: int,
    stale_count: int,
    source_refs_preserved: bool,
) -> tuple[str, ...]:
    notes = []
    if unsupported_context_count:
        notes.append(f"unsupported_context_count={unsupported_context_count}")
    if stale_count:
        notes.append(f"stale_observation_count={stale_count}")
    if not source_refs_preserved:
        notes.append("source_refs_not_preserved")
    if variant == "masked_history":
        notes.append("masking_is_route_specific_candidate_not_global_policy")
    return tuple(notes)


def _best_variant(
    variants: tuple[ContextPolicyVariantResult, ...],
) -> ContextPolicyVariantResult:
    if not variants:
        raise ValueError("at least one context policy variant is required")
    return max(variants, key=_variant_key)


def _variant_key(result: ContextPolicyVariantResult) -> tuple[int, float, int, int]:
    status_score = 2 if result.answer_status == "ok" else 1
    return (
        status_score,
        result.citation_ready_yield,
        -result.unsupported_context_count,
        -result.stale_observation_count,
    )


def _ratio(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round(numerator / denominator, 4)
