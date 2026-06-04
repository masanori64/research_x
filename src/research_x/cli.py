from __future__ import annotations

import argparse
import contextlib
import json
import sys
from pathlib import Path

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


def _add_api_budget_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--api-budget-policy",
        default="default",
        help="API budget policy id used for paid API calls",
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
        help="allow paid API calls even when provider/model price is not in the local catalog",
    )


def _api_budget_for_args(args: argparse.Namespace):
    if not hasattr(args, "api_budget_policy"):
        return contextlib.nullcontext()
    db_path = getattr(args, "db", None) or "runs/x_data.sqlite3"
    from research_x.memory.api_budget import api_budget_context

    return api_budget_context(
        db_path=db_path,
        policy_id=args.api_budget_policy,
        run_id=args.api_run_id,
        max_run_usd_override=args.max_run_usd,
        allow_unpriced_api=args.allow_unpriced_api,
        metadata={
            "cli_command": getattr(args, "command", None),
            "memory_command": getattr(args, "memory_command", None),
        },
    )


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
        help="enable kill switch for new paid API calls",
    )
    memory_api_budget_stop_parser.add_argument("--db", default="runs/x_data.sqlite3")
    memory_api_budget_stop_parser.add_argument("--policy-id", default="default")
    memory_api_budget_stop_parser.add_argument("--json", action="store_true")
    memory_api_budget_resume_parser = memory_api_budget_subparsers.add_parser(
        "resume",
        help="disable kill switch for new paid API calls",
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
    memory_embedding_parser = memory_subparsers.add_parser(
        "build-embeddings",
        help="build semantic embedding index over memory_documents",
    )
    memory_embedding_parser.add_argument("--db", default="runs/x_data.sqlite3")
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
    memory_embedding_parser.add_argument("--rebuild", action="store_true")
    memory_embedding_parser.add_argument("--progress-every", type=int, default=1000)
    _add_api_budget_options(memory_embedding_parser)
    memory_embedding_estimate_parser = memory_subparsers.add_parser(
        "embedding-estimate",
        help="estimate documents, API batches, tokens, and optional cost for embedding builds",
    )
    memory_embedding_estimate_parser.add_argument("--db", default="runs/x_data.sqlite3")
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
    memory_embedding_estimate_parser.add_argument("--rebuild", action="store_true")
    memory_embedding_estimate_parser.add_argument(
        "--price-per-million-input-tokens",
        type=float,
        default=None,
        help="optional provider price used only for a rough input-cost estimate",
    )
    memory_embedding_estimate_parser.add_argument("--json", action="store_true")
    memory_specs_parser = memory_subparsers.add_parser(
        "embedding-specs",
        help="list available embedding indexes in the DB",
    )
    memory_specs_parser.add_argument("--db", default="runs/x_data.sqlite3")
    memory_embedding_coverage_parser = memory_subparsers.add_parser(
        "embedding-coverage",
        help="show embedding coverage and staleness by memory document type",
    )
    memory_embedding_coverage_parser.add_argument("--db", default="runs/x_data.sqlite3")
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
        help="search native media embeddings and restore tweet/media source bundles",
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
    _add_api_budget_options(memory_media_search_parser)
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
    memory_search_parser.add_argument("--json", action="store_true")
    memory_search_parser.add_argument(
        "--semantic-provider",
        default=None,
        choices=MEMORY_EMBEDDING_PROVIDER_CHOICES,
        help=(
            "optional semantic provider: auto, local_hash, openai, gemini, voyage, "
            "cohere, mistral, jina, or openai_compatible"
        ),
    )
    memory_search_parser.add_argument("--semantic-model", default=None)
    memory_search_parser.add_argument("--semantic-dimensions", type=int, default=None)
    memory_search_parser.add_argument("--semantic-profile", default=None)
    memory_search_parser.add_argument("--semantic-template-version", default=None)
    memory_search_parser.add_argument("--semantic-api-key-env", default=None)
    memory_search_parser.add_argument("--semantic-base-url", default=None)
    memory_search_parser.add_argument("--semantic-weight", type=float, default=3.0)
    memory_search_parser.add_argument("--semantic-candidates", type=int, default=80)
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
    memory_evidence_parser.add_argument("--semantic-model", default=None)
    memory_evidence_parser.add_argument("--semantic-dimensions", type=int, default=None)
    memory_evidence_parser.add_argument("--semantic-profile", default=None)
    memory_evidence_parser.add_argument("--semantic-template-version", default=None)
    memory_evidence_parser.add_argument("--semantic-api-key-env", default=None)
    memory_evidence_parser.add_argument("--semantic-base-url", default=None)
    memory_evidence_parser.add_argument("--semantic-weight", type=float, default=3.0)
    memory_evidence_parser.add_argument("--semantic-candidates", type=int, default=80)
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
    memory_context_parser.add_argument(
        "--semantic-provider",
        default=None,
        choices=MEMORY_EMBEDDING_PROVIDER_CHOICES,
    )
    memory_context_parser.add_argument("--semantic-model", default=None)
    memory_context_parser.add_argument("--semantic-dimensions", type=int, default=None)
    memory_context_parser.add_argument("--semantic-profile", default=None)
    memory_context_parser.add_argument("--semantic-template-version", default=None)
    memory_context_parser.add_argument("--semantic-api-key-env", default=None)
    memory_context_parser.add_argument("--semantic-base-url", default=None)
    memory_context_parser.add_argument("--semantic-weight", type=float, default=3.0)
    memory_context_parser.add_argument("--semantic-candidates", type=int, default=80)
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
    memory_answer_parser.add_argument("--semantic-model", default=None)
    memory_answer_parser.add_argument("--semantic-dimensions", type=int, default=None)
    memory_answer_parser.add_argument("--semantic-profile", default=None)
    memory_answer_parser.add_argument("--semantic-template-version", default=None)
    memory_answer_parser.add_argument("--semantic-api-key-env", default=None)
    memory_answer_parser.add_argument("--semantic-base-url", default=None)
    memory_answer_parser.add_argument("--semantic-weight", type=float, default=3.0)
    memory_answer_parser.add_argument("--semantic-candidates", type=int, default=80)
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
    memory_workflow_parser.add_argument("--json", action="store_true")
    memory_workflow_parser.add_argument(
        "--semantic-provider",
        default=None,
        choices=MEMORY_EMBEDDING_PROVIDER_CHOICES,
    )
    memory_workflow_parser.add_argument("--semantic-model", default=None)
    memory_workflow_parser.add_argument("--semantic-dimensions", type=int, default=None)
    memory_workflow_parser.add_argument("--semantic-profile", default=None)
    memory_workflow_parser.add_argument("--semantic-template-version", default=None)
    memory_workflow_parser.add_argument("--semantic-api-key-env", default=None)
    memory_workflow_parser.add_argument("--semantic-base-url", default=None)
    memory_workflow_parser.add_argument("--semantic-weight", type=float, default=3.0)
    memory_workflow_parser.add_argument("--semantic-candidates", type=int, default=80)
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
        "--allow-fixture-provider",
        action="store_true",
        help="allow storing deterministic fake provider output for tests only",
    )
    _add_api_budget_options(memory_workflow_parser)
    memory_external_parser = memory_subparsers.add_parser(
        "external-search",
        help="run an external URL-discovery provider and store normalized results",
    )
    memory_external_parser.add_argument("--db", default="runs/x_data.sqlite3")
    memory_external_parser.add_argument("--query", required=True)
    memory_external_parser.add_argument(
        "--provider",
        choices=["fake", "serper"],
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
    memory_eval_parser.add_argument("--semantic-model", default=None)
    memory_eval_parser.add_argument("--semantic-dimensions", type=int, default=None)
    memory_eval_parser.add_argument("--semantic-profile", default=None)
    memory_eval_parser.add_argument("--semantic-template-version", default=None)
    memory_eval_parser.add_argument("--semantic-api-key-env", default=None)
    memory_eval_parser.add_argument("--semantic-base-url", default=None)
    memory_eval_parser.add_argument("--semantic-weight", type=float, default=3.0)
    memory_eval_parser.add_argument("--semantic-candidates", type=int, default=80)
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
            "compare lexical, source-bundle, workflow, and candidate semantic arms "
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
    memory_question_types_parser = memory_subparsers.add_parser(
        "question-types",
        help="list memory-search question types used to broaden eval coverage",
    )
    memory_question_types_parser.add_argument("--json", action="store_true")
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
        action=argparse.BooleanOptionalAction,
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
            format_api_budget_status,
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
    if args.memory_command == "api-watch":
        from research_x.memory.api_budget import serve_api_watch

        serve_api_watch(
            db_path=args.db,
            host=args.host,
            port=args.port,
            open_browser=args.open_browser,
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
        return 2 if args.strict and report.warnings else 0
    if args.memory_command == "build-embeddings":
        from research_x.memory.embeddings import build_memory_embeddings, summary_as_dict

        summary = build_memory_embeddings(
            args.db,
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
        )
        output = (
            embedding_estimate_json(estimate)
            if args.json
            else format_embedding_estimate(estimate)
        )
        print(output)
        return 0
    if args.memory_command == "embedding-specs":
        from research_x.memory.embeddings import available_embedding_specs

        specs = [spec.__dict__ for spec in available_embedding_specs(args.db)]
        print(json.dumps(specs, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    if args.memory_command == "embedding-coverage":
        from research_x.memory.embeddings import (
            embedding_coverage_json,
            embedding_coverage_report,
            format_embedding_coverage,
        )

        report = embedding_coverage_report(
            args.db,
            provider=None if args.provider == "latest" else args.provider,
            model=args.model,
            dimensions=args.dimensions,
            embedding_profile=args.embedding_profile,
            text_template_version=args.text_template_version,
        )
        print(embedding_coverage_json(report) if args.json else format_embedding_coverage(report))
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
        )
        print(media_search_json(hits) if args.json else format_media_search(hits))
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

        results = search_memory(
            args.db,
            args.query,
            limit=args.limit,
            doc_type=args.doc_type,
            account=args.account,
            semantic_provider=args.semantic_provider,
            semantic_model=args.semantic_model,
            semantic_dimensions=args.semantic_dimensions,
            semantic_profile=args.semantic_profile,
            semantic_template_version=args.semantic_template_version,
            semantic_api_key_env=args.semantic_api_key_env,
            semantic_base_url=args.semantic_base_url,
            semantic_weight=args.semantic_weight,
            semantic_candidates=args.semantic_candidates,
        )
        print(format_search_results(results, json_output=args.json))
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
            semantic_model=args.semantic_model,
            semantic_dimensions=args.semantic_dimensions,
            semantic_profile=args.semantic_profile,
            semantic_template_version=args.semantic_template_version,
            semantic_api_key_env=args.semantic_api_key_env,
            semantic_base_url=args.semantic_base_url,
            semantic_weight=args.semantic_weight,
            semantic_candidates=args.semantic_candidates,
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
            semantic_model=args.semantic_model,
            semantic_dimensions=args.semantic_dimensions,
            semantic_profile=args.semantic_profile,
            semantic_template_version=args.semantic_template_version,
            semantic_api_key_env=args.semantic_api_key_env,
            semantic_base_url=args.semantic_base_url,
            semantic_weight=args.semantic_weight,
            semantic_candidates=args.semantic_candidates,
            external_run_id=args.external_run_id,
            external_reader_provider=args.external_provider,
            external_limit=args.external_limit,
            external_max_chars=args.external_max_chars,
            external_timeout_seconds=args.external_timeout_seconds,
            external_user_agent=args.external_user_agent,
            external_max_bytes=args.external_max_bytes,
            store=store,
        )
        print(context_bundle_json(bundle))
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
            semantic_model=args.semantic_model,
            semantic_dimensions=args.semantic_dimensions,
            semantic_profile=args.semantic_profile,
            semantic_template_version=args.semantic_template_version,
            semantic_api_key_env=args.semantic_api_key_env,
            semantic_base_url=args.semantic_base_url,
            semantic_weight=args.semantic_weight,
            semantic_candidates=args.semantic_candidates,
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
        print(answer_json(answer))
        return 0
    if args.memory_command == "workflow":
        from research_x.memory.workflow import (
            format_workflow,
            run_memory_workflow,
            workflow_json,
        )

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
        _require_fixture_provider_opt_in(
            provider=args.answer_provider if args.answer_provider != "none" else None,
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
        _require_fixture_provider_opt_in(
            provider=(
                args.llm_context_provider
                if args.llm_context_provider != "none"
                else None
            ),
            role="llm-context",
            store=store,
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
            semantic_model=args.semantic_model,
            semantic_dimensions=args.semantic_dimensions,
            semantic_profile=args.semantic_profile,
            semantic_template_version=args.semantic_template_version,
            semantic_api_key_env=args.semantic_api_key_env,
            semantic_base_url=args.semantic_base_url,
            semantic_weight=args.semantic_weight,
            semantic_candidates=args.semantic_candidates,
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
        )
        print(workflow_json(workflow) if args.json else format_workflow(workflow))
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
    if args.memory_command == "export-corpus2skill":
        from research_x.memory.corpus import (
            export_corpus2skill_bundle,
            export_corpus2skill_jsonl,
            summary_as_dict,
        )

        if args.bundle_dir:
            summary = export_corpus2skill_bundle(
                args.db,
                args.bundle_dir,
                limit=args.limit,
                doc_types=tuple(args.doc_type),
            )
            print(json.dumps(summary_as_dict(summary), ensure_ascii=False, indent=2))
            return 0
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
            semantic_model=args.semantic_model,
            semantic_dimensions=args.semantic_dimensions,
            semantic_profile=args.semantic_profile,
            semantic_template_version=args.semantic_template_version,
            semantic_api_key_env=args.semantic_api_key_env,
            semantic_base_url=args.semantic_base_url,
            semantic_weight=args.semantic_weight,
            semantic_candidates=args.semantic_candidates,
            answer_provider=args.answer_provider,
            answer_model=args.answer_model,
            answer_api_key_env=args.answer_api_key_env,
            answer_base_url=args.answer_base_url,
            answer_timeout_seconds=args.answer_timeout_seconds,
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
    if args.memory_command == "question-types":
        from research_x.memory.question_types import format_question_types, question_types_json

        print(question_types_json() if args.json else format_question_types())
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
