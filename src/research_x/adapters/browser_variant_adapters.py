from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from research_x.adapters.playwright_adapter import (
    _ensure_windows_playwright_event_loop_policy,
    _fetch_target,
)
from research_x.contracts import (
    AcquisitionTarget,
    AdapterConfig,
    FetchOutcome,
    OutcomeStatus,
    utc_now,
)

_SUPPRESS_PAGE_ERRORS_SCRIPT = """
window.addEventListener('error', event => event.preventDefault(), true);
window.addEventListener('unhandledrejection', event => event.preventDefault(), true);
"""


class CamoufoxAdapter:
    adapter_id = "camoufox"

    def __init__(self, config: AdapterConfig) -> None:
        self.config = config

    def fetch(self, target: AcquisitionTarget) -> FetchOutcome:
        _ensure_windows_playwright_event_loop_policy()
        runner = _BrowserVariantRunner(self.adapter_id, "camoufox", self.config)
        return asyncio.run(runner.fetch(target))


class PatchrightAdapter:
    adapter_id = "patchright"

    def __init__(self, config: AdapterConfig) -> None:
        self.config = config

    def fetch(self, target: AcquisitionTarget) -> FetchOutcome:
        _ensure_windows_playwright_event_loop_policy()
        runner = _BrowserVariantRunner(self.adapter_id, "patchright", self.config)
        return asyncio.run(runner.fetch(target))


class RebrowserPlaywrightAdapter:
    adapter_id = "rebrowser_playwright"

    def __init__(self, config: AdapterConfig) -> None:
        self.config = config

    def fetch(self, target: AcquisitionTarget) -> FetchOutcome:
        _ensure_windows_playwright_event_loop_policy()
        runner = _BrowserVariantRunner(self.adapter_id, "rebrowser_playwright", self.config)
        return asyncio.run(runner.fetch(target))


class _BrowserVariantRunner:
    def __init__(self, adapter_id: str, library: str, config: AdapterConfig) -> None:
        self.adapter_id = adapter_id
        self.library = library
        self.config = config

    async def fetch(self, target: AcquisitionTarget) -> FetchOutcome:
        started_at = utc_now()
        settings = _BrowserVariantSettings.from_config(self.config)
        if settings.require_storage_state and not settings.storage_state.exists():
            return FetchOutcome(
                adapter_id=self.adapter_id,
                target=target,
                status=OutcomeStatus.NOT_CONFIGURED,
                started_at=started_at,
                finished_at=utc_now(),
                error_type="MissingStorageState",
                error_message=(
                    f"{self.adapter_id} needs an authorized Playwright storage_state file."
                ),
                metadata={"storage_state": str(settings.storage_state), "library": self.library},
            )

        try:
            if self.library == "camoufox":
                items = await self._fetch_with_camoufox(target, settings)
            elif self.library == "patchright":
                items = await self._fetch_with_playwright_variant(
                    "patchright.async_api",
                    target,
                    settings,
                )
            elif self.library == "rebrowser_playwright":
                items = await self._fetch_with_playwright_variant(
                    "rebrowser_playwright.async_api",
                    target,
                    settings,
                )
            else:
                raise RuntimeError(f"unknown browser variant library: {self.library}")
        except ImportError as exc:
            return FetchOutcome(
                adapter_id=self.adapter_id,
                target=target,
                status=OutcomeStatus.NOT_CONFIGURED,
                started_at=started_at,
                finished_at=utc_now(),
                error_type="MissingDependency",
                error_message=f"Install {self.library} to enable this adapter.",
                metadata={"dependency": self.library, "detail": str(exc)},
            )
        except Exception as exc:  # noqa: BLE001 - browser providers are isolated.
            return FetchOutcome(
                adapter_id=self.adapter_id,
                target=target,
                status=OutcomeStatus.ERROR,
                started_at=started_at,
                finished_at=utc_now(),
                error_type=type(exc).__name__,
                error_message=str(exc),
                metadata={
                    "library": self.library,
                    "storage_state": str(settings.storage_state),
                    "headless": settings.headless,
                },
            )

        return FetchOutcome(
            adapter_id=self.adapter_id,
            target=target,
            status=OutcomeStatus.OK if items else OutcomeStatus.EMPTY,
            started_at=started_at,
            finished_at=utc_now(),
            items=tuple(items),
            metadata={
                "library": self.library,
                "storage_state": str(settings.storage_state),
                "headless": settings.headless,
            },
        )

    async def _fetch_with_playwright_variant(
        self,
        module_name: str,
        target: AcquisitionTarget,
        settings: _BrowserVariantSettings,
    ):
        module = __import__(module_name, fromlist=["async_playwright"])
        async_playwright = module.async_playwright
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=settings.headless)
            context = await browser.new_context(**settings.context_kwargs())
            page = await context.new_page()
            page.set_default_timeout(settings.timeout_ms)
            page.set_default_navigation_timeout(settings.timeout_ms)
            items = await _fetch_target(page, target, settings)
            await context.close()
            await browser.close()
            return items

    async def _fetch_with_camoufox(
        self,
        target: AcquisitionTarget,
        settings: _BrowserVariantSettings,
    ):
        from camoufox import AsyncCamoufox
        from camoufox.addons import DefaultAddons

        _patch_playwright_pageerror_location_guard()
        items = []
        try:
            async with AsyncCamoufox(
                headless=settings.headless,
                exclude_addons=[DefaultAddons.UBO],
            ) as browser_or_context:
                if hasattr(browser_or_context, "new_context"):
                    context = await browser_or_context.new_context(**settings.context_kwargs())
                    close_context = True
                else:
                    context = browser_or_context
                    close_context = False
                await context.add_init_script(_SUPPRESS_PAGE_ERRORS_SCRIPT)
                page = await context.new_page()
                page.set_default_timeout(settings.timeout_ms)
                page.set_default_navigation_timeout(settings.timeout_ms)
                items = await _fetch_target(page, target, settings)
                if close_context:
                    await context.close()
        except Exception:
            if items:
                return items
            raise
        return items


class _BrowserVariantSettings:
    def __init__(
        self,
        *,
        storage_state: Path,
        require_storage_state: bool,
        headless: bool,
        timeout_ms: float,
        viewport: dict[str, int],
        wait_until: str,
    ) -> None:
        self.storage_state = storage_state
        self.require_storage_state = require_storage_state
        self.headless = headless
        self.timeout_ms = timeout_ms
        self.viewport = viewport
        self.wait_until = wait_until

    @classmethod
    def from_config(cls, config: AdapterConfig) -> _BrowserVariantSettings:
        width = int(config.options.get("viewport_width", 1280))
        height = int(config.options.get("viewport_height", 900))
        return cls(
            storage_state=Path(
                str(config.options.get("storage_state", ".secrets/playwright_x_state.json"))
            ),
            require_storage_state=bool(config.options.get("require_storage_state", True)),
            headless=bool(config.options.get("headless", True)),
            timeout_ms=float(config.options.get("timeout_ms", 45000)),
            viewport={"width": width, "height": height},
            wait_until=str(config.options.get("wait_until", "domcontentloaded")),
        )

    def context_kwargs(self) -> dict[str, Any]:
        kwargs: dict[str, Any] = {"viewport": self.viewport}
        if self.storage_state.exists():
            kwargs["storage_state"] = str(self.storage_state)
        return kwargs


def _patch_playwright_pageerror_location_guard() -> bool:
    try:
        import playwright
    except ImportError:
        return False

    path = Path(playwright.__file__).parent / "driver" / "package" / "lib" / "coreBundle.js"
    if not path.exists():
        return False
    old = """location: {
              url: pageError.location.url,
              line: pageError.location.lineNumber,
              column: pageError.location.columnNumber
            }"""
    new = """location: {
              url: pageError.location ? pageError.location.url : "",
              line: pageError.location ? pageError.location.lineNumber : 0,
              column: pageError.location ? pageError.location.columnNumber : 0
            }"""
    text = path.read_text(encoding="utf-8")
    if new in text:
        return True
    if old not in text:
        return False
    backup = path.with_suffix(path.suffix + ".research_x.bak")
    if not backup.exists():
        backup.write_text(text, encoding="utf-8")
    path.write_text(text.replace(old, new), encoding="utf-8")
    return True
