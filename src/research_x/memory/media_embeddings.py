from __future__ import annotations

import base64
import hashlib
import json
import mimetypes
import sqlite3
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np

from research_x.memory.api_budget import (
    api_units,
    budgeted_api_call,
    require_provider_quota_approval,
    rough_text_tokens,
)
from research_x.memory.embeddings import (
    _api_key,
    _gemini_model_name,
    _normalize_vector,
    _post_json,
    pack_embedding,
)
from research_x.memory.schema import ensure_memory_schema

GEMINI_MEDIA_PROVIDER = "gemini"
GEMINI_MEDIA_DEFAULT_MODEL = "gemini-embedding-2"
FIXTURE_MEDIA_PROVIDER = "fixture_media"
FIXTURE_MEDIA_DEFAULT_MODEL = "fixture-media-embedding-v1"
MEDIA_EMBEDDING_PROVIDER_ROLE = "media_embedding"
GEMINI_MEDIA_DEFAULT_DIMENSIONS = 1536
DEFAULT_MEDIA_EMBEDDING_PROFILE = "native_multimodal_media"
DEFAULT_INPUT_TEMPLATE_VERSION = "gemini-media-input-v1"
DEFAULT_MAX_FILE_BYTES = 20 * 1024 * 1024
SUPPORTED_MEDIA_MIME_TYPES = (
    "image/jpeg",
    "image/png",
    "image/webp",
    "application/pdf",
)
MEDIA_PROVIDER_QUOTA_GATE_MESSAGE = (
    "native media embedding provider API use requires ProviderExecutionPolicy, budget preflight, "
    "and the paid/quota report pause. Build or search provider media embeddings only with "
    "allow_provider_quota=True and API Budget Guard preflight."
)
MEDIA_TEXT_BRIDGE_SPACE_ID = "media.text_bridge.v1"
MEDIA_NATIVE_MULTIMODAL_SPACE_ID = "media.native_multimodal.v1"
EXTERNAL_FETCH_TEXT_SPACE_ID = "external.fetch_text.v1"
MEDIA_EXTERNAL_PROJECTION_READINESS_KIND = "typed_projection_readiness"
MEDIA_EXTERNAL_PROJECTION_READINESS_VERSION = "media-external-projection-readiness-v1"


@dataclass(frozen=True)
class ProjectionReadinessSpaceReport:
    space_id: str
    state: str
    source_records: int
    eligible_records: int
    skipped_records: int
    blocked_records: int
    skip_reasons: dict[str, int]
    blocked_reasons: dict[str, int]
    source_restoration_required: bool
    source_restoration_status: str
    source_restoration_requirements: tuple[str, ...]
    evidence_level: str
    not_evidence_reason: str
    answer_support_allowed: bool
    citation_ready: bool
    provider_gate: str | None
    storage_rights_policy: str
    projection_artifact_kind: str


@dataclass(frozen=True)
class MediaExternalProjectionReadinessReport:
    db_path: str
    status: str
    generated_at: str
    spaces: tuple[ProjectionReadinessSpaceReport, ...]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class _ProjectionReadinessRecord:
    state: str
    reason: str
    restoration_status: str


@dataclass(frozen=True)
class MediaEmbeddingSpec:
    provider: str = GEMINI_MEDIA_PROVIDER
    model: str = GEMINI_MEDIA_DEFAULT_MODEL
    dimensions: int = GEMINI_MEDIA_DEFAULT_DIMENSIONS
    embedding_profile: str = DEFAULT_MEDIA_EMBEDDING_PROFILE
    input_template_version: str = DEFAULT_INPUT_TEMPLATE_VERSION
    api_key_env: str | None = None
    base_url: str | None = None
    timeout_seconds: float = 60.0


@dataclass(frozen=True)
class MediaInput:
    media_id: str
    doc_id: str
    source_tweet_id: str
    mime_type: str
    local_path: str
    resolved_path: str
    media_url: str | None
    media_file_hash: str
    media_metadata_hash: str
    input_parts: dict[str, Any]
    input_bytes: int
    context_text: str
    skipped_reason: str | None = None
    current_status: str = "missing"


@dataclass(frozen=True)
class MediaEmbeddingEstimate:
    db_path: str
    provider: str
    model: str
    dimensions: int
    embedding_profile: str
    input_template_version: str
    media: int
    selected: int
    current: int
    missing: int
    stale_file: int
    stale_metadata: int
    skipped: int
    estimated_api_calls: int
    estimated_input_bytes: int
    by_mime_type: dict[str, int]
    skipped_reasons: dict[str, int]


@dataclass(frozen=True)
class MediaEmbeddingBuildSummary:
    db_path: str
    provider: str
    model: str
    dimensions: int
    embedding_profile: str
    input_template_version: str
    selected: int
    embedded: int
    skipped: int


@dataclass(frozen=True)
class MediaEmbeddingCoverageReport:
    db_path: str
    provider: str
    model: str
    dimensions: int
    embedding_profile: str
    input_template_version: str
    media: int
    current: int
    missing: int
    stale_file: int
    stale_metadata: int
    skipped: int
    by_mime_type: dict[str, int]
    skipped_reasons: dict[str, int]


@dataclass(frozen=True)
class MediaSearchHit:
    media_id: str
    doc_id: str
    source_tweet_id: str
    similarity: float
    evidence_level: str
    evidence_status: str
    provider: str
    model: str
    dimensions: int
    embedding_profile: str
    input_template_version: str
    evidence_role: str
    answer_support_allowed: bool
    citation_ready: bool
    promotion_gate: str
    quality_scope: str
    source_view: dict[str, Any]

    @property
    def bundle(self) -> dict[str, Any]:
        """Legacy evidence-first name for the KnowledgeOps source view."""

        restored = dict(self.source_view)
        if restored.get("media_signal_role") == "raw_media_source_view":
            restored["media_signal_role"] = "raw_media_source_bundle"
        return restored


def resolve_media_embedding_spec(
    *,
    provider: str | None = None,
    model: str | None = None,
    dimensions: int | None = None,
    embedding_profile: str | None = None,
    input_template_version: str | None = None,
    api_key_env: str | None = None,
    base_url: str | None = None,
    timeout_seconds: float = 60.0,
) -> MediaEmbeddingSpec:
    resolved_provider = (provider or GEMINI_MEDIA_PROVIDER).strip().lower()
    if resolved_provider not in {GEMINI_MEDIA_PROVIDER, FIXTURE_MEDIA_PROVIDER}:
        raise ValueError(
            "native media embeddings currently support provider=gemini or fixture_media"
        )
    resolved_dimensions = dimensions or GEMINI_MEDIA_DEFAULT_DIMENSIONS
    if resolved_dimensions <= 0:
        raise ValueError("media embedding dimensions must be positive")
    resolved_model = (
        model
        or (
            FIXTURE_MEDIA_DEFAULT_MODEL
            if resolved_provider == FIXTURE_MEDIA_PROVIDER
            else GEMINI_MEDIA_DEFAULT_MODEL
        )
    )
    return MediaEmbeddingSpec(
        provider=resolved_provider,
        model=resolved_model,
        dimensions=resolved_dimensions,
        embedding_profile=embedding_profile or DEFAULT_MEDIA_EMBEDDING_PROFILE,
        input_template_version=input_template_version or DEFAULT_INPUT_TEMPLATE_VERSION,
        api_key_env=api_key_env,
        base_url=base_url,
        timeout_seconds=timeout_seconds,
    )


def estimate_media_embedding_build(
    db_path: str | Path,
    *,
    provider: str | None = None,
    model: str | None = None,
    dimensions: int | None = None,
    embedding_profile: str | None = None,
    input_template_version: str | None = None,
    api_key_env: str | None = None,
    base_url: str | None = None,
    limit: int | None = None,
    rebuild: bool = False,
    max_file_bytes: int = DEFAULT_MAX_FILE_BYTES,
    mime_types: tuple[str, ...] = (),
) -> MediaEmbeddingEstimate:
    spec = resolve_media_embedding_spec(
        provider=provider,
        model=model,
        dimensions=dimensions,
        embedding_profile=embedding_profile,
        input_template_version=input_template_version,
        api_key_env=api_key_env,
        base_url=base_url,
    )
    inputs = _media_inputs(
        db_path,
        spec=spec,
        max_file_bytes=max_file_bytes,
        mime_types=mime_types,
        row_limit=limit,
    )
    counts = _status_counts(inputs)
    selected = _selected_inputs(inputs, rebuild=rebuild, limit=limit)
    return MediaEmbeddingEstimate(
        db_path=str(Path(db_path)),
        provider=spec.provider,
        model=spec.model,
        dimensions=spec.dimensions,
        embedding_profile=spec.embedding_profile,
        input_template_version=spec.input_template_version,
        media=len(inputs),
        selected=len(selected),
        current=counts["current"],
        missing=counts["missing"],
        stale_file=counts["stale_file"],
        stale_metadata=counts["stale_metadata"],
        skipped=counts["skipped"],
        estimated_api_calls=len(selected),
        estimated_input_bytes=sum(item.input_bytes for item in selected),
        by_mime_type=_bucket(inputs, "mime_type"),
        skipped_reasons=_skipped_reasons(inputs),
    )


def build_media_embeddings(
    db_path: str | Path,
    *,
    provider: str | None = None,
    model: str | None = None,
    dimensions: int | None = None,
    embedding_profile: str | None = None,
    input_template_version: str | None = None,
    api_key_env: str | None = None,
    base_url: str | None = None,
    limit: int | None = None,
    rebuild: bool = False,
    max_file_bytes: int = DEFAULT_MAX_FILE_BYTES,
    mime_types: tuple[str, ...] = (),
    timeout_seconds: float = 60.0,
    allow_provider_quota: bool = False,
) -> MediaEmbeddingBuildSummary:
    path = Path(db_path)
    spec = resolve_media_embedding_spec(
        provider=provider,
        model=model,
        dimensions=dimensions,
        embedding_profile=embedding_profile,
        input_template_version=input_template_version,
        api_key_env=api_key_env,
        base_url=base_url,
        timeout_seconds=timeout_seconds,
    )
    if spec.provider != FIXTURE_MEDIA_PROVIDER:
        _require_media_provider_quota_allowed(
            allow_provider_quota=allow_provider_quota,
            provider=spec.provider,
            model=spec.model,
        )
    inputs = _selected_inputs(
        _media_inputs(
            path,
            spec=spec,
            max_file_bytes=max_file_bytes,
            mime_types=mime_types,
            row_limit=limit,
        ),
        rebuild=rebuild,
        limit=limit,
    )
    embedder = _media_embedder(spec)
    embedded = 0
    with sqlite3.connect(path, timeout=60) as conn:
        conn.row_factory = sqlite3.Row
        ensure_memory_schema(conn)
        if conn.in_transaction:
            # Provider/budget guard calls use their own SQLite connection.
            conn.commit()
        for media_input in inputs:
            vector = embedder.embed_media(media_input)
            _upsert_media_embedding(conn, spec=spec, media_input=media_input, vector=vector)
            embedded += 1
        conn.commit()
    return MediaEmbeddingBuildSummary(
        db_path=str(path),
        provider=spec.provider,
        model=spec.model,
        dimensions=spec.dimensions,
        embedding_profile=spec.embedding_profile,
        input_template_version=spec.input_template_version,
        selected=len(inputs),
        embedded=embedded,
        skipped=0,
    )


def media_embedding_coverage_report(
    db_path: str | Path,
    *,
    provider: str | None = None,
    model: str | None = None,
    dimensions: int | None = None,
    embedding_profile: str | None = None,
    input_template_version: str | None = None,
    max_file_bytes: int = DEFAULT_MAX_FILE_BYTES,
    mime_types: tuple[str, ...] = (),
) -> MediaEmbeddingCoverageReport:
    spec = resolve_media_embedding_spec(
        provider=provider,
        model=model,
        dimensions=dimensions,
        embedding_profile=embedding_profile,
        input_template_version=input_template_version,
    )
    inputs = _media_inputs(
        db_path,
        spec=spec,
        max_file_bytes=max_file_bytes,
        mime_types=mime_types,
    )
    counts = _status_counts(inputs)
    return MediaEmbeddingCoverageReport(
        db_path=str(Path(db_path)),
        provider=spec.provider,
        model=spec.model,
        dimensions=spec.dimensions,
        embedding_profile=spec.embedding_profile,
        input_template_version=spec.input_template_version,
        media=len(inputs),
        current=counts["current"],
        missing=counts["missing"],
        stale_file=counts["stale_file"],
        stale_metadata=counts["stale_metadata"],
        skipped=counts["skipped"],
        by_mime_type=_bucket(inputs, "mime_type"),
        skipped_reasons=_skipped_reasons(inputs),
    )


def media_external_projection_readiness_report(
    db_path: str | Path,
    *,
    max_file_bytes: int = DEFAULT_MAX_FILE_BYTES,
    mime_types: tuple[str, ...] = (),
) -> MediaExternalProjectionReadinessReport:
    path = Path(db_path)
    generated_at = _utc_now()
    with sqlite3.connect(path, timeout=60) as conn:
        conn.row_factory = sqlite3.Row
        ensure_memory_schema(conn)
        if conn.in_transaction:
            conn.commit()
        text_bridge = _media_text_bridge_readiness(conn)
        native_media = _native_multimodal_readiness(
            path,
            conn=conn,
            max_file_bytes=max_file_bytes,
            mime_types=mime_types,
        )
        external_fetch = _external_fetch_text_readiness(conn)
    spaces = (text_bridge, native_media, external_fetch)
    return MediaExternalProjectionReadinessReport(
        db_path=str(path),
        status=_readiness_report_status(spaces),
        generated_at=generated_at,
        spaces=spaces,
    )


def store_media_external_projection_readiness(
    db_path: str | Path,
    *,
    run_id: str | None = None,
    max_file_bytes: int = DEFAULT_MAX_FILE_BYTES,
    mime_types: tuple[str, ...] = (),
) -> MediaExternalProjectionReadinessReport:
    report = media_external_projection_readiness_report(
        db_path,
        max_file_bytes=max_file_bytes,
        mime_types=mime_types,
    )
    with sqlite3.connect(Path(db_path), timeout=60) as conn:
        conn.row_factory = sqlite3.Row
        ensure_memory_schema(conn)
        for space in report.spaces:
            _store_projection_readiness_space(
                conn,
                space=space,
                generated_at=report.generated_at,
                run_id=run_id,
            )
        conn.commit()
    return report


def media_external_projection_readiness_json(
    report: MediaExternalProjectionReadinessReport,
) -> str:
    return json.dumps(report.as_dict(), ensure_ascii=False, indent=2, sort_keys=True)


def search_media_embeddings(
    db_path: str | Path,
    query: str,
    *,
    provider: str | None = None,
    model: str | None = None,
    dimensions: int | None = None,
    embedding_profile: str | None = None,
    input_template_version: str | None = None,
    api_key_env: str | None = None,
    base_url: str | None = None,
    limit: int = 10,
    timeout_seconds: float = 60.0,
    allow_provider_quota: bool = False,
) -> tuple[MediaSearchHit, ...]:
    path = Path(db_path)
    spec = resolve_media_embedding_spec(
        provider=provider,
        model=model,
        dimensions=dimensions,
        embedding_profile=embedding_profile,
        input_template_version=input_template_version,
        api_key_env=api_key_env,
        base_url=base_url,
        timeout_seconds=timeout_seconds,
    )
    if spec.provider != FIXTURE_MEDIA_PROVIDER:
        _require_media_provider_quota_allowed(
            allow_provider_quota=allow_provider_quota,
            provider=spec.provider,
            model=spec.model,
        )
    query_vector = _media_embedder(spec).embed_query(query)
    with sqlite3.connect(path, timeout=60) as conn:
        conn.row_factory = sqlite3.Row
        ensure_memory_schema(conn)
        rows = _stored_media_embedding_rows(conn, spec)
        if not rows:
            raise RuntimeError(
                "media embedding index not found for "
                f"{spec.provider}/{spec.model} dims={spec.dimensions}; "
                "run `research_x memory build-media-embeddings` first"
            )
        scored = _score_media_rows(rows, query_vector=query_vector, dimensions=spec.dimensions)
        hits = []
        for row, score in scored[: max(1, limit)]:
            source_view = restore_media_source_view(conn, str(row["media_id"]))
            signal_policy = _media_signal_policy("media_embedding_similarity")
            hits.append(
                MediaSearchHit(
                    media_id=str(row["media_id"]),
                    doc_id=str(row["doc_id"]),
                    source_tweet_id=str(row["source_tweet_id"] or ""),
                    similarity=float(score),
                    evidence_level="media_source_evidence",
                    evidence_status="unconfirmed_media_match",
                    provider=str(row["provider"]),
                    model=str(row["model"]),
                    dimensions=int(row["dimensions"]),
                    embedding_profile=str(row["embedding_profile"]),
                    input_template_version=str(row["input_template_version"]),
                    evidence_role=signal_policy["evidence_role"],
                    answer_support_allowed=signal_policy["answer_support_allowed"],
                    citation_ready=signal_policy["citation_ready"],
                    promotion_gate=signal_policy["promotion_gate"],
                    quality_scope=signal_policy["quality_scope"],
                    source_view=source_view,
                )
            )
    return tuple(hits)


def restore_media_source_view(conn: sqlite3.Connection, media_id: str) -> dict[str, Any]:
    row = conn.execute(
        """
        SELECT
            m.media_id, m.tweet_id, m.type, m.url AS media_url, m.alt_text,
            m.local_path, m.download_status, m.content_type,
            t.url AS tweet_url, t.author_screen_name, t.text AS tweet_text,
            t.created_at, t.last_observed_at,
            d.doc_id AS media_doc_id,
            b.account_id AS bookmark_account_id
        FROM media m
        JOIN tweets t ON t.tweet_id = m.tweet_id
        LEFT JOIN memory_documents d ON d.doc_id = 'media:' || m.media_id
        LEFT JOIN (
            SELECT tweet_id, MIN(account_id) AS account_id
            FROM account_bookmarks
            GROUP BY tweet_id
        ) b ON b.tweet_id = m.tweet_id
        WHERE m.media_id = ?
        """,
        (media_id,),
    ).fetchone()
    if row is None:
        return {
            "media_id": media_id,
            "evidence_level": "raw_media_match",
            "evidence_status": "unconfirmed_media_match",
            **_media_signal_policy("raw_media_source_view"),
            "restored": False,
        }
    tweet_id = str(row["tweet_id"])
    quotes = conn.execute(
        """
        SELECT parent_tweet_id, child_tweet_id, relation, child_also_bookmarked
        FROM tweet_edges
        WHERE relation = 'quote'
          AND (parent_tweet_id = ? OR child_tweet_id = ?)
        ORDER BY parent_tweet_id, child_tweet_id
        """,
        (tweet_id, tweet_id),
    ).fetchall()
    relations = conn.execute(
        """
        SELECT source_doc_id, target_doc_id, relation_type, strength, status, evidence_json
        FROM memory_relations
        WHERE source_doc_id = ? OR target_doc_id = ?
        ORDER BY relation_type, target_doc_id, source_doc_id
        """,
        (f"media:{media_id}", f"media:{media_id}"),
    ).fetchall()
    content_chunks = conn.execute(
        """
        SELECT COUNT(*)
        FROM memory_context_chunks
        WHERE source_id IN (?, ?)
        """,
        (media_id, f"media:{media_id}"),
    ).fetchone()[0]
    media_signal = _media_signal_policy("raw_media_source_view")
    return {
        "media_id": row["media_id"],
        "doc_id": row["media_doc_id"] or f"media:{media_id}",
        "tweet_id": row["tweet_id"],
        "tweet_url": row["tweet_url"],
        "media_url": row["media_url"],
        "local_path": row["local_path"],
        "download_status": row["download_status"],
        "author_screen_name": row["author_screen_name"],
        "bookmark_account_id": row["bookmark_account_id"],
        "media_type": row["type"],
        "mime_type": row["content_type"],
        "alt_text": row["alt_text"],
        "tweet_text": row["tweet_text"],
        "quote_edges": [
            {
                "parent_tweet_id": quote["parent_tweet_id"],
                "child_tweet_id": quote["child_tweet_id"],
                "relation": quote["relation"],
                "child_also_bookmarked": bool(quote["child_also_bookmarked"]),
            }
            for quote in quotes
        ],
        "relations": [
            {
                "source_doc_id": relation["source_doc_id"],
                "target_doc_id": relation["target_doc_id"],
                "relation_type": relation["relation_type"],
                "strength": relation["strength"],
                "status": relation["status"],
                "evidence": _loads_json(relation["evidence_json"]),
            }
            for relation in relations
        ],
        "evidence_level": "media_source_evidence",
        "evidence_status": "unconfirmed_media_match",
        **media_signal,
        "media_content_evidence": bool(content_chunks),
        "context_text": _media_context_text(row),
        "restored": True,
    }


def restore_media_source_bundle(conn: sqlite3.Connection, media_id: str) -> dict[str, Any]:
    """Backward-compatible citation-bundle view for existing callers.

    KnowledgeOps names the restored record a source view.  The evidence-first
    API historically exposed the same record as a source bundle, with a
    distinct signal label that is persisted in traces.  Preserve both names
    while the shared result remains candidate-only until OCR/caption context is
    promoted through the citation gate.
    """

    restored = dict(restore_media_source_view(conn, media_id))
    if restored.get("media_signal_role") == "raw_media_source_view":
        restored["media_signal_role"] = "raw_media_source_bundle"
    return restored


def _media_signal_policy(signal_role: str) -> dict[str, Any]:
    return {
        "media_signal_role": signal_role,
        "evidence_role": "media_source_candidate_signal",
        "answer_support_allowed": False,
        "citation_ready": False,
        "promotion_gate": "ocr_caption_vlm_context_chunk_citation_required",
        "quality_scope": "media_signal_boundary_not_model_quality",
    }


def _require_media_provider_quota_allowed(
    *,
    allow_provider_quota: bool,
    provider: str,
    model: str,
) -> None:
    if not allow_provider_quota:
        raise RuntimeError(MEDIA_PROVIDER_QUOTA_GATE_MESSAGE)
    require_provider_quota_approval(
        provider=provider,
        model=model,
        operation="media_embedding",
        provider_role=MEDIA_EMBEDDING_PROVIDER_ROLE,
    )


class GeminiMediaEmbedder:
    def __init__(self, spec: MediaEmbeddingSpec) -> None:
        self.spec = spec
        self.api_key = _api_key(spec.api_key_env or "GEMINI_API_KEY")

    def embed_query(self, query: str) -> list[float]:
        request = _gemini_text_embedding_request(
            self.spec,
            f"task: search result | query: {query}",
        )
        return self._embed_request(request)

    def embed_media(self, media_input: MediaInput) -> list[float]:
        data = Path(media_input.resolved_path).read_bytes()
        request = {
            "model": _gemini_model_name(self.spec.model),
            "content": {
                "parts": [
                    {"text": media_input.context_text},
                    {
                        "inlineData": {
                            "mimeType": media_input.mime_type,
                            "data": base64.b64encode(data).decode("ascii"),
                        }
                    },
                ]
            },
            "embedContentConfig": {"outputDimensionality": self.spec.dimensions},
        }
        return self._embed_request(request)

    def _embed_request(self, request: dict[str, Any]) -> list[float]:
        model_name = _gemini_model_name(self.spec.model)
        response = _post_json_budgeted(
            self.spec.base_url
            or f"https://generativelanguage.googleapis.com/v1beta/{model_name}:batchEmbedContents",
            {"requests": [request]},
            headers={"x-goog-api-key": self.api_key},
            timeout_seconds=self.spec.timeout_seconds,
            budget_provider=self.spec.provider,
            budget_model=self.spec.model,
            budget_operation="media_embedding",
            budget_units=api_units(
                calls=3,
                retries=2,
                input_tokens=rough_text_tokens(request),
                media_bytes=_request_media_bytes(request),
                documents=1,
            ),
        )
        embeddings = response.get("embeddings")
        if not isinstance(embeddings, list) or not embeddings:
            raise RuntimeError(f"Gemini media embedding response missing embeddings: {response}")
        values = embeddings[0].get("values")
        if not isinstance(values, list):
            raise RuntimeError(f"Gemini media embedding response missing values: {response}")
        return _normalize_vector([float(value) for value in values])


class FixtureMediaEmbedder:
    def __init__(self, spec: MediaEmbeddingSpec) -> None:
        self.spec = spec

    def embed_query(self, query: str) -> list[float]:
        return _fixture_vector(f"query:{query}", dimensions=self.spec.dimensions)

    def embed_media(self, media_input: MediaInput) -> list[float]:
        payload = f"media:{media_input.media_id}:{media_input.context_text}"
        return _fixture_vector(payload, dimensions=self.spec.dimensions)


def _media_embedder(spec: MediaEmbeddingSpec) -> GeminiMediaEmbedder | FixtureMediaEmbedder:
    if spec.provider == FIXTURE_MEDIA_PROVIDER:
        return FixtureMediaEmbedder(spec)
    return GeminiMediaEmbedder(spec)


def _fixture_vector(value: str, *, dimensions: int) -> list[float]:
    digest = hashlib.sha256(value.encode("utf-8")).digest()
    raw = [
        ((digest[index % len(digest)] / 255.0) * 2.0) - 1.0
        for index in range(dimensions)
    ]
    return _normalize_vector(raw)


def media_embedding_estimate_json(estimate: MediaEmbeddingEstimate) -> str:
    return json.dumps(asdict(estimate), ensure_ascii=False, indent=2, sort_keys=True)


def media_embedding_coverage_json(report: MediaEmbeddingCoverageReport) -> str:
    return json.dumps(asdict(report), ensure_ascii=False, indent=2, sort_keys=True)


def media_search_json(hits: tuple[MediaSearchHit, ...]) -> str:
    return json.dumps([asdict(hit) for hit in hits], ensure_ascii=False, indent=2, sort_keys=True)


def summary_as_dict(summary: MediaEmbeddingBuildSummary) -> dict[str, Any]:
    return asdict(summary)


def format_media_embedding_estimate(estimate: MediaEmbeddingEstimate) -> str:
    return "\n".join(
        (
            f"db: {estimate.db_path}",
            (
                "spec: "
                f"{estimate.provider}/{estimate.model} dims={estimate.dimensions} "
                f"profile={estimate.embedding_profile} template={estimate.input_template_version}"
            ),
            (
                "media: "
                f"{estimate.media} selected={estimate.selected} current={estimate.current} "
                f"missing={estimate.missing} stale_file={estimate.stale_file} "
                f"stale_metadata={estimate.stale_metadata} skipped={estimate.skipped}"
            ),
            (
                "input estimate: "
                f"bytes={estimate.estimated_input_bytes} "
                f"api_calls={estimate.estimated_api_calls}"
            ),
            (
                "by_mime_type: "
                f"{json.dumps(estimate.by_mime_type, ensure_ascii=False, sort_keys=True)}"
            ),
            (
                "skipped_reasons: "
                f"{json.dumps(estimate.skipped_reasons, ensure_ascii=False, sort_keys=True)}"
            ),
        )
    )


def format_media_embedding_coverage(report: MediaEmbeddingCoverageReport) -> str:
    return "\n".join(
        (
            f"db: {report.db_path}",
            (
                "spec: "
                f"{report.provider}/{report.model} dims={report.dimensions} "
                f"profile={report.embedding_profile} template={report.input_template_version}"
            ),
            (
                "media: "
                f"{report.media} current={report.current} missing={report.missing} "
                f"stale_file={report.stale_file} stale_metadata={report.stale_metadata} "
                f"skipped={report.skipped}"
            ),
            f"by_mime_type: {json.dumps(report.by_mime_type, ensure_ascii=False, sort_keys=True)}",
            (
                "skipped_reasons: "
                f"{json.dumps(report.skipped_reasons, ensure_ascii=False, sort_keys=True)}"
            ),
        )
    )


def format_media_search(hits: tuple[MediaSearchHit, ...]) -> str:
    lines = []
    for index, hit in enumerate(hits, start=1):
        source_view = hit.source_view
        lines.append(
            f"{index}. score={hit.similarity:.4f} media_id={hit.media_id} "
            f"tweet_id={hit.source_tweet_id} evidence={hit.evidence_status}"
        )
        lines.append(f"   tweet_url={source_view.get('tweet_url') or ''}")
        lines.append(f"   media_url={source_view.get('media_url') or ''}")
        lines.append(f"   local_path={source_view.get('local_path') or ''}")
        lines.append(f"   author=@{source_view.get('author_screen_name') or ''}")
    return "\n".join(lines)


def _media_text_bridge_readiness(conn: sqlite3.Connection) -> ProjectionReadinessSpaceReport:
    records: list[_ProjectionReadinessRecord] = []
    source_records = 0
    has_media_sources = _table_exists(conn, "media") and _table_exists(conn, "tweets")
    if has_media_sources:
        for row in conn.execute(
            """
            SELECT m.media_id, m.tweet_id, m.alt_text, t.tweet_id AS restored_tweet_id
            FROM media m
            LEFT JOIN tweets t ON t.tweet_id = m.tweet_id
            ORDER BY m.media_id
            """
        ).fetchall():
            alt_text = str(row["alt_text"] or "").strip()
            if not alt_text:
                continue
            source_records += 1
            if not row["restored_tweet_id"]:
                records.append(
                    _ProjectionReadinessRecord(
                        state="blocked",
                        reason="media_alt_text_source_not_restored",
                        restoration_status="source_not_restored",
                    )
                )
                continue
            records.append(
                _ProjectionReadinessRecord(
                    state="eligible",
                    reason="media_alt_text_restorable",
                    restoration_status="media_to_tweet_restorable",
                )
            )
    if _table_exists(conn, "memory_ocr_texts"):
        if has_media_sources:
            rows = conn.execute(
                """
                SELECT
                    o.text_id, o.media_id, o.text_profile, o.raw_ocr_text,
                    o.normalized_text, o.corrected_text, o.source_image_hash,
                    o.region_hash, m.media_id AS restored_media_id,
                    t.tweet_id AS restored_tweet_id
                FROM memory_ocr_texts o
                LEFT JOIN media m ON m.media_id = o.media_id
                LEFT JOIN tweets t ON t.tweet_id = m.tweet_id
                ORDER BY o.created_at, o.text_id
                """
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT
                    text_id, media_id, text_profile, raw_ocr_text,
                    normalized_text, corrected_text, source_image_hash,
                    region_hash, NULL AS restored_media_id,
                    NULL AS restored_tweet_id
                FROM memory_ocr_texts
                ORDER BY created_at, text_id
                """
            ).fetchall()
        for row in rows:
            source_records += 1
            text = _ocr_projection_text(row)
            if not text:
                records.append(
                    _ProjectionReadinessRecord(
                        state="skipped",
                        reason="empty_media_text",
                        restoration_status="not_applicable",
                    )
                )
                continue
            if not has_media_sources:
                records.append(
                    _ProjectionReadinessRecord(
                        state="blocked",
                        reason="media_source_tables_missing",
                        restoration_status="source_not_restored",
                    )
                )
                continue
            if not row["restored_media_id"] or not row["restored_tweet_id"]:
                records.append(
                    _ProjectionReadinessRecord(
                        state="blocked",
                        reason="media_text_source_not_restored",
                        restoration_status="source_not_restored",
                    )
                )
                continue
            if not row["source_image_hash"] or not row["region_hash"]:
                records.append(
                    _ProjectionReadinessRecord(
                        state="blocked",
                        reason="media_text_hash_missing",
                        restoration_status="source_hash_missing",
                    )
                )
                continue
            records.append(
                _ProjectionReadinessRecord(
                    state="eligible",
                    reason="media_text_restorable",
                    restoration_status="media_text_to_source_restorable",
                )
            )
    if not records:
        records.append(
            _ProjectionReadinessRecord(
                state="skipped",
                reason="no_media_text_candidates",
                restoration_status="not_applicable",
            )
        )
    return _aggregate_space_readiness(
        space_id=MEDIA_TEXT_BRIDGE_SPACE_ID,
        records=tuple(records),
        source_records=source_records,
        source_restoration_requirements=(
            "media_id",
            "tweet_id",
            "source_doc_hash_or_media_hash",
            "context_chunk",
            "citation_annotation",
        ),
        evidence_level="candidate",
        not_evidence_reason="media_text_bridge_candidate_requires_source_bundle_context_citation",
        provider_gate=None,
        storage_rights_policy="local-media-derived-text",
        projection_artifact_kind="media_text_projection_input",
    )


def _native_multimodal_readiness(
    db_path: Path,
    *,
    conn: sqlite3.Connection,
    max_file_bytes: int,
    mime_types: tuple[str, ...],
) -> ProjectionReadinessSpaceReport:
    records: list[_ProjectionReadinessRecord] = []
    if not _table_exists(conn, "media") or not _table_exists(conn, "tweets"):
        records.append(
            _ProjectionReadinessRecord(
                state="skipped",
                reason="no_media_source_tables",
                restoration_status="not_applicable",
            )
        )
        source_records = 0
    else:
        spec = resolve_media_embedding_spec()
        inputs = _media_inputs(
            db_path,
            spec=spec,
            max_file_bytes=max_file_bytes,
            mime_types=mime_types,
        )
        source_records = len(inputs)
        for media_input in inputs:
            if media_input.skipped_reason:
                records.append(
                    _ProjectionReadinessRecord(
                        state="skipped",
                        reason=media_input.skipped_reason,
                        restoration_status="not_applicable",
                    )
                )
                continue
            records.append(
                _ProjectionReadinessRecord(
                    state="eligible",
                    reason="native_media_local_file_ready_provider_gate_required",
                    restoration_status="media_to_tweet_restorable",
                )
            )
        if not records:
            records.append(
                _ProjectionReadinessRecord(
                    state="skipped",
                    reason="no_media_rows",
                    restoration_status="not_applicable",
                )
            )
    return _aggregate_space_readiness(
        space_id=MEDIA_NATIVE_MULTIMODAL_SPACE_ID,
        records=tuple(records),
        source_records=source_records,
        source_restoration_requirements=(
            "media_id",
            "tweet_id",
            "media_file_hash",
            "source_bundle",
            "context_chunk",
            "citation_annotation",
        ),
        evidence_level="candidate",
        not_evidence_reason="native_media_vector_candidate_only_context_citation_required",
        provider_gate="provider_authorization_required_before_native_media_embedding",
        storage_rights_policy="provider-upload-reviewed-media",
        projection_artifact_kind="native_media_reference",
    )


def _external_fetch_text_readiness(conn: sqlite3.Connection) -> ProjectionReadinessSpaceReport:
    records: list[_ProjectionReadinessRecord] = []
    source_records = 0
    if _table_exists(conn, "memory_fetch_artifacts"):
        for row in conn.execute(
            """
            SELECT
                artifact_id, response_hash, extracted_text_hash,
                prompt_injection_status, storage_rights, metadata_json
            FROM memory_fetch_artifacts
            ORDER BY fetched_at, artifact_id
            """
        ).fetchall():
            source_records += 1
            metadata = _loads_json(row["metadata_json"]) or {}
            prompt_status = str(row["prompt_injection_status"] or "")
            storage_rights = str(row["storage_rights"] or "").strip().lower()
            if not row["response_hash"] or not row["extracted_text_hash"]:
                records.append(
                    _ProjectionReadinessRecord(
                        state="blocked",
                        reason="fetch_artifact_hash_missing",
                        restoration_status="source_hash_missing",
                    )
                )
                continue
            if prompt_status != "passed":
                records.append(
                    _ProjectionReadinessRecord(
                        state="blocked",
                        reason="prompt_injection_review_not_passed",
                        restoration_status="review_required",
                    )
                )
                continue
            if not (
                metadata.get("source_bundle_id") or metadata.get("source_restore_id")
            ) or metadata.get("lineage_status") != "restored":
                records.append(
                    _ProjectionReadinessRecord(
                        state="blocked",
                        reason="fetch_artifact_source_not_restored",
                        restoration_status="source_not_restored",
                    )
                )
                continue
            if not storage_rights or storage_rights == "unknown":
                records.append(
                    _ProjectionReadinessRecord(
                        state="blocked",
                        reason="fetch_artifact_storage_rights_not_approved",
                        restoration_status="storage_rights_not_approved",
                    )
                )
                continue
            records.append(
                _ProjectionReadinessRecord(
                    state="eligible",
                    reason="fetch_artifact_hash_review_lineage_ready",
                    restoration_status="fetch_artifact_restored",
                )
            )
    if not records:
        records.append(
            _ProjectionReadinessRecord(
                state="skipped",
                reason="no_fetch_artifacts",
                restoration_status="not_applicable",
            )
        )
    return _aggregate_space_readiness(
        space_id=EXTERNAL_FETCH_TEXT_SPACE_ID,
        records=tuple(records),
        source_records=source_records,
        source_restoration_requirements=(
            "fetch_artifact_id",
            "response_hash",
            "extracted_text_hash",
            "source_bundle_id|source_restore_id",
            "prompt_injection_passed",
        ),
        evidence_level="candidate",
        not_evidence_reason="external_fetch_text_candidate_requires_context_citation",
        provider_gate=None,
        storage_rights_policy="approved-fetch-artifact-text",
        projection_artifact_kind="external_fetch_text_section",
    )


def _aggregate_space_readiness(
    *,
    space_id: str,
    records: tuple[_ProjectionReadinessRecord, ...],
    source_records: int,
    source_restoration_requirements: tuple[str, ...],
    evidence_level: str,
    not_evidence_reason: str,
    provider_gate: str | None,
    storage_rights_policy: str,
    projection_artifact_kind: str,
) -> ProjectionReadinessSpaceReport:
    eligible = sum(1 for record in records if record.state == "eligible")
    skipped = sum(1 for record in records if record.state == "skipped")
    blocked = sum(1 for record in records if record.state == "blocked")
    return ProjectionReadinessSpaceReport(
        space_id=space_id,
        state=_space_state(eligible=eligible, blocked=blocked),
        source_records=source_records,
        eligible_records=eligible,
        skipped_records=skipped,
        blocked_records=blocked,
        skip_reasons=_reason_counts(records, state="skipped"),
        blocked_reasons=_reason_counts(records, state="blocked"),
        source_restoration_required=True,
        source_restoration_status=_source_restoration_status(
            eligible=eligible,
            skipped=skipped,
            blocked=blocked,
        ),
        source_restoration_requirements=source_restoration_requirements,
        evidence_level=evidence_level,
        not_evidence_reason=not_evidence_reason,
        answer_support_allowed=False,
        citation_ready=False,
        provider_gate=provider_gate,
        storage_rights_policy=storage_rights_policy,
        projection_artifact_kind=projection_artifact_kind,
    )


def _store_projection_readiness_space(
    conn: sqlite3.Connection,
    *,
    space: ProjectionReadinessSpaceReport,
    generated_at: str,
    run_id: str | None,
) -> None:
    payload = asdict(space)
    generation_id = _projection_readiness_generation_id(space, generated_at=generated_at)
    coverage = {
        "state": space.state,
        "source_records": space.source_records,
        "eligible_records": space.eligible_records,
        "skipped_records": space.skipped_records,
        "blocked_records": space.blocked_records,
        "skip_reasons": space.skip_reasons,
        "blocked_reasons": space.blocked_reasons,
        "source_restoration_required": space.source_restoration_required,
        "source_restoration_status": space.source_restoration_status,
    }
    manifest = {
        "space_id": space.space_id,
        "projection_artifact_kind": space.projection_artifact_kind,
        "source_restoration_requirements": list(space.source_restoration_requirements),
        "not_evidence_reason": space.not_evidence_reason,
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
            MEDIA_EXTERNAL_PROJECTION_READINESS_KIND,
            space.space_id,
            space.space_id,
            MEDIA_EXTERNAL_PROJECTION_READINESS_VERSION,
            "local_readiness_classification",
            None,
            space.projection_artifact_kind,
            MEDIA_EXTERNAL_PROJECTION_READINESS_VERSION,
            json.dumps(manifest, ensure_ascii=False, sort_keys=True),
            space.state,
            json.dumps(coverage, ensure_ascii=False, sort_keys=True),
            space.source_records,
            space.eligible_records,
            space.skipped_records,
            "source_or_artifact_hash_change_reclassifies_readiness",
            None,
            run_id,
            generated_at,
            json.dumps(payload, ensure_ascii=False, sort_keys=True),
        ),
    )


def _projection_readiness_generation_id(
    space: ProjectionReadinessSpaceReport,
    *,
    generated_at: str,
) -> str:
    material = json.dumps(
        {"generated_at": generated_at, "space": asdict(space)},
        ensure_ascii=False,
        sort_keys=True,
    )
    digest = hashlib.blake2b(material.encode("utf-8"), digest_size=16).hexdigest()
    return f"projection-readiness-{digest}"


def _ocr_projection_text(row: sqlite3.Row) -> str:
    profile = str(row["text_profile"] or "")
    if profile == "corrected_text":
        return str(row["corrected_text"] or row["normalized_text"] or "").strip()
    return str(row["normalized_text"] or row["corrected_text"] or row["raw_ocr_text"] or "").strip()


def _space_state(*, eligible: int, blocked: int) -> str:
    if eligible:
        return "eligible"
    if blocked:
        return "blocked"
    return "skipped"


def _source_restoration_status(*, eligible: int, skipped: int, blocked: int) -> str:
    if eligible and not blocked:
        return "restorable"
    if eligible and blocked:
        return "partial"
    if blocked:
        return "blocked"
    if skipped:
        return "not_applicable"
    return "unknown"


def _readiness_report_status(spaces: tuple[ProjectionReadinessSpaceReport, ...]) -> str:
    if any(space.blocked_records for space in spaces):
        return "has_blocked_records"
    if any(space.eligible_records for space in spaces):
        return "has_eligible_records"
    return "all_skipped"


def _reason_counts(
    records: tuple[_ProjectionReadinessRecord, ...],
    *,
    state: str,
) -> dict[str, int]:
    counts: dict[str, int] = {}
    for record in records:
        if record.state != state:
            continue
        counts[record.reason] = counts.get(record.reason, 0) + 1
    return dict(sorted(counts.items()))


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        """
        SELECT 1
        FROM sqlite_master
        WHERE type IN ('table', 'view')
          AND name = ?
        """,
        (table,),
    ).fetchone()
    return row is not None


def _media_inputs(
    db_path: str | Path,
    *,
    spec: MediaEmbeddingSpec,
    max_file_bytes: int,
    mime_types: tuple[str, ...],
    row_limit: int | None = None,
) -> tuple[MediaInput, ...]:
    path = Path(db_path)
    with sqlite3.connect(path, timeout=60) as conn:
        conn.row_factory = sqlite3.Row
        ensure_memory_schema(conn)
        sql = """
            SELECT
                m.media_id, m.tweet_id, m.type, m.url AS media_url, m.alt_text,
                m.local_path, m.download_status, m.content_type,
                t.url AS tweet_url, t.author_screen_name, t.text AS tweet_text,
                e.media_file_hash AS embedded_file_hash,
                e.media_metadata_hash AS embedded_metadata_hash
            FROM media m
            JOIN tweets t ON t.tweet_id = m.tweet_id
            LEFT JOIN memory_media_embeddings e
              ON e.media_id = m.media_id
             AND e.provider = ?
             AND e.model = ?
             AND e.dimensions = ?
             AND e.embedding_profile = ?
             AND e.input_template_version = ?
            ORDER BY t.last_observed_at DESC, m.media_id
            """
        params: list[Any] = [
            spec.provider,
            spec.model,
            spec.dimensions,
            spec.embedding_profile,
            spec.input_template_version,
        ]
        if row_limit is not None and row_limit > 0:
            sql += " LIMIT ?"
            params.append(row_limit)
        rows = conn.execute(sql, params).fetchall()
    allowed = tuple(mime_types) if mime_types else SUPPORTED_MEDIA_MIME_TYPES
    return tuple(
        _resolve_media_input(
            row,
            db_path=path,
            allowed_mime_types=allowed,
            max_file_bytes=max_file_bytes,
        )
        for row in rows
    )


def _resolve_media_input(
    row: sqlite3.Row,
    *,
    db_path: Path,
    allowed_mime_types: tuple[str, ...],
    max_file_bytes: int,
) -> MediaInput:
    local_path = str(row["local_path"] or "")
    resolved = _resolve_media_path(local_path, db_path=db_path)
    mime_type = _resolve_mime_type(row, resolved)
    metadata_hash = _media_metadata_hash(row)
    skipped_reason = None
    file_hash = ""
    input_bytes = 0
    if not local_path:
        skipped_reason = "missing_local_path"
    elif resolved is None:
        skipped_reason = "missing_file"
    elif not mime_type or mime_type not in allowed_mime_types:
        skipped_reason = "unsupported_mime_type"
    else:
        input_bytes = resolved.stat().st_size
        if input_bytes <= 0:
            skipped_reason = "zero_byte_file"
        elif input_bytes > max_file_bytes:
            skipped_reason = "file_too_large"
        else:
            file_hash = _file_hash(resolved)
    if skipped_reason:
        status = "skipped"
    elif not row["embedded_file_hash"]:
        status = "missing"
    elif row["embedded_file_hash"] != file_hash:
        status = "stale_file"
    elif row["embedded_metadata_hash"] != metadata_hash:
        status = "stale_metadata"
    else:
        status = "current"
    context_text = _media_context_text(row)
    input_parts = {
        "template": DEFAULT_INPUT_TEMPLATE_VERSION,
        "text": context_text,
        "media": {
            "media_id": row["media_id"],
            "mime_type": mime_type,
            "local_path": local_path,
            "media_file_hash": file_hash,
            "bytes": input_bytes,
        },
    }
    return MediaInput(
        media_id=str(row["media_id"]),
        doc_id=f"media:{row['media_id']}",
        source_tweet_id=str(row["tweet_id"]),
        mime_type=mime_type or "",
        local_path=local_path,
        resolved_path=str(resolved) if resolved else "",
        media_url=row["media_url"],
        media_file_hash=file_hash,
        media_metadata_hash=metadata_hash,
        input_parts=input_parts,
        input_bytes=input_bytes,
        context_text=context_text,
        skipped_reason=skipped_reason,
        current_status=status,
    )


def _selected_inputs(
    inputs: tuple[MediaInput, ...],
    *,
    rebuild: bool,
    limit: int | None,
) -> tuple[MediaInput, ...]:
    selected = [
        item
        for item in inputs
        if item.skipped_reason is None and (rebuild or item.current_status != "current")
    ]
    if limit is not None and limit > 0:
        selected = selected[:limit]
    return tuple(selected)


def _upsert_media_embedding(
    conn: sqlite3.Connection,
    *,
    spec: MediaEmbeddingSpec,
    media_input: MediaInput,
    vector: list[float],
) -> None:
    if len(vector) != spec.dimensions:
        raise RuntimeError(
            f"media embedding provider returned {len(vector)} dimensions for "
            f"{spec.provider}/{spec.model}, expected {spec.dimensions}"
        )
    now = _utc_now()
    conn.execute(
        """
        INSERT INTO memory_media_embeddings (
            media_id, doc_id, source_tweet_id, provider, model, dimensions,
            embedding_profile, input_template_version, embedding, mime_type, local_path,
            media_url, media_file_hash, media_metadata_hash, input_parts_json,
            created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(
            media_id, provider, model, dimensions,
            embedding_profile, input_template_version
        ) DO UPDATE SET
            doc_id=excluded.doc_id,
            source_tweet_id=excluded.source_tweet_id,
            embedding=excluded.embedding,
            mime_type=excluded.mime_type,
            local_path=excluded.local_path,
            media_url=excluded.media_url,
            media_file_hash=excluded.media_file_hash,
            media_metadata_hash=excluded.media_metadata_hash,
            input_parts_json=excluded.input_parts_json,
            updated_at=excluded.updated_at
        """,
        (
            media_input.media_id,
            media_input.doc_id,
            media_input.source_tweet_id,
            spec.provider,
            spec.model,
            spec.dimensions,
            spec.embedding_profile,
            spec.input_template_version,
            pack_embedding(_normalize_vector(vector)),
            media_input.mime_type,
            media_input.local_path,
            media_input.media_url,
            media_input.media_file_hash,
            media_input.media_metadata_hash,
            json.dumps(media_input.input_parts, ensure_ascii=False, sort_keys=True),
            now,
            now,
        ),
    )


def _stored_media_embedding_rows(
    conn: sqlite3.Connection,
    spec: MediaEmbeddingSpec,
) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT
            media_id, doc_id, source_tweet_id, provider, model, dimensions,
            embedding_profile, input_template_version, embedding
        FROM memory_media_embeddings
        WHERE provider = ?
          AND model = ?
          AND dimensions = ?
          AND embedding_profile = ?
          AND input_template_version = ?
        ORDER BY updated_at DESC, media_id
        """,
        (
            spec.provider,
            spec.model,
            spec.dimensions,
            spec.embedding_profile,
            spec.input_template_version,
        ),
    ).fetchall()


def _score_media_rows(
    rows: list[sqlite3.Row],
    *,
    query_vector: list[float],
    dimensions: int,
) -> list[tuple[sqlite3.Row, float]]:
    query = np.asarray(query_vector[:dimensions], dtype=np.float32)
    matrix = np.frombuffer(
        b"".join(row["embedding"] for row in rows),
        dtype="<f4",
    ).reshape(len(rows), dimensions)
    scores = matrix @ query
    ranked = sorted(zip(rows, scores, strict=True), key=lambda item: float(item[1]), reverse=True)
    return [(row, float(score)) for row, score in ranked]


def _gemini_text_embedding_request(
    spec: MediaEmbeddingSpec,
    text: str,
) -> dict[str, Any]:
    return {
        "model": _gemini_model_name(spec.model),
        "content": {"parts": [{"text": text}]},
        "embedContentConfig": {"outputDimensionality": spec.dimensions},
    }


def _post_json_budgeted(
    url: str,
    payload: dict[str, Any],
    *,
    headers: dict[str, str],
    timeout_seconds: float,
    budget_provider: str,
    budget_model: str,
    budget_operation: str,
    budget_units: dict[str, int | float],
) -> dict[str, Any]:
    with budgeted_api_call(
        provider=budget_provider,
        model=budget_model,
        provider_role=MEDIA_EMBEDDING_PROVIDER_ROLE,
        operation=budget_operation,
        units=budget_units,
        request_payload=payload,
        metadata={"url": url},
    ):
        return _post_json(
            url,
            payload,
            headers=headers,
            timeout_seconds=timeout_seconds,
        )


def _request_media_bytes(request: dict[str, Any]) -> int:
    parts = request.get("content", {}).get("parts", [])
    total = 0
    if isinstance(parts, list):
        for part in parts:
            if not isinstance(part, dict):
                continue
            inline = part.get("inlineData") or part.get("inline_data")
            if isinstance(inline, dict):
                data = inline.get("data")
                if isinstance(data, str):
                    total += len(data) * 3 // 4
    return total


def _media_context_text(row: sqlite3.Row) -> str:
    parts = [
        "task: search result | document context:",
        f"media_id: {row['media_id']}",
        f"tweet_id: {row['tweet_id']}",
        f"media_type: {row['type'] or ''}",
        f"media_url: {row['media_url'] or ''}",
        f"local_path: {row['local_path'] or ''}",
        f"download_status: {row['download_status'] or ''}",
        f"author: @{row['author_screen_name'] or ''}",
        f"tweet_url: {row['tweet_url'] or ''}",
        f"alt_text: {row['alt_text'] or ''}",
        f"tweet_text: {row['tweet_text'] or ''}",
    ]
    return "\n".join(part for part in parts if part.strip())


def _media_metadata_hash(row: sqlite3.Row) -> str:
    payload = {
        "media_id": row["media_id"],
        "tweet_id": row["tweet_id"],
        "type": row["type"],
        "url": row["media_url"],
        "local_path": row["local_path"],
        "download_status": row["download_status"],
        "alt_text": row["alt_text"],
        "tweet_text": row["tweet_text"],
    }
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()


def _resolve_media_path(local_path: str, *, db_path: Path) -> Path | None:
    if not local_path:
        return None
    raw = Path(local_path)
    candidates = [raw] if raw.is_absolute() else [raw, Path.cwd() / raw, db_path.parent / raw]
    for candidate in candidates:
        if candidate.exists() and candidate.is_file():
            return candidate
    return None


def _resolve_mime_type(row: sqlite3.Row, path: Path | None) -> str:
    raw = str(row["content_type"] or "").strip().lower()
    if raw:
        return "image/jpeg" if raw == "image/jpg" else raw
    if path:
        guessed, _ = mimetypes.guess_type(str(path))
        return guessed or ""
    return ""


def _file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _status_counts(inputs: tuple[MediaInput, ...]) -> dict[str, int]:
    counts = {
        "current": 0,
        "missing": 0,
        "stale_file": 0,
        "stale_metadata": 0,
        "skipped": 0,
    }
    for item in inputs:
        counts[item.current_status] = counts.get(item.current_status, 0) + 1
    return counts


def _bucket(inputs: tuple[MediaInput, ...], field: str) -> dict[str, int]:
    result: dict[str, int] = {}
    for item in inputs:
        value = str(getattr(item, field) or "unknown")
        result[value] = result.get(value, 0) + 1
    return dict(sorted(result.items()))


def _skipped_reasons(inputs: tuple[MediaInput, ...]) -> dict[str, int]:
    result: dict[str, int] = {}
    for item in inputs:
        if item.skipped_reason:
            result[item.skipped_reason] = result.get(item.skipped_reason, 0) + 1
    return dict(sorted(result.items()))


def _loads_json(value: str | None) -> Any:
    if not value:
        return None
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return None


def _utc_now() -> str:
    return datetime.now(tz=UTC).isoformat()
