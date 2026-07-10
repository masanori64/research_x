from __future__ import annotations

import hashlib
import json
import sqlite3
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from research_x.memory.artifact_roles import (
    ArtifactRole,
    normalize_artifact_role,
)
from research_x.memory.authority_levels import (
    AuthorityLevel,
    authority_at_least,
    normalize_authority_level,
)
from research_x.memory.output_modes import OutputMode, normalize_output_mode
from research_x.memory.schema import ensure_memory_schema

ACTIVE_STATUSES = frozenset({"active", "available", "ok", "ready", "citation_ready"})
INACTIVE_STATUSES = frozenset(
    {
        "blocked",
        "deleted",
        "expired",
        "missing",
        "stale",
        "suppressed",
        "tombstoned",
        "unavailable",
    }
)
SEARCHABLE_ROLES = frozenset(
    {
        ArtifactRole.RAW_SOURCE,
        ArtifactRole.CURATED_SOURCE,
        ArtifactRole.IMPORTED_SOURCE,
        ArtifactRole.PROJECTION,
        ArtifactRole.DERIVED_SIGNAL,
        ArtifactRole.WORKING_NOTE,
        ArtifactRole.EVIDENCE_VIEW,
    }
)
WORKING_NOTE_ROLES = SEARCHABLE_ROLES


@dataclass(frozen=True)
class ParticipationDecision:
    output_mode: OutputMode
    can_search: bool
    can_explore: bool
    can_use_in_working_note: bool
    can_use_as_evidence: bool
    can_use_in_answer: bool
    can_trigger_external_fetch: bool
    reason: str

    def as_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["output_mode"] = self.output_mode.value
        return data


@dataclass(frozen=True)
class ParticipationRebuildSummary:
    db_path: str
    decisions: int
    subjects: int
    by_output_mode: dict[str, int]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def evaluate_artifact_participation(
    *,
    artifact_role: str | ArtifactRole,
    authority_level: str | AuthorityLevel,
    output_mode: str | OutputMode,
    status: str,
) -> ParticipationDecision:
    role = normalize_artifact_role(artifact_role)
    authority = normalize_authority_level(authority_level)
    mode = normalize_output_mode(output_mode)
    active = _status_is_active(status)
    searchable = active and role in SEARCHABLE_ROLES
    evidence_ready = active and role is ArtifactRole.EVIDENCE_VIEW
    answer_ready = evidence_ready and authority_at_least(
        authority,
        AuthorityLevel.CLAIM_SUPPORTED,
    )
    return ParticipationDecision(
        output_mode=mode,
        can_search=searchable,
        can_explore=searchable and mode is OutputMode.EXPLORE,
        can_use_in_working_note=active and role in WORKING_NOTE_ROLES,
        can_use_as_evidence=evidence_ready,
        can_use_in_answer=answer_ready and mode is OutputMode.ANSWER,
        can_trigger_external_fetch=False,
        reason=_artifact_reason(role=role, authority=authority, active=active),
    )


def evaluate_source_participation(
    *,
    source_status: str,
    output_mode: str | OutputMode,
) -> ParticipationDecision:
    mode = normalize_output_mode(output_mode)
    active = _status_is_active(source_status)
    return ParticipationDecision(
        output_mode=mode,
        can_search=active,
        can_explore=active and mode is OutputMode.EXPLORE,
        can_use_in_working_note=active,
        can_use_as_evidence=active,
        can_use_in_answer=False,
        can_trigger_external_fetch=False,
        reason="source_available" if active else f"source_status_{source_status}",
    )


def rebuild_participation_decisions(
    db_path: str | Path,
    *,
    output_modes: tuple[str | OutputMode, ...] = tuple(OutputMode),
    decided_at: str = "",
) -> ParticipationRebuildSummary:
    path = Path(db_path)
    if not path.exists():
        raise FileNotFoundError(f"database not found: {path}")
    modes = tuple(normalize_output_mode(mode) for mode in output_modes)
    with sqlite3.connect(path, timeout=60) as conn:
        conn.row_factory = sqlite3.Row
        ensure_memory_schema(conn)
        count = 0
        mode_counts: Counter[str] = Counter()
        subject_count = 0
        for row in conn.execute(
            "SELECT source_ref, source_status FROM memory_sources ORDER BY source_ref"
        ):
            subject_count += 1
            for mode in modes:
                decision = evaluate_source_participation(
                    source_status=row["source_status"],
                    output_mode=mode,
                )
                _upsert_decision(
                    conn,
                    source_ref=row["source_ref"],
                    artifact_id=None,
                    decision=decision,
                    decided_at=decided_at,
                )
                count += 1
                mode_counts[mode.value] += 1
        for row in conn.execute(
            """
            SELECT artifact_id, artifact_role, authority_level, artifact_status
            FROM memory_artifacts
            ORDER BY artifact_id
            """
        ):
            subject_count += 1
            for mode in modes:
                decision = evaluate_artifact_participation(
                    artifact_role=row["artifact_role"],
                    authority_level=row["authority_level"],
                    output_mode=mode,
                    status=row["artifact_status"],
                )
                _upsert_decision(
                    conn,
                    source_ref=None,
                    artifact_id=row["artifact_id"],
                    decision=decision,
                    decided_at=decided_at,
                )
                count += 1
                mode_counts[mode.value] += 1
    return ParticipationRebuildSummary(
        db_path=str(path),
        decisions=count,
        subjects=subject_count,
        by_output_mode=dict(sorted(mode_counts.items())),
    )


def _upsert_decision(
    conn: sqlite3.Connection,
    *,
    source_ref: str | None,
    artifact_id: str | None,
    decision: ParticipationDecision,
    decided_at: str,
) -> None:
    subject_kind = "source" if source_ref is not None else "artifact"
    input_hash = {
        "artifact_id": artifact_id,
        "output_mode": decision.output_mode.value,
        "source_ref": source_ref,
    }
    decision_id = _stable_hash(
        {
            "artifact_id": artifact_id,
            "output_mode": decision.output_mode.value,
            "source_ref": source_ref,
        }
    )
    conn.execute(
        """
        INSERT INTO memory_participation_decisions (
            decision_id, subject_kind, source_ref, artifact_id, output_mode,
            policy_version, severity, can_search, can_explore,
            can_use_in_working_note, can_use_as_evidence, can_use_in_answer,
            can_trigger_external_fetch, reason, decided_by, decided_at,
            input_hash_json, metadata_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(decision_id) DO UPDATE SET
            subject_kind=excluded.subject_kind,
            policy_version=excluded.policy_version,
            severity=excluded.severity,
            can_search=excluded.can_search,
            can_explore=excluded.can_explore,
            can_use_in_working_note=excluded.can_use_in_working_note,
            can_use_as_evidence=excluded.can_use_as_evidence,
            can_use_in_answer=excluded.can_use_in_answer,
            can_trigger_external_fetch=excluded.can_trigger_external_fetch,
            reason=excluded.reason,
            decided_by=excluded.decided_by,
            decided_at=excluded.decided_at,
            input_hash_json=excluded.input_hash_json,
            metadata_json=excluded.metadata_json
        """,
        (
            decision_id,
            subject_kind,
            source_ref,
            artifact_id,
            decision.output_mode.value,
            "knowledgeops-v1",
            "info",
            int(decision.can_search),
            int(decision.can_explore),
            int(decision.can_use_in_working_note),
            int(decision.can_use_as_evidence),
            int(decision.can_use_in_answer),
            int(decision.can_trigger_external_fetch),
            decision.reason,
            "research_x.memory.participation",
            decided_at,
            _json(input_hash),
            _json(decision.as_dict()),
        ),
    )


def _status_is_active(status: str) -> bool:
    normalized = status.strip().casefold()
    if normalized in INACTIVE_STATUSES:
        return False
    if normalized in ACTIVE_STATUSES:
        return True
    return normalized not in {"", "none", "null"}


def _artifact_reason(
    *,
    role: ArtifactRole,
    authority: AuthorityLevel,
    active: bool,
) -> str:
    if not active:
        return "inactive_status"
    if role is ArtifactRole.CONTROL_STATE:
        return "control_state_not_evidence"
    if role is ArtifactRole.WORKING_NOTE:
        return "working_note_not_evidence"
    if role is ArtifactRole.DERIVED_SIGNAL:
        return "derived_signal_not_evidence"
    if role is ArtifactRole.PROJECTION:
        return "projection_not_source"
    if role is ArtifactRole.EVIDENCE_VIEW and authority_at_least(
        authority,
        AuthorityLevel.CLAIM_SUPPORTED,
    ):
        return "claim_supported_evidence_view"
    if role is ArtifactRole.EVIDENCE_VIEW:
        return "evidence_view_needs_claim_support_for_answer"
    return "source_role_not_direct_answer"


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
