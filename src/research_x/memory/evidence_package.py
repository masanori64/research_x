from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from research_x.memory.output_modes import OutputMode
from research_x.memory.schema import ensure_memory_schema
from research_x.tool_interface.memory_tool_contract import (
    CONTRACT_VERSION_V2,
    ToolCitation,
    ToolOutputItemV2,
    ToolOutputV2,
    validate_tool_output_v2,
)

STALE_STATUSES = frozenset({"stale", "orphaned", "rebuild_required", "tombstoned"})


def candidate_to_evidence_view(candidate: Mapping[str, Any]) -> dict[str, Any]:
    if not candidate.get("source_ref"):
        raise ValueError("candidate cannot become evidence_view without source_ref")
    if not candidate.get("restore_path"):
        raise ValueError("candidate cannot become evidence_view without source restore")
    if not isinstance(candidate.get("context_range"), Mapping) or not candidate.get(
        "context_range"
    ):
        raise ValueError("candidate cannot become evidence_view without context range")
    if validate_staleness(candidate) != "active":
        raise ValueError("candidate cannot become evidence_view while stale")
    return {
        "artifact_role": "evidence_view",
        "authority_level": "evidence_view",
        "source_ref": candidate.get("source_ref"),
        "restore_path": candidate.get("restore_path"),
        "context_range": candidate.get("context_range"),
        "metadata": dict(candidate.get("metadata") or {}),
    }


def promote_candidate_to_evidence_package(
    db_path: str | Path,
    *,
    query: str,
    candidate: Mapping[str, Any],
    artifact_id: str | None = None,
    created_at: str | None = None,
) -> ToolOutputV2:
    evidence_view = candidate_to_evidence_view(candidate)
    resolved_artifact_id = artifact_id or _stable_id("evidence-view", evidence_view)
    now = created_at or _now()
    source_ref = str(evidence_view["source_ref"])
    metadata = {
        "candidate": dict(candidate),
        "restore_path": evidence_view["restore_path"],
        "context_range": evidence_view["context_range"],
    }
    with sqlite3.connect(db_path, timeout=60) as conn:
        ensure_memory_schema(conn)
        conn.execute(
            """
            INSERT INTO memory_artifacts (
                artifact_id, artifact_role, artifact_kind, artifact_scope, title,
                source_refs_json, content_ref, content_hash, authority_level,
                output_mode, retention_policy, artifact_status, created_by,
                builder_version, confidence, expires_at, created_at, updated_at,
                metadata_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(artifact_id) DO UPDATE SET
                artifact_role=excluded.artifact_role,
                artifact_kind=excluded.artifact_kind,
                artifact_scope=excluded.artifact_scope,
                title=excluded.title,
                source_refs_json=excluded.source_refs_json,
                content_ref=excluded.content_ref,
                content_hash=excluded.content_hash,
                authority_level=excluded.authority_level,
                output_mode=excluded.output_mode,
                retention_policy=excluded.retention_policy,
                artifact_status=excluded.artifact_status,
                updated_at=excluded.updated_at,
                metadata_json=excluded.metadata_json
            """,
            (
                resolved_artifact_id,
                "evidence_view",
                "candidate_evidence_view",
                "memory_candidate",
                str(candidate.get("title") or source_ref),
                _json([source_ref]),
                _json(evidence_view["restore_path"]),
                _stable_id("evidence-view-content", evidence_view),
                "evidence_view",
                OutputMode.EVIDENCE_PACKAGE.value,
                "evidence_package_builder",
                "active",
                "research_x.memory.evidence_package",
                "candidate-to-evidence-view-v1",
                float(candidate.get("confidence", 1.0)),
                None,
                now,
                now,
                _json(metadata),
            ),
        )
    return build_evidence_package_output(
        db_path,
        query=query,
        artifact_ids=(resolved_artifact_id,),
    )


def build_context_chunk(
    *,
    source_ref: str,
    chunk_id: str,
    text: str,
    restore_path: Mapping[str, Any],
    context_range: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    if not source_ref or not chunk_id or not text:
        raise ValueError("source_ref, chunk_id, and text are required")
    if not restore_path:
        raise ValueError("restore_path is required")
    return {
        "chunk_id": chunk_id,
        "source_ref": source_ref,
        "text": text,
        "restore_path": dict(restore_path),
        "context_range": dict(context_range or {}),
    }


def build_citation_candidate(
    *,
    artifact_id: str,
    source_ref: str,
    chunk_id: str,
) -> dict[str, Any]:
    if not artifact_id or not source_ref or not chunk_id:
        raise ValueError("artifact_id, source_ref, and chunk_id are required")
    return {
        "artifact_id": artifact_id,
        "source_refs": [source_ref],
        "chunk_id": chunk_id,
        "status": "candidate",
    }


def validate_source_restore(candidate: Mapping[str, Any]) -> bool:
    return bool(candidate.get("source_ref") and candidate.get("restore_path"))


def validate_staleness(candidate: Mapping[str, Any]) -> str:
    status = str(candidate.get("artifact_status") or "active").strip().casefold()
    return "stale" if status in STALE_STATUSES else "active"


def validate_role(
    *,
    artifact_role: str,
    authority_level: str,
) -> bool:
    return artifact_role == "evidence_view" and authority_level in {
        "evidence_view",
        "claim_supported",
    }


def build_evidence_package_output(
    db_path: str | Path,
    *,
    query: str,
    artifact_ids: tuple[str, ...],
    tool_kind: str = "research_x.memory.evidence_package",
) -> ToolOutputV2:
    if not artifact_ids:
        raise ValueError("evidence package requires at least one artifact_id")
    with sqlite3.connect(db_path, timeout=60) as conn:
        conn.row_factory = sqlite3.Row
        ensure_memory_schema(conn)
        rows = _artifact_rows(conn, artifact_ids)
        participation_blocked = _participation_blocked_artifacts(
            conn,
            artifact_ids=tuple(str(row["artifact_id"]) for row in rows),
            output_mode=OutputMode.EVIDENCE_PACKAGE,
        )
    missing = sorted(set(artifact_ids) - {row["artifact_id"] for row in rows})
    if missing:
        raise ValueError("missing evidence artifacts: " + ", ".join(missing))
    if participation_blocked:
        raise ValueError(
            "participation policy blocks evidence package artifacts: "
            + ", ".join(participation_blocked)
        )
    invalid = [
        row["artifact_id"]
        for row in rows
        if row["artifact_role"] != "evidence_view"
        or row["authority_level"] not in {
            "evidence_view",
            "claim_supported",
        }
    ]
    if invalid:
        raise ValueError(
            "evidence package accepts only evidence_view artifacts: "
            + ", ".join(invalid)
        )
    output = ToolOutputV2(
        contract_version=CONTRACT_VERSION_V2,
        tool_kind=tool_kind,
        query=query,
        output_mode=OutputMode.EVIDENCE_PACKAGE.value,
        status="evidence_package",
        answer_text=None,
        items=tuple(_item(row) for row in rows),
        citations=(),
        claim_support=None,
        working_note_id=None,
        trace={
            "citation_candidates": _citation_candidates(rows),
            "participation_enforcement": {
                "output_mode": OutputMode.EVIDENCE_PACKAGE.value,
                "checked_artifacts": len(rows),
                "blocked_artifacts": [],
            },
        },
    )
    errors = validate_tool_output_v2(output)
    if errors:
        raise ValueError("; ".join(errors))
    return output


def promote_evidence_package_to_answer(
    db_path: str | Path,
    *,
    evidence_package: ToolOutputV2,
    answer_text: str,
    claims: tuple[Mapping[str, Any], ...],
    output_run_id: str | None = None,
    created_at: str | None = None,
    tool_kind: str = "research_x.memory.answer",
) -> ToolOutputV2:
    if evidence_package.output_mode != OutputMode.EVIDENCE_PACKAGE.value:
        raise ValueError("answer promotion requires an evidence_package output")
    if not str(answer_text).strip():
        raise ValueError("answer_text is required")
    if not claims:
        raise ValueError("answer promotion requires at least one claim")
    citation_candidates = _evidence_package_citation_candidates(evidence_package)
    citations = tuple(_citation_from_candidate(candidate) for candidate in citation_candidates)
    if not citations:
        raise ValueError("answer promotion requires citation candidates")
    known_citation_ids = {citation.citation_id for citation in citations}
    normalized_claims = tuple(_normalize_claim(claim) for claim in claims)
    unknown = _unknown_claim_citations(normalized_claims, known_citation_ids)
    if unknown:
        raise ValueError("claim_support references unknown citations: " + ", ".join(unknown))
    unsupported = [
        claim["claim_id"]
        for claim in normalized_claims
        if claim["support_status"] != "supported"
    ]
    if unsupported:
        raise ValueError(
            "unsupported claims cannot become answer assertions: "
            + ", ".join(unsupported)
        )
    output_items = tuple(_answer_item(item) for item in evidence_package.items)
    claim_support = {
        "status": "supported",
        "claims": [dict(claim) for claim in normalized_claims],
    }
    run_id = output_run_id or _stable_id(
        "answer-output",
        evidence_package.query,
        answer_text,
        normalized_claims,
    )
    now = created_at or _now()
    with sqlite3.connect(db_path, timeout=60) as conn:
        conn.row_factory = sqlite3.Row
        ensure_memory_schema(conn)
        blocked = _participation_blocked_artifacts(
            conn,
            artifact_ids=tuple(item.item_id for item in evidence_package.items),
            output_mode=OutputMode.ANSWER,
        )
        if blocked:
            raise ValueError(
                "participation policy blocks answer artifacts: " + ", ".join(blocked)
            )
        _store_answer_output_run(
            conn,
            output_run_id=run_id,
            query=evidence_package.query,
            status="answer",
            started_at=now,
            finished_at=now,
            metadata={
                "source_output_mode": evidence_package.output_mode,
                "tool_kind": tool_kind,
            },
        )
        _store_answer_output_items(conn, output_run_id=run_id, items=output_items, created_at=now)
        _store_claim_support_assessments(
            conn,
            output_run_id=run_id,
            claims=normalized_claims,
            created_at=now,
        )
    output = ToolOutputV2(
        contract_version=CONTRACT_VERSION_V2,
        tool_kind=tool_kind,
        query=evidence_package.query,
        output_mode=OutputMode.ANSWER.value,
        status="answer",
        answer_text=answer_text,
        items=output_items,
        citations=citations,
        claim_support=claim_support,
        working_note_id=evidence_package.working_note_id,
        trace={
            "db_backed_validation": {
                "status": "passed",
                "output_run_id": run_id,
                "claim_support_assessments": len(normalized_claims),
            },
            "source_output_mode": evidence_package.output_mode,
            "participation_enforcement": {
                "output_mode": OutputMode.ANSWER.value,
                "checked_artifacts": len(evidence_package.items),
                "blocked_artifacts": [],
            },
        },
    )
    errors = validate_tool_output_v2(output)
    if errors:
        raise ValueError("; ".join(errors))
    return output


def _artifact_rows(
    conn: sqlite3.Connection,
    artifact_ids: tuple[str, ...],
) -> tuple[sqlite3.Row, ...]:
    placeholders = ",".join("?" for _ in artifact_ids)
    rows = conn.execute(
        f"""
        SELECT artifact_id, artifact_role, artifact_kind, source_refs_json,
               content_hash, authority_level, artifact_status, metadata_json
        FROM memory_artifacts
        WHERE artifact_id IN ({placeholders})
        ORDER BY artifact_id
        """,
        artifact_ids,
    ).fetchall()
    return tuple(rows)


def _item(row: sqlite3.Row) -> ToolOutputItemV2:
    return ToolOutputItemV2(
        item_id=row["artifact_id"],
        subject_kind=row["artifact_kind"],
        subject_id=row["artifact_id"],
        artifact_role=row["artifact_role"],
        authority_level=row["authority_level"],
        source_refs=tuple(json.loads(row["source_refs_json"] or "[]")),
        source_status="available",
        projection_id=None,
        score=None,
        why_relevant="selected_evidence_artifact",
        risk_flags=(),
        metadata={
            "artifact_status": row["artifact_status"],
            "content_hash": row["content_hash"],
            "metadata": json.loads(row["metadata_json"] or "{}"),
        },
    )


def _participation_blocked_artifacts(
    conn: sqlite3.Connection,
    *,
    artifact_ids: tuple[str, ...],
    output_mode: OutputMode,
) -> tuple[str, ...]:
    if not artifact_ids:
        return ()
    placeholders = ",".join("?" for _ in artifact_ids)
    rows = conn.execute(
        f"""
        SELECT artifact_id, can_use_as_evidence, can_use_in_answer
        FROM memory_participation_decisions
        WHERE artifact_id IN ({placeholders})
          AND output_mode = ?
        """,
        (*artifact_ids, output_mode.value),
    ).fetchall()
    blocked: list[str] = []
    for row in rows:
        if output_mode is OutputMode.EVIDENCE_PACKAGE and int(row["can_use_as_evidence"]) == 0:
            blocked.append(str(row["artifact_id"]))
        if output_mode is OutputMode.ANSWER and int(row["can_use_in_answer"]) == 0:
            blocked.append(str(row["artifact_id"]))
    return tuple(dict.fromkeys(blocked))


def _citation_candidates(rows: tuple[sqlite3.Row, ...]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for row in rows:
        metadata = json.loads(row["metadata_json"] or "{}")
        source_refs = json.loads(row["source_refs_json"] or "[]")
        if row["artifact_kind"] == "memory_citation_annotation":
            candidates.append(
                {
                    "artifact_id": row["artifact_id"],
                    "source_refs": source_refs,
                    "citation_id": row["artifact_id"],
                    "chunk_id": row["artifact_id"],
                    "source_kind": "memory_artifact",
                    "source_id": row["artifact_id"],
                    "status": "candidate",
                    "restore": {
                        "artifact_id": row["artifact_id"],
                        "lineage_status": "restored",
                    },
                }
            )
            continue
        if row["artifact_role"] == "evidence_view":
            context_range = metadata.get("context_range")
            if not isinstance(context_range, dict):
                context_range = {}
            restore_path = metadata.get("restore_path")
            if not isinstance(restore_path, dict):
                restore_path = {"artifact_id": row["artifact_id"]}
            candidates.append(
                {
                    "artifact_id": row["artifact_id"],
                    "source_refs": source_refs,
                    "citation_id": row["artifact_id"],
                    "chunk_id": str(context_range.get("chunk_id") or row["artifact_id"]),
                    "source_kind": "memory_artifact",
                    "source_id": row["artifact_id"],
                    "status": "candidate",
                    "restore": {
                        "artifact_id": row["artifact_id"],
                        "lineage_status": "restored",
                        "restore_path": restore_path,
                    },
                }
            )
    return candidates


def _evidence_package_citation_candidates(output: ToolOutputV2) -> tuple[dict[str, Any], ...]:
    candidates = output.trace.get("citation_candidates")
    if not isinstance(candidates, list):
        return ()
    return tuple(candidate for candidate in candidates if isinstance(candidate, dict))


def _citation_from_candidate(candidate: Mapping[str, Any]) -> ToolCitation:
    source_refs = tuple(str(ref) for ref in candidate.get("source_refs") or ())
    citation_id = str(candidate.get("citation_id") or candidate.get("artifact_id") or "")
    if not citation_id:
        raise ValueError("citation candidate requires citation_id or artifact_id")
    source_id = str(candidate.get("source_id") or candidate.get("artifact_id") or citation_id)
    return ToolCitation(
        citation_id=citation_id,
        chunk_id=str(candidate.get("chunk_id") or citation_id),
        source_kind=str(candidate.get("source_kind") or "memory_artifact"),
        source_id=source_id,
        source_url=None,
        title=source_refs[0] if source_refs else source_id,
        evidence_status="citation_ready",
        citation_ready=True,
        restore={
            "lineage_status": "restored",
            "citation_ready": True,
            "source_restored": True,
            "context_chunk_restored": True,
            **dict(candidate.get("restore") or {}),
        },
    )


def _normalize_claim(claim: Mapping[str, Any]) -> dict[str, Any]:
    claim_id = str(claim.get("claim_id") or "").strip()
    if not claim_id:
        raise ValueError("claim_id is required")
    citation_ids = claim.get("citation_ids")
    if isinstance(citation_ids, list):
        normalized_citations = tuple(str(item) for item in citation_ids if str(item).strip())
    elif claim.get("citation_id"):
        normalized_citations = (str(claim["citation_id"]),)
    else:
        normalized_citations = ()
    if not normalized_citations:
        raise ValueError(f"claim {claim_id} requires citation_ids")
    support_status = str(
        claim.get("support_status")
        or claim.get("status")
        or "supported"
    ).strip().casefold()
    return {
        "claim_id": claim_id,
        "claim_text": str(claim.get("claim_text") or ""),
        "support_status": support_status,
        "support_score": float(claim.get("support_score", 1.0)),
        "citation_ids": list(normalized_citations),
    }


def _unknown_claim_citations(
    claims: tuple[dict[str, Any], ...],
    known_citation_ids: set[str],
) -> list[str]:
    unknown: list[str] = []
    for claim in claims:
        for citation_id in claim["citation_ids"]:
            if citation_id not in known_citation_ids:
                unknown.append(f"{claim['claim_id']}:{citation_id}")
    return unknown


def _answer_item(item: ToolOutputItemV2) -> ToolOutputItemV2:
    if item.artifact_role != "evidence_view":
        raise ValueError(f"answer item requires evidence_view artifact_role: {item.item_id}")
    return ToolOutputItemV2(
        item_id=item.item_id,
        subject_kind=item.subject_kind,
        subject_id=item.subject_id,
        artifact_role=item.artifact_role,
        authority_level="answer_assertion",
        source_refs=item.source_refs,
        source_status=item.source_status,
        projection_id=item.projection_id,
        score=item.score,
        why_relevant="claim_supported_answer_assertion",
        risk_flags=item.risk_flags,
        metadata={**item.metadata, "promoted_from": item.authority_level},
    )


def _store_answer_output_run(
    conn: sqlite3.Connection,
    *,
    output_run_id: str,
    query: str,
    status: str,
    started_at: str,
    finished_at: str,
    metadata: Mapping[str, Any],
) -> None:
    conn.execute(
        """
        INSERT INTO memory_output_runs (
            output_run_id, query, output_mode, status, started_at, finished_at,
            metadata_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(output_run_id) DO UPDATE SET
            query=excluded.query,
            output_mode=excluded.output_mode,
            status=excluded.status,
            finished_at=excluded.finished_at,
            metadata_json=excluded.metadata_json
        """,
        (
            output_run_id,
            query,
            OutputMode.ANSWER.value,
            status,
            started_at,
            finished_at,
            _json(metadata),
        ),
    )


def _store_answer_output_items(
    conn: sqlite3.Connection,
    *,
    output_run_id: str,
    items: tuple[ToolOutputItemV2, ...],
    created_at: str,
) -> None:
    for index, item in enumerate(items):
        conn.execute(
            """
            INSERT INTO memory_output_items (
                output_item_id, output_run_id, item_index, artifact_id,
                artifact_role, authority_level, source_ref, text, created_at,
                metadata_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(output_item_id) DO UPDATE SET
                artifact_role=excluded.artifact_role,
                authority_level=excluded.authority_level,
                source_ref=excluded.source_ref,
                text=excluded.text,
                metadata_json=excluded.metadata_json
            """,
            (
                _stable_id("answer-output-item", output_run_id, item.item_id, index),
                output_run_id,
                index,
                item.item_id,
                item.artifact_role,
                item.authority_level,
                item.source_refs[0] if item.source_refs else None,
                item.metadata.get("text"),
                created_at,
                _json(item.as_dict()),
            ),
        )


def _store_claim_support_assessments(
    conn: sqlite3.Connection,
    *,
    output_run_id: str,
    claims: tuple[dict[str, Any], ...],
    created_at: str,
) -> None:
    for claim in claims:
        for citation_id in claim["citation_ids"]:
            conn.execute(
                """
                INSERT INTO memory_claim_support_assessments (
                    assessment_id, output_run_id, claim_id, citation_id,
                    support_status, support_score, evidence_json, created_at,
                    metadata_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(assessment_id) DO UPDATE SET
                    support_status=excluded.support_status,
                    support_score=excluded.support_score,
                    evidence_json=excluded.evidence_json,
                    metadata_json=excluded.metadata_json
                """,
                (
                    _stable_id(
                        "claim-support",
                        output_run_id,
                        claim["claim_id"],
                        citation_id,
                    ),
                    output_run_id,
                    claim["claim_id"],
                    citation_id,
                    claim["support_status"],
                    claim["support_score"],
                    _json(
                        {
                            "claim_text": claim["claim_text"],
                            "citation_id": citation_id,
                        }
                    ),
                    created_at,
                    _json({"source": "promote_evidence_package_to_answer"}),
                ),
            )


def _stable_id(*parts: Any) -> str:
    return hashlib.sha256(_json(parts).encode("utf-8")).hexdigest()[:24]


def _json(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def _now() -> str:
    return datetime.now(UTC).isoformat()
