from __future__ import annotations

import html
import json
import os
import shutil
import sqlite3
import threading
import time
import traceback
import uuid
import webbrowser
from contextlib import contextmanager
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse

from research_x.accounts import normalize_account_id, resolve_account_paths, write_account_profile
from research_x.bookmarks import run_bookmark_job
from research_x.db_view import format_display_rows, load_display_rows
from research_x.label_existing import LABEL_EXISTING_KINDS, label_existing_items
from research_x.memory.api_budget import (
    BUDGET_EXHAUSTED_STATUS,
    api_budget_context,
    api_budget_status,
    format_api_budget_status,
    set_api_kill_switch,
)
from research_x.playwright_auth import capture_storage_state_auto, storage_state_has_x_auth_cookies
from research_x.progress import ProgressSnapshot, progress_snapshot


@dataclass
class AppJob:
    job_id: str
    account_id: str
    out_dir: Path
    db_path: Path
    result_kind: str = "bookmarks"
    account_filter: str | None = None
    status: str = "queued"
    started_at: float = field(default_factory=time.time)
    finished_at: float | None = None
    logs: list[str] = field(default_factory=list)
    error: str | None = None
    cancel_requested: bool = False
    rollback_requested: bool = False
    rollback_applied: bool = False
    rollback_error: str | None = None
    rollback_in_progress: bool = False
    rollback_watch_started: bool = False
    db_backup_path: Path | None = None
    db_existed_at_start: bool | None = None


class CollectionApp:
    def __init__(self) -> None:
        self.jobs: dict[str, AppJob] = {}
        self.lock = threading.Lock()
        self.auth_lock = threading.Lock()

    def start_job(self, form: dict[str, str]) -> AppJob:
        screen_name = form.get("screen_name", "").strip().lstrip("@")
        account = form.get("account", "").strip() or screen_name
        account_id = normalize_account_id(account)
        out_dir = Path(form.get("out_dir", "").strip() or f"runs/bookmarks_{account_id}_full")
        db_path = Path(form.get("db_path", "").strip() or "runs/x_data.sqlite3")
        job = AppJob(
            job_id=uuid.uuid4().hex[:12],
            account_id=account_id,
            out_dir=out_dir,
            db_path=db_path,
            result_kind="bookmarks",
            account_filter=account_id,
        )
        with self.lock:
            self.jobs[job.job_id] = job
        thread = threading.Thread(target=self._run_job, args=(job, form), daemon=True)
        thread.start()
        return job

    def start_label_job(self, form: dict[str, str]) -> AppJob:
        raw_account = form.get("account", "").strip()
        account_id = normalize_account_id(raw_account) if raw_account else "all_accounts"
        job_id = uuid.uuid4().hex[:12]
        out_dir = Path(form.get("out_dir", "").strip() or f"runs/labels_{account_id}_{job_id}")
        db_path = Path(form.get("db_path", "").strip() or "runs/x_data.sqlite3")
        kind = form.get("kind", "bookmarks") or "bookmarks"
        job = AppJob(
            job_id=job_id,
            account_id=account_id,
            out_dir=out_dir,
            db_path=db_path,
            result_kind=kind,
            account_filter=normalize_account_id(raw_account) if raw_account else None,
        )
        with self.lock:
            self.jobs[job.job_id] = job
        thread = threading.Thread(target=self._run_label_job, args=(job, form), daemon=True)
        thread.start()
        return job

    def get_job(self, job_id: str) -> AppJob | None:
        with self.lock:
            return self.jobs.get(job_id)

    def list_jobs(self) -> list[AppJob]:
        with self.lock:
            return sorted(self.jobs.values(), key=lambda job: job.started_at, reverse=True)

    def _run_job(self, job: AppJob, form: dict[str, str]) -> None:
        try:
            self._prepare_db_backup(job)
            self._raise_if_cancelled(job)
            self._set_status(job, "account", "account profileを保存しています")
            screen_name = form.get("screen_name", "").strip().lstrip("@") or job.account_id
            write_account_profile(
                account=job.account_id,
                screen_name=screen_name,
                user_id=form.get("user_id", "").strip() or None,
                display_name=form.get("display_name", "").strip() or None,
                url=form.get("url", "").strip() or f"https://x.com/{screen_name}",
            )
            paths = resolve_account_paths(job.account_id)

            password = form.get("password", "")
            use_standard_profile = form.get("use_standard_browser_profile") == "on"
            if password or use_standard_profile:
                if storage_state_has_x_auth_cookies(paths.storage_state):
                    self._append_log(
                        job,
                        "既存storage_stateにXログインCookieがあるためログインをスキップします",
                    )
                else:
                    self._set_status(job, "auth", "自動ログインを実行しています")
                    app_env = {
                        "RESEARCH_X_APP_USERNAME": screen_name,
                        "RESEARCH_X_APP_PASSWORD": password,
                        "RESEARCH_X_APP_EMAIL_OR_PHONE": form.get(
                            "email_or_phone", ""
                        ).strip(),
                        "RESEARCH_X_APP_VERIFICATION_CODE": form.get(
                            "verification_code", ""
                        ).strip(),
                        "RESEARCH_X_APP_TOTP_SECRET": form.get("totp_secret", "").strip(),
                    }
                    with self.auth_lock, _temporary_env(app_env):
                        ok = capture_storage_state_auto(
                            storage_state=paths.storage_state,
                            user_data_dir=paths.user_data_dir,
                            username_env="RESEARCH_X_APP_USERNAME",
                            password_env="RESEARCH_X_APP_PASSWORD",
                            email_or_phone_env="RESEARCH_X_APP_EMAIL_OR_PHONE",
                            verification_code_env="RESEARCH_X_APP_VERIFICATION_CODE",
                            totp_secret_env="RESEARCH_X_APP_TOTP_SECRET",
                            try_cdp=True,
                            try_system_browser=True,
                            try_system_browser_profile=use_standard_profile,
                            system_browser=form.get("browser", "msedge") or "msedge",
                            system_browser_disable_extensions=True,
                            system_browser_profile_directory=form.get(
                                "browser_profile_directory", ""
                            ).strip()
                            or None,
                            system_browser_profile_close_existing=(
                                form.get("close_existing_browser") == "on"
                            ),
                            cdp_timeout_seconds=3,
                            headless=True,
                            timeout_seconds=float(form.get("auth_timeout", "180") or 180),
                        )
                    if not ok:
                        raise RuntimeError("automatic auth did not produce X cookies")
            else:
                self._append_log(job, "password未入力のため、既存storage_stateだけを使います")

            self._raise_if_cancelled(job)
            self._set_status(job, "bookmarks", "ブックマークを取得しています")
            fetch_all = form.get("fetch_all") == "on"
            limit = max(1, int(form.get("limit", "100") or 100))
            api_key_env = form.get("api_key_env", "GEMINI_API_KEY") or "GEMINI_API_KEY"
            with _temporary_classifier_env(form, api_key_env), _app_api_budget_context(job, form):
                result, classification = run_bookmark_job(
                    out_dir=job.out_dir,
                    account=job.account_id,
                    limit=limit,
                    headless=True,
                    max_scroll_steps=1000 if fetch_all else 20,
                    classify=form.get("classify") == "on",
                    classifier_provider=form.get("classifier_provider", "gemini") or "gemini",
                    model=form.get("model", "gemini-2.5-flash") or "gemini-2.5-flash",
                    api_key_env=api_key_env,
                    categories_path=form.get("categories", "examples/bookmark_categories.toml")
                    or None,
                    min_successful_providers=1,
                    download_media=form.get("download_media") == "on",
                    db_path=job.db_path,
                    exhaustive=fetch_all,
                    reasoning_effort=form.get("reasoning_effort", "low") or None,
                )
            self._raise_if_cancelled(job)
            providers = ",".join(result.providers_used) or "-"
            self._append_log(
                job,
                (
                    f"取得完了: status={result.status.value} items={len(result.items)} "
                    f"providers={providers} classification={classification.status}"
                ),
            )
            if classification.status == BUDGET_EXHAUSTED_STATUS:
                job.error = (
                    f"{classification.error_type or 'ApiBudgetExceeded'}: "
                    f"{classification.error_message or classification.status}"
                )
                self._set_status(job, BUDGET_EXHAUSTED_STATUS, "API予算上限で終了しました")
            else:
                self._set_status(job, "done", "完了")
            job.finished_at = time.time()
            self._apply_pending_rollback(job)
        except JobCancelled as exc:
            self._append_log(job, str(exc))
            self._set_status(job, "canceled", "停止しました")
            job.finished_at = time.time()
            self._apply_pending_rollback(job)
        except Exception as exc:  # noqa: BLE001 - app job must report failures in UI.
            job.error = f"{type(exc).__name__}: {exc}"
            self._append_log(job, traceback.format_exc())
            self._set_status(job, "failed", job.error)
            job.finished_at = time.time()
            self._apply_pending_rollback(job)

    def _run_label_job(self, job: AppJob, form: dict[str, str]) -> None:
        try:
            self._prepare_db_backup(job)
            self._raise_if_cancelled(job)
            self._set_status(job, "labeling", "既存DBの未分類データをAI分類しています")
            label_all = form.get("all") == "on"
            kind = form.get("kind", "bookmarks") or "bookmarks"
            if kind not in LABEL_EXISTING_KINDS:
                raise ValueError(f"unsupported kind: {kind}")
            api_key_env = form.get("api_key_env", "GEMINI_API_KEY") or "GEMINI_API_KEY"
            with _temporary_classifier_env(form, api_key_env), _app_api_budget_context(job, form):
                report, classification = label_existing_items(
                    db_path=job.db_path,
                    account=job.account_filter,
                    kind=kind,
                    limit=None if label_all else max(1, int(form.get("limit", "100") or 100)),
                    include_labeled=form.get("include_labeled") == "on",
                    out_dir=job.out_dir,
                    classifier_provider=form.get("classifier_provider", "gemini") or "gemini",
                    model=form.get("model", "gemini-2.5-flash") or "gemini-2.5-flash",
                    api_key_env=api_key_env,
                    categories_path=form.get("categories", "examples/bookmark_categories.toml")
                    or None,
                    batch_size=max(1, int(form.get("batch_size", "20") or 20)),
                    retry_attempts=max(0, int(form.get("retry_attempts", "100") or 100)),
                    retry_base_seconds=max(
                        0.0,
                        float(form.get("retry_base_seconds", "10") or 10),
                    ),
                    request_timeout_seconds=max(
                        10.0,
                        float(form.get("request_timeout_seconds", "120") or 120),
                    ),
                    reasoning_effort=form.get("reasoning_effort", "low") or None,
                    cancel_check=lambda: self._is_cancel_requested(job),
                    min_request_interval_seconds=max(
                        0.0,
                        float(form.get("min_request_interval_seconds", "3.2") or 3.2),
                    ),
                    stop_on_rate_limit=form.get("stop_on_rate_limit") == "on",
                )
            self._append_log(
                job,
                (
                    f"分類完了: status={classification.status} "
                    f"selected={report.selected_items} unique={report.unique_tweets} "
                    f"written={report.written_labels} "
                    f"already_labeled={report.already_labeled}/{report.candidate_total} "
                    f"model={report.model}"
                ),
            )
            if classification.error_message and classification.status != "canceled":
                self._append_log(
                    job,
                    f"{classification.error_type}: {classification.error_message}",
                )
            if classification.status == "canceled":
                self._set_status(job, "canceled", "停止しました")
            elif classification.status == "quota_exhausted":
                job.error = (
                    f"{classification.error_type or 'QuotaExhausted'}: "
                    f"{classification.error_message or classification.status}"
                )
                self._set_status(job, "quota_exhausted", "API quota上限で終了しました")
            elif classification.status == BUDGET_EXHAUSTED_STATUS:
                job.error = (
                    f"{classification.error_type or 'ApiBudgetExceeded'}: "
                    f"{classification.error_message or classification.status}"
                )
                self._set_status(job, BUDGET_EXHAUSTED_STATUS, "API予算上限で終了しました")
            elif classification.status in {"ok", "empty"}:
                self._set_status(job, "done", "完了")
            else:
                job.error = (
                    f"{classification.error_type or 'ClassificationError'}: "
                    f"{classification.error_message or classification.status}"
                )
                self._set_status(job, "failed", job.error)
            job.finished_at = time.time()
            self._apply_pending_rollback(job)
        except JobCancelled as exc:
            self._append_log(job, str(exc))
            self._set_status(job, "canceled", "停止しました")
            job.finished_at = time.time()
            self._apply_pending_rollback(job)
        except Exception as exc:  # noqa: BLE001 - app job must report failures in UI.
            job.error = f"{type(exc).__name__}: {exc}"
            self._append_log(job, traceback.format_exc())
            self._set_status(job, "failed", job.error)
            job.finished_at = time.time()
            self._apply_pending_rollback(job)

    def request_cancel(self, job_id: str, *, rollback: bool = False) -> AppJob | None:
        watch_rollback = False
        with self.lock:
            job = self.jobs.get(job_id)
            if job is None:
                return None
            if rollback:
                job.rollback_requested = True
                watch_rollback = True
            if _is_terminal_status(job.status):
                job.logs.append("完了済みのジョブのため停止は不要です")
            else:
                job.cancel_requested = True
                job.status = "canceling"
                if rollback:
                    job.logs.append("停止後に開始前DBへ戻す要求を受け付けました")
                else:
                    job.logs.append("停止要求を受け付けました")
                watch_rollback = rollback
        if _is_terminal_status(job.status) and rollback:
            self.rollback_job(job_id)
        elif watch_rollback:
            self._start_rollback_watch(job)
        return job

    def rollback_job(self, job_id: str) -> AppJob | None:
        watch_rollback = False
        with self.lock:
            job = self.jobs.get(job_id)
            if job is None:
                return None
            if not _is_terminal_status(job.status):
                job.cancel_requested = True
                job.rollback_requested = True
                job.status = "canceling"
                job.logs.append("実行中のため、停止後に開始前DBへ戻します")
                watch_rollback = True
        if watch_rollback:
            self._start_rollback_watch(job)
        else:
            self._restore_db_backup(job)
        return job

    def _set_status(self, job: AppJob, status: str, message: str) -> None:
        with self.lock:
            job.status = status
            job.logs.append(message)

    def _append_log(self, job: AppJob, message: str) -> None:
        with self.lock:
            job.logs.append(message)

    def _prepare_db_backup(self, job: AppJob) -> None:
        job.out_dir.mkdir(parents=True, exist_ok=True)
        backup_dir = job.out_dir / "_rollback"
        backup_dir.mkdir(parents=True, exist_ok=True)
        db_path = job.db_path
        if not db_path.exists():
            with self.lock:
                job.db_existed_at_start = False
                job.db_backup_path = None
                job.logs.append("DBは開始時点で存在しませんでした。復元時はDBを削除します")
            return
        backup_path = backup_dir / f"{job.job_id}_before.sqlite3"
        source = sqlite3.connect(db_path)
        backup = sqlite3.connect(backup_path)
        try:
            source.backup(backup)
        finally:
            backup.close()
            source.close()
        with self.lock:
            job.db_existed_at_start = True
            job.db_backup_path = backup_path
            job.logs.append(f"開始前DBバックアップ: {backup_path}")

    def _restore_db_backup(self, job: AppJob) -> None:
        with self.lock:
            if job.rollback_applied or job.rollback_in_progress:
                return
            job.rollback_in_progress = True
        try:
            if job.db_existed_at_start is None:
                raise RuntimeError("開始前DBバックアップがまだ準備されていません")
            if job.db_existed_at_start:
                if job.db_backup_path is None or not job.db_backup_path.exists():
                    raise RuntimeError("開始前DBバックアップが見つかりません")
                job.db_path.parent.mkdir(parents=True, exist_ok=True)
                _delete_sqlite_sidecars(job.db_path)
                shutil.copy2(job.db_backup_path, job.db_path)
            else:
                _delete_sqlite_files(job.db_path)
            with self.lock:
                job.rollback_applied = True
                job.rollback_error = None
                job.status = "rolled_back"
                job.logs.append("開始前DBへ戻しました")
                job.finished_at = job.finished_at or time.time()
        except Exception as exc:  # noqa: BLE001 - rollback errors must be visible in UI.
            with self.lock:
                job.rollback_error = f"{type(exc).__name__}: {exc}"
                job.logs.append(f"DB復元に失敗しました: {job.rollback_error}")
        finally:
            with self.lock:
                job.rollback_in_progress = False

    def _apply_pending_rollback(self, job: AppJob) -> None:
        with self.lock:
            rollback_requested = job.rollback_requested
        if rollback_requested:
            self._restore_db_backup(job)

    def _start_rollback_watch(self, job: AppJob) -> None:
        with self.lock:
            if job.rollback_watch_started:
                return
            job.rollback_watch_started = True
        thread = threading.Thread(target=self._rollback_when_terminal, args=(job,), daemon=True)
        thread.start()

    def _rollback_when_terminal(self, job: AppJob) -> None:
        while True:
            with self.lock:
                terminal = _is_terminal_status(job.status)
                should_restore = (
                    terminal and job.rollback_requested and not job.rollback_applied
                )
            if should_restore:
                self._restore_db_backup(job)
                return
            if terminal:
                return
            time.sleep(0.25)

    def _is_cancel_requested(self, job: AppJob) -> bool:
        with self.lock:
            return job.cancel_requested

    def _raise_if_cancelled(self, job: AppJob) -> None:
        if self._is_cancel_requested(job):
            raise JobCancelled("停止要求によりジョブを中断しました")


class JobCancelled(Exception):
    pass


def serve_collection_app(
    *,
    host: str = "127.0.0.1",
    port: int = 8765,
    open_browser: bool = True,
) -> None:
    app = CollectionApp()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802 - stdlib handler API.
            parsed = urlparse(self.path)
            if parsed.path == "/":
                self._html(_home_page(app.list_jobs()))
                return
            if parsed.path == "/status":
                params = parse_qs(parsed.query)
                job = app.get_job(_first(params, "job"))
                self._html(_status_page(job))
                return
            if parsed.path == "/api/status":
                params = parse_qs(parsed.query)
                job = app.get_job(_first(params, "job"))
                if job is None:
                    self._json({"error": "job_not_found"}, status=404)
                    return
                self._json(_job_status_payload(job))
                return
            if parsed.path == "/api/budget":
                params = parse_qs(parsed.query)
                db = _first(params, "db") or "runs/x_data.sqlite3"
                self._json(api_budget_status(db))
                return
            if parsed.path == "/results":
                params = parse_qs(parsed.query)
                db = _first(params, "db") or "runs/x_data.sqlite3"
                account = _first(params, "account") or None
                kind = _first(params, "kind") or "bookmarks"
                limit = int(_first(params, "limit") or "50")
                self._html(_results_page(db=db, account=account, kind=kind, limit=limit))
                return
            self.send_error(404)

        def do_POST(self) -> None:  # noqa: N802 - stdlib handler API.
            parsed_path = urlparse(self.path).path
            if parsed_path not in {
                "/run",
                "/label-existing",
                "/job/cancel",
                "/job/cancel-rollback",
                "/job/rollback",
                "/api/budget/stop",
                "/api/budget/resume",
            }:
                self.send_error(404)
                return
            length = int(self.headers.get("content-length", "0") or "0")
            body = self.rfile.read(length).decode("utf-8", errors="replace")
            form = {key: values[-1] for key, values in parse_qs(body).items()}
            if parsed_path in {"/api/budget/stop", "/api/budget/resume"}:
                db = form.get("db", "runs/x_data.sqlite3") or "runs/x_data.sqlite3"
                set_api_kill_switch(db, enabled=parsed_path.endswith("/stop"))
                location = "/"
                job_id = form.get("job", "")
                if job_id:
                    location = "/status?" + urlencode({"job": job_id})
                self.send_response(303)
                self.send_header("Location", location)
                self.end_headers()
                return
            if parsed_path in {"/job/cancel", "/job/cancel-rollback", "/job/rollback"}:
                job_id = form.get("job", "")
                if parsed_path == "/job/cancel":
                    job = app.request_cancel(job_id)
                elif parsed_path == "/job/cancel-rollback":
                    job = app.request_cancel(job_id, rollback=True)
                else:
                    job = app.rollback_job(job_id)
                location = "/status?" + urlencode({"job": job_id})
                if job is None:
                    location = "/"
                self.send_response(303)
                self.send_header("Location", location)
                self.end_headers()
                return
            job = (
                app.start_label_job(form)
                if parsed_path == "/label-existing"
                else app.start_job(form)
            )
            location = "/status?" + urlencode({"job": job.job_id})
            self.send_response(303)
            self.send_header("Location", location)
            self.end_headers()

        def log_message(self, format: str, *args: Any) -> None:
            return

        def _html(self, body: str) -> None:
            payload = body.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def _json(self, value: dict[str, Any], *, status: int = 200) -> None:
            payload = json.dumps(value, ensure_ascii=False, sort_keys=True).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

    server = ThreadingHTTPServer((host, port), Handler)
    url = f"http://{host}:{port}"
    print(f"research_x app: {url}")
    try:
        if open_browser:
            webbrowser.open(url)
        server.serve_forever()
    except KeyboardInterrupt:
        print("research_x app: shutting down")
    finally:
        server.server_close()


def _home_page(jobs: list[AppJob] | None = None) -> str:
    job_links = _job_links(jobs or [])
    provider_options = _provider_options("gemini")
    model_options = _model_options("gemini-2.5-flash")
    reasoning_options = _reasoning_options("low")
    budget_panel = _api_budget_panel("runs/x_data.sqlite3")
    return _page(
        "X収集アプリ",
        f"""
        <h1>X収集アプリ</h1>
        {budget_panel}
        {job_links}
        <form method="post" action="/run">
          <section>
            <h2>アカウント</h2>
            <label>Account ID <input name="account" placeholder="my_account"></label>
            <label>Screen name
              <input name="screen_name" placeholder="my_screen_name" required>
            </label>
            <label>User ID <input name="user_id" placeholder="1234567890"></label>
            <label>Display name <input name="display_name" placeholder="My Account"></label>
            <label>URL <input name="url" placeholder="https://x.com/my_screen_name"></label>
            <label>Password
              <input name="password" type="password" autocomplete="current-password">
            </label>
            <label>Email/phone challenge
              <input name="email_or_phone" placeholder="必要な場合だけ">
            </label>
            <label>Security code
              <input name="verification_code" placeholder="8桁コードが送られた場合だけ">
            </label>
            <label>TOTP secret
              <input name="totp_secret" type="password" autocomplete="off">
            </label>
            <label>
              <input name="use_standard_browser_profile" type="checkbox" checked>
              PC標準Edge/Chromeのログイン済みプロファイルを優先
            </label>
            <label>Browser profile directory
              <input name="browser_profile_directory" placeholder="Default / Profile 1">
            </label>
            <label>
              <input name="close_existing_browser" type="checkbox">
              既存Edge/Chromeを一度閉じて標準プロファイルをCDP付きで再起動
            </label>
          </section>
          <section>
            <h2>取得</h2>
            <label>Output dir
              <input name="out_dir" placeholder="runs/bookmarks_my_account_full">
            </label>
            <label>DB path <input name="db_path" value="runs/x_data.sqlite3"></label>
            <label>Limit <input name="limit" type="number" value="100"></label>
            <label><input name="fetch_all" type="checkbox" checked> 全件取得モード</label>
            <label>
              <input name="download_media" type="checkbox" checked>
              画像も保存（大量件数では時間がかかります）
            </label>
            <label>Browser
              <select name="browser">
                <option value="msedge">Edge</option>
                <option value="chrome">Chrome</option>
              </select>
            </label>
            <label>Auth timeout seconds
              <input name="auth_timeout" type="number" value="180">
            </label>
          </section>
          <section>
            <h2>AI分類</h2>
            <label><input name="classify" type="checkbox"> AI分類する</label>
            <label>Provider
              <select name="classifier_provider">{provider_options}</select>
            </label>
            <label>Model
              <select name="model">{model_options}</select>
            </label>
            <label>Reasoning effort
              <select name="reasoning_effort">{reasoning_options}</select>
            </label>
            <label>API key env <input name="api_key_env" value="GEMINI_API_KEY"></label>
            <label>API key
              <input name="api_key_value" type="password" autocomplete="off">
            </label>
            {_api_budget_form_fields()}
            <label>Categories
              <input name="categories" value="examples/bookmark_categories.toml">
            </label>
          </section>
          <button type="submit">収集開始</button>
        </form>
        <form method="post" action="/label-existing">
          <h2>既存DBをAI分類</h2>
          <label>DB path <input name="db_path" value="runs/x_data.sqlite3"></label>
          <label>Account
            <input name="account" placeholder="空なら全アカウント">
          </label>
          <label>Kind
            <select name="kind">
              <option value="bookmarks">bookmarks</option>
              <option value="tweets">tweets</option>
              <option value="all">all</option>
            </select>
          </label>
          <label>Output dir
            <input name="out_dir" placeholder="runs/labels_my_account">
          </label>
          <label>Limit <input name="limit" type="number" value="100"></label>
          <label><input name="all" type="checkbox"> 未分類を全部処理</label>
          <label><input name="include_labeled" type="checkbox"> ラベル済みも再分類</label>
          <label>Provider
            <select name="classifier_provider">{provider_options}</select>
          </label>
          <label>Model
            <select name="model">{model_options}</select>
          </label>
          <label>Reasoning effort
            <select name="reasoning_effort">{reasoning_options}</select>
          </label>
          <label>API key env <input name="api_key_env" value="GEMINI_API_KEY"></label>
          <label>API key
            <input name="api_key_value" type="password" autocomplete="off">
          </label>
          {_api_budget_form_fields()}
          <label>Categories
            <input name="categories" value="examples/bookmark_categories.toml">
          </label>
          <label>Batch size <input name="batch_size" type="number" value="20"></label>
          <label>Retry attempts <input name="retry_attempts" type="number" value="100"></label>
          <label>Retry base seconds
            <input name="retry_base_seconds" type="number" value="10">
          </label>
          <label>Request timeout seconds
            <input name="request_timeout_seconds" type="number" value="120">
          </label>
          <label>Min request interval seconds
            <input name="min_request_interval_seconds" type="number" step="0.1" value="3.2">
          </label>
          <label>
            <input name="stop_on_rate_limit" type="checkbox" checked>
            quota上限が来たら待たずに終了
          </label>
          <button type="submit">分類開始</button>
        </form>
        <form method="get" action="/results" class="inline">
          <h2>既存DBを見る</h2>
          <label>DB <input name="db" value="runs/x_data.sqlite3"></label>
          <label>Account <input name="account" placeholder="mcreatefuture_3"></label>
          <label>Kind
            <select name="kind">
              <option value="bookmarks">bookmarks</option>
              <option value="tweets">tweets</option>
              <option value="all">all</option>
            </select>
          </label>
          <label>Limit <input name="limit" type="number" value="50"></label>
          <button type="submit">表示</button>
        </form>
        """,
    )


def _status_page(job: AppJob | None) -> str:
    if job is None:
        return _page("Job not found", "<h1>Job not found</h1><a href='/'>戻る</a>")
    snapshot = progress_snapshot(
        job.out_dir,
        started_at=job.started_at,
        finished_at=job.finished_at,
    )
    progress = _progress_box(job)
    budget_panel = _api_budget_panel(str(job.db_path), job=job)
    cursor_state = _cursor_state(job.out_dir)
    state_text = _status_label(job.status, cursor_state=cursor_state)
    elapsed = _elapsed_text(job)
    result_query = {
        "db": str(job.db_path),
        "kind": (
            job.result_kind
            if job.result_kind in {"bookmarks", "tweets", "all"}
            else "bookmarks"
        ),
        "limit": "100",
    }
    if job.account_filter:
        result_query["account"] = job.account_filter
    result_params = urlencode(result_query)
    result_link = (
        f"<a href='/results?{result_params}'>本文を見る</a>"
        if job.status == "done"
        else ""
    )
    logs = "\n".join(html.escape(item) for item in job.logs[-80:])
    completion_sound = _completion_sound_script(job)
    live_script = _live_status_script(job)
    controls = _job_controls(job)
    return _page(
        f"Job {job.job_id}",
        f"""
        {completion_sound}
        {live_script}
        <h1>Job {html.escape(job.job_id)}</h1>
        <p>status: <strong id="job-status">{html.escape(job.status)}</strong> -
          <span id="job-status-label">{state_text}</span>
        </p>
        <p>elapsed: <span id="job-elapsed">{html.escape(elapsed)}</span></p>
        <p>account: {html.escape(job.account_id)}</p>
        <p>out: {html.escape(str(job.out_dir))}</p>
        <p>db: {html.escape(str(job.db_path))}</p>
        {controls}
        {budget_panel}
        {_progress_bars(snapshot)}
        {progress}
        <p>{result_link} <a href="/">新規実行</a></p>
        <p class="note">新規実行はこのジョブを止めません。別の入力画面へ戻るだけです。</p>
        <pre id="job-logs">{logs}</pre>
        """,
    )


def _results_page(*, db: str, account: str | None, kind: str, limit: int) -> str:
    try:
        rows = load_display_rows(db, account=account, kind=kind, limit=limit)
        text = format_display_rows(rows)
    except Exception as exc:  # noqa: BLE001 - render errors in app.
        text = f"{type(exc).__name__}: {exc}"
    return _page(
        "Results",
        f"""
        <h1>本文表示</h1>
        <p><a href="/">戻る</a></p>
        <pre>{html.escape(text)}</pre>
        """,
    )


def _api_budget_form_fields() -> str:
    return """
            <label>API budget policy
              <input name="api_budget_policy" value="default">
            </label>
            <label>Max run USD override
              <input name="max_run_usd" type="number" step="0.01" placeholder="例: 1.00">
            </label>
            <label>
              <input name="allow_unpriced_api" type="checkbox">
              価格未登録APIも許可する（危険。台帳にはunpriced_overrideを残します）
            </label>
    """


def _api_budget_panel(db_path: str, *, job: AppJob | None = None) -> str:
    try:
        status = api_budget_status(db_path, run_id=job.job_id if job else None)
        summary = format_api_budget_status(status)
    except Exception as exc:  # noqa: BLE001 - budget panel must not break app rendering.
        summary = f"{type(exc).__name__}: {exc}"
    escaped_db = html.escape(db_path, quote=True)
    job_input = ""
    if job is not None:
        escaped_job = html.escape(job.job_id, quote=True)
        job_input = f'<input type="hidden" name="job" value="{escaped_job}">'
    return f"""
        <section>
          <h2>API予算</h2>
          <pre id="api-budget-panel">{html.escape(summary)}</pre>
          <div class="actions">
            <form method="post" action="/api/budget/stop">
              <input type="hidden" name="db" value="{escaped_db}">
              {job_input}
              <button class="danger" type="submit">API kill switch ON</button>
            </form>
            <form method="post" action="/api/budget/resume">
              <input type="hidden" name="db" value="{escaped_db}">
              {job_input}
              <button type="submit">API kill switch OFF</button>
            </form>
          </div>
          <script>
          (() => {{
            const db = {json.dumps(db_path)};
            async function pollBudget() {{
              try {{
                const res = await fetch(`/api/budget?db=${{encodeURIComponent(db)}}`, {{
                  cache: "no-store"
                }});
                const payload = await res.json();
                const policy = payload.policy || {{}};
                const usage = payload.usage || {{}};
                const lines = [
                  `policy: ${{policy.policy_id}} enabled=${{Boolean(policy.enabled)}} ` +
                    `kill_switch=${{Boolean(policy.kill_switch_enabled)}} ` +
                    `unknown_price=${{policy.unknown_price_action}}`,
                  `run: $${{Number((usage.run || {{}}).estimated_cost_usd || 0).toFixed(6)}}` +
                    ` calls=${{(usage.run || {{}}).calls || 0}}`,
                  `day: $${{Number((usage.day || {{}}).estimated_cost_usd || 0).toFixed(6)}}` +
                    ` calls=${{(usage.day || {{}}).calls || 0}}`,
                  `month: $${{Number((usage.month || {{}}).estimated_cost_usd || 0).toFixed(6)}}` +
                    ` calls=${{(usage.month || {{}}).calls || 0}}`,
                  `warnings: ${{(payload.warnings || []).join("; ")}}`,
                  "",
                  "recent events:",
                  ...((payload.recent_events || []).slice(0, 8).map((event) =>
                    `${{event.status}} ${{event.provider}}/${{event.model}} ` +
                    `${{event.operation}} ` +
                    `cost=$${{Number(event.estimated_cost_usd || 0).toFixed(6)}} ` +
                    `${{event.error || ""}}`
                  ))
                ];
                const panel = document.getElementById("api-budget-panel");
                if (panel) panel.textContent = lines.join("\\n");
              }} catch (error) {{
                const panel = document.getElementById("api-budget-panel");
                if (panel) panel.textContent = `API budget monitor failed: ${{error}}`;
              }}
            }}
            setInterval(pollBudget, 1000);
            pollBudget();
          }})();
          </script>
        </section>
    """


def _page(title: str, body: str) -> str:
    return f"""<!doctype html>
<html lang="ja">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(title)}</title>
  <style>
    body {{ font-family: system-ui, sans-serif; margin: 24px; max-width: 960px; }}
    h1 {{ font-size: 24px; }}
    h2 {{ font-size: 16px; margin-top: 20px; }}
    form, section {{ display: grid; gap: 10px; }}
    label {{ display: grid; gap: 4px; }}
    input, select, button {{ font: inherit; padding: 8px; }}
    button {{ width: fit-content; }}
    .actions {{ display: flex; gap: 8px; flex-wrap: wrap; margin: 12px 0; }}
    .actions form {{ display: inline; }}
    .danger {{ background: #991b1b; color: white; border: 1px solid #991b1b; }}
    pre {{ white-space: pre-wrap; background: #f6f6f6; padding: 12px; overflow: auto; }}
    .progress-grid {{ display: grid; gap: 12px; margin: 14px 0; }}
    .progress-row {{ display: flex; justify-content: space-between; gap: 12px; }}
    .progress-bar {{ height: 18px; background: #e5e7eb; border-radius: 4px; overflow: hidden; }}
    .progress-fill {{
      height: 100%; width: 0%; background: #2563eb; transition: width .25s linear;
    }}
    .progress-fill.done {{ background: #16a34a; }}
    .progress-fill.waiting {{ background: #d97706; }}
    .note {{ color: #555; }}
    .ok {{ color: #126b28; }}
    .bad {{ color: #9f1239; }}
    .running {{ color: #92400e; }}
    table {{ border-collapse: collapse; }}
    th, td {{ border-bottom: 1px solid #ddd; padding: 6px 10px; text-align: left; }}
  </style>
</head>
<body>{body}</body>
</html>"""


def _job_status_payload(job: AppJob) -> dict[str, Any]:
    snapshot = progress_snapshot(
        job.out_dir,
        started_at=job.started_at,
        finished_at=job.finished_at,
    )
    cursor_state = _cursor_state(job.out_dir)
    logs = list(job.logs[-80:])
    status = job.status
    error = job.error
    finished_at = job.finished_at
    try:
        budget = api_budget_status(job.db_path, run_id=job.job_id, recent_limit=10)
    except Exception as exc:  # noqa: BLE001 - job status must remain available.
        budget = {"error": f"{type(exc).__name__}: {exc}"}
    return {
        "job_id": job.job_id,
        "account_id": job.account_id,
        "status": status,
        "status_label": _status_label(status, cursor_state=cursor_state),
        "error": error,
        "started_at": job.started_at,
        "finished_at": finished_at,
        "server_time": time.time(),
        "logs": logs,
        "cancel_requested": job.cancel_requested,
        "rollback_requested": job.rollback_requested,
        "rollback_applied": job.rollback_applied,
        "rollback_error": job.rollback_error,
        "rollback_in_progress": job.rollback_in_progress,
        "db_backup_path": str(job.db_backup_path) if job.db_backup_path else None,
        "db_existed_at_start": job.db_existed_at_start,
        "progress": snapshot.as_dict(),
        "api_budget": budget,
    }


def _job_controls(job: AppJob) -> str:
    escaped_job = html.escape(job.job_id, quote=True)
    active = not _is_terminal_status(job.status)
    rollback_available = _rollback_available(job)
    backup_text = "なし"
    if job.db_existed_at_start is False:
        backup_text = "開始時DBなし"
    elif job.db_backup_path:
        backup_text = str(job.db_backup_path)
    rollback_state = ""
    if job.rollback_applied:
        rollback_state = "<p class='note'>開始前DBへ復元済みです。</p>"
    elif job.rollback_error:
        rollback_state = f"<p class='bad'>DB復元失敗: {html.escape(job.rollback_error)}</p>"
    forms: list[str] = []
    if active:
        forms.append(
            f"""
            <form method="post" action="/job/cancel">
              <input type="hidden" name="job" value="{escaped_job}">
              <button type="submit">停止</button>
            </form>
            """
        )
        forms.append(
            f"""
            <form method="post" action="/job/cancel-rollback">
              <input type="hidden" name="job" value="{escaped_job}">
              <button class="danger" type="submit">停止して開始前DBへ戻す</button>
            </form>
            """
        )
    elif rollback_available and not job.rollback_applied:
        forms.append(
            f"""
            <form method="post" action="/job/rollback">
              <input type="hidden" name="job" value="{escaped_job}">
              <button class="danger" type="submit">開始前DBへ戻す</button>
            </form>
            """
        )
    return f"""
        <section>
          <h2>ジョブ操作</h2>
          <p class="note">開始前DBバックアップ: {html.escape(backup_text)}</p>
          <div class="actions">{''.join(forms)}</div>
          {rollback_state}
        </section>
    """


def _completion_sound_script(job: AppJob) -> str:
    if job.status not in {"done", "failed"}:
        return ""
    message = "作業が終了しました" if job.status == "done" else "作業が失敗しました"
    key = f"research_x_notified_{job.job_id}"
    return f"""
        <script>
        (() => {{
          const key = {json.dumps(key)};
          if (sessionStorage.getItem(key)) return;
          sessionStorage.setItem(key, "1");
          const message = {json.dumps(message, ensure_ascii=False)};
          try {{
            const AudioContext = window.AudioContext || window.webkitAudioContext;
            if (AudioContext) {{
              const context = new AudioContext();
              const oscillator = context.createOscillator();
              const gain = context.createGain();
              oscillator.type = "sine";
              oscillator.frequency.setValueAtTime(880, context.currentTime);
              oscillator.frequency.setValueAtTime(1174, context.currentTime + 0.12);
              gain.gain.setValueAtTime(0.001, context.currentTime);
              gain.gain.exponentialRampToValueAtTime(0.18, context.currentTime + 0.03);
              gain.gain.exponentialRampToValueAtTime(0.001, context.currentTime + 0.45);
              oscillator.connect(gain);
              gain.connect(context.destination);
              oscillator.start();
              oscillator.stop(context.currentTime + 0.5);
            }}
          }} catch (error) {{}}
          try {{
            if ("speechSynthesis" in window) {{
              const utterance = new SpeechSynthesisUtterance(message);
              utterance.lang = "ja-JP";
              window.speechSynthesis.speak(utterance);
            }}
          }} catch (error) {{}}
        }})();
        </script>
    """


def _progress_bars(snapshot: ProgressSnapshot) -> str:
    text_percent = 100.0 if snapshot.cursor_finished else 0.0
    media_percent = _percent(snapshot.media_done, snapshot.media_total)
    label_percent = _percent(snapshot.label_done, snapshot.label_total)
    text_label = (
        f"完了 {snapshot.cursor_item_count or 0}件 / {snapshot.page_count} pages"
        if snapshot.cursor_finished
        else f"取得中 {snapshot.cursor_item_count or 0}件 / {snapshot.page_count} pages"
    )
    media_label = (
        f"{snapshot.media_done or 0}/{snapshot.media_total or 0} ({media_percent:.1f}%)"
        if snapshot.media_total
        else "待機中"
    )
    label_label = (
        f"{snapshot.label_done or 0}/{snapshot.label_total or 0} ({label_percent:.1f}%)"
        if snapshot.label_total
        else "待機中"
    )
    escaped_text_label = html.escape(text_label)
    escaped_media_label = html.escape(media_label)
    escaped_label_label = html.escape(label_label)
    label_style = "" if snapshot.label_total else "display:none"
    return f"""
        <section class="progress-grid">
          <div>
            <div class="progress-row">
              <strong>本文取得</strong>
              <span id="text-progress-label">{escaped_text_label}</span>
            </div>
            <div class="progress-bar">
              <div id="text-progress-fill"
                class="progress-fill waiting"
                style="width: {text_percent:.1f}%"></div>
            </div>
          </div>
          <div>
            <div class="progress-row">
              <strong>画像保存</strong>
              <span id="media-progress-label">{escaped_media_label}</span>
            </div>
            <div class="progress-bar">
              <div id="media-progress-fill"
                class="progress-fill"
                style="width: {media_percent:.1f}%"></div>
            </div>
          </div>
          <div id="label-progress-section" style="{label_style}">
            <div class="progress-row">
              <strong>AI分類</strong>
              <span id="label-progress-label">{escaped_label_label}</span>
            </div>
            <div class="progress-bar">
              <div id="label-progress-fill"
                class="progress-fill"
                style="width: {label_percent:.1f}%"></div>
            </div>
          </div>
        </section>
    """


def _live_status_script(job: AppJob) -> str:
    job_id = json.dumps(job.job_id)
    return f"""
        <script>
        (() => {{
          const jobId = {job_id};
          let payload = null;
          let receivedAt = Date.now();
          let statusMessage = "";

          function durationText(value) {{
            if (value === null || value === undefined || !Number.isFinite(value)) {{
              return "unknown";
            }}
            const seconds = Math.max(0, Math.floor(value));
            const minutes = Math.floor(seconds / 60);
            const rest = seconds % 60;
            const hours = Math.floor(minutes / 60);
            const mins = minutes % 60;
            return hours ? `${{hours}}h ${{mins}}m ${{rest}}s` : `${{mins}}m ${{rest}}s`;
          }}

          function percent(done, total) {{
            if (!total || total <= 0 || done === null || done === undefined) return 0;
            return Math.max(0, Math.min(100, done / total * 100));
          }}

          function setFill(id, value, finished) {{
            const fill = document.getElementById(id);
            if (!fill) return;
            fill.style.width = `${{value.toFixed(1)}}%`;
            fill.classList.toggle("done", Boolean(finished));
            fill.classList.toggle("waiting", !finished && value <= 0);
          }}

          function render() {{
            if (!payload) return;
            const progress = payload.progress || {{}};
            const now = Date.now();
            const drift = (now - receivedAt) / 1000;
            const end = payload.finished_at || (Date.now() / 1000);
            document.getElementById("job-status").textContent = payload.status || "";
            document.getElementById("job-status-label").innerHTML = payload.status_label || "";
            document.getElementById("job-elapsed").textContent =
              durationText(end - payload.started_at);

            const textFinished = progress.cursor_finished === true;
            const textCount = progress.cursor_item_count || 0;
            const textPercent = textFinished ? 100 : 0;
            document.getElementById("text-progress-label").textContent = textFinished
              ? `完了 ${{textCount}}件 / ${{progress.page_count || 0}} pages`
              : `取得中 ${{textCount}}件 / ${{progress.page_count || 0}} pages`;
            setFill("text-progress-fill", textPercent, textFinished);

            const mediaDone = progress.media_done || 0;
            const mediaTotal = progress.media_total || 0;
            const mediaPercent = percent(mediaDone, mediaTotal);
            const eta = progress.media_estimated_remaining_seconds == null
              ? null
              : Math.max(0, progress.media_estimated_remaining_seconds - drift);
            document.getElementById("media-progress-label").textContent = mediaTotal
              ? (
                `${{mediaDone}}/${{mediaTotal}} ` +
                `(${{mediaPercent.toFixed(1)}}%) 残り ${{durationText(eta)}}`
              )
              : "待機中";
            setFill("media-progress-fill", mediaPercent, progress.media_finished === true);

            const mediaElapsed = progress.media_elapsed_seconds == null
              ? null
              : progress.media_elapsed_seconds + drift;
            const labelDone = progress.label_done || 0;
            const labelTotal = progress.label_total || 0;
            const labelPercent = percent(labelDone, labelTotal);
            const labelEta = progress.label_estimated_remaining_seconds == null
              ? null
              : Math.max(0, progress.label_estimated_remaining_seconds - drift);
            const labelSection = document.getElementById("label-progress-section");
            if (labelSection) labelSection.style.display = labelTotal ? "" : "none";
            if (labelTotal) {{
              document.getElementById("label-progress-label").textContent =
                `${{labelDone}}/${{labelTotal}} ` +
                `(${{labelPercent.toFixed(1)}}%) 残り ${{durationText(labelEta)}}`;
              setFill(
                "label-progress-fill",
                labelPercent,
                progress.label_finished === true
              );
            }}
            const labelElapsed = progress.label_elapsed_seconds == null
              ? null
              : progress.label_elapsed_seconds + drift;
            document.getElementById("progress-details").textContent = [
              statusMessage,
              `output exists: ${{progress.output_exists}}`,
              `bookmarks_items.jsonl rows: ${{progress.bookmarks_rows || 0}}`,
              `x_web_graphql saved pages: ${{progress.page_count || 0}}`,
              (
                `media progress: ${{mediaDone}}/${{mediaTotal}} ` +
                `remaining ${{progress.media_remaining || 0}} ` +
                `(${{mediaPercent.toFixed(1)}}%)`
              ),
              `media elapsed: ${{durationText(mediaElapsed)}}`,
              (
                `media ok/error/skipped: ${{progress.media_ok || 0}}/` +
                `${{progress.media_error || 0}}/${{progress.media_skipped || 0}}`
              ),
              `estimated media remaining: ${{durationText(eta)}}`,
              (
                `label progress: ${{labelDone}}/${{labelTotal}} ` +
                `remaining ${{progress.label_remaining || 0}} ` +
                `(${{labelPercent.toFixed(1)}}%)`
              ),
              `label written: ${{progress.label_written || 0}}`,
              `label elapsed: ${{durationText(labelElapsed)}}`,
              `estimated label remaining: ${{durationText(labelEta)}}`,
              `label status: ${{progress.label_status || "unknown"}}`,
              `label error: ${{progress.label_error_message || ""}}`,
              (
                `label retry: ${{progress.label_retry_attempt || ""}}/` +
                `${{progress.label_retry_attempts || ""}} ` +
                `after ${{durationText(progress.label_retry_after_seconds)}}`
              ),
              `cursor item_count: ${{progress.cursor_item_count || 0}}`,
              `cursor finished: ${{progress.cursor_finished}}`,
              `rate_limited: ${{progress.rate_limited}}`
            ].join("\\n");
            const logs = document.getElementById("job-logs");
            if (logs) logs.textContent = (payload.logs || []).join("\\n");
          }}

          function hasUsefulProgress(progress) {{
            return (
              (progress.cursor_item_count && progress.cursor_item_count > 0) ||
              (progress.page_count && progress.page_count > 0) ||
              progress.cursor_finished === true ||
              progress.rate_limited === true ||
              (progress.media_total && progress.media_total > 0) ||
              (progress.label_total !== null && progress.label_total !== undefined)
            );
          }}

          async function poll() {{
            try {{
              const response = await fetch(`/api/status?job=${{encodeURIComponent(jobId)}}`, {{
                cache: "no-store"
              }});
              const next = await response.json();
              const nextProgress = next.progress || {{}};
              if (hasUsefulProgress(nextProgress) || !payload) {{
                payload = next;
                receivedAt = Date.now();
                statusMessage = "";
                render();
              }} else {{
                statusMessage = "progress source returned incomplete data; keeping last value";
                render();
              }}
            }} catch (error) {{
              statusMessage = `progress update failed; keeping last value: ${{error}}`;
              render();
            }}
          }}

          setInterval(render, 1000);
          setInterval(poll, 1000);
          poll();
        }})();
        </script>
    """


def _job_links(jobs: list[AppJob]) -> str:
    if not jobs:
        return ""
    rows = []
    for job in jobs[:10]:
        status_url = "/status?" + urlencode({"job": job.job_id})
        rows.append(
            "<tr>"
            f"<td><a href='{status_url}'>{html.escape(job.job_id)}</a></td>"
            f"<td>{html.escape(job.account_id)}</td>"
            f"<td>{html.escape(job.status)}</td>"
            f"<td>{html.escape(_elapsed_text(job))}</td>"
            "</tr>"
        )
    return (
        "<section><h2>最近のジョブ</h2><table>"
        "<tr><th>Job</th><th>Account</th><th>Status</th><th>Elapsed</th></tr>"
        + "".join(rows)
        + "</table></section>"
    )


def _provider_options(selected: str) -> str:
    providers = (
        ("gemini", "Gemini"),
        ("openai_chat", "OpenAI Chat"),
        ("openai_responses", "OpenAI Responses"),
        ("qwen", "Qwen"),
        ("kimi", "Kimi"),
        ("glm", "GLM"),
        ("openai_compatible", "OpenAI compatible custom"),
    )
    return "".join(
        (
            f"<option value='{html.escape(value)}'"
            f"{' selected' if value == selected else ''}>{html.escape(label)}</option>"
        )
        for value, label in providers
    )


def _model_options(selected: str) -> str:
    models = (
        "gemini-2.5-flash",
        "gemini-2.5-flash-lite",
        "gemini-3.5-flash",
        "gemini-3.1-flash-lite",
        "gpt-4o-mini",
        "qwen-turbo-latest",
        "kimi-latest",
        "glm-4-flash",
    )
    return "".join(
        (
            f"<option value='{html.escape(model)}'"
            f"{' selected' if model == selected else ''}>{html.escape(model)}</option>"
        )
        for model in models
    )


def _reasoning_options(selected: str) -> str:
    options = (
        ("low", "low"),
        ("default", "default"),
        ("minimal", "minimal"),
        ("medium", "medium"),
        ("high", "high"),
    )
    return "".join(
        (
            f"<option value='{html.escape(value)}'"
            f"{' selected' if value == selected else ''}>{html.escape(label)}</option>"
        )
        for value, label in options
    )


def _status_label(status: str, *, cursor_state: dict[str, Any] | None = None) -> str:
    if status == "bookmarks" and cursor_state and cursor_state.get("finished"):
        return "<span class='running'>本文取得完了。画像保存またはDB書き込み中</span>"
    labels = {
        "queued": "<span class='running'>待機中</span>",
        "account": "<span class='running'>アカウント情報を保存中</span>",
        "auth": "<span class='running'>自動ログイン中。まだ取得は始まっていません</span>",
        "bookmarks": "<span class='running'>ブックマーク取得中</span>",
        "labeling": "<span class='running'>既存DBをAI分類中</span>",
        "canceling": "<span class='running'>停止要求中。現在の処理が区切れるまで待機中</span>",
        "canceled": "<span class='bad'>停止済み</span>",
        "quota_exhausted": "<span class='bad'>API quota上限で終了</span>",
        BUDGET_EXHAUSTED_STATUS: "<span class='bad'>API予算上限で終了</span>",
        "rolled_back": "<span class='ok'>開始前DBへ復元済み</span>",
        "done": "<span class='ok'>完了</span>",
        "failed": "<span class='bad'>失敗。ログ末尾に原因があります</span>",
    }
    return labels.get(status, html.escape(status))


def _elapsed_text(job: AppJob) -> str:
    end = job.finished_at or time.time()
    seconds = max(0, int(end - job.started_at))
    minutes, rest = divmod(seconds, 60)
    return f"{minutes}m {rest}s"


def _progress_box(job: AppJob) -> str:
    snapshot = progress_snapshot(
        job.out_dir,
        started_at=job.started_at,
        finished_at=job.finished_at,
    )
    media_percent = _percent(snapshot.media_done, snapshot.media_total)
    lines = [
        f"output exists: {snapshot.output_exists}",
        f"bookmarks_items.jsonl rows: {snapshot.bookmarks_rows}",
        f"x_web_graphql saved pages: {snapshot.page_count}",
    ]
    if snapshot.media_total is not None:
        lines.extend(
            [
                (
                    f"media progress: {snapshot.media_done or 0}/{snapshot.media_total or 0} "
                    f"remaining {snapshot.media_remaining or 0} ({media_percent:.1f}%)"
                ),
                (
                    f"media ok/error/skipped: {snapshot.media_ok or 0}/"
                    f"{snapshot.media_error or 0}/{snapshot.media_skipped or 0}"
                ),
                (
                    "estimated media remaining: "
                    f"{_duration_text(snapshot.media_estimated_remaining_seconds)}"
                ),
            ]
        )
    if snapshot.label_total is not None:
        label_percent = _percent(snapshot.label_done, snapshot.label_total)
        lines.extend(
            [
                (
                    f"label progress: {snapshot.label_done or 0}/{snapshot.label_total or 0} "
                    f"remaining {snapshot.label_remaining or 0} ({label_percent:.1f}%)"
                ),
                f"label written: {snapshot.label_written or 0}",
                f"label status: {snapshot.label_status or 'unknown'}",
                f"label error: {snapshot.label_error_message or ''}",
                (
                    f"label retry: {snapshot.label_retry_attempt or ''}/"
                    f"{snapshot.label_retry_attempts or ''} "
                    f"after {_duration_text(snapshot.label_retry_after_seconds)}"
                ),
                (
                    "estimated label remaining: "
                    f"{_duration_text(snapshot.label_estimated_remaining_seconds)}"
                ),
            ]
        )
    if snapshot.cursor_item_count is not None:
        lines.append(f"cursor item_count: {snapshot.cursor_item_count}")
        lines.append(f"cursor finished: {snapshot.cursor_finished}")
        lines.append(f"rate_limited: {snapshot.rate_limited}")
    return "<pre id='progress-details'>" + html.escape("\n".join(lines)) + "</pre>"


def _percent(done: int | None, total: int | None) -> float:
    if not total or total <= 0 or done is None:
        return 0.0
    return max(0.0, min(100.0, done / total * 100))


def _jsonl_count(path: Path) -> int:
    if not path.exists():
        return 0
    with path.open("r", encoding="utf-8") as handle:
        return sum(1 for _ in handle)


def _cursor_state(out_dir: Path) -> dict[str, Any]:
    path = out_dir / "bookmark_pages" / "x_web_graphql_cursor_state.json"
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _media_progress(out_dir: Path) -> dict[str, Any]:
    path = out_dir / "media_progress.json"
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _estimated_remaining_seconds(job: AppJob, *, done: int, remaining: int) -> float | None:
    if done <= 0 or remaining <= 0:
        return 0.0 if remaining <= 0 else None
    elapsed = max(0.001, time.time() - job.started_at)
    rate = done / elapsed
    return remaining / rate if rate > 0 else None


def _duration_text(value: Any) -> str:
    if not isinstance(value, int | float):
        return "unknown"
    seconds = max(0, int(value))
    minutes, rest = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}h {minutes}m {rest}s"
    return f"{minutes}m {rest}s"


def _safe_int(value: Any, *, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _first(params: dict[str, list[str]], key: str) -> str:
    values = params.get(key) or [""]
    return values[-1]


def _is_terminal_status(status: str) -> bool:
    return status in {
        "done",
        "failed",
        "canceled",
        "quota_exhausted",
        BUDGET_EXHAUSTED_STATUS,
        "rolled_back",
    }


def _rollback_available(job: AppJob) -> bool:
    return job.db_existed_at_start is False or (
        job.db_backup_path is not None and job.db_backup_path.exists()
    )


def _delete_sqlite_files(path: Path) -> None:
    for candidate in (path, Path(f"{path}-wal"), Path(f"{path}-shm")):
        _unlink_with_retry(candidate)


def _delete_sqlite_sidecars(path: Path) -> None:
    for candidate in (Path(f"{path}-wal"), Path(f"{path}-shm")):
        _unlink_with_retry(candidate)


def _unlink_with_retry(path: Path, *, attempts: int = 10) -> None:
    for attempt in range(attempts):
        if not path.exists():
            return
        try:
            path.unlink()
            return
        except PermissionError:
            if attempt >= attempts - 1:
                raise
            time.sleep(0.2)


def _temporary_classifier_env(form: dict[str, str], api_key_env: str):
    api_key_value = form.get("api_key_value", "").strip()
    return _temporary_env({api_key_env: api_key_value} if api_key_value else {})


def _app_api_budget_context(job: AppJob, form: dict[str, str]):
    max_run_usd_text = form.get("max_run_usd", "").strip()
    max_run_usd = float(max_run_usd_text) if max_run_usd_text else None
    return api_budget_context(
        db_path=job.db_path,
        policy_id=form.get("api_budget_policy", "default") or "default",
        run_id=job.job_id,
        job_id=job.job_id,
        max_run_usd_override=max_run_usd,
        allow_unpriced_api=form.get("allow_unpriced_api") == "on",
        metadata={"app_job": job.job_id, "account_id": job.account_id},
    )


@contextmanager
def _temporary_env(values: dict[str, str]):
    previous = {key: os.environ.get(key) for key in values}
    try:
        for key, value in values.items():
            if value:
                os.environ[key] = value
            else:
                os.environ.pop(key, None)
        yield
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
