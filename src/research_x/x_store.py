from __future__ import annotations

import hashlib
import json
import mimetypes
import sqlite3
import time
from collections.abc import Iterable
from dataclasses import asdict, dataclass, is_dataclass
from datetime import datetime
from http.client import IncompleteRead
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from research_x.contracts import AcquisitionTarget, XItem, utc_now


@dataclass(frozen=True)
class XStoreSummary:
    collection_kind: str
    collection_items: int
    bookmarks: int
    tweets: int
    edges: int
    media: int
    downloaded_media: int
    media_errors: int
    db_path: str


def write_x_store_outputs(
    out_dir: str | Path,
    *,
    items: Iterable[XItem],
    collection_kind: str,
    target: AcquisitionTarget,
    account_id: str | None = None,
    account_profile: Any | None = None,
    attempts: Iterable[Any] = (),
    run_id: str | None = None,
    db_path: str | Path | None = None,
    download_media: bool = True,
    media_timeout_seconds: float = 30.0,
) -> XStoreSummary:
    output_path = Path(out_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    media_dir = output_path / "media"
    media_dir.mkdir(parents=True, exist_ok=True)

    item_tuple = tuple(items)
    resolved_run_id = run_id or _stable_run_id(collection_kind, target, account_id)
    resolved_db_path = Path(db_path) if db_path else output_path / "x_data.sqlite3"

    tweets: dict[str, dict[str, Any]] = {}
    edges: dict[tuple[str, str, str], dict[str, Any]] = {}
    media: dict[str, dict[str, Any]] = {}
    collection_rows: list[dict[str, Any]] = []
    bookmark_rows: list[dict[str, Any]] = []
    raw_rows: list[dict[str, Any]] = []
    root_ids = {item.source_id for item in item_tuple if item.source_id}
    collection_id = _collection_id(collection_kind, target, account_id)

    for index, item in enumerate(item_tuple):
        role = "bookmark_root" if collection_kind == "bookmarks" else "target_tweet"
        root = _tweet_from_item(item, role=role)
        if root is None:
            continue
        root["collection_kind"] = collection_kind
        root["providers"] = item.raw.get("_providers", [])
        tweets[root["tweet_id"]] = _merge_tweet(tweets.get(root["tweet_id"]), root)
        position = _bookmark_index(item, index) if collection_kind == "bookmarks" else index
        collection_rows.append(
            {
                "collection_id": collection_id,
                "collection_kind": collection_kind,
                "account_id": account_id,
                "target_kind": target.kind.value,
                "target_value": target.value,
                "tweet_id": root["tweet_id"],
                "position": position,
                "observed_at": item.observed_at,
                "providers": item.raw.get("_providers", []),
                "run_id": resolved_run_id,
            }
        )
        if collection_kind == "bookmarks":
            bookmark_rows.append(
                {
                    "bookmark_id": f"bookmark:{account_id or 'default'}:{root['tweet_id']}",
                    "account_id": account_id,
                    "tweet_id": root["tweet_id"],
                    "bookmark_index": position,
                    "url": root["url"],
                    "providers": item.raw.get("_providers", []),
                    "observed_at": item.observed_at,
                    "run_id": resolved_run_id,
                }
            )
        raw_rows.append(_raw_payload_row(item, target, collection_kind, resolved_run_id))
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
        progress_path = output_path / "media_progress.json"
        started = time.monotonic()
        _write_media_progress(progress_path, media_rows, current_index=0, started=started)
        for index, row in enumerate(media_rows, start=1):
            _download_media(row, media_dir=media_dir, timeout_seconds=media_timeout_seconds)
            _write_media_progress(
                progress_path,
                media_rows,
                current_index=index,
                started=started,
            )
        _write_media_progress(
            progress_path,
            media_rows,
            current_index=len(media_rows),
            started=started,
            finished=True,
        )

    tree_rows = [
        _tree_for_bookmark(row, tweets=tweets, edges=edges, root_ids=root_ids)
        for row in bookmark_rows
    ]

    _write_jsonl(output_path / "collection_items.jsonl", collection_rows)
    _write_jsonl(output_path / "tweets.jsonl", tweets.values())
    _write_jsonl(output_path / "tweet_edges.jsonl", edges.values())
    _write_jsonl(output_path / "media.jsonl", media_rows)
    _write_jsonl(output_path / "raw_payloads.jsonl", raw_rows)
    if collection_kind == "bookmarks":
        _write_jsonl(output_path / "account_bookmarks.jsonl", bookmark_rows)
        _write_jsonl(output_path / "bookmarks.jsonl", bookmark_rows)
        _write_jsonl(output_path / "bookmark_trees.jsonl", tree_rows)

    _write_sqlite(
        resolved_db_path,
        account_profile=account_profile,
        attempts=attempts,
        collection_rows=collection_rows,
        bookmark_rows=bookmark_rows,
        tweets=tweets.values(),
        edges=edges.values(),
        media_rows=media_rows,
        raw_rows=raw_rows,
    )

    downloaded = sum(1 for row in media_rows if row.get("download_status") == "ok")
    errors = sum(1 for row in media_rows if row.get("download_status") == "error")
    summary = XStoreSummary(
        collection_kind=collection_kind,
        collection_items=len(collection_rows),
        bookmarks=len(bookmark_rows),
        tweets=len(tweets),
        edges=len(edges),
        media=len(media_rows),
        downloaded_media=downloaded,
        media_errors=errors,
        db_path=str(resolved_db_path),
    )
    (output_path / "x_store_report.json").write_text(
        json.dumps(_jsonable(summary), ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    if collection_kind == "bookmarks":
        (output_path / "bookmark_store_report.json").write_text(
            json.dumps(_jsonable(summary), ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
    return summary


def write_label_store_outputs(
    db_path: str | Path,
    *,
    classifications: Iterable[Any],
    label_scope: str,
    account_id: str | None = None,
    run_id: str | None = None,
    model: str | None = None,
    generated_at: datetime | None = None,
) -> None:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as conn:
        _ensure_schema(conn)
        for classification in classifications:
            row = _classification_row(
                classification,
                label_scope=label_scope,
                account_id=account_id,
                run_id=run_id,
                model=model,
                generated_at=generated_at,
            )
            conn.execute(
                """
                INSERT INTO ai_labels (
                    label_id, account_id, tweet_id, label_scope, category_id,
                    category_label, confidence, tags_json, summary, rationale,
                    model, run_id, generated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(label_id) DO UPDATE SET
                    category_id=excluded.category_id,
                    category_label=excluded.category_label,
                    confidence=excluded.confidence,
                    tags_json=excluded.tags_json,
                    summary=excluded.summary,
                    rationale=excluded.rationale,
                    model=excluded.model,
                    run_id=excluded.run_id,
                    generated_at=excluded.generated_at
                """,
                row,
            )


def _write_sqlite(
    db_path: Path,
    *,
    account_profile: Any | None,
    attempts: Iterable[Any],
    collection_rows: list[dict[str, Any]],
    bookmark_rows: list[dict[str, Any]],
    tweets: Iterable[dict[str, Any]],
    edges: Iterable[dict[str, Any]],
    media_rows: Iterable[dict[str, Any]],
    raw_rows: Iterable[dict[str, Any]],
) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        _ensure_schema(conn)
        if account_profile is not None:
            _upsert_account(conn, account_profile)
        for attempt in attempts:
            _insert_provider_run(conn, attempt)
        for row in tweets:
            _upsert_tweet(conn, row)
        for row in collection_rows:
            conn.execute(
                """
                INSERT INTO collection_items (
                    collection_id, collection_kind, account_id, target_kind, target_value,
                    tweet_id, position, observed_at, providers_json, run_id
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(collection_id, tweet_id) DO UPDATE SET
                    position=excluded.position,
                    observed_at=excluded.observed_at,
                    providers_json=excluded.providers_json,
                    run_id=excluded.run_id
                """,
                (
                    row["collection_id"],
                    row["collection_kind"],
                    row.get("account_id"),
                    row["target_kind"],
                    row["target_value"],
                    row["tweet_id"],
                    row["position"],
                    _iso(row["observed_at"]),
                    json.dumps(_jsonable(row.get("providers", [])), ensure_ascii=False),
                    row.get("run_id"),
                ),
            )
        for row in bookmark_rows:
            conn.execute(
                """
                INSERT INTO account_bookmarks (
                    account_id, tweet_id, bookmark_index, observed_at,
                    providers_json, run_id
                )
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(account_id, tweet_id) DO UPDATE SET
                    bookmark_index=excluded.bookmark_index,
                    observed_at=excluded.observed_at,
                    providers_json=excluded.providers_json,
                    run_id=excluded.run_id
                """,
                (
                    row.get("account_id") or "default",
                    row["tweet_id"],
                    row["bookmark_index"],
                    _iso(row["observed_at"]),
                    json.dumps(_jsonable(row.get("providers", [])), ensure_ascii=False),
                    row.get("run_id"),
                ),
            )
        for row in edges:
            conn.execute(
                """
                INSERT INTO tweet_edges (
                    parent_tweet_id, child_tweet_id, relation, child_also_bookmarked
                )
                VALUES (?, ?, ?, ?)
                ON CONFLICT(parent_tweet_id, child_tweet_id, relation) DO UPDATE SET
                    child_also_bookmarked=excluded.child_also_bookmarked
                """,
                (
                    row["parent_tweet_id"],
                    row["child_tweet_id"],
                    row["relation"],
                    int(bool(row.get("child_also_bookmarked"))),
                ),
            )
        for row in media_rows:
            conn.execute(
                """
                INSERT INTO media (
                    media_id, tweet_id, type, url, alt_text, local_path,
                    download_status, bytes, content_type, download_error
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(media_id) DO UPDATE SET
                    local_path=excluded.local_path,
                    download_status=excluded.download_status,
                    bytes=excluded.bytes,
                    content_type=excluded.content_type,
                    download_error=excluded.download_error
                """,
                (
                    row["media_id"],
                    row["tweet_id"],
                    row.get("type"),
                    row.get("url"),
                    row.get("alt_text"),
                    row.get("local_path"),
                    row.get("download_status"),
                    row.get("bytes"),
                    row.get("content_type"),
                    row.get("download_error"),
                ),
            )
        for row in raw_rows:
            conn.execute(
                """
                INSERT INTO raw_payloads (
                    raw_id, run_id, provider_id, target_kind, target_value,
                    source_id, observed_at, payload_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(raw_id) DO UPDATE SET payload_json=excluded.payload_json
                """,
                (
                    row["raw_id"],
                    row["run_id"],
                    row["provider_id"],
                    row["target_kind"],
                    row["target_value"],
                    row["source_id"],
                    _iso(row["observed_at"]),
                    json.dumps(_jsonable(row["payload"]), ensure_ascii=False),
                ),
            )


def _ensure_schema(conn: sqlite3.Connection) -> None:
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS accounts (
            account_id TEXT PRIMARY KEY,
            screen_name TEXT,
            user_id TEXT,
            display_name TEXT,
            url TEXT,
            metadata_json TEXT,
            updated_at TEXT
        );
        CREATE TABLE IF NOT EXISTS provider_runs (
            provider_run_id TEXT PRIMARY KEY,
            provider_id TEXT,
            target_kind TEXT,
            target_value TEXT,
            status TEXT,
            started_at TEXT,
            finished_at TEXT,
            item_count INTEGER,
            error_type TEXT,
            error_message TEXT,
            metadata_json TEXT,
            evidence_path TEXT
        );
        CREATE TABLE IF NOT EXISTS tweets (
            tweet_id TEXT PRIMARY KEY,
            url TEXT,
            author_screen_name TEXT,
            text TEXT,
            created_at TEXT,
            first_observed_at TEXT,
            last_observed_at TEXT,
            role TEXT,
            collection_kind TEXT,
            providers_json TEXT,
            raw_json TEXT,
            updated_at TEXT
        );
        CREATE TABLE IF NOT EXISTS collection_items (
            collection_id TEXT,
            collection_kind TEXT,
            account_id TEXT,
            target_kind TEXT,
            target_value TEXT,
            tweet_id TEXT,
            position INTEGER,
            observed_at TEXT,
            providers_json TEXT,
            run_id TEXT,
            PRIMARY KEY(collection_id, tweet_id)
        );
        CREATE TABLE IF NOT EXISTS account_bookmarks (
            account_id TEXT,
            tweet_id TEXT,
            bookmark_index INTEGER,
            observed_at TEXT,
            providers_json TEXT,
            run_id TEXT,
            PRIMARY KEY(account_id, tweet_id)
        );
        CREATE TABLE IF NOT EXISTS tweet_edges (
            parent_tweet_id TEXT,
            child_tweet_id TEXT,
            relation TEXT,
            child_also_bookmarked INTEGER DEFAULT 0,
            PRIMARY KEY(parent_tweet_id, child_tweet_id, relation)
        );
        CREATE TABLE IF NOT EXISTS media (
            media_id TEXT PRIMARY KEY,
            tweet_id TEXT,
            type TEXT,
            url TEXT,
            alt_text TEXT,
            local_path TEXT,
            download_status TEXT,
            bytes INTEGER,
            content_type TEXT,
            download_error TEXT
        );
        CREATE TABLE IF NOT EXISTS raw_payloads (
            raw_id TEXT PRIMARY KEY,
            run_id TEXT,
            provider_id TEXT,
            target_kind TEXT,
            target_value TEXT,
            source_id TEXT,
            observed_at TEXT,
            payload_json TEXT
        );
        CREATE TABLE IF NOT EXISTS ai_labels (
            label_id TEXT PRIMARY KEY,
            account_id TEXT,
            tweet_id TEXT,
            label_scope TEXT,
            category_id TEXT,
            category_label TEXT,
            confidence REAL,
            tags_json TEXT,
            summary TEXT,
            rationale TEXT,
            model TEXT,
            run_id TEXT,
            generated_at TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_collection_items_tweet_id
            ON collection_items(tweet_id);
        CREATE INDEX IF NOT EXISTS idx_account_bookmarks_tweet_id
            ON account_bookmarks(tweet_id);
        CREATE INDEX IF NOT EXISTS idx_ai_labels_tweet_id
            ON ai_labels(tweet_id);
        """
    )


def _upsert_account(conn: sqlite3.Connection, profile: Any) -> None:
    account_id = getattr(profile, "account_id", None)
    if not account_id:
        return
    conn.execute(
        """
        INSERT INTO accounts (
            account_id, screen_name, user_id, display_name, url,
            metadata_json, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(account_id) DO UPDATE SET
            screen_name=excluded.screen_name,
            user_id=excluded.user_id,
            display_name=excluded.display_name,
            url=excluded.url,
            metadata_json=excluded.metadata_json,
            updated_at=excluded.updated_at
        """,
        (
            account_id,
            getattr(profile, "screen_name", None),
            getattr(profile, "user_id", None),
            getattr(profile, "display_name", None),
            getattr(profile, "url", None),
            json.dumps(_jsonable(getattr(profile, "metadata", {}) or {}), ensure_ascii=False),
            _iso(utc_now()),
        ),
    )


def _insert_provider_run(conn: sqlite3.Connection, attempt: Any) -> None:
    outcome = getattr(attempt, "outcome", None)
    if outcome is None:
        return
    key = "|".join(
        [
            str(getattr(attempt, "provider_id", outcome.adapter_id)),
            outcome.target.kind.value,
            outcome.target.value,
            _iso(outcome.started_at),
        ]
    )
    provider_run_id = _stable_digest(key)
    conn.execute(
        """
        INSERT INTO provider_runs (
            provider_run_id, provider_id, target_kind, target_value, status,
            started_at, finished_at, item_count, error_type, error_message,
            metadata_json, evidence_path
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(provider_run_id) DO UPDATE SET
            status=excluded.status,
            finished_at=excluded.finished_at,
            item_count=excluded.item_count,
            error_type=excluded.error_type,
            error_message=excluded.error_message,
            metadata_json=excluded.metadata_json,
            evidence_path=excluded.evidence_path
        """,
        (
            provider_run_id,
            getattr(attempt, "provider_id", outcome.adapter_id),
            outcome.target.kind.value,
            outcome.target.value,
            outcome.status.value,
            _iso(outcome.started_at),
            _iso(outcome.finished_at),
            len(outcome.items),
            outcome.error_type,
            outcome.error_message,
            json.dumps(_jsonable(outcome.metadata), ensure_ascii=False),
            str(getattr(attempt, "evidence_path", "") or ""),
        ),
    )


def _upsert_tweet(conn: sqlite3.Connection, row: dict[str, Any]) -> None:
    existing = conn.execute(
        "SELECT url, author_screen_name, text, created_at, first_observed_at, role, raw_json "
        "FROM tweets WHERE tweet_id = ?",
        (row["tweet_id"],),
    ).fetchone()
    observed_at = _iso(row.get("observed_at") or utc_now())
    if existing is not None:
        row = {
            **row,
            "url": row.get("url") or existing[0],
            "author": row.get("author") or existing[1],
            "text": row.get("text") or existing[2],
            "created_at": row.get("created_at") or existing[3],
            "first_observed_at": existing[4] or observed_at,
            "role": _preferred_role(existing[5], row.get("role")),
            "raw": row.get("raw") or _loads_json(existing[6]),
        }
    else:
        row["first_observed_at"] = observed_at
    conn.execute(
        """
        INSERT INTO tweets (
            tweet_id, url, author_screen_name, text, created_at,
            first_observed_at, last_observed_at, role, collection_kind,
            providers_json, raw_json, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(tweet_id) DO UPDATE SET
            url=excluded.url,
            author_screen_name=excluded.author_screen_name,
            text=excluded.text,
            created_at=excluded.created_at,
            last_observed_at=excluded.last_observed_at,
            role=excluded.role,
            collection_kind=excluded.collection_kind,
            providers_json=excluded.providers_json,
            raw_json=excluded.raw_json,
            updated_at=excluded.updated_at
        """,
        (
            row["tweet_id"],
            row.get("url"),
            row.get("author"),
            row.get("text"),
            _iso(row.get("created_at")),
            _iso(row.get("first_observed_at")),
            observed_at,
            row.get("role"),
            row.get("collection_kind"),
            json.dumps(_jsonable(row.get("providers", [])), ensure_ascii=False),
            json.dumps(_jsonable(row.get("raw", {})), ensure_ascii=False),
            _iso(utc_now()),
        ),
    )


def _preferred_role(existing: str | None, incoming: str | None) -> str | None:
    order = {"bookmark_root": 3, "target_tweet": 2, "quoted_tweet": 1, None: 0}
    return incoming if order.get(incoming, 0) > order.get(existing, 0) else existing


def _raw_payload_row(
    item: XItem,
    target: AcquisitionTarget,
    collection_kind: str,
    run_id: str,
) -> dict[str, Any]:
    provider_id = ",".join(str(value) for value in item.raw.get("_providers", [])) or "unknown"
    key = json.dumps(
        {
            "run_id": run_id,
            "provider_id": provider_id,
            "source_id": item.source_id,
            "raw": _jsonable(item.raw),
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    return {
        "raw_id": _stable_digest(key),
        "run_id": run_id,
        "provider_id": provider_id,
        "target_kind": target.kind.value,
        "target_value": target.value,
        "collection_kind": collection_kind,
        "source_id": item.source_id,
        "observed_at": item.observed_at,
        "payload": item.raw,
    }


def _classification_row(
    classification: Any,
    *,
    label_scope: str,
    account_id: str | None,
    run_id: str | None,
    model: str | None,
    generated_at: datetime | None,
) -> tuple[Any, ...]:
    source_id = str(classification.source_id)
    resolved_model = model or str(getattr(classification, "model", ""))
    resolved_generated_at = (
        generated_at or getattr(classification, "generated_at", None) or utc_now()
    )
    label_id = _stable_digest(
        "|".join(
            [account_id or "global", label_scope, source_id, resolved_model, run_id or ""]
        )
    )
    return (
        label_id,
        account_id,
        source_id,
        label_scope,
        getattr(classification, "category_id", None),
        getattr(classification, "category_label", None),
        float(getattr(classification, "confidence", 0.0)),
        json.dumps(_jsonable(getattr(classification, "tags", ())), ensure_ascii=False),
        getattr(classification, "summary", ""),
        getattr(classification, "rationale", ""),
        resolved_model,
        run_id,
        _iso(resolved_generated_at),
    )


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
        "raw": item.raw,
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
        "raw": raw,
    }


def _merge_tweet(existing: dict[str, Any] | None, incoming: dict[str, Any]) -> dict[str, Any]:
    if existing is None:
        return incoming
    merged = dict(existing)
    for key, value in incoming.items():
        if merged.get(key) in (None, "", []):
            merged[key] = value
    merged["role"] = _preferred_role(merged.get("role"), incoming.get("role"))
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
        media_id = _stable_digest(f"{tweet_id}:{url}", digest_size=8)
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
    if target_path.exists() and target_path.stat().st_size > 0:
        row["download_status"] = "ok"
        row["local_path"] = str(target_path)
        row["bytes"] = target_path.stat().st_size
        return
    request = Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urlopen(request, timeout=timeout_seconds) as response:  # noqa: S310
            data = response.read()
            target_path.write_bytes(data)
            row["download_status"] = "ok"
            row["local_path"] = str(target_path)
            row["bytes"] = len(data)
            row["content_type"] = response.headers.get("content-type")
    except (OSError, URLError, TimeoutError, IncompleteRead) as exc:
        row["download_status"] = "error"
        row["download_error"] = f"{type(exc).__name__}: {exc}"


def _write_media_progress(
    path: Path,
    media_rows: list[dict[str, Any]],
    *,
    current_index: int,
    started: float,
    finished: bool = False,
) -> None:
    total = len(media_rows)
    counts: dict[str, int] = {}
    for row in media_rows:
        status = str(row.get("download_status") or "pending")
        counts[status] = counts.get(status, 0) + 1
    done = sum(counts.get(status, 0) for status in ("ok", "error", "skipped"))
    elapsed = max(0.001, time.monotonic() - started)
    rate = done / elapsed if done else 0.0
    remaining = max(0, total - done)
    payload = {
        "updated_at": utc_now().isoformat(),
        "finished": finished,
        "total": total,
        "done": done,
        "remaining": remaining,
        "current_index": current_index,
        "ok": counts.get("ok", 0),
        "error": counts.get("error", 0),
        "skipped": counts.get("skipped", 0),
        "pending": counts.get("pending", 0),
        "elapsed_seconds": elapsed,
        "items_per_second": rate,
        "estimated_remaining_seconds": remaining / rate if rate > 0 else None,
    }
    path.write_text(
        json.dumps(_jsonable(payload), ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def _media_extension(url: str) -> str:
    suffix = Path(urlparse(url).path).suffix
    if suffix:
        return suffix
    return mimetypes.guess_extension(urlparse(url).path) or ".bin"


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


def _collection_id(collection_kind: str, target: AcquisitionTarget, account_id: str | None) -> str:
    return "|".join([account_id or "global", collection_kind, target.kind.value, target.value])


def _stable_run_id(collection_kind: str, target: AcquisitionTarget, account_id: str | None) -> str:
    payload = "|".join(
        [account_id or "global", collection_kind, target.kind.value, target.value, _iso(utc_now())]
    )
    return _stable_digest(payload, digest_size=10)


def _stable_digest(value: str, *, digest_size: int = 20) -> str:
    return hashlib.blake2b(value.encode("utf-8"), digest_size=digest_size).hexdigest()


def _write_jsonl(path: Path, rows) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(_jsonable(row), ensure_ascii=False, sort_keys=True) + "\n")


def _loads_json(value: str | None) -> Any:
    if not value:
        return {}
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return {}


def _iso(value: Any) -> str | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


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
