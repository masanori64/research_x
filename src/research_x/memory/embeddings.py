from __future__ import annotations

import hashlib
import json
import math
import os
import re
import sqlite3
import struct
import sys
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np

from research_x.memory.schema import ensure_memory_schema, memory_document_count

LOCAL_HASH_PROVIDER = "local_hash"
LOCAL_HASH_MODEL = "local-hash-v1"
OPENAI_PROVIDER = "openai"
OPENAI_DEFAULT_MODEL = "text-embedding-3-small"
GEMINI_PROVIDER = "gemini"
GEMINI_DEFAULT_MODEL = "gemini-embedding-2"
PRODUCTION_PROVIDERS = (GEMINI_PROVIDER, OPENAI_PROVIDER)
DEFAULT_EMBEDDING_PROFILE = "general_memory"
DEFAULT_TEXT_TEMPLATE_VERSION = "memory-doc-embedding-v1"

DEFAULT_DIMENSIONS = {
    LOCAL_HASH_PROVIDER: 512,
    OPENAI_PROVIDER: 1536,
    GEMINI_PROVIDER: 768,
}


@dataclass(frozen=True)
class EmbeddingSpec:
    provider: str
    model: str
    dimensions: int
    embedding_profile: str = DEFAULT_EMBEDDING_PROFILE
    text_template_version: str = DEFAULT_TEXT_TEMPLATE_VERSION
    api_key_env: str | None = None
    base_url: str | None = None
    timeout_seconds: float = 60.0


@dataclass(frozen=True)
class EmbeddingBuildSummary:
    db_path: str
    provider: str
    model: str
    dimensions: int
    embedding_profile: str
    text_template_version: str
    selected: int
    embedded: int
    skipped: int


@dataclass(frozen=True)
class EmbeddingCoverageRow:
    doc_type: str
    documents: int
    current: int
    missing: int
    stale_text: int
    stale_source: int


@dataclass(frozen=True)
class EmbeddingCoverageReport:
    db_path: str
    provider: str
    model: str
    dimensions: int
    embedding_profile: str
    text_template_version: str
    documents: int
    current: int
    missing: int
    stale_text: int
    stale_source: int
    by_doc_type: tuple[EmbeddingCoverageRow, ...]


@dataclass(frozen=True)
class SemanticHit:
    doc_id: str
    similarity: float
    provider: str
    model: str
    dimensions: int
    embedding_profile: str
    text_template_version: str


@dataclass(frozen=True)
class SemanticScore:
    doc_id: str
    similarity: float
    provider: str
    model: str
    dimensions: int
    embedding_profile: str
    text_template_version: str


def resolve_embedding_spec(
    *,
    provider: str | None = None,
    model: str | None = None,
    dimensions: int | None = None,
    embedding_profile: str | None = None,
    text_template_version: str | None = None,
    api_key_env: str | None = None,
    base_url: str | None = None,
    timeout_seconds: float = 60.0,
) -> EmbeddingSpec:
    resolved_provider = (provider or "auto").strip().lower()
    if resolved_provider == "auto":
        resolved_provider = _auto_embedding_provider()
    if resolved_provider == LOCAL_HASH_PROVIDER:
        resolved_model = model or LOCAL_HASH_MODEL
    elif resolved_provider == OPENAI_PROVIDER:
        resolved_model = model or OPENAI_DEFAULT_MODEL
    elif resolved_provider == GEMINI_PROVIDER:
        resolved_model = model or GEMINI_DEFAULT_MODEL
    else:
        raise ValueError(f"unknown embedding provider: {provider}")
    resolved_dimensions = dimensions or DEFAULT_DIMENSIONS[resolved_provider]
    if resolved_dimensions <= 0:
        raise ValueError("embedding dimensions must be positive")
    return EmbeddingSpec(
        provider=resolved_provider,
        model=resolved_model,
        dimensions=resolved_dimensions,
        embedding_profile=_clean_id(embedding_profile) or DEFAULT_EMBEDDING_PROFILE,
        text_template_version=_clean_id(text_template_version)
        or DEFAULT_TEXT_TEMPLATE_VERSION,
        api_key_env=api_key_env,
        base_url=base_url,
        timeout_seconds=timeout_seconds,
    )


def build_memory_embeddings(
    db_path: str | Path,
    *,
    provider: str | None = None,
    model: str | None = None,
    dimensions: int | None = None,
    embedding_profile: str | None = None,
    text_template_version: str | None = None,
    api_key_env: str | None = None,
    base_url: str | None = None,
    batch_size: int = 64,
    limit: int | None = None,
    rebuild: bool = False,
    progress_every: int = 1000,
) -> EmbeddingBuildSummary:
    path = Path(db_path)
    if not path.exists():
        raise FileNotFoundError(f"database not found: {path}")
    spec = resolve_embedding_spec(
        provider=provider,
        model=model,
        dimensions=dimensions,
        embedding_profile=embedding_profile,
        text_template_version=text_template_version,
        api_key_env=api_key_env,
        base_url=base_url,
    )
    resolved_batch_size = max(1, batch_size)
    selected = 0
    embedded = 0
    skipped = 0
    with sqlite3.connect(path, timeout=60) as conn:
        conn.row_factory = sqlite3.Row
        ensure_memory_schema(conn)
        if memory_document_count(conn) == 0:
            raise RuntimeError("memory_documents is empty; run memory build-corpus first")
        rows = _embedding_source_rows(
            conn,
            spec=spec,
            limit=limit,
            rebuild=rebuild,
        )
        selected = len(rows)
        embedder = _embedder(spec)
        for batch in _chunks(rows, resolved_batch_size):
            texts = [_embedding_text(row) for row in batch]
            vectors = embedder.embed_texts(texts, task_type="RETRIEVAL_DOCUMENT")
            if len(vectors) != len(batch):
                raise RuntimeError(
                    f"embedding provider returned {len(vectors)} vectors for {len(batch)} texts"
                )
            now = _utc_now()
            for row, text, vector in zip(batch, texts, vectors, strict=True):
                text_hash = _text_hash(text)
                source_hash = _source_doc_hash(row)
                existing_hash = row["embedded_text_hash"]
                existing_source_hash = row["source_doc_hash"]
                if (
                    not rebuild
                    and existing_hash == text_hash
                    and existing_source_hash == source_hash
                ):
                    skipped += 1
                    continue
                _upsert_embedding(
                    conn,
                    spec=spec,
                    doc_id=row["doc_id"],
                    vector=vector,
                    text_hash=text_hash,
                    source_doc_hash=source_hash,
                    now=now,
                )
                embedded += 1
            conn.commit()
            if progress_every > 0 and (embedded + skipped) % progress_every < len(batch):
                print(
                    f"embedding progress: {embedded + skipped}/{selected} "
                    f"embedded={embedded} skipped={skipped}",
                    file=sys.stderr,
                    flush=True,
                )
    return EmbeddingBuildSummary(
        db_path=str(path),
        provider=spec.provider,
        model=spec.model,
        dimensions=spec.dimensions,
        embedding_profile=spec.embedding_profile,
        text_template_version=spec.text_template_version,
        selected=selected,
        embedded=embedded,
        skipped=skipped,
    )


def semantic_search_memory(
    db_path: str | Path,
    query: str,
    *,
    provider: str | None = None,
    model: str | None = None,
    dimensions: int | None = None,
    embedding_profile: str | None = None,
    text_template_version: str | None = None,
    api_key_env: str | None = None,
    base_url: str | None = None,
    limit: int = 50,
    doc_type: str | None = None,
    account: str | None = None,
) -> tuple[SemanticHit, ...]:
    path = Path(db_path)
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
            api_key_env=api_key_env,
            base_url=base_url,
        )
        query_vector = _embedder(spec).embed_texts([query], task_type="RETRIEVAL_QUERY")[0]
        rows = _embedding_rows(conn, spec=spec, doc_type=doc_type, account=account)
        expected_rows = _embedding_document_count(conn, doc_type=doc_type, account=account)
        if expected_rows and len(rows) < expected_rows:
            raise RuntimeError(
                "semantic index is incomplete for the requested scope: "
                f"{len(rows)}/{expected_rows} documents indexed for "
                f"{spec.provider}/{spec.model} dims={spec.dimensions}"
            )
    hits = _semantic_hits_from_rows(rows, query_vector=query_vector)
    hits.sort(key=lambda hit: hit.similarity, reverse=True)
    return tuple(hits[: max(1, limit)])


def semantic_scores_for_doc_ids(
    db_path: str | Path,
    query: str,
    doc_ids: tuple[str, ...],
    *,
    provider: str | None = None,
    model: str | None = None,
    dimensions: int | None = None,
    embedding_profile: str | None = None,
    text_template_version: str | None = None,
    api_key_env: str | None = None,
    base_url: str | None = None,
) -> dict[str, SemanticScore]:
    if not doc_ids:
        return {}
    path = Path(db_path)
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
            api_key_env=api_key_env,
            base_url=base_url,
        )
        query_vector = _embedder(spec).embed_texts([query], task_type="RETRIEVAL_QUERY")[0]
        rows = _embedding_rows_for_doc_ids(conn, spec=spec, doc_ids=doc_ids)
        if len(rows) < len(set(doc_ids)):
            raise RuntimeError(
                "semantic index is incomplete for the candidate set: "
                f"{len(rows)}/{len(set(doc_ids))} documents indexed for "
                f"{spec.provider}/{spec.model} dims={spec.dimensions}"
            )
    return {
        row["doc_id"]: SemanticScore(
            doc_id=row["doc_id"],
            similarity=cosine_similarity(
                query_vector,
                unpack_embedding_array(row["embedding"], int(row["dimensions"])),
            ),
            provider=row["provider"],
            model=row["model"],
            dimensions=int(row["dimensions"]),
            embedding_profile=row["embedding_profile"],
            text_template_version=row["text_template_version"],
        )
        for row in rows
    }


def available_embedding_specs(db_path: str | Path) -> tuple[EmbeddingSpec, ...]:
    path = Path(db_path)
    with sqlite3.connect(path, timeout=60) as conn:
        conn.row_factory = sqlite3.Row
        ensure_memory_schema(conn)
        rows = conn.execute(
            """
            SELECT
                provider, model, dimensions,
                embedding_profile, text_template_version
            FROM memory_embeddings
            GROUP BY
                provider, model, dimensions,
                embedding_profile, text_template_version
            ORDER BY
                MAX(updated_at) DESC, provider, model, dimensions,
                embedding_profile, text_template_version
            """
        ).fetchall()
    return tuple(
        EmbeddingSpec(
            provider=row["provider"],
            model=row["model"],
            dimensions=int(row["dimensions"]),
            embedding_profile=row["embedding_profile"],
            text_template_version=row["text_template_version"],
        )
        for row in rows
    )


def embedding_coverage_report(
    db_path: str | Path,
    *,
    provider: str | None = None,
    model: str | None = None,
    dimensions: int | None = None,
    embedding_profile: str | None = None,
    text_template_version: str | None = None,
) -> EmbeddingCoverageReport:
    path = Path(db_path)
    if not path.exists():
        raise FileNotFoundError(f"database not found: {path}")
    with sqlite3.connect(path, timeout=60) as conn:
        conn.row_factory = sqlite3.Row
        ensure_memory_schema(conn)
        if memory_document_count(conn) == 0:
            raise RuntimeError("memory_documents is empty; run memory build-corpus first")
        spec = _coverage_spec(
            conn,
            provider=provider,
            model=model,
            dimensions=dimensions,
            embedding_profile=embedding_profile,
            text_template_version=text_template_version,
        )
        rows = conn.execute(
            """
            SELECT
                d.doc_id, d.doc_type, d.title, d.compact_text, d.body, d.metadata_json,
                e.embedded_text_hash, e.source_doc_hash
            FROM memory_documents d
            LEFT JOIN memory_embeddings e
              ON e.doc_id = d.doc_id
             AND e.provider = ?
             AND e.model = ?
             AND e.dimensions = ?
             AND e.embedding_profile = ?
             AND e.text_template_version = ?
            ORDER BY d.doc_type, d.doc_id
            """,
            (
                spec.provider,
                spec.model,
                spec.dimensions,
                spec.embedding_profile,
                spec.text_template_version,
            ),
        ).fetchall()
    by_type: dict[str, dict[str, int]] = {}
    totals = {"documents": 0, "current": 0, "missing": 0, "stale_text": 0, "stale_source": 0}
    for row in rows:
        bucket = by_type.setdefault(
            str(row["doc_type"]),
            {"documents": 0, "current": 0, "missing": 0, "stale_text": 0, "stale_source": 0},
        )
        status = _coverage_status(row)
        bucket["documents"] += 1
        totals["documents"] += 1
        bucket[status] += 1
        totals[status] += 1
    by_doc_type = tuple(
        EmbeddingCoverageRow(doc_type=doc_type, **counts)
        for doc_type, counts in sorted(by_type.items())
    )
    return EmbeddingCoverageReport(
        db_path=str(path),
        provider=spec.provider,
        model=spec.model,
        dimensions=spec.dimensions,
        embedding_profile=spec.embedding_profile,
        text_template_version=spec.text_template_version,
        documents=totals["documents"],
        current=totals["current"],
        missing=totals["missing"],
        stale_text=totals["stale_text"],
        stale_source=totals["stale_source"],
        by_doc_type=by_doc_type,
    )


def embedding_coverage_json(report: EmbeddingCoverageReport) -> str:
    return json.dumps(asdict(report), ensure_ascii=False, indent=2, sort_keys=True)


def format_embedding_coverage(report: EmbeddingCoverageReport) -> str:
    lines = [
        f"db: {report.db_path}",
        (
            "spec: "
            f"{report.provider}/{report.model} dims={report.dimensions} "
            f"profile={report.embedding_profile} template={report.text_template_version}"
        ),
        (
            "documents: "
            f"{report.documents} current={report.current} missing={report.missing} "
            f"stale_text={report.stale_text} stale_source={report.stale_source}"
        ),
        "by doc_type:",
    ]
    for row in report.by_doc_type:
        lines.append(
            "  "
            f"{row.doc_type}: docs={row.documents} current={row.current} "
            f"missing={row.missing} stale_text={row.stale_text} "
            f"stale_source={row.stale_source}"
        )
    return "\n".join(lines)


def summary_as_dict(summary: EmbeddingBuildSummary) -> dict[str, Any]:
    return asdict(summary)


def pack_embedding(vector: list[float]) -> bytes:
    return struct.pack(f"<{len(vector)}f", *vector)


def unpack_embedding(value: bytes, dimensions: int) -> list[float]:
    if len(value) != dimensions * 4:
        raise ValueError(
            f"embedding blob size mismatch: got {len(value)} bytes for {dimensions} dimensions"
        )
    return list(struct.unpack(f"<{dimensions}f", value))


def unpack_embedding_array(value: bytes, dimensions: int):
    if len(value) != dimensions * 4:
        raise ValueError(
            f"embedding blob size mismatch: got {len(value)} bytes for {dimensions} dimensions"
        )
    return np.frombuffer(value, dtype="<f4")


def cosine_similarity(left, right) -> float:
    length = min(len(left), len(right))
    if length == 0:
        return 0.0
    dot = sum(left[index] * right[index] for index in range(length))
    left_norm = math.sqrt(sum(left[index] * left[index] for index in range(length)))
    right_norm = math.sqrt(sum(right[index] * right[index] for index in range(length)))
    if not left_norm or not right_norm:
        return 0.0
    return dot / (left_norm * right_norm)


class _LocalHashEmbedder:
    def __init__(self, spec: EmbeddingSpec) -> None:
        self.spec = spec

    def embed_texts(self, texts: list[str], *, task_type: str) -> list[list[float]]:
        return [_local_hash_embedding(text, dimensions=self.spec.dimensions) for text in texts]


class _OpenAIEmbedder:
    def __init__(self, spec: EmbeddingSpec) -> None:
        self.spec = spec
        self.api_key = _api_key(spec.api_key_env or "OPENAI_API_KEY")

    def embed_texts(self, texts: list[str], *, task_type: str) -> list[list[float]]:
        payload: dict[str, Any] = {
            "model": self.spec.model,
            "input": texts,
            "encoding_format": "float",
        }
        if self.spec.dimensions:
            payload["dimensions"] = self.spec.dimensions
        response = _post_json(
            self.spec.base_url or "https://api.openai.com/v1/embeddings",
            payload,
            headers={"Authorization": f"Bearer {self.api_key}"},
            timeout_seconds=self.spec.timeout_seconds,
        )
        data = response.get("data")
        if not isinstance(data, list):
            raise RuntimeError(f"OpenAI embeddings response missing data: {response}")
        vectors = []
        for item in sorted(data, key=lambda row: int(row.get("index", 0))):
            vector = item.get("embedding")
            if not isinstance(vector, list):
                raise RuntimeError(f"OpenAI embeddings response missing embedding: {item}")
            vectors.append(_normalize_vector([float(value) for value in vector]))
        return vectors


class _GeminiEmbedder:
    def __init__(self, spec: EmbeddingSpec) -> None:
        self.spec = spec
        self.api_key = _api_key(spec.api_key_env or "GEMINI_API_KEY")

    def embed_texts(self, texts: list[str], *, task_type: str) -> list[list[float]]:
        model_name = _gemini_model_name(self.spec.model)
        requests = []
        for text in texts:
            config: dict[str, Any] = {}
            if self.spec.dimensions:
                config["outputDimensionality"] = self.spec.dimensions
            if not _is_gemini_embedding_2(self.spec.model):
                config["taskType"] = task_type
            request: dict[str, Any] = {
                "model": model_name,
                "content": {
                    "parts": [
                        {
                            "text": _gemini_content_text(
                                text,
                                model=self.spec.model,
                                task_type=task_type,
                            )
                        }
                    ]
                },
            }
            if config:
                request["embedContentConfig"] = config
            requests.append(request)
        response = _post_json(
            self.spec.base_url
            or f"https://generativelanguage.googleapis.com/v1beta/{model_name}:batchEmbedContents",
            {"requests": requests},
            headers={"x-goog-api-key": self.api_key},
            timeout_seconds=self.spec.timeout_seconds,
        )
        embeddings = response.get("embeddings")
        if not isinstance(embeddings, list):
            raise RuntimeError(f"Gemini embeddings response missing embeddings: {response}")
        vectors = []
        for item in embeddings:
            values = item.get("values")
            if not isinstance(values, list):
                raise RuntimeError(f"Gemini embeddings response missing values: {item}")
            vectors.append(_normalize_vector([float(value) for value in values]))
        return vectors


def _embedder(spec: EmbeddingSpec):
    if spec.provider == LOCAL_HASH_PROVIDER:
        return _LocalHashEmbedder(spec)
    if spec.provider == OPENAI_PROVIDER:
        return _OpenAIEmbedder(spec)
    if spec.provider == GEMINI_PROVIDER:
        return _GeminiEmbedder(spec)
    raise ValueError(f"unknown embedding provider: {spec.provider}")


def _embedding_source_rows(
    conn: sqlite3.Connection,
    *,
    spec: EmbeddingSpec,
    limit: int | None,
    rebuild: bool,
) -> list[sqlite3.Row]:
    sql = """
        SELECT
            d.doc_id, d.title, d.compact_text, d.body, d.metadata_json,
            e.embedded_text_hash, e.source_doc_hash
        FROM memory_documents d
        LEFT JOIN memory_embeddings e
          ON e.doc_id = d.doc_id
         AND e.provider = ?
         AND e.model = ?
         AND e.dimensions = ?
         AND e.embedding_profile = ?
         AND e.text_template_version = ?
        ORDER BY d.observed_at DESC, d.doc_id
    """
    params: list[Any] = [
        spec.provider,
        spec.model,
        spec.dimensions,
        spec.embedding_profile,
        spec.text_template_version,
    ]
    if limit is not None and limit > 0:
        sql += " LIMIT ?"
        params.append(limit)
    rows = conn.execute(sql, params).fetchall()
    if rebuild:
        return rows
    return [
        row
        for row in rows
        if (
            row["embedded_text_hash"] != _text_hash(_embedding_text(row))
            or row["source_doc_hash"] != _source_doc_hash(row)
        )
    ]


def _embedding_rows(
    conn: sqlite3.Connection,
    *,
    spec: EmbeddingSpec,
    doc_type: str | None,
    account: str | None,
) -> list[sqlite3.Row]:
    filters = []
    params: list[Any] = [
        spec.provider,
        spec.model,
        spec.dimensions,
        spec.embedding_profile,
        spec.text_template_version,
    ]
    if doc_type:
        filters.append("AND d.doc_type = ?")
        params.append(doc_type)
    if account:
        filters.append("AND d.account_id = ?")
        params.append(account)
    return conn.execute(
        f"""
        SELECT
            e.doc_id, e.provider, e.model, e.dimensions,
            e.embedding_profile, e.text_template_version, e.embedding
        FROM memory_embeddings e
        JOIN memory_documents d ON d.doc_id = e.doc_id
        WHERE e.provider = ?
          AND e.model = ?
          AND e.dimensions = ?
          AND e.embedding_profile = ?
          AND e.text_template_version = ?
        {' '.join(filters)}
        """,
        params,
    ).fetchall()


def _embedding_document_count(
    conn: sqlite3.Connection,
    *,
    doc_type: str | None,
    account: str | None,
) -> int:
    filters, params = [], []
    if doc_type:
        filters.append("doc_type = ?")
        params.append(doc_type)
    if account:
        filters.append("account_id = ?")
        params.append(account)
    where = f"WHERE {' AND '.join(filters)}" if filters else ""
    return int(
        conn.execute(f"SELECT COUNT(*) FROM memory_documents {where}", params).fetchone()[0]
    )


def _embedding_rows_for_doc_ids(
    conn: sqlite3.Connection,
    *,
    spec: EmbeddingSpec,
    doc_ids: tuple[str, ...],
) -> list[sqlite3.Row]:
    placeholders = ",".join("?" for _ in doc_ids)
    return conn.execute(
        f"""
        SELECT
            e.doc_id, e.provider, e.model, e.dimensions,
            e.embedding_profile, e.text_template_version, e.embedding
        FROM memory_embeddings e
        WHERE e.provider = ?
          AND e.model = ?
          AND e.dimensions = ?
          AND e.embedding_profile = ?
          AND e.text_template_version = ?
          AND e.doc_id IN ({placeholders})
        """,
        (
            spec.provider,
            spec.model,
            spec.dimensions,
            spec.embedding_profile,
            spec.text_template_version,
            *doc_ids,
        ),
    ).fetchall()


def _semantic_hits_from_rows(
    rows: list[sqlite3.Row],
    *,
    query_vector: list[float],
) -> list[SemanticHit]:
    if not rows:
        return []
    dimensions = int(rows[0]["dimensions"])
    query = np.asarray(query_vector[:dimensions], dtype=np.float32)
    hits: list[SemanticHit] = []
    batch_size = max(1, min(10000, len(rows)))
    for batch in _chunks(rows, batch_size):
        blobs = b"".join(row["embedding"] for row in batch)
        matrix = np.frombuffer(blobs, dtype="<f4").reshape(len(batch), dimensions)
        scores = matrix @ query
        for row, score in zip(batch, scores, strict=True):
            hits.append(
                SemanticHit(
                    doc_id=row["doc_id"],
                    similarity=float(score),
                    provider=row["provider"],
                    model=row["model"],
                    dimensions=dimensions,
                    embedding_profile=row["embedding_profile"],
                    text_template_version=row["text_template_version"],
                )
            )
    return hits


def _resolve_available_spec(
    conn: sqlite3.Connection,
    *,
    provider: str | None,
    model: str | None,
    dimensions: int | None,
    embedding_profile: str | None,
    text_template_version: str | None,
    api_key_env: str | None,
    base_url: str | None,
) -> EmbeddingSpec:
    resolved_provider = provider.strip().lower() if provider else None
    if resolved_provider == "auto":
        resolved_provider = None
    if resolved_provider:
        spec = resolve_embedding_spec(
            provider=provider,
            model=model,
            dimensions=dimensions,
            embedding_profile=embedding_profile,
            text_template_version=text_template_version,
            api_key_env=api_key_env,
            base_url=base_url,
        )
        rows = _embedding_index_count(conn, spec)
        if rows == 0:
            raise RuntimeError(
                "embedding index not found for "
                f"{spec.provider}/{spec.model} dims={spec.dimensions}; "
                "run `research_x memory build-embeddings` for this provider first"
            )
        return spec
    filters = [
        f"provider IN ({','.join('?' for _ in PRODUCTION_PROVIDERS)})",
    ]
    params: list[Any] = list(PRODUCTION_PROVIDERS)
    if model:
        filters.append("model = ?")
        params.append(model)
    if dimensions:
        filters.append("dimensions = ?")
        params.append(dimensions)
    if embedding_profile:
        filters.append("embedding_profile = ?")
        params.append(embedding_profile)
    if text_template_version:
        filters.append("text_template_version = ?")
        params.append(text_template_version)
    row = conn.execute(
        f"""
        SELECT
            provider, model, dimensions,
            embedding_profile, text_template_version
        FROM memory_embeddings
        WHERE {' AND '.join(filters)}
        GROUP BY
            provider, model, dimensions,
            embedding_profile, text_template_version
        ORDER BY
            MAX(updated_at) DESC, provider, model, dimensions,
            embedding_profile, text_template_version
        LIMIT 1
        """,
        params,
    ).fetchone()
    if row:
        return resolve_embedding_spec(
            provider=row["provider"],
            model=row["model"],
            dimensions=int(row["dimensions"]),
            embedding_profile=row["embedding_profile"],
            text_template_version=row["text_template_version"],
            api_key_env=api_key_env,
            base_url=base_url,
        )
    local_hash_rows = conn.execute(
        "SELECT COUNT(*) FROM memory_embeddings WHERE provider = ?",
        (LOCAL_HASH_PROVIDER,),
    ).fetchone()[0]
    if local_hash_rows:
        raise RuntimeError(
            "only diagnostic local_hash embeddings are available. "
            "Build a production embedding index with OpenAI or Gemini, "
            "or explicitly pass --semantic-provider local_hash for diagnostic searches."
        )
    raise RuntimeError(
        "no production memory embeddings found; run "
        "`research_x memory build-embeddings --provider gemini` or "
        "`research_x memory build-embeddings --provider openai` first"
    )


def _coverage_spec(
    conn: sqlite3.Connection,
    *,
    provider: str | None,
    model: str | None,
    dimensions: int | None,
    embedding_profile: str | None,
    text_template_version: str | None,
) -> EmbeddingSpec:
    resolved_provider = provider.strip().lower() if provider else None
    if resolved_provider in {None, "", "latest"}:
        row = conn.execute(
            """
            SELECT
                provider, model, dimensions,
                embedding_profile, text_template_version
            FROM memory_embeddings
            GROUP BY
                provider, model, dimensions,
                embedding_profile, text_template_version
            ORDER BY
                CASE WHEN provider IN ('gemini', 'openai') THEN 0 ELSE 1 END,
                MAX(updated_at) DESC,
                provider, model, dimensions, embedding_profile, text_template_version
            LIMIT 1
            """
        ).fetchone()
        if row:
            return resolve_embedding_spec(
                provider=row["provider"],
                model=row["model"],
                dimensions=int(row["dimensions"]),
                embedding_profile=row["embedding_profile"],
                text_template_version=row["text_template_version"],
            )
        return resolve_embedding_spec(provider=GEMINI_PROVIDER)
    if resolved_provider == "auto":
        resolved_provider = _auto_embedding_provider()
    return resolve_embedding_spec(
        provider=resolved_provider,
        model=model,
        dimensions=dimensions,
        embedding_profile=embedding_profile,
        text_template_version=text_template_version,
    )


def _coverage_status(row: sqlite3.Row) -> str:
    if row["embedded_text_hash"] is None:
        return "missing"
    if row["source_doc_hash"] != _source_doc_hash(row):
        return "stale_source"
    if row["embedded_text_hash"] != _text_hash(_embedding_text(row)):
        return "stale_text"
    return "current"


def _embedding_index_count(conn: sqlite3.Connection, spec: EmbeddingSpec) -> int:
    row = conn.execute(
        """
        SELECT COUNT(*)
        FROM memory_embeddings
        WHERE provider = ?
          AND model = ?
          AND dimensions = ?
          AND embedding_profile = ?
          AND text_template_version = ?
        """,
        (
            spec.provider,
            spec.model,
            spec.dimensions,
            spec.embedding_profile,
            spec.text_template_version,
        ),
    ).fetchone()
    if not row:
        return 0
    return int(row[0])


def _upsert_embedding(
    conn: sqlite3.Connection,
    *,
    spec: EmbeddingSpec,
    doc_id: str,
    vector: list[float],
    text_hash: str,
    source_doc_hash: str,
    now: str,
) -> None:
    if len(vector) != spec.dimensions:
        raise RuntimeError(
            f"embedding provider returned {len(vector)} dimensions for "
            f"{spec.provider}/{spec.model}, expected {spec.dimensions}"
        )
    conn.execute(
        """
        INSERT INTO memory_embeddings (
            doc_id, provider, model, dimensions,
            embedding_profile, text_template_version,
            embedding, source_doc_hash, embedded_text_hash, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(
            doc_id, provider, model, dimensions,
            embedding_profile, text_template_version
        ) DO UPDATE SET
            embedding=excluded.embedding,
            source_doc_hash=excluded.source_doc_hash,
            embedded_text_hash=excluded.embedded_text_hash,
            updated_at=excluded.updated_at
        """,
        (
            doc_id,
            spec.provider,
            spec.model,
            spec.dimensions,
            spec.embedding_profile,
            spec.text_template_version,
            pack_embedding(_normalize_vector(vector)),
            source_doc_hash,
            text_hash,
            now,
            now,
        ),
    )


def _embedding_text(row: sqlite3.Row) -> str:
    metadata = _compact_metadata(row["metadata_json"])
    compact_text = row["compact_text"] or ""
    body = row["body"] or ""
    body_extra = body[:1200] if compact_text not in body else ""
    text = "\n".join(
        part
        for part in (
            row["title"] or "",
            compact_text,
            body_extra,
            metadata,
        )
        if part
    )
    return text[:2400]


def _source_doc_hash(row: sqlite3.Row) -> str:
    payload = {
        "doc_id": row["doc_id"],
        "title": row["title"],
        "compact_text": row["compact_text"],
        "body": row["body"],
        "metadata_json": row["metadata_json"],
    }
    return _text_hash(json.dumps(payload, ensure_ascii=False, sort_keys=True))


def _compact_metadata(value: str | None) -> str:
    if not value:
        return ""
    try:
        metadata = json.loads(value)
    except json.JSONDecodeError:
        return ""
    if not isinstance(metadata, dict):
        return ""
    useful = {
        key: metadata.get(key)
        for key in ("url", "role", "collection_kind", "labels", "type", "download_status")
        if metadata.get(key)
    }
    return f"metadata: {json.dumps(useful, ensure_ascii=False, sort_keys=True)}" if useful else ""


def _text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _clean_id(value: str | None) -> str | None:
    if value is None:
        return None
    text = value.strip()
    if not text:
        return None
    if not re.fullmatch(r"[A-Za-z0-9_.:-]+", text):
        raise ValueError(
            "embedding profile/template values may only contain letters, numbers, "
            "underscore, dot, colon, or dash"
        )
    return text


_TOKEN_RE = re.compile(r"[A-Za-z0-9_]+|[\u3040-\u30ff\u3400-\u9fff]+")


def _local_hash_embedding(text: str, *, dimensions: int) -> list[float]:
    vector = [0.0] * dimensions
    normalized_text = " ".join(text.casefold().split())
    features: list[tuple[str, float]] = []
    for token in _TOKEN_RE.findall(normalized_text):
        features.append((f"tok:{token}", 2.0))
        for ngram_size in (2, 3):
            if len(token) >= ngram_size:
                for index in range(len(token) - ngram_size + 1):
                    features.append((f"ng{ngram_size}:{token[index:index + ngram_size]}", 0.75))
    if not features:
        features.append((normalized_text, 1.0))
    for feature, weight in features:
        digest = hashlib.blake2b(feature.encode("utf-8"), digest_size=8).digest()
        bucket = int.from_bytes(digest[:4], "little") % dimensions
        sign = 1.0 if digest[4] & 1 else -1.0
        vector[bucket] += sign * weight
    return _normalize_vector(vector)


def _normalize_vector(vector: list[float]) -> list[float]:
    norm = math.sqrt(sum(value * value for value in vector))
    if not norm:
        return vector
    return [float(value / norm) for value in vector]


def _api_key(env_name: str) -> str:
    value = os.environ.get(env_name)
    if not value:
        raise RuntimeError(f"missing API key environment variable: {env_name}")
    return value


def _auto_embedding_provider() -> str:
    if os.environ.get("GEMINI_API_KEY"):
        return GEMINI_PROVIDER
    if os.environ.get("OPENAI_API_KEY"):
        return OPENAI_PROVIDER
    raise RuntimeError(
        "no production embedding API key found. Set GEMINI_API_KEY or OPENAI_API_KEY, "
        "or explicitly pass --provider local_hash for an offline diagnostic index."
    )


def _post_json(
    url: str,
    payload: dict[str, Any],
    *,
    headers: dict[str, str],
    timeout_seconds: float,
    retries: int = 3,
) -> dict[str, Any]:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        headers={
            "Content-Type": "application/json",
            **headers,
        },
        method="POST",
    )
    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            payload_text = exc.read().decode("utf-8", errors="replace")
            if exc.code not in {429, 500, 502, 503, 504} or attempt == retries:
                raise RuntimeError(f"embedding API HTTP {exc.code}: {payload_text}") from exc
            last_error = exc
        except TimeoutError as exc:
            if attempt == retries:
                raise RuntimeError("embedding API timed out") from exc
            last_error = exc
        time.sleep(min(2**attempt, 30))
    raise RuntimeError(f"embedding API failed: {last_error}")


def _gemini_model_name(model: str) -> str:
    return model if model.startswith("models/") else f"models/{model}"


def _is_gemini_embedding_2(model: str) -> bool:
    return model.removeprefix("models/") == "gemini-embedding-2"


def _gemini_content_text(text: str, *, model: str, task_type: str) -> str:
    if not _is_gemini_embedding_2(model):
        return text
    if task_type == "RETRIEVAL_QUERY":
        return f"Represent this search query for retrieval:\n{text}"
    return f"Represent this document for retrieval:\n{text}"


def _chunks(rows: list[sqlite3.Row], size: int):
    for index in range(0, len(rows), size):
        yield rows[index : index + size]


def _utc_now() -> str:
    return datetime.now(tz=UTC).isoformat()
