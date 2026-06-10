from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from research_x.memory.schema import ensure_memory_schema

GOVERNANCE_TYPES = {"profile", "contradiction", "retention", "forgetting", "tombstone"}
GOVERNANCE_STATUSES = {"active", "superseded", "restored", "expired", "rejected"}
DEFAULT_RETENTION_POLICY = "source_lifetime"


@dataclass(frozen=True)
class GovernanceRecord:
    record_id: str
    governance_type: str
    subject_kind: str
    subject_id: str
    statement: str
    status: str
    confidence: float
    source_kind: str
    source_id: str
    source_url: str | None
    source_hash: str | None
    source_anchor: dict[str, Any]
    retention_policy: str
    expires_at: str | None
    supersedes_record_id: str | None
    created_at: str
    updated_at: str
    metadata: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def add_governance_record(
    db_path: str | Path,
    *,
    governance_type: str,
    subject_kind: str,
    subject_id: str,
    statement: str,
    source_kind: str,
    source_id: str,
    source_url: str | None = None,
    source_hash: str | None = None,
    source_anchor: dict[str, Any] | None = None,
    confidence: float = 1.0,
    status: str = "active",
    retention_policy: str = DEFAULT_RETENTION_POLICY,
    expires_at: str | None = None,
    supersedes_record_id: str | None = None,
    metadata: dict[str, Any] | None = None,
    created_at: str | None = None,
) -> GovernanceRecord:
    record = _governance_record(
        governance_type=governance_type,
        subject_kind=subject_kind,
        subject_id=subject_id,
        statement=statement,
        source_kind=source_kind,
        source_id=source_id,
        source_url=source_url,
        source_hash=source_hash,
        source_anchor=source_anchor or {},
        confidence=confidence,
        status=status,
        retention_policy=retention_policy,
        expires_at=expires_at,
        supersedes_record_id=supersedes_record_id,
        metadata=metadata or {},
        created_at=created_at,
    )
    with sqlite3.connect(Path(db_path), timeout=60) as conn:
        ensure_memory_schema(conn)
        _insert_governance_record(conn, record)
    return record


def add_tombstone(
    db_path: str | Path,
    *,
    artifact_kind: str,
    artifact_id: str,
    reason: str,
    source_kind: str,
    source_id: str,
    source_url: str | None = None,
    source_hash: str | None = None,
    source_anchor: dict[str, Any] | None = None,
    retention_policy: str = "suppress_until_restored",
    metadata: dict[str, Any] | None = None,
    created_at: str | None = None,
) -> GovernanceRecord:
    return add_governance_record(
        db_path,
        governance_type="tombstone",
        subject_kind=_artifact_subject_kind(artifact_kind),
        subject_id=artifact_id,
        statement=reason,
        source_kind=source_kind,
        source_id=source_id,
        source_url=source_url,
        source_hash=source_hash,
        source_anchor={
            "artifact_kind": artifact_kind,
            "artifact_id": artifact_id,
            **(source_anchor or {}),
        },
        confidence=1.0,
        status="active",
        retention_policy=retention_policy,
        metadata={
            "artifact_kind": artifact_kind,
            "artifact_id": artifact_id,
            "governance_action": "suppress",
            **(metadata or {}),
        },
        created_at=created_at,
    )


def restore_governance_record(
    db_path: str | Path,
    *,
    record_id: str,
    reason: str,
    updated_at: str | None = None,
) -> GovernanceRecord:
    timestamp = updated_at or _utc_now()
    with sqlite3.connect(Path(db_path), timeout=60) as conn:
        conn.row_factory = sqlite3.Row
        ensure_memory_schema(conn)
        row = conn.execute(
            "SELECT * FROM memory_governance_records WHERE record_id = ?",
            (record_id,),
        ).fetchone()
        if row is None:
            raise ValueError(f"governance record not found: {record_id}")
        metadata = _json_object(row["metadata_json"])
        metadata["restore_reason"] = reason
        metadata["restored_at"] = timestamp
        conn.execute(
            """
            UPDATE memory_governance_records
            SET status = 'restored', updated_at = ?, metadata_json = ?
            WHERE record_id = ?
            """,
            (
                timestamp,
                json.dumps(metadata, ensure_ascii=False, sort_keys=True),
                record_id,
            ),
        )
        restored = conn.execute(
            "SELECT * FROM memory_governance_records WHERE record_id = ?",
            (record_id,),
        ).fetchone()
    return _record_from_row(restored)


def list_governance_records(
    db_path: str | Path,
    *,
    governance_type: str | None = None,
    subject_kind: str | None = None,
    subject_id: str | None = None,
    include_inactive: bool = False,
    limit: int = 50,
) -> tuple[GovernanceRecord, ...]:
    filters: list[str] = []
    params: list[Any] = []
    if governance_type:
        filters.append("governance_type = ?")
        params.append(governance_type)
    if subject_kind:
        filters.append("subject_kind = ?")
        params.append(subject_kind)
    if subject_id:
        filters.append("subject_id = ?")
        params.append(subject_id)
    if not include_inactive:
        filters.append("status = 'active'")
    where = f"WHERE {' AND '.join(filters)}" if filters else ""
    with sqlite3.connect(Path(db_path), timeout=60) as conn:
        conn.row_factory = sqlite3.Row
        ensure_memory_schema(conn)
        rows = conn.execute(
            f"""
            SELECT *
            FROM memory_governance_records
            {where}
            ORDER BY updated_at DESC, record_id
            LIMIT ?
            """,
            (*params, max(1, limit)),
        ).fetchall()
    return tuple(_record_from_row(row) for row in rows)


def active_tombstone_ids(
    conn: sqlite3.Connection,
    *,
    artifact_kind: str,
    artifact_ids: tuple[str, ...],
    now: str | None = None,
) -> set[str]:
    if not artifact_ids:
        return set()
    placeholders = ",".join("?" for _ in artifact_ids)
    subject_kind = _artifact_subject_kind(artifact_kind)
    timestamp = now or _utc_now()
    rows = conn.execute(
        f"""
        SELECT subject_id
        FROM memory_governance_records
        WHERE governance_type = 'tombstone'
          AND subject_kind = ?
          AND subject_id IN ({placeholders})
          AND status = 'active'
          AND (expires_at IS NULL OR expires_at > ?)
        """,
        (subject_kind, *artifact_ids, timestamp),
    ).fetchall()
    return {str(row["subject_id"] if isinstance(row, sqlite3.Row) else row[0]) for row in rows}


def is_artifact_tombstoned(
    db_path: str | Path,
    *,
    artifact_kind: str,
    artifact_id: str,
) -> bool:
    with sqlite3.connect(Path(db_path), timeout=60) as conn:
        conn.row_factory = sqlite3.Row
        ensure_memory_schema(conn)
        return bool(
            active_tombstone_ids(
                conn,
                artifact_kind=artifact_kind,
                artifact_ids=(artifact_id,),
            )
        )


def governance_records_json(records: tuple[GovernanceRecord, ...]) -> str:
    return json.dumps(
        [record.as_dict() for record in records],
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    )


def format_governance_records(records: tuple[GovernanceRecord, ...]) -> str:
    if not records:
        return "(no memory governance records)"
    lines: list[str] = []
    for record in records:
        lines.append(
            " ".join(
                [
                    f"{record.record_id}",
                    f"type={record.governance_type}",
                    f"status={record.status}",
                    f"subject={record.subject_kind}:{record.subject_id}",
                    f"source={record.source_kind}:{record.source_id}",
                ]
            )
        )
        lines.append(f"  statement: {record.statement}")
        lines.append(f"  retention: {record.retention_policy}")
    return "\n".join(lines)


def _governance_record(
    *,
    governance_type: str,
    subject_kind: str,
    subject_id: str,
    statement: str,
    source_kind: str,
    source_id: str,
    source_url: str | None,
    source_hash: str | None,
    source_anchor: dict[str, Any],
    confidence: float,
    status: str,
    retention_policy: str,
    expires_at: str | None,
    supersedes_record_id: str | None,
    metadata: dict[str, Any],
    created_at: str | None,
) -> GovernanceRecord:
    _validate_record_input(
        governance_type=governance_type,
        subject_kind=subject_kind,
        subject_id=subject_id,
        statement=statement,
        source_kind=source_kind,
        source_id=source_id,
        status=status,
        confidence=confidence,
    )
    timestamp = created_at or _utc_now()
    normalized_anchor = _normalize_source_anchor(source_anchor)
    record_id = _record_id(
        governance_type,
        subject_kind,
        subject_id,
        statement,
        source_kind,
        source_id,
        timestamp,
    )
    return GovernanceRecord(
        record_id=record_id,
        governance_type=governance_type,
        subject_kind=subject_kind,
        subject_id=subject_id,
        statement=statement,
        status=status,
        confidence=max(0.0, min(1.0, float(confidence))),
        source_kind=source_kind,
        source_id=source_id,
        source_url=source_url,
        source_hash=source_hash,
        source_anchor=normalized_anchor,
        retention_policy=retention_policy,
        expires_at=expires_at,
        supersedes_record_id=supersedes_record_id,
        created_at=timestamp,
        updated_at=timestamp,
        metadata={
            "citation_excluded": True,
            "evidence_role": "governance_control_not_answer_evidence",
            **metadata,
        },
    )


def _insert_governance_record(conn: sqlite3.Connection, record: GovernanceRecord) -> None:
    conn.execute(
        """
        INSERT INTO memory_governance_records (
            record_id, governance_type, subject_kind, subject_id, statement,
            status, confidence, source_kind, source_id, source_url, source_hash,
            source_anchor_json, retention_policy, expires_at, supersedes_record_id,
            created_at, updated_at, metadata_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            record.record_id,
            record.governance_type,
            record.subject_kind,
            record.subject_id,
            record.statement,
            record.status,
            record.confidence,
            record.source_kind,
            record.source_id,
            record.source_url,
            record.source_hash,
            json.dumps(record.source_anchor, ensure_ascii=False, sort_keys=True),
            record.retention_policy,
            record.expires_at,
            record.supersedes_record_id,
            record.created_at,
            record.updated_at,
            json.dumps(record.metadata, ensure_ascii=False, sort_keys=True),
        ),
    )


def _record_from_row(row: sqlite3.Row) -> GovernanceRecord:
    return GovernanceRecord(
        record_id=str(row["record_id"]),
        governance_type=str(row["governance_type"]),
        subject_kind=str(row["subject_kind"]),
        subject_id=str(row["subject_id"]),
        statement=str(row["statement"]),
        status=str(row["status"]),
        confidence=float(row["confidence"]),
        source_kind=str(row["source_kind"]),
        source_id=str(row["source_id"]),
        source_url=_string_or_none(row["source_url"]),
        source_hash=_string_or_none(row["source_hash"]),
        source_anchor=_json_object(row["source_anchor_json"]),
        retention_policy=str(row["retention_policy"]),
        expires_at=_string_or_none(row["expires_at"]),
        supersedes_record_id=_string_or_none(row["supersedes_record_id"]),
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
        metadata=_json_object(row["metadata_json"]),
    )


def _validate_record_input(
    *,
    governance_type: str,
    subject_kind: str,
    subject_id: str,
    statement: str,
    source_kind: str,
    source_id: str,
    status: str,
    confidence: float,
) -> None:
    if governance_type not in GOVERNANCE_TYPES:
        raise ValueError(f"governance_type must be one of {sorted(GOVERNANCE_TYPES)}")
    if status not in GOVERNANCE_STATUSES:
        raise ValueError(f"status must be one of {sorted(GOVERNANCE_STATUSES)}")
    for name, value in {
        "subject_kind": subject_kind,
        "subject_id": subject_id,
        "statement": statement,
        "source_kind": source_kind,
        "source_id": source_id,
    }.items():
        if not str(value).strip():
            raise ValueError(f"{name} is required")
    if not 0.0 <= float(confidence) <= 1.0:
        raise ValueError("confidence must be between 0.0 and 1.0")


def _normalize_source_anchor(source_anchor: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(source_anchor, dict):
        raise ValueError("source_anchor must be an object")
    return {
        "source_backed": True,
        "restore_required_before_answer_use": True,
        **source_anchor,
    }


def _artifact_subject_kind(artifact_kind: str) -> str:
    value = artifact_kind.strip()
    if not value:
        raise ValueError("artifact_kind is required")
    return f"artifact:{value}"


def _record_id(*parts: str) -> str:
    payload = "\0".join(parts).encode("utf-8")
    return "gov_" + hashlib.sha256(payload).hexdigest()[:24]


def _json_object(value: str | None) -> dict[str, Any]:
    if not value:
        return {}
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _string_or_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text or None


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
