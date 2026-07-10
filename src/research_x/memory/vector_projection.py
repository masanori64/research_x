from __future__ import annotations

import hashlib
import json
import sqlite3
import time
import uuid
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np

from research_x.memory.audit_events import record_audit_event
from research_x.memory.embeddings import (
    EmbeddingSpec,
    SemanticHit,
    _embedder,
    _embedding_document_count,
    _embedding_rows,
    _resolve_available_spec,
    _resolve_spec_for_space_id,
    _semantic_matrix_from_rows,
    embedding_provider_signal_policy,
    require_embedding_provider_quota_allowed,
    semantic_search_memory,
)
from research_x.memory.schema import ensure_memory_schema

VECTOR_PROJECTION_KIND = "local_vector_projection"
VECTOR_PROJECTION_BUILDER_VERSION = "local-vector-projection-v1"
VECTOR_PROJECTION_FULL_SELECTION_POLICY = "current_embeddings"
VECTOR_PROJECTION_PARTIAL_SELECTION_POLICY = "partial_current_embeddings_explicit"
SUPPORTED_VECTOR_BACKENDS = ("numpy", "turbovec")
BENCHMARK_VECTOR_BACKENDS = ("numpy", "turbovec", "zvec")
DEFAULT_VECTOR_INDEX_DIR = Path("runs") / "memory_vector_indexes"


@dataclass(frozen=True)
class VectorProjectionBuildSummary:
    db_path: str
    generation_id: str
    space_id: str
    backend: str
    provider: str
    model: str
    dimensions: int
    embedding_profile: str
    text_template_version: str
    bit_width: int | None
    documents: int
    expected_documents: int
    missing_documents: int
    index_path: str
    mapping_path: str
    source_scope: str
    status: str
    production_eligible: bool
    not_evidence: bool


@dataclass(frozen=True)
class VectorProjectionCoverage:
    db_path: str
    generation_id: str | None
    space_id: str | None
    backend: str | None
    provider: str | None
    model: str | None
    dimensions: int | None
    embedding_profile: str | None
    text_template_version: str | None
    projection_documents: int
    expected_documents: int
    current_memberships: int
    stale_memberships: int
    missing_memberships: int
    index_path: str | None
    index_exists: bool
    status: str
    partial: bool
    production_eligible: bool
    not_evidence: bool


@dataclass(frozen=True)
class VectorBackendBenchmarkThresholds:
    max_build_seconds: float = 5.0
    max_avg_search_seconds: float = 0.5
    max_cold_start_seconds: float = 1.0
    min_recall_at_limit: float = 1.0
    max_disk_bytes_per_vector: int = 16_384
    max_memory_bytes_per_vector: int | None = None
    require_update_delete: bool = False
    require_source_restoration: bool = True

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class VectorBackendBenchmarkResult:
    backend: str
    status: str
    documents: int
    query_count: int
    build_seconds: float | None
    avg_search_seconds: float | None
    cold_start_seconds: float | None
    recall_at_limit: float | None
    disk_bytes: int | None
    disk_bytes_per_vector: float | None
    memory_bytes: int | None
    memory_bytes_per_vector: float | None
    update_delete_supported: bool
    source_restoration_ok: bool
    index_path: str | None
    mapping_path: str | None
    thresholds: dict[str, Any]
    notes: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class VectorBackendBenchmarkReport:
    db_path: str
    status: str
    provider: str | None
    model: str | None
    dimensions: int | None
    embedding_profile: str | None
    text_template_version: str | None
    limit: int
    queries: tuple[str, ...]
    results: tuple[VectorBackendBenchmarkResult, ...]
    metadata: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["results"] = [result.as_dict() for result in self.results]
        return data


def build_vector_projection(
    db_path: str | Path,
    *,
    space_id: str | None = None,
    provider: str | None = None,
    model: str | None = None,
    dimensions: int | None = None,
    embedding_profile: str | None = None,
    text_template_version: str | None = None,
    backend: str = "numpy",
    bit_width: int = 4,
    out_dir: str | Path | None = None,
    doc_type: str | None = None,
    account: str | None = None,
    allow_partial: bool = False,
) -> VectorProjectionBuildSummary:
    resolved_backend = _resolve_backend(backend)
    resolved_bit_width = _resolve_bit_width(bit_width, backend=resolved_backend)
    path = Path(db_path)
    if not path.exists():
        raise FileNotFoundError(f"database not found: {path}")
    with sqlite3.connect(path, timeout=60) as conn:
        conn.row_factory = sqlite3.Row
        ensure_memory_schema(conn)
        spec = (
            _resolve_spec_for_space_id(
                conn,
                space_id=space_id,
                provider=provider,
                model=model,
                dimensions=dimensions,
                embedding_profile=embedding_profile,
                text_template_version=text_template_version,
            )
            if space_id
            else _resolve_available_spec(
                conn,
                provider=provider,
                model=model,
                dimensions=dimensions,
                embedding_profile=embedding_profile,
                text_template_version=text_template_version,
                api_key_env=None,
                base_url=None,
            )
        )
        rows = _embedding_rows(conn, spec=spec, doc_type=doc_type, account=account)
        if space_id:
            rows = [row for row in rows if row["space_id"] == space_id]
        expected_rows = _embedding_document_count(conn, doc_type=doc_type, account=account)
        partial = bool(expected_rows and len(rows) < expected_rows)
        missing_rows = max(0, expected_rows - len(rows))
        if partial and not allow_partial:
            raise RuntimeError(
                "cannot build local vector projection from incomplete or stale embeddings: "
                f"{len(rows)}/{expected_rows} current rows for "
                f"{spec.provider}/{spec.model} dims={spec.dimensions}"
            )
        if not rows:
            raise RuntimeError("no current embeddings found for vector projection")
        space_id = _space_id_from_rows(rows)
        doc_ids = tuple(str(row["doc_id"]) for row in rows)
        if len(doc_ids) != len(set(doc_ids)):
            raise RuntimeError("duplicate doc_id rows would make vector projection unsafe")
        matrix = _semantic_matrix_from_rows(rows, dimensions=spec.dimensions)
        generation_id = f"vecproj-{uuid.uuid4().hex}"
        source_scope = _source_scope(doc_type=doc_type, account=account)
        artifact_dir = Path(out_dir) if out_dir else DEFAULT_VECTOR_INDEX_DIR
        artifact_dir.mkdir(parents=True, exist_ok=True)
        mapping = _build_mapping(rows)
        index_path, mapping_path = _write_projection_files(
            artifact_dir,
            generation_id=generation_id,
            backend=resolved_backend,
            matrix=matrix,
            mapping=mapping,
            dimensions=spec.dimensions,
            bit_width=resolved_bit_width,
        )
        _store_projection_generation(
            conn,
            generation_id=generation_id,
            space_id=space_id,
            spec=spec,
            backend=resolved_backend,
            bit_width=resolved_bit_width,
            source_scope=source_scope,
            index_path=index_path,
            mapping_path=mapping_path,
            rows=rows,
            expected_documents=expected_rows or len(rows),
            allow_partial=allow_partial,
            doc_type=doc_type,
            account=account,
        )
    from research_x.memory.projection_lifecycle import register_projection_lifecycle

    lifecycle_summary = register_projection_lifecycle(path)
    summary = VectorProjectionBuildSummary(
        db_path=str(path),
        generation_id=generation_id,
        space_id=space_id,
        backend=resolved_backend,
        provider=spec.provider,
        model=spec.model,
        dimensions=spec.dimensions,
        embedding_profile=spec.embedding_profile,
        text_template_version=spec.text_template_version,
        bit_width=resolved_bit_width,
        documents=len(rows),
        expected_documents=expected_rows or len(rows),
        missing_documents=missing_rows,
        index_path=str(index_path),
        mapping_path=str(mapping_path),
        source_scope=source_scope,
        status="partial" if partial else "current",
        production_eligible=not partial,
        not_evidence=True,
    )
    record_audit_event(
        path,
        event_type="projection_built",
        subject_kind="projection_generation",
        subject_id=generation_id,
        severity="info",
        message=(
            "Vector projection build wrote generation, index membership, "
            "files, and lifecycle rows."
        ),
        created_at=_now(),
        metadata={
            "builder_call_path": "research_x.memory.vector_projection.build_vector_projection",
            "build_summary": summary.as_dict() if hasattr(summary, "as_dict") else asdict(summary),
            "lifecycle_audit_event_id": lifecycle_summary.audit_event_id,
            "lifecycle_status": lifecycle_summary.status,
        },
    )
    return summary


def vector_projection_coverage(
    db_path: str | Path,
    *,
    generation_id: str | None = None,
    space_id: str | None = None,
    provider: str | None = None,
    model: str | None = None,
    dimensions: int | None = None,
    embedding_profile: str | None = None,
    text_template_version: str | None = None,
    backend: str | None = None,
) -> VectorProjectionCoverage:
    path = Path(db_path)
    if not path.exists():
        raise FileNotFoundError(f"database not found: {path}")
    with sqlite3.connect(path, timeout=60) as conn:
        conn.row_factory = sqlite3.Row
        ensure_memory_schema(conn)
        row = _projection_generation_row(
            conn,
            generation_id=generation_id,
            space_id=space_id,
            provider=provider,
            model=model,
            dimensions=dimensions,
            embedding_profile=embedding_profile,
            text_template_version=text_template_version,
            backend=backend,
        )
        if row is None:
            return VectorProjectionCoverage(
                db_path=str(path),
                generation_id=None,
                space_id=space_id,
                backend=backend,
                provider=provider,
                model=model,
                dimensions=dimensions,
                embedding_profile=embedding_profile,
                text_template_version=text_template_version,
                projection_documents=0,
                expected_documents=0,
                current_memberships=0,
                stale_memberships=0,
                missing_memberships=0,
                index_path=None,
                index_exists=False,
                status="missing",
                partial=False,
                production_eligible=False,
                not_evidence=True,
            )
        metadata = json.loads(row["metadata_json"] or "{}")
        spec_payload = metadata.get("embedding_spec") or {}
        expected_documents = _embedding_document_count(
            conn,
            doc_type=metadata.get("doc_type"),
            account=metadata.get("account"),
        )
        membership_rows = conn.execute(
            """
            SELECT m.artifact_id, m.source_hash, d.source_doc_hash
            FROM memory_index_membership m
            LEFT JOIN memory_documents d ON d.doc_id = m.source_id
            WHERE m.generation_id = ?
              AND m.artifact_kind = 'memory_document_embedding'
            """,
            (row["generation_id"],),
        ).fetchall()
    stale = sum(
        1
        for membership in membership_rows
        if membership["source_doc_hash"] is None
        or membership["source_hash"] != membership["source_doc_hash"]
    )
    current = len(membership_rows) - stale
    projection_documents = int(metadata.get("documents") or len(membership_rows))
    missing = max(0, expected_documents - current)
    index_path = metadata.get("index_path")
    index_exists = bool(index_path and Path(index_path).exists())
    partial = bool(metadata.get("partial") or missing > 0)
    if not index_exists or stale:
        status = "stale"
    elif partial:
        status = "partial"
    else:
        status = "ok"
    production_eligible_payload = metadata.get("production_eligible")
    production_eligible = (
        not partial
        if production_eligible_payload is None
        else bool(production_eligible_payload and not partial)
    )
    return VectorProjectionCoverage(
        db_path=str(path),
        generation_id=row["generation_id"],
        space_id=row["space_id"] or metadata.get("space_id"),
        backend=metadata.get("backend"),
        provider=spec_payload.get("provider"),
        model=spec_payload.get("model"),
        dimensions=int(spec_payload["dimensions"]) if spec_payload.get("dimensions") else None,
        embedding_profile=spec_payload.get("embedding_profile"),
        text_template_version=spec_payload.get("text_template_version"),
        projection_documents=projection_documents,
        expected_documents=expected_documents,
        current_memberships=current,
        stale_memberships=stale,
        missing_memberships=missing,
        index_path=index_path,
        index_exists=index_exists,
        status=status,
        partial=partial,
        production_eligible=production_eligible,
        not_evidence=bool(metadata.get("not_evidence", True)),
    )


def search_vector_projection(
    db_path: str | Path,
    query: str,
    *,
    generation_id: str | None = None,
    space_id: str | None = None,
    provider: str | None = None,
    model: str | None = None,
    dimensions: int | None = None,
    embedding_profile: str | None = None,
    text_template_version: str | None = None,
    backend: str | None = None,
    limit: int = 50,
    doc_type: str | None = None,
    account: str | None = None,
    doc_ids: tuple[str, ...] = (),
    allow_provider_quota: bool = False,
) -> tuple[SemanticHit, ...]:
    path = Path(db_path)
    with sqlite3.connect(path, timeout=60) as conn:
        conn.row_factory = sqlite3.Row
        ensure_memory_schema(conn)
        row = _projection_generation_row(
            conn,
            generation_id=generation_id,
            space_id=space_id,
            provider=provider,
            model=model,
            dimensions=dimensions,
            embedding_profile=embedding_profile,
            text_template_version=text_template_version,
            backend=backend,
        )
        if row is None:
            raise RuntimeError("local vector projection not found for the requested spec")
        metadata = json.loads(row["metadata_json"] or "{}")
        spec = _spec_from_metadata(metadata)
        mapping = _load_mapping(Path(metadata["mapping_path"]))
        memberships = _projection_memberships_by_doc_id(conn, row["generation_id"])
        allowed_ids = _allowed_vector_ids(
            conn,
            row["generation_id"],
            mapping=mapping,
            doc_type=doc_type,
            account=account,
            doc_ids=doc_ids,
        )
    require_embedding_provider_quota_allowed(
        spec.provider,
        allow_provider_quota=allow_provider_quota,
        model=spec.model,
    )
    query_vector = _embedder(spec).embed_texts([query], task_type="RETRIEVAL_QUERY")[0]
    hits = _search_projection_files(
        query_vector=query_vector,
        metadata=metadata,
        mapping=mapping,
        allowed_ids=allowed_ids,
        limit=max(1, limit),
    )
    return tuple(
        SemanticHit(
            doc_id=hit["doc_id"],
            similarity=float(hit["score"]),
            space_id=row["space_id"] or metadata.get("space_id"),
            provider=spec.provider,
            model=spec.model,
            dimensions=spec.dimensions,
            embedding_profile=spec.embedding_profile,
            text_template_version=spec.text_template_version,
            source_doc_hash=(memberships.get(hit["doc_id"]) or {}).get("source_doc_hash"),
            embedded_text_hash=(memberships.get(hit["doc_id"]) or {}).get("embedded_text_hash"),
            generated_at=row["created_at"],
            stale_status="current" if row["status"] == "current" else "stale",
            projection_generation_id=row["generation_id"],
            projection_hash=metadata.get("projection_hash"),
            projection_status=row["status"],
        )
        for hit in hits
    )


def benchmark_vector_backends(
    db_path: str | Path,
    *,
    backends: tuple[str, ...] = ("numpy",),
    queries: tuple[str, ...] = ("robot paper",),
    provider: str | None = "local_hash",
    model: str | None = None,
    dimensions: int | None = None,
    embedding_profile: str | None = None,
    text_template_version: str | None = None,
    limit: int = 5,
    out_dir: str | Path | None = None,
    doc_type: str | None = None,
    account: str | None = None,
    thresholds: VectorBackendBenchmarkThresholds | None = None,
) -> VectorBackendBenchmarkReport:
    path = Path(db_path)
    resolved_thresholds = thresholds or VectorBackendBenchmarkThresholds()
    resolved_backends = tuple(backends) or ("numpy",)
    resolved_queries = tuple(query for query in queries if query.strip()) or ("robot paper",)
    if provider != "local_hash":
        threshold_payload = resolved_thresholds.as_dict()
        results = tuple(
            _benchmark_provider_gated_result(
                backend=backend,
                query_count=len(resolved_queries),
                thresholds=threshold_payload,
            )
            for backend in resolved_backends
        )
    else:
        results = tuple(
            _benchmark_backend(
                path,
                backend=backend,
                queries=resolved_queries,
                provider=provider,
                model=model,
                dimensions=dimensions,
                embedding_profile=embedding_profile,
                text_template_version=text_template_version,
                limit=max(1, limit),
                out_dir=out_dir,
                doc_type=doc_type,
                account=account,
                thresholds=resolved_thresholds,
            )
            for backend in resolved_backends
        )
    semantic_policy = embedding_provider_signal_policy(provider)
    status = "ok" if all(result.status == "ok" for result in results) else "needs_review"
    return VectorBackendBenchmarkReport(
        db_path=str(path),
        status=status,
        provider=provider,
        model=model,
        dimensions=dimensions,
        embedding_profile=embedding_profile,
        text_template_version=text_template_version,
        limit=max(1, limit),
        queries=resolved_queries,
        results=results,
        metadata={
            "benchmark_version": "vector-backend-benchmark-v1",
            "candidate_backends": list(BENCHMARK_VECTOR_BACKENDS),
            "dependency_gate": "zvec and other new backends require source/dependency review",
            "query_embedding_policy": (
                "local_hash query embeddings are the default until "
                "ProviderExecutionPolicy selects a provider"
            ),
            **semantic_policy,
        },
    )


def summary_as_dict(summary: VectorProjectionBuildSummary) -> dict[str, Any]:
    return asdict(summary)


def coverage_json(report: VectorProjectionCoverage) -> str:
    return json.dumps(asdict(report), ensure_ascii=False, indent=2, sort_keys=True)


def summary_json(summary: VectorProjectionBuildSummary) -> str:
    return json.dumps(asdict(summary), ensure_ascii=False, indent=2, sort_keys=True)


def benchmark_json(report: VectorBackendBenchmarkReport) -> str:
    return json.dumps(report.as_dict(), ensure_ascii=False, indent=2, sort_keys=True)


def format_vector_projection_summary(summary: VectorProjectionBuildSummary) -> str:
    return "\n".join(
        [
            f"generation_id: {summary.generation_id}",
            f"space_id: {summary.space_id}",
            f"backend: {summary.backend}",
            (
                "spec: "
                f"{summary.provider}/{summary.model} dims={summary.dimensions} "
                f"profile={summary.embedding_profile} "
                f"template={summary.text_template_version}"
            ),
            (
                "documents: "
                f"{summary.documents}/{summary.expected_documents} "
                f"missing={summary.missing_documents}"
            ),
            f"status: {summary.status}",
            f"production_eligible: {summary.production_eligible}",
            f"not_evidence: {summary.not_evidence}",
            f"index: {summary.index_path}",
            f"mapping: {summary.mapping_path}",
        ]
    )


def format_vector_projection_coverage(report: VectorProjectionCoverage) -> str:
    if report.status == "missing":
        return "local vector projection: missing"
    return "\n".join(
        [
            f"generation_id: {report.generation_id}",
            f"space_id: {report.space_id}",
            f"backend: {report.backend}",
            (
                "spec: "
                f"{report.provider}/{report.model} dims={report.dimensions} "
                f"profile={report.embedding_profile} "
                f"template={report.text_template_version}"
            ),
            (
                "memberships: "
                f"projection={report.projection_documents} current={report.current_memberships} "
                f"stale={report.stale_memberships} missing={report.missing_memberships}"
            ),
            f"index_exists: {report.index_exists}",
            f"status: {report.status}",
            f"partial: {report.partial}",
            f"production_eligible: {report.production_eligible}",
            f"not_evidence: {report.not_evidence}",
        ]
    )


def format_vector_backend_benchmark(report: VectorBackendBenchmarkReport) -> str:
    lines = [
        (
            "vector-backend-benchmark: "
            f"status={report.status} backends={len(report.results)} "
            f"queries={len(report.queries)} limit={report.limit}"
        )
    ]
    for result in report.results:
        lines.append(
            "  "
            f"{result.backend}: status={result.status} docs={result.documents} "
            f"build={_duration(result.build_seconds)} "
            f"avg_search={_duration(result.avg_search_seconds)} "
            f"cold_start={_duration(result.cold_start_seconds)} "
            f"recall={_metric(result.recall_at_limit)} "
            f"disk_per_vector={_metric(result.disk_bytes_per_vector)} "
            f"memory_per_vector={_metric(result.memory_bytes_per_vector)}"
        )
        for note in result.notes:
            lines.append(f"    note: {note}")
    return "\n".join(lines)


def _resolve_backend(backend: str) -> str:
    resolved = backend.strip().lower()
    if resolved not in SUPPORTED_VECTOR_BACKENDS:
        raise ValueError(f"unsupported local vector backend: {backend}")
    return resolved


def _resolve_benchmark_backend(backend: str) -> str:
    resolved = backend.strip().lower()
    if resolved not in BENCHMARK_VECTOR_BACKENDS:
        raise ValueError(f"unsupported vector benchmark backend: {backend}")
    return resolved


def _benchmark_backend(
    db_path: Path,
    *,
    backend: str,
    queries: tuple[str, ...],
    provider: str | None,
    model: str | None,
    dimensions: int | None,
    embedding_profile: str | None,
    text_template_version: str | None,
    limit: int,
    out_dir: str | Path | None,
    doc_type: str | None,
    account: str | None,
    thresholds: VectorBackendBenchmarkThresholds,
) -> VectorBackendBenchmarkResult:
    resolved_backend = _resolve_benchmark_backend(backend)
    threshold_payload = thresholds.as_dict()
    if resolved_backend not in SUPPORTED_VECTOR_BACKENDS:
        return VectorBackendBenchmarkResult(
            backend=resolved_backend,
            status="dependency_review_required",
            documents=0,
            query_count=len(queries),
            build_seconds=None,
            avg_search_seconds=None,
            cold_start_seconds=None,
            recall_at_limit=None,
            disk_bytes=None,
            disk_bytes_per_vector=None,
            memory_bytes=None,
            memory_bytes_per_vector=None,
            update_delete_supported=False,
            source_restoration_ok=False,
            index_path=None,
            mapping_path=None,
            thresholds=threshold_payload,
            notes=("backend is candidate-only; no import/install attempted",),
        )
    try:
        build_started = time.perf_counter()
        summary = build_vector_projection(
            db_path,
            provider=provider,
            model=model,
            dimensions=dimensions,
            embedding_profile=embedding_profile,
            text_template_version=text_template_version,
            backend=resolved_backend,
            out_dir=out_dir,
            doc_type=doc_type,
            account=account,
        )
        build_seconds = time.perf_counter() - build_started
        search_durations: list[float] = []
        recall_scores: list[float] = []
        for query in queries:
            baseline = semantic_search_memory(
                db_path,
                query,
                provider=provider,
                model=model,
                dimensions=dimensions,
                embedding_profile=embedding_profile,
                text_template_version=text_template_version,
                limit=limit,
                doc_type=doc_type,
                account=account,
            )
            search_started = time.perf_counter()
            projected = search_vector_projection(
                db_path,
                query,
                generation_id=summary.generation_id,
                limit=limit,
                doc_type=doc_type,
                account=account,
            )
            search_durations.append(time.perf_counter() - search_started)
            recall_scores.append(_recall_at_limit(baseline, projected))
        avg_search_seconds = sum(search_durations) / len(search_durations)
        recall_at_limit = sum(recall_scores) / len(recall_scores)
        disk_bytes = _projection_disk_bytes(summary)
        disk_bytes_per_vector = disk_bytes / max(1, summary.documents)
        memory_bytes = _projection_memory_bytes(summary)
        memory_bytes_per_vector = memory_bytes / max(1, summary.documents)
        coverage = vector_projection_coverage(
            db_path,
            generation_id=summary.generation_id,
        )
        source_restoration_ok = coverage.status == "ok"
        notes = _benchmark_notes(
            build_seconds=build_seconds,
            avg_search_seconds=avg_search_seconds,
            cold_start_seconds=search_durations[0],
            recall_at_limit=recall_at_limit,
            disk_bytes_per_vector=disk_bytes_per_vector,
            memory_bytes_per_vector=memory_bytes_per_vector,
            update_delete_supported=False,
            source_restoration_ok=source_restoration_ok,
            thresholds=thresholds,
        )
        return VectorBackendBenchmarkResult(
            backend=resolved_backend,
            status="ok" if not notes else "needs_review",
            documents=summary.documents,
            query_count=len(queries),
            build_seconds=round(build_seconds, 6),
            avg_search_seconds=round(avg_search_seconds, 6),
            cold_start_seconds=round(search_durations[0], 6),
            recall_at_limit=round(recall_at_limit, 4),
            disk_bytes=disk_bytes,
            disk_bytes_per_vector=round(disk_bytes_per_vector, 2),
            memory_bytes=memory_bytes,
            memory_bytes_per_vector=round(memory_bytes_per_vector, 2),
            update_delete_supported=False,
            source_restoration_ok=source_restoration_ok,
            index_path=summary.index_path,
            mapping_path=summary.mapping_path,
            thresholds=threshold_payload,
            notes=tuple(notes),
        )
    except (FileNotFoundError, RuntimeError, ValueError) as exc:
        return VectorBackendBenchmarkResult(
            backend=resolved_backend,
            status="error",
            documents=0,
            query_count=len(queries),
            build_seconds=None,
            avg_search_seconds=None,
            cold_start_seconds=None,
            recall_at_limit=None,
            disk_bytes=None,
            disk_bytes_per_vector=None,
            memory_bytes=None,
            memory_bytes_per_vector=None,
            update_delete_supported=False,
            source_restoration_ok=False,
            index_path=None,
            mapping_path=None,
            thresholds=threshold_payload,
            notes=(str(exc),),
        )


def _benchmark_provider_gated_result(
    *,
    backend: str,
    query_count: int,
    thresholds: dict[str, Any],
) -> VectorBackendBenchmarkResult:
    resolved_backend = _resolve_benchmark_backend(backend)
    return VectorBackendBenchmarkResult(
        backend=resolved_backend,
        status="provider_gated",
        documents=0,
        query_count=query_count,
        build_seconds=None,
        avg_search_seconds=None,
        cold_start_seconds=None,
        recall_at_limit=None,
        disk_bytes=None,
        disk_bytes_per_vector=None,
        memory_bytes=None,
        memory_bytes_per_vector=None,
        update_delete_supported=False,
        source_restoration_ok=False,
        index_path=None,
        mapping_path=None,
        thresholds=thresholds,
        notes=("non-local query embeddings require scoped ProviderExecutionPolicy",),
    )


def _benchmark_notes(
    *,
    build_seconds: float,
    avg_search_seconds: float,
    cold_start_seconds: float,
    recall_at_limit: float,
    disk_bytes_per_vector: float,
    memory_bytes_per_vector: float,
    update_delete_supported: bool,
    source_restoration_ok: bool,
    thresholds: VectorBackendBenchmarkThresholds,
) -> list[str]:
    notes = []
    if build_seconds > thresholds.max_build_seconds:
        notes.append("build_seconds_exceeds_threshold")
    if avg_search_seconds > thresholds.max_avg_search_seconds:
        notes.append("avg_search_seconds_exceeds_threshold")
    if cold_start_seconds > thresholds.max_cold_start_seconds:
        notes.append("cold_start_seconds_exceeds_threshold")
    if recall_at_limit < thresholds.min_recall_at_limit:
        notes.append("recall_below_threshold")
    if disk_bytes_per_vector > thresholds.max_disk_bytes_per_vector:
        notes.append("disk_bytes_per_vector_exceeds_threshold")
    if (
        thresholds.max_memory_bytes_per_vector is not None
        and memory_bytes_per_vector > thresholds.max_memory_bytes_per_vector
    ):
        notes.append("memory_bytes_per_vector_exceeds_threshold")
    if thresholds.require_update_delete and not update_delete_supported:
        notes.append("update_delete_not_supported")
    if thresholds.require_source_restoration and not source_restoration_ok:
        notes.append("source_restoration_not_ok")
    return notes


def _recall_at_limit(
    baseline: tuple[SemanticHit, ...],
    projected: tuple[SemanticHit, ...],
) -> float:
    baseline_ids = {hit.doc_id for hit in baseline}
    if not baseline_ids:
        return 1.0
    projected_ids = {hit.doc_id for hit in projected}
    return len(baseline_ids & projected_ids) / len(baseline_ids)


def _projection_disk_bytes(summary: VectorProjectionBuildSummary) -> int:
    paths = [Path(summary.index_path), Path(summary.mapping_path)]
    return sum(path.stat().st_size for path in paths if path.exists())


def _projection_memory_bytes(summary: VectorProjectionBuildSummary) -> int:
    # Lower-bound resident vector footprint; backend runtime overhead is dependency-specific.
    return summary.documents * summary.dimensions * np.dtype(np.float32).itemsize


def _duration(value: float | None) -> str:
    return "-" if value is None else f"{value:.4f}s"


def _metric(value: float | None) -> str:
    return "-" if value is None else f"{value:.4f}"


def _resolve_bit_width(bit_width: int, *, backend: str) -> int | None:
    if backend == "numpy":
        return None
    if bit_width not in {2, 4}:
        raise ValueError("turbovec bit_width must be 2 or 4")
    return bit_width


def _source_scope(*, doc_type: str | None, account: str | None) -> str:
    parts = ["memory_documents"]
    if doc_type:
        parts.append(f"doc_type={doc_type}")
    if account:
        parts.append(f"account={account}")
    return "|".join(parts)


def _space_id_from_rows(rows: list[sqlite3.Row]) -> str:
    space_ids = {str(row["space_id"] or "").strip() for row in rows}
    space_ids.discard("")
    if not space_ids:
        raise RuntimeError("cannot build vector projection from embedding rows without space_id")
    if len(space_ids) != 1:
        raise RuntimeError("cannot mix multiple embedding spaces in one vector projection")
    return next(iter(space_ids))


def _build_mapping(rows: list[sqlite3.Row]) -> list[dict[str, Any]]:
    mapping = []
    for index, row in enumerate(rows, start=1):
        mapping.append(
            {
                "vector_id": index,
                "doc_id": str(row["doc_id"]),
                "space_id": row["space_id"],
                "source_doc_hash": row["source_doc_hash"],
                "embedded_text_hash": row["embedded_text_hash"],
            }
        )
    return mapping


def _write_projection_files(
    artifact_dir: Path,
    *,
    generation_id: str,
    backend: str,
    matrix: np.ndarray,
    mapping: list[dict[str, Any]],
    dimensions: int,
    bit_width: int | None,
) -> tuple[Path, Path]:
    mapping_path = artifact_dir / f"{generation_id}.mapping.json"
    mapping_path.write_text(json.dumps(mapping, ensure_ascii=False, indent=2), encoding="utf-8")
    if backend == "numpy":
        index_path = artifact_dir / f"{generation_id}.npz"
        np.savez_compressed(
            index_path,
            matrix=np.ascontiguousarray(matrix, dtype=np.float32),
            vector_ids=np.asarray([row["vector_id"] for row in mapping], dtype=np.uint64),
        )
        return index_path, mapping_path
    index_path = artifact_dir / f"{generation_id}.turbovec.tvim"
    _write_turbovec_index(
        index_path,
        matrix=np.ascontiguousarray(matrix, dtype=np.float32),
        vector_ids=np.asarray([row["vector_id"] for row in mapping], dtype=np.uint64),
        dimensions=dimensions,
        bit_width=bit_width or 4,
    )
    return index_path, mapping_path


def _write_turbovec_index(
    index_path: Path,
    *,
    matrix: np.ndarray,
    vector_ids: np.ndarray,
    dimensions: int,
    bit_width: int,
) -> None:
    try:
        from turbovec import IdMapIndex  # type: ignore[import-not-found]
    except ImportError as exc:
        raise RuntimeError(
            "turbovec backend requires the optional turbovec package; "
            "install the local-vector extra or choose --backend numpy"
        ) from exc
    index = IdMapIndex(dim=dimensions, bit_width=bit_width)
    index.add_with_ids(matrix, vector_ids)
    index.write(str(index_path))


def _store_projection_generation(
    conn: sqlite3.Connection,
    *,
    generation_id: str,
    space_id: str,
    spec: EmbeddingSpec,
    backend: str,
    bit_width: int | None,
    source_scope: str,
    index_path: Path,
    mapping_path: Path,
    rows: list[sqlite3.Row],
    expected_documents: int,
    allow_partial: bool,
    doc_type: str | None,
    account: str | None,
) -> None:
    now = _now()
    missing_documents = max(0, expected_documents - len(rows))
    partial = missing_documents > 0
    status = "partial" if partial else "current"
    selection_policy = (
        VECTOR_PROJECTION_PARTIAL_SELECTION_POLICY
        if partial
        else VECTOR_PROJECTION_FULL_SELECTION_POLICY
    )
    production_eligible = not partial
    production_eligible_reason = "partial_projection" if partial else "complete_current_projection"
    manifest = {
        "space_id": space_id,
        "embedding_spec": asdict(spec),
        "source_scope": source_scope,
        "doc_type": doc_type,
        "account": account,
        "rows": len(rows),
        "expected_documents": expected_documents,
        "missing_documents": missing_documents,
        "partial": partial,
        "allow_partial": allow_partial,
        "production_eligible": production_eligible,
        "not_evidence": True,
    }
    coverage = {
        "documents": len(rows),
        "expected_documents": expected_documents,
        "current": len(rows),
        "stale": 0,
        "missing": missing_documents,
        "partial": partial,
        "production_eligible": production_eligible,
        "not_evidence": True,
    }
    projection_hash = _projection_hash(index_path=index_path, mapping_path=mapping_path)
    metadata = {
        "backend": backend,
        "space_id": space_id,
        "bit_width": bit_width,
        "index_path": str(index_path),
        "mapping_path": str(mapping_path),
        "projection_hash": projection_hash,
        "documents": len(rows),
        "expected_documents": expected_documents,
        "missing_documents": missing_documents,
        "partial": partial,
        "production_eligible": production_eligible,
        "production_eligible_reason": production_eligible_reason,
        "not_evidence": True,
        "evidence_role": "candidate_signal_not_evidence",
        "allow_partial": allow_partial,
        "doc_type": doc_type,
        "account": account,
        "embedding_spec": asdict(spec),
        "embedding_provider_policy": embedding_provider_signal_policy(spec.provider),
    }
    conn.execute(
        """
        INSERT INTO memory_projection_generations (
            generation_id, projection_kind, space_id, projection_name,
            projection_version, selection_policy, source_query, source_scope,
            builder_version, input_manifest_json, status, coverage_json,
            source_count, projected_count, skipped_count, stale_policy,
            code_commit, run_id, created_at, metadata_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            generation_id,
            VECTOR_PROJECTION_KIND,
            space_id,
            spec.embedding_profile,
            VECTOR_PROJECTION_BUILDER_VERSION,
            selection_policy,
            None,
            source_scope,
            VECTOR_PROJECTION_BUILDER_VERSION,
            json.dumps(manifest, ensure_ascii=False, sort_keys=True),
            status,
            json.dumps(coverage, ensure_ascii=False, sort_keys=True),
            expected_documents,
            len(rows),
            missing_documents,
            "source_or_embedding_hash_change_marks_stale",
            None,
            None,
            now,
            json.dumps(metadata, ensure_ascii=False, sort_keys=True),
        ),
    )
    conn.execute(
        """
        INSERT OR REPLACE INTO memory_vector_indexes (
            index_id, space_id, backend, index_path, mapping_path,
            build_generation_id, vector_count, coverage_json, created_at,
            status, metadata_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            generation_id,
            space_id,
            backend,
            str(index_path),
            str(mapping_path),
            generation_id,
            len(rows),
            json.dumps(coverage, ensure_ascii=False, sort_keys=True),
            now,
            status,
            json.dumps(metadata, ensure_ascii=False, sort_keys=True),
        ),
    )
    conn.executemany(
        """
        INSERT INTO memory_index_membership (
            membership_id, generation_id, artifact_kind, artifact_id, source_id,
            source_hash, membership_status, created_at, metadata_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            (
                f"membership-{uuid.uuid4().hex}",
                generation_id,
                "memory_document_embedding",
                f"vector:{index}",
                row["doc_id"],
                row["source_doc_hash"],
                "current",
                now,
                json.dumps(
                    {
                        "vector_id": index,
                        "space_id": space_id,
                        "embedded_text_hash": row["embedded_text_hash"],
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                ),
            )
            for index, row in enumerate(rows, start=1)
        ),
    )
    conn.commit()


def _projection_generation_row(
    conn: sqlite3.Connection,
    *,
    generation_id: str | None,
    space_id: str | None,
    provider: str | None,
    model: str | None,
    dimensions: int | None,
    embedding_profile: str | None,
    text_template_version: str | None,
    backend: str | None,
) -> sqlite3.Row | None:
    if generation_id:
        row = conn.execute(
            """
            SELECT *
            FROM memory_projection_generations
            WHERE generation_id = ?
              AND projection_kind = ?
            """,
            (generation_id, VECTOR_PROJECTION_KIND),
        ).fetchone()
        if row is None:
            return None
        return row if _projection_row_matches(
            row,
            space_id=space_id,
            provider=provider,
            model=model,
            dimensions=dimensions,
            embedding_profile=embedding_profile,
            text_template_version=text_template_version,
            backend=backend,
            skip_implicit_local_hash=False,
        ) else None
    rows = conn.execute(
        """
        SELECT *
        FROM memory_projection_generations
        WHERE projection_kind = ?
          AND status = 'current'
        ORDER BY created_at DESC
        """,
        (VECTOR_PROJECTION_KIND,),
    ).fetchall()
    matches = [
        row
        for row in rows
        if _projection_row_matches(
            row,
            space_id=space_id,
            provider=provider,
            model=model,
            dimensions=dimensions,
            embedding_profile=embedding_profile,
            text_template_version=text_template_version,
            backend=backend,
            skip_implicit_local_hash=True,
        )
    ]
    if not matches:
        return None
    space_ids = {
        _row_space_id(row)
        for row in matches
        if _row_space_id(row) is not None
    }
    if space_id is None and len(space_ids) > 1:
        raise RuntimeError(
            "local vector projection matched multiple embedding spaces for one spec; "
            "pass --semantic-space-id or --space-id to avoid raw score mixing"
        )
    return matches[0]


def _projection_row_matches(
    row: sqlite3.Row,
    *,
    space_id: str | None,
    provider: str | None,
    model: str | None,
    dimensions: int | None,
    embedding_profile: str | None,
    text_template_version: str | None,
    backend: str | None,
    skip_implicit_local_hash: bool,
) -> bool:
    metadata = json.loads(row["metadata_json"] or "{}")
    spec = metadata.get("embedding_spec") or {}
    if (
        skip_implicit_local_hash
        and provider is None
        and space_id is None
        and spec.get("provider") == "local_hash"
    ):
        return False
    if backend and metadata.get("backend") != backend:
        return False
    if space_id and _row_space_id(row) != space_id:
        return False
    if provider and spec.get("provider") != provider:
        return False
    if model and spec.get("model") != model:
        return False
    if dimensions and int(spec.get("dimensions") or 0) != dimensions:
        return False
    if embedding_profile and spec.get("embedding_profile") != embedding_profile:
        return False
    return not (
        text_template_version
        and spec.get("text_template_version") != text_template_version
    )


def _row_space_id(row: sqlite3.Row) -> str | None:
    metadata = json.loads(row["metadata_json"] or "{}")
    value = row["space_id"] or metadata.get("space_id")
    return str(value) if value else None


def _spec_from_metadata(metadata: dict[str, Any]) -> EmbeddingSpec:
    payload = metadata.get("embedding_spec") or {}
    return EmbeddingSpec(
        provider=payload["provider"],
        model=payload["model"],
        dimensions=int(payload["dimensions"]),
        embedding_profile=payload["embedding_profile"],
        text_template_version=payload["text_template_version"],
        api_key_env=payload.get("api_key_env"),
        base_url=payload.get("base_url"),
        timeout_seconds=float(payload.get("timeout_seconds") or 60.0),
    )


def _load_mapping(mapping_path: Path) -> dict[int, str]:
    payload = json.loads(mapping_path.read_text(encoding="utf-8"))
    return {int(row["vector_id"]): str(row["doc_id"]) for row in payload}


def _projection_memberships_by_doc_id(
    conn: sqlite3.Connection,
    generation_id: str,
) -> dict[str, dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT source_id, source_hash, metadata_json
        FROM memory_index_membership
        WHERE generation_id = ?
          AND artifact_kind = 'memory_document_embedding'
        """,
        (generation_id,),
    ).fetchall()
    memberships: dict[str, dict[str, Any]] = {}
    for row in rows:
        metadata = json.loads(row["metadata_json"] or "{}")
        memberships[str(row["source_id"])] = {
            "source_doc_hash": row["source_hash"],
            "embedded_text_hash": metadata.get("embedded_text_hash"),
        }
    return memberships


def _allowed_vector_ids(
    conn: sqlite3.Connection,
    generation_id: str,
    *,
    mapping: dict[int, str],
    doc_type: str | None,
    account: str | None,
    doc_ids: tuple[str, ...],
) -> set[int] | None:
    if not doc_type and not account and not doc_ids:
        return None
    filters = []
    params: list[Any] = [generation_id]
    if doc_type:
        filters.append("d.doc_type = ?")
        params.append(doc_type)
    if account:
        filters.append("d.account_id = ?")
        params.append(account)
    if doc_ids:
        placeholders = ",".join("?" for _ in doc_ids)
        filters.append(f"d.doc_id IN ({placeholders})")
        params.extend(doc_ids)
    rows = conn.execute(
        f"""
        SELECT m.metadata_json
        FROM memory_index_membership m
        JOIN memory_documents d ON d.doc_id = m.source_id
        WHERE m.generation_id = ?
          AND {' AND '.join(filters)}
        """,
        params,
    ).fetchall()
    allowed = set()
    known_ids = set(mapping)
    for row in rows:
        metadata = json.loads(row["metadata_json"] or "{}")
        vector_id = int(metadata.get("vector_id") or 0)
        if vector_id in known_ids:
            allowed.add(vector_id)
    return allowed


def _search_projection_files(
    *,
    query_vector: list[float],
    metadata: dict[str, Any],
    mapping: dict[int, str],
    allowed_ids: set[int] | None,
    limit: int,
) -> list[dict[str, Any]]:
    backend = str(metadata["backend"])
    index_path = Path(metadata["index_path"])
    if not index_path.exists():
        raise RuntimeError(f"local vector projection file is missing: {index_path}")
    dimensions = int((metadata.get("embedding_spec") or {})["dimensions"])
    query = np.asarray(query_vector[:dimensions], dtype=np.float32)
    if backend == "numpy":
        return _search_numpy_projection(
            index_path,
            query=query,
            mapping=mapping,
            allowed_ids=allowed_ids,
            limit=limit,
        )
    if backend == "turbovec":
        return _search_turbovec_projection(
            index_path,
            query=query,
            mapping=mapping,
            allowed_ids=allowed_ids,
            limit=limit,
        )
    raise RuntimeError(f"unsupported projection backend in metadata: {backend}")


def _search_numpy_projection(
    index_path: Path,
    *,
    query: np.ndarray,
    mapping: dict[int, str],
    allowed_ids: set[int] | None,
    limit: int,
) -> list[dict[str, Any]]:
    payload = np.load(index_path)
    matrix = payload["matrix"].astype(np.float32, copy=False)
    vector_ids = payload["vector_ids"].astype(np.uint64, copy=False)
    scores = matrix @ query
    if allowed_ids is not None:
        allowed_mask = np.asarray([int(vector_id) in allowed_ids for vector_id in vector_ids])
        scores = np.where(allowed_mask, scores, -np.inf)
    candidate_count = int(np.isfinite(scores).sum())
    if candidate_count == 0:
        return []
    resolved_limit = min(limit, candidate_count)
    if resolved_limit < len(scores):
        candidate_indices = np.argpartition(scores, -resolved_limit)[-resolved_limit:]
        ranked_indices = candidate_indices[np.argsort(scores[candidate_indices])[::-1]]
    else:
        ranked_indices = np.argsort(scores)[::-1]
    hits = []
    for row_index in ranked_indices:
        score = float(scores[int(row_index)])
        if not np.isfinite(score):
            continue
        vector_id = int(vector_ids[int(row_index)])
        hits.append({"doc_id": mapping[vector_id], "score": score})
    return hits


def _search_turbovec_projection(
    index_path: Path,
    *,
    query: np.ndarray,
    mapping: dict[int, str],
    allowed_ids: set[int] | None,
    limit: int,
) -> list[dict[str, Any]]:
    try:
        from turbovec import IdMapIndex  # type: ignore[import-not-found]
    except ImportError as exc:
        raise RuntimeError(
            "turbovec backend requires the optional turbovec package; "
            "install the local-vector extra or choose --backend numpy"
        ) from exc
    index = IdMapIndex.load(str(index_path))
    kwargs: dict[str, Any] = {}
    if allowed_ids is not None:
        kwargs["allowlist"] = np.asarray(sorted(allowed_ids), dtype=np.uint64)
    scores, ids = index.search(query, k=limit, **kwargs)
    hits = []
    for score, vector_id in zip(scores, ids, strict=False):
        doc_id = mapping.get(int(vector_id))
        if doc_id is not None:
            hits.append({"doc_id": doc_id, "score": float(score)})
    return hits


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _projection_hash(*, index_path: Path, mapping_path: Path) -> str:
    digest = hashlib.sha256()
    for path in (index_path, mapping_path):
        digest.update(path.name.encode("utf-8"))
        digest.update(_sha256_file(path).encode("ascii"))
    return digest.hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
