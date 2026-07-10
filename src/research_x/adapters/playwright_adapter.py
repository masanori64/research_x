from __future__ import annotations

import asyncio
import os
import re
from datetime import datetime
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


class PlaywrightAdapter:
    adapter_id = "playwright"

    def __init__(self, config: AdapterConfig) -> None:
        self.config = config

    def fetch(self, target: AcquisitionTarget) -> FetchOutcome:
        return asyncio.run(self._fetch(target))

    async def _fetch(self, target: AcquisitionTarget) -> FetchOutcome:
        started_at = utc_now()
        settings = _PlaywrightSettings.from_config(self.config)
        try:
            from playwright.async_api import TimeoutError as PlaywrightTimeoutError
            from playwright.async_api import async_playwright
        except ImportError as exc:
            return FetchOutcome(
                adapter_id=self.adapter_id,
                target=target,
                status=OutcomeStatus.NOT_CONFIGURED,
                started_at=started_at,
                finished_at=utc_now(),
                error_type="MissingDependency",
                error_message="Install playwright and browser binaries to enable this adapter.",
                metadata={"dependency": "playwright", "detail": str(exc)},
            )

        if not settings.storage_state.exists() and not settings.login_enabled:
            return FetchOutcome(
                adapter_id=self.adapter_id,
                target=target,
                status=OutcomeStatus.NOT_CONFIGURED,
                started_at=started_at,
                finished_at=utc_now(),
                error_type="MissingStorageState",
                error_message=(
                    "Playwright storage_state is missing. Run "
                    "`uv run python -m research_x auth playwright` first."
                ),
                metadata={"storage_state": str(settings.storage_state)},
            )

        try:
            async with async_playwright() as pw:
                browser = await pw.chromium.launch(headless=settings.headless)
                context_kwargs: dict[str, Any] = {"viewport": settings.viewport}
                if settings.storage_state.exists():
                    context_kwargs["storage_state"] = str(settings.storage_state)
                context = await browser.new_context(**context_kwargs)
                page = await context.new_page()
                page.set_default_timeout(settings.timeout_ms)
                page.set_default_navigation_timeout(settings.timeout_ms)

                if not settings.storage_state.exists() and settings.login_enabled:
                    await _login(page, context, settings)

                items = await _fetch_target(page, target, settings)
                await context.close()
                await browser.close()
        except PlaywrightTimeoutError as exc:
            return _error_outcome(
                target,
                started_at,
                "PlaywrightTimeout",
                str(exc),
                {"storage_state": str(settings.storage_state)},
            )
        except Exception as exc:  # noqa: BLE001 - browser adapters must be isolated.
            return _error_outcome(
                target,
                started_at,
                type(exc).__name__,
                str(exc),
                {"storage_state": str(settings.storage_state)},
            )

        return FetchOutcome(
            adapter_id=self.adapter_id,
            target=target,
            status=OutcomeStatus.OK if items else OutcomeStatus.EMPTY,
            started_at=started_at,
            finished_at=utc_now(),
            items=tuple(items),
            metadata={
                "library": "playwright",
                "storage_state": str(settings.storage_state),
                "headless": settings.headless,
            },
        )


class _PlaywrightSettings:
    def __init__(
        self,
        *,
        storage_state: Path,
        username: str | None,
        email: str | None,
        password: str | None,
        login_enabled: bool,
        headless: bool,
        timeout_ms: float,
        viewport: dict[str, int],
        env_prefix: str,
        max_scroll_steps: int,
        scroll_pause_ms: int,
    ) -> None:
        self.storage_state = storage_state
        self.username = username
        self.email = email
        self.password = password
        self.login_enabled = login_enabled
        self.headless = headless
        self.timeout_ms = timeout_ms
        self.viewport = viewport
        self.env_prefix = env_prefix
        self.max_scroll_steps = max_scroll_steps
        self.scroll_pause_ms = scroll_pause_ms

    @classmethod
    def from_config(cls, config: AdapterConfig) -> _PlaywrightSettings:
        env_prefix = str(config.options.get("env_prefix", "RESEARCH_X"))
        width = int(config.options.get("viewport_width", 1280))
        height = int(config.options.get("viewport_height", 900))
        return cls(
            storage_state=Path(
                str(config.options.get("storage_state", ".secrets/playwright_x_state.json"))
            ),
            username=_env(config, "username_env", f"{env_prefix}_X_USERNAME"),
            email=_env(config, "email_env", f"{env_prefix}_X_EMAIL"),
            password=_env(config, "password_env", f"{env_prefix}_X_PASSWORD"),
            login_enabled=bool(config.options.get("login", False)),
            headless=bool(config.options.get("headless", True)),
            timeout_ms=float(config.options.get("timeout_ms", 45000)),
            viewport={"width": width, "height": height},
            env_prefix=env_prefix,
            max_scroll_steps=int(config.options.get("max_scroll_steps", 3)),
            scroll_pause_ms=int(config.options.get("scroll_pause_ms", 1500)),
        )


async def _login(page: Any, context: Any, settings: _PlaywrightSettings) -> None:
    if not settings.username or not settings.password:
        raise RuntimeError(
            "Playwright login needs an existing storage_state file or env credentials."
        )
    settings.storage_state.parent.mkdir(parents=True, exist_ok=True)
    await page.goto("https://x.com/i/flow/login", wait_until="domcontentloaded")
    await _fill_first(
        page,
        ["input[autocomplete='username']", "input[name='text']"],
        settings.username,
    )
    await _click_button(page, "Next")
    await page.wait_for_timeout(2500)

    if not await _is_any_visible(page, ["input[name='password']", "input[type='password']"]):
        await _fill_first(page, ["input[name='text']"], settings.email or settings.username)
        await _click_button(page, "Next")
        await page.wait_for_timeout(2500)

    await _fill_first(page, ["input[name='password']", "input[type='password']"], settings.password)
    await _click_button(page, "Log in")
    await page.wait_for_load_state("domcontentloaded")
    await page.wait_for_timeout(5000)

    if await _is_visible(page, "input[name='text']"):
        raise RuntimeError("X login requested an additional verification code.")
    body_text = await page.locator("body").inner_text(timeout=5000)
    if "blocked" in body_text.lower() or "attention required" in body_text.lower():
        raise RuntimeError("X returned an access-control or challenge page during login.")
    await context.storage_state(path=str(settings.storage_state))


async def _fetch_target(
    page: Any,
    target: AcquisitionTarget,
    settings: _PlaywrightSettings,
) -> list[XItem]:
    wait_until = getattr(settings, "wait_until", "domcontentloaded")
    if target.kind == TargetKind.PROFILE:
        screen_name = _screen_name(target.value)
        await page.goto(f"https://x.com/{screen_name}", wait_until=wait_until)
        await _wait_for_tweet_articles(page, settings)
        return await _extract_profile_items(page, screen_name, target.limit, settings)
    if target.kind == TargetKind.URL:
        await page.goto(target.value, wait_until=wait_until)
        await _wait_for_tweet_articles(page, settings)
        return await _extract_profile_items(page, None, target.limit, settings)
    if target.kind == TargetKind.SEARCH:
        query = target.value.replace(" ", "%20")
        await page.goto(
            f"https://x.com/search?q={query}&src=typed_query&f=live",
            wait_until=wait_until,
        )
        await _wait_for_tweet_articles(page, settings)
        return await _extract_profile_items(page, None, target.limit, settings)
    if target.kind == TargetKind.BOOKMARKS:
        await page.goto("https://x.com/i/bookmarks", wait_until=wait_until)
        await _wait_for_tweet_articles(page, settings)
        items = await _extract_profile_items(page, None, target.limit, settings)
        return [_with_bookmark_metadata(item, index) for index, item in enumerate(items)]
    raise ValueError(f"unsupported target kind for playwright: {target.kind}")


async def _wait_for_tweet_articles(page: Any, settings: _PlaywrightSettings) -> None:
    try:
        await page.locator("article[data-testid='tweet']").first.wait_for(
            state="visible",
            timeout=settings.timeout_ms,
        )
    except Exception:
        # Empty/protected profiles and login pages are handled by returning an empty outcome.
        return


async def _extract_profile_items(
    page: Any,
    fallback_author: str | None,
    limit: int,
    settings: _PlaywrightSettings,
) -> list[XItem]:
    items: list[XItem] = []
    seen: set[str] = set()
    max_scroll_steps = max(1, int(getattr(settings, "max_scroll_steps", 3)))
    scroll_pause_ms = max(0, int(getattr(settings, "scroll_pause_ms", 1500)))
    for _ in range(max_scroll_steps):
        articles = page.locator("article[data-testid='tweet']")
        count = await articles.count()
        for index in range(count):
            item = await _article_to_item(articles.nth(index), fallback_author)
            if item is not None and item.source_id not in seen:
                seen.add(item.source_id)
                items.append(item)
                if len(items) >= limit:
                    return items
        await page.mouse.wheel(0, settings.viewport["height"])
        await page.wait_for_timeout(scroll_pause_ms)
    return items


def _with_bookmark_metadata(item: XItem, index: int) -> XItem:
    raw = dict(item.raw)
    raw["source_timeline"] = "bookmarks"
    raw["bookmark_root"] = True
    raw["bookmark_index"] = index
    return XItem(
        source_id=item.source_id,
        url=item.url,
        author=item.author,
        text=item.text,
        created_at=item.created_at,
        observed_at=item.observed_at,
        raw=raw,
    )


async def _article_to_item(article: Any, fallback_author: str | None) -> XItem | None:
    text = await article.inner_text(timeout=3000)
    hrefs = await article.locator("a[href*='/status/']").evaluate_all(
        "(els) => els.map((el) => el.getAttribute('href')).filter(Boolean)"
    )
    status_href = next((href for href in hrefs if "/status/" in href), None)
    source_id = _tweet_id(status_href) if status_href else _stable_source_id(text)
    author = _author_from_href(status_href) or fallback_author
    created_at = await _article_created_at(article)
    return XItem(
        source_id=source_id,
        url=_absolute_x_url(status_href),
        author=author,
        text=text,
        created_at=created_at,
        observed_at=utc_now(),
        raw={
            "href": status_href,
            "text": text,
            "created_at": created_at.isoformat() if created_at else None,
        },
    )


async def _article_created_at(article: Any) -> datetime | None:
    value = await article.locator("time").first.get_attribute("datetime")
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


async def _fill_first(page: Any, selectors: list[str], value: str) -> None:
    for selector in selectors:
        locator = page.locator(selector).first
        try:
            await locator.wait_for(state="visible", timeout=10000)
            await locator.click()
            await page.keyboard.press("Control+A")
            await page.keyboard.type(value, delay=25)
            return
        except Exception:  # noqa: BLE001 - continue through alternate selectors.
            continue
    raise RuntimeError(f"Could not find any input selector: {selectors}")


async def _is_visible(page: Any, selector: str) -> bool:
    locator = page.locator(selector).first
    return await locator.count() > 0 and await locator.is_visible()


async def _is_any_visible(page: Any, selectors: list[str]) -> bool:
    for selector in selectors:
        if await _is_visible(page, selector):
            return True
    return False


async def _click_button(page: Any, name: str) -> None:
    candidates = [
        page.get_by_role("button", name=name).first,
        page.locator(f"[role='button']:has-text('{name}')").first,
    ]
    for locator in candidates:
        try:
            await locator.wait_for(state="visible", timeout=10000)
            await locator.click()
            return
        except Exception:  # noqa: BLE001 - continue through alternate selectors.
            continue
    raise RuntimeError(f"Could not find button: {name}")


def _error_outcome(
    target: AcquisitionTarget,
    started_at,
    error_type: str,
    error_message: str,
    metadata: dict[str, Any],
) -> FetchOutcome:
    return FetchOutcome(
        adapter_id=PlaywrightAdapter.adapter_id,
        target=target,
        status=OutcomeStatus.ERROR,
        started_at=started_at,
        finished_at=utc_now(),
        error_type=error_type,
        error_message=error_message,
        metadata=metadata,
    )


def _env(config: AdapterConfig, option_name: str, default_env_name: str) -> str | None:
    env_name = str(config.options.get(option_name, default_env_name))
    value = os.environ.get(env_name)
    if value is None or value == "":
        return None
    return value


def _screen_name(value: str) -> str:
    value = value.strip()
    if value.startswith("@"):
        return value[1:]
    match = re.search(r"x\.com/([^/?#]+)", value)
    if match:
        return match.group(1)
    return value


def _tweet_id(value: str | None) -> str:
    if not value:
        return ""
    match = re.search(r"/status/(\d+)", value)
    if match:
        return match.group(1)
    if value.isdigit():
        return value
    return ""


def _author_from_href(value: str | None) -> str | None:
    if not value:
        return None
    match = re.search(r"/([^/]+)/status/\d+", value)
    if match:
        return match.group(1)
    return None


def _absolute_x_url(value: str | None) -> str | None:
    if value and value.startswith("/"):
        return f"https://x.com{value}"
    return value


def _stable_source_id(value: str) -> str:
    return str(abs(hash(value)))
