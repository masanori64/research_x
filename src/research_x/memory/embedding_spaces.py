from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

DEFAULT_TEXT_PROVIDER = "gemini"
DEFAULT_TEXT_MODEL = "gemini-embedding-2"
DEFAULT_TEXT_DIMENSIONS = 768
DEFAULT_TEXT_TEMPLATE_VERSION = "memory-doc-embedding-v1"
DEFAULT_DISTANCE_METRIC = "cosine"


@dataclass(frozen=True)
class EmbeddingSpaceDefinition:
    space_id: str
    provider: str
    model: str
    dimensions: int
    distance_metric: str
    embedding_profile: str
    text_template_version: str
    modality: str
    document_scope: str
    source_kind_filter: str
    language_filter: str
    storage_rights_policy: str
    provider_role: str
    status: str
    notes: str

    def as_row(
        self,
        *,
        created_at: str,
        created_by_run_id: str | None = None,
    ) -> dict[str, Any]:
        return {
            **asdict(self),
            "created_at": created_at,
            "created_by_run_id": created_by_run_id,
        }


FINAL_EMBEDDING_SPACE_DEFINITIONS: tuple[EmbeddingSpaceDefinition, ...] = (
    EmbeddingSpaceDefinition(
        space_id="text.general_memory.v1",
        provider=DEFAULT_TEXT_PROVIDER,
        model=DEFAULT_TEXT_MODEL,
        dimensions=DEFAULT_TEXT_DIMENSIONS,
        distance_metric=DEFAULT_DISTANCE_METRIC,
        embedding_profile="general_memory",
        text_template_version=DEFAULT_TEXT_TEMPLATE_VERSION,
        modality="text",
        document_scope="memory_documents",
        source_kind_filter="local_x_text",
        language_filter="any",
        storage_rights_policy="local-db-derived-text",
        provider_role="text_embedding",
        status="planned",
        notes="Broad semantic recall over normal memory_documents.",
    ),
    EmbeddingSpaceDefinition(
        space_id="text.jp_multilingual.v1",
        provider=DEFAULT_TEXT_PROVIDER,
        model=DEFAULT_TEXT_MODEL,
        dimensions=DEFAULT_TEXT_DIMENSIONS,
        distance_metric=DEFAULT_DISTANCE_METRIC,
        embedding_profile="jp_multilingual",
        text_template_version=DEFAULT_TEXT_TEMPLATE_VERSION,
        modality="text",
        document_scope="memory_documents",
        source_kind_filter="local_x_text",
        language_filter="ja,mixed,en",
        storage_rights_policy="local-db-derived-text",
        provider_role="text_embedding",
        status="planned",
        notes="Japanese, mixed Japanese/English, and cross-lingual recall.",
    ),
    EmbeddingSpaceDefinition(
        space_id="text.code_technical.v1",
        provider=DEFAULT_TEXT_PROVIDER,
        model=DEFAULT_TEXT_MODEL,
        dimensions=DEFAULT_TEXT_DIMENSIONS,
        distance_metric=DEFAULT_DISTANCE_METRIC,
        embedding_profile="code_technical",
        text_template_version=DEFAULT_TEXT_TEMPLATE_VERSION,
        modality="text",
        document_scope="memory_documents",
        source_kind_filter="technical_text",
        language_filter="any",
        storage_rights_policy="local-db-derived-text",
        provider_role="text_embedding",
        status="planned",
        notes="Code, APIs, commands, package names, providers, and error text.",
    ),
    EmbeddingSpaceDefinition(
        space_id="text.relation_context.v1",
        provider=DEFAULT_TEXT_PROVIDER,
        model=DEFAULT_TEXT_MODEL,
        dimensions=DEFAULT_TEXT_DIMENSIONS,
        distance_metric=DEFAULT_DISTANCE_METRIC,
        embedding_profile="relation_context",
        text_template_version=DEFAULT_TEXT_TEMPLATE_VERSION,
        modality="text",
        document_scope="memory_documents+relations",
        source_kind_filter="local_x_relation_text",
        language_filter="any",
        storage_rights_policy="local-db-derived-text",
        provider_role="text_embedding",
        status="planned",
        notes="Quote, reply, thread, bookmark, account, and relation-heavy context.",
    ),
    EmbeddingSpaceDefinition(
        space_id="media.text_bridge.v1",
        provider=DEFAULT_TEXT_PROVIDER,
        model=DEFAULT_TEXT_MODEL,
        dimensions=DEFAULT_TEXT_DIMENSIONS,
        distance_metric=DEFAULT_DISTANCE_METRIC,
        embedding_profile="media_text_bridge",
        text_template_version=DEFAULT_TEXT_TEMPLATE_VERSION,
        modality="text",
        document_scope="media_ocr_caption_text",
        source_kind_filter="media_text",
        language_filter="any",
        storage_rights_policy="local-media-derived-text",
        provider_role="text_embedding",
        status="planned",
        notes="Text queries to OCR, caption, alt text, and reviewed media descriptions.",
    ),
    EmbeddingSpaceDefinition(
        space_id="media.native_multimodal.v1",
        provider=DEFAULT_TEXT_PROVIDER,
        model=DEFAULT_TEXT_MODEL,
        dimensions=1536,
        distance_metric=DEFAULT_DISTANCE_METRIC,
        embedding_profile="native_multimodal_media",
        text_template_version="media-native-input-v1",
        modality="media",
        document_scope="local_media_files",
        source_kind_filter="local_x_media",
        language_filter="not_applicable",
        storage_rights_policy="provider-upload-reviewed-media",
        provider_role="media_embedding",
        status="planned",
        notes="Native media recall; candidate-only until media lineage restores.",
    ),
    EmbeddingSpaceDefinition(
        space_id="external.fetch_text.v1",
        provider=DEFAULT_TEXT_PROVIDER,
        model=DEFAULT_TEXT_MODEL,
        dimensions=DEFAULT_TEXT_DIMENSIONS,
        distance_metric=DEFAULT_DISTANCE_METRIC,
        embedding_profile="external_fetch_text",
        text_template_version=DEFAULT_TEXT_TEMPLATE_VERSION,
        modality="text",
        document_scope="memory_fetch_artifacts",
        source_kind_filter="external_fetch_text",
        language_filter="any",
        storage_rights_policy="approved-fetch-artifact-text",
        provider_role="text_embedding",
        status="planned",
        notes="Approved fetched/Reader artifacts after hash and prompt-injection review.",
    ),
    EmbeddingSpaceDefinition(
        space_id="text.temporal_event.v1",
        provider=DEFAULT_TEXT_PROVIDER,
        model=DEFAULT_TEXT_MODEL,
        dimensions=DEFAULT_TEXT_DIMENSIONS,
        distance_metric=DEFAULT_DISTANCE_METRIC,
        embedding_profile="temporal_event",
        text_template_version=DEFAULT_TEXT_TEMPLATE_VERSION,
        modality="text",
        document_scope="memory_documents",
        source_kind_filter="dated_status_text",
        language_filter="any",
        storage_rights_policy="local-db-derived-text",
        provider_role="text_embedding",
        status="planned",
        notes="Dated, chronological, event-sequence, and status-change recall.",
    ),
)

FINAL_EMBEDDING_SPACE_IDS = tuple(
    definition.space_id for definition in FINAL_EMBEDDING_SPACE_DEFINITIONS
)


@dataclass(frozen=True)
class EmbeddingSpacePlanReport:
    db_path: str
    final_space_count: int
    registered_space_count: int
    final_space_ids: tuple[str, ...]
    missing_final_space_ids: tuple[str, ...]
    status: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def ensure_final_embedding_spaces(
    conn: sqlite3.Connection,
    *,
    created_by_run_id: str | None = None,
) -> None:
    now = _utc_now()
    for definition in FINAL_EMBEDDING_SPACE_DEFINITIONS:
        _upsert_embedding_space(
            conn,
            definition.as_row(created_at=now, created_by_run_id=created_by_run_id),
            preserve_existing_status=True,
        )


def ensure_embedding_space_for_spec(
    conn: sqlite3.Connection,
    *,
    provider: str,
    model: str,
    dimensions: int,
    embedding_profile: str,
    text_template_version: str,
    modality: str = "text",
    document_scope: str = "memory_documents",
    source_kind_filter: str | None = None,
    language_filter: str | None = None,
    storage_rights_policy: str = "local-db-derived-text",
    provider_role: str = "text_embedding",
    distance_metric: str = DEFAULT_DISTANCE_METRIC,
    status: str = "active",
    created_by_run_id: str | None = None,
    notes: str = "",
) -> str:
    ensure_final_embedding_spaces(conn, created_by_run_id=created_by_run_id)
    identity = {
        "provider": _clean(provider),
        "model": _clean(model),
        "dimensions": int(dimensions),
        "distance_metric": _clean(distance_metric),
        "embedding_profile": _clean(embedding_profile),
        "text_template_version": _clean(text_template_version),
        "modality": _clean(modality),
        "document_scope": _clean(document_scope),
        "source_kind_filter": _clean(source_kind_filter) or "any",
        "language_filter": _clean(language_filter) or "any",
        "storage_rights_policy": _clean(storage_rights_policy),
        "provider_role": _clean(provider_role),
    }
    space_id = embedding_space_id_for_identity(identity)
    row = {
        **identity,
        "space_id": space_id,
        "status": status,
        "created_at": _utc_now(),
        "created_by_run_id": created_by_run_id,
        "notes": notes or "Concrete embedding space registered from runtime spec.",
    }
    _upsert_embedding_space(conn, row, preserve_existing_status=False)
    return space_id


def embedding_space_id_for_identity(identity: dict[str, Any]) -> str:
    base = _base_space_for_identity(identity)
    canonical = _identity_for_definition(base) if base else None
    comparable = {
        "provider": _clean(identity.get("provider")),
        "model": _clean(identity.get("model")),
        "dimensions": int(identity.get("dimensions") or 0),
        "distance_metric": _clean(identity.get("distance_metric") or DEFAULT_DISTANCE_METRIC),
        "embedding_profile": _clean(identity.get("embedding_profile")),
        "text_template_version": _clean(identity.get("text_template_version")),
        "modality": _clean(identity.get("modality")),
        "document_scope": _clean(identity.get("document_scope")),
        "source_kind_filter": _clean(identity.get("source_kind_filter")) or "any",
        "language_filter": _clean(identity.get("language_filter")) or "any",
        "storage_rights_policy": _clean(identity.get("storage_rights_policy")),
        "provider_role": _clean(identity.get("provider_role")),
    }
    if base and comparable == canonical:
        return base.space_id
    prefix = (
        base.space_id
        if base
        else f"{comparable['modality']}.{comparable['embedding_profile']}.v1"
    )
    digest = hashlib.sha256(
        json.dumps(comparable, ensure_ascii=False, sort_keys=True).encode()
    ).hexdigest()[:12]
    return f"{prefix}.space-{digest}"


def list_embedding_space_rows(db_path: str | Path) -> tuple[dict[str, Any], ...]:
    from research_x.memory.schema import ensure_memory_schema

    path = Path(db_path)
    if not path.exists():
        raise FileNotFoundError(f"database not found: {path}")
    with sqlite3.connect(path, timeout=60) as conn:
        conn.row_factory = sqlite3.Row
        ensure_memory_schema(conn)
        rows = conn.execute(
            """
            SELECT *
            FROM memory_embedding_spaces
            ORDER BY space_id
            """
        ).fetchall()
    return tuple(dict(row) for row in rows)


def plan_embedding_spaces(db_path: str | Path) -> EmbeddingSpacePlanReport:
    from research_x.memory.schema import ensure_memory_schema

    path = Path(db_path)
    if not path.exists():
        raise FileNotFoundError(f"database not found: {path}")
    with sqlite3.connect(path, timeout=60) as conn:
        conn.row_factory = sqlite3.Row
        ensure_memory_schema(conn)
        registered = {
            str(row["space_id"])
            for row in conn.execute("SELECT space_id FROM memory_embedding_spaces").fetchall()
        }
    missing = tuple(
        space_id for space_id in FINAL_EMBEDDING_SPACE_IDS if space_id not in registered
    )
    return EmbeddingSpacePlanReport(
        db_path=str(path),
        final_space_count=len(FINAL_EMBEDDING_SPACE_IDS),
        registered_space_count=len(registered),
        final_space_ids=FINAL_EMBEDDING_SPACE_IDS,
        missing_final_space_ids=missing,
        status="ready" if not missing else "missing_final_spaces",
    )


def embedding_spaces_json(rows: tuple[dict[str, Any], ...]) -> str:
    return json.dumps(rows, ensure_ascii=False, indent=2, sort_keys=True)


def embedding_space_plan_json(report: EmbeddingSpacePlanReport) -> str:
    return json.dumps(report.as_dict(), ensure_ascii=False, indent=2, sort_keys=True)


def format_embedding_space_rows(rows: tuple[dict[str, Any], ...]) -> str:
    if not rows:
        return "embedding spaces: none"
    lines = ["embedding spaces:"]
    for row in rows:
        lines.append(
            "  "
            f"{row['space_id']} "
            f"{row['provider']}/{row['model']} "
            f"dims={row['dimensions']} "
            f"profile={row['embedding_profile']} "
            f"modality={row['modality']} "
            f"scope={row['document_scope']} "
            f"status={row['status']}"
        )
    return "\n".join(lines)


def format_embedding_space_plan(report: EmbeddingSpacePlanReport) -> str:
    lines = [
        f"embedding-space-plan: {report.status}",
        f"final spaces: {report.final_space_count}",
        f"registered spaces: {report.registered_space_count}",
    ]
    if report.missing_final_space_ids:
        lines.append("missing:")
        lines.extend(f"  {space_id}" for space_id in report.missing_final_space_ids)
    else:
        lines.append("missing: none")
    return "\n".join(lines)


def _upsert_embedding_space(
    conn: sqlite3.Connection,
    row: dict[str, Any],
    *,
    preserve_existing_status: bool,
) -> None:
    conn.execute(
        """
        INSERT INTO memory_embedding_spaces (
            space_id, provider, model, dimensions, distance_metric,
            embedding_profile, text_template_version, modality, document_scope,
            source_kind_filter, language_filter, storage_rights_policy, provider_role,
            status, created_at, created_by_run_id, notes
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(space_id) DO UPDATE SET
            provider=excluded.provider,
            model=excluded.model,
            dimensions=excluded.dimensions,
            distance_metric=excluded.distance_metric,
            embedding_profile=excluded.embedding_profile,
            text_template_version=excluded.text_template_version,
            modality=excluded.modality,
            document_scope=excluded.document_scope,
            source_kind_filter=excluded.source_kind_filter,
            language_filter=excluded.language_filter,
            storage_rights_policy=excluded.storage_rights_policy,
            provider_role=excluded.provider_role,
            status=CASE
                WHEN ? THEN memory_embedding_spaces.status
                ELSE excluded.status
            END,
            created_by_run_id=COALESCE(
                excluded.created_by_run_id,
                memory_embedding_spaces.created_by_run_id
            ),
            notes=excluded.notes
        """,
        (
            row["space_id"],
            row["provider"],
            row["model"],
            int(row["dimensions"]),
            row["distance_metric"],
            row["embedding_profile"],
            row["text_template_version"],
            row["modality"],
            row["document_scope"],
            row["source_kind_filter"],
            row["language_filter"],
            row["storage_rights_policy"],
            row["provider_role"],
            row["status"],
            row["created_at"],
            row.get("created_by_run_id"),
            row.get("notes") or "",
            1 if preserve_existing_status else 0,
        ),
    )


def _base_space_for_identity(identity: dict[str, Any]) -> EmbeddingSpaceDefinition | None:
    profile = _clean(identity.get("embedding_profile"))
    modality = _clean(identity.get("modality"))
    document_scope = _clean(identity.get("document_scope"))
    for definition in FINAL_EMBEDDING_SPACE_DEFINITIONS:
        if definition.embedding_profile != profile:
            continue
        if definition.modality != modality:
            continue
        if definition.document_scope == document_scope:
            return definition
    for definition in FINAL_EMBEDDING_SPACE_DEFINITIONS:
        if definition.embedding_profile == profile and definition.modality == modality:
            return definition
    return None


def _identity_for_definition(definition: EmbeddingSpaceDefinition) -> dict[str, Any]:
    return {
        "provider": definition.provider,
        "model": definition.model,
        "dimensions": definition.dimensions,
        "distance_metric": definition.distance_metric,
        "embedding_profile": definition.embedding_profile,
        "text_template_version": definition.text_template_version,
        "modality": definition.modality,
        "document_scope": definition.document_scope,
        "source_kind_filter": definition.source_kind_filter,
        "language_filter": definition.language_filter,
        "storage_rights_policy": definition.storage_rights_policy,
        "provider_role": definition.provider_role,
    }


def _clean(value: object | None) -> str:
    return str(value or "").strip()


def _utc_now() -> str:
    return datetime.now(tz=UTC).isoformat()
