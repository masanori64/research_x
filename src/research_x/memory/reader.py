from __future__ import annotations

import hashlib
import html
import json
import os
import re
import sqlite3
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import UTC, datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Protocol

from research_x.memory.api_budget import (
    api_units,
    budgeted_api_call,
    require_provider_transport_send_allowed,
    rough_text_tokens,
)
from research_x.memory.schema import ensure_memory_schema
from research_x.memory.source_identity import source_lineage_ids
from research_x.memory.source_kinds import (
    EXTERNAL_WEB_MEDIUM,
    classify_external_source_kind,
    evidence_status_for_source,
    source_quality_class,
    source_risk_flags,
)

FETCH_AGENT_ROLE = "fetch_agent"
READER_EXTRACTOR_VERSION = "reader-extract-v1"
DEFAULT_USER_AGENT = "research-x/0.1"
FIRECRAWL_READER_ENDPOINT = "https://api.firecrawl.dev/v1/scrape"
FIRECRAWL_READER_MODEL = "firecrawl-extract"
PROMPT_INJECTION_REVIEW = "deterministic-prompt-injection-v1"
PROMPT_INJECTION_PATTERNS: tuple[tuple[str, str], ...] = (
    (
        "ignore_previous_instructions",
        r"\bignore\s+(?:all\s+)?(?:previous|prior|above)\s+(?:instructions|rules|prompts)\b",
    ),
    (
        "disregard_previous_instructions",
        r"\bdisregard\s+(?:all\s+)?(?:previous|prior|above)\s+(?:instructions|rules|prompts)\b",
    ),
    (
        "override_system_or_developer_message",
        r"\boverride\s+(?:the\s+)?(?:system|developer|previous|prior)\s+"
        r"(?:prompt|message|instructions|rules)\b",
    ),
    (
        "reveal_hidden_instructions",
        r"\breveal\s+(?:the\s+)?(?:system|developer|hidden)\s+"
        r"(?:prompt|message|instructions|rules)\b",
    ),
    (
        "do_not_follow_instructions",
        r"\bdo\s+not\s+(?:follow|obey)\s+(?:the\s+)?"
        r"(?:system|developer|previous|prior|above)\s+(?:instructions|rules|prompt)\b",
    ),
)


@dataclass(frozen=True)
class ReaderPage:
    url: str
    title: str
    text: str
    status_code: int | None
    content_type: str
    retrieved_at: str
    metadata: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {
            "url": self.url,
            "title": self.title,
            "text": self.text,
            "status_code": self.status_code,
            "content_type": self.content_type,
            "retrieved_at": self.retrieved_at,
            "metadata": self.metadata,
        }


@dataclass(frozen=True)
class ReaderContextBundle:
    tool_call_id: str
    provider: str
    provider_role: str
    action: str
    url: str
    query: str | None
    page: ReaderPage
    context_chunk: dict[str, Any]
    citation_annotation: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {
            "tool_call_id": self.tool_call_id,
            "provider": self.provider,
            "provider_role": self.provider_role,
            "action": self.action,
            "url": self.url,
            "query": self.query,
            "page": self.page.as_dict(),
            "context_chunk": self.context_chunk,
            "citation_annotation": self.citation_annotation,
        }


class ReaderProvider(Protocol):
    provider_id: str
    provider_role: str

    def extract(
        self,
        url: str,
        *,
        query: str | None,
        title: str | None,
        max_chars: int,
    ) -> ReaderPage:
        """Fetch and extract readable text for a known URL."""


class FakeReaderProvider:
    provider_id = "fake"
    provider_role = FETCH_AGENT_ROLE

    def extract(
        self,
        url: str,
        *,
        query: str | None,
        title: str | None,
        max_chars: int,
    ) -> ReaderPage:
        text = (
            f"Fake extracted page for {url}. "
            "This deterministic content is used to test reader/extract wiring."
        )
        if query:
            text += f" Query context: {query}."
        return ReaderPage(
            url=url,
            title=title or f"Fake page for {_domain(url) or 'unknown'}",
            text=_compact_text(text, limit=max_chars),
            status_code=None,
            content_type="text/plain; fixture=fake",
            retrieved_at=_utc_now(),
            metadata={"fixture": True, "response_hash": _text_hash(text)},
        )


class HttpReaderProvider:
    provider_id = "http"
    provider_role = FETCH_AGENT_ROLE

    def __init__(
        self,
        *,
        timeout_seconds: float = 30.0,
        user_agent: str = DEFAULT_USER_AGENT,
        max_bytes: int = 2_000_000,
    ) -> None:
        self.timeout_seconds = timeout_seconds
        self.user_agent = user_agent
        self.max_bytes = max(1024, max_bytes)

    def extract(
        self,
        url: str,
        *,
        query: str | None,
        title: str | None,
        max_chars: int,
    ) -> ReaderPage:
        with budgeted_api_call(
            provider=self.provider_id,
            model="direct-http",
            provider_role=self.provider_role,
            operation="reader_extract",
            units=api_units(calls=1, input_tokens=rough_text_tokens({"url": url, "query": query})),
            request_payload={"url": url, "query": query, "max_chars": max_chars},
            metadata={"direct_http_reader": True},
        ):
            require_provider_transport_send_allowed(url)
            response = _read_url(
                url,
                timeout_seconds=self.timeout_seconds,
                user_agent=self.user_agent,
                max_bytes=self.max_bytes,
            )
        extracted_title, text = _extract_text(response.body, response.content_type)
        resolved_title = title or extracted_title or response.final_url
        metadata = {
            "final_url": response.final_url,
            "truncated_bytes": response.truncated,
            "query": query,
            "response_hash": _bytes_hash(response.body),
        }
        return ReaderPage(
            url=response.final_url,
            title=resolved_title,
            text=_compact_text(text, limit=max_chars),
            status_code=response.status_code,
            content_type=response.content_type,
            retrieved_at=_utc_now(),
            metadata=metadata,
        )


class JinaReaderProvider:
    provider_id = "jina"
    provider_role = FETCH_AGENT_ROLE

    def __init__(
        self,
        *,
        timeout_seconds: float = 30.0,
        user_agent: str = DEFAULT_USER_AGENT,
        max_bytes: int = 2_000_000,
        endpoint_base: str = "https://r.jina.ai",
    ) -> None:
        self.timeout_seconds = timeout_seconds
        self.user_agent = user_agent
        self.max_bytes = max(1024, max_bytes)
        self.endpoint_base = endpoint_base.rstrip("/")

    def extract(
        self,
        url: str,
        *,
        query: str | None,
        title: str | None,
        max_chars: int,
    ) -> ReaderPage:
        request = _jina_reader_request(
            endpoint_base=self.endpoint_base,
            url=url,
            api_key=os.environ.get("JINA_API_KEY"),
            timeout_seconds=self.timeout_seconds,
            user_agent=self.user_agent,
            max_bytes=self.max_bytes,
        )
        with budgeted_api_call(
            provider=self.provider_id,
            model="reader",
            provider_role=self.provider_role,
            operation="reader_extract",
            units=api_units(calls=1, input_tokens=rough_text_tokens({"url": url, "query": query})),
            request_payload={"url": url, "query": query, "max_chars": max_chars},
            metadata={"endpoint": request["url"], "uses_api_key": bool(request["api_key_used"])},
        ):
            require_provider_transport_send_allowed(request["url"])
            response = _read_url(
                request["url"],
                timeout_seconds=request["timeout_seconds"],
                user_agent=request["user_agent"],
                max_bytes=request["max_bytes"],
                extra_headers=request["headers"],
            )
        _extracted_title, text = _extract_text(response.body, response.content_type)
        return ReaderPage(
            url=url,
            title=title or _domain(url) or url,
            text=_compact_text(text, limit=max_chars),
            status_code=response.status_code,
            content_type=response.content_type or "text/plain; provider=jina",
            retrieved_at=_utc_now(),
            metadata={
                "reader_endpoint": response.final_url,
                "query": query,
                "truncated_bytes": response.truncated,
                "uses_api_key": bool(request["api_key_used"]),
                "response_hash": _bytes_hash(response.body),
                "request_shape": _safe_request_shape(request),
            },
        )


class FirecrawlReaderProvider:
    provider_id = "firecrawl"
    provider_role = FETCH_AGENT_ROLE

    def __init__(
        self,
        *,
        timeout_seconds: float = 30.0,
        endpoint: str = FIRECRAWL_READER_ENDPOINT,
        api_key_env: str = "FIRECRAWL_API_KEY",
    ) -> None:
        self.timeout_seconds = timeout_seconds
        self.endpoint = endpoint
        self.api_key_env = api_key_env

    def extract(
        self,
        url: str,
        *,
        query: str | None,
        title: str | None,
        max_chars: int,
    ) -> ReaderPage:
        api_key = os.environ.get(self.api_key_env)
        request = _firecrawl_reader_request(
            endpoint=self.endpoint,
            url=url,
            api_key=api_key,
            api_key_env=self.api_key_env,
            timeout_seconds=self.timeout_seconds,
        )
        with budgeted_api_call(
            provider=self.provider_id,
            model=FIRECRAWL_READER_MODEL,
            provider_role=self.provider_role,
            operation="reader_extract",
            units=api_units(calls=1, input_tokens=rough_text_tokens({"url": url, "query": query})),
            request_payload={"url": url, "query": query, "max_chars": max_chars},
            metadata={"endpoint": request["url"], "uses_api_key": bool(request["api_key_used"])},
        ):
            if request["api_key_required"] and not request["api_key_used"]:
                raise RuntimeError(f"{self.api_key_env} is not set")
            raw = _post_json(
                request["url"],
                request["payload"],
                headers=request["headers"],
                timeout_seconds=request["timeout_seconds"],
            )
        extracted_title, text, content_type = _firecrawl_response_text(raw)
        response_hash = _json_hash(raw)
        return ReaderPage(
            url=url,
            title=title or extracted_title or _domain(url) or url,
            text=_compact_text(text, limit=max_chars),
            status_code=_optional_int(raw.get("statusCode") or raw.get("status_code")),
            content_type=content_type,
            retrieved_at=_utc_now(),
            metadata={
                "query": query,
                "response_hash": response_hash,
                "provider_response_hash": response_hash,
                "request_shape": _safe_request_shape(request),
                "firecrawl_metadata": _firecrawl_metadata(raw),
                "uses_api_key": bool(request["api_key_used"]),
            },
        )


def _jina_reader_request(
    *,
    endpoint_base: str,
    url: str,
    api_key: str | None,
    timeout_seconds: float,
    user_agent: str,
    max_bytes: int,
) -> dict[str, Any]:
    headers: dict[str, str] = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    return {
        "url": f"{endpoint_base.rstrip('/')}/{url}",
        "headers": headers,
        "timeout_seconds": timeout_seconds,
        "user_agent": user_agent,
        "max_bytes": max_bytes,
        "api_key_used": bool(api_key),
        "request_shape_only": True,
        "provider_quality_proof": False,
    }


def _firecrawl_reader_request(
    *,
    endpoint: str,
    url: str,
    api_key: str | None,
    api_key_env: str = "FIRECRAWL_API_KEY",
    timeout_seconds: float,
) -> dict[str, Any]:
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    return {
        "provider": "firecrawl",
        "provider_role": FETCH_AGENT_ROLE,
        "operation": "reader_extract",
        "model": FIRECRAWL_READER_MODEL,
        "method": "POST",
        "url": endpoint,
        "endpoint": endpoint,
        "payload": {
            "url": url,
            "formats": ["markdown"],
            "onlyMainContent": True,
        },
        "headers": headers,
        "timeout_seconds": timeout_seconds,
        "api_key_env": api_key_env,
        "api_key_used": bool(api_key),
        "api_key_required": True,
        "request_shape_only": True,
        "provider_quality_proof": False,
        "reader_context_candidate_only": True,
    }


@dataclass(frozen=True)
class HttpResponse:
    final_url: str
    status_code: int
    content_type: str
    body: bytes
    truncated: bool = False


def extract_url_to_context(
    db_path: str | Path,
    url: str,
    *,
    run_id: str | None = None,
    provider: str = "fake",
    query: str | None = None,
    title: str | None = None,
    max_chars: int = 4000,
    timeout_seconds: float = 30.0,
    user_agent: str = DEFAULT_USER_AGENT,
    max_bytes: int = 2_000_000,
    store: bool = True,
    metadata: dict[str, Any] | None = None,
) -> ReaderContextBundle:
    input_metadata = dict(metadata or {})
    provider_impl = _provider(
        provider,
        timeout_seconds=timeout_seconds,
        user_agent=user_agent,
        max_bytes=max_bytes,
    )
    started_at = _utc_now()
    page = provider_impl.extract(
        url,
        query=query,
        title=title,
        max_chars=max(1, max_chars),
    )
    finished_at = _utc_now()
    tool_call_id = _hash_id(
        "reader-tool-call",
        provider_impl.provider_id,
        page.url,
        query or "",
        started_at,
        _text_hash(page.text),
    )[:24]
    prompt_review = review_prompt_injection_text(page.text)
    fetch_artifact = _fetch_artifact_record(
        tool_call_id=tool_call_id,
        run_id=run_id,
        requested_url=url,
        provider=provider_impl.provider_id,
        page=page,
        fetched_at=finished_at,
        prompt_review=prompt_review,
        metadata=input_metadata,
    )
    chunk = _context_chunk(
        tool_call_id=tool_call_id,
        provider=provider_impl.provider_id,
        provider_role=provider_impl.provider_role,
        page=page,
        run_id=run_id,
        query=query,
        metadata=input_metadata,
        fetch_artifact=fetch_artifact,
        prompt_review=prompt_review,
    )
    citation = _citation_annotation(
        tool_call_id=tool_call_id,
        chunk=chunk,
        page=page,
        metadata=input_metadata,
        fetch_artifact=fetch_artifact,
        prompt_review=prompt_review,
    )
    bundle = ReaderContextBundle(
        tool_call_id=tool_call_id,
        provider=provider_impl.provider_id,
        provider_role=provider_impl.provider_role,
        action="reader_extract",
        url=url,
        query=query,
        page=page,
        context_chunk=chunk,
        citation_annotation=citation,
    )
    if store:
        _store_reader_bundle(
            db_path,
            bundle,
            started_at=started_at,
            finished_at=finished_at,
            metadata=input_metadata,
            fetch_artifact=fetch_artifact,
        )
    return bundle


def extract_external_run_to_context(
    db_path: str | Path,
    external_run_id: str,
    *,
    run_id: str | None = None,
    provider: str = "fake",
    limit: int = 5,
    query: str | None = None,
    max_chars: int = 4000,
    timeout_seconds: float = 30.0,
    user_agent: str = DEFAULT_USER_AGENT,
    max_bytes: int = 2_000_000,
    store: bool = True,
) -> list[ReaderContextBundle]:
    path = Path(db_path)
    with sqlite3.connect(path, timeout=60) as conn:
        conn.row_factory = sqlite3.Row
        ensure_memory_schema(conn)
        rows = conn.execute(
            """
            SELECT item_id, title, url, snippet, source, position
            FROM memory_external_items
            WHERE run_id = ?
            ORDER BY position
            LIMIT ?
            """,
            (external_run_id, max(1, limit)),
        ).fetchall()
    bundles = []
    for row in rows:
        bundles.append(
            extract_url_to_context(
                path,
                row["url"],
                run_id=run_id,
                provider=provider,
                query=query,
                title=row["title"],
                max_chars=max_chars,
                timeout_seconds=timeout_seconds,
                user_agent=user_agent,
                max_bytes=max_bytes,
                store=store,
                metadata={
                    "external_run_id": external_run_id,
                    "external_item_id": row["item_id"],
                    "external_position": row["position"],
                    "external_snippet": row["snippet"],
                    "external_snippet_citation_excluded": True,
                    "external_rank_citation_excluded": True,
                    "external_discovery_evidence_status": (
                        "not_evidence_until_reader_chunk"
                    ),
                    "external_source": row["source"],
                },
            )
        )
    return bundles


def reader_context_json(value: ReaderContextBundle | list[ReaderContextBundle]) -> str:
    if isinstance(value, list):
        payload: Any = {"extractions": [bundle.as_dict() for bundle in value]}
    else:
        payload = value.as_dict()
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)


def _store_reader_bundle(
    db_path: str | Path,
    bundle: ReaderContextBundle,
    *,
    started_at: str,
    finished_at: str,
    metadata: dict[str, Any],
    fetch_artifact: dict[str, Any],
) -> None:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path, timeout=60) as conn:
        ensure_memory_schema(conn)
        conn.execute(
            """
            INSERT INTO memory_tool_calls (
                tool_call_id, run_id, provider, provider_role, action,
                input_json, output_json, status, error, started_at, finished_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(tool_call_id) DO UPDATE SET
                output_json=excluded.output_json,
                status=excluded.status,
                error=excluded.error,
                finished_at=excluded.finished_at
            """,
            (
                bundle.tool_call_id,
                bundle.context_chunk["run_id"],
                bundle.provider,
                bundle.provider_role,
                bundle.action,
                json.dumps(
                    {
                        "url": bundle.url,
                        "query": bundle.query,
                        "metadata": metadata,
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                ),
                json.dumps(
                    {
                        "url": bundle.page.url,
                        "title": bundle.page.title,
                        "status_code": bundle.page.status_code,
                        "content_type": bundle.page.content_type,
                        "text_hash": _text_hash(bundle.page.text),
                        "response_hash": fetch_artifact["response_hash"],
                        "extracted_text_hash": fetch_artifact["extracted_text_hash"],
                        "fetch_artifact_id": fetch_artifact["artifact_id"],
                        "char_count": len(bundle.page.text),
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                ),
                "ok",
                None,
                started_at,
                finished_at,
            ),
        )
        conn.execute(
            """
            INSERT INTO memory_fetch_artifacts (
                artifact_id, tool_call_id, run_id, requested_url, final_url,
                fetched_at, retrieved_at, content_type, status_code, response_hash,
                extracted_text_hash, raw_artifact_path, prompt_injection_review,
                prompt_injection_status, prompt_injection_flags_json, storage_rights,
                fetch_provider, metadata_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(artifact_id) DO UPDATE SET
                tool_call_id=excluded.tool_call_id,
                run_id=excluded.run_id,
                final_url=excluded.final_url,
                fetched_at=excluded.fetched_at,
                retrieved_at=excluded.retrieved_at,
                content_type=excluded.content_type,
                status_code=excluded.status_code,
                response_hash=excluded.response_hash,
                extracted_text_hash=excluded.extracted_text_hash,
                raw_artifact_path=excluded.raw_artifact_path,
                prompt_injection_review=excluded.prompt_injection_review,
                prompt_injection_status=excluded.prompt_injection_status,
                prompt_injection_flags_json=excluded.prompt_injection_flags_json,
                storage_rights=excluded.storage_rights,
                fetch_provider=excluded.fetch_provider,
                metadata_json=excluded.metadata_json
            """,
            (
                fetch_artifact["artifact_id"],
                fetch_artifact["tool_call_id"],
                fetch_artifact["run_id"],
                fetch_artifact["requested_url"],
                fetch_artifact["final_url"],
                fetch_artifact["fetched_at"],
                fetch_artifact["retrieved_at"],
                fetch_artifact["content_type"],
                fetch_artifact["status_code"],
                fetch_artifact["response_hash"],
                fetch_artifact["extracted_text_hash"],
                fetch_artifact["raw_artifact_path"],
                fetch_artifact["prompt_injection_review"],
                fetch_artifact["prompt_injection_status"],
                json.dumps(
                    fetch_artifact["prompt_injection_flags"],
                    ensure_ascii=False,
                    sort_keys=True,
                ),
                fetch_artifact["storage_rights"],
                fetch_artifact["fetch_provider"],
                json.dumps(fetch_artifact["metadata"], ensure_ascii=False, sort_keys=True),
            ),
        )
        chunk = bundle.context_chunk
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
                metadata_json=excluded.metadata_json
            """,
                (
                    chunk["chunk_id"],
                    chunk["run_id"],
                    chunk["source_kind"],
                    chunk["source_id"],
                chunk["source_url"],
                chunk["provider"],
                chunk["provider_role"],
                chunk["chunk_text"],
                chunk["chunk_index"],
                None,
                None,
                chunk["token_count"],
                chunk["relevance_score"],
                chunk["extractor_version"],
                chunk["created_at"],
                json.dumps(chunk["metadata"], ensure_ascii=False, sort_keys=True),
            ),
        )
        citation = bundle.citation_annotation
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
                support_type=excluded.support_type,
                evidence_status=excluded.evidence_status,
                confidence=excluded.confidence,
                metadata_json=excluded.metadata_json
            """,
            (
                citation["citation_id"],
                None,
                citation["chunk_id"],
                citation["source_kind"],
                citation["source_id"],
                citation["source_url"],
                citation["title"],
                None,
                None,
                citation["field_path"],
                citation["support_type"],
                citation["evidence_status"],
                citation["confidence"],
                citation["created_at"],
                json.dumps(citation["metadata"], ensure_ascii=False, sort_keys=True),
            ),
        )


def _context_chunk(
    *,
    tool_call_id: str,
    provider: str,
    provider_role: str,
    page: ReaderPage,
    run_id: str | None,
    query: str | None,
    metadata: dict[str, Any],
    fetch_artifact: dict[str, Any],
    prompt_review: dict[str, Any],
) -> dict[str, Any]:
    source_id = _external_source_id(page.url)
    source_kind = classify_external_source_kind(page.url, metadata=metadata)
    chunk_text = _reader_chunk_text(page=page, query=query)
    chunk_id = _hash_id("external-chunk", tool_call_id, page.url, _text_hash(chunk_text))
    artifact_metadata = _fetch_artifact_metadata(
        fetch_artifact,
        source_kind=source_kind,
        prompt_review=prompt_review,
    )
    return {
        "chunk_id": chunk_id,
        "run_id": run_id,
        "source_kind": source_kind,
        "source_id": source_id,
        "source_url": page.url,
        "provider": provider,
        "provider_role": provider_role,
        "chunk_text": chunk_text,
        "chunk_index": 0,
        "token_count": _estimate_tokens(chunk_text),
        "relevance_score": 0.0,
        "extractor_version": READER_EXTRACTOR_VERSION,
        "created_at": page.retrieved_at,
        "metadata": {
            "title": page.title,
            "status_code": page.status_code,
            "content_type": page.content_type,
            "source_medium": EXTERNAL_WEB_MEDIUM,
            "evidence_source_kind": source_kind,
            "source_quality_class": source_quality_class(page.url, source_kind=source_kind),
            "source_risk_flags": source_risk_flags(page.url, source_kind=source_kind),
            "page_metadata": page.metadata,
            **metadata,
            **artifact_metadata,
        },
    }


def _citation_annotation(
    *,
    tool_call_id: str,
    chunk: dict[str, Any],
    page: ReaderPage,
    metadata: dict[str, Any],
    fetch_artifact: dict[str, Any],
    prompt_review: dict[str, Any],
) -> dict[str, Any]:
    citation_id = _hash_id("external-citation", tool_call_id, chunk["chunk_id"], page.url)
    evidence_status = evidence_status_for_source(page.url, provider=str(chunk["provider"]))
    if prompt_review["status"] == "review_required":
        evidence_status = "needs_review"
    artifact_metadata = _fetch_artifact_metadata(
        fetch_artifact,
        source_kind=str(chunk["source_kind"]),
        prompt_review=prompt_review,
    )
    return {
        "citation_id": citation_id,
        "answer_id": None,
        "chunk_id": chunk["chunk_id"],
        "source_kind": chunk["source_kind"],
        "source_id": chunk["source_id"],
        "source_url": page.url,
        "title": page.title,
        "field_path": "context_chunks[external]",
        "support_type": "background",
        "evidence_status": evidence_status,
        "confidence": 0.8 if evidence_status == "fact" else 0.4,
        "created_at": page.retrieved_at,
        "metadata": {
            "provider_role": chunk["provider_role"],
            "tool_call_id": tool_call_id,
            "source_medium": EXTERNAL_WEB_MEDIUM,
            "evidence_source_kind": chunk["source_kind"],
            **metadata,
            **artifact_metadata,
        },
    }


def _provider(
    provider: str,
    *,
    timeout_seconds: float,
    user_agent: str,
    max_bytes: int,
) -> ReaderProvider:
    provider_id = provider.strip().lower()
    if provider_id == "fake":
        return FakeReaderProvider()
    if provider_id == "http":
        return HttpReaderProvider(
            timeout_seconds=timeout_seconds,
            user_agent=user_agent,
            max_bytes=max_bytes,
        )
    if provider_id in {"jina", "jina_reader"}:
        return JinaReaderProvider(
            timeout_seconds=timeout_seconds,
            user_agent=user_agent,
            max_bytes=max_bytes,
        )
    if provider_id in {"firecrawl", "firecrawl_reader"}:
        return FirecrawlReaderProvider(timeout_seconds=timeout_seconds)
    raise ValueError(f"unknown reader provider: {provider}")


def review_prompt_injection_text(text: str) -> dict[str, Any]:
    flags = [
        flag
        for flag, pattern in PROMPT_INJECTION_PATTERNS
        if re.search(pattern, text, flags=re.IGNORECASE)
    ]
    return {
        "review": PROMPT_INJECTION_REVIEW,
        "status": "review_required" if flags else "passed",
        "flags": flags,
        "review_required": bool(flags),
        "answer_support_allowed": not flags,
    }


def _fetch_artifact_record(
    *,
    tool_call_id: str,
    run_id: str | None,
    requested_url: str,
    provider: str,
    page: ReaderPage,
    fetched_at: str,
    prompt_review: dict[str, Any],
    metadata: dict[str, Any],
) -> dict[str, Any]:
    extracted_text_hash = _text_hash(page.text)
    response_hash = str(page.metadata.get("response_hash") or extracted_text_hash)
    source_id = _external_source_id(page.url)
    lineage_ids = source_lineage_ids(source_id, response_hash)
    artifact_id = _hash_id(
        "fetch-artifact",
        tool_call_id,
        requested_url,
        page.url,
        response_hash,
        extracted_text_hash,
    )[:24]
    raw_artifact_path = _optional_text(
        metadata.get("raw_artifact_path") or page.metadata.get("raw_artifact_path")
    )
    storage_rights = _optional_text(
        metadata.get("storage_rights")
        or metadata.get("storage_rights_status")
        or page.metadata.get("storage_rights")
    ) or "unknown"
    artifact_metadata = {
        "source_id": source_id,
        "source_url": page.url,
        "source_doc_hash": response_hash,
        **lineage_ids,
        "lineage_status": "restored",
        "response_hash": response_hash,
        "extracted_text_hash": extracted_text_hash,
        "prompt_injection_review": prompt_review["review"],
        "prompt_injection_review_status": prompt_review["status"],
        "prompt_injection_flags": prompt_review["flags"],
        "answer_support_allowed": prompt_review["answer_support_allowed"],
        "input_metadata": metadata,
        "page_metadata": page.metadata,
    }
    return {
        "artifact_id": artifact_id,
        "tool_call_id": tool_call_id,
        "run_id": run_id,
        "requested_url": requested_url,
        "final_url": page.url,
        "fetched_at": fetched_at,
        "retrieved_at": page.retrieved_at,
        "content_type": page.content_type,
        "status_code": page.status_code,
        "response_hash": response_hash,
        "extracted_text_hash": extracted_text_hash,
        "raw_artifact_path": raw_artifact_path,
        "prompt_injection_review": prompt_review["review"],
        "prompt_injection_status": prompt_review["status"],
        "prompt_injection_flags": prompt_review["flags"],
        "storage_rights": storage_rights,
        "fetch_provider": provider,
        "source_id": source_id,
        **lineage_ids,
        "metadata": artifact_metadata,
    }


def _fetch_artifact_metadata(
    fetch_artifact: dict[str, Any],
    *,
    source_kind: str,
    prompt_review: dict[str, Any],
) -> dict[str, Any]:
    source_lineage = {
        "document_id": fetch_artifact["source_id"],
        "source_id": fetch_artifact["source_id"],
        "source_kind": source_kind,
        "source_url": fetch_artifact["final_url"],
        "source_doc_hash": fetch_artifact["response_hash"],
        "response_hash": fetch_artifact["response_hash"],
        "extracted_text_hash": fetch_artifact["extracted_text_hash"],
        "fetch_artifact_id": fetch_artifact["artifact_id"],
        "source_bundle_id": fetch_artifact["source_bundle_id"],
        "source_restore_id": fetch_artifact["source_restore_id"],
        "lineage_status": "restored",
        "restored_at": fetch_artifact["retrieved_at"],
        "fetch_provider": fetch_artifact["fetch_provider"],
        "storage_rights": fetch_artifact["storage_rights"],
    }
    metadata = {
        "fetch_artifact_id": fetch_artifact["artifact_id"],
        "fetch_provider": fetch_artifact["fetch_provider"],
        "requested_url": fetch_artifact["requested_url"],
        "final_url": fetch_artifact["final_url"],
        "response_hash": fetch_artifact["response_hash"],
        "extracted_text_hash": fetch_artifact["extracted_text_hash"],
        "source_doc_hash": fetch_artifact["response_hash"],
        "source_bundle_id": fetch_artifact["source_bundle_id"],
        "source_restore_id": fetch_artifact["source_restore_id"],
        "lineage_status": "restored",
        "source_lineage": source_lineage,
        "primary_evidence_source_kind": source_kind,
        "primary_evidence_source_id": fetch_artifact["source_id"],
        "primary_evidence_hash": fetch_artifact["response_hash"],
        "primary_evidence_key": fetch_artifact["artifact_id"],
        "primary_evidence_identity": {
            "source_kind": source_kind,
            "source_id": fetch_artifact["source_id"],
            "identity_hash": fetch_artifact["response_hash"],
            "identity_key": fetch_artifact["artifact_id"],
        },
        "storage_rights": fetch_artifact["storage_rights"],
        "prompt_injection_review": prompt_review["review"],
        "prompt_injection_review_status": prompt_review["status"],
        "prompt_injection_flags": prompt_review["flags"],
        "prompt_injection_review_required": prompt_review["review_required"],
        "answer_support_allowed": prompt_review["answer_support_allowed"],
        "citation_policy": "reader_fetch_artifact_restored",
    }
    if prompt_review["review_required"]:
        metadata.update(
            {
                "citation_excluded": True,
                "support_policy": "review_required_before_answer_support",
                "citation_policy": "prompt_injection_review_required",
            }
        )
    return metadata


def _post_json(
    url: str,
    payload: dict[str, Any],
    *,
    headers: dict[str, str],
    timeout_seconds: float,
) -> dict[str, Any]:
    require_provider_transport_send_allowed(url)
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:  # noqa: S310
            body = response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        detail = exc.read(1000).decode("utf-8", errors="replace")
        raise RuntimeError(f"reader provider HTTP {exc.code}: {_compact_error(detail)}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"reader provider request failed: {exc.reason}") from exc
    try:
        parsed = json.loads(body)
    except json.JSONDecodeError as exc:
        raise RuntimeError("reader provider returned non-JSON response") from exc
    if not isinstance(parsed, dict):
        raise RuntimeError("reader provider returned unsupported JSON shape")
    return parsed


def _read_url(
    url: str,
    *,
    timeout_seconds: float,
    user_agent: str,
    max_bytes: int,
    extra_headers: dict[str, str] | None = None,
) -> HttpResponse:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError(f"unsupported URL scheme for reader provider: {parsed.scheme}")
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": user_agent,
            **(extra_headers or {}),
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:  # noqa: S310
            body = response.read(max_bytes + 1)
            content_type = response.headers.get("Content-Type", "")
            status_code = int(getattr(response, "status", 200))
            final_url = response.geturl()
    except urllib.error.HTTPError as exc:
        detail = exc.read(1000).decode("utf-8", errors="replace")
        raise RuntimeError(f"reader HTTP {exc.code}: {_compact_error(detail)}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"reader request failed: {exc.reason}") from exc
    truncated = len(body) > max_bytes
    return HttpResponse(
        final_url=final_url,
        status_code=status_code,
        content_type=content_type,
        body=body[:max_bytes],
        truncated=truncated,
    )


def _extract_text(body: bytes, content_type: str) -> tuple[str, str]:
    charset = _charset(content_type)
    text = body.decode(charset, errors="replace")
    if "html" in content_type.lower() or _looks_like_html(text):
        parser = _HtmlTextExtractor()
        parser.feed(text)
        return parser.title, _normalize_text(" ".join(parser.parts))
    return "", _normalize_text(text)


def _firecrawl_response_text(raw: dict[str, Any]) -> tuple[str, str, str]:
    data = raw.get("data")
    if isinstance(data, list):
        data = data[0] if data and isinstance(data[0], dict) else {}
    if not isinstance(data, dict):
        data = raw
    metadata = data.get("metadata") if isinstance(data.get("metadata"), dict) else {}
    title = _optional_text(data.get("title") or metadata.get("title") or metadata.get("ogTitle"))
    markdown = _optional_text(data.get("markdown"))
    if markdown:
        return title or "", _normalize_text(markdown), "text/markdown; provider=firecrawl"
    text = _optional_text(
        data.get("content")
        or data.get("text")
        or data.get("summary")
        or data.get("description")
    )
    if text:
        return title or "", _normalize_text(text), "text/plain; provider=firecrawl"
    html_text = _optional_text(data.get("html"))
    if html_text:
        extracted_title, extracted_text = _extract_text(
            html_text.encode("utf-8"),
            "text/html; charset=utf-8",
        )
        return title or extracted_title, extracted_text, "text/html; provider=firecrawl"
    return title or "", "", "text/plain; provider=firecrawl"


def _firecrawl_metadata(raw: dict[str, Any]) -> dict[str, Any]:
    data = raw.get("data")
    if isinstance(data, list):
        data = data[0] if data and isinstance(data[0], dict) else {}
    if not isinstance(data, dict):
        data = raw
    metadata = data.get("metadata")
    return metadata if isinstance(metadata, dict) else {}


class _HtmlTextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.title_parts: list[str] = []
        self.title = ""
        self._skip_depth = 0
        self._in_title = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        del attrs
        lowered = tag.lower()
        if lowered in {"script", "style", "noscript"}:
            self._skip_depth += 1
        elif lowered == "title":
            self._in_title = True
        elif lowered in {"p", "div", "br", "li", "section", "article", "h1", "h2", "h3"}:
            self.parts.append(" ")

    def handle_endtag(self, tag: str) -> None:
        lowered = tag.lower()
        if lowered in {"script", "style", "noscript"} and self._skip_depth:
            self._skip_depth -= 1
        elif lowered == "title":
            self._in_title = False
            self.title = _normalize_text(" ".join(self.title_parts))
        elif lowered in {"p", "div", "li", "section", "article"}:
            self.parts.append(" ")

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        if self._in_title:
            self.title_parts.append(data)
        else:
            self.parts.append(data)


def _reader_chunk_text(*, page: ReaderPage, query: str | None) -> str:
    parts = [
        f"Source URL: {page.url}",
        f"Title: {page.title}",
        f"Content type: {page.content_type}",
    ]
    if query:
        parts.append(f"Query context: {query}")
    parts.append(f"Extracted text: {page.text}")
    return "\n".join(parts)


def _charset(content_type: str) -> str:
    match = re.search(r"charset=([\w.-]+)", content_type, flags=re.IGNORECASE)
    return match.group(1) if match else "utf-8"


def _looks_like_html(text: str) -> bool:
    prefix = text.lstrip()[:200].lower()
    return prefix.startswith("<!doctype html") or prefix.startswith("<html") or "<body" in prefix


def _compact_text(value: str, *, limit: int) -> str:
    text = _normalize_text(value)
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 3)].rstrip() + "..."


def _normalize_text(value: str) -> str:
    return " ".join(html.unescape(value).split())


def _domain(url: str) -> str:
    return urllib.parse.urlparse(url).netloc.lower()


def _external_source_id(url: str) -> str:
    return _hash_id("external-web", url)[:24]


def _hash_id(*parts: str) -> str:
    return hashlib.sha256("\0".join(parts).encode("utf-8")).hexdigest()


def _text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _bytes_hash(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _json_hash(value: dict[str, Any]) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _safe_request_shape(request: dict[str, Any]) -> dict[str, Any]:
    safe = dict(request)
    headers = dict(safe.get("headers") or {})
    safe["headers"] = {
        key: ("<redacted>" if key.lower() in {"authorization", "x-api-key", "api-key"} else value)
        for key, value in headers.items()
    }
    return safe


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _optional_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _optional_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    return int(value)


def _estimate_tokens(text: str) -> int:
    ascii_words = len([part for part in text.split() if part])
    non_ascii = sum(1 for char in text if ord(char) > 127)
    return max(1, ascii_words + (non_ascii + 1) // 2)


def _compact_error(value: str, *, limit: int = 500) -> str:
    text = " ".join(value.split())
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 3)].rstrip() + "..."
