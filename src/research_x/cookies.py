from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

REQUIRED_X_SESSION_COOKIES = ("auth_token", "ct0")


def load_cookie_dict_from_playwright_state(path: str | Path) -> dict[str, str]:
    state_path = Path(path)
    payload = json.loads(state_path.read_text(encoding="utf-8"))
    cookies = payload.get("cookies", [])
    if not isinstance(cookies, list):
        raise ValueError(f"Playwright storage_state cookies must be a list: {state_path}")
    result: dict[str, str] = {}
    now = time.time()
    for cookie in cookies:
        if not is_usable_x_cookie(cookie, now=now):
            continue
        name = cookie.get("name")
        value = cookie.get("value")
        if isinstance(name, str) and isinstance(value, str):
            result[name] = value
    return result


def write_cookie_dict(path: str | Path, cookies: dict[str, str]) -> None:
    cookie_path = Path(path)
    cookie_path.parent.mkdir(parents=True, exist_ok=True)
    cookie_path.write_text(json.dumps(cookies, indent=2, sort_keys=True), encoding="utf-8")


def cookie_header(cookies: dict[str, str]) -> str:
    return "; ".join(f"{name}={value}" for name, value in sorted(cookies.items()))


def parse_cookie_header(value: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for part in value.split(";"):
        if "=" not in part:
            continue
        name, cookie_value = part.split("=", 1)
        name = name.strip()
        cookie_value = cookie_value.strip()
        if name:
            result[name] = cookie_value
    return result


def require_x_session_cookies(cookies: dict[str, str]) -> None:
    missing = [name for name in REQUIRED_X_SESSION_COOKIES if not cookies.get(name)]
    if missing:
        raise ValueError("missing required X session cookies: " + ", ".join(missing))


def usable_x_cookie_names(cookies: list[Any]) -> set[str]:
    now = time.time()
    return {
        str(cookie.get("name"))
        for cookie in cookies
        if is_usable_x_cookie(cookie, now=now)
    }


def is_usable_x_cookie(cookie: Any, *, now: float | None = None) -> bool:
    if not _is_x_cookie(cookie):
        return False
    name = cookie.get("name")
    value = cookie.get("value")
    if not isinstance(name, str) or not name:
        return False
    if not isinstance(value, str) or not value:
        return False
    return not _cookie_is_expired(cookie, now=now)


def _is_x_cookie(cookie: Any) -> bool:
    if not isinstance(cookie, dict):
        return False
    domain = str(cookie.get("domain", ""))
    return domain == "x.com" or domain.endswith(".x.com") or domain.endswith(".twitter.com")


def _cookie_is_expired(cookie: dict[str, Any], *, now: float | None = None) -> bool:
    expires = cookie.get("expires")
    if expires in (None, "", 0, -1):
        return False
    try:
        expires_at = float(expires)
    except (TypeError, ValueError):
        return True
    if expires_at <= 0:
        return False
    return expires_at <= (now if now is not None else time.time())
