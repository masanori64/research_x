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

from research_x.memory.api_budget import (
    api_units,
    budgeted_api_call,
    require_provider_quota_approval,
    require_provider_transport_send_allowed,
    rough_text_tokens,
)
from research_x.memory.document_hashes import (
    memory_document_embedding_text,
    memory_document_source_hash,
    text_hash,
)
from research_x.memory.schema import ensure_memory_schema, memory_document_count

LOCAL_HASH_PROVIDER = "local_hash"
LOCAL_HASH_MODEL = "local-hash-v1"
OPENAI_PROVIDER = "openai"
OPENAI_DEFAULT_MODEL = "text-embedding-3-small"
OPENAI_COMPATIBLE_PROVIDER = "openai_compatible"
OPENAI_COMPATIBLE_DEFAULT_MODEL = OPENAI_DEFAULT_MODEL
OPENAI_COMPATIBLE_BASE_URL_ENV = "OPENAI_COMPATIBLE_EMBEDDINGS_URL"
GEMINI_PROVIDER = "gemini"
GEMINI_DEFAULT_MODEL = "gemini-embedding-2"
VOYAGE_PROVIDER = "voyage"
VOYAGE_DEFAULT_MODEL = "voyage-4"
COHERE_PROVIDER = "cohere"
COHERE_DEFAULT_MODEL = "embed-v4.0"
MISTRAL_PROVIDER = "mistral"
MISTRAL_DEFAULT_MODEL = "codestral-embed-2505"
JINA_PROVIDER = "jina"
JINA_DEFAULT_MODEL = "jina-embeddings-v5-text-small"
PRODUCTION_PROVIDERS = (
    GEMINI_PROVIDER,
    OPENAI_PROVIDER,
    VOYAGE_PROVIDER,
    COHERE_PROVIDER,
    MISTRAL_PROVIDER,
    JINA_PROVIDER,
    OPENAI_COMPATIBLE_PROVIDER,
)
EMBEDDING_PROVIDER_CHOICES = ("auto", LOCAL_HASH_PROVIDER, *PRODUCTION_PROVIDERS)
DEFAULT_EMBEDDING_PROFILE = "general_memory"
DEFAULT_TEXT_TEMPLATE_VERSION = "memory-doc-embedding-v1"
EMBEDDING_EXECUTION_STAGES = (
    "auto",
    "technical_canary",
    "eval_slice",
    "production_scope",
)
EMBEDDING_SELECTION_POLICIES = (
    "auto",
    "sequential",
    "doc_type_round_robin",
)
EMBEDDING_PROVIDER_QUOTA_GATE_MESSAGE = (
    "semantic embedding provider API use is frozen, including paid/free-tier, "
    "trial-credit, zero-dollar, and keyless quota calls. Non-local embedding "
    "providers are provider_gated/quarantined while the no-quota freeze is active; "
    "use provider=local_hash only for diagnostic wiring or pass "
    "allow_provider_quota=True after explicit approval with API Budget Guard preflight."
)

DEFAULT_DIMENSIONS = {
    LOCAL_HASH_PROVIDER: 512,
    OPENAI_PROVIDER: 1536,
    OPENAI_COMPATIBLE_PROVIDER: 1536,
    GEMINI_PROVIDER: 768,
    VOYAGE_PROVIDER: 1024,
    COHERE_PROVIDER: 1536,
    MISTRAL_PROVIDER: 1024,
    JINA_PROVIDER: 1024,
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
    execution_stage: str
    selection_policy: str
    selection_contract: str


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
class EmbeddingBuildEstimate:
    db_path: str
    provider: str
    model: str
    dimensions: int
    embedding_profile: str
    text_template_version: str
    documents: int
    selected: int
    missing: int
    stale_text: int
    stale_source: int
    current: int
    estimated_input_chars: int
    estimated_input_tokens: int
    batch_size: int
    estimated_batches: int
    price_per_million_input_tokens: float | None = None
    estimated_input_cost: float | None = None
    execution_stage: str = "production_scope"
    selection_policy: str = "sequential"
    selection_contract: str = ""


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


def embedding_provider_signal_policy(provider: str | None) -> dict[str, Any]:
    normalized = _normalize_provider_for_policy(provider)
    provider_gated = normalized != LOCAL_HASH_PROVIDER
    return {
        "evidence_role": "retrieval_candidate_signal",
        "answer_support_allowed": False,
        "diagnostic_only": not provider_gated,
        "provider_gated": provider_gated,
        "quarantined": provider_gated,
        "production_eligible": False,
        "production_eligible_reason": (
            "provider_gated_while_no_quota_freeze"
            if provider_gated
            else "diagnostic_local_hash_only"
        ),
        "provider_policy": (
            "no_quota_freeze_provider_gated"
            if provider_gated
            else "local_hash_diagnostic_only"
        ),
        "promotion_gate": "source_bundle_context_citation_required",
    }


def require_embedding_provider_quota_allowed(
    provider: str | None,
    *,
    allow_provider_quota: bool,
    model: str | None = None,
    operation: str = "embedding",
) -> None:
    if _normalize_provider_for_policy(provider) == LOCAL_HASH_PROVIDER:
        return
    if not allow_provider_quota:
        raise RuntimeError(EMBEDDING_PROVIDER_QUOTA_GATE_MESSAGE)
    require_provider_quota_approval(
        provider=provider or "auto",
        model=model,
        operation=operation,
    )


def _normalize_provider_for_policy(provider: str | None) -> str:
    return (provider or "").strip().lower().replace("-", "_") or "auto"


@dataclass(frozen=True)
class LoadedSemanticIndex:
    spec: EmbeddingSpec
    doc_ids: tuple[str, ...]
    matrix: Any


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
    elif resolved_provider == OPENAI_COMPATIBLE_PROVIDER:
        resolved_model = model or OPENAI_COMPATIBLE_DEFAULT_MODEL
        base_url = base_url or os.environ.get(OPENAI_COMPATIBLE_BASE_URL_ENV)
    elif resolved_provider == GEMINI_PROVIDER:
        resolved_model = model or GEMINI_DEFAULT_MODEL
    elif resolved_provider == VOYAGE_PROVIDER:
        resolved_model = model or VOYAGE_DEFAULT_MODEL
    elif resolved_provider == COHERE_PROVIDER:
        resolved_model = model or COHERE_DEFAULT_MODEL
    elif resolved_provider == MISTRAL_PROVIDER:
        resolved_model = model or MISTRAL_DEFAULT_MODEL
    elif resolved_provider == JINA_PROVIDER:
        resolved_model = model or JINA_DEFAULT_MODEL
    else:
        raise ValueError(f"unknown embedding provider: {provider}")
    resolved_dimensions = dimensions or _default_dimensions(resolved_provider, resolved_model)
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
    execution_stage: str = "auto",
    selection_policy: str = "auto",
    allow_provider_quota: bool = False,
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
    require_embedding_provider_quota_allowed(
        spec.provider,
        allow_provider_quota=allow_provider_quota,
        model=spec.model,
    )
    resolved_execution_stage = _resolve_embedding_execution_stage(
        execution_stage,
        limit=limit,
    )
    resolved_selection_policy = _resolve_embedding_selection_policy(
        selection_policy,
        execution_stage=resolved_execution_stage,
    )
    selection_contract = _embedding_selection_contract(
        execution_stage=resolved_execution_stage,
        selection_policy=resolved_selection_policy,
        limit=limit,
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
            selection_policy=resolved_selection_policy,
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
        execution_stage=resolved_execution_stage,
        selection_policy=resolved_selection_policy,
        selection_contract=selection_contract,
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
    allow_provider_quota: bool = False,
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
        require_embedding_provider_quota_allowed(
            spec.provider,
            allow_provider_quota=allow_provider_quota,
            model=spec.model,
        )
        query_vector = _embedder(spec).embed_texts([query], task_type="RETRIEVAL_QUERY")[0]
        rows = _embedding_rows(conn, spec=spec, doc_type=doc_type, account=account)
        expected_rows = _embedding_document_count(conn, doc_type=doc_type, account=account)
        if expected_rows and len(rows) < expected_rows:
            raise RuntimeError(
                "semantic index is incomplete or stale for the requested scope: "
                f"{len(rows)}/{expected_rows} documents indexed for "
                f"{spec.provider}/{spec.model} dims={spec.dimensions}"
            )
    hits = _semantic_hits_from_rows(rows, query_vector=query_vector)
    hits.sort(key=lambda hit: hit.similarity, reverse=True)
    return tuple(hits[: max(1, limit)])


def load_semantic_index(
    db_path: str | Path,
    *,
    provider: str | None = None,
    model: str | None = None,
    dimensions: int | None = None,
    embedding_profile: str | None = None,
    text_template_version: str | None = None,
    api_key_env: str | None = None,
    base_url: str | None = None,
    doc_type: str | None = None,
    account: str | None = None,
) -> LoadedSemanticIndex:
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
        rows = _embedding_rows(conn, spec=spec, doc_type=doc_type, account=account)
        expected_rows = _embedding_document_count(conn, doc_type=doc_type, account=account)
        if expected_rows and len(rows) < expected_rows:
            raise RuntimeError(
                "semantic index is incomplete or stale for the requested scope: "
                f"{len(rows)}/{expected_rows} documents indexed for "
                f"{spec.provider}/{spec.model} dims={spec.dimensions}"
            )
    matrix = _semantic_matrix_from_rows(rows, dimensions=spec.dimensions)
    return LoadedSemanticIndex(
        spec=spec,
        doc_ids=tuple(str(row["doc_id"]) for row in rows),
        matrix=matrix,
    )


def semantic_search_loaded_index(
    index: LoadedSemanticIndex,
    query: str,
    *,
    limit: int = 50,
    allow_provider_quota: bool = False,
) -> tuple[SemanticHit, ...]:
    if not index.doc_ids:
        return ()
    require_embedding_provider_quota_allowed(
        index.spec.provider,
        allow_provider_quota=allow_provider_quota,
        model=index.spec.model,
    )
    query_vector = _embedder(index.spec).embed_texts([query], task_type="RETRIEVAL_QUERY")[0]
    query_array = np.asarray(query_vector[: index.spec.dimensions], dtype=np.float32)
    scores = index.matrix @ query_array
    resolved_limit = min(max(1, limit), len(index.doc_ids))
    if resolved_limit < len(index.doc_ids):
        candidate_indices = np.argpartition(scores, -resolved_limit)[-resolved_limit:]
        ranked_indices = candidate_indices[np.argsort(scores[candidate_indices])[::-1]]
    else:
        ranked_indices = np.argsort(scores)[::-1]
    return tuple(
        SemanticHit(
            doc_id=index.doc_ids[int(row_index)],
            similarity=float(scores[int(row_index)]),
            provider=index.spec.provider,
            model=index.spec.model,
            dimensions=index.spec.dimensions,
            embedding_profile=index.spec.embedding_profile,
            text_template_version=index.spec.text_template_version,
        )
        for row_index in ranked_indices
    )


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
    allow_provider_quota: bool = False,
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
        require_embedding_provider_quota_allowed(
            spec.provider,
            allow_provider_quota=allow_provider_quota,
            model=spec.model,
        )
        query_vector = _embedder(spec).embed_texts([query], task_type="RETRIEVAL_QUERY")[0]
        rows = _embedding_rows_for_doc_ids(conn, spec=spec, doc_ids=doc_ids)
        if len(rows) < len(set(doc_ids)):
            raise RuntimeError(
                "semantic index is incomplete or stale for the candidate set: "
                f"{len(rows)}/{len(set(doc_ids))} documents indexed for "
                f"{spec.provider}/{spec.model} dims={spec.dimensions}"
            )
    dimensions = spec.dimensions
    query_array = np.asarray(query_vector[:dimensions], dtype=np.float32)
    matrix = _semantic_matrix_from_rows(rows, dimensions=dimensions)
    scores = matrix @ query_array
    return {
        row["doc_id"]: SemanticScore(
            doc_id=row["doc_id"],
            similarity=float(score),
            provider=row["provider"],
            model=row["model"],
            dimensions=int(row["dimensions"]),
            embedding_profile=row["embedding_profile"],
            text_template_version=row["text_template_version"],
        )
        for row, score in zip(rows, scores, strict=True)
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


def estimate_memory_embedding_build(
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
    price_per_million_input_tokens: float | None = None,
    execution_stage: str = "auto",
    selection_policy: str = "auto",
) -> EmbeddingBuildEstimate:
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
    resolved_execution_stage = _resolve_embedding_execution_stage(
        execution_stage,
        limit=limit,
    )
    resolved_selection_policy = _resolve_embedding_selection_policy(
        selection_policy,
        execution_stage=resolved_execution_stage,
    )
    selection_contract = _embedding_selection_contract(
        execution_stage=resolved_execution_stage,
        selection_policy=resolved_selection_policy,
        limit=limit,
    )
    resolved_batch_size = max(1, batch_size)
    with sqlite3.connect(path, timeout=60) as conn:
        conn.row_factory = sqlite3.Row
        ensure_memory_schema(conn)
        documents = memory_document_count(conn)
        if documents == 0:
            raise RuntimeError("memory_documents is empty; run memory build-corpus first")
        rows = _embedding_source_rows(
            conn,
            spec=spec,
            limit=limit,
            rebuild=rebuild,
            selection_policy=resolved_selection_policy,
        )
    counts = {"missing": 0, "stale_text": 0, "stale_source": 0, "current": 0}
    input_chars = 0
    input_tokens = 0
    for row in rows:
        status = _coverage_status(row)
        counts[status] += 1
        text = _embedding_text(row)
        input_chars += len(text)
        input_tokens += _rough_input_token_count(text)
    selected = len(rows)
    estimated_cost = None
    if price_per_million_input_tokens is not None:
        estimated_cost = (input_tokens / 1_000_000) * price_per_million_input_tokens
    return EmbeddingBuildEstimate(
        db_path=str(path),
        provider=spec.provider,
        model=spec.model,
        dimensions=spec.dimensions,
        embedding_profile=spec.embedding_profile,
        text_template_version=spec.text_template_version,
        documents=documents,
        selected=selected,
        missing=counts["missing"],
        stale_text=counts["stale_text"],
        stale_source=counts["stale_source"],
        current=counts["current"],
        estimated_input_chars=input_chars,
        estimated_input_tokens=input_tokens,
        batch_size=resolved_batch_size,
        estimated_batches=math.ceil(selected / resolved_batch_size) if selected else 0,
        price_per_million_input_tokens=price_per_million_input_tokens,
        estimated_input_cost=estimated_cost,
        execution_stage=resolved_execution_stage,
        selection_policy=resolved_selection_policy,
        selection_contract=selection_contract,
    )


def embedding_estimate_json(estimate: EmbeddingBuildEstimate) -> str:
    return json.dumps(asdict(estimate), ensure_ascii=False, indent=2, sort_keys=True)


def format_embedding_estimate(estimate: EmbeddingBuildEstimate) -> str:
    lines = [
        f"db: {estimate.db_path}",
        (
            "spec: "
            f"{estimate.provider}/{estimate.model} dims={estimate.dimensions} "
            f"profile={estimate.embedding_profile} template={estimate.text_template_version}"
        ),
        (
            "documents: "
            f"{estimate.documents} selected={estimate.selected} "
            f"missing={estimate.missing} stale_text={estimate.stale_text} "
            f"stale_source={estimate.stale_source} current={estimate.current}"
        ),
        (
            "input estimate: "
            f"chars={estimate.estimated_input_chars} "
            f"tokens~={estimate.estimated_input_tokens}"
        ),
        (
            "api batches: "
            f"batch_size={estimate.batch_size} estimated_batches={estimate.estimated_batches}"
        ),
        (
            "execution: "
            f"stage={estimate.execution_stage} selection_policy={estimate.selection_policy}"
        ),
        f"selection contract: {estimate.selection_contract}",
    ]
    if estimate.estimated_input_cost is None:
        lines.append("estimated input cost: unknown")
    else:
        lines.append(
            "estimated input cost: "
            f"{estimate.estimated_input_cost:.6f} "
            f"@ {estimate.price_per_million_input_tokens}/1M input tokens"
        )
    return "\n".join(lines)


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


class _LocalHashEmbedder:
    def __init__(self, spec: EmbeddingSpec) -> None:
        self.spec = spec

    def embed_texts(self, texts: list[str], *, task_type: str) -> list[list[float]]:
        return [_local_hash_embedding(text, dimensions=self.spec.dimensions) for text in texts]


def _embedding_provider_request(
    *,
    spec: EmbeddingSpec,
    api_key: str,
    texts: list[str],
    task_type: str,
) -> dict[str, Any]:
    if spec.provider == OPENAI_PROVIDER:
        payload: dict[str, Any] = {
            "model": spec.model,
            "input": texts,
            "encoding_format": "float",
        }
        if spec.dimensions:
            payload["dimensions"] = spec.dimensions
        url = spec.base_url or "https://api.openai.com/v1/embeddings"
        headers = {"Authorization": f"Bearer {api_key}"}
    elif spec.provider == OPENAI_COMPATIBLE_PROVIDER:
        if not spec.base_url:
            raise RuntimeError(
                "openai_compatible embeddings require --base-url or "
                f"{OPENAI_COMPATIBLE_BASE_URL_ENV}"
            )
        payload = {
            "model": spec.model,
            "input": texts,
            "encoding_format": "float",
        }
        if spec.dimensions:
            payload["dimensions"] = spec.dimensions
        url = spec.base_url
        headers = {"Authorization": f"Bearer {api_key}"}
    elif spec.provider == GEMINI_PROVIDER:
        model_name = _gemini_model_name(spec.model)
        requests = []
        for text in texts:
            config: dict[str, Any] = {}
            if spec.dimensions:
                config["outputDimensionality"] = spec.dimensions
            if not _is_gemini_embedding_2(spec.model):
                config["taskType"] = task_type
            request: dict[str, Any] = {
                "model": model_name,
                "content": {
                    "parts": [
                        {
                            "text": _gemini_content_text(
                                text,
                                model=spec.model,
                                embedding_profile=spec.embedding_profile,
                                task_type=task_type,
                            )
                        }
                    ]
                },
            }
            if config:
                request["embedContentConfig"] = config
            requests.append(request)
        payload = {"requests": requests}
        url = (
            spec.base_url
            or f"https://generativelanguage.googleapis.com/v1beta/{model_name}:batchEmbedContents"
        )
        headers = {"x-goog-api-key": api_key}
    elif spec.provider == VOYAGE_PROVIDER:
        payload = {
            "model": spec.model,
            "input": texts,
            "input_type": _voyage_input_type(task_type),
            "truncation": True,
            "output_dtype": "float",
        }
        if spec.dimensions:
            payload["output_dimension"] = spec.dimensions
        url = spec.base_url or "https://api.voyageai.com/v1/embeddings"
        headers = {"Authorization": f"Bearer {api_key}"}
    elif spec.provider == COHERE_PROVIDER:
        payload = {
            "model": spec.model,
            "texts": texts,
            "input_type": _cohere_input_type(task_type),
            "embedding_types": ["float"],
            "truncate": "END",
        }
        if spec.dimensions:
            payload["output_dimension"] = spec.dimensions
        url = spec.base_url or "https://api.cohere.com/v2/embed"
        headers = {"Authorization": f"Bearer {api_key}"}
    elif spec.provider == MISTRAL_PROVIDER:
        payload = {
            "model": spec.model,
            "input": texts,
            "encoding_format": "float",
        }
        url = spec.base_url or "https://api.mistral.ai/v1/embeddings"
        headers = {"Authorization": f"Bearer {api_key}"}
    elif spec.provider == JINA_PROVIDER:
        payload = {
            "model": spec.model,
            "input": texts,
            "task": _jina_task(task_type),
            "embedding_type": "float",
            "normalized": True,
            "truncate": True,
        }
        if spec.dimensions:
            payload["dimensions"] = spec.dimensions
        url = spec.base_url or "https://api.jina.ai/v1/embeddings"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "User-Agent": "research-x/0.1 (+https://github.com/masanori64/research_x)",
        }
    else:
        raise RuntimeError(f"provider has no remote embedding request shape: {spec.provider}")
    return {
        "url": url,
        "payload": payload,
        "headers": headers,
        "timeout_seconds": spec.timeout_seconds,
        "request_shape_only": True,
        "provider_quality_proof": False,
    }


class _OpenAIEmbedder:
    def __init__(self, spec: EmbeddingSpec) -> None:
        self.spec = spec
        self.api_key = _api_key(spec.api_key_env or "OPENAI_API_KEY")

    def embed_texts(self, texts: list[str], *, task_type: str) -> list[list[float]]:
        request = _embedding_provider_request(
            spec=self.spec,
            api_key=self.api_key,
            texts=texts,
            task_type=task_type,
        )
        response = _post_json_budgeted(
            request["url"],
            request["payload"],
            headers=request["headers"],
            timeout_seconds=request["timeout_seconds"],
            budget_provider=self.spec.provider,
            budget_model=self.spec.model,
            budget_operation="embedding",
            budget_units=_embedding_api_units(texts, retries=3),
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


class _OpenAICompatibleEmbedder:
    def __init__(self, spec: EmbeddingSpec) -> None:
        self.spec = spec
        if not spec.base_url:
            raise RuntimeError(
                "openai_compatible embeddings require --base-url or "
                f"{OPENAI_COMPATIBLE_BASE_URL_ENV}"
            )
        self.api_key = _api_key(spec.api_key_env or "OPENAI_COMPATIBLE_API_KEY")

    def embed_texts(self, texts: list[str], *, task_type: str) -> list[list[float]]:
        request = _embedding_provider_request(
            spec=self.spec,
            api_key=self.api_key,
            texts=texts,
            task_type=task_type,
        )
        response = _post_json_budgeted(
            request["url"],
            request["payload"],
            headers=request["headers"],
            timeout_seconds=request["timeout_seconds"],
            budget_provider=self.spec.provider,
            budget_model=self.spec.model,
            budget_operation="embedding",
            budget_units=_embedding_api_units(texts, retries=3),
        )
        data = response.get("data")
        if not isinstance(data, list):
            raise RuntimeError(f"OpenAI-compatible embeddings response missing data: {response}")
        vectors = []
        for item in sorted(data, key=lambda row: int(row.get("index", 0))):
            vector = item.get("embedding")
            if not isinstance(vector, list):
                raise RuntimeError(
                    f"OpenAI-compatible embeddings response missing embedding: {item}"
                )
            vectors.append(_normalize_vector([float(value) for value in vector]))
        return vectors


class _GeminiEmbedder:
    def __init__(self, spec: EmbeddingSpec) -> None:
        self.spec = spec
        self.api_key = _api_key(spec.api_key_env or "GEMINI_API_KEY")

    def embed_texts(self, texts: list[str], *, task_type: str) -> list[list[float]]:
        request = _embedding_provider_request(
            spec=self.spec,
            api_key=self.api_key,
            texts=texts,
            task_type=task_type,
        )
        response = _post_json_budgeted(
            request["url"],
            request["payload"],
            headers=request["headers"],
            timeout_seconds=request["timeout_seconds"],
            budget_provider=self.spec.provider,
            budget_model=self.spec.model,
            budget_operation="embedding",
            budget_units=_embedding_api_units(texts, retries=3),
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


class _VoyageEmbedder:
    def __init__(self, spec: EmbeddingSpec) -> None:
        self.spec = spec
        self.api_key = _api_key(spec.api_key_env or "VOYAGE_API_KEY")

    def embed_texts(self, texts: list[str], *, task_type: str) -> list[list[float]]:
        request = _embedding_provider_request(
            spec=self.spec,
            api_key=self.api_key,
            texts=texts,
            task_type=task_type,
        )
        response = _post_json_budgeted(
            request["url"],
            request["payload"],
            headers=request["headers"],
            timeout_seconds=request["timeout_seconds"],
            budget_provider=self.spec.provider,
            budget_model=self.spec.model,
            budget_operation="embedding",
            budget_units=_embedding_api_units(texts, retries=3),
        )
        return _embedding_vectors_from_data_response(response, "Voyage")


class _CohereEmbedder:
    def __init__(self, spec: EmbeddingSpec) -> None:
        self.spec = spec
        self.api_key = _api_key(spec.api_key_env or "COHERE_API_KEY")

    def embed_texts(self, texts: list[str], *, task_type: str) -> list[list[float]]:
        request = _embedding_provider_request(
            spec=self.spec,
            api_key=self.api_key,
            texts=texts,
            task_type=task_type,
        )
        response = _post_json_budgeted(
            request["url"],
            request["payload"],
            headers=request["headers"],
            timeout_seconds=request["timeout_seconds"],
            budget_provider=self.spec.provider,
            budget_model=self.spec.model,
            budget_operation="embedding",
            budget_units=_embedding_api_units(texts, retries=3),
        )
        embeddings_value = response.get("embeddings")
        if isinstance(embeddings_value, dict):
            vectors = embeddings_value.get("float")
        else:
            vectors = embeddings_value
        return _embedding_vectors_from_sequence(vectors, "Cohere")


class _MistralEmbedder:
    def __init__(self, spec: EmbeddingSpec) -> None:
        self.spec = spec
        self.api_key = _api_key(spec.api_key_env or "MISTRAL_API_KEY")

    def embed_texts(self, texts: list[str], *, task_type: str) -> list[list[float]]:
        request = _embedding_provider_request(
            spec=self.spec,
            api_key=self.api_key,
            texts=texts,
            task_type=task_type,
        )
        response = _post_json_budgeted(
            request["url"],
            request["payload"],
            headers=request["headers"],
            timeout_seconds=request["timeout_seconds"],
            budget_provider=self.spec.provider,
            budget_model=self.spec.model,
            budget_operation="embedding",
            budget_units=_embedding_api_units(texts, retries=3),
        )
        return _embedding_vectors_from_data_response(response, "Mistral")


class _JinaEmbedder:
    def __init__(self, spec: EmbeddingSpec) -> None:
        self.spec = spec
        self.api_key = _api_key(spec.api_key_env or "JINA_API_KEY")

    def embed_texts(self, texts: list[str], *, task_type: str) -> list[list[float]]:
        request = _embedding_provider_request(
            spec=self.spec,
            api_key=self.api_key,
            texts=texts,
            task_type=task_type,
        )
        response = _post_json_budgeted(
            request["url"],
            request["payload"],
            headers=request["headers"],
            timeout_seconds=request["timeout_seconds"],
            budget_provider=self.spec.provider,
            budget_model=self.spec.model,
            budget_operation="embedding",
            budget_units=_embedding_api_units(texts, retries=3),
        )
        return _embedding_vectors_from_data_response(response, "Jina")


def _embedder(spec: EmbeddingSpec):
    if spec.provider == LOCAL_HASH_PROVIDER:
        return _LocalHashEmbedder(spec)
    if spec.provider == OPENAI_PROVIDER:
        return _OpenAIEmbedder(spec)
    if spec.provider == OPENAI_COMPATIBLE_PROVIDER:
        return _OpenAICompatibleEmbedder(spec)
    if spec.provider == GEMINI_PROVIDER:
        return _GeminiEmbedder(spec)
    if spec.provider == VOYAGE_PROVIDER:
        return _VoyageEmbedder(spec)
    if spec.provider == COHERE_PROVIDER:
        return _CohereEmbedder(spec)
    if spec.provider == MISTRAL_PROVIDER:
        return _MistralEmbedder(spec)
    if spec.provider == JINA_PROVIDER:
        return _JinaEmbedder(spec)
    raise ValueError(f"unknown embedding provider: {spec.provider}")


def _embedding_source_rows(
    conn: sqlite3.Connection,
    *,
    spec: EmbeddingSpec,
    limit: int | None,
    rebuild: bool,
    selection_policy: str,
) -> list[sqlite3.Row]:
    sql = """
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
        ORDER BY d.observed_at DESC, d.doc_id
    """
    params: list[Any] = [
        spec.provider,
        spec.model,
        spec.dimensions,
        spec.embedding_profile,
        spec.text_template_version,
    ]
    rows = conn.execute(sql, params).fetchall()
    if not rebuild:
        rows = [
            row
            for row in rows
            if (
                row["embedded_text_hash"] != _text_hash(_embedding_text(row))
                or row["source_doc_hash"] != _source_doc_hash(row)
            )
        ]
    return _select_embedding_rows(rows, limit=limit, selection_policy=selection_policy)


def _resolve_embedding_execution_stage(stage: str, *, limit: int | None) -> str:
    normalized = _clean_id(stage).replace("-", "_") or "auto"
    if normalized not in EMBEDDING_EXECUTION_STAGES:
        raise ValueError(
            "embedding execution stage must be one of: "
            + ", ".join(EMBEDDING_EXECUTION_STAGES)
        )
    if normalized == "auto":
        return "technical_canary" if limit is not None else "production_scope"
    if normalized == "production_scope" and limit is not None:
        raise ValueError(
            "production_scope embedding builds must not use --limit; use "
            "technical_canary or eval_slice for limited preflight work"
        )
    if normalized in {"technical_canary", "eval_slice"} and limit is None:
        raise ValueError(f"{normalized} embedding stage requires --limit")
    return normalized


def _resolve_embedding_selection_policy(policy: str, *, execution_stage: str) -> str:
    normalized = _clean_id(policy).replace("-", "_") or "auto"
    if normalized not in EMBEDDING_SELECTION_POLICIES:
        raise ValueError(
            "embedding selection policy must be one of: "
            + ", ".join(EMBEDDING_SELECTION_POLICIES)
        )
    if normalized == "auto":
        return "doc_type_round_robin" if execution_stage == "eval_slice" else "sequential"
    return normalized


def _embedding_selection_contract(
    *,
    execution_stage: str,
    selection_policy: str,
    limit: int | None,
) -> str:
    if execution_stage == "technical_canary":
        return (
            "limited technical canary: verifies provider payload, dimensions, DB writes, "
            "coverage, and budget guard only; not a production index"
        )
    if execution_stage == "eval_slice":
        return (
            "limited evaluation slice: compares provider/profile behavior on a stable "
            f"{selection_policy} sample; adopted arms still require full selected-scope coverage"
        )
    return (
        "production scope: selected provider/profile is expected to cover the full selected "
        "document scope"
        if limit is None
        else "invalid limited production scope"
    )


def _select_embedding_rows(
    rows: list[sqlite3.Row],
    *,
    limit: int | None,
    selection_policy: str,
) -> list[sqlite3.Row]:
    if limit is None or limit <= 0 or len(rows) <= limit:
        return rows
    if selection_policy == "sequential":
        return rows[:limit]
    if selection_policy == "doc_type_round_robin":
        grouped: dict[str, list[sqlite3.Row]] = {}
        for row in rows:
            grouped.setdefault(str(row["doc_type"]), []).append(row)
        selected: list[sqlite3.Row] = []
        doc_types = sorted(grouped)
        index = 0
        while len(selected) < limit and grouped:
            doc_type = doc_types[index % len(doc_types)]
            bucket = grouped.get(doc_type)
            if bucket:
                selected.append(bucket.pop(0))
                if not bucket:
                    grouped.pop(doc_type, None)
                    doc_types = sorted(grouped)
                    index = 0
                    continue
            index += 1
        return selected
    raise ValueError(f"unknown embedding selection policy: {selection_policy}")


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
            e.embedding_profile, e.text_template_version, e.embedding,
            e.source_doc_hash, e.embedded_text_hash
        FROM memory_embeddings e
        JOIN memory_documents d ON d.doc_id = e.doc_id
        WHERE e.provider = ?
          AND e.model = ?
          AND e.dimensions = ?
          AND e.embedding_profile = ?
          AND e.text_template_version = ?
          AND e.source_doc_hash = d.source_doc_hash
          AND e.embedded_text_hash = d.embedding_text_hash
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
        JOIN memory_documents d ON d.doc_id = e.doc_id
        WHERE e.provider = ?
          AND e.model = ?
          AND e.dimensions = ?
          AND e.embedding_profile = ?
          AND e.text_template_version = ?
          AND e.source_doc_hash = d.source_doc_hash
          AND e.embedded_text_hash = d.embedding_text_hash
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
        matrix = _semantic_matrix_from_rows(batch, dimensions=dimensions)
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


def _semantic_matrix_from_rows(rows: list[sqlite3.Row], *, dimensions: int):
    if not rows:
        return np.empty((0, dimensions), dtype=np.float32)
    blobs = b"".join(row["embedding"] for row in rows)
    return np.frombuffer(blobs, dtype="<f4").reshape(len(rows), dimensions).copy()


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
            available_spec = _matching_available_spec(
                conn,
                provider=spec.provider,
                model=model,
                dimensions=dimensions,
                embedding_profile=spec.embedding_profile,
                text_template_version=spec.text_template_version,
                api_key_env=api_key_env,
                base_url=base_url,
            )
            if available_spec and (
                dimensions is None or available_spec.dimensions == dimensions
            ):
                return available_spec
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
            "Build a production embedding index with OpenAI, Gemini, Voyage, Cohere, "
            "Mistral, Jina, or OpenAI-compatible, "
            "or explicitly pass --semantic-provider local_hash for diagnostic searches."
        )
    raise RuntimeError(
        "no production memory embeddings found; run "
        "`research_x memory build-embeddings --provider gemini` or "
        "`research_x memory build-embeddings --provider openai` or "
        "`research_x memory build-embeddings --provider voyage` or "
        "`research_x memory build-embeddings --provider cohere` or "
        "`research_x memory build-embeddings --provider mistral` or "
        "`research_x memory build-embeddings --provider jina` or "
        "`research_x memory build-embeddings --provider openai_compatible --base-url ...` first"
    )


def _matching_available_spec(
    conn: sqlite3.Connection,
    *,
    provider: str,
    model: str | None,
    dimensions: int | None,
    embedding_profile: str,
    text_template_version: str,
    api_key_env: str | None,
    base_url: str | None,
) -> EmbeddingSpec | None:
    filters = [
        "provider = ?",
        "embedding_profile = ?",
        "text_template_version = ?",
    ]
    params: list[Any] = [provider, embedding_profile, text_template_version]
    if model:
        filters.append("model = ?")
        params.append(model)
    if dimensions:
        filters.append("dimensions = ?")
        params.append(dimensions)
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
    if not row:
        return None
    return resolve_embedding_spec(
        provider=row["provider"],
        model=row["model"],
        dimensions=int(row["dimensions"]),
        embedding_profile=row["embedding_profile"],
        text_template_version=row["text_template_version"],
        api_key_env=api_key_env,
        base_url=base_url,
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
                CASE
                  WHEN provider IN (
                    'gemini', 'openai', 'voyage', 'cohere',
                    'mistral', 'jina', 'openai_compatible'
                  ) THEN 0
                  ELSE 1
                END,
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
    return memory_document_embedding_text(row)


def _source_doc_hash(row: sqlite3.Row) -> str:
    return memory_document_source_hash(row)


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
    return text_hash(text)


def _rough_input_token_count(text: str) -> int:
    if not text:
        return 0
    return max(1, math.ceil(len(text) / 2))


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


def _embedding_vectors_from_data_response(
    response: dict[str, Any],
    provider_name: str,
) -> list[list[float]]:
    data = response.get("data")
    if not isinstance(data, list):
        raise RuntimeError(f"{provider_name} embeddings response missing data: {response}")
    vectors = []
    for item in sorted(data, key=_embedding_data_index):
        if not isinstance(item, dict):
            raise RuntimeError(f"{provider_name} embeddings response item is invalid: {item}")
        vectors.append(_embedding_vector_from_value(item.get("embedding"), provider_name))
    return vectors


def _embedding_vectors_from_sequence(value: Any, provider_name: str) -> list[list[float]]:
    if not isinstance(value, list):
        raise RuntimeError(f"{provider_name} embeddings response missing vectors: {value}")
    return [_embedding_vector_from_value(vector, provider_name) for vector in value]


def _embedding_vector_from_value(value: Any, provider_name: str) -> list[float]:
    if not isinstance(value, list):
        raise RuntimeError(f"{provider_name} embeddings response missing embedding: {value}")
    return _normalize_vector([float(item) for item in value])


def _embedding_data_index(value: Any) -> int:
    if not isinstance(value, dict):
        return 0
    try:
        return int(value.get("index", 0))
    except (TypeError, ValueError):
        return 0


def _voyage_input_type(task_type: str) -> str:
    return "query" if task_type == "RETRIEVAL_QUERY" else "document"


def _cohere_input_type(task_type: str) -> str:
    return "search_query" if task_type == "RETRIEVAL_QUERY" else "search_document"


def _jina_task(task_type: str) -> str:
    return "retrieval.query" if task_type == "RETRIEVAL_QUERY" else "retrieval.passage"


def _default_dimensions(provider: str, model: str) -> int:
    if provider == OPENAI_PROVIDER and model == "text-embedding-3-large":
        return 3072
    if provider == JINA_PROVIDER and model == "jina-embeddings-v4":
        return 2048
    return DEFAULT_DIMENSIONS[provider]


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
    if os.environ.get("VOYAGE_API_KEY"):
        return VOYAGE_PROVIDER
    if os.environ.get("COHERE_API_KEY"):
        return COHERE_PROVIDER
    if os.environ.get("MISTRAL_API_KEY"):
        return MISTRAL_PROVIDER
    if os.environ.get("JINA_API_KEY"):
        return JINA_PROVIDER
    if os.environ.get("OPENAI_COMPATIBLE_API_KEY") and os.environ.get(
        OPENAI_COMPATIBLE_BASE_URL_ENV
    ):
        return OPENAI_COMPATIBLE_PROVIDER
    raise RuntimeError(
        "no production embedding API key found. Set GEMINI_API_KEY, OPENAI_API_KEY, "
        "VOYAGE_API_KEY, COHERE_API_KEY, MISTRAL_API_KEY, JINA_API_KEY, or "
        f"OPENAI_COMPATIBLE_API_KEY plus {OPENAI_COMPATIBLE_BASE_URL_ENV}, "
        "or explicitly pass --provider local_hash for an offline diagnostic index."
    )


def _post_json(
    url: str,
    payload: dict[str, Any],
    *,
    headers: dict[str, str],
    timeout_seconds: float,
    retries: int = 3,
    budget_provider: str | None = None,
    budget_model: str | None = None,
    budget_operation: str = "embedding",
    budget_units: dict[str, int | float] | None = None,
) -> dict[str, Any]:
    def send() -> dict[str, Any]:
        return _post_json_unbudgeted(
            url,
            payload,
            headers=headers,
            timeout_seconds=timeout_seconds,
            retries=retries,
        )

    if budget_provider is None and budget_model is None and budget_units is None:
        return send()
    with budgeted_api_call(
        provider=budget_provider or "unknown",
        model=budget_model or str(payload.get("model") or "unknown"),
        provider_role="embedding",
        operation=budget_operation,
        units=budget_units or api_units(calls=retries, retries=max(0, retries - 1)),
        request_payload=payload,
        metadata={"url": url, "max_attempts": retries},
    ):
        return send()


def _post_json_budgeted(
    url: str,
    payload: dict[str, Any],
    *,
    headers: dict[str, str],
    timeout_seconds: float,
    retries: int = 3,
    budget_provider: str,
    budget_model: str,
    budget_operation: str = "embedding",
    budget_units: dict[str, int | float] | None = None,
) -> dict[str, Any]:
    with budgeted_api_call(
        provider=budget_provider,
        model=budget_model,
        provider_role="embedding",
        operation=budget_operation,
        units=budget_units or api_units(calls=retries, retries=max(0, retries - 1)),
        request_payload=payload,
        metadata={"url": url, "max_attempts": retries},
    ):
        return _post_json(
            url,
            payload,
            headers=headers,
            timeout_seconds=timeout_seconds,
            retries=retries,
        )


def _post_json_unbudgeted(
    url: str,
    payload: dict[str, Any],
    *,
    headers: dict[str, str],
    timeout_seconds: float,
    retries: int = 3,
) -> dict[str, Any]:
    require_provider_transport_send_allowed(url)
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        headers={
            "Content-Type": "application/json",
            "User-Agent": "research-x/0.1 (+https://github.com/masanori64/research_x)",
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
        time.sleep(_retry_sleep_seconds(last_error, attempt=attempt))
    raise RuntimeError(f"embedding API failed: {last_error}")


def _embedding_api_units(texts: list[str], *, retries: int) -> dict[str, int | float]:
    return api_units(
        calls=retries,
        retries=max(0, retries - 1),
        input_tokens=sum(rough_text_tokens(text) for text in texts),
        documents=len(texts),
    )


def _retry_sleep_seconds(error: Exception | None, *, attempt: int) -> float:
    if isinstance(error, urllib.error.HTTPError):
        retry_after = error.headers.get("Retry-After") if error.headers else None
        if retry_after:
            try:
                return max(0.0, min(float(retry_after), 300.0))
            except ValueError:
                pass
    return float(min(2**attempt, 30))


def _gemini_model_name(model: str) -> str:
    return model if model.startswith("models/") else f"models/{model}"


def _is_gemini_embedding_2(model: str) -> bool:
    return model.removeprefix("models/") == "gemini-embedding-2"


def _gemini_content_text(
    text: str,
    *,
    model: str,
    embedding_profile: str,
    task_type: str,
) -> str:
    if not _is_gemini_embedding_2(model):
        return text
    if task_type == "RETRIEVAL_QUERY":
        return f"task: {_gemini_query_task(embedding_profile)} | query: {text}"
    return f"task: {_gemini_document_task(embedding_profile)} | document: {text}"


def _gemini_query_task(embedding_profile: str) -> str:
    if embedding_profile == "general_memory":
        return "question answering"
    if embedding_profile == "code_technical":
        return "code retrieval"
    return "search result"


def _gemini_document_task(embedding_profile: str) -> str:
    if embedding_profile == "code_technical":
        return "code retrieval"
    return "search result"


def _chunks(rows: list[sqlite3.Row], size: int):
    for index in range(0, len(rows), size):
        yield rows[index : index + size]


def _utc_now() -> str:
    return datetime.now(tz=UTC).isoformat()
