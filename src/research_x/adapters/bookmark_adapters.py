from __future__ import annotations

import asyncio
import contextlib
import json
import sys
from dataclasses import dataclass
from datetime import datetime
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any

from research_x.contracts import (
    AcquisitionTarget,
    AdapterConfig,
    FetchOutcome,
    OutcomeStatus,
    TargetKind,
    XItem,
    utc_now,
)
from research_x.cookies import (
    cookie_header,
    is_usable_x_cookie,
    load_cookie_dict_from_playwright_state,
    require_x_session_cookies,
)


class XWebGraphQLBookmarksAdapter:
    adapter_id = "x_web_graphql_bookmarks"

    def __init__(self, config: AdapterConfig) -> None:
        self.config = config

    def fetch(self, target: AcquisitionTarget) -> FetchOutcome:
        return asyncio.run(self._fetch(target))

    async def _fetch(self, target: AcquisitionTarget) -> FetchOutcome:
        started_at = utc_now()
        if target.kind != TargetKind.BOOKMARKS:
            return _unsupported(self.adapter_id, target, started_at)
        settings = _XWebGraphQLBookmarkSettings.from_config(self.config)
        readiness = settings.readiness_error()
        if readiness is not None:
            return FetchOutcome(
                adapter_id=self.adapter_id,
                target=target,
                status=OutcomeStatus.NOT_CONFIGURED,
                started_at=started_at,
                finished_at=utc_now(),
                error_type="NotConfigured",
                error_message=readiness,
                metadata={"storage_state": str(settings.storage_state)},
            )

        try:
            import httpx
            from twikit.client.gql import Endpoint
            from twikit.constants import BOOKMARK_FOLDER_TIMELINE_FEATURES, FEATURES, TOKEN
            from twikit.utils import flatten_params
        except ImportError as exc:
            return FetchOutcome(
                adapter_id=self.adapter_id,
                target=target,
                status=OutcomeStatus.NOT_CONFIGURED,
                started_at=started_at,
                finished_at=utc_now(),
                error_type="MissingDependency",
                error_message="Install twikit and httpx to enable this adapter.",
                metadata={"dependency": "twikit/httpx", "detail": str(exc)},
            )

        cookies = settings.cookies()
        headers = {
            "authorization": f"Bearer {TOKEN}",
            "cookie": cookie_header(cookies),
            "referer": "https://x.com/i/bookmarks",
            "x-csrf-token": cookies["ct0"],
            "x-twitter-active-user": "yes",
            "x-twitter-auth-type": "OAuth2Session",
            "x-twitter-client-language": settings.language,
            "user-agent": settings.user_agent,
        }

        items: list[XItem] = []
        cursor_state = settings.load_cursor_state()
        if cursor_state is not None:
            items.extend(settings.load_raw_page_items(limit=target.limit))
        cursor = cursor_state.next_cursor if cursor_state else None
        seen_cursors: set[str] = set(cursor_state.seen_cursors if cursor_state else ())
        page_index = cursor_state.page_count if cursor_state else 0
        resumed_from_page_count = page_index
        resumed_item_count = len(items)
        page_item_counts: list[int] = []
        cursor_exhausted = False
        rate_limited = False
        last_status_code: int | None = None
        try:
            async with httpx.AsyncClient(
                timeout=settings.request_timeout_seconds,
                headers=headers,
                follow_redirects=True,
            ) as client:
                while len(items) < target.limit and page_index < settings.max_pages:
                    endpoint, params = settings.request(
                        Endpoint,
                        FEATURES,
                        BOOKMARK_FOLDER_TIMELINE_FEATURES,
                        flatten_params,
                        cursor,
                        remaining=target.limit - len(items),
                    )
                    response = await client.get(endpoint, params=params)
                    last_status_code = response.status_code
                    if response.status_code >= 400:
                        rate_limited = response.status_code == 429
                        settings.write_error_page(
                            page_index,
                            endpoint=endpoint,
                            status_code=response.status_code,
                            text=response.text,
                            cursor=cursor,
                            headers=dict(response.headers),
                        )
                        settings.write_cursor_state(
                            next_cursor=cursor,
                            page_count=page_index,
                            seen_cursors=seen_cursors,
                            item_count=len(items),
                            finished=False,
                            last_status_code=response.status_code,
                            rate_limited=rate_limited,
                        )
                        if items:
                            break
                        return _http_error(
                            self.adapter_id,
                            target,
                            started_at,
                            endpoint,
                            response.status_code,
                            response.text,
                            metadata={
                                "storage_state": str(settings.storage_state),
                                "folder_id": settings.folder_id,
                                "raw_pages_dir": (
                                    str(settings.raw_pages_dir)
                                    if settings.raw_pages_dir is not None
                                    else None
                                ),
                                "cursor_state_file": (
                                    str(settings.cursor_state_file)
                                    if settings.cursor_state_file is not None
                                    else None
                                ),
                                "next_cursor": cursor,
                                "page_count": page_index,
                                "rate_limited": rate_limited,
                            },
                        )
                    payload = response.json()
                    settings.write_raw_page(
                        page_index,
                        payload,
                        endpoint=endpoint,
                        cursor=cursor,
                        status_code=response.status_code,
                    )
                    page_items = _web_graphql_items(payload, offset=len(items))
                    items.extend(page_items)
                    page_item_counts.append(len(page_items))
                    cursor = _next_bottom_cursor(payload)
                    page_index += 1
                    if not cursor or cursor in seen_cursors:
                        cursor_exhausted = True
                        settings.write_cursor_state(
                            next_cursor=cursor,
                            page_count=page_index,
                            seen_cursors=seen_cursors,
                            item_count=len(items),
                            finished=True,
                            last_status_code=response.status_code,
                            rate_limited=False,
                        )
                        break
                    seen_cursors.add(cursor)
                    settings.write_cursor_state(
                        next_cursor=cursor,
                        page_count=page_index,
                        seen_cursors=seen_cursors,
                        item_count=len(items),
                        finished=False,
                        last_status_code=response.status_code,
                        rate_limited=False,
                    )
        except Exception as exc:  # noqa: BLE001 - provider isolation.
            return FetchOutcome(
                adapter_id=self.adapter_id,
                target=target,
                status=OutcomeStatus.ERROR,
                started_at=started_at,
                finished_at=utc_now(),
                error_type=type(exc).__name__,
                error_message=str(exc),
                metadata={"storage_state": str(settings.storage_state)},
            )

        items = _dedupe_items(items)[: max(1, target.limit)]
        status = (
            OutcomeStatus.OK
            if items and (len(items) >= target.limit or cursor_exhausted)
            else OutcomeStatus.PARTIAL
        )
        if not items:
            status = OutcomeStatus.EMPTY
        return FetchOutcome(
            adapter_id=self.adapter_id,
            target=target,
            status=status,
            started_at=started_at,
            finished_at=utc_now(),
            items=tuple(items),
            metadata={
                "library": "x_web_graphql",
                "storage_state": str(settings.storage_state),
                "folder_id": settings.folder_id,
                "page_count": page_index,
                "pages_fetched_this_run": len(page_item_counts),
                "resumed_from_page_count": resumed_from_page_count,
                "resumed_item_count": resumed_item_count,
                "page_item_counts": page_item_counts,
                "cursor_exhausted": cursor_exhausted,
                "next_cursor": cursor,
                "seen_cursor_count": len(seen_cursors),
                "raw_pages_dir": (
                    str(settings.raw_pages_dir) if settings.raw_pages_dir is not None else None
                ),
                "cursor_state_file": (
                    str(settings.cursor_state_file)
                    if settings.cursor_state_file is not None
                    else None
                ),
                "rate_limited": rate_limited,
                "last_status_code": last_status_code,
                "max_pages": settings.max_pages,
            },
        )


class GalleryDLBookmarksAdapter:
    adapter_id = "gallery_dl_bookmarks"

    def __init__(self, config: AdapterConfig) -> None:
        self.config = config

    def fetch(self, target: AcquisitionTarget) -> FetchOutcome:
        return asyncio.run(self._fetch(target))

    async def _fetch(self, target: AcquisitionTarget) -> FetchOutcome:
        started_at = utc_now()
        if target.kind != TargetKind.BOOKMARKS:
            return _unsupported(self.adapter_id, target, started_at)
        settings = _GalleryDLBookmarkSettings.from_config(self.config)
        readiness = settings.readiness_error()
        if readiness is not None:
            return FetchOutcome(
                adapter_id=self.adapter_id,
                target=target,
                status=OutcomeStatus.NOT_CONFIGURED,
                started_at=started_at,
                finished_at=utc_now(),
                error_type="NotConfigured",
                error_message=readiness,
                metadata={"storage_state": str(settings.storage_state)},
            )

        try:
            __import__("gallery_dl")
        except ImportError as exc:
            return FetchOutcome(
                adapter_id=self.adapter_id,
                target=target,
                status=OutcomeStatus.NOT_CONFIGURED,
                started_at=started_at,
                finished_at=utc_now(),
                error_type="MissingDependency",
                error_message="Install gallery-dl to enable this adapter.",
                metadata={"dependency": "gallery-dl", "detail": str(exc)},
            )

        work_dir = settings.work_dir
        work_dir.mkdir(parents=True, exist_ok=True)
        cookies_path = (work_dir / "gallery-dl-x-cookies.txt").resolve()
        _write_netscape_cookies(settings.storage_state, cookies_path)
        command = [
            sys.executable,
            "-m",
            "gallery_dl",
            "--dump-json",
            "--no-download",
            "--cookies",
            str(cookies_path),
        ]
        if not settings.exhaustive:
            command.extend(["--range", f"1-{max(1, target.limit)}"])
        command.append("https://x.com/i/bookmarks")
        try:
            process = await asyncio.create_subprocess_exec(
                *command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(work_dir),
            )
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=settings.request_timeout_seconds,
            )
        except Exception as exc:  # noqa: BLE001 - provider isolation.
            return FetchOutcome(
                adapter_id=self.adapter_id,
                target=target,
                status=OutcomeStatus.ERROR,
                started_at=started_at,
                finished_at=utc_now(),
                error_type=type(exc).__name__,
                error_message=str(exc),
                metadata={"work_dir": str(work_dir)},
            )

        stdout_text = stdout.decode("utf-8", errors="replace")
        stderr_text = stderr.decode("utf-8", errors="replace")
        if process.returncode not in (0, None):
            return FetchOutcome(
                adapter_id=self.adapter_id,
                target=target,
                status=OutcomeStatus.ERROR,
                started_at=started_at,
                finished_at=utc_now(),
                error_type="GalleryDLExit",
                error_message=stderr_text[-1200:] or stdout_text[-1200:],
                metadata={"returncode": process.returncode, "work_dir": str(work_dir)},
            )

        items = _gallery_dl_items(stdout_text, limit=max(1, target.limit))
        return FetchOutcome(
            adapter_id=self.adapter_id,
            target=target,
            status=OutcomeStatus.OK if items else OutcomeStatus.EMPTY,
            started_at=started_at,
            finished_at=utc_now(),
            items=tuple(items),
            metadata={
                "library": "gallery-dl",
                "work_dir": str(work_dir),
                "exhaustive": settings.exhaustive,
                "stderr": stderr_text[-1200:] if stderr_text else None,
            },
        )


class PlaywrightNetworkBookmarksAdapter:
    adapter_id = "playwright_network_bookmarks"

    def __init__(self, config: AdapterConfig) -> None:
        self.config = config

    def fetch(self, target: AcquisitionTarget) -> FetchOutcome:
        return asyncio.run(self._fetch(target))

    async def _fetch(self, target: AcquisitionTarget) -> FetchOutcome:
        started_at = utc_now()
        if target.kind != TargetKind.BOOKMARKS:
            return _unsupported(self.adapter_id, target, started_at)
        settings = _PlaywrightNetworkBookmarkSettings.from_config(self.config)
        if not settings.storage_state.exists():
            return FetchOutcome(
                adapter_id=self.adapter_id,
                target=target,
                status=OutcomeStatus.NOT_CONFIGURED,
                started_at=started_at,
                finished_at=utc_now(),
                error_type="MissingStorageState",
                error_message="Playwright network bookmarks needs a storage_state file.",
                metadata={"storage_state": str(settings.storage_state)},
            )

        try:
            from playwright.async_api import async_playwright
        except ImportError as exc:
            return FetchOutcome(
                adapter_id=self.adapter_id,
                target=target,
                status=OutcomeStatus.NOT_CONFIGURED,
                started_at=started_at,
                finished_at=utc_now(),
                error_type="MissingDependency",
                error_message="Install playwright to enable this adapter.",
                metadata={"dependency": "playwright", "detail": str(exc)},
            )

        captured: list[XItem] = []
        tasks: list[asyncio.Task] = []
        try:
            async with async_playwright() as pw:
                browser = await pw.chromium.launch(headless=settings.headless)
                context = await browser.new_context(
                    storage_state=str(settings.storage_state),
                    viewport=settings.viewport,
                )
                page = await context.new_page()
                page.set_default_timeout(settings.timeout_ms)
                page.set_default_navigation_timeout(settings.timeout_ms)

                def on_response(response: Any) -> None:
                    if not _is_bookmark_graphql_url(response.url):
                        return
                    tasks.append(
                        asyncio.create_task(_capture_bookmark_response(response, captured))
                    )

                page.on("response", on_response)
                await page.goto("https://x.com/i/bookmarks", wait_until=settings.wait_until)
                with contextlib.suppress(Exception):
                    await page.locator("article[data-testid='tweet']").first.wait_for(
                        state="attached",
                        timeout=settings.timeout_ms,
                    )
                for _ in range(max(1, settings.max_scroll_steps)):
                    await _drain_tasks(tasks)
                    if len(_dedupe_items(captured)) >= target.limit:
                        break
                    await page.mouse.wheel(0, settings.viewport["height"])
                    await page.wait_for_timeout(settings.scroll_pause_ms)
                await _drain_tasks(tasks)
                await context.close()
                await browser.close()
        except Exception as exc:  # noqa: BLE001 - provider isolation.
            if captured:
                items = _dedupe_items(captured)[: max(1, target.limit)]
                return FetchOutcome(
                    adapter_id=self.adapter_id,
                    target=target,
                    status=OutcomeStatus.PARTIAL,
                    started_at=started_at,
                    finished_at=utc_now(),
                    items=tuple(items),
                    error_type=type(exc).__name__,
                    error_message=str(exc),
                    metadata={"storage_state": str(settings.storage_state)},
                )
            return FetchOutcome(
                adapter_id=self.adapter_id,
                target=target,
                status=OutcomeStatus.ERROR,
                started_at=started_at,
                finished_at=utc_now(),
                error_type=type(exc).__name__,
                error_message=str(exc),
                metadata={"storage_state": str(settings.storage_state)},
            )

        items = _dedupe_items(captured)[: max(1, target.limit)]
        return FetchOutcome(
            adapter_id=self.adapter_id,
            target=target,
            status=OutcomeStatus.OK if items else OutcomeStatus.EMPTY,
            started_at=started_at,
            finished_at=utc_now(),
            items=tuple(items),
            metadata={
                "library": "playwright",
                "mode": "network_graphql_capture",
                "storage_state": str(settings.storage_state),
            },
        )


@dataclass(frozen=True)
class _XWebBookmarkCursorState:
    next_cursor: str | None
    page_count: int
    seen_cursors: tuple[str, ...]
    item_count: int
    finished: bool
    last_status_code: int | None
    rate_limited: bool


class _XWebGraphQLBookmarkSettings:
    def __init__(
        self,
        *,
        storage_state: Path,
        folder_id: str | None,
        page_size: int,
        request_timeout_seconds: float,
        language: str,
        user_agent: str,
        raw_pages_dir: Path | None,
        cursor_state_file: Path | None,
        resume: bool,
        max_pages: int,
    ) -> None:
        self.storage_state = storage_state
        self.folder_id = folder_id
        self.page_size = max(1, min(100, page_size))
        self.request_timeout_seconds = request_timeout_seconds
        self.language = language
        self.user_agent = user_agent
        self.raw_pages_dir = raw_pages_dir
        self.cursor_state_file = cursor_state_file
        self.resume = resume
        self.max_pages = max(1, max_pages)

    @classmethod
    def from_config(cls, config: AdapterConfig) -> _XWebGraphQLBookmarkSettings:
        folder_id = config.options.get("folder_id")
        folder_id = str(folder_id) if folder_id is not None and folder_id != "" else None
        raw_pages_dir = _optional_path(config.options.get("raw_pages_dir"))
        cursor_state_file = _optional_path(config.options.get("cursor_state_file"))
        return cls(
            storage_state=Path(
                str(config.options.get("storage_state", ".secrets/playwright_x_state.json"))
            ),
            folder_id=folder_id,
            page_size=int(config.options.get("page_size", 100)),
            request_timeout_seconds=float(config.options.get("request_timeout_seconds", 45)),
            language=str(config.options.get("language", "en")),
            user_agent=str(
                config.options.get(
                    "user_agent",
                    "Mozilla/5.0 AppleWebKit/537.36 Chrome/120 Safari/537.36",
                )
            ),
            raw_pages_dir=raw_pages_dir,
            cursor_state_file=cursor_state_file,
            resume=bool(config.options.get("resume", True)),
            max_pages=int(config.options.get("max_pages", 1000)),
        )

    def readiness_error(self) -> str | None:
        if not self.storage_state.exists():
            return "X Web GraphQL bookmarks needs a Playwright storage_state file."
        try:
            self.cookies()
        except ValueError as exc:
            return str(exc)
        return None

    def cookies(self) -> dict[str, str]:
        cookies = load_cookie_dict_from_playwright_state(self.storage_state)
        require_x_session_cookies(cookies)
        return cookies

    def load_cursor_state(self) -> _XWebBookmarkCursorState | None:
        if not self.resume or self.cursor_state_file is None or not self.cursor_state_file.exists():
            return None
        try:
            data = json.loads(self.cursor_state_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if data.get("finished"):
            return None
        cursor = data.get("next_cursor")
        if cursor is not None and not isinstance(cursor, str):
            return None
        seen = data.get("seen_cursors", [])
        if not isinstance(seen, list):
            seen = []
        return _XWebBookmarkCursorState(
            next_cursor=cursor,
            page_count=max(0, int(data.get("page_count", 0) or 0)),
            seen_cursors=tuple(str(item) for item in seen if item),
            item_count=max(0, int(data.get("item_count", 0) or 0)),
            finished=bool(data.get("finished", False)),
            last_status_code=(
                int(data["last_status_code"]) if data.get("last_status_code") is not None else None
            ),
            rate_limited=bool(data.get("rate_limited", False)),
        )

    def write_cursor_state(
        self,
        *,
        next_cursor: str | None,
        page_count: int,
        seen_cursors: set[str],
        item_count: int,
        finished: bool,
        last_status_code: int | None,
        rate_limited: bool,
    ) -> None:
        if self.cursor_state_file is None:
            return
        self.cursor_state_file.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "updated_at": utc_now().isoformat(),
            "next_cursor": next_cursor,
            "page_count": page_count,
            "seen_cursors": sorted(seen_cursors),
            "item_count": item_count,
            "finished": finished,
            "last_status_code": last_status_code,
            "rate_limited": rate_limited,
        }
        self.cursor_state_file.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )

    def load_raw_page_items(self, *, limit: int) -> list[XItem]:
        if self.raw_pages_dir is None or not self.raw_pages_dir.exists():
            return []
        items: list[XItem] = []
        for page_path in sorted(self.raw_pages_dir.glob("*.json")):
            if page_path.name.endswith(".error.json"):
                continue
            try:
                raw = json.loads(page_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            payload = raw.get("payload") if isinstance(raw, dict) else None
            if not isinstance(payload, dict):
                continue
            items.extend(_web_graphql_items(payload, offset=len(items)))
            if len(items) >= limit:
                return _dedupe_items(items)[:limit]
        return _dedupe_items(items)[:limit]

    def write_raw_page(
        self,
        page_index: int,
        payload: dict[str, Any],
        *,
        endpoint: str,
        cursor: str | None,
        status_code: int,
    ) -> None:
        if self.raw_pages_dir is None:
            return
        self.raw_pages_dir.mkdir(parents=True, exist_ok=True)
        page_path = self.raw_pages_dir / f"{page_index:05d}.json"
        page_payload = {
            "fetched_at": utc_now().isoformat(),
            "endpoint": endpoint,
            "cursor": cursor,
            "status_code": status_code,
            "payload": payload,
        }
        page_path.write_text(
            json.dumps(page_payload, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )

    def write_error_page(
        self,
        page_index: int,
        *,
        endpoint: str,
        status_code: int,
        text: str,
        cursor: str | None,
        headers: dict[str, Any],
    ) -> None:
        if self.raw_pages_dir is None:
            return
        self.raw_pages_dir.mkdir(parents=True, exist_ok=True)
        page_path = self.raw_pages_dir / f"{page_index:05d}.error.json"
        payload = {
            "fetched_at": utc_now().isoformat(),
            "endpoint": endpoint,
            "cursor": cursor,
            "status_code": status_code,
            "headers": headers,
            "text": text[:4000],
        }
        page_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )

    def request(
        self,
        endpoint_module: Any,
        features: dict[str, Any],
        folder_features: dict[str, Any],
        flatten_params: Any,
        cursor: str | None,
        *,
        remaining: int,
    ) -> tuple[str, dict[str, str]]:
        count = max(1, min(self.page_size, remaining, 100))
        variables: dict[str, Any] = {
            "count": count,
            "includePromotedContent": True,
        }
        if cursor is not None:
            variables["cursor"] = cursor
        if self.folder_id:
            variables["bookmark_collection_id"] = self.folder_id
            return endpoint_module.BOOKMARK_FOLDER_TIMELINE, flatten_params(
                {"variables": variables, "features": folder_features}
            )
        merged_features = dict(features)
        merged_features["graphql_timeline_v2_bookmark_timeline"] = True
        return endpoint_module.BOOKMARKS, flatten_params(
            {"variables": variables, "features": merged_features}
        )


class _GalleryDLBookmarkSettings:
    def __init__(
        self,
        *,
        storage_state: Path,
        work_dir: Path,
        request_timeout_seconds: float,
        exhaustive: bool,
    ) -> None:
        self.storage_state = storage_state
        self.work_dir = work_dir
        self.request_timeout_seconds = request_timeout_seconds
        self.exhaustive = exhaustive

    @classmethod
    def from_config(cls, config: AdapterConfig) -> _GalleryDLBookmarkSettings:
        return cls(
            storage_state=Path(
                str(config.options.get("storage_state", ".secrets/playwright_x_state.json"))
            ),
            work_dir=Path(str(config.options.get("work_dir", ".secrets/gallery_dl_bookmarks"))),
            request_timeout_seconds=float(config.options.get("request_timeout_seconds", 120)),
            exhaustive=bool(config.options.get("exhaustive", False)),
        )

    def readiness_error(self) -> str | None:
        if not self.storage_state.exists():
            return "gallery-dl bookmarks needs a Playwright storage_state file."
        try:
            cookies = load_cookie_dict_from_playwright_state(self.storage_state)
            require_x_session_cookies(cookies)
        except ValueError as exc:
            return str(exc)
        return None


class _PlaywrightNetworkBookmarkSettings:
    def __init__(
        self,
        *,
        storage_state: Path,
        headless: bool,
        timeout_ms: float,
        viewport: dict[str, int],
        wait_until: str,
        max_scroll_steps: int,
        scroll_pause_ms: int,
    ) -> None:
        self.storage_state = storage_state
        self.headless = headless
        self.timeout_ms = timeout_ms
        self.viewport = viewport
        self.wait_until = wait_until
        self.max_scroll_steps = max_scroll_steps
        self.scroll_pause_ms = scroll_pause_ms

    @classmethod
    def from_config(cls, config: AdapterConfig) -> _PlaywrightNetworkBookmarkSettings:
        return cls(
            storage_state=Path(
                str(config.options.get("storage_state", ".secrets/playwright_x_state.json"))
            ),
            headless=bool(config.options.get("headless", True)),
            timeout_ms=float(config.options.get("timeout_ms", 45000)),
            viewport={
                "width": int(config.options.get("viewport_width", 1280)),
                "height": int(config.options.get("viewport_height", 900)),
            },
            wait_until=str(config.options.get("wait_until", "domcontentloaded")),
            max_scroll_steps=int(config.options.get("max_scroll_steps", 20)),
            scroll_pause_ms=int(config.options.get("scroll_pause_ms", 1200)),
        )


def _web_graphql_items(payload: dict[str, Any], *, offset: int = 0) -> list[XItem]:
    items: list[XItem] = []
    seen: set[str] = set()
    for tweet in _iter_bookmark_tweet_results(payload):
        legacy = tweet.get("legacy", {})
        if not isinstance(legacy, dict):
            continue
        source_id = str(tweet.get("rest_id") or legacy.get("id_str") or "")
        if not source_id or source_id in seen:
            continue
        seen.add(source_id)
        user = tweet.get("core", {}).get("user_results", {}).get("result", {})
        user_legacy = user.get("legacy", {}) if isinstance(user, dict) else {}
        author = user_legacy.get("screen_name") or user.get("screen_name")
        raw = dict(tweet)
        raw["source_timeline"] = "bookmarks"
        raw["bookmark_root"] = True
        raw["bookmark_index"] = offset + len(items)
        raw["source_api"] = "x_web_graphql"
        items.append(
            XItem(
                source_id=source_id,
                url=f"https://x.com/{author}/status/{source_id}" if author else None,
                author=str(author) if author else None,
                text=legacy.get("full_text"),
                created_at=_parse_datetime(legacy.get("created_at")),
                observed_at=utc_now(),
                raw=raw,
            )
        )
    return items


def _gallery_dl_items(text: str, *, limit: int) -> list[XItem]:
    rows = _json_objects_from_text(text)
    items: list[XItem] = []
    seen: set[str] = set()
    for row in rows:
        for tweet in _iter_gallery_dl_tweets(row):
            source_id = _first_str(tweet, ("tweet_id", "id", "rest_id", "id_str"))
            if not source_id or source_id in seen:
                continue
            seen.add(source_id)
            author = _gallery_dl_author(tweet)
            quoted_by_id = _gallery_dl_quoted_by_id(tweet)
            is_bookmark_root = quoted_by_id is None
            raw = dict(tweet)
            raw["source_timeline"] = "bookmarks"
            raw["bookmark_root"] = is_bookmark_root
            raw["bookmark_index"] = len(items)
            raw["source_api"] = "gallery_dl"
            if quoted_by_id is not None:
                raw["bookmark_relation"] = "quoted_tweet"
                raw["quoted_by_id_str"] = quoted_by_id
            items.append(
                XItem(
                    source_id=source_id,
                    url=_gallery_dl_url(tweet, author, source_id),
                    author=author,
                    text=_first_str(tweet, ("content", "text", "full_text", "description")),
                    created_at=_parse_datetime(tweet.get("date") or tweet.get("created_at")),
                    observed_at=utc_now(),
                    raw=raw,
                )
            )
            if len(items) >= limit:
                return items
    return items


def _gallery_dl_quoted_by_id(row: dict[str, Any]) -> str | None:
    legacy = row.get("legacy")
    if isinstance(legacy, dict):
        value = legacy.get("quoted_by_id_str")
        if value:
            return str(value)
    value = row.get("quoted_by_id_str")
    return str(value) if value else None


def _json_objects_from_text(text: str) -> list[Any]:
    stripped = text.strip()
    if not stripped:
        return []
    try:
        parsed = json.loads(stripped)
        return parsed if isinstance(parsed, list) else [parsed]
    except json.JSONDecodeError:
        pass
    decoder = json.JSONDecoder()
    rows: list[Any] = []
    index = 0
    while index < len(text):
        while index < len(text) and text[index].isspace():
            index += 1
        if index >= len(text):
            break
        try:
            row, next_index = decoder.raw_decode(text, index)
        except json.JSONDecodeError:
            index += 1
            continue
        rows.append(row)
        index = next_index
    return rows


def _iter_gallery_dl_tweets(value: Any):
    if isinstance(value, dict):
        if any(key in value for key in ("tweet_id", "content", "full_text")):
            yield value
        for item in value.values():
            yield from _iter_gallery_dl_tweets(item)
    elif isinstance(value, list):
        for item in value:
            yield from _iter_gallery_dl_tweets(item)


def _first_str(row: dict[str, Any], keys: tuple[str, ...]) -> str | None:
    for key in keys:
        value = row.get(key)
        if value not in (None, ""):
            return str(value)
    return None


def _gallery_dl_author(row: dict[str, Any]) -> str | None:
    author = row.get("author") or row.get("user")
    if isinstance(author, dict):
        return _first_str(author, ("nick", "name", "screen_name", "username", "id"))
    if author not in (None, ""):
        return str(author)
    return None


def _gallery_dl_url(row: dict[str, Any], author: str | None, source_id: str) -> str | None:
    for key in ("tweet_url", "url", "post_url"):
        value = row.get(key)
        if isinstance(value, str) and "/status/" in value:
            return value
    if author and source_id:
        return f"https://x.com/{author}/status/{source_id}"
    return None


def _is_bookmark_graphql_url(url: str) -> bool:
    return "/i/api/graphql/" in url and (
        "Bookmarks" in url or "BookmarkFolderTimeline" in url
    )


async def _capture_bookmark_response(response: Any, captured: list[XItem]) -> None:
    with contextlib.suppress(Exception):
        payload = await response.json()
        captured.extend(_web_graphql_items(payload, offset=len(captured)))


async def _drain_tasks(tasks: list[asyncio.Task]) -> None:
    if not tasks:
        return
    pending = list(tasks)
    tasks.clear()
    await asyncio.gather(*pending, return_exceptions=True)


def _write_netscape_cookies(storage_state: Path, output_path: Path) -> None:
    payload = json.loads(storage_state.read_text(encoding="utf-8"))
    rows = ["# Netscape HTTP Cookie File"]
    for cookie in payload.get("cookies", []):
        if not is_usable_x_cookie(cookie):
            continue
        domain = str(cookie.get("domain", ""))
        include_subdomains = "TRUE" if domain.startswith(".") else "FALSE"
        path = str(cookie.get("path", "/"))
        secure = "TRUE" if cookie.get("secure", True) else "FALSE"
        expires = int(float(cookie.get("expires", 0) or 0))
        name = str(cookie.get("name", ""))
        value = str(cookie.get("value", ""))
        if name:
            rows.append(
                "\t".join([domain, include_subdomains, path, secure, str(expires), name, value])
            )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(rows) + "\n", encoding="utf-8")


def _iter_bookmark_tweet_results(value: Any):
    for entry in _iter_timeline_entries(value):
        yield from _tweet_results_from_entry(entry)


def _iter_timeline_entries(value: Any):
    if isinstance(value, dict):
        if isinstance(value.get("content"), dict) and isinstance(value.get("entryId"), str):
            yield value
        for item in value.values():
            yield from _iter_timeline_entries(item)
    elif isinstance(value, list):
        for item in value:
            yield from _iter_timeline_entries(item)


def _tweet_results_from_entry(entry: dict[str, Any]):
    content = entry.get("content")
    if not isinstance(content, dict):
        return
    item_content = content.get("itemContent")
    if isinstance(item_content, dict):
        tweet = _unwrap_tweet_result(item_content.get("tweet_results"))
        if tweet is not None:
            yield tweet
    items = content.get("items")
    if isinstance(items, list):
        for item in items:
            if not isinstance(item, dict):
                continue
            nested_content = item.get("item", {}).get("itemContent")
            if not isinstance(nested_content, dict):
                nested_content = item.get("itemContent")
            if isinstance(nested_content, dict):
                tweet = _unwrap_tweet_result(nested_content.get("tweet_results"))
                if tweet is not None:
                    yield tweet


def _unwrap_tweet_result(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    result = value.get("result", value)
    if not isinstance(result, dict):
        return None
    if result.get("__typename") == "TweetWithVisibilityResults":
        result = result.get("tweet")
    if (
        isinstance(result, dict)
        and result.get("__typename") in (None, "Tweet")
        and isinstance(result.get("legacy"), dict)
        and result.get("rest_id")
    ):
        return result
    return None


def _next_bottom_cursor(payload: dict[str, Any]) -> str | None:
    for value in _iter_dicts(payload):
        if value.get("cursorType") == "Bottom" and value.get("value"):
            return str(value["value"])
        entry_id = str(value.get("entryId", ""))
        content = value.get("content")
        if entry_id.startswith("cursor-bottom") and isinstance(content, dict):
            cursor_value = content.get("value")
            if cursor_value:
                return str(cursor_value)
    return None


def _iter_dicts(value: Any):
    if isinstance(value, dict):
        yield value
        for item in value.values():
            yield from _iter_dicts(item)
    elif isinstance(value, list):
        for item in value:
            yield from _iter_dicts(item)


def _dedupe_items(items: list[XItem]) -> list[XItem]:
    result: list[XItem] = []
    seen: set[str] = set()
    for item in items:
        key = item.source_id or item.url or item.text or str(len(result))
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


def _parse_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        try:
            return parsedate_to_datetime(value)
        except (TypeError, ValueError):
            return None


def _optional_path(value: Any) -> Path | None:
    if value in (None, ""):
        return None
    return Path(str(value))


def _unsupported(adapter_id: str, target: AcquisitionTarget, started_at) -> FetchOutcome:
    return FetchOutcome(
        adapter_id=adapter_id,
        target=target,
        status=OutcomeStatus.UNSUPPORTED,
        started_at=started_at,
        finished_at=utc_now(),
        error_type="UnsupportedTarget",
        error_message=f"{adapter_id} only supports bookmarks targets.",
    )


def _http_error(
    adapter_id: str,
    target: AcquisitionTarget,
    started_at,
    url: str,
    status_code: int,
    text: str,
    *,
    metadata: dict[str, Any] | None = None,
) -> FetchOutcome:
    return FetchOutcome(
        adapter_id=adapter_id,
        target=target,
        status=OutcomeStatus.ERROR,
        started_at=started_at,
        finished_at=utc_now(),
        error_type="HTTPStatus",
        error_message=f"{url} returned HTTP {status_code}: {text[:600]}",
        metadata={"url": url, "http_status": status_code, **(metadata or {})},
    )
