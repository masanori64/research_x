from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from research_x.memory.artifact_roles import ArtifactRole
from research_x.memory.audit_events import record_audit_event
from research_x.memory.authority_levels import AuthorityLevel
from research_x.memory.human_oversight import classify_human_oversight
from research_x.memory.output_modes import OutputMode
from research_x.memory.schema import ensure_memory_schema


@dataclass(frozen=True)
class WorkingNote:
    working_note_id: str
    task_scope: str
    thread_scope: str | None
    title: str
    body: str
    source_refs: tuple[str, ...]
    artifact_refs: tuple[str, ...]
    content_hash: str
    retention_policy: str
    note_status: str
    created_at: str
    updated_at: str
    expires_at: str | None
    metadata: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["source_refs"] = list(self.source_refs)
        data["artifact_refs"] = list(self.artifact_refs)
        return data


@dataclass(frozen=True)
class WorkingNotePromotion:
    working_note_id: str
    source_ref: str
    artifact_id: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def create_working_note(
    db_path: str | Path,
    *,
    title: str,
    body: str,
    task_scope: str,
    thread_scope: str | None = None,
    source_refs: tuple[str, ...] = (),
    artifact_refs: tuple[str, ...] = (),
    retention_policy: str = "task",
    created_at: str | None = None,
    expires_at: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> WorkingNote:
    timestamp = created_at or _utcnow()
    normalized_source_refs = _dedupe(source_refs)
    normalized_artifact_refs = _dedupe(artifact_refs)
    content_hash = _stable_hash(
        {
            "artifact_refs": normalized_artifact_refs,
            "body": body,
            "source_refs": normalized_source_refs,
            "title": title,
        }
    )
    working_note_id = "working-note:" + _stable_hash(
        {
            "content_hash": content_hash,
            "task_scope": task_scope,
            "thread_scope": thread_scope,
            "title": title,
            "created_at": timestamp,
        }
    )[:24]
    with sqlite3.connect(db_path, timeout=60) as conn:
        ensure_memory_schema(conn)
        conn.execute(
            """
            INSERT INTO memory_working_notes (
                working_note_id, task_scope, thread_scope, title, body,
                source_refs_json, artifact_refs_json, content_hash,
                retention_policy, note_status, created_at, updated_at,
                expires_at, metadata_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                working_note_id,
                task_scope,
                thread_scope,
                title,
                body,
                _json(list(normalized_source_refs)),
                _json(list(normalized_artifact_refs)),
                content_hash,
                retention_policy,
                "active",
                timestamp,
                timestamp,
                expires_at,
                _json(metadata or {}),
            ),
        )
    note = read_working_note(db_path, working_note_id)
    if note is None:
        raise RuntimeError(f"working note was not created: {working_note_id}")
    return note


def append_working_note(
    db_path: str | Path,
    working_note_id: str,
    text: str,
    *,
    updated_at: str | None = None,
) -> WorkingNote:
    note = read_working_note(db_path, working_note_id)
    if note is None:
        raise KeyError(f"working note not found: {working_note_id}")
    timestamp = updated_at or _utcnow()
    body = note.body + ("\n" if note.body else "") + text
    content_hash = _stable_hash(
        {
            "artifact_refs": note.artifact_refs,
            "body": body,
            "source_refs": note.source_refs,
            "title": note.title,
        }
    )
    with sqlite3.connect(db_path, timeout=60) as conn:
        ensure_memory_schema(conn)
        conn.execute(
            """
            UPDATE memory_working_notes
            SET body = ?, content_hash = ?, updated_at = ?
            WHERE working_note_id = ?
            """,
            (body, content_hash, timestamp, working_note_id),
        )
    updated = read_working_note(db_path, working_note_id)
    if updated is None:
        raise RuntimeError(f"working note disappeared: {working_note_id}")
    return updated


def read_working_note(db_path: str | Path, working_note_id: str) -> WorkingNote | None:
    with sqlite3.connect(db_path, timeout=60) as conn:
        conn.row_factory = sqlite3.Row
        ensure_memory_schema(conn)
        row = conn.execute(
            """
            SELECT *
            FROM memory_working_notes
            WHERE working_note_id = ?
            """,
            (working_note_id,),
        ).fetchone()
    if row is None:
        return None
    return _note_from_row(row)


def link_working_note_to_artifacts(
    db_path: str | Path,
    working_note_id: str,
    *,
    source_refs: tuple[str, ...] = (),
    artifact_refs: tuple[str, ...] = (),
    updated_at: str | None = None,
) -> WorkingNote:
    note = read_working_note(db_path, working_note_id)
    if note is None:
        raise KeyError(f"working note not found: {working_note_id}")
    merged_sources = _dedupe((*note.source_refs, *source_refs))
    merged_artifacts = _dedupe((*note.artifact_refs, *artifact_refs))
    timestamp = updated_at or _utcnow()
    with sqlite3.connect(db_path, timeout=60) as conn:
        ensure_memory_schema(conn)
        conn.execute(
            """
            UPDATE memory_working_notes
            SET source_refs_json = ?, artifact_refs_json = ?, updated_at = ?
            WHERE working_note_id = ?
            """,
            (
                _json(list(merged_sources)),
                _json(list(merged_artifacts)),
                timestamp,
                working_note_id,
            ),
        )
    updated = read_working_note(db_path, working_note_id)
    if updated is None:
        raise RuntimeError(f"working note disappeared: {working_note_id}")
    return updated


def expire_working_note(
    db_path: str | Path,
    working_note_id: str,
    *,
    expired_at: str | None = None,
) -> WorkingNote:
    timestamp = expired_at or _utcnow()
    with sqlite3.connect(db_path, timeout=60) as conn:
        ensure_memory_schema(conn)
        conn.execute(
            """
            UPDATE memory_working_notes
            SET note_status = 'expired', updated_at = ?, expires_at = ?
            WHERE working_note_id = ?
            """,
            (timestamp, timestamp, working_note_id),
        )
    note = read_working_note(db_path, working_note_id)
    if note is None:
        raise KeyError(f"working note not found: {working_note_id}")
    return note


def promote_working_note_to_curated_source(
    db_path: str | Path,
    working_note_id: str,
    *,
    human_in_loop_approved: bool = False,
    approved_by: str | None = None,
    approval_note: str | None = None,
    promoted_at: str | None = None,
) -> WorkingNotePromotion:
    oversight = classify_human_oversight("working_note_promote")
    if oversight.requires_explicit_approval and not human_in_loop_approved:
        raise ValueError(
            "working note promotion requires explicit human-in-the-loop approval"
        )
    note = read_working_note(db_path, working_note_id)
    if note is None:
        raise KeyError(f"working note not found: {working_note_id}")
    timestamp = promoted_at or _utcnow()
    source_ref = f"working_note:{working_note_id}"
    artifact_id = f"curated_source:{working_note_id}"
    with sqlite3.connect(db_path, timeout=60) as conn:
        ensure_memory_schema(conn)
        conn.execute(
            """
            INSERT INTO memory_sources (
                source_ref, source_kind, source_uri, source_title, source_owner,
                raw_hash, normalized_content_hash, relation_hash, media_hash,
                source_status, visibility, first_observed_at, last_observed_at,
                updated_at, metadata_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(source_ref) DO UPDATE SET
                source_title=excluded.source_title,
                raw_hash=excluded.raw_hash,
                normalized_content_hash=excluded.normalized_content_hash,
                source_status=excluded.source_status,
                last_observed_at=excluded.last_observed_at,
                updated_at=excluded.updated_at,
                metadata_json=excluded.metadata_json
            """,
            (
                source_ref,
                "working_note",
                None,
                note.title,
                None,
                note.content_hash,
                note.content_hash,
                None,
                None,
                "available",
                "private",
                note.created_at,
                timestamp,
                timestamp,
                _json(
                    {
                        "artifact_role": ArtifactRole.CURATED_SOURCE.value,
                        "human_oversight": oversight.as_dict(),
                        "human_in_loop_approved": human_in_loop_approved,
                        "approved_by": approved_by,
                        "approval_note": approval_note,
                        "promoted_from_working_note_id": working_note_id,
                    }
                ),
            ),
        )
        conn.execute(
            """
            INSERT INTO memory_artifacts (
                artifact_id, artifact_role, artifact_kind, source_refs_json,
                content_hash, authority_level, output_mode, retention_policy,
                artifact_status, created_at, updated_at, metadata_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(artifact_id) DO UPDATE SET
                source_refs_json=excluded.source_refs_json,
                content_hash=excluded.content_hash,
                authority_level=excluded.authority_level,
                artifact_status=excluded.artifact_status,
                updated_at=excluded.updated_at,
                metadata_json=excluded.metadata_json
            """,
            (
                artifact_id,
                ArtifactRole.CURATED_SOURCE.value,
                "working_note_curated_source",
                _json([source_ref, *note.source_refs]),
                note.content_hash,
                AuthorityLevel.SOURCE_BACKED.value,
                OutputMode.COLLECT.value,
                "user_promoted",
                "active",
                timestamp,
                timestamp,
                _json(
                    {
                        "working_note_id": working_note_id,
                        "human_oversight": oversight.as_dict(),
                        "human_in_loop_approved": human_in_loop_approved,
                        "approved_by": approved_by,
                        "approval_note": approval_note,
                    }
                ),
            ),
        )
    record_audit_event(
        db_path,
        event_type="working_note_promoted",
        subject_kind="working_note",
        subject_id=working_note_id,
        severity="info",
        message="Working note promoted to curated source after human-in-the-loop approval.",
        created_at=timestamp,
        metadata={
            "source_ref": source_ref,
            "artifact_id": artifact_id,
            "human_oversight": oversight.as_dict(),
            "human_in_loop_approved": human_in_loop_approved,
            "approved_by": approved_by,
            "approval_note": approval_note,
        },
    )
    return WorkingNotePromotion(
        working_note_id=working_note_id,
        source_ref=source_ref,
        artifact_id=artifact_id,
    )


def _note_from_row(row: sqlite3.Row) -> WorkingNote:
    return WorkingNote(
        working_note_id=row["working_note_id"],
        task_scope=row["task_scope"],
        thread_scope=row["thread_scope"],
        title=row["title"],
        body=row["body"],
        source_refs=tuple(json.loads(row["source_refs_json"] or "[]")),
        artifact_refs=tuple(json.loads(row["artifact_refs_json"] or "[]")),
        content_hash=row["content_hash"],
        retention_policy=row["retention_policy"],
        note_status=row["note_status"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        expires_at=row["expires_at"],
        metadata=json.loads(row["metadata_json"] or "{}"),
    )


def _dedupe(values: tuple[str, ...]) -> tuple[str, ...]:
    refs: list[str] = []
    for value in values:
        if value and value not in refs:
            refs.append(value)
    return tuple(refs)


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


def _utcnow() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
