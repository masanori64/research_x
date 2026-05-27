from __future__ import annotations

import argparse
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
        limit = 100000 if args.all else args.limit
        max_scroll_steps = max(args.max_scroll_steps, 1000) if args.all else args.max_scroll_steps
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


def _configure_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
