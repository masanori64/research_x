from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from research_x.memory.evidence import build_evidence_bundle
from research_x.memory.schema import ensure_memory_schema

EXTRACTOR_VERSION = "local-evidence-context-v1"


@dataclass(frozen=True)
class ContextChunk:
    chunk_id: str
    run_id: str
    source_kind: str
    source_id: str
    source_url: str | None
    provider: str
    provider_role: str
    chunk_text: str
    chunk_index: int
    token_count: int
    relevance_score: float
    extractor_version: str
    created_at: str
    metadata: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {
            "chunk_id": self.chunk_id,
            "run_id": self.run_id,
            "source_kind": self.source_kind,
            "source_id": self.source_id,
            "source_url": self.source_url,
            "provider": self.provider,
            "provider_role": self.provider_role,
            "chunk_text": self.chunk_text,
            "chunk_index": self.chunk_index,
            "token_count": self.token_count,
            "relevance_score": self.relevance_score,
            "extractor_version": self.extractor_version,
            "created_at": self.created_at,
            "metadata": self.metadata,
        }


@dataclass(frozen=True)
class CitationAnnotation:
    citation_id: str
    answer_id: str | None
    chunk_id: str
    source_kind: str
    source_id: str
    source_url: str | None
    title: str
    field_path: str
    support_type: str
    evidence_status: str
    confidence: float
    created_at: str
    metadata: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {
            "citation_id": self.citation_id,
            "answer_id": self.answer_id,
            "chunk_id": self.chunk_id,
            "source_kind": self.source_kind,
            "source_id": self.source_id,
            "source_url": self.source_url,
            "title": self.title,
            "field_path": self.field_path,
            "support_type": self.support_type,
            "evidence_status": self.evidence_status,
            "confidence": self.confidence,
            "created_at": self.created_at,
            "metadata": self.metadata,
        }


@dataclass(frozen=True)
class ContextBundle:
    run_id: str
    query: str
    query_plan: dict[str, Any]
    parameters: dict[str, Any]
    retrieved_hits: list[dict[str, Any]]
    context_chunks: tuple[ContextChunk, ...]
    citation_annotations: tuple[CitationAnnotation, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "query": self.query,
            "query_plan": self.query_plan,
            "parameters": self.parameters,
            "retrieved_hits": self.retrieved_hits,
            "context_chunks": [chunk.as_dict() for chunk in self.context_chunks],
            "citation_annotations": [
                citation.as_dict() for citation in self.citation_annotations
            ],
        }


def build_context_bundle(
    db_path: str | Path,
    query: str,
    *,
    limit: int = 5,
    doc_type: str | None = None,
    account: str | None = None,
    semantic_provider: str | None = None,
    semantic_model: str | None = None,
    semantic_dimensions: int | None = None,
    semantic_api_key_env: str | None = None,
    semantic_base_url: str | None = None,
    semantic_weight: float = 3.0,
    semantic_candidates: int = 80,
    store: bool = True,
) -> ContextBundle:
    parameters = {
        "limit": max(1, limit),
        "doc_type": doc_type,
        "account": account,
        "semantic_provider": semantic_provider,
        "semantic_model": semantic_model,
        "semantic_dimensions": semantic_dimensions,
        "semantic_api_key_env": semantic_api_key_env,
        "semantic_base_url": semantic_base_url,
        "semantic_weight": semantic_weight,
        "semantic_candidates": semantic_candidates,
    }
    started_at = _utc_now()
    evidence = build_evidence_bundle(
        db_path,
        query,
        limit=limit,
        doc_type=doc_type,
        account=account,
        semantic_provider=semantic_provider,
        semantic_model=semantic_model,
        semantic_dimensions=semantic_dimensions,
        semantic_api_key_env=semantic_api_key_env,
        semantic_base_url=semantic_base_url,
        semantic_weight=semantic_weight,
        semantic_candidates=semantic_candidates,
    )
    finished_at = _utc_now()
    hits = list(evidence["hits"])
    run_id = _run_id(query, evidence["query_plan"], parameters, started_at)
    chunks = tuple(
        _chunk(
            run_id=run_id,
            query=query,
            hit=hit,
            index=index,
            created_at=finished_at,
        )
        for index, hit in enumerate(hits)
    )
    citations = tuple(
        _citation(chunk=chunk, hit=hit, index=index, created_at=finished_at)
        for index, (chunk, hit) in enumerate(zip(chunks, hits, strict=True))
    )
    bundle = ContextBundle(
        run_id=run_id,
        query=query,
        query_plan=evidence["query_plan"],
        parameters=parameters,
        retrieved_hits=hits,
        context_chunks=chunks,
        citation_annotations=citations,
    )
    if store:
        _store_context_bundle(
            db_path,
            bundle,
            started_at=started_at,
            finished_at=finished_at,
        )
    return bundle


def context_bundle_json(bundle: ContextBundle) -> str:
    return json.dumps(bundle.as_dict(), ensure_ascii=False, indent=2, sort_keys=True)


def _chunk(
    *,
    run_id: str,
    query: str,
    hit: dict[str, Any],
    index: int,
    created_at: str,
) -> ContextChunk:
    evidence = hit.get("evidence") or {}
    source_url = _string_or_none(evidence.get("url"))
    source_id = str(hit["doc_id"])
    text = _chunk_text(query=query, hit=hit, evidence=evidence)
    metadata = {
        "doc_type": hit.get("doc_type"),
        "tweet_id": hit.get("tweet_id"),
        "matched_terms": hit.get("matched_terms") or [],
        "score_components": hit.get("score_components") or {},
        "freshness": hit.get("freshness"),
        "bookmark_account_count": hit.get("bookmark_account_count"),
    }
    chunk_id = _hash_id(
        "chunk",
        run_id,
        source_id,
        str(index),
        hashlib.sha256(text.encode("utf-8")).hexdigest(),
    )
    return ContextChunk(
        chunk_id=chunk_id,
        run_id=run_id,
        source_kind="local_x_db",
        source_id=source_id,
        source_url=source_url,
        provider="local_memory",
        provider_role="context_builder",
        chunk_text=text,
        chunk_index=index,
        token_count=_estimate_tokens(text),
        relevance_score=float(hit.get("score") or 0.0),
        extractor_version=EXTRACTOR_VERSION,
        created_at=created_at,
        metadata=metadata,
    )


def _citation(
    *,
    chunk: ContextChunk,
    hit: dict[str, Any],
    index: int,
    created_at: str,
) -> CitationAnnotation:
    source_url = chunk.source_url
    evidence_status = "fact" if source_url or hit.get("tweet_id") else "unconfirmed"
    title = str(hit.get("title") or chunk.source_id)
    citation_id = _hash_id("citation", chunk.run_id, chunk.chunk_id, str(index), source_url or "")
    return CitationAnnotation(
        citation_id=citation_id,
        answer_id=None,
        chunk_id=chunk.chunk_id,
        source_kind=chunk.source_kind,
        source_id=chunk.source_id,
        source_url=source_url,
        title=title,
        field_path=f"context_chunks[{index}]",
        support_type="background",
        evidence_status=evidence_status,
        confidence=1.0 if evidence_status == "fact" else 0.4,
        created_at=created_at,
        metadata={
            "doc_type": hit.get("doc_type"),
            "tweet_id": hit.get("tweet_id"),
            "author": (hit.get("evidence") or {}).get("author"),
        },
    )


def _chunk_text(*, query: str, hit: dict[str, Any], evidence: dict[str, Any]) -> str:
    parts = [
        f"Query: {query}",
        f"Source: {hit.get('doc_type')} {hit.get('doc_id')}",
        f"Title: {hit.get('title') or ''}",
        f"Author: {evidence.get('author') or ''}",
        f"URL: {evidence.get('url') or ''}",
        f"Why relevant: {hit.get('why_relevant') or ''}",
        f"Text: {hit.get('compact_text') or ''}",
    ]
    quoted = evidence.get("quoted_tweets") or []
    if quoted:
        quote_lines = [
            f"- @{row.get('author') or ''}: {row.get('text') or ''} {row.get('url') or ''}".strip()
            for row in quoted[:3]
            if isinstance(row, dict)
        ]
        if quote_lines:
            parts.append("Quoted tweets:\n" + "\n".join(quote_lines))
    media = evidence.get("media") or []
    if media:
        media_lines = [
            (
                f"- {row.get('type') or ''} status={row.get('download_status') or ''} "
                f"alt={row.get('alt_text') or ''} path={row.get('local_path') or ''}"
            ).strip()
            for row in media[:4]
            if isinstance(row, dict)
        ]
        if media_lines:
            parts.append("Media:\n" + "\n".join(media_lines))
    relations = evidence.get("relations") or []
    if relations:
        relation_lines = [
            (
                f"- {row.get('relation_type')}: {row.get('source_doc_id')} -> "
                f"{row.get('target_doc_id')} strength={row.get('strength')}"
            )
            for row in relations[:4]
            if isinstance(row, dict)
        ]
        if relation_lines:
            parts.append("Relations:\n" + "\n".join(relation_lines))
    return "\n".join(part for part in parts if part.strip())


def _store_context_bundle(
    db_path: str | Path,
    bundle: ContextBundle,
    *,
    started_at: str,
    finished_at: str,
) -> None:
    path = Path(db_path)
    with sqlite3.connect(path, timeout=60) as conn:
        ensure_memory_schema(conn)
        conn.execute(
            """
            INSERT INTO memory_search_runs (
                run_id, query, query_plan_json, parameters_json, status,
                result_count, started_at, finished_at, error
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(run_id) DO UPDATE SET
                status=excluded.status,
                result_count=excluded.result_count,
                finished_at=excluded.finished_at,
                error=excluded.error
            """,
            (
                bundle.run_id,
                bundle.query,
                json.dumps(bundle.query_plan, ensure_ascii=False, sort_keys=True),
                json.dumps(bundle.parameters, ensure_ascii=False, sort_keys=True),
                "ok",
                len(bundle.retrieved_hits),
                started_at,
                finished_at,
                None,
            ),
        )
        for chunk in bundle.context_chunks:
            conn.execute(
                """
                INSERT INTO memory_context_chunks (
                    chunk_id, run_id, source_kind, source_id, source_url,
                    provider, provider_role, chunk_text, chunk_index,
                    offset_start, offset_end, token_count, relevance_score,
                    extractor_version, created_at, metadata_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(chunk_id) DO UPDATE SET
                    chunk_text=excluded.chunk_text,
                    token_count=excluded.token_count,
                    relevance_score=excluded.relevance_score,
                    metadata_json=excluded.metadata_json
                """,
                (
                    chunk.chunk_id,
                    chunk.run_id,
                    chunk.source_kind,
                    chunk.source_id,
                    chunk.source_url,
                    chunk.provider,
                    chunk.provider_role,
                    chunk.chunk_text,
                    chunk.chunk_index,
                    None,
                    None,
                    chunk.token_count,
                    chunk.relevance_score,
                    chunk.extractor_version,
                    chunk.created_at,
                    json.dumps(chunk.metadata, ensure_ascii=False, sort_keys=True),
                ),
            )
        for citation in bundle.citation_annotations:
            conn.execute(
                """
                INSERT INTO memory_citation_annotations (
                    citation_id, answer_id, chunk_id, source_kind, source_id,
                    source_url, title, answer_start_index, answer_end_index,
                    field_path, support_type, evidence_status, confidence,
                    created_at, metadata_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(citation_id) DO UPDATE SET
                    title=excluded.title,
                    field_path=excluded.field_path,
                    support_type=excluded.support_type,
                    evidence_status=excluded.evidence_status,
                    confidence=excluded.confidence,
                    metadata_json=excluded.metadata_json
                """,
                (
                    citation.citation_id,
                    citation.answer_id,
                    citation.chunk_id,
                    citation.source_kind,
                    citation.source_id,
                    citation.source_url,
                    citation.title,
                    None,
                    None,
                    citation.field_path,
                    citation.support_type,
                    citation.evidence_status,
                    citation.confidence,
                    citation.created_at,
                    json.dumps(citation.metadata, ensure_ascii=False, sort_keys=True),
                ),
            )


def _run_id(
    query: str,
    query_plan: dict[str, Any],
    parameters: dict[str, Any],
    started_at: str,
) -> str:
    return _hash_id(
        "search-run",
        query,
        json.dumps(query_plan, ensure_ascii=False, sort_keys=True),
        json.dumps(parameters, ensure_ascii=False, sort_keys=True),
        started_at,
    )[:24]


def _hash_id(*parts: str) -> str:
    return hashlib.sha256("\0".join(parts).encode("utf-8")).hexdigest()


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _string_or_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _estimate_tokens(text: str) -> int:
    ascii_words = len([part for part in text.split() if part])
    non_ascii = sum(1 for char in text if ord(char) > 127)
    return max(1, ascii_words + (non_ascii + 1) // 2)
