from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from research_x.memory.api_budget import api_units, budgeted_api_call, rough_text_tokens
from research_x.memory.schema import ensure_memory_schema
from research_x.memory.source_kinds import (
    EXTERNAL_WEB_MEDIUM,
    classify_external_source_kind,
    evidence_status_for_source,
    source_quality_class,
    source_risk_flags,
)

LLM_CONTEXT_ROLE = "llm_context_provider"
LLM_CONTEXT_EXTRACTOR_VERSION = "llm-context-v1"
BRAVE_LLM_CONTEXT_ENDPOINT = "https://api.search.brave.com/res/v1/llm/context"


@dataclass(frozen=True)
class LLMContextSource:
    source_id: str
    url: str | None
    title: str
    text: str
    content_type: str
    position: int
    metadata: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "url": self.url,
            "title": self.title,
            "text": self.text,
            "content_type": self.content_type,
            "position": self.position,
            "metadata": self.metadata,
        }


@dataclass(frozen=True)
class LLMContextBundle:
    tool_call_id: str
    provider: str
    provider_role: str
    action: str
    query: str
    endpoint: str
    parameters: dict[str, Any]
    sources: tuple[LLMContextSource, ...]
    context_chunks: tuple[dict[str, Any], ...]
    citation_annotations: tuple[dict[str, Any], ...]
    raw_response_hash: str | None
    retrieved_at: str
    retention_policy: str
    metadata: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {
            "tool_call_id": self.tool_call_id,
            "provider": self.provider,
            "provider_role": self.provider_role,
            "action": self.action,
            "query": self.query,
            "endpoint": self.endpoint,
            "parameters": self.parameters,
            "sources": [source.as_dict() for source in self.sources],
            "context_chunks": list(self.context_chunks),
            "citation_annotations": list(self.citation_annotations),
            "raw_response_hash": self.raw_response_hash,
            "retrieved_at": self.retrieved_at,
            "retention_policy": self.retention_policy,
            "metadata": self.metadata,
        }


class LLMContextProvider(Protocol):
    provider_id: str
    provider_role: str

    def fetch(
        self,
        query: str,
        *,
        parameters: dict[str, Any],
        max_chars_per_source: int,
    ) -> tuple[tuple[LLMContextSource, ...], str | None, dict[str, Any]]:
        """Return LLM-ready context sources for a search query."""


class FakeLLMContextProvider:
    provider_id = "fake"
    provider_role = LLM_CONTEXT_ROLE

    def fetch(
        self,
        query: str,
        *,
        parameters: dict[str, Any],
        max_chars_per_source: int,
    ) -> tuple[tuple[LLMContextSource, ...], str | None, dict[str, Any]]:
        del parameters
        text = (
            f"Fake LLM context for {query}. "
            "This deterministic source verifies LLM-context storage and citation wiring."
        )
        source = LLMContextSource(
            source_id=_hash_id("llm-source", "fake", query)[:24],
            url=f"memory://fake-llm-context/{_hash_id(query)[:12]}",
            title=f"Fake LLM context: {query}",
            text=_compact_text(text, limit=max_chars_per_source),
            content_type="text/plain; fixture=fake",
            position=0,
            metadata={"fixture": True},
        )
        return (source,), None, {"fixture": True}


class BraveLLMContextProvider:
    provider_id = "brave"
    provider_role = LLM_CONTEXT_ROLE

    def __init__(
        self,
        *,
        api_key_env: str = "BRAVE_SEARCH_API_KEY",
        endpoint: str | None = None,
        timeout_seconds: float = 30.0,
    ) -> None:
        self.api_key_env = api_key_env
        self.endpoint = endpoint or BRAVE_LLM_CONTEXT_ENDPOINT
        self.timeout_seconds = timeout_seconds

    def fetch(
        self,
        query: str,
        *,
        parameters: dict[str, Any],
        max_chars_per_source: int,
    ) -> tuple[tuple[LLMContextSource, ...], str | None, dict[str, Any]]:
        payload = {"q": query, **parameters}
        raw = _post_json_budgeted(
            self.endpoint,
            payload,
            headers={"X-Subscription-Token": _api_key(self.api_key_env)},
            timeout_seconds=self.timeout_seconds,
            budget_provider=self.provider_id,
            budget_model="llm-context",
            budget_units=api_units(
                calls=1,
                input_tokens=rough_text_tokens(payload),
                documents=int(parameters.get("count") or 0),
            ),
        )
        sources = _sources_from_brave_response(raw, max_chars_per_source=max_chars_per_source)
        return sources, _json_hash(raw), {"grounding_keys": sorted(raw.get("grounding") or {})}


def fetch_llm_context_to_context(
    db_path: str | Path,
    query: str,
    *,
    run_id: str | None = None,
    chunk_index_offset: int = 0,
    provider: str = "brave",
    api_key_env: str = "BRAVE_SEARCH_API_KEY",
    endpoint: str | None = None,
    country: str | None = None,
    search_lang: str | None = None,
    count: int = 20,
    maximum_number_of_urls: int = 20,
    maximum_number_of_tokens: int = 8192,
    maximum_number_of_snippets: int = 50,
    context_threshold_mode: str = "balanced",
    maximum_number_of_tokens_per_url: int = 4096,
    maximum_number_of_snippets_per_url: int = 50,
    freshness: str | None = None,
    enable_local: bool | None = None,
    goggles: str | None = None,
    max_chars_per_source: int = 6000,
    timeout_seconds: float = 30.0,
    store: bool = True,
) -> LLMContextBundle:
    provider_impl = _provider(
        provider,
        api_key_env=api_key_env,
        endpoint=endpoint,
        timeout_seconds=timeout_seconds,
    )
    parameters = _request_parameters(
        country=country,
        search_lang=search_lang,
        count=count,
        maximum_number_of_urls=maximum_number_of_urls,
        maximum_number_of_tokens=maximum_number_of_tokens,
        maximum_number_of_snippets=maximum_number_of_snippets,
        context_threshold_mode=context_threshold_mode,
        maximum_number_of_tokens_per_url=maximum_number_of_tokens_per_url,
        maximum_number_of_snippets_per_url=maximum_number_of_snippets_per_url,
        freshness=freshness,
        enable_local=enable_local,
        goggles=goggles,
    )
    retrieved_at = _utc_now()
    sources, raw_response_hash, provider_metadata = provider_impl.fetch(
        query,
        parameters=parameters,
        max_chars_per_source=max(1, max_chars_per_source),
    )
    tool_call_id = _hash_id(
        "llm-context-tool-call",
        provider_impl.provider_id,
        query,
        retrieved_at,
        raw_response_hash or _json_hash([source.as_dict() for source in sources]),
    )[:24]
    chunks = tuple(
        _context_chunk(
            tool_call_id=tool_call_id,
            provider=provider_impl.provider_id,
            source=source,
            run_id=run_id,
            query=query,
            chunk_index_offset=max(0, chunk_index_offset),
        )
        for source in sources
    )
    citations = tuple(
        _citation_annotation(tool_call_id=tool_call_id, chunk=chunk, source=source)
        for chunk, source in zip(chunks, sources, strict=True)
    )
    bundle = LLMContextBundle(
        tool_call_id=tool_call_id,
        provider=provider_impl.provider_id,
        provider_role=provider_impl.provider_role,
        action="llm_context",
        query=query,
        endpoint=endpoint or (
            BRAVE_LLM_CONTEXT_ENDPOINT
            if provider_impl.provider_id == "brave"
            else "memory://fake-llm-context"
        ),
        parameters={
            **parameters,
            "api_key_env": api_key_env if provider_impl.provider_id == "brave" else None,
            "max_chars_per_source": max_chars_per_source,
        },
        sources=sources,
        context_chunks=chunks,
        citation_annotations=citations,
        raw_response_hash=raw_response_hash,
        retrieved_at=retrieved_at,
        retention_policy="extracted_context_with_source_urls",
        metadata=provider_metadata,
    )
    if store:
        _store_llm_context_bundle(db_path, bundle)
    return bundle


def llm_context_json(bundle: LLMContextBundle) -> str:
    return json.dumps(bundle.as_dict(), ensure_ascii=False, indent=2, sort_keys=True)


def _store_llm_context_bundle(db_path: str | Path, bundle: LLMContextBundle) -> None:
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
                bundle.context_chunks[0]["run_id"] if bundle.context_chunks else None,
                bundle.provider,
                bundle.provider_role,
                bundle.action,
                json.dumps(
                    {
                        "query": bundle.query,
                        "endpoint": bundle.endpoint,
                        "parameters": bundle.parameters,
                        "retention_policy": bundle.retention_policy,
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                ),
                json.dumps(
                    {
                        "source_count": len(bundle.sources),
                        "chunk_count": len(bundle.context_chunks),
                        "citation_count": len(bundle.citation_annotations),
                        "raw_response_hash": bundle.raw_response_hash,
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                ),
                "ok",
                None,
                bundle.retrieved_at,
                bundle.retrieved_at,
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
    source: LLMContextSource,
    run_id: str | None,
    query: str,
    chunk_index_offset: int,
) -> dict[str, Any]:
    chunk_text = _chunk_text(query=query, source=source)
    source_kind = classify_external_source_kind(source.url, metadata=source.metadata)
    chunk_id = _hash_id("llm-context-chunk", tool_call_id, source.source_id, _text_hash(chunk_text))
    return {
        "chunk_id": chunk_id,
        "run_id": run_id,
        "source_kind": source_kind,
        "source_id": source.source_id,
        "source_url": source.url,
        "provider": provider,
        "provider_role": LLM_CONTEXT_ROLE,
        "chunk_text": chunk_text,
        "chunk_index": chunk_index_offset + source.position,
        "token_count": _estimate_tokens(chunk_text),
        "relevance_score": 0.0,
        "extractor_version": LLM_CONTEXT_EXTRACTOR_VERSION,
        "created_at": _utc_now(),
        "metadata": {
            "title": source.title,
            "content_type": source.content_type,
            "source_medium": EXTERNAL_WEB_MEDIUM,
            "evidence_source_kind": source_kind,
            "source_quality_class": source_quality_class(source.url, source_kind=source_kind),
            "source_risk_flags": source_risk_flags(source.url, source_kind=source_kind),
            "source_metadata": source.metadata,
            "retention_policy": "extracted_context_with_source_urls",
        },
    }


def _citation_annotation(
    *,
    tool_call_id: str,
    chunk: dict[str, Any],
    source: LLMContextSource,
) -> dict[str, Any]:
    citation_id = _hash_id("llm-context-citation", tool_call_id, chunk["chunk_id"])
    evidence_status = evidence_status_for_source(source.url, provider=str(chunk["provider"]))
    return {
        "citation_id": citation_id,
        "answer_id": None,
        "chunk_id": chunk["chunk_id"],
        "source_kind": chunk["source_kind"],
        "source_id": source.source_id,
        "source_url": source.url,
        "title": source.title,
        "field_path": "context_chunks[llm_context]",
        "support_type": "background",
        "evidence_status": evidence_status,
        "confidence": 0.8 if evidence_status == "fact" else 0.4,
        "created_at": _utc_now(),
        "metadata": {
            "provider_role": LLM_CONTEXT_ROLE,
            "tool_call_id": tool_call_id,
            "content_type": source.content_type,
            "source_medium": EXTERNAL_WEB_MEDIUM,
            "evidence_source_kind": chunk["source_kind"],
        },
    }


def _provider(
    provider: str,
    *,
    api_key_env: str,
    endpoint: str | None,
    timeout_seconds: float,
) -> LLMContextProvider:
    provider_id = provider.strip().lower()
    if provider_id == "fake":
        return FakeLLMContextProvider()
    if provider_id == "brave":
        return BraveLLMContextProvider(
            api_key_env=api_key_env,
            endpoint=endpoint,
            timeout_seconds=timeout_seconds,
        )
    raise ValueError(f"unknown LLM-context provider: {provider}")


def _request_parameters(
    *,
    country: str | None,
    search_lang: str | None,
    count: int,
    maximum_number_of_urls: int,
    maximum_number_of_tokens: int,
    maximum_number_of_snippets: int,
    context_threshold_mode: str,
    maximum_number_of_tokens_per_url: int,
    maximum_number_of_snippets_per_url: int,
    freshness: str | None,
    enable_local: bool | None,
    goggles: str | None,
) -> dict[str, Any]:
    params: dict[str, Any] = {
        "count": _clamp(count, 1, 50),
        "maximum_number_of_urls": _clamp(maximum_number_of_urls, 1, 50),
        "maximum_number_of_tokens": _clamp(maximum_number_of_tokens, 1024, 32768),
        "maximum_number_of_snippets": _clamp(maximum_number_of_snippets, 1, 256),
        "context_threshold_mode": context_threshold_mode,
        "maximum_number_of_tokens_per_url": _clamp(maximum_number_of_tokens_per_url, 512, 8192),
        "maximum_number_of_snippets_per_url": _clamp(maximum_number_of_snippets_per_url, 1, 100),
    }
    if country:
        params["country"] = country
    if search_lang:
        params["search_lang"] = search_lang
    if freshness:
        params["freshness"] = freshness
    if enable_local is not None:
        params["enable_local"] = enable_local
    if goggles:
        params["goggles"] = goggles
    return params


def _sources_from_brave_response(
    raw: dict[str, Any],
    *,
    max_chars_per_source: int,
) -> tuple[LLMContextSource, ...]:
    grounding = raw.get("grounding")
    if not isinstance(grounding, dict):
        return ()
    source_metadata = raw.get("sources") if isinstance(raw.get("sources"), dict) else {}
    sources: list[LLMContextSource] = []
    for content_type, value in grounding.items():
        for item in _iter_grounding_items(value):
            url = _string_or_none(item.get("url") or item.get("link") or item.get("website"))
            metadata = source_metadata.get(url, {}) if url else {}
            title = _string_or_none(item.get("title") or item.get("name"))
            if not title and isinstance(metadata, dict):
                title = _string_or_none(metadata.get("title") or metadata.get("site_name"))
            text = _grounding_text(item)
            if not text:
                continue
            source_id = _hash_id("llm-source", url or content_type, str(len(sources)))[:24]
            sources.append(
                LLMContextSource(
                    source_id=source_id,
                    url=url,
                    title=title or url or content_type,
                    text=_compact_text(text, limit=max_chars_per_source),
                    content_type=str(content_type),
                    position=len(sources),
                    metadata={
                        "brave_source_metadata": metadata if isinstance(metadata, dict) else {},
                        "raw_keys": sorted(str(key) for key in item),
                    },
                )
            )
    return tuple(sources)


def _iter_grounding_items(value: Any):
    if isinstance(value, list):
        for item in value:
            if isinstance(item, dict):
                yield item
    elif isinstance(value, dict):
        yield value


def _grounding_text(item: dict[str, Any]) -> str:
    snippets = item.get("snippets")
    if isinstance(snippets, list):
        parts = [str(snippet) for snippet in snippets if str(snippet).strip()]
        if parts:
            return "\n\n".join(parts)
    text = item.get("text") or item.get("description") or item.get("summary")
    if isinstance(text, str) and text.strip():
        return text
    return json.dumps(item, ensure_ascii=False, sort_keys=True)


def _chunk_text(*, query: str, source: LLMContextSource) -> str:
    parts = [
        f"Source URL: {source.url or ''}",
        f"Title: {source.title}",
        f"Content type: {source.content_type}",
        f"Query context: {query}",
        f"Extracted text: {source.text}",
    ]
    return "\n".join(parts)


def _post_json(
    url: str,
    payload: dict[str, Any],
    *,
    headers: dict[str, str],
    timeout_seconds: float,
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
        )

    if budget_provider is None and budget_model is None and budget_units is None:
        return send()
    with budgeted_api_call(
        provider=budget_provider or "unknown",
        model=budget_model or "unknown",
        provider_role=LLM_CONTEXT_ROLE,
        operation="llm_context",
        units=budget_units or api_units(calls=1),
        request_payload=payload,
        metadata={"url": url},
    ):
        return send()


def _post_json_budgeted(
    url: str,
    payload: dict[str, Any],
    *,
    headers: dict[str, str],
    timeout_seconds: float,
    budget_provider: str,
    budget_model: str,
    budget_units: dict[str, int | float] | None = None,
) -> dict[str, Any]:
    with budgeted_api_call(
        provider=budget_provider,
        model=budget_model,
        provider_role=LLM_CONTEXT_ROLE,
        operation="llm_context",
        units=budget_units or api_units(calls=1),
        request_payload=payload,
        metadata={"url": url},
    ):
        return _post_json(
            url,
            payload,
            headers=headers,
            timeout_seconds=timeout_seconds,
        )


def _post_json_unbudgeted(
    url: str,
    payload: dict[str, Any],
    *,
    headers: dict[str, str],
    timeout_seconds: float,
) -> dict[str, Any]:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        headers={"Accept": "application/json", "Content-Type": "application/json", **headers},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:  # noqa: S310
            data = response.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read(2000).decode("utf-8", errors="replace")
        raise RuntimeError(f"LLM-context API HTTP {exc.code}: {_compact_error(detail)}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"LLM-context API request failed: {exc.reason}") from exc
    parsed = json.loads(data.decode("utf-8"))
    if not isinstance(parsed, dict):
        raise RuntimeError("LLM-context API response must be a JSON object")
    return parsed


def _api_key(env_name: str) -> str:
    value = os.environ.get(env_name)
    if not value:
        raise RuntimeError(f"missing API key environment variable: {env_name}")
    return value


def _string_or_none(value: Any) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _clamp(value: int, minimum: int, maximum: int) -> int:
    return min(maximum, max(minimum, int(value)))


def _compact_text(value: str, *, limit: int) -> str:
    text = " ".join(value.split())
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 3)].rstrip() + "..."


def _compact_error(value: str, *, limit: int = 500) -> str:
    text = " ".join(value.split())
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 3)].rstrip() + "..."


def _json_hash(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()


def _hash_id(*parts: str) -> str:
    return hashlib.sha256("\0".join(parts).encode("utf-8")).hexdigest()


def _text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _estimate_tokens(text: str) -> int:
    ascii_words = len([part for part in text.split() if part])
    non_ascii = sum(1 for char in text if ord(char) > 127)
    return max(1, ascii_words + (non_ascii + 1) // 2)
