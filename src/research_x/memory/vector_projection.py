from __future__ import annotations

import json
import sqlite3
import uuid
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np

from research_x.memory.embeddings import (
    EmbeddingSpec,
    SemanticHit,
    _embedder,
    _embedding_document_count,
    _embedding_rows,
    _resolve_available_spec,
    _semantic_matrix_from_rows,
)
from research_x.memory.schema import ensure_memory_schema

VECTOR_PROJECTION_KIND = "local_vector_projection"
VECTOR_PROJECTION_BUILDER_VERSION = "local-vector-projection-v1"
SUPPORTED_VECTOR_BACKENDS = ("numpy", "turbovec")
DEFAULT_VECTOR_INDEX_DIR = Path("runs") / "memory_vector_indexes"


@dataclass(frozen=True)
class VectorProjectionBuildSummary:
    db_path: str
    generation_id: str
    backend: str
    provider: str
    model: str
    dimensions: int
    embedding_profile: str
    text_template_version: str
    bit_width: int | None
    documents: int
    index_path: str
    mapping_path: str
    source_scope: str


@dataclass(frozen=True)
class VectorProjectionCoverage:
    db_path: str
    generation_id: str | None
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


def build_vector_projection(
    db_path: str | Path,
    *,
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
) -> VectorProjectionBuildSummary:
    resolved_backend = _resolve_backend(backend)
    resolved_bit_width = _resolve_bit_width(bit_width, backend=resolved_backend)
    path = Path(db_path)
    if not path.exists():
        raise FileNotFoundError(f"database not found: {path}")
    with sqlite3.connect(path, timeout=60) as conn:
        conn.row_factory = sqlite3.Row
        ensure_memory_schema(conn)
        spec = _resolve_available_spec(
            conn,
            provider=provider,
            model=model,
            dimensions=dimensions,
            embedding_profile=embedding_profile,
            text_template_version=text_template_version,
            api_key_env=None,
            base_url=None,
        )
        rows = _embedding_rows(conn, spec=spec, doc_type=doc_type, account=account)
        expected_rows = _embedding_document_count(conn, doc_type=doc_type, account=account)
        if expected_rows and len(rows) < expected_rows:
            raise RuntimeError(
                "cannot build local vector projection from incomplete or stale embeddings: "
                f"{len(rows)}/{expected_rows} current rows for "
                f"{spec.provider}/{spec.model} dims={spec.dimensions}"
            )
        if not rows:
            raise RuntimeError("no current embeddings found for vector projection")
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
            spec=spec,
            backend=resolved_backend,
            bit_width=resolved_bit_width,
            source_scope=source_scope,
            index_path=index_path,
            mapping_path=mapping_path,
            rows=rows,
            doc_type=doc_type,
            account=account,
        )
    return VectorProjectionBuildSummary(
        db_path=str(path),
        generation_id=generation_id,
        backend=resolved_backend,
        provider=spec.provider,
        model=spec.model,
        dimensions=spec.dimensions,
        embedding_profile=spec.embedding_profile,
        text_template_version=spec.text_template_version,
        bit_width=resolved_bit_width,
        documents=len(rows),
        index_path=str(index_path),
        mapping_path=str(mapping_path),
        source_scope=source_scope,
    )


def vector_projection_coverage(
    db_path: str | Path,
    *,
    generation_id: str | None = None,
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
    status = "ok" if current == projection_documents and stale == 0 and index_exists else "stale"
    return VectorProjectionCoverage(
        db_path=str(path),
        generation_id=row["generation_id"],
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
    )


def search_vector_projection(
    db_path: str | Path,
    query: str,
    *,
    generation_id: str | None = None,
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
) -> tuple[SemanticHit, ...]:
    path = Path(db_path)
    with sqlite3.connect(path, timeout=60) as conn:
        conn.row_factory = sqlite3.Row
        ensure_memory_schema(conn)
        row = _projection_generation_row(
            conn,
            generation_id=generation_id,
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
        allowed_ids = _allowed_vector_ids(
            conn,
            row["generation_id"],
            mapping=mapping,
            doc_type=doc_type,
            account=account,
            doc_ids=doc_ids,
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
            provider=spec.provider,
            model=spec.model,
            dimensions=spec.dimensions,
            embedding_profile=spec.embedding_profile,
            text_template_version=spec.text_template_version,
        )
        for hit in hits
    )


def summary_as_dict(summary: VectorProjectionBuildSummary) -> dict[str, Any]:
    return asdict(summary)


def coverage_json(report: VectorProjectionCoverage) -> str:
    return json.dumps(asdict(report), ensure_ascii=False, indent=2, sort_keys=True)


def summary_json(summary: VectorProjectionBuildSummary) -> str:
    return json.dumps(asdict(summary), ensure_ascii=False, indent=2, sort_keys=True)


def format_vector_projection_summary(summary: VectorProjectionBuildSummary) -> str:
    return "\n".join(
        [
            f"generation_id: {summary.generation_id}",
            f"backend: {summary.backend}",
            (
                "spec: "
                f"{summary.provider}/{summary.model} dims={summary.dimensions} "
                f"profile={summary.embedding_profile} "
                f"template={summary.text_template_version}"
            ),
            f"documents: {summary.documents}",
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
        ]
    )


def _resolve_backend(backend: str) -> str:
    resolved = backend.strip().lower()
    if resolved not in SUPPORTED_VECTOR_BACKENDS:
        raise ValueError(f"unsupported local vector backend: {backend}")
    return resolved


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


def _build_mapping(rows: list[sqlite3.Row]) -> list[dict[str, Any]]:
    mapping = []
    for index, row in enumerate(rows, start=1):
        mapping.append(
            {
                "vector_id": index,
                "doc_id": str(row["doc_id"]),
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
    spec: EmbeddingSpec,
    backend: str,
    bit_width: int | None,
    source_scope: str,
    index_path: Path,
    mapping_path: Path,
    rows: list[sqlite3.Row],
    doc_type: str | None,
    account: str | None,
) -> None:
    now = _now()
    manifest = {
        "embedding_spec": asdict(spec),
        "source_scope": source_scope,
        "doc_type": doc_type,
        "account": account,
        "rows": len(rows),
    }
    coverage = {
        "documents": len(rows),
        "current": len(rows),
        "stale": 0,
    }
    metadata = {
        "backend": backend,
        "bit_width": bit_width,
        "index_path": str(index_path),
        "mapping_path": str(mapping_path),
        "documents": len(rows),
        "doc_type": doc_type,
        "account": account,
        "embedding_spec": asdict(spec),
    }
    conn.execute(
        """
        INSERT INTO memory_projection_generations (
            generation_id, projection_kind, source_scope, builder_version,
            input_manifest_json, status, coverage_json, created_at, metadata_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            generation_id,
            VECTOR_PROJECTION_KIND,
            source_scope,
            VECTOR_PROJECTION_BUILDER_VERSION,
            json.dumps(manifest, ensure_ascii=False, sort_keys=True),
            "current",
            json.dumps(coverage, ensure_ascii=False, sort_keys=True),
            now,
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
    provider: str | None,
    model: str | None,
    dimensions: int | None,
    embedding_profile: str | None,
    text_template_version: str | None,
    backend: str | None,
) -> sqlite3.Row | None:
    if generation_id:
        return conn.execute(
            """
            SELECT *
            FROM memory_projection_generations
            WHERE generation_id = ?
              AND projection_kind = ?
            """,
            (generation_id, VECTOR_PROJECTION_KIND),
        ).fetchone()
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
    for row in rows:
        metadata = json.loads(row["metadata_json"] or "{}")
        spec = metadata.get("embedding_spec") or {}
        if provider is None and spec.get("provider") == "local_hash":
            continue
        if backend and metadata.get("backend") != backend:
            continue
        if provider and spec.get("provider") != provider:
            continue
        if model and spec.get("model") != model:
            continue
        if dimensions and int(spec.get("dimensions") or 0) != dimensions:
            continue
        if embedding_profile and spec.get("embedding_profile") != embedding_profile:
            continue
        if text_template_version and spec.get("text_template_version") != text_template_version:
            continue
        return row
    return None


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
