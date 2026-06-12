from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from research_x.memory.document_hashes import memory_document_source_hash, text_hash
from research_x.memory.schema import ensure_memory_schema

DEFAULT_RETRIEVAL_TEXT_PROFILES = ("raw_compact", "contextual_bm25")
RETRIEVAL_TEXT_BUILDER_VERSION = "retrieval-text-profiles-v1"


@dataclass(frozen=True)
class RetrievalTextBuildSummary:
    db_path: str
    profiles: tuple[str, ...]
    documents: int
    profile_rows: int
    fts_rows: int
    rebuilt: bool

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RetrievalTextCoverage:
    db_path: str
    documents: int
    profile_rows: int
    fts_rows: int
    by_profile: dict[str, int]
    missing_by_profile: dict[str, int]
    stale_by_profile: dict[str, int]
    citation_included_rows: int
    orphaned_fts_rows: int
    profiles_missing_fts_rows: int

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_retrieval_text_profiles(
    db_path: str | Path,
    *,
    profiles: tuple[str, ...] = DEFAULT_RETRIEVAL_TEXT_PROFILES,
    limit: int | None = None,
    rebuild: bool = True,
) -> RetrievalTextBuildSummary:
    path = Path(db_path)
    now = _utc_now()
    selected_profiles = _normalize_profiles(profiles)
    with sqlite3.connect(path, timeout=60) as conn:
        conn.row_factory = sqlite3.Row
        ensure_memory_schema(conn)
        documents = _document_rows(conn, limit=limit)
        if rebuild:
            _delete_profiles(conn, selected_profiles)
        rows = _profile_rows(documents, profiles=selected_profiles, now=now)
        _upsert_profiles(conn, rows, refresh_fts=not rebuild)
        conn.commit()
        fts_rows = _fts_count(conn)
    return RetrievalTextBuildSummary(
        db_path=str(path),
        profiles=selected_profiles,
        documents=len(documents),
        profile_rows=len(rows),
        fts_rows=fts_rows,
        rebuilt=rebuild,
    )


def retrieval_text_coverage(db_path: str | Path) -> RetrievalTextCoverage:
    path = Path(db_path)
    with sqlite3.connect(path, timeout=60) as conn:
        conn.row_factory = sqlite3.Row
        ensure_memory_schema(conn)
        documents = _document_rows(conn, limit=None)
        profile_rows = int(
            conn.execute("SELECT COUNT(*) FROM memory_retrieval_text_profiles").fetchone()[0]
        )
        fts_rows = _fts_count(conn)
        by_profile = {
            str(row["retrieval_text_profile"]): int(row["count"])
            for row in conn.execute(
                """
                SELECT retrieval_text_profile, COUNT(*) AS count
                FROM memory_retrieval_text_profiles
                GROUP BY retrieval_text_profile
                ORDER BY retrieval_text_profile
                """
            ).fetchall()
        }
        stale_by_profile: dict[str, int] = {}
        expected: dict[str, set[str]] = {}
        actual: dict[str, set[str]] = {}
        for doc in documents:
            for row in _profile_rows((doc,), profiles=DEFAULT_RETRIEVAL_TEXT_PROFILES, now=""):
                expected.setdefault(str(row["retrieval_text_profile"]), set()).add(
                    str(row["doc_id"])
                )
        profile_records = conn.execute(
            """
            SELECT p.profile_id, p.doc_id, p.retrieval_text_profile, p.source_doc_hash,
                   d.title, d.body, d.compact_text, d.metadata_json
            FROM memory_retrieval_text_profiles p
            LEFT JOIN memory_documents d ON d.doc_id = p.doc_id
            """
        ).fetchall()
        profile_ids = {str(record["profile_id"]) for record in profile_records}
        for record in profile_records:
            profile = str(record["retrieval_text_profile"])
            doc_id = str(record["doc_id"])
            actual.setdefault(profile, set()).add(doc_id)
            if record["title"] is None:
                stale_by_profile[profile] = stale_by_profile.get(profile, 0) + 1
                continue
            if str(record["source_doc_hash"] or "") != memory_document_source_hash(record):
                stale_by_profile[profile] = stale_by_profile.get(profile, 0) + 1
        citation_included_rows = int(
            conn.execute(
                """
                SELECT COUNT(*)
                FROM memory_retrieval_text_profiles
                WHERE citation_excluded != 1
                """
            ).fetchone()[0]
        )
        fts_profile_ids = tuple(
            str(row["profile_id"])
            for row in conn.execute("SELECT profile_id FROM memory_retrieval_text_fts")
        )
        fts_profile_id_set = set(fts_profile_ids)
        orphaned_fts_rows = sum(
            1 for profile_id in fts_profile_ids if profile_id not in profile_ids
        )
        profiles_missing_fts_rows = sum(
            1 for profile_id in profile_ids if profile_id not in fts_profile_id_set
        )
        missing_by_profile = {
            profile: max(0, len(doc_ids - actual.get(profile, set())))
            for profile, doc_ids in expected.items()
        }
    return RetrievalTextCoverage(
        db_path=str(path),
        documents=len(documents),
        profile_rows=profile_rows,
        fts_rows=fts_rows,
        by_profile=by_profile,
        missing_by_profile={key: value for key, value in missing_by_profile.items() if value},
        stale_by_profile={key: value for key, value in stale_by_profile.items() if value},
        citation_included_rows=citation_included_rows,
        orphaned_fts_rows=orphaned_fts_rows,
        profiles_missing_fts_rows=profiles_missing_fts_rows,
    )


def retrieval_text_summary_json(
    summary: RetrievalTextBuildSummary | RetrievalTextCoverage,
) -> str:
    return json.dumps(summary.as_dict(), ensure_ascii=False, indent=2, sort_keys=True)


def format_retrieval_text_summary(
    summary: RetrievalTextBuildSummary | RetrievalTextCoverage,
) -> str:
    data = summary.as_dict()
    lines = [f"db: {data['db_path']}"]
    for key, value in data.items():
        if key == "db_path":
            continue
        lines.append(f"{key}: {value}")
    return "\n".join(lines)


def _document_rows(conn: sqlite3.Connection, *, limit: int | None) -> tuple[sqlite3.Row, ...]:
    sql = """
        SELECT
            doc_id, doc_type, author_screen_name, title, body, compact_text,
            metadata_json, source_doc_hash
        FROM memory_documents
        ORDER BY observed_at DESC, doc_id
    """
    if limit is not None:
        sql += " LIMIT ?"
        return tuple(conn.execute(sql, (max(0, limit),)).fetchall())
    return tuple(conn.execute(sql).fetchall())


def _profile_rows(
    documents: tuple[sqlite3.Row, ...],
    *,
    profiles: tuple[str, ...],
    now: str,
) -> tuple[dict[str, Any], ...]:
    rows: list[dict[str, Any]] = []
    for doc in documents:
        source_hash = str(doc["source_doc_hash"] or memory_document_source_hash(doc))
        for profile in profiles:
            text = _retrieval_text_for_profile(doc, profile=profile)
            if not text:
                continue
            rows.append(
                {
                    "profile_id": _profile_id(str(doc["doc_id"]), profile, source_hash),
                    "doc_id": str(doc["doc_id"]),
                    "retrieval_text_profile": profile,
                    "retrieval_text": text,
                    "source_doc_hash": source_hash,
                    "citation_excluded": 1,
                    "created_at": now,
                    "metadata_json": json.dumps(
                        {
                            "builder_version": RETRIEVAL_TEXT_BUILDER_VERSION,
                            "contract": "retrieval_text_profile_is_projection_not_source",
                            "doc_type": doc["doc_type"],
                        },
                        ensure_ascii=False,
                        sort_keys=True,
                    ),
                }
            )
    return tuple(rows)


def _retrieval_text_for_profile(row: sqlite3.Row, *, profile: str) -> str:
    compact = str(row["compact_text"] or row["body"] or "").strip()
    if profile == "raw_compact":
        return compact
    if profile == "contextual_bm25":
        metadata = _compact_metadata(str(row["metadata_json"] or ""))
        parts = (
            f"title: {row['title']}" if row["title"] else "",
            f"author: {row['author_screen_name']}" if row["author_screen_name"] else "",
            f"type: {row['doc_type']}" if row["doc_type"] else "",
            metadata,
            f"text: {compact}" if compact else "",
        )
        return " | ".join(part for part in parts if part)
    raise ValueError(f"unknown retrieval text profile: {profile}")


def _compact_metadata(value: str) -> str:
    if not value:
        return ""
    try:
        metadata = json.loads(value)
    except json.JSONDecodeError:
        return ""
    if not isinstance(metadata, dict):
        return ""
    useful = {
        key: metadata.get(key)
        for key in (
            "url",
            "role",
            "collection_kind",
            "labels",
            "type",
            "download_status",
            "media_id",
        )
        if metadata.get(key)
    }
    if not useful:
        return ""
    return f"metadata: {json.dumps(useful, ensure_ascii=False, sort_keys=True)}"


def _upsert_profiles(
    conn: sqlite3.Connection,
    rows: tuple[dict[str, Any], ...],
    *,
    refresh_fts: bool,
) -> None:
    if not rows:
        return
    conn.executemany(
        """
        INSERT INTO memory_retrieval_text_profiles (
            profile_id, doc_id, retrieval_text_profile, retrieval_text,
            source_doc_hash, citation_excluded, created_at, metadata_json
        )
        VALUES (
            :profile_id, :doc_id, :retrieval_text_profile, :retrieval_text,
            :source_doc_hash, :citation_excluded, :created_at, :metadata_json
        )
        ON CONFLICT(profile_id) DO UPDATE SET
            retrieval_text=excluded.retrieval_text,
            source_doc_hash=excluded.source_doc_hash,
            citation_excluded=excluded.citation_excluded,
            created_at=excluded.created_at,
            metadata_json=excluded.metadata_json
        """,
        rows,
    )
    if refresh_fts:
        conn.executemany(
            "DELETE FROM memory_retrieval_text_fts WHERE profile_id = ?",
            [(row["profile_id"],) for row in rows],
        )
    conn.executemany(
        """
        INSERT INTO memory_retrieval_text_fts (
            profile_id, doc_id, retrieval_text_profile, retrieval_text
        )
        VALUES (?, ?, ?, ?)
        """,
        [
            (
                row["profile_id"],
                row["doc_id"],
                row["retrieval_text_profile"],
                row["retrieval_text"],
            )
            for row in rows
        ],
    )


def _delete_profiles(conn: sqlite3.Connection, profiles: tuple[str, ...]) -> None:
    if not profiles:
        return
    placeholders = ",".join("?" for _ in profiles)
    conn.execute(
        f"""
        DELETE FROM memory_retrieval_text_fts
        WHERE retrieval_text_profile IN ({placeholders})
        """,
        profiles,
    )
    conn.execute(
        f"""
        DELETE FROM memory_retrieval_text_profiles
        WHERE retrieval_text_profile IN ({placeholders})
        """,
        profiles,
    )


def _fts_count(conn: sqlite3.Connection) -> int:
    return int(conn.execute("SELECT COUNT(*) FROM memory_retrieval_text_fts").fetchone()[0])


def _normalize_profiles(profiles: tuple[str, ...]) -> tuple[str, ...]:
    normalized: list[str] = []
    allowed = set(DEFAULT_RETRIEVAL_TEXT_PROFILES)
    for profile in profiles:
        value = profile.strip()
        if value not in allowed:
            raise ValueError(
                "retrieval text profile must be one of: "
                + ", ".join(DEFAULT_RETRIEVAL_TEXT_PROFILES)
            )
        if value not in normalized:
            normalized.append(value)
    return tuple(normalized) or DEFAULT_RETRIEVAL_TEXT_PROFILES


def _profile_id(doc_id: str, profile: str, source_hash: str) -> str:
    return text_hash("|".join(("retrieval-text", doc_id, profile, source_hash)))[:32]


def _utc_now() -> str:
    return datetime.now(tz=UTC).isoformat()
