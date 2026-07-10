from __future__ import annotations

import hashlib
import json
import sqlite3
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from research_x.memory.artifact_registry import backfill_memory_artifacts
from research_x.memory.artifact_roles import ArtifactRole
from research_x.memory.audit_events import record_audit_event
from research_x.memory.authority_levels import AuthorityLevel
from research_x.memory.output_modes import OutputMode
from research_x.memory.schema import ensure_memory_schema

ACTIVE_GENERATION_STATUSES = frozenset({"active", "current", "ready", "ok"})


@dataclass(frozen=True)
class ProjectionRebuildTarget:
    projection_kind: str
    generation_id: str
    projection_id: str
    source_ref: str
    source_hash: str | None
    current_source_hash: str | None
    reasons: tuple[str, ...]
    requires_builder: bool = True


@dataclass(frozen=True)
class ProjectionBuildPlan:
    mode: str
    build_semantics: str
    builder_call_path: str | None
    projection_kind: str | None
    targets: tuple[ProjectionRebuildTarget, ...]
    diagnostic_counts: dict[str, int]

    def as_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["targets"] = [asdict(target) for target in self.targets]
        return data


@dataclass(frozen=True)
class ProjectionLifecycleSummary:
    db_path: str
    status: str
    generations: int
    projections: int
    projections_missing: int
    projections_stale: int
    projections_orphaned: int
    projections_registered: int
    projections_updated: int
    projections_unchanged: int
    audit_event_id: str | None
    actions: tuple[dict[str, Any], ...]
    by_projection_status: dict[str, int]
    build_plan: ProjectionBuildPlan | None = None
    builder_dispatches: tuple[dict[str, Any], ...] = ()

    def as_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["actions"] = list(self.actions)
        if self.build_plan is not None:
            data["build_plan"] = self.build_plan.as_dict()
        data["builder_dispatches"] = list(self.builder_dispatches)
        return data


def plan_projection_lifecycle(
    db_path: str | Path,
    *,
    projection_kind: str | None = None,
) -> ProjectionLifecycleSummary:
    """Inspect projection generation rows without writing lifecycle registrations."""

    path = Path(db_path)
    with sqlite3.connect(path, timeout=60) as conn:
        conn.row_factory = sqlite3.Row
        ensure_memory_schema(conn)
        rows = _projection_rows(conn)
        build_plan = _projection_build_plan(
            conn,
            rows,
            mode="plan",
            projection_kind=projection_kind,
        )
        actions = tuple(_plan_actions(conn, rows, build_plan=build_plan))
        status_counts = Counter(str(row["projection_status"]) for row in rows["projections"])
    return _summary(
        path=path,
        generation_count=len(rows["generations"]),
        projection_count=len(rows["projections"]),
        actions=actions,
        status_counts=status_counts,
        audit_event_id=None,
        registered=0,
        updated=0,
        unchanged=0,
        build_plan=build_plan,
        builder_dispatches=(),
    )


def register_projection_lifecycle(db_path: str | Path) -> ProjectionLifecycleSummary:
    """Register existing projection builds in the KnowledgeOps lifecycle ledger."""

    path = Path(db_path)
    if path.exists():
        backfill_memory_artifacts(path)
    now = _now()
    registered = 0
    updated = 0
    unchanged = 0
    with sqlite3.connect(path, timeout=60) as conn:
        conn.row_factory = sqlite3.Row
        ensure_memory_schema(conn)
        rows = _projection_rows(conn)
        initial_build_plan = _projection_build_plan(conn, rows, mode="register")
        initial_actions = tuple(_plan_actions(conn, rows, build_plan=initial_build_plan))
        for generation in rows["generations"]:
            desired = _desired_projection_record(conn, generation, now=now)
            existing = _projection_by_id(conn, desired["projection_id"])
            _upsert_projection_artifact(conn, desired)
            _upsert_projection_lifecycle(conn, desired)
            if existing is None:
                registered += 1
            elif _projection_changed(existing, desired):
                updated += 1
            else:
                unchanged += 1
        _mark_orphaned_projections(conn, now=now)
        final_rows = _projection_rows(conn)
        final_build_plan = _projection_build_plan(conn, final_rows, mode="register")
        final_actions = tuple(_plan_actions(conn, final_rows, build_plan=final_build_plan))
    audit_event = record_audit_event(
        path,
        event_type="projection_lifecycle_registered",
        subject_kind="projection_lifecycle",
        subject_id="memory_projection_artifacts",
        severity="info",
        message="Projection lifecycle ledger refreshed from existing projection generations.",
        created_at=now,
        metadata={
            "initial_actions": list(initial_actions),
            "initial_build_plan": initial_build_plan.as_dict(),
            "remaining_actions": list(final_actions),
            "remaining_build_plan": final_build_plan.as_dict(),
            "registered": registered,
            "updated": updated,
            "unchanged": unchanged,
            "build_semantics": "lifecycle_registration_only",
            "builder_call_path": None,
        },
    )
    status_counts = Counter(str(row["projection_status"]) for row in final_rows["projections"])
    return _summary(
        path=path,
        generation_count=len(final_rows["generations"]),
        projection_count=len(final_rows["projections"]),
        actions=final_actions,
        status_counts=status_counts,
        audit_event_id=audit_event.event_id,
        registered=registered,
        updated=updated,
        unchanged=unchanged,
        build_plan=final_build_plan,
        builder_dispatches=(),
    )


def build_projection_lifecycle(
    db_path: str | Path,
    *,
    mode: str = "incremental",
    projection_kind: str | None = None,
    builder_params: dict[str, Any] | None = None,
) -> ProjectionLifecycleSummary:
    """Orchestrate projection builders, then refresh lifecycle registrations."""

    normalized_mode = mode.strip().casefold()
    if normalized_mode not in {"incremental", "full"}:
        raise ValueError("projection lifecycle build mode must be incremental or full")
    if normalized_mode == "full":
        _mark_all_projections_rebuild_required(db_path)
    preflight = plan_projection_lifecycle(db_path, projection_kind=projection_kind)
    builder_dispatches = tuple(
        _dispatch_projection_builders(
            db_path,
            mode=normalized_mode,
            projection_kind=projection_kind,
            build_plan=preflight.build_plan,
            builder_params=builder_params or {},
        )
    )
    summary = register_projection_lifecycle(db_path)
    summary_plan = _build_plan_with_dispatch_semantics(
        summary.build_plan,
        builder_dispatches=builder_dispatches,
    )
    if projection_kind:
        plan = _filter_build_plan(summary_plan, projection_kind=projection_kind)
        return _summary(
            path=Path(summary.db_path),
            generation_count=summary.generations,
            projection_count=summary.projections,
            actions=summary.actions,
            status_counts=Counter(summary.by_projection_status),
            audit_event_id=summary.audit_event_id,
            registered=summary.projections_registered,
            updated=summary.projections_updated,
            unchanged=summary.projections_unchanged,
            build_plan=plan,
            builder_dispatches=builder_dispatches,
        )
    return _summary(
        path=Path(summary.db_path),
        generation_count=summary.generations,
        projection_count=summary.projections,
        actions=summary.actions,
        status_counts=Counter(summary.by_projection_status),
        audit_event_id=summary.audit_event_id,
        registered=summary.projections_registered,
        updated=summary.projections_updated,
        unchanged=summary.projections_unchanged,
        build_plan=summary_plan,
        builder_dispatches=builder_dispatches,
    )


def projection_lifecycle_coverage(db_path: str | Path) -> ProjectionLifecycleSummary:
    return plan_projection_lifecycle(db_path)


def projection_lifecycle_rows(
    db_path: str | Path,
    *,
    projection_id: str | None = None,
) -> tuple[dict[str, Any], ...]:
    path = Path(db_path)
    with sqlite3.connect(path, timeout=60) as conn:
        conn.row_factory = sqlite3.Row
        ensure_memory_schema(conn)
        if projection_id:
            rows = conn.execute(
                "SELECT * FROM memory_projection_artifacts WHERE projection_id = ?",
                (projection_id,),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT projection_id, projection_kind, artifact_id, projection_status,
                       generation_id, updated_at
                FROM memory_projection_artifacts
                ORDER BY updated_at DESC, projection_id
                LIMIT 100
                """
            ).fetchall()
    return tuple(dict(row) for row in rows)


def _dispatch_projection_builders(
    db_path: str | Path,
    *,
    mode: str,
    projection_kind: str | None,
    build_plan: ProjectionBuildPlan | None,
    builder_params: dict[str, Any],
) -> list[dict[str, Any]]:
    requested_kind = projection_kind or "local_vector_projection"
    if requested_kind != "local_vector_projection":
        return [
            _record_projection_build_dispatch(
                db_path,
                projection_kind=requested_kind,
                status="skipped",
                event_type="projection_build_skipped",
                message="Projection kind has no registered local builder dispatch.",
                metadata={
                    "reason": "unsupported_projection_kind",
                    "projection_kind": requested_kind,
                    "mode": mode,
                },
            )
        ]
    if not _local_vector_projection_build_needed(
        db_path,
        mode=mode,
        build_plan=build_plan,
    ):
        return [
            _record_projection_build_dispatch(
                db_path,
                projection_kind=requested_kind,
                status="skipped",
                event_type="projection_build_skipped",
                message=(
                    "Local vector projection builder skipped; current lifecycle "
                    "has no rebuild target."
                ),
                metadata={
                    "reason": "no_rebuild_target",
                    "projection_kind": requested_kind,
                    "mode": mode,
                },
            )
        ]
    if _local_hash_embedding_count(db_path) == 0:
        return [
            _record_projection_build_dispatch(
                db_path,
                projection_kind=requested_kind,
                status="skipped",
                event_type="projection_build_skipped",
                message=(
                    "Local vector projection builder skipped; no local_hash "
                    "embeddings are available."
                ),
                metadata={
                    "reason": "no_local_hash_embeddings",
                    "projection_kind": requested_kind,
                    "mode": mode,
                },
            )
        ]
    try:
        from research_x.memory.vector_projection import build_vector_projection

        summary = build_vector_projection(
            db_path,
            provider=str(builder_params.get("provider") or "local_hash"),
            model=builder_params.get("model"),
            dimensions=_optional_int(builder_params.get("dimensions")),
            embedding_profile=builder_params.get("embedding_profile"),
            text_template_version=builder_params.get("text_template_version"),
            backend=str(builder_params.get("backend") or "numpy"),
            bit_width=int(builder_params.get("bit_width") or 4),
            out_dir=builder_params.get("out_dir"),
            doc_type=builder_params.get("doc_type"),
            account=builder_params.get("account"),
        )
    except (FileNotFoundError, RuntimeError, ValueError) as exc:
        return [
            _record_projection_build_dispatch(
                db_path,
                projection_kind=requested_kind,
                status="failed",
                event_type="projection_build_failed",
                severity="warning",
                message="Local vector projection builder failed.",
                metadata={
                    "error": str(exc),
                    "projection_kind": requested_kind,
                    "mode": mode,
                    "builder_call_path": (
                        "research_x.memory.vector_projection.build_vector_projection"
                    ),
                },
            )
        ]
    return [
        _record_projection_build_dispatch(
            db_path,
            projection_kind=requested_kind,
            status="built",
            event_type="projection_build_orchestrated",
            message="Projection lifecycle build dispatched the local vector projection builder.",
            metadata={
                "projection_kind": requested_kind,
                "mode": mode,
                "builder_call_path": (
                    "research_x.memory.vector_projection.build_vector_projection"
                ),
                "build_summary": asdict(summary),
            },
        )
    ]


def _record_projection_build_dispatch(
    db_path: str | Path,
    *,
    projection_kind: str,
    status: str,
    event_type: str,
    message: str,
    metadata: dict[str, Any],
    severity: str = "info",
) -> dict[str, Any]:
    event = record_audit_event(
        db_path,
        event_type=event_type,
        subject_kind="projection_kind",
        subject_id=projection_kind,
        severity=severity,
        message=message,
        created_at=_now(),
        metadata=metadata,
    )
    return {
        "projection_kind": projection_kind,
        "status": status,
        "event_type": event_type,
        "audit_event_id": event.event_id,
        **metadata,
    }


def _local_vector_projection_build_needed(
    db_path: str | Path,
    *,
    mode: str,
    build_plan: ProjectionBuildPlan | None,
) -> bool:
    if mode == "full":
        return True
    if build_plan is not None and any(
        target.projection_kind == "local_vector_projection"
        for target in build_plan.targets
    ):
        return True
    with sqlite3.connect(db_path, timeout=60) as conn:
        ensure_memory_schema(conn)
        row = conn.execute(
            """
            SELECT 1
            FROM memory_projection_generations
            WHERE projection_kind = 'local_vector_projection'
              AND status IN ('active', 'current', 'ready', 'ok')
            LIMIT 1
            """
        ).fetchone()
    return row is None


def _local_hash_embedding_count(db_path: str | Path) -> int:
    with sqlite3.connect(db_path, timeout=60) as conn:
        ensure_memory_schema(conn)
        return int(
            conn.execute(
                "SELECT COUNT(*) FROM memory_embeddings WHERE provider = 'local_hash'"
            ).fetchone()[0]
        )


def _optional_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    return int(value)


def _projection_rows(conn: sqlite3.Connection) -> dict[str, tuple[sqlite3.Row, ...]]:
    generations = conn.execute(
        "SELECT * FROM memory_projection_generations ORDER BY created_at DESC, generation_id"
    ).fetchall()
    projections = conn.execute(
        "SELECT * FROM memory_projection_artifacts ORDER BY updated_at DESC, projection_id"
    ).fetchall()
    return {"generations": tuple(generations), "projections": tuple(projections)}


def _plan_actions(
    conn: sqlite3.Connection,
    rows: dict[str, tuple[sqlite3.Row, ...]],
    *,
    build_plan: ProjectionBuildPlan,
) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = _build_orchestration_actions(conn, rows, build_plan)
    known_generation_ids = {str(row["generation_id"]) for row in rows["generations"]}
    known_projection_ids = {str(row["projection_id"]) for row in rows["projections"]}
    now = _now()
    for generation in rows["generations"]:
        desired = _desired_projection_record(conn, generation, now=now)
        existing = _projection_by_id(conn, desired["projection_id"])
        if existing is None:
            actions.append(
                {
                    "action": "register_projection",
                    "projection_id": desired["projection_id"],
                    "generation_id": desired["generation_id"],
                    "projection_kind": desired["projection_kind"],
                }
            )
        elif _projection_changed(existing, desired):
            actions.append(
                {
                    "action": "update_projection",
                    "projection_id": desired["projection_id"],
                    "generation_id": desired["generation_id"],
                    "projection_kind": desired["projection_kind"],
                }
            )
    for projection in rows["projections"]:
        generation_id = str(projection["generation_id"] or "")
        projection_id = str(projection["projection_id"])
        if generation_id and generation_id not in known_generation_ids:
            actions.append(
                {
                    "action": "mark_projection_orphan",
                    "projection_id": projection_id,
                    "generation_id": generation_id,
                    "projection_kind": projection["projection_kind"],
                }
            )
        elif projection_id not in known_projection_ids:
            actions.append({"action": "review_projection", "projection_id": projection_id})
    return actions


def _build_orchestration_actions(
    conn: sqlite3.Connection,
    rows: dict[str, tuple[sqlite3.Row, ...]],
    build_plan: ProjectionBuildPlan,
) -> list[dict[str, Any]]:
    source_count = int(conn.execute("SELECT COUNT(*) FROM memory_sources").fetchone()[0])
    observed_source_count = int(
        conn.execute(
            """
            SELECT COUNT(DISTINCT source_ref)
            FROM memory_source_observations
            """
        ).fetchone()[0]
    )
    participation_decision_count = int(
        conn.execute("SELECT COUNT(*) FROM memory_participation_decisions").fetchone()[0]
    )
    index_membership_count = int(
        conn.execute("SELECT COUNT(*) FROM memory_index_membership").fetchone()[0]
    )
    membership_generation_ids = {
        str(row[0])
        for row in conn.execute(
            """
            SELECT DISTINCT generation_id
            FROM memory_index_membership
            WHERE generation_id IS NOT NULL AND generation_id != ''
            """
        ).fetchall()
    }
    generation_ids = {str(row["generation_id"]) for row in rows["generations"]}
    projection_generation_ids = {
        str(row["generation_id"])
        for row in rows["projections"]
        if str(row["generation_id"] or "")
    }
    return [
        {
            "action": "source_observation_diff",
            "source_count": source_count,
            "observed_source_count": observed_source_count,
            "unobserved_source_count": max(0, source_count - observed_source_count),
        },
        {
            "action": "participation_decision_summary",
            "participation_decision_count": participation_decision_count,
        },
        {
            "action": "projection_build_plan",
            "build_semantics": build_plan.build_semantics,
            "builder_call_path": build_plan.builder_call_path,
            "generation_count": len(rows["generations"]),
            "projection_count": len(rows["projections"]),
            "rebuild_target_count": len(build_plan.targets),
            "rebuild_reasons": build_plan.diagnostic_counts,
            "generation_without_projection_count": len(
                generation_ids - projection_generation_ids
            ),
            "index_membership_count": index_membership_count,
        },
        {
            "action": "projection_artifact_summary",
            "projection_artifact_count": len(rows["projections"]),
            "missing_projection_artifact_count": len(
                generation_ids - projection_generation_ids
            ),
        },
        {
            "action": "index_membership_summary",
            "index_membership_count": index_membership_count,
            "generation_with_membership_count": len(membership_generation_ids),
        },
        {
            "action": "audit_event_plan",
            "event_type": "projection_lifecycle_registered",
            "writes_on_build": True,
            "actual_builder_event_type": "projection_built",
            "lifecycle_only_without_builder": (
                build_plan.build_semantics == "lifecycle_registration_only"
            ),
        },
    ]


def _projection_build_plan(
    conn: sqlite3.Connection,
    rows: dict[str, tuple[sqlite3.Row, ...]],
    *,
    mode: str,
    projection_kind: str | None = None,
) -> ProjectionBuildPlan:
    targets: list[ProjectionRebuildTarget] = []
    for generation in rows["generations"]:
        kind = str(generation["projection_kind"])
        if projection_kind and kind != projection_kind:
            continue
        generation_id = str(generation["generation_id"])
        projection_id = f"projection:{generation_id}"
        generation_status = _projection_status(str(generation["status"]))
        membership_rows = conn.execute(
            """
            SELECT source_id, source_hash, membership_status
            FROM memory_index_membership
            WHERE generation_id = ?
            ORDER BY membership_id
            """,
            (generation_id,),
        ).fetchall()
        if not membership_rows:
            targets.append(
                ProjectionRebuildTarget(
                    projection_kind=kind,
                    generation_id=generation_id,
                    projection_id=projection_id,
                    source_ref="",
                    source_hash=None,
                    current_source_hash=None,
                    reasons=("missing_index_membership",),
                )
            )
            continue
        for membership in membership_rows:
            source_ref = str(membership["source_id"] or "")
            stored_hash = _string_or_none(membership["source_hash"])
            current_hash = _current_source_hash(conn, source_ref)
            reasons: list[str] = []
            if generation_status not in {"active", "current"}:
                reasons.append(f"generation_status:{generation_status}")
            if str(membership["membership_status"] or "").casefold() not in {
                "active",
                "current",
                "ready",
                "ok",
            }:
                reasons.append(f"membership_status:{membership['membership_status']}")
            if stored_hash and current_hash and stored_hash != current_hash:
                reasons.append("source_hash_changed")
            if stored_hash and not current_hash:
                reasons.append("current_source_hash_missing")
            reasons.extend(_participation_rebuild_reasons(conn, source_ref, projection_id))
            if not _projection_by_id(conn, projection_id):
                reasons.append("projection_lifecycle_missing")
            if reasons:
                targets.append(
                    ProjectionRebuildTarget(
                        projection_kind=kind,
                        generation_id=generation_id,
                        projection_id=projection_id,
                        source_ref=source_ref,
                        source_hash=stored_hash,
                        current_source_hash=current_hash,
                        reasons=tuple(dict.fromkeys(reasons)),
                    )
                )
    diagnostic_counts = Counter(
        reason for target in targets for reason in target.reasons
    )
    return ProjectionBuildPlan(
        mode=mode,
        build_semantics="lifecycle_registration_only",
        builder_call_path=None,
        projection_kind=projection_kind,
        targets=tuple(targets),
        diagnostic_counts=dict(sorted(diagnostic_counts.items())),
    )


def _filter_build_plan(
    build_plan: ProjectionBuildPlan | None,
    *,
    projection_kind: str,
) -> ProjectionBuildPlan:
    if build_plan is None:
        return ProjectionBuildPlan(
            mode="filtered",
            build_semantics="lifecycle_registration_only",
            builder_call_path=None,
            projection_kind=projection_kind,
            targets=(),
            diagnostic_counts={},
        )
    targets = tuple(
        target for target in build_plan.targets if target.projection_kind == projection_kind
    )
    diagnostic_counts = Counter(reason for target in targets for reason in target.reasons)
    return ProjectionBuildPlan(
        mode=build_plan.mode,
        build_semantics=build_plan.build_semantics,
        builder_call_path=build_plan.builder_call_path,
        projection_kind=projection_kind,
        targets=targets,
        diagnostic_counts=dict(sorted(diagnostic_counts.items())),
    )


def _build_plan_with_dispatch_semantics(
    build_plan: ProjectionBuildPlan | None,
    *,
    builder_dispatches: tuple[dict[str, Any], ...],
) -> ProjectionBuildPlan | None:
    if build_plan is None:
        return None
    if not builder_dispatches:
        return build_plan
    build_semantics = _dispatch_build_semantics(builder_dispatches)
    builder_call_path = next(
        (
            str(dispatch["builder_call_path"])
            for dispatch in builder_dispatches
            if dispatch.get("builder_call_path")
        ),
        None,
    )
    return ProjectionBuildPlan(
        mode=build_plan.mode,
        build_semantics=build_semantics,
        builder_call_path=builder_call_path,
        projection_kind=build_plan.projection_kind,
        targets=build_plan.targets,
        diagnostic_counts=build_plan.diagnostic_counts,
    )


def _dispatch_build_semantics(
    builder_dispatches: tuple[dict[str, Any], ...],
) -> str:
    if any(dispatch.get("status") in {"built", "failed"} for dispatch in builder_dispatches):
        return "local_vector_builder_dispatch"
    reasons = {str(dispatch.get("reason") or "") for dispatch in builder_dispatches}
    if "unsupported_projection_kind" in reasons:
        return "unsupported_projection_kind"
    if reasons:
        return "dry_run_build_plan"
    return "lifecycle_registration_only"


def _current_source_hash(conn: sqlite3.Connection, source_ref: str) -> str | None:
    if not source_ref:
        return None
    document = conn.execute(
        """
        SELECT source_doc_hash, embedding_text_hash
        FROM memory_documents
        WHERE doc_id = ?
        """,
        (source_ref,),
    ).fetchone()
    if document is not None:
        return _string_or_none(document["source_doc_hash"]) or _string_or_none(
            document["embedding_text_hash"]
        )
    source = conn.execute(
        """
        SELECT raw_hash, normalized_content_hash, relation_hash, media_hash
        FROM memory_sources
        WHERE source_ref = ?
        """,
        (source_ref,),
    ).fetchone()
    if source is not None:
        return (
            _string_or_none(source["normalized_content_hash"])
            or _string_or_none(source["raw_hash"])
            or _string_or_none(source["relation_hash"])
            or _string_or_none(source["media_hash"])
        )
    return None


def _participation_rebuild_reasons(
    conn: sqlite3.Connection,
    source_ref: str,
    projection_id: str,
) -> list[str]:
    rows = conn.execute(
        """
        SELECT output_mode, can_search, can_explore, can_use_in_working_note,
               can_use_as_evidence, can_use_in_answer, reason
        FROM memory_participation_decisions
        WHERE (source_ref = ? AND source_ref IS NOT NULL)
           OR (artifact_id = ? AND artifact_id IS NOT NULL)
        """,
        (source_ref, projection_id),
    ).fetchall()
    reasons: list[str] = []
    for row in rows:
        mode = str(row["output_mode"] or "unknown")
        if int(row["can_search"]) == 0 and mode in {"explore", "collect", "synthesize"}:
            reasons.append(f"participation_blocks_search:{mode}")
        if int(row["can_use_in_working_note"]) == 0 and mode == "working_note":
            reasons.append("participation_blocks_working_note")
        if int(row["can_use_as_evidence"]) == 0 and mode == "evidence_package":
            reasons.append("participation_blocks_evidence")
        if int(row["can_use_in_answer"]) == 0 and mode == "answer":
            reasons.append("participation_blocks_answer")
    return reasons


def _desired_projection_record(
    conn: sqlite3.Connection,
    generation: sqlite3.Row,
    *,
    now: str,
) -> dict[str, Any]:
    generation_id = str(generation["generation_id"])
    projection_id = f"projection:{generation_id}"
    source_refs = _generation_source_refs(conn, generation_id)
    input_manifest = _json_loads(generation["input_manifest_json"])
    coverage = _json_loads(generation["coverage_json"])
    metadata = _json_loads(generation["metadata_json"])
    projection_status = _projection_status(str(generation["status"]))
    output_hash = _stable_hash(
        {
            "generation_id": generation_id,
            "projection_kind": generation["projection_kind"],
            "coverage": coverage,
            "metadata": metadata,
            "source_refs": source_refs,
        }
    )
    restore_path = {
        "table": "memory_projection_generations",
        "generation_id": generation_id,
        "source_scope": generation["source_scope"],
        "index_membership_table": "memory_index_membership",
        "source_refs": list(source_refs),
    }
    lifecycle_metadata = {
        "source_table": "memory_projection_generations",
        "generation_status": generation["status"],
        "source_scope": generation["source_scope"],
        "coverage": coverage,
        "generation_metadata": metadata,
        "index_membership_count": _membership_count(conn, generation_id),
    }
    return {
        "projection_id": projection_id,
        "projection_kind": str(generation["projection_kind"]),
        "artifact_id": projection_id,
        "source_refs_json": _json(source_refs),
        "builder_version": str(generation["builder_version"]),
        "input_hash_json": _json(
            {
                "input_manifest_hash": _stable_hash(input_manifest),
                "source_refs_hash": _stable_hash(source_refs),
            }
        ),
        "output_hash": output_hash,
        "projection_status": projection_status,
        "restore_path_json": _json(restore_path),
        "generation_id": generation_id,
        "created_at": str(generation["created_at"] or now),
        "updated_at": now,
        "metadata_json": _json(lifecycle_metadata),
    }


def _upsert_projection_artifact(conn: sqlite3.Connection, record: dict[str, Any]) -> None:
    conn.execute(
        """
        INSERT INTO memory_artifacts (
            artifact_id, artifact_role, artifact_kind, source_refs_json,
            content_hash, authority_level, output_mode, retention_policy,
            artifact_status, created_at, updated_at, metadata_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(artifact_id) DO UPDATE SET
            artifact_role=excluded.artifact_role,
            artifact_kind=excluded.artifact_kind,
            source_refs_json=excluded.source_refs_json,
            content_hash=excluded.content_hash,
            authority_level=excluded.authority_level,
            output_mode=excluded.output_mode,
            retention_policy=excluded.retention_policy,
            artifact_status=excluded.artifact_status,
            updated_at=excluded.updated_at,
            metadata_json=excluded.metadata_json
        """,
        (
            record["artifact_id"],
            ArtifactRole.PROJECTION.value,
            record["projection_kind"],
            record["source_refs_json"],
            record["output_hash"],
            AuthorityLevel.CANDIDATE.value,
            OutputMode.EXPLORE.value,
            "projection_lifecycle",
            record["projection_status"],
            record["created_at"],
            record["updated_at"],
            record["metadata_json"],
        ),
    )


def _upsert_projection_lifecycle(conn: sqlite3.Connection, record: dict[str, Any]) -> None:
    conn.execute(
        """
        INSERT INTO memory_projection_artifacts (
            projection_id, projection_kind, artifact_id, source_refs_json,
            builder_version, input_hash_json, output_hash, projection_status,
            restore_path_json, generation_id, created_at, updated_at,
            metadata_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(projection_id) DO UPDATE SET
            projection_kind=excluded.projection_kind,
            artifact_id=excluded.artifact_id,
            source_refs_json=excluded.source_refs_json,
            builder_version=excluded.builder_version,
            input_hash_json=excluded.input_hash_json,
            output_hash=excluded.output_hash,
            projection_status=excluded.projection_status,
            restore_path_json=excluded.restore_path_json,
            generation_id=excluded.generation_id,
            updated_at=excluded.updated_at,
            metadata_json=excluded.metadata_json
        """,
        (
            record["projection_id"],
            record["projection_kind"],
            record["artifact_id"],
            record["source_refs_json"],
            record["builder_version"],
            record["input_hash_json"],
            record["output_hash"],
            record["projection_status"],
            record["restore_path_json"],
            record["generation_id"],
            record["created_at"],
            record["updated_at"],
            record["metadata_json"],
        ),
    )


def _mark_orphaned_projections(conn: sqlite3.Connection, *, now: str) -> None:
    conn.execute(
        """
        UPDATE memory_projection_artifacts
        SET projection_status = 'orphan',
            updated_at = ?
        WHERE generation_id IS NOT NULL
          AND generation_id NOT IN (
              SELECT generation_id FROM memory_projection_generations
          )
        """,
        (now,),
    )
    conn.execute(
        """
        UPDATE memory_artifacts
        SET artifact_status = 'orphan',
            updated_at = ?
        WHERE artifact_id IN (
            SELECT artifact_id
            FROM memory_projection_artifacts
            WHERE projection_status = 'orphan'
        )
        """,
        (now,),
    )


def _mark_all_projections_rebuild_required(db_path: str | Path) -> None:
    path = Path(db_path)
    now = _now()
    with sqlite3.connect(path, timeout=60) as conn:
        ensure_memory_schema(conn)
        conn.execute(
            """
            UPDATE memory_projection_artifacts
            SET projection_status = 'rebuild_required',
                updated_at = ?
            """,
            (now,),
        )
        conn.execute(
            """
            UPDATE memory_artifacts
            SET artifact_status = 'rebuild_required',
                updated_at = ?
            WHERE artifact_role = ?
            """,
            (now, ArtifactRole.PROJECTION.value),
        )
        conn.commit()


def _projection_by_id(conn: sqlite3.Connection, projection_id: str) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM memory_projection_artifacts WHERE projection_id = ?",
        (projection_id,),
    ).fetchone()


def _projection_changed(existing: sqlite3.Row, desired: dict[str, Any]) -> bool:
    compared = (
        "projection_kind",
        "artifact_id",
        "source_refs_json",
        "builder_version",
        "input_hash_json",
        "output_hash",
        "projection_status",
        "restore_path_json",
        "generation_id",
        "metadata_json",
    )
    return any(str(existing[key]) != str(desired[key]) for key in compared)


def _generation_source_refs(conn: sqlite3.Connection, generation_id: str) -> tuple[str, ...]:
    refs: list[str] = []
    rows = conn.execute(
        """
        SELECT source_id
        FROM memory_index_membership
        WHERE generation_id = ?
        ORDER BY membership_id
        """,
        (generation_id,),
    ).fetchall()
    for row in rows:
        source_id = row["source_id"]
        if not source_id:
            continue
        artifact_refs = _artifact_source_refs(conn, f"memory_document:{source_id}")
        refs.extend(artifact_refs or (str(source_id),))
    return tuple(dict.fromkeys(refs))


def _artifact_source_refs(conn: sqlite3.Connection, artifact_id: str) -> tuple[str, ...]:
    row = conn.execute(
        "SELECT source_refs_json FROM memory_artifacts WHERE artifact_id = ?",
        (artifact_id,),
    ).fetchone()
    if row is None:
        return ()
    payload = _json_loads(row["source_refs_json"])
    if not isinstance(payload, list):
        return ()
    return tuple(str(item) for item in payload if str(item).strip())


def _membership_count(conn: sqlite3.Connection, generation_id: str) -> int:
    return int(
        conn.execute(
            "SELECT COUNT(*) FROM memory_index_membership WHERE generation_id = ?",
            (generation_id,),
        ).fetchone()[0]
    )


def _projection_status(generation_status: str) -> str:
    normalized = generation_status.strip().casefold()
    if normalized in ACTIVE_GENERATION_STATUSES:
        return "active"
    if normalized in {"stale", "outdated"}:
        return "stale"
    if normalized in {"failed", "error"}:
        return "failed"
    return normalized or "needs_review"


def _summary(
    *,
    path: Path,
    generation_count: int,
    projection_count: int,
    actions: tuple[dict[str, Any], ...],
    status_counts: Counter[str],
    audit_event_id: str | None,
    registered: int,
    updated: int,
    unchanged: int,
    build_plan: ProjectionBuildPlan | None,
    builder_dispatches: tuple[dict[str, Any], ...],
) -> ProjectionLifecycleSummary:
    missing = sum(1 for action in actions if action["action"] == "register_projection")
    stale = sum(1 for action in actions if action["action"] == "update_projection")
    orphaned = sum(1 for action in actions if action["action"] == "mark_projection_orphan")
    status = "ok" if missing == 0 and stale == 0 and orphaned == 0 else "needs_build"
    return ProjectionLifecycleSummary(
        db_path=str(path),
        status=status,
        generations=generation_count,
        projections=projection_count,
        projections_missing=missing,
        projections_stale=stale,
        projections_orphaned=orphaned,
        projections_registered=registered,
        projections_updated=updated,
        projections_unchanged=unchanged,
        audit_event_id=audit_event_id,
        actions=actions,
        by_projection_status=dict(sorted(status_counts.items())),
        build_plan=build_plan,
        builder_dispatches=builder_dispatches,
    )


def _json(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def _json_loads(payload: Any) -> Any:
    if payload is None:
        return {}
    if isinstance(payload, (dict, list)):
        return payload
    try:
        return json.loads(str(payload))
    except json.JSONDecodeError:
        return str(payload)


def _stable_hash(payload: Any) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _string_or_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _now() -> str:
    return datetime.now(UTC).isoformat()
