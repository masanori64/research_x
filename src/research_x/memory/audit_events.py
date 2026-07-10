from __future__ import annotations

import hashlib
import json
import sqlite3
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from research_x.memory.human_oversight import classify_human_oversight
from research_x.memory.schema import ensure_memory_schema


@dataclass(frozen=True)
class AuditEvent:
    event_id: str
    event_type: str
    subject_kind: str
    subject_id: str
    severity: str
    message: str
    created_at: str
    metadata: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class AlertSink:
    sink_id: str
    sink_kind: str
    sink_config: dict[str, Any]
    enabled: bool

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class AlertRule:
    rule_id: str
    event_type: str
    sink_id: str
    rule_status: str
    threshold: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def record_audit_event(
    db_path: str | Path,
    *,
    event_type: str,
    subject_kind: str,
    subject_id: str,
    severity: str,
    message: str,
    created_at: str,
    metadata: dict[str, Any] | None = None,
) -> AuditEvent:
    event_id = "audit-event:" + _stable_hash(
        {
            "created_at": created_at,
            "event_type": event_type,
            "subject_id": subject_id,
            "subject_kind": subject_kind,
        }
    )[:24]
    event = AuditEvent(
        event_id=event_id,
        event_type=event_type,
        subject_kind=subject_kind,
        subject_id=subject_id,
        severity=severity,
        message=message,
        created_at=created_at,
        metadata=metadata or {},
    )
    with sqlite3.connect(db_path, timeout=60) as conn:
        ensure_memory_schema(conn)
        conn.execute(
            """
            INSERT INTO memory_audit_events (
                event_id, event_type, subject_kind, subject_id, severity,
                message, created_at, metadata_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(event_id) DO UPDATE SET
                severity=excluded.severity,
                message=excluded.message,
                metadata_json=excluded.metadata_json
            """,
            (
                event.event_id,
                event.event_type,
                event.subject_kind,
                event.subject_id,
                event.severity,
                event.message,
                event.created_at,
                _json(event.metadata),
            ),
        )
    return event


def list_audit_events(
    db_path: str | Path,
    *,
    event_type: str | None = None,
) -> tuple[AuditEvent, ...]:
    with sqlite3.connect(db_path, timeout=60) as conn:
        conn.row_factory = sqlite3.Row
        ensure_memory_schema(conn)
        return _list_audit_events_from_conn(conn, event_type=event_type)


def audit_summary(db_path: str | Path) -> dict[str, Any]:
    events = list_audit_events(db_path)
    return {
        "events": len(events),
        "by_event_type": dict(sorted(Counter(event.event_type for event in events).items())),
        "by_severity": dict(sorted(Counter(event.severity for event in events).items())),
    }


def register_alert_sink(
    db_path: str | Path,
    *,
    sink_kind: str,
    sink_config: dict[str, Any],
    sink_id: str | None = None,
    enabled: bool = True,
    human_in_loop_approved: bool = False,
    approved_by: str | None = None,
    approval_note: str | None = None,
    created_at: str,
) -> AlertSink:
    oversight = classify_human_oversight("external_alert_sink_enablement")
    if sink_kind != "local_jsonl" and enabled and not human_in_loop_approved:
        raise ValueError("external alert sink enablement requires human-in-the-loop approval")
    resolved_sink_id = sink_id or f"alert-sink:{sink_kind}:{_stable_hash(sink_config)[:12]}"
    metadata = {
        "human_oversight": oversight.as_dict(),
        "human_in_loop_approved": human_in_loop_approved,
        "approved_by": approved_by,
        "approval_note": approval_note,
        "local_only_sink": sink_kind == "local_jsonl",
    }
    with sqlite3.connect(db_path, timeout=60) as conn:
        ensure_memory_schema(conn)
        conn.execute(
            """
            INSERT INTO memory_alert_sinks (
                sink_id, sink_kind, sink_config_json, enabled, created_at,
                updated_at, metadata_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(sink_id) DO UPDATE SET
                sink_config_json=excluded.sink_config_json,
                enabled=excluded.enabled,
                updated_at=excluded.updated_at
            """,
            (
                resolved_sink_id,
                sink_kind,
                _json(sink_config),
                int(enabled),
                created_at,
                created_at,
                _json(metadata),
            ),
        )
    return AlertSink(
        sink_id=resolved_sink_id,
        sink_kind=sink_kind,
        sink_config=sink_config,
        enabled=enabled,
    )


def register_alert_rule(
    db_path: str | Path,
    *,
    event_type: str,
    sink_id: str,
    threshold: dict[str, Any] | None = None,
    rule_id: str | None = None,
    rule_status: str = "active",
    created_at: str,
) -> AlertRule:
    resolved_threshold = threshold or {}
    resolved_rule_id = rule_id or "alert-rule:" + _stable_hash(
        {
            "event_type": event_type,
            "sink_id": sink_id,
            "threshold": resolved_threshold,
        }
    )[:24]
    rule = AlertRule(
        rule_id=resolved_rule_id,
        event_type=event_type,
        sink_id=sink_id,
        rule_status=rule_status,
        threshold=resolved_threshold,
    )
    with sqlite3.connect(db_path, timeout=60) as conn:
        ensure_memory_schema(conn)
        conn.execute(
            """
            INSERT INTO memory_alert_rules (
                rule_id, event_type, sink_id, rule_status, threshold_json,
                created_at, updated_at, metadata_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(rule_id) DO UPDATE SET
                event_type=excluded.event_type,
                sink_id=excluded.sink_id,
                rule_status=excluded.rule_status,
                threshold_json=excluded.threshold_json,
                updated_at=excluded.updated_at
            """,
            (
                rule.rule_id,
                rule.event_type,
                rule.sink_id,
                rule.rule_status,
                _json(rule.threshold),
                created_at,
                created_at,
                "{}",
            ),
        )
    return rule


def evaluate_alert_rules(
    db_path: str | Path,
    *,
    delivered_at: str,
) -> dict[str, Any]:
    delivered = 0
    skipped = 0
    unsupported = 0
    evaluated_rules = 0
    with sqlite3.connect(db_path, timeout=60) as conn:
        conn.row_factory = sqlite3.Row
        ensure_memory_schema(conn)
        rules = conn.execute(
            """
            SELECT r.*, s.sink_kind, s.sink_config_json, s.enabled
            FROM memory_alert_rules r
            JOIN memory_alert_sinks s ON s.sink_id = r.sink_id
            WHERE r.rule_status = 'active'
            ORDER BY r.rule_id
            """
        ).fetchall()
        for rule in rules:
            evaluated_rules += 1
            if int(rule["enabled"]) != 1:
                skipped += 1
                continue
            events = _matching_events_for_rule(conn, rule)
            if rule["sink_kind"] != "local_jsonl":
                unsupported += len(events)
                for event in events:
                    _record_delivery(
                        conn,
                        sink_id=rule["sink_id"],
                        event_id=event.event_id,
                        delivered_at=delivered_at,
                        rule_id=rule["rule_id"],
                        status="unsupported_sink",
                        last_error=f"unsupported sink_kind: {rule['sink_kind']}",
                    )
                continue
            output_path = Path(json.loads(rule["sink_config_json"])["path"])
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with output_path.open("a", encoding="utf-8") as handle:
                for event in events:
                    if _delivery_exists(
                        conn,
                        rule_id=rule["rule_id"],
                        sink_id=rule["sink_id"],
                        event_id=event.event_id,
                    ):
                        skipped += 1
                        continue
                    handle.write(_json(event.as_dict()) + "\n")
                    _record_delivery(
                        conn,
                        sink_id=rule["sink_id"],
                        event_id=event.event_id,
                        delivered_at=delivered_at,
                        rule_id=rule["rule_id"],
                    )
                    delivered += 1
    return {
        "status": "ok",
        "rules": evaluated_rules,
        "delivered": delivered,
        "skipped": skipped,
        "unsupported": unsupported,
    }


def deliver_audit_events_to_jsonl(
    db_path: str | Path,
    *,
    sink_id: str,
    event_type: str | None = None,
    delivered_at: str,
) -> int:
    with sqlite3.connect(db_path, timeout=60) as conn:
        conn.row_factory = sqlite3.Row
        ensure_memory_schema(conn)
        sink = conn.execute(
            "SELECT * FROM memory_alert_sinks WHERE sink_id = ?",
            (sink_id,),
        ).fetchone()
        if sink is None:
            raise KeyError(f"alert sink not found: {sink_id}")
        if int(sink["enabled"]) != 1:
            return 0
        if sink["sink_kind"] != "local_jsonl":
            raise ValueError(f"unsupported sink_kind for local delivery: {sink['sink_kind']}")
        events = _list_audit_events_from_conn(conn, event_type=event_type)
        output_path = Path(json.loads(sink["sink_config_json"])["path"])
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open("a", encoding="utf-8") as handle:
            for event in events:
                handle.write(_json(event.as_dict()) + "\n")
                _record_delivery(
                    conn,
                    sink_id=sink_id,
                    event_id=event.event_id,
                    delivered_at=delivered_at,
                )
    return len(events)


def _list_audit_events_from_conn(
    conn: sqlite3.Connection,
    *,
    event_type: str | None = None,
) -> tuple[AuditEvent, ...]:
    if event_type:
        rows = conn.execute(
            """
            SELECT *
            FROM memory_audit_events
            WHERE event_type = ?
            ORDER BY created_at, event_id
            """,
            (event_type,),
        ).fetchall()
    else:
        rows = conn.execute(
            """
            SELECT *
            FROM memory_audit_events
            ORDER BY created_at, event_id
            """
        ).fetchall()
    return tuple(_event_from_row(row) for row in rows)


def _record_delivery(
    conn: sqlite3.Connection,
    *,
    sink_id: str,
    event_id: str,
    delivered_at: str,
    rule_id: str = "manual-local-jsonl",
    status: str = "delivered",
    last_error: str | None = None,
) -> None:
    delivery_id = "alert-delivery:" + _stable_hash(
        {
            "event_id": event_id,
            "rule_id": rule_id,
            "sink_id": sink_id,
            "status": status,
        }
    )[:24]
    conn.execute(
        """
        INSERT INTO memory_alert_deliveries (
            delivery_id, rule_id, sink_id, event_id, delivery_status,
            attempt_count, last_error, created_at, updated_at, metadata_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(delivery_id) DO UPDATE SET
            delivery_status=excluded.delivery_status,
            attempt_count=excluded.attempt_count,
            updated_at=excluded.updated_at
        """,
        (
            delivery_id,
            rule_id,
            sink_id,
            event_id,
            status,
            1,
            last_error,
            delivered_at,
            delivered_at,
            "{}",
        ),
    )


def _matching_events_for_rule(
    conn: sqlite3.Connection,
    rule: sqlite3.Row,
) -> tuple[AuditEvent, ...]:
    threshold = json.loads(rule["threshold_json"] or "{}")
    min_severity = threshold.get("min_severity")
    subject_kind = threshold.get("subject_kind")
    events = _list_audit_events_from_conn(conn, event_type=rule["event_type"])
    return tuple(
        event
        for event in events
        if _severity_at_least(event.severity, min_severity)
        and (subject_kind is None or event.subject_kind == subject_kind)
    )


def _delivery_exists(
    conn: sqlite3.Connection,
    *,
    rule_id: str,
    sink_id: str,
    event_id: str,
) -> bool:
    row = conn.execute(
        """
        SELECT 1
        FROM memory_alert_deliveries
        WHERE rule_id = ? AND sink_id = ? AND event_id = ?
        LIMIT 1
        """,
        (rule_id, sink_id, event_id),
    ).fetchone()
    return row is not None


def _severity_at_least(severity: str, minimum: Any) -> bool:
    if minimum is None:
        return True
    ranks = {"debug": 0, "info": 1, "warning": 2, "error": 3, "critical": 4}
    actual = ranks.get(str(severity).strip().casefold(), 0)
    required = ranks.get(str(minimum).strip().casefold(), 0)
    return actual >= required


def _event_from_row(row: sqlite3.Row) -> AuditEvent:
    return AuditEvent(
        event_id=row["event_id"],
        event_type=row["event_type"],
        subject_kind=row["subject_kind"],
        subject_id=row["subject_id"],
        severity=row["severity"],
        message=row["message"],
        created_at=row["created_at"],
        metadata=json.loads(row["metadata_json"] or "{}"),
    )


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
