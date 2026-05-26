from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import os
import re
import struct
import subprocess
import time
from contextlib import suppress
from pathlib import Path
from typing import Any


def capture_playwright_storage_state(
    *,
    storage_state: str | Path,
    user_data_dir: str | Path = ".secrets/playwright_profile",
    channel: str | None = None,
    executable_path: str | Path | None = None,
    start_url: str = "https://x.com",
    timeout_seconds: float = 900,
) -> bool:
    return asyncio.run(
        _capture_playwright_storage_state(
            storage_state=Path(storage_state),
            user_data_dir=Path(user_data_dir),
            channel=channel,
            executable_path=Path(executable_path) if executable_path else None,
            start_url=start_url,
            timeout_seconds=timeout_seconds,
        )
    )


def storage_state_has_x_auth_cookies(storage_state: str | Path) -> bool:
    path = Path(storage_state)
    if not path.exists():
        return False
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    names = {
        cookie.get("name")
        for cookie in payload.get("cookies", [])
        if isinstance(cookie, dict)
        and str(cookie.get("domain", "")).endswith(("x.com", "twitter.com"))
    }
    return {"auth_token", "ct0"}.issubset(names)


def capture_storage_state_with_credentials(
    *,
    storage_state: str | Path,
    user_data_dir: str | Path = ".secrets/playwright_profile",
    username_env: str = "RESEARCH_X_X_USERNAME",
    password_env: str = "RESEARCH_X_X_PASSWORD",
    email_or_phone_env: str = "RESEARCH_X_X_EMAIL_OR_PHONE",
    verification_code_env: str = "RESEARCH_X_X_VERIFICATION_CODE",
    totp_secret_env: str = "RESEARCH_X_X_TOTP_SECRET",
    channel: str | None = None,
    executable_path: str | Path | None = None,
    start_url: str = "https://x.com/i/flow/login",
    headless: bool = True,
    user_agent: str | None = None,
    timeout_seconds: float = 180,
) -> bool:
    username = os.environ.get(username_env)
    password = os.environ.get(password_env)
    if not username or not password:
        missing = [
            name
            for name, value in ((username_env, username), (password_env, password))
            if not value
        ]
        raise RuntimeError("Missing credential env values: " + ", ".join(missing))

    try:
        return asyncio.run(
            _capture_storage_state_with_credentials(
                storage_state=Path(storage_state),
                user_data_dir=Path(user_data_dir),
                username=username,
                password=password,
                email_or_phone=os.environ.get(email_or_phone_env),
                verification_code=os.environ.get(verification_code_env),
                totp_secret=os.environ.get(totp_secret_env),
                channel=channel,
                executable_path=Path(executable_path) if executable_path else None,
                start_url=start_url,
                headless=headless,
                user_agent=user_agent,
                timeout_seconds=timeout_seconds,
            )
        )
    except RuntimeError as exc:
        print(f"Automated X credential login failed: {exc}")
        return False


def capture_storage_state_with_system_browser_credentials(
    *,
    storage_state: str | Path,
    user_data_dir: str | Path = ".secrets/system_browser_profile",
    username_env: str = "RESEARCH_X_X_USERNAME",
    password_env: str = "RESEARCH_X_X_PASSWORD",
    email_or_phone_env: str = "RESEARCH_X_X_EMAIL_OR_PHONE",
    verification_code_env: str = "RESEARCH_X_X_VERIFICATION_CODE",
    totp_secret_env: str = "RESEARCH_X_X_TOTP_SECRET",
    browser: str = "msedge",
    executable_path: str | Path | None = None,
    start_url: str = "https://x.com/i/flow/login",
    debugging_port: int = 9225,
    disable_extensions: bool = True,
    timeout_seconds: float = 180,
) -> bool:
    username = os.environ.get(username_env)
    password = os.environ.get(password_env)
    if not username or not password:
        missing = [
            name
            for name, value in ((username_env, username), (password_env, password))
            if not value
        ]
        raise RuntimeError("Missing credential env values: " + ", ".join(missing))

    try:
        return asyncio.run(
            _capture_storage_state_with_system_browser_credentials(
                storage_state=Path(storage_state),
                user_data_dir=Path(user_data_dir),
                username=username,
                password=password,
                email_or_phone=os.environ.get(email_or_phone_env),
                verification_code=os.environ.get(verification_code_env),
                totp_secret=os.environ.get(totp_secret_env),
                browser=browser,
                executable_path=Path(executable_path) if executable_path else None,
                start_url=start_url,
                debugging_port=debugging_port,
                disable_extensions=disable_extensions,
                timeout_seconds=timeout_seconds,
            )
        )
    except RuntimeError as exc:
        print(f"System browser X credential login failed: {exc}")
        return False


def capture_storage_state_auto(
    *,
    storage_state: str | Path,
    user_data_dir: str | Path = ".secrets/playwright_profile",
    username_env: str = "RESEARCH_X_X_USERNAME",
    password_env: str = "RESEARCH_X_X_PASSWORD",
    email_or_phone_env: str = "RESEARCH_X_X_EMAIL_OR_PHONE",
    verification_code_env: str = "RESEARCH_X_X_VERIFICATION_CODE",
    totp_secret_env: str = "RESEARCH_X_X_TOTP_SECRET",
    auth_token_env: str = "RESEARCH_X_X_AUTH_TOKEN",
    ct0_env: str = "RESEARCH_X_X_CT0",
    endpoint_url: str = "http://localhost:9222",
    try_cdp: bool = True,
    cdp_timeout_seconds: float = 3,
    try_system_browser: bool = True,
    system_browser: str = "msedge",
    system_browser_debugging_port: int = 9225,
    system_browser_disable_extensions: bool = True,
    channel: str | None = None,
    executable_path: str | Path | None = None,
    start_url: str = "https://x.com/i/flow/login",
    headless: bool = True,
    user_agent: str | None = None,
    timeout_seconds: float = 180,
) -> bool:
    attempts: list[dict[str, Any]] = []
    storage_state_path = Path(storage_state)
    if storage_state_has_x_auth_cookies(storage_state_path):
        print(f"Existing Playwright storage state is usable: {storage_state_path}")
        return True

    if os.environ.get(auth_token_env) and os.environ.get(ct0_env):
        try:
            write_storage_state_from_cookie_env(
                storage_state=storage_state_path,
                auth_token_env=auth_token_env,
                ct0_env=ct0_env,
            )
            attempts.append({"route": "cookie_env", "status": "ok"})
            return True
        except Exception as exc:  # noqa: BLE001 - continue to next auth route.
            attempts.append(
                {"route": "cookie_env", "status": "error", "error": _safe_error(exc)}
            )
    else:
        attempts.append({"route": "cookie_env", "status": "skipped_missing_env"})

    ok = capture_storage_state_from_persistent_profile(
        storage_state=storage_state_path,
        user_data_dir=user_data_dir,
        channel=channel,
        executable_path=executable_path,
    )
    attempts.append({"route": "persistent_profile", "status": "ok" if ok else "failed"})
    if ok:
        return True

    if try_cdp:
        ok = capture_storage_state_from_cdp(
            storage_state=storage_state_path,
            endpoint_url=endpoint_url,
            timeout_seconds=cdp_timeout_seconds,
        )
        attempts.append({"route": "cdp", "status": "ok" if ok else "failed"})
        if ok:
            return True

    if os.environ.get(username_env) and os.environ.get(password_env):
        if try_system_browser:
            ok = capture_storage_state_with_system_browser_credentials(
                storage_state=storage_state_path,
                user_data_dir=user_data_dir,
                username_env=username_env,
                password_env=password_env,
                email_or_phone_env=email_or_phone_env,
                verification_code_env=verification_code_env,
                totp_secret_env=totp_secret_env,
                browser=system_browser,
                executable_path=executable_path,
                start_url=start_url,
                debugging_port=system_browser_debugging_port,
                disable_extensions=system_browser_disable_extensions,
                timeout_seconds=timeout_seconds,
            )
            attempts.append(
                {
                    "route": "system_browser_credentials",
                    "status": "ok" if ok else "failed",
                }
            )
            if ok:
                return True

        ok = capture_storage_state_with_credentials(
            storage_state=storage_state_path,
            user_data_dir=user_data_dir,
            username_env=username_env,
            password_env=password_env,
            email_or_phone_env=email_or_phone_env,
            verification_code_env=verification_code_env,
            totp_secret_env=totp_secret_env,
            channel=channel,
            executable_path=executable_path,
            start_url=start_url,
            headless=headless,
            user_agent=user_agent,
            timeout_seconds=timeout_seconds,
        )
        attempts.append({"route": "credentials", "status": "ok" if ok else "failed"})
        if ok:
            return True
        if user_agent is None:
            for label, fallback_user_agent in _USER_AGENT_FALLBACKS:
                ok = capture_storage_state_with_credentials(
                    storage_state=storage_state_path,
                    user_data_dir=user_data_dir,
                    username_env=username_env,
                    password_env=password_env,
                    email_or_phone_env=email_or_phone_env,
                    verification_code_env=verification_code_env,
                    totp_secret_env=totp_secret_env,
                    channel=channel,
                    executable_path=executable_path,
                    start_url=start_url,
                    headless=headless,
                    user_agent=fallback_user_agent,
                    timeout_seconds=timeout_seconds,
                )
                attempts.append(
                    {
                        "route": f"credentials_user_agent:{label}",
                        "status": "ok" if ok else "failed",
                    }
                )
                if ok:
                    return True
    else:
        attempts.append({"route": "credentials", "status": "skipped_missing_env"})

    print("No automatic X auth route produced a valid storage state.")
    print(json.dumps(attempts, ensure_ascii=False, indent=2, sort_keys=True))
    return False


async def _capture_playwright_storage_state(
    *,
    storage_state: Path,
    user_data_dir: Path,
    channel: str | None,
    executable_path: Path | None,
    start_url: str,
    timeout_seconds: float,
) -> bool:
    from playwright.async_api import Error as PlaywrightError
    from playwright.async_api import async_playwright

    storage_state.parent.mkdir(parents=True, exist_ok=True)
    user_data_dir.mkdir(parents=True, exist_ok=True)
    async with async_playwright() as pw:
        context = await pw.chromium.launch_persistent_context(
            str(user_data_dir),
            channel=channel,
            executable_path=str(executable_path) if executable_path else None,
            headless=False,
            viewport={"width": 1280, "height": 900},
        )
        page = context.pages[0] if context.pages else await context.new_page()
        await _safe_goto(page, start_url)

        print("Visible Chromium is open. Log in to X manually in that window.")
        print(f"Waiting up to {int(timeout_seconds)} seconds for auth cookies...")
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            try:
                if await _has_x_auth_cookies(context):
                    await context.storage_state(path=str(storage_state))
                    await context.close()
                    print(f"Saved Playwright storage state to {storage_state}")
                    return True
                await page.wait_for_timeout(2000)
            except PlaywrightError:
                return await _export_from_persistent_profile(
                    pw=pw,
                    user_data_dir=user_data_dir,
                    channel=channel,
                    executable_path=executable_path,
                    storage_state=storage_state,
                )

        await context.close()
        print("Timed out before X auth cookies were detected.")
        return False


async def _capture_storage_state_with_credentials(
    *,
    storage_state: Path,
    user_data_dir: Path,
    username: str,
    password: str,
    email_or_phone: str | None,
    verification_code: str | None,
    totp_secret: str | None,
    channel: str | None,
    executable_path: Path | None,
    start_url: str,
    headless: bool,
    user_agent: str | None,
    timeout_seconds: float,
) -> bool:
    from playwright.async_api import async_playwright

    storage_state.parent.mkdir(parents=True, exist_ok=True)
    user_data_dir.mkdir(parents=True, exist_ok=True)
    async with async_playwright() as pw:
        context = await pw.chromium.launch_persistent_context(
            str(user_data_dir),
            channel=channel,
            executable_path=str(executable_path) if executable_path else None,
            headless=headless,
            viewport={"width": 1280, "height": 900},
            user_agent=user_agent,
        )
        try:
            page = context.pages[0] if context.pages else await context.new_page()
            try:
                return await _drive_x_credential_login(
                    context=context,
                    page=page,
                    storage_state=storage_state,
                    start_url=start_url,
                    username=username,
                    password=password,
                    email_or_phone=email_or_phone,
                    verification_code=verification_code,
                    totp_secret=totp_secret,
                    timeout_seconds=timeout_seconds,
                )
            except Exception as exc:
                await _write_auth_diagnostics(
                    page,
                    diagnostics_dir=storage_state.parent / "auth_diagnostics",
                    reason=_safe_error(exc),
                )
                raise
        finally:
            await context.close()


async def _capture_storage_state_with_system_browser_credentials(
    *,
    storage_state: Path,
    user_data_dir: Path,
    username: str,
    password: str,
    email_or_phone: str | None,
    verification_code: str | None,
    totp_secret: str | None,
    browser: str,
    executable_path: Path | None,
    start_url: str,
    debugging_port: int,
    disable_extensions: bool,
    timeout_seconds: float,
) -> bool:
    from playwright.async_api import async_playwright

    executable = executable_path or _system_browser_executable(browser)
    storage_state.parent.mkdir(parents=True, exist_ok=True)
    user_data_dir.mkdir(parents=True, exist_ok=True)
    args = [
        str(executable),
        f"--remote-debugging-port={debugging_port}",
        f"--user-data-dir={user_data_dir.resolve()}",
        "--no-first-run",
        "--no-default-browser-check",
    ]
    if disable_extensions:
        args.append("--disable-extensions")
    args.append(start_url)
    process = subprocess.Popen(args)  # noqa: S603
    try:
        async with async_playwright() as pw:
            browser_client = None
            endpoint = f"http://127.0.0.1:{debugging_port}"
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline:
                try:
                    browser_client = await pw.chromium.connect_over_cdp(endpoint)
                    break
                except Exception:
                    await asyncio.sleep(1)
            if browser_client is None:
                raise RuntimeError(f"Could not connect to system browser CDP at {endpoint}")
            try:
                context = (
                    browser_client.contexts[0]
                    if browser_client.contexts
                    else await browser_client.new_context()
                )
                page = await _x_login_page(context, start_url)
                try:
                    return await _drive_x_credential_login(
                        context=context,
                        page=page,
                        storage_state=storage_state,
                        start_url=start_url,
                        username=username,
                        password=password,
                        email_or_phone=email_or_phone,
                        verification_code=verification_code,
                        totp_secret=totp_secret,
                        timeout_seconds=timeout_seconds,
                    )
                except Exception as exc:
                    await _write_auth_diagnostics(
                        page,
                        diagnostics_dir=storage_state.parent / "auth_diagnostics",
                        reason=_safe_error(exc),
                    )
                    raise
            finally:
                await browser_client.close()
    finally:
        with suppress(Exception):
            process.terminate()


async def _drive_x_credential_login(
    *,
    context,
    page,
    storage_state: Path,
    start_url: str,
    username: str,
    password: str,
    email_or_phone: str | None,
    verification_code: str | None,
    totp_secret: str | None,
    timeout_seconds: float,
) -> bool:
    await _safe_goto(page, start_url)
    await _close_non_x_pages(context, keep=page)
    if await _wait_for_x_auth_cookies(context, 5):
        await context.storage_state(path=str(storage_state))
        print(f"Saved Playwright storage state to {storage_state}")
        return True

    await _set_first_visible_input(page, _USERNAME_SELECTORS, username, "username")
    await _submit_username_and_wait(page)
    await _close_non_x_pages(context, keep=page)

    if await _wait_for_x_auth_cookies(context, 2):
        await context.storage_state(path=str(storage_state))
        print(f"Saved Playwright storage state to {storage_state}")
        return True

    if not await _has_visible_locator(page, _PASSWORD_SELECTORS):
        challenge_input = await _first_visible_locator(page, _TEXT_CHALLENGE_SELECTORS, 5)
        if challenge_input is not None:
            if not email_or_phone:
                raise RuntimeError(
                    "X requested email/phone confirmation. Set RESEARCH_X_X_EMAIL_OR_PHONE."
                )
            await _set_locator_input(page, challenge_input, email_or_phone, "challenge")
            await _click_named_button(page, _NEXT_BUTTON_PATTERNS)
            await page.wait_for_timeout(2500)
            await _close_non_x_pages(context, keep=page)

    await _set_first_visible_input(page, _PASSWORD_SELECTORS, password, "password")
    await _click_named_button(page, _LOGIN_BUTTON_PATTERNS)
    await page.wait_for_timeout(2500)
    await _close_non_x_pages(context, keep=page)

    code = verification_code or (_totp_code(totp_secret) if totp_secret else None)
    if await _needs_verification_code(page):
        if not code:
            raise RuntimeError(
                "X requested a verification code. Set RESEARCH_X_X_VERIFICATION_CODE "
                "or RESEARCH_X_X_TOTP_SECRET."
            )
        await _set_first_visible_input(page, _TEXT_CHALLENGE_SELECTORS, code, "verification")
        await _click_named_button(page, _NEXT_BUTTON_PATTERNS + _LOGIN_BUTTON_PATTERNS)
        await _close_non_x_pages(context, keep=page)

    await _raise_if_hard_challenge(page)
    if not await _wait_for_x_auth_cookies(context, timeout_seconds):
        await _raise_if_hard_challenge(page)
        raise RuntimeError("Timed out before X auth cookies were detected.")

    await context.storage_state(path=str(storage_state))
    print(f"Saved Playwright storage state to {storage_state}")
    return True


async def _x_login_page(context, start_url: str):
    x_page = None
    for page in context.pages:
        if "x.com" in page.url or "twitter.com" in page.url:
            x_page = page
            break
    if x_page is None:
        x_page = await context.new_page()
    await _close_non_x_pages(context, keep=x_page)
    await _safe_goto(x_page, start_url)
    return x_page


async def _close_non_x_pages(context, *, keep) -> None:
    for page in list(context.pages):
        if page is keep:
            continue
        if "x.com" in page.url or "twitter.com" in page.url:
            continue
        with suppress(Exception):
            await page.close()


async def _export_from_persistent_profile(
    *,
    pw,
    user_data_dir: Path,
    channel: str | None,
    executable_path: Path | None,
    storage_state: Path,
) -> bool:
    context = None
    try:
        context = await pw.chromium.launch_persistent_context(
            str(user_data_dir),
            channel=channel,
            executable_path=str(executable_path) if executable_path else None,
            headless=True,
            viewport={"width": 1280, "height": 900},
        )
        if await _has_x_auth_cookies(context):
            await context.storage_state(path=str(storage_state))
            await context.close()
            print(f"Saved Playwright storage state to {storage_state}")
            return True
    except Exception as exc:  # noqa: BLE001 - best-effort export after manual close.
        print(f"Browser closed before auth cookies could be saved: {type(exc).__name__}: {exc}")
        return False
    finally:
        if context is not None:
            with suppress(Exception):
                await context.close()
    print("Browser closed before X auth cookies were detected.")
    return False


def capture_storage_state_from_cdp(
    *,
    storage_state: str | Path,
    endpoint_url: str = "http://localhost:9222",
    timeout_seconds: float = 900,
) -> bool:
    return asyncio.run(
        _poll_storage_state_from_cdp(
            storage_state=Path(storage_state),
            endpoint_url=endpoint_url,
            timeout_seconds=timeout_seconds,
        )
    )


def capture_storage_state_from_persistent_profile(
    *,
    storage_state: str | Path,
    user_data_dir: str | Path = ".secrets/playwright_profile",
    channel: str | None = None,
    executable_path: str | Path | None = None,
) -> bool:
    return asyncio.run(
        _capture_storage_state_from_persistent_profile(
            storage_state=Path(storage_state),
            user_data_dir=Path(user_data_dir),
            channel=channel,
            executable_path=Path(executable_path) if executable_path else None,
        )
    )


async def _capture_storage_state_from_persistent_profile(
    *,
    storage_state: Path,
    user_data_dir: Path,
    channel: str | None,
    executable_path: Path | None,
) -> bool:
    if not user_data_dir.exists():
        return False
    from playwright.async_api import async_playwright

    storage_state.parent.mkdir(parents=True, exist_ok=True)
    async with async_playwright() as pw:
        return await _export_from_persistent_profile(
            pw=pw,
            user_data_dir=user_data_dir,
            channel=channel,
            executable_path=executable_path,
            storage_state=storage_state,
        )


async def _poll_storage_state_from_cdp(
    *,
    storage_state: Path,
    endpoint_url: str,
    timeout_seconds: float,
) -> bool:
    deadline = time.monotonic() + timeout_seconds
    last_error: str | None = None
    while True:
        try:
            if await _capture_storage_state_from_cdp(
                storage_state=storage_state,
                endpoint_url=endpoint_url,
            ):
                return True
        except Exception as exc:  # noqa: BLE001 - retry until timeout for interactive login.
            last_error = f"{type(exc).__name__}: {exc}"
        if time.monotonic() >= deadline:
            if last_error:
                print(f"Could not connect to CDP endpoint {endpoint_url}: {last_error}")
            else:
                print("Timed out before connected browser exposed X auth cookies.")
            return False
        await asyncio.sleep(2)


async def _capture_storage_state_from_cdp(*, storage_state: Path, endpoint_url: str) -> bool:
    from playwright.async_api import async_playwright

    storage_state.parent.mkdir(parents=True, exist_ok=True)
    async with async_playwright() as pw:
        browser = await pw.chromium.connect_over_cdp(endpoint_url)
        try:
            context = browser.contexts[0] if browser.contexts else await browser.new_context()
            if not context.pages:
                await context.new_page()
            if not await _has_x_auth_cookies(context):
                print("Connected browser does not contain X auth cookies.")
                return False
            await context.storage_state(path=str(storage_state))
            print(f"Saved Playwright storage state to {storage_state}")
            return True
        finally:
            await browser.close()


async def _safe_goto(page, url: str) -> None:
    try:
        await page.goto(url, wait_until="domcontentloaded")
    except Exception as exc:  # noqa: BLE001 - user can still navigate manually.
        print(
            "Initial navigation failed; navigate manually if needed: "
            f"{type(exc).__name__}: {exc}"
        )


async def _wait_for_x_auth_cookies(context, timeout_seconds: float) -> bool:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if await _has_x_auth_cookies(context):
            return True
        await asyncio.sleep(0.5)
    return await _has_x_auth_cookies(context)


async def _has_x_auth_cookies(context) -> bool:
    cookies = await context.cookies("https://x.com")
    names = {cookie.get("name") for cookie in cookies}
    return {"auth_token", "ct0"}.issubset(names)


async def _first_visible_locator(page, selectors: tuple[str, ...], timeout_seconds: float):
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        for selector in selectors:
            locator = page.locator(selector).first
            try:
                if (
                    await locator.count()
                    and await locator.is_visible(timeout=300)
                    and await _is_actionable_login_field(locator)
                ):
                    return locator
            except Exception:  # noqa: BLE001 - try the next selector.
                continue
        await page.wait_for_timeout(250)
    return None


async def _has_visible_locator(page, selectors: tuple[str, ...]) -> bool:
    return await _first_visible_locator(page, selectors, 0.5) is not None


async def _fill_first_visible(
    page,
    selectors: tuple[str, ...],
    value: str,
    description: str,
) -> None:
    locator = await _first_visible_locator(page, selectors, 12)
    if locator is None:
        await _raise_if_hard_challenge(page)
        raise RuntimeError(f"Could not find visible X login {description} field.")
    await locator.fill(value)


async def _set_first_visible_input(
    page,
    selectors: tuple[str, ...],
    value: str,
    description: str,
) -> None:
    locator = await _first_visible_locator(page, selectors, 12)
    if locator is None:
        await _raise_if_hard_challenge(page)
        raise RuntimeError(f"Could not find visible X login {description} field.")
    await _set_locator_input(page, locator, value, description)


async def _set_locator_input(page, locator, value: str, description: str = "text") -> None:
    try:
        await locator.click(timeout=5000)
    except Exception:  # noqa: BLE001 - fallback for login fields covered by animated shells.
        await locator.evaluate("(element) => element.focus()")
    await locator.fill("")
    await locator.press_sequentially(value, delay=45)
    await page.wait_for_timeout(300)
    if await _locator_value(locator) == value:
        return
    await locator.evaluate(
        """
        (element, text) => {
          element.focus();
          element.value = text;
          element.dispatchEvent(new InputEvent('input', {
            bubbles: true,
            cancelable: true,
            inputType: 'insertText',
            data: text
          }));
          element.dispatchEvent(new Event('change', { bubbles: true }));
        }
        """,
        value,
    )
    await page.wait_for_timeout(300)
    if await _locator_value(locator) != value:
        raise RuntimeError(f"Could not set X login {description} field value.")


async def _is_actionable_login_field(locator) -> bool:
    return bool(
        await locator.evaluate(
            """
            (element) => {
              const style = window.getComputedStyle(element);
              const rect = element.getBoundingClientRect();
              return element.getAttribute('aria-hidden') !== 'true'
                && element.tabIndex !== -1
                && style.visibility !== 'hidden'
                && style.display !== 'none'
                && rect.width > 0
                && rect.height > 0;
            }
            """
        )
    )


async def _locator_value(locator) -> str | None:
    try:
        return await locator.input_value(timeout=1000)
    except Exception:  # noqa: BLE001 - non-input locators are handled by caller diagnostics.
        return None


async def _submit_username_and_wait(page) -> None:
    actions = (
        lambda: _click_named_button(page, _NEXT_BUTTON_PATTERNS),
        lambda: page.keyboard.press("Enter"),
        lambda: _click_text_button_with_dispatch(page, _NEXT_BUTTON_PATTERNS),
    )
    for action in actions:
        await action()
        if await _wait_for_post_username_state(page, timeout_seconds=8):
            return
    body = await _body_text(page)
    if _looks_like_initial_login_screen(body):
        raise RuntimeError("X did not advance from the username screen after submitting.")


async def _wait_for_post_username_state(page, *, timeout_seconds: float) -> bool:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        body = await _body_text(page)
        if await _has_visible_locator(page, _PASSWORD_SELECTORS):
            return True
        if not _looks_like_initial_login_screen(body):
            return True
        if any(term in body.lower() for term in _HARD_CHALLENGE_TERMS):
            return True
        await page.wait_for_timeout(500)
    return False


async def _click_named_button(page, patterns: tuple[str, ...]) -> None:
    for pattern in patterns:
        locator = page.get_by_role("button", name=re.compile(pattern, re.IGNORECASE)).first
        try:
            if await locator.count() and await locator.is_visible(timeout=500):
                await locator.click()
                return
        except Exception:  # noqa: BLE001 - try fallback locators.
            continue
    for text in _pattern_texts(patterns):
        selectors = (
            f"div[role='button']:has-text('{text}')",
            f"button:has-text('{text}')",
            f"text={text}",
        )
        for selector in selectors:
            locator = page.locator(selector).first
            try:
                if await locator.count() and await locator.is_visible(timeout=300):
                    await locator.click()
                    return
            except Exception:  # noqa: BLE001 - press enter as final fallback.
                continue
    await page.keyboard.press("Enter")


async def _click_text_button_with_dispatch(page, patterns: tuple[str, ...]) -> None:
    for text in _pattern_texts(patterns):
        locator = page.locator(f"div[role='button']:has-text('{text}')").first
        try:
            if await locator.count():
                await locator.dispatch_event("click")
                return
        except Exception:  # noqa: BLE001 - continue through fallback texts.
            continue
    await page.keyboard.press("Enter")


async def _needs_verification_code(page) -> bool:
    body_text = await _body_text(page)
    lowered = body_text.lower()
    if any(term in lowered for term in _VERIFICATION_TERMS):
        return await _has_visible_locator(page, _TEXT_CHALLENGE_SELECTORS)
    return False


async def _raise_if_hard_challenge(page) -> None:
    body_text = await _body_text(page)
    lowered = body_text.lower()
    if any(term in lowered for term in _HARD_CHALLENGE_TERMS):
        raise RuntimeError(
            "X presented a CAPTCHA or security challenge that cannot be completed "
            "by this authorized automation route."
        )


async def _body_text(page) -> str:
    try:
        return await page.locator("body").inner_text(timeout=1000)
    except Exception:  # noqa: BLE001 - empty text is enough for callers.
        return ""


async def _write_auth_diagnostics(page, *, diagnostics_dir: Path, reason: str) -> None:
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    payload = {
        "reason": reason,
        "url": page.url,
        "title": await _page_title(page),
        "body_text": await _body_text(page),
    }
    (diagnostics_dir / f"{stamp}.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    with suppress(Exception):
        await page.screenshot(path=str(diagnostics_dir / f"{stamp}.png"), full_page=True)
    print(f"Saved auth diagnostics to {diagnostics_dir}")


async def _page_title(page) -> str:
    try:
        return await page.title()
    except Exception:  # noqa: BLE001 - diagnostics should not hide the original failure.
        return ""


def _pattern_texts(patterns: tuple[str, ...]) -> tuple[str, ...]:
    texts: list[str] = []
    for pattern in patterns:
        for value in re.findall(r"[A-Za-z][A-Za-z ]+|[\u3040-\u30ff\u3400-\u9fff]+", pattern):
            value = value.strip()
            if value and value not in texts:
                texts.append(value)
    return tuple(texts)


def _looks_like_initial_login_screen(body_text: str) -> bool:
    return (
        ("電話番号/メールアドレス/ユーザー" in body_text or "phone" in body_text.lower())
        and ("パスワードを忘れた" in body_text or "forgot password" in body_text.lower())
        and "password" not in body_text.lower()
    )


def _totp_code(secret: str, *, timestamp: float | None = None) -> str:
    normalized = re.sub(r"\s+", "", secret).upper()
    padding = "=" * ((8 - len(normalized) % 8) % 8)
    key = base64.b32decode(normalized + padding, casefold=True)
    counter = int((timestamp if timestamp is not None else time.time()) // 30)
    digest = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    code = struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF
    return f"{code % 1_000_000:06d}"


def _safe_error(exc: Exception) -> str:
    return f"{type(exc).__name__}: {exc}"


def _system_browser_executable(browser: str) -> Path:
    candidates: tuple[str, ...]
    if browser == "chrome":
        candidates = (
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        )
    elif browser == "msedge":
        candidates = (
            r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        )
    else:
        raise RuntimeError(f"Unsupported system browser: {browser}")
    for candidate in candidates:
        path = Path(candidate)
        if path.exists():
            return path
    raise RuntimeError(f"Could not find installed {browser} executable")


def write_storage_state_from_cookie_env(
    *,
    storage_state: str | Path,
    auth_token_env: str = "RESEARCH_X_X_AUTH_TOKEN",
    ct0_env: str = "RESEARCH_X_X_CT0",
) -> bool:
    auth_token = os.environ.get(auth_token_env)
    ct0 = os.environ.get(ct0_env)
    if not auth_token or not ct0:
        missing = [
            name
            for name, value in ((auth_token_env, auth_token), (ct0_env, ct0))
            if not value
        ]
        raise RuntimeError("Missing cookie env values: " + ", ".join(missing))

    path = Path(storage_state)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "cookies": [
            _cookie("auth_token", auth_token, http_only=True),
            _cookie("ct0", ct0, http_only=False),
        ],
        "origins": [
            {
                "origin": "https://x.com",
                "localStorage": [],
            }
        ],
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    print(f"Saved Playwright storage state to {path}")
    return True


def _cookie(name: str, value: str, *, http_only: bool) -> dict[str, object]:
    return {
        "name": name,
        "value": value,
        "domain": ".x.com",
        "path": "/",
        "expires": -1,
        "httpOnly": http_only,
        "secure": True,
        "sameSite": "Lax",
    }


_USERNAME_SELECTORS = (
    "input[autocomplete='username']",
    "input[name='text']",
    "input[data-testid='ocfEnterTextTextInput']",
    "input[type='text']",
)

_TEXT_CHALLENGE_SELECTORS = (
    "input[data-testid='ocfEnterTextTextInput']",
    "input[name='text']",
    "input[type='text']",
)

_PASSWORD_SELECTORS = (
    "input[name='password']",
    "input[type='password']",
    "input[autocomplete='current-password']",
)

_NEXT_BUTTON_PATTERNS = (
    r"^(Next|次へ|Weiter|Siguiente|Suivant|Avanti)$",
    r"^(Continue|続ける|続行)$",
)

_LOGIN_BUTTON_PATTERNS = (
    r"^(Log in|Login|Sign in|ログイン|ログインする)$",
)

_VERIFICATION_TERMS = (
    "verification code",
    "authentication code",
    "confirmation code",
    "認証コード",
    "確認コード",
)

_HARD_CHALLENGE_TERMS = (
    "captcha",
    "arkose",
    "verify you are human",
    "prove you are human",
    "unusual login activity",
    "suspicious login",
    "account locked",
    "アカウントがロック",
    "不審なログイン",
)

_USER_AGENT_FALLBACKS = (
    (
        "opera_windows",
        (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36 OPR/114.0.0.0"
        ),
    ),
    (
        "chrome_windows",
        (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
        ),
    ),
)
