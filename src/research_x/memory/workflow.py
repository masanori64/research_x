from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from research_x.memory.answer import MemoryAnswer, build_memory_answer
from research_x.memory.context import ContextBundle, build_context_bundle
from research_x.memory.query import QueryPlan, build_query_plan
from research_x.memory.schema import ensure_memory_schema

WORKFLOW_VERSION = "memory-workflow-v1"
ANSWER_PROVIDER_NONE = "none"
STOP_ENOUGH_EVIDENCE = "enough_evidence"
STOP_NO_LOCAL_EVIDENCE = "no_local_evidence"
STOP_EXTERNAL_CONTEXT_NEEDED = "external_context_needed"
STOP_NEEDS_USER_REVIEW = "needs_user_review"
STOP_BUDGET_EXHAUSTED = "budget_exhausted"
STOP_PROVIDER_ERROR = "provider_error"


@dataclass(frozen=True)
class WorkflowRoute:
    route: str
    reasons: tuple[str, ...]
    recommended_doc_types: tuple[str, ...]
    wants_external_context: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "route": self.route,
            "reasons": list(self.reasons),
            "recommended_doc_types": list(self.recommended_doc_types),
            "wants_external_context": self.wants_external_context,
        }


@dataclass(frozen=True)
class WorkflowStep:
    step_id: str
    workflow_id: str
    step_index: int
    action: str
    input: dict[str, Any]
    output: dict[str, Any] | None
    status: str
    error: str | None
    created_at: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "step_id": self.step_id,
            "workflow_id": self.workflow_id,
            "step_index": self.step_index,
            "action": self.action,
            "input": self.input,
            "output": self.output,
            "status": self.status,
            "error": self.error,
            "created_at": self.created_at,
        }


@dataclass(frozen=True)
class MemoryWorkflow:
    workflow_id: str
    query: str
    route: str
    status: str
    stop_reason: str
    started_at: str
    finished_at: str
    metadata: dict[str, Any]
    steps: tuple[WorkflowStep, ...]
    context_bundle: ContextBundle | None
    answer: MemoryAnswer | None

    def as_dict(self) -> dict[str, Any]:
        return {
            "workflow_id": self.workflow_id,
            "query": self.query,
            "route": self.route,
            "status": self.status,
            "stop_reason": self.stop_reason,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "metadata": self.metadata,
            "steps": [step.as_dict() for step in self.steps],
            "context_bundle": (
                self.context_bundle.as_dict() if self.context_bundle is not None else None
            ),
            "answer": self.answer.as_dict() if self.answer is not None else None,
        }


def run_memory_workflow(
    db_path: str | Path,
    query: str,
    *,
    route: str = "auto",
    limit: int = 5,
    doc_type: str | None = None,
    account: str | None = None,
    semantic_provider: str | None = None,
    semantic_model: str | None = None,
    semantic_dimensions: int | None = None,
    semantic_api_key_env: str | None = None,
    semantic_base_url: str | None = None,
    semantic_weight: float = 3.0,
    semantic_candidates: int = 80,
    external_run_id: str | None = None,
    external_reader_provider: str = "http",
    external_limit: int = 5,
    external_max_chars: int = 4000,
    external_timeout_seconds: float = 30.0,
    external_user_agent: str = "research-x/0.1",
    external_max_bytes: int = 2_000_000,
    answer_provider: str = ANSWER_PROVIDER_NONE,
    answer_model: str | None = None,
    answer_api_key_env: str | None = None,
    answer_base_url: str | None = None,
    answer_timeout_seconds: float = 90.0,
    prompt_version: str = "memory-answer-v1",
    max_context_chunks: int = 8,
    max_context_chars: int = 12_000,
    max_steps: int = 4,
    store: bool = True,
) -> MemoryWorkflow:
    path = Path(db_path)
    if not path.exists():
        raise FileNotFoundError(f"database not found: {path}")

    started_at = _utc_now()
    query_plan = build_query_plan(query)
    route_plan = plan_workflow_route(query_plan, requested_route=route)
    workflow_id = _workflow_id(query, route_plan.route, started_at)
    steps: list[WorkflowStep] = []
    context_bundle: ContextBundle | None = None
    answer: MemoryAnswer | None = None

    metadata = {
        "workflow_version": WORKFLOW_VERSION,
        "query_plan": query_plan.as_dict(),
        "route_plan": route_plan.as_dict(),
        "parameters": {
            "limit": max(1, limit),
            "doc_type": doc_type,
            "account": account,
            "semantic_provider": semantic_provider,
            "semantic_model": semantic_model,
            "semantic_dimensions": semantic_dimensions,
            "semantic_api_key_env": semantic_api_key_env,
            "semantic_base_url": semantic_base_url,
            "semantic_weight": semantic_weight,
            "semantic_candidates": semantic_candidates,
            "external_run_id": external_run_id,
            "external_reader_provider": external_reader_provider,
            "external_limit": external_limit,
            "answer_provider": answer_provider,
            "answer_model": answer_model,
            "max_context_chunks": max_context_chunks,
            "max_context_chars": max_context_chars,
            "max_steps": max(1, max_steps),
        },
    }
    if store:
        _insert_workflow_run(
            path,
            workflow_id=workflow_id,
            query=query,
            route=route_plan.route,
            status="running",
            stop_reason=None,
            started_at=started_at,
            finished_at=None,
            metadata=metadata,
        )

    def add_step(
        action: str,
        input_payload: dict[str, Any],
        output_payload: dict[str, Any] | None,
        *,
        status: str = "ok",
        error: str | None = None,
    ) -> None:
        step = _workflow_step(
            workflow_id=workflow_id,
            step_index=len(steps),
            action=action,
            input_payload=input_payload,
            output_payload=output_payload,
            status=status,
            error=error,
        )
        steps.append(step)
        if store:
            _store_workflow_step(path, step)

    add_step(
        "plan",
        {"query": query, "requested_route": route},
        {
            "route": route_plan.route,
            "query_plan": query_plan.as_dict(),
            "recommended_doc_types": list(route_plan.recommended_doc_types),
            "wants_external_context": route_plan.wants_external_context,
        },
    )

    if len(steps) >= max(1, max_steps):
        return _finish_workflow(
            path,
            workflow_id=workflow_id,
            query=query,
            route=route_plan.route,
            status="needs_review",
            stop_reason=STOP_BUDGET_EXHAUSTED,
            started_at=started_at,
            metadata=metadata,
            steps=steps,
            context_bundle=context_bundle,
            answer=answer,
            store=store,
        )

    wants_answer = answer_provider.strip().lower() != ANSWER_PROVIDER_NONE
    if wants_answer and len(steps) + 2 <= max(1, max_steps):
        try:
            answer = build_memory_answer(
                path,
                query,
                limit=limit,
                doc_type=doc_type,
                account=account,
                semantic_provider=semantic_provider,
                semantic_model=semantic_model,
                semantic_dimensions=semantic_dimensions,
                semantic_api_key_env=semantic_api_key_env,
                semantic_base_url=semantic_base_url,
                semantic_weight=semantic_weight,
                semantic_candidates=semantic_candidates,
                external_run_id=external_run_id,
                external_reader_provider=external_reader_provider,
                external_limit=external_limit,
                external_max_chars=external_max_chars,
                external_timeout_seconds=external_timeout_seconds,
                external_user_agent=external_user_agent,
                external_max_bytes=external_max_bytes,
                answer_provider=answer_provider,
                answer_model=answer_model,
                answer_api_key_env=answer_api_key_env,
                answer_base_url=answer_base_url,
                answer_timeout_seconds=answer_timeout_seconds,
                prompt_version=prompt_version,
                max_context_chunks=max_context_chunks,
                max_context_chars=max_context_chars,
                workflow_id=workflow_id,
                store=store,
            )
        except (FileNotFoundError, RuntimeError, ValueError) as exc:
            add_step(
                "answer",
                {"answer_provider": answer_provider, "model": answer_model},
                None,
                status="error",
                error=_compact_error(str(exc)),
            )
            return _finish_workflow(
                path,
                workflow_id=workflow_id,
                query=query,
                route=route_plan.route,
                status="error",
                stop_reason=STOP_PROVIDER_ERROR,
                started_at=started_at,
                metadata=metadata,
                steps=steps,
                context_bundle=context_bundle,
                answer=answer,
                store=store,
            )
        context_bundle = answer.context_bundle
        add_step(
            "context",
            {"query": query, "limit": limit, "external_run_id": external_run_id},
            _context_summary(context_bundle),
            status="ok" if context_bundle.context_chunks else "needs_review",
        )
        add_step(
            "answer",
            {"answer_provider": answer_provider, "model": answer.model},
            {
                "answer_id": answer.answer_id,
                "status": answer.status,
                "citation_count": len(answer.citation_annotations),
                "selected_chunk_count": len(answer.selected_context_chunks),
            },
            status=answer.status,
        )
    else:
        try:
            context_bundle = build_context_bundle(
                path,
                query,
                limit=limit,
                doc_type=doc_type,
                account=account,
                semantic_provider=semantic_provider,
                semantic_model=semantic_model,
                semantic_dimensions=semantic_dimensions,
                semantic_api_key_env=semantic_api_key_env,
                semantic_base_url=semantic_base_url,
                semantic_weight=semantic_weight,
                semantic_candidates=semantic_candidates,
                external_run_id=external_run_id,
                external_reader_provider=external_reader_provider,
                external_limit=external_limit,
                external_max_chars=external_max_chars,
                external_timeout_seconds=external_timeout_seconds,
                external_user_agent=external_user_agent,
                external_max_bytes=external_max_bytes,
                store=store,
            )
        except (FileNotFoundError, RuntimeError, ValueError) as exc:
            add_step(
                "context",
                {"query": query, "limit": limit, "external_run_id": external_run_id},
                None,
                status="error",
                error=_compact_error(str(exc)),
            )
            return _finish_workflow(
                path,
                workflow_id=workflow_id,
                query=query,
                route=route_plan.route,
                status="error",
                stop_reason=STOP_PROVIDER_ERROR,
                started_at=started_at,
                metadata=metadata,
                steps=steps,
                context_bundle=context_bundle,
                answer=answer,
                store=store,
            )
        add_step(
            "context",
            {"query": query, "limit": limit, "external_run_id": external_run_id},
            _context_summary(context_bundle),
            status="ok" if context_bundle.context_chunks else "needs_review",
        )

    stop_reason = _stop_reason(
        context_bundle=context_bundle,
        answer=answer,
        route_plan=route_plan,
        external_run_id=external_run_id,
        wants_answer=wants_answer,
        step_count=len(steps),
        max_steps=max(1, max_steps),
    )
    status = "ok" if stop_reason == STOP_ENOUGH_EVIDENCE else "needs_review"
    return _finish_workflow(
        path,
        workflow_id=workflow_id,
        query=query,
        route=route_plan.route,
        status=status,
        stop_reason=stop_reason,
        started_at=started_at,
        metadata=metadata,
        steps=steps,
        context_bundle=context_bundle,
        answer=answer,
        store=store,
    )


def plan_workflow_route(plan: QueryPlan, *, requested_route: str = "auto") -> WorkflowRoute:
    requested = requested_route.strip().lower()
    if requested != "auto":
        if requested not in _ROUTE_DOC_TYPES:
            raise ValueError(f"unknown workflow route: {requested_route}")
        return WorkflowRoute(
            route=requested,
            reasons=("explicit_route",),
            recommended_doc_types=_ROUTE_DOC_TYPES[requested],
            wants_external_context=requested == "current_fact_check",
        )
    intents = set(plan.intents)
    if "food" in intents:
        return _route("place_recall", "food_intent")
    if "finance" in intents:
        return _route("company_event", "finance_intent")
    if plan.author_terms or "author" in intents:
        return _route("author_stance", "author_intent")
    if "quote_context" in intents:
        return _route("quote_context", "quote_intent")
    if "adult_comic" in intents:
        return _route("adult_comic", "adult_comic_intent")
    if "media" in intents:
        return _route("media_context", "media_intent")
    if "cross_account" in intents:
        return _route("cross_account", "cross_account_intent")
    if _looks_like_current_fact_check(plan):
        return _route("current_fact_check", "freshness_or_current_fact_check")
    if "event" in intents:
        return _route("event_recall", "event_intent")
    if intents.intersection({"technology", "science"}):
        return _route("learning_map", "learning_or_research_intent")
    if _looks_like_broad_topic_map(plan):
        return _route("learning_map", "broad_topic_map")
    return _route("local_memory_search", "default_local_search")


def workflow_json(workflow: MemoryWorkflow) -> str:
    return json.dumps(workflow.as_dict(), ensure_ascii=False, indent=2, sort_keys=True)


def format_workflow(workflow: MemoryWorkflow) -> str:
    lines = [
        (
            f"workflow: {workflow.workflow_id} status={workflow.status} "
            f"route={workflow.route} stop={workflow.stop_reason}"
        )
    ]
    for step in workflow.steps:
        suffix = f" error={step.error}" if step.error else ""
        lines.append(f"step {step.step_index}: {step.action} status={step.status}{suffix}")
    if workflow.context_bundle is not None:
        lines.append(
            "context: "
            f"run={workflow.context_bundle.run_id} "
            f"chunks={len(workflow.context_bundle.context_chunks)} "
            f"hits={len(workflow.context_bundle.retrieved_hits)}"
        )
    if workflow.answer is not None:
        lines.append(
            "answer: "
            f"id={workflow.answer.answer_id} status={workflow.answer.status} "
            f"citations={len(workflow.answer.citation_annotations)}"
        )
    return "\n".join(lines)


_ROUTE_DOC_TYPES: dict[str, tuple[str, ...]] = {
    "place_recall": ("place_card", "bookmark_doc", "media_doc"),
    "company_event": ("ticker_event", "author_profile", "bookmark_doc", "tweet_doc"),
    "author_stance": ("author_profile", "bookmark_doc", "tweet_doc", "quote_tree_doc"),
    "learning_map": ("bookmark_doc", "tweet_doc", "media_doc", "quote_tree_doc"),
    "current_fact_check": ("bookmark_doc", "tweet_doc", "ticker_event"),
    "quote_context": ("quote_tree_doc", "bookmark_doc"),
    "adult_comic": ("bookmark_doc", "media_doc"),
    "media_context": ("media_doc", "bookmark_doc"),
    "event_recall": ("bookmark_doc", "tweet_doc", "ticker_event"),
    "cross_account": ("bookmark_doc", "tweet_doc"),
    "local_memory_search": ("bookmark_doc", "tweet_doc", "place_card", "author_profile"),
}


def _route(route: str, reason: str) -> WorkflowRoute:
    return WorkflowRoute(
        route=route,
        reasons=(reason,),
        recommended_doc_types=_ROUTE_DOC_TYPES[route],
        wants_external_context=route == "current_fact_check",
    )


def _looks_like_current_fact_check(plan: QueryPlan) -> bool:
    text = plan.normalized_query.casefold()
    current_terms = (
        "今も",
        "現在",
        "正しい",
        "最新",
        "古くな",
        "obsolete",
        "事実確認",
        "ファクトチェック",
    )
    return any(term.casefold() in text for term in current_terms)


def _looks_like_broad_topic_map(plan: QueryPlan) -> bool:
    text = plan.normalized_query.casefold()
    return any(term.casefold() in text for term in ("関心領域", "db 全体", "db全体", "全体"))


def _stop_reason(
    *,
    context_bundle: ContextBundle | None,
    answer: MemoryAnswer | None,
    route_plan: WorkflowRoute,
    external_run_id: str | None,
    wants_answer: bool,
    step_count: int,
    max_steps: int,
) -> str:
    if step_count >= max_steps and wants_answer and answer is None:
        return STOP_BUDGET_EXHAUSTED
    if context_bundle is None or not context_bundle.context_chunks:
        return STOP_NO_LOCAL_EVIDENCE
    if route_plan.wants_external_context and not external_run_id:
        return STOP_EXTERNAL_CONTEXT_NEEDED
    if answer is not None and answer.status != "ok":
        return STOP_NEEDS_USER_REVIEW
    return STOP_ENOUGH_EVIDENCE


def _context_summary(bundle: ContextBundle) -> dict[str, Any]:
    return {
        "context_run_id": bundle.run_id,
        "hit_count": len(bundle.retrieved_hits),
        "chunk_count": len(bundle.context_chunks),
        "citation_count": len(bundle.citation_annotations),
        "source_kinds": sorted(
            {
                str(chunk.metadata.get("evidence_source_kind") or chunk.source_kind)
                for chunk in bundle.context_chunks
            }
        ),
        "top_doc_ids": [str(hit.get("doc_id")) for hit in bundle.retrieved_hits[:5]],
    }


def _finish_workflow(
    db_path: Path,
    *,
    workflow_id: str,
    query: str,
    route: str,
    status: str,
    stop_reason: str,
    started_at: str,
    metadata: dict[str, Any],
    steps: list[WorkflowStep],
    context_bundle: ContextBundle | None,
    answer: MemoryAnswer | None,
    store: bool,
) -> MemoryWorkflow:
    finished_at = _utc_now()
    if store:
        _insert_workflow_run(
            db_path,
            workflow_id=workflow_id,
            query=query,
            route=route,
            status=status,
            stop_reason=stop_reason,
            started_at=started_at,
            finished_at=finished_at,
            metadata=metadata,
        )
    return MemoryWorkflow(
        workflow_id=workflow_id,
        query=query,
        route=route,
        status=status,
        stop_reason=stop_reason,
        started_at=started_at,
        finished_at=finished_at,
        metadata=metadata,
        steps=tuple(steps),
        context_bundle=context_bundle,
        answer=answer,
    )


def _insert_workflow_run(
    db_path: Path,
    *,
    workflow_id: str,
    query: str,
    route: str,
    status: str,
    stop_reason: str | None,
    started_at: str,
    finished_at: str | None,
    metadata: dict[str, Any],
) -> None:
    with sqlite3.connect(db_path, timeout=60) as conn:
        ensure_memory_schema(conn)
        conn.execute(
            """
            INSERT INTO memory_workflow_runs (
                workflow_id, query, route, status, stop_reason,
                started_at, finished_at, metadata_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(workflow_id) DO UPDATE SET
                status=excluded.status,
                stop_reason=excluded.stop_reason,
                finished_at=excluded.finished_at,
                metadata_json=excluded.metadata_json
            """,
            (
                workflow_id,
                query,
                route,
                status,
                stop_reason,
                started_at,
                finished_at,
                json.dumps(metadata, ensure_ascii=False, sort_keys=True),
            ),
        )


def _store_workflow_step(db_path: Path, step: WorkflowStep) -> None:
    with sqlite3.connect(db_path, timeout=60) as conn:
        ensure_memory_schema(conn)
        conn.execute(
            """
            INSERT INTO memory_workflow_steps (
                step_id, workflow_id, step_index, action, input_json,
                output_json, status, error, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(step_id) DO UPDATE SET
                output_json=excluded.output_json,
                status=excluded.status,
                error=excluded.error
            """,
            (
                step.step_id,
                step.workflow_id,
                step.step_index,
                step.action,
                json.dumps(step.input, ensure_ascii=False, sort_keys=True),
                json.dumps(step.output, ensure_ascii=False, sort_keys=True)
                if step.output is not None
                else None,
                step.status,
                step.error,
                step.created_at,
            ),
        )


def _workflow_step(
    *,
    workflow_id: str,
    step_index: int,
    action: str,
    input_payload: dict[str, Any],
    output_payload: dict[str, Any] | None,
    status: str,
    error: str | None,
) -> WorkflowStep:
    created_at = _utc_now()
    step_id = _hash_id("workflow-step", workflow_id, str(step_index), action, created_at)
    return WorkflowStep(
        step_id=step_id,
        workflow_id=workflow_id,
        step_index=step_index,
        action=action,
        input=input_payload,
        output=output_payload,
        status=status,
        error=error,
        created_at=created_at,
    )


def _workflow_id(query: str, route: str, started_at: str) -> str:
    return _hash_id("workflow", query, route, started_at)


def _hash_id(prefix: str, *parts: str) -> str:
    digest = hashlib.sha256("\0".join(parts).encode("utf-8")).hexdigest()[:20]
    return f"{prefix}:{digest}"


def _compact_error(value: str, *, limit: int = 500) -> str:
    text = " ".join(value.split())
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 3)].rstrip() + "..."


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()
