from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from research_x.memory.context import CitationAnnotation
from research_x.memory.document_hashes import memory_document_source_hash
from research_x.memory.embeddings import PRODUCTION_PROVIDERS
from research_x.memory.evidence_invariants import citation_block_reasons
from research_x.memory.retrieval_strategy import DEFAULT_RETRIEVAL_STRATEGIES
from research_x.memory.schema import ensure_memory_schema


@dataclass(frozen=True)
class MemoryAuditReport:
    db_path: str
    documents: int
    fts_rows: int
    relations: int
    orphaned_relations: int
    relation_covered_documents: int
    isolated_documents_by_type: dict[str, int]
    embedding_specs: tuple[dict[str, Any], ...]
    orphaned_feedback: int
    v2_orphans: dict[str, int]
    invalid_json_by_field: dict[str, int]
    invalid_enums_by_field: dict[str, int]
    fixture_artifacts: dict[str, int]
    answer_status_counts: dict[str, int]
    claim_citation_issues: dict[str, int]
    freshness_lineage_issues: dict[str, int]
    strategy_gap_counts: dict[str, int]
    warnings: tuple[str, ...]


def audit_memory_db(db_path: str | Path) -> MemoryAuditReport:
    path = Path(db_path)
    if not path.exists():
        raise FileNotFoundError(f"database not found: {path}")
    with sqlite3.connect(path, timeout=60) as conn:
        conn.row_factory = sqlite3.Row
        ensure_memory_schema(conn)
        documents = _count(conn, "memory_documents")
        fts_rows = _count(conn, "memory_document_fts")
        relations = _count(conn, "memory_relations")
        orphaned_relations = _orphaned_relations(conn)
        relation_covered = _relation_covered_documents(conn)
        isolated = _isolated_documents_by_type(conn)
        specs = _embedding_specs(conn)
        orphaned_feedback = _orphaned_feedback(conn)
        v2_orphans = _v2_orphan_counts(conn)
        invalid_json = _invalid_json_counts(conn)
        invalid_enums = _invalid_enum_counts(conn)
        fixture_artifacts = _fixture_artifact_counts(conn)
        answer_status_counts = _answer_status_counts(conn)
        claim_citation_issues = _claim_citation_issues(conn)
        freshness_lineage_issues = _freshness_lineage_issues(conn)
        strategy_gap_counts = _strategy_gap_counts()
    warnings = _warnings(
        documents=documents,
        fts_rows=fts_rows,
        relations=relations,
        orphaned_relations=orphaned_relations,
        relation_covered=relation_covered,
        isolated=isolated,
        specs=specs,
        orphaned_feedback=orphaned_feedback,
        v2_orphans=v2_orphans,
        invalid_json=invalid_json,
        invalid_enums=invalid_enums,
        fixture_artifacts=fixture_artifacts,
        answer_status_counts=answer_status_counts,
        claim_citation_issues=claim_citation_issues,
        freshness_lineage_issues=freshness_lineage_issues,
        strategy_gap_counts=strategy_gap_counts,
    )
    return MemoryAuditReport(
        db_path=str(path),
        documents=documents,
        fts_rows=fts_rows,
        relations=relations,
        orphaned_relations=orphaned_relations,
        relation_covered_documents=relation_covered,
        isolated_documents_by_type=isolated,
        embedding_specs=tuple(specs),
        orphaned_feedback=orphaned_feedback,
        v2_orphans=v2_orphans,
        invalid_json_by_field=invalid_json,
        invalid_enums_by_field=invalid_enums,
        fixture_artifacts=fixture_artifacts,
        answer_status_counts=answer_status_counts,
        claim_citation_issues=claim_citation_issues,
        freshness_lineage_issues=freshness_lineage_issues,
        strategy_gap_counts=strategy_gap_counts,
        warnings=tuple(warnings),
    )


def audit_report_json(report: MemoryAuditReport) -> str:
    return json.dumps(asdict(report), ensure_ascii=False, indent=2, sort_keys=True)


def format_audit_report(report: MemoryAuditReport) -> str:
    lines = [
        f"db: {report.db_path}",
        f"documents: {report.documents}",
        f"fts rows: {report.fts_rows}",
        f"relations: {report.relations}",
        f"orphaned relations: {report.orphaned_relations}",
        f"relation-covered documents: {report.relation_covered_documents}",
        f"isolated documents by type: {report.isolated_documents_by_type or {}}",
        f"orphaned feedback: {report.orphaned_feedback}",
        f"V2 orphan rows: {report.v2_orphans or {}}",
        f"invalid JSON by field: {report.invalid_json_by_field or {}}",
        f"invalid enum values by field: {report.invalid_enums_by_field or {}}",
        f"fixture artifacts: {report.fixture_artifacts or {}}",
        f"answer statuses: {report.answer_status_counts or {}}",
        f"claim/citation issues: {report.claim_citation_issues or {}}",
        f"freshness/lineage issues: {report.freshness_lineage_issues or {}}",
        f"strategy gap counts: {report.strategy_gap_counts or {}}",
        "embedding specs:",
    ]
    if report.embedding_specs:
        for spec in report.embedding_specs:
            parts = [
                f"{spec['provider']}/{spec['model']}",
                f"dims={spec['dimensions']}",
                f"profile={spec['embedding_profile']}",
                f"template={spec['text_template_version']}",
                f"rows={spec['rows']}",
            ]
            if spec.get("orphaned_rows"):
                parts.append(f"orphaned={spec['orphaned_rows']}")
            if spec.get("source_hash_missing"):
                parts.append(f"source_hash_missing={spec['source_hash_missing']}")
            lines.append("  " + " ".join(parts))
    else:
        lines.append("  none")
    lines.append(f"production-ready: {'no' if report.warnings else 'yes'}")
    if report.warnings:
        lines.append("warnings:")
        lines.extend(f"  - {warning}" for warning in report.warnings)
    else:
        lines.append("warnings: none")
    return "\n".join(lines)


def _count(conn: sqlite3.Connection, table: str) -> int:
    return int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])


def _relation_covered_documents(conn: sqlite3.Connection) -> int:
    return int(
        conn.execute(
            """
            SELECT COUNT(DISTINCT doc_id)
            FROM (
                SELECT source_doc_id AS doc_id FROM memory_relations
                UNION
                SELECT target_doc_id AS doc_id FROM memory_relations
            )
            """
        ).fetchone()[0]
    )


def _isolated_documents_by_type(conn: sqlite3.Connection) -> dict[str, int]:
    rows = conn.execute(
        """
        SELECT d.doc_type, COUNT(*) AS count
        FROM memory_documents d
        LEFT JOIN (
            SELECT source_doc_id AS doc_id FROM memory_relations
            UNION
            SELECT target_doc_id AS doc_id FROM memory_relations
        ) r ON r.doc_id = d.doc_id
        WHERE r.doc_id IS NULL
        GROUP BY d.doc_type
        ORDER BY count DESC, d.doc_type
        """
    ).fetchall()
    return {row["doc_type"]: int(row["count"]) for row in rows}


def _orphaned_relations(conn: sqlite3.Connection) -> int:
    return int(
        conn.execute(
            """
            SELECT COUNT(*)
            FROM memory_relations r
            LEFT JOIN memory_documents s ON s.doc_id = r.source_doc_id
            LEFT JOIN memory_documents t ON t.doc_id = r.target_doc_id
            WHERE s.doc_id IS NULL OR t.doc_id IS NULL
            """
        ).fetchone()[0]
    )


def _orphaned_feedback(conn: sqlite3.Connection) -> int:
    return int(
        conn.execute(
            """
            SELECT COUNT(*)
            FROM memory_feedback f
            LEFT JOIN memory_documents d ON d.doc_id = f.doc_id
            WHERE d.doc_id IS NULL
            """
        ).fetchone()[0]
    )


def _embedding_specs(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT
            e.provider,
            e.model,
            e.dimensions,
            e.embedding_profile,
            e.text_template_version,
            COUNT(*) AS rows,
            SUM(CASE WHEN d.doc_id IS NULL THEN 1 ELSE 0 END) AS orphaned_rows,
            SUM(
                CASE
                    WHEN e.source_doc_hash IS NULL OR TRIM(e.source_doc_hash) = ''
                    THEN 1
                    ELSE 0
                END
            ) AS source_hash_missing
        FROM memory_embeddings e
        LEFT JOIN memory_documents d ON d.doc_id = e.doc_id
        GROUP BY
            e.provider,
            e.model,
            e.dimensions,
            e.embedding_profile,
            e.text_template_version
        ORDER BY rows DESC, provider, model, dimensions, embedding_profile, text_template_version
        """
    ).fetchall()
    return [
        {
            "provider": row["provider"],
            "model": row["model"],
            "dimensions": int(row["dimensions"]),
            "embedding_profile": row["embedding_profile"],
            "text_template_version": row["text_template_version"],
            "rows": int(row["rows"]),
            "orphaned_rows": int(row["orphaned_rows"] or 0),
            "source_hash_missing": int(row["source_hash_missing"] or 0),
        }
        for row in rows
    ]


def _invalid_json_counts(conn: sqlite3.Connection) -> dict[str, int]:
    field_specs = [
        ("memory_documents", "metadata_json"),
        ("memory_feedback", "query_terms_json"),
        ("memory_feedback", "intents_json"),
        ("memory_relations", "evidence_json"),
        ("memory_external_runs", "parameters_json"),
        ("memory_external_items", "metadata_json"),
        ("memory_search_runs", "query_plan_json"),
        ("memory_search_runs", "parameters_json"),
        ("memory_search_results", "metadata_json"),
        ("memory_tool_calls", "input_json"),
        ("memory_tool_calls", "output_json"),
        ("memory_context_chunks", "metadata_json"),
        ("memory_citation_annotations", "metadata_json"),
        ("memory_answer_runs", "retrieval_config_json"),
        ("memory_answer_runs", "structured_json"),
        ("memory_workflow_runs", "metadata_json"),
        ("memory_workflow_steps", "input_json"),
        ("memory_workflow_steps", "output_json"),
        ("memory_eval_runs", "parameters_json"),
        ("memory_eval_results", "matched_terms_json"),
        ("memory_eval_results", "retrieval_engines_json"),
        ("memory_eval_results", "source_kinds_json"),
        ("memory_eval_results", "notes_json"),
        ("memory_eval_results", "metadata_json"),
    ]
    if _table_exists(conn, "ai_labels"):
        field_specs.append(("ai_labels", "tags_json"))
    invalid: dict[str, int] = {}
    for table, column in field_specs:
        count = 0
        rows = conn.execute(
            f"""
            SELECT {column}
            FROM {table}
            WHERE {column} IS NOT NULL
              AND TRIM({column}) != ''
            """
        ).fetchall()
        for row in rows:
            try:
                json.loads(row[column])
            except (TypeError, json.JSONDecodeError):
                count += 1
        if count:
            invalid[f"{table}.{column}"] = count
    return invalid


def _v2_orphan_counts(conn: sqlite3.Connection) -> dict[str, int]:
    specs = [
        (
            "memory_external_items.run_id",
            """
            SELECT COUNT(*)
            FROM memory_external_items i
            LEFT JOIN memory_external_runs r ON r.run_id = i.run_id
            WHERE r.run_id IS NULL
            """,
        ),
        (
            "memory_search_results.run_id",
            """
            SELECT COUNT(*)
            FROM memory_search_results sr
            LEFT JOIN memory_search_runs r ON r.run_id = sr.run_id
            WHERE r.run_id IS NULL
            """,
        ),
        (
            "memory_search_results.doc_id",
            """
            SELECT COUNT(*)
            FROM memory_search_results sr
            LEFT JOIN memory_documents d ON d.doc_id = sr.doc_id
            WHERE d.doc_id IS NULL
            """,
        ),
        (
            "memory_tool_calls.run_id",
            """
            SELECT COUNT(*)
            FROM memory_tool_calls tc
            LEFT JOIN memory_search_runs r ON r.run_id = tc.run_id
            WHERE tc.run_id IS NOT NULL
              AND r.run_id IS NULL
            """,
        ),
        (
            "memory_context_chunks.run_id",
            """
            SELECT COUNT(*)
            FROM memory_context_chunks c
            LEFT JOIN memory_search_runs r ON r.run_id = c.run_id
            WHERE c.run_id IS NOT NULL
              AND r.run_id IS NULL
            """,
        ),
        (
            "memory_citation_annotations.chunk_id",
            """
            SELECT COUNT(*)
            FROM memory_citation_annotations ca
            LEFT JOIN memory_context_chunks c ON c.chunk_id = ca.chunk_id
            WHERE c.chunk_id IS NULL
            """,
        ),
        (
            "memory_citation_annotations.answer_id",
            """
            SELECT COUNT(*)
            FROM memory_citation_annotations ca
            LEFT JOIN memory_answer_runs a ON a.answer_id = ca.answer_id
            WHERE ca.answer_id IS NOT NULL
              AND a.answer_id IS NULL
            """,
        ),
        (
            "memory_answer_runs.workflow_id",
            """
            SELECT COUNT(*)
            FROM memory_answer_runs a
            LEFT JOIN memory_workflow_runs w ON w.workflow_id = a.workflow_id
            WHERE a.workflow_id IS NOT NULL
              AND w.workflow_id IS NULL
            """,
        ),
        (
            "memory_workflow_steps.workflow_id",
            """
            SELECT COUNT(*)
            FROM memory_workflow_steps s
            LEFT JOIN memory_workflow_runs w ON w.workflow_id = s.workflow_id
            WHERE w.workflow_id IS NULL
            """,
        ),
        (
            "memory_eval_results.run_id",
            """
            SELECT COUNT(*)
            FROM memory_eval_results er
            LEFT JOIN memory_eval_runs r ON r.run_id = er.run_id
            WHERE r.run_id IS NULL
            """,
        ),
    ]
    counts: dict[str, int] = {}
    for key, sql in specs:
        count = int(conn.execute(sql).fetchone()[0])
        if count:
            counts[key] = count
    return counts


def _invalid_enum_counts(conn: sqlite3.Connection) -> dict[str, int]:
    specs = [
        (
            "memory_external_runs.provider_role",
            "memory_external_runs",
            "provider_role",
            {"index_provider", "fetch_agent", "llm_context_provider", "answer_engine"},
        ),
        (
            "memory_search_results.source_kind",
            "memory_search_results",
            "source_kind",
            {"local_x_db", "official", "secondary", "user_generated"},
        ),
        (
            "memory_search_results.provider_role",
            "memory_search_results",
            "provider_role",
            {"index_provider"},
        ),
        (
            "memory_search_results.evidence_status",
            "memory_search_results",
            "evidence_status",
            {"fact", "inference", "unconfirmed"},
        ),
        (
            "memory_tool_calls.provider_role",
            "memory_tool_calls",
            "provider_role",
            {"index_provider", "fetch_agent", "llm_context_provider", "answer_engine"},
        ),
        (
            "memory_context_chunks.source_kind",
            "memory_context_chunks",
            "source_kind",
            {"local_x_db", "official", "secondary", "user_generated"},
        ),
        (
            "memory_context_chunks.provider_role",
            "memory_context_chunks",
            "provider_role",
            {"context_builder", "fetch_agent", "llm_context_provider", "answer_engine"},
        ),
        (
            "memory_citation_annotations.source_kind",
            "memory_citation_annotations",
            "source_kind",
            {"local_x_db", "official", "secondary", "user_generated"},
        ),
        (
            "memory_citation_annotations.evidence_status",
            "memory_citation_annotations",
            "evidence_status",
            {"fact", "inference", "unconfirmed"},
        ),
        (
            "memory_answer_runs.status",
            "memory_answer_runs",
            "status",
            {"ok", "needs_review", "error"},
        ),
        (
            "memory_workflow_runs.status",
            "memory_workflow_runs",
            "status",
            {"running", "ok", "needs_review", "error"},
        ),
        (
            "memory_workflow_runs.stop_reason",
            "memory_workflow_runs",
            "stop_reason",
            {
                "enough_evidence",
                "no_local_evidence",
                "external_context_needed",
                "stale_or_conflicting_evidence",
                "rate_limited",
                "provider_error",
                "needs_user_review",
                "budget_exhausted",
            },
        ),
        (
            "memory_workflow_steps.status",
            "memory_workflow_steps",
            "status",
            {"ok", "needs_review", "error"},
        ),
        (
            "memory_eval_runs.status",
            "memory_eval_runs",
            "status",
            {"ok", "needs_review", "fail"},
        ),
        (
            "memory_eval_results.status",
            "memory_eval_results",
            "status",
            {"ok", "needs_review", "fail"},
        ),
    ]
    counts: dict[str, int] = {}
    for key, table, column, allowed in specs:
        placeholders = ", ".join("?" for _ in allowed)
        sql = f"""
            SELECT COUNT(*)
            FROM {table}
            WHERE {column} IS NOT NULL
              AND {column} NOT IN ({placeholders})
        """
        count = int(conn.execute(sql, tuple(sorted(allowed))).fetchone()[0])
        if count:
            counts[key] = count
    return counts


def _fixture_artifact_counts(conn: sqlite3.Connection) -> dict[str, int]:
    specs = [
        (
            "memory_external_runs.fake_provider",
            """
            SELECT COUNT(*)
            FROM memory_external_runs
            WHERE provider = 'fake'
               OR endpoint LIKE 'memory://fake%'
            """,
        ),
        (
            "memory_external_items.fixture",
            """
            SELECT COUNT(*)
            FROM memory_external_items
            WHERE metadata_json LIKE '%"fixture": true%'
               OR source = 'example.invalid'
            """,
        ),
        (
            "memory_tool_calls.fake_provider",
            """
            SELECT COUNT(*)
            FROM memory_tool_calls
            WHERE provider = 'fake'
            """,
        ),
        (
            "memory_context_chunks.fixture",
            """
            SELECT COUNT(*)
            FROM memory_context_chunks
            WHERE provider = 'fake'
               OR metadata_json LIKE '%"fixture": true%'
               OR chunk_text LIKE '%Fake extracted page%'
            """,
        ),
        (
            "memory_answer_runs.fake_provider",
            """
            SELECT COUNT(*)
            FROM memory_answer_runs
            WHERE structured_json LIKE '%"mode": "deterministic_fake"%'
            """,
        ),
    ]
    counts: dict[str, int] = {}
    for key, sql in specs:
        count = int(conn.execute(sql).fetchone()[0])
        if count:
            counts[key] = count
    return counts


def _answer_status_counts(conn: sqlite3.Connection) -> dict[str, int]:
    rows = conn.execute(
        """
        SELECT status, COUNT(*) AS count
        FROM memory_answer_runs
        GROUP BY status
        ORDER BY status
        """
    ).fetchall()
    return {str(row["status"]): int(row["count"]) for row in rows}


def _claim_citation_issues(conn: sqlite3.Connection) -> dict[str, int]:
    issues: dict[str, int] = {}
    answers = conn.execute(
        """
        SELECT answer_id, answer_text, structured_json, status
        FROM memory_answer_runs
        WHERE answer_text IS NOT NULL
          AND TRIM(answer_text) != ''
        """
    ).fetchall()
    for answer in answers:
        answer_id = str(answer["answer_id"])
        status = str(answer["status"] or "")
        text = str(answer["answer_text"] or "")
        structured = _loads_json(answer["structured_json"], default={})
        citations = conn.execute(
            """
            SELECT
                ca.citation_id, ca.chunk_id, ca.source_kind, ca.source_id,
                ca.source_url, ca.title, ca.field_path, ca.support_type,
                ca.evidence_status, ca.confidence, ca.created_at,
                ca.answer_start_index, ca.answer_end_index, ca.metadata_json,
                c.source_id AS chunk_source_id, c.metadata_json AS chunk_metadata_json
            FROM memory_citation_annotations ca
            LEFT JOIN memory_context_chunks c ON c.chunk_id = ca.chunk_id
            WHERE answer_id = ?
            """,
            (answer_id,),
        ).fetchall()
        markers = _answer_markers(text)
        citation_markers = [marker for row in citations if (marker := _citation_marker(row))]
        extra_markers = set(markers) - set(citation_markers)
        missing_answer_markers = set(citation_markers) - set(markers)
        duplicate_markers = len(markers) - len(set(markers))
        if status == "ok" and extra_markers:
            _increment(issues, "ok_answer_with_unmapped_citation_markers", len(extra_markers))
        if status == "ok" and missing_answer_markers:
            _increment(
                issues,
                "ok_answer_with_unrendered_citation_markers",
                len(missing_answer_markers),
            )
        if status == "ok" and duplicate_markers:
            _increment(issues, "ok_answer_with_duplicate_citation_markers", duplicate_markers)
        if status == "ok" and not citations:
            _increment(issues, "ok_answer_without_citations")
        missing_markers = (
            structured.get("missing_citation_markers")
            if isinstance(structured, dict)
            else None
        )
        if status == "ok" and missing_markers:
            _increment(issues, "ok_answer_with_missing_citation_markers")
        selected_chunk_ids = _selected_chunk_ids(structured)
        if status == "ok" and selected_chunk_ids:
            outside_selection = [
                row for row in citations if str(row["chunk_id"] or "") not in selected_chunk_ids
            ]
            if outside_selection:
                _increment(
                    issues,
                    "ok_answer_cites_chunk_outside_selection",
                    len(outside_selection),
                )
        uncited_context = [
            row for row in citations if str(row["support_type"] or "") == "uncited_context"
        ]
        if status == "ok" and uncited_context:
            _increment(issues, "ok_answer_with_uncited_context", len(uncited_context))
        missing_spans = [
            row
            for row in citations
            if row["answer_start_index"] is None or row["answer_end_index"] is None
        ]
        if status == "ok" and missing_spans:
            _increment(issues, "ok_answer_with_missing_citation_spans", len(missing_spans))
        bad_spans = [
            row
            for row in citations
            if row["answer_start_index"] is not None
            and row["answer_end_index"] is not None
            and text[int(row["answer_start_index"]): int(row["answer_end_index"])]
            != (_citation_marker(row) or "")
        ]
        if status == "ok" and bad_spans:
            _increment(issues, "ok_answer_with_invalid_citation_spans", len(bad_spans))
        non_fact = [
            row for row in citations if str(row["evidence_status"] or "") != "fact"
        ]
        if status == "ok" and non_fact:
            _increment(issues, "ok_answer_cites_non_fact_evidence", len(non_fact))
        non_ready = [row for row in citations if _citation_block_reasons_for_row(row)]
        if status == "ok" and non_ready:
            _increment(issues, "ok_answer_cites_non_ready_evidence", len(non_ready))
        not_evidence = [
            row
            for row in citations
            if "not_evidence" in _citation_block_reasons_for_row(row)
        ]
        if status == "ok" and not_evidence:
            _increment(issues, "ok_answer_cites_not_evidence", len(not_evidence))
        stale = [
            row
            for row in citations
            if "stale_evidence" in _citation_block_reasons_for_row(row)
        ]
        if status == "ok" and stale:
            _increment(issues, "ok_answer_cites_stale_evidence", len(stale))
        source_drift = [
            row for row in citations if _citation_source_hash_drift(conn, row)
        ]
        if status == "ok" and source_drift:
            _increment(issues, "ok_answer_citation_source_hash_drift", len(source_drift))
        uncited_claims = _uncited_claim_lines(text)
        if status == "ok" and uncited_claims:
            _increment(issues, "ok_answer_with_uncited_claim_lines", len(uncited_claims))
    return issues


def _citation_block_reasons_for_row(row: sqlite3.Row) -> tuple[str, ...]:
    metadata = _loads_json(row["metadata_json"], default={})
    return citation_block_reasons(
        CitationAnnotation(
            citation_id=str(row["citation_id"] or ""),
            answer_id=None,
            chunk_id=str(row["chunk_id"] or ""),
            source_kind=str(row["source_kind"] or ""),
            source_id=str(row["source_id"] or ""),
            source_url=row["source_url"],
            title=str(row["title"] or ""),
            field_path=str(row["field_path"] or ""),
            support_type=str(row["support_type"] or ""),
            evidence_status=str(row["evidence_status"] or ""),
            confidence=float(row["confidence"] or 0.0),
            created_at=str(row["created_at"] or ""),
            metadata=metadata,
        )
    )


def _freshness_lineage_issues(conn: sqlite3.Connection) -> dict[str, int]:
    issues: dict[str, int] = {}
    docs = conn.execute(
        """
        SELECT doc_id, title, body, compact_text, metadata_json, source_doc_hash
        FROM memory_documents
        """
    ).fetchall()
    for doc in docs:
        stored = str(doc["source_doc_hash"] or "")
        if not stored:
            _increment(issues, "documents_missing_source_doc_hash")
            continue
        if stored != memory_document_source_hash(doc):
            _increment(issues, "documents_stale_source_doc_hash")
    stale_embeddings = int(
        conn.execute(
            """
            SELECT COUNT(*)
            FROM memory_embeddings e
            JOIN memory_documents d ON d.doc_id = e.doc_id
            WHERE e.source_doc_hash IS NULL
               OR e.source_doc_hash != d.source_doc_hash
            """
        ).fetchone()[0]
    )
    if stale_embeddings:
        issues["embeddings_stale_source_doc_hash"] = stale_embeddings
    if _table_exists(conn, "memory_retrieval_text_profiles"):
        citation_included_retrieval_text = int(
            conn.execute(
                """
                SELECT COUNT(*)
                FROM memory_retrieval_text_profiles
                WHERE citation_excluded != 1
                """
            ).fetchone()[0]
        )
        stale_retrieval_text = int(
            conn.execute(
                """
                SELECT COUNT(*)
                FROM memory_retrieval_text_profiles p
                JOIN memory_documents d ON d.doc_id = p.doc_id
                WHERE p.source_doc_hash IS NULL
                   OR p.source_doc_hash != d.source_doc_hash
                """
            ).fetchone()[0]
        )
        orphaned_retrieval_text = int(
            conn.execute(
                """
                SELECT COUNT(*)
                FROM memory_retrieval_text_profiles p
                LEFT JOIN memory_documents d ON d.doc_id = p.doc_id
                WHERE d.doc_id IS NULL
                """
            ).fetchone()[0]
        )
        profile_ids = {
            str(row["profile_id"])
            for row in conn.execute("SELECT profile_id FROM memory_retrieval_text_profiles")
        }
        fts_profile_ids = tuple(
            str(row["profile_id"])
            for row in conn.execute("SELECT profile_id FROM memory_retrieval_text_fts")
        )
        fts_profile_id_set = set(fts_profile_ids)
        orphaned_retrieval_text_fts = sum(
            1 for profile_id in fts_profile_ids if profile_id not in profile_ids
        )
        missing_retrieval_text_fts = sum(
            1 for profile_id in profile_ids if profile_id not in fts_profile_id_set
        )
        if citation_included_retrieval_text:
            issues["retrieval_text_not_citation_excluded"] = citation_included_retrieval_text
        if stale_retrieval_text:
            issues["retrieval_text_stale_source_doc_hash"] = stale_retrieval_text
        if orphaned_retrieval_text:
            issues["retrieval_text_orphaned_documents"] = orphaned_retrieval_text
        if orphaned_retrieval_text_fts:
            issues["retrieval_text_fts_orphaned_profiles"] = orphaned_retrieval_text_fts
        if missing_retrieval_text_fts:
            issues["retrieval_text_profiles_missing_fts"] = missing_retrieval_text_fts
    if _table_exists(conn, "memory_query_transforms"):
        citation_included_transforms = int(
            conn.execute(
                """
                SELECT COUNT(*)
                FROM memory_query_transforms
                WHERE citation_excluded != 1
                """
            ).fetchone()[0]
        )
        if citation_included_transforms:
            issues["query_transforms_not_citation_excluded"] = citation_included_transforms
    if _table_exists(conn, "memory_index_membership"):
        stale_memberships = int(
            conn.execute(
                """
                SELECT COUNT(*)
                FROM memory_index_membership m
                JOIN memory_documents d ON d.doc_id = m.artifact_id
                WHERE m.artifact_kind = 'memory_document'
                  AND m.membership_status = 'active'
                  AND m.source_hash IS NOT NULL
                  AND d.source_doc_hash IS NOT NULL
                  AND m.source_hash != d.source_doc_hash
                """
            ).fetchone()[0]
        )
        orphaned_memberships = int(
            conn.execute(
                """
                SELECT COUNT(*)
                FROM memory_index_membership m
                LEFT JOIN memory_documents d ON d.doc_id = m.artifact_id
                WHERE m.artifact_kind = 'memory_document'
                  AND m.membership_status = 'active'
                  AND d.doc_id IS NULL
                """
            ).fetchone()[0]
        )
        if stale_memberships:
            issues["index_membership_stale_source_hash"] = stale_memberships
        if orphaned_memberships:
            issues["index_membership_orphaned_documents"] = orphaned_memberships
    if _table_exists(conn, "memory_visual_recall_evidence"):
        overclaimed_visual = int(
            conn.execute(
                """
                SELECT COUNT(*)
                FROM memory_visual_recall_evidence
                WHERE citation_ready = 1
                  AND evidence_level IN (
                    'raw_media_match',
                    'visual_recall_evidence',
                    'media_role_profile',
                    'codex_observation'
                  )
                """
            ).fetchone()[0]
        )
        if overclaimed_visual:
            issues["visual_recall_overclaimed_citation_ready"] = overclaimed_visual
    return issues


def _strategy_gap_counts() -> dict[str, int]:
    counts: dict[str, int] = {}
    for strategy_obj in DEFAULT_RETRIEVAL_STRATEGIES:
        strategy = strategy_obj.as_dict()
        adoption = str(strategy.get("adoption") or "")
        _classify_strategy_status(counts, adoption)
        for candidate in strategy.get("candidates") or ():
            if not isinstance(candidate, dict):
                continue
            _classify_strategy_status(counts, str(candidate.get("status") or ""))
    return {key: value for key, value in counts.items() if value}


def _classify_strategy_status(counts: dict[str, int], status: str) -> None:
    if not status:
        return
    normalized = status.strip().lower()
    if normalized in {"needs_implementation", "requires_implementation", "partially_implemented"}:
        _increment(counts, "no_spend_gap")
        return
    if normalized.startswith("deferred_") or normalized in {
        "needs_real_api_eval",
        "fixed_eval_candidate",
        "provider_quota_gate",
    }:
        _increment(counts, "human_gate")
        return
    if normalized in {
        "legacy_comparison_only",
        "latest_alias_optional",
        "older_comparison_only",
        "reference_only",
    }:
        _increment(counts, "reference_only")
        return
    if "implemented" in normalized or normalized in {
        "candidate",
        "eval_only",
        "requires_eval",
        "always_on_control_surface",
        "workflow_hint_not_evidence",
        "eval_only_explicit",
        "conditional_eval",
        "requires_explicit_eval",
        "text_only_bridge_candidate",
        "always_on_baseline",
        "always_on_guard",
        "implemented_audit_gate",
        "implemented_lineage_audit",
        "implemented_projection",
        "provider_quota_gate",
    }:
        _increment(counts, "implemented_or_candidate")
        return
    _increment(counts, f"unclassified_status:{normalized}")


def _selected_chunk_ids(structured: Any) -> set[str]:
    if not isinstance(structured, dict):
        return set()
    values: set[str] = set()
    for key in ("selected_chunk_ids", "used_chunk_ids"):
        raw_values = structured.get(key)
        if isinstance(raw_values, list):
            values.update(str(value) for value in raw_values if value is not None)
    context_selection = structured.get("context_selection")
    if isinstance(context_selection, dict):
        raw_values = context_selection.get("selected_chunk_ids")
        if isinstance(raw_values, list):
            values.update(str(value) for value in raw_values if value is not None)
    return values


def _uncited_claim_lines(answer_text: str) -> list[str]:
    lines = []
    for raw_line in answer_text.splitlines():
        line = raw_line.strip()
        if not line or re_match_citation_marker(line):
            continue
        if _is_nonclaim_answer_line(line):
            continue
        if not _looks_like_claim_line(line):
            continue
        lines.append(line)
    return lines


def _answer_markers(text: str) -> list[str]:
    return [match.group(0) for match in re.finditer(r"\[(\d{1,3})\]", text)]


def re_match_citation_marker(text: str) -> bool:
    return bool(_answer_markers(text))


def _citation_marker(row: sqlite3.Row) -> str | None:
    metadata = _loads_json(row["metadata_json"], default={})
    if isinstance(metadata, dict) and metadata.get("marker"):
        return str(metadata["marker"])
    display_index = metadata.get("display_index") if isinstance(metadata, dict) else None
    if display_index is None:
        return None
    return f"[{display_index}]"


def _citation_source_hash_drift(conn: sqlite3.Connection, row: sqlite3.Row) -> bool:
    source_id = str(row["source_id"] or "")
    if not source_id:
        return False
    doc = conn.execute(
        """
        SELECT doc_id, title, body, compact_text, metadata_json, source_doc_hash
        FROM memory_documents
        WHERE doc_id = ?
        """,
        (source_id,),
    ).fetchone()
    if doc is None:
        return False
    current_hash = memory_document_source_hash(doc)
    if str(doc["source_doc_hash"] or "") != current_hash:
        return True
    chunk_metadata = _loads_json(row["chunk_metadata_json"], default={})
    if not isinstance(chunk_metadata, dict):
        return False
    chunk_hash = chunk_metadata.get("source_doc_hash")
    return bool(chunk_hash and str(chunk_hash) != current_hash)


def _is_nonclaim_answer_line(line: str) -> bool:
    prefixes = (
        "質問:",
        "根拠ベースの回答",
        "推論:",
        "context:",
        "prompt_version:",
        "根拠になるコンテキストが見つかりません",
        "追加取得または検索条件の変更が必要",
    )
    stripped = line.lstrip("- ").strip()
    return any(stripped.startswith(prefix) for prefix in prefixes)


def _looks_like_claim_line(line: str) -> bool:
    text = line.lstrip("- ").strip()
    if len(text) < 12:
        return False
    has_letter_or_digit = any(char.isalpha() or char.isdigit() for char in text)
    has_japanese = any(
        "\u3040" <= char <= "\u30ff" or "\u4e00" <= char <= "\u9fff"
        for char in text
    )
    return has_letter_or_digit or has_japanese


def _increment(values: dict[str, int], key: str, amount: int = 1) -> None:
    values[key] = values.get(key, 0) + amount


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        """
        SELECT 1
        FROM sqlite_master
        WHERE type IN ('table', 'view')
          AND name = ?
        LIMIT 1
        """,
        (table,),
    ).fetchone()
    return bool(row)


def _loads_json(value: Any, *, default: Any) -> Any:
    if value is None:
        return default
    if isinstance(value, dict | list):
        return value
    try:
        return json.loads(str(value))
    except json.JSONDecodeError:
        return default


def _warnings(
    *,
    documents: int,
    fts_rows: int,
    relations: int,
    orphaned_relations: int,
    relation_covered: int,
    isolated: dict[str, int],
    specs: list[dict[str, Any]],
    orphaned_feedback: int,
    v2_orphans: dict[str, int],
    invalid_json: dict[str, int],
    invalid_enums: dict[str, int],
    fixture_artifacts: dict[str, int],
    answer_status_counts: dict[str, int],
    claim_citation_issues: dict[str, int],
    freshness_lineage_issues: dict[str, int],
    strategy_gap_counts: dict[str, int],
) -> list[str]:
    warnings: list[str] = []
    if documents == 0:
        warnings.append("memory_documents is empty; run memory build-corpus")
    if fts_rows != documents:
        warnings.append(f"FTS row count differs from documents: fts={fts_rows} docs={documents}")
    if relations == 0 and documents:
        warnings.append("memory_relations is empty; run memory build-relations")
    if orphaned_relations:
        warnings.append(
            f"{orphaned_relations} relation edges point to missing documents; "
            "run memory build-relations"
        )
    if relation_covered < documents:
        warnings.append(
            f"{documents - relation_covered} documents have no relation edge: {isolated}"
        )
    if orphaned_feedback:
        warnings.append(
            f"{orphaned_feedback} feedback rows point to missing documents; "
            "review or rebuild memory feedback"
        )
    if v2_orphans:
        warnings.append(f"V2 evidence graph has orphan rows: {v2_orphans}")
    if invalid_json:
        warnings.append(f"invalid JSON detected: {invalid_json}")
    if invalid_enums:
        warnings.append(f"invalid enum values detected: {invalid_enums}")
    if fixture_artifacts:
        warnings.append(
            "fixture/fake memory artifacts are present; "
            f"do not use them as production evidence: {fixture_artifacts}"
        )
    review_answers = {
        status: count
        for status, count in answer_status_counts.items()
        if status in {"needs_review", "error"} and count
    }
    if review_answers:
        warnings.append(
            "stored answer artifacts need review or regeneration: "
            f"{review_answers}"
        )
    if claim_citation_issues:
        warnings.append(
            "claim/citation verification issues detected: "
            f"{claim_citation_issues}"
        )
    if freshness_lineage_issues:
        warnings.append(
            "freshness/projection lineage issues detected: "
            f"{freshness_lineage_issues}"
        )
    if strategy_gap_counts.get("no_spend_gap"):
        warnings.append(
            "retrieval strategy catalog still has no-spend implementation gaps: "
            f"{strategy_gap_counts}"
        )
    production_specs = [
        spec
        for spec in specs
        if spec["provider"] in PRODUCTION_PROVIDERS
    ]
    if specs and not production_specs:
        warnings.append(
            "only local_hash embeddings are present; "
            "this is diagnostic, not production semantic search"
        )
    for spec in specs:
        if int(spec["rows"]) < documents:
            warnings.append(
                f"embedding index incomplete for {spec['provider']}/{spec['model']}: "
                f"{spec['rows']}/{documents}"
            )
        if int(spec.get("orphaned_rows") or 0):
            warnings.append(
                f"embedding index has stale rows for {spec['provider']}/{spec['model']}: "
                f"orphaned={spec['orphaned_rows']}"
            )
        if int(spec.get("source_hash_missing") or 0):
            warnings.append(
                f"embedding index lacks source hashes for {spec['provider']}/{spec['model']} "
                f"profile={spec['embedding_profile']} "
                f"template={spec['text_template_version']}: "
                f"missing={spec['source_hash_missing']}; rebuild memory embeddings"
            )
    return warnings
