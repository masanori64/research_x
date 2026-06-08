from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from research_x.memory.schema import ensure_memory_schema


@dataclass(frozen=True)
class ResearchRunSummary:
    run_id: str
    run_kind: str
    query: str
    status: str
    route: str | None
    stop_reason: str | None
    started_at: str
    finished_at: str | None
    detail_counts: dict[str, int]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ResearchRunDetail:
    summary: ResearchRunSummary
    metadata: dict[str, Any]
    steps: tuple[dict[str, Any], ...]
    results: tuple[dict[str, Any], ...]
    context_chunks: tuple[dict[str, Any], ...]
    citations: tuple[dict[str, Any], ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "summary": self.summary.as_dict(),
            "metadata": self.metadata,
            "steps": list(self.steps),
            "results": list(self.results),
            "context_chunks": list(self.context_chunks),
            "citations": list(self.citations),
        }


def list_research_runs(
    db_path: str | Path,
    *,
    run_kind: str = "all",
    limit: int = 20,
) -> tuple[ResearchRunSummary, ...]:
    path = Path(db_path)
    if not path.exists():
        raise FileNotFoundError(f"database not found: {path}")
    kinds = _resolve_run_kind(run_kind)
    summaries: list[ResearchRunSummary] = []
    with sqlite3.connect(path, timeout=60) as conn:
        conn.row_factory = sqlite3.Row
        ensure_memory_schema(conn)
        if "objective" in kinds:
            summaries.extend(_objective_run_summaries(conn, limit=max(1, limit)))
        if "workflow" in kinds:
            summaries.extend(_workflow_run_summaries(conn, limit=max(1, limit)))
        if "search" in kinds:
            summaries.extend(_search_run_summaries(conn, limit=max(1, limit)))
    summaries.sort(key=lambda item: item.started_at, reverse=True)
    return tuple(summaries[: max(1, limit)])


def show_research_run(
    db_path: str | Path,
    run_id: str,
    *,
    run_kind: str = "auto",
) -> ResearchRunDetail:
    path = Path(db_path)
    if not path.exists():
        raise FileNotFoundError(f"database not found: {path}")
    with sqlite3.connect(path, timeout=60) as conn:
        conn.row_factory = sqlite3.Row
        ensure_memory_schema(conn)
        kinds = _resolve_run_kind(run_kind)
        if "objective" in kinds:
            detail = _objective_run_detail(conn, run_id)
            if detail is not None:
                return detail
        if "workflow" in kinds:
            detail = _workflow_run_detail(conn, run_id)
            if detail is not None:
                return detail
        if "search" in kinds:
            detail = _search_run_detail(conn, run_id)
            if detail is not None:
                return detail
    raise KeyError(f"research run not found: {run_id}")


def research_runs_json(runs: tuple[ResearchRunSummary, ...]) -> str:
    return json.dumps([run.as_dict() for run in runs], ensure_ascii=False, indent=2, sort_keys=True)


def research_run_json(detail: ResearchRunDetail) -> str:
    return json.dumps(detail.as_dict(), ensure_ascii=False, indent=2, sort_keys=True)


def format_research_runs(runs: tuple[ResearchRunSummary, ...]) -> str:
    if not runs:
        return "research runs: none"
    lines = ["research runs:"]
    for run in runs:
        counts = " ".join(f"{key}={value}" for key, value in sorted(run.detail_counts.items()))
        route = f" route={run.route}" if run.route else ""
        stop = f" stop={run.stop_reason}" if run.stop_reason else ""
        lines.append(
            f"- {run.run_kind} {run.run_id} status={run.status}{route}{stop} "
            f"at={run.started_at} {counts}".rstrip()
        )
    return "\n".join(lines)


def format_research_run(detail: ResearchRunDetail) -> str:
    summary = detail.summary
    lines = [
        (
            f"{summary.run_kind}: {summary.run_id} status={summary.status} "
            f"route={summary.route or '-'} stop={summary.stop_reason or '-'}"
        ),
        f"query: {summary.query}",
    ]
    _append_objective_artifacts(lines, detail.metadata)
    if detail.steps:
        lines.append("steps:")
        for step in detail.steps[:12]:
            lines.append(
                "  "
                + " ".join(
                    part
                    for part in (
                        f"{step.get('step_index', '-')}:",
                        str(step.get("action") or step.get("route_arm") or "-"),
                        f"status={step.get('status', '-')}",
                        f"evidence={step.get('evidence_count')}"
                        if step.get("evidence_count") is not None
                        else "",
                        f"citations={step.get('citation_count')}"
                        if step.get("citation_count") is not None
                        else "",
                        f"stop={step.get('stop_condition')}"
                        if step.get("stop_condition")
                        else "",
                        f"error={step.get('error')}" if step.get("error") else "",
                    )
                    if part
                )
            )
    if detail.results:
        lines.append("results:")
        for result in detail.results[:10]:
            quality = _source_quality_text(result.get("metadata"))
            lines.append(
                "  "
                f"{result.get('rank', '-')}: {result.get('doc_id', '-')}"
                f" score={result.get('score', '-')}"
                f" provider={result.get('provider', '-')}/{result.get('provider_role', '-')}"
                f" evidence={result.get('evidence_status', '-')}"
                f"{quality}"
            )
    if detail.context_chunks:
        lines.append(f"context_chunks: {len(detail.context_chunks)}")
        for chunk in detail.context_chunks[:5]:
            quality = _source_quality_text(chunk.get("metadata"))
            lines.append(
                "  "
                f"{chunk.get('chunk_index', '-')}: {chunk.get('source_kind', '-')}"
                f" provider={chunk.get('provider', '-')}/{chunk.get('provider_role', '-')}"
                f" source={chunk.get('source_id', '-')}"
                f"{quality}"
            )
    if detail.citations:
        lines.append(f"citations: {len(detail.citations)}")
        for citation in detail.citations[:5]:
            quality = _source_quality_text(citation.get("metadata"))
            lines.append(
                "  "
                f"{citation.get('source_kind', '-')}"
                f" source={citation.get('source_id', '-')}"
                f" support={citation.get('support_type', '-')}"
                f" evidence={citation.get('evidence_status', '-')}"
                f"{quality}"
            )
    return "\n".join(lines)


def _append_objective_artifacts(lines: list[str], metadata: dict[str, Any]) -> None:
    task_frame = _dict(metadata.get("research_task_frame"))
    if task_frame:
        lines.append(
            "research_task_frame: "
            f"objective={task_frame.get('objective_type', '-')} "
            f"local_x_db_primary={task_frame.get('local_x_db_primary', False)} "
            f"goal={task_frame.get('primary_goal', '-')}"
        )
    graph = _dict(metadata.get("search_plan_graph"))
    if graph:
        nodes = graph.get("nodes") if isinstance(graph.get("nodes"), list) else []
        variants = (
            graph.get("query_variants")
            if isinstance(graph.get("query_variants"), list)
            else []
        )
        lines.append(
            "search_plan_graph: "
            f"nodes={len(nodes)} variants={len(variants)} "
            f"contract={graph.get('contract', '-')}"
        )
        for node in nodes[:6]:
            if isinstance(node, dict):
                roles = ",".join(str(role) for role in node.get("provider_roles", []) or [])
                lines.append(
                    "  - "
                    f"{node.get('route_arm', '-')} "
                    f"roles={roles} quota={node.get('quota_policy', '-')}"
                )
    provider_matrix = _dict(metadata.get("provider_capability_matrix"))
    if provider_matrix:
        rows = (
            provider_matrix.get("rows")
            if isinstance(provider_matrix.get("rows"), list)
            else []
        )
        gated = [
            str(row.get("provider"))
            for row in rows
            if isinstance(row, dict) and str(row.get("status")) == "gated"
        ]
        lines.append(
            "provider_capability_matrix: "
            f"rows={len(rows)} gated={','.join(gated[:8]) or '-'} "
            f"contract={provider_matrix.get('contract', '-')}"
        )
    personalization = _dict(metadata.get("personalization_policy"))
    if personalization:
        disallowed = ",".join(
            str(use) for use in personalization.get("disallowed_uses", []) or []
        )
        lines.append(
            "personalization_policy: "
            f"mode={personalization.get('mode', '-')} "
            f"always_on={personalization.get('always_on_personal_boost', False)} "
            f"disallowed={disallowed}"
        )
    user_signal = _dict(metadata.get("user_signal_policy"))
    if user_signal:
        lines.append(
            "user_signal_policy: "
            f"scope={user_signal.get('route_scope', '-')} "
            f"evidence={user_signal.get('evidence_status', '-')}"
        )
    brief = _dict(metadata.get("research_brief"))
    if brief:
        lines.append(
            "research_brief: "
            f"evidence={brief.get('evidence_total', 0)} "
            f"citations={brief.get('citation_total', 0)} "
            f"gaps={brief.get('gap_count', 0)} "
            f"claim_support={brief.get('claim_support_status', '-')}"
        )
        next_actions = brief.get("next_actions") or []
        if next_actions:
            lines.append(f"next_actions: {', '.join(str(action) for action in next_actions)}")
    coverage = _dict(metadata.get("result_coverage_map"))
    if coverage:
        executed = ",".join(str(route) for route in coverage.get("executed_routes", []) or [])
        provider_skipped = ",".join(
            str(route) for route in coverage.get("provider_quota_skipped_routes", []) or []
        )
        lines.append(
            "result_coverage: "
            f"executed={executed or '-'} "
            f"evidence={coverage.get('evidence_total', 0)} "
            f"citations={coverage.get('citation_total', 0)} "
            f"provider_skipped={provider_skipped or '-'}"
        )
    episode = _dict(metadata.get("search_episode_trace"))
    if episode:
        events = episode.get("events") if isinstance(episode.get("events"), list) else []
        lines.append(
            "search_episode_trace: "
            f"events={len(events)} stop={episode.get('stop_reason', '-')} "
            f"contract={episode.get('contract', '-')}"
        )
    reader_quality = _dict(metadata.get("reader_quality_profile"))
    if reader_quality:
        lines.append(
            "reader_quality_profile: "
            f"status={reader_quality.get('status', '-')} "
            f"external_routes={reader_quality.get('external_route_count', 0)} "
            f"urls={reader_quality.get('discovered_url_count', 0)}"
        )
    gaps = _dict(metadata.get("evidence_gap"))
    gap_rows = gaps.get("gaps") if isinstance(gaps.get("gaps"), list) else []
    if gap_rows:
        lines.append("evidence_gaps:")
        for gap in gap_rows[:8]:
            if isinstance(gap, dict):
                lines.append(f"  - {gap.get('gap_id', '-')}: {gap.get('message', '')}")
    serp = _dict(metadata.get("serp_flattening_audit"))
    if serp:
        checks = _dict(serp.get("checks"))
        lines.append(
            "serp_flattening: "
            f"status={serp.get('status', '-')} "
            f"rank_evidence={checks.get('rank_used_as_evidence', False)} "
            f"snippet_evidence={checks.get('snippet_used_as_evidence', False)}"
        )
    source_signals = metadata.get("source_quality_signals")
    if isinstance(source_signals, list) and source_signals:
        lines.append("source_quality:")
        for signal in source_signals[:8]:
            if isinstance(signal, dict):
                lines.append(
                    "  - "
                    f"{signal.get('source_kind', '-')}: {signal.get('quality_class', '-')}"
                    f" evidence={signal.get('evidence_status', '-')}"
                )
    claim = _dict(metadata.get("claim_support_check"))
    if claim:
        lines.append(
            "claim_support: "
            f"status={claim.get('status', '-')} "
            f"citations={claim.get('citation_count', 0)} "
            f"evidence={claim.get('evidence_count', 0)}"
        )


def _source_quality_text(metadata: Any) -> str:
    if not isinstance(metadata, dict):
        return ""
    quality = metadata.get("source_quality_class")
    risks = metadata.get("source_risk_flags")
    risk_text = ""
    if isinstance(risks, list) and risks:
        risk_text = ",".join(str(risk) for risk in risks[:4])
    parts = []
    if quality:
        parts.append(f"quality={quality}")
    if risk_text:
        parts.append(f"risk={risk_text}")
    return " " + " ".join(parts) if parts else ""


def _objective_run_summaries(
    conn: sqlite3.Connection,
    *,
    limit: int,
) -> list[ResearchRunSummary]:
    rows = conn.execute(
        """
        SELECT route_run_id, query, primary_route, status, stop_reason, created_at, updated_at,
               selected_routes_json, metadata_json
        FROM memory_objective_route_runs
        ORDER BY created_at DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    summaries = []
    for row in rows:
        metadata = _objective_metadata(_loads_dict(row["metadata_json"]))
        brief = _dict(metadata.get("research_brief"))
        summaries.append(
            ResearchRunSummary(
                run_id=row["route_run_id"],
                run_kind="objective",
                query=row["query"],
                status=row["status"],
                route=row["primary_route"],
                stop_reason=row["stop_reason"],
                started_at=row["created_at"],
                finished_at=row["updated_at"],
                detail_counts={
                    "steps": _count_objective_steps(conn, row["route_run_id"]),
                    "evidence": int(brief.get("evidence_total") or 0),
                    "citations": int(brief.get("citation_total") or 0),
                    "gaps": int(brief.get("gap_count") or 0),
                },
            )
        )
    return summaries


def _workflow_run_summaries(
    conn: sqlite3.Connection,
    *,
    limit: int,
) -> list[ResearchRunSummary]:
    rows = conn.execute(
        """
        SELECT workflow_id, query, route, status, stop_reason, started_at, finished_at,
               metadata_json
        FROM memory_workflow_runs
        ORDER BY started_at DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    summaries = []
    for row in rows:
        workflow_id = row["workflow_id"]
        context_run_ids = _workflow_context_run_ids_from_db(conn, workflow_id)
        summaries.append(
            ResearchRunSummary(
                run_id=workflow_id,
                run_kind="workflow",
                query=row["query"],
                status=row["status"],
                route=row["route"],
                stop_reason=row["stop_reason"],
                started_at=row["started_at"],
                finished_at=row["finished_at"],
                detail_counts={
                    "steps": _count_workflow_steps(conn, workflow_id),
                    "chunks": _count_context_chunks_for_run_ids(conn, context_run_ids),
                    "citations": _count_workflow_citations_for_run_ids(conn, context_run_ids),
                },
            )
        )
    return summaries


def _search_run_summaries(
    conn: sqlite3.Connection,
    *,
    limit: int,
) -> list[ResearchRunSummary]:
    rows = conn.execute(
        """
        SELECT run_id, query, status, result_count, started_at, finished_at, error
        FROM memory_search_runs
        ORDER BY started_at DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    return [
        ResearchRunSummary(
            run_id=row["run_id"],
            run_kind="search",
            query=row["query"],
            status=row["status"],
            route=None,
            stop_reason=row["error"],
            started_at=row["started_at"],
            finished_at=row["finished_at"],
            detail_counts={"results": int(row["result_count"] or 0)},
        )
        for row in rows
    ]


def _objective_run_detail(conn: sqlite3.Connection, run_id: str) -> ResearchRunDetail | None:
    row = conn.execute(
        """
        SELECT *
        FROM memory_objective_route_runs
        WHERE route_run_id = ?
        """,
        (run_id,),
    ).fetchone()
    if row is None:
        return None
    metadata = _objective_metadata(_loads_dict(row["metadata_json"]))
    steps = tuple(
        _objective_step_dict(step)
        for step in conn.execute(
            """
            SELECT *
            FROM memory_objective_route_steps
            WHERE route_run_id = ?
            ORDER BY step_index
            """,
            (run_id,),
        ).fetchall()
    )
    summary = ResearchRunSummary(
        run_id=row["route_run_id"],
        run_kind="objective",
        query=row["query"],
        status=row["status"],
        route=row["primary_route"],
        stop_reason=row["stop_reason"],
        started_at=row["created_at"],
        finished_at=row["updated_at"],
        detail_counts={
            "steps": len(steps),
            "evidence": int(_dict(metadata.get("research_brief")).get("evidence_total") or 0),
            "citations": int(_dict(metadata.get("research_brief")).get("citation_total") or 0),
            "gaps": int(_dict(metadata.get("research_brief")).get("gap_count") or 0),
        },
    )
    return ResearchRunDetail(
        summary=summary,
        metadata=metadata,
        steps=steps,
        results=(),
        context_chunks=(),
        citations=(),
    )


def _workflow_run_detail(conn: sqlite3.Connection, run_id: str) -> ResearchRunDetail | None:
    row = conn.execute(
        """
        SELECT *
        FROM memory_workflow_runs
        WHERE workflow_id = ?
        """,
        (run_id,),
    ).fetchone()
    if row is None:
        return None
    metadata = _loads_dict(row["metadata_json"])
    steps = tuple(
        _workflow_step_dict(step)
        for step in conn.execute(
            """
            SELECT *
            FROM memory_workflow_steps
            WHERE workflow_id = ?
            ORDER BY step_index
            """,
            (run_id,),
        ).fetchall()
    )
    context_run_ids = _workflow_context_run_ids(steps, fallback_run_id=run_id)
    chunks = _context_chunks_for_run_ids(conn, context_run_ids)
    citations = _citations_for_run_ids(conn, context_run_ids)
    summary = ResearchRunSummary(
        run_id=row["workflow_id"],
        run_kind="workflow",
        query=row["query"],
        status=row["status"],
        route=row["route"],
        stop_reason=row["stop_reason"],
        started_at=row["started_at"],
        finished_at=row["finished_at"],
        detail_counts={"steps": len(steps), "chunks": len(chunks), "citations": len(citations)},
    )
    return ResearchRunDetail(
        summary=summary,
        metadata=metadata,
        steps=steps,
        results=(),
        context_chunks=chunks,
        citations=citations,
    )


def _search_run_detail(conn: sqlite3.Connection, run_id: str) -> ResearchRunDetail | None:
    row = conn.execute(
        """
        SELECT *
        FROM memory_search_runs
        WHERE run_id = ?
        """,
        (run_id,),
    ).fetchone()
    if row is None:
        return None
    results = tuple(
        _search_result_dict(result)
        for result in conn.execute(
            """
            SELECT *
            FROM memory_search_results
            WHERE run_id = ?
            ORDER BY rank
            """,
            (run_id,),
        ).fetchall()
    )
    summary = ResearchRunSummary(
        run_id=row["run_id"],
        run_kind="search",
        query=row["query"],
        status=row["status"],
        route=None,
        stop_reason=row["error"],
        started_at=row["started_at"],
        finished_at=row["finished_at"],
        detail_counts={"results": len(results)},
    )
    return ResearchRunDetail(
        summary=summary,
        metadata={
            "query_plan": _loads_dict(row["query_plan_json"]),
            "parameters": _loads_dict(row["parameters_json"]),
        },
        steps=(),
        results=results,
        context_chunks=(),
        citations=(),
    )


def _context_chunks(conn: sqlite3.Connection, run_id: str) -> tuple[dict[str, Any], ...]:
    rows = conn.execute(
        """
        SELECT *
        FROM memory_context_chunks
        WHERE run_id = ?
        ORDER BY chunk_index
        """,
        (run_id,),
    ).fetchall()
    return tuple(_chunk_dict(row) for row in rows)


def _citations_for_run(conn: sqlite3.Connection, run_id: str) -> tuple[dict[str, Any], ...]:
    rows = conn.execute(
        """
        SELECT c.*
        FROM memory_citation_annotations c
        JOIN memory_context_chunks chunk ON chunk.chunk_id = c.chunk_id
        WHERE chunk.run_id = ?
        ORDER BY c.created_at, c.citation_id
        """,
        (run_id,),
    ).fetchall()
    return tuple(_citation_dict(row) for row in rows)


def _context_chunks_for_run_ids(
    conn: sqlite3.Connection,
    run_ids: tuple[str, ...],
) -> tuple[dict[str, Any], ...]:
    chunks: list[dict[str, Any]] = []
    for run_id in run_ids:
        chunks.extend(_context_chunks(conn, run_id))
    return tuple(chunks)


def _citations_for_run_ids(
    conn: sqlite3.Connection,
    run_ids: tuple[str, ...],
) -> tuple[dict[str, Any], ...]:
    citations: list[dict[str, Any]] = []
    for run_id in run_ids:
        citations.extend(_citations_for_run(conn, run_id))
    return tuple(citations)


def _workflow_context_run_ids(
    steps: tuple[dict[str, Any], ...],
    *,
    fallback_run_id: str,
) -> tuple[str, ...]:
    values = [fallback_run_id]
    for step in steps:
        output = step.get("output") if isinstance(step.get("output"), dict) else {}
        context_run_id = output.get("context_run_id") if isinstance(output, dict) else None
        if isinstance(context_run_id, str) and context_run_id:
            values.append(context_run_id)
    return _dedupe(values)


def _workflow_context_run_ids_from_db(
    conn: sqlite3.Connection,
    workflow_id: str,
) -> tuple[str, ...]:
    rows = conn.execute(
        """
        SELECT output_json
        FROM memory_workflow_steps
        WHERE workflow_id = ?
        ORDER BY step_index
        """,
        (workflow_id,),
    ).fetchall()
    steps = tuple({"output": _loads_dict(row["output_json"])} for row in rows)
    return _workflow_context_run_ids(steps, fallback_run_id=workflow_id)


def _objective_step_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "step_index": int(row["step_index"]),
        "route_arm": row["route_arm"],
        "status": row["status"],
        "evidence_count": int(row["evidence_count"]),
        "citation_count": int(row["citation_count"]),
        "stop_condition": row["stop_condition"],
        "escalation_trigger": row["escalation_trigger"],
        "provider_quota_skipped": bool(row["provider_quota_skipped"]),
        "output": _loads_dict(row["output_json"]),
        "created_at": row["created_at"],
    }


def _workflow_step_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "step_index": int(row["step_index"]),
        "action": row["action"],
        "status": row["status"],
        "error": row["error"],
        "input": _loads_dict(row["input_json"]),
        "output": _loads_dict(row["output_json"]),
        "created_at": row["created_at"],
    }


def _search_result_dict(row: sqlite3.Row) -> dict[str, Any]:
    metadata = _loads_dict(row["metadata_json"])
    return {
        "rank": int(row["rank"]),
        "doc_id": row["doc_id"],
        "doc_type": row["doc_type"],
        "source_kind": row["source_kind"],
        "source_id": row["source_id"],
        "source_url": row["source_url"],
        "score": float(row["score"]),
        "provider": row["provider"],
        "provider_role": row["provider_role"],
        "match_method": row["match_method"],
        "evidence_status": row["evidence_status"],
        "snippet": row["snippet"],
        "metadata": metadata,
    }


def _chunk_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "chunk_id": row["chunk_id"],
        "run_id": row["run_id"],
        "source_kind": row["source_kind"],
        "source_id": row["source_id"],
        "source_url": row["source_url"],
        "provider": row["provider"],
        "provider_role": row["provider_role"],
        "chunk_index": int(row["chunk_index"]),
        "token_count": row["token_count"],
        "relevance_score": row["relevance_score"],
        "extractor_version": row["extractor_version"],
        "metadata": _loads_dict(row["metadata_json"]),
    }


def _citation_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "citation_id": row["citation_id"],
        "chunk_id": row["chunk_id"],
        "source_kind": row["source_kind"],
        "source_id": row["source_id"],
        "source_url": row["source_url"],
        "title": row["title"],
        "support_type": row["support_type"],
        "evidence_status": row["evidence_status"],
        "confidence": row["confidence"],
        "metadata": _loads_dict(row["metadata_json"]),
    }


def _resolve_run_kind(run_kind: str) -> tuple[str, ...]:
    normalized = (run_kind or "all").strip().lower()
    if normalized == "auto":
        return ("objective", "workflow", "search")
    if normalized == "all":
        return ("objective", "workflow", "search")
    if normalized in {"objective", "workflow", "search"}:
        return (normalized,)
    raise ValueError(f"unknown research run kind: {run_kind}")


def _dedupe(values: list[str]) -> tuple[str, ...]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        out.append(value)
    return tuple(out)


def _count_objective_steps(conn: sqlite3.Connection, run_id: str) -> int:
    return int(
        conn.execute(
            "SELECT COUNT(*) FROM memory_objective_route_steps WHERE route_run_id = ?",
            (run_id,),
        ).fetchone()[0]
    )


def _count_workflow_steps(conn: sqlite3.Connection, run_id: str) -> int:
    return int(
        conn.execute(
            "SELECT COUNT(*) FROM memory_workflow_steps WHERE workflow_id = ?",
            (run_id,),
        ).fetchone()[0]
    )


def _count_context_chunks(conn: sqlite3.Connection, run_id: str) -> int:
    return int(
        conn.execute(
            "SELECT COUNT(*) FROM memory_context_chunks WHERE run_id = ?",
            (run_id,),
        ).fetchone()[0]
    )


def _count_context_chunks_for_run_ids(
    conn: sqlite3.Connection,
    run_ids: tuple[str, ...],
) -> int:
    return sum(_count_context_chunks(conn, run_id) for run_id in run_ids)


def _count_workflow_citations(conn: sqlite3.Connection, run_id: str) -> int:
    return int(
        conn.execute(
            """
            SELECT COUNT(*)
            FROM memory_citation_annotations c
            JOIN memory_context_chunks chunk ON chunk.chunk_id = c.chunk_id
            WHERE chunk.run_id = ?
            """,
            (run_id,),
        ).fetchone()[0]
    )


def _count_workflow_citations_for_run_ids(
    conn: sqlite3.Connection,
    run_ids: tuple[str, ...],
) -> int:
    return sum(_count_workflow_citations(conn, run_id) for run_id in run_ids)


def _loads_dict(value: str | None) -> dict[str, Any]:
    if not value:
        return {}
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _objective_metadata(payload: dict[str, Any]) -> dict[str, Any]:
    nested = payload.get("metadata")
    return nested if isinstance(nested, dict) else payload
