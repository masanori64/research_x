from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_cookie_dict_from_playwright_state(path: str | Path) -> dict[str, str]:
    state_path = Path(path)
    payload = json.loads(state_path.read_text(encoding="utf-8"))
    cookies = payload.get("cookies", [])
    if not isinstance(cookies, list):
        raise ValueError(f"Playwright storage_state cookies must be a list: {state_path}")
    result: dict[str, str] = {}
    for cookie in cookies:
        if not _is_x_cookie(cookie):
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
    missing = [name for name in ("auth_token", "ct0") if not cookies.get(name)]
    if missing:
        raise ValueError("missing required X session cookies: " + ", ".join(missing))


def _is_x_cookie(cookie: Any) -> bool:
    if not isinstance(cookie, dict):
        return False
    domain = str(cookie.get("domain", ""))
    return domain == "x.com" or domain.endswith(".x.com") or domain.endswith(".twitter.com")
