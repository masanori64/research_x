from __future__ import annotations

import html
import re
from pathlib import Path
from urllib.parse import quote

from research_x.contracts import AcquisitionTarget, TargetKind, XItem, utc_now
from research_x.cookies import (
    cookie_header,
    load_cookie_dict_from_playwright_state,
    require_x_session_cookies,
)

_AUTHOR_STATUS_RE = re.compile(
    r"(?:https?:)?//(?:x\.com|twitter\.com)/([A-Za-z0-9_]{1,20})/status(?:es)?/(\d{5,25})"
)
_RELATIVE_AUTHOR_STATUS_RE = re.compile(
    r"(?<![A-Za-z0-9_])/(?!i/)([A-Za-z0-9_]{1,20})/status(?:es)?/(\d{5,25})"
)
_WEB_STATUS_RE = re.compile(
    r"(?:https?:)?//(?:x\.com|twitter\.com)/i/web/status(?:es)?/(\d{5,25})"
)


def target_to_x_url(target: AcquisitionTarget) -> str:
    if target.kind == TargetKind.PROFILE:
        return f"https://x.com/{screen_name(target.value)}"
    if target.kind == TargetKind.SEARCH:
        return f"https://x.com/search?q={quote(target.value)}&src=typed_query&f=live"
    if target.kind == TargetKind.URL:
        return target.value
    if target.kind == TargetKind.BOOKMARKS:
        return "https://x.com/i/bookmarks"
    raise ValueError(f"unsupported target kind: {target.kind}")


def screen_name(value: str) -> str:
    value = value.strip()
    if value.startswith("@"):
        return value[1:]
    match = re.search(r"(?:x\.com|twitter\.com)/([^/?#]+)", value)
    if match:
        return match.group(1)
    return value


def storage_state_cookie_header(path: str | Path | None) -> str | None:
    if path is None:
        return None
    state_path = Path(path)
    if not state_path.exists():
        return None
    cookies = load_cookie_dict_from_playwright_state(state_path)
    require_x_session_cookies(cookies)
    return cookie_header(cookies)


def status_items_from_text(
    text: str,
    target: AcquisitionTarget,
    *,
    limit: int | None = None,
) -> list[XItem]:
    normalized = html.unescape(text).replace("\\/", "/")
    max_items = max(1, limit or target.limit)
    seen: set[str] = set()
    items: list[XItem] = []

    for author, source_id in _iter_author_statuses(normalized):
        if source_id in seen:
            continue
        seen.add(source_id)
        items.append(
            XItem(
                source_id=source_id,
                url=f"https://x.com/{author}/status/{source_id}",
                author=author,
                text=None,
                created_at=None,
                observed_at=utc_now(),
                raw={"extraction": "status_link", "target": target.value},
            )
        )
        if len(items) >= max_items:
            return items

    for source_id in _iter_web_statuses(normalized):
        if source_id in seen:
            continue
        seen.add(source_id)
        items.append(
            XItem(
                source_id=source_id,
                url=f"https://x.com/i/web/status/{source_id}",
                author=None,
                text=None,
                created_at=None,
                observed_at=utc_now(),
                raw={"extraction": "web_status_link", "target": target.value},
            )
        )
        if len(items) >= max_items:
            return items

    if target.kind == TargetKind.URL:
        target_item = status_item_from_url(target.value)
        if target_item is not None:
            return [target_item]
    return items


def status_item_from_url(value: str) -> XItem | None:
    normalized = html.unescape(value).replace("\\/", "/")
    match = _AUTHOR_STATUS_RE.search(normalized)
    if match:
        author, source_id = match.groups()
        return XItem(
            source_id=source_id,
            url=f"https://x.com/{author}/status/{source_id}",
            author=author,
            text=None,
            created_at=None,
            observed_at=utc_now(),
            raw={"extraction": "target_url"},
        )
    match = _WEB_STATUS_RE.search(normalized)
    if match:
        source_id = match.group(1)
        return XItem(
            source_id=source_id,
            url=f"https://x.com/i/web/status/{source_id}",
            author=None,
            text=None,
            created_at=None,
            observed_at=utc_now(),
            raw={"extraction": "target_url"},
        )
    return None


def _iter_author_statuses(value: str):
    for match in _AUTHOR_STATUS_RE.finditer(value):
        author, source_id = match.groups()
        if author != "i":
            yield author, source_id
    for match in _RELATIVE_AUTHOR_STATUS_RE.finditer(value):
        author, source_id = match.groups()
        yield author, source_id


def _iter_web_statuses(value: str):
    for match in _WEB_STATUS_RE.finditer(value):
        yield match.group(1)
