from __future__ import annotations

import asyncio
import contextlib
import io
import json
import os
from pathlib import Path
from typing import Any

from research_x.adapters.url_tools import (
    status_items_from_text,
    storage_state_cookie_header,
    target_to_x_url,
)
from research_x.contracts import (
    AcquisitionTarget,
    AdapterConfig,
    FetchOutcome,
    OutcomeStatus,
    utc_now,
)


class ScraplingAdapter:
    adapter_id = "scrapling"

    def __init__(self, config: AdapterConfig) -> None:
        self.config = config

    def fetch(self, target: AcquisitionTarget) -> FetchOutcome:
        return asyncio.run(self._fetch(target))

    async def _fetch(self, target: AcquisitionTarget) -> FetchOutcome:
        started_at = utc_now()
        settings = _GenericUrlSettings.from_config(self.config)
        url = target_to_x_url(target)
        try:
            from scrapling.fetchers import AsyncFetcher, PlayWrightFetcher
        except ImportError as exc:
            return _not_configured(
                self.adapter_id,
                target,
                started_at,
                "scrapling",
                "Install scrapling to enable this adapter.",
                exc,
            )

        try:
            response = await asyncio.wait_for(
                AsyncFetcher.get(
                    url,
                    timeout=settings.request_timeout_seconds,
                    proxy=settings.proxy,
                    retries=settings.retries,
                    stealthy_headers=True,
                    headers=settings.headers(),
                ),
                timeout=settings.request_timeout_seconds + 5,
            )
        except Exception as exc:  # noqa: BLE001 - provider isolation.
            return _error(self.adapter_id, target, started_at, type(exc).__name__, str(exc), url)

        text = _response_text(response)
        status_code = int(getattr(response, "status", 0) or 0)
        if status_code >= 400:
            return _http_error(self.adapter_id, target, started_at, url, status_code, text)
        items = status_items_from_text(text, target)
        fetcher = "AsyncFetcher"
        if not items and settings.render_fallback:
            rendered = await _scrapling_rendered_response(
                PlayWrightFetcher,
                url,
                settings,
            )
            text = _response_text(rendered)
            status_code = int(getattr(rendered, "status", 0) or 0)
            items = status_items_from_text(text, target)
            fetcher = "PlayWrightFetcher"
        return _outcome(
            self.adapter_id,
            target,
            started_at,
            items,
            {
                "library": "scrapling",
                "fetcher": fetcher,
                "url": url,
                "http_status": status_code or None,
                "auth": settings.auth_mode(),
            },
        )


class Crawl4AIAdapter:
    adapter_id = "crawl4ai"

    def __init__(self, config: AdapterConfig) -> None:
        self.config = config

    def fetch(self, target: AcquisitionTarget) -> FetchOutcome:
        return asyncio.run(self._fetch(target))

    async def _fetch(self, target: AcquisitionTarget) -> FetchOutcome:
        started_at = utc_now()
        settings = _GenericUrlSettings.from_config(self.config)
        url = target_to_x_url(target)
        try:
            from crawl4ai import AsyncWebCrawler, BrowserConfig, CacheMode, CrawlerRunConfig
        except ImportError as exc:
            return _not_configured(
                self.adapter_id,
                target,
                started_at,
                "crawl4ai",
                "Install crawl4ai to enable this adapter.",
                exc,
            )

        browser_config = BrowserConfig(
            headless=settings.headless,
            storage_state=str(settings.storage_state)
            if settings.storage_state is not None and settings.storage_state.exists()
            else None,
            viewport_width=settings.viewport_width,
            viewport_height=settings.viewport_height,
            proxy=settings.proxy,
            user_agent=settings.user_agent or BrowserConfig().user_agent,
            verbose=False,
        )
        run_config = CrawlerRunConfig(
            cache_mode=CacheMode.BYPASS,
            page_timeout=int(settings.request_timeout_seconds * 1000),
            wait_until="domcontentloaded",
            delay_before_return_html=settings.delay_before_return_seconds,
            scan_full_page=True,
            max_scroll_steps=settings.max_scroll_steps,
        )
        try:
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(
                io.StringIO()
            ):
                async with AsyncWebCrawler(config=browser_config) as crawler:
                    result = await asyncio.wait_for(
                        crawler.arun(url=url, config=run_config),
                        timeout=settings.request_timeout_seconds + 10,
                    )
        except Exception as exc:  # noqa: BLE001 - provider isolation.
            return _error(self.adapter_id, target, started_at, type(exc).__name__, str(exc), url)

        text = _crawl4ai_text(result)
        status_code = int(getattr(result, "status_code", 0) or 0)
        success = bool(getattr(result, "success", False))
        if status_code >= 400:
            return _http_error(self.adapter_id, target, started_at, url, status_code, text)
        if not success and not text:
            return _error(
                self.adapter_id,
                target,
                started_at,
                "Crawl4AIError",
                str(getattr(result, "error_message", "crawl4ai run did not succeed")),
                url,
            )
        items = status_items_from_text(text, target)
        if not items and settings.render_fallback:
            items = await _browser_items_with_playwright(target, settings)
        return _outcome(
            self.adapter_id,
            target,
            started_at,
            items,
            {
                "library": "crawl4ai",
                "url": url,
                "http_status": status_code or None,
                "success": success,
                "auth": settings.auth_mode(),
            },
        )


class ScrapyAdapter:
    adapter_id = "scrapy"

    def __init__(self, config: AdapterConfig) -> None:
        self.config = config

    def fetch(self, target: AcquisitionTarget) -> FetchOutcome:
        return asyncio.run(self._fetch(target))

    async def _fetch(self, target: AcquisitionTarget) -> FetchOutcome:
        started_at = utc_now()
        settings = _GenericUrlSettings.from_config(self.config)
        url = target_to_x_url(target)
        try:
            import httpx
            from scrapy.http import TextResponse
        except ImportError as exc:
            return _not_configured(
                self.adapter_id,
                target,
                started_at,
                "scrapy",
                "Install scrapy and httpx to enable this adapter.",
                exc,
            )

        try:
            async with httpx.AsyncClient(
                follow_redirects=True,
                headers=settings.headers(),
                proxy=settings.proxy,
                timeout=settings.request_timeout_seconds,
            ) as client:
                response = await client.get(url)
        except Exception as exc:  # noqa: BLE001 - provider isolation.
            return _error(self.adapter_id, target, started_at, type(exc).__name__, str(exc), url)

        text = response.text
        scrapy_response = TextResponse(
            url=str(response.url),
            body=response.content,
            encoding=response.encoding or "utf-8",
        )
        links = "\n".join(scrapy_response.css("a::attr(href)").getall())
        if response.status_code >= 400:
            return _http_error(
                self.adapter_id,
                target,
                started_at,
                url,
                response.status_code,
                text,
            )
        items = status_items_from_text(f"{text}\n{links}", target)
        mode = "static_http"
        if not items and settings.render_fallback:
            rendered_html = await _rendered_html_with_playwright(url, settings)
            rendered_response = TextResponse(
                url=url,
                body=rendered_html.encode("utf-8"),
                encoding="utf-8",
            )
            rendered_links = "\n".join(rendered_response.css("a::attr(href)").getall())
            items = status_items_from_text(f"{rendered_html}\n{rendered_links}", target)
            mode = "playwright_rendered_scrapy_parse"
        if not items and settings.render_fallback:
            items = await _browser_items_with_playwright(target, settings)
            mode = "playwright_contract_fallback"
        return _outcome(
            self.adapter_id,
            target,
            started_at,
            items,
            {
                "library": "scrapy",
                "url": url,
                "http_status": response.status_code,
                "auth": settings.auth_mode(),
                "mode": mode,
            },
        )


class _GenericUrlSettings:
    def __init__(
        self,
        *,
        storage_state: Path | None,
        request_timeout_seconds: float,
        proxy: str | None,
        user_agent: str | None,
        headless: bool,
        viewport_width: int,
        viewport_height: int,
        delay_before_return_seconds: float,
        max_scroll_steps: int,
        retries: int,
        render_fallback: bool,
        wait_until: str,
    ) -> None:
        self.storage_state = storage_state
        self.request_timeout_seconds = request_timeout_seconds
        self.timeout_ms = request_timeout_seconds * 1000
        self.proxy = proxy
        self.user_agent = user_agent
        self.headless = headless
        self.viewport_width = viewport_width
        self.viewport_height = viewport_height
        self.viewport = {"width": viewport_width, "height": viewport_height}
        self.delay_before_return_seconds = delay_before_return_seconds
        self.max_scroll_steps = max_scroll_steps
        self.retries = retries
        self.render_fallback = render_fallback
        self.wait_until = wait_until

    @classmethod
    def from_config(cls, config: AdapterConfig) -> _GenericUrlSettings:
        env_prefix = str(config.options.get("env_prefix", "RESEARCH_X"))
        storage_state_value = config.options.get("storage_state")
        return cls(
            storage_state=Path(str(storage_state_value)) if storage_state_value else None,
            request_timeout_seconds=float(config.options.get("request_timeout_seconds", 30)),
            proxy=_env(config, "proxy_env", f"{env_prefix}_X_PROXY"),
            user_agent=_option_or_env(
                config,
                "user_agent",
                "user_agent_env",
                f"{env_prefix}_X_USER_AGENT",
            ),
            headless=bool(config.options.get("headless", True)),
            viewport_width=int(config.options.get("viewport_width", 1280)),
            viewport_height=int(config.options.get("viewport_height", 900)),
            delay_before_return_seconds=float(config.options.get("delay_before_return_seconds", 2)),
            max_scroll_steps=int(config.options.get("max_scroll_steps", 2)),
            retries=int(config.options.get("retries", 1)),
            render_fallback=bool(config.options.get("render_fallback", True)),
            wait_until=str(config.options.get("wait_until", "domcontentloaded")),
        )

    def headers(self) -> dict[str, str]:
        headers: dict[str, str] = {}
        if self.user_agent:
            headers["User-Agent"] = self.user_agent
        cookies = storage_state_cookie_header(self.storage_state)
        if cookies:
            headers["Cookie"] = cookies
        return headers

    def auth_mode(self) -> str:
        if self.storage_state is not None and self.storage_state.exists():
            return "playwright_storage_state"
        return "none"


def _response_text(response: Any) -> str:
    parts: list[str] = []
    for attr in ("text", "html_content", "body"):
        value = getattr(response, attr, None)
        if callable(value):
            value = value()
        if isinstance(value, bytes):
            parts.append(value.decode("utf-8", errors="replace"))
        elif isinstance(value, str):
            parts.append(value)
    return "\n".join(part for part in parts if part)


def _crawl4ai_text(result: Any) -> str:
    parts = [
        getattr(result, "html", None),
        getattr(result, "cleaned_html", None),
        getattr(result, "markdown", None),
        getattr(result, "extracted_content", None),
    ]
    links = getattr(result, "links", None)
    if isinstance(links, dict):
        parts.append(str(links))
    return "\n".join(str(part) for part in parts if part)


async def _scrapling_rendered_response(fetcher: Any, url: str, settings: _GenericUrlSettings):
    cookies = _storage_state_cookies(settings.storage_state)

    async def page_action(page: Any):
        if cookies:
            await page.context.add_cookies(cookies)
            await page.goto(url, wait_until=settings.wait_until)
        await page.wait_for_timeout(int(settings.delay_before_return_seconds * 1000))
        return page

    return await fetcher.async_fetch(
        url,
        headless=settings.headless,
        timeout=settings.request_timeout_seconds * 1000,
        wait=1000,
        wait_selector="article[data-testid='tweet']",
        wait_selector_state="attached",
        page_action=page_action,
        extra_headers=settings.headers(),
        google_search=False,
    )


async def _rendered_html_with_playwright(url: str, settings: _GenericUrlSettings) -> str:
    from playwright.async_api import async_playwright

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=settings.headless)
        context_kwargs: dict[str, Any] = {
            "viewport": {"width": settings.viewport_width, "height": settings.viewport_height}
        }
        if settings.storage_state is not None and settings.storage_state.exists():
            context_kwargs["storage_state"] = str(settings.storage_state)
        context = await browser.new_context(**context_kwargs)
        page = await context.new_page()
        timeout_ms = settings.request_timeout_seconds * 1000
        page.set_default_timeout(timeout_ms)
        page.set_default_navigation_timeout(timeout_ms)
        await page.goto(url, wait_until=settings.wait_until)
        with contextlib.suppress(Exception):
            await page.locator("article[data-testid='tweet']").first.wait_for(
                state="attached",
                timeout=timeout_ms,
            )
        for _ in range(max(0, settings.max_scroll_steps)):
            await page.mouse.wheel(0, settings.viewport_height)
            await page.wait_for_timeout(750)
        html = await page.content()
        await context.close()
        await browser.close()
        return html


async def _browser_items_with_playwright(
    target: AcquisitionTarget,
    settings: _GenericUrlSettings,
):
    from playwright.async_api import async_playwright

    from research_x.adapters.playwright_adapter import _fetch_target

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=settings.headless)
        context_kwargs: dict[str, Any] = {
            "viewport": {"width": settings.viewport_width, "height": settings.viewport_height}
        }
        if settings.storage_state is not None and settings.storage_state.exists():
            context_kwargs["storage_state"] = str(settings.storage_state)
        context = await browser.new_context(**context_kwargs)
        page = await context.new_page()
        timeout_ms = settings.request_timeout_seconds * 1000
        page.set_default_timeout(timeout_ms)
        page.set_default_navigation_timeout(timeout_ms)
        items = await _fetch_target(page, target, settings)
        await context.close()
        await browser.close()
        return items


def _storage_state_cookies(path: Path | None) -> list[dict[str, Any]]:
    if path is None or not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    cookies = payload.get("cookies", [])
    return [cookie for cookie in cookies if isinstance(cookie, dict)]


def _outcome(
    adapter_id: str,
    target: AcquisitionTarget,
    started_at,
    items,
    metadata: dict[str, Any],
) -> FetchOutcome:
    return FetchOutcome(
        adapter_id=adapter_id,
        target=target,
        status=OutcomeStatus.OK if items else OutcomeStatus.EMPTY,
        started_at=started_at,
        finished_at=utc_now(),
        items=tuple(items),
        metadata=metadata,
    )


def _http_error(
    adapter_id: str,
    target: AcquisitionTarget,
    started_at,
    url: str,
    status_code: int,
    text: str,
) -> FetchOutcome:
    return FetchOutcome(
        adapter_id=adapter_id,
        target=target,
        status=OutcomeStatus.ERROR,
        started_at=started_at,
        finished_at=utc_now(),
        error_type="HTTPStatus",
        error_message=f"{url} returned HTTP {status_code}: {text[:300]}",
        metadata={"url": url, "http_status": status_code},
    )


def _error(
    adapter_id: str,
    target: AcquisitionTarget,
    started_at,
    error_type: str,
    message: str,
    url: str,
) -> FetchOutcome:
    return FetchOutcome(
        adapter_id=adapter_id,
        target=target,
        status=OutcomeStatus.ERROR,
        started_at=started_at,
        finished_at=utc_now(),
        error_type=error_type,
        error_message=message,
        metadata={"url": url},
    )


def _not_configured(
    adapter_id: str,
    target: AcquisitionTarget,
    started_at,
    dependency: str,
    message: str,
    exc: Exception,
) -> FetchOutcome:
    return FetchOutcome(
        adapter_id=adapter_id,
        target=target,
        status=OutcomeStatus.NOT_CONFIGURED,
        started_at=started_at,
        finished_at=utc_now(),
        error_type="MissingDependency",
        error_message=message,
        metadata={"dependency": dependency, "detail": str(exc)},
    )


def _env(config: AdapterConfig, option_name: str, default_env_name: str) -> str | None:
    env_name = str(config.options.get(option_name, default_env_name))
    value = os.environ.get(env_name)
    if value is None or value == "":
        return None
    return value


def _option_or_env(
    config: AdapterConfig,
    direct_option_name: str,
    env_option_name: str,
    default_env_name: str,
) -> str | None:
    direct_value = config.options.get(direct_option_name)
    if direct_value not in (None, ""):
        return str(direct_value)
    return _env(config, env_option_name, default_env_name)
