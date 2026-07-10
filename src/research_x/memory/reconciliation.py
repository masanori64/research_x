from __future__ import annotations

import hashlib
import json
import sqlite3
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from research_x.memory.audit_events import record_audit_event
from research_x.memory.schema import ensure_memory_schema

ACTIVE_GENERATION_STATUSES = frozenset({"active", "current", "ready", "ok"})
ACTIVE_PROJECTION_STATUSES = frozenset({"active", "current", "ready", "ok"})
STALE_PROJECTION_STATUSES = frozenset(
    {"stale", "orphan", "orphaned", "rebuild_required", "failed", "error"}
)


@dataclass(frozen=True)
class ReconciliationItem:
    subject_kind: str
    subject_id: str
    action: str
    reason: str
    status: str
    metadata: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ReconciliationSummary:
    db_path: str
    reconciliation_run_id: str
    observation_completeness: str
    items: int
    by_status: dict[str, int]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def reconcile_source_observation(
    db_path: str | Path,
    *,
    observed_source_refs: tuple[str, ...],
    observation_completeness: str,
    reconciliation_scope: str = "local_source_manifest",
    reconciliation_run_id: str | None = None,
    started_at: str = "",
) -> ReconciliationSummary:
    completeness = observation_completeness.strip().casefold()
    if completeness not in {"complete", "partial", "unknown"}:
        raise ValueError("observation_completeness must be complete, partial, or unknown")
    path = Path(db_path)
    if not path.exists():
        raise FileNotFoundError(f"database not found: {path}")
    run_id = reconciliation_run_id or "reconciliation:" + _stable_hash(
        {
            "completeness": completeness,
            "observed_source_refs": sorted(set(observed_source_refs)),
            "scope": reconciliation_scope,
            "started_at": started_at,
        }
    )[:24]
    observed = set(observed_source_refs)
    with sqlite3.connect(path, timeout=60) as conn:
        conn.row_factory = sqlite3.Row
        ensure_memory_schema(conn)
        source_refs = tuple(
            row["source_ref"]
            for row in conn.execute(
                "SELECT source_ref FROM memory_sources ORDER BY source_ref"
            )
        )
        items = tuple(
            [
                *_reconciliation_items(source_refs, observed, completeness),
                *_projection_reconciliation_items(conn),
                *_artifact_role_reconciliation_items(conn),
            ]
        )
        _upsert_run(
            conn,
            reconciliation_run_id=run_id,
            reconciliation_scope=reconciliation_scope,
            observation_completeness=completeness,
            status="completed",
            started_at=started_at,
        )
        for item in items:
            _upsert_item(conn, reconciliation_run_id=run_id, item=item)
    by_status = Counter(item.status for item in items)
    record_audit_event(
        path,
        event_type="source_reconciliation_completed",
        subject_kind="reconciliation_run",
        subject_id=run_id,
        severity="info" if completeness != "unknown" else "warning",
        message="Source observation reconciliation completed.",
        created_at=started_at,
        metadata={
            "artifact_role": "control_state",
            "authority_level": "navigation_signal",
            "not_evidence": True,
            "observation_completeness": completeness,
            "reconciliation_scope": reconciliation_scope,
            "observed_source_refs": sorted(observed),
            "items": len(items),
            "by_status": dict(sorted(by_status.items())),
        },
    )
    return ReconciliationSummary(
        db_path=str(path),
        reconciliation_run_id=run_id,
        observation_completeness=completeness,
        items=len(items),
        by_status=dict(sorted(by_status.items())),
    )


def _reconciliation_items(
    source_refs: tuple[str, ...],
    observed: set[str],
    completeness: str,
) -> list[ReconciliationItem]:
    items: list[ReconciliationItem] = []
    for source_ref in source_refs:
        if source_ref in observed:
            items.append(
                ReconciliationItem(
                    subject_kind="memory_source",
                    subject_id=source_ref,
                    action="unchanged",
                    reason="source_observed",
                    status="unchanged",
                    metadata={},
                )
            )
            continue
        if completeness == "complete":
            items.append(
                ReconciliationItem(
                    subject_kind="memory_source",
                    subject_id=source_ref,
                    action="source_missing_complete",
                    reason="missing_from_complete_observation",
                    status="tombstone_candidate",
                    metadata={"partial_safe": True},
                )
            )
        elif completeness == "partial":
            items.append(
                ReconciliationItem(
                    subject_kind="memory_source",
                    subject_id=source_ref,
                    action="source_missing_partial",
                    reason="missing_from_partial_observation",
                    status="missing_in_partial_observation",
                    metadata={"tombstone_allowed": False},
                )
            )
        else:
            items.append(
                ReconciliationItem(
                    subject_kind="memory_source",
                    subject_id=source_ref,
                    action="needs_review",
                    reason="unknown_observation_completeness",
                    status="needs_review",
                    metadata={"tombstone_allowed": False},
                )
            )
    return items


def _projection_reconciliation_items(conn: sqlite3.Connection) -> list[ReconciliationItem]:
    items: list[ReconciliationItem] = []
    rows = conn.execute(
        """
        SELECT p.projection_id, p.projection_kind, p.artifact_id,
               p.projection_status, p.generation_id, p.metadata_json,
               g.status AS generation_status, g.coverage_json
        FROM memory_projection_artifacts p
        LEFT JOIN memory_projection_generations g
          ON g.generation_id = p.generation_id
        ORDER BY p.projection_id
        """
    ).fetchall()
    for row in rows:
        projection_id = str(row["projection_id"])
        generation_status = str(row["generation_status"] or "").strip().casefold()
        projection_status = str(row["projection_status"] or "").strip().casefold()
        coverage = _json_loads(row["coverage_json"])
        if row["generation_id"] and not row["generation_status"]:
            items.append(
                ReconciliationItem(
                    subject_kind="memory_projection_artifact",
                    subject_id=projection_id,
                    action="projection_orphan",
                    reason="projection_generation_missing",
                    status="projection_orphan",
                    metadata={
                        "generation_id": row["generation_id"],
                        "projection_kind": row["projection_kind"],
                        "tombstone_allowed": False,
                    },
                )
            )
            continue
        if projection_status in STALE_PROJECTION_STATUSES:
            items.append(
                ReconciliationItem(
                    subject_kind="memory_projection_artifact",
                    subject_id=projection_id,
                    action="projection_stale",
                    reason="projection_status_not_active",
                    status="projection_rebuild_required",
                    metadata={
                        "projection_status": projection_status,
                        "projection_kind": row["projection_kind"],
                    },
                )
            )
            continue
        if generation_status and generation_status not in ACTIVE_GENERATION_STATUSES:
            items.append(
                ReconciliationItem(
                    subject_kind="memory_projection_artifact",
                    subject_id=projection_id,
                    action="projection_rebuild_required",
                    reason="generation_status_not_current",
                    status="projection_rebuild_required",
                    metadata={
                        "generation_status": generation_status,
                        "projection_kind": row["projection_kind"],
                    },
                )
            )
            continue
        if _coverage_indicates_projection_stale(coverage):
            items.append(
                ReconciliationItem(
                    subject_kind="memory_projection_artifact",
                    subject_id=projection_id,
                    action="projection_stale",
                    reason="generation_coverage_not_current",
                    status="projection_rebuild_required",
                    metadata={
                        "coverage": coverage,
                        "projection_kind": row["projection_kind"],
                    },
                )
            )
            continue
        if projection_status in ACTIVE_PROJECTION_STATUSES:
            items.append(
                ReconciliationItem(
                    subject_kind="memory_projection_artifact",
                    subject_id=projection_id,
                    action="unchanged",
                    reason="projection_current",
                    status="unchanged",
                    metadata={"projection_kind": row["projection_kind"]},
                )
            )
    return items


def _artifact_role_reconciliation_items(conn: sqlite3.Connection) -> list[ReconciliationItem]:
    items: list[ReconciliationItem] = []
    rows = conn.execute(
        """
        SELECT artifact_id, artifact_role, authority_level, output_mode,
               artifact_status
        FROM memory_artifacts
        WHERE artifact_status = 'active'
        ORDER BY artifact_id
        """
    ).fetchall()
    for row in rows:
        reason = _artifact_role_mismatch_reason(row)
        if not reason:
            continue
        items.append(
            ReconciliationItem(
                subject_kind="memory_artifact",
                subject_id=str(row["artifact_id"]),
                action="artifact_role_mismatch",
                reason=reason,
                status="needs_review",
                metadata={
                    "artifact_role": row["artifact_role"],
                    "authority_level": row["authority_level"],
                    "output_mode": row["output_mode"],
                },
            )
        )
    return items


def _coverage_indicates_projection_stale(coverage: Any) -> bool:
    if not isinstance(coverage, dict):
        return False
    stale = int(coverage.get("stale") or coverage.get("stale_memberships") or 0)
    missing = int(coverage.get("missing") or coverage.get("missing_memberships") or 0)
    current = int(coverage.get("current") or coverage.get("current_memberships") or 0)
    documents = int(
        coverage.get("documents")
        or coverage.get("projection_documents")
        or current
    )
    return stale > 0 or missing > 0 or current < documents


def _artifact_role_mismatch_reason(row: sqlite3.Row) -> str | None:
    artifact_role = str(row["artifact_role"] or "").strip()
    authority_level = str(row["authority_level"] or "").strip()
    output_mode = str(row["output_mode"] or "").strip()
    if output_mode == "answer":
        if artifact_role != "evidence_view":
            return "answer_output_requires_evidence_view"
        if authority_level != "answer_assertion":
            return "answer_output_requires_answer_assertion"
    if output_mode == "evidence_package":
        if artifact_role != "evidence_view":
            return "evidence_package_requires_evidence_view"
        if authority_level not in {"evidence_view", "claim_supported", "answer_assertion"}:
            return "evidence_package_requires_evidence_authority"
    if artifact_role in {"projection", "derived_signal", "working_note", "control_state"} and (
        authority_level in {"evidence_view", "claim_supported", "answer_assertion"}
    ):
        return "non_evidence_role_has_evidence_authority"
    return None


def _upsert_run(
    conn: sqlite3.Connection,
    *,
    reconciliation_run_id: str,
    reconciliation_scope: str,
    observation_completeness: str,
    status: str,
    started_at: str,
) -> None:
    conn.execute(
        """
        INSERT INTO memory_reconciliation_runs (
            reconciliation_run_id, reconciliation_scope,
            observation_completeness, status, started_at, finished_at,
            metadata_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(reconciliation_run_id) DO UPDATE SET
            observation_completeness=excluded.observation_completeness,
            status=excluded.status,
            finished_at=excluded.finished_at,
            metadata_json=excluded.metadata_json
        """,
        (
            reconciliation_run_id,
            reconciliation_scope,
            observation_completeness,
            status,
            started_at,
            started_at,
            "{}",
        ),
    )


def _upsert_item(
    conn: sqlite3.Connection,
    *,
    reconciliation_run_id: str,
    item: ReconciliationItem,
) -> None:
    item_id = _stable_hash(
        {
            "action": item.action,
            "reconciliation_run_id": reconciliation_run_id,
            "subject_id": item.subject_id,
            "subject_kind": item.subject_kind,
        }
    )
    conn.execute(
        """
        INSERT INTO memory_reconciliation_items (
            reconciliation_item_id, reconciliation_run_id, subject_kind,
            subject_id, action, reason, status, created_at, metadata_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(reconciliation_item_id) DO UPDATE SET
            action=excluded.action,
            reason=excluded.reason,
            status=excluded.status,
            metadata_json=excluded.metadata_json
        """,
        (
            item_id,
            reconciliation_run_id,
            item.subject_kind,
            item.subject_id,
            item.action,
            item.reason,
            item.status,
            "",
            _json(item.metadata),
        ),
    )


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


def _json_loads(value: Any) -> Any:
    if value is None:
        return {}
    try:
        return json.loads(str(value))
    except json.JSONDecodeError:
        return {}
