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
from collections import Counter
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
    memory_document_embedding_text_hash,
    memory_document_source_hash,
    text_hash,
)
from research_x.memory.embedding_input import (
    DEFAULT_CLASSIFICATION_VERSION,
    DEFAULT_PROJECTION_POLICY_VERSION,
    PROFILE_TARGET_SPACE,
)
from research_x.memory.embedding_spaces import (
    embedding_space_id_for_identity,
    ensure_embedding_space_for_spec,
)
from research_x.memory.schema import ensure_memory_schema, memory_document_count

LOCAL_HASH_PROVIDER = "local_hash"
LOCAL_HASH_MODEL = "local-hash-v1"
TEXT_EMBEDDING_PROVIDER_ROLE = "text_embedding"
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
    "semantic embedding provider API use requires ProviderExecutionPolicy, budget preflight, "
    "and the paid/quota report pause. Non-local embedding providers remain candidate-only "
    "until approved; use provider=local_hash for diagnostic wiring or pass "
    "allow_provider_quota=True with scoped ProviderExecutionPolicy and API Budget Guard preflight."
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
    space_id: str
    generation_id: str | None
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
    eligible: int
    ineligible: int
    skip_reasons: dict[str, int]
    uses_projection_rows: bool = False
    projection_profile: str | None = None
    target_space_id: str | None = None
    classification_version: str | None = None
    projection_policy_version: str | None = None
    provider_requests_made: int = 0


@dataclass(frozen=True)
class EmbeddingCoverageRow:
    doc_type: str
    documents: int
    current: int
    missing: int
    stale_text: int
    stale_source: int
    ineligible: int


@dataclass(frozen=True)
class EmbeddingCoverageReport:
    db_path: str
    space_id: str
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
    eligible: int
    ineligible: int
    skip_reasons: dict[str, int]
    by_doc_type: tuple[EmbeddingCoverageRow, ...]


@dataclass(frozen=True)
class EmbeddingBuildEstimate:
    db_path: str
    space_id: str
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
    eligible: int
    ineligible: int
    skip_reasons: dict[str, int]
    estimated_input_chars: int
    estimated_input_tokens: int
    batch_size: int
    estimated_batches: int
    price_per_million_input_tokens: float | None = None
    estimated_input_cost: float | None = None
    execution_stage: str = "production_scope"
    selection_policy: str = "sequential"
    selection_contract: str = ""
    uses_projection_rows: bool = False
    projection_profile: str | None = None
    target_space_id: str | None = None
    classification_version: str | None = None
    projection_policy_version: str | None = None
    eligible_documents: int = 0
    eligible_projections: int = 0
    selected_projections: int = 0
    skipped_stale_projections: int = 0
    skipped_missing_restoration: int = 0
    provider_requests_made: int = 0


@dataclass(frozen=True)
class SemanticHit:
    doc_id: str
    similarity: float
    space_id: str | None
    provider: str
    model: str
    dimensions: int
    embedding_profile: str
    text_template_version: str
    source_doc_hash: str | None = None
    embedded_text_hash: str | None = None
    generated_at: str | None = None
    stale_status: str = "current"
    projection_generation_id: str | None = None
    projection_hash: str | None = None
    projection_status: str | None = None


@dataclass(frozen=True)
class SemanticScore:
    doc_id: str
    similarity: float
    space_id: str | None
    provider: str
    model: str
    dimensions: int
    embedding_profile: str
    text_template_version: str
    source_doc_hash: str | None = None
    embedded_text_hash: str | None = None
    generated_at: str | None = None
    stale_status: str = "current"
    projection_generation_id: str | None = None
    projection_hash: str | None = None
    projection_status: str | None = None


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
            "provider_policy_required"
            if provider_gated
            else "diagnostic_local_hash_only"
        ),
        "provider_policy": (
            "provider_policy_controlled"
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
        provider_role=TEXT_EMBEDDING_PROVIDER_ROLE,
    )


def _normalize_provider_for_policy(provider: str | None) -> str:
    return (provider or "").strip().lower().replace("-", "_") or "auto"


@dataclass(frozen=True)
class LoadedSemanticIndex:
    spec: EmbeddingSpec
    space_id: str | None
    doc_ids: tuple[str, ...]
    matrix: Any


EmbeddingInputRow = sqlite3.Row | dict[str, Any]


@dataclass(frozen=True)
class _EmbeddingProjectionSelection:
    rows: list[EmbeddingInputRow]
    source_count: int
    eligible_count: int
    ineligible_count: int
    skip_reasons: dict[str, int]


_TEXT_PROJECTION_BUILDER_VERSION = "typed-text-projection-v1"
_CLASSIFICATION_COLUMNS = (
    "source_kind",
    "source_subkind",
    "language",
    "modality",
    "relation_type",
    "account_scope",
    "privacy_class",
    "retention_class",
    "embedding_eligibility",
)
_JP_RE = re.compile(r"[\u3040-\u30ff\u3400-\u9fff]")
_ASCII_WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9_+-]*")
_DATE_RE = re.compile(
    r"\b(?:20\d{2}|19\d{2})[-/年](?:0?[1-9]|1[0-2])(?:[-/月](?:0?[1-9]|[12]\d|3[01])日?)?\b"
)
_TECHNICAL_RE = re.compile(
    r"(```|`[^`]+`|\b(?:api|sdk|cli|http|json|sqlite|python|typescript|"
    r"javascript|docker|pytest|ruff|uv|github|repository|package|provider|"
    r"model|embedding|rerank|ocr|traceback|exception|error|stack|npm|pip|cargo|"
    r"gemini|openai|voyage|cohere|mistral|jina)\b|[A-Za-z_][\w.:-]+\(\)|"
    r"--[A-Za-z0-9][\w-]*|[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)",
    re.IGNORECASE,
)
_COMMAND_OR_ERROR_RE = re.compile(
    r"(^|\n)\s*(?:uv|python|pytest|ruff|git|gh|npm|pnpm|yarn|docker|cargo)\b.*"
    r"|\b(?:Traceback|Exception|Error|HTTP\s+\d{3})\b",
    re.IGNORECASE,
)
_SECRET_ASSIGNMENT_RE = re.compile(
    r"(?i)\b(api[_-]?key|access[_-]?token|secret|password|bearer)\b"
    r"(\s*[:=]\s*)([^\s,;]+)"
)
_ELIGIBLE_VALUES = {"", "eligible", "true", "yes", "allow", "allowed", "embed"}
_INELIGIBLE_VALUES = {
    "skip",
    "ineligible",
    "false",
    "no",
    "deny",
    "denied",
    "do_not_embed",
    "not_allowed",
}


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
    space_id: str | None = None,
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
    projection_profile: str | None = None,
    classification_version: str | None = None,
    projection_policy_version: str | None = None,
    require_projections: bool = False,
) -> EmbeddingBuildSummary:
    path = Path(db_path)
    if not path.exists():
        raise FileNotFoundError(f"database not found: {path}")
    spec = (
        _resolve_spec_from_db_space_id(
            path,
            space_id=space_id,
            provider=provider,
            model=model,
            dimensions=dimensions,
            embedding_profile=embedding_profile,
            text_template_version=text_template_version,
            api_key_env=api_key_env,
            base_url=base_url,
        )
        if space_id
        else resolve_embedding_spec(
            provider=provider,
            model=model,
            dimensions=dimensions,
            embedding_profile=embedding_profile,
            text_template_version=text_template_version,
            api_key_env=api_key_env,
            base_url=base_url,
        )
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
    uses_projection_rows = bool(
        require_projections
        or projection_profile
        or classification_version
        or projection_policy_version
    )
    if (
        not uses_projection_rows
        and execution_stage != "auto"
        and resolved_execution_stage in {"eval_slice", "production_scope"}
    ):
        raise RuntimeError(
            "eval_slice and production_scope embedding builds require "
            "memory_embedding_projections; pass --require-projections with "
            "--classification-version and --projection-policy-version"
        )
    resolved_batch_size = max(1, batch_size)
    selected = 0
    embedded = 0
    skipped = 0
    requested_space_id = space_id
    space_id = requested_space_id or _space_id_for_spec(spec)
    generation_id: str | None = None
    with sqlite3.connect(path, timeout=60) as conn:
        conn.row_factory = sqlite3.Row
        ensure_memory_schema(conn)
        documents = memory_document_count(conn)
        if documents == 0:
            raise RuntimeError("memory_documents is empty; run memory build-corpus first")
        if requested_space_id:
            space_id = requested_space_id
        else:
            space_defaults = _text_space_defaults_for_profile(spec.embedding_profile)
            space_id = ensure_embedding_space_for_spec(
                conn,
                provider=spec.provider,
                model=spec.model,
                dimensions=spec.dimensions,
                embedding_profile=spec.embedding_profile,
                text_template_version=spec.text_template_version,
                modality="text",
                document_scope=space_defaults["document_scope"],
                source_kind_filter=space_defaults["source_kind_filter"],
                language_filter=space_defaults["language_filter"],
                storage_rights_policy=space_defaults["storage_rights_policy"],
                provider_role=TEXT_EMBEDDING_PROVIDER_ROLE,
                status="active",
                notes="Text embedding space used by memory build-embeddings.",
            )
        if uses_projection_rows:
            selection = _stored_embedding_projection_selection(
                conn,
                spec=spec,
                space_id=space_id,
                projection_profile=projection_profile or spec.embedding_profile,
                classification_version=classification_version
                or DEFAULT_CLASSIFICATION_VERSION,
                projection_policy_version=projection_policy_version
                or DEFAULT_PROJECTION_POLICY_VERSION,
                limit=limit,
                rebuild=rebuild,
                selection_policy=resolved_selection_policy,
            )
            if require_projections and not selection.eligible_count:
                raise RuntimeError(
                    "required memory_embedding_projections are missing for "
                    f"profile={projection_profile or spec.embedding_profile} "
                    f"space_id={space_id}"
                )
        else:
            selection = _embedding_projection_selection(
                conn,
                spec=spec,
                space_id=space_id,
                limit=limit,
                rebuild=rebuild,
                selection_policy=resolved_selection_policy,
            )
        rows = selection.rows
        selected = len(rows)
        if rows:
            generation_id = _store_embedding_projection_generation(
                conn,
                space_id=space_id,
                spec=spec,
                execution_stage=resolved_execution_stage,
                selection_policy=resolved_selection_policy,
                source_count=selection.source_count,
                projected_count=selected,
                skipped_count=max(0, selection.source_count - selected),
                skip_reasons=selection.skip_reasons,
            )
        if conn.in_transaction:
            # Provider/budget guard calls use their own SQLite connection.
            conn.commit()
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
                    space_id=space_id,
                    generation_id=generation_id,
                    doc_id=row["doc_id"],
                    vector=vector,
                    text_hash=text_hash,
                    source_doc_hash=source_hash,
                    token_count=_rough_input_token_count(text),
                    now=now,
                    projection_id=_row_text(row, "projection_id") or None,
                    projection_policy_version=_row_text(
                        row,
                        "projection_policy_version",
                    )
                    or None,
                    classification_version=_row_text(row, "classification_version") or None,
                    target_space_id=_row_text(row, "target_space_id") or None,
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
        space_id=space_id,
        generation_id=generation_id,
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
        eligible=selection.eligible_count,
        ineligible=selection.ineligible_count,
        skip_reasons=selection.skip_reasons,
        uses_projection_rows=uses_projection_rows,
        projection_profile=projection_profile
        or (spec.embedding_profile if uses_projection_rows else None),
        target_space_id=space_id if uses_projection_rows else None,
        classification_version=classification_version if uses_projection_rows else None,
        projection_policy_version=projection_policy_version if uses_projection_rows else None,
        provider_requests_made=0 if spec.provider == LOCAL_HASH_PROVIDER else embedded,
    )


def semantic_search_memory(
    db_path: str | Path,
    query: str,
    *,
    space_id: str | None = None,
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
        spec = _resolve_semantic_query_spec(
            conn,
            space_id=space_id,
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
        rows = _embedding_rows(
            conn,
            spec=spec,
            space_id=space_id,
            doc_type=doc_type,
            account=account,
        )
        _single_space_id_from_embedding_rows(rows, requested_space_id=space_id)
        expected_rows = _embedding_document_count(
            conn,
            spec=spec,
            space_id=space_id,
            doc_type=doc_type,
            account=account,
        )
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
    space_id: str | None = None,
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
        spec = _resolve_semantic_query_spec(
            conn,
            space_id=space_id,
            provider=provider,
            model=model,
            dimensions=dimensions,
            embedding_profile=embedding_profile,
            text_template_version=text_template_version,
            api_key_env=api_key_env,
            base_url=base_url,
        )
        rows = _embedding_rows(
            conn,
            spec=spec,
            space_id=space_id,
            doc_type=doc_type,
            account=account,
        )
        resolved_space_id = _single_space_id_from_embedding_rows(
            rows,
            requested_space_id=space_id,
        )
        expected_rows = _embedding_document_count(
            conn,
            spec=spec,
            space_id=space_id,
            doc_type=doc_type,
            account=account,
        )
        if expected_rows and len(rows) < expected_rows:
            raise RuntimeError(
                "semantic index is incomplete or stale for the requested scope: "
                f"{len(rows)}/{expected_rows} documents indexed for "
                f"{spec.provider}/{spec.model} dims={spec.dimensions}"
            )
    matrix = _semantic_matrix_from_rows(rows, dimensions=spec.dimensions)
    return LoadedSemanticIndex(
        spec=spec,
        space_id=resolved_space_id,
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
            space_id=index.space_id or _space_id_for_spec(index.spec),
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
    space_id: str | None = None,
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
        spec = _resolve_semantic_query_spec(
            conn,
            space_id=space_id,
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
        rows = _embedding_rows_for_doc_ids(
            conn,
            spec=spec,
            space_id=space_id,
            doc_ids=doc_ids,
        )
        _single_space_id_from_embedding_rows(rows, requested_space_id=space_id)
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
            space_id=row["space_id"],
            provider=row["provider"],
            model=row["model"],
            dimensions=int(row["dimensions"]),
            embedding_profile=row["embedding_profile"],
            text_template_version=row["text_template_version"],
            source_doc_hash=row["source_doc_hash"],
            embedded_text_hash=row["embedded_text_hash"],
            generated_at=_embedding_generated_at(row),
            stale_status="current",
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
    space_id: str | None = None,
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
            else _coverage_spec(
                conn,
                provider=provider,
                model=model,
                dimensions=dimensions,
                embedding_profile=embedding_profile,
                text_template_version=text_template_version,
            )
        )
        rows = _memory_document_projection_rows(
            conn,
            spec=spec,
            space_id=space_id or _space_id_for_spec(spec),
        )
    by_type: dict[str, dict[str, int]] = {}
    totals = {
        "documents": 0,
        "current": 0,
        "missing": 0,
        "stale_text": 0,
        "stale_source": 0,
        "ineligible": 0,
    }
    skip_reasons: Counter[str] = Counter()
    for row in rows:
        bucket = by_type.setdefault(
            str(row["doc_type"]),
            {
                "documents": 0,
                "current": 0,
                "missing": 0,
                "stale_text": 0,
                "stale_source": 0,
                "ineligible": 0,
            },
        )
        status = _coverage_status(row)
        if status == "ineligible":
            skip_reasons[str(row["projection_skip_reason"])] += 1
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
        space_id=space_id or _space_id_for_spec(spec),
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
        eligible=totals["documents"] - totals["ineligible"],
        ineligible=totals["ineligible"],
        skip_reasons=dict(sorted(skip_reasons.items())),
        by_doc_type=by_doc_type,
    )


def embedding_coverage_json(report: EmbeddingCoverageReport) -> str:
    return json.dumps(asdict(report), ensure_ascii=False, indent=2, sort_keys=True)


def estimate_memory_embedding_build(
    db_path: str | Path,
    *,
    space_id: str | None = None,
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
    projection_profile: str | None = None,
    classification_version: str | None = None,
    projection_policy_version: str | None = None,
    require_projections: bool = False,
) -> EmbeddingBuildEstimate:
    path = Path(db_path)
    if not path.exists():
        raise FileNotFoundError(f"database not found: {path}")
    spec = (
        _resolve_spec_from_db_space_id(
            path,
            space_id=space_id,
            provider=provider,
            model=model,
            dimensions=dimensions,
            embedding_profile=embedding_profile,
            text_template_version=text_template_version,
            api_key_env=api_key_env,
            base_url=base_url,
        )
        if space_id
        else resolve_embedding_spec(
            provider=provider,
            model=model,
            dimensions=dimensions,
            embedding_profile=embedding_profile,
            text_template_version=text_template_version,
            api_key_env=api_key_env,
            base_url=base_url,
        )
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
    uses_projection_rows = bool(
        require_projections
        or projection_profile
        or classification_version
        or projection_policy_version
    )
    if (
        not uses_projection_rows
        and execution_stage != "auto"
        and resolved_execution_stage in {"eval_slice", "production_scope"}
    ):
        raise RuntimeError(
            "eval_slice and production_scope embedding estimates require "
            "memory_embedding_projections; pass --require-projections with "
            "--classification-version and --projection-policy-version"
        )
    resolved_batch_size = max(1, batch_size)
    with sqlite3.connect(path, timeout=60) as conn:
        conn.row_factory = sqlite3.Row
        ensure_memory_schema(conn)
        documents = memory_document_count(conn)
        if documents == 0:
            raise RuntimeError("memory_documents is empty; run memory build-corpus first")
        target_space_id = space_id or _space_id_for_spec(spec)
        if uses_projection_rows:
            selection = _stored_embedding_projection_selection(
                conn,
                spec=spec,
                space_id=target_space_id,
                projection_profile=projection_profile or spec.embedding_profile,
                classification_version=classification_version
                or DEFAULT_CLASSIFICATION_VERSION,
                projection_policy_version=projection_policy_version
                or DEFAULT_PROJECTION_POLICY_VERSION,
                limit=limit,
                rebuild=rebuild,
                selection_policy=resolved_selection_policy,
            )
        else:
            selection = _embedding_projection_selection(
                conn,
                spec=spec,
                space_id=target_space_id,
                limit=limit,
                rebuild=rebuild,
                selection_policy=resolved_selection_policy,
            )
    rows = selection.rows
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
        space_id=space_id or _space_id_for_spec(spec),
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
        eligible=selection.eligible_count,
        ineligible=selection.ineligible_count,
        skip_reasons=selection.skip_reasons,
        estimated_input_chars=input_chars,
        estimated_input_tokens=input_tokens,
        batch_size=resolved_batch_size,
        estimated_batches=math.ceil(selected / resolved_batch_size) if selected else 0,
        price_per_million_input_tokens=price_per_million_input_tokens,
        estimated_input_cost=estimated_cost,
        execution_stage=resolved_execution_stage,
        selection_policy=resolved_selection_policy,
        selection_contract=selection_contract,
        uses_projection_rows=uses_projection_rows,
        projection_profile=projection_profile
        or (spec.embedding_profile if uses_projection_rows else None),
        target_space_id=space_id or _space_id_for_spec(spec),
        classification_version=classification_version if uses_projection_rows else None,
        projection_policy_version=projection_policy_version if uses_projection_rows else None,
        eligible_documents=selection.eligible_count,
        eligible_projections=selection.eligible_count if uses_projection_rows else 0,
        selected_projections=selected if uses_projection_rows else 0,
        skipped_stale_projections=selection.skip_reasons.get("stale_projection", 0),
        skipped_missing_restoration=selection.skip_reasons.get(
            "missing_restoration_path",
            0,
        ),
        provider_requests_made=0,
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
            f"eligible={estimate.eligible} ineligible={estimate.ineligible} "
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
    if estimate.skip_reasons:
        lines.append(
            "skip reasons: "
            + ", ".join(
                f"{reason}={count}" for reason, count in estimate.skip_reasons.items()
            )
        )
    return "\n".join(lines)


def format_embedding_coverage(report: EmbeddingCoverageReport) -> str:
    lines = [
        f"db: {report.db_path}",
        f"space: {report.space_id}",
        (
            "spec: "
            f"{report.provider}/{report.model} dims={report.dimensions} "
            f"profile={report.embedding_profile} template={report.text_template_version}"
        ),
        (
            "documents: "
            f"{report.documents} current={report.current} missing={report.missing} "
            f"stale_text={report.stale_text} stale_source={report.stale_source} "
            f"eligible={report.eligible} ineligible={report.ineligible}"
        ),
        "by doc_type:",
    ]
    for row in report.by_doc_type:
        lines.append(
            "  "
            f"{row.doc_type}: docs={row.documents} current={row.current} "
            f"missing={row.missing} stale_text={row.stale_text} "
            f"stale_source={row.stale_source} ineligible={row.ineligible}"
        )
    if report.skip_reasons:
        lines.append(
            "skip reasons: "
            + ", ".join(
                f"{reason}={count}" for reason, count in report.skip_reasons.items()
            )
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


def _embedding_projection_selection(
    conn: sqlite3.Connection,
    *,
    spec: EmbeddingSpec,
    space_id: str | None,
    limit: int | None,
    rebuild: bool,
    selection_policy: str,
) -> _EmbeddingProjectionSelection:
    rows = _memory_document_projection_rows(conn, spec=spec, space_id=space_id)
    skip_reasons: Counter[str] = Counter(
        str(row["projection_skip_reason"])
        for row in rows
        if row["projection_skip_reason"]
    )
    eligible_rows = [row for row in rows if not row["projection_skip_reason"]]
    candidate_rows = eligible_rows
    if not rebuild:
        candidate_rows = [
            row for row in eligible_rows if _coverage_status(row) != "current"
        ]
    selected_rows = _select_embedding_rows(
        candidate_rows,
        limit=limit,
        selection_policy=selection_policy,
    )
    return _EmbeddingProjectionSelection(
        rows=selected_rows,
        source_count=len(rows),
        eligible_count=len(eligible_rows),
        ineligible_count=len(rows) - len(eligible_rows),
        skip_reasons=dict(sorted(skip_reasons.items())),
    )


def _stored_embedding_projection_selection(
    conn: sqlite3.Connection,
    *,
    spec: EmbeddingSpec,
    space_id: str,
    projection_profile: str,
    classification_version: str,
    projection_policy_version: str,
    limit: int | None,
    rebuild: bool,
    selection_policy: str,
) -> _EmbeddingProjectionSelection:
    rows = _stored_embedding_projection_rows(
        conn,
        spec=spec,
        space_id=space_id,
        projection_profile=projection_profile,
        canonical_space_id=PROFILE_TARGET_SPACE.get(projection_profile, space_id),
        classification_version=classification_version,
        projection_policy_version=projection_policy_version,
    )
    skip_reasons: Counter[str] = Counter(
        str(row["projection_skip_reason"])
        for row in rows
        if row["projection_skip_reason"]
    )
    eligible_rows = [row for row in rows if not row["projection_skip_reason"]]
    candidate_rows = eligible_rows
    if not rebuild:
        candidate_rows = [
            row for row in eligible_rows if _coverage_status(row) != "current"
        ]
    selected_rows = _select_embedding_rows(
        candidate_rows,
        limit=limit,
        selection_policy=selection_policy,
    )
    return _EmbeddingProjectionSelection(
        rows=selected_rows,
        source_count=len(rows),
        eligible_count=len(eligible_rows),
        ineligible_count=len(rows) - len(eligible_rows),
        skip_reasons=dict(sorted(skip_reasons.items())),
    )


def _stored_embedding_projection_rows(
    conn: sqlite3.Connection,
    *,
    spec: EmbeddingSpec,
    space_id: str,
    projection_profile: str,
    canonical_space_id: str,
    classification_version: str,
    projection_policy_version: str,
) -> list[EmbeddingInputRow]:
    rows = conn.execute(
        """
        SELECT
            p.doc_id,
            d.doc_type,
            d.source_tweet_id,
            d.account_id,
            d.author_screen_name,
            d.title,
            d.compact_text,
            d.body,
            d.metadata_json,
            d.created_at,
            d.observed_at,
            d.updated_at,
            t.source_kind,
            t.ownership_kind,
            t.content_role,
            t.relation_role,
            t.modality_kind AS modality,
            t.language,
            t.sensitivity_kind AS privacy_class,
            'retain' AS retention_class,
            CASE
                WHEN p.projection_status = 'active' AND p.stale_status = 'current'
                THEN 'eligible'
                ELSE 'not_eligible'
            END AS embedding_eligibility,
            p.source_doc_hash AS projection_source_doc_hash,
            p.embedded_text AS projection_text,
            p.embedded_text_hash AS projection_hash,
            p.projection_id,
            p.classification_version,
            p.projection_policy_version,
            p.target_space_id,
            p.text_template_version AS projection_text_template_version,
            p.projection_status,
            p.stale_status AS projection_stale_status,
            p.source_restore_path_json,
            e.provider,
            e.model,
            e.dimensions,
            e.embedding_profile,
            e.text_template_version,
            e.embedding,
            e.embedded_text_hash,
            e.embedded_input_hash,
            e.source_doc_hash,
            e.space_id,
            e.generation_id,
            e.stale_status,
            e.created_at AS embedding_created_at,
            e.updated_at AS embedding_updated_at
        FROM memory_embedding_projections p
        JOIN memory_documents d ON d.doc_id = p.doc_id
        LEFT JOIN memory_document_taxonomy t
          ON t.doc_id = p.doc_id
         AND t.classification_version = p.classification_version
        LEFT JOIN memory_embeddings e
          ON e.projection_id = p.projection_id
         AND e.provider = ?
         AND e.model = ?
         AND e.dimensions = ?
         AND e.embedding_profile = ?
         AND e.space_id = ?
        WHERE p.classification_version = ?
          AND p.projection_policy_version = ?
          AND p.projection_profile = ?
          AND p.target_space_id IN (?, ?)
        ORDER BY d.observed_at DESC, p.doc_id, p.projection_id
        """,
        (
            spec.provider,
            spec.model,
            spec.dimensions,
            spec.embedding_profile,
            space_id,
            classification_version,
            projection_policy_version,
            projection_profile,
            space_id,
            canonical_space_id,
        ),
    ).fetchall()
    return [_stored_projection_row(row) for row in rows]


def _stored_projection_row(row: sqlite3.Row) -> EmbeddingInputRow:
    payload = dict(row)
    skip_reason = None
    if row["projection_status"] != "active":
        skip_reason = "inactive_projection"
    elif row["projection_stale_status"] != "current":
        skip_reason = "stale_projection"
    elif not _row_text(row, "source_restore_path_json"):
        skip_reason = "missing_restoration_path"
    elif not _row_text(row, "projection_hash"):
        skip_reason = "missing_embedded_text_hash"
    payload["projection_skip_reason"] = skip_reason
    return payload


def _memory_document_projection_rows(
    conn: sqlite3.Connection,
    *,
    spec: EmbeddingSpec,
    space_id: str | None,
    doc_type: str | None = None,
    account: str | None = None,
    doc_ids: tuple[str, ...] = (),
) -> list[EmbeddingInputRow]:
    if doc_ids and not tuple(doc_id for doc_id in doc_ids if doc_id):
        return []
    document_columns = _memory_document_select_expressions(conn)
    space_join = "AND e.space_id = ?" if space_id else ""
    filters: list[str] = []
    params: list[Any] = [
        spec.provider,
        spec.model,
        spec.dimensions,
        spec.embedding_profile,
        spec.text_template_version,
    ]
    if space_id:
        params.append(space_id)
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
    where = f"WHERE {' AND '.join(filters)}" if filters else ""
    rows = conn.execute(
        f"""
        SELECT
            {", ".join(document_columns)},
            e.provider,
            e.model,
            e.dimensions,
            e.embedding_profile,
            e.text_template_version,
            e.embedding,
            e.embedded_text_hash,
            e.embedded_input_hash,
            e.source_doc_hash,
            e.space_id,
            e.generation_id,
            e.stale_status,
            e.created_at AS embedding_created_at,
            e.updated_at AS embedding_updated_at
        FROM memory_documents d
        LEFT JOIN memory_embeddings e
          ON e.doc_id = d.doc_id
         AND e.provider = ?
         AND e.model = ?
         AND e.dimensions = ?
         AND e.embedding_profile = ?
         AND e.text_template_version = ?
         {space_join}
        {where}
        ORDER BY d.observed_at DESC, d.doc_id
        """,
        params,
    ).fetchall()
    return [_projection_row(row, spec=spec) for row in rows]


def _memory_document_select_expressions(conn: sqlite3.Connection) -> list[str]:
    existing_columns = _table_column_names(conn, "memory_documents")
    expressions = [
        "d.doc_id",
        "d.doc_type",
        "d.source_tweet_id",
        "d.account_id",
        "d.author_screen_name",
        "d.title",
        "d.compact_text",
        "d.body",
        "d.metadata_json",
        "d.created_at",
        "d.observed_at",
        "d.updated_at",
    ]
    for column in _CLASSIFICATION_COLUMNS:
        expressions.append(
            f"d.{column} AS {column}" if column in existing_columns else f"NULL AS {column}"
        )
    return expressions


def _table_column_names(conn: sqlite3.Connection, table: str) -> set[str]:
    return {
        str(row[1])
        for row in conn.execute(f"PRAGMA table_info({table})").fetchall()
    }


def _projection_row(row: sqlite3.Row, *, spec: EmbeddingSpec) -> EmbeddingInputRow:
    projection_text, skip_reason = _typed_text_projection(row, spec=spec)
    payload = dict(row)
    payload["projection_text"] = projection_text
    payload["projection_hash"] = _text_hash(projection_text) if projection_text else ""
    payload["projection_skip_reason"] = skip_reason
    return payload


def _typed_text_projection(
    row: EmbeddingInputRow,
    *,
    spec: EmbeddingSpec,
) -> tuple[str, str | None]:
    classification = _document_classification(row)
    base_text = _redact_projection_text(memory_document_embedding_text(row).strip())
    if not base_text:
        return "", "empty_projection_text"
    explicit_skip = _explicit_projection_skip_reason(classification)
    if explicit_skip:
        return "", explicit_skip
    profile = spec.embedding_profile
    profile_skip = _profile_projection_skip_reason(
        row,
        profile=profile,
        classification=classification,
        base_text=base_text,
    )
    if profile_skip:
        return "", profile_skip
    if profile == "general_memory":
        return _general_memory_projection(row, classification, base_text), None
    if profile == "jp_multilingual":
        return _jp_multilingual_projection(row, classification, base_text), None
    if profile == "code_technical":
        return _code_technical_projection(row, classification, base_text), None
    if profile == "relation_context":
        return _relation_context_projection(row, classification, base_text), None
    if profile == "temporal_event":
        return _temporal_event_projection(row, classification, base_text), None
    if profile == "media_text_bridge":
        return _media_text_bridge_projection(row, classification, base_text), None
    if profile == "external_fetch_text":
        return _external_fetch_text_projection(row, classification, base_text), None
    return base_text, None


def _document_classification(row: EmbeddingInputRow) -> dict[str, str]:
    metadata = _metadata_dict(row)
    doc_type = _row_text(row, "doc_type")
    source_kind = (
        _row_text(row, "source_kind")
        or _metadata_text(metadata, "source_kind", "evidence_source_kind")
        or "local_x_text"
    )
    source_subkind = (
        _row_text(row, "source_subkind")
        or _metadata_text(metadata, "source_subkind", "type", "role")
        or doc_type
    )
    language = (
        _row_text(row, "language")
        or _metadata_text(metadata, "language", "lang")
        or _detect_projection_language(row)
    )
    relation_type = (
        _row_text(row, "relation_type")
        or _metadata_text(metadata, "relation_type", "relation")
        or _relation_type_from_doc_type(doc_type)
    )
    modality = (
        _row_text(row, "modality")
        or _metadata_text(metadata, "modality")
        or (
            "text_from_media"
            if _looks_like_media_doc(doc_type, source_kind, source_subkind)
            else "text"
        )
    )
    account_scope = (
        _row_text(row, "account_scope")
        or _metadata_text(metadata, "account_scope")
        or ("account_specific" if _row_text(row, "account_id") else "global")
    )
    return {
        "source_kind": source_kind,
        "source_subkind": source_subkind,
        "doc_type": doc_type,
        "language": language,
        "modality": modality,
        "relation_type": relation_type,
        "account_scope": account_scope,
        "privacy_class": (
            _row_text(row, "privacy_class")
            or _metadata_text(metadata, "privacy_class", "storage_rights_policy")
            or "local"
        ),
        "retention_class": (
            _row_text(row, "retention_class")
            or _metadata_text(metadata, "retention_class")
            or "default"
        ),
        "embedding_eligibility": (
            _row_text(row, "embedding_eligibility")
            or _metadata_text(metadata, "embedding_eligibility", "embedding_policy")
            or "eligible"
        ),
    }


def _explicit_projection_skip_reason(classification: dict[str, str]) -> str | None:
    eligibility = classification["embedding_eligibility"].strip().lower()
    if eligibility in _INELIGIBLE_VALUES:
        return f"embedding_eligibility:{eligibility}"
    if eligibility not in _ELIGIBLE_VALUES:
        return f"embedding_eligibility:{eligibility}"
    privacy_class = classification["privacy_class"].strip().lower()
    if privacy_class in {"secret", "credential", "credentials", "private_key", "do_not_embed"}:
        return f"privacy_class:{privacy_class}"
    return None


def _profile_projection_skip_reason(
    row: EmbeddingInputRow,
    *,
    profile: str,
    classification: dict[str, str],
    base_text: str,
) -> str | None:
    metadata = _metadata_dict(row)
    doc_type = classification["doc_type"].lower()
    source_kind = classification["source_kind"].lower()
    source_subkind = classification["source_subkind"].lower()
    relation_type = classification["relation_type"].lower()
    modality = classification["modality"].lower()
    language = classification["language"].lower()
    combined_kind = " ".join((doc_type, source_kind, source_subkind, relation_type, modality))
    if profile == "general_memory":
        return None
    if profile == "jp_multilingual":
        if (
            language in {"ja", "jp", "japanese", "mixed", "ja-en", "en-ja"}
            or _JP_RE.search(base_text)
            or _has_metadata_key(
                metadata,
                "japanese_cues",
                "ja_aliases",
                "aliases",
                "translation",
                "transliteration",
            )
        ):
            return None
        return "language_not_japanese_or_mixed"
    if profile == "code_technical":
        if "technical" in combined_kind or "code" in combined_kind:
            return None
        if _TECHNICAL_RE.search(base_text):
            return None
        return "not_technical_text"
    if profile == "relation_context":
        if any(
            marker in combined_kind
            for marker in (
                "quote",
                "reply",
                "thread",
                "bookmark",
                "account",
                "relation",
                "author_profile",
                "topic_thread",
            )
        ):
            return None
        if _has_metadata_key(
            metadata,
            "parent_tweet_id",
            "quote_tweet_id",
            "reply_to_tweet_id",
            "thread_id",
            "collection_kind",
            "neighbor_snippets",
            "relation_labels",
        ):
            return None
        return "not_relation_context"
    if profile == "temporal_event":
        if _has_temporal_event_signal(
            row,
            classification=classification,
            metadata=metadata,
            base_text=base_text,
        ):
            return None
        return "missing_temporal_signal"
    if profile == "media_text_bridge":
        if "media" in combined_kind or "ocr" in combined_kind or "caption" in combined_kind:
            return None
        if _has_metadata_key(
            metadata,
            "media_id",
            "ocr_text",
            "corrected_ocr_text",
            "caption",
            "alt_text",
            "media_role",
            "ocr_source",
            "region",
            "page",
        ):
            return None
        return "not_media_text"
    if profile == "external_fetch_text":
        if any(marker in combined_kind for marker in ("external", "fetch", "reader")):
            return None
        if _has_metadata_key(
            metadata,
            "requested_url",
            "final_url",
            "fetched_at",
            "content_hash",
            "text_hash",
            "reader_provider",
            "prompt_injection_review_status",
        ):
            return None
        return "not_external_fetch_text"
    return None


def _general_memory_projection(
    row: EmbeddingInputRow,
    classification: dict[str, str],
    base_text: str,
) -> str:
    return _projection_text(
        "Template: text.general_memory.v1",
        f"Source Kind: {classification['source_kind']}",
        f"Source Subkind: {classification['source_subkind']}",
        f"Doc Type: {classification['doc_type']}",
        f"Author/Account: {_account_hint(row)}",
        f"Date: {_row_text(row, 'created_at')}",
        f"Observed Date: {_row_text(row, 'observed_at')}",
        f"Language: {classification['language']}",
        _relation_hint_line(row, classification),
        f"Main Text:\n{base_text}",
    )


def _jp_multilingual_projection(
    row: EmbeddingInputRow,
    classification: dict[str, str],
    base_text: str,
) -> str:
    metadata = _metadata_dict(row)
    return _projection_text(
        "Template: text.jp_multilingual.v1",
        f"Language: {classification['language']}",
        f"Doc Type: {classification['doc_type']}",
        f"Original Text:\n{base_text}",
        _projection_json_line(
            "Japanese Cues",
            _metadata_subset(metadata, ("japanese_cues", "ja_aliases", "aliases", "entities")),
        ),
    )


def _code_technical_projection(
    row: EmbeddingInputRow,
    classification: dict[str, str],
    base_text: str,
) -> str:
    identifiers = _technical_identifiers(base_text)
    command_or_error = _command_or_error_excerpt(base_text)
    return _projection_text(
        "Template: text.code_technical.v1",
        "Kind: technical",
        f"Doc Type: {classification['doc_type']}",
        _projection_csv_line("Identifiers", identifiers),
        f"Error/Command: {command_or_error}" if command_or_error else "",
        f"Context:\n{base_text}",
    )


def _relation_context_projection(
    row: EmbeddingInputRow,
    classification: dict[str, str],
    base_text: str,
) -> str:
    metadata = _metadata_dict(row)
    return _projection_text(
        "Template: text.relation_context.v1",
        f"Subject Doc: {_row_text(row, 'doc_id')}",
        f"Source Tweet: {_row_text(row, 'source_tweet_id')}",
        f"Relation Type: {classification['relation_type']}",
        f"Author/Account: {_account_hint(row)}",
        _projection_json_line(
            "Relation Hints",
            _metadata_subset(
                metadata,
                (
                    "parent_tweet_id",
                    "quote_tweet_id",
                    "reply_to_tweet_id",
                    "thread_id",
                    "collection_kind",
                    "neighbor_snippets",
                    "relation_labels",
                ),
            ),
        ),
        f"Text:\n{base_text}",
    )


def _temporal_event_projection(
    row: EmbeddingInputRow,
    classification: dict[str, str],
    base_text: str,
) -> str:
    metadata = _metadata_dict(row)
    event_date = (
        _metadata_text(metadata, "event_at", "published_at")
        or _row_text(row, "created_at")
    )
    return _projection_text(
        "Template: text.temporal_event.v1",
        f"Event Date: {event_date}",
        f"Observed At: {_row_text(row, 'observed_at')}",
        f"Updated At: {_row_text(row, 'updated_at')}",
        _projection_csv_line("Time Expressions", _time_expressions(base_text)),
        _projection_json_line(
            "Status Fields",
            _metadata_subset(metadata, ("status", "status_changed_at", "changed_at")),
        ),
        f"Main Event Text:\n{base_text}",
    )


def _media_text_bridge_projection(
    row: EmbeddingInputRow,
    classification: dict[str, str],
    base_text: str,
) -> str:
    metadata = _metadata_dict(row)
    return _projection_text(
        "Template: media.text_bridge.v1",
        f"Media ID: {_metadata_text(metadata, 'media_id') or _row_text(row, 'doc_id')}",
        f"Source Tweet: {_row_text(row, 'source_tweet_id')}",
        f"Media Role: {_metadata_text(metadata, 'media_role', 'role', 'type')}",
        "OCR/Caption Source: "
        f"{_metadata_text(metadata, 'ocr_source', 'caption_source', 'source_type')}",
        f"Region/Page: {_metadata_text(metadata, 'region', 'page')}",
        f"Review State: {_metadata_text(metadata, 'review_state', 'confidence')}",
        f"Text:\n{base_text}",
    )


def _external_fetch_text_projection(
    row: EmbeddingInputRow,
    classification: dict[str, str],
    base_text: str,
) -> str:
    metadata = _metadata_dict(row)
    return _projection_text(
        "Template: external.fetch_text.v1",
        f"Requested URL: {_metadata_text(metadata, 'requested_url')}",
        f"Final URL: {_metadata_text(metadata, 'final_url', 'url')}",
        f"Domain: {_metadata_text(metadata, 'domain')}",
        f"Fetched At: {_metadata_text(metadata, 'fetched_at')}",
        f"Content Hash: {_metadata_text(metadata, 'content_hash')}",
        f"Text Hash: {_metadata_text(metadata, 'text_hash')}",
        f"Title: {_row_text(row, 'title')}",
        f"Source Kind: {classification['source_kind']}",
        f"Prompt Injection Review: {_metadata_text(metadata, 'prompt_injection_review_status')}",
        f"Text:\n{base_text}",
    )


def _projection_text(*parts: str) -> str:
    return "\n".join(part for part in parts if part).strip()[:3600]


def _projection_json_line(label: str, value: dict[str, Any]) -> str:
    if not value:
        return ""
    return f"{label}: {json.dumps(value, ensure_ascii=False, sort_keys=True)}"


def _projection_csv_line(label: str, values: tuple[str, ...]) -> str:
    return f"{label}: {', '.join(values)}" if values else ""


def _relation_hint_line(row: EmbeddingInputRow, classification: dict[str, str]) -> str:
    metadata = _metadata_dict(row)
    hints: dict[str, Any] = {}
    if classification["relation_type"]:
        hints["relation_type"] = classification["relation_type"]
    hints.update(
        _metadata_subset(
            metadata,
            (
                "parent_tweet_id",
                "quote_tweet_id",
                "reply_to_tweet_id",
                "thread_id",
                "collection_kind",
                "relation_labels",
            ),
        )
    )
    return _projection_json_line("Relation Hints", hints)


def _has_temporal_event_signal(
    row: EmbeddingInputRow,
    *,
    classification: dict[str, str],
    metadata: dict[str, Any],
    base_text: str,
) -> bool:
    combined_kind = " ".join(
        (
            classification["doc_type"],
            classification["source_subkind"],
            classification["relation_type"],
            classification["source_kind"],
        )
    ).lower()
    if any(
        marker in combined_kind
        for marker in (
            "temporal",
            "event",
            "status",
            "change",
            "changed",
            "update",
            "timeline",
            "chronology",
            "history",
            "dated",
            "older_than",
            "newer_than",
            "obsolete",
            "ticker_event",
        )
    ):
        return True
    if _has_metadata_key(
        metadata,
        "event_at",
        "changed_at",
        "status",
        "status_changed_at",
        "published_at",
        "event_date",
        "timeline",
    ):
        return True
    if _DATE_RE.search(base_text):
        return True
    return _updated_at_signals_change(row)


def _updated_at_signals_change(row: EmbeddingInputRow) -> bool:
    updated_at = _normalized_timestamp(_row_text(row, "updated_at"))
    if not updated_at:
        return False
    baselines = {
        _normalized_timestamp(_row_text(row, "created_at")),
        _normalized_timestamp(_row_text(row, "observed_at")),
    }
    baselines.discard("")
    return bool(baselines) and all(updated_at != baseline for baseline in baselines)


def _normalized_timestamp(value: str) -> str:
    return value.strip().replace("Z", "+00:00")


def _metadata_subset(metadata: dict[str, Any], keys: tuple[str, ...]) -> dict[str, Any]:
    return {key: metadata[key] for key in keys if metadata.get(key) not in (None, "", [], {})}


def _technical_identifiers(text: str) -> tuple[str, ...]:
    tokens = []
    for token in _ASCII_WORD_RE.findall(text):
        if (
            "_" in token
            or "-" in token
            or "." in token
            or token.isupper()
            or token.lower()
            in {
                "api",
                "cli",
                "json",
                "sqlite",
                "python",
                "pytest",
                "ruff",
                "uv",
                "gemini",
                "openai",
                "voyage",
                "cohere",
                "mistral",
                "jina",
            }
        ):
            tokens.append(token)
    return tuple(dict.fromkeys(tokens[:24]))


def _command_or_error_excerpt(text: str) -> str:
    match = _COMMAND_OR_ERROR_RE.search(text)
    return match.group(0).strip()[:400] if match else ""


def _time_expressions(text: str) -> tuple[str, ...]:
    return tuple(dict.fromkeys(match.group(0) for match in _DATE_RE.finditer(text)))[:12]


def _account_hint(row: EmbeddingInputRow) -> str:
    return " / ".join(
        part
        for part in (
            _row_text(row, "account_id"),
            _row_text(row, "author_screen_name"),
        )
        if part
    )


def _metadata_dict(row: EmbeddingInputRow) -> dict[str, Any]:
    raw = _row_text(row, "metadata_json")
    if not raw:
        return {}
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def _metadata_text(metadata: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = metadata.get(key)
        if value in (None, "", [], {}):
            continue
        if isinstance(value, (dict, list, tuple)):
            return json.dumps(value, ensure_ascii=False, sort_keys=True)
        return str(value).strip()
    return ""


def _has_metadata_key(metadata: dict[str, Any], *keys: str) -> bool:
    return any(metadata.get(key) not in (None, "", [], {}) for key in keys)


def _detect_projection_language(row: EmbeddingInputRow) -> str:
    text = " ".join(
        part
        for part in (
            _row_text(row, "title"),
            _row_text(row, "compact_text"),
            _row_text(row, "body"),
        )
        if part
    )
    has_japanese = bool(_JP_RE.search(text))
    has_ascii = bool(_ASCII_WORD_RE.search(text))
    if has_japanese and has_ascii:
        return "mixed"
    if has_japanese:
        return "ja"
    if has_ascii:
        return "en"
    return "und"


def _relation_type_from_doc_type(doc_type: str) -> str:
    lowered = doc_type.lower()
    if "quote" in lowered:
        return "quote_relation"
    if "reply" in lowered:
        return "reply_relation"
    if "thread" in lowered:
        return "thread_context"
    if "bookmark" in lowered:
        return "bookmark_context"
    if "author" in lowered or "account" in lowered:
        return "account_context"
    return ""


def _looks_like_media_doc(doc_type: str, source_kind: str, source_subkind: str) -> bool:
    haystack = " ".join((doc_type, source_kind, source_subkind)).lower()
    return "media" in haystack or "ocr" in haystack or "caption" in haystack


def _row_text(row: EmbeddingInputRow, key: str) -> str:
    try:
        value = row.get(key) if isinstance(row, dict) else row[key]
    except (KeyError, IndexError):
        value = None
    return str(value or "").strip()


def _redact_projection_text(text: str) -> str:
    return _SECRET_ASSIGNMENT_RE.sub(r"\1\2[REDACTED]", text)


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
    rows: list[EmbeddingInputRow],
    *,
    limit: int | None,
    selection_policy: str,
) -> list[EmbeddingInputRow]:
    if limit is None or limit <= 0 or len(rows) <= limit:
        return rows
    if selection_policy == "sequential":
        return rows[:limit]
    if selection_policy == "doc_type_round_robin":
        grouped: dict[str, list[EmbeddingInputRow]] = {}
        for row in rows:
            grouped.setdefault(str(row["doc_type"]), []).append(row)
        selected: list[EmbeddingInputRow] = []
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
    space_id: str | None = None,
    doc_type: str | None,
    account: str | None,
) -> list[EmbeddingInputRow]:
    rows = _memory_document_projection_rows(
        conn,
        spec=spec,
        space_id=space_id,
        doc_type=doc_type,
        account=account,
    )
    return [
        row
        for row in rows
        if _embedding_row_available_for_index(row, spec=spec)
    ]


def _embedding_document_count(
    conn: sqlite3.Connection,
    *,
    spec: EmbeddingSpec | None = None,
    space_id: str | None = None,
    doc_type: str | None,
    account: str | None,
) -> int:
    if spec is not None:
        rows = _memory_document_projection_rows(
            conn,
            spec=spec,
            space_id=space_id,
            doc_type=doc_type,
            account=account,
        )
        return sum(1 for row in rows if not row["projection_skip_reason"])
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
    space_id: str | None = None,
    doc_ids: tuple[str, ...],
) -> list[EmbeddingInputRow]:
    rows = _memory_document_projection_rows(
        conn,
        spec=spec,
        space_id=space_id,
        doc_ids=doc_ids,
    )
    return [
        row
        for row in rows
        if _embedding_row_available_for_index(row, spec=spec)
    ]


def _embedding_row_available_for_index(
    row: EmbeddingInputRow,
    *,
    spec: EmbeddingSpec,
) -> bool:
    if row["embedded_text_hash"] is None:
        return False
    if row["stale_status"] != "current":
        return False
    if _row_text(row, "projection_skip_reason"):
        return False
    if row["source_doc_hash"] != _source_doc_hash(row):
        return False
    if row["embedded_text_hash"] == _text_hash(_embedding_text(row)):
        return True
    return (
        _normalize_provider_for_policy(spec.provider) != LOCAL_HASH_PROVIDER
        and row["embedded_text_hash"] == memory_document_embedding_text_hash(row)
    )


def _single_space_id_from_embedding_rows(
    rows: list[sqlite3.Row],
    *,
    requested_space_id: str | None,
) -> str | None:
    space_ids = {str(row["space_id"] or "").strip() for row in rows}
    space_ids.discard("")
    if requested_space_id:
        unexpected = space_ids - {requested_space_id}
        if unexpected:
            raise RuntimeError(
                "semantic embedding rows crossed embedding spaces; requested "
                f"{requested_space_id}, saw {sorted(unexpected)}"
            )
        return requested_space_id
    if len(space_ids) > 1:
        raise RuntimeError(
            "semantic search matched multiple embedding spaces for one spec; "
            "pass --semantic-space-id or --space-id to avoid raw score mixing"
        )
    return next(iter(space_ids), None)


def _semantic_hits_from_rows(
    rows: list[EmbeddingInputRow],
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
                    space_id=row["space_id"],
                    provider=row["provider"],
                    model=row["model"],
                    dimensions=dimensions,
                    embedding_profile=row["embedding_profile"],
                    text_template_version=row["text_template_version"],
                    source_doc_hash=row["source_doc_hash"],
                    embedded_text_hash=row["embedded_text_hash"],
                    generated_at=_embedding_generated_at(row),
                    stale_status="current",
                )
            )
    return hits


def _embedding_generated_at(row: EmbeddingInputRow) -> str | None:
    return (
        _row_text(row, "embedding_updated_at")
        or _row_text(row, "embedding_created_at")
        or _row_text(row, "updated_at")
        or _row_text(row, "created_at")
        or None
    )


def _semantic_matrix_from_rows(rows: list[EmbeddingInputRow], *, dimensions: int):
    if not rows:
        return np.empty((0, dimensions), dtype=np.float32)
    blobs = b"".join(row["embedding"] for row in rows)
    return np.frombuffer(blobs, dtype="<f4").reshape(len(rows), dimensions).copy()


def _resolve_semantic_query_spec(
    conn: sqlite3.Connection,
    *,
    space_id: str | None,
    provider: str | None,
    model: str | None,
    dimensions: int | None,
    embedding_profile: str | None,
    text_template_version: str | None,
    api_key_env: str | None,
    base_url: str | None,
) -> EmbeddingSpec:
    if space_id:
        return _resolve_spec_for_space_id(
            conn,
            space_id=space_id,
            provider=provider,
            model=model,
            dimensions=dimensions,
            embedding_profile=embedding_profile,
            text_template_version=text_template_version,
            api_key_env=api_key_env,
            base_url=base_url,
        )
    return _resolve_available_spec(
        conn,
        provider=provider,
        model=model,
        dimensions=dimensions,
        embedding_profile=embedding_profile,
        text_template_version=text_template_version,
        api_key_env=api_key_env,
        base_url=base_url,
    )


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


def _resolve_spec_from_db_space_id(
    db_path: Path,
    *,
    space_id: str,
    provider: str | None,
    model: str | None,
    dimensions: int | None,
    embedding_profile: str | None,
    text_template_version: str | None,
    api_key_env: str | None,
    base_url: str | None,
) -> EmbeddingSpec:
    with sqlite3.connect(db_path, timeout=60) as conn:
        conn.row_factory = sqlite3.Row
        ensure_memory_schema(conn)
        return _resolve_spec_for_space_id(
            conn,
            space_id=space_id,
            provider=provider,
            model=model,
            dimensions=dimensions,
            embedding_profile=embedding_profile,
            text_template_version=text_template_version,
            api_key_env=api_key_env,
            base_url=base_url,
        )


def _resolve_spec_for_space_id(
    conn: sqlite3.Connection,
    *,
    space_id: str,
    provider: str | None,
    model: str | None,
    dimensions: int | None,
    embedding_profile: str | None,
    text_template_version: str | None,
    api_key_env: str | None = None,
    base_url: str | None = None,
) -> EmbeddingSpec:
    row = conn.execute(
        """
        SELECT provider, model, dimensions, embedding_profile, text_template_version
        FROM memory_embedding_spaces
        WHERE space_id = ?
        """,
        (space_id,),
    ).fetchone()
    if row is None:
        raise ValueError(f"unknown embedding space_id: {space_id}")
    expected = {
        "provider": str(row["provider"]),
        "model": str(row["model"]),
        "dimensions": int(row["dimensions"]),
        "embedding_profile": str(row["embedding_profile"]),
        "text_template_version": str(row["text_template_version"]),
    }
    requested = {
        "provider": provider if provider not in {None, "", "auto", "latest"} else None,
        "model": model,
        "dimensions": dimensions,
        "embedding_profile": embedding_profile,
        "text_template_version": text_template_version,
    }
    for key, value in requested.items():
        if value is None:
            continue
        if str(value) != str(expected[key]):
            raise ValueError(
                f"--space-id {space_id} conflicts with requested {key}={value}"
            )
    return resolve_embedding_spec(
        provider=expected["provider"],
        model=expected["model"],
        dimensions=expected["dimensions"],
        embedding_profile=expected["embedding_profile"],
        text_template_version=expected["text_template_version"],
        api_key_env=api_key_env,
        base_url=base_url,
    )


def _coverage_status(row: sqlite3.Row) -> str:
    if _row_text(row, "projection_skip_reason"):
        return "ineligible"
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


def _space_id_for_spec(spec: EmbeddingSpec) -> str:
    space_defaults = _text_space_defaults_for_profile(spec.embedding_profile)
    return embedding_space_id_for_identity(
        {
            "provider": spec.provider,
            "model": spec.model,
            "dimensions": spec.dimensions,
            "distance_metric": "cosine",
            "embedding_profile": spec.embedding_profile,
            "text_template_version": spec.text_template_version,
            "modality": "text",
            "document_scope": space_defaults["document_scope"],
            "source_kind_filter": space_defaults["source_kind_filter"],
            "language_filter": space_defaults["language_filter"],
            "storage_rights_policy": space_defaults["storage_rights_policy"],
            "provider_role": TEXT_EMBEDDING_PROVIDER_ROLE,
        }
    )


def _text_space_defaults_for_profile(embedding_profile: str) -> dict[str, str]:
    if embedding_profile == "jp_multilingual":
        return {
            "document_scope": "memory_documents",
            "source_kind_filter": "local_x_text",
            "language_filter": "ja,mixed,en",
            "storage_rights_policy": "local-db-derived-text",
        }
    if embedding_profile == "code_technical":
        return {
            "document_scope": "memory_documents",
            "source_kind_filter": "technical_text",
            "language_filter": "any",
            "storage_rights_policy": "local-db-derived-text",
        }
    if embedding_profile == "relation_context":
        return {
            "document_scope": "memory_documents+relations",
            "source_kind_filter": "local_x_relation_text",
            "language_filter": "any",
            "storage_rights_policy": "local-db-derived-text",
        }
    if embedding_profile == "media_text_bridge":
        return {
            "document_scope": "media_ocr_caption_text",
            "source_kind_filter": "media_text",
            "language_filter": "any",
            "storage_rights_policy": "local-media-derived-text",
        }
    if embedding_profile == "external_fetch_text":
        return {
            "document_scope": "memory_fetch_artifacts",
            "source_kind_filter": "external_fetch_text",
            "language_filter": "any",
            "storage_rights_policy": "approved-fetch-artifact-text",
        }
    if embedding_profile == "temporal_event":
        return {
            "document_scope": "memory_documents",
            "source_kind_filter": "dated_status_text",
            "language_filter": "any",
            "storage_rights_policy": "local-db-derived-text",
        }
    return {
        "document_scope": "memory_documents",
        "source_kind_filter": "local_x_text",
        "language_filter": "any",
        "storage_rights_policy": "local-db-derived-text",
    }


def _store_embedding_projection_generation(
    conn: sqlite3.Connection,
    *,
    space_id: str,
    spec: EmbeddingSpec,
    execution_stage: str,
    selection_policy: str,
    source_count: int,
    projected_count: int,
    skipped_count: int,
    skip_reasons: dict[str, int],
) -> str:
    generation_id = _stable_id(
        "embedding-input-projection",
        space_id,
        execution_stage,
        selection_policy,
        _utc_now(),
    )
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
            "embedding_input_projection",
            space_id,
            spec.embedding_profile,
            spec.text_template_version,
            selection_policy,
            None,
            "memory_documents",
            _TEXT_PROJECTION_BUILDER_VERSION,
            json.dumps(
                {
                    "provider": spec.provider,
                    "model": spec.model,
                    "dimensions": spec.dimensions,
                    "embedding_profile": spec.embedding_profile,
                    "text_template_version": spec.text_template_version,
                    "execution_stage": execution_stage,
                    "builder_version": _TEXT_PROJECTION_BUILDER_VERSION,
                    "skip_reasons": skip_reasons,
                },
                ensure_ascii=False,
                sort_keys=True,
            ),
            "current",
            json.dumps(
                {
                    "source_count": source_count,
                    "projected_count": projected_count,
                    "skipped_count": skipped_count,
                    "skip_reasons": skip_reasons,
                },
                ensure_ascii=False,
                sort_keys=True,
            ),
            source_count,
            projected_count,
            skipped_count,
            "source_or_input_hash_change_marks_stale",
            None,
            None,
            _utc_now(),
            json.dumps(
                {
                    "contract": "embedding_input_projection_not_evidence",
                    "space_id": space_id,
                    "builder_version": _TEXT_PROJECTION_BUILDER_VERSION,
                },
                ensure_ascii=False,
                sort_keys=True,
            ),
        ),
    )
    return generation_id


def _stable_id(*parts: object) -> str:
    raw = "\0".join(str(part) for part in parts).encode()
    return hashlib.sha256(raw).hexdigest()[:24]


def _upsert_embedding(
    conn: sqlite3.Connection,
    *,
    spec: EmbeddingSpec,
    space_id: str,
    generation_id: str | None,
    doc_id: str,
    vector: list[float],
    text_hash: str,
    source_doc_hash: str,
    token_count: int,
    now: str,
    projection_id: str | None = None,
    projection_policy_version: str | None = None,
    classification_version: str | None = None,
    target_space_id: str | None = None,
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
            embedding, source_doc_hash, embedded_text_hash, created_at, updated_at,
            embedding_id, space_id, generation_id, embedded_input_hash,
            projection_id, projection_policy_version, classification_version,
            target_space_id,
            token_count, stale_status
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(
            doc_id, provider, model, dimensions,
            embedding_profile, text_template_version, space_id
        ) DO UPDATE SET
            embedding=excluded.embedding,
            source_doc_hash=excluded.source_doc_hash,
            embedded_text_hash=excluded.embedded_text_hash,
            embedded_input_hash=excluded.embedded_input_hash,
            space_id=excluded.space_id,
            generation_id=excluded.generation_id,
            token_count=excluded.token_count,
            projection_id=excluded.projection_id,
            projection_policy_version=excluded.projection_policy_version,
            classification_version=excluded.classification_version,
            target_space_id=excluded.target_space_id,
            stale_status=excluded.stale_status,
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
            _stable_id(
                "embedding",
                doc_id,
                spec.provider,
                spec.model,
                spec.dimensions,
                spec.embedding_profile,
                spec.text_template_version,
                space_id,
            ),
            space_id,
            generation_id,
            text_hash,
            projection_id,
            projection_policy_version,
            classification_version,
            target_space_id,
            token_count,
            "current",
        ),
    )


def _embedding_text(row: sqlite3.Row) -> str:
    projected = _row_text(row, "projection_text")
    if projected:
        return projected
    return memory_document_embedding_text(row)


def _source_doc_hash(row: sqlite3.Row) -> str:
    projection_source_hash = _row_text(row, "projection_source_doc_hash")
    if projection_source_hash:
        return projection_source_hash
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
        provider_role=TEXT_EMBEDDING_PROVIDER_ROLE,
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
        provider_role=TEXT_EMBEDDING_PROVIDER_ROLE,
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
