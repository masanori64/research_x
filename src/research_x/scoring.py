from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC
from statistics import median

from research_x.contracts import FetchOutcome, OutcomeStatus, PromotionStatus

DEFAULT_WEIGHTS = {
    "success_rate": 0.35,
    "item_yield": 0.20,
    "freshness": 0.15,
    "latency": 0.15,
    "coverage": 0.15,
}

DEFAULT_THRESHOLDS = {
    "min_score": 0.70,
    "min_success_rate": 0.90,
    "min_items": 1.0,
    "max_error_rate": 0.10,
    "max_median_latency_ms": 5000.0,
}


@dataclass(frozen=True)
class AdapterMetrics:
    adapter_id: str
    attempts: int
    successes: int
    partials: int
    errors: int
    not_configured: int
    total_items: int
    success_rate: float
    error_rate: float
    median_latency_ms: float
    coverage: float
    freshness: float
    score: float
    promotion_status: PromotionStatus
    promotion_reasons: tuple[str, ...]


def score_adapters(
    outcomes: list[FetchOutcome],
    expected_targets: int,
    weights: dict[str, float] | None = None,
    thresholds: dict[str, float] | None = None,
) -> dict[str, AdapterMetrics]:
    resolved_weights = _normalize_weights(weights or DEFAULT_WEIGHTS)
    resolved_thresholds = {**DEFAULT_THRESHOLDS, **(thresholds or {})}
    by_adapter: dict[str, list[FetchOutcome]] = {}
    for outcome in outcomes:
        by_adapter.setdefault(outcome.adapter_id, []).append(outcome)
    return {
        adapter_id: _score_one(
            adapter_id,
            adapter_outcomes,
            expected_targets,
            resolved_weights,
            resolved_thresholds,
        )
        for adapter_id, adapter_outcomes in sorted(by_adapter.items())
    }


def _score_one(
    adapter_id: str,
    outcomes: list[FetchOutcome],
    expected_targets: int,
    weights: dict[str, float],
    thresholds: dict[str, float],
) -> AdapterMetrics:
    attempts = len(outcomes)
    successes = sum(outcome.status == OutcomeStatus.OK for outcome in outcomes)
    partials = sum(outcome.status == OutcomeStatus.PARTIAL for outcome in outcomes)
    errors = sum(outcome.status == OutcomeStatus.ERROR for outcome in outcomes)
    not_configured = sum(outcome.status == OutcomeStatus.NOT_CONFIGURED for outcome in outcomes)
    total_items = sum(len(outcome.items) for outcome in outcomes)
    usable = successes + partials
    success_rate = usable / attempts if attempts else 0.0
    error_rate = (errors + not_configured) / attempts if attempts else 0.0
    latencies = [outcome.latency_ms for outcome in outcomes]
    median_latency_ms = median(latencies) if latencies else 0.0
    coverage = min(1.0, usable / expected_targets) if expected_targets else 0.0
    freshness = _freshness_score(outcomes)
    item_yield = min(1.0, total_items / _expected_item_count(outcomes))
    latency_score = 1.0 / (1.0 + median_latency_ms / 1000.0)
    score = (
        weights["success_rate"] * success_rate
        + weights["item_yield"] * item_yield
        + weights["freshness"] * freshness
        + weights["latency"] * latency_score
        + weights["coverage"] * coverage
    )
    promotion_status, reasons = _promotion_status(
        score=score,
        success_rate=success_rate,
        error_rate=error_rate,
        total_items=total_items,
        median_latency_ms=median_latency_ms,
        thresholds=thresholds,
    )
    return AdapterMetrics(
        adapter_id=adapter_id,
        attempts=attempts,
        successes=successes,
        partials=partials,
        errors=errors,
        not_configured=not_configured,
        total_items=total_items,
        success_rate=success_rate,
        error_rate=error_rate,
        median_latency_ms=median_latency_ms,
        coverage=coverage,
        freshness=freshness,
        score=score,
        promotion_status=promotion_status,
        promotion_reasons=reasons,
    )


def _normalize_weights(weights: dict[str, float]) -> dict[str, float]:
    merged = {**DEFAULT_WEIGHTS, **weights}
    total = sum(merged.values())
    if total <= 0:
        raise ValueError("scoring weights must sum to a positive value")
    return {key: value / total for key, value in merged.items()}


def _expected_item_count(outcomes: list[FetchOutcome]) -> int:
    return max(1, sum(outcome.target.limit for outcome in outcomes))


def _freshness_score(outcomes: list[FetchOutcome]) -> float:
    items = [item for outcome in outcomes for item in outcome.items if item.created_at is not None]
    if not items:
        return 0.0
    observed_latest = max(item.observed_at for item in items)
    item_scores = []
    for item in items:
        created_at = item.created_at
        if created_at is None:
            continue
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=UTC)
        age_seconds = max(0.0, (observed_latest - created_at).total_seconds())
        item_scores.append(1.0 / (1.0 + age_seconds / 86400.0))
    return sum(item_scores) / len(item_scores) if item_scores else 0.0


def _promotion_status(
    *,
    score: float,
    success_rate: float,
    error_rate: float,
    total_items: int,
    median_latency_ms: float,
    thresholds: dict[str, float],
) -> tuple[PromotionStatus, tuple[str, ...]]:
    failures: list[str] = []
    if score < thresholds["min_score"]:
        failures.append(f"score {score:.3f} < {thresholds['min_score']:.3f}")
    if success_rate < thresholds["min_success_rate"]:
        failures.append(
            f"success_rate {success_rate:.3f} < {thresholds['min_success_rate']:.3f}"
        )
    if total_items < thresholds["min_items"]:
        failures.append(f"items {total_items} < {thresholds['min_items']:.0f}")
    if error_rate > thresholds["max_error_rate"]:
        failures.append(f"error_rate {error_rate:.3f} > {thresholds['max_error_rate']:.3f}")
    if median_latency_ms > thresholds["max_median_latency_ms"]:
        failures.append(
            "median_latency_ms "
            f"{median_latency_ms:.1f} > {thresholds['max_median_latency_ms']:.1f}"
        )
    if not failures:
        return PromotionStatus.PROMOTED, ("all promotion gates passed",)
    if score >= thresholds["min_score"] * 0.85 and success_rate > 0:
        return PromotionStatus.CANDIDATE, tuple(failures)
    return PromotionStatus.REJECTED, tuple(failures)
