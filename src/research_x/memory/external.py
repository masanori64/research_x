from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from research_x.memory.api_budget import api_units, budgeted_api_call, rough_text_tokens
from research_x.memory.schema import ensure_memory_schema

INDEX_PROVIDER_ROLE = "index_provider"
DEFAULT_RETENTION_POLICY = "normalized_results_only"
SERPER_ENDPOINT = "https://google.serper.dev/search"


@dataclass(frozen=True)
class ExternalEvidenceItem:
    position: int
    title: str
    url: str
    snippet: str
    source: str
    metadata: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {
            "position": self.position,
            "title": self.title,
            "url": self.url,
            "snippet": self.snippet,
            "source": self.source,
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

    def as_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "query": self.query,
            "provider": self.provider,
            "provider_role": self.provider_role,
            "endpoint": self.endpoint,
            "parameters": self.parameters,
            "status": self.status,
            "retrieved_at": self.retrieved_at,
            "raw_response_hash": self.raw_response_hash,
            "retention_policy": self.retention_policy,
            "items": [item.as_dict() for item in self.items],
            "error": self.error,
        }


class ExternalSearchProvider(Protocol):
    provider_id: str
    provider_role: str

    def search(self, query: str, *, limit: int) -> ExternalEvidenceBundle:
        """Return URL discovery results. The bundle is not citation-ready evidence."""


class FakeExternalSearchProvider:
    provider_id = "fake"
    provider_role = INDEX_PROVIDER_ROLE
    endpoint = "memory://fake-external-search"

    def search(self, query: str, *, limit: int) -> ExternalEvidenceBundle:
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
                    "Use this provider to test external evidence wiring."
                ),
                source="example.invalid",
                metadata={"fixture": True},
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


class SerperSearchProvider:
    provider_id = "serper"
    provider_role = INDEX_PROVIDER_ROLE

    def __init__(
        self,
        *,
        api_key_env: str = "SERPER_API_KEY",
        endpoint: str = SERPER_ENDPOINT,
        timeout_seconds: float = 30.0,
        country: str | None = None,
        language: str | None = None,
        location: str | None = None,
    ) -> None:
        self.api_key_env = api_key_env
        self.endpoint = endpoint
        self.timeout_seconds = timeout_seconds
        self.country = country
        self.language = language
        self.location = location

    def search(self, query: str, *, limit: int) -> ExternalEvidenceBundle:
        api_key = os.environ.get(self.api_key_env)
        if not api_key:
            raise RuntimeError(f"{self.api_key_env} is not set")
        resolved_limit = max(1, limit)
        payload: dict[str, Any] = {"q": query, "num": resolved_limit}
        if self.country:
            payload["gl"] = self.country
        if self.language:
            payload["hl"] = self.language
        if self.location:
            payload["location"] = self.location

        retrieved_at = _utc_now()
        raw = _post_json_budgeted(
            self.endpoint,
            payload,
            headers={"X-API-KEY": api_key, "Content-Type": "application/json"},
            timeout_seconds=self.timeout_seconds,
            budget_provider=self.provider_id,
            budget_model="serper-search",
            budget_units=api_units(
                calls=1,
                input_tokens=rough_text_tokens(payload),
                documents=resolved_limit,
            ),
        )
        items = _serper_items(raw, limit=resolved_limit)
        return _bundle(
            query=query,
            provider=self.provider_id,
            provider_role=self.provider_role,
            endpoint=self.endpoint,
            parameters=_public_parameters(payload, api_key_env=self.api_key_env),
            status="ok",
            retrieved_at=retrieved_at,
            raw_response=raw,
            items=items,
        )


def search_external_evidence(
    db_path: str | Path,
    query: str,
    *,
    provider: str = "fake",
    limit: int = 5,
    api_key_env: str = "SERPER_API_KEY",
    endpoint: str | None = None,
    country: str | None = None,
    language: str | None = None,
    location: str | None = None,
    timeout_seconds: float = 30.0,
    store: bool = True,
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
    bundle = provider_impl.search(query, limit=limit)
    if store:
        store_external_evidence_bundle(db_path, bundle)
    return bundle


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
                    json.dumps(item.metadata, ensure_ascii=False, sort_keys=True),
                ),
            )


def external_evidence_json(bundle: ExternalEvidenceBundle) -> str:
    return json.dumps(bundle.as_dict(), ensure_ascii=False, indent=2, sort_keys=True)


def _provider(
    provider: str,
    *,
    api_key_env: str,
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
) -> ExternalEvidenceBundle:
    raw_hash = _json_hash(raw_response)
    run_id = _run_id(provider, provider_role, query, endpoint, parameters, retrieved_at, raw_hash)
    return ExternalEvidenceBundle(
        run_id=run_id,
        query=query,
        provider=provider,
        provider_role=provider_role,
        endpoint=endpoint,
        parameters=parameters,
        status=status,
        retrieved_at=retrieved_at,
        raw_response_hash=raw_hash,
        retention_policy=DEFAULT_RETENTION_POLICY,
        items=items,
    )


def _serper_items(raw: dict[str, Any], *, limit: int) -> tuple[ExternalEvidenceItem, ...]:
    organic = raw.get("organic")
    if not isinstance(organic, list):
        return ()
    items: list[ExternalEvidenceItem] = []
    for index, row in enumerate(organic[:limit], start=1):
        if not isinstance(row, dict):
            continue
        url = str(row.get("link") or row.get("url") or "").strip()
        if not url:
            continue
        items.append(
            ExternalEvidenceItem(
                position=index,
                title=str(row.get("title") or ""),
                url=url,
                snippet=str(row.get("snippet") or ""),
                source=str(row.get("source") or _domain(url)),
                metadata={
                    key: row[key]
                    for key in ("date", "position", "sitelinks")
                    if key in row
                },
            )
        )
    return tuple(items)


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
        provider_role=INDEX_PROVIDER_ROLE,
        operation="external_search",
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
        provider_role=INDEX_PROVIDER_ROLE,
        operation="external_search",
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


def _public_parameters(payload: dict[str, Any], *, api_key_env: str) -> dict[str, Any]:
    public = dict(payload)
    public["api_key_env"] = api_key_env
    return public


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
        "query": query,
        "endpoint": endpoint,
        "parameters": parameters,
        "retrieved_at": retrieved_at,
        "raw_hash": raw_hash,
    }
    return hashlib.sha256(
        json.dumps(material, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()[:24]


def _item_id(run_id: str, item: ExternalEvidenceItem) -> str:
    return hashlib.sha256(f"{run_id}\0{item.position}\0{item.url}".encode()).hexdigest()


def _json_hash(value: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", value).strip("-").lower()
    return slug or "query"


def _domain(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    return parsed.netloc.lower()


def _compact_error(value: str, *, limit: int = 500) -> str:
    text = " ".join(value.split())
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 3)].rstrip() + "..."
