from __future__ import annotations

import html
import os
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
from research_x.playwright_auth import capture_storage_state_auto


@dataclass
class AppJob:
    job_id: str
    account_id: str
    out_dir: Path
    db_path: Path
    status: str = "queued"
    started_at: float = field(default_factory=time.time)
    finished_at: float | None = None
    logs: list[str] = field(default_factory=list)
    error: str | None = None


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
        )
        with self.lock:
            self.jobs[job.job_id] = job
        thread = threading.Thread(target=self._run_job, args=(job, form), daemon=True)
        thread.start()
        return job

    def get_job(self, job_id: str) -> AppJob | None:
        with self.lock:
            return self.jobs.get(job_id)

    def _run_job(self, job: AppJob, form: dict[str, str]) -> None:
        try:
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
            if password:
                self._set_status(job, "auth", "自動ログインを実行しています")
                app_env = {
                    "RESEARCH_X_APP_USERNAME": screen_name,
                    "RESEARCH_X_APP_PASSWORD": password,
                    "RESEARCH_X_APP_EMAIL_OR_PHONE": form.get("email_or_phone", "").strip(),
                }
                with self.auth_lock, _temporary_env(app_env):
                    ok = capture_storage_state_auto(
                        storage_state=paths.storage_state,
                        user_data_dir=paths.user_data_dir,
                        username_env="RESEARCH_X_APP_USERNAME",
                        password_env="RESEARCH_X_APP_PASSWORD",
                        email_or_phone_env="RESEARCH_X_APP_EMAIL_OR_PHONE",
                        try_cdp=True,
                        try_system_browser=True,
                        system_browser=form.get("browser", "msedge") or "msedge",
                        system_browser_disable_extensions=True,
                        cdp_timeout_seconds=3,
                        headless=True,
                        timeout_seconds=float(form.get("auth_timeout", "180") or 180),
                    )
                if not ok:
                    raise RuntimeError("automatic auth did not produce X cookies")
            else:
                self._append_log(job, "password未入力のため、既存storage_stateだけを使います")

            self._set_status(job, "bookmarks", "ブックマークを取得しています")
            fetch_all = form.get("fetch_all") == "on"
            limit = 100000 if fetch_all else max(1, int(form.get("limit", "100") or 100))
            result, classification = run_bookmark_job(
                out_dir=job.out_dir,
                account=job.account_id,
                limit=limit,
                headless=True,
                max_scroll_steps=1000 if fetch_all else 20,
                classify=form.get("classify") == "on",
                classifier_provider=form.get("classifier_provider", "gemini") or "gemini",
                model=form.get("model", "gpt-4o-mini") or "gpt-4o-mini",
                api_key_env=form.get("api_key_env", "GEMINI_API_KEY") or "GEMINI_API_KEY",
                categories_path=form.get("categories", "examples/bookmark_categories.toml")
                or None,
                min_successful_providers=1,
                download_media=form.get("download_media") == "on",
                db_path=job.db_path,
                exhaustive=fetch_all,
            )
            providers = ",".join(result.providers_used) or "-"
            self._append_log(
                job,
                (
                    f"取得完了: status={result.status.value} items={len(result.items)} "
                    f"providers={providers} classification={classification.status}"
                ),
            )
            self._set_status(job, "done", "完了")
            job.finished_at = time.time()
        except Exception as exc:  # noqa: BLE001 - app job must report failures in UI.
            job.error = f"{type(exc).__name__}: {exc}"
            self._append_log(job, traceback.format_exc())
            self._set_status(job, "failed", job.error)
            job.finished_at = time.time()

    def _set_status(self, job: AppJob, status: str, message: str) -> None:
        with self.lock:
            job.status = status
            job.logs.append(message)

    def _append_log(self, job: AppJob, message: str) -> None:
        with self.lock:
            job.logs.append(message)


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
                self._html(_home_page())
                return
            if parsed.path == "/status":
                params = parse_qs(parsed.query)
                job = app.get_job(_first(params, "job"))
                self._html(_status_page(job))
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
            if urlparse(self.path).path != "/run":
                self.send_error(404)
                return
            length = int(self.headers.get("content-length", "0") or "0")
            body = self.rfile.read(length).decode("utf-8", errors="replace")
            form = {key: values[-1] for key, values in parse_qs(body).items()}
            job = app.start_job(form)
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

    server = ThreadingHTTPServer((host, port), Handler)
    url = f"http://{host}:{port}"
    print(f"research_x app: {url}")
    if open_browser:
        webbrowser.open(url)
    server.serve_forever()


def _home_page() -> str:
    return _page(
        "X収集アプリ",
        """
        <h1>X収集アプリ</h1>
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
          </section>
          <section>
            <h2>取得</h2>
            <label>Output dir
              <input name="out_dir" placeholder="runs/bookmarks_mcreatefuture_3_full">
            </label>
            <label>DB path <input name="db_path" value="runs/x_data.sqlite3"></label>
            <label>Limit <input name="limit" type="number" value="100"></label>
            <label><input name="fetch_all" type="checkbox" checked> 全件取得モード</label>
            <label><input name="download_media" type="checkbox" checked> 画像も保存</label>
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
            <label>Provider <input name="classifier_provider" value="gemini"></label>
            <label>Model <input name="model" value="gpt-4o-mini"></label>
            <label>API key env <input name="api_key_env" value="GEMINI_API_KEY"></label>
            <label>Categories
              <input name="categories" value="examples/bookmark_categories.toml">
            </label>
          </section>
          <button type="submit">収集開始</button>
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
    refresh = "" if job.status in {"done", "failed"} else "<meta http-equiv='refresh' content='5'>"
    result_params = urlencode(
        {
            "db": str(job.db_path),
            "account": job.account_id,
            "kind": "bookmarks",
            "limit": "100",
        }
    )
    result_link = (
        f"<a href='/results?{result_params}'>本文を見る</a>"
        if job.status == "done"
        else ""
    )
    logs = "\n".join(html.escape(item) for item in job.logs[-80:])
    return _page(
        f"Job {job.job_id}",
        f"""
        {refresh}
        <h1>Job {html.escape(job.job_id)}</h1>
        <p>status: <strong>{html.escape(job.status)}</strong></p>
        <p>account: {html.escape(job.account_id)}</p>
        <p>out: {html.escape(str(job.out_dir))}</p>
        <p>db: {html.escape(str(job.db_path))}</p>
        <p>{result_link} <a href="/">新規実行</a></p>
        <pre>{logs}</pre>
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
    pre {{ white-space: pre-wrap; background: #f6f6f6; padding: 12px; overflow: auto; }}
  </style>
</head>
<body>{body}</body>
</html>"""


def _first(params: dict[str, list[str]], key: str) -> str:
    values = params.get(key) or [""]
    return values[-1]


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
