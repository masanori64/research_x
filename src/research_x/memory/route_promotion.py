from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from research_x.memory.output_modes import OutputMode, normalize_output_mode
from research_x.memory.schema import ensure_memory_schema

EXPLORE_BLOCKING_DELTAS = {
    "expected_source_recall_at_k": "min",
    "diversity_at_k": "min",
    "negative_hit_rate": "max",
    "noise_budget_violation_rate": "max",
    "role_mismatch_rate": "max",
}
ANSWER_BLOCKING_DELTAS = {
    "source_restore_rate": "min",
    "citation_ready_rate": "min",
    "claim_support_rate": "min",
    "stale_hit_rate": "max",
    "answer_assertion_support_rate": "min",
}


@dataclass(frozen=True)
class RoutePromotionDecision:
    promotion_decision_id: str
    candidate_route_version: str
    baseline_route_version: str | None
    eval_run_ids: tuple[str, ...]
    output_modes: tuple[str, ...]
    status: str
    thresholds: dict[str, Any]
    deltas: dict[str, float]
    blocking_reasons: tuple[str, ...]
    metadata: dict[str, Any]
    created_at: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def check_route_promotion(
    db_path: str | Path,
    *,
    candidate_route_version: str,
    baseline_route_version: str | None,
    eval_run_ids: tuple[str, ...],
    output_modes: tuple[str, ...],
    deltas: dict[str, float],
    thresholds: dict[str, Any] | None = None,
    created_at: str,
    metadata: dict[str, Any] | None = None,
) -> RoutePromotionDecision:
    modes = tuple(normalize_output_mode(mode).value for mode in output_modes)
    if not candidate_route_version:
        raise ValueError("candidate_route_version is required")
    if not eval_run_ids:
        raise ValueError("eval_run_ids is required")
    if not modes:
        raise ValueError("output_modes is required")
    normalized_deltas = {str(key): float(value) for key, value in deltas.items()}
    resolved_thresholds = thresholds or {}
    blocking = _blocking_reasons(
        modes=modes,
        deltas=normalized_deltas,
        thresholds=resolved_thresholds,
    )
    decision = RoutePromotionDecision(
        promotion_decision_id=_decision_id(
            candidate_route_version=candidate_route_version,
            baseline_route_version=baseline_route_version,
            eval_run_ids=eval_run_ids,
            output_modes=modes,
            created_at=created_at,
        ),
        candidate_route_version=candidate_route_version,
        baseline_route_version=baseline_route_version,
        eval_run_ids=eval_run_ids,
        output_modes=modes,
        status="blocked" if blocking else "approved",
        thresholds=resolved_thresholds,
        deltas=normalized_deltas,
        blocking_reasons=tuple(blocking),
        metadata=metadata or {},
        created_at=created_at,
    )
    _store_decision(db_path, decision)
    return decision


def approve_route_promotion(
    db_path: str | Path,
    *,
    promotion_decision_id: str,
    approved_at: str,
    reason: str,
) -> RoutePromotionDecision:
    decision = _load_decision(db_path, promotion_decision_id)
    updated = _replace_decision_status(
        decision,
        status="approved",
        metadata={
            **decision.metadata,
            "manual_approval": {"approved_at": approved_at, "reason": reason},
        },
    )
    _store_decision(db_path, updated)
    return updated


def reject_route_promotion(
    db_path: str | Path,
    *,
    promotion_decision_id: str,
    rejected_at: str,
    reason: str,
) -> RoutePromotionDecision:
    decision = _load_decision(db_path, promotion_decision_id)
    updated = _replace_decision_status(
        decision,
        status="rejected",
        metadata={
            **decision.metadata,
            "manual_rejection": {"rejected_at": rejected_at, "reason": reason},
        },
    )
    _store_decision(db_path, updated)
    return updated


def list_route_promotion_decisions(
    db_path: str | Path,
    *,
    status: str | None = None,
) -> tuple[RoutePromotionDecision, ...]:
    with sqlite3.connect(db_path, timeout=60) as conn:
        conn.row_factory = sqlite3.Row
        ensure_memory_schema(conn)
        if status:
            rows = conn.execute(
                """
                SELECT *
                FROM memory_route_promotion_decisions
                WHERE status = ?
                ORDER BY created_at, promotion_decision_id
                """,
                (status,),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT *
                FROM memory_route_promotion_decisions
                ORDER BY created_at, promotion_decision_id
                """
            ).fetchall()
    return tuple(_decision_from_row(row) for row in rows)


def _blocking_reasons(
    *,
    modes: tuple[str, ...],
    deltas: dict[str, float],
    thresholds: dict[str, Any],
) -> list[str]:
    reasons: list[str] = []
    checks: dict[str, str] = {}
    if OutputMode.EXPLORE.value in modes:
        checks.update(EXPLORE_BLOCKING_DELTAS)
    if OutputMode.ANSWER.value in modes:
        checks.update(ANSWER_BLOCKING_DELTAS)
    for metric, direction in checks.items():
        if metric not in deltas:
            continue
        delta = deltas[metric]
        allowed = float(thresholds.get(metric, 0.0))
        if direction == "min" and delta < allowed:
            reasons.append(f"{metric}_regressed:{delta:g}<{allowed:g}")
        if direction == "max" and delta > allowed:
            reasons.append(f"{metric}_worsened:{delta:g}>{allowed:g}")
    return reasons


def _replace_decision_status(
    decision: RoutePromotionDecision,
    *,
    status: str,
    metadata: dict[str, Any],
) -> RoutePromotionDecision:
    return RoutePromotionDecision(
        promotion_decision_id=decision.promotion_decision_id,
        candidate_route_version=decision.candidate_route_version,
        baseline_route_version=decision.baseline_route_version,
        eval_run_ids=decision.eval_run_ids,
        output_modes=decision.output_modes,
        status=status,
        thresholds=decision.thresholds,
        deltas=decision.deltas,
        blocking_reasons=decision.blocking_reasons,
        metadata=metadata,
        created_at=decision.created_at,
    )


def _store_decision(
    db_path: str | Path,
    decision: RoutePromotionDecision,
) -> None:
    with sqlite3.connect(db_path, timeout=60) as conn:
        ensure_memory_schema(conn)
        conn.execute(
            """
            INSERT INTO memory_route_promotion_decisions (
                promotion_decision_id, candidate_route_version,
                baseline_route_version, eval_run_ids_json, output_modes_json,
                status, thresholds_json, deltas_json, blocking_reasons_json,
                metadata_json, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(promotion_decision_id) DO UPDATE SET
                status=excluded.status,
                thresholds_json=excluded.thresholds_json,
                deltas_json=excluded.deltas_json,
                blocking_reasons_json=excluded.blocking_reasons_json,
                metadata_json=excluded.metadata_json
            """,
            (
                decision.promotion_decision_id,
                decision.candidate_route_version,
                decision.baseline_route_version,
                _json(list(decision.eval_run_ids)),
                _json(list(decision.output_modes)),
                decision.status,
                _json(decision.thresholds),
                _json(decision.deltas),
                _json(list(decision.blocking_reasons)),
                _json(decision.metadata),
                decision.created_at,
            ),
        )


def _load_decision(
    db_path: str | Path,
    promotion_decision_id: str,
) -> RoutePromotionDecision:
    with sqlite3.connect(db_path, timeout=60) as conn:
        conn.row_factory = sqlite3.Row
        ensure_memory_schema(conn)
        row = conn.execute(
            """
            SELECT *
            FROM memory_route_promotion_decisions
            WHERE promotion_decision_id = ?
            """,
            (promotion_decision_id,),
        ).fetchone()
    if row is None:
        raise KeyError(f"route promotion decision not found: {promotion_decision_id}")
    return _decision_from_row(row)


def _decision_from_row(row: sqlite3.Row) -> RoutePromotionDecision:
    return RoutePromotionDecision(
        promotion_decision_id=row["promotion_decision_id"],
        candidate_route_version=row["candidate_route_version"],
        baseline_route_version=row["baseline_route_version"],
        eval_run_ids=tuple(json.loads(row["eval_run_ids_json"] or "[]")),
        output_modes=tuple(json.loads(row["output_modes_json"] or "[]")),
        status=row["status"],
        thresholds=json.loads(row["thresholds_json"] or "{}"),
        deltas={
            key: float(value)
            for key, value in json.loads(row["deltas_json"] or "{}").items()
        },
        blocking_reasons=tuple(json.loads(row["blocking_reasons_json"] or "[]")),
        metadata=json.loads(row["metadata_json"] or "{}"),
        created_at=row["created_at"],
    )


def _decision_id(
    *,
    candidate_route_version: str,
    baseline_route_version: str | None,
    eval_run_ids: tuple[str, ...],
    output_modes: tuple[str, ...],
    created_at: str,
) -> str:
    return "route-promotion:" + _stable_hash(
        {
            "baseline_route_version": baseline_route_version,
            "candidate_route_version": candidate_route_version,
            "created_at": created_at,
            "eval_run_ids": list(eval_run_ids),
            "output_modes": list(output_modes),
        }
    )[:24]


def _stable_hash(value: Any) -> str:
    return hashlib.sha256(_json(value).encode("utf-8")).hexdigest()


def _json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
