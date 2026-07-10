from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from research_x.memory.api_budget import (
    PROVIDER_EXECUTION_POLICY_REQUIRED_STATUS,
    active_api_budget_context,
    api_units,
    budgeted_api_call,
    require_provider_transport_send_allowed,
    rough_text_tokens,
)
from research_x.memory.schema import ensure_memory_schema

INDEX_PROVIDER_ROLE = "index_provider"
EXTERNAL_SEARCH_OPERATION = "external_search"
DEFAULT_RETENTION_POLICY = "normalized_results_only"
CANDIDATE_EVIDENCE_STATUS = "not_evidence_until_reader_chunk"

SERPER_ENDPOINT = "https://google.serper.dev/search"
TAVILY_ENDPOINT = "https://api.tavily.com/search"
EXA_ENDPOINT = "https://api.exa.ai/search"
PERPLEXITY_ENDPOINT = "https://api.perplexity.ai/search"
FIRECRAWL_SEARCH_ENDPOINT = "https://api.firecrawl.dev/v1/search"
SEARXNG_ENDPOINT = "http://127.0.0.1:8080/search"

PROVIDER_ENDPOINTS = {
    "serper": SERPER_ENDPOINT,
    "tavily": TAVILY_ENDPOINT,
    "exa": EXA_ENDPOINT,
    "perplexity": PERPLEXITY_ENDPOINT,
    "firecrawl": FIRECRAWL_SEARCH_ENDPOINT,
    "searxng": SEARXNG_ENDPOINT,
}
PROVIDER_API_KEY_ENVS = {
    "serper": "SERPER_API_KEY",
    "tavily": "TAVILY_API_KEY",
    "exa": "EXA_API_KEY",
    "perplexity": "PERPLEXITY_API_KEY",
    "firecrawl": "FIRECRAWL_API_KEY",
    "searxng": None,
}
PROVIDER_MODELS = {
    "serper": "serper-search",
    "tavily": "tavily-search",
    "exa": "exa-search",
    "perplexity": "perplexity-search",
    "firecrawl": "firecrawl-search",
    "searxng": "searxng-search",
}
API_KEY_HEADER_NAMES = {"authorization", "x-api-key", "api-key"}

ExternalTransport = Callable[[dict[str, Any]], dict[str, Any]]


@dataclass(frozen=True)
class ExternalEvidenceItem:
    position: int
    title: str
    url: str
    snippet: str
    source: str
    metadata: dict[str, Any] = field(default_factory=dict)
    provider: str = ""
    source_id: str = ""
    run_id: str = ""
    content: str | None = None
    published_at: str | None = None
    raw_payload: dict[str, Any] = field(default_factory=dict)
    evidence_status: str = CANDIDATE_EVIDENCE_STATUS
    citation_excluded: bool = True
    candidate_score: float | None = None

    def as_dict(self) -> dict[str, Any]:
        provider = self.provider or str(self.metadata.get("provider") or "")
        source_id = self.source_id or _source_candidate_id(provider, self.url, self.title)
        return {
            "position": self.position,
            "rank": self.position,
            "provider": provider,
            "source_id": source_id,
            "run_id": self.run_id,
            "title": self.title,
            "url": self.url,
            "snippet": self.snippet,
            "content": self.content if self.content is not None else self.snippet,
            "published_at": self.published_at,
            "source": self.source,
            "domain": self.source,
            "raw_payload": self.raw_payload,
            "candidate_score": self.candidate_score,
            "citation_excluded": self.citation_excluded,
            "evidence_status": self.evidence_status,
            "metadata": self.metadata,
        }


@dataclass(frozen=True)
class ExternalEvidenceBundle:
    run_id: str
    query: str
    provider: str
    provider_role: str
    endpoint: str
    parameters: dict[str, Any]
    status: str
    retrieved_at: str
    raw_response_hash: str | None
    retention_policy: str
    items: tuple[ExternalEvidenceItem, ...]
    error: str | None = None
    provider_policy_status: str | None = None
    request_shape: dict[str, Any] | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "query": self.query,
            "provider": self.provider,
            "provider_role": self.provider_role,
            "endpoint": self.endpoint,
            "parameters": self.parameters,
            "status": self.status,
            "provider_policy_status": self.provider_policy_status,
            "retrieved_at": self.retrieved_at,
            "raw_response_hash": self.raw_response_hash,
            "retention_policy": self.retention_policy,
            "source_candidate_policy": {
                "raw_provider_response_is_answer_support": False,
                "external_item_is_source_candidate_only": True,
                "requires_fetch_artifact": True,
                "requires_source_bundle": True,
                "requires_context_chunk": True,
                "requires_citation_annotation": True,
            },
            "evidence_policy": {
                "url_discovery_is_not_evidence": True,
                "rank_is_not_evidence": True,
                "snippet_is_not_evidence": True,
                "raw_payload_is_not_evidence": True,
                "requires_reader_context_chunk": True,
            },
            "request_shape": self.request_shape,
            "items": [item.as_dict() for item in self.items],
            "error": self.error,
        }


class ExternalSearchProvider(Protocol):
    provider_id: str
    provider_role: str

    def search(
        self,
        query: str,
        *,
        limit: int,
        transport: ExternalTransport | None = None,
    ) -> ExternalEvidenceBundle:
        """Return URL discovery candidates. The bundle is not citation-ready evidence."""


class FakeExternalSearchProvider:
    provider_id = "fake"
    provider_role = INDEX_PROVIDER_ROLE
    endpoint = "memory://fake-external-search"

    def search(
        self,
        query: str,
        *,
        limit: int,
        transport: ExternalTransport | None = None,
    ) -> ExternalEvidenceBundle:
        resolved_limit = max(1, limit)
        retrieved_at = _utc_now()
        slug = _slug(query)
        items = tuple(
            ExternalEvidenceItem(
                position=index,
                title=f"Fake external result {index} for {query}",
                url=f"https://example.invalid/research-x/{slug}/{index}",
                snippet=(
                    "Deterministic no-network discovery result. "
                    "Use this provider to test external candidate wiring."
                ),
                source="example.invalid",
                provider=self.provider_id,
                raw_payload={"fixture": True, "position": index, "query": query},
                metadata={
                    "fixture": True,
                    "citation_excluded": True,
                    "evidence_status": CANDIDATE_EVIDENCE_STATUS,
                    "rank_is_not_evidence": True,
                    "snippet_is_not_evidence": True,
                    "raw_payload_is_not_evidence": True,
                },
            )
            for index in range(1, resolved_limit + 1)
        )
        raw = {"query": query, "items": [item.as_dict() for item in items]}
        return _bundle(
            query=query,
            provider=self.provider_id,
            provider_role=self.provider_role,
            endpoint=self.endpoint,
            parameters={"limit": resolved_limit},
            status="ok",
            retrieved_at=retrieved_at,
            raw_response=raw,
            items=items,
        )


class ProviderExternalSearchProvider:
    provider_role = INDEX_PROVIDER_ROLE

    def __init__(
        self,
        provider_id: str,
        *,
        api_key_env: str | None = None,
        endpoint: str | None = None,
        timeout_seconds: float = 30.0,
        country: str | None = None,
        language: str | None = None,
        location: str | None = None,
    ) -> None:
        self.provider_id = _provider_id(provider_id)
        self.api_key_env = _resolved_api_key_env(self.provider_id, api_key_env)
        self.endpoint = endpoint or PROVIDER_ENDPOINTS[self.provider_id]
        self.timeout_seconds = timeout_seconds
        self.country = country
        self.language = language
        self.location = location

    def search(
        self,
        query: str,
        *,
        limit: int,
        transport: ExternalTransport | None = None,
    ) -> ExternalEvidenceBundle:
        resolved_limit = max(1, limit)
        api_key = os.environ.get(self.api_key_env) if self.api_key_env else None
        request = build_external_search_request(
            self.provider_id,
            query=query,
            limit=resolved_limit,
            api_key=api_key,
            api_key_env=self.api_key_env,
            endpoint=self.endpoint,
            country=self.country,
            language=self.language,
            location=self.location,
            timeout_seconds=self.timeout_seconds,
        )
        retrieved_at = _utc_now()

        if transport is None and not _active_provider_policy_present():
            return _provider_policy_required_bundle(
                query=query,
                provider=self.provider_id,
                endpoint=self.endpoint,
                parameters=_request_public_parameters(request),
                retrieved_at=retrieved_at,
                request_shape=request,
                error=PROVIDER_EXECUTION_POLICY_REQUIRED_STATUS,
            )
        if transport is None and request["api_key_required"] and not api_key:
            raise RuntimeError(f"{self.api_key_env} is not set")

        try:
            raw = transport(request) if transport is not None else _send_provider_request(request)
        except RuntimeError as exc:
            if _is_provider_policy_error(exc):
                return _provider_policy_required_bundle(
                    query=query,
                    provider=self.provider_id,
                    endpoint=self.endpoint,
                    parameters=_request_public_parameters(request),
                    retrieved_at=retrieved_at,
                    request_shape=request,
                    error=str(exc),
                )
            raise

        if not isinstance(raw, dict):
            raise RuntimeError("external provider transport returned unsupported JSON shape")
        items = normalize_external_source_candidates(
            self.provider_id,
            raw,
            limit=resolved_limit,
            query=query,
        )
        return _bundle(
            query=query,
            provider=self.provider_id,
            provider_role=self.provider_role,
            endpoint=self.endpoint,
            parameters=_request_public_parameters(request),
            status="ok",
            retrieved_at=retrieved_at,
            raw_response=raw,
            items=items,
            request_shape=request,
        )


class SerperSearchProvider(ProviderExternalSearchProvider):
    def __init__(
        self,
        *,
        api_key_env: str | None = "SERPER_API_KEY",
        endpoint: str = SERPER_ENDPOINT,
        timeout_seconds: float = 30.0,
        country: str | None = None,
        language: str | None = None,
        location: str | None = None,
    ) -> None:
        super().__init__(
            "serper",
            api_key_env=api_key_env,
            endpoint=endpoint,
            timeout_seconds=timeout_seconds,
            country=country,
            language=language,
            location=location,
        )


def build_external_search_request(
    provider: str,
    *,
    query: str,
    limit: int,
    api_key: str | None = None,
    api_key_env: str | None = None,
    endpoint: str | None = None,
    country: str | None = None,
    language: str | None = None,
    location: str | None = None,
    timeout_seconds: float = 30.0,
) -> dict[str, Any]:
    provider_id = _provider_id(provider)
    resolved_limit = max(1, limit)
    resolved_endpoint = endpoint or PROVIDER_ENDPOINTS[provider_id]
    resolved_api_key_env = _resolved_api_key_env(provider_id, api_key_env)
    request: dict[str, Any] = {
        "provider": provider_id,
        "provider_role": INDEX_PROVIDER_ROLE,
        "operation": EXTERNAL_SEARCH_OPERATION,
        "model": PROVIDER_MODELS[provider_id],
        "method": "POST",
        "url": resolved_endpoint,
        "endpoint": resolved_endpoint,
        "payload": {},
        "params": {},
        "headers": {"Content-Type": "application/json"},
        "timeout_seconds": timeout_seconds,
        "api_key_env": resolved_api_key_env,
        "api_key_used": bool(api_key),
        "api_key_required": provider_id != "searxng",
        "request_shape_only": True,
        "provider_quality_proof": False,
        "source_candidate_only": True,
    }

    if provider_id == "serper":
        payload: dict[str, Any] = {"q": query, "num": resolved_limit}
        if country:
            payload["gl"] = country
        if language:
            payload["hl"] = language
        if location:
            payload["location"] = location
        request["payload"] = payload
        if api_key:
            request["headers"]["X-API-KEY"] = api_key
        return request

    if provider_id == "tavily":
        request["payload"] = {
            "query": query,
            "max_results": resolved_limit,
            "search_depth": "basic",
        }
        if api_key:
            request["headers"]["Authorization"] = f"Bearer {api_key}"
        return request

    if provider_id == "exa":
        request["payload"] = {
            "query": query,
            "numResults": resolved_limit,
            "type": "auto",
            "contents": {"text": {"maxCharacters": 1000}},
        }
        if api_key:
            request["headers"]["x-api-key"] = api_key
        return request

    if provider_id == "perplexity":
        request["payload"] = {"query": query, "max_results": resolved_limit}
        if api_key:
            request["headers"]["Authorization"] = f"Bearer {api_key}"
        return request

    if provider_id == "firecrawl":
        request["payload"] = {"query": query, "limit": resolved_limit}
        if api_key:
            request["headers"]["Authorization"] = f"Bearer {api_key}"
        return request

    if provider_id == "searxng":
        params: dict[str, Any] = {"q": query, "format": "json"}
        if language:
            params["language"] = language
        request.update(
            {
                "method": "GET",
                "payload": {},
                "params": params,
                "headers": {"Accept": "application/json"},
            }
        )
        return request

    raise AssertionError(f"unhandled external provider {provider_id}")


def normalize_external_source_candidates(
    provider: str,
    raw_response: dict[str, Any],
    *,
    limit: int,
    query: str = "",
    run_id: str = "",
) -> tuple[ExternalEvidenceItem, ...]:
    provider_id = _provider_id(provider)
    rows = _provider_result_rows(provider_id, raw_response)
    items: list[ExternalEvidenceItem] = []
    for index, raw_row in enumerate(rows[: max(1, limit)], start=1):
        row = _coerce_raw_row(raw_row)
        url = _row_url(row)
        if not url:
            continue
        title = _row_title(row) or url
        content = _row_content(row)
        snippet = _row_snippet(row, content=content)
        published_at = _row_published_at(row)
        domain = _domain(url)
        source_id = _source_candidate_id(provider_id, url, title)
        raw_payload_hash = _json_hash(row)
        metadata = _external_item_metadata(row)
        metadata.update(
            {
                "provider": provider_id,
                "source_id": source_id,
                "run_id": run_id,
                "query": query,
                "raw_payload_hash": raw_payload_hash,
                "raw_payload": row,
                "raw_payload_is_not_evidence": True,
                "source_candidate_policy": "requires_fetch_extract_chunk_citation",
                "prompt_injection_review": "required_before_fetch",
                "storage_rights": "requires_fetch_artifact_review",
            }
        )
        score = _row_score(row)
        if score is not None:
            metadata["candidate_score"] = score
        items.append(
            ExternalEvidenceItem(
                position=index,
                title=title,
                url=url,
                snippet=snippet,
                content=content,
                published_at=published_at,
                source=domain,
                provider=provider_id,
                source_id=source_id,
                run_id=run_id,
                raw_payload=row,
                candidate_score=score,
                metadata=metadata,
            )
        )
    return tuple(items)


def search_external_candidates(
    db_path: str | Path,
    query: str,
    *,
    provider: str = "fake",
    limit: int = 5,
    api_key_env: str | None = "SERPER_API_KEY",
    endpoint: str | None = None,
    country: str | None = None,
    language: str | None = None,
    location: str | None = None,
    timeout_seconds: float = 30.0,
    store: bool = True,
    transport: ExternalTransport | None = None,
) -> ExternalEvidenceBundle:
    provider_impl = _provider(
        provider,
        api_key_env=api_key_env,
        endpoint=endpoint,
        country=country,
        language=language,
        location=location,
        timeout_seconds=timeout_seconds,
    )
    bundle = provider_impl.search(query, limit=limit, transport=transport)
    if store:
        store_external_evidence_bundle(db_path, bundle)
    return bundle


def search_external_evidence(
    db_path: str | Path,
    query: str,
    *,
    provider: str = "fake",
    limit: int = 5,
    api_key_env: str | None = "SERPER_API_KEY",
    endpoint: str | None = None,
    country: str | None = None,
    language: str | None = None,
    location: str | None = None,
    timeout_seconds: float = 30.0,
    store: bool = True,
    transport: ExternalTransport | None = None,
) -> ExternalEvidenceBundle:
    return search_external_candidates(
        db_path,
        query,
        provider=provider,
        limit=limit,
        api_key_env=api_key_env,
        endpoint=endpoint,
        country=country,
        language=language,
        location=location,
        timeout_seconds=timeout_seconds,
        store=store,
        transport=transport,
    )


def store_external_evidence_bundle(
    db_path: str | Path,
    bundle: ExternalEvidenceBundle,
) -> None:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path, timeout=60) as conn:
        ensure_memory_schema(conn)
        conn.execute(
            """
            INSERT INTO memory_external_runs (
                run_id, provider, provider_role, query, endpoint, parameters_json,
                status, retrieved_at, raw_response_hash, retention_policy, error
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(run_id) DO UPDATE SET
                status=excluded.status,
                raw_response_hash=excluded.raw_response_hash,
                error=excluded.error
            """,
            (
                bundle.run_id,
                bundle.provider,
                bundle.provider_role,
                bundle.query,
                bundle.endpoint,
                json.dumps(bundle.parameters, ensure_ascii=False, sort_keys=True),
                bundle.status,
                bundle.retrieved_at,
                bundle.raw_response_hash,
                bundle.retention_policy,
                bundle.error,
            ),
        )
        for item in bundle.items:
            item_id = _item_id(bundle.run_id, item)
            conn.execute(
                """
                INSERT INTO memory_external_items (
                    item_id, run_id, position, title, url, snippet, source, metadata_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(item_id) DO UPDATE SET
                    position=excluded.position,
                    title=excluded.title,
                    snippet=excluded.snippet,
                    source=excluded.source,
                    metadata_json=excluded.metadata_json
                """,
                (
                    item_id,
                    bundle.run_id,
                    item.position,
                    item.title,
                    item.url,
                    item.snippet,
                    item.source,
                    json.dumps(_stored_item_metadata(item), ensure_ascii=False, sort_keys=True),
                ),
            )


def external_candidates_json(bundle: ExternalEvidenceBundle) -> str:
    return json.dumps(bundle.as_dict(), ensure_ascii=False, indent=2, sort_keys=True)


def external_evidence_json(bundle: ExternalEvidenceBundle) -> str:
    return external_candidates_json(bundle)


def _provider(
    provider: str,
    *,
    api_key_env: str | None,
    endpoint: str | None,
    country: str | None,
    language: str | None,
    location: str | None,
    timeout_seconds: float,
) -> ExternalSearchProvider:
    provider_id = provider.strip().lower()
    if provider_id == "fake":
        return FakeExternalSearchProvider()
    if provider_id == "serper":
        return SerperSearchProvider(
            api_key_env=api_key_env,
            endpoint=endpoint or SERPER_ENDPOINT,
            country=country,
            language=language,
            location=location,
            timeout_seconds=timeout_seconds,
        )
    if provider_id in PROVIDER_ENDPOINTS:
        return ProviderExternalSearchProvider(
            provider_id,
            api_key_env=api_key_env,
            endpoint=endpoint,
            country=country,
            language=language,
            location=location,
            timeout_seconds=timeout_seconds,
        )
    raise ValueError(f"unknown external evidence provider: {provider}")


def _bundle(
    *,
    query: str,
    provider: str,
    provider_role: str,
    endpoint: str,
    parameters: dict[str, Any],
    status: str,
    retrieved_at: str,
    raw_response: dict[str, Any],
    items: tuple[ExternalEvidenceItem, ...],
    error: str | None = None,
    provider_policy_status: str | None = None,
    request_shape: dict[str, Any] | None = None,
) -> ExternalEvidenceBundle:
    raw_hash = _json_hash(raw_response)
    run_id = _run_id(provider, provider_role, query, endpoint, parameters, retrieved_at, raw_hash)
    prepared_items = _items_with_run_info(items, run_id=run_id, provider=provider)
    return ExternalEvidenceBundle(
        run_id=run_id,
        query=query,
        provider=provider,
        provider_role=provider_role,
        endpoint=endpoint,
        parameters=parameters,
        status=status,
        provider_policy_status=provider_policy_status,
        retrieved_at=retrieved_at,
        raw_response_hash=raw_hash,
        retention_policy=DEFAULT_RETENTION_POLICY,
        items=prepared_items,
        error=error,
        request_shape=_safe_request_shape(request_shape) if request_shape else None,
    )


def _provider_policy_required_bundle(
    *,
    query: str,
    provider: str,
    endpoint: str,
    parameters: dict[str, Any],
    retrieved_at: str,
    request_shape: dict[str, Any],
    error: str,
) -> ExternalEvidenceBundle:
    raw = {
        "provider_policy_required": True,
        "request_shape": _safe_request_shape(request_shape),
        "items": [],
    }
    return _bundle(
        query=query,
        provider=provider,
        provider_role=INDEX_PROVIDER_ROLE,
        endpoint=endpoint,
        parameters=parameters,
        status=PROVIDER_EXECUTION_POLICY_REQUIRED_STATUS,
        provider_policy_status=PROVIDER_EXECUTION_POLICY_REQUIRED_STATUS,
        retrieved_at=retrieved_at,
        raw_response=raw,
        items=(),
        error=error,
        request_shape=request_shape,
    )


def _serper_search_request(
    *,
    endpoint: str,
    api_key: str,
    query: str,
    limit: int,
    country: str | None,
    language: str | None,
    location: str | None,
    timeout_seconds: float,
) -> dict[str, Any]:
    return build_external_search_request(
        "serper",
        endpoint=endpoint,
        api_key=api_key,
        api_key_env="SERPER_API_KEY",
        query=query,
        limit=limit,
        country=country,
        language=language,
        location=location,
        timeout_seconds=timeout_seconds,
    )


def _serper_items(raw: dict[str, Any], *, limit: int) -> tuple[ExternalEvidenceItem, ...]:
    return normalize_external_source_candidates("serper", raw, limit=limit)


def _external_item_metadata(row: dict[str, Any]) -> dict[str, Any]:
    metadata = {
        "citation_excluded": True,
        "evidence_status": CANDIDATE_EVIDENCE_STATUS,
        "rank_is_not_evidence": True,
        "snippet_is_not_evidence": True,
    }
    metadata.update({key: row[key] for key in ("date", "position", "sitelinks") if key in row})
    return metadata


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
    request = {
        "provider": budget_provider or "unknown",
        "model": budget_model or "unknown",
        "provider_role": INDEX_PROVIDER_ROLE,
        "operation": EXTERNAL_SEARCH_OPERATION,
        "method": "POST",
        "url": url,
        "payload": payload,
        "params": {},
        "headers": headers,
        "timeout_seconds": timeout_seconds,
    }
    if budget_provider is None and budget_model is None and budget_units is None:
        return _send_provider_request_unbudgeted(request)
    return _send_provider_request(request, units=budget_units or api_units(calls=1))


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
    return _send_provider_request(
        {
            "provider": budget_provider,
            "model": budget_model,
            "provider_role": INDEX_PROVIDER_ROLE,
            "operation": EXTERNAL_SEARCH_OPERATION,
            "method": "POST",
            "url": url,
            "payload": payload,
            "params": {},
            "headers": headers,
            "timeout_seconds": timeout_seconds,
        },
        units=budget_units or api_units(calls=1),
    )


def _send_provider_request(
    request: dict[str, Any],
    *,
    units: dict[str, int | float] | None = None,
) -> dict[str, Any]:
    budget_units = units or request.get("budget_units") or api_units(
        calls=1,
        input_tokens=rough_text_tokens(_request_payload_for_budget(request)),
        documents=_request_document_limit(request),
    )
    with budgeted_api_call(
        provider=str(request.get("provider") or "unknown"),
        model=str(request.get("model") or "unknown"),
        provider_role=INDEX_PROVIDER_ROLE,
        operation=EXTERNAL_SEARCH_OPERATION,
        units=budget_units,
        request_payload=_request_payload_for_budget(request),
        metadata={
            "url": request.get("url"),
            "method": request.get("method", "POST"),
            "source_candidate_only": True,
        },
    ):
        return _send_provider_request_unbudgeted(request)


def _send_provider_request_unbudgeted(request: dict[str, Any]) -> dict[str, Any]:
    url = str(request["url"])
    require_provider_transport_send_allowed(url)
    method = str(request.get("method") or "POST").upper()
    headers = dict(request.get("headers") or {})
    timeout_seconds = float(request.get("timeout_seconds") or 30.0)
    data: bytes | None = None
    if method == "GET":
        params = request.get("params") or {}
        if params:
            separator = "&" if urllib.parse.urlsplit(url).query else "?"
            url = url + separator + urllib.parse.urlencode(params)
    else:
        data = json.dumps(request.get("payload") or {}).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout_seconds) as response:  # noqa: S310
            body = response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"external provider HTTP {exc.code}: {_compact_error(detail)}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"external provider request failed: {exc.reason}") from exc
    try:
        parsed = json.loads(body)
    except json.JSONDecodeError as exc:
        raise RuntimeError("external provider returned non-JSON response") from exc
    if not isinstance(parsed, dict):
        raise RuntimeError("external provider returned unsupported JSON shape")
    return parsed


def _post_json_unbudgeted(
    url: str,
    payload: dict[str, Any],
    *,
    headers: dict[str, str],
    timeout_seconds: float,
) -> dict[str, Any]:
    require_provider_transport_send_allowed(url)
    return _send_provider_request_unbudgeted(
        {
            "method": "POST",
            "url": url,
            "payload": payload,
            "params": {},
            "headers": headers,
            "timeout_seconds": timeout_seconds,
        }
    )


def _provider_result_rows(provider: str, raw: dict[str, Any]) -> list[Any]:
    provider_id = _provider_id(provider)
    if provider_id == "serper":
        return _list_value(raw.get("organic"))
    if provider_id in {"tavily", "exa", "searxng"}:
        return _list_value(raw.get("results"))
    if provider_id == "firecrawl":
        rows = _list_value(raw.get("data"))
        return rows or _list_value(raw.get("results"))
    if provider_id == "perplexity":
        rows = _list_value(raw.get("results"))
        if rows:
            return rows
        citations = _list_value(raw.get("citations"))
        return [{"url": citation} for citation in citations if isinstance(citation, str)]
    return _list_value(raw.get("results"))


def _coerce_raw_row(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        return {"url": value}
    return {"value": value}


def _row_url(row: dict[str, Any]) -> str:
    for key in ("url", "link", "href"):
        value = _optional_text(row.get(key))
        if value:
            return value
    metadata = row.get("metadata")
    if isinstance(metadata, dict):
        for key in ("url", "sourceURL", "ogUrl"):
            value = _optional_text(metadata.get(key))
            if value:
                return value
    return ""


def _row_title(row: dict[str, Any]) -> str:
    for key in ("title", "name"):
        value = _optional_text(row.get(key))
        if value:
            return value
    metadata = row.get("metadata")
    if isinstance(metadata, dict):
        for key in ("title", "ogTitle"):
            value = _optional_text(metadata.get(key))
            if value:
                return value
    return ""


def _row_snippet(row: dict[str, Any], *, content: str | None) -> str:
    for key in ("snippet", "content", "text", "description", "summary", "markdown"):
        value = _optional_text(row.get(key))
        if value:
            return _compact_error(value, limit=700)
    metadata = row.get("metadata")
    if isinstance(metadata, dict):
        for key in ("description", "ogDescription"):
            value = _optional_text(metadata.get(key))
            if value:
                return _compact_error(value, limit=700)
    return _compact_error(content or "", limit=700)


def _row_content(row: dict[str, Any]) -> str | None:
    for key in ("content", "text", "markdown", "snippet", "description", "summary"):
        value = _optional_text(row.get(key))
        if value:
            return value
    return None


def _row_published_at(row: dict[str, Any]) -> str | None:
    for key in ("published_at", "publishedAt", "published_date", "publishedDate", "date"):
        value = _optional_text(row.get(key))
        if value:
            return value
    metadata = row.get("metadata")
    if isinstance(metadata, dict):
        for key in ("published_at", "publishedAt", "published_date", "publishedDate", "date"):
            value = _optional_text(metadata.get(key))
            if value:
                return value
    return None


def _row_score(row: dict[str, Any]) -> float | None:
    value = row.get("score")
    if isinstance(value, int | float):
        return float(value)
    return None


def _request_public_parameters(request: dict[str, Any]) -> dict[str, Any]:
    public = _public_parameters(
        dict(request.get("payload") or request.get("params") or {}),
        api_key_env=str(request.get("api_key_env") or ""),
    )
    public.update(
        {
            "provider": request.get("provider"),
            "method": request.get("method"),
            "model": request.get("model"),
            "api_key_required": request.get("api_key_required"),
            "api_key_used": request.get("api_key_used"),
        }
    )
    return public


def _public_parameters(payload: dict[str, Any], *, api_key_env: str) -> dict[str, Any]:
    public = dict(payload)
    if api_key_env:
        public["api_key_env"] = api_key_env
    return public


def _request_payload_for_budget(request: dict[str, Any]) -> dict[str, Any]:
    if str(request.get("method") or "POST").upper() == "GET":
        return dict(request.get("params") or {})
    return dict(request.get("payload") or {})


def _request_document_limit(request: dict[str, Any]) -> int:
    payload = _request_payload_for_budget(request)
    for key in ("num", "max_results", "numResults", "limit"):
        value = payload.get(key)
        if isinstance(value, int):
            return max(1, value)
    return 1


def _stored_item_metadata(item: ExternalEvidenceItem) -> dict[str, Any]:
    data = dict(item.metadata)
    data.update(
        {
            "provider": item.provider,
            "source_id": item.source_id,
            "run_id": item.run_id,
            "published_at": item.published_at,
            "raw_payload": item.raw_payload,
            "citation_excluded": item.citation_excluded,
            "evidence_status": item.evidence_status,
            "raw_payload_is_not_evidence": True,
        }
    )
    if item.candidate_score is not None:
        data["candidate_score"] = item.candidate_score
    return data


def _items_with_run_info(
    items: tuple[ExternalEvidenceItem, ...],
    *,
    run_id: str,
    provider: str,
) -> tuple[ExternalEvidenceItem, ...]:
    prepared = []
    for item in items:
        source_id = item.source_id or _source_candidate_id(provider, item.url, item.title)
        metadata = {
            **item.metadata,
            "provider": item.provider or provider,
            "source_id": source_id,
            "run_id": run_id,
        }
        prepared.append(
            replace(
                item,
                provider=item.provider or provider,
                source_id=source_id,
                run_id=run_id,
                metadata=metadata,
            )
        )
    return tuple(prepared)


def _safe_request_shape(request: dict[str, Any] | None) -> dict[str, Any] | None:
    if request is None:
        return None
    safe = dict(request)
    headers = dict(safe.get("headers") or {})
    safe["headers"] = {
        key: ("<redacted>" if key.lower() in API_KEY_HEADER_NAMES else value)
        for key, value in headers.items()
    }
    return safe


def _source_candidate_id(provider: str, url: str, title: str) -> str:
    material = _url_identity_without_credentials(url) + "\0" + provider + "\0" + title
    return "external_candidate_" + hashlib.blake2b(material.encode(), digest_size=16).hexdigest()


def _run_id(
    provider: str,
    provider_role: str,
    query: str,
    endpoint: str,
    parameters: dict[str, Any],
    retrieved_at: str,
    raw_hash: str | None,
) -> str:
    material = {
        "provider": provider,
        "provider_role": provider_role,
        "query_length": len(query),
        "endpoint": endpoint,
        "parameters": _public_parameter_fingerprint(parameters),
        "retrieved_at": retrieved_at,
        "raw_hash_present": raw_hash is not None,
        "raw_hash_length": len(raw_hash or ""),
    }
    payload = json.dumps(material, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.blake2b(payload, digest_size=12).hexdigest()


def _item_id(run_id: str, item: ExternalEvidenceItem) -> str:
    safe_url = _url_identity_without_credentials(item.url)
    return hashlib.blake2b(
        f"{run_id}\0{item.position}\0{safe_url}".encode(),
        digest_size=32,
    ).hexdigest()


def _json_hash(value: dict[str, Any]) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    return hashlib.blake2b(payload, digest_size=32).hexdigest()


def _provider_id(provider: str) -> str:
    provider_id = provider.strip().lower().replace("-", "_")
    aliases = {"firecrawl_search": "firecrawl", "searxng_local": "searxng"}
    provider_id = aliases.get(provider_id, provider_id)
    if provider_id not in PROVIDER_ENDPOINTS:
        raise ValueError(f"unknown external evidence provider: {provider}")
    return provider_id


def _resolved_api_key_env(provider: str, requested: str | None) -> str | None:
    default = PROVIDER_API_KEY_ENVS[_provider_id(provider)]
    if requested and requested != "SERPER_API_KEY":
        return requested
    if requested == "SERPER_API_KEY" and provider == "serper":
        return requested
    return default


def _active_provider_policy_present() -> bool:
    context = active_api_budget_context()
    return context is not None and context.provider_execution_policy is not None


def _is_provider_policy_error(exc: RuntimeError) -> bool:
    text = str(exc)
    return (
        PROVIDER_EXECUTION_POLICY_REQUIRED_STATUS in text
        or "ProviderExecutionPolicy" in text
        or "provider execution policy" in text.lower()
    )


def _list_value(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _optional_text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    return text


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", value).strip("-").lower()
    return slug or "query"


def _public_parameter_fingerprint(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float)):
        return {"type": type(value).__name__}
    if isinstance(value, str):
        return {"type": "str", "length": len(value)}
    if isinstance(value, dict):
        return {
            "type": "dict",
            "length": len(value),
            "items": _public_parameter_fingerprint_dict_items(value),
        }
    if isinstance(value, (list, tuple, set)):
        items = list(value)
        return {
            "type": type(value).__name__,
            "length": len(items),
            "items": [_public_parameter_fingerprint(item) for item in items[:20]],
        }
    return {"type": type(value).__name__, "repr_length": len(str(value))}


def _public_parameter_fingerprint_dict_items(value: dict[Any, Any]) -> list[dict[str, Any]]:
    items = [
        {
            "key": {"type": type(key).__name__, "length": len(str(key))},
            "value": _public_parameter_fingerprint(item),
        }
        for key, item in value.items()
    ]
    return sorted(
        items,
        key=lambda item: json.dumps(item, ensure_ascii=False, sort_keys=True, default=str),
    )


def _url_identity_without_credentials(url: str) -> str:
    parsed = urllib.parse.urlsplit(url)
    hostname = (parsed.hostname or "").lower()
    port = f":{parsed.port}" if parsed.port is not None else ""
    netloc = f"{hostname}{port}"
    return urllib.parse.urlunsplit((parsed.scheme.lower(), netloc, parsed.path, "", ""))


def _domain(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    return parsed.netloc.lower()


def _compact_error(value: str, *, limit: int = 500) -> str:
    text = " ".join(value.split())
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 3)].rstrip() + "..."
