from __future__ import annotations

import html
import json
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
from research_x.playwright_auth import capture_storage_state_auto, storage_state_has_x_auth_cookies


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

    def list_jobs(self) -> list[AppJob]:
        with self.lock:
            return sorted(self.jobs.values(), key=lambda job: job.started_at, reverse=True)

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
                self._html(_home_page(app.list_jobs()))
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
    return _page(
        "X収集アプリ",
        f"""
        <h1>X収集アプリ</h1>
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
    progress = _progress_box(job)
    cursor_state = _cursor_state(job.out_dir)
    state_text = _status_label(job.status, cursor_state=cursor_state)
    elapsed = _elapsed_text(job)
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
    completion_sound = _completion_sound_script(job)
    return _page(
        f"Job {job.job_id}",
        f"""
        {refresh}
        {completion_sound}
        <h1>Job {html.escape(job.job_id)}</h1>
        <p>status: <strong>{html.escape(job.status)}</strong> - {state_text}</p>
        <p>elapsed: {html.escape(elapsed)}</p>
        <p>account: {html.escape(job.account_id)}</p>
        <p>out: {html.escape(str(job.out_dir))}</p>
        <p>db: {html.escape(str(job.db_path))}</p>
        {progress}
        <p>{result_link} <a href="/">新規実行</a></p>
        <p class="note">新規実行はこのジョブを止めません。別の入力画面へ戻るだけです。</p>
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


def _status_label(status: str, *, cursor_state: dict[str, Any] | None = None) -> str:
    if status == "bookmarks" and cursor_state and cursor_state.get("finished"):
        return "<span class='running'>本文取得完了。画像保存またはDB書き込み中</span>"
    labels = {
        "queued": "<span class='running'>待機中</span>",
        "account": "<span class='running'>アカウント情報を保存中</span>",
        "auth": "<span class='running'>自動ログイン中。まだ取得は始まっていません</span>",
        "bookmarks": "<span class='running'>ブックマーク取得中</span>",
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
    out_dir = job.out_dir
    item_count = _jsonl_count(out_dir / "bookmarks_items.jsonl")
    page_count = len(list((out_dir / "bookmark_pages" / "x_web_graphql").glob("*.json")))
    media_count = _media_file_count(out_dir / "media")
    media_progress = _media_progress(out_dir)
    cursor_state = _cursor_state(out_dir)
    existing = out_dir.exists()
    lines = [
        f"output exists: {existing}",
        f"bookmarks_items.jsonl rows: {item_count}",
        f"x_web_graphql saved pages: {page_count}",
        f"downloaded media files: {media_count}",
    ]
    if media_progress:
        total = _safe_int(media_progress.get("total"))
        done = _safe_int(media_progress.get("done"))
        remaining = _safe_int(media_progress.get("remaining"), default=max(0, total - done))
        percent = (done / total * 100) if total else 0.0
        eta = _duration_text(media_progress.get("estimated_remaining_seconds"))
        lines.extend(
            [
                f"media progress: {done}/{total} remaining {remaining} ({percent:.1f}%)",
                f"media ok/error/skipped: {media_progress.get('ok', 0)}/"
                f"{media_progress.get('error', 0)}/{media_progress.get('skipped', 0)}",
                f"estimated media remaining: {eta}",
            ]
        )
    elif (out_dir / "items.jsonl").exists():
        total = _estimate_media_total_from_items(out_dir / "items.jsonl")
        done = min(media_count, total) if total else media_count
        remaining = max(0, total - done)
        percent = (done / total * 100) if total else 0.0
        eta = _duration_text(_estimated_remaining_seconds(job, done=done, remaining=remaining))
        lines.append(
            f"media progress estimate: {done}/{total} remaining {remaining} ({percent:.1f}%)"
        )
        lines.append(f"estimated media remaining: {eta}")
    if cursor_state:
        lines.append(f"cursor item_count: {cursor_state.get('item_count')}")
        lines.append(f"cursor finished: {cursor_state.get('finished')}")
        lines.append(f"rate_limited: {cursor_state.get('rate_limited')}")
    return "<pre>" + html.escape("\n".join(lines)) + "</pre>"


def _jsonl_count(path: Path) -> int:
    if not path.exists():
        return 0
    with path.open("r", encoding="utf-8") as handle:
        return sum(1 for _ in handle)


def _media_file_count(path: Path) -> int:
    if not path.exists():
        return 0
    return sum(1 for candidate in path.glob("*/*") if candidate.is_file())


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


def _estimate_media_total_from_items(path: Path) -> int:
    try:
        from research_x.x_store import _add_media

        media: dict[str, dict[str, Any]] = {}
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                row = json.loads(line)
                if not isinstance(row, dict):
                    continue
                source_id = str(row.get("source_id") or "")
                raw = row.get("raw")
                if source_id and isinstance(raw, dict):
                    _add_media(media, source_id, raw)
        return len(media)
    except Exception:  # noqa: BLE001 - progress fallback should never break status page.
        return 0


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
