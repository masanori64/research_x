from __future__ import annotations

import base64
import hashlib
import json
import mimetypes
import sqlite3
import uuid
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from research_x.memory.api_budget import (
    api_units,
    budgeted_api_call,
    require_provider_quota_approval,
)
from research_x.memory.embeddings import _api_key, _post_json
from research_x.memory.media_embeddings import restore_media_source_view
from research_x.memory.schema import ensure_memory_schema

OCR_PROVIDER_FAKE = "fake"
OCR_PROVIDER_LOCAL = "local"
OCR_PROVIDER_MISTRAL = "mistral"
OCR_DEFAULT_PROVIDER = OCR_PROVIDER_FAKE
OCR_DEFAULT_MODEL = "mistral-ocr-2512"
OCR_LOCAL_DEFAULT_MODEL = "local-metadata-ocr-v1"
OCR_DEFAULT_PROFILE = "ocr-evidence-v1"
OCR_EXTRACTOR_VERSION = "ocr-evidence-v1"
OCR_REGION_DETECTOR_VERSION = "ocr-local-region-v1"
OCR_SECOND_PASS_PROVIDER = "local_quality"
OCR_SECOND_PASS_MODEL = "rule-based-second-pass-v1"
DEFAULT_SAMPLE_POLICY = "stratified"
DEFAULT_MAX_FILE_BYTES = 20 * 1024 * 1024
MIN_CONFIDENCE_FOR_CITATION = 0.45
SUPPORTED_OCR_MIME_TYPES = (
    "image/jpeg",
    "image/png",
    "image/webp",
    "application/pdf",
)
LOCAL_OCR_PROVIDER_FAMILIES = {OCR_PROVIDER_FAKE, OCR_PROVIDER_LOCAL}
SUPPORTED_OCR_PROVIDERS = {
    OCR_PROVIDER_FAKE,
    OCR_PROVIDER_LOCAL,
    OCR_PROVIDER_MISTRAL,
}


@dataclass(frozen=True)
class OcrRegion:
    region_id: str
    media_id: str
    source_tweet_id: str
    page_index: int
    region_index: int
    reading_order: int
    bbox: dict[str, int | float | str]
    region_hash: str
    source_image_hash: str
    local_path: str
    resolved_path: str
    crop_path: str
    mime_type: str
    quality_flags: dict[str, Any]
    strata: tuple[str, ...]
    engine_route: str
    detector_version: str
    status: str
    skip_reason: str | None
    media_url: str | None
    tweet_url: str | None
    alt_text: str | None
    tweet_text: str | None

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["strata"] = list(self.strata)
        return payload


@dataclass(frozen=True)
class OcrEstimate:
    db_path: str
    sample_policy: str
    limit: int | None
    media: int
    selected: int
    skipped: int
    by_strata: dict[str, int]
    by_engine_route: dict[str, int]
    skipped_reasons: dict[str, int]
    by_quality_flag: dict[str, int]
    estimated_pages: int

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class OcrResult:
    raw_text: str
    normalized_text: str
    confidence: float | None
    corrected_text: str | None = None
    metadata: dict[str, Any] | None = None


@dataclass(frozen=True)
class OcrBuildSummary:
    db_path: str
    provider: str
    model: str
    ocr_profile: str
    ocr_run_id: str
    selected: int
    processed: int
    skipped: int
    promoted_chunks: int
    second_pass_candidates: int

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class OcrCoverage:
    db_path: str
    regions: int
    texts: int
    context_chunks: int
    second_pass_candidates: int
    by_provider_model: dict[str, int]
    by_evidence_status: dict[str, int]
    by_text_profile: dict[str, int]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class OcrPromotionSummary:
    db_path: str
    promoted_chunks: int
    skipped: int

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class OcrSecondPassSummary:
    db_path: str
    candidates: int
    corrected_profiles: int

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class MediaObservationSummary:
    db_path: str
    imported: int
    promoted_chunks: int

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class MediaObservationCoverage:
    db_path: str
    texts: int
    chunks: int
    visual_annotations: int

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


class OcrProvider(Protocol):
    provider_id: str

    def extract(self, region: OcrRegion, *, model: str, timeout_seconds: float) -> OcrResult:
        """Extract OCR text from a resolved media region."""


class FakeOcrProvider:
    provider_id = OCR_PROVIDER_FAKE

    def extract(self, region: OcrRegion, *, model: str, timeout_seconds: float) -> OcrResult:
        text = f"Fake OCR text for {region.media_id}: 画像 OCR robot diagram label"
        return OcrResult(
            raw_text=text,
            normalized_text=_normalize_ocr_text(text),
            confidence=0.93,
            metadata={"fixture": True, "engine_route": region.engine_route},
        )


class LocalMetadataOcrProvider:
    provider_id = OCR_PROVIDER_LOCAL

    def extract(self, region: OcrRegion, *, model: str, timeout_seconds: float) -> OcrResult:
        text_parts = _local_ocr_candidate_text_parts(region)
        raw_text = "\n".join(text_parts)
        return OcrResult(
            raw_text=raw_text,
            normalized_text=_normalize_ocr_text(raw_text),
            confidence=_local_ocr_confidence(region, text_parts),
            metadata={
                "provider_family": "local_ocr",
                "engine_family": _local_ocr_engine_family(region),
                "engine_route": region.engine_route,
                "model": model,
                "local_only": True,
                "network_allowed": False,
                "provider_quota_required": False,
                "fixture": False,
                "candidate_source": _local_ocr_candidate_sources(region),
                "text_likelihood": region.quality_flags.get("text_likelihood"),
                "estimated_text_density": region.quality_flags.get("estimated_text_density"),
                "metadata_backed_fallback": True,
            },
        )


class MistralOcrProvider:
    provider_id = OCR_PROVIDER_MISTRAL

    def __init__(
        self,
        *,
        api_key_env: str = "MISTRAL_API_KEY",
        base_url: str | None = None,
    ) -> None:
        self.api_key = _api_key(api_key_env)
        self.base_url = base_url or "https://api.mistral.ai/v1/ocr"

    def extract(self, region: OcrRegion, *, model: str, timeout_seconds: float) -> OcrResult:
        data_url = _data_url(region.resolved_path, region.mime_type)
        document_key = "document_url" if region.mime_type == "application/pdf" else "image_url"
        payload = {
            "model": model,
            "document": {
                "type": document_key,
                document_key: data_url,
            },
            "include_image_base64": False,
        }
        with budgeted_api_call(
            provider=OCR_PROVIDER_MISTRAL,
            model=model,
            provider_role="ocr",
            operation="ocr",
            units=api_units(
                calls=1,
                pages=1,
                media_bytes=Path(region.resolved_path).stat().st_size,
            ),
            request_payload={
                "model": model,
                "media_id": region.media_id,
                "mime_type": region.mime_type,
            },
            metadata={"region_id": region.region_id, "engine_route": region.engine_route},
        ):
            response = _post_json(
                self.base_url,
                payload,
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout_seconds=timeout_seconds,
            )
        raw_text = _extract_mistral_text(response)
        return OcrResult(
            raw_text=raw_text,
            normalized_text=_normalize_ocr_text(raw_text),
            confidence=None,
            metadata={"response_shape": _response_shape(response)},
        )


def estimate_ocr_evidence(
    db_path: str | Path,
    *,
    sample_policy: str = DEFAULT_SAMPLE_POLICY,
    limit: int | None = 100,
    max_file_bytes: int = DEFAULT_MAX_FILE_BYTES,
    media_ids: tuple[str, ...] = (),
    tweet_ids: tuple[str, ...] = (),
    engine_routes: tuple[str, ...] = (),
) -> OcrEstimate:
    all_regions = _ocr_regions(
        db_path,
        max_file_bytes=max_file_bytes,
        media_ids=media_ids,
        tweet_ids=tweet_ids,
    )
    regions = _selected_regions(
        all_regions,
        sample_policy=sample_policy,
        limit=limit,
        engine_routes=engine_routes,
    )
    skipped = [region for region in all_regions if region.status == "skipped"]
    return OcrEstimate(
        db_path=str(Path(db_path)),
        sample_policy=sample_policy,
        limit=limit,
        media=len(all_regions),
        selected=len(regions),
        skipped=len(skipped),
        by_strata=_count_strata(regions),
        by_engine_route=_count_attr(regions, "engine_route"),
        skipped_reasons=_count_skip_reasons(skipped),
        by_quality_flag=_count_quality_flags(regions),
        estimated_pages=len(regions),
    )


def build_ocr_evidence(
    db_path: str | Path,
    *,
    provider: str = OCR_DEFAULT_PROVIDER,
    model: str | None = OCR_DEFAULT_MODEL,
    ocr_profile: str = OCR_DEFAULT_PROFILE,
    sample_policy: str = DEFAULT_SAMPLE_POLICY,
    limit: int | None = 100,
    max_file_bytes: int = DEFAULT_MAX_FILE_BYTES,
    timeout_seconds: float = 60.0,
    promote_chunks: bool = True,
    api_key_env: str | None = None,
    base_url: str | None = None,
    allow_provider_quota: bool = False,
    media_ids: tuple[str, ...] = (),
    tweet_ids: tuple[str, ...] = (),
    engine_routes: tuple[str, ...] = (),
) -> OcrBuildSummary:
    path = Path(db_path)
    normalized_provider = provider.strip().lower()
    if normalized_provider not in SUPPORTED_OCR_PROVIDERS:
        raise ValueError(f"unsupported OCR provider: {provider}")
    effective_model = _effective_ocr_model(normalized_provider, model)
    if normalized_provider not in LOCAL_OCR_PROVIDER_FAMILIES and not allow_provider_quota:
        raise RuntimeError(
            "provider OCR API use requires ProviderExecutionPolicy, budget preflight, and the "
            "paid/quota report pause. Use provider=fake or provider=local for local verification."
        )
    if normalized_provider not in LOCAL_OCR_PROVIDER_FAMILIES:
        require_provider_quota_approval(
            provider=normalized_provider,
            model=effective_model,
            operation="ocr",
            provider_role="ocr",
        )
    selected = _selected_regions(
        _ocr_regions(
            path,
            max_file_bytes=max_file_bytes,
            media_ids=media_ids,
            tweet_ids=tweet_ids,
        ),
        sample_policy=sample_policy,
        limit=limit,
        engine_routes=engine_routes,
    )
    ocr_run_id = f"ocr-{uuid.uuid4().hex[:12]}"
    started = _utc_now()
    provider_impl = _provider(normalized_provider, api_key_env=api_key_env, base_url=base_url)
    processed = 0
    skipped = 0
    promoted = 0
    second_pass_candidates = 0
    with sqlite3.connect(path, timeout=60) as conn:
        conn.row_factory = sqlite3.Row
        ensure_memory_schema(conn)
        _insert_ocr_run(
            conn,
            ocr_run_id=ocr_run_id,
            provider=provider_impl.provider_id,
            model=effective_model,
            ocr_profile=ocr_profile,
            sample_policy=sample_policy,
            limit=limit,
            status="running",
            started_at=started,
            selected=len(selected),
        )
        try:
            for original_region in selected:
                region = _prepare_region_crop(original_region, db_path=path)
                _insert_ocr_region(conn, ocr_run_id=ocr_run_id, region=region)
                if region.status == "skipped":
                    skipped += 1
                    continue
                result = provider_impl.extract(
                    region,
                    model=effective_model,
                    timeout_seconds=timeout_seconds,
                )
                second_pass = _second_pass_decision(region, result)
                text_id = _insert_ocr_text(
                    conn,
                    ocr_run_id=ocr_run_id,
                    region=region,
                    provider=provider_impl.provider_id,
                    model=effective_model,
                    ocr_profile=ocr_profile,
                    result=result,
                    text_profile="raw_ocr",
                    second_pass_status=second_pass["status"],
                    second_pass_reason=second_pass["reason"],
                )
                processed += 1
                if second_pass["status"] == "candidate":
                    second_pass_candidates += 1
                if promote_chunks and result.normalized_text:
                    _promote_text_to_chunk(
                        conn,
                        text_id=text_id,
                    )
                    promoted += 1
        except Exception as exc:
            _finish_ocr_run(
                conn,
                ocr_run_id=ocr_run_id,
                status="error",
                processed=processed,
                skipped=skipped,
                error=str(exc),
            )
            conn.commit()
            raise
        _finish_ocr_run(
            conn,
            ocr_run_id=ocr_run_id,
            status="ok",
            processed=processed,
            skipped=skipped,
        )
        conn.commit()
    return OcrBuildSummary(
        db_path=str(path),
        provider=provider_impl.provider_id,
        model=effective_model,
        ocr_profile=ocr_profile,
        ocr_run_id=ocr_run_id,
        selected=len(selected),
        processed=processed,
        skipped=skipped,
        promoted_chunks=promoted,
        second_pass_candidates=second_pass_candidates,
    )


def ocr_coverage(db_path: str | Path) -> OcrCoverage:
    with sqlite3.connect(db_path, timeout=60) as conn:
        ensure_memory_schema(conn)
        regions = conn.execute("SELECT COUNT(*) FROM memory_ocr_regions").fetchone()[0]
        texts = conn.execute("SELECT COUNT(*) FROM memory_ocr_texts").fetchone()[0]
        chunks = conn.execute(
            """
            SELECT COUNT(*)
            FROM memory_context_chunks
            WHERE provider_role = 'ocr'
            """
        ).fetchone()[0]
        provider_rows = conn.execute(
            """
            SELECT provider || '/' || model, COUNT(*)
            FROM memory_ocr_texts
            GROUP BY provider, model
            """
        ).fetchall()
        status_rows = conn.execute(
            """
            SELECT evidence_status, COUNT(*)
            FROM memory_ocr_texts
            GROUP BY evidence_status
            """
        ).fetchall()
        profile_rows = conn.execute(
            """
            SELECT text_profile, COUNT(*)
            FROM memory_ocr_texts
            GROUP BY text_profile
            """
        ).fetchall()
        second_pass_candidates = conn.execute(
            """
            SELECT COUNT(*)
            FROM memory_ocr_texts
            WHERE second_pass_status = 'candidate'
            """
        ).fetchone()[0]
    return OcrCoverage(
        db_path=str(Path(db_path)),
        regions=int(regions),
        texts=int(texts),
        context_chunks=int(chunks),
        second_pass_candidates=int(second_pass_candidates),
        by_provider_model={str(key): int(value) for key, value in provider_rows},
        by_evidence_status={str(key): int(value) for key, value in status_rows},
        by_text_profile={str(key): int(value) for key, value in profile_rows},
    )


def add_media_observation(
    db_path: str | Path,
    *,
    media_id: str,
    observation_text: str,
    observation_kind: str = "codex_interpretation",
    provider: str = "codex_interactive",
    model: str = "unspecified",
    confidence: float | None = 0.7,
    prompt: str | None = None,
    session_id: str | None = None,
    promote_chunks: bool = True,
) -> MediaObservationSummary:
    text = _normalize_ocr_text(observation_text)
    if not text:
        raise ValueError("observation_text must not be empty")
    path = Path(db_path)
    regions = _ocr_regions(
        path,
        max_file_bytes=DEFAULT_MAX_FILE_BYTES,
        media_ids=(media_id,),
    )
    if not regions:
        raise ValueError(f"media not found: {media_id}")
    region = replace(
        regions[0],
        bbox={
            "type": "full_media",
            "x": 0.0,
            "y": 0.0,
            "width": 1.0,
            "height": 1.0,
            "reading_order": 0,
        },
        region_index=0,
        reading_order=0,
        engine_route="vlm_observation",
        detector_version="media-observation-v1",
        status="candidate",
        skip_reason=None,
        quality_flags={
            **regions[0].quality_flags,
            "observation_kind": observation_kind,
            "provider_role": "media_observation",
        },
    )
    ocr_run_id = f"media-observation-{uuid.uuid4().hex[:12]}"
    now = _utc_now()
    result = OcrResult(
        raw_text=observation_text,
        normalized_text=text,
        confidence=confidence,
        metadata={
            "observation_kind": observation_kind,
            "prompt": prompt,
            "session_id": session_id,
            "source": "user_or_codex_supplied_observation",
        },
    )
    promoted = 0
    with sqlite3.connect(path, timeout=60) as conn:
        conn.row_factory = sqlite3.Row
        ensure_memory_schema(conn)
        _insert_ocr_run(
            conn,
            ocr_run_id=ocr_run_id,
            provider=provider,
            model=model,
            ocr_profile="media-observation-v1",
            sample_policy="single_media_observation",
            limit=1,
            status="running",
            started_at=now,
            selected=1,
        )
        _insert_ocr_region(conn, ocr_run_id=ocr_run_id, region=region)
        text_id = _insert_ocr_text(
            conn,
            ocr_run_id=ocr_run_id,
            region=region,
            provider=provider,
            model=model,
            ocr_profile="media-observation-v1",
            result=result,
            text_profile="codex_observation",
            second_pass_status="not_needed",
            second_pass_reason=None,
        )
        _insert_visual_observation_profile(
            conn,
            media_id=media_id,
            source_tweet_id=region.source_tweet_id,
            source_image_hash=region.source_image_hash,
            provider=provider,
            model=model,
            observation_kind=observation_kind,
            confidence=confidence,
            prompt=prompt,
            session_id=session_id,
            now=now,
        )
        if promote_chunks:
            promoted = int(_promote_text_to_chunk(conn, text_id=text_id))
        _finish_ocr_run(
            conn,
            ocr_run_id=ocr_run_id,
            status="ok",
            processed=1,
            skipped=0,
        )
        conn.commit()
    return MediaObservationSummary(db_path=str(path), imported=1, promoted_chunks=promoted)


def import_media_observations(
    db_path: str | Path,
    jsonl_path: str | Path,
    *,
    promote_chunks: bool = True,
) -> MediaObservationSummary:
    imported = 0
    promoted = 0
    with Path(jsonl_path).open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            payload = json.loads(line)
            observation_text = payload.get("text")
            if observation_text is None:
                observation_text = payload.get("observation_text")
            summary = add_media_observation(
                db_path,
                media_id=str(payload["media_id"]),
                observation_text=str(observation_text or ""),
                observation_kind=str(payload.get("observation_kind") or "codex_interpretation"),
                provider=str(payload.get("provider") or "codex_interactive"),
                model=str(payload.get("model") or "unspecified"),
                confidence=payload.get("confidence", 0.7),
                prompt=payload.get("prompt"),
                session_id=payload.get("session_id"),
                promote_chunks=promote_chunks,
            )
            imported += summary.imported
            promoted += summary.promoted_chunks
    return MediaObservationSummary(
        db_path=str(Path(db_path)),
        imported=imported,
        promoted_chunks=promoted,
    )


def media_observation_coverage(db_path: str | Path) -> MediaObservationCoverage:
    with sqlite3.connect(db_path, timeout=60) as conn:
        ensure_memory_schema(conn)
        texts = conn.execute(
            """
            SELECT COUNT(*)
            FROM memory_ocr_texts
            WHERE text_profile = 'codex_observation'
            """
        ).fetchone()[0]
        chunks = conn.execute(
            """
            SELECT COUNT(*)
            FROM memory_context_chunks
            WHERE provider_role = 'ocr'
              AND metadata_json LIKE '%"text_profile": "codex_observation"%'
            """
        ).fetchone()[0]
        visual = conn.execute(
            """
            SELECT COUNT(*)
            FROM memory_visual_recall_evidence
            WHERE evidence_level = 'codex_observation'
            """
        ).fetchone()[0]
    return MediaObservationCoverage(
        db_path=str(Path(db_path)),
        texts=int(texts),
        chunks=int(chunks),
        visual_annotations=int(visual),
    )


def media_observation_summary_json(
    summary: MediaObservationSummary | MediaObservationCoverage,
) -> str:
    return json.dumps(summary.as_dict(), ensure_ascii=False, indent=2, sort_keys=True)


def format_media_observation_summary(
    summary: MediaObservationSummary | MediaObservationCoverage,
) -> str:
    if isinstance(summary, MediaObservationCoverage):
        return "\n".join(
            (
                f"db: {summary.db_path}",
                f"texts: {summary.texts}",
                f"chunks: {summary.chunks}",
                f"visual_annotations: {summary.visual_annotations}",
            )
        )
    return "\n".join(
        (
            f"db: {summary.db_path}",
            f"imported: {summary.imported}",
            f"promoted_chunks: {summary.promoted_chunks}",
        )
    )


def ocr_search(db_path: str | Path, query: str, *, limit: int = 10) -> tuple[dict[str, Any], ...]:
    terms = tuple(term for term in _normalize_ocr_text(query).split() if term)
    with sqlite3.connect(db_path, timeout=60) as conn:
        conn.row_factory = sqlite3.Row
        ensure_memory_schema(conn)
        rows = conn.execute(
            """
            SELECT t.text_id, t.media_id, t.normalized_text, t.confidence, t.text_profile,
                   t.evidence_status, r.bbox_json, r.local_path, r.mime_type
            FROM memory_ocr_texts t
            JOIN memory_ocr_regions r ON r.region_id = t.region_id
            ORDER BY t.created_at DESC
            """
        ).fetchall()
        hits = []
        for row in rows:
            text = str(row["normalized_text"] or "")
            if terms and not all(term.casefold() in text.casefold() for term in terms):
                continue
            source_view = restore_media_source_view(conn, str(row["media_id"]))
            hits.append(
                {
                    "text_id": row["text_id"],
                    "media_id": row["media_id"],
                    "text": text,
                    "confidence": row["confidence"],
                    "text_profile": row["text_profile"],
                    "evidence_status": row["evidence_status"],
                    "bbox": _loads_json(row["bbox_json"]),
                    "source_view": source_view,
                    "bundle": source_view,
                }
            )
            if len(hits) >= max(1, limit):
                break
    return tuple(hits)


def promote_ocr_chunks(
    db_path: str | Path,
    *,
    limit: int | None = None,
    include_profiles: tuple[str, ...] = (
        "raw_ocr",
        "caption",
        "vlm_caption",
        "codex_observation",
    ),
) -> OcrPromotionSummary:
    promoted = 0
    skipped = 0
    with sqlite3.connect(db_path, timeout=60) as conn:
        conn.row_factory = sqlite3.Row
        ensure_memory_schema(conn)
        rows = conn.execute(
            """
            SELECT text_id, normalized_text, text_profile
            FROM memory_ocr_texts
            ORDER BY created_at DESC
            """
        ).fetchall()
        allowed = set(include_profiles)
        for row in rows:
            if limit is not None and promoted >= max(0, limit):
                break
            if str(row["text_profile"]) not in allowed:
                skipped += 1
                continue
            if not str(row["normalized_text"] or "").strip():
                skipped += 1
                continue
            if _promote_text_to_chunk(conn, text_id=str(row["text_id"])):
                promoted += 1
            else:
                skipped += 1
        conn.commit()
    return OcrPromotionSummary(
        db_path=str(Path(db_path)),
        promoted_chunks=promoted,
        skipped=skipped,
    )


def mark_ocr_second_pass_candidates(
    db_path: str | Path,
    *,
    confidence_threshold: float = MIN_CONFIDENCE_FOR_CITATION,
    limit: int | None = None,
    create_corrected_profile: bool = True,
) -> OcrSecondPassSummary:
    candidates = 0
    corrected = 0
    with sqlite3.connect(db_path, timeout=60) as conn:
        conn.row_factory = sqlite3.Row
        ensure_memory_schema(conn)
        rows = conn.execute(
            """
            SELECT
                t.text_id, t.ocr_run_id, t.region_id, t.media_id, t.provider, t.model,
                t.ocr_profile, t.raw_ocr_text, t.normalized_text, t.confidence,
                t.source_image_hash, t.region_hash,
                r.quality_flags_json, r.engine_route
            FROM memory_ocr_texts t
            JOIN memory_ocr_regions r ON r.region_id = t.region_id
            WHERE t.text_profile = 'raw_ocr'
            ORDER BY t.created_at DESC
            """
        ).fetchall()
        for row in rows:
            if limit is not None and candidates >= max(0, limit):
                break
            quality = _loads_json(row["quality_flags_json"]) or {}
            decision = _second_pass_decision_from_row(
                confidence=row["confidence"],
                normalized_text=str(row["normalized_text"] or ""),
                quality_flags=quality,
                engine_route=str(row["engine_route"] or ""),
                confidence_threshold=confidence_threshold,
            )
            if decision["status"] != "candidate":
                continue
            candidates += 1
            conn.execute(
                """
                UPDATE memory_ocr_texts
                SET second_pass_status = ?, second_pass_reason = ?
                WHERE text_id = ?
                """,
                (decision["status"], decision["reason"], row["text_id"]),
            )
            if create_corrected_profile:
                corrected_text = _local_correct_ocr_text(str(row["normalized_text"] or ""))
                if corrected_text:
                    _insert_ocr_text_variant(
                        conn,
                        parent=row,
                        text_profile="corrected_text",
                        normalized_text=corrected_text,
                        confidence=row["confidence"],
                        reason=decision["reason"],
                    )
                    corrected += 1
        conn.commit()
    return OcrSecondPassSummary(
        db_path=str(Path(db_path)),
        candidates=candidates,
        corrected_profiles=corrected,
    )


def estimate_json(estimate: OcrEstimate) -> str:
    return json.dumps(estimate.as_dict(), ensure_ascii=False, indent=2, sort_keys=True)


def summary_json(summary: OcrBuildSummary) -> str:
    return json.dumps(summary.as_dict(), ensure_ascii=False, indent=2, sort_keys=True)


def coverage_json(coverage: OcrCoverage) -> str:
    return json.dumps(coverage.as_dict(), ensure_ascii=False, indent=2, sort_keys=True)


def promotion_json(summary: OcrPromotionSummary) -> str:
    return json.dumps(summary.as_dict(), ensure_ascii=False, indent=2, sort_keys=True)


def second_pass_json(summary: OcrSecondPassSummary) -> str:
    return json.dumps(summary.as_dict(), ensure_ascii=False, indent=2, sort_keys=True)


def search_json(hits: tuple[dict[str, Any], ...]) -> str:
    return json.dumps(hits, ensure_ascii=False, indent=2, sort_keys=True)


def format_estimate(estimate: OcrEstimate) -> str:
    return "\n".join(
        (
            f"db: {estimate.db_path}",
            f"sample_policy: {estimate.sample_policy} limit={estimate.limit}",
            f"media: {estimate.media} selected={estimate.selected} skipped={estimate.skipped}",
            f"estimated_pages: {estimate.estimated_pages}",
            f"by_strata: {json.dumps(estimate.by_strata, ensure_ascii=False, sort_keys=True)}",
            (
                "by_engine_route: "
                f"{json.dumps(estimate.by_engine_route, ensure_ascii=False, sort_keys=True)}"
            ),
            (
                "skipped_reasons: "
                f"{json.dumps(estimate.skipped_reasons, ensure_ascii=False, sort_keys=True)}"
            ),
            (
                "by_quality_flag: "
                f"{json.dumps(estimate.by_quality_flag, ensure_ascii=False, sort_keys=True)}"
            ),
        )
    )


def format_summary(summary: OcrBuildSummary) -> str:
    return "\n".join(
        (
            f"db: {summary.db_path}",
            f"run: {summary.ocr_run_id}",
            f"provider: {summary.provider}/{summary.model} profile={summary.ocr_profile}",
            (
                f"selected={summary.selected} processed={summary.processed} "
                f"skipped={summary.skipped} promoted_chunks={summary.promoted_chunks}"
            ),
            f"second_pass_candidates={summary.second_pass_candidates}",
        )
    )


def format_coverage(coverage: OcrCoverage) -> str:
    return "\n".join(
        (
            f"db: {coverage.db_path}",
            (
                f"regions={coverage.regions} texts={coverage.texts} "
                f"context_chunks={coverage.context_chunks} "
                f"second_pass_candidates={coverage.second_pass_candidates}"
            ),
            (
                "by_provider_model: "
                f"{json.dumps(coverage.by_provider_model, ensure_ascii=False, sort_keys=True)}"
            ),
            (
                "by_evidence_status: "
                f"{json.dumps(coverage.by_evidence_status, ensure_ascii=False, sort_keys=True)}"
            ),
            (
                "by_text_profile: "
                f"{json.dumps(coverage.by_text_profile, ensure_ascii=False, sort_keys=True)}"
            ),
        )
    )


def format_promotion(summary: OcrPromotionSummary) -> str:
    return "\n".join(
        (
            f"db: {summary.db_path}",
            f"promoted_chunks={summary.promoted_chunks} skipped={summary.skipped}",
        )
    )


def format_second_pass(summary: OcrSecondPassSummary) -> str:
    return "\n".join(
        (
            f"db: {summary.db_path}",
            (
                f"second_pass_candidates={summary.candidates} "
                f"corrected_profiles={summary.corrected_profiles}"
            ),
        )
    )


def format_search(hits: tuple[dict[str, Any], ...]) -> str:
    lines = []
    for index, hit in enumerate(hits, start=1):
        source_view = hit["source_view"]
        lines.append(
            f"{index}. media_id={hit['media_id']} tweet_id={source_view.get('tweet_id') or ''} "
            f"profile={hit.get('text_profile')} confidence={hit.get('confidence')}"
        )
        lines.append(f"   text={hit['text']}")
        lines.append(f"   tweet_url={source_view.get('tweet_url') or ''}")
    return "\n".join(lines) if lines else "no OCR hits"


def _ocr_regions(
    db_path: str | Path,
    *,
    max_file_bytes: int,
    media_ids: tuple[str, ...] = (),
    tweet_ids: tuple[str, ...] = (),
) -> tuple[OcrRegion, ...]:
    path = Path(db_path)
    media_filter = {str(value) for value in media_ids if str(value)}
    tweet_filter = {str(value) for value in tweet_ids if str(value)}
    with sqlite3.connect(path, timeout=60) as conn:
        conn.row_factory = sqlite3.Row
        ensure_memory_schema(conn)
        rows = conn.execute(
            """
            SELECT
                m.media_id, m.tweet_id, m.type, m.url AS media_url, m.alt_text,
                m.local_path, m.download_status, m.content_type, m.bytes,
                t.url AS tweet_url, t.text AS tweet_text
            FROM media m
            JOIN tweets t ON t.tweet_id = m.tweet_id
            ORDER BY t.last_observed_at DESC, m.media_id
            """
        ).fetchall()
    regions: list[OcrRegion] = []
    for row in rows:
        if media_filter and str(row["media_id"]) not in media_filter:
            continue
        if tweet_filter and str(row["tweet_id"]) not in tweet_filter:
            continue
        regions.extend(_regions_from_row(row, db_path=path, max_file_bytes=max_file_bytes))
    return tuple(regions)


def _regions_from_row(
    row: sqlite3.Row,
    *,
    db_path: Path,
    max_file_bytes: int,
) -> tuple[OcrRegion, ...]:
    local_path = str(row["local_path"] or "")
    resolved = _resolve_media_path(local_path, db_path=db_path)
    mime_type = _resolve_mime_type(row, resolved)
    quality_flags = _quality_flags(row, resolved=resolved, max_file_bytes=max_file_bytes)
    skip_reason = quality_flags.get("skip_reason")
    source_hash = _file_hash(resolved) if resolved and not skip_reason else ""
    dimensions = _image_dimensions(resolved, mime_type) if resolved and not skip_reason else None
    if dimensions:
        quality_flags = {**quality_flags, **_dimension_quality_flags(dimensions)}
    strata = _strata(row, mime_type=mime_type, quality_flags=quality_flags)
    engine_route = _engine_route(strata)
    if engine_route == "no_text_likely" and not skip_reason:
        skip_reason = "no_text_likely"
    bboxes = _candidate_bboxes(engine_route=engine_route, dimensions=dimensions)
    regions: list[OcrRegion] = []
    for region_index, bbox in enumerate(bboxes):
        reading_order = int(bbox.get("reading_order", region_index))
        region_hash = _stable_hash(
            {
                "media_id": row["media_id"],
                "local_path": local_path,
                "mime_type": mime_type,
                "source_hash": source_hash,
                "bbox": bbox,
                "detector_version": OCR_REGION_DETECTOR_VERSION,
            }
        )
        regions.append(
            OcrRegion(
                region_id=f"ocr-region-{region_hash[:16]}",
                media_id=str(row["media_id"]),
                source_tweet_id=str(row["tweet_id"] or ""),
                page_index=0,
                region_index=region_index,
                reading_order=reading_order,
                bbox=bbox,
                region_hash=region_hash,
                source_image_hash=source_hash,
                local_path=local_path,
                resolved_path=str(resolved) if resolved else "",
                crop_path="",
                mime_type=mime_type,
                quality_flags=quality_flags,
                strata=strata,
                engine_route=engine_route,
                detector_version=OCR_REGION_DETECTOR_VERSION,
                status="skipped" if skip_reason else "candidate",
                skip_reason=str(skip_reason) if skip_reason else None,
                media_url=row["media_url"],
                tweet_url=row["tweet_url"],
                alt_text=row["alt_text"],
                tweet_text=row["tweet_text"],
            )
        )
    return tuple(regions)


def _selected_regions(
    regions: tuple[OcrRegion, ...],
    *,
    sample_policy: str,
    limit: int | None,
    engine_routes: tuple[str, ...] = (),
) -> tuple[OcrRegion, ...]:
    route_filter = {route.strip() for route in engine_routes if route.strip()}
    candidates = [
        region
        for region in regions
        if region.status != "skipped"
        and (not route_filter or region.engine_route in route_filter)
    ]
    normalized_policy = sample_policy.strip().lower().replace("-", "_")
    if normalized_policy in {"all", "full"}:
        selected = candidates
    elif normalized_policy in {"stratified", "stratified_calibration"}:
        selected = _stratified(candidates, limit=limit)
    elif normalized_policy == "candidate_set":
        selected = candidates
    else:
        selected = candidates
    if limit is not None and limit >= 0:
        selected = selected[:limit]
    return tuple(selected)


def _stratified(candidates: list[OcrRegion], *, limit: int | None) -> list[OcrRegion]:
    if limit is None or limit <= 0:
        return candidates
    buckets: dict[str, list[OcrRegion]] = {}
    for region in candidates:
        key = region.strata[0] if region.strata else "unknown"
        buckets.setdefault(key, []).append(region)
    selected: list[OcrRegion] = []
    keys = sorted(buckets)
    while len(selected) < limit and any(buckets.values()):
        for key in keys:
            if buckets[key] and len(selected) < limit:
                selected.append(buckets[key].pop(0))
    return selected


def _quality_flags(
    row: sqlite3.Row,
    *,
    resolved: Path | None,
    max_file_bytes: int,
) -> dict[str, Any]:
    local_path = str(row["local_path"] or "")
    mime_type = _resolve_mime_type(row, resolved)
    flags: dict[str, Any] = {
        "download_status": row["download_status"],
        "declared_bytes": int(row["bytes"] or 0),
        "has_alt_text": bool(row["alt_text"]),
        "tweet_text_chars": len(str(row["tweet_text"] or "")),
        "media_type": row["type"],
        "is_pdf": mime_type == "application/pdf",
        "content_type": mime_type,
    }
    if not local_path:
        flags["skip_reason"] = "missing_local_path"
    elif resolved is None:
        flags["skip_reason"] = "missing_file"
    elif mime_type not in SUPPORTED_OCR_MIME_TYPES:
        flags["skip_reason"] = "unsupported_mime_type"
    else:
        size = resolved.stat().st_size
        flags["file_bytes"] = size
        if size <= 0:
            flags["skip_reason"] = "zero_byte_file"
        elif size > max_file_bytes:
            flags["skip_reason"] = "file_too_large"
    flags["screenshot_likelihood"] = _keyword_likelihood(
        row,
        ("スクショ", "screenshot", "画面", "ui", "エラー", "設定", "terminal"),
    )
    flags["manga_likelihood"] = _keyword_likelihood(
        row,
        ("漫画", "manga", "同人", "縦書", "吹き出し", "イラスト"),
    )
    flags["pdf_likelihood"] = "high" if mime_type == "application/pdf" else "unknown"
    flags["text_likelihood"] = _text_likelihood(row, mime_type=mime_type)
    flags["estimated_text_density"] = _estimated_text_density(flags)
    return flags


def _strata(row: sqlite3.Row, *, mime_type: str, quality_flags: dict[str, Any]) -> tuple[str, ...]:
    text = " ".join(
        str(row[key] or "") for key in ("alt_text", "tweet_text", "media_url")
    ).casefold()
    values: list[str] = []
    if mime_type == "application/pdf":
        values.append("document_or_table")
    if any(term in text for term in ("スクショ", "screenshot", "画面", "ui")):
        values.append("screenshot_or_ui")
    if any(term in text for term in ("漫画", "manga", "同人", "縦書", "吹き出し")):
        values.append("manga_or_vertical_text")
    if quality_flags.get("text_likelihood") == "high":
        values.append("general_japanese_image")
    if not quality_flags.get("has_alt_text"):
        values.append("alt_text_missing")
    if quality_flags.get("tweet_text_chars", 0) < 24:
        values.append("tweet_text_insufficient")
    if not values:
        values.append("media_recall_top_hit")
    return tuple(dict.fromkeys(values))


def _engine_route(strata: tuple[str, ...]) -> str:
    if "document_or_table" in strata:
        return "document_pdf_or_table"
    if "screenshot_or_ui" in strata:
        return "screenshot_or_ui_text"
    if "manga_or_vertical_text" in strata:
        return "manga_or_vertical_text"
    if "general_japanese_image" in strata:
        return "japanese_general_image"
    if "media_recall_top_hit" in strata:
        return "no_text_likely"
    return "mistral_general"


def _text_likelihood(row: sqlite3.Row, *, mime_type: str) -> str:
    text = " ".join(str(row[key] or "") for key in ("alt_text", "tweet_text"))
    if mime_type == "application/pdf":
        return "high"
    if any(term in text for term in ("資料", "図表", "スクショ", "文字", "説明", "メニュー")):
        return "high"
    if row["alt_text"]:
        return "medium"
    return "unknown"


def _image_dimensions(path: Path | None, mime_type: str) -> tuple[int, int] | None:
    if path is None or mime_type == "application/pdf":
        return None
    try:
        from PIL import Image

        with Image.open(path) as image:
            return int(image.width), int(image.height)
    except Exception:
        return None


def _dimension_quality_flags(dimensions: tuple[int, int]) -> dict[str, Any]:
    width, height = dimensions
    pixels = max(0, width) * max(0, height)
    megapixels = pixels / 1_000_000 if pixels else 0.0
    aspect_ratio = width / height if height else 0.0
    return {
        "image_width": width,
        "image_height": height,
        "megapixels": round(megapixels, 4),
        "aspect_ratio": round(aspect_ratio, 4),
        "too_small_for_ocr": width < 320 or height < 120,
        "very_large_image": pixels > 16_000_000,
        "vertical_layout_likely": height > width * 1.4 if width else False,
        "wide_layout_likely": width > height * 1.8 if height else False,
        "blur_score": None,
    }


def _candidate_bboxes(
    *,
    engine_route: str,
    dimensions: tuple[int, int] | None,
) -> tuple[dict[str, int | float | str], ...]:
    full = {
        "type": "full_media",
        "x": 0.0,
        "y": 0.0,
        "width": 1.0,
        "height": 1.0,
        "reading_order": 0,
    }
    if dimensions is None or engine_route in {"document_pdf_or_table", "mistral_general"}:
        return (full,)
    if engine_route == "screenshot_or_ui_text":
        return (
            {
                "type": "top_band",
                "x": 0.0,
                "y": 0.0,
                "width": 1.0,
                "height": 0.34,
                "reading_order": 0,
            },
            {
                "type": "middle_band",
                "x": 0.0,
                "y": 0.33,
                "width": 1.0,
                "height": 0.34,
                "reading_order": 1,
            },
            {
                "type": "bottom_band",
                "x": 0.0,
                "y": 0.66,
                "width": 1.0,
                "height": 0.34,
                "reading_order": 2,
            },
        )
    if engine_route == "manga_or_vertical_text":
        return (
            {
                "type": "right_column",
                "x": 0.5,
                "y": 0.0,
                "width": 0.5,
                "height": 1.0,
                "reading_order": 0,
            },
            {
                "type": "left_column",
                "x": 0.0,
                "y": 0.0,
                "width": 0.5,
                "height": 1.0,
                "reading_order": 1,
            },
        )
    return (full,)


def _local_ocr_candidate_text_parts(region: OcrRegion) -> list[str]:
    parts: list[str] = []
    if region.alt_text:
        parts.append(_normalize_ocr_text(str(region.alt_text)))
    if region.tweet_text:
        tweet_text = _normalize_ocr_text(str(region.tweet_text))
        if tweet_text and tweet_text not in parts:
            parts.append(tweet_text)
    if not parts:
        route_text = " ".join(
            str(value)
            for value in (
                _local_ocr_engine_family(region),
                region.engine_route,
                region.bbox.get("type", "full_media"),
            )
            if value
        )
        parts.append(_normalize_ocr_text(route_text))
    return list(dict.fromkeys(part for part in parts if part))


def _local_ocr_candidate_sources(region: OcrRegion) -> list[str]:
    sources: list[str] = []
    if region.alt_text:
        sources.append("alt_text")
    if region.tweet_text:
        sources.append("tweet_text")
    if not sources:
        sources.append("region_route")
    return sources


def _local_ocr_engine_family(region: OcrRegion) -> str:
    if region.engine_route == "manga_or_vertical_text":
        return "manga-ocr-metadata-fallback"
    if region.engine_route == "document_pdf_or_table":
        return "paddleocr-vl-metadata-fallback"
    if region.engine_route in {"screenshot_or_ui_text", "japanese_general_image"}:
        return "paddleocr-metadata-fallback"
    return "local-ocr-metadata-fallback"


def _local_ocr_confidence(region: OcrRegion, text_parts: list[str]) -> float:
    if not text_parts:
        return 0.0
    score = 0.38
    if region.alt_text:
        score += 0.16
    if region.tweet_text:
        score += 0.08
    if region.quality_flags.get("text_likelihood") == "high":
        score += 0.08
    if region.quality_flags.get("estimated_text_density") == "high":
        score += 0.06
    if region.engine_route in {"screenshot_or_ui_text", "manga_or_vertical_text"}:
        score += 0.04
    return round(min(score, 0.82), 4)


def _keyword_likelihood(row: sqlite3.Row, terms: tuple[str, ...]) -> str:
    text = " ".join(str(row[key] or "") for key in ("alt_text", "tweet_text", "media_url"))
    text = text.casefold()
    return "high" if any(term.casefold() in text for term in terms) else "unknown"


def _estimated_text_density(flags: dict[str, Any]) -> str:
    if flags.get("is_pdf"):
        return "high"
    if flags.get("screenshot_likelihood") == "high":
        return "high"
    if flags.get("manga_likelihood") == "high":
        return "medium"
    if flags.get("text_likelihood") == "high":
        return "medium"
    if flags.get("has_alt_text"):
        return "low"
    return "unknown"


def _insert_ocr_run(
    conn: sqlite3.Connection,
    *,
    ocr_run_id: str,
    provider: str,
    model: str,
    ocr_profile: str,
    sample_policy: str,
    limit: int | None,
    status: str,
    started_at: str,
    selected: int,
) -> None:
    conn.execute(
        """
        INSERT INTO memory_ocr_runs (
            ocr_run_id, provider, model, ocr_profile, sample_policy, limit_count,
            status, selected_regions, processed_regions, skipped_regions,
            budget_event_id, started_at, finished_at, error, metadata_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, 0, ?, ?, ?, ?, ?)
        """,
        (
            ocr_run_id,
            provider,
            model,
            ocr_profile,
            sample_policy,
            limit,
            status,
            selected,
            None,
            started_at,
            None,
            None,
            "{}",
        ),
    )


def _prepare_region_crop(region: OcrRegion, *, db_path: Path) -> OcrRegion:
    if region.status == "skipped":
        return region
    if region.mime_type == "application/pdf":
        return region
    bbox_type = str(region.bbox.get("type", ""))
    if bbox_type == "full_media":
        return region
    source_path = Path(region.resolved_path)
    if not source_path.exists():
        return region
    try:
        from PIL import Image

        crop_dir = db_path.parent / "ocr_crops"
        crop_dir.mkdir(parents=True, exist_ok=True)
        ext = ".png" if region.mime_type in {"image/png", "image/webp"} else ".jpg"
        crop_path = crop_dir / f"{region.media_id}-{region.region_hash[:12]}{ext}"
        with Image.open(source_path) as image:
            width, height = image.size
            x = float(region.bbox.get("x", 0))
            y = float(region.bbox.get("y", 0))
            box_width = float(region.bbox.get("width", 1))
            box_height = float(region.bbox.get("height", 1))
            left = max(0, min(width, int(round(x * width))))
            top = max(0, min(height, int(round(y * height))))
            right = max(left + 1, min(width, int(round((x + box_width) * width))))
            bottom = max(top + 1, min(height, int(round((y + box_height) * height))))
            cropped = image.crop((left, top, right, bottom))
            cropped.save(crop_path)
        return replace(region, crop_path=str(crop_path), resolved_path=str(crop_path))
    except Exception:
        flags = {**region.quality_flags, "crop_error": True}
        return replace(region, quality_flags=flags)


def _finish_ocr_run(
    conn: sqlite3.Connection,
    *,
    ocr_run_id: str,
    status: str,
    processed: int,
    skipped: int,
    error: str | None = None,
) -> None:
    conn.execute(
        """
        UPDATE memory_ocr_runs
        SET status = ?, processed_regions = ?, skipped_regions = ?, finished_at = ?, error = ?
        WHERE ocr_run_id = ?
        """,
        (status, processed, skipped, _utc_now(), error, ocr_run_id),
    )


def _region_metadata(region: OcrRegion) -> dict[str, Any]:
    return {
        "media_id": region.media_id,
        "source_tweet_id": region.source_tweet_id,
        "mime_type": region.mime_type,
        "bbox": region.bbox,
        "dimensions": _dimensions_from_quality_flags(region.quality_flags),
        "text_likelihood": region.quality_flags.get("text_likelihood"),
        "estimated_text_density": region.quality_flags.get("estimated_text_density"),
        "quality_flags": region.quality_flags,
        "engine_route": region.engine_route,
        "strata": list(region.strata),
        "detector_version": region.detector_version,
        "skip_reason": region.skip_reason,
        "source_restoration": {
            "media_id": region.media_id,
            "tweet_id": region.source_tweet_id,
            "source_image_hash": region.source_image_hash,
            "local_path": region.local_path,
            "crop_path": region.crop_path,
        },
    }


def _dimensions_from_quality_flags(quality_flags: dict[str, Any]) -> dict[str, int] | None:
    width = quality_flags.get("image_width")
    height = quality_flags.get("image_height")
    if isinstance(width, int) and isinstance(height, int):
        return {"width": width, "height": height}
    return None


def _insert_ocr_region(conn: sqlite3.Connection, *, ocr_run_id: str, region: OcrRegion) -> None:
    conn.execute(
        """
        INSERT INTO memory_ocr_regions (
            region_id, ocr_run_id, media_id, source_tweet_id, page_index, region_index,
            reading_order, bbox_json, region_hash, source_image_hash, local_path, crop_path,
            mime_type, quality_flags_json, strata_json, engine_route, detector_version,
            status, created_at, metadata_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(region_id) DO UPDATE SET
            ocr_run_id=excluded.ocr_run_id,
            reading_order=excluded.reading_order,
            crop_path=excluded.crop_path,
            status=excluded.status,
            quality_flags_json=excluded.quality_flags_json,
            detector_version=excluded.detector_version,
            metadata_json=excluded.metadata_json
        """,
        (
            region.region_id,
            ocr_run_id,
            region.media_id,
            region.source_tweet_id,
            region.page_index,
            region.region_index,
            region.reading_order,
            json.dumps(region.bbox, ensure_ascii=False, sort_keys=True),
            region.region_hash,
            region.source_image_hash,
            region.local_path,
            region.crop_path,
            region.mime_type,
            json.dumps(region.quality_flags, ensure_ascii=False, sort_keys=True),
            json.dumps(region.strata, ensure_ascii=False),
            region.engine_route,
            region.detector_version,
            region.status,
            _utc_now(),
            json.dumps(_region_metadata(region), ensure_ascii=False, sort_keys=True),
        ),
    )


def _insert_ocr_text(
    conn: sqlite3.Connection,
    *,
    ocr_run_id: str,
    region: OcrRegion,
    provider: str,
    model: str,
    ocr_profile: str,
    result: OcrResult,
    text_profile: str,
    parent_text_id: str | None = None,
    second_pass_status: str = "not_needed",
    second_pass_reason: str | None = None,
) -> str:
    text_id = _stable_id(
        "ocr-text",
        ocr_run_id,
        region.region_id,
        provider,
        model,
        ocr_profile,
        text_profile,
        parent_text_id or "",
    )
    conn.execute(
        """
        INSERT INTO memory_ocr_texts (
            text_id, ocr_run_id, region_id, media_id, provider, model, ocr_profile,
            text_profile, parent_text_id, raw_ocr_text, normalized_text, corrected_text,
            confidence, evidence_status, source_image_hash, region_hash, quality_flags_json,
            second_pass_status, second_pass_reason, created_at, metadata_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(text_id) DO UPDATE SET
            raw_ocr_text=excluded.raw_ocr_text,
            normalized_text=excluded.normalized_text,
            corrected_text=excluded.corrected_text,
            confidence=excluded.confidence,
            quality_flags_json=excluded.quality_flags_json,
            second_pass_status=excluded.second_pass_status,
            second_pass_reason=excluded.second_pass_reason,
            metadata_json=excluded.metadata_json
        """,
        (
            text_id,
            ocr_run_id,
            region.region_id,
            region.media_id,
            provider,
            model,
            ocr_profile,
            text_profile,
            parent_text_id,
            result.raw_text,
            result.normalized_text,
            result.corrected_text,
            result.confidence,
            _evidence_status_for_text(text_profile, result.normalized_text),
            region.source_image_hash,
            region.region_hash,
            json.dumps(region.quality_flags, ensure_ascii=False, sort_keys=True),
            second_pass_status,
            second_pass_reason,
            _utc_now(),
            json.dumps(
                {
                    **(result.metadata or {}),
                    "region_metadata": _region_metadata(region),
                    **_media_text_signal_metadata(text_profile),
                },
                ensure_ascii=False,
                sort_keys=True,
            ),
        ),
    )
    return text_id


def _insert_ocr_text_variant(
    conn: sqlite3.Connection,
    *,
    parent: sqlite3.Row,
    text_profile: str,
    normalized_text: str,
    confidence: float | None,
    reason: str | None,
) -> str:
    text_id = _stable_id("ocr-text-variant", str(parent["text_id"]), text_profile)
    conn.execute(
        """
        INSERT INTO memory_ocr_texts (
            text_id, ocr_run_id, region_id, media_id, provider, model, ocr_profile,
            text_profile, parent_text_id, raw_ocr_text, normalized_text, corrected_text,
            confidence, evidence_status, source_image_hash, region_hash, quality_flags_json,
            second_pass_status, second_pass_reason, created_at, metadata_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(text_id) DO UPDATE SET
            normalized_text=excluded.normalized_text,
            corrected_text=excluded.corrected_text,
            metadata_json=excluded.metadata_json
        """,
        (
            text_id,
            parent["ocr_run_id"],
            parent["region_id"],
            parent["media_id"],
            OCR_SECOND_PASS_PROVIDER,
            OCR_SECOND_PASS_MODEL,
            parent["ocr_profile"],
            text_profile,
            parent["text_id"],
            parent["raw_ocr_text"],
            normalized_text,
            normalized_text,
            confidence,
            "inference",
            parent["source_image_hash"],
            parent["region_hash"],
            parent["quality_flags_json"],
            "created_profile",
            reason,
            _utc_now(),
            json.dumps(
                {
                    "derived_from": parent["text_id"],
                    "reason": reason,
                    "raw_text_preserved": True,
                    **_media_text_signal_metadata(text_profile),
                },
                ensure_ascii=False,
                sort_keys=True,
            ),
        ),
    )
    return text_id


def _insert_visual_observation_profile(
    conn: sqlite3.Connection,
    *,
    media_id: str,
    source_tweet_id: str,
    source_image_hash: str,
    provider: str,
    model: str,
    observation_kind: str,
    confidence: float | None,
    prompt: str | None,
    session_id: str | None,
    now: str,
) -> None:
    visual_id = _stable_id(
        "media-observation",
        media_id,
        provider,
        model,
        observation_kind,
        session_id or "",
    )
    bbox = {
        "type": "full_media",
        "x": 0.0,
        "y": 0.0,
        "width": 1.0,
        "height": 1.0,
    }
    conn.execute(
        """
        INSERT INTO memory_visual_recall_evidence (
            visual_evidence_id, media_id, source_tweet_id, evidence_level, page_index,
            region_index, pixel_bbox_json, normalized_bbox_json, citation_ready,
            source_image_hash, provider, model, created_at, metadata_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(visual_evidence_id) DO UPDATE SET
            source_tweet_id=excluded.source_tweet_id,
            source_image_hash=excluded.source_image_hash,
            provider=excluded.provider,
            model=excluded.model,
            metadata_json=excluded.metadata_json
        """,
        (
            visual_id,
            media_id,
            source_tweet_id,
            "codex_observation",
            0,
            0,
            json.dumps(bbox, ensure_ascii=False, sort_keys=True),
            json.dumps(bbox, ensure_ascii=False, sort_keys=True),
            0,
            source_image_hash,
            provider,
            model,
            now,
            json.dumps(
                {
                    "observation_kind": observation_kind,
                    "confidence": confidence,
                    "prompt": prompt,
                    "session_id": session_id,
                    "contract": "codex_observation_is_inference_annotation_not_fact",
                    **_media_text_signal_metadata("codex_observation"),
                },
                ensure_ascii=False,
                sort_keys=True,
            ),
        ),
    )


def _evidence_status_for_text(text_profile: str, normalized_text: str) -> str:
    if not normalized_text:
        return "unconfirmed"
    if text_profile == "raw_ocr":
        return "fact"
    if text_profile in {"caption", "vlm_caption"}:
        return "inference"
    return "inference"


def _media_text_signal_metadata(text_profile: str) -> dict[str, Any]:
    return {
        "media_signal_role": text_profile,
        "evidence_role": "media_text_candidate_signal",
        "answer_support_allowed": False,
        "citation_ready": False,
        "promotion_gate": "context_chunk_citation_annotation_required",
        "quality_scope": "media_signal_boundary_not_model_quality",
        "not_evidence": True,
    }


def _second_pass_decision(region: OcrRegion, result: OcrResult) -> dict[str, str | None]:
    return _second_pass_decision_from_row(
        confidence=result.confidence,
        normalized_text=result.normalized_text,
        quality_flags=region.quality_flags,
        engine_route=region.engine_route,
        confidence_threshold=MIN_CONFIDENCE_FOR_CITATION,
    )


def _second_pass_decision_from_row(
    *,
    confidence: Any,
    normalized_text: str,
    quality_flags: dict[str, Any],
    engine_route: str,
    confidence_threshold: float,
) -> dict[str, str | None]:
    confidence_value = float(confidence) if isinstance(confidence, int | float) else None
    if confidence_value is not None and confidence_value < confidence_threshold:
        return {"status": "candidate", "reason": "low_confidence"}
    if (
        not normalized_text.strip()
        and quality_flags.get("estimated_text_density") in {"high", "medium"}
    ):
        return {"status": "candidate", "reason": "empty_ocr_with_text_likelihood"}
    if engine_route in {"screenshot_or_ui_text", "manga_or_vertical_text"}:
        return {"status": "candidate", "reason": "specialized_route_quality_check"}
    return {"status": "not_needed", "reason": None}


def _local_correct_ocr_text(text: str) -> str:
    corrected = _normalize_ocr_text(text)
    replacements = {
        "Ｏ": "O",
        "０": "0",
        "１": "1",
        "ｌ": "l",
        "｜": "|",
    }
    for source, target in replacements.items():
        corrected = corrected.replace(source, target)
    return corrected


def _promote_region_to_chunk(
    conn: sqlite3.Connection,
    *,
    ocr_run_id: str,
    region: OcrRegion,
    provider: str,
    model: str,
    ocr_profile: str,
    result: OcrResult,
) -> None:
    source_view = restore_media_source_view(conn, region.media_id)
    chunk_id = _stable_id("ocr-chunk", ocr_run_id, region.region_id, provider, model)
    now = _utc_now()
    source_url = source_view.get("tweet_url") or region.tweet_url or region.media_url
    title = f"OCR media {region.media_id}"
    metadata = {
        "ocr_run_id": ocr_run_id,
        "region_id": region.region_id,
        "bbox": region.bbox,
        "mime_type": region.mime_type,
        "dimensions": _dimensions_from_quality_flags(region.quality_flags),
        "text_likelihood": region.quality_flags.get("text_likelihood"),
        "estimated_text_density": region.quality_flags.get("estimated_text_density"),
        "quality_flags": region.quality_flags,
        "engine_route": region.engine_route,
        "strata": region.strata,
        "source_image_hash": region.source_image_hash,
        "provider": provider,
        "model": model,
        "ocr_profile": ocr_profile,
        "raw_text_preserved": True,
        **_promoted_media_context_metadata(
            "raw_ocr",
            answer_support_allowed=True,
        ),
    }
    conn.execute(
        """
        INSERT INTO memory_context_chunks (
            chunk_id, run_id, source_kind, source_id, source_url,
            provider, provider_role, chunk_text, chunk_index, offset_start,
            offset_end, token_count, relevance_score, extractor_version, created_at,
            metadata_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(chunk_id) DO UPDATE SET
            chunk_text=excluded.chunk_text,
            token_count=excluded.token_count,
            metadata_json=excluded.metadata_json
        """,
        (
            chunk_id,
            ocr_run_id,
            "local_x_db",
            region.media_id,
            source_url,
            provider,
            "ocr",
            result.normalized_text,
            region.region_index,
            None,
            None,
            max(1, len(result.normalized_text) // 2),
            result.confidence,
            OCR_EXTRACTOR_VERSION,
            now,
            json.dumps(metadata, ensure_ascii=False, sort_keys=True),
        ),
    )
    citation_id = _stable_id("ocr-citation", chunk_id, region.media_id)
    conn.execute(
        """
        INSERT INTO memory_citation_annotations (
            citation_id, answer_id, chunk_id, source_kind, source_id, source_url,
            title, answer_start_index, answer_end_index, field_path, support_type,
            evidence_status, confidence, created_at, metadata_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(citation_id) DO UPDATE SET
            support_type=excluded.support_type,
            evidence_status=excluded.evidence_status,
            confidence=excluded.confidence,
            metadata_json=excluded.metadata_json
        """,
        (
            citation_id,
            None,
            chunk_id,
            "local_x_db",
            region.media_id,
            source_url,
            title,
            None,
            None,
            "media.ocr_text",
            "supports_media_content",
            "fact",
            result.confidence,
            now,
            json.dumps(metadata, ensure_ascii=False, sort_keys=True),
        ),
    )


def _promote_text_to_chunk(conn: sqlite3.Connection, *, text_id: str) -> bool:
    row = conn.execute(
        """
        SELECT
            t.text_id, t.ocr_run_id, t.media_id, t.provider, t.model, t.ocr_profile,
            t.text_profile, t.normalized_text, t.confidence, t.evidence_status,
            t.source_image_hash, t.second_pass_status, t.second_pass_reason,
            r.region_id, r.bbox_json, r.engine_route, r.strata_json, r.reading_order,
            r.local_path, r.crop_path, r.mime_type, r.quality_flags_json
        FROM memory_ocr_texts t
        JOIN memory_ocr_regions r ON r.region_id = t.region_id
        WHERE t.text_id = ?
        """,
        (text_id,),
    ).fetchone()
    if row is None:
        return False
    text = str(row["normalized_text"] or "").strip()
    if not text:
        return False
    source_view = restore_media_source_view(conn, str(row["media_id"]))
    chunk_id = _stable_id("ocr-chunk", str(row["text_id"]))
    now = _utc_now()
    source_url = source_view.get("tweet_url")
    title = f"OCR media {row['media_id']}"
    text_profile = str(row["text_profile"])
    quality_flags = _loads_json(row["quality_flags_json"]) or {}
    metadata = {
        "ocr_run_id": row["ocr_run_id"],
        "region_id": row["region_id"],
        "bbox": _loads_json(row["bbox_json"]),
        "mime_type": row["mime_type"],
        "dimensions": _dimensions_from_quality_flags(quality_flags),
        "text_likelihood": quality_flags.get("text_likelihood"),
        "estimated_text_density": quality_flags.get("estimated_text_density"),
        "quality_flags": quality_flags,
        "engine_route": row["engine_route"],
        "strata": _loads_json(row["strata_json"]),
        "source_image_hash": row["source_image_hash"],
        "provider": row["provider"],
        "model": row["model"],
        "ocr_profile": row["ocr_profile"],
        "text_profile": text_profile,
        "second_pass_status": row["second_pass_status"],
        "second_pass_reason": row["second_pass_reason"],
        "raw_text_preserved": True,
        "crop_path": row["crop_path"],
        "local_path": row["local_path"],
    }
    evidence_status = str(row["evidence_status"] or "unconfirmed")
    support_type = (
        "supports_media_content" if text_profile == "raw_ocr" else "supports_search_helper"
    )
    metadata.update(
        _promoted_media_context_metadata(
            text_profile,
            answer_support_allowed=support_type == "supports_media_content",
        )
    )
    conn.execute(
        """
        INSERT INTO memory_context_chunks (
            chunk_id, run_id, source_kind, source_id, source_url,
            provider, provider_role, chunk_text, chunk_index, offset_start,
            offset_end, token_count, relevance_score, extractor_version, created_at,
            metadata_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(chunk_id) DO UPDATE SET
            chunk_text=excluded.chunk_text,
            token_count=excluded.token_count,
            relevance_score=excluded.relevance_score,
            metadata_json=excluded.metadata_json
        """,
        (
            chunk_id,
            row["ocr_run_id"],
            "local_x_db",
            row["media_id"],
            source_url,
            row["provider"],
            "ocr",
            text,
            row["reading_order"],
            None,
            None,
            max(1, len(text) // 2),
            row["confidence"],
            OCR_EXTRACTOR_VERSION,
            now,
            json.dumps(metadata, ensure_ascii=False, sort_keys=True),
        ),
    )
    citation_id = _stable_id("ocr-citation", chunk_id, str(row["media_id"]))
    conn.execute(
        """
        INSERT INTO memory_citation_annotations (
            citation_id, answer_id, chunk_id, source_kind, source_id, source_url,
            title, answer_start_index, answer_end_index, field_path, support_type,
            evidence_status, confidence, created_at, metadata_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(citation_id) DO UPDATE SET
            support_type=excluded.support_type,
            evidence_status=excluded.evidence_status,
            confidence=excluded.confidence,
            metadata_json=excluded.metadata_json
        """,
        (
            citation_id,
            None,
            chunk_id,
            "local_x_db",
            row["media_id"],
            source_url,
            title,
            None,
            None,
            f"media.ocr_text.{text_profile}",
            support_type,
            evidence_status,
            row["confidence"],
            now,
            json.dumps(metadata, ensure_ascii=False, sort_keys=True),
        ),
    )
    return True


def _promoted_media_context_metadata(
    text_profile: str,
    *,
    answer_support_allowed: bool,
) -> dict[str, Any]:
    metadata: dict[str, Any] = {
        "source_media_signal_role": text_profile,
        "media_signal_role": "promoted_context_chunk",
        "evidence_role": "context_chunk_from_media_text",
        "promotion_gate": "context_chunk_citation_annotation_created",
        "quality_scope": "media_signal_boundary_not_model_quality",
    }
    if not answer_support_allowed:
        metadata["answer_support_allowed"] = False
        metadata["not_evidence"] = True
    return metadata


def _provider(
    provider: str,
    *,
    api_key_env: str | None,
    base_url: str | None,
) -> OcrProvider:
    normalized = provider.strip().lower()
    if normalized == OCR_PROVIDER_FAKE:
        return FakeOcrProvider()
    if normalized == OCR_PROVIDER_LOCAL:
        return LocalMetadataOcrProvider()
    if normalized == OCR_PROVIDER_MISTRAL:
        return MistralOcrProvider(
            api_key_env=api_key_env or "MISTRAL_API_KEY",
            base_url=base_url,
        )
    raise ValueError(f"unsupported OCR provider: {provider}")


def _effective_ocr_model(provider: str, model: str | None) -> str:
    normalized_model = (model or "").strip()
    if provider == OCR_PROVIDER_LOCAL and (
        not normalized_model or normalized_model == OCR_DEFAULT_MODEL
    ):
        return OCR_LOCAL_DEFAULT_MODEL
    return normalized_model or OCR_DEFAULT_MODEL


def _extract_mistral_text(response: dict[str, Any]) -> str:
    parts: list[str] = []
    if isinstance(response.get("text"), str):
        parts.append(response["text"])
    pages = response.get("pages")
    if isinstance(pages, list):
        for page in pages:
            if not isinstance(page, dict):
                continue
            for key in ("markdown", "text"):
                if isinstance(page.get(key), str):
                    parts.append(page[key])
            images = page.get("images")
            if isinstance(images, list):
                for image in images:
                    if isinstance(image, dict) and isinstance(image.get("text"), str):
                        parts.append(image["text"])
    return "\n\n".join(part for part in parts if part).strip()


def _response_shape(response: dict[str, Any]) -> dict[str, Any]:
    return {
        "keys": tuple(sorted(response)),
        "pages": len(response.get("pages") or []) if isinstance(response.get("pages"), list) else 0,
    }


def _resolve_media_path(local_path: str, *, db_path: Path) -> Path | None:
    if not local_path:
        return None
    raw = Path(local_path)
    candidates = (raw, db_path.parent / raw, Path.cwd() / raw)
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def _resolve_mime_type(row: sqlite3.Row, path: Path | None) -> str:
    value = str(row["content_type"] or "").split(";")[0].strip().lower()
    if value:
        return value
    if path:
        guessed, _ = mimetypes.guess_type(path.name)
        return guessed or ""
    return ""


def _data_url(path: str, mime_type: str) -> str:
    data = Path(path).read_bytes()
    return f"data:{mime_type};base64,{base64.b64encode(data).decode('ascii')}"


def _file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _stable_hash(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()


def _stable_id(prefix: str, *parts: str) -> str:
    return f"{prefix}-{_stable_hash(parts)[:16]}"


def _normalize_ocr_text(value: str) -> str:
    return " ".join((value or "").replace("\r", "\n").split())


def _loads_json(value: str | None) -> Any:
    if not value:
        return None
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return None


def _count_attr(regions: tuple[OcrRegion, ...] | list[OcrRegion], attr: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for region in regions:
        key = str(getattr(region, attr))
        counts[key] = counts.get(key, 0) + 1
    return counts


def _count_strata(regions: tuple[OcrRegion, ...] | list[OcrRegion]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for region in regions:
        for stratum in region.strata:
            counts[stratum] = counts.get(stratum, 0) + 1
    return counts


def _count_skip_reasons(regions: list[OcrRegion]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for region in regions:
        key = region.skip_reason or "unknown"
        counts[key] = counts.get(key, 0) + 1
    return counts


def _count_quality_flags(regions: tuple[OcrRegion, ...] | list[OcrRegion]) -> dict[str, int]:
    keys = (
        "too_small_for_ocr",
        "very_large_image",
        "vertical_layout_likely",
        "wide_layout_likely",
        "has_alt_text",
        "is_pdf",
    )
    counts: dict[str, int] = {}
    for region in regions:
        for key in keys:
            if region.quality_flags.get(key):
                counts[key] = counts.get(key, 0) + 1
        density = region.quality_flags.get("estimated_text_density")
        if density:
            bucket = f"text_density:{density}"
            counts[bucket] = counts.get(bucket, 0) + 1
    return counts


def _utc_now() -> str:
    return datetime.now(tz=UTC).isoformat()
