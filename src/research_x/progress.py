from __future__ import annotations

import json
import time
import webbrowser
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


@dataclass(frozen=True)
class ProgressSnapshot:
    out_dir: str
    output_exists: bool
    server_time: float
    started_at: float | None
    finished_at: float | None
    bookmarks_rows: int
    page_count: int
    cursor_item_count: int | None
    cursor_finished: bool | None
    rate_limited: bool | None
    media_total: int | None
    media_done: int | None
    media_remaining: int | None
    media_ok: int | None
    media_error: int | None
    media_skipped: int | None
    media_pending: int | None
    media_finished: bool | None
    media_elapsed_seconds: float | None
    media_estimated_remaining_seconds: float | None
    media_items_per_second: float | None
    media_updated_at: str | None
    label_total: int | None
    label_done: int | None
    label_remaining: int | None
    label_written: int | None
    label_finished: bool | None
    label_elapsed_seconds: float | None
    label_estimated_remaining_seconds: float | None
    label_items_per_second: float | None
    label_status: str | None
    label_error_message: str | None
    label_retry_after_seconds: float | None
    label_next_retry_at: float | None
    label_retry_attempt: int | None
    label_retry_attempts: int | None
    label_updated_at: str | None

    def as_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


def progress_snapshot(
    out_dir: str | Path,
    *,
    started_at: float | None = None,
    finished_at: float | None = None,
) -> ProgressSnapshot:
    output_path = Path(out_dir)
    cursor = _read_json(output_path / "bookmark_pages" / "x_web_graphql_cursor_state.json")
    media = _read_json(output_path / "media_progress.json")
    label = _read_json(output_path / "label_progress.json")
    return ProgressSnapshot(
        out_dir=str(output_path),
        output_exists=output_path.exists(),
        server_time=time.time(),
        started_at=started_at,
        finished_at=finished_at,
        bookmarks_rows=_jsonl_count(output_path / "bookmarks_items.jsonl"),
        page_count=_page_count(output_path),
        cursor_item_count=_safe_int_or_none(cursor.get("item_count")),
        cursor_finished=_safe_bool_or_none(cursor.get("finished")),
        rate_limited=_safe_bool_or_none(cursor.get("rate_limited")),
        media_total=_safe_int_or_none(media.get("total")),
        media_done=_safe_int_or_none(media.get("done")),
        media_remaining=_safe_int_or_none(media.get("remaining")),
        media_ok=_safe_int_or_none(media.get("ok")),
        media_error=_safe_int_or_none(media.get("error")),
        media_skipped=_safe_int_or_none(media.get("skipped")),
        media_pending=_safe_int_or_none(media.get("pending")),
        media_finished=_safe_bool_or_none(media.get("finished")),
        media_elapsed_seconds=_safe_float_or_none(media.get("elapsed_seconds")),
        media_estimated_remaining_seconds=_safe_float_or_none(
            media.get("estimated_remaining_seconds")
        ),
        media_items_per_second=_safe_float_or_none(media.get("items_per_second")),
        media_updated_at=str(media.get("updated_at") or "") or None,
        label_total=_safe_int_or_none(label.get("total")),
        label_done=_safe_int_or_none(label.get("done")),
        label_remaining=_safe_int_or_none(label.get("remaining")),
        label_written=_safe_int_or_none(label.get("written_labels")),
        label_finished=_safe_bool_or_none(label.get("finished")),
        label_elapsed_seconds=_safe_float_or_none(label.get("elapsed_seconds")),
        label_estimated_remaining_seconds=_safe_float_or_none(
            label.get("estimated_remaining_seconds")
        ),
        label_items_per_second=_safe_float_or_none(label.get("items_per_second")),
        label_status=str(label.get("status") or "") or None,
        label_error_message=str(label.get("error_message") or "") or None,
        label_retry_after_seconds=_safe_float_or_none(label.get("retry_after_seconds")),
        label_next_retry_at=_safe_float_or_none(label.get("next_retry_at")),
        label_retry_attempt=_safe_int_or_none(label.get("retry_attempt")),
        label_retry_attempts=_safe_int_or_none(label.get("retry_attempts")),
        label_updated_at=str(label.get("updated_at") or "") or None,
    )


def serve_progress_monitor(
    *,
    out_dir: str | Path,
    host: str = "127.0.0.1",
    port: int = 8766,
    open_browser: bool = True,
) -> None:
    output_path = Path(out_dir)
    state_cache: dict[str, Any] = {}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802 - stdlib handler API.
            parsed = urlparse(self.path)
            if parsed.path == "/":
                self._html(_monitor_page(output_path))
                return
            if parsed.path == "/data":
                payload = _stable_progress_payload(output_path, state_cache)
                self._json(payload)
                return
            self.send_error(404)

        def log_message(self, format: str, *args: Any) -> None:
            return

        def _html(self, body: str) -> None:
            payload = body.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def _json(self, payload: dict[str, Any]) -> None:
            body = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    server = ThreadingHTTPServer((host, port), Handler)
    url = f"http://{host}:{port}"
    print(f"research_x progress monitor: {url}")
    print(f"out_dir: {output_path}")
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("research_x progress monitor: shutting down")
    finally:
        server.server_close()


def _monitor_page(out_dir: Path) -> str:
    escaped_out = _html_escape(str(out_dir))
    return f"""<!doctype html>
<html lang="ja">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>research_x progress</title>
  <style>
    body {{ font-family: system-ui, sans-serif; margin: 24px; max-width: 960px; }}
    h1 {{ font-size: 24px; }}
    .row {{ display: flex; justify-content: space-between; gap: 16px; }}
    .bar {{ width: 100%; height: 18px; background: #e5e7eb; border-radius: 4px; overflow: hidden; }}
    .fill {{ height: 100%; width: 0%; background: #2563eb; transition: width 0.25s linear; }}
    .done {{ background: #16a34a; }}
    .warn {{ background: #d97706; }}
    .grid {{ display: grid; gap: 14px; }}
    pre {{ white-space: pre-wrap; background: #f6f6f6; padding: 12px; overflow: auto; }}
  </style>
</head>
<body>
  <h1>research_x live progress</h1>
  <p>out: <code>{escaped_out}</code></p>
  <section class="grid">
    <div>
      <div class="row"><strong>本文取得</strong><span id="text-label">loading</span></div>
      <div class="bar"><div id="text-fill" class="fill warn"></div></div>
    </div>
    <div>
      <div class="row"><strong>画像保存</strong><span id="media-label">loading</span></div>
      <div class="bar"><div id="media-fill" class="fill"></div></div>
    </div>
    <div id="label-block" style="display:none">
      <div class="row"><strong>AI分類</strong><span id="label-label">loading</span></div>
      <div class="bar"><div id="label-fill" class="fill"></div></div>
    </div>
    <pre id="details">loading</pre>
  </section>
  <script>
    let state = null;
    let receivedAt = Date.now();
    let statusMessage = "";

    function fmtDuration(value) {{
      if (value === null || value === undefined || !Number.isFinite(value)) return "unknown";
      const seconds = Math.max(0, Math.floor(value));
      const h = Math.floor(seconds / 3600);
      const m = Math.floor((seconds % 3600) / 60);
      const s = seconds % 60;
      if (h) return `${{h}}h ${{m}}m ${{s}}s`;
      return `${{m}}m ${{s}}s`;
    }}

    function pct(done, total) {{
      if (!total || total <= 0 || done === null || done === undefined) return 0;
      return Math.max(0, Math.min(100, done / total * 100));
    }}

    function setBar(id, percent, finished) {{
      const el = document.getElementById(id);
      el.style.width = `${{percent.toFixed(1)}}%`;
      el.classList.toggle("done", Boolean(finished));
    }}

    function render() {{
      if (!state) return;
      const now = Date.now();
      const drift = (now - receivedAt) / 1000;
      const textFinished = state.cursor_finished === true;
      const textCount = state.cursor_item_count ?? 0;
      const textPercent = textFinished ? 100 : 0;
      document.getElementById("text-label").textContent =
        textFinished
          ? `完了 ${{textCount}}件 / ${{state.page_count}} pages`
          : `取得中 ${{textCount}}件 / ${{state.page_count}} pages`;
      setBar("text-fill", textPercent, textFinished);

      const mediaDone = state.media_done ?? 0;
      const mediaTotal = state.media_total ?? 0;
      const mediaPercent = pct(mediaDone, mediaTotal);
      const mediaEta = state.media_estimated_remaining_seconds == null
        ? null
        : Math.max(0, state.media_estimated_remaining_seconds - drift);
      document.getElementById("media-label").textContent =
        mediaTotal
          ? (
            `${{mediaDone}}/${{mediaTotal}} ` +
            `(${{mediaPercent.toFixed(1)}}%) 残り ${{fmtDuration(mediaEta)}}`
          )
          : "待機中";
      setBar("media-fill", mediaPercent, state.media_finished === true);

      const mediaElapsed = state.media_elapsed_seconds == null
        ? null
        : state.media_elapsed_seconds + drift;
      const labelDone = state.label_done ?? 0;
      const labelTotal = state.label_total ?? 0;
      const labelPercent = pct(labelDone, labelTotal);
      const labelEta = state.label_estimated_remaining_seconds == null
        ? null
        : Math.max(0, state.label_estimated_remaining_seconds - drift);
      const labelBlock = document.getElementById("label-block");
      labelBlock.style.display = labelTotal ? "" : "none";
      if (labelTotal) {{
        document.getElementById("label-label").textContent =
          `${{labelDone}}/${{labelTotal}} ` +
          `(${{labelPercent.toFixed(1)}}%) 残り ${{fmtDuration(labelEta)}}`;
        setBar("label-fill", labelPercent, state.label_finished === true);
      }}
      const labelElapsed = state.label_elapsed_seconds == null
        ? null
        : state.label_elapsed_seconds + drift;
      document.getElementById("details").textContent = [
        statusMessage,
        `output exists: ${{state.output_exists}}`,
        `bookmarks_items rows: ${{state.bookmarks_rows}}`,
        `cursor finished: ${{state.cursor_finished}}`,
        `rate limited: ${{state.rate_limited}}`,
        `media elapsed: ${{fmtDuration(mediaElapsed)}}`,
        (
          `media ok/error/skipped: ${{state.media_ok ?? 0}}/` +
          `${{state.media_error ?? 0}}/${{state.media_skipped ?? 0}}`
        ),
        `media pending: ${{state.media_pending ?? 0}}`,
        (
          "media speed: " +
          `${{state.media_items_per_second == null
            ? "unknown"
            : state.media_items_per_second.toFixed(2) + "/s"}}`
        ),
        `label progress: ${{labelDone}}/${{labelTotal}}`,
        `label written: ${{state.label_written ?? 0}}`,
        `label elapsed: ${{fmtDuration(labelElapsed)}}`,
        `label status: ${{state.label_status ?? "unknown"}}`,
        `label error: ${{state.label_error_message ?? ""}}`,
        (
          `label retry: ${{state.label_retry_attempt ?? ""}}/` +
          `${{state.label_retry_attempts ?? ""}} ` +
          `after ${{fmtDuration(state.label_retry_after_seconds)}}`
        ),
        `updated: ${{state.media_updated_at ?? "unknown"}}`
      ].join("\\n");
    }}

    function hasMediaProgress(candidate) {{
      return candidate && candidate.media_total && candidate.media_total > 0;
    }}

    async function poll() {{
      try {{
        const response = await fetch("/data", {{ cache: "no-store" }});
        const next = await response.json();
        statusMessage = next.stale
          ? `progress source is temporarily busy; showing cached data (${{next.stale_reason}})`
          : "";
        if (hasMediaProgress(next) || !state) {{
          state = next;
          receivedAt = Date.now();
          render();
        }} else {{
          statusMessage = "progress source returned incomplete data; keeping last value";
          render();
        }}
      }} catch (error) {{
        statusMessage = `poll failed; keeping last value: ${{error}}`;
        render();
      }}
    }}

    setInterval(render, 1000);
    setInterval(poll, 1000);
    poll();
  </script>
</body>
</html>"""


def _stable_progress_payload(out_dir: Path, cache: dict[str, Any]) -> dict[str, Any]:
    snapshot = progress_snapshot(out_dir).as_dict()
    if _has_media_progress(snapshot) or _has_label_progress(snapshot):
        snapshot["stale"] = False
        snapshot["stale_reason"] = None
        cache["snapshot"] = snapshot
        return snapshot
    previous = cache.get("snapshot")
    if isinstance(previous, dict):
        stale = dict(previous)
        stale["server_time"] = time.time()
        stale["stale"] = True
        stale["stale_reason"] = "incomplete_media_progress"
        return stale
    snapshot["stale"] = True
    snapshot["stale_reason"] = "no_complete_snapshot_yet"
    return snapshot


def _has_media_progress(snapshot: dict[str, Any]) -> bool:
    total = snapshot.get("media_total")
    done = snapshot.get("media_done")
    return isinstance(total, int) and total > 0 and isinstance(done, int) and done >= 0


def _has_label_progress(snapshot: dict[str, Any]) -> bool:
    total = snapshot.get("label_total")
    done = snapshot.get("label_done")
    return isinstance(total, int) and total >= 0 and isinstance(done, int) and done >= 0


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _jsonl_count(path: Path) -> int:
    if not path.exists():
        return 0
    try:
        with path.open("r", encoding="utf-8") as handle:
            return sum(1 for _ in handle)
    except OSError:
        return 0


def _page_count(out_dir: Path) -> int:
    page_dir = out_dir / "bookmark_pages" / "x_web_graphql"
    if not page_dir.exists():
        return 0
    return sum(1 for candidate in page_dir.glob("*.json") if candidate.is_file())


def _safe_int_or_none(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _safe_float_or_none(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _safe_bool_or_none(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    return None


def _html_escape(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )
