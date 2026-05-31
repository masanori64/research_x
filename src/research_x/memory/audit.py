from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

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
    invalid_json_by_field: dict[str, int]
    fixture_artifacts: dict[str, int]
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
        invalid_json = _invalid_json_counts(conn)
        fixture_artifacts = _fixture_artifact_counts(conn)
    warnings = _warnings(
        documents=documents,
        fts_rows=fts_rows,
        relations=relations,
        orphaned_relations=orphaned_relations,
        relation_covered=relation_covered,
        isolated=isolated,
        specs=specs,
        orphaned_feedback=orphaned_feedback,
        invalid_json=invalid_json,
        fixture_artifacts=fixture_artifacts,
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
        invalid_json_by_field=invalid_json,
        fixture_artifacts=fixture_artifacts,
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
        f"invalid JSON by field: {report.invalid_json_by_field or {}}",
        f"fixture artifacts: {report.fixture_artifacts or {}}",
        "embedding specs:",
    ]
    if report.embedding_specs:
        for spec in report.embedding_specs:
            parts = [
                f"{spec['provider']}/{spec['model']}",
                f"dims={spec['dimensions']}",
                f"rows={spec['rows']}",
            ]
            if spec.get("orphaned_rows"):
                parts.append(f"orphaned={spec['orphaned_rows']}")
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
            COUNT(*) AS rows,
            SUM(CASE WHEN d.doc_id IS NULL THEN 1 ELSE 0 END) AS orphaned_rows
        FROM memory_embeddings e
        LEFT JOIN memory_documents d ON d.doc_id = e.doc_id
        GROUP BY e.provider, e.model, e.dimensions
        ORDER BY rows DESC, provider, model, dimensions
        """
    ).fetchall()
    return [
        {
            "provider": row["provider"],
            "model": row["model"],
            "dimensions": int(row["dimensions"]),
            "rows": int(row["rows"]),
            "orphaned_rows": int(row["orphaned_rows"] or 0),
        }
        for row in rows
    ]


def _invalid_json_counts(conn: sqlite3.Connection) -> dict[str, int]:
    field_specs = [
        ("memory_documents", "metadata_json"),
        ("memory_relations", "evidence_json"),
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
    invalid_json: dict[str, int],
    fixture_artifacts: dict[str, int],
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
    if invalid_json:
        warnings.append(f"invalid JSON detected: {invalid_json}")
    if fixture_artifacts:
        warnings.append(
            "fixture/fake memory artifacts are present; "
            f"do not use them as production evidence: {fixture_artifacts}"
        )
    if not specs and documents:
        warnings.append("no embeddings found; run memory build-embeddings with openai or gemini")
    production_specs = [spec for spec in specs if spec["provider"] in {"openai", "gemini"}]
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
    return warnings
