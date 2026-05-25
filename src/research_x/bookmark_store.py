from __future__ import annotations

import hashlib
import json
import mimetypes
from dataclasses import asdict, dataclass, is_dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from research_x.contracts import XItem, utc_now


@dataclass(frozen=True)
class BookmarkStoreSummary:
    bookmarks: int
    tweets: int
    edges: int
    media: int
    downloaded_media: int
    media_errors: int


def write_bookmark_store_outputs(
    out_dir: str | Path,
    *,
    items: tuple[XItem, ...],
    download_media: bool = True,
    media_timeout_seconds: float = 30.0,
) -> BookmarkStoreSummary:
    output_path = Path(out_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    media_dir = output_path / "media"
    media_dir.mkdir(parents=True, exist_ok=True)

    tweets: dict[str, dict[str, Any]] = {}
    edges: dict[tuple[str, str, str], dict[str, Any]] = {}
    media: dict[str, dict[str, Any]] = {}
    bookmark_rows: list[dict[str, Any]] = []
    root_ids = {item.source_id for item in items if item.source_id}

    for index, item in enumerate(items):
        root = _tweet_from_item(item, role="bookmark_root")
        if root is None:
            continue
        root["bookmark_index"] = _bookmark_index(item, index)
        tweets[root["tweet_id"]] = _merge_tweet(tweets.get(root["tweet_id"]), root)
        bookmark_rows.append(
            {
                "bookmark_id": f"bookmark:{root['tweet_id']}",
                "tweet_id": root["tweet_id"],
                "bookmark_index": root["bookmark_index"],
                "url": root["url"],
                "providers": item.raw.get("_providers", []),
                "observed_at": item.observed_at,
            }
        )
        _add_media(media, root["tweet_id"], item.raw)
        for quote in _quoted_tweets_from_raw(item.raw):
            _add_quote_tree(
                parent_id=root["tweet_id"],
                quote=quote,
                tweets=tweets,
                edges=edges,
                media=media,
                root_ids=root_ids,
            )

    media_rows = list(media.values())
    if download_media:
        for row in media_rows:
            _download_media(row, media_dir=media_dir, timeout_seconds=media_timeout_seconds)

    tree_rows = [
        _tree_for_bookmark(row, tweets=tweets, edges=edges, root_ids=root_ids)
        for row in bookmark_rows
    ]

    _write_jsonl(output_path / "bookmarks.jsonl", bookmark_rows)
    _write_jsonl(output_path / "tweets.jsonl", tweets.values())
    _write_jsonl(output_path / "tweet_edges.jsonl", edges.values())
    _write_jsonl(output_path / "media.jsonl", media_rows)
    _write_jsonl(output_path / "bookmark_trees.jsonl", tree_rows)

    downloaded = sum(1 for row in media_rows if row.get("download_status") == "ok")
    errors = sum(1 for row in media_rows if row.get("download_status") == "error")
    summary = BookmarkStoreSummary(
        bookmarks=len(bookmark_rows),
        tweets=len(tweets),
        edges=len(edges),
        media=len(media_rows),
        downloaded_media=downloaded,
        media_errors=errors,
    )
    (output_path / "bookmark_store_report.json").write_text(
        json.dumps(_jsonable(summary), ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return summary


def _add_quote_tree(
    *,
    parent_id: str,
    quote: dict[str, Any],
    tweets: dict[str, dict[str, Any]],
    edges: dict[tuple[str, str, str], dict[str, Any]],
    media: dict[str, dict[str, Any]],
    root_ids: set[str],
) -> None:
    child = _tweet_from_raw(quote, role="quoted_tweet")
    if child is None:
        return
    child["also_bookmarked"] = child["tweet_id"] in root_ids
    tweets[child["tweet_id"]] = _merge_tweet(tweets.get(child["tweet_id"]), child)
    key = (parent_id, child["tweet_id"], "quote")
    edges[key] = {
        "parent_tweet_id": parent_id,
        "child_tweet_id": child["tweet_id"],
        "relation": "quote",
        "child_also_bookmarked": child["tweet_id"] in root_ids,
    }
    _add_media(media, child["tweet_id"], quote)
    for nested in _quoted_tweets_from_raw(quote):
        _add_quote_tree(
            parent_id=child["tweet_id"],
            quote=nested,
            tweets=tweets,
            edges=edges,
            media=media,
            root_ids=root_ids,
        )


def _tweet_from_item(item: XItem, *, role: str) -> dict[str, Any] | None:
    if not item.source_id:
        return None
    return {
        "tweet_id": item.source_id,
        "url": item.url,
        "author": item.author,
        "text": item.text,
        "created_at": item.created_at,
        "observed_at": item.observed_at,
        "role": role,
    }


def _tweet_from_raw(raw: dict[str, Any], *, role: str) -> dict[str, Any] | None:
    tweet_id = _tweet_id(raw)
    if tweet_id is None:
        return None
    author = _author(raw)
    return {
        "tweet_id": tweet_id,
        "url": _tweet_url(raw, author, tweet_id),
        "author": author,
        "text": _text(raw),
        "created_at": _created_at(raw),
        "observed_at": utc_now(),
        "role": role,
    }


def _merge_tweet(existing: dict[str, Any] | None, incoming: dict[str, Any]) -> dict[str, Any]:
    if existing is None:
        return incoming
    merged = dict(existing)
    for key, value in incoming.items():
        if merged.get(key) in (None, "", []):
            merged[key] = value
    if incoming.get("role") == "bookmark_root":
        merged["role"] = "bookmark_root"
    if incoming.get("also_bookmarked"):
        merged["also_bookmarked"] = True
    return merged


def _quoted_tweets_from_raw(raw: dict[str, Any]) -> list[dict[str, Any]]:
    quotes: list[dict[str, Any]] = []
    _append_quote(quotes, raw.get("quotedTweet"))
    _append_quote(quotes, raw.get("quoted_tweet"))
    _append_quote(quotes, raw.get("quoted_status"))
    quoted_status_result = raw.get("quoted_status_result")
    if isinstance(quoted_status_result, dict):
        _append_quote(quotes, quoted_status_result.get("result"))
    for provider_raw in _provider_raw_values(raw):
        if provider_raw is raw:
            continue
        quotes.extend(_quoted_tweets_from_raw(provider_raw))
    return _dedupe_quotes(quotes)


def _append_quote(quotes: list[dict[str, Any]], value: Any) -> None:
    if not isinstance(value, dict):
        return
    if value.get("__typename") == "TweetWithVisibilityResults" and isinstance(
        value.get("tweet"), dict
    ):
        value = value["tweet"]
    if isinstance(value.get("result"), dict):
        value = value["result"]
    if isinstance(value, dict) and _tweet_id(value):
        quotes.append(value)


def _provider_raw_values(raw: dict[str, Any]):
    provider_raw = raw.get("_provider_raw")
    if isinstance(provider_raw, dict):
        for value in provider_raw.values():
            if isinstance(value, dict):
                yield value


def _dedupe_quotes(quotes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for quote in quotes:
        tweet_id = _tweet_id(quote)
        if tweet_id is None or tweet_id in seen:
            continue
        seen.add(tweet_id)
        result.append(quote)
    return result


def _tweet_id(raw: dict[str, Any]) -> str | None:
    for key in ("id", "id_str", "rest_id", "tweet_id"):
        value = raw.get(key)
        if value not in (None, ""):
            return str(value)
    legacy = raw.get("legacy")
    if isinstance(legacy, dict):
        for key in ("id_str", "id"):
            value = legacy.get(key)
            if value not in (None, ""):
                return str(value)
    return None


def _author(raw: dict[str, Any]) -> str | None:
    user = raw.get("user")
    if isinstance(user, dict):
        value = user.get("username") or user.get("screen_name")
        if value:
            return str(value)
    core_user = raw.get("core", {}).get("user_results", {}).get("result", {})
    if isinstance(core_user, dict):
        legacy = core_user.get("legacy", {})
        value = legacy.get("screen_name") if isinstance(legacy, dict) else None
        value = value or core_user.get("screen_name")
        if value:
            return str(value)
    return None


def _text(raw: dict[str, Any]) -> str | None:
    for key in ("rawContent", "text", "full_text", "content"):
        value = raw.get(key)
        if value not in (None, ""):
            return str(value)
    legacy = raw.get("legacy")
    if isinstance(legacy, dict):
        value = legacy.get("full_text") or legacy.get("text")
        if value:
            return str(value)
    return None


def _created_at(raw: dict[str, Any]) -> Any:
    for key in ("date", "created_at", "createdAt"):
        value = raw.get(key)
        if value not in (None, ""):
            return value
    legacy = raw.get("legacy")
    if isinstance(legacy, dict):
        return legacy.get("created_at")
    return None


def _tweet_url(raw: dict[str, Any], author: str | None, tweet_id: str) -> str | None:
    value = raw.get("url")
    if isinstance(value, str) and value:
        return value
    if author:
        return f"https://x.com/{author}/status/{tweet_id}"
    return None


def _add_media(media: dict[str, dict[str, Any]], tweet_id: str, raw: dict[str, Any]) -> None:
    for url, media_type, alt_text in _media_values(raw):
        media_id = hashlib.sha1(f"{tweet_id}:{url}".encode()).hexdigest()[:16]
        media.setdefault(
            media_id,
            {
                "media_id": media_id,
                "tweet_id": tweet_id,
                "type": media_type,
                "url": url,
                "alt_text": alt_text,
                "local_path": None,
                "download_status": "pending",
            },
        )


def _media_values(raw: dict[str, Any]):
    media = raw.get("media")
    if isinstance(media, dict):
        for photo in media.get("photos", []) or []:
            if isinstance(photo, dict) and photo.get("url"):
                yield str(photo["url"]), "photo", photo.get("altText") or photo.get("alt_text")
        for video in media.get("videos", []) or []:
            if isinstance(video, dict) and video.get("thumbnailUrl"):
                yield str(video["thumbnailUrl"]), "video_thumbnail", None
    legacy = raw.get("legacy")
    if isinstance(legacy, dict):
        entities = legacy.get("extended_entities") or legacy.get("entities") or {}
        if isinstance(entities, dict):
            for row in entities.get("media", []) or []:
                if not isinstance(row, dict):
                    continue
                url = row.get("media_url_https") or row.get("media_url")
                if url:
                    yield str(url), str(row.get("type") or "media"), row.get("ext_alt_text")
    for provider_raw in _provider_raw_values(raw):
        if provider_raw is raw:
            continue
        yield from _media_values(provider_raw)


def _download_media(
    row: dict[str, Any],
    *,
    media_dir: Path,
    timeout_seconds: float,
) -> None:
    url = row.get("url")
    if not isinstance(url, str) or not url:
        row["download_status"] = "skipped"
        return
    ext = _media_extension(url)
    target_dir = media_dir / str(row["tweet_id"])
    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = target_dir / f"{row['media_id']}{ext}"
    request = Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urlopen(request, timeout=timeout_seconds) as response:  # noqa: S310
            data = response.read()
            target_path.write_bytes(data)
            row["download_status"] = "ok"
            row["local_path"] = str(target_path)
            row["bytes"] = len(data)
            row["content_type"] = response.headers.get("content-type")
    except (OSError, URLError, TimeoutError) as exc:
        row["download_status"] = "error"
        row["download_error"] = f"{type(exc).__name__}: {exc}"


def _media_extension(url: str) -> str:
    path = urlparse(url).path
    suffix = Path(path).suffix
    if suffix:
        return suffix
    guessed = mimetypes.guess_extension(urlparse(url).path)
    return guessed or ".bin"


def _tree_for_bookmark(
    bookmark: dict[str, Any],
    *,
    tweets: dict[str, dict[str, Any]],
    edges: dict[tuple[str, str, str], dict[str, Any]],
    root_ids: set[str],
) -> dict[str, Any]:
    root_id = bookmark["tweet_id"]
    return {
        "bookmark": bookmark,
        "tweet": _tree_node(root_id, tweets=tweets, edges=edges, root_ids=root_ids),
    }


def _tree_node(
    tweet_id: str,
    *,
    tweets: dict[str, dict[str, Any]],
    edges: dict[tuple[str, str, str], dict[str, Any]],
    root_ids: set[str],
) -> dict[str, Any]:
    tweet = dict(tweets.get(tweet_id, {"tweet_id": tweet_id}))
    tweet["also_bookmarked"] = tweet_id in root_ids and tweet.get("role") != "bookmark_root"
    children = [
        _tree_node(edge["child_tweet_id"], tweets=tweets, edges=edges, root_ids=root_ids)
        for edge in edges.values()
        if edge["parent_tweet_id"] == tweet_id and edge["relation"] == "quote"
    ]
    if children:
        tweet["quoted_tweets"] = children
    return tweet


def _bookmark_index(item: XItem, fallback: int) -> int:
    value = item.raw.get("bookmark_index")
    if isinstance(value, int):
        return value
    return fallback


def _write_jsonl(path: Path, rows) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(_jsonable(row), ensure_ascii=False, sort_keys=True) + "\n")


def _jsonable(value: Any):
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if is_dataclass(value) and not isinstance(value, type):
        return _jsonable(asdict(value))
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if hasattr(value, "value"):
        return value.value
    return value
