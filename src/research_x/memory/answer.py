from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from research_x.memory.api_budget import api_units, budgeted_api_call, rough_text_tokens
from research_x.memory.context import (
    CitationAnnotation,
    ContextBundle,
    ContextChunk,
    build_context_bundle,
)
from research_x.memory.context_budget import ContextBudgetPolicy, budgeted_json
from research_x.memory.schema import ensure_memory_schema

ANSWER_ENGINE_ROLE = "answer_engine"
DEFAULT_PROMPT_VERSION = "memory-answer-v1"
FAKE_ANSWER_MODEL = "fake-answer-v1"
DEFAULT_OPENAI_MODEL = "gpt-4o-mini"
DEFAULT_GEMINI_MODEL = "gemini-2.5-flash"

OPENAI_COMPATIBLE_PRESETS = {
    "openai_chat": {
        "base_url": "https://api.openai.com/v1",
        "api_key_env": "OPENAI_API_KEY",
        "model": DEFAULT_OPENAI_MODEL,
    },
    "gemini": {
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
        "api_key_env": "GEMINI_API_KEY",
        "model": DEFAULT_GEMINI_MODEL,
    },
}


@dataclass(frozen=True)
class GeneratedAnswer:
    answer_text: str
    model: str
    structured: dict[str, Any]
    raw_response_hash: str | None = None


@dataclass(frozen=True)
class AnswerCitation:
    citation_id: str
    answer_id: str
    chunk_id: str
    source_kind: str
    source_id: str
    source_url: str | None
    title: str
    answer_start_index: int | None
    answer_end_index: int | None
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
            "answer_start_index": self.answer_start_index,
            "answer_end_index": self.answer_end_index,
            "field_path": self.field_path,
            "support_type": self.support_type,
            "evidence_status": self.evidence_status,
            "confidence": self.confidence,
            "created_at": self.created_at,
            "metadata": self.metadata,
        }


@dataclass(frozen=True)
class MemoryAnswer:
    answer_id: str
    question: str
    workflow_id: str | None
    context_run_id: str
    provider: str
    provider_role: str
    model: str
    prompt_version: str
    retrieval_config: dict[str, Any]
    answer_text: str
    structured: dict[str, Any]
    status: str
    created_at: str
    citation_annotations: tuple[AnswerCitation, ...]
    context_bundle: ContextBundle
    selected_context_chunks: tuple[ContextChunk, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "answer_id": self.answer_id,
            "question": self.question,
            "workflow_id": self.workflow_id,
            "context_run_id": self.context_run_id,
            "provider": self.provider,
            "provider_role": self.provider_role,
            "model": self.model,
            "prompt_version": self.prompt_version,
            "retrieval_config": self.retrieval_config,
            "answer_text": self.answer_text,
            "structured": self.structured,
            "status": self.status,
            "created_at": self.created_at,
            "selected_context_chunks": [
                chunk.as_dict() for chunk in self.selected_context_chunks
            ],
            "citation_annotations": [
                citation.as_dict() for citation in self.citation_annotations
            ],
            "context_bundle": self.context_bundle.as_dict(),
        }


@dataclass(frozen=True)
class ChunkSelection:
    chunks: tuple[ContextChunk, ...]
    omitted_chunk_ids: tuple[str, ...]
    omitted_char_count: int
    truncated_chunk_ids: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "selected_chunk_ids": [chunk.chunk_id for chunk in self.chunks],
            "omitted_chunk_ids": list(self.omitted_chunk_ids),
            "omitted_char_count": self.omitted_char_count,
            "truncated_chunk_ids": list(self.truncated_chunk_ids),
        }


class AnswerProvider(Protocol):
    provider_id: str
    provider_role: str
    model: str

    def generate(
        self,
        *,
        question: str,
        chunks: tuple[ContextChunk, ...],
        citations: tuple[CitationAnnotation, ...],
        prompt_version: str,
    ) -> GeneratedAnswer:
        """Generate an answer from already-grounded context chunks."""


class FakeAnswerProvider:
    provider_id = "fake"
    provider_role = ANSWER_ENGINE_ROLE

    def __init__(self, *, model: str = FAKE_ANSWER_MODEL) -> None:
        self.model = model

    def generate(
        self,
        *,
        question: str,
        chunks: tuple[ContextChunk, ...],
        citations: tuple[CitationAnnotation, ...],
        prompt_version: str,
    ) -> GeneratedAnswer:
        if not chunks:
            return GeneratedAnswer(
                answer_text=(
                    "根拠になるコンテキストが見つかりませんでした。"
                    "追加取得または検索条件の変更が必要です。"
                ),
                model=self.model,
                structured={
                    "mode": "deterministic_fake",
                    "prompt_version": prompt_version,
                    "used_chunk_ids": [],
                },
            )

        lines = [
            f"質問: {question}",
            "根拠ベースの回答:",
        ]
        used_chunk_ids: list[str] = []
        for index, chunk in enumerate(chunks, start=1):
            citation = citations[index - 1] if index <= len(citations) else None
            title = citation.title if citation else chunk.source_id
            excerpt = _best_excerpt(chunk.chunk_text)
            lines.append(f"- {title}: {excerpt} [{index}]")
            used_chunk_ids.append(chunk.chunk_id)
        lines.append("推論: 上記コンテキスト外の補完はしていません。")
        return GeneratedAnswer(
            answer_text="\n".join(lines),
            model=self.model,
            structured={
                "mode": "deterministic_fake",
                "prompt_version": prompt_version,
                "used_chunk_ids": used_chunk_ids,
            },
        )


class OpenAICompatibleAnswerProvider:
    provider_role = ANSWER_ENGINE_ROLE

    def __init__(
        self,
        *,
        provider_id: str,
        base_url: str,
        api_key_env: str,
        model: str,
        timeout_seconds: float,
    ) -> None:
        self.provider_id = provider_id
        self.base_url = base_url.rstrip("/")
        self.api_key_env = api_key_env
        self.model = model
        self.timeout_seconds = timeout_seconds

    def generate(
        self,
        *,
        question: str,
        chunks: tuple[ContextChunk, ...],
        citations: tuple[CitationAnnotation, ...],
        prompt_version: str,
    ) -> GeneratedAnswer:
        api_key = _api_key(self.api_key_env)
        payload = {
            "model": self.model,
            "messages": _answer_messages(
                question=question,
                chunks=chunks,
                citations=citations,
                prompt_version=prompt_version,
            ),
            "temperature": 0.1,
        }
        raw = _post_json_budgeted(
            f"{self.base_url}/chat/completions",
            payload,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout_seconds=self.timeout_seconds,
            budget_provider=self.provider_id,
            budget_model=self.model,
            budget_units=api_units(
                calls=3,
                retries=2,
                input_tokens=rough_text_tokens(payload),
                documents=len(chunks),
            ),
        )
        answer_text = _extract_chat_text(raw)
        return GeneratedAnswer(
            answer_text=answer_text,
            model=self.model,
            structured={
                "prompt_version": prompt_version,
                "provider": self.provider_id,
                "context_chunk_count": len(chunks),
                "citation_count": len(citations),
            },
            raw_response_hash=_json_hash(raw),
        )


def build_memory_answer(
    db_path: str | Path,
    query: str,
    *,
    context_bundle: ContextBundle | None = None,
    limit: int = 5,
    doc_type: str | None = None,
    account: str | None = None,
    semantic_provider: str | None = None,
    semantic_model: str | None = None,
    semantic_dimensions: int | None = None,
    semantic_profile: str | None = None,
    semantic_template_version: str | None = None,
    semantic_api_key_env: str | None = None,
    semantic_base_url: str | None = None,
    semantic_weight: float = 3.0,
    semantic_candidates: int = 80,
    semantic_backend: str = "sqlite",
    external_run_id: str | None = None,
    external_reader_provider: str = "fake",
    external_limit: int = 5,
    external_max_chars: int = 4000,
    external_timeout_seconds: float = 30.0,
    external_user_agent: str = "research-x/0.1",
    external_max_bytes: int = 2_000_000,
    answer_provider: str = "fake",
    answer_model: str | None = None,
    answer_api_key_env: str | None = None,
    answer_base_url: str | None = None,
    answer_timeout_seconds: float = 90.0,
    prompt_version: str = DEFAULT_PROMPT_VERSION,
    max_context_chunks: int = 8,
    max_context_chars: int = 12_000,
    workflow_id: str | None = None,
    store: bool = True,
) -> MemoryAnswer:
    if context_bundle is None:
        context_bundle = build_context_bundle(
            db_path,
            query,
            limit=limit,
            doc_type=doc_type,
            account=account,
            semantic_provider=semantic_provider,
            semantic_model=semantic_model,
            semantic_dimensions=semantic_dimensions,
            semantic_profile=semantic_profile,
            semantic_template_version=semantic_template_version,
            semantic_api_key_env=semantic_api_key_env,
            semantic_base_url=semantic_base_url,
            semantic_weight=semantic_weight,
            semantic_candidates=semantic_candidates,
            semantic_backend=semantic_backend,
            external_run_id=external_run_id,
            external_reader_provider=external_reader_provider,
            external_limit=external_limit,
            external_max_chars=external_max_chars,
            external_timeout_seconds=external_timeout_seconds,
            external_user_agent=external_user_agent,
            external_max_bytes=external_max_bytes,
            store=store,
        )
    provider = _provider(
        answer_provider,
        model=answer_model,
        api_key_env=answer_api_key_env,
        base_url=answer_base_url,
        timeout_seconds=answer_timeout_seconds,
    )
    selection = _select_chunks(
        context_bundle.context_chunks,
        max_chunks=max_context_chunks,
        max_chars=max_context_chars,
    )
    chunks = selection.chunks
    citations = _citations_for_chunks(context_bundle.citation_annotations, chunks)
    generated = provider.generate(
        question=query,
        chunks=chunks,
        citations=citations,
        prompt_version=prompt_version,
    )
    created_at = _utc_now()
    retrieval_config = _retrieval_config(
        context_bundle=context_bundle,
        provider=provider,
        prompt_version=prompt_version,
        max_context_chunks=max_context_chunks,
        max_context_chars=max_context_chars,
        selection=selection,
    )
    answer_id = _answer_id(
        query,
        context_bundle.run_id,
        provider.provider_id,
        generated.model,
        prompt_version,
        created_at,
        generated.answer_text,
    )
    answer_citations = _answer_citations(
        answer_id=answer_id,
        answer_text=generated.answer_text,
        citations=citations,
        created_at=created_at,
    )
    missing_markers = [
        citation.metadata["marker"]
        for citation in answer_citations
        if not citation.metadata.get("marker_found")
    ]
    status = (
        "ok"
        if chunks and generated.answer_text.strip() and not missing_markers
        else "needs_review"
    )
    structured = {
        **generated.structured,
        "context_run_id": context_bundle.run_id,
        "raw_response_hash": generated.raw_response_hash,
        "context_selection": selection.as_dict(),
        "selected_chunk_ids": [chunk.chunk_id for chunk in chunks],
        "missing_citation_markers": missing_markers,
        "answer_citation_count": len(answer_citations),
    }
    answer = MemoryAnswer(
        answer_id=answer_id,
        question=query,
        workflow_id=workflow_id,
        context_run_id=context_bundle.run_id,
        provider=provider.provider_id,
        provider_role=provider.provider_role,
        model=generated.model,
        prompt_version=prompt_version,
        retrieval_config=retrieval_config,
        answer_text=generated.answer_text,
        structured=structured,
        status=status,
        created_at=created_at,
        citation_annotations=answer_citations,
        context_bundle=context_bundle,
        selected_context_chunks=chunks,
    )
    if store:
        store_memory_answer(db_path, answer)
    return answer


def answer_json(
    answer: MemoryAnswer,
    *,
    budget_policy: ContextBudgetPolicy | None = None,
) -> str:
    payload = answer.as_dict()
    if budget_policy is not None:
        return budgeted_json(
            payload,
            policy=budget_policy,
            payload_kind="memory_answer",
            run_id=answer.context_bundle.run_id,
        )
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)


def store_memory_answer(db_path: str | Path, answer: MemoryAnswer) -> None:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path, timeout=60) as conn:
        ensure_memory_schema(conn)
        conn.execute(
            """
            INSERT INTO memory_answer_runs (
                answer_id, question, workflow_id, model, prompt_version,
                retrieval_config_json, answer_text, structured_json, status, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(answer_id) DO UPDATE SET
                answer_text=excluded.answer_text,
                structured_json=excluded.structured_json,
                status=excluded.status
            """,
            (
                answer.answer_id,
                answer.question,
                answer.workflow_id,
                answer.model,
                answer.prompt_version,
                json.dumps(answer.retrieval_config, ensure_ascii=False, sort_keys=True),
                answer.answer_text,
                json.dumps(answer.structured, ensure_ascii=False, sort_keys=True),
                answer.status,
                answer.created_at,
            ),
        )
        conn.execute(
            """
            INSERT INTO memory_tool_calls (
                tool_call_id, run_id, provider, provider_role, action, input_json,
                output_json, status, error, started_at, finished_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(tool_call_id) DO UPDATE SET
                output_json=excluded.output_json,
                status=excluded.status,
                error=excluded.error,
                finished_at=excluded.finished_at
            """,
            (
                _tool_call_id(answer),
                answer.context_run_id,
                answer.provider,
                answer.provider_role,
                "answer",
                json.dumps(
                    {
                        "question": answer.question,
                        "model": answer.model,
                        "prompt_version": answer.prompt_version,
                        "context_run_id": answer.context_run_id,
                        "chunk_ids": answer.structured.get("selected_chunk_ids", []),
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                ),
                json.dumps(
                    {
                        "answer_id": answer.answer_id,
                        "status": answer.status,
                        "answer_text_hash": _text_hash(answer.answer_text),
                        "citation_count": len(answer.citation_annotations),
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                ),
                answer.status,
                None,
                answer.created_at,
                answer.created_at,
            ),
        )
        _store_selected_context_chunks(conn, answer)
        for citation in answer.citation_annotations:
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
                    answer_start_index=excluded.answer_start_index,
                    answer_end_index=excluded.answer_end_index,
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
                    citation.answer_start_index,
                    citation.answer_end_index,
                    citation.field_path,
                    citation.support_type,
                    citation.evidence_status,
                    citation.confidence,
                    citation.created_at,
                    json.dumps(citation.metadata, ensure_ascii=False, sort_keys=True),
                ),
            )


def _provider(
    provider: str,
    *,
    model: str | None,
    api_key_env: str | None,
    base_url: str | None,
    timeout_seconds: float,
) -> AnswerProvider:
    provider_id = provider.strip().lower()
    if provider_id == "fake":
        return FakeAnswerProvider(model=model or FAKE_ANSWER_MODEL)
    if provider_id == "openai_compatible":
        if not base_url:
            raise ValueError("--answer-base-url is required for openai_compatible")
        return OpenAICompatibleAnswerProvider(
            provider_id=provider_id,
            base_url=base_url,
            api_key_env=api_key_env or "OPENAI_API_KEY",
            model=model or DEFAULT_OPENAI_MODEL,
            timeout_seconds=timeout_seconds,
        )
    if provider_id in OPENAI_COMPATIBLE_PRESETS:
        preset = OPENAI_COMPATIBLE_PRESETS[provider_id]
        return OpenAICompatibleAnswerProvider(
            provider_id=provider_id,
            base_url=base_url or preset["base_url"],
            api_key_env=api_key_env or preset["api_key_env"],
            model=model or preset["model"],
            timeout_seconds=timeout_seconds,
        )
    raise ValueError(f"unknown answer provider: {provider}")


def _select_chunks(
    chunks: tuple[ContextChunk, ...],
    *,
    max_chunks: int,
    max_chars: int,
) -> ChunkSelection:
    selected: list[ContextChunk] = []
    used_chars = 0
    limit_chars = max(1, max_chars)
    truncated: list[str] = []
    truncated_omitted_chars = 0
    for chunk in chunks[: max(1, max_chunks)]:
        next_chars = len(chunk.chunk_text)
        if selected and used_chars + next_chars > limit_chars:
            break
        if not selected and next_chars > limit_chars:
            text = chunk.chunk_text[:limit_chars]
            subchunk_id = _hash_id(
                "answer-subchunk",
                chunk.chunk_id,
                str(limit_chars),
                _text_hash(text),
            )
            selected.append(
                ContextChunk(
                    chunk_id=subchunk_id,
                    run_id=chunk.run_id,
                    source_kind=chunk.source_kind,
                    source_id=chunk.source_id,
                    source_url=chunk.source_url,
                    provider=chunk.provider,
                    provider_role=chunk.provider_role,
                    chunk_text=text,
                    chunk_index=chunk.chunk_index,
                    token_count=_estimate_tokens(text),
                    relevance_score=chunk.relevance_score,
                    extractor_version=chunk.extractor_version,
                    created_at=chunk.created_at,
                    metadata={
                        **chunk.metadata,
                        "original_chunk_id": chunk.chunk_id,
                        "truncated_for_answer": True,
                        "omitted_chars": max(0, len(chunk.chunk_text) - len(text)),
                    },
                )
            )
            truncated.append(chunk.chunk_id)
            truncated_omitted_chars += max(0, len(chunk.chunk_text) - len(text))
            break
        selected.append(chunk)
        used_chars += next_chars
    selected_ids = {
        str(chunk.metadata.get("original_chunk_id") or chunk.chunk_id) for chunk in selected
    }
    omitted = tuple(chunk.chunk_id for chunk in chunks if chunk.chunk_id not in selected_ids)
    omitted_chars = truncated_omitted_chars + sum(
        len(chunk.chunk_text)
        for chunk in chunks
        if chunk.chunk_id not in selected_ids
    )
    return ChunkSelection(
        chunks=tuple(selected),
        omitted_chunk_ids=omitted,
        omitted_char_count=omitted_chars,
        truncated_chunk_ids=tuple(truncated),
    )


def _citations_for_chunks(
    citations: tuple[CitationAnnotation, ...],
    chunks: tuple[ContextChunk, ...],
) -> tuple[CitationAnnotation, ...]:
    by_chunk_id = {citation.chunk_id: citation for citation in citations}
    result: list[CitationAnnotation] = []
    for chunk in chunks:
        original_chunk_id = str(chunk.metadata.get("original_chunk_id") or chunk.chunk_id)
        citation = by_chunk_id.get(original_chunk_id)
        if citation is None:
            continue
        if citation.chunk_id == chunk.chunk_id:
            result.append(citation)
            continue
        result.append(
            CitationAnnotation(
                citation_id=_hash_id(
                    "answer-subchunk-citation",
                    citation.citation_id,
                    chunk.chunk_id,
                ),
                answer_id=citation.answer_id,
                chunk_id=chunk.chunk_id,
                source_kind=citation.source_kind,
                source_id=citation.source_id,
                source_url=citation.source_url,
                title=citation.title,
                field_path=citation.field_path,
                support_type=citation.support_type,
                evidence_status=citation.evidence_status,
                confidence=citation.confidence,
                created_at=citation.created_at,
                metadata={
                    **citation.metadata,
                    "original_chunk_id": original_chunk_id,
                    "truncated_for_answer": True,
                },
            )
        )
    return tuple(result)


def _store_selected_context_chunks(conn: sqlite3.Connection, answer: MemoryAnswer) -> None:
    for chunk in answer.selected_context_chunks:
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


def _answer_citations(
    *,
    answer_id: str,
    answer_text: str,
    citations: tuple[CitationAnnotation, ...],
    created_at: str,
) -> tuple[AnswerCitation, ...]:
    result: list[AnswerCitation] = []
    for index, citation in enumerate(citations, start=1):
        marker = f"[{index}]"
        start, end = _marker_span(answer_text, marker)
        marker_found = start is not None and end is not None
        result.append(
            AnswerCitation(
                citation_id=_hash_id(
                    "answer-citation",
                    answer_id,
                    citation.citation_id,
                    marker,
                ),
                answer_id=answer_id,
                chunk_id=citation.chunk_id,
                source_kind=citation.source_kind,
                source_id=citation.source_id,
                source_url=citation.source_url,
                title=citation.title,
                answer_start_index=start,
                answer_end_index=end,
                field_path=f"answer_text.annotations[{index - 1}]",
                support_type="supports_answer" if marker_found else "uncited_context",
                evidence_status=citation.evidence_status,
                confidence=citation.confidence if marker_found else min(0.35, citation.confidence),
                created_at=created_at,
                metadata={
                    "display_index": index,
                    "marker": marker,
                    "marker_found": marker_found,
                    "source_context_citation_id": citation.citation_id,
                    "source_field_path": citation.field_path,
                    **citation.metadata,
                },
            )
        )
    return tuple(result)


def _retrieval_config(
    *,
    context_bundle: ContextBundle,
    provider: AnswerProvider,
    prompt_version: str,
    max_context_chunks: int,
    max_context_chars: int,
    selection: ChunkSelection,
) -> dict[str, Any]:
    return {
        "context_run_id": context_bundle.run_id,
        "context_parameters": context_bundle.parameters,
        "query_plan": context_bundle.query_plan,
        "retrieved_hit_count": len(context_bundle.retrieved_hits),
        "context_chunk_count": len(context_bundle.context_chunks),
        "answer_provider": provider.provider_id,
        "answer_provider_role": provider.provider_role,
        "answer_model": provider.model,
        "prompt_version": prompt_version,
        "max_context_chunks": max_context_chunks,
        "max_context_chars": max_context_chars,
        "context_selection": selection.as_dict(),
    }


def _answer_messages(
    *,
    question: str,
    chunks: tuple[ContextChunk, ...],
    citations: tuple[CitationAnnotation, ...],
    prompt_version: str,
) -> list[dict[str, str]]:
    context_lines: list[str] = []
    for index, chunk in enumerate(chunks, start=1):
        citation = citations[index - 1] if index <= len(citations) else None
        source_url = citation.source_url if citation else chunk.source_url
        title = citation.title if citation else chunk.source_id
        context_lines.append(
            "\n".join(
                [
                    f"[{index}] title={title}",
                    f"source_kind={chunk.source_kind}",
                    f"source_id={chunk.source_id}",
                    f"url={source_url or ''}",
                    f"evidence_status={(citation.evidence_status if citation else 'unknown')}",
                    chunk.chunk_text,
                ]
            )
        )
    system = (
        "You are the answer engine for a local personal memory-search tool. "
        "Use only the supplied context. Cite evidence-backed claims with bracket markers "
        "like [1]. Separate evidence-backed facts from likely inference. If context is "
        "insufficient, say what is missing instead of guessing. Generated answers are not "
        "canonical evidence."
    )
    user = "\n\n".join(
        [
            f"prompt_version: {prompt_version}",
            f"question: {question}",
            "context:",
            "\n\n".join(context_lines) if context_lines else "(no context)",
        ]
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def _best_excerpt(text: str) -> str:
    for prefix in ("Text:", "Why relevant:", "Title:"):
        match = re.search(rf"^{re.escape(prefix)}\s*(.+)$", text, flags=re.MULTILINE)
        if match and match.group(1).strip():
            return _truncate(_compact_whitespace(match.group(1)), 240)
    return _truncate(_compact_whitespace(text), 240)


def _marker_span(text: str, marker: str) -> tuple[int | None, int | None]:
    start = text.find(marker)
    if start < 0:
        return None, None
    return start, start + len(marker)


def _extract_chat_text(raw: dict[str, Any]) -> str:
    choices = raw.get("choices")
    if isinstance(choices, list) and choices:
        first = choices[0]
        if isinstance(first, dict):
            message = first.get("message")
            if isinstance(message, dict):
                content = message.get("content")
                if isinstance(content, str) and content.strip():
                    return content.strip()
    raise RuntimeError("answer provider response did not include message content")


def _post_json(
    url: str,
    payload: dict[str, Any],
    *,
    headers: dict[str, str],
    timeout_seconds: float,
    retries: int = 3,
    budget_provider: str | None = None,
    budget_model: str | None = None,
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
        provider_role=ANSWER_ENGINE_ROLE,
        operation="answer",
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
    budget_units: dict[str, int | float] | None = None,
) -> dict[str, Any]:
    with budgeted_api_call(
        provider=budget_provider,
        model=budget_model,
        provider_role=ANSWER_ENGINE_ROLE,
        operation="answer",
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
            with urllib.request.urlopen(request, timeout=timeout_seconds) as response:  # noqa: S310
                parsed = json.loads(response.read().decode("utf-8"))
            if not isinstance(parsed, dict):
                raise RuntimeError("answer provider returned unsupported JSON shape")
            return parsed
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            if exc.code not in {429, 500, 502, 503, 504} or attempt == retries:
                raise RuntimeError(f"answer provider HTTP {exc.code}: {detail[:800]}") from exc
            last_error = exc
        except TimeoutError as exc:
            if attempt == retries:
                raise RuntimeError("answer provider timed out") from exc
            last_error = exc
        time.sleep(min(2**attempt, 30))
    raise RuntimeError(f"answer provider failed: {last_error}")


def _api_key(env_name: str) -> str:
    value = os.environ.get(env_name)
    if not value:
        raise RuntimeError(f"missing API key environment variable: {env_name}")
    return value


def _answer_id(
    query: str,
    context_run_id: str,
    provider: str,
    model: str,
    prompt_version: str,
    created_at: str,
    answer_text: str,
) -> str:
    return _hash_id(
        "answer",
        query,
        context_run_id,
        provider,
        model,
        prompt_version,
        created_at,
        _text_hash(answer_text),
    )[:24]


def _tool_call_id(answer: MemoryAnswer) -> str:
    return _hash_id("tool-call", answer.answer_id, answer.context_run_id, answer.provider)[:24]


def _json_hash(value: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()


def _text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _hash_id(*parts: str) -> str:
    return hashlib.sha256("\0".join(parts).encode("utf-8")).hexdigest()


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _compact_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _truncate(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return text[: max(0, max_chars - 3)].rstrip() + "..."


def _estimate_tokens(text: str) -> int:
    ascii_words = len([part for part in text.split() if part])
    non_ascii = sum(1 for char in text if ord(char) > 127)
    return max(1, ascii_words + (non_ascii + 1) // 2)
