from __future__ import annotations

import argparse
import contextlib
import json
import sys
from pathlib import Path
from typing import Any

from research_x.accounts import resolve_account_paths, write_account_profile
from research_x.adapters import catalog_entries, known_adapter_ids
from research_x.bookmarks import run_bookmark_job
from research_x.config import load_config
from research_x.contracts import OutcomeStatus
from research_x.label_existing import LABEL_EXISTING_KINDS, label_existing_items
from research_x.pipeline import run_pipeline
from research_x.playwright_auth import (
    capture_playwright_storage_state,
    capture_storage_state_auto,
    capture_storage_state_from_cdp,
    capture_storage_state_from_system_browser_profile,
    capture_storage_state_with_credentials,
    capture_storage_state_with_system_browser_credentials,
    write_storage_state_from_cookie_env,
)
from research_x.runner import run_experiment
from research_x.tweets import run_tweet_job, run_tweet_stage_job

MEMORY_EMBEDDING_PROVIDER_CHOICES = [
    "auto",
    "local_hash",
    "openai",
    "gemini",
    "voyage",
    "cohere",
    "mistral",
    "jina",
    "openai_compatible",
]
MEMORY_EMBEDDING_PROVIDER_OR_LATEST_CHOICES = [
    "latest",
    *MEMORY_EMBEDDING_PROVIDER_CHOICES,
]
MEMORY_EMBEDDING_EXECUTION_STAGE_CHOICES = [
    "auto",
    "technical-canary",
    "eval-slice",
    "production-scope",
]
MEMORY_EMBEDDING_SELECTION_POLICY_CHOICES = [
    "auto",
    "sequential",
    "doc-type-round-robin",
]
MEMORY_REAL_API_ESTIMATE_SELECTION_POLICY_CHOICES = [
    *MEMORY_EMBEDDING_SELECTION_POLICY_CHOICES,
    "representative",
    "all-eligible",
]
MEMORY_SEMANTIC_BACKEND_CHOICES = ["sqlite", "projection"]
MEMORY_SEARCH_ROUTE_CHOICES = [
    "auto",
    "general_semantic",
    "japanese_or_crosslingual",
    "technical_or_code",
    "relation_heavy",
    "media_content",
    "time_sensitive",
    "external_needed",
    "exact_identifier",
    "account_specific",
    "conflict_sensitive",
]
MEMORY_VECTOR_PROJECTION_BACKEND_CHOICES = ["numpy", "turbovec"]
MEMORY_VECTOR_BENCHMARK_BACKEND_CHOICES = ["numpy", "turbovec", "zvec"]
MEMORY_VECTOR_BENCHMARK_PROVIDER_CHOICES = ["local_hash"]
MEMORY_AUDIT_READINESS_SCOPE_CHOICES = ["provider-production", "local-no-provider"]
DEFAULT_FINAL_SKELETON_PREFLIGHT_QUERY = "final skeleton preflight"
MEDIA_DOWNLOAD_POLICY_CHOICES = [
    "no_media_download",
    "metadata_only",
    "thumbnails_only",
    "full_media_allowed",
]


def _add_api_budget_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--api-budget-policy",
        default="default",
        help="API budget policy id used for future provider calls",
    )
    parser.add_argument(
        "--api-run-id",
        default=None,
        help="run id used to group API usage ledger events",
    )
    parser.add_argument(
        "--max-run-usd",
        type=float,
        default=None,
        help="temporary run-level USD cap override for this command",
    )
    parser.add_argument(
        "--allow-unpriced-api",
        action="store_true",
        help="allow provider calls without a local price row only under scoped provider policy",
    )
    parser.add_argument(
        "--provider-authorization-id",
        default=None,
        help="saved ProviderExecutionPolicy authorization id to load from the API budget DB",
    )
    parser.add_argument(
        "--provider-execution-policy-id",
        default=None,
        help="saved ProviderExecutionPolicy id to load from the API budget DB",
    )


def _add_provider_quota_gate_option(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--allow-provider-quota",
        action="store_true",
        help=(
            "allow provider/quota execution only with scoped approval, ProviderExecutionPolicy, "
            "and API Budget Guard"
        ),
    )
    _add_provider_quota_approval_options(parser)


def _add_provider_quota_approval_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--provider-quota-approval-id",
        default=None,
        help="scoped provider quota approval id used with real provider execution flags",
    )
    parser.add_argument(
        "--provider-quota-provider",
        default=None,
        help="provider covered by the scoped approval object",
    )
    parser.add_argument(
        "--provider-quota-model",
        default=None,
        help="model covered by the scoped approval object",
    )
    parser.add_argument(
        "--provider-quota-operation",
        default=None,
        help="operation covered by the scoped approval object",
    )
    parser.add_argument(
        "--provider-quota-max-calls",
        type=int,
        default=None,
        help="maximum provider call count covered by the approval object",
    )
    parser.add_argument(
        "--provider-quota-max-cost-usd",
        type=float,
        default=None,
        help="maximum estimated USD cost covered by the approval object",
    )
    parser.add_argument(
        "--provider-quota-price-source",
        default=None,
        help="price source reviewed for the approval object",
    )
    parser.add_argument(
        "--provider-quota-approved-scope",
        default=None,
        help="scope covered by the approval object, or *",
    )
    parser.add_argument(
        "--provider-quota-approved-at",
        default=None,
        help="ISO-8601 approval timestamp with timezone",
    )
    parser.add_argument("--provider-quota-approved-by", default=None)
    parser.add_argument("--provider-quota-expires-at", default=None)


def _add_context_budget_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--context-budget-max-chars",
        type=int,
        default=None,
        help="maximum JSON payload chars before context chunk text is offloaded",
    )
    parser.add_argument(
        "--context-budget-chunk-chars",
        type=int,
        default=None,
        help="maximum inline chars for each context chunk text",
    )
    parser.add_argument(
        "--context-budget-preview-chars",
        type=int,
        default=None,
        help="preview chars kept inline for offloaded context chunk text",
    )
    parser.add_argument(
        "--context-offload-dir",
        type=Path,
        default=None,
        help="directory for local context offload pointer artifacts",
    )


def _api_budget_for_args(args: argparse.Namespace):
    if not hasattr(args, "api_budget_policy"):
        return contextlib.nullcontext()
    db_path = getattr(args, "db", None) or "runs/x_data.sqlite3"
    from research_x.memory.api_budget import api_budget_context

    provider_execution_policy = _provider_execution_policy_payload_for_args(args, db_path)
    provider_quota_approval = _provider_quota_approval_payload_for_args(
        args,
        require_when_allowed=provider_execution_policy is None,
    )
    provider_quota_current_scope = _provider_quota_current_scope_for_args(args)
    metadata = {
        "cli_command": getattr(args, "command", None),
        "memory_command": getattr(args, "memory_command", None),
    }
    if provider_quota_approval:
        metadata["provider_quota_approval_id"] = provider_quota_approval.get(
            "provider_quota_approval_id"
        )
    if provider_execution_policy:
        metadata["provider_authorization_id"] = provider_execution_policy.get("authorization_id")
        metadata["provider_execution_policy_id"] = provider_execution_policy.get("policy_id")
    return api_budget_context(
        db_path=db_path,
        policy_id=args.api_budget_policy,
        run_id=args.api_run_id,
        max_run_usd_override=args.max_run_usd,
        allow_unpriced_api=args.allow_unpriced_api,
        metadata=metadata,
        provider_quota_approval=provider_quota_approval,
        provider_execution_policy=provider_execution_policy,
        provider_quota_current_scope=provider_quota_current_scope,
    )


def _provider_execution_policy_payload_for_args(
    args: argparse.Namespace,
    db_path: str | Path,
) -> dict[str, Any] | None:
    authorization_id = getattr(args, "provider_authorization_id", None)
    execution_policy_id = getattr(args, "provider_execution_policy_id", None)
    if not authorization_id and not execution_policy_id:
        return None
    from research_x.memory.api_budget import (
        load_provider_execution_policy,
        provider_execution_policy_as_dict,
    )

    policy = load_provider_execution_policy(
        db_path,
        authorization_id=authorization_id,
        policy_id=execution_policy_id,
    )
    return provider_execution_policy_as_dict(policy)


def _provider_quota_approval_payload_for_args(
    args: argparse.Namespace,
    *,
    require_when_allowed: bool = False,
) -> dict[str, Any] | None:
    payload = {
        "provider_quota_approval_id": getattr(args, "provider_quota_approval_id", None),
        "provider": getattr(args, "provider_quota_provider", None),
        "model": getattr(args, "provider_quota_model", None),
        "operation": getattr(args, "provider_quota_operation", None),
        "max_calls": getattr(args, "provider_quota_max_calls", None),
        "max_cost_usd": getattr(args, "provider_quota_max_cost_usd", None),
        "price_source": getattr(args, "provider_quota_price_source", None),
        "approved_scope": getattr(args, "provider_quota_approved_scope", None),
        "approved_at": getattr(args, "provider_quota_approved_at", None),
        "approved_by": getattr(args, "provider_quota_approved_by", None),
        "expires_at": getattr(args, "provider_quota_expires_at", None),
    }
    if any(value not in (None, "") for value in payload.values()):
        return payload
    if require_when_allowed and bool(getattr(args, "allow_provider_quota", False)):
        return payload
    return None


def _provider_quota_current_scope_for_args(args: argparse.Namespace) -> str | None:
    if getattr(args, "memory_command", None):
        return f"memory:{args.memory_command}"
    return getattr(args, "command", None)


def _provider_quota_units_for_args(args: argparse.Namespace) -> dict[str, int | float]:
    calls = getattr(args, "calls", None) or getattr(args, "limit", None) or 1
    return {
        "calls": calls,
        "input_tokens": getattr(args, "input_tokens", 0),
        "output_tokens": getattr(args, "output_tokens", 0),
        "media_bytes": getattr(args, "media_bytes", 0),
        "documents": getattr(args, "documents", 0),
        "pages": getattr(args, "pages", 0),
    }


def _print_cli_payload(payload: Any, *, json_output: bool) -> None:
    if json_output:
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
        return
    if isinstance(payload, list):
        for item in payload:
            print(json.dumps(item, ensure_ascii=False, sort_keys=True))
        return
    if isinstance(payload, dict):
        for key, value in payload.items():
            if isinstance(value, (dict, list, tuple)):
                formatted = json.dumps(value, ensure_ascii=False, sort_keys=True)
            else:
                formatted = value
            print(f"{key}: {formatted}")
        return
    print(payload)


def _select_knowledge_rows(
    db_path: str,
    query: str,
    params: tuple[Any, ...] = (),
) -> list[dict[str, Any]]:
    import sqlite3

    from research_x.memory.schema import ensure_memory_schema

    with sqlite3.connect(db_path, timeout=60) as conn:
        conn.row_factory = sqlite3.Row
        ensure_memory_schema(conn)
        rows = conn.execute(query, params).fetchall()
    return [dict(row) for row in rows]


def _knowledgeops_status(db_path: str) -> dict[str, Any]:
    import sqlite3

    from research_x.memory.schema import ensure_memory_schema

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


def _artifact_registry_validation(db_path: str) -> dict[str, Any]:
    rows = _select_knowledge_rows(
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
            issues.append(
                {"artifact_id": row["artifact_id"], "issue": "missing_source_refs_json"}
            )
    return {
        "status": "ok" if not issues else "needs_review",
        "artifacts": len(rows),
        "issues": issues,
    }


def _projection_lifecycle_payload(
    db_path: str,
    *,
    command: str,
    projection_id: str | None,
    mode: str = "incremental",
    projection_kind: str | None = None,
    builder_params: dict[str, Any] | None = None,
) -> dict[str, Any] | list[dict[str, Any]]:
    from research_x.memory.projection_lifecycle import (
        build_projection_lifecycle,
        plan_projection_lifecycle,
        projection_lifecycle_coverage,
        projection_lifecycle_rows,
    )

    if command == "plan":
        return plan_projection_lifecycle(
            db_path,
            projection_kind=projection_kind,
        ).as_dict()
    if command == "build":
        return build_projection_lifecycle(
            db_path,
            mode=mode,
            projection_kind=projection_kind,
            builder_params=builder_params,
        ).as_dict()
    if command == "coverage":
        return projection_lifecycle_coverage(db_path).as_dict()
    if command == "show":
        rows = projection_lifecycle_rows(db_path, projection_id=projection_id)
        if projection_id:
            return rows[0] if rows else {}
        return list(rows)
    raise AssertionError(f"unhandled projections command {command}")


def _participation_payload(
    db_path: str,
    *,
    source_ref: str | None,
    artifact_id: str | None,
    output_mode: str,
) -> dict[str, Any]:
    if not source_ref and not artifact_id:
        raise ValueError("source_ref or artifact_id is required")
    if source_ref:
        rows = _select_knowledge_rows(
            db_path,
            """
            SELECT *
            FROM memory_participation_decisions
            WHERE source_ref = ? AND output_mode = ?
            """,
            (source_ref, output_mode),
        )
    else:
        rows = _select_knowledge_rows(
            db_path,
            """
            SELECT *
            FROM memory_participation_decisions
            WHERE artifact_id = ? AND output_mode = ?
            """,
            (artifact_id, output_mode),
        )
    return rows[0] if rows else {"status": "missing_decision"}


def _reconciliation_show_payload(db_path: str, *, run_id: str) -> dict[str, Any]:
    run_rows = _select_knowledge_rows(
        db_path,
        "SELECT * FROM memory_reconciliation_runs WHERE reconciliation_run_id = ?",
        (run_id,),
    )
    item_rows = _select_knowledge_rows(
        db_path,
        """
        SELECT *
        FROM memory_reconciliation_items
        WHERE reconciliation_run_id = ?
        ORDER BY created_at, reconciliation_item_id
        """,
        (run_id,),
    )
    return {
        "status": "ok" if run_rows else "missing_run",
        "run": run_rows[0] if run_rows else None,
        "items": item_rows,
    }


def _knowledge_cleanup_orphans_payload(
    db_path: str,
    *,
    dry_run: bool,
) -> dict[str, Any]:
    import sqlite3

    from research_x.memory.schema import ensure_memory_schema

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
                """
                UPDATE memory_artifacts
                SET artifact_status = 'orphaned'
                WHERE artifact_id = ?
                """,
                [(artifact_id,) for artifact_id in orphans],
            )
    return {
        "status": "dry_run" if dry_run else "updated",
        "orphan_candidates": orphans,
        "orphan_count": len(orphans),
        "destructive_delete": False,
    }


def _audit_latest_payload(db_path: str) -> dict[str, Any]:
    rows = _select_knowledge_rows(
        db_path,
        """
        SELECT *
        FROM memory_audit_events
        ORDER BY created_at DESC, event_id DESC
        LIMIT 1
        """,
    )
    return rows[0] if rows else {"status": "no_events"}


def _parse_float_mapping(values: list[str]) -> dict[str, float]:
    parsed: dict[str, float] = {}
    for value in values:
        if "=" not in value:
            raise ValueError(f"expected key=value: {value}")
        key, raw_number = value.split("=", 1)
        parsed[key] = float(raw_number)
    return parsed


def _eval_v2_report_payload(db_path: str, *, run_id: str) -> dict[str, Any]:
    import sqlite3

    from research_x.memory.schema import ensure_memory_schema

    with sqlite3.connect(db_path, timeout=60) as conn:
        conn.row_factory = sqlite3.Row
        ensure_memory_schema(conn)
        run = conn.execute(
            "SELECT * FROM memory_eval_runs WHERE run_id = ?",
            (run_id,),
        ).fetchone()
        results = conn.execute(
            """
            SELECT *
            FROM memory_eval_results
            WHERE run_id = ?
            ORDER BY case_index
            """,
            (run_id,),
        ).fetchall()
    if run is None:
        return {
            "status": "missing_run",
            "run_id": run_id,
            "output_mode": "eval_v2_report",
        }
    return {
        "status": "ok",
        "run": dict(run),
        "results": [dict(result) for result in results],
        "output_mode": "eval_v2_report",
    }


def _eval_v2_compare_payload(
    db_path: str,
    *,
    baseline: str,
    candidate: str,
) -> dict[str, Any]:
    baseline_report = _eval_v2_report_payload(db_path, run_id=baseline)
    candidate_report = _eval_v2_report_payload(db_path, run_id=candidate)
    baseline_results = baseline_report.get("results") or []
    candidate_results = candidate_report.get("results") or []
    return {
        "status": (
            "ok"
            if baseline_report["status"] == "ok"
            and candidate_report["status"] == "ok"
            else "missing_run"
        ),
        "baseline": baseline,
        "candidate": candidate,
        "baseline_cases": len(baseline_results),
        "candidate_cases": len(candidate_results),
        "case_delta": len(candidate_results) - len(baseline_results),
        "missing": [
            run_id
            for run_id, report in (
                (baseline, baseline_report),
                (candidate, candidate_report),
            )
            if report["status"] != "ok"
        ],
        "output_mode": "eval_v2_compare",
    }


def main(argv: list[str] | None = None) -> int:
    _configure_stdio()
    parser = argparse.ArgumentParser(prog="research-x")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="run an acquisition experiment")
    run_parser.add_argument("--config", required=True, help="path to experiment TOML")
    run_parser.add_argument("--out", required=True, help="output directory")

    pipeline_parser = subparsers.add_parser(
        "pipeline",
        help="run the resilient acquisition pipeline",
    )
    pipeline_parser.add_argument("--config", required=True, help="path to pipeline TOML")
    pipeline_parser.add_argument("--out", required=True, help="output directory")
    pipeline_parser.add_argument(
        "--account",
        default=None,
        help="account id whose saved session should be used",
    )
    pipeline_parser.add_argument(
        "--storage-state",
        default=None,
        help="Playwright storage state used by the session broker",
    )
    pipeline_parser.add_argument(
        "--min-successful-providers",
        type=int,
        default=2,
        help="minimum successful providers before stopping a target chain",
    )

    db_show_parser = subparsers.add_parser(
        "db-show",
        help="print stored tweet/bookmark text from the SQLite database",
    )
    db_show_parser.add_argument("--db", default="runs/x_data.sqlite3", help="SQLite database path")
    db_show_parser.add_argument("--account", default=None, help="account id filter")
    db_show_parser.add_argument(
        "--kind",
        choices=["bookmarks", "tweets", "all"],
        default="bookmarks",
        help="stored row type to display",
    )
    db_show_parser.add_argument("--limit", type=int, default=20)
    db_show_parser.add_argument("--json", action="store_true", help="emit rows as JSON")
    db_backup_parser = subparsers.add_parser(
        "db-backup",
        help="create a timestamped local SQLite x_data backup with a manifest",
    )
    db_backup_parser.add_argument("--db", default="runs/x_data.sqlite3")
    db_backup_parser.add_argument("--backup-dir", default=None)
    db_backup_parser.add_argument("--label", default=None)
    db_backup_parser.add_argument("--json", action="store_true")
    db_rollback_parser = subparsers.add_parser(
        "db-rollback",
        help="restore a local SQLite x_data database from a named backup",
    )
    db_rollback_parser.add_argument("--db", default="runs/x_data.sqlite3")
    db_rollback_parser.add_argument("--backup-dir", default=None)
    db_rollback_parser.add_argument("--backup-id", required=True)
    db_rollback_parser.add_argument("--json", action="store_true")

    label_existing_parser = subparsers.add_parser(
        "label-existing",
        help="classify stored DB rows that do not yet have AI labels",
    )
    label_existing_parser.add_argument(
        "--db",
        default="runs/x_data.sqlite3",
        help="SQLite database path containing stored tweets/bookmarks",
    )
    label_existing_parser.add_argument(
        "--account",
        default=None,
        help="account id filter; omit to classify all accounts",
    )
    label_existing_parser.add_argument(
        "--kind",
        choices=LABEL_EXISTING_KINDS,
        default="bookmarks",
        help="stored rows to classify",
    )
    label_existing_parser.add_argument(
        "--limit",
        type=int,
        default=100,
        help="maximum unlabeled rows to classify in this run",
    )
    label_existing_parser.add_argument(
        "--all",
        action="store_true",
        help="classify all currently unlabeled rows",
    )
    label_existing_parser.add_argument(
        "--include-labeled",
        action="store_true",
        help="classify even rows that already have an AI label",
    )
    label_existing_parser.add_argument(
        "--out",
        default=None,
        help="optional output directory for classification JSONL/report files",
    )
    label_existing_parser.add_argument(
        "--model",
        default="gpt-4o-mini",
        help="model used for classification",
    )
    label_existing_parser.add_argument(
        "--classifier-provider",
        default="gemini",
        help=(
            "classifier provider: openai_responses, openai_compatible, "
            "qwen, kimi, glm, gemini, or openai_chat"
        ),
    )
    label_existing_parser.add_argument(
        "--api-base-url",
        default=None,
        help="OpenAI-compatible API base URL for non-Responses classifiers",
    )
    label_existing_parser.add_argument(
        "--api-key-env",
        default="GEMINI_API_KEY",
        help="environment variable containing the classifier API key",
    )
    label_existing_parser.add_argument(
        "--categories",
        default="examples/bookmark_categories.toml",
        help="optional TOML taxonomy with [[categories]] entries",
    )
    label_existing_parser.add_argument(
        "--batch-size",
        type=int,
        default=20,
        help="number of rows per AI classification request",
    )
    label_existing_parser.add_argument(
        "--retry-attempts",
        type=int,
        default=3,
        help="retry count for transient classifier API errors",
    )
    label_existing_parser.add_argument(
        "--retry-base-seconds",
        type=float,
        default=10.0,
        help="base wait seconds between transient classifier retries",
    )
    label_existing_parser.add_argument(
        "--request-timeout-seconds",
        type=float,
        default=120.0,
        help="timeout for each classifier request",
    )
    label_existing_parser.add_argument(
        "--reasoning-effort",
        default="low",
        help="Gemini/OpenAI-compatible reasoning effort: default, minimal, low, medium, or high",
    )
    label_existing_parser.add_argument(
        "--min-request-interval-seconds",
        type=float,
        default=0.0,
        help="minimum wait between classifier requests",
    )
    label_existing_parser.add_argument(
        "--stop-on-rate-limit",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="finish the job immediately when the classifier returns quota/rate-limit 429",
    )
    _add_api_budget_options(label_existing_parser)

    app_parser = subparsers.add_parser(
        "app",
        help="start a local browser app for account auth and collection",
    )
    app_parser.add_argument("--host", default="127.0.0.1")
    app_parser.add_argument("--port", type=int, default=8765)
    app_parser.add_argument(
        "--open-browser",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="open the app in the default browser",
    )

    notify_parser = subparsers.add_parser(
        "notify",
        help="play a local completion notification",
    )
    notify_parser.add_argument(
        "--message",
        default="作業が終了しました",
        help="message to speak when voice output is available",
    )
    notify_parser.add_argument(
        "--beep",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="play a short notification sound",
    )
    notify_parser.add_argument(
        "--voice",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="speak the message when the OS supports it",
    )
    notify_parser.add_argument(
        "--strict",
        action="store_true",
        help="return non-zero if no notification method succeeds",
    )

    adoption_parser = subparsers.add_parser(
        "adoption",
        help="audit source adoption boundaries for research_x and Codex foundation bridge",
    )
    adoption_subparsers = adoption_parser.add_subparsers(
        dest="adoption_command",
        required=True,
    )
    adoption_audit_parser = adoption_subparsers.add_parser(
        "audit",
        help="validate control/adoption_registry.toml",
    )
    adoption_audit_parser.add_argument(
        "--registry",
        type=Path,
        default=Path("control/adoption_registry.toml"),
    )
    adoption_audit_parser.add_argument("--json", action="store_true")

    project_control_parser = subparsers.add_parser(
        "project-control",
        help="inspect the current authority, state, conflicts, unknowns, and permission profile",
    )
    project_control_subparsers = project_control_parser.add_subparsers(
        dest="project_control_command",
        required=True,
    )
    for command_name in ("status", "validate"):
        command_parser = project_control_subparsers.add_parser(command_name)
        command_parser.add_argument("--project-root", type=Path, default=Path("."))
        command_parser.add_argument("--json", action="store_true")

    progress_parser = subparsers.add_parser(
        "progress",
        help="serve a live progress page for an output directory",
    )
    progress_parser.add_argument("--out", required=True, help="output directory to monitor")
    progress_parser.add_argument("--host", default="127.0.0.1")
    progress_parser.add_argument("--port", type=int, default=8766)
    progress_parser.add_argument(
        "--open-browser",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="open the progress page in the default browser",
    )

    test_diagnose_parser = subparsers.add_parser(
        "test-diagnose",
        help="run pytest in bounded units to identify slow or hanging tests",
    )
    test_diagnose_parser.add_argument(
        "targets",
        nargs="*",
        help="pytest target files or nodeids; default is tests",
    )
    test_diagnose_parser.add_argument(
        "--mode",
        choices=["files", "tests"],
        default="files",
        help="run each target as a file/unit, or collect and run each test nodeid separately",
    )
    test_diagnose_parser.add_argument(
        "--timeout-seconds",
        type=float,
        default=120.0,
        help="maximum seconds for each diagnostic pytest unit",
    )
    test_diagnose_parser.add_argument(
        "--collect-timeout-seconds",
        type=float,
        default=60.0,
        help="maximum seconds for pytest collection in --mode tests",
    )
    test_diagnose_parser.add_argument(
        "--pytest-arg",
        action="append",
        default=[],
        help="extra argument appended to each pytest unit; repeatable",
    )
    test_diagnose_parser.add_argument(
        "--max-output-chars",
        type=int,
        default=4000,
        help="stdout/stderr tail kept for each non-passing unit",
    )
    test_diagnose_parser.add_argument(
        "--stop-on-fail",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="stop after the first failed or timed-out unit",
    )
    test_diagnose_parser.add_argument("--json", action="store_true")

    presentation_parser = subparsers.add_parser(
        "presentation",
        help="validate local presentation facts and build inputs",
    )
    presentation_subparsers = presentation_parser.add_subparsers(
        dest="presentation_command",
        required=True,
    )
    presentation_validate_parser = presentation_subparsers.add_parser(
        "validate-facts",
        help="validate docs/presentation/project-facts.json",
    )
    presentation_validate_parser.add_argument(
        "--facts",
        type=Path,
        default=Path("docs/presentation/project-facts.json"),
        help="presentation facts JSON path",
    )
    presentation_validate_parser.add_argument("--json", action="store_true")
    presentation_slides_parser = presentation_subparsers.add_parser(
        "validate-slides",
        help="validate generated presentation source against project facts",
    )
    presentation_slides_parser.add_argument(
        "--facts",
        type=Path,
        default=Path("docs/presentation/project-facts.json"),
        help="presentation facts JSON path",
    )
    presentation_slides_parser.add_argument(
        "--slides",
        type=Path,
        default=Path("docs/presentation/deck.marp"),
        help="presentation generated slide source path",
    )
    presentation_slides_parser.add_argument(
        "--allow-missing-assets",
        action="store_true",
        help="allow diagram assets that have not been rendered yet",
    )
    presentation_slides_parser.add_argument("--json", action="store_true")

    memory_parser = subparsers.add_parser(
        "memory",
        help="build and query the local AI-callable memory search layer",
    )
    memory_subparsers = memory_parser.add_subparsers(dest="memory_command", required=True)
    memory_api_budget_parser = memory_subparsers.add_parser(
        "api-budget",
        help="inspect or change local API budget guard settings",
    )
    memory_api_budget_parser.add_argument("--db", default="runs/x_data.sqlite3")
    memory_api_budget_subparsers = memory_api_budget_parser.add_subparsers(
        dest="api_budget_command",
        required=True,
    )
    memory_api_budget_status_parser = memory_api_budget_subparsers.add_parser(
        "status",
        help="show API budget policy, usage, and recent events",
    )
    memory_api_budget_status_parser.add_argument("--db", default="runs/x_data.sqlite3")
    memory_api_budget_status_parser.add_argument("--policy-id", default="default")
    memory_api_budget_status_parser.add_argument("--run-id", default=None)
    memory_api_budget_status_parser.add_argument("--json", action="store_true")
    memory_api_budget_set_parser = memory_api_budget_subparsers.add_parser(
        "set",
        help="set API budget caps for a policy",
    )
    memory_api_budget_set_parser.add_argument("--db", default="runs/x_data.sqlite3")
    memory_api_budget_set_parser.add_argument("--policy-id", default="default")
    memory_api_budget_set_parser.add_argument("--enabled", action=argparse.BooleanOptionalAction)
    memory_api_budget_set_parser.add_argument("--max-run-usd", type=float, default=None)
    memory_api_budget_set_parser.add_argument("--max-day-usd", type=float, default=None)
    memory_api_budget_set_parser.add_argument("--max-month-usd", type=float, default=None)
    memory_api_budget_set_parser.add_argument("--max-run-calls", type=int, default=None)
    memory_api_budget_set_parser.add_argument("--max-day-calls", type=int, default=None)
    memory_api_budget_set_parser.add_argument("--max-run-input-tokens", type=int, default=None)
    memory_api_budget_set_parser.add_argument("--max-run-media-bytes", type=int, default=None)
    memory_api_budget_set_parser.add_argument(
        "--unknown-price-action",
        choices=["block", "allow"],
        default=None,
    )
    memory_api_budget_set_parser.add_argument("--json", action="store_true")
    memory_api_budget_stop_parser = memory_api_budget_subparsers.add_parser(
        "stop",
        help="enable kill switch for new provider API calls",
    )
    memory_api_budget_stop_parser.add_argument("--db", default="runs/x_data.sqlite3")
    memory_api_budget_stop_parser.add_argument("--policy-id", default="default")
    memory_api_budget_stop_parser.add_argument("--json", action="store_true")
    memory_api_budget_resume_parser = memory_api_budget_subparsers.add_parser(
        "resume",
        help="disable kill switch for new provider API calls",
    )
    memory_api_budget_resume_parser.add_argument("--db", default="runs/x_data.sqlite3")
    memory_api_budget_resume_parser.add_argument("--policy-id", default="default")
    memory_api_budget_resume_parser.add_argument("--json", action="store_true")
    memory_api_budget_price_parser = memory_api_budget_subparsers.add_parser(
        "price-set",
        help="register a checked provider/model price row used by budget estimates",
    )
    memory_api_budget_price_parser.add_argument("--db", default="runs/x_data.sqlite3")
    memory_api_budget_price_parser.add_argument("--provider", required=True)
    memory_api_budget_price_parser.add_argument("--model", required=True)
    memory_api_budget_price_parser.add_argument("--operation", required=True)
    memory_api_budget_price_parser.add_argument(
        "--unit",
        required=True,
        choices=[
            "input_token",
            "input_tokens",
            "output_token",
            "output_tokens",
            "media_byte",
            "media_bytes",
            "document",
            "documents",
            "page",
            "pages",
            "call",
            "calls",
        ],
    )
    memory_api_budget_price_parser.add_argument("--usd-per-unit", type=float, required=True)
    memory_api_budget_price_parser.add_argument("--source-url", default=None)
    memory_api_budget_price_parser.add_argument("--checked-at", default=None)
    memory_api_budget_price_parser.add_argument("--notes", default=None)
    memory_api_budget_seed_prices_parser = memory_api_budget_subparsers.add_parser(
        "seed-default-prices",
        help="register checked default provider/model price rows used before future provider runs",
    )
    memory_api_budget_seed_prices_parser.add_argument("--db", default="runs/x_data.sqlite3")
    memory_api_budget_preflight_parser = memory_api_budget_subparsers.add_parser(
        "preflight",
        help="dry-run validate scoped provider quota approval and API budget guard",
    )
    memory_api_budget_preflight_parser.add_argument("--db", default="runs/x_data.sqlite3")
    memory_api_budget_preflight_parser.add_argument("--policy-id", default="default")
    memory_api_budget_preflight_parser.add_argument("--run-id", default=None)
    memory_api_budget_preflight_parser.add_argument("--provider", required=True)
    memory_api_budget_preflight_parser.add_argument("--model", required=True)
    memory_api_budget_preflight_parser.add_argument("--operation", required=True)
    memory_api_budget_preflight_parser.add_argument("--provider-role", default="provider")
    memory_api_budget_preflight_parser.add_argument(
        "--limit",
        type=int,
        default=1,
        help="planned provider call count for this dry-run preflight",
    )
    memory_api_budget_preflight_parser.add_argument("--calls", type=int, default=None)
    memory_api_budget_preflight_parser.add_argument("--input-tokens", type=int, default=0)
    memory_api_budget_preflight_parser.add_argument("--output-tokens", type=int, default=0)
    memory_api_budget_preflight_parser.add_argument("--media-bytes", type=int, default=0)
    memory_api_budget_preflight_parser.add_argument("--documents", type=int, default=0)
    memory_api_budget_preflight_parser.add_argument("--pages", type=int, default=0)
    memory_api_budget_preflight_parser.add_argument("--max-run-usd", type=float, default=None)
    memory_api_budget_preflight_parser.add_argument("--allow-unpriced-api", action="store_true")
    memory_api_budget_preflight_parser.add_argument(
        "--provider-authorization-id",
        default=None,
        help="saved ProviderExecutionPolicy authorization id to load for this dry-run preflight",
    )
    memory_api_budget_preflight_parser.add_argument(
        "--provider-execution-policy-id",
        default=None,
        help="saved ProviderExecutionPolicy id to load for this dry-run preflight",
    )
    memory_api_budget_preflight_parser.add_argument(
        "--current-scope",
        default=None,
        help="scope being checked against the approval object",
    )
    _add_provider_quota_approval_options(memory_api_budget_preflight_parser)
    memory_api_budget_preflight_parser.add_argument("--json", action="store_true")
    memory_api_budget_authorize_parser = memory_api_budget_subparsers.add_parser(
        "authorize",
        help="record a scoped provider execution authorization for future budgeted calls",
    )
    memory_api_budget_authorize_parser.add_argument("--db", default="runs/x_data.sqlite3")
    memory_api_budget_authorize_parser.add_argument("--authorization-id", required=True)
    memory_api_budget_authorize_parser.add_argument("--policy-id", default=None)
    memory_api_budget_authorize_parser.add_argument("--provider", required=True)
    memory_api_budget_authorize_parser.add_argument("--model", required=True)
    memory_api_budget_authorize_parser.add_argument("--operation", required=True)
    memory_api_budget_authorize_parser.add_argument("--provider-role", default=None)
    memory_api_budget_authorize_parser.add_argument("--max-calls", type=int, required=True)
    memory_api_budget_authorize_parser.add_argument("--max-cost-usd", type=float, required=True)
    memory_api_budget_authorize_parser.add_argument("--max-input-tokens", type=int, default=None)
    memory_api_budget_authorize_parser.add_argument("--max-output-tokens", type=int, default=None)
    memory_api_budget_authorize_parser.add_argument("--max-media-bytes", type=int, default=None)
    memory_api_budget_authorize_parser.add_argument("--max-documents", type=int, default=None)
    memory_api_budget_authorize_parser.add_argument("--approved-scope", default="*")
    memory_api_budget_authorize_parser.add_argument("--approved-by", default=None)
    memory_api_budget_authorize_parser.add_argument("--approval-source", default="manual")
    memory_api_budget_authorize_parser.add_argument("--approved-at", default=None)
    memory_api_budget_authorize_parser.add_argument("--valid-until", default=None)
    memory_api_budget_authorize_parser.add_argument("--storage-rights", default=None)
    memory_api_budget_authorize_parser.add_argument(
        "--prompt-injection-required",
        action=argparse.BooleanOptionalAction,
        default=None,
    )
    memory_api_budget_authorize_parser.add_argument("--rollback-scope", default=None)
    memory_api_budget_authorize_parser.add_argument(
        "--metadata",
        action="append",
        default=[],
        help="metadata key=value pair; repeatable",
    )
    memory_api_budget_authorize_parser.add_argument("--json", action="store_true")

    memory_api_usage_parser = memory_subparsers.add_parser(
        "api-usage",
        help="show API usage ledger rows and totals",
    )
    memory_api_usage_parser.add_argument("--db", default="runs/x_data.sqlite3")
    memory_api_usage_parser.add_argument("--run-id", default=None)
    memory_api_usage_parser.add_argument("--today", action="store_true")
    memory_api_usage_parser.add_argument("--month", action="store_true")
    memory_api_usage_parser.add_argument("--limit", type=int, default=100)
    memory_api_usage_parser.add_argument("--json", action="store_true")

    memory_api_watch_parser = memory_subparsers.add_parser(
        "api-watch",
        help="serve a lightweight live API budget monitor for a DB",
    )
    memory_api_watch_parser.add_argument("--db", default="runs/x_data.sqlite3")
    memory_api_watch_parser.add_argument("--host", default="127.0.0.1")
    memory_api_watch_parser.add_argument("--port", type=int, default=8767)
    memory_api_watch_parser.add_argument(
        "--open-browser",
        action=argparse.BooleanOptionalAction,
        default=True,
    )
    memory_api_watch_parser.add_argument("--policy-id", default="default")
    memory_api_watch_parser.add_argument("--run-id", default=None)
    memory_api_watch_parser.add_argument("--recent-limit", type=int, default=20)

    memory_api_dashboard_parser = memory_subparsers.add_parser(
        "api-dashboard",
        help="serve a live all-API budget and provider ledger dashboard for a DB",
    )
    memory_api_dashboard_parser.add_argument("--db", default="runs/x_data.sqlite3")
    memory_api_dashboard_parser.add_argument("--host", default="127.0.0.1")
    memory_api_dashboard_parser.add_argument("--port", type=int, default=8767)
    memory_api_dashboard_parser.add_argument(
        "--open-browser",
        action=argparse.BooleanOptionalAction,
        default=True,
    )
    memory_api_dashboard_parser.add_argument("--policy-id", default="default")
    memory_api_dashboard_parser.add_argument("--run-id", default=None)
    memory_api_dashboard_parser.add_argument("--recent-limit", type=int, default=20)

    memory_api_lane_estimate_parser = memory_subparsers.add_parser(
        "api-lane-estimate",
        help="estimate planned provider lanes without making provider API calls",
    )
    memory_api_lane_estimate_parser.add_argument("--db", default="runs/x_data.sqlite3")
    memory_api_lane_estimate_parser.add_argument(
        "--include-reference-managed-rag",
        action="store_true",
        help="show managed RAG reference rows as enabled reference lanes",
    )
    memory_api_lane_estimate_parser.add_argument(
        "--include-latest-ocr",
        action="store_true",
        help="also estimate mistral-ocr-latest; default estimates the fixed OCR model only",
    )
    memory_api_lane_estimate_parser.add_argument(
        "--ocr-scope",
        choices=["none", "sample", "candidate-set", "all"],
        default="sample",
        help="OCR cost scope; candidate-set estimates routed media candidates, all is expensive",
    )
    memory_api_lane_estimate_parser.add_argument(
        "--ocr-limit",
        type=int,
        default=100,
        help="media item cap used when --ocr-scope sample or candidate-set",
    )
    memory_api_lane_estimate_parser.add_argument("--reader-url-limit", type=int, default=100)
    memory_api_lane_estimate_parser.add_argument("--reader-max-chars", type=int, default=4000)
    memory_api_lane_estimate_parser.add_argument("--rerank-query-count", type=int, default=5)
    memory_api_lane_estimate_parser.add_argument("--rerank-candidate-limit", type=int, default=20)
    memory_api_lane_estimate_parser.add_argument(
        "--rerank-avg-candidate-tokens",
        type=int,
        default=250,
    )
    memory_api_lane_estimate_parser.add_argument(
        "--external-search-query-count",
        type=int,
        default=1,
        help="successful Serper external-search calls to estimate; set 0 to skip",
    )
    memory_api_lane_estimate_parser.add_argument(
        "--external-search-result-limit",
        type=int,
        default=10,
        help="results requested per Serper call; affects returned documents, not call pricing",
    )
    memory_api_lane_estimate_parser.add_argument(
        "--llm-context-query-count",
        type=int,
        default=1,
        help="Brave LLM Context calls to estimate; set 0 to skip",
    )
    memory_api_lane_estimate_parser.add_argument(
        "--max-file-bytes",
        type=int,
        default=20 * 1024 * 1024,
    )
    memory_api_lane_estimate_parser.add_argument("--json", action="store_true")
    memory_knowledge_parser = memory_subparsers.add_parser(
        "knowledge",
        help="KnowledgeOps source manifest, observation, reconciliation, and status commands",
    )
    memory_knowledge_parser.add_argument("--db", default="runs/x_data.sqlite3")
    memory_knowledge_subparsers = memory_knowledge_parser.add_subparsers(
        dest="knowledge_command",
        required=True,
    )
    memory_knowledge_sync_parser = memory_knowledge_subparsers.add_parser(
        "sync-sources",
        help="sync local X tables into memory_sources and observations",
    )
    memory_knowledge_sync_parser.add_argument("--db", default="runs/x_data.sqlite3")
    memory_knowledge_sync_parser.add_argument("--observation-run-id", default=None)
    memory_knowledge_sync_parser.add_argument(
        "--observation-completeness",
        choices=["complete", "partial", "unknown"],
        default=None,
    )
    memory_knowledge_sync_parser.add_argument("--observed-at", default=None)
    memory_knowledge_sync_parser.add_argument("--json", action="store_true")
    memory_knowledge_source_list_parser = memory_knowledge_subparsers.add_parser(
        "source-list",
        help="list KnowledgeOps sources",
    )
    memory_knowledge_source_list_parser.add_argument("--db", default="runs/x_data.sqlite3")
    memory_knowledge_source_list_parser.add_argument("--limit", type=int, default=50)
    memory_knowledge_source_list_parser.add_argument("--json", action="store_true")
    memory_knowledge_source_show_parser = memory_knowledge_subparsers.add_parser(
        "source-show",
        help="show one KnowledgeOps source",
    )
    memory_knowledge_source_show_parser.add_argument("--db", default="runs/x_data.sqlite3")
    memory_knowledge_source_show_parser.add_argument("--source-ref", required=True)
    memory_knowledge_source_show_parser.add_argument("--json", action="store_true")
    memory_knowledge_observations_parser = memory_knowledge_subparsers.add_parser(
        "observations",
        help="list source observations",
    )
    memory_knowledge_observations_parser.add_argument("--db", default="runs/x_data.sqlite3")
    memory_knowledge_observations_parser.add_argument("--source-ref", default=None)
    memory_knowledge_observations_parser.add_argument("--limit", type=int, default=50)
    memory_knowledge_observations_parser.add_argument("--json", action="store_true")
    memory_knowledge_reconcile_parser = memory_knowledge_subparsers.add_parser(
        "reconcile",
        help="run partial-safe source reconciliation",
    )
    memory_knowledge_reconcile_parser.add_argument("--db", default="runs/x_data.sqlite3")
    memory_knowledge_reconcile_parser.add_argument(
        "--observed-source-ref",
        action="append",
        default=[],
    )
    memory_knowledge_reconcile_parser.add_argument(
        "--observation-completeness",
        choices=["complete", "partial", "unknown"],
        default="unknown",
    )
    memory_knowledge_reconcile_parser.add_argument("--scope", default="local-db-full-scan")
    memory_knowledge_reconcile_parser.add_argument("--run-id", default=None)
    memory_knowledge_reconcile_parser.add_argument("--started-at", default="")
    memory_knowledge_reconcile_parser.add_argument("--json", action="store_true")
    memory_knowledge_reconcile_show_parser = memory_knowledge_subparsers.add_parser(
        "reconcile-show",
        help="show a previous reconciliation run and its items",
    )
    memory_knowledge_reconcile_show_parser.add_argument(
        "--db",
        default="runs/x_data.sqlite3",
    )
    memory_knowledge_reconcile_show_parser.add_argument("--run-id", required=True)
    memory_knowledge_reconcile_show_parser.add_argument("--json", action="store_true")
    memory_knowledge_cleanup_orphans_parser = memory_knowledge_subparsers.add_parser(
        "cleanup-orphans",
        help="mark orphaned projection/artifact records without deleting sources",
    )
    memory_knowledge_cleanup_orphans_parser.add_argument(
        "--db",
        default="runs/x_data.sqlite3",
    )
    memory_knowledge_cleanup_orphans_parser.add_argument("--dry-run", action="store_true")
    memory_knowledge_cleanup_orphans_parser.add_argument("--json", action="store_true")
    memory_knowledge_status_parser = memory_knowledge_subparsers.add_parser(
        "status",
        help="summarize KnowledgeOps source/artifact/reconciliation state",
    )
    memory_knowledge_status_parser.add_argument("--db", default="runs/x_data.sqlite3")
    memory_knowledge_status_parser.add_argument("--json", action="store_true")

    memory_artifacts_parser = memory_subparsers.add_parser(
        "artifacts",
        help="KnowledgeOps artifact registry commands",
    )
    memory_artifacts_subparsers = memory_artifacts_parser.add_subparsers(
        dest="artifacts_command",
        required=True,
    )
    memory_artifacts_list_parser = memory_artifacts_subparsers.add_parser("list")
    memory_artifacts_list_parser.add_argument("--db", default="runs/x_data.sqlite3")
    memory_artifacts_list_parser.add_argument("--limit", type=int, default=50)
    memory_artifacts_list_parser.add_argument("--json", action="store_true")
    memory_artifacts_show_parser = memory_artifacts_subparsers.add_parser("show")
    memory_artifacts_show_parser.add_argument("--db", default="runs/x_data.sqlite3")
    memory_artifacts_show_parser.add_argument("--artifact-id", required=True)
    memory_artifacts_show_parser.add_argument("--json", action="store_true")
    memory_artifacts_links_parser = memory_artifacts_subparsers.add_parser("links")
    memory_artifacts_links_parser.add_argument("--db", default="runs/x_data.sqlite3")
    memory_artifacts_links_parser.add_argument("--artifact-id", required=True)
    memory_artifacts_links_parser.add_argument("--json", action="store_true")
    memory_artifacts_validate_parser = memory_artifacts_subparsers.add_parser("validate")
    memory_artifacts_validate_parser.add_argument("--db", default="runs/x_data.sqlite3")
    memory_artifacts_validate_parser.add_argument("--json", action="store_true")

    memory_projections_parser = memory_subparsers.add_parser(
        "projections",
        help="KnowledgeOps projection lifecycle commands",
    )
    memory_projections_subparsers = memory_projections_parser.add_subparsers(
        dest="projections_command",
        required=True,
    )
    for _projection_command in ("plan", "build", "coverage", "show"):
        _projection_parser = memory_projections_subparsers.add_parser(_projection_command)
        _projection_parser.add_argument("--db", default="runs/x_data.sqlite3")
        _projection_parser.add_argument("--projection-id", default=None)
        _projection_parser.add_argument("--projection-kind", default=None)
        if _projection_command == "build":
            _projection_parser.add_argument(
                "--mode",
                choices=("incremental", "full"),
                default="incremental",
            )
            _projection_parser.add_argument("--provider", default="local_hash")
            _projection_parser.add_argument("--model", default=None)
            _projection_parser.add_argument("--dimensions", type=int, default=None)
            _projection_parser.add_argument("--embedding-profile", default=None)
            _projection_parser.add_argument("--text-template-version", default=None)
            _projection_parser.add_argument("--backend", default="numpy")
            _projection_parser.add_argument("--bit-width", type=int, default=4)
            _projection_parser.add_argument("--out-dir", default=None)
            _projection_parser.add_argument("--doc-type", default=None)
            _projection_parser.add_argument("--account", default=None)
        _projection_parser.add_argument("--json", action="store_true")

    memory_participation_parser = memory_subparsers.add_parser(
        "participation",
        help="KnowledgeOps participation policy commands",
    )
    memory_participation_subparsers = memory_participation_parser.add_subparsers(
        dest="participation_command",
        required=True,
    )
    memory_participation_rebuild_parser = memory_participation_subparsers.add_parser(
        "rebuild"
    )
    memory_participation_rebuild_parser.add_argument("--db", default="runs/x_data.sqlite3")
    memory_participation_rebuild_parser.add_argument("--output-mode", action="append", default=[])
    memory_participation_rebuild_parser.add_argument("--decided-at", default="")
    memory_participation_rebuild_parser.add_argument("--json", action="store_true")
    for _participation_command in ("check", "explain"):
        _participation_parser = memory_participation_subparsers.add_parser(
            _participation_command
        )
        _participation_parser.add_argument("--db", default="runs/x_data.sqlite3")
        _participation_parser.add_argument("--source-ref", default=None)
        _participation_parser.add_argument("--artifact-id", default=None)
        _participation_parser.add_argument("--output-mode", required=True)
        _participation_parser.add_argument("--json", action="store_true")

    for _mode_command in ("explore", "collect"):
        _mode_parser = memory_subparsers.add_parser(
            _mode_command,
            help=f"mode-aware {_mode_command} output over local memory search",
        )
        _mode_parser.add_argument("--db", default="runs/x_data.sqlite3")
        _mode_parser.add_argument("--query", required=True)
        _mode_parser.add_argument("--limit", type=int, default=5)
        _mode_parser.add_argument("--doc-type", default=None)
        _mode_parser.add_argument("--account", default=None)
        _mode_parser.add_argument("--json", action="store_true")
    memory_working_note_parser = memory_subparsers.add_parser(
        "working-note",
        help="create, append, show, promote, or expire KnowledgeOps working notes",
    )
    memory_working_note_subparsers = memory_working_note_parser.add_subparsers(
        dest="working_note_command",
        required=True,
    )
    memory_working_note_create_parser = memory_working_note_subparsers.add_parser(
        "create"
    )
    memory_working_note_create_parser.add_argument("--db", default="runs/x_data.sqlite3")
    memory_working_note_create_parser.add_argument("--title", required=True)
    memory_working_note_create_parser.add_argument("--body", required=True)
    memory_working_note_create_parser.add_argument("--task-scope", required=True)
    memory_working_note_create_parser.add_argument("--thread-scope", default=None)
    memory_working_note_create_parser.add_argument("--source-ref", action="append", default=[])
    memory_working_note_create_parser.add_argument("--artifact-ref", action="append", default=[])
    memory_working_note_create_parser.add_argument("--retention-policy", default="task")
    memory_working_note_create_parser.add_argument("--created-at", default=None)
    memory_working_note_create_parser.add_argument("--expires-at", default=None)
    memory_working_note_create_parser.add_argument("--json", action="store_true")
    memory_working_note_append_parser = memory_working_note_subparsers.add_parser(
        "append"
    )
    memory_working_note_append_parser.add_argument("--db", default="runs/x_data.sqlite3")
    memory_working_note_append_parser.add_argument("--note-id", required=True)
    memory_working_note_append_parser.add_argument("--text", required=True)
    memory_working_note_append_parser.add_argument("--updated-at", default=None)
    memory_working_note_append_parser.add_argument("--json", action="store_true")
    memory_working_note_show_parser = memory_working_note_subparsers.add_parser("show")
    memory_working_note_show_parser.add_argument("--db", default="runs/x_data.sqlite3")
    memory_working_note_show_parser.add_argument("--note-id", required=True)
    memory_working_note_show_parser.add_argument("--json", action="store_true")
    memory_working_note_link_parser = memory_working_note_subparsers.add_parser("link")
    memory_working_note_link_parser.add_argument("--db", default="runs/x_data.sqlite3")
    memory_working_note_link_parser.add_argument("--note-id", required=True)
    memory_working_note_link_parser.add_argument("--source-ref", action="append", default=[])
    memory_working_note_link_parser.add_argument("--artifact-ref", action="append", default=[])
    memory_working_note_link_parser.add_argument("--updated-at", default=None)
    memory_working_note_link_parser.add_argument("--json", action="store_true")
    memory_working_note_promote_parser = memory_working_note_subparsers.add_parser(
        "promote"
    )
    memory_working_note_promote_parser.add_argument("--db", default="runs/x_data.sqlite3")
    memory_working_note_promote_parser.add_argument("--note-id", required=True)
    memory_working_note_promote_parser.add_argument("--promoted-at", default=None)
    memory_working_note_promote_parser.add_argument(
        "--confirm-human-in-loop",
        action="store_true",
        help="required approval gate for promoting a working note to a curated source",
    )
    memory_working_note_promote_parser.add_argument("--approved-by", default=None)
    memory_working_note_promote_parser.add_argument("--approval-note", default=None)
    memory_working_note_promote_parser.add_argument("--json", action="store_true")
    memory_working_note_expire_parser = memory_working_note_subparsers.add_parser(
        "expire"
    )
    memory_working_note_expire_parser.add_argument("--db", default="runs/x_data.sqlite3")
    memory_working_note_expire_parser.add_argument("--note-id", required=True)
    memory_working_note_expire_parser.add_argument("--expired-at", default=None)
    memory_working_note_expire_parser.add_argument("--json", action="store_true")
    memory_synthesize_parser = memory_subparsers.add_parser(
        "synthesize",
        help="return non-answer synthesis scaffolding for candidate material",
    )
    memory_synthesize_parser.add_argument("--query", required=True)
    memory_synthesize_parser.add_argument("--json", action="store_true")
    memory_evidence_package_parser = memory_subparsers.add_parser(
        "evidence-package",
        help="alias for mode-aware evidence package output",
    )
    memory_evidence_package_parser.add_argument("--db", default="runs/x_data.sqlite3")
    memory_evidence_package_parser.add_argument("--query", required=True)
    memory_evidence_package_parser.add_argument("--limit", type=int, default=5)
    memory_evidence_package_parser.add_argument("--json", action="store_true")

    memory_eval_v2_parser = memory_subparsers.add_parser(
        "eval-v2",
        help="run, compare, or report mode-aware EvalCaseV2 checks",
    )
    memory_eval_v2_parser.add_argument(
        "eval_v2_command",
        nargs="?",
        choices=["run", "compare", "report"],
        default="run",
    )
    memory_eval_v2_parser.add_argument("--db", default="runs/x_data.sqlite3")
    memory_eval_v2_parser.add_argument("--cases", default=None)
    memory_eval_v2_parser.add_argument("--baseline", default=None)
    memory_eval_v2_parser.add_argument("--candidate", default=None)
    memory_eval_v2_parser.add_argument("--run-id", default=None)
    memory_eval_v2_parser.add_argument("--json", action="store_true")

    memory_route_promotion_parser = memory_subparsers.add_parser(
        "route-promotion",
        help="check, approve, or reject KnowledgeOps route promotion decisions",
    )
    memory_route_promotion_subparsers = memory_route_promotion_parser.add_subparsers(
        dest="route_promotion_command",
        required=True,
    )
    memory_route_promotion_check_parser = memory_route_promotion_subparsers.add_parser(
        "check"
    )
    memory_route_promotion_check_parser.add_argument("--db", default="runs/x_data.sqlite3")
    memory_route_promotion_check_parser.add_argument("--candidate-route-version", required=True)
    memory_route_promotion_check_parser.add_argument("--baseline-route-version", default=None)
    memory_route_promotion_check_parser.add_argument(
        "--eval-run-id",
        action="append",
        required=True,
    )
    memory_route_promotion_check_parser.add_argument(
        "--output-mode",
        action="append",
        required=True,
    )
    memory_route_promotion_check_parser.add_argument(
        "--delta",
        action="append",
        default=[],
        help="metric=value; repeatable",
    )
    memory_route_promotion_check_parser.add_argument(
        "--threshold",
        action="append",
        default=[],
        help="metric=value; repeatable",
    )
    memory_route_promotion_check_parser.add_argument("--created-at", required=True)
    memory_route_promotion_check_parser.add_argument("--json", action="store_true")
    for _route_command in ("approve", "reject"):
        _route_parser = memory_route_promotion_subparsers.add_parser(_route_command)
        _route_parser.add_argument("--db", default="runs/x_data.sqlite3")
        _route_parser.add_argument("--decision-id", required=True)
        _route_parser.add_argument("--at", required=True)
        _route_parser.add_argument("--reason", required=True)
        _route_parser.add_argument("--json", action="store_true")
    memory_route_promotion_list_parser = memory_route_promotion_subparsers.add_parser("list")
    memory_route_promotion_list_parser.add_argument("--db", default="runs/x_data.sqlite3")
    memory_route_promotion_list_parser.add_argument("--status", default=None)
    memory_route_promotion_list_parser.add_argument("--json", action="store_true")

    memory_audit_events_parser = memory_subparsers.add_parser(
        "audit-events",
        help="list KnowledgeOps audit events",
    )
    memory_audit_events_parser.add_argument("--db", default="runs/x_data.sqlite3")
    memory_audit_events_parser.add_argument("--event-type", default=None)
    memory_audit_events_parser.add_argument("--json", action="store_true")
    memory_audit_latest_parser = memory_subparsers.add_parser(
        "audit-latest",
        help="show the latest KnowledgeOps audit event",
    )
    memory_audit_latest_parser.add_argument("--db", default="runs/x_data.sqlite3")
    memory_audit_latest_parser.add_argument("--json", action="store_true")
    memory_audit_summary_parser = memory_subparsers.add_parser(
        "audit-summary",
        help="summarize KnowledgeOps audit events",
    )
    memory_audit_summary_parser.add_argument("--db", default="runs/x_data.sqlite3")
    memory_audit_summary_parser.add_argument("--json", action="store_true")
    memory_alert_test_parser = memory_subparsers.add_parser(
        "alert-test",
        help="deliver audit events to a local_jsonl alert sink",
    )
    memory_alert_test_parser.add_argument("--db", default="runs/x_data.sqlite3")
    memory_alert_test_parser.add_argument("--sink-id", default="alert-test-local-jsonl")
    memory_alert_test_parser.add_argument("--path", required=True)
    memory_alert_test_parser.add_argument("--event-type", default=None)
    memory_alert_test_parser.add_argument("--delivered-at", default="")
    memory_alert_test_parser.add_argument("--json", action="store_true")
    memory_build_parser = memory_subparsers.add_parser(
        "build-corpus",
        help="build memory_documents and FTS index from the canonical X store",
    )
    memory_build_parser.add_argument(
        "--db",
        default="runs/x_data.sqlite3",
        help="SQLite database path",
    )
    memory_derived_parser = memory_subparsers.add_parser(
        "build-derived",
        help="build derived place, author, ticker-event, and topic-thread documents",
    )
    memory_derived_parser.add_argument("--db", default="runs/x_data.sqlite3")
    memory_derived_parser.add_argument(
        "--kind",
        action="append",
        choices=["place_card", "author_profile", "ticker_event", "topic_thread"],
        default=None,
        help="derived document kind to rebuild; repeat to select multiple",
    )
    memory_derived_parser.add_argument(
        "--max-source-docs-per-card",
        type=int,
        default=8,
        help="maximum source documents quoted in each derived card",
    )
    memory_derived_parser.add_argument(
        "--min-author-docs",
        type=int,
        default=1,
        help="minimum source documents required for an author_profile",
    )
    memory_derived_parser.add_argument(
        "--min-topic-docs",
        type=int,
        default=2,
        help="minimum source documents required for a topic_thread",
    )
    memory_audit_parser = memory_subparsers.add_parser(
        "audit",
        help="audit memory indexes and fail in strict mode when production readiness is missing",
    )
    memory_audit_parser.add_argument("--db", default="runs/x_data.sqlite3")
    memory_audit_parser.add_argument("--json", action="store_true")
    memory_audit_parser.add_argument(
        "--strict",
        action="store_true",
        help="return a non-zero exit code when audit warnings are present",
    )
    memory_audit_parser.add_argument(
        "--readiness-scope",
        choices=MEMORY_AUDIT_READINESS_SCOPE_CHOICES,
        default="provider-production",
        help=(
            "readiness gate used by --strict; provider-production preserves the "
            "historical warning-sensitive behavior, local-no-provider ignores "
            "expected provider/quota gates"
        ),
    )
    memory_embedding_parser = memory_subparsers.add_parser(
        "build-embeddings",
        help="build semantic embedding index over memory_documents",
    )
    memory_embedding_parser.add_argument("--db", default="runs/x_data.sqlite3")
    memory_embedding_parser.add_argument("--space-id", default=None)
    memory_embedding_parser.add_argument(
        "--provider",
        default="auto",
        choices=MEMORY_EMBEDDING_PROVIDER_CHOICES,
    )
    memory_embedding_parser.add_argument("--model", default=None)
    memory_embedding_parser.add_argument("--dimensions", type=int, default=None)
    memory_embedding_parser.add_argument("--embedding-profile", default="general_memory")
    memory_embedding_parser.add_argument(
        "--text-template-version",
        default="memory-doc-embedding-v1",
    )
    memory_embedding_parser.add_argument("--api-key-env", default=None)
    memory_embedding_parser.add_argument("--base-url", default=None)
    memory_embedding_parser.add_argument("--batch-size", type=int, default=64)
    memory_embedding_parser.add_argument("--limit", type=int, default=None)
    memory_embedding_parser.add_argument(
        "--execution-stage",
        choices=MEMORY_EMBEDDING_EXECUTION_STAGE_CHOICES,
        default="auto",
        help=(
            "embedding build intent; limited auto builds are technical canaries, "
            "production-scope must not use --limit"
        ),
    )
    memory_embedding_parser.add_argument(
        "--selection-policy",
        choices=MEMORY_EMBEDDING_SELECTION_POLICY_CHOICES,
        default="auto",
        help="document selection policy for limited canary/eval-slice builds",
    )
    memory_embedding_parser.add_argument("--rebuild", action="store_true")
    memory_embedding_parser.add_argument("--progress-every", type=int, default=1000)
    memory_embedding_parser.add_argument("--projection-profile", default=None)
    memory_embedding_parser.add_argument("--classification-version", default=None)
    memory_embedding_parser.add_argument("--projection-policy-version", default=None)
    memory_embedding_parser.add_argument("--require-projections", action="store_true")
    _add_api_budget_options(memory_embedding_parser)
    _add_provider_quota_gate_option(memory_embedding_parser)
    memory_embedding_estimate_parser = memory_subparsers.add_parser(
        "embedding-estimate",
        help="estimate documents, API batches, tokens, and optional cost for embedding builds",
    )
    memory_embedding_estimate_parser.add_argument("--db", default="runs/x_data.sqlite3")
    memory_embedding_estimate_parser.add_argument("--space-id", default=None)
    memory_embedding_estimate_parser.add_argument(
        "--provider",
        default="auto",
        choices=MEMORY_EMBEDDING_PROVIDER_CHOICES,
    )
    memory_embedding_estimate_parser.add_argument("--model", default=None)
    memory_embedding_estimate_parser.add_argument("--dimensions", type=int, default=None)
    memory_embedding_estimate_parser.add_argument("--embedding-profile", default="general_memory")
    memory_embedding_estimate_parser.add_argument(
        "--text-template-version",
        default="memory-doc-embedding-v1",
    )
    memory_embedding_estimate_parser.add_argument("--api-key-env", default=None)
    memory_embedding_estimate_parser.add_argument("--base-url", default=None)
    memory_embedding_estimate_parser.add_argument("--batch-size", type=int, default=64)
    memory_embedding_estimate_parser.add_argument("--limit", type=int, default=None)
    memory_embedding_estimate_parser.add_argument(
        "--execution-stage",
        choices=MEMORY_EMBEDDING_EXECUTION_STAGE_CHOICES,
        default="auto",
        help=(
            "embedding estimate intent; limited auto estimates are technical canaries, "
            "production-scope must not use --limit"
        ),
    )
    memory_embedding_estimate_parser.add_argument(
        "--selection-policy",
        choices=MEMORY_EMBEDDING_SELECTION_POLICY_CHOICES,
        default="auto",
        help="document selection policy for limited canary/eval-slice estimates",
    )
    memory_embedding_estimate_parser.add_argument("--rebuild", action="store_true")
    memory_embedding_estimate_parser.add_argument(
        "--price-per-million-input-tokens",
        type=float,
        default=None,
        help="optional provider price used only for a rough input-cost estimate",
    )
    memory_embedding_estimate_parser.add_argument("--projection-profile", default=None)
    memory_embedding_estimate_parser.add_argument("--classification-version", default=None)
    memory_embedding_estimate_parser.add_argument("--projection-policy-version", default=None)
    memory_embedding_estimate_parser.add_argument("--require-projections", action="store_true")
    memory_embedding_estimate_parser.add_argument("--json", action="store_true")
    memory_classify_embedding_parser = memory_subparsers.add_parser(
        "classify-embedding-inputs",
        help="classify memory_documents into A-D embedding input taxonomy rows",
    )
    memory_classify_embedding_parser.add_argument("--db", default="runs/x_data.sqlite3")
    memory_classify_embedding_parser.add_argument(
        "--classification-version",
        default="embedding-taxonomy-v1",
    )
    memory_classify_embedding_parser.add_argument("--dry-run", action="store_true")
    memory_classify_embedding_parser.add_argument("--write", action="store_true")
    memory_classify_embedding_parser.add_argument("--doc-id", default=None)
    memory_classify_embedding_parser.add_argument("--source-kind", default=None)
    memory_classify_embedding_parser.add_argument("--limit", type=int, default=None)
    memory_classify_embedding_parser.add_argument("--json", action="store_true")
    memory_template_policy_parser = memory_subparsers.add_parser(
        "embedding-template-policy",
        help="write or inspect default A-D embedding template policies",
    )
    memory_template_policy_parser.add_argument("--db", default="runs/x_data.sqlite3")
    memory_template_policy_parser.add_argument(
        "--policy-version",
        default="embedding-template-policy-v1",
    )
    memory_template_policy_parser.add_argument("--write-defaults", action="store_true")
    memory_template_policy_parser.add_argument("--json", action="store_true")
    memory_template_examples_parser = memory_subparsers.add_parser(
        "embedding-template-examples",
        help="render deterministic A-D embedding template examples",
    )
    memory_template_examples_parser.add_argument("--db", default="runs/x_data.sqlite3")
    memory_template_examples_parser.add_argument(
        "--policy-version",
        default="embedding-template-policy-v1",
    )
    memory_template_examples_parser.add_argument(
        "--classification-version",
        default="embedding-taxonomy-v1",
    )
    memory_template_examples_parser.add_argument("--limit", type=int, default=50)
    memory_template_examples_parser.add_argument("--json", action="store_true")
    memory_build_embedding_projections_parser = memory_subparsers.add_parser(
        "build-embedding-projections",
        help="build deterministic A-D embedding projection rows",
    )
    memory_build_embedding_projections_parser.add_argument("--db", default="runs/x_data.sqlite3")
    memory_build_embedding_projections_parser.add_argument(
        "--classification-version",
        default="embedding-taxonomy-v1",
    )
    memory_build_embedding_projections_parser.add_argument(
        "--projection-policy-version",
        default="embedding-projection-policy-v1",
    )
    memory_build_embedding_projections_parser.add_argument("--projection-profile", default=None)
    memory_build_embedding_projections_parser.add_argument("--space-id", default=None)
    memory_build_embedding_projections_parser.add_argument("--doc-id", default=None)
    memory_build_embedding_projections_parser.add_argument("--source-kind", default=None)
    memory_build_embedding_projections_parser.add_argument("--limit", type=int, default=None)
    memory_build_embedding_projections_parser.add_argument("--dry-run", action="store_true")
    memory_build_embedding_projections_parser.add_argument("--write", action="store_true")
    memory_build_embedding_projections_parser.add_argument("--json", action="store_true")
    memory_projection_coverage_parser = memory_subparsers.add_parser(
        "projection-coverage",
        help="report A-D embedding projection coverage",
    )
    memory_projection_coverage_parser.add_argument("--db", default="runs/x_data.sqlite3")
    memory_projection_coverage_parser.add_argument(
        "--classification-version",
        default="embedding-taxonomy-v1",
    )
    memory_projection_coverage_parser.add_argument(
        "--projection-policy-version",
        default="embedding-projection-policy-v1",
    )
    memory_projection_coverage_parser.add_argument("--json", action="store_true")
    memory_metadata_filter_policy_parser = memory_subparsers.add_parser(
        "embedding-metadata-filter-policy",
        help="write A-D metadata filter policy reports",
    )
    memory_metadata_filter_policy_parser.add_argument(
        "--policy-version",
        default="embedding-metadata-filter-policy-v1",
    )
    memory_metadata_filter_policy_parser.add_argument("--json", action="store_true")
    memory_full_run_readiness_parser = memory_subparsers.add_parser(
        "embedding-full-run-readiness",
        help="write A-D full embedding readiness report",
    )
    memory_full_run_readiness_parser.add_argument("--db", default="runs/x_data.sqlite3")
    memory_full_run_readiness_parser.add_argument("--tests-passed", action="store_true")
    memory_full_run_readiness_parser.add_argument(
        "--quarantine-legacy-embeddings",
        action="store_true",
        help="mark current embedding rows without A-D projection lineage as stale",
    )
    memory_full_run_readiness_parser.add_argument("--json", action="store_true")
    for embedding_control_parser in (
        memory_classify_embedding_parser,
        memory_template_policy_parser,
        memory_template_examples_parser,
        memory_build_embedding_projections_parser,
        memory_projection_coverage_parser,
        memory_metadata_filter_policy_parser,
        memory_full_run_readiness_parser,
    ):
        embedding_control_parser.add_argument(
            "--persistence",
            choices=("none", "trace", "artifacts"),
            default="none",
            help=(
                "sidecar persistence boundary; only artifacts writes derived control "
                "artifacts, while none and trace do not"
            ),
        )
        embedding_control_parser.add_argument(
            "--artifact-dir",
            type=Path,
            default=Path("runs") / "control_artifacts" / "embedding_input",
        )
    memory_real_api_estimate_artifacts_parser = memory_subparsers.add_parser(
        "real-api-estimate-artifacts",
        help="write offline real API estimate artifacts without provider requests",
    )
    memory_real_api_estimate_artifacts_parser.add_argument(
        "--db",
        default="runs/x_data.sqlite3",
    )
    memory_real_api_estimate_artifacts_parser.add_argument("--run-id", default=None)
    memory_real_api_estimate_artifacts_parser.add_argument(
        "--output-root",
        type=Path,
        default=Path("runs") / "real_api",
    )
    memory_real_api_estimate_artifacts_parser.add_argument(
        "--space-id",
        action="append",
        default=[],
        help="final typed embedding space id to estimate; repeatable",
    )
    memory_real_api_estimate_artifacts_parser.add_argument("--batch-size", type=int, default=64)
    memory_real_api_estimate_artifacts_parser.add_argument("--limit", type=int, default=None)
    memory_real_api_estimate_artifacts_parser.add_argument(
        "--execution-stage",
        choices=MEMORY_EMBEDDING_EXECUTION_STAGE_CHOICES,
        default="auto",
    )
    memory_real_api_estimate_artifacts_parser.add_argument(
        "--selection-policy",
        choices=MEMORY_REAL_API_ESTIMATE_SELECTION_POLICY_CHOICES,
        default="all-eligible",
    )
    memory_real_api_estimate_artifacts_parser.add_argument("--rebuild", action="store_true")
    memory_real_api_estimate_artifacts_parser.add_argument(
        "--price-per-million-input-tokens",
        type=float,
        default=None,
    )
    memory_real_api_estimate_artifacts_parser.add_argument(
        "--max-file-bytes",
        type=int,
        default=20 * 1024 * 1024,
    )
    memory_real_api_estimate_artifacts_parser.add_argument(
        "--mime-type",
        action="append",
        default=[],
    )
    memory_real_api_estimate_artifacts_parser.add_argument("--json", action="store_true")
    memory_specs_parser = memory_subparsers.add_parser(
        "embedding-specs",
        help="list available embedding indexes in the DB",
    )
    memory_specs_parser.add_argument("--db", default="runs/x_data.sqlite3")
    memory_embedding_spaces_parser = memory_subparsers.add_parser(
        "embedding-spaces",
        help="list or plan final typed embedding spaces",
    )
    memory_embedding_spaces_parser.add_argument("--db", default="runs/x_data.sqlite3")
    memory_embedding_spaces_parser.add_argument("--json", action="store_true")
    memory_embedding_spaces_subparsers = memory_embedding_spaces_parser.add_subparsers(
        dest="embedding_spaces_command",
    )
    memory_embedding_spaces_list_parser = memory_embedding_spaces_subparsers.add_parser(
        "list",
        help="list registered embedding spaces",
    )
    memory_embedding_spaces_list_parser.add_argument("--db", default="runs/x_data.sqlite3")
    memory_embedding_spaces_list_parser.add_argument("--json", action="store_true")
    memory_embedding_spaces_plan_parser = memory_embedding_spaces_subparsers.add_parser(
        "plan",
        help="confirm final typed embedding spaces are registered",
    )
    memory_embedding_spaces_plan_parser.add_argument("--db", default="runs/x_data.sqlite3")
    memory_embedding_spaces_plan_parser.add_argument("--json", action="store_true")
    memory_embedding_coverage_parser = memory_subparsers.add_parser(
        "embedding-coverage",
        help="show embedding coverage and staleness by memory document type",
    )
    memory_embedding_coverage_parser.add_argument("--db", default="runs/x_data.sqlite3")
    memory_embedding_coverage_parser.add_argument("--space-id", default=None)
    memory_embedding_coverage_parser.add_argument(
        "--provider",
        default="latest",
        choices=MEMORY_EMBEDDING_PROVIDER_OR_LATEST_CHOICES,
        help="embedding provider to inspect; latest uses the newest existing index",
    )
    memory_embedding_coverage_parser.add_argument("--model", default=None)
    memory_embedding_coverage_parser.add_argument("--dimensions", type=int, default=None)
    memory_embedding_coverage_parser.add_argument("--embedding-profile", default=None)
    memory_embedding_coverage_parser.add_argument("--text-template-version", default=None)
    memory_embedding_coverage_parser.add_argument("--json", action="store_true")
    memory_vector_projection_parser = memory_subparsers.add_parser(
        "build-vector-projection",
        help="build a local vector projection file from one current memory_embeddings scope",
    )
    memory_vector_projection_parser.add_argument("--db", default="runs/x_data.sqlite3")
    memory_vector_projection_parser.add_argument("--space-id", default=None)
    memory_vector_projection_parser.add_argument(
        "--provider",
        default=None,
        choices=MEMORY_EMBEDDING_PROVIDER_CHOICES[1:],
    )
    memory_vector_projection_parser.add_argument("--model", default=None)
    memory_vector_projection_parser.add_argument("--dimensions", type=int, default=None)
    memory_vector_projection_parser.add_argument("--embedding-profile", default="general_memory")
    memory_vector_projection_parser.add_argument(
        "--text-template-version",
        default="memory-doc-embedding-v1",
    )
    memory_vector_projection_parser.add_argument(
        "--backend",
        default="numpy",
        choices=MEMORY_VECTOR_PROJECTION_BACKEND_CHOICES,
    )
    memory_vector_projection_parser.add_argument("--bit-width", type=int, default=4)
    memory_vector_projection_parser.add_argument("--out-dir", default=None)
    memory_vector_projection_parser.add_argument("--doc-type", default=None)
    memory_vector_projection_parser.add_argument("--account", default=None)
    memory_vector_projection_parser.add_argument(
        "--allow-partial",
        action="store_true",
        help=(
            "allow a partial canary/eval projection when current embeddings do not "
            "cover the full source scope; stored as non-production and not evidence"
        ),
    )
    memory_vector_projection_parser.add_argument("--json", action="store_true")
    memory_vector_projection_coverage_parser = memory_subparsers.add_parser(
        "vector-projection-coverage",
        help="show local vector projection coverage, staleness, and artifact status",
    )
    memory_vector_projection_coverage_parser.add_argument("--db", default="runs/x_data.sqlite3")
    memory_vector_projection_coverage_parser.add_argument("--generation-id", default=None)
    memory_vector_projection_coverage_parser.add_argument("--space-id", default=None)
    memory_vector_projection_coverage_parser.add_argument("--provider", default=None)
    memory_vector_projection_coverage_parser.add_argument("--model", default=None)
    memory_vector_projection_coverage_parser.add_argument("--dimensions", type=int, default=None)
    memory_vector_projection_coverage_parser.add_argument("--embedding-profile", default=None)
    memory_vector_projection_coverage_parser.add_argument("--text-template-version", default=None)
    memory_vector_projection_coverage_parser.add_argument(
        "--backend",
        default=None,
        choices=MEMORY_VECTOR_PROJECTION_BACKEND_CHOICES,
    )
    memory_vector_projection_coverage_parser.add_argument("--json", action="store_true")
    memory_vector_index_parser = memory_subparsers.add_parser(
        "vector-index",
        help="build or inspect typed vector indexes",
    )
    memory_vector_index_subparsers = memory_vector_index_parser.add_subparsers(
        dest="vector_index_command",
    )
    memory_vector_index_build_parser = memory_vector_index_subparsers.add_parser(
        "build",
        help="build a typed vector index for one embedding space",
    )
    memory_vector_index_build_parser.add_argument("--db", default="runs/x_data.sqlite3")
    memory_vector_index_build_parser.add_argument("--space-id", required=True)
    memory_vector_index_build_parser.add_argument(
        "--backend",
        default="numpy",
        choices=MEMORY_VECTOR_PROJECTION_BACKEND_CHOICES,
    )
    memory_vector_index_build_parser.add_argument("--bit-width", type=int, default=4)
    memory_vector_index_build_parser.add_argument("--out-dir", default=None)
    memory_vector_index_build_parser.add_argument("--doc-type", default=None)
    memory_vector_index_build_parser.add_argument("--account", default=None)
    memory_vector_index_build_parser.add_argument(
        "--allow-partial",
        action="store_true",
        help=(
            "allow a partial canary/eval index when current embeddings do not cover "
            "the full source scope; stored as non-production and not evidence"
        ),
    )
    memory_vector_index_build_parser.add_argument("--json", action="store_true")
    memory_vector_index_coverage_parser = memory_vector_index_subparsers.add_parser(
        "coverage",
        help="show typed vector index coverage",
    )
    memory_vector_index_coverage_parser.add_argument("--db", default="runs/x_data.sqlite3")
    memory_vector_index_coverage_parser.add_argument("--space-id", required=True)
    memory_vector_index_coverage_parser.add_argument("--generation-id", default=None)
    memory_vector_index_coverage_parser.add_argument(
        "--backend",
        default=None,
        choices=MEMORY_VECTOR_PROJECTION_BACKEND_CHOICES,
    )
    memory_vector_index_coverage_parser.add_argument("--json", action="store_true")
    memory_vector_backend_benchmark_parser = memory_subparsers.add_parser(
        "vector-backend-benchmark",
        help="benchmark local vector projection candidates without installing new backends",
    )
    memory_vector_backend_benchmark_parser.add_argument("--db", default="runs/x_data.sqlite3")
    memory_vector_backend_benchmark_parser.add_argument(
        "--provider",
        required=True,
        choices=MEMORY_VECTOR_BENCHMARK_PROVIDER_CHOICES,
    )
    memory_vector_backend_benchmark_parser.add_argument("--model", default=None)
    memory_vector_backend_benchmark_parser.add_argument("--dimensions", type=int, default=None)
    memory_vector_backend_benchmark_parser.add_argument(
        "--embedding-profile",
        default="general_memory",
    )
    memory_vector_backend_benchmark_parser.add_argument(
        "--text-template-version",
        default="memory-doc-embedding-v1",
    )
    memory_vector_backend_benchmark_parser.add_argument(
        "--backend",
        action="append",
        default=[],
        choices=MEMORY_VECTOR_BENCHMARK_BACKEND_CHOICES,
        help="backend to include; repeat for multiple backends",
    )
    memory_vector_backend_benchmark_parser.add_argument(
        "--query",
        action="append",
        default=[],
        help="benchmark query; repeat for multiple queries",
    )
    memory_vector_backend_benchmark_parser.add_argument("--limit", type=int, default=5)
    memory_vector_backend_benchmark_parser.add_argument("--out-dir", default=None)
    memory_vector_backend_benchmark_parser.add_argument("--doc-type", default=None)
    memory_vector_backend_benchmark_parser.add_argument("--account", default=None)
    memory_vector_backend_benchmark_parser.add_argument(
        "--max-build-seconds",
        type=float,
        default=5.0,
    )
    memory_vector_backend_benchmark_parser.add_argument(
        "--max-avg-search-seconds",
        type=float,
        default=0.5,
    )
    memory_vector_backend_benchmark_parser.add_argument(
        "--max-cold-start-seconds",
        type=float,
        default=1.0,
    )
    memory_vector_backend_benchmark_parser.add_argument(
        "--min-recall-at-limit",
        type=float,
        default=1.0,
    )
    memory_vector_backend_benchmark_parser.add_argument(
        "--max-disk-bytes-per-vector",
        type=int,
        default=16_384,
    )
    memory_vector_backend_benchmark_parser.add_argument(
        "--max-memory-bytes-per-vector",
        type=int,
        default=None,
    )
    memory_vector_backend_benchmark_parser.add_argument(
        "--require-update-delete",
        action="store_true",
    )
    memory_vector_backend_benchmark_parser.add_argument(
        "--no-require-source-restoration",
        action="store_true",
    )
    memory_vector_backend_benchmark_parser.add_argument("--json", action="store_true")
    memory_media_embedding_estimate_parser = memory_subparsers.add_parser(
        "media-embedding-estimate",
        help="estimate saved media files, staleness, skips, and calls for native media embeddings",
    )
    memory_media_embedding_estimate_parser.add_argument("--db", default="runs/x_data.sqlite3")
    memory_media_embedding_estimate_parser.add_argument("--provider", default="gemini")
    memory_media_embedding_estimate_parser.add_argument("--model", default=None)
    memory_media_embedding_estimate_parser.add_argument("--dimensions", type=int, default=None)
    memory_media_embedding_estimate_parser.add_argument(
        "--embedding-profile",
        default="native_multimodal_media",
    )
    memory_media_embedding_estimate_parser.add_argument(
        "--input-template-version",
        default="gemini-media-input-v1",
    )
    memory_media_embedding_estimate_parser.add_argument("--api-key-env", default=None)
    memory_media_embedding_estimate_parser.add_argument("--base-url", default=None)
    memory_media_embedding_estimate_parser.add_argument("--limit", type=int, default=None)
    memory_media_embedding_estimate_parser.add_argument("--rebuild", action="store_true")
    memory_media_embedding_estimate_parser.add_argument(
        "--max-file-bytes",
        type=int,
        default=20 * 1024 * 1024,
    )
    memory_media_embedding_estimate_parser.add_argument(
        "--mime-type",
        action="append",
        default=[],
    )
    memory_media_embedding_estimate_parser.add_argument("--json", action="store_true")
    memory_media_embedding_parser = memory_subparsers.add_parser(
        "build-media-embeddings",
        help="build native media embeddings over saved local image/PDF media files",
    )
    memory_media_embedding_parser.add_argument("--db", default="runs/x_data.sqlite3")
    memory_media_embedding_parser.add_argument("--provider", default="gemini")
    memory_media_embedding_parser.add_argument("--model", default=None)
    memory_media_embedding_parser.add_argument("--dimensions", type=int, default=None)
    memory_media_embedding_parser.add_argument(
        "--embedding-profile",
        default="native_multimodal_media",
    )
    memory_media_embedding_parser.add_argument(
        "--input-template-version",
        default="gemini-media-input-v1",
    )
    memory_media_embedding_parser.add_argument("--api-key-env", default=None)
    memory_media_embedding_parser.add_argument("--base-url", default=None)
    memory_media_embedding_parser.add_argument("--limit", type=int, default=None)
    memory_media_embedding_parser.add_argument("--rebuild", action="store_true")
    memory_media_embedding_parser.add_argument(
        "--max-file-bytes",
        type=int,
        default=20 * 1024 * 1024,
    )
    memory_media_embedding_parser.add_argument("--mime-type", action="append", default=[])
    memory_media_embedding_parser.add_argument("--timeout-seconds", type=float, default=60.0)
    _add_provider_quota_gate_option(memory_media_embedding_parser)
    _add_api_budget_options(memory_media_embedding_parser)
    memory_media_embedding_coverage_parser = memory_subparsers.add_parser(
        "media-embedding-coverage",
        help="show native media embedding coverage/staleness by mime and skipped reason",
    )
    memory_media_embedding_coverage_parser.add_argument("--db", default="runs/x_data.sqlite3")
    memory_media_embedding_coverage_parser.add_argument("--provider", default="gemini")
    memory_media_embedding_coverage_parser.add_argument("--model", default=None)
    memory_media_embedding_coverage_parser.add_argument("--dimensions", type=int, default=None)
    memory_media_embedding_coverage_parser.add_argument(
        "--embedding-profile",
        default="native_multimodal_media",
    )
    memory_media_embedding_coverage_parser.add_argument(
        "--input-template-version",
        default="gemini-media-input-v1",
    )
    memory_media_embedding_coverage_parser.add_argument(
        "--max-file-bytes",
        type=int,
        default=20 * 1024 * 1024,
    )
    memory_media_embedding_coverage_parser.add_argument("--mime-type", action="append", default=[])
    memory_media_embedding_coverage_parser.add_argument("--json", action="store_true")
    memory_media_search_parser = memory_subparsers.add_parser(
        "media-search",
        help="search native media embeddings and restore tweet/media source restorations",
    )
    memory_media_search_parser.add_argument("--db", default="runs/x_data.sqlite3")
    memory_media_search_parser.add_argument("--query", required=True)
    memory_media_search_parser.add_argument("--provider", default="gemini")
    memory_media_search_parser.add_argument("--model", default=None)
    memory_media_search_parser.add_argument("--dimensions", type=int, default=None)
    memory_media_search_parser.add_argument(
        "--embedding-profile",
        default="native_multimodal_media",
    )
    memory_media_search_parser.add_argument(
        "--input-template-version",
        default="gemini-media-input-v1",
    )
    memory_media_search_parser.add_argument("--api-key-env", default=None)
    memory_media_search_parser.add_argument("--base-url", default=None)
    memory_media_search_parser.add_argument("--limit", type=int, default=10)
    memory_media_search_parser.add_argument("--timeout-seconds", type=float, default=60.0)
    memory_media_search_parser.add_argument("--json", action="store_true")
    _add_provider_quota_gate_option(memory_media_search_parser)
    _add_api_budget_options(memory_media_search_parser)
    memory_ocr_estimate_parser = memory_subparsers.add_parser(
        "ocr-estimate",
        help="estimate stratified OCR evidence candidates without calling provider OCR APIs",
    )
    memory_ocr_estimate_parser.add_argument("--db", default="runs/x_data.sqlite3")
    memory_ocr_estimate_parser.add_argument("--sample-policy", default="stratified")
    memory_ocr_estimate_parser.add_argument("--limit", type=int, default=100)
    memory_ocr_estimate_parser.add_argument("--max-file-bytes", type=int, default=20 * 1024 * 1024)
    memory_ocr_estimate_parser.add_argument("--media-id", action="append", default=[])
    memory_ocr_estimate_parser.add_argument("--tweet-id", action="append", default=[])
    memory_ocr_estimate_parser.add_argument("--engine-route", action="append", default=[])
    memory_ocr_estimate_parser.add_argument("--json", action="store_true")
    memory_media_role_estimate_parser = memory_subparsers.add_parser(
        "media-role-estimate",
        help="estimate local media roles and evidence actions without writing the database",
    )
    memory_media_role_estimate_parser.add_argument("--db", default="runs/x_data.sqlite3")
    memory_media_role_estimate_parser.add_argument("--limit", type=int, default=100)
    memory_media_role_estimate_parser.add_argument("--json", action="store_true")
    memory_media_role_build_parser = memory_subparsers.add_parser(
        "media-role-build",
        help="store local media role annotations for OCR/caption routing",
    )
    memory_media_role_build_parser.add_argument("--db", default="runs/x_data.sqlite3")
    memory_media_role_build_parser.add_argument("--limit", type=int, default=100)
    memory_media_role_build_parser.add_argument("--json", action="store_true")
    memory_media_role_coverage_parser = memory_subparsers.add_parser(
        "media-role-coverage",
        help="show stored local media role annotations",
    )
    memory_media_role_coverage_parser.add_argument("--db", default="runs/x_data.sqlite3")
    memory_media_role_coverage_parser.add_argument("--json", action="store_true")
    memory_ocr_build_parser = memory_subparsers.add_parser(
        "build-ocr-evidence",
        help="build OCR evidence rows and promote citation-ready OCR chunks",
    )
    memory_ocr_build_parser.add_argument("--db", default="runs/x_data.sqlite3")
    memory_ocr_build_parser.add_argument(
        "--provider",
        choices=["fake", "local", "mistral"],
        default="fake",
        help=(
            "fake is fixture-only; local is deterministic and local-only; mistral requires scoped "
            "provider policy and budget authorization"
        ),
    )
    memory_ocr_build_parser.add_argument(
        "--model",
        default=None,
        help=(
            "OCR model label; defaults to mistral-ocr-2512 for fake/mistral and "
            "local-metadata-ocr-v1 for local"
        ),
    )
    memory_ocr_build_parser.add_argument("--ocr-profile", default="ocr-evidence-v1")
    memory_ocr_build_parser.add_argument("--sample-policy", default="stratified")
    memory_ocr_build_parser.add_argument("--limit", type=int, default=100)
    memory_ocr_build_parser.add_argument("--max-file-bytes", type=int, default=20 * 1024 * 1024)
    memory_ocr_build_parser.add_argument("--media-id", action="append", default=[])
    memory_ocr_build_parser.add_argument("--tweet-id", action="append", default=[])
    memory_ocr_build_parser.add_argument("--engine-route", action="append", default=[])
    memory_ocr_build_parser.add_argument("--timeout-seconds", type=float, default=60.0)
    memory_ocr_build_parser.add_argument("--api-key-env", default=None)
    memory_ocr_build_parser.add_argument("--base-url", default=None)
    memory_ocr_build_parser.add_argument(
        "--no-promote-chunks",
        action="store_true",
        help="store raw OCR rows without creating context chunks/citations",
    )
    memory_ocr_build_parser.add_argument(
        "--allow-real-api",
        action="store_true",
        help="allow provider OCR only with scoped ProviderExecutionPolicy and API Budget Guard",
    )
    memory_ocr_build_parser.add_argument("--json", action="store_true")
    _add_api_budget_options(memory_ocr_build_parser)
    _add_provider_quota_approval_options(memory_ocr_build_parser)
    memory_ocr_coverage_parser = memory_subparsers.add_parser(
        "ocr-coverage",
        help="show OCR evidence rows and promoted OCR context chunks",
    )
    memory_ocr_coverage_parser.add_argument("--db", default="runs/x_data.sqlite3")
    memory_ocr_coverage_parser.add_argument("--json", action="store_true")
    memory_ocr_promote_parser = memory_subparsers.add_parser(
        "ocr-promote-chunks",
        help="promote stored OCR text rows into citation-ready context chunks",
    )
    memory_ocr_promote_parser.add_argument("--db", default="runs/x_data.sqlite3")
    memory_ocr_promote_parser.add_argument("--limit", type=int, default=None)
    memory_ocr_promote_parser.add_argument(
        "--include-corrected",
        action="store_true",
        help="also promote corrected_text helper profiles as inference chunks",
    )
    memory_ocr_promote_parser.add_argument("--json", action="store_true")
    memory_ocr_second_pass_parser = memory_subparsers.add_parser(
        "ocr-second-pass",
        help="mark local OCR second-pass candidates and create local corrected profiles",
    )
    memory_ocr_second_pass_parser.add_argument("--db", default="runs/x_data.sqlite3")
    memory_ocr_second_pass_parser.add_argument("--confidence-threshold", type=float, default=0.45)
    memory_ocr_second_pass_parser.add_argument("--limit", type=int, default=None)
    memory_ocr_second_pass_parser.add_argument(
        "--no-corrected-profile",
        action="store_true",
        help="mark candidates without creating corrected_text profiles",
    )
    memory_ocr_second_pass_parser.add_argument("--json", action="store_true")
    memory_media_observation_add_parser = memory_subparsers.add_parser(
        "media-observation-add",
        help="store a Codex/VLM media observation as an inference annotation",
    )
    memory_media_observation_add_parser.add_argument("--db", default="runs/x_data.sqlite3")
    memory_media_observation_add_parser.add_argument("--media-id", required=True)
    memory_media_observation_add_parser.add_argument("--text-file", required=True)
    memory_media_observation_add_parser.add_argument(
        "--observation-kind",
        default="codex_interpretation",
    )
    memory_media_observation_add_parser.add_argument("--provider", default="codex_interactive")
    memory_media_observation_add_parser.add_argument("--model", default="unspecified")
    memory_media_observation_add_parser.add_argument("--confidence", type=float, default=0.7)
    memory_media_observation_add_parser.add_argument("--prompt", default=None)
    memory_media_observation_add_parser.add_argument("--session-id", default=None)
    memory_media_observation_add_parser.add_argument(
        "--no-promote-chunks",
        action="store_true",
        help="store observation text without creating inference context chunks",
    )
    memory_media_observation_add_parser.add_argument("--json", action="store_true")
    memory_media_observation_import_parser = memory_subparsers.add_parser(
        "media-observation-import",
        help="import Codex/VLM media observations from JSONL",
    )
    memory_media_observation_import_parser.add_argument("--db", default="runs/x_data.sqlite3")
    memory_media_observation_import_parser.add_argument("--jsonl", required=True)
    memory_media_observation_import_parser.add_argument(
        "--no-promote-chunks",
        action="store_true",
    )
    memory_media_observation_import_parser.add_argument("--json", action="store_true")
    memory_media_observation_coverage_parser = memory_subparsers.add_parser(
        "media-observation-coverage",
        help="show stored Codex/VLM media observations",
    )
    memory_media_observation_coverage_parser.add_argument("--db", default="runs/x_data.sqlite3")
    memory_media_observation_coverage_parser.add_argument("--json", action="store_true")
    memory_ocr_search_parser = memory_subparsers.add_parser(
        "ocr-search",
        help="search stored OCR evidence text and restore media bundles",
    )
    memory_ocr_search_parser.add_argument("--db", default="runs/x_data.sqlite3")
    memory_ocr_search_parser.add_argument("--query", required=True)
    memory_ocr_search_parser.add_argument("--limit", type=int, default=10)
    memory_ocr_search_parser.add_argument("--json", action="store_true")
    memory_relations_build_parser = memory_subparsers.add_parser(
        "build-relations",
        help="build relation edges over memory_documents",
    )
    memory_relations_build_parser.add_argument("--db", default="runs/x_data.sqlite3")
    memory_relations_parser = memory_subparsers.add_parser(
        "relations",
        help="show relation edges for a memory document",
    )
    memory_relations_parser.add_argument("--db", default="runs/x_data.sqlite3")
    memory_relations_parser.add_argument("--doc-id", required=True)
    memory_relations_parser.add_argument("--limit", type=int, default=20)
    memory_relations_parser.add_argument("--json", action="store_true")
    memory_judge_relations_parser = memory_subparsers.add_parser(
        "judge-relations",
        help="judge supports/contradicts relation edges from freshness candidates",
    )
    memory_judge_relations_parser.add_argument("--db", default="runs/x_data.sqlite3")
    memory_judge_relations_parser.add_argument(
        "--provider",
        choices=["fake", "gemini", "openai_chat", "openai_compatible"],
        default="fake",
        help="relation judge; fake is deterministic and no-network",
    )
    memory_judge_relations_parser.add_argument("--model", default=None)
    memory_judge_relations_parser.add_argument("--api-key-env", default=None)
    memory_judge_relations_parser.add_argument("--base-url", default=None)
    memory_judge_relations_parser.add_argument(
        "--candidate-relation-type",
        action="append",
        default=None,
        help=(
            "candidate relation type to judge, e.g. obsolete_candidate; "
            "repeat to select multiple"
        ),
    )
    memory_judge_relations_parser.add_argument("--limit", type=int, default=50)
    memory_judge_relations_parser.add_argument("--batch-size", type=int, default=10)
    memory_judge_relations_parser.add_argument("--min-confidence", type=float, default=0.55)
    memory_judge_relations_parser.add_argument(
        "--prompt-version",
        default="memory-relation-judge-v1",
    )
    memory_judge_relations_parser.add_argument("--timeout-seconds", type=float, default=90.0)
    memory_judge_relations_parser.add_argument(
        "--store",
        action=argparse.BooleanOptionalAction,
        default=None,
        help=(
            "store judged supports/contradicts edges and tool-call audit rows; "
            "defaults to no-store for fake providers"
        ),
    )
    memory_judge_relations_parser.add_argument(
        "--allow-fixture-provider",
        action="store_true",
        help="allow storing deterministic fake provider output for tests only",
    )
    memory_judge_relations_parser.add_argument("--json", action="store_true")
    _add_api_budget_options(memory_judge_relations_parser)
    memory_search_parser = memory_subparsers.add_parser(
        "search",
        help=(
            "search memory_documents with lexical, metadata, relation, "
            "and optional semantic ranking"
        ),
    )
    memory_search_parser.add_argument("--db", default="runs/x_data.sqlite3")
    memory_search_parser.add_argument("--query", required=True)
    memory_search_parser.add_argument("--limit", type=int, default=10)
    memory_search_parser.add_argument("--doc-type", default=None)
    memory_search_parser.add_argument("--account", default=None)
    memory_search_parser.add_argument("--intent", default=None)
    memory_search_parser.add_argument("--author-id", default=None)
    memory_search_parser.add_argument("--bookmark-owner-account-id", default=None)
    memory_search_parser.add_argument("--source-kind", default=None)
    memory_search_parser.add_argument("--ownership-kind", default=None)
    memory_search_parser.add_argument("--content-role", default=None)
    memory_search_parser.add_argument("--relation-role", default=None)
    memory_search_parser.add_argument("--language", default=None)
    memory_search_parser.add_argument("--modality-kind", default=None)
    memory_search_parser.add_argument("--sensitivity-kind", default=None)
    memory_search_parser.add_argument("--projection-profile", default=None)
    memory_search_parser.add_argument("--space-id", default=None)
    memory_search_parser.add_argument("--require-projections", action="store_true")
    memory_search_parser.add_argument("--explain-filters", action="store_true")
    memory_search_parser.add_argument("--json", action="store_true")
    memory_search_parser.add_argument(
        "--route",
        default=None,
        choices=MEMORY_SEARCH_ROUTE_CHOICES,
        help="optional route-aware typed retrieval tag to expose engine choices",
    )
    memory_search_parser.add_argument(
        "--semantic-provider",
        default=None,
        choices=MEMORY_EMBEDDING_PROVIDER_CHOICES,
        help=(
            "optional semantic provider: auto, local_hash, openai, gemini, voyage, "
            "cohere, mistral, jina, or openai_compatible"
        ),
    )
    memory_search_parser.add_argument("--semantic-space-id", default=None)
    memory_search_parser.add_argument("--semantic-model", default=None)
    memory_search_parser.add_argument("--semantic-dimensions", type=int, default=None)
    memory_search_parser.add_argument("--semantic-profile", default=None)
    memory_search_parser.add_argument("--semantic-template-version", default=None)
    memory_search_parser.add_argument("--semantic-api-key-env", default=None)
    memory_search_parser.add_argument("--semantic-base-url", default=None)
    memory_search_parser.add_argument("--semantic-weight", type=float, default=3.0)
    memory_search_parser.add_argument("--semantic-candidates", type=int, default=80)
    memory_search_parser.add_argument(
        "--semantic-backend",
        default="sqlite",
        choices=MEMORY_SEMANTIC_BACKEND_CHOICES,
        help="semantic scoring backend: sqlite matrix scan or local vector projection",
    )
    _add_api_budget_options(memory_search_parser)
    memory_plan_parser = memory_subparsers.add_parser(
        "plan",
        help="explain how a natural-language memory query will be interpreted",
    )
    memory_plan_parser.add_argument("--query", required=True)
    memory_evidence_parser = memory_subparsers.add_parser(
        "evidence",
        help="return compact evidence bundle JSON for an AI caller",
    )
    memory_evidence_parser.add_argument("--db", default="runs/x_data.sqlite3")
    memory_evidence_parser.add_argument("--query", required=True)
    memory_evidence_parser.add_argument("--limit", type=int, default=5)
    memory_evidence_parser.add_argument("--doc-type", default=None)
    memory_evidence_parser.add_argument("--account", default=None)
    memory_evidence_parser.add_argument(
        "--semantic-provider",
        default=None,
        choices=MEMORY_EMBEDDING_PROVIDER_CHOICES,
    )
    memory_evidence_parser.add_argument("--semantic-space-id", default=None)
    memory_evidence_parser.add_argument("--semantic-model", default=None)
    memory_evidence_parser.add_argument("--semantic-dimensions", type=int, default=None)
    memory_evidence_parser.add_argument("--semantic-profile", default=None)
    memory_evidence_parser.add_argument("--semantic-template-version", default=None)
    memory_evidence_parser.add_argument("--semantic-api-key-env", default=None)
    memory_evidence_parser.add_argument("--semantic-base-url", default=None)
    memory_evidence_parser.add_argument("--semantic-weight", type=float, default=3.0)
    memory_evidence_parser.add_argument("--semantic-candidates", type=int, default=80)
    memory_evidence_parser.add_argument(
        "--semantic-backend",
        default="sqlite",
        choices=MEMORY_SEMANTIC_BACKEND_CHOICES,
    )
    _add_api_budget_options(memory_evidence_parser)
    memory_context_parser = memory_subparsers.add_parser(
        "context",
        help="build LLM-ready context chunks and citation-ready metadata for a memory query",
    )
    memory_context_parser.add_argument("--db", default="runs/x_data.sqlite3")
    memory_context_parser.add_argument("--query", required=True)
    memory_context_parser.add_argument("--limit", type=int, default=5)
    memory_context_parser.add_argument("--doc-type", default=None)
    memory_context_parser.add_argument("--account", default=None)
    memory_context_parser.add_argument("--intent", default=None)
    memory_context_parser.add_argument("--author-id", default=None)
    memory_context_parser.add_argument("--bookmark-owner-account-id", default=None)
    memory_context_parser.add_argument("--source-kind", default=None)
    memory_context_parser.add_argument("--ownership-kind", default=None)
    memory_context_parser.add_argument("--content-role", default=None)
    memory_context_parser.add_argument("--relation-role", default=None)
    memory_context_parser.add_argument("--language", default=None)
    memory_context_parser.add_argument("--modality-kind", default=None)
    memory_context_parser.add_argument("--sensitivity-kind", default=None)
    memory_context_parser.add_argument("--projection-profile", default=None)
    memory_context_parser.add_argument("--space-id", default=None)
    memory_context_parser.add_argument("--require-projections", action="store_true")
    memory_context_parser.add_argument("--explain-filters", action="store_true")
    memory_context_parser.add_argument(
        "--semantic-provider",
        default=None,
        choices=MEMORY_EMBEDDING_PROVIDER_CHOICES,
    )
    memory_context_parser.add_argument("--semantic-space-id", default=None)
    memory_context_parser.add_argument("--semantic-model", default=None)
    memory_context_parser.add_argument("--semantic-dimensions", type=int, default=None)
    memory_context_parser.add_argument("--semantic-profile", default=None)
    memory_context_parser.add_argument("--semantic-template-version", default=None)
    memory_context_parser.add_argument("--semantic-api-key-env", default=None)
    memory_context_parser.add_argument("--semantic-base-url", default=None)
    memory_context_parser.add_argument("--semantic-weight", type=float, default=3.0)
    memory_context_parser.add_argument("--semantic-candidates", type=int, default=80)
    memory_context_parser.add_argument(
        "--semantic-backend",
        default="sqlite",
        choices=MEMORY_SEMANTIC_BACKEND_CHOICES,
    )
    memory_context_parser.add_argument(
        "--external-run-id",
        default=None,
        help="also extract URLs from this external-search run into the same context bundle",
    )
    memory_context_parser.add_argument(
        "--external-provider",
        choices=["fake", "http", "jina"],
        default="fake",
        help="reader/extract provider for --external-run-id",
    )
    memory_context_parser.add_argument("--external-limit", type=int, default=5)
    memory_context_parser.add_argument("--external-max-chars", type=int, default=4000)
    memory_context_parser.add_argument("--external-timeout-seconds", type=float, default=30.0)
    memory_context_parser.add_argument("--external-user-agent", default="research-x/0.1")
    memory_context_parser.add_argument("--external-max-bytes", type=int, default=2_000_000)
    memory_context_parser.add_argument(
        "--store",
        action=argparse.BooleanOptionalAction,
        default=None,
        help=(
            "store the search run, context chunks, and citation annotations; "
            "defaults to no-store when a fake external provider is used"
        ),
    )
    memory_context_parser.add_argument(
        "--allow-fixture-provider",
        action="store_true",
        help="allow storing deterministic fake provider output for tests only",
    )
    _add_context_budget_options(memory_context_parser)
    _add_api_budget_options(memory_context_parser)
    memory_answer_parser = memory_subparsers.add_parser(
        "answer",
        help="build context chunks and generate a cited answer artifact",
    )
    memory_answer_parser.add_argument("--db", default="runs/x_data.sqlite3")
    memory_answer_parser.add_argument("--query", required=True)
    memory_answer_parser.add_argument("--limit", type=int, default=5)
    memory_answer_parser.add_argument("--doc-type", default=None)
    memory_answer_parser.add_argument("--account", default=None)
    memory_answer_parser.add_argument(
        "--semantic-provider",
        default=None,
        choices=MEMORY_EMBEDDING_PROVIDER_CHOICES,
    )
    memory_answer_parser.add_argument("--semantic-space-id", default=None)
    memory_answer_parser.add_argument("--semantic-model", default=None)
    memory_answer_parser.add_argument("--semantic-dimensions", type=int, default=None)
    memory_answer_parser.add_argument("--semantic-profile", default=None)
    memory_answer_parser.add_argument("--semantic-template-version", default=None)
    memory_answer_parser.add_argument("--semantic-api-key-env", default=None)
    memory_answer_parser.add_argument("--semantic-base-url", default=None)
    memory_answer_parser.add_argument("--semantic-weight", type=float, default=3.0)
    memory_answer_parser.add_argument("--semantic-candidates", type=int, default=80)
    memory_answer_parser.add_argument(
        "--semantic-backend",
        default="sqlite",
        choices=MEMORY_SEMANTIC_BACKEND_CHOICES,
    )
    memory_answer_parser.add_argument(
        "--external-run-id",
        default=None,
        help="also extract URLs from this external-search run into the answer context",
    )
    memory_answer_parser.add_argument(
        "--external-provider",
        choices=["fake", "http", "jina"],
        default="fake",
        help="reader/extract provider for --external-run-id",
    )
    memory_answer_parser.add_argument("--external-limit", type=int, default=5)
    memory_answer_parser.add_argument("--external-max-chars", type=int, default=4000)
    memory_answer_parser.add_argument("--external-timeout-seconds", type=float, default=30.0)
    memory_answer_parser.add_argument("--external-user-agent", default="research-x/0.1")
    memory_answer_parser.add_argument("--external-max-bytes", type=int, default=2_000_000)
    memory_answer_parser.add_argument(
        "--answer-provider",
        choices=["fake", "gemini", "openai_chat", "openai_compatible"],
        default="fake",
        help="answer engine; fake is deterministic and no-network",
    )
    memory_answer_parser.add_argument("--answer-model", default=None)
    memory_answer_parser.add_argument("--answer-api-key-env", default=None)
    memory_answer_parser.add_argument("--answer-base-url", default=None)
    memory_answer_parser.add_argument("--answer-timeout-seconds", type=float, default=90.0)
    memory_answer_parser.add_argument("--prompt-version", default="memory-answer-v1")
    memory_answer_parser.add_argument("--max-context-chunks", type=int, default=8)
    memory_answer_parser.add_argument("--max-context-chars", type=int, default=12_000)
    memory_answer_parser.add_argument(
        "--store",
        action=argparse.BooleanOptionalAction,
        default=None,
        help=(
            "store the search run, context chunks, answer, and answer citations; "
            "defaults to no-store for fake providers"
        ),
    )
    memory_answer_parser.add_argument(
        "--allow-fixture-provider",
        action="store_true",
        help="allow storing deterministic fake provider output for tests only",
    )
    _add_context_budget_options(memory_answer_parser)
    _add_api_budget_options(memory_answer_parser)
    memory_workflow_parser = memory_subparsers.add_parser(
        "workflow",
        help="run a bounded memory workflow with route, steps, and stop reason",
    )
    memory_workflow_parser.add_argument("--db", default="runs/x_data.sqlite3")
    memory_workflow_parser.add_argument("--query", required=True)
    memory_workflow_parser.add_argument("--route", default="auto")
    memory_workflow_parser.add_argument("--limit", type=int, default=5)
    memory_workflow_parser.add_argument("--doc-type", default=None)
    memory_workflow_parser.add_argument("--account", default=None)
    memory_workflow_parser.add_argument("--intent", default=None)
    memory_workflow_parser.add_argument("--author-id", default=None)
    memory_workflow_parser.add_argument("--bookmark-owner-account-id", default=None)
    memory_workflow_parser.add_argument("--source-kind", default=None)
    memory_workflow_parser.add_argument("--ownership-kind", default=None)
    memory_workflow_parser.add_argument("--content-role", default=None)
    memory_workflow_parser.add_argument("--relation-role", default=None)
    memory_workflow_parser.add_argument("--language", default=None)
    memory_workflow_parser.add_argument("--modality-kind", default=None)
    memory_workflow_parser.add_argument("--sensitivity-kind", default=None)
    memory_workflow_parser.add_argument("--projection-profile", default=None)
    memory_workflow_parser.add_argument("--space-id", default=None)
    memory_workflow_parser.add_argument("--require-projections", action="store_true")
    memory_workflow_parser.add_argument("--explain-filters", action="store_true")
    memory_workflow_parser.add_argument("--json", action="store_true")
    memory_workflow_parser.add_argument(
        "--tool-json",
        action="store_true",
        help=(
            "emit the stable AI-callable research_x tool contract instead of "
            "internal workflow JSON"
        ),
    )
    memory_workflow_parser.add_argument(
        "--semantic-provider",
        default=None,
        choices=MEMORY_EMBEDDING_PROVIDER_CHOICES,
    )
    memory_workflow_parser.add_argument("--semantic-space-id", default=None)
    memory_workflow_parser.add_argument("--semantic-model", default=None)
    memory_workflow_parser.add_argument("--semantic-dimensions", type=int, default=None)
    memory_workflow_parser.add_argument("--semantic-profile", default=None)
    memory_workflow_parser.add_argument("--semantic-template-version", default=None)
    memory_workflow_parser.add_argument("--semantic-api-key-env", default=None)
    memory_workflow_parser.add_argument("--semantic-base-url", default=None)
    memory_workflow_parser.add_argument("--semantic-weight", type=float, default=3.0)
    memory_workflow_parser.add_argument("--semantic-candidates", type=int, default=80)
    memory_workflow_parser.add_argument(
        "--semantic-backend",
        default="sqlite",
        choices=MEMORY_SEMANTIC_BACKEND_CHOICES,
    )
    memory_workflow_parser.add_argument(
        "--external-run-id",
        default=None,
        help="also extract URLs from this external-search run into the workflow context",
    )
    memory_workflow_parser.add_argument(
        "--external-provider",
        choices=["fake", "http", "jina"],
        default="http",
        help="reader/extract provider for --external-run-id",
    )
    memory_workflow_parser.add_argument("--external-limit", type=int, default=5)
    memory_workflow_parser.add_argument("--external-max-chars", type=int, default=4000)
    memory_workflow_parser.add_argument("--external-timeout-seconds", type=float, default=30.0)
    memory_workflow_parser.add_argument("--external-user-agent", default="research-x/0.1")
    memory_workflow_parser.add_argument("--external-max-bytes", type=int, default=2_000_000)
    memory_workflow_parser.add_argument(
        "--llm-context-provider",
        choices=["none", "fake", "brave"],
        default="none",
        help="optional LLM-context provider to add external grounding to the workflow context",
    )
    memory_workflow_parser.add_argument(
        "--llm-context-api-key-env",
        default="BRAVE_SEARCH_API_KEY",
    )
    memory_workflow_parser.add_argument("--llm-context-endpoint", default=None)
    memory_workflow_parser.add_argument("--llm-context-country", default=None)
    memory_workflow_parser.add_argument("--llm-context-search-lang", default=None)
    memory_workflow_parser.add_argument("--llm-context-count", type=int, default=20)
    memory_workflow_parser.add_argument("--llm-context-max-urls", type=int, default=20)
    memory_workflow_parser.add_argument("--llm-context-max-tokens", type=int, default=8192)
    memory_workflow_parser.add_argument("--llm-context-max-snippets", type=int, default=50)
    memory_workflow_parser.add_argument("--llm-context-threshold-mode", default="balanced")
    memory_workflow_parser.add_argument(
        "--llm-context-max-tokens-per-url",
        type=int,
        default=4096,
    )
    memory_workflow_parser.add_argument(
        "--llm-context-max-snippets-per-url",
        type=int,
        default=50,
    )
    memory_workflow_parser.add_argument("--llm-context-freshness", default=None)
    memory_workflow_parser.add_argument(
        "--llm-context-enable-local",
        action=argparse.BooleanOptionalAction,
        default=None,
    )
    memory_workflow_parser.add_argument("--llm-context-goggles", default=None)
    memory_workflow_parser.add_argument(
        "--llm-context-max-chars-per-source",
        type=int,
        default=6000,
    )
    memory_workflow_parser.add_argument("--llm-context-timeout-seconds", type=float, default=30.0)
    memory_workflow_parser.add_argument(
        "--answer-provider",
        choices=["none", "fake", "gemini", "openai_chat", "openai_compatible"],
        default="none",
        help="optional answer engine; none only builds workflow context",
    )
    memory_workflow_parser.add_argument("--answer-model", default=None)
    memory_workflow_parser.add_argument("--answer-api-key-env", default=None)
    memory_workflow_parser.add_argument("--answer-base-url", default=None)
    memory_workflow_parser.add_argument("--answer-timeout-seconds", type=float, default=90.0)
    memory_workflow_parser.add_argument("--prompt-version", default="memory-answer-v1")
    memory_workflow_parser.add_argument("--max-context-chunks", type=int, default=8)
    memory_workflow_parser.add_argument("--max-context-chars", type=int, default=12_000)
    memory_workflow_parser.add_argument("--max-steps", type=int, default=4)
    memory_workflow_parser.add_argument(
        "--store",
        action=argparse.BooleanOptionalAction,
        default=None,
        help=(
            "store workflow run, steps, context, and optional answer artifacts; "
            "defaults to no-store for fake providers"
        ),
    )
    memory_workflow_parser.add_argument(
        "--persistence",
        choices=["none", "trace", "artifacts"],
        default=None,
        help=(
            "explicit persistence boundary; none writes nothing, trace writes only "
            "workflow audit rows, and artifacts also writes search/context/citation/answer rows"
        ),
    )
    memory_workflow_parser.add_argument(
        "--allow-fixture-provider",
        action="store_true",
        help="allow storing deterministic fake provider output for tests only",
    )
    _add_context_budget_options(memory_workflow_parser)
    _add_api_budget_options(memory_workflow_parser)
    memory_external_parser = memory_subparsers.add_parser(
        "external-search",
        help="run an external URL-discovery provider and store normalized results",
    )
    memory_external_parser.add_argument("--db", default="runs/x_data.sqlite3")
    memory_external_parser.add_argument("--query", required=True)
    memory_external_parser.add_argument(
        "--provider",
        choices=["fake", "serper", "tavily", "exa", "perplexity", "firecrawl", "searxng"],
        default="fake",
        help="external discovery provider; fake is deterministic and no-network",
    )
    memory_external_parser.add_argument("--limit", type=int, default=5)
    memory_external_parser.add_argument("--api-key-env", default="SERPER_API_KEY")
    memory_external_parser.add_argument("--endpoint", default=None)
    memory_external_parser.add_argument("--country", default=None)
    memory_external_parser.add_argument("--language", default=None)
    memory_external_parser.add_argument("--location", default=None)
    memory_external_parser.add_argument("--timeout-seconds", type=float, default=30.0)
    memory_external_parser.add_argument(
        "--store",
        action=argparse.BooleanOptionalAction,
        default=None,
        help=(
            "store the normalized external run/items in the memory DB; "
            "defaults to no-store for fake providers"
        ),
    )
    memory_external_parser.add_argument(
        "--allow-fixture-provider",
        action="store_true",
        help="allow storing deterministic fake provider output for tests only",
    )
    _add_api_budget_options(memory_external_parser)
    memory_extract_parser = memory_subparsers.add_parser(
        "extract-url",
        help="extract readable text from a URL or external-search run into context chunks",
    )
    memory_extract_parser.add_argument("--db", default="runs/x_data.sqlite3")
    memory_extract_parser.add_argument("--url", default=None, help="single URL to extract")
    memory_extract_parser.add_argument(
        "--external-run-id",
        default=None,
        help="extract URLs from a stored memory external-search run",
    )
    memory_extract_parser.add_argument(
        "--provider",
        choices=["fake", "http", "jina"],
        default="fake",
        help="reader/extract provider; fake is deterministic and no-network",
    )
    memory_extract_parser.add_argument("--query", default=None)
    memory_extract_parser.add_argument("--title", default=None)
    memory_extract_parser.add_argument("--limit", type=int, default=5)
    memory_extract_parser.add_argument("--max-chars", type=int, default=4000)
    memory_extract_parser.add_argument("--timeout-seconds", type=float, default=30.0)
    memory_extract_parser.add_argument("--user-agent", default="research-x/0.1")
    memory_extract_parser.add_argument("--max-bytes", type=int, default=2_000_000)
    memory_extract_parser.add_argument(
        "--store",
        action=argparse.BooleanOptionalAction,
        default=None,
        help=(
            "store tool call, context chunk, and citation annotation rows; "
            "defaults to no-store for fake providers"
        ),
    )
    memory_extract_parser.add_argument(
        "--allow-fixture-provider",
        action="store_true",
        help="allow storing deterministic fake provider output for tests only",
    )
    _add_api_budget_options(memory_extract_parser)
    memory_llm_context_parser = memory_subparsers.add_parser(
        "llm-context",
        help="fetch pre-extracted Web context for LLM grounding",
    )
    memory_llm_context_parser.add_argument("--db", default="runs/x_data.sqlite3")
    memory_llm_context_parser.add_argument("--query", required=True)
    memory_llm_context_parser.add_argument(
        "--provider",
        choices=["fake", "brave"],
        default="brave",
        help="LLM-context provider; brave calls Brave Search LLM Context",
    )
    memory_llm_context_parser.add_argument("--api-key-env", default="BRAVE_SEARCH_API_KEY")
    memory_llm_context_parser.add_argument("--endpoint", default=None)
    memory_llm_context_parser.add_argument("--country", default=None)
    memory_llm_context_parser.add_argument("--search-lang", default=None)
    memory_llm_context_parser.add_argument("--count", type=int, default=20)
    memory_llm_context_parser.add_argument("--max-urls", type=int, default=20)
    memory_llm_context_parser.add_argument("--max-tokens", type=int, default=8192)
    memory_llm_context_parser.add_argument("--max-snippets", type=int, default=50)
    memory_llm_context_parser.add_argument("--threshold-mode", default="balanced")
    memory_llm_context_parser.add_argument("--max-tokens-per-url", type=int, default=4096)
    memory_llm_context_parser.add_argument("--max-snippets-per-url", type=int, default=50)
    memory_llm_context_parser.add_argument("--freshness", default=None)
    memory_llm_context_parser.add_argument(
        "--enable-local",
        action=argparse.BooleanOptionalAction,
        default=None,
    )
    memory_llm_context_parser.add_argument("--goggles", default=None)
    memory_llm_context_parser.add_argument("--max-chars-per-source", type=int, default=6000)
    memory_llm_context_parser.add_argument("--timeout-seconds", type=float, default=30.0)
    memory_llm_context_parser.add_argument(
        "--store",
        action=argparse.BooleanOptionalAction,
        default=None,
        help=(
            "store tool call, external context chunks, and citation annotations; "
            "defaults to no-store for fake providers"
        ),
    )
    memory_llm_context_parser.add_argument(
        "--allow-fixture-provider",
        action="store_true",
        help="allow storing deterministic fake provider output for tests only",
    )
    _add_api_budget_options(memory_llm_context_parser)
    memory_feedback_parser = memory_subparsers.add_parser(
        "feedback",
        help="record search-result feedback for later ranking improvements",
    )
    memory_feedback_parser.add_argument("--db", default="runs/x_data.sqlite3")
    memory_feedback_parser.add_argument("--query", required=True)
    memory_feedback_parser.add_argument("--doc-id", required=True)
    memory_feedback_parser.add_argument(
        "--label",
        required=True,
        choices=[
            "useful",
            "not_useful",
            "wrong_topic",
            "too_old",
            "missing_context",
            "good_for_skill",
            "bad_skill_route",
        ],
    )
    memory_feedback_parser.add_argument("--note", default=None)
    memory_feedback_parser.add_argument(
        "--route",
        default=None,
        help="optional workflow route this feedback applies to",
    )
    memory_governance_parser = memory_subparsers.add_parser(
        "governance",
        help="manage source-backed memory governance records",
    )
    memory_governance_subparsers = memory_governance_parser.add_subparsers(
        dest="governance_command",
        required=True,
    )
    governance_add_parser = memory_governance_subparsers.add_parser(
        "add",
        help="add a source-backed governance record",
    )
    governance_add_parser.add_argument("--db", default="runs/x_data.sqlite3")
    governance_add_parser.add_argument(
        "--type",
        required=True,
        choices=["profile", "contradiction", "retention", "forgetting"],
    )
    governance_add_parser.add_argument("--subject-kind", required=True)
    governance_add_parser.add_argument("--subject-id", required=True)
    governance_add_parser.add_argument("--statement", required=True)
    governance_add_parser.add_argument("--source-kind", required=True)
    governance_add_parser.add_argument("--source-id", required=True)
    governance_add_parser.add_argument("--source-url", default=None)
    governance_add_parser.add_argument("--source-hash", default=None)
    governance_add_parser.add_argument("--source-anchor", action="append", default=[])
    governance_add_parser.add_argument("--metadata", action="append", default=[])
    governance_add_parser.add_argument("--confidence", type=float, default=1.0)
    governance_add_parser.add_argument("--retention-policy", default="source_lifetime")
    governance_add_parser.add_argument("--expires-at", default=None)
    governance_add_parser.add_argument("--json", action="store_true")
    governance_tombstone_parser = memory_governance_subparsers.add_parser(
        "tombstone",
        help="add an active tombstone for a local artifact",
    )
    governance_tombstone_parser.add_argument("--db", default="runs/x_data.sqlite3")
    governance_tombstone_parser.add_argument("--artifact-kind", required=True)
    governance_tombstone_parser.add_argument("--artifact-id", required=True)
    governance_tombstone_parser.add_argument("--reason", required=True)
    governance_tombstone_parser.add_argument("--source-kind", required=True)
    governance_tombstone_parser.add_argument("--source-id", required=True)
    governance_tombstone_parser.add_argument("--source-url", default=None)
    governance_tombstone_parser.add_argument("--source-hash", default=None)
    governance_tombstone_parser.add_argument("--source-anchor", action="append", default=[])
    governance_tombstone_parser.add_argument("--metadata", action="append", default=[])
    governance_tombstone_parser.add_argument(
        "--retention-policy",
        default="suppress_until_restored",
    )
    governance_tombstone_parser.add_argument("--json", action="store_true")
    governance_restore_parser = memory_governance_subparsers.add_parser(
        "restore",
        help="restore a tombstone/governance record by marking it inactive",
    )
    governance_restore_parser.add_argument("--db", default="runs/x_data.sqlite3")
    governance_restore_parser.add_argument("--record-id", required=True)
    governance_restore_parser.add_argument("--reason", required=True)
    governance_restore_parser.add_argument("--json", action="store_true")
    governance_list_parser = memory_governance_subparsers.add_parser(
        "list",
        help="list source-backed governance records",
    )
    governance_list_parser.add_argument("--db", default="runs/x_data.sqlite3")
    governance_list_parser.add_argument(
        "--type",
        choices=["profile", "contradiction", "retention", "forgetting", "tombstone"],
        default=None,
    )
    governance_list_parser.add_argument("--subject-kind", default=None)
    governance_list_parser.add_argument("--subject-id", default=None)
    governance_list_parser.add_argument("--include-inactive", action="store_true")
    governance_list_parser.add_argument("--limit", type=int, default=50)
    governance_list_parser.add_argument("--json", action="store_true")
    governance_check_parser = memory_governance_subparsers.add_parser(
        "check",
        help="check whether an artifact is actively tombstoned",
    )
    governance_check_parser.add_argument("--db", default="runs/x_data.sqlite3")
    governance_check_parser.add_argument("--artifact-kind", required=True)
    governance_check_parser.add_argument("--artifact-id", required=True)
    governance_check_parser.add_argument("--json", action="store_true")
    memory_export_parser = memory_subparsers.add_parser(
        "export-corpus2skill",
        help="export memory_documents to Corpus2Skill-compatible JSONL",
    )
    memory_export_parser.add_argument("--db", default="runs/x_data.sqlite3")
    memory_export_parser.add_argument("--out", default=None)
    memory_export_parser.add_argument(
        "--doc-type",
        action="append",
        default=[],
        help="limit export to this memory_documents.doc_type; repeatable",
    )
    memory_export_parser.add_argument(
        "--bundle-dir",
        default=None,
        help="write corpus.jsonl plus manifest.json for the official Corpus2Skill compiler",
    )
    memory_export_parser.add_argument(
        "--openai-agent-yaml",
        action="store_true",
        help="include advisory agents/openai.yaml metadata in the bundle",
    )
    memory_export_parser.add_argument(
        "--hook-advisory",
        action="store_true",
        help="include an inert hook advisory note in the bundle",
    )
    memory_export_parser.add_argument(
        "--openai-agent-name",
        default=None,
        help="skill-style name referenced by the advisory OpenAI agent metadata",
    )
    memory_export_parser.add_argument("--limit", type=int, default=None)
    memory_eval_parser = memory_subparsers.add_parser(
        "eval",
        help="run fixed evaluation queries against the memory search layer",
    )
    memory_eval_parser.add_argument("--db", default="runs/x_data.sqlite3")
    memory_eval_parser.add_argument(
        "--cases",
        default=None,
        help="optional JSON/JSONL eval cases file; omit to use built-in route cases",
    )
    memory_eval_parser.add_argument("--limit", type=int, default=3)
    memory_eval_parser.add_argument(
        "--semantic-provider",
        default=None,
        choices=MEMORY_EMBEDDING_PROVIDER_CHOICES,
    )
    memory_eval_parser.add_argument("--semantic-space-id", default=None)
    memory_eval_parser.add_argument("--semantic-model", default=None)
    memory_eval_parser.add_argument("--semantic-dimensions", type=int, default=None)
    memory_eval_parser.add_argument("--semantic-profile", default=None)
    memory_eval_parser.add_argument("--semantic-template-version", default=None)
    memory_eval_parser.add_argument("--semantic-api-key-env", default=None)
    memory_eval_parser.add_argument("--semantic-base-url", default=None)
    memory_eval_parser.add_argument("--semantic-weight", type=float, default=3.0)
    memory_eval_parser.add_argument("--semantic-candidates", type=int, default=80)
    memory_eval_parser.add_argument(
        "--semantic-backend",
        default="sqlite",
        choices=MEMORY_SEMANTIC_BACKEND_CHOICES,
    )
    memory_eval_parser.add_argument(
        "--answer-provider",
        choices=["none", "fake", "gemini", "openai_chat", "openai_compatible"],
        default="fake",
        help="no-store answer wiring check for eval cases",
    )
    memory_eval_parser.add_argument("--answer-model", default=None)
    memory_eval_parser.add_argument("--answer-api-key-env", default=None)
    memory_eval_parser.add_argument("--answer-base-url", default=None)
    memory_eval_parser.add_argument("--answer-timeout-seconds", type=float, default=90.0)
    memory_eval_parser.add_argument(
        "--store",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="store eval run/results for later comparison",
    )
    memory_eval_parser.add_argument("--json", action="store_true")
    memory_eval_parser.add_argument(
        "--strict",
        action="store_true",
        help="return a non-zero exit code when any eval case is not ok",
    )
    _add_api_budget_options(memory_eval_parser)
    memory_portfolio_eval_parser = memory_subparsers.add_parser(
        "portfolio-eval",
        help=(
            "compare lexical, source-ref, workflow, and candidate semantic arms "
            "without promoting multi-provider search to production"
        ),
    )
    memory_portfolio_eval_parser.add_argument("--db", default="runs/x_data.sqlite3")
    memory_portfolio_eval_parser.add_argument(
        "--cases",
        default=None,
        help="optional JSON/JSONL eval cases file; omit to use built-in route cases",
    )
    memory_portfolio_eval_parser.add_argument("--limit", type=int, default=5)
    memory_portfolio_eval_parser.add_argument(
        "--case-limit",
        type=int,
        default=None,
        help="optional maximum number of eval cases to run; useful for bounded preflight",
    )
    memory_portfolio_eval_parser.add_argument(
        "--fast",
        action="store_true",
        help="run a lightweight local-arm subset for quick offline preflight",
    )
    memory_portfolio_eval_parser.add_argument("--arm-limit", type=int, default=20)
    memory_portfolio_eval_parser.add_argument("--rrf-k", type=float, default=60.0)
    memory_portfolio_eval_parser.add_argument(
        "--fusion-mode",
        choices=["guarded_rrf", "rrf"],
        default="guarded_rrf",
        help="guarded_rrf preserves lexical/multi-arm agreement before raw RRF-only candidates",
    )
    memory_portfolio_eval_parser.add_argument(
        "--min-agreement",
        type=int,
        default=2,
        help="minimum distinct arms needed for non-lexical candidates in guarded_rrf",
    )
    memory_portfolio_eval_parser.add_argument(
        "--semantic-spec",
        action="append",
        default=[],
        help=(
            "candidate semantic arm as key=value CSV, e.g. "
            "provider=gemini,model=gemini-embedding-2,dimensions=768,"
            "profile=general_memory,name=gemini_general,mode=semantic_only,"
            "weight=1.0; repeatable"
        ),
    )
    memory_portfolio_eval_parser.add_argument(
        "--reranker-spec",
        action="append",
        default=[],
        help=(
            "candidate rerank arm as key=value CSV, e.g. "
            "provider=cohere,model=rerank-v4.0-pro,name=cohere_v4,top_n=5,"
            "candidate_limit=20; repeatable"
        ),
    )
    memory_portfolio_eval_parser.add_argument(
        "--strategy",
        action="append",
        default=[],
        help=(
            "add candidate semantic arms from a named retrieval/evidence strategy, "
            "for example api_embedding_portfolio, general_memory, jp_multilingual, "
            "learning_long, code_technical, or media_text_bridge; repeatable. "
            "Non-semantic strategies such as corpus2skill_navigation and "
            "bounded_workflow_orchestration intentionally add no semantic arms"
        ),
    )
    memory_portfolio_eval_parser.add_argument("--json", action="store_true")
    memory_portfolio_eval_parser.add_argument(
        "--strict",
        action="store_true",
        help=(
            "return a non-zero exit code when cases fail, candidate arms error, "
            "or promotion blockers remain"
        ),
    )
    _add_api_budget_options(memory_portfolio_eval_parser)
    memory_eval_runs_parser = memory_subparsers.add_parser(
        "eval-runs",
        help="list stored memory eval runs",
    )
    memory_eval_runs_parser.add_argument("--db", default="runs/x_data.sqlite3")
    memory_eval_runs_parser.add_argument("--limit", type=int, default=20)
    memory_eval_runs_parser.add_argument("--json", action="store_true")
    memory_eval_show_parser = memory_subparsers.add_parser(
        "eval-show",
        help="show one stored memory eval run and its case results",
    )
    memory_eval_show_parser.add_argument("--db", default="runs/x_data.sqlite3")
    memory_eval_show_parser.add_argument("--run-id", required=True)
    memory_eval_show_parser.add_argument("--json", action="store_true")
    memory_research_runs_parser = memory_subparsers.add_parser(
        "research-runs",
        help="list recent search, workflow, and objective route traces",
    )
    memory_research_runs_parser.add_argument("--db", default="runs/x_data.sqlite3")
    memory_research_runs_parser.add_argument(
        "--kind",
        choices=["all", "objective", "workflow", "search"],
        default="all",
    )
    memory_research_runs_parser.add_argument("--limit", type=int, default=20)
    memory_research_runs_parser.add_argument("--json", action="store_true")
    memory_show_run_parser = memory_subparsers.add_parser(
        "show-run",
        help="show one stored search/workflow/objective trace with gaps and source state",
    )
    memory_show_run_parser.add_argument("--db", default="runs/x_data.sqlite3")
    memory_show_run_parser.add_argument("--run-id", required=True)
    memory_show_run_parser.add_argument(
        "--kind",
        choices=["auto", "objective", "workflow", "search"],
        default="auto",
    )
    memory_show_run_parser.add_argument("--json", action="store_true")
    memory_question_types_parser = memory_subparsers.add_parser(
        "question-types",
        help="list memory-search question types used to broaden eval coverage",
    )
    memory_question_types_parser.add_argument("--json", action="store_true")
    memory_objective_routes_parser = memory_subparsers.add_parser(
        "objective-routes",
        help="plan primary, fallback, and escalation routes for one objective query",
    )
    memory_objective_routes_parser.add_argument("--db", default="runs/x_data.sqlite3")
    memory_objective_routes_parser.add_argument("--query", required=True)
    memory_objective_routes_parser.add_argument("--route", default="auto")
    memory_objective_routes_parser.add_argument("--budget-policy", default="default")
    memory_objective_routes_parser.add_argument(
        "--output-mode",
        choices=[
            "explore",
            "collect",
            "working_note",
            "synthesize",
            "evidence_package",
            "answer",
        ],
        default="explore",
    )
    memory_objective_routes_parser.add_argument("--store", action="store_true")
    memory_objective_routes_parser.add_argument("--json", action="store_true")
    memory_objective_execute_parser = memory_subparsers.add_parser(
        "objective-execute",
        help="execute ObjectiveRoutePlan over no-spend local evidence arms",
    )
    memory_objective_execute_parser.add_argument("--db", default="runs/x_data.sqlite3")
    memory_objective_execute_parser.add_argument("--query", required=True)
    memory_objective_execute_parser.add_argument("--route", default="auto")
    memory_objective_execute_parser.add_argument("--budget-policy", default="default")
    memory_objective_execute_parser.add_argument(
        "--output-mode",
        choices=[
            "explore",
            "collect",
            "working_note",
            "synthesize",
            "evidence_package",
            "answer",
        ],
        default="explore",
    )
    memory_objective_execute_parser.add_argument("--limit", type=int, default=5)
    memory_objective_execute_parser.add_argument("--account", default=None)
    memory_objective_execute_parser.add_argument("--max-route-arms", type=int, default=4)
    memory_objective_execute_parser.add_argument(
        "--ocr-mode",
        choices=["off", "stored", "fake"],
        default="stored",
        help="media route OCR handling; fake runs no-network candidate-set OCR explicitly",
    )
    memory_objective_execute_parser.add_argument("--ocr-limit", type=int, default=10)
    memory_objective_execute_parser.add_argument(
        "--ocr-sample-policy",
        default="candidate_set",
    )
    memory_objective_execute_parser.add_argument(
        "--ocr-max-file-bytes",
        type=int,
        default=20 * 1024 * 1024,
    )
    memory_objective_execute_parser.add_argument(
        "--store",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="store objective route run/step trace rows",
    )
    memory_objective_execute_parser.add_argument("--json", action="store_true")
    memory_final_skeleton_parser = memory_subparsers.add_parser(
        "final-skeleton-preflight",
        help="write local final skeleton artifacts up to the provider-policy gate",
    )
    memory_final_skeleton_parser.add_argument("--db", default="runs/x_data.sqlite3")
    memory_final_skeleton_parser.add_argument(
        "--query",
        default=DEFAULT_FINAL_SKELETON_PREFLIGHT_QUERY,
        help="query frame used for local preflight planning",
    )
    memory_final_skeleton_parser.add_argument("--route", default="auto")
    memory_final_skeleton_parser.add_argument("--limit", type=int, default=10)
    memory_final_skeleton_parser.add_argument(
        "--store",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="store local final skeleton preflight artifacts",
    )
    memory_final_skeleton_parser.add_argument("--json", action="store_true")
    memory_retrieval_text_parser = memory_subparsers.add_parser(
        "build-retrieval-text",
        help="build no-spend retrieval-text projections for FTS recall",
    )
    memory_retrieval_text_parser.add_argument("--db", default="runs/x_data.sqlite3")
    memory_retrieval_text_parser.add_argument(
        "--profile",
        action="append",
        default=[],
        choices=["raw_compact", "contextual_bm25"],
        help="retrieval text profile to build; repeatable",
    )
    memory_retrieval_text_parser.add_argument("--limit", type=int, default=None)
    memory_retrieval_text_parser.add_argument(
        "--rebuild",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="replace existing rows for the selected profiles before rebuilding",
    )
    memory_retrieval_text_parser.add_argument("--json", action="store_true")
    memory_retrieval_text_coverage_parser = memory_subparsers.add_parser(
        "retrieval-text-coverage",
        help="show retrieval-text projection coverage and staleness",
    )
    memory_retrieval_text_coverage_parser.add_argument("--db", default="runs/x_data.sqlite3")
    memory_retrieval_text_coverage_parser.add_argument("--json", action="store_true")
    memory_retrieval_strategies_parser = memory_subparsers.add_parser(
        "retrieval-strategies",
        help="list route/retrieval/evidence strategies for portfolio experiments",
    )
    memory_retrieval_strategies_parser.add_argument("--query", default=None)
    memory_retrieval_strategies_parser.add_argument(
        "--question-type",
        action="append",
        default=[],
        help="filter/recommend strategies by question type; repeatable",
    )
    memory_retrieval_strategies_parser.add_argument(
        "--strategy",
        action="append",
        default=[],
        help="show specific strategy id; repeatable",
    )
    memory_retrieval_strategies_parser.add_argument("--json", action="store_true")
    memory_embedding_strategies_parser = memory_subparsers.add_parser(
        "embedding-strategies",
        help="deprecated alias of retrieval-strategies",
    )
    memory_embedding_strategies_parser.add_argument("--query", default=None)
    memory_embedding_strategies_parser.add_argument(
        "--question-type",
        action="append",
        default=[],
        help="filter/recommend strategies by question type; repeatable",
    )
    memory_embedding_strategies_parser.add_argument(
        "--strategy",
        action="append",
        default=[],
        help="show specific strategy id; repeatable",
    )
    memory_embedding_strategies_parser.add_argument("--json", action="store_true")
    memory_rerank_parser = memory_subparsers.add_parser(
        "rerank",
        help="rerank restored evidence-bundle candidates with fake or real reranker providers",
    )
    memory_rerank_parser.add_argument("--db", default="runs/x_data.sqlite3")
    memory_rerank_parser.add_argument("--query", required=True)
    memory_rerank_parser.add_argument("--limit", type=int, default=20)
    memory_rerank_parser.add_argument("--top-n", type=int, default=5)
    memory_rerank_parser.add_argument(
        "--provider",
        choices=["fake", "voyage", "cohere", "jina"],
        default="fake",
    )
    memory_rerank_parser.add_argument("--model", default=None)
    memory_rerank_parser.add_argument("--api-key-env", default=None)
    memory_rerank_parser.add_argument("--base-url", default=None)
    memory_rerank_parser.add_argument("--timeout-seconds", type=float, default=60.0)
    memory_rerank_parser.add_argument(
        "--store",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="store reranker tool-call metadata; defaults to no-store for fake providers",
    )
    memory_rerank_parser.add_argument(
        "--allow-fixture-provider",
        action="store_true",
        help="allow storing deterministic fake provider output for tests only",
    )
    memory_rerank_parser.add_argument("--json", action="store_true")
    _add_api_budget_options(memory_rerank_parser)

    adapters_parser = subparsers.add_parser("adapters", help="list known adapter ids")
    adapters_parser.add_argument(
        "--details",
        action="store_true",
        help="show researched adapter details",
    )
    adapters_parser.add_argument(
        "--json",
        action="store_true",
        help="emit researched adapter details as JSON",
    )

    bookmarks_parser = subparsers.add_parser(
        "bookmarks",
        help="fetch logged-in X bookmarks and group them with AI classification",
    )
    bookmarks_parser.add_argument("--out", required=True, help="output directory")
    bookmarks_parser.add_argument(
        "--account",
        default=None,
        help="account id whose bookmark timeline should be fetched",
    )
    bookmarks_parser.add_argument("--limit", type=int, default=100, help="bookmark item limit")
    bookmarks_parser.add_argument(
        "--all",
        action="store_true",
        help="attempt to fetch the full bookmark timeline with a high cursor limit",
    )
    bookmarks_parser.add_argument(
        "--storage-state",
        default=None,
        help="Playwright storage state for the logged-in X account",
    )
    bookmarks_parser.add_argument(
        "--db",
        default=None,
        help="SQLite database path for canonical tweets/bookmarks",
    )
    bookmarks_parser.add_argument(
        "--headless",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="run the browser headlessly",
    )
    bookmarks_parser.add_argument(
        "--timeout-ms",
        type=float,
        default=45000,
        help="browser timeout in milliseconds",
    )
    bookmarks_parser.add_argument(
        "--max-scroll-steps",
        type=int,
        default=20,
        help="maximum bookmark timeline scroll steps",
    )
    bookmarks_parser.add_argument(
        "--classify",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="classify fetched bookmarks with the configured model",
    )
    bookmarks_parser.add_argument(
        "--model",
        default="gpt-4o-mini",
        help="model used for bookmark classification",
    )
    bookmarks_parser.add_argument(
        "--classifier-provider",
        default="openai_responses",
        help=(
            "classifier provider: openai_responses, openai_compatible, "
            "qwen, kimi, glm, gemini, or openai_chat"
        ),
    )
    bookmarks_parser.add_argument(
        "--api-base-url",
        default=None,
        help="OpenAI-compatible API base URL for non-Responses classifiers",
    )
    bookmarks_parser.add_argument(
        "--api-key-env",
        default="OPENAI_API_KEY",
        help="environment variable containing the OpenAI API key",
    )
    bookmarks_parser.add_argument(
        "--categories",
        default=None,
        help="optional TOML taxonomy with [[categories]] entries",
    )
    bookmarks_parser.add_argument(
        "--batch-size",
        type=int,
        default=20,
        help="number of bookmarks per AI classification request",
    )
    bookmarks_parser.add_argument(
        "--reasoning-effort",
        default=None,
        help="Gemini/OpenAI-compatible reasoning effort: default, minimal, low, medium, or high",
    )
    bookmarks_parser.add_argument(
        "--min-successful-providers",
        type=int,
        default=1,
        help="minimum successful bookmark providers before stopping the chain",
    )
    bookmarks_parser.add_argument(
        "--download-media",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="download tweet image media into the output media directory",
    )
    bookmarks_parser.add_argument(
        "--media-download-policy",
        choices=MEDIA_DOWNLOAD_POLICY_CHOICES,
        default=None,
        help="media handling contract; overrides --download-media when set",
    )
    bookmarks_parser.add_argument(
        "--media-timeout-seconds",
        type=float,
        default=30.0,
        help="timeout for each media download",
    )
    _add_api_budget_options(bookmarks_parser)

    tweets_parser = subparsers.add_parser(
        "tweets",
        help="fetch profile/search/url tweets and store them in the shared X database",
    )
    tweets_parser.add_argument("--out", required=True, help="output directory")
    tweets_parser.add_argument(
        "--kind",
        choices=["profile", "search", "url"],
        default="profile",
        help="tweet acquisition target kind",
    )
    tweets_parser.add_argument("--value", required=True, help="target value, e.g. @user")
    tweets_parser.add_argument("--limit", type=int, default=100, help="tweet item limit")
    tweets_parser.add_argument("--account", default=None, help="account id for auth/session")
    tweets_parser.add_argument("--storage-state", default=None, help="Playwright storage state")
    tweets_parser.add_argument("--db", default=None, help="SQLite database path")
    tweets_parser.add_argument(
        "--headless",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="run browser providers headlessly",
    )
    tweets_parser.add_argument("--timeout-ms", type=float, default=45000)
    tweets_parser.add_argument("--max-scroll-steps", type=int, default=20)
    tweets_parser.add_argument("--min-successful-providers", type=int, default=1)
    tweets_parser.add_argument(
        "--download-media",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="download media for fetched tweets",
    )
    tweets_parser.add_argument(
        "--media-download-policy",
        choices=MEDIA_DOWNLOAD_POLICY_CHOICES,
        default=None,
        help="media handling contract; overrides --download-media when set",
    )
    tweets_parser.add_argument("--media-timeout-seconds", type=float, default=30.0)
    tweets_parser.add_argument(
        "--classify",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="classify fetched tweets with the configured model",
    )
    tweets_parser.add_argument("--model", default="gpt-4o-mini")
    tweets_parser.add_argument(
        "--classifier-provider",
        default="openai_responses",
        help="classifier provider: openai_responses, openai_compatible, qwen, kimi, glm, gemini",
    )
    tweets_parser.add_argument("--api-base-url", default=None)
    tweets_parser.add_argument("--api-key-env", default="OPENAI_API_KEY")
    tweets_parser.add_argument("--categories", default=None)
    tweets_parser.add_argument("--batch-size", type=int, default=20)
    tweets_parser.add_argument("--reasoning-effort", default=None)
    _add_api_budget_options(tweets_parser)

    stages_parser = subparsers.add_parser(
        "tweet-stages",
        help="run staged tweet acquisition limits and discard each stage by default",
    )
    stages_parser.add_argument("--out", required=True, help="output directory")
    stages_parser.add_argument("--kind", choices=["profile", "search", "url"], default="profile")
    stages_parser.add_argument("--value", required=True, help="target value, e.g. @user")
    stages_parser.add_argument(
        "--stage-limits",
        default="100,200,300,400",
        help="comma-separated staged limits",
    )
    stages_parser.add_argument("--account", default=None, help="account id for auth/session")
    stages_parser.add_argument("--storage-state", default=None, help="Playwright storage state")
    stages_parser.add_argument(
        "--discard-stage-data",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="delete per-stage pipeline outputs after each stage",
    )
    stages_parser.add_argument("--headless", action=argparse.BooleanOptionalAction, default=True)
    stages_parser.add_argument("--timeout-ms", type=float, default=45000)
    stages_parser.add_argument("--max-scroll-steps", type=int, default=20)
    stages_parser.add_argument("--min-successful-providers", type=int, default=1)

    accounts_parser = subparsers.add_parser("accounts", help="manage local account profiles")
    accounts_subparsers = accounts_parser.add_subparsers(dest="accounts_command", required=True)
    accounts_add_parser = accounts_subparsers.add_parser(
        "add",
        help="register non-password account metadata for account-scoped sessions",
    )
    accounts_add_parser.add_argument("--account", required=True, help="account id, e.g. my_account")
    accounts_add_parser.add_argument("--screen-name", default=None)
    accounts_add_parser.add_argument("--user-id", default=None)
    accounts_add_parser.add_argument("--display-name", default=None)
    accounts_add_parser.add_argument("--url", default=None)

    auth_parser = subparsers.add_parser("auth", help="capture authorized sessions")
    auth_subparsers = auth_parser.add_subparsers(dest="auth_command", required=True)
    playwright_auth_parser = auth_subparsers.add_parser(
        "playwright",
        help="open visible Chromium and save X storage state after manual login",
    )
    playwright_auth_parser.add_argument("--account", default=None, help="account id to save under")
    playwright_auth_parser.add_argument(
        "--storage-state",
        default=None,
        help="path to write Playwright storage state JSON",
    )
    playwright_auth_parser.add_argument(
        "--user-data-dir",
        default=None,
        help="persistent Chromium profile directory for manual login",
    )
    playwright_auth_parser.add_argument(
        "--channel",
        choices=["chrome", "msedge", "chromium", "chrome-beta", "msedge-beta", "msedge-dev"],
        default=None,
        help="installed Chromium browser channel to launch",
    )
    playwright_auth_parser.add_argument(
        "--executable-path",
        default=None,
        help="explicit Chromium/Chrome/Edge executable path",
    )
    playwright_auth_parser.add_argument(
        "--start-url",
        default="https://x.com",
        help="URL to open for manual login",
    )
    playwright_auth_parser.add_argument(
        "--timeout-seconds",
        type=float,
        default=900,
        help="maximum time to wait for manual login",
    )
    cookie_auth_parser = auth_subparsers.add_parser(
        "cookies",
        help="write Playwright storage state from auth_token and ct0 env values",
    )
    cookie_auth_parser.add_argument("--account", default=None, help="account id to save under")
    cookie_auth_parser.add_argument(
        "--storage-state",
        default=None,
        help="path to write Playwright storage state JSON",
    )
    cookie_auth_parser.add_argument(
        "--auth-token-env",
        default="RESEARCH_X_X_AUTH_TOKEN",
        help="env var containing X auth_token cookie value",
    )
    cookie_auth_parser.add_argument(
        "--ct0-env",
        default="RESEARCH_X_X_CT0",
        help="env var containing X ct0 cookie value",
    )
    cdp_auth_parser = auth_subparsers.add_parser(
        "cdp",
        help="connect to an existing Chromium browser over CDP and export storage state",
    )
    cdp_auth_parser.add_argument("--account", default=None, help="account id to save under")
    cdp_auth_parser.add_argument(
        "--storage-state",
        default=None,
        help="path to write Playwright storage state JSON",
    )
    cdp_auth_parser.add_argument(
        "--endpoint-url",
        default="http://localhost:9222",
        help="Chrome DevTools Protocol endpoint URL",
    )
    cdp_auth_parser.add_argument(
        "--timeout-seconds",
        type=float,
        default=900,
        help="maximum time to wait for a CDP browser with X auth cookies",
    )
    cdp_auth_parser.add_argument(
        "--no-defaults",
        action="store_true",
        default=False,
        help="avoid Playwright default context overrides when attaching to a daily browser",
    )
    credentials_auth_parser = auth_subparsers.add_parser(
        "credentials",
        help="log in to X automatically with username/password env values",
    )
    credentials_auth_parser.add_argument("--account", default=None, help="account id to save under")
    credentials_auth_parser.add_argument("--storage-state", default=None)
    credentials_auth_parser.add_argument("--user-data-dir", default=None)
    credentials_auth_parser.add_argument("--username-env", default="RESEARCH_X_X_USERNAME")
    credentials_auth_parser.add_argument("--password-env", default="RESEARCH_X_X_PASSWORD")
    credentials_auth_parser.add_argument(
        "--email-or-phone-env",
        default="RESEARCH_X_X_EMAIL_OR_PHONE",
    )
    credentials_auth_parser.add_argument(
        "--verification-code-env",
        default="RESEARCH_X_X_VERIFICATION_CODE",
    )
    credentials_auth_parser.add_argument("--totp-secret-env", default="RESEARCH_X_X_TOTP_SECRET")
    credentials_auth_parser.add_argument(
        "--channel",
        choices=["chrome", "msedge", "chromium", "chrome-beta", "msedge-beta", "msedge-dev"],
        default=None,
    )
    credentials_auth_parser.add_argument("--executable-path", default=None)
    credentials_auth_parser.add_argument(
        "--start-url",
        default="https://x.com/i/flow/login",
    )
    credentials_auth_parser.add_argument(
        "--headless",
        action=argparse.BooleanOptionalAction,
        default=True,
    )
    credentials_auth_parser.add_argument("--user-agent", default=None)
    credentials_auth_parser.add_argument("--timeout-seconds", type=float, default=180)
    auto_auth_parser = auth_subparsers.add_parser(
        "auto",
        help="try all non-interactive auth routes: existing state, cookie env, credentials, CDP",
    )
    auto_auth_parser.add_argument("--account", default=None, help="account id to save under")
    auto_auth_parser.add_argument("--storage-state", default=None)
    auto_auth_parser.add_argument("--user-data-dir", default=None)
    auto_auth_parser.add_argument("--username-env", default="RESEARCH_X_X_USERNAME")
    auto_auth_parser.add_argument("--password-env", default="RESEARCH_X_X_PASSWORD")
    auto_auth_parser.add_argument("--email-or-phone-env", default="RESEARCH_X_X_EMAIL_OR_PHONE")
    auto_auth_parser.add_argument(
        "--verification-code-env",
        default="RESEARCH_X_X_VERIFICATION_CODE",
    )
    auto_auth_parser.add_argument("--totp-secret-env", default="RESEARCH_X_X_TOTP_SECRET")
    auto_auth_parser.add_argument("--auth-token-env", default="RESEARCH_X_X_AUTH_TOKEN")
    auto_auth_parser.add_argument("--ct0-env", default="RESEARCH_X_X_CT0")
    auto_auth_parser.add_argument("--endpoint-url", default="http://localhost:9222")
    auto_auth_parser.add_argument(
        "--try-cdp",
        action=argparse.BooleanOptionalAction,
        default=True,
    )
    auto_auth_parser.add_argument(
        "--try-system-browser",
        action=argparse.BooleanOptionalAction,
        default=True,
    )
    auto_auth_parser.add_argument(
        "--try-system-browser-profile",
        "--try-edge-profile",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="try the normal Edge/Chrome profile before password login",
    )
    auto_auth_parser.add_argument(
        "--system-browser-disable-extensions",
        action=argparse.BooleanOptionalAction,
        default=True,
    )
    auto_auth_parser.add_argument(
        "--system-browser",
        choices=["msedge", "chrome"],
        default="msedge",
    )
    auto_auth_parser.add_argument("--system-browser-debugging-port", type=int, default=9225)
    auto_auth_parser.add_argument(
        "--system-browser-profile-directory",
        "--edge-profile-directory",
        default=None,
        help="normal browser profile directory name, for example Default or Profile 1",
    )
    auto_auth_parser.add_argument(
        "--system-browser-profile-close-existing",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="close existing Edge/Chrome before launching the normal profile with CDP",
    )
    auto_auth_parser.add_argument("--cdp-timeout-seconds", type=float, default=3)
    system_profile_auth_parser = auth_subparsers.add_parser(
        "system-profile",
        aliases=["edge-profile"],
        help="export X auth from the normal Edge/Chrome profile over CDP",
    )
    system_profile_auth_parser.add_argument(
        "--account",
        default=None,
        help="account id to save under",
    )
    system_profile_auth_parser.add_argument("--storage-state", default=None)
    system_profile_auth_parser.add_argument(
        "--browser",
        choices=["msedge", "chrome"],
        default="msedge",
    )
    system_profile_auth_parser.add_argument("--executable-path", default=None)
    system_profile_auth_parser.add_argument(
        "--profile-directory",
        default=None,
        help="normal browser profile directory name, for example Default or Profile 1",
    )
    system_profile_auth_parser.add_argument("--debugging-port", type=int, default=9225)
    system_profile_auth_parser.add_argument("--start-url", default="https://x.com")
    system_profile_auth_parser.add_argument(
        "--close-existing-browser",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="close existing Edge/Chrome before launching the normal profile with CDP",
    )
    system_profile_auth_parser.add_argument("--timeout-seconds", type=float, default=30)
    auto_auth_parser.add_argument(
        "--channel",
        choices=["chrome", "msedge", "chromium", "chrome-beta", "msedge-beta", "msedge-dev"],
        default=None,
    )
    auto_auth_parser.add_argument("--executable-path", default=None)
    auto_auth_parser.add_argument("--start-url", default="https://x.com/i/flow/login")
    auto_auth_parser.add_argument(
        "--headless",
        action=argparse.BooleanOptionalAction,
        default=True,
    )
    auto_auth_parser.add_argument("--user-agent", default=None)
    auto_auth_parser.add_argument("--timeout-seconds", type=float, default=180)
    system_browser_auth_parser = auth_subparsers.add_parser(
        "system-browser",
        help="launch normal Edge/Chrome with CDP and log in automatically",
    )
    system_browser_auth_parser.add_argument(
        "--account",
        default=None,
        help="account id to save under",
    )
    system_browser_auth_parser.add_argument("--storage-state", default=None)
    system_browser_auth_parser.add_argument("--user-data-dir", default=None)
    system_browser_auth_parser.add_argument("--username-env", default="RESEARCH_X_X_USERNAME")
    system_browser_auth_parser.add_argument("--password-env", default="RESEARCH_X_X_PASSWORD")
    system_browser_auth_parser.add_argument(
        "--email-or-phone-env",
        default="RESEARCH_X_X_EMAIL_OR_PHONE",
    )
    system_browser_auth_parser.add_argument(
        "--verification-code-env",
        default="RESEARCH_X_X_VERIFICATION_CODE",
    )
    system_browser_auth_parser.add_argument("--totp-secret-env", default="RESEARCH_X_X_TOTP_SECRET")
    system_browser_auth_parser.add_argument(
        "--browser",
        choices=["msedge", "chrome"],
        default="msedge",
    )
    system_browser_auth_parser.add_argument("--executable-path", default=None)
    system_browser_auth_parser.add_argument("--start-url", default="https://x.com/i/flow/login")
    system_browser_auth_parser.add_argument("--debugging-port", type=int, default=9225)
    system_browser_auth_parser.add_argument(
        "--disable-extensions",
        action=argparse.BooleanOptionalAction,
        default=True,
    )
    system_browser_auth_parser.add_argument("--timeout-seconds", type=float, default=180)

    args = parser.parse_args(argv)
    if args.command == "adapters":
        if args.json:
            payload = [entry.to_dict() for entry in catalog_entries()]
            print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
        elif args.details:
            for entry in catalog_entries():
                print(
                    f"{entry.adapter_id}: {entry.fit} "
                    f"(layer={entry.acquisition_layer}, readiness={entry.readiness})"
                )
        else:
            for adapter_id in known_adapter_ids():
                print(adapter_id)
        return 0
    if args.command == "db-show":
        from research_x.db_view import format_display_rows, load_display_rows

        rows = load_display_rows(
            args.db,
            account=args.account,
            kind=args.kind,
            limit=args.limit,
        )
        print(format_display_rows(rows, json_output=args.json))
        return 0
    if args.command == "db-backup":
        from research_x.db_backup import create_sqlite_backup

        manifest = create_sqlite_backup(
            args.db,
            backup_dir=args.backup_dir,
            label=args.label,
        )
        print(
            json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True)
            if args.json
            else f"db backup: {manifest['backup_id']} path={manifest['backup_path']}"
        )
        return 0
    if args.command == "db-rollback":
        from research_x.db_backup import rollback_sqlite_backup

        result = rollback_sqlite_backup(
            args.db,
            backup_id=args.backup_id,
            backup_dir=args.backup_dir,
        )
        print(
            json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True)
            if args.json
            else f"db rollback: {result['backup_id']} restored={result['restored_db_path']}"
        )
        return 0
    if args.command == "label-existing":
        limit = None if args.all else max(1, args.limit)
        with _api_budget_for_args(args):
            report, classification = label_existing_items(
                db_path=args.db,
                account=args.account,
                kind=args.kind,
                limit=limit,
                include_labeled=args.include_labeled,
                out_dir=args.out,
                model=args.model,
                api_key_env=args.api_key_env,
                categories_path=args.categories or None,
                batch_size=args.batch_size,
                classifier_provider=args.classifier_provider,
                api_base_url=args.api_base_url,
                retry_attempts=args.retry_attempts,
                retry_base_seconds=args.retry_base_seconds,
                request_timeout_seconds=args.request_timeout_seconds,
                reasoning_effort=args.reasoning_effort,
                min_request_interval_seconds=args.min_request_interval_seconds,
                stop_on_rate_limit=args.stop_on_rate_limit,
            )
        print(
            "label-existing: "
            f"{report.status} selected={report.selected_items} "
            f"unique={report.unique_tweets} written={report.written_labels} "
            f"already_labeled={report.already_labeled}/{report.candidate_total} "
            f"model={report.model} db={report.db_path}"
        )
        if classification.error_message:
            print(f"{classification.error_type}: {classification.error_message}", file=sys.stderr)
        return 0 if report.status in {"ok", "empty"} else 1
    if args.command == "app":
        from research_x.local_app import serve_collection_app

        serve_collection_app(
            host=args.host,
            port=args.port,
            open_browser=args.open_browser,
        )
        return 0
    if args.command == "notify":
        from research_x.notify import notify_completion

        result = notify_completion(
            args.message,
            beep=args.beep,
            voice=args.voice,
        )
        if result.errors:
            print("notification warnings: " + "; ".join(result.errors), file=sys.stderr)
        return 0 if result.ok or not args.strict else 1
    if args.command == "adoption":
        from research_x.adoption_registry import adoption_audit, format_adoption_audit

        if args.adoption_command == "audit":
            audit = adoption_audit(args.registry)
            print(
                json.dumps(audit, ensure_ascii=False, indent=2, sort_keys=True)
                if args.json
                else format_adoption_audit(args.registry)
            )
            return 0 if audit["status"] == "ok" else 2
        raise AssertionError(f"unhandled adoption command {args.adoption_command}")
    if args.command == "project-control":
        from research_x.project_control import (
            project_control_inventory,
            validate_project_control,
        )

        errors = validate_project_control(args.project_root)
        if args.project_control_command == "validate":
            payload = {
                "status": "ok" if not errors else "failed",
                "errors": list(errors),
            }
        elif args.project_control_command == "status":
            payload = project_control_inventory(args.project_root)
            payload["status"] = "ok" if not errors else "failed"
        else:
            raise AssertionError(
                f"unhandled project-control command {args.project_control_command}"
            )
        if args.json:
            print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
        elif errors:
            print("project control failed:\n" + "\n".join(f"- {error}" for error in errors))
        else:
            print("project control ok")
            if args.project_control_command == "status":
                print(
                    "architecture="
                    f"{payload['architecture_authority']} "
                    f"state={payload['current_state_authority']} "
                    f"promotion={payload['semantic_promotion']}"
                )
        return 0 if not errors else 2
    if args.command == "progress":
        from research_x.progress import serve_progress_monitor

        serve_progress_monitor(
            out_dir=args.out,
            host=args.host,
            port=args.port,
            open_browser=args.open_browser,
        )
        return 0
    if args.command == "test-diagnose":
        from research_x.test_diagnostics import (
            diagnose_pytest,
            format_test_diagnostic_results,
            normalize_targets,
            test_diagnostic_results_json,
        )

        results = diagnose_pytest(
            targets=normalize_targets(args.targets),
            mode=args.mode,
            timeout_seconds=args.timeout_seconds,
            collect_timeout_seconds=args.collect_timeout_seconds,
            pytest_args=tuple(args.pytest_arg),
            max_output_chars=args.max_output_chars,
            stop_on_fail=args.stop_on_fail,
        )
        print(
            test_diagnostic_results_json(results)
            if args.json
            else format_test_diagnostic_results(results)
        )
        return 0 if all(result.status == "passed" for result in results) else 2
    if args.command == "presentation":
        from research_x.presentation import (
            format_presentation_facts_validation,
            validate_presentation_facts,
        )

        if args.presentation_command == "validate-facts":
            result = validate_presentation_facts(args.facts)
            print(
                json.dumps(result.as_dict(), ensure_ascii=False, indent=2, sort_keys=True)
                if args.json
                else format_presentation_facts_validation(result)
            )
            return 0 if result.ok else 2
        if args.presentation_command == "validate-slides":
            from research_x.presentation import (
                format_presentation_slides_validation,
                validate_presentation_slides,
            )

            result = validate_presentation_slides(
                args.slides,
                facts_path=args.facts,
                allow_missing_assets=args.allow_missing_assets,
            )
            print(
                json.dumps(result.as_dict(), ensure_ascii=False, indent=2, sort_keys=True)
                if args.json
                else format_presentation_slides_validation(result)
            )
            return 0 if result.ok else 2
        raise AssertionError(f"unhandled presentation command {args.presentation_command}")
    if args.command == "memory":
        try:
            return _handle_memory_command(args)
        except (FileNotFoundError, RuntimeError, ValueError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
    if args.command == "accounts":
        if args.accounts_command == "add":
            profile = write_account_profile(
                account=args.account,
                screen_name=args.screen_name,
                user_id=args.user_id,
                display_name=args.display_name,
                url=args.url,
            )
            print(f"account: {profile.account_id} screen_name={profile.screen_name}")
            return 0
        raise AssertionError(f"unhandled accounts command {args.accounts_command}")
    if args.command == "auth":
        if args.auth_command == "playwright":
            paths = resolve_account_paths(
                args.account,
                storage_state=args.storage_state,
                user_data_dir=args.user_data_dir,
            )
            ok = capture_playwright_storage_state(
                storage_state=paths.storage_state,
                user_data_dir=paths.user_data_dir,
                channel=args.channel,
                executable_path=args.executable_path,
                start_url=args.start_url,
                timeout_seconds=args.timeout_seconds,
            )
            return 0 if ok else 1
        if args.auth_command == "cookies":
            paths = resolve_account_paths(args.account, storage_state=args.storage_state)
            write_storage_state_from_cookie_env(
                storage_state=paths.storage_state,
                auth_token_env=args.auth_token_env,
                ct0_env=args.ct0_env,
            )
            return 0
        if args.auth_command == "cdp":
            paths = resolve_account_paths(args.account, storage_state=args.storage_state)
            ok = capture_storage_state_from_cdp(
                storage_state=paths.storage_state,
                endpoint_url=args.endpoint_url,
                timeout_seconds=args.timeout_seconds,
                no_defaults=args.no_defaults,
            )
            return 0 if ok else 1
        if args.auth_command == "credentials":
            paths = resolve_account_paths(
                args.account,
                storage_state=args.storage_state,
                user_data_dir=args.user_data_dir,
            )
            ok = capture_storage_state_with_credentials(
                storage_state=paths.storage_state,
                user_data_dir=paths.user_data_dir,
                username_env=args.username_env,
                password_env=args.password_env,
                email_or_phone_env=args.email_or_phone_env,
                verification_code_env=args.verification_code_env,
                totp_secret_env=args.totp_secret_env,
                channel=args.channel,
                executable_path=args.executable_path,
                start_url=args.start_url,
                headless=args.headless,
                user_agent=args.user_agent,
                timeout_seconds=args.timeout_seconds,
            )
            return 0 if ok else 1
        if args.auth_command == "auto":
            paths = resolve_account_paths(
                args.account,
                storage_state=args.storage_state,
                user_data_dir=args.user_data_dir,
            )
            ok = capture_storage_state_auto(
                storage_state=paths.storage_state,
                user_data_dir=paths.user_data_dir,
                username_env=args.username_env,
                password_env=args.password_env,
                email_or_phone_env=args.email_or_phone_env,
                verification_code_env=args.verification_code_env,
                totp_secret_env=args.totp_secret_env,
                auth_token_env=args.auth_token_env,
                ct0_env=args.ct0_env,
                endpoint_url=args.endpoint_url,
                try_cdp=args.try_cdp,
                cdp_timeout_seconds=args.cdp_timeout_seconds,
                try_system_browser=args.try_system_browser,
                try_system_browser_profile=args.try_system_browser_profile,
                system_browser=args.system_browser,
                system_browser_debugging_port=args.system_browser_debugging_port,
                system_browser_profile_directory=args.system_browser_profile_directory,
                system_browser_profile_close_existing=(
                    args.system_browser_profile_close_existing
                ),
                system_browser_disable_extensions=args.system_browser_disable_extensions,
                channel=args.channel,
                executable_path=args.executable_path,
                start_url=args.start_url,
                headless=args.headless,
                user_agent=args.user_agent,
                timeout_seconds=args.timeout_seconds,
            )
            return 0 if ok else 1
        if args.auth_command in {"system-profile", "edge-profile"}:
            paths = resolve_account_paths(args.account, storage_state=args.storage_state)
            ok = capture_storage_state_from_system_browser_profile(
                storage_state=paths.storage_state,
                browser=args.browser,
                executable_path=args.executable_path,
                profile_directory=args.profile_directory,
                close_existing=args.close_existing_browser,
                debugging_port=args.debugging_port,
                start_url=args.start_url,
                timeout_seconds=args.timeout_seconds,
            )
            return 0 if ok else 1
        if args.auth_command == "system-browser":
            paths = resolve_account_paths(
                args.account,
                storage_state=args.storage_state,
                user_data_dir=args.user_data_dir,
            )
            ok = capture_storage_state_with_system_browser_credentials(
                storage_state=paths.storage_state,
                user_data_dir=paths.user_data_dir,
                username_env=args.username_env,
                password_env=args.password_env,
                email_or_phone_env=args.email_or_phone_env,
                verification_code_env=args.verification_code_env,
                totp_secret_env=args.totp_secret_env,
                browser=args.browser,
                executable_path=args.executable_path,
                start_url=args.start_url,
                debugging_port=args.debugging_port,
                disable_extensions=args.disable_extensions,
                timeout_seconds=args.timeout_seconds,
            )
            return 0 if ok else 1
        raise AssertionError(f"unhandled auth command {args.auth_command}")
    if args.command == "bookmarks":
        limit = args.limit
        max_scroll_steps = max(args.max_scroll_steps, 1000) if args.all else args.max_scroll_steps
        with _api_budget_for_args(args):
            result, classification = run_bookmark_job(
                out_dir=Path(args.out),
                account=args.account,
                storage_state=args.storage_state,
                limit=limit,
                headless=args.headless,
                timeout_ms=args.timeout_ms,
                max_scroll_steps=max_scroll_steps,
                classify=args.classify,
                model=args.model,
                api_key_env=args.api_key_env,
                categories_path=args.categories,
                batch_size=args.batch_size,
                min_successful_providers=args.min_successful_providers,
                download_media=args.download_media,
                media_download_policy=args.media_download_policy,
                media_timeout_seconds=args.media_timeout_seconds,
                classifier_provider=args.classifier_provider,
                api_base_url=args.api_base_url,
                db_path=args.db,
                exhaustive=args.all,
                reasoning_effort=args.reasoning_effort,
            )
        providers = ",".join(result.providers_used) or "-"
        print(
            f"bookmarks: {result.status.value} items={len(result.items)} "
            f"providers={providers} classification={classification.status} out={args.out}"
        )
        if result.status.value in (OutcomeStatus.OK.value, OutcomeStatus.PARTIAL.value):
            return 0
        return 1
    if args.command == "tweets":
        with _api_budget_for_args(args):
            result, store_summary, classification = run_tweet_job(
                out_dir=Path(args.out),
                kind=args.kind,
                value=args.value,
                account=args.account,
                storage_state=args.storage_state,
                limit=args.limit,
                headless=args.headless,
                timeout_ms=args.timeout_ms,
                max_scroll_steps=args.max_scroll_steps,
                min_successful_providers=args.min_successful_providers,
                download_media=args.download_media,
                media_download_policy=args.media_download_policy,
                media_timeout_seconds=args.media_timeout_seconds,
                db_path=args.db,
                classify=args.classify,
                model=args.model,
                api_key_env=args.api_key_env,
                categories_path=args.categories,
                batch_size=args.batch_size,
                classifier_provider=args.classifier_provider,
                api_base_url=args.api_base_url,
                reasoning_effort=args.reasoning_effort,
            )
        providers = ",".join(result.providers_used) or "-"
        db_text = f" db={store_summary.db_path}" if store_summary else ""
        print(
            f"tweets: {result.status.value} items={len(result.items)} "
            f"providers={providers} classification={classification.status}{db_text} out={args.out}"
        )
        if result.status.value in (OutcomeStatus.OK.value, OutcomeStatus.PARTIAL.value):
            return 0
        return 1
    if args.command == "tweet-stages":
        stage_limits = tuple(
            int(value.strip())
            for value in args.stage_limits.split(",")
            if value.strip()
        )
        reports = run_tweet_stage_job(
            out_dir=Path(args.out),
            kind=args.kind,
            value=args.value,
            stage_limits=stage_limits,
            discard_stage_data=args.discard_stage_data,
            account=args.account,
            storage_state=args.storage_state,
            headless=args.headless,
            timeout_ms=args.timeout_ms,
            max_scroll_steps=args.max_scroll_steps,
            min_successful_providers=args.min_successful_providers,
        )
        for report in reports:
            providers = ",".join(report["providers_used"]) or "-"
            print(
                f"stage:{report['limit']}: {report['status']} "
                f"items={report['items']} providers={providers}"
            )
        return 0
    if args.command == "run":
        config = load_config(args.config)
        metrics = run_experiment(config, Path(args.out))
        for metric in metrics.values():
            print(
                f"{metric.adapter_id}: {metric.promotion_status.value} "
                f"score={metric.score:.3f} success={metric.success_rate:.3f} "
                f"items={metric.total_items}"
            )
        return 0
    if args.command == "pipeline":
        paths = resolve_account_paths(args.account, storage_state=args.storage_state)
        config = load_config(args.config)
        results = run_pipeline(
            config,
            Path(args.out),
            storage_state=paths.storage_state,
            twikit_cookies_file=paths.twikit_cookies_file,
            scweet_cookies_file=paths.scweet_cookies_file,
            masa_cookies_file=paths.masa_cookies_file,
            twscrape_accounts_db=paths.twscrape_accounts_db,
            min_successful_providers=args.min_successful_providers,
        )
        for result in results:
            providers = ",".join(result.providers_used) or "-"
            print(
                f"{result.target.kind}:{result.target.value}: {result.status.value} "
                f"items={len(result.items)} providers={providers}"
            )
        return 0
    raise AssertionError(f"unhandled command {args.command}")


def _handle_memory_command(args: argparse.Namespace) -> int:
    if hasattr(args, "api_budget_policy") and not getattr(args, "_api_budget_active", False):
        args._api_budget_active = True
        with _api_budget_for_args(args):
            return _handle_memory_command(args)
    if args.memory_command == "api-budget":
        from research_x.memory.api_budget import (
            api_budget_status,
            authorize_provider_execution,
            format_api_budget_status,
            format_provider_quota_preflight,
            provider_quota_preflight,
            set_api_budget_policy,
            set_api_kill_switch,
            upsert_api_price,
        )

        if args.api_budget_command == "status":
            status = api_budget_status(args.db, policy_id=args.policy_id, run_id=args.run_id)
            print(
                json.dumps(status, ensure_ascii=False, indent=2, sort_keys=True)
                if args.json
                else format_api_budget_status(status)
            )
            return 0
        if args.api_budget_command == "set":
            status = set_api_budget_policy(
                args.db,
                policy_id=args.policy_id,
                enabled=args.enabled,
                max_run_usd=args.max_run_usd,
                max_day_usd=args.max_day_usd,
                max_month_usd=args.max_month_usd,
                max_run_calls=args.max_run_calls,
                max_day_calls=args.max_day_calls,
                max_run_input_tokens=args.max_run_input_tokens,
                max_run_media_bytes=args.max_run_media_bytes,
                unknown_price_action=args.unknown_price_action,
            )
            print(
                json.dumps(status, ensure_ascii=False, indent=2, sort_keys=True)
                if args.json
                else format_api_budget_status(status)
            )
            return 0
        if args.api_budget_command in {"stop", "resume"}:
            status = set_api_kill_switch(
                args.db,
                policy_id=args.policy_id,
                enabled=args.api_budget_command == "stop",
            )
            print(
                json.dumps(status, ensure_ascii=False, indent=2, sort_keys=True)
                if args.json
                else format_api_budget_status(status)
            )
            return 0
        if args.api_budget_command == "price-set":
            upsert_api_price(
                args.db,
                provider=args.provider,
                model=args.model,
                operation=args.operation,
                unit=args.unit,
                usd_per_unit=args.usd_per_unit,
                source_url=args.source_url,
                checked_at=args.checked_at,
                notes=args.notes,
            )
            print(
                "api price set: "
                f"{args.provider}/{args.model} {args.operation} "
                f"{args.unit}=${args.usd_per_unit}"
            )
            return 0
        if args.api_budget_command == "seed-default-prices":
            from research_x.memory.api_lane_estimate import seed_default_api_price_catalog

            count = seed_default_api_price_catalog(args.db)
            print(f"seeded default API prices: {count}")
            return 0
        if args.api_budget_command == "preflight":
            report = provider_quota_preflight(
                args.db,
                provider=args.provider,
                model=args.model,
                operation=args.operation,
                provider_role=args.provider_role,
                units=_provider_quota_units_for_args(args),
                approval=_provider_quota_approval_payload_for_args(args),
                policy_id=args.policy_id,
                run_id=args.run_id,
                approved_scope=args.current_scope,
                max_run_usd_override=args.max_run_usd,
                allow_unpriced_api=args.allow_unpriced_api,
                provider_authorization_id=args.provider_authorization_id,
                provider_execution_policy_id=args.provider_execution_policy_id,
            )
            print(
                json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
                if args.json
                else format_provider_quota_preflight(report)
            )
            return 0
        if args.api_budget_command == "authorize":
            result = authorize_provider_execution(
                args.db,
                authorization_id=args.authorization_id,
                policy_id=args.policy_id,
                provider=args.provider,
                model=args.model,
                operation=args.operation,
                provider_role=args.provider_role,
                max_calls=args.max_calls,
                max_cost_usd=args.max_cost_usd,
                max_input_tokens=args.max_input_tokens,
                max_output_tokens=args.max_output_tokens,
                max_media_bytes=args.max_media_bytes,
                max_documents=args.max_documents,
                approved_scope=args.approved_scope,
                approved_by=args.approved_by,
                approval_source=args.approval_source,
                approved_at=args.approved_at,
                valid_until=args.valid_until,
                storage_rights=args.storage_rights,
                prompt_injection_required=args.prompt_injection_required,
                rollback_scope=args.rollback_scope,
                metadata=_parse_key_value_pairs(args.metadata),
            )
            print(
                json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True)
                if args.json
                else (
                    "provider execution authorized: "
                    f"{result['execution_policy']['policy_id']} "
                    f"auth={result['authorization']['provider_quota_approval_id']}"
                )
            )
            return 0
        raise AssertionError(f"unhandled api-budget command {args.api_budget_command}")
    if args.memory_command == "api-usage":
        from research_x.memory.api_budget import api_usage_report, format_api_usage_report

        report = api_usage_report(
            args.db,
            run_id=args.run_id,
            today=args.today,
            month=args.month,
            limit=args.limit,
        )
        print(
            json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
            if args.json
            else format_api_usage_report(report)
        )
        return 0
    if args.memory_command in {"api-watch", "api-dashboard"}:
        from research_x.memory.api_budget import serve_api_watch

        serve_api_watch(
            db_path=args.db,
            host=args.host,
            port=args.port,
            open_browser=args.open_browser,
            policy_id=args.policy_id,
            run_id=args.run_id,
            recent_limit=args.recent_limit,
            command_name=args.memory_command,
        )
        return 0
    if args.memory_command == "api-lane-estimate":
        from research_x.memory.api_lane_estimate import (
            api_lane_estimate_json,
            build_api_lane_estimate_report,
            format_api_lane_estimate,
        )

        report = build_api_lane_estimate_report(
            args.db,
            include_reference_managed_rag=args.include_reference_managed_rag,
            include_latest_ocr=args.include_latest_ocr,
            ocr_scope=args.ocr_scope,
            ocr_limit=args.ocr_limit,
            reader_url_limit=args.reader_url_limit,
            reader_max_chars=args.reader_max_chars,
            rerank_query_count=args.rerank_query_count,
            rerank_candidate_limit=args.rerank_candidate_limit,
            rerank_avg_candidate_tokens=args.rerank_avg_candidate_tokens,
            external_search_query_count=args.external_search_query_count,
            external_search_result_limit=args.external_search_result_limit,
            llm_context_query_count=args.llm_context_query_count,
            max_file_bytes=args.max_file_bytes,
        )
        print(api_lane_estimate_json(report) if args.json else format_api_lane_estimate(report))
        return 0
    if args.memory_command == "knowledge":
        if args.knowledge_command == "sync-sources":
            from research_x.memory.source_manifest import sync_x_source_manifest

            summary = sync_x_source_manifest(
                args.db,
                observation_run_id=args.observation_run_id,
                observation_completeness=args.observation_completeness,
                observed_at=args.observed_at,
            )
            _print_cli_payload(summary.as_dict(), json_output=args.json)
            return 0
        if args.knowledge_command == "source-list":
            rows = _select_knowledge_rows(
                args.db,
                """
                SELECT source_ref, source_kind, source_status, updated_at
                FROM memory_sources
                ORDER BY updated_at DESC, source_ref
                LIMIT ?
                """,
                (args.limit,),
            )
            _print_cli_payload(rows, json_output=args.json)
            return 0
        if args.knowledge_command == "source-show":
            rows = _select_knowledge_rows(
                args.db,
                "SELECT * FROM memory_sources WHERE source_ref = ?",
                (args.source_ref,),
            )
            _print_cli_payload(rows[0] if rows else {}, json_output=args.json)
            return 0
        if args.knowledge_command == "observations":
            if args.source_ref:
                rows = _select_knowledge_rows(
                    args.db,
                    """
                    SELECT *
                    FROM memory_source_observations
                    WHERE source_ref = ?
                    ORDER BY observed_at DESC
                    LIMIT ?
                    """,
                    (args.source_ref, args.limit),
                )
            else:
                rows = _select_knowledge_rows(
                    args.db,
                    """
                    SELECT *
                    FROM memory_source_observations
                    ORDER BY observed_at DESC
                    LIMIT ?
                    """,
                    (args.limit,),
                )
            _print_cli_payload(rows, json_output=args.json)
            return 0
        if args.knowledge_command == "reconcile":
            from research_x.memory.reconciliation import reconcile_source_observation

            summary = reconcile_source_observation(
                args.db,
                observed_source_refs=tuple(args.observed_source_ref),
                observation_completeness=args.observation_completeness,
                reconciliation_scope=args.scope,
                reconciliation_run_id=args.run_id,
                started_at=args.started_at,
            )
            _print_cli_payload(summary.as_dict(), json_output=args.json)
            return 0
        if args.knowledge_command == "reconcile-show":
            _print_cli_payload(
                _reconciliation_show_payload(args.db, run_id=args.run_id),
                json_output=args.json,
            )
            return 0
        if args.knowledge_command == "cleanup-orphans":
            _print_cli_payload(
                _knowledge_cleanup_orphans_payload(args.db, dry_run=args.dry_run),
                json_output=args.json,
            )
            return 0
        if args.knowledge_command == "status":
            _print_cli_payload(_knowledgeops_status(args.db), json_output=args.json)
            return 0
        raise AssertionError(f"unhandled knowledge command {args.knowledge_command}")
    if args.memory_command == "artifacts":
        if args.artifacts_command == "list":
            rows = _select_knowledge_rows(
                args.db,
                """
                SELECT artifact_id, artifact_role, artifact_kind,
                       authority_level, output_mode, artifact_status
                FROM memory_artifacts
                ORDER BY updated_at DESC, artifact_id
                LIMIT ?
                """,
                (args.limit,),
            )
            _print_cli_payload(rows, json_output=args.json)
            return 0
        if args.artifacts_command == "show":
            rows = _select_knowledge_rows(
                args.db,
                "SELECT * FROM memory_artifacts WHERE artifact_id = ?",
                (args.artifact_id,),
            )
            _print_cli_payload(rows[0] if rows else {}, json_output=args.json)
            return 0
        if args.artifacts_command == "links":
            rows = _select_knowledge_rows(
                args.db,
                """
                SELECT *
                FROM memory_artifact_links
                WHERE source_artifact_id = ? OR target_artifact_id = ?
                ORDER BY created_at, link_id
                """,
                (args.artifact_id, args.artifact_id),
            )
            _print_cli_payload(rows, json_output=args.json)
            return 0
        if args.artifacts_command == "validate":
            _print_cli_payload(_artifact_registry_validation(args.db), json_output=args.json)
            return 0
        raise AssertionError(f"unhandled artifacts command {args.artifacts_command}")
    if args.memory_command == "projections":
        _print_cli_payload(
            _projection_lifecycle_payload(
                args.db,
                command=args.projections_command,
                projection_id=args.projection_id,
                mode=getattr(args, "mode", "incremental"),
                projection_kind=args.projection_kind,
                builder_params={
                    "provider": getattr(args, "provider", "local_hash"),
                    "model": getattr(args, "model", None),
                    "dimensions": getattr(args, "dimensions", None),
                    "embedding_profile": getattr(args, "embedding_profile", None),
                    "text_template_version": getattr(
                        args,
                        "text_template_version",
                        None,
                    ),
                    "backend": getattr(args, "backend", "numpy"),
                    "bit_width": getattr(args, "bit_width", 4),
                    "out_dir": getattr(args, "out_dir", None),
                    "doc_type": getattr(args, "doc_type", None),
                    "account": getattr(args, "account", None),
                },
            ),
            json_output=args.json,
        )
        return 0
    if args.memory_command == "participation":
        if args.participation_command == "rebuild":
            from research_x.memory.participation import rebuild_participation_decisions

            output_modes = tuple(args.output_mode) if args.output_mode else (
                "explore",
                "collect",
                "working_note",
                "synthesize",
                "evidence_package",
                "answer",
            )
            summary = rebuild_participation_decisions(
                args.db,
                output_modes=output_modes,
                decided_at=args.decided_at,
            )
            _print_cli_payload(summary.as_dict(), json_output=args.json)
            return 0
        if args.participation_command in {"check", "explain"}:
            payload = _participation_payload(
                args.db,
                source_ref=args.source_ref,
                artifact_id=args.artifact_id,
                output_mode=args.output_mode,
            )
            _print_cli_payload(payload, json_output=args.json)
            return 0
        raise AssertionError(
            f"unhandled participation command {args.participation_command}"
        )
    if args.memory_command in {"explore", "collect"}:
        from research_x.memory.search import search_memory
        from research_x.tool_interface.mode_aware_search import (
            search_results_tool_output_v2,
        )

        results = search_memory(
            args.db,
            args.query,
            limit=args.limit,
            doc_type=args.doc_type,
            account=args.account,
        )
        output = search_results_tool_output_v2(
            query=args.query,
            results=results,
            output_mode=args.memory_command,
        )
        _print_cli_payload(output.as_dict(), json_output=args.json)
        return 0
    if args.memory_command == "working-note":
        from research_x.memory.working_notes import (
            append_working_note,
            create_working_note,
            expire_working_note,
            link_working_note_to_artifacts,
            promote_working_note_to_curated_source,
            read_working_note,
        )
        from research_x.tool_interface.memory_tool_contract import (
            CONTRACT_VERSION_V2,
            ToolOutputItemV2,
            ToolOutputV2,
        )

        if args.working_note_command == "create":
            note = create_working_note(
                args.db,
                title=args.title,
                body=args.body,
                task_scope=args.task_scope,
                thread_scope=args.thread_scope,
                source_refs=tuple(args.source_ref),
                artifact_refs=tuple(args.artifact_ref),
                retention_policy=args.retention_policy,
                created_at=args.created_at,
                expires_at=args.expires_at,
            )
        elif args.working_note_command == "append":
            note = append_working_note(
                args.db,
                args.note_id,
                args.text,
                updated_at=args.updated_at,
            )
        elif args.working_note_command == "show":
            note = read_working_note(args.db, args.note_id)
            if note is None:
                raise KeyError(f"working note not found: {args.note_id}")
        elif args.working_note_command == "link":
            note = link_working_note_to_artifacts(
                args.db,
                args.note_id,
                source_refs=tuple(args.source_ref),
                artifact_refs=tuple(args.artifact_ref),
                updated_at=args.updated_at,
            )
        elif args.working_note_command == "expire":
            note = expire_working_note(
                args.db,
                args.note_id,
                expired_at=args.expired_at,
            )
        elif args.working_note_command == "promote":
            promotion = promote_working_note_to_curated_source(
                args.db,
                args.note_id,
                human_in_loop_approved=args.confirm_human_in_loop,
                approved_by=args.approved_by,
                approval_note=args.approval_note,
                promoted_at=args.promoted_at,
            )
            _print_cli_payload(promotion.as_dict(), json_output=args.json)
            return 0
        else:
            raise AssertionError(
                f"unhandled working-note command {args.working_note_command}"
            )
        output = ToolOutputV2(
            contract_version=CONTRACT_VERSION_V2,
            tool_kind="research_x.memory.working_note",
            query=note.title,
            output_mode="working_note",
            status="working_note_written",
            answer_text=None,
            items=(
                ToolOutputItemV2(
                    item_id=note.working_note_id,
                    subject_kind="working_note",
                    subject_id=note.working_note_id,
                    artifact_role="working_note",
                    authority_level="candidate",
                    source_refs=note.source_refs,
                    source_status="available",
                    projection_id=None,
                    score=None,
                    why_relevant=f"working_note_{args.working_note_command}",
                    risk_flags=("working_note_not_evidence",),
                    metadata=note.as_dict(),
                ),
            ),
            citations=(),
            claim_support=None,
            working_note_id=note.working_note_id,
            trace={
                "unsupported_claims": [],
                "unresolved_items": [],
                "working_note_not_evidence": True,
            },
        )
        _print_cli_payload(output.as_dict(), json_output=args.json)
        return 0
    if args.memory_command == "synthesize":
        from research_x.tool_interface.memory_tool_contract import (
            CONTRACT_VERSION_V2,
            ToolOutputV2,
        )

        output = ToolOutputV2(
            contract_version=CONTRACT_VERSION_V2,
            tool_kind="research_x.memory.synthesize",
            query=args.query,
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
        _print_cli_payload(output.as_dict(), json_output=args.json)
        return 0
    if args.memory_command == "evidence-package":
        from research_x.memory.evidence_package import build_evidence_package_output

        artifact_rows = _select_knowledge_rows(
            args.db,
            """
            SELECT artifact_id
            FROM memory_artifacts
            WHERE artifact_role = 'evidence_view'
            ORDER BY updated_at DESC, artifact_id
            LIMIT ?
            """,
            (args.limit,),
        )
        artifact_ids = tuple(row["artifact_id"] for row in artifact_rows)
        output = build_evidence_package_output(
            args.db,
            query=args.query,
            artifact_ids=artifact_ids,
        )
        _print_cli_payload(output.as_dict(), json_output=args.json)
        return 0
    if args.memory_command == "eval-v2":
        from research_x.memory.evals_v2 import run_eval_cases_v2

        if args.eval_v2_command == "compare":
            if not args.baseline or not args.candidate:
                raise ValueError("eval-v2 compare requires --baseline and --candidate")
            _print_cli_payload(
                _eval_v2_compare_payload(
                    args.db,
                    baseline=args.baseline,
                    candidate=args.candidate,
                ),
                json_output=args.json,
            )
            return 0
        if args.eval_v2_command == "report":
            if not args.run_id:
                raise ValueError("eval-v2 report requires --run-id")
            _print_cli_payload(
                _eval_v2_report_payload(args.db, run_id=args.run_id),
                json_output=args.json,
            )
            return 0
        if not args.cases:
            raise ValueError("eval-v2 run requires --cases")
        summary = run_eval_cases_v2(
            args.db,
            cases_path=args.cases,
            run_id=args.run_id,
        )
        _print_cli_payload(summary.as_dict(), json_output=args.json)
        return 1 if summary.status == "failed" else 0
    if args.memory_command == "route-promotion":
        from research_x.memory.route_promotion import (
            approve_route_promotion,
            check_route_promotion,
            list_route_promotion_decisions,
            reject_route_promotion,
        )

        if args.route_promotion_command == "check":
            decision = check_route_promotion(
                args.db,
                candidate_route_version=args.candidate_route_version,
                baseline_route_version=args.baseline_route_version,
                eval_run_ids=tuple(args.eval_run_id),
                output_modes=tuple(args.output_mode),
                deltas=_parse_float_mapping(args.delta),
                thresholds=_parse_float_mapping(args.threshold),
                created_at=args.created_at,
            )
            _print_cli_payload(decision.as_dict(), json_output=args.json)
            return 2 if decision.status == "blocked" else 0
        if args.route_promotion_command == "approve":
            decision = approve_route_promotion(
                args.db,
                promotion_decision_id=args.decision_id,
                approved_at=args.at,
                reason=args.reason,
            )
            _print_cli_payload(decision.as_dict(), json_output=args.json)
            return 0
        if args.route_promotion_command == "reject":
            decision = reject_route_promotion(
                args.db,
                promotion_decision_id=args.decision_id,
                rejected_at=args.at,
                reason=args.reason,
            )
            _print_cli_payload(decision.as_dict(), json_output=args.json)
            return 0
        if args.route_promotion_command == "list":
            decisions = list_route_promotion_decisions(args.db, status=args.status)
            _print_cli_payload(
                [decision.as_dict() for decision in decisions],
                json_output=args.json,
            )
            return 0
        raise AssertionError(
            f"unhandled route-promotion command {args.route_promotion_command}"
        )
    if args.memory_command == "audit-events":
        from research_x.memory.audit_events import list_audit_events

        events = list_audit_events(args.db, event_type=args.event_type)
        _print_cli_payload([event.as_dict() for event in events], json_output=args.json)
        return 0
    if args.memory_command == "audit-latest":
        _print_cli_payload(_audit_latest_payload(args.db), json_output=args.json)
        return 0
    if args.memory_command == "audit-summary":
        from research_x.memory.audit_events import audit_summary

        _print_cli_payload(audit_summary(args.db), json_output=args.json)
        return 0
    if args.memory_command == "alert-test":
        from research_x.memory.audit_events import (
            deliver_audit_events_to_jsonl,
            register_alert_sink,
        )

        sink = register_alert_sink(
            args.db,
            sink_kind="local_jsonl",
            sink_config={"path": args.path},
            sink_id=args.sink_id,
            created_at=args.delivered_at,
        )
        delivered = deliver_audit_events_to_jsonl(
            args.db,
            sink_id=sink.sink_id,
            event_type=args.event_type,
            delivered_at=args.delivered_at,
        )
        _print_cli_payload(
            {
                "status": "ok",
                "sink": sink.as_dict(),
                "delivered": delivered,
            },
            json_output=args.json,
        )
        return 0
    if args.memory_command == "build-corpus":
        from research_x.memory.corpus import build_memory_corpus, summary_as_dict

        summary = build_memory_corpus(args.db)
        print(json.dumps(summary_as_dict(summary), ensure_ascii=False, indent=2))
        return 0
    if args.memory_command == "build-derived":
        from research_x.memory.derived import build_derived_documents, summary_as_dict

        summary = build_derived_documents(
            args.db,
            kinds=tuple(args.kind) if args.kind else None,
            max_source_docs_per_card=args.max_source_docs_per_card,
            min_author_docs=args.min_author_docs,
            min_topic_docs=args.min_topic_docs,
        )
        print(json.dumps(summary_as_dict(summary), ensure_ascii=False, indent=2))
        return 0
    if args.memory_command == "audit":
        from research_x.memory.audit import (
            audit_memory_db,
            audit_report_json,
            format_audit_report,
        )

        report = audit_memory_db(args.db)
        print(audit_report_json(report) if args.json else format_audit_report(report))
        if not args.strict:
            return 0
        readiness_key = (
            "local_no_provider_ready"
            if args.readiness_scope == "local-no-provider"
            else "provider_production_ready"
        )
        return 0 if report.readiness[readiness_key] else 2
    if args.memory_command == "build-embeddings":
        from research_x.memory.embeddings import build_memory_embeddings, summary_as_dict

        summary = build_memory_embeddings(
            args.db,
            space_id=args.space_id,
            provider=args.provider,
            model=args.model,
            dimensions=args.dimensions,
            embedding_profile=args.embedding_profile,
            text_template_version=args.text_template_version,
            api_key_env=args.api_key_env,
            base_url=args.base_url,
            batch_size=args.batch_size,
            limit=args.limit,
            rebuild=args.rebuild,
            progress_every=args.progress_every,
            execution_stage=args.execution_stage,
            selection_policy=args.selection_policy,
            allow_provider_quota=args.allow_provider_quota,
            projection_profile=args.projection_profile,
            classification_version=args.classification_version,
            projection_policy_version=args.projection_policy_version,
            require_projections=args.require_projections,
        )
        print(json.dumps(summary_as_dict(summary), ensure_ascii=False, indent=2))
        return 0
    if args.memory_command == "embedding-estimate":
        from research_x.memory.embeddings import (
            embedding_estimate_json,
            estimate_memory_embedding_build,
            format_embedding_estimate,
        )

        estimate = estimate_memory_embedding_build(
            args.db,
            space_id=args.space_id,
            provider=args.provider,
            model=args.model,
            dimensions=args.dimensions,
            embedding_profile=args.embedding_profile,
            text_template_version=args.text_template_version,
            api_key_env=args.api_key_env,
            base_url=args.base_url,
            batch_size=args.batch_size,
            limit=args.limit,
            rebuild=args.rebuild,
            price_per_million_input_tokens=args.price_per_million_input_tokens,
            execution_stage=args.execution_stage,
            selection_policy=args.selection_policy,
            projection_profile=args.projection_profile,
            classification_version=args.classification_version,
            projection_policy_version=args.projection_policy_version,
            require_projections=args.require_projections,
        )
        output = (
            embedding_estimate_json(estimate)
            if args.json
            else format_embedding_estimate(estimate)
        )
        print(output)
        return 0
    if args.memory_command == "classify-embedding-inputs":
        from research_x.memory.embedding_input import classify_embedding_inputs

        report = classify_embedding_inputs(
            args.db,
            classification_version=args.classification_version,
            write=args.write and not args.dry_run,
            doc_id=args.doc_id,
            source_kind=args.source_kind,
            limit=args.limit,
            report_dir=args.artifact_dir,
            persistence=args.persistence,
        )
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    if args.memory_command == "embedding-template-policy":
        from research_x.memory.embedding_input import write_default_template_policies

        report = write_default_template_policies(
            args.db,
            policy_version=args.policy_version,
            write=args.write_defaults,
            report_dir=args.artifact_dir,
            persistence=args.persistence,
        )
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    if args.memory_command == "embedding-template-examples":
        from research_x.memory.embedding_input import build_embedding_template_examples

        examples = build_embedding_template_examples(
            args.db,
            policy_version=args.policy_version,
            classification_version=args.classification_version,
            limit=args.limit,
            write=args.persistence == "artifacts",
            report_dir=args.artifact_dir,
            persistence=args.persistence,
        )
        print(json.dumps(examples, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    if args.memory_command == "build-embedding-projections":
        from research_x.memory.embedding_input import build_embedding_projections

        report = build_embedding_projections(
            args.db,
            classification_version=args.classification_version,
            projection_policy_version=args.projection_policy_version,
            projection_profile=args.projection_profile,
            space_id=args.space_id,
            doc_id=args.doc_id,
            source_kind=args.source_kind,
            limit=args.limit,
            write=args.write and not args.dry_run,
            report_dir=args.artifact_dir,
            persistence=args.persistence,
        )
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    if args.memory_command == "projection-coverage":
        from research_x.memory.embedding_input import projection_coverage_report

        report = projection_coverage_report(
            args.db,
            classification_version=args.classification_version,
            projection_policy_version=args.projection_policy_version,
            report_dir=args.artifact_dir,
            persistence=args.persistence,
        )
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    if args.memory_command == "embedding-metadata-filter-policy":
        from research_x.memory.embedding_input import metadata_filter_policy_report

        report = metadata_filter_policy_report(
            policy_version=args.policy_version,
            report_dir=args.artifact_dir,
            persistence=args.persistence,
        )
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    if args.memory_command == "embedding-full-run-readiness":
        from research_x.memory.embedding_input import write_full_run_readiness

        report = write_full_run_readiness(
            args.db,
            tests_passed=args.tests_passed,
            quarantine_legacy_embeddings=args.quarantine_legacy_embeddings,
            report_dir=args.artifact_dir,
            persistence=args.persistence,
        )
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    if args.memory_command == "real-api-estimate-artifacts":
        from research_x.memory.real_api_artifacts import (
            format_real_api_estimate_artifacts,
            real_api_estimate_artifacts_json,
            write_offline_estimate_artifacts,
        )

        result = write_offline_estimate_artifacts(
            args.db,
            run_id=args.run_id,
            output_root=args.output_root,
            space_ids=tuple(args.space_id),
            batch_size=args.batch_size,
            limit=args.limit,
            execution_stage=args.execution_stage,
            selection_policy=args.selection_policy,
            rebuild=args.rebuild,
            price_per_million_input_tokens=args.price_per_million_input_tokens,
            max_file_bytes=args.max_file_bytes,
            mime_types=tuple(args.mime_type),
        )
        print(
            real_api_estimate_artifacts_json(result)
            if args.json
            else format_real_api_estimate_artifacts(result)
        )
        return 0
    if args.memory_command == "embedding-specs":
        from research_x.memory.embeddings import available_embedding_specs

        specs = [spec.__dict__ for spec in available_embedding_specs(args.db)]
        print(json.dumps(specs, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    if args.memory_command == "embedding-spaces":
        from research_x.memory.embedding_spaces import (
            embedding_space_plan_json,
            embedding_spaces_json,
            format_embedding_space_plan,
            format_embedding_space_rows,
            list_embedding_space_rows,
            plan_embedding_spaces,
        )

        command = args.embedding_spaces_command or "list"
        if command == "plan":
            report = plan_embedding_spaces(args.db)
            print(
                embedding_space_plan_json(report)
                if args.json
                else format_embedding_space_plan(report)
            )
            return 0 if report.status == "ready" else 1
        rows = list_embedding_space_rows(args.db)
        print(
            embedding_spaces_json(rows)
            if args.json
            else format_embedding_space_rows(rows)
        )
        return 0
    if args.memory_command == "embedding-coverage":
        from research_x.memory.embeddings import (
            embedding_coverage_json,
            embedding_coverage_report,
            format_embedding_coverage,
        )

        report = embedding_coverage_report(
            args.db,
            space_id=args.space_id,
            provider=None if args.provider == "latest" else args.provider,
            model=args.model,
            dimensions=args.dimensions,
            embedding_profile=args.embedding_profile,
            text_template_version=args.text_template_version,
        )
        print(embedding_coverage_json(report) if args.json else format_embedding_coverage(report))
        return 0
    if args.memory_command == "build-vector-projection":
        from research_x.memory.vector_projection import (
            build_vector_projection,
            format_vector_projection_summary,
            summary_json,
        )

        summary = build_vector_projection(
            args.db,
            space_id=args.space_id,
            provider=args.provider,
            model=args.model,
            dimensions=args.dimensions,
            embedding_profile=args.embedding_profile,
            text_template_version=args.text_template_version,
            backend=args.backend,
            bit_width=args.bit_width,
            out_dir=args.out_dir,
            doc_type=args.doc_type,
            account=args.account,
            allow_partial=args.allow_partial,
        )
        print(summary_json(summary) if args.json else format_vector_projection_summary(summary))
        return 0
    if args.memory_command == "vector-projection-coverage":
        from research_x.memory.vector_projection import (
            coverage_json,
            format_vector_projection_coverage,
            vector_projection_coverage,
        )

        report = vector_projection_coverage(
            args.db,
            generation_id=args.generation_id,
            space_id=args.space_id,
            provider=args.provider,
            model=args.model,
            dimensions=args.dimensions,
            embedding_profile=args.embedding_profile,
            text_template_version=args.text_template_version,
            backend=args.backend,
        )
        print(coverage_json(report) if args.json else format_vector_projection_coverage(report))
        return 0
    if args.memory_command == "vector-index":
        from research_x.memory.vector_projection import (
            build_vector_projection,
            coverage_json,
            format_vector_projection_coverage,
            format_vector_projection_summary,
            summary_json,
            vector_projection_coverage,
        )

        if args.vector_index_command == "build":
            summary = build_vector_projection(
                args.db,
                space_id=args.space_id,
                backend=args.backend,
                bit_width=args.bit_width,
                out_dir=args.out_dir,
                doc_type=args.doc_type,
                account=args.account,
                allow_partial=args.allow_partial,
            )
            print(summary_json(summary) if args.json else format_vector_projection_summary(summary))
            return 0
        if args.vector_index_command == "coverage":
            report = vector_projection_coverage(
                args.db,
                generation_id=args.generation_id,
                space_id=args.space_id,
                backend=args.backend,
            )
            print(coverage_json(report) if args.json else format_vector_projection_coverage(report))
            return 0
        print("vector-index requires a subcommand: build or coverage", file=sys.stderr)
        return 2
    if args.memory_command == "vector-backend-benchmark":
        from research_x.memory.vector_projection import (
            VectorBackendBenchmarkThresholds,
            benchmark_json,
            benchmark_vector_backends,
            format_vector_backend_benchmark,
        )

        report = benchmark_vector_backends(
            args.db,
            backends=tuple(args.backend) or ("numpy",),
            queries=tuple(args.query) or ("robot paper",),
            provider=args.provider,
            model=args.model,
            dimensions=args.dimensions,
            embedding_profile=args.embedding_profile,
            text_template_version=args.text_template_version,
            limit=args.limit,
            out_dir=args.out_dir,
            doc_type=args.doc_type,
            account=args.account,
            thresholds=VectorBackendBenchmarkThresholds(
                max_build_seconds=args.max_build_seconds,
                max_avg_search_seconds=args.max_avg_search_seconds,
                max_cold_start_seconds=args.max_cold_start_seconds,
                min_recall_at_limit=args.min_recall_at_limit,
                max_disk_bytes_per_vector=args.max_disk_bytes_per_vector,
                max_memory_bytes_per_vector=args.max_memory_bytes_per_vector,
                require_update_delete=args.require_update_delete,
                require_source_restoration=not args.no_require_source_restoration,
            ),
        )
        print(benchmark_json(report) if args.json else format_vector_backend_benchmark(report))
        return 0
    if args.memory_command == "media-embedding-estimate":
        from research_x.memory.media_embeddings import (
            estimate_media_embedding_build,
            format_media_embedding_estimate,
            media_embedding_estimate_json,
        )

        estimate = estimate_media_embedding_build(
            args.db,
            provider=args.provider,
            model=args.model,
            dimensions=args.dimensions,
            embedding_profile=args.embedding_profile,
            input_template_version=args.input_template_version,
            api_key_env=args.api_key_env,
            base_url=args.base_url,
            limit=args.limit,
            rebuild=args.rebuild,
            max_file_bytes=args.max_file_bytes,
            mime_types=tuple(args.mime_type),
        )
        print(
            media_embedding_estimate_json(estimate)
            if args.json
            else format_media_embedding_estimate(estimate)
        )
        return 0
    if args.memory_command == "build-media-embeddings":
        from research_x.memory.media_embeddings import build_media_embeddings, summary_as_dict

        summary = build_media_embeddings(
            args.db,
            provider=args.provider,
            model=args.model,
            dimensions=args.dimensions,
            embedding_profile=args.embedding_profile,
            input_template_version=args.input_template_version,
            api_key_env=args.api_key_env,
            base_url=args.base_url,
            limit=args.limit,
            rebuild=args.rebuild,
            max_file_bytes=args.max_file_bytes,
            mime_types=tuple(args.mime_type),
            timeout_seconds=args.timeout_seconds,
            allow_provider_quota=args.allow_provider_quota,
        )
        print(json.dumps(summary_as_dict(summary), ensure_ascii=False, indent=2))
        return 0
    if args.memory_command == "media-embedding-coverage":
        from research_x.memory.media_embeddings import (
            format_media_embedding_coverage,
            media_embedding_coverage_json,
            media_embedding_coverage_report,
        )

        report = media_embedding_coverage_report(
            args.db,
            provider=args.provider,
            model=args.model,
            dimensions=args.dimensions,
            embedding_profile=args.embedding_profile,
            input_template_version=args.input_template_version,
            max_file_bytes=args.max_file_bytes,
            mime_types=tuple(args.mime_type),
        )
        print(
            media_embedding_coverage_json(report)
            if args.json
            else format_media_embedding_coverage(report)
        )
        return 0
    if args.memory_command == "media-search":
        from research_x.memory.media_embeddings import (
            format_media_search,
            media_search_json,
            search_media_embeddings,
        )

        hits = search_media_embeddings(
            args.db,
            args.query,
            provider=args.provider,
            model=args.model,
            dimensions=args.dimensions,
            embedding_profile=args.embedding_profile,
            input_template_version=args.input_template_version,
            api_key_env=args.api_key_env,
            base_url=args.base_url,
            limit=args.limit,
            timeout_seconds=args.timeout_seconds,
            allow_provider_quota=args.allow_provider_quota,
        )
        print(media_search_json(hits) if args.json else format_media_search(hits))
        return 0
    if args.memory_command == "ocr-estimate":
        from research_x.memory.ocr import estimate_json, estimate_ocr_evidence, format_estimate

        estimate = estimate_ocr_evidence(
            args.db,
            sample_policy=args.sample_policy,
            limit=args.limit,
            max_file_bytes=args.max_file_bytes,
            media_ids=tuple(args.media_id),
            tweet_ids=tuple(args.tweet_id),
            engine_routes=tuple(args.engine_route),
        )
        print(estimate_json(estimate) if args.json else format_estimate(estimate))
        return 0
    if args.memory_command == "media-role-estimate":
        from research_x.memory.media_roles import (
            estimate_media_roles,
            format_media_role_summary,
            media_role_summary_json,
        )

        summary = estimate_media_roles(args.db, limit=args.limit)
        print(media_role_summary_json(summary) if args.json else format_media_role_summary(summary))
        return 0
    if args.memory_command == "media-role-build":
        from research_x.memory.media_roles import (
            build_media_roles,
            format_media_role_summary,
            media_role_summary_json,
        )

        summary = build_media_roles(args.db, limit=args.limit)
        print(media_role_summary_json(summary) if args.json else format_media_role_summary(summary))
        return 0
    if args.memory_command == "media-role-coverage":
        from research_x.memory.media_roles import (
            format_media_role_summary,
            media_role_coverage,
            media_role_summary_json,
        )

        coverage = media_role_coverage(args.db)
        print(
            media_role_summary_json(coverage)
            if args.json
            else format_media_role_summary(coverage)
        )
        return 0
    if args.memory_command == "build-ocr-evidence":
        from research_x.memory.ocr import build_ocr_evidence, format_summary, summary_json

        local_ocr_providers = {"fake", "local"}
        if args.provider not in local_ocr_providers and not args.allow_real_api:
            raise RuntimeError(
                "provider OCR API use requires scoped ProviderExecutionPolicy, API Budget Guard "
                "preflight, and explicit paid/quota review. Re-run with provider=fake or "
                "provider=local for a local path."
            )
        with _api_budget_for_args(args):
            summary = build_ocr_evidence(
                args.db,
                provider=args.provider,
                model=args.model,
                ocr_profile=args.ocr_profile,
                sample_policy=args.sample_policy,
                limit=args.limit,
                max_file_bytes=args.max_file_bytes,
                timeout_seconds=args.timeout_seconds,
                promote_chunks=not args.no_promote_chunks,
                api_key_env=args.api_key_env,
                base_url=args.base_url,
                media_ids=tuple(args.media_id),
                tweet_ids=tuple(args.tweet_id),
                engine_routes=tuple(args.engine_route),
                allow_provider_quota=args.allow_real_api,
            )
        print(summary_json(summary) if args.json else format_summary(summary))
        return 0
    if args.memory_command == "ocr-coverage":
        from research_x.memory.ocr import coverage_json, format_coverage, ocr_coverage

        coverage = ocr_coverage(args.db)
        print(coverage_json(coverage) if args.json else format_coverage(coverage))
        return 0
    if args.memory_command == "ocr-promote-chunks":
        from research_x.memory.ocr import (
            format_promotion,
            promote_ocr_chunks,
            promotion_json,
        )

        profiles = ("raw_ocr", "caption", "vlm_caption", "codex_observation")
        if args.include_corrected:
            profiles = (*profiles, "corrected_text")
        summary = promote_ocr_chunks(args.db, limit=args.limit, include_profiles=profiles)
        print(promotion_json(summary) if args.json else format_promotion(summary))
        return 0
    if args.memory_command == "ocr-second-pass":
        from research_x.memory.ocr import (
            format_second_pass,
            mark_ocr_second_pass_candidates,
            second_pass_json,
        )

        summary = mark_ocr_second_pass_candidates(
            args.db,
            confidence_threshold=args.confidence_threshold,
            limit=args.limit,
            create_corrected_profile=not args.no_corrected_profile,
        )
        print(second_pass_json(summary) if args.json else format_second_pass(summary))
        return 0
    if args.memory_command == "media-observation-add":
        from research_x.memory.ocr import (
            add_media_observation,
            format_media_observation_summary,
            media_observation_summary_json,
        )

        text = Path(args.text_file).read_text(encoding="utf-8")
        summary = add_media_observation(
            args.db,
            media_id=args.media_id,
            observation_text=text,
            observation_kind=args.observation_kind,
            provider=args.provider,
            model=args.model,
            confidence=args.confidence,
            prompt=args.prompt,
            session_id=args.session_id,
            promote_chunks=not args.no_promote_chunks,
        )
        print(
            media_observation_summary_json(summary)
            if args.json
            else format_media_observation_summary(summary)
        )
        return 0
    if args.memory_command == "media-observation-import":
        from research_x.memory.ocr import (
            format_media_observation_summary,
            import_media_observations,
            media_observation_summary_json,
        )

        summary = import_media_observations(
            args.db,
            args.jsonl,
            promote_chunks=not args.no_promote_chunks,
        )
        print(
            media_observation_summary_json(summary)
            if args.json
            else format_media_observation_summary(summary)
        )
        return 0
    if args.memory_command == "media-observation-coverage":
        from research_x.memory.ocr import (
            format_media_observation_summary,
            media_observation_coverage,
            media_observation_summary_json,
        )

        coverage = media_observation_coverage(args.db)
        print(
            media_observation_summary_json(coverage)
            if args.json
            else format_media_observation_summary(coverage)
        )
        return 0
    if args.memory_command == "ocr-search":
        from research_x.memory.ocr import format_search, ocr_search, search_json

        hits = ocr_search(args.db, args.query, limit=args.limit)
        print(search_json(hits) if args.json else format_search(hits))
        return 0
    if args.memory_command == "build-relations":
        from research_x.memory.relations import build_memory_relations, summary_as_dict

        summary = build_memory_relations(args.db)
        print(json.dumps(summary_as_dict(summary), ensure_ascii=False, indent=2))
        return 0
    if args.memory_command == "relations":
        from research_x.memory.relations import format_relations, relations_for_doc

        relations = relations_for_doc(args.db, args.doc_id, limit=args.limit)
        print(format_relations(relations, json_output=args.json))
        return 0
    if args.memory_command == "judge-relations":
        from research_x.memory.judge_relations import (
            format_relation_judge_summary,
            judge_memory_relations,
            relation_judge_summary_json,
        )

        store = _resolve_fixture_sensitive_store(args.store, args.provider)
        _require_fixture_provider_opt_in(
            provider=args.provider,
            role="relation judge",
            store=store,
            allow=args.allow_fixture_provider,
        )
        summary = judge_memory_relations(
            args.db,
            provider=args.provider,
            model=args.model,
            api_key_env=args.api_key_env,
            base_url=args.base_url,
            candidate_relation_types=(
                tuple(args.candidate_relation_type) if args.candidate_relation_type else None
            ),
            limit=args.limit,
            batch_size=args.batch_size,
            min_confidence=args.min_confidence,
            prompt_version=args.prompt_version,
            timeout_seconds=args.timeout_seconds,
            store=store,
        )
        print(
            relation_judge_summary_json(summary)
            if args.json
            else format_relation_judge_summary(summary)
        )
        return 0
    if args.memory_command == "search":
        from research_x.memory.search import format_search_results, search_memory

        route_plan = None
        if args.route:
            from research_x.memory.objective_routes import plan_route_aware_retrieval

            route_plan = plan_route_aware_retrieval(args.query, requested_route=args.route)
        results = search_memory(
            args.db,
            args.query,
            limit=args.limit,
            doc_type=args.doc_type,
            account=args.account,
            semantic_provider=args.semantic_provider,
            semantic_space_id=args.semantic_space_id,
            semantic_model=args.semantic_model,
            semantic_dimensions=args.semantic_dimensions,
            semantic_profile=args.semantic_profile,
            semantic_template_version=args.semantic_template_version,
            semantic_api_key_env=args.semantic_api_key_env,
            semantic_base_url=args.semantic_base_url,
            semantic_weight=args.semantic_weight,
            semantic_candidates=args.semantic_candidates,
            semantic_backend=args.semantic_backend,
            route=args.route,
            intent=args.intent,
            author_id=args.author_id,
            bookmark_owner_account_id=args.bookmark_owner_account_id,
            source_kind=args.source_kind,
            ownership_kind=args.ownership_kind,
            content_role=args.content_role,
            relation_role=args.relation_role,
            language=args.language,
            modality_kind=args.modality_kind,
            sensitivity_kind=args.sensitivity_kind,
            projection_profile=args.projection_profile,
            filter_space_id=args.space_id,
            require_projections=args.require_projections,
            explain_filters=args.explain_filters,
        )
        filter_explanation = (
            results[0].metadata.get("embedding_filter_explanation")
            if results and args.explain_filters
            else None
        )
        print(
            format_search_results(
                results,
                json_output=args.json,
                route_plan=route_plan,
                filter_explanation=filter_explanation,
            )
        )
        return 0
    if args.memory_command == "plan":
        from research_x.memory.query import build_query_plan, query_plan_json

        print(query_plan_json(build_query_plan(args.query)))
        return 0
    if args.memory_command == "evidence":
        from research_x.memory.evidence import build_evidence_bundle, evidence_bundle_json

        bundle = build_evidence_bundle(
            args.db,
            args.query,
            limit=args.limit,
            doc_type=args.doc_type,
            account=args.account,
            semantic_provider=args.semantic_provider,
            semantic_space_id=args.semantic_space_id,
            semantic_model=args.semantic_model,
            semantic_dimensions=args.semantic_dimensions,
            semantic_profile=args.semantic_profile,
            semantic_template_version=args.semantic_template_version,
            semantic_api_key_env=args.semantic_api_key_env,
            semantic_base_url=args.semantic_base_url,
            semantic_weight=args.semantic_weight,
            semantic_candidates=args.semantic_candidates,
            semantic_backend=args.semantic_backend,
        )
        print(evidence_bundle_json(bundle))
        return 0
    if args.memory_command == "context":
        from research_x.memory.context import build_context_bundle, context_bundle_json

        store = _resolve_fixture_sensitive_store(
            args.store,
            args.external_provider if args.external_run_id else None,
        )
        _require_fixture_provider_opt_in(
            provider=args.external_provider if args.external_run_id else None,
            role="reader/extract",
            store=store,
            allow=args.allow_fixture_provider,
        )
        bundle = build_context_bundle(
            args.db,
            args.query,
            limit=args.limit,
            doc_type=args.doc_type,
            account=args.account,
            semantic_provider=args.semantic_provider,
            semantic_space_id=args.semantic_space_id,
            semantic_model=args.semantic_model,
            semantic_dimensions=args.semantic_dimensions,
            semantic_profile=args.semantic_profile,
            semantic_template_version=args.semantic_template_version,
            semantic_api_key_env=args.semantic_api_key_env,
            semantic_base_url=args.semantic_base_url,
            semantic_weight=args.semantic_weight,
            semantic_candidates=args.semantic_candidates,
            semantic_backend=args.semantic_backend,
            intent=args.intent,
            author_id=args.author_id,
            bookmark_owner_account_id=args.bookmark_owner_account_id,
            source_kind=args.source_kind,
            ownership_kind=args.ownership_kind,
            content_role=args.content_role,
            relation_role=args.relation_role,
            language=args.language,
            modality_kind=args.modality_kind,
            sensitivity_kind=args.sensitivity_kind,
            projection_profile=args.projection_profile,
            filter_space_id=args.space_id,
            require_projections=args.require_projections,
            explain_filters=args.explain_filters,
            external_run_id=args.external_run_id,
            external_reader_provider=args.external_provider,
            external_limit=args.external_limit,
            external_max_chars=args.external_max_chars,
            external_timeout_seconds=args.external_timeout_seconds,
            external_user_agent=args.external_user_agent,
            external_max_bytes=args.external_max_bytes,
            store=store,
        )
        print(context_bundle_json(bundle, budget_policy=_context_budget_policy_for_args(args)))
        return 0
    if args.memory_command == "answer":
        from research_x.memory.answer import answer_json, build_memory_answer

        store = _resolve_fixture_sensitive_store(
            args.store,
            args.answer_provider,
            args.external_provider if args.external_run_id else None,
        )
        _require_fixture_provider_opt_in(
            provider=args.answer_provider,
            role="answer",
            store=store,
            allow=args.allow_fixture_provider,
        )
        _require_fixture_provider_opt_in(
            provider=args.external_provider if args.external_run_id else None,
            role="reader/extract",
            store=store,
            allow=args.allow_fixture_provider,
        )
        answer = build_memory_answer(
            args.db,
            args.query,
            limit=args.limit,
            doc_type=args.doc_type,
            account=args.account,
            semantic_provider=args.semantic_provider,
            semantic_space_id=args.semantic_space_id,
            semantic_model=args.semantic_model,
            semantic_dimensions=args.semantic_dimensions,
            semantic_profile=args.semantic_profile,
            semantic_template_version=args.semantic_template_version,
            semantic_api_key_env=args.semantic_api_key_env,
            semantic_base_url=args.semantic_base_url,
            semantic_weight=args.semantic_weight,
            semantic_candidates=args.semantic_candidates,
            semantic_backend=args.semantic_backend,
            external_run_id=args.external_run_id,
            external_reader_provider=args.external_provider,
            external_limit=args.external_limit,
            external_max_chars=args.external_max_chars,
            external_timeout_seconds=args.external_timeout_seconds,
            external_user_agent=args.external_user_agent,
            external_max_bytes=args.external_max_bytes,
            answer_provider=args.answer_provider,
            answer_model=args.answer_model,
            answer_api_key_env=args.answer_api_key_env,
            answer_base_url=args.answer_base_url,
            answer_timeout_seconds=args.answer_timeout_seconds,
            prompt_version=args.prompt_version,
            max_context_chunks=args.max_context_chunks,
            max_context_chars=args.max_context_chars,
            store=store,
        )
        print(answer_json(answer, budget_policy=_context_budget_policy_for_args(args)))
        return 0
    if args.memory_command == "workflow":
        from research_x.memory.workflow import (
            format_workflow,
            run_memory_workflow,
            workflow_json,
        )
        from research_x.tool_interface.memory_tool_contract import workflow_tool_output_json

        store = _resolve_fixture_sensitive_store(
            args.store,
            args.answer_provider if args.answer_provider != "none" else None,
            args.external_provider if args.external_run_id else None,
            (
                args.llm_context_provider
                if args.llm_context_provider != "none"
                else None
            ),
        )
        stores_artifacts = (
            args.persistence == "artifacts"
            or (args.persistence is None and store)
        )
        _require_fixture_provider_opt_in(
            provider=args.answer_provider if args.answer_provider != "none" else None,
            role="answer",
            store=stores_artifacts,
            allow=args.allow_fixture_provider,
        )
        _require_fixture_provider_opt_in(
            provider=args.external_provider if args.external_run_id else None,
            role="reader/extract",
            store=stores_artifacts,
            allow=args.allow_fixture_provider,
        )
        _require_fixture_provider_opt_in(
            provider=(
                args.llm_context_provider
                if args.llm_context_provider != "none"
                else None
            ),
            role="llm-context",
            store=stores_artifacts,
            allow=args.allow_fixture_provider,
        )
        workflow = run_memory_workflow(
            args.db,
            args.query,
            route=args.route,
            limit=args.limit,
            doc_type=args.doc_type,
            account=args.account,
            semantic_provider=args.semantic_provider,
            semantic_space_id=args.semantic_space_id,
            semantic_model=args.semantic_model,
            semantic_dimensions=args.semantic_dimensions,
            semantic_profile=args.semantic_profile,
            semantic_template_version=args.semantic_template_version,
            semantic_api_key_env=args.semantic_api_key_env,
            semantic_base_url=args.semantic_base_url,
            semantic_weight=args.semantic_weight,
            semantic_candidates=args.semantic_candidates,
            semantic_backend=args.semantic_backend,
            external_run_id=args.external_run_id,
            external_reader_provider=args.external_provider,
            external_limit=args.external_limit,
            external_max_chars=args.external_max_chars,
            external_timeout_seconds=args.external_timeout_seconds,
            external_user_agent=args.external_user_agent,
            external_max_bytes=args.external_max_bytes,
            llm_context_provider=args.llm_context_provider,
            llm_context_api_key_env=args.llm_context_api_key_env,
            llm_context_endpoint=args.llm_context_endpoint,
            llm_context_country=args.llm_context_country,
            llm_context_search_lang=args.llm_context_search_lang,
            llm_context_count=args.llm_context_count,
            llm_context_max_urls=args.llm_context_max_urls,
            llm_context_max_tokens=args.llm_context_max_tokens,
            llm_context_max_snippets=args.llm_context_max_snippets,
            llm_context_threshold_mode=args.llm_context_threshold_mode,
            llm_context_max_tokens_per_url=args.llm_context_max_tokens_per_url,
            llm_context_max_snippets_per_url=args.llm_context_max_snippets_per_url,
            llm_context_freshness=args.llm_context_freshness,
            llm_context_enable_local=args.llm_context_enable_local,
            llm_context_goggles=args.llm_context_goggles,
            llm_context_max_chars_per_source=args.llm_context_max_chars_per_source,
            llm_context_timeout_seconds=args.llm_context_timeout_seconds,
            answer_provider=args.answer_provider,
            answer_model=args.answer_model,
            answer_api_key_env=args.answer_api_key_env,
            answer_base_url=args.answer_base_url,
            answer_timeout_seconds=args.answer_timeout_seconds,
            prompt_version=args.prompt_version,
            max_context_chunks=args.max_context_chunks,
            max_context_chars=args.max_context_chars,
            max_steps=args.max_steps,
            store=store,
            persistence=args.persistence,
        )
        if args.tool_json:
            print(workflow_tool_output_json(workflow, db_path=args.db))
        elif args.json:
            print(workflow_json(workflow, budget_policy=_context_budget_policy_for_args(args)))
        else:
            print(format_workflow(workflow))
        return 1 if workflow.status == "error" else 0
    if args.memory_command == "external-search":
        from research_x.memory.external import external_evidence_json, search_external_evidence

        store = _resolve_fixture_sensitive_store(args.store, args.provider)
        _require_fixture_provider_opt_in(
            provider=args.provider,
            role="external-search",
            store=store,
            allow=args.allow_fixture_provider,
        )
        bundle = search_external_evidence(
            args.db,
            args.query,
            provider=args.provider,
            limit=args.limit,
            api_key_env=args.api_key_env,
            endpoint=args.endpoint,
            country=args.country,
            language=args.language,
            location=args.location,
            timeout_seconds=args.timeout_seconds,
            store=store,
        )
        print(external_evidence_json(bundle))
        return 0
    if args.memory_command == "extract-url":
        from research_x.memory.reader import (
            extract_external_run_to_context,
            extract_url_to_context,
            reader_context_json,
        )

        if not args.url and not args.external_run_id:
            raise ValueError("pass --url or --external-run-id")
        if args.url and args.external_run_id:
            raise ValueError("pass only one of --url or --external-run-id")
        store = _resolve_fixture_sensitive_store(args.store, args.provider)
        _require_fixture_provider_opt_in(
            provider=args.provider,
            role="reader/extract",
            store=store,
            allow=args.allow_fixture_provider,
        )
        if args.external_run_id:
            bundles = extract_external_run_to_context(
                args.db,
                args.external_run_id,
                provider=args.provider,
                limit=args.limit,
                query=args.query,
                max_chars=args.max_chars,
                timeout_seconds=args.timeout_seconds,
                user_agent=args.user_agent,
                max_bytes=args.max_bytes,
                store=store,
            )
            print(reader_context_json(bundles))
            return 0
        bundle = extract_url_to_context(
            args.db,
            args.url,
            provider=args.provider,
            query=args.query,
            title=args.title,
            max_chars=args.max_chars,
            timeout_seconds=args.timeout_seconds,
            user_agent=args.user_agent,
            max_bytes=args.max_bytes,
            store=store,
        )
        print(reader_context_json(bundle))
        return 0
    if args.memory_command == "llm-context":
        from research_x.memory.llm_context import fetch_llm_context_to_context, llm_context_json

        store = _resolve_fixture_sensitive_store(args.store, args.provider)
        _require_fixture_provider_opt_in(
            provider=args.provider,
            role="llm-context",
            store=store,
            allow=args.allow_fixture_provider,
        )
        bundle = fetch_llm_context_to_context(
            args.db,
            args.query,
            provider=args.provider,
            api_key_env=args.api_key_env,
            endpoint=args.endpoint,
            country=args.country,
            search_lang=args.search_lang,
            count=args.count,
            maximum_number_of_urls=args.max_urls,
            maximum_number_of_tokens=args.max_tokens,
            maximum_number_of_snippets=args.max_snippets,
            context_threshold_mode=args.threshold_mode,
            maximum_number_of_tokens_per_url=args.max_tokens_per_url,
            maximum_number_of_snippets_per_url=args.max_snippets_per_url,
            freshness=args.freshness,
            enable_local=args.enable_local,
            goggles=args.goggles,
            max_chars_per_source=args.max_chars_per_source,
            timeout_seconds=args.timeout_seconds,
            store=store,
        )
        print(llm_context_json(bundle))
        return 0
    if args.memory_command == "feedback":
        from research_x.memory.feedback import add_feedback

        feedback_id = add_feedback(
            args.db,
            query=args.query,
            doc_id=args.doc_id,
            label=args.label,
            route=args.route,
            note=args.note,
        )
        print(f"feedback: {feedback_id}")
        return 0
    if args.memory_command == "governance":
        from research_x.memory.governance import (
            add_governance_record,
            add_tombstone,
            format_governance_records,
            governance_records_json,
            is_artifact_tombstoned,
            list_governance_records,
            restore_governance_record,
        )

        if args.governance_command == "add":
            record = add_governance_record(
                args.db,
                governance_type=args.type,
                subject_kind=args.subject_kind,
                subject_id=args.subject_id,
                statement=args.statement,
                source_kind=args.source_kind,
                source_id=args.source_id,
                source_url=args.source_url,
                source_hash=args.source_hash,
                source_anchor=_parse_key_value_pairs(args.source_anchor),
                confidence=args.confidence,
                retention_policy=args.retention_policy,
                expires_at=args.expires_at,
                metadata=_parse_key_value_pairs(args.metadata),
            )
            print(
                json.dumps(record.as_dict(), ensure_ascii=False, indent=2, sort_keys=True)
                if args.json
                else f"governance: {record.record_id}"
            )
            return 0
        if args.governance_command == "tombstone":
            record = add_tombstone(
                args.db,
                artifact_kind=args.artifact_kind,
                artifact_id=args.artifact_id,
                reason=args.reason,
                source_kind=args.source_kind,
                source_id=args.source_id,
                source_url=args.source_url,
                source_hash=args.source_hash,
                source_anchor=_parse_key_value_pairs(args.source_anchor),
                retention_policy=args.retention_policy,
                metadata=_parse_key_value_pairs(args.metadata),
            )
            print(
                json.dumps(record.as_dict(), ensure_ascii=False, indent=2, sort_keys=True)
                if args.json
                else f"governance tombstone: {record.record_id}"
            )
            return 0
        if args.governance_command == "restore":
            record = restore_governance_record(
                args.db,
                record_id=args.record_id,
                reason=args.reason,
            )
            print(
                json.dumps(record.as_dict(), ensure_ascii=False, indent=2, sort_keys=True)
                if args.json
                else f"governance restored: {record.record_id}"
            )
            return 0
        if args.governance_command == "list":
            records = list_governance_records(
                args.db,
                governance_type=args.type,
                subject_kind=args.subject_kind,
                subject_id=args.subject_id,
                include_inactive=args.include_inactive,
                limit=args.limit,
            )
            print(
                governance_records_json(records)
                if args.json
                else format_governance_records(records)
            )
            return 0
        if args.governance_command == "check":
            tombstoned = is_artifact_tombstoned(
                args.db,
                artifact_kind=args.artifact_kind,
                artifact_id=args.artifact_id,
            )
            payload = {
                "artifact_kind": args.artifact_kind,
                "artifact_id": args.artifact_id,
                "tombstoned": tombstoned,
            }
            print(
                json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
                if args.json
                else f"tombstoned={str(tombstoned).lower()}"
            )
            return 0
        raise AssertionError(f"unhandled governance command {args.governance_command}")
    if args.memory_command == "export-corpus2skill":
        from research_x.memory.corpus import (
            export_corpus2skill_bundle,
            export_corpus2skill_jsonl,
            summary_as_dict,
        )

        if args.openai_agent_name and not (args.openai_agent_yaml or args.hook_advisory):
            raise ValueError(
                "pass --openai-agent-yaml or --hook-advisory when using --openai-agent-name"
            )
        if args.bundle_dir:
            summary = export_corpus2skill_bundle(
                args.db,
                args.bundle_dir,
                limit=args.limit,
                doc_types=tuple(args.doc_type),
                include_openai_agent=args.openai_agent_yaml,
                include_hook_advisory=args.hook_advisory,
                openai_agent_name=args.openai_agent_name or "research-x-memory-navigation",
            )
            print(json.dumps(summary_as_dict(summary), ensure_ascii=False, indent=2))
            return 0
        if args.openai_agent_yaml or args.hook_advisory:
            raise ValueError("pass --bundle-dir when using advisory agent export options")
        if not args.out:
            raise ValueError("pass --out for JSONL export or --bundle-dir for bundle export")
        count = export_corpus2skill_jsonl(
            args.db,
            args.out,
            limit=args.limit,
            doc_types=tuple(args.doc_type),
        )
        print(f"corpus2skill-export: rows={count} out={args.out}")
        return 0
    if args.memory_command == "eval":
        from research_x.memory.evals import (
            eval_results_json,
            format_eval_results,
            load_eval_cases,
            run_memory_eval,
            store_memory_eval_results,
        )

        cases = load_eval_cases(args.cases) if args.cases else None
        results = run_memory_eval(
            args.db,
            cases=cases,
            limit=args.limit,
            semantic_provider=args.semantic_provider,
            semantic_space_id=args.semantic_space_id,
            semantic_model=args.semantic_model,
            semantic_dimensions=args.semantic_dimensions,
            semantic_profile=args.semantic_profile,
            semantic_template_version=args.semantic_template_version,
            semantic_api_key_env=args.semantic_api_key_env,
            semantic_base_url=args.semantic_base_url,
            semantic_weight=args.semantic_weight,
            semantic_candidates=args.semantic_candidates,
            semantic_backend=args.semantic_backend,
            answer_provider=args.answer_provider,
            answer_model=args.answer_model,
            answer_api_key_env=args.answer_api_key_env,
            answer_base_url=args.answer_base_url,
            answer_timeout_seconds=args.answer_timeout_seconds,
            store_workflows=bool(args.store),
        )
        stored_run_id = None
        if args.store:
            stored_run_id = store_memory_eval_results(
                args.db,
                results,
                cases_path=args.cases,
                parameters={
                    "limit": args.limit,
                    "case_count": len(cases) if cases is not None else None,
                    "semantic_provider": args.semantic_provider,
                    "semantic_space_id": args.semantic_space_id,
                    "semantic_model": args.semantic_model,
                    "semantic_dimensions": args.semantic_dimensions,
                    "semantic_profile": args.semantic_profile,
                    "semantic_template_version": args.semantic_template_version,
                    "semantic_weight": args.semantic_weight,
                    "semantic_candidates": args.semantic_candidates,
                    "answer_provider": args.answer_provider,
                    "answer_model": args.answer_model,
                },
            )
        if args.json:
            if stored_run_id:
                print(
                    json.dumps(
                        {
                            "run_id": stored_run_id,
                            "results": [result.__dict__ for result in results],
                        },
                        ensure_ascii=False,
                        indent=2,
                        sort_keys=True,
                    )
                )
            else:
                print(eval_results_json(results))
        else:
            output = format_eval_results(results)
            if stored_run_id:
                output = f"{output}\nstored eval run: {stored_run_id}"
            print(output)
        return 2 if args.strict and any(not result.ok for result in results) else 0
    if args.memory_command == "portfolio-eval":
        from research_x.memory.evals import load_eval_cases
        from research_x.memory.portfolio import (
            format_portfolio_eval,
            parse_portfolio_reranker_specs,
            parse_portfolio_semantic_specs,
            portfolio_eval_json,
            run_portfolio_eval,
        )
        from research_x.memory.retrieval_strategy import (
            reranker_spec_strings_for_strategies,
            semantic_spec_strings_for_strategies,
        )

        cases = load_eval_cases(args.cases) if args.cases else None
        semantic_spec_values = [
            *args.semantic_spec,
            *semantic_spec_strings_for_strategies(tuple(args.strategy)),
        ]
        reranker_spec_values = [
            *args.reranker_spec,
            *reranker_spec_strings_for_strategies(tuple(args.strategy)),
        ]
        report = run_portfolio_eval(
            args.db,
            cases=cases,
            case_limit=args.case_limit,
            fast=args.fast,
            semantic_specs=parse_portfolio_semantic_specs(semantic_spec_values),
            reranker_specs=parse_portfolio_reranker_specs(reranker_spec_values),
            limit=args.limit,
            arm_limit=args.arm_limit,
            rrf_k=args.rrf_k,
            fusion_mode=args.fusion_mode,
            min_agreement=args.min_agreement,
        )
        print(portfolio_eval_json(report) if args.json else format_portfolio_eval(report))
        strict_failed = any(case.status != "ok" for case in report.cases) or bool(
            report.verdict.blockers
        )
        return 2 if args.strict and strict_failed else 0
    if args.memory_command == "rerank":
        from research_x.memory.rerank import (
            format_rerank_report,
            rerank_evidence_query,
            rerank_report_json,
        )

        store = _resolve_fixture_sensitive_store(args.store, args.provider)
        _require_fixture_provider_opt_in(
            provider=args.provider,
            role="reranker",
            store=store,
            allow=args.allow_fixture_provider,
        )
        report = rerank_evidence_query(
            args.db,
            args.query,
            provider=args.provider,
            model=args.model,
            limit=args.limit,
            top_n=args.top_n,
            api_key_env=args.api_key_env,
            base_url=args.base_url,
            timeout_seconds=args.timeout_seconds,
            store=store,
        )
        print(rerank_report_json(report) if args.json else format_rerank_report(report))
        return 0
    if args.memory_command == "eval-runs":
        from research_x.memory.evals import eval_runs_json, format_eval_runs, list_memory_eval_runs

        runs = list_memory_eval_runs(args.db, limit=args.limit)
        print(eval_runs_json(runs) if args.json else format_eval_runs(runs))
        return 0
    if args.memory_command == "eval-show":
        from research_x.memory.evals import (
            eval_run_json,
            format_eval_run,
            load_memory_eval_run,
        )

        payload = load_memory_eval_run(args.db, args.run_id)
        print(eval_run_json(payload) if args.json else format_eval_run(payload))
        return 0
    if args.memory_command == "research-runs":
        from research_x.memory.observability import (
            format_research_runs,
            list_research_runs,
            research_runs_json,
        )

        runs = list_research_runs(args.db, run_kind=args.kind, limit=args.limit)
        print(research_runs_json(runs) if args.json else format_research_runs(runs))
        return 0
    if args.memory_command == "show-run":
        from research_x.memory.observability import (
            format_research_run,
            research_run_json,
            show_research_run,
        )

        detail = show_research_run(args.db, args.run_id, run_kind=args.kind)
        print(research_run_json(detail) if args.json else format_research_run(detail))
        return 0
    if args.memory_command == "question-types":
        from research_x.memory.question_types import format_question_types, question_types_json

        print(question_types_json() if args.json else format_question_types())
        return 0
    if args.memory_command == "objective-routes":
        from research_x.memory.objective_routes import (
            format_objective_route_plan,
            objective_route_plan_json,
            plan_objective_routes,
            store_objective_route_plan,
        )

        plan = plan_objective_routes(
            args.query,
            requested_route=args.route,
            budget_policy=args.budget_policy,
            output_mode=args.output_mode,
        )
        if args.store:
            store_objective_route_plan(args.db, plan)
        print(objective_route_plan_json(plan) if args.json else format_objective_route_plan(plan))
        return 0
    if args.memory_command == "objective-execute":
        from research_x.memory.objective_executor import (
            format_objective_route_execution,
            objective_route_execution_json,
            run_objective_route_execution,
        )

        execution = run_objective_route_execution(
            args.db,
            args.query,
            route=args.route,
            budget_policy=args.budget_policy,
            output_mode=args.output_mode,
            limit=args.limit,
            account=args.account,
            max_route_arms=args.max_route_arms,
            ocr_mode=args.ocr_mode,
            ocr_limit=args.ocr_limit,
            ocr_sample_policy=args.ocr_sample_policy,
            ocr_max_file_bytes=args.ocr_max_file_bytes,
            store=args.store,
        )
        print(
            objective_route_execution_json(execution)
            if args.json
            else format_objective_route_execution(execution)
        )
        return 0
    if args.memory_command == "final-skeleton-preflight":
        from research_x.memory.final_skeleton import (
            final_skeleton_preflight_json,
            format_final_skeleton_preflight,
            run_final_skeleton_preflight,
        )

        report = run_final_skeleton_preflight(
            args.db,
            args.query,
            route=args.route,
            limit=args.limit,
            store=args.store,
        )
        print(
            final_skeleton_preflight_json(report)
            if args.json
            else format_final_skeleton_preflight(report)
        )
        return 0
    if args.memory_command == "build-retrieval-text":
        from research_x.memory.retrieval_text import (
            build_retrieval_text_profiles,
            format_retrieval_text_summary,
            retrieval_text_summary_json,
        )

        summary = build_retrieval_text_profiles(
            args.db,
            profiles=tuple(args.profile) if args.profile else ("raw_compact", "contextual_bm25"),
            limit=args.limit,
            rebuild=args.rebuild,
        )
        print(
            retrieval_text_summary_json(summary)
            if args.json
            else format_retrieval_text_summary(summary)
        )
        return 0
    if args.memory_command == "retrieval-text-coverage":
        from research_x.memory.retrieval_text import (
            format_retrieval_text_summary,
            retrieval_text_coverage,
            retrieval_text_summary_json,
        )

        coverage = retrieval_text_coverage(args.db)
        print(
            retrieval_text_summary_json(coverage)
            if args.json
            else format_retrieval_text_summary(coverage)
        )
        return 0
    if args.memory_command in {"retrieval-strategies", "embedding-strategies"}:
        from research_x.memory.retrieval_strategy import (
            format_retrieval_strategies,
            retrieval_strategies_json,
        )

        kwargs = {
            "query": args.query,
            "question_types": tuple(args.question_type),
            "strategy_ids": tuple(args.strategy),
        }
        print(
            retrieval_strategies_json(**kwargs)
            if args.json
            else format_retrieval_strategies(**kwargs)
        )
        return 0
    raise AssertionError(f"unhandled memory command {args.memory_command}")


def _require_fixture_provider_opt_in(
    *,
    provider: str | None,
    role: str,
    store: bool,
    allow: bool,
) -> None:
    if provider != "fake" or not store or allow:
        return
    raise ValueError(
        f"{role} provider 'fake' is diagnostic-only. "
        "Pass --no-store for a dry wiring check, or pass --allow-fixture-provider "
        "when intentionally writing fixture rows to a test DB."
    )


def _context_budget_policy_for_args(args: argparse.Namespace):
    if not hasattr(args, "context_budget_max_chars"):
        return None
    values = (
        args.context_budget_max_chars,
        args.context_budget_chunk_chars,
        args.context_budget_preview_chars,
        args.context_offload_dir,
    )
    if all(value is None for value in values):
        return None

    from research_x.memory.context_budget import (
        DEFAULT_CONTEXT_OFFLOAD_DIR,
        ContextBudgetPolicy,
    )

    defaults = ContextBudgetPolicy()
    return ContextBudgetPolicy(
        max_output_chars=args.context_budget_max_chars or defaults.max_output_chars,
        max_inline_chunk_chars=(
            args.context_budget_chunk_chars or defaults.max_inline_chunk_chars
        ),
        preview_chars=args.context_budget_preview_chars or defaults.preview_chars,
        offload_dir=args.context_offload_dir or DEFAULT_CONTEXT_OFFLOAD_DIR,
    )


def _parse_key_value_pairs(values: list[str]) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for value in values:
        if "=" not in value:
            raise ValueError(f"expected key=value: {value}")
        key, raw = value.split("=", 1)
        key = key.strip()
        if not key:
            raise ValueError(f"empty key in key=value pair: {value}")
        parsed[key] = raw
    return parsed


def _resolve_fixture_sensitive_store(
    raw_store: bool | None,
    *providers: str | None,
) -> bool:
    if raw_store is not None:
        return raw_store
    return not any(provider == "fake" for provider in providers if provider)


def _configure_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
