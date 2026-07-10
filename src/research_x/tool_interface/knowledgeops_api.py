from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from research_x.memory.schema import ensure_memory_schema
from research_x.tool_interface.codex_bridge import FORBIDDEN_BRIDGE_FIELDS

KNOWLEDGEOPS_API_CONTRACT_VERSION = "research-x-knowledgeops-api-v1"

SUPPORTED_KNOWLEDGEOPS_API_OPERATIONS = (
    "knowledge.sync_sources",
    "knowledge.source_list",
    "knowledge.source_show",
    "knowledge.observations",
    "knowledge.reconcile",
    "knowledge.reconcile_show",
    "knowledge.cleanup_orphans",
    "knowledge.status",
    "artifacts.list",
    "artifacts.show",
    "artifacts.links",
    "artifacts.validate",
    "projections.plan",
    "projections.build",
    "projections.coverage",
    "projections.show",
    "participation.rebuild",
    "participation.check",
    "participation.explain",
    "memory.explore",
    "memory.collect",
    "memory.working_note.create",
    "memory.working_note.append",
    "memory.working_note.show",
    "memory.working_note.link",
    "memory.working_note.promote",
    "memory.working_note.expire",
    "memory.synthesize",
    "memory.evidence_package",
    "memory.answer",
    "eval_v2.run",
    "eval_v2.compare",
    "eval_v2.report",
    "route_promotion.check",
    "route_promotion.approve",
    "route_promotion.reject",
    "route_promotion.list",
    "audit.events",
    "audit.latest",
    "audit.summary",
    "audit.alert_local_jsonl_test",
)


@dataclass(frozen=True)
class KnowledgeOpsApiRequest:
    operation: str
    db_path: str | Path = "runs/x_data.sqlite3"
    params: Mapping[str, Any] = field(default_factory=dict)
    contract_version: str = KNOWLEDGEOPS_API_CONTRACT_VERSION

    def as_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["db_path"] = str(self.db_path)
        data["params"] = dict(self.params)
        return data


@dataclass(frozen=True)
class KnowledgeOpsApiResponse:
    operation: str
    status: str
    payload: Any
    trace: dict[str, Any]
    contract_version: str = KNOWLEDGEOPS_API_CONTRACT_VERSION

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


Handler = Callable[[Path, dict[str, Any]], Any]


def knowledgeops_api_manifest() -> dict[str, Any]:
    return {
        "contract_version": KNOWLEDGEOPS_API_CONTRACT_VERSION,
        "api_surface": "research_x.tool_interface.knowledgeops_api",
        "operation_count": len(SUPPORTED_KNOWLEDGEOPS_API_OPERATIONS),
        "operations": list(SUPPORTED_KNOWLEDGEOPS_API_OPERATIONS),
        "provider_runtime_calls_allowed": False,
        "answer_boundary": (
            "memory.answer requires evidence_package artifacts and explicit supported claims"
        ),
    }


def run_knowledgeops_api(
    request: KnowledgeOpsApiRequest | Mapping[str, Any] | str,
    *,
    db_path: str | Path | None = None,
    params: Mapping[str, Any] | None = None,
) -> KnowledgeOpsApiResponse:
    if isinstance(request, KnowledgeOpsApiRequest):
        _reject_forbidden_bridge_fields(request.as_dict())
    elif isinstance(request, Mapping):
        _reject_forbidden_bridge_fields(request)
    resolved = _coerce_request(request, db_path=db_path, params=params)
    _reject_forbidden_bridge_fields(resolved.as_dict())
    if resolved.contract_version != KNOWLEDGEOPS_API_CONTRACT_VERSION:
        raise ValueError("invalid KnowledgeOps API contract_version")
    handler = _HANDLERS.get(resolved.operation)
    if handler is None:
        raise ValueError(f"unsupported KnowledgeOps API operation: {resolved.operation}")
    payload = _as_payload(handler(Path(resolved.db_path), dict(resolved.params)))
    return KnowledgeOpsApiResponse(
        operation=resolved.operation,
        status=_payload_status(payload),
        payload=payload,
        trace={
            "api_surface": "tool_interface",
            "provider_runtime_calls_allowed": False,
            "operation": resolved.operation,
        },
    )


def _coerce_request(
    request: KnowledgeOpsApiRequest | Mapping[str, Any] | str,
    *,
    db_path: str | Path | None,
    params: Mapping[str, Any] | None,
) -> KnowledgeOpsApiRequest:
    if isinstance(request, KnowledgeOpsApiRequest):
        if db_path is None and params is None:
            return request
        return KnowledgeOpsApiRequest(
            operation=request.operation,
            db_path=db_path or request.db_path,
            params=params or request.params,
            contract_version=request.contract_version,
        )
    if isinstance(request, str):
        return KnowledgeOpsApiRequest(
            operation=request,
            db_path=db_path or "runs/x_data.sqlite3",
            params=params or {},
        )
    payload = dict(request)
    return KnowledgeOpsApiRequest(
        operation=str(payload.get("operation") or ""),
        db_path=db_path or payload.get("db_path") or "runs/x_data.sqlite3",
        params=params or payload.get("params") or {},
        contract_version=str(
            payload.get("contract_version") or KNOWLEDGEOPS_API_CONTRACT_VERSION
        ),
    )


def _reject_forbidden_bridge_fields(value: Any, *, path: str = "request") -> None:
    if isinstance(value, Mapping):
        for key, nested in value.items():
            if key in FORBIDDEN_BRIDGE_FIELDS:
                raise ValueError(f"{path}: forbidden bridge field {key!r}")
            _reject_forbidden_bridge_fields(nested, path=f"{path}.{key}")
    elif isinstance(value, list | tuple):
        for index, nested in enumerate(value):
            _reject_forbidden_bridge_fields(nested, path=f"{path}[{index}]")


def _as_payload(value: Any) -> Any:
    if hasattr(value, "as_dict"):
        return value.as_dict()
    if isinstance(value, tuple):
        return [_as_payload(item) for item in value]
    if isinstance(value, list):
        return [_as_payload(item) for item in value]
    if isinstance(value, dict):
        return {key: _as_payload(item) for key, item in value.items()}
    return value


def _payload_status(payload: Any) -> str:
    if isinstance(payload, dict) and isinstance(payload.get("status"), str):
        return payload["status"]
    return "ok"


def _knowledge_sync_sources(db_path: Path, params: dict[str, Any]) -> Any:
    from research_x.memory.source_manifest import sync_x_source_manifest

    return sync_x_source_manifest(
        db_path,
        observation_run_id=params.get("observation_run_id"),
        observation_completeness=params.get("observation_completeness"),
        observed_at=params.get("observed_at"),
    )


def _knowledge_source_list(db_path: Path, params: dict[str, Any]) -> Any:
    return _select_rows(
        db_path,
        """
        SELECT source_ref, source_kind, source_status, updated_at
        FROM memory_sources
        ORDER BY updated_at DESC, source_ref
        LIMIT ?
        """,
        (_int(params.get("limit"), default=50),),
    )


def _knowledge_source_show(db_path: Path, params: dict[str, Any]) -> Any:
    source_ref = _required_str(params, "source_ref")
    rows = _select_rows(db_path, "SELECT * FROM memory_sources WHERE source_ref = ?", (source_ref,))
    return rows[0] if rows else {}


def _knowledge_observations(db_path: Path, params: dict[str, Any]) -> Any:
    source_ref = params.get("source_ref")
    limit = _int(params.get("limit"), default=50)
    if source_ref:
        return _select_rows(
            db_path,
            """
            SELECT *
            FROM memory_source_observations
            WHERE source_ref = ?
            ORDER BY observed_at DESC
            LIMIT ?
            """,
            (str(source_ref), limit),
        )
    return _select_rows(
        db_path,
        """
        SELECT *
        FROM memory_source_observations
        ORDER BY observed_at DESC
        LIMIT ?
        """,
        (limit,),
    )


def _knowledge_reconcile(db_path: Path, params: dict[str, Any]) -> Any:
    from research_x.memory.reconciliation import reconcile_source_observation

    return reconcile_source_observation(
        db_path,
        observed_source_refs=_str_tuple(params.get("observed_source_refs")),
        observation_completeness=str(params.get("observation_completeness") or "partial"),
        reconciliation_scope=str(params.get("scope") or "local-db-full-scan"),
        reconciliation_run_id=params.get("run_id"),
        started_at=str(params.get("started_at") or ""),
    )


def _knowledge_reconcile_show(db_path: Path, params: dict[str, Any]) -> Any:
    run_id = _required_str(params, "run_id")
    return {
        "status": "ok",
        "run": _one_or_none(
            _select_rows(
                db_path,
                "SELECT * FROM memory_reconciliation_runs WHERE reconciliation_run_id = ?",
                (run_id,),
            )
        ),
        "items": _select_rows(
            db_path,
            """
            SELECT *
            FROM memory_reconciliation_items
            WHERE reconciliation_run_id = ?
            ORDER BY created_at, reconciliation_item_id
            """,
            (run_id,),
        ),
    }


def _knowledge_cleanup_orphans(db_path: Path, params: dict[str, Any]) -> Any:
    dry_run = bool(params.get("dry_run", True))
    with sqlite3.connect(db_path, timeout=60) as conn:
        conn.row_factory = sqlite3.Row
        ensure_memory_schema(conn)
        sources = {
            row["source_ref"]
            for row in conn.execute("SELECT source_ref FROM memory_sources")
        }
        artifact_rows = conn.execute(
            """
            SELECT artifact_id, source_refs_json
            FROM memory_artifacts
            WHERE artifact_status = 'active'
            ORDER BY artifact_id
            """
        ).fetchall()
        orphans: list[str] = []
        for row in artifact_rows:
            source_refs = json.loads(row["source_refs_json"] or "[]")
            if source_refs and not any(source_ref in sources for source_ref in source_refs):
                orphans.append(row["artifact_id"])
        if orphans and not dry_run:
            conn.executemany(
                "UPDATE memory_artifacts SET artifact_status = 'orphaned' WHERE artifact_id = ?",
                [(artifact_id,) for artifact_id in orphans],
            )
    return {
        "status": "dry_run" if dry_run else "updated",
        "orphan_candidates": orphans,
        "orphan_count": len(orphans),
        "destructive_delete": False,
    }


def _knowledge_status(db_path: Path, _params: dict[str, Any]) -> Any:
    tables = (
        "memory_sources",
        "memory_source_observations",
        "memory_artifacts",
        "memory_projection_artifacts",
        "memory_participation_decisions",
        "memory_reconciliation_runs",
        "memory_route_promotion_decisions",
        "memory_audit_events",
    )
    with sqlite3.connect(db_path, timeout=60) as conn:
        ensure_memory_schema(conn)
        counts = {
            table: conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in tables
        }
    return {"status": "ok", "counts": counts}


def _artifacts_list(db_path: Path, params: dict[str, Any]) -> Any:
    return _select_rows(
        db_path,
        """
        SELECT artifact_id, artifact_role, artifact_kind,
               authority_level, output_mode, artifact_status
        FROM memory_artifacts
        ORDER BY updated_at DESC, artifact_id
        LIMIT ?
        """,
        (_int(params.get("limit"), default=50),),
    )


def _artifacts_show(db_path: Path, params: dict[str, Any]) -> Any:
    artifact_id = _required_str(params, "artifact_id")
    rows = _select_rows(
        db_path,
        "SELECT * FROM memory_artifacts WHERE artifact_id = ?",
        (artifact_id,),
    )
    return rows[0] if rows else {}


def _artifacts_links(db_path: Path, params: dict[str, Any]) -> Any:
    artifact_id = _required_str(params, "artifact_id")
    return _select_rows(
        db_path,
        """
        SELECT *
        FROM memory_artifact_links
        WHERE source_artifact_id = ? OR target_artifact_id = ?
        ORDER BY created_at, link_id
        """,
        (artifact_id, artifact_id),
    )


def _artifacts_validate(db_path: Path, _params: dict[str, Any]) -> Any:
    rows = _select_rows(
        db_path,
        """
        SELECT artifact_id, artifact_role, authority_level, source_refs_json,
               artifact_status
        FROM memory_artifacts
        ORDER BY artifact_id
        """,
    )
    issues: list[dict[str, Any]] = []
    for row in rows:
        if not row["artifact_role"] or not row["authority_level"]:
            issues.append({"artifact_id": row["artifact_id"], "issue": "missing_role"})
        if row["source_refs_json"] is None:
            issues.append({"artifact_id": row["artifact_id"], "issue": "missing_source_refs_json"})
    return {
        "status": "ok" if not issues else "needs_review",
        "artifacts": len(rows),
        "issues": issues,
    }


def _projections(db_path: Path, params: dict[str, Any], *, command: str) -> Any:
    from research_x.memory.projection_lifecycle import (
        build_projection_lifecycle,
        plan_projection_lifecycle,
        projection_lifecycle_coverage,
        projection_lifecycle_rows,
    )

    if command == "plan":
        return plan_projection_lifecycle(
            db_path,
            projection_kind=params.get("projection_kind"),
        )
    if command == "build":
        return build_projection_lifecycle(
            db_path,
            mode=str(params.get("mode") or "incremental"),
            projection_kind=params.get("projection_kind"),
            builder_params={
                "provider": params.get("provider") or "local_hash",
                "model": params.get("model"),
                "dimensions": params.get("dimensions"),
                "embedding_profile": params.get("embedding_profile"),
                "text_template_version": params.get("text_template_version"),
                "backend": params.get("backend") or "numpy",
                "bit_width": params.get("bit_width") or 4,
                "out_dir": params.get("out_dir"),
                "doc_type": params.get("doc_type"),
                "account": params.get("account"),
            },
        )
    if command == "coverage":
        return projection_lifecycle_coverage(db_path)
    rows = projection_lifecycle_rows(db_path, projection_id=params.get("projection_id"))
    return rows[0] if params.get("projection_id") and rows else list(rows)


def _participation_rebuild(db_path: Path, params: dict[str, Any]) -> Any:
    from research_x.memory.participation import rebuild_participation_decisions

    output_modes = _str_tuple(params.get("output_modes") or params.get("output_mode"))
    if not output_modes:
        output_modes = (
            "explore",
            "collect",
            "working_note",
            "synthesize",
            "evidence_package",
            "answer",
        )
    return rebuild_participation_decisions(
        db_path,
        output_modes=output_modes,
        decided_at=str(params.get("decided_at") or ""),
    )


def _participation_lookup(db_path: Path, params: dict[str, Any]) -> Any:
    source_ref = params.get("source_ref")
    artifact_id = params.get("artifact_id")
    output_mode = _required_str(params, "output_mode")
    if not source_ref and not artifact_id:
        raise ValueError("source_ref or artifact_id is required")
    if source_ref:
        rows = _select_rows(
            db_path,
            """
            SELECT *
            FROM memory_participation_decisions
            WHERE source_ref = ? AND output_mode = ?
            """,
            (str(source_ref), output_mode),
        )
    else:
        rows = _select_rows(
            db_path,
            """
            SELECT *
            FROM memory_participation_decisions
            WHERE artifact_id = ? AND output_mode = ?
            """,
            (str(artifact_id), output_mode),
        )
    return rows[0] if rows else {"status": "missing_decision"}


def _mode_search(db_path: Path, params: dict[str, Any], *, output_mode: str) -> Any:
    from research_x.memory.search import search_memory
    from research_x.tool_interface.mode_aware_search import search_results_tool_output_v2

    query = _required_str(params, "query")
    results = search_memory(
        db_path,
        query,
        limit=_int(params.get("limit"), default=5),
        doc_type=params.get("doc_type"),
        account=params.get("account"),
    )
    return search_results_tool_output_v2(
        query=query,
        results=results,
        output_mode=output_mode,
    )


def _working_note(db_path: Path, params: dict[str, Any], *, command: str) -> Any:
    from research_x.memory.working_notes import (
        append_working_note,
        create_working_note,
        expire_working_note,
        link_working_note_to_artifacts,
        promote_working_note_to_curated_source,
        read_working_note,
    )

    if command == "create":
        return create_working_note(
            db_path,
            title=_required_str(params, "title"),
            body=_required_str(params, "body"),
            task_scope=_required_str(params, "task_scope"),
            thread_scope=params.get("thread_scope"),
            source_refs=_str_tuple(params.get("source_refs") or params.get("source_ref")),
            artifact_refs=_str_tuple(params.get("artifact_refs") or params.get("artifact_ref")),
            retention_policy=str(params.get("retention_policy") or "task"),
            created_at=params.get("created_at"),
            expires_at=params.get("expires_at"),
            metadata=_mapping(params.get("metadata")),
        )
    if command == "append":
        return append_working_note(
            db_path,
            _required_str(params, "note_id"),
            _required_str(params, "text"),
            updated_at=params.get("updated_at"),
        )
    if command == "show":
        note = read_working_note(db_path, _required_str(params, "note_id"))
        if note is None:
            raise KeyError(f"working note not found: {params['note_id']}")
        return note
    if command == "link":
        return link_working_note_to_artifacts(
            db_path,
            _required_str(params, "note_id"),
            source_refs=_str_tuple(params.get("source_refs") or params.get("source_ref")),
            artifact_refs=_str_tuple(params.get("artifact_refs") or params.get("artifact_ref")),
            updated_at=params.get("updated_at"),
        )
    if command == "promote":
        return promote_working_note_to_curated_source(
            db_path,
            _required_str(params, "note_id"),
            human_in_loop_approved=bool(
                params.get("human_in_loop_approved")
                or params.get("confirm_human_in_loop")
            ),
            approved_by=params.get("approved_by"),
            approval_note=params.get("approval_note"),
            promoted_at=params.get("promoted_at"),
        )
    return expire_working_note(
        db_path,
        _required_str(params, "note_id"),
        expired_at=params.get("expired_at"),
    )


def _synthesize(_db_path: Path, params: dict[str, Any]) -> Any:
    from research_x.tool_interface.memory_tool_contract import (
        CONTRACT_VERSION_V2,
        ToolOutputV2,
    )

    return ToolOutputV2(
        contract_version=CONTRACT_VERSION_V2,
        tool_kind="research_x.memory.synthesize",
        query=_required_str(params, "query"),
        output_mode="synthesize",
        status="ok",
        answer_text=None,
        items=(),
        citations=(),
        claim_support=None,
        working_note_id=None,
        trace={
            "unsupported_claims": [],
            "unresolved_items": [],
            "synthesis_is_not_answer": True,
        },
    )


def _evidence_package(db_path: Path, params: dict[str, Any]) -> Any:
    from research_x.memory.evidence_package import build_evidence_package_output

    artifact_ids = _evidence_artifact_ids(db_path, params)
    return build_evidence_package_output(
        db_path,
        query=_required_str(params, "query"),
        artifact_ids=artifact_ids,
    )


def _answer(db_path: Path, params: dict[str, Any]) -> Any:
    from research_x.memory.evidence_package import promote_evidence_package_to_answer

    evidence_package = _evidence_package(db_path, params)
    return promote_evidence_package_to_answer(
        db_path,
        evidence_package=evidence_package,
        answer_text=_required_str(params, "answer_text"),
        claims=tuple(_mapping_list(params.get("claims"))),
        output_run_id=params.get("output_run_id"),
        created_at=params.get("created_at"),
    )


def _evidence_artifact_ids(db_path: Path, params: dict[str, Any]) -> tuple[str, ...]:
    artifact_ids = _str_tuple(params.get("artifact_ids") or params.get("artifact_id"))
    if artifact_ids:
        return artifact_ids
    rows = _select_rows(
        db_path,
        """
        SELECT artifact_id
        FROM memory_artifacts
        WHERE artifact_role = 'evidence_view'
        ORDER BY updated_at DESC, artifact_id
        LIMIT ?
        """,
        (_int(params.get("limit"), default=5),),
    )
    return tuple(row["artifact_id"] for row in rows)


def _eval_run(db_path: Path, params: dict[str, Any]) -> Any:
    from research_x.memory.evals_v2 import run_eval_cases_v2

    return run_eval_cases_v2(
        db_path,
        cases_path=_required_str(params, "cases_path"),
        run_id=params.get("run_id"),
        started_at=params.get("started_at"),
    )


def _eval_compare(db_path: Path, params: dict[str, Any]) -> Any:
    baseline = _required_str(params, "baseline")
    candidate = _required_str(params, "candidate")
    rows = _select_rows(
        db_path,
        """
        SELECT *
        FROM memory_eval_runs
        WHERE run_id IN (?, ?)
        ORDER BY run_id
        """,
        (baseline, candidate),
    )
    found = {row["run_id"] for row in rows}
    missing = sorted({baseline, candidate} - found)
    return {"status": "ok" if not missing else "missing_run", "runs": rows, "missing": missing}


def _eval_report(db_path: Path, params: dict[str, Any]) -> Any:
    run_id = _required_str(params, "run_id")
    return {
        "status": "ok",
        "run": _one_or_none(
            _select_rows(db_path, "SELECT * FROM memory_eval_runs WHERE run_id = ?", (run_id,))
        ),
        "results": _select_rows(
            db_path,
            """
            SELECT *
            FROM memory_eval_results
            WHERE run_id = ?
            ORDER BY case_index, result_id
            """,
            (run_id,),
        ),
    }


def _route_promotion(db_path: Path, params: dict[str, Any], *, command: str) -> Any:
    from research_x.memory.route_promotion import (
        approve_route_promotion,
        check_route_promotion,
        list_route_promotion_decisions,
        reject_route_promotion,
    )

    if command == "check":
        return check_route_promotion(
            db_path,
            candidate_route_version=_required_str(params, "candidate_route_version"),
            baseline_route_version=params.get("baseline_route_version"),
            eval_run_ids=_str_tuple(params.get("eval_run_ids") or params.get("eval_run_id")),
            output_modes=_str_tuple(params.get("output_modes") or params.get("output_mode")),
            deltas=_float_mapping(params.get("deltas")),
            thresholds=_mapping(params.get("thresholds")),
            created_at=_required_str(params, "created_at"),
            metadata=_mapping(params.get("metadata")),
        )
    if command == "approve":
        return approve_route_promotion(
            db_path,
            promotion_decision_id=_required_str(params, "decision_id"),
            approved_at=_required_str(params, "at"),
            reason=_required_str(params, "reason"),
        )
    if command == "reject":
        return reject_route_promotion(
            db_path,
            promotion_decision_id=_required_str(params, "decision_id"),
            rejected_at=_required_str(params, "at"),
            reason=_required_str(params, "reason"),
        )
    return list_route_promotion_decisions(db_path, status=params.get("status"))


def _audit_events(db_path: Path, params: dict[str, Any]) -> Any:
    from research_x.memory.audit_events import list_audit_events

    return list_audit_events(db_path, event_type=params.get("event_type"))


def _audit_latest(db_path: Path, _params: dict[str, Any]) -> Any:
    rows = _select_rows(
        db_path,
        """
        SELECT *
        FROM memory_audit_events
        ORDER BY created_at DESC, event_id DESC
        LIMIT 1
        """,
    )
    return rows[0] if rows else {"status": "no_events"}


def _audit_summary(db_path: Path, _params: dict[str, Any]) -> Any:
    from research_x.memory.audit_events import audit_summary

    return audit_summary(db_path)


def _audit_alert_local_jsonl_test(db_path: Path, params: dict[str, Any]) -> Any:
    from research_x.memory.audit_events import (
        deliver_audit_events_to_jsonl,
        register_alert_sink,
    )

    sink = register_alert_sink(
        db_path,
        sink_kind="local_jsonl",
        sink_config={"path": _required_str(params, "path")},
        sink_id=params.get("sink_id"),
        created_at=_required_str(params, "delivered_at"),
    )
    delivered = deliver_audit_events_to_jsonl(
        db_path,
        sink_id=sink.sink_id,
        event_type=params.get("event_type"),
        delivered_at=_required_str(params, "delivered_at"),
    )
    return {"status": "ok", "sink": sink.as_dict(), "delivered": delivered}


def _select_rows(
    db_path: str | Path,
    query: str,
    params: tuple[Any, ...] = (),
) -> list[dict[str, Any]]:
    with sqlite3.connect(db_path, timeout=60) as conn:
        conn.row_factory = sqlite3.Row
        ensure_memory_schema(conn)
        rows = conn.execute(query, params).fetchall()
    return [dict(row) for row in rows]


def _one_or_none(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    return rows[0] if rows else None


def _required_str(params: Mapping[str, Any], key: str) -> str:
    value = params.get(key)
    if value is None or str(value).strip() == "":
        raise ValueError(f"{key} is required")
    return str(value)


def _str_tuple(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,) if value else ()
    return tuple(str(item) for item in value if str(item).strip())


def _int(value: Any, *, default: int) -> int:
    if value is None:
        return default
    return int(value)


def _mapping(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise TypeError("expected mapping")
    return dict(value)


def _mapping_list(value: Any) -> list[dict[str, Any]]:
    if value is None:
        return []
    if not isinstance(value, list | tuple):
        raise TypeError("expected list of mappings")
    return [_mapping(item) for item in value]


def _float_mapping(value: Any) -> dict[str, float]:
    return {str(key): float(item) for key, item in _mapping(value).items()}


_HANDLERS: dict[str, Handler] = {
    "knowledge.sync_sources": _knowledge_sync_sources,
    "knowledge.source_list": _knowledge_source_list,
    "knowledge.source_show": _knowledge_source_show,
    "knowledge.observations": _knowledge_observations,
    "knowledge.reconcile": _knowledge_reconcile,
    "knowledge.reconcile_show": _knowledge_reconcile_show,
    "knowledge.cleanup_orphans": _knowledge_cleanup_orphans,
    "knowledge.status": _knowledge_status,
    "artifacts.list": _artifacts_list,
    "artifacts.show": _artifacts_show,
    "artifacts.links": _artifacts_links,
    "artifacts.validate": _artifacts_validate,
    "projections.plan": lambda db, params: _projections(db, params, command="plan"),
    "projections.build": lambda db, params: _projections(db, params, command="build"),
    "projections.coverage": lambda db, params: _projections(db, params, command="coverage"),
    "projections.show": lambda db, params: _projections(db, params, command="show"),
    "participation.rebuild": _participation_rebuild,
    "participation.check": _participation_lookup,
    "participation.explain": _participation_lookup,
    "memory.explore": lambda db, params: _mode_search(db, params, output_mode="explore"),
    "memory.collect": lambda db, params: _mode_search(db, params, output_mode="collect"),
    "memory.working_note.create": lambda db, params: _working_note(db, params, command="create"),
    "memory.working_note.append": lambda db, params: _working_note(db, params, command="append"),
    "memory.working_note.show": lambda db, params: _working_note(db, params, command="show"),
    "memory.working_note.link": lambda db, params: _working_note(db, params, command="link"),
    "memory.working_note.promote": lambda db, params: _working_note(db, params, command="promote"),
    "memory.working_note.expire": lambda db, params: _working_note(db, params, command="expire"),
    "memory.synthesize": _synthesize,
    "memory.evidence_package": _evidence_package,
    "memory.answer": _answer,
    "eval_v2.run": _eval_run,
    "eval_v2.compare": _eval_compare,
    "eval_v2.report": _eval_report,
    "route_promotion.check": lambda db, params: _route_promotion(db, params, command="check"),
    "route_promotion.approve": lambda db, params: _route_promotion(db, params, command="approve"),
    "route_promotion.reject": lambda db, params: _route_promotion(db, params, command="reject"),
    "route_promotion.list": lambda db, params: _route_promotion(db, params, command="list"),
    "audit.events": _audit_events,
    "audit.latest": _audit_latest,
    "audit.summary": _audit_summary,
    "audit.alert_local_jsonl_test": _audit_alert_local_jsonl_test,
}
