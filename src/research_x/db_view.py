from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class DisplayRow:
    position: int | None
    account_id: str | None
    tweet_id: str
    author: str | None
    url: str | None
    text: str | None
    category: str | None = None
    source: str | None = None


def load_display_rows(
    db_path: str | Path,
    *,
    account: str | None = None,
    kind: str = "bookmarks",
    limit: int = 20,
) -> list[DisplayRow]:
    path = Path(db_path)
    if not path.exists():
        raise FileNotFoundError(f"database not found: {path}")
    resolved_limit = max(1, limit)
    with sqlite3.connect(path) as conn:
        conn.row_factory = sqlite3.Row
        if kind == "bookmarks":
            return _bookmark_rows(conn, account=account, limit=resolved_limit)
        if kind == "tweets":
            return _tweet_rows(conn, account=account, limit=resolved_limit)
        if kind == "all":
            rows = _bookmark_rows(conn, account=account, limit=resolved_limit)
            if len(rows) < resolved_limit:
                rows.extend(
                    _tweet_rows(conn, account=account, limit=resolved_limit - len(rows))
                )
            return rows
    raise ValueError(f"unsupported kind: {kind}")


def rows_as_dicts(rows: list[DisplayRow]) -> list[dict[str, Any]]:
    return [
        {
            "position": row.position,
            "account_id": row.account_id,
            "tweet_id": row.tweet_id,
            "author": row.author,
            "url": row.url,
            "text": row.text,
            "category": row.category,
            "source": row.source,
        }
        for row in rows
    ]


def format_display_rows(rows: list[DisplayRow], *, json_output: bool = False) -> str:
    if json_output:
        return json.dumps(rows_as_dicts(rows), ensure_ascii=False, indent=2, sort_keys=True)
    if not rows:
        return "(no rows)"
    blocks: list[str] = []
    for index, row in enumerate(rows, start=1):
        header_parts = [f"#{index}"]
        if row.position is not None:
            header_parts.append(f"pos={row.position}")
        if row.account_id:
            header_parts.append(f"account={row.account_id}")
        if row.category:
            header_parts.append(f"category={row.category}")
        if row.source:
            header_parts.append(f"source={row.source}")
        header_parts.append(f"id={row.tweet_id}")
        if row.author:
            header_parts.append(f"@{row.author}")
        blocks.append(
            "\n".join(
                [
                    " ".join(header_parts),
                    f"url: {row.url or ''}",
                    f"text: {_single_line(row.text)}",
                ]
            )
        )
    return "\n\n".join(blocks)


def _bookmark_rows(
    conn: sqlite3.Connection,
    *,
    account: str | None,
    limit: int,
) -> list[DisplayRow]:
    rows = conn.execute(
        """
        SELECT
            ab.bookmark_index AS position,
            ab.account_id AS account_id,
            t.tweet_id AS tweet_id,
            t.author_screen_name AS author,
            t.url AS url,
            t.text AS text,
            (
                SELECT al.category_label
                FROM ai_labels al
                WHERE al.tweet_id = t.tweet_id
                  AND (al.account_id = ab.account_id OR al.account_id IS NULL)
                  AND al.label_scope = 'bookmarks'
                ORDER BY al.generated_at DESC
                LIMIT 1
            ) AS category
        FROM account_bookmarks ab
        JOIN tweets t ON t.tweet_id = ab.tweet_id
        WHERE (? IS NULL OR ab.account_id = ?)
        ORDER BY ab.bookmark_index ASC, ab.observed_at ASC
        LIMIT ?
        """,
        (account, account, limit),
    ).fetchall()
    return [
        DisplayRow(
            position=row["position"],
            account_id=row["account_id"],
            tweet_id=row["tweet_id"],
            author=row["author"],
            url=row["url"],
            text=row["text"],
            category=row["category"],
            source="bookmarks",
        )
        for row in rows
    ]


def _tweet_rows(
    conn: sqlite3.Connection,
    *,
    account: str | None,
    limit: int,
) -> list[DisplayRow]:
    rows = conn.execute(
        """
        SELECT
            ci.position AS position,
            ci.account_id AS account_id,
            ci.collection_kind AS source,
            t.tweet_id AS tweet_id,
            t.author_screen_name AS author,
            t.url AS url,
            t.text AS text,
            (
                SELECT al.category_label
                FROM ai_labels al
                WHERE al.tweet_id = t.tweet_id
                ORDER BY al.generated_at DESC
                LIMIT 1
            ) AS category
        FROM collection_items ci
        JOIN tweets t ON t.tweet_id = ci.tweet_id
        WHERE ci.collection_kind <> 'bookmarks'
          AND (? IS NULL OR ci.account_id = ?)
        ORDER BY ci.observed_at DESC, ci.position ASC
        LIMIT ?
        """,
        (account, account, limit),
    ).fetchall()
    return [
        DisplayRow(
            position=row["position"],
            account_id=row["account_id"],
            tweet_id=row["tweet_id"],
            author=row["author"],
            url=row["url"],
            text=row["text"],
            category=row["category"],
            source=row["source"],
        )
        for row in rows
    ]


def _single_line(value: str | None) -> str:
    if value is None:
        return ""
    return " ".join(str(value).split())
