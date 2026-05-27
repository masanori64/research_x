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
    relation_covered_documents: int
    isolated_documents_by_type: dict[str, int]
    embedding_specs: tuple[dict[str, Any], ...]
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
        relation_covered = _relation_covered_documents(conn)
        isolated = _isolated_documents_by_type(conn)
        specs = _embedding_specs(conn)
    warnings = _warnings(
        documents=documents,
        fts_rows=fts_rows,
        relations=relations,
        relation_covered=relation_covered,
        isolated=isolated,
        specs=specs,
    )
    return MemoryAuditReport(
        db_path=str(path),
        documents=documents,
        fts_rows=fts_rows,
        relations=relations,
        relation_covered_documents=relation_covered,
        isolated_documents_by_type=isolated,
        embedding_specs=tuple(specs),
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
        f"relation-covered documents: {report.relation_covered_documents}",
        f"isolated documents by type: {report.isolated_documents_by_type or {}}",
        "embedding specs:",
    ]
    if report.embedding_specs:
        for spec in report.embedding_specs:
            lines.append(
                "  "
                + " ".join(
                    [
                        f"{spec['provider']}/{spec['model']}",
                        f"dims={spec['dimensions']}",
                        f"rows={spec['rows']}",
                    ]
                )
            )
    else:
        lines.append("  none")
    if report.warnings:
        lines.append("warnings:")
        lines.extend(f"  - {warning}" for warning in report.warnings)
    else:
        lines.append("warnings: none")
    return "\n".join(lines)


def _count(conn: sqlite3.Connection, table: str) -> int:
    try:
        return int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
    except sqlite3.OperationalError:
        return 0


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


def _embedding_specs(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT provider, model, dimensions, COUNT(*) AS rows
        FROM memory_embeddings
        GROUP BY provider, model, dimensions
        ORDER BY rows DESC, provider, model, dimensions
        """
    ).fetchall()
    return [
        {
            "provider": row["provider"],
            "model": row["model"],
            "dimensions": int(row["dimensions"]),
            "rows": int(row["rows"]),
        }
        for row in rows
    ]


def _warnings(
    *,
    documents: int,
    fts_rows: int,
    relations: int,
    relation_covered: int,
    isolated: dict[str, int],
    specs: list[dict[str, Any]],
) -> list[str]:
    warnings: list[str] = []
    if documents == 0:
        warnings.append("memory_documents is empty; run memory build-corpus")
    if fts_rows != documents:
        warnings.append(f"FTS row count differs from documents: fts={fts_rows} docs={documents}")
    if relations == 0 and documents:
        warnings.append("memory_relations is empty; run memory build-relations")
    if relation_covered < documents:
        warnings.append(
            f"{documents - relation_covered} documents have no relation edge: {isolated}"
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
    return warnings
