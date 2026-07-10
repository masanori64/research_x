from __future__ import annotations

import hashlib
import json
import sqlite3
from collections import Counter
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from research_x.memory import source_refs
from research_x.memory.schema import ensure_memory_schema


@dataclass(frozen=True)
class SourceManifestSyncSummary:
    db_path: str
    observation_run_id: str
    sources: int
    observations: int
    by_source_kind: dict[str, int]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def sync_x_source_manifest(
    db_path: str | Path,
    *,
    observation_run_id: str | None = None,
    observation_completeness: str | None = None,
    observed_at: str | None = None,
) -> SourceManifestSyncSummary:
    path = Path(db_path)
    if not path.exists():
        raise FileNotFoundError(f"database not found: {path}")
    timestamp = observed_at or _utcnow()
    run_id = observation_run_id or f"x-source-manifest:{timestamp}"
    with sqlite3.connect(path, timeout=60) as conn:
        conn.row_factory = sqlite3.Row
        ensure_memory_schema(conn)
        records = tuple(
            _iter_x_source_records(
                conn,
                observed_at=timestamp,
                observation_completeness=observation_completeness,
            )
        )
        for record in records:
            _upsert_source(conn, record)
            _upsert_observation(conn, record, observation_run_id=run_id)
        by_kind = Counter(record.source_kind for record in records)
    return SourceManifestSyncSummary(
        db_path=str(path),
        observation_run_id=run_id,
        sources=len(records),
        observations=len(records),
        by_source_kind=dict(sorted(by_kind.items())),
    )


@dataclass(frozen=True)
class _SourceRecord:
    source_ref: str
    source_kind: str
    source_uri: str | None
    source_title: str | None
    source_owner: str | None
    raw_hash: str
    normalized_content_hash: str | None
    relation_hash: str | None
    media_hash: str | None
    source_status: str
    visibility: str
    first_observed_at: str
    last_observed_at: str
    updated_at: str
    observation_kind: str
    observation_completeness: str
    observed_at: str
    metadata: dict[str, Any]


def _iter_x_source_records(
    conn: sqlite3.Connection,
    *,
    observed_at: str,
    observation_completeness: str | None = None,
) -> Iterable[_SourceRecord]:
    if _table_exists(conn, "tweets"):
        for row in conn.execute("SELECT * FROM tweets ORDER BY tweet_id"):
            data = _row_dict(row)
            yield _record(
                table_name="tweets",
                source_ref=source_refs.x_tweet(data["tweet_id"]),
                source_kind="tweet",
                data=data,
                source_uri=data.get("url"),
                source_title=_short_title(data.get("text")),
                source_owner=data.get("author_screen_name"),
                normalized_payload={
                    "author_screen_name": data.get("author_screen_name"),
                    "collection_kind": data.get("collection_kind"),
                    "role": data.get("role"),
                    "text": data.get("text"),
                    "tweet_id": data.get("tweet_id"),
                    "url": data.get("url"),
                },
                first_observed_at=data.get("first_observed_at"),
                last_observed_at=data.get("last_observed_at"),
                updated_at=data.get("updated_at"),
                observed_at=observed_at,
                observation_completeness=observation_completeness,
            )
    if _table_exists(conn, "account_bookmarks"):
        for row in conn.execute(
            "SELECT * FROM account_bookmarks ORDER BY account_id, tweet_id"
        ):
            data = _row_dict(row)
            yield _record(
                table_name="account_bookmarks",
                source_ref=source_refs.x_bookmark(data["account_id"], data["tweet_id"]),
                source_kind="account_bookmark",
                data=data,
                source_uri=None,
                source_title=f"bookmark {data['account_id']} {data['tweet_id']}",
                source_owner=data.get("account_id"),
                normalized_payload={
                    "account_id": data.get("account_id"),
                    "bookmark_index": data.get("bookmark_index"),
                    "tweet_id": data.get("tweet_id"),
                },
                first_observed_at=data.get("observed_at"),
                last_observed_at=data.get("observed_at"),
                updated_at=data.get("observed_at"),
                observed_at=observed_at,
                observation_completeness=observation_completeness,
            )
    if _table_exists(conn, "collection_items"):
        for row in conn.execute(
            """
            SELECT * FROM collection_items
            ORDER BY collection_id, tweet_id, position
            """
        ):
            data = _row_dict(row)
            yield _record(
                table_name="collection_items",
                source_ref=source_refs.x_collection(
                    data["collection_id"],
                    data["tweet_id"],
                ),
                source_kind="collection_item",
                data=data,
                source_uri=None,
                source_title=f"collection {data['collection_id']} {data['tweet_id']}",
                source_owner=data.get("account_id"),
                normalized_payload={
                    "account_id": data.get("account_id"),
                    "collection_id": data.get("collection_id"),
                    "collection_kind": data.get("collection_kind"),
                    "position": data.get("position"),
                    "target_kind": data.get("target_kind"),
                    "target_value": data.get("target_value"),
                    "tweet_id": data.get("tweet_id"),
                },
                first_observed_at=data.get("observed_at"),
                last_observed_at=data.get("observed_at"),
                updated_at=data.get("observed_at"),
                observed_at=observed_at,
                observation_completeness=observation_completeness,
            )
    if _table_exists(conn, "tweet_edges"):
        for row in conn.execute(
            """
            SELECT * FROM tweet_edges
            ORDER BY parent_tweet_id, child_tweet_id, relation
            """
        ):
            data = _row_dict(row)
            relation_hash = _stable_hash(data)
            yield _record(
                table_name="tweet_edges",
                source_ref=source_refs.x_edge(
                    data["relation"],
                    data["parent_tweet_id"],
                    data["child_tweet_id"],
                ),
                source_kind="tweet_edge",
                data=data,
                source_uri=None,
                source_title=(
                    f"{data['parent_tweet_id']} {data['relation']} "
                    f"{data['child_tweet_id']}"
                ),
                source_owner=None,
                normalized_payload=data,
                relation_hash=relation_hash,
                observed_at=observed_at,
                observation_completeness=observation_completeness,
            )
    if _table_exists(conn, "media"):
        for row in conn.execute("SELECT * FROM media ORDER BY media_id"):
            data = _row_dict(row)
            media_hash = _stable_hash(
                {
                    "alt_text": data.get("alt_text"),
                    "bytes": data.get("bytes"),
                    "content_type": data.get("content_type"),
                    "media_id": data.get("media_id"),
                    "tweet_id": data.get("tweet_id"),
                    "type": data.get("type"),
                    "url": data.get("url"),
                }
            )
            yield _record(
                table_name="media",
                source_ref=source_refs.x_media(data["media_id"]),
                source_kind="media",
                data=data,
                source_uri=data.get("url") or data.get("local_path"),
                source_title=data.get("alt_text") or data.get("type"),
                source_owner=None,
                normalized_payload={
                    "alt_text": data.get("alt_text"),
                    "media_id": data.get("media_id"),
                    "tweet_id": data.get("tweet_id"),
                    "type": data.get("type"),
                    "url": data.get("url"),
                },
                media_hash=media_hash,
                source_status=data.get("download_status") or "available",
                observed_at=observed_at,
                observation_completeness=observation_completeness,
            )
    if _table_exists(conn, "raw_payloads"):
        for row in conn.execute("SELECT * FROM raw_payloads ORDER BY raw_id"):
            data = _row_dict(row)
            yield _record(
                table_name="raw_payloads",
                source_ref=source_refs.x_raw_payload(data["raw_id"]),
                source_kind="raw_payload",
                data=data,
                source_uri=None,
                source_title=f"{data.get('provider_id')} {data.get('target_kind')}",
                source_owner=data.get("provider_id"),
                normalized_payload={
                    "payload_json": data.get("payload_json"),
                    "provider_id": data.get("provider_id"),
                    "source_id": data.get("source_id"),
                    "target_kind": data.get("target_kind"),
                    "target_value": data.get("target_value"),
                },
                first_observed_at=data.get("observed_at"),
                last_observed_at=data.get("observed_at"),
                updated_at=data.get("observed_at"),
                observed_at=observed_at,
                observation_completeness=observation_completeness,
            )
    if _table_exists(conn, "provider_runs"):
        for row in conn.execute("SELECT * FROM provider_runs ORDER BY provider_run_id"):
            data = _row_dict(row)
            yield _record(
                table_name="provider_runs",
                source_ref=source_refs.x_provider_run(data["provider_run_id"]),
                source_kind="provider_run",
                data=data,
                source_uri=data.get("evidence_path"),
                source_title=(
                    f"{data.get('provider_id')} "
                    f"{data.get('target_kind')}:{data.get('target_value')}"
                ),
                source_owner=data.get("provider_id"),
                normalized_payload={
                    "item_count": data.get("item_count"),
                    "provider_id": data.get("provider_id"),
                    "status": data.get("status"),
                    "target_kind": data.get("target_kind"),
                    "target_value": data.get("target_value"),
                },
                source_status=data.get("status") or "available",
                first_observed_at=data.get("started_at"),
                last_observed_at=data.get("finished_at") or data.get("started_at"),
                updated_at=data.get("finished_at") or data.get("started_at"),
                observed_at=observed_at,
                observation_completeness=observation_completeness,
            )
    if _table_exists(conn, "accounts"):
        for row in conn.execute("SELECT * FROM accounts ORDER BY account_id"):
            data = _row_dict(row)
            yield _record(
                table_name="accounts",
                source_ref=source_refs.x_account(data["account_id"]),
                source_kind="account",
                data=data,
                source_uri=data.get("profile_url"),
                source_title=data.get("screen_name") or data.get("account_id"),
                source_owner=data.get("account_id"),
                normalized_payload={
                    "account_id": data.get("account_id"),
                    "screen_name": data.get("screen_name"),
                    "display_name": data.get("display_name"),
                },
                first_observed_at=data.get("first_observed_at"),
                last_observed_at=data.get("last_observed_at"),
                updated_at=data.get("updated_at"),
                observed_at=observed_at,
                observation_completeness=observation_completeness,
            )


def _record(
    *,
    table_name: str,
    source_ref: str,
    source_kind: str,
    data: dict[str, Any],
    source_uri: str | None,
    source_title: str | None,
    source_owner: str | None,
    normalized_payload: dict[str, Any],
    observed_at: str,
    relation_hash: str | None = None,
    media_hash: str | None = None,
    source_status: str = "available",
    observation_completeness: str | None = None,
    first_observed_at: str | None = None,
    last_observed_at: str | None = None,
    updated_at: str | None = None,
) -> _SourceRecord:
    completeness = _infer_observation_completeness(
        table_name=table_name,
        data=data,
        explicit=observation_completeness,
    )
    return _SourceRecord(
        source_ref=source_ref,
        source_kind=source_kind,
        source_uri=source_uri,
        source_title=source_title,
        source_owner=source_owner,
        raw_hash=_stable_hash(data),
        normalized_content_hash=_stable_hash(normalized_payload),
        relation_hash=relation_hash,
        media_hash=media_hash,
        source_status=source_status,
        visibility="private",
        first_observed_at=first_observed_at or observed_at,
        last_observed_at=last_observed_at or observed_at,
        updated_at=updated_at or observed_at,
        observation_kind=f"{table_name}_sync",
        observation_completeness=completeness,
        observed_at=observed_at,
        metadata={
            "source_table": table_name,
            "source_ref": source_ref,
            "source_kind": source_kind,
            "observation_completeness": completeness,
            "provider_run_id": data.get("provider_run_id"),
        },
    )


def _upsert_source(conn: sqlite3.Connection, record: _SourceRecord) -> None:
    conn.execute(
        """
        INSERT INTO memory_sources (
            source_ref, source_kind, source_type, source_uri, canonical_uri,
            source_title, source_owner, owner_scope, user_control_status,
            source_origin, lifecycle_status, upstream_ref, storage_ref_json,
            raw_hash, normalized_content_hash, relation_hash, media_hash,
            source_status, visibility, created_at, first_observed_at, last_observed_at,
            updated_at, metadata_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(source_ref) DO UPDATE SET
            source_kind=excluded.source_kind,
            source_type=excluded.source_type,
            source_uri=excluded.source_uri,
            canonical_uri=excluded.canonical_uri,
            source_title=excluded.source_title,
            source_owner=excluded.source_owner,
            owner_scope=excluded.owner_scope,
            user_control_status=excluded.user_control_status,
            source_origin=excluded.source_origin,
            lifecycle_status=excluded.lifecycle_status,
            upstream_ref=excluded.upstream_ref,
            storage_ref_json=excluded.storage_ref_json,
            raw_hash=excluded.raw_hash,
            normalized_content_hash=excluded.normalized_content_hash,
            relation_hash=excluded.relation_hash,
            media_hash=excluded.media_hash,
            source_status=excluded.source_status,
            visibility=excluded.visibility,
            last_observed_at=excluded.last_observed_at,
            updated_at=excluded.updated_at,
            metadata_json=excluded.metadata_json
        """,
        (
            record.source_ref,
            record.source_kind,
            record.source_kind,
            record.source_uri,
            record.source_uri,
            record.source_title,
            record.source_owner,
            record.source_owner or "user",
            "user_selected",
            "x_manifest_sync",
            "active",
            None,
            _json({"source_table": record.metadata.get("source_table")}),
            record.raw_hash,
            record.normalized_content_hash,
            record.relation_hash,
            record.media_hash,
            record.source_status,
            record.visibility,
            record.first_observed_at,
            record.first_observed_at,
            record.last_observed_at,
            record.updated_at,
            _json(record.metadata),
        ),
    )


def _upsert_observation(
    conn: sqlite3.Connection,
    record: _SourceRecord,
    *,
    observation_run_id: str,
) -> None:
    observation_id = _stable_hash(
        {
            "observation_run_id": observation_run_id,
            "source_ref": record.source_ref,
        }
    )
    conn.execute(
        """
        INSERT INTO memory_source_observations (
            observation_id, source_ref, observation_run_id, observation_kind,
            observation_completeness, provider_run_id, availability_status,
            raw_hash, normalized_content_hash, relation_hash, media_hash, fetched_at,
            observed_at, status, metadata_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(observation_id) DO UPDATE SET
            observation_completeness=excluded.observation_completeness,
            provider_run_id=excluded.provider_run_id,
            availability_status=excluded.availability_status,
            raw_hash=excluded.raw_hash,
            normalized_content_hash=excluded.normalized_content_hash,
            relation_hash=excluded.relation_hash,
            media_hash=excluded.media_hash,
            fetched_at=excluded.fetched_at,
            observed_at=excluded.observed_at,
            status=excluded.status,
            metadata_json=excluded.metadata_json
        """,
        (
            observation_id,
            record.source_ref,
            observation_run_id,
            record.observation_kind,
            record.observation_completeness,
            _provider_run_id(record.metadata),
            record.source_status,
            record.raw_hash,
            record.normalized_content_hash,
            record.relation_hash,
            record.media_hash,
            record.observed_at,
            record.observed_at,
            "observed",
            _json(record.metadata),
        ),
    )


def _infer_observation_completeness(
    *,
    table_name: str,
    data: dict[str, Any],
    explicit: str | None,
) -> str:
    if explicit:
        normalized = explicit.strip().casefold()
        if normalized not in {"complete", "partial", "unknown"}:
            raise ValueError(
                "observation_completeness must be complete, partial, or unknown"
            )
        return normalized
    signals = _observation_status_signals(data)
    if signals & {
        "rate_limited",
        "interrupted",
        "timeout",
        "manual_subset",
        "search_limited",
        "timeline_limited",
    }:
        return "partial"
    if signals & {"fixture", "legacy", "unknown", "missing_provider_metadata"}:
        return "unknown"
    if signals & {
        "local_full_scan",
        "full_scan",
        "exact_url_fetch",
        "cursor_exhausted",
        "bookmark_cursor_exhausted",
        "explicit_deleted",
        "deleted_response",
    }:
        return "complete"
    if table_name == "provider_runs":
        status = str(data.get("status") or "").casefold()
        if status in {"complete", "completed", "ok", "success", "exhausted"}:
            return "complete"
        if status in {"partial", "rate_limited", "interrupted", "timeout"}:
            return "partial"
        return "unknown"
    return "unknown"


def _observation_status_signals(data: dict[str, Any]) -> set[str]:
    status_keys = {
        "status",
        "download_status",
        "error_type",
        "run_status",
        "availability_status",
        "completion_status",
        "observation_status",
        "observation_completeness",
    }
    structured_keys = {
        "metadata_json",
        "providers_json",
        "raw_json",
        "payload_json",
    }
    signals: set[str] = set()
    for key in status_keys:
        signals.update(_signal_tokens(data.get(key)))
    for key in structured_keys:
        signals.update(_signal_tokens(_loads_json_value(data.get(key))))
    return signals


def _signal_tokens(value: Any) -> set[str]:
    tokens: set[str] = set()
    if value is None:
        return tokens
    if isinstance(value, dict):
        for key, nested in value.items():
            if _is_observation_signal_key(str(key)) or isinstance(nested, dict | list):
                tokens.update(_signal_tokens(nested))
        return tokens
    if isinstance(value, list):
        for item in value:
            tokens.update(_signal_tokens(item))
        return tokens
    text = str(value).strip()
    if not text:
        return tokens
    normalized = (
        text.casefold()
        .replace("-", "_")
        .replace(" ", "_")
        .replace("/", "_")
    )
    tokens.add(normalized)
    return tokens


def _is_observation_signal_key(key: str) -> bool:
    normalized = key.casefold().replace("-", "_").replace(" ", "_")
    return normalized in {
        "status",
        "state",
        "observation",
        "observation_status",
        "completion",
        "completion_status",
        "cursor",
        "cursor_status",
        "fetch_mode",
        "run_status",
        "availability_status",
    }


def _loads_json_value(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value


def _provider_run_id(metadata: dict[str, Any]) -> str | None:
    value = metadata.get("provider_run_id")
    return str(value) if value else None


def _table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    return (
        conn.execute(
            """
            SELECT 1
            FROM sqlite_master
            WHERE type = 'table' AND name = ?
            """,
            (table_name,),
        ).fetchone()
        is not None
    )


def _row_dict(row: sqlite3.Row) -> dict[str, Any]:
    return dict(row)


def _stable_hash(value: Any) -> str:
    return hashlib.sha256(_json(value).encode("utf-8")).hexdigest()


def _json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )


def _short_title(value: Any, *, limit: int = 120) -> str | None:
    if value is None:
        return None
    text = " ".join(str(value).split())
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def _utcnow() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
