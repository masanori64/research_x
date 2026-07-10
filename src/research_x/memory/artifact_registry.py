from __future__ import annotations

import hashlib
import json
import sqlite3
from collections import Counter
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from research_x.memory import source_refs
from research_x.memory.artifact_roles import ArtifactRole
from research_x.memory.authority_levels import AuthorityLevel
from research_x.memory.output_modes import OutputMode
from research_x.memory.schema import ensure_memory_schema


@dataclass(frozen=True)
class ArtifactBackfillSummary:
    db_path: str
    artifacts: int
    links: int
    by_artifact_kind: dict[str, int]
    by_artifact_role: dict[str, int]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class _ArtifactRecord:
    artifact_id: str
    artifact_role: ArtifactRole
    artifact_kind: str
    source_refs: tuple[str, ...]
    content_hash: str | None
    authority_level: AuthorityLevel
    output_mode: OutputMode | None
    retention_policy: str
    artifact_status: str
    created_at: str
    updated_at: str
    metadata: dict[str, Any]


@dataclass(frozen=True)
class _ArtifactLink:
    source_artifact_id: str
    target_artifact_id: str
    relation_type: str
    link_status: str
    created_at: str
    metadata: dict[str, Any]


def backfill_memory_artifacts(db_path: str | Path) -> ArtifactBackfillSummary:
    path = Path(db_path)
    if not path.exists():
        raise FileNotFoundError(f"database not found: {path}")
    with sqlite3.connect(path, timeout=60) as conn:
        conn.row_factory = sqlite3.Row
        ensure_memory_schema(conn)
        artifacts = tuple(_iter_artifacts(conn))
        links = tuple(_iter_links(conn))
        for artifact in artifacts:
            _upsert_artifact(conn, artifact)
        for link in links:
            _upsert_link(conn, link)
        by_kind = Counter(artifact.artifact_kind for artifact in artifacts)
        by_role = Counter(artifact.artifact_role.value for artifact in artifacts)
    return ArtifactBackfillSummary(
        db_path=str(path),
        artifacts=len(artifacts),
        links=len(links),
        by_artifact_kind=dict(sorted(by_kind.items())),
        by_artifact_role=dict(sorted(by_role.items())),
    )


def _iter_artifacts(conn: sqlite3.Connection) -> Iterable[_ArtifactRecord]:
    if _table_exists(conn, "memory_documents"):
        for row in conn.execute("SELECT * FROM memory_documents ORDER BY doc_id"):
            data = _row_dict(row)
            yield _artifact(
                artifact_id=f"memory_document:{data['doc_id']}",
                artifact_role=ArtifactRole.PROJECTION,
                artifact_kind="memory_document",
                source_refs=_source_refs_from_tweet(data.get("source_tweet_id")),
                content_hash=data.get("source_doc_hash")
                or _stable_hash(
                    {
                        "body": data.get("body"),
                        "compact_text": data.get("compact_text"),
                        "metadata_json": data.get("metadata_json"),
                        "title": data.get("title"),
                    }
                ),
                authority_level=AuthorityLevel.SOURCE_BACKED
                if data.get("source_tweet_id")
                else AuthorityLevel.CANDIDATE,
                output_mode=OutputMode.EXPLORE,
                retention_policy="rebuildable_projection",
                artifact_status="active",
                created_at=data.get("created_at"),
                updated_at=data.get("updated_at"),
                metadata={"source_table": "memory_documents", "doc_id": data["doc_id"]},
            )
    if _table_exists(conn, "memory_retrieval_text_profiles"):
        for row in conn.execute(
            """
            SELECT p.*, d.source_tweet_id
            FROM memory_retrieval_text_profiles p
            LEFT JOIN memory_documents d ON d.doc_id = p.doc_id
            ORDER BY p.profile_id
            """
        ):
            data = _row_dict(row)
            yield _artifact(
                artifact_id=f"retrieval_text:{data['profile_id']}",
                artifact_role=ArtifactRole.PROJECTION,
                artifact_kind="memory_retrieval_text_profile",
                source_refs=_source_refs_from_tweet(data.get("source_tweet_id")),
                content_hash=data.get("source_doc_hash")
                or _stable_hash(data.get("retrieval_text")),
                authority_level=AuthorityLevel.CANDIDATE,
                output_mode=OutputMode.EXPLORE,
                retention_policy="rebuildable_projection",
                artifact_status="active",
                created_at=data.get("created_at"),
                updated_at=data.get("created_at"),
                metadata={
                    "source_table": "memory_retrieval_text_profiles",
                    "doc_id": data.get("doc_id"),
                    "profile_id": data["profile_id"],
                },
            )
    if _table_exists(conn, "memory_embeddings"):
        for row in conn.execute(
            """
            SELECT e.*, d.source_tweet_id
            FROM memory_embeddings e
            LEFT JOIN memory_documents d ON d.doc_id = e.doc_id
            ORDER BY e.doc_id, e.provider, e.model, e.dimensions,
                     e.embedding_profile, e.text_template_version
            """
        ):
            data = _row_dict(row)
            yield _artifact(
                artifact_id=(
                    "embedding:"
                    f"{data['doc_id']}:{data['provider']}:{data['model']}:"
                    f"{data['dimensions']}:{data['embedding_profile']}:"
                    f"{data['text_template_version']}"
                ),
                artifact_role=ArtifactRole.PROJECTION,
                artifact_kind="memory_embedding",
                source_refs=_source_refs_from_tweet(data.get("source_tweet_id")),
                content_hash=data.get("embedded_text_hash"),
                authority_level=AuthorityLevel.CANDIDATE,
                output_mode=OutputMode.EXPLORE,
                retention_policy="rebuildable_projection",
                artifact_status="active",
                created_at=data.get("created_at"),
                updated_at=data.get("updated_at"),
                metadata={
                    "doc_id": data.get("doc_id"),
                    "provider": data.get("provider"),
                    "source_table": "memory_embeddings",
                },
            )
    if _table_exists(conn, "memory_media_embeddings"):
        for row in conn.execute(
            """
            SELECT *
            FROM memory_media_embeddings
            ORDER BY media_id, provider, model, dimensions,
                     embedding_profile, input_template_version
            """
        ):
            data = _row_dict(row)
            yield _artifact(
                artifact_id=(
                    "media_embedding:"
                    f"{data['media_id']}:{data['provider']}:{data['model']}:"
                    f"{data['dimensions']}:{data['embedding_profile']}:"
                    f"{data['input_template_version']}"
                ),
                artifact_role=ArtifactRole.PROJECTION,
                artifact_kind="memory_media_embedding",
                source_refs=_dedupe_refs(
                    (
                        f"x:media:{data['media_id']}",
                        *_source_refs_from_tweet(data.get("source_tweet_id")),
                    )
                ),
                content_hash=data.get("media_metadata_hash"),
                authority_level=AuthorityLevel.CANDIDATE,
                output_mode=OutputMode.EXPLORE,
                retention_policy="rebuildable_projection",
                artifact_status="active",
                created_at=data.get("created_at"),
                updated_at=data.get("updated_at"),
                metadata={
                    "media_id": data.get("media_id"),
                    "provider": data.get("provider"),
                    "source_table": "memory_media_embeddings",
                },
            )
    if _table_exists(conn, "memory_ocr_texts"):
        for row in conn.execute("SELECT * FROM memory_ocr_texts ORDER BY text_id"):
            data = _row_dict(row)
            yield _artifact(
                artifact_id=f"ocr_text:{data['text_id']}",
                artifact_role=ArtifactRole.DERIVED_SIGNAL,
                artifact_kind="memory_ocr_text",
                source_refs=_dedupe_refs((f"x:media:{data['media_id']}",)),
                content_hash=data.get("region_hash")
                or _stable_hash(data.get("normalized_text")),
                authority_level=AuthorityLevel.SOURCE_BACKED,
                output_mode=OutputMode.EXPLORE,
                retention_policy="reviewable_signal",
                artifact_status=data.get("evidence_status") or "active",
                created_at=data.get("created_at"),
                updated_at=data.get("created_at"),
                metadata={
                    "media_id": data.get("media_id"),
                    "source_table": "memory_ocr_texts",
                    "text_profile": data.get("text_profile"),
                },
            )
    if _table_exists(conn, "ai_labels"):
        for row in conn.execute("SELECT * FROM ai_labels ORDER BY label_id"):
            data = _row_dict(row)
            yield _artifact(
                artifact_id=f"ai_label:{data['label_id']}",
                artifact_role=ArtifactRole.DERIVED_SIGNAL,
                artifact_kind="ai_label",
                source_refs=_source_refs_from_tweet(data.get("tweet_id")),
                content_hash=_stable_hash(
                    {
                        "category_id": data.get("category_id"),
                        "category_label": data.get("category_label"),
                        "confidence": data.get("confidence"),
                        "rationale": data.get("rationale"),
                        "summary": data.get("summary"),
                        "tags_json": data.get("tags_json"),
                    }
                ),
                authority_level=AuthorityLevel.SOURCE_BACKED
                if data.get("tweet_id")
                else AuthorityLevel.CANDIDATE,
                output_mode=OutputMode.EXPLORE,
                retention_policy="reviewable_signal",
                artifact_status="active",
                created_at=data.get("generated_at"),
                updated_at=data.get("generated_at"),
                metadata={
                    "account_id": data.get("account_id"),
                    "label_scope": data.get("label_scope"),
                    "model": data.get("model"),
                    "source_table": "ai_labels",
                    "tweet_id": data.get("tweet_id"),
                },
            )
    if _table_exists(conn, "memory_context_chunks"):
        for row in conn.execute("SELECT * FROM memory_context_chunks ORDER BY chunk_id"):
            data = _row_dict(row)
            yield _artifact(
                artifact_id=f"context_chunk:{data['chunk_id']}",
                artifact_role=ArtifactRole.EVIDENCE_VIEW,
                artifact_kind="memory_context_chunk",
                source_refs=_source_refs_from_kind_id(
                    data.get("source_kind"),
                    data.get("source_id"),
                ),
                content_hash=_stable_hash(
                    {
                        "chunk_text": data.get("chunk_text"),
                        "offset_end": data.get("offset_end"),
                        "offset_start": data.get("offset_start"),
                        "source_id": data.get("source_id"),
                        "source_kind": data.get("source_kind"),
                    }
                ),
                authority_level=AuthorityLevel.EVIDENCE_VIEW,
                output_mode=OutputMode.EVIDENCE_PACKAGE,
                retention_policy="evidence_lineage",
                artifact_status="active",
                created_at=data.get("created_at"),
                updated_at=data.get("created_at"),
                metadata={
                    "chunk_id": data.get("chunk_id"),
                    "source_table": "memory_context_chunks",
                },
            )
    if _table_exists(conn, "memory_citation_annotations"):
        for row in conn.execute(
            "SELECT * FROM memory_citation_annotations ORDER BY citation_id"
        ):
            data = _row_dict(row)
            yield _artifact(
                artifact_id=f"citation:{data['citation_id']}",
                artifact_role=ArtifactRole.EVIDENCE_VIEW,
                artifact_kind="memory_citation_annotation",
                source_refs=_source_refs_from_kind_id(
                    data.get("source_kind"),
                    data.get("source_id"),
                ),
                content_hash=_stable_hash(
                    {
                        "chunk_id": data.get("chunk_id"),
                        "field_path": data.get("field_path"),
                        "source_id": data.get("source_id"),
                        "source_kind": data.get("source_kind"),
                    }
                ),
                authority_level=AuthorityLevel.EVIDENCE_VIEW,
                output_mode=OutputMode.EVIDENCE_PACKAGE,
                retention_policy="evidence_lineage",
                artifact_status=data.get("evidence_status") or "active",
                created_at=data.get("created_at"),
                updated_at=data.get("created_at"),
                metadata={
                    "citation_id": data.get("citation_id"),
                    "chunk_id": data.get("chunk_id"),
                    "source_table": "memory_citation_annotations",
                },
            )
    if _table_exists(conn, "memory_workflow_runs"):
        for row in conn.execute("SELECT * FROM memory_workflow_runs ORDER BY workflow_id"):
            data = _row_dict(row)
            yield _artifact(
                artifact_id=f"workflow_run:{data['workflow_id']}",
                artifact_role=ArtifactRole.CONTROL_STATE,
                artifact_kind="memory_workflow_run",
                source_refs=(),
                content_hash=_stable_hash(data),
                authority_level=AuthorityLevel.NAVIGATION_SIGNAL,
                output_mode=OutputMode.EXPLORE,
                retention_policy="operational_trace",
                artifact_status=data.get("status") or "active",
                created_at=data.get("started_at"),
                updated_at=data.get("finished_at") or data.get("started_at"),
                metadata={"source_table": "memory_workflow_runs"},
            )
    if _table_exists(conn, "memory_projection_generations"):
        for row in conn.execute(
            "SELECT * FROM memory_projection_generations ORDER BY generation_id"
        ):
            data = _row_dict(row)
            yield _artifact(
                artifact_id=f"projection_generation:{data['generation_id']}",
                artifact_role=ArtifactRole.CONTROL_STATE,
                artifact_kind="memory_projection_generation",
                source_refs=(),
                content_hash=_stable_hash(data.get("input_manifest_json")),
                authority_level=AuthorityLevel.NAVIGATION_SIGNAL,
                output_mode=OutputMode.EXPLORE,
                retention_policy="projection_lifecycle",
                artifact_status=data.get("status") or "active",
                created_at=data.get("created_at"),
                updated_at=data.get("created_at"),
                metadata={
                    "generation_id": data.get("generation_id"),
                    "source_table": "memory_projection_generations",
                },
            )
    if _table_exists(conn, "memory_index_membership"):
        for row in conn.execute(
            "SELECT * FROM memory_index_membership ORDER BY membership_id"
        ):
            data = _row_dict(row)
            yield _artifact(
                artifact_id=f"index_membership:{data['membership_id']}",
                artifact_role=ArtifactRole.CONTROL_STATE,
                artifact_kind="memory_index_membership",
                source_refs=_dedupe_refs((data.get("source_id"),)),
                content_hash=data.get("source_hash") or _stable_hash(data),
                authority_level=AuthorityLevel.NAVIGATION_SIGNAL,
                output_mode=OutputMode.EXPLORE,
                retention_policy="projection_lifecycle",
                artifact_status=data.get("membership_status") or "active",
                created_at=data.get("created_at"),
                updated_at=data.get("created_at"),
                metadata={
                    "artifact_id": data.get("artifact_id"),
                    "generation_id": data.get("generation_id"),
                    "source_table": "memory_index_membership",
                },
            )


def _iter_links(conn: sqlite3.Connection) -> Iterable[_ArtifactLink]:
    if _table_exists(conn, "memory_retrieval_text_profiles"):
        for row in conn.execute(
            """
            SELECT profile_id, doc_id, created_at
            FROM memory_retrieval_text_profiles
            """
        ):
            yield _link(
                source_artifact_id=f"retrieval_text:{row['profile_id']}",
                target_artifact_id=f"memory_document:{row['doc_id']}",
                relation_type="derived_from",
                created_at=row["created_at"],
                metadata={"source_table": "memory_retrieval_text_profiles"},
            )
    if _table_exists(conn, "memory_embeddings"):
        for row in conn.execute(
            """
            SELECT doc_id, provider, model, dimensions, embedding_profile,
                   text_template_version, created_at
            FROM memory_embeddings
            """
        ):
            yield _link(
                source_artifact_id=(
                    "embedding:"
                    f"{row['doc_id']}:{row['provider']}:{row['model']}:"
                    f"{row['dimensions']}:{row['embedding_profile']}:"
                    f"{row['text_template_version']}"
                ),
                target_artifact_id=f"memory_document:{row['doc_id']}",
                relation_type="derived_from",
                created_at=row["created_at"],
                metadata={"source_table": "memory_embeddings"},
            )
    if _table_exists(conn, "memory_citation_annotations"):
        for row in conn.execute(
            "SELECT citation_id, chunk_id, created_at FROM memory_citation_annotations"
        ):
            yield _link(
                source_artifact_id=f"citation:{row['citation_id']}",
                target_artifact_id=f"context_chunk:{row['chunk_id']}",
                relation_type="annotates",
                created_at=row["created_at"],
                metadata={"source_table": "memory_citation_annotations"},
            )
    if _table_exists(conn, "ai_labels") and _table_exists(conn, "memory_documents"):
        for row in conn.execute(
            """
            SELECT l.label_id, l.generated_at, d.doc_id
            FROM ai_labels l
            JOIN memory_documents d ON d.source_tweet_id = l.tweet_id
            ORDER BY l.label_id, d.doc_id
            """
        ):
            yield _link(
                source_artifact_id=f"ai_label:{row['label_id']}",
                target_artifact_id=f"memory_document:{row['doc_id']}",
                relation_type="describes",
                created_at=row["generated_at"],
                metadata={"source_table": "ai_labels"},
            )


def _artifact(
    *,
    artifact_id: str,
    artifact_role: ArtifactRole,
    artifact_kind: str,
    source_refs: tuple[str, ...],
    content_hash: str | None,
    authority_level: AuthorityLevel,
    output_mode: OutputMode | None,
    retention_policy: str,
    artifact_status: str,
    created_at: str | None,
    updated_at: str | None,
    metadata: dict[str, Any],
) -> _ArtifactRecord:
    timestamp = created_at or updated_at or ""
    return _ArtifactRecord(
        artifact_id=artifact_id,
        artifact_role=artifact_role,
        artifact_kind=artifact_kind,
        source_refs=_dedupe_refs(source_refs),
        content_hash=content_hash,
        authority_level=authority_level,
        output_mode=output_mode,
        retention_policy=retention_policy,
        artifact_status=artifact_status,
        created_at=timestamp,
        updated_at=updated_at or timestamp,
        metadata=metadata,
    )


def _link(
    *,
    source_artifact_id: str,
    target_artifact_id: str,
    relation_type: str,
    created_at: str,
    metadata: dict[str, Any],
) -> _ArtifactLink:
    return _ArtifactLink(
        source_artifact_id=source_artifact_id,
        target_artifact_id=target_artifact_id,
        relation_type=relation_type,
        link_status="active",
        created_at=created_at,
        metadata=metadata,
    )


def _upsert_artifact(conn: sqlite3.Connection, artifact: _ArtifactRecord) -> None:
    conn.execute(
        """
        INSERT INTO memory_artifacts (
            artifact_id, artifact_role, artifact_kind, source_refs_json,
            content_hash, authority_level, output_mode, retention_policy,
            artifact_status, created_at, updated_at, metadata_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(artifact_id) DO UPDATE SET
            artifact_role=excluded.artifact_role,
            artifact_kind=excluded.artifact_kind,
            source_refs_json=excluded.source_refs_json,
            content_hash=excluded.content_hash,
            authority_level=excluded.authority_level,
            output_mode=excluded.output_mode,
            retention_policy=excluded.retention_policy,
            artifact_status=excluded.artifact_status,
            updated_at=excluded.updated_at,
            metadata_json=excluded.metadata_json
        """,
        (
            artifact.artifact_id,
            artifact.artifact_role.value,
            artifact.artifact_kind,
            _json(list(artifact.source_refs)),
            artifact.content_hash,
            artifact.authority_level.value,
            artifact.output_mode.value if artifact.output_mode else None,
            artifact.retention_policy,
            artifact.artifact_status,
            artifact.created_at,
            artifact.updated_at,
            _json(artifact.metadata),
        ),
    )


def _upsert_link(conn: sqlite3.Connection, link: _ArtifactLink) -> None:
    link_id = _stable_hash(
        {
            "relation_type": link.relation_type,
            "source_artifact_id": link.source_artifact_id,
            "target_artifact_id": link.target_artifact_id,
        }
    )
    conn.execute(
        """
        INSERT INTO memory_artifact_links (
            link_id, source_artifact_id, target_artifact_id, relation_type,
            link_status, created_at, metadata_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(link_id) DO UPDATE SET
            link_status=excluded.link_status,
            metadata_json=excluded.metadata_json
        """,
        (
            link_id,
            link.source_artifact_id,
            link.target_artifact_id,
            link.relation_type,
            link.link_status,
            link.created_at,
            _json(link.metadata),
        ),
    )


def _source_refs_from_tweet(tweet_id: Any) -> tuple[str, ...]:
    if not tweet_id:
        return ()
    return (source_refs.x_tweet(tweet_id),)


def _source_refs_from_kind_id(source_kind: Any, source_id: Any) -> tuple[str, ...]:
    if not source_id:
        return ()
    if source_kind == "tweet":
        return (source_refs.x_tweet(source_id),)
    if source_kind == "media":
        return (source_refs.x_media(source_id),)
    return (f"{source_kind}:{source_id}",)


def _dedupe_refs(values: Iterable[Any]) -> tuple[str, ...]:
    refs: list[str] = []
    for value in values:
        if value is None:
            continue
        text = str(value)
        if not text or text in refs:
            continue
        refs.append(text)
    return tuple(refs)


def _table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    return (
        conn.execute(
            """
            SELECT 1
            FROM sqlite_master
            WHERE type = 'table' AND name = ?
            """,
            (table_name,),
        ).fetchone()
        is not None
    )


def _row_dict(row: sqlite3.Row) -> dict[str, Any]:
    return dict(row)


def _stable_hash(value: Any) -> str:
    return hashlib.sha256(_json(value).encode("utf-8")).hexdigest()


def _json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
