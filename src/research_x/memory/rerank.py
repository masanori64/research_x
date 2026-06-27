from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from research_x.memory.api_budget import api_units, budgeted_api_call, rough_text_tokens
from research_x.memory.evidence import build_evidence_bundle
from research_x.memory.schema import ensure_memory_schema

RERANK_PROVIDER_ROLE = "reranker"
FAKE_RERANK_PROVIDER = "fake"
VOYAGE_RERANK_PROVIDER = "voyage"
COHERE_RERANK_PROVIDER = "cohere"
JINA_RERANK_PROVIDER = "jina"
RERANK_PROVIDER_CHOICES = (
    FAKE_RERANK_PROVIDER,
    VOYAGE_RERANK_PROVIDER,
    COHERE_RERANK_PROVIDER,
    JINA_RERANK_PROVIDER,
)
DEFAULT_RERANK_MODELS = {
    FAKE_RERANK_PROVIDER: "fake-rerank-v1",
    VOYAGE_RERANK_PROVIDER: "rerank-2.5",
    COHERE_RERANK_PROVIDER: "rerank-v4.0-pro",
    JINA_RERANK_PROVIDER: "jina-reranker-v3",
}


@dataclass(frozen=True)
class RerankInputDocument:
    index: int
    doc_id: str
    bundle_key: str
    text: str
    metadata: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RerankResult:
    rank: int
    index: int
    doc_id: str
    bundle_key: str
    score: float
    provider: str
    model: str
    metadata: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RerankReport:
    query: str
    provider: str
    model: str
    provider_role: str
    input_hash: str
    candidate_count: int
    top_n: int
    results: tuple[RerankResult, ...]
    tool_call_id: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "query": self.query,
            "provider": self.provider,
            "model": self.model,
            "provider_role": self.provider_role,
            "input_hash": self.input_hash,
            "candidate_count": self.candidate_count,
            "top_n": self.top_n,
            "tool_call_id": self.tool_call_id,
            "results": [result.as_dict() for result in self.results],
        }


class RerankProvider(Protocol):
    provider_id: str

    def rerank(
        self,
        query: str,
        documents: tuple[RerankInputDocument, ...],
        *,
        top_n: int,
    ) -> tuple[RerankResult, ...]:
        """Rank restored evidence-bundle candidates for a query."""


class FakeRerankProvider:
    provider_id = FAKE_RERANK_PROVIDER

    def __init__(self, model: str) -> None:
        self.model = model

    def rerank(
        self,
        query: str,
        documents: tuple[RerankInputDocument, ...],
        *,
        top_n: int,
    ) -> tuple[RerankResult, ...]:
        query_terms = _terms(query)
        scored = []
        for document in documents:
            doc_terms = _terms(document.text)
            overlap = len(query_terms.intersection(doc_terms))
            score = float(overlap) + (1.0 / (document.index + 1))
            scored.append((score, document))
        scored.sort(key=lambda item: (item[0], -item[1].index), reverse=True)
        return tuple(
            RerankResult(
                rank=rank,
                index=document.index,
                doc_id=document.doc_id,
                bundle_key=document.bundle_key,
                score=score,
                provider=self.provider_id,
                model=self.model,
                metadata={"fixture": True},
            )
            for rank, (score, document) in enumerate(scored[: max(1, top_n)], start=1)
        )


class VoyageRerankProvider:
    provider_id = VOYAGE_RERANK_PROVIDER

    def __init__(
        self,
        *,
        model: str,
        api_key_env: str | None = None,
        base_url: str | None = None,
        timeout_seconds: float = 60.0,
    ) -> None:
        self.model = model
        self.api_key = _api_key(api_key_env or "VOYAGE_API_KEY")
        self.base_url = base_url or "https://api.voyageai.com/v1/rerank"
        self.timeout_seconds = timeout_seconds

    def rerank(
        self,
        query: str,
        documents: tuple[RerankInputDocument, ...],
        *,
        top_n: int,
    ) -> tuple[RerankResult, ...]:
        request = _rerank_provider_request(
            provider=self.provider_id,
            base_url=self.base_url,
            api_key=self.api_key,
            model=self.model,
            query=query,
            documents=documents,
            top_n=top_n,
            timeout_seconds=self.timeout_seconds,
        )
        response = _post_json_budgeted(
            request["url"],
            request["payload"],
            headers=request["headers"],
            timeout_seconds=request["timeout_seconds"],
            budget_provider=self.provider_id,
            budget_model=self.model,
            budget_units=_rerank_api_units(query, documents, retries=3),
        )
        return _results_from_response(
            response.get("data") or response.get("results"),
            documents=documents,
            provider=self.provider_id,
            model=self.model,
            score_keys=("relevance_score", "score"),
        )


class CohereRerankProvider:
    provider_id = COHERE_RERANK_PROVIDER

    def __init__(
        self,
        *,
        model: str,
        api_key_env: str | None = None,
        base_url: str | None = None,
        timeout_seconds: float = 60.0,
    ) -> None:
        self.model = model
        self.api_key = _api_key(api_key_env or "COHERE_API_KEY")
        self.base_url = base_url or "https://api.cohere.com/v2/rerank"
        self.timeout_seconds = timeout_seconds

    def rerank(
        self,
        query: str,
        documents: tuple[RerankInputDocument, ...],
        *,
        top_n: int,
    ) -> tuple[RerankResult, ...]:
        request = _rerank_provider_request(
            provider=self.provider_id,
            base_url=self.base_url,
            api_key=self.api_key,
            model=self.model,
            query=query,
            documents=documents,
            top_n=top_n,
            timeout_seconds=self.timeout_seconds,
        )
        response = _post_json_budgeted(
            request["url"],
            request["payload"],
            headers=request["headers"],
            timeout_seconds=request["timeout_seconds"],
            budget_provider=self.provider_id,
            budget_model=self.model,
            budget_units=_rerank_api_units(query, documents, retries=3),
        )
        return _results_from_response(
            response.get("results"),
            documents=documents,
            provider=self.provider_id,
            model=self.model,
            score_keys=("relevance_score", "score"),
        )


class JinaRerankProvider:
    provider_id = JINA_RERANK_PROVIDER

    def __init__(
        self,
        *,
        model: str,
        api_key_env: str | None = None,
        base_url: str | None = None,
        timeout_seconds: float = 60.0,
    ) -> None:
        self.model = model
        self.api_key = _api_key(api_key_env or "JINA_API_KEY")
        self.base_url = base_url or "https://api.jina.ai/v1/rerank"
        self.timeout_seconds = timeout_seconds

    def rerank(
        self,
        query: str,
        documents: tuple[RerankInputDocument, ...],
        *,
        top_n: int,
    ) -> tuple[RerankResult, ...]:
        request = _rerank_provider_request(
            provider=self.provider_id,
            base_url=self.base_url,
            api_key=self.api_key,
            model=self.model,
            query=query,
            documents=documents,
            top_n=top_n,
            timeout_seconds=self.timeout_seconds,
        )
        response = _post_json_budgeted(
            request["url"],
            request["payload"],
            headers=request["headers"],
            timeout_seconds=request["timeout_seconds"],
            budget_provider=self.provider_id,
            budget_model=self.model,
            budget_units=_rerank_api_units(query, documents, retries=3),
        )
        return _results_from_response(
            response.get("results"),
            documents=documents,
            provider=self.provider_id,
            model=self.model,
            score_keys=("relevance_score", "score"),
        )


def _rerank_provider_request(
    *,
    provider: str,
    base_url: str,
    api_key: str,
    model: str,
    query: str,
    documents: tuple[RerankInputDocument, ...],
    top_n: int,
    timeout_seconds: float,
) -> dict[str, Any]:
    provider_id = _resolve_provider(provider)
    if provider_id == VOYAGE_RERANK_PROVIDER:
        payload: dict[str, Any] = {
            "model": model,
            "query": query,
            "documents": [document.text for document in documents],
            "top_k": max(1, top_n),
            "truncation": True,
        }
    elif provider_id == COHERE_RERANK_PROVIDER:
        payload = {
            "model": model,
            "query": query,
            "documents": [document.text for document in documents],
            "top_n": max(1, top_n),
        }
    elif provider_id == JINA_RERANK_PROVIDER:
        payload = {
            "model": model,
            "query": query,
            "documents": [{"text": document.text} for document in documents],
            "top_n": max(1, top_n),
        }
    else:
        raise ValueError(f"provider has no remote rerank request shape: {provider}")
    return {
        "url": base_url,
        "payload": payload,
        "headers": {"Authorization": f"Bearer {api_key}"},
        "timeout_seconds": timeout_seconds,
        "request_shape_only": True,
        "provider_quality_proof": False,
    }


def rerank_evidence_query(
    db_path: str | Path,
    query: str,
    *,
    provider: str = FAKE_RERANK_PROVIDER,
    model: str | None = None,
    limit: int = 20,
    top_n: int = 5,
    api_key_env: str | None = None,
    base_url: str | None = None,
    timeout_seconds: float = 60.0,
    store: bool = False,
) -> RerankReport:
    bundle = build_evidence_bundle(db_path, query, limit=max(1, limit))
    report = rerank_hits(
        query,
        list(bundle["hits"]),
        provider=provider,
        model=model,
        top_n=top_n,
        api_key_env=api_key_env,
        base_url=base_url,
        timeout_seconds=timeout_seconds,
    )
    if store:
        report = store_rerank_report(db_path, report)
    return report


def rerank_hits(
    query: str,
    hits: list[dict[str, Any]],
    *,
    provider: str = FAKE_RERANK_PROVIDER,
    model: str | None = None,
    top_n: int = 5,
    api_key_env: str | None = None,
    base_url: str | None = None,
    timeout_seconds: float = 60.0,
) -> RerankReport:
    documents = tuple(_document_from_hit(index, hit) for index, hit in enumerate(hits))
    resolved_provider = _resolve_provider(provider)
    resolved_model = model or DEFAULT_RERANK_MODELS[resolved_provider]
    input_hash = _input_hash(query, documents, provider=resolved_provider, model=resolved_model)
    provider_impl = _provider(
        resolved_provider,
        model=resolved_model,
        api_key_env=api_key_env,
        base_url=base_url,
        timeout_seconds=timeout_seconds,
    )
    results = provider_impl.rerank(query, documents, top_n=max(1, top_n))
    return RerankReport(
        query=query,
        provider=resolved_provider,
        model=resolved_model,
        provider_role=RERANK_PROVIDER_ROLE,
        input_hash=input_hash,
        candidate_count=len(documents),
        top_n=max(1, top_n),
        results=tuple(results),
    )


def store_rerank_report(db_path: str | Path, report: RerankReport) -> RerankReport:
    now = _utc_now()
    tool_call_id = _hash_id(
        "rerank-tool-call",
        report.provider,
        report.model,
        report.input_hash,
        now,
    )[:24]
    path = Path(db_path)
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
                tool_call_id,
                None,
                report.provider,
                report.provider_role,
                "rerank",
                json.dumps(
                    {
                        "query": report.query,
                        "model": report.model,
                        "input_hash": report.input_hash,
                        "candidate_count": report.candidate_count,
                        "top_n": report.top_n,
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                ),
                json.dumps(
                    {
                        "results": [result.as_dict() for result in report.results],
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                ),
                "ok",
                None,
                now,
                now,
            ),
        )
    return RerankReport(
        query=report.query,
        provider=report.provider,
        model=report.model,
        provider_role=report.provider_role,
        input_hash=report.input_hash,
        candidate_count=report.candidate_count,
        top_n=report.top_n,
        results=report.results,
        tool_call_id=tool_call_id,
    )


def rerank_report_json(report: RerankReport) -> str:
    return json.dumps(report.as_dict(), ensure_ascii=False, indent=2, sort_keys=True)


def format_rerank_report(report: RerankReport) -> str:
    lines = [
        "rerank: "
        f"provider={report.provider} model={report.model} "
        f"candidates={report.candidate_count} top_n={report.top_n}",
        f"input_hash: {report.input_hash}",
    ]
    if report.tool_call_id:
        lines.append(f"tool_call_id: {report.tool_call_id}")
    for result in report.results:
        lines.append(
            f"{result.rank}. score={result.score:.6f} "
            f"doc={result.doc_id} bundle={result.bundle_key}"
        )
    return "\n".join(lines)


def _provider(
    provider: str,
    *,
    model: str,
    api_key_env: str | None,
    base_url: str | None,
    timeout_seconds: float,
) -> RerankProvider:
    if provider == FAKE_RERANK_PROVIDER:
        return FakeRerankProvider(model)
    if provider == VOYAGE_RERANK_PROVIDER:
        return VoyageRerankProvider(
            model=model,
            api_key_env=api_key_env,
            base_url=base_url,
            timeout_seconds=timeout_seconds,
        )
    if provider == COHERE_RERANK_PROVIDER:
        return CohereRerankProvider(
            model=model,
            api_key_env=api_key_env,
            base_url=base_url,
            timeout_seconds=timeout_seconds,
        )
    if provider == JINA_RERANK_PROVIDER:
        return JinaRerankProvider(
            model=model,
            api_key_env=api_key_env,
            base_url=base_url,
            timeout_seconds=timeout_seconds,
        )
    raise ValueError(f"unknown rerank provider: {provider}")


def _document_from_hit(index: int, hit: dict[str, Any]) -> RerankInputDocument:
    doc_id = str(hit.get("doc_id") or "")
    bundle_key = _bundle_key(hit)
    evidence = hit.get("evidence") if isinstance(hit.get("evidence"), dict) else {}
    metadata = hit.get("metadata") if isinstance(hit.get("metadata"), dict) else {}
    text_parts = [
        f"Title: {hit.get('title') or ''}",
        f"Type: {hit.get('doc_type') or ''}",
        f"Text: {hit.get('compact_text') or ''}",
        f"Author: {evidence.get('author') or metadata.get('author_screen_name') or ''}",
        f"URL: {evidence.get('url') or metadata.get('url') or ''}",
    ]
    quoted = evidence.get("quoted_tweets")
    if isinstance(quoted, list) and quoted:
        text_parts.append("Quoted: " + " ".join(str(item.get("text") or "") for item in quoted))
    media = evidence.get("media")
    if isinstance(media, list) and media:
        text_parts.append(
            "Media: "
            + " ".join(
                str(item.get("alt_text") or item.get("url") or item.get("local_path") or "")
                for item in media
            )
        )
    return RerankInputDocument(
        index=index,
        doc_id=doc_id,
        bundle_key=bundle_key,
        text="\n".join(text_parts),
        metadata={
            "doc_type": hit.get("doc_type"),
            "tweet_id": hit.get("tweet_id"),
            "score": hit.get("score"),
            "match_method": metadata.get("retrieval_method"),
        },
    )


def _results_from_response(
    value: Any,
    *,
    documents: tuple[RerankInputDocument, ...],
    provider: str,
    model: str,
    score_keys: tuple[str, ...],
) -> tuple[RerankResult, ...]:
    if not isinstance(value, list):
        raise RuntimeError(f"{provider} rerank response missing results: {value}")
    by_index = {document.index: document for document in documents}
    results = []
    for rank, item in enumerate(value, start=1):
        if not isinstance(item, dict):
            raise RuntimeError(f"{provider} rerank result is not an object: {item}")
        result_index = _int_value(item.get("index"))
        document = by_index.get(result_index)
        if document is None:
            raise RuntimeError(f"{provider} rerank result index out of range: {item}")
        results.append(
            RerankResult(
                rank=rank,
                index=document.index,
                doc_id=document.doc_id,
                bundle_key=document.bundle_key,
                score=_score_value(item, score_keys),
                provider=provider,
                model=model,
                metadata={
                    key: value
                    for key, value in item.items()
                    if key not in {"index", *score_keys, "document"}
                },
            )
        )
    return tuple(results)


def _score_value(item: dict[str, Any], keys: tuple[str, ...]) -> float:
    for key in keys:
        if key in item:
            return float(item[key])
    return 0.0


def _int_value(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise RuntimeError(f"rerank result missing integer index: {value}") from exc


def _resolve_provider(value: str) -> str:
    provider = value.strip().lower().replace("-", "_")
    if provider not in RERANK_PROVIDER_CHOICES:
        raise ValueError(f"unknown rerank provider: {value}")
    return provider


def _api_key(env_name: str) -> str:
    value = os.environ.get(env_name)
    if not value:
        raise RuntimeError(f"missing API key environment variable: {env_name}")
    return value


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
        provider_role=RERANK_PROVIDER_ROLE,
        operation="rerank",
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
        provider_role=RERANK_PROVIDER_ROLE,
        operation="rerank",
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
            with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            if exc.code not in {429, 500, 502, 503, 504} or attempt == retries:
                raise RuntimeError(f"rerank API HTTP {exc.code}: {_compact_error(detail)}") from exc
            last_error = exc
        except TimeoutError as exc:
            if attempt == retries:
                raise RuntimeError("rerank API timed out") from exc
            last_error = exc
        time.sleep(_retry_sleep_seconds(last_error, attempt=attempt))
    raise RuntimeError(f"rerank API failed: {last_error}")


def _rerank_api_units(
    query: str,
    documents: tuple[RerankInputDocument, ...],
    *,
    retries: int,
) -> dict[str, int | float]:
    processed_tokens = rough_text_tokens(query) * len(documents) + sum(
        rough_text_tokens(document.text) for document in documents
    )
    return api_units(
        calls=retries,
        retries=max(0, retries - 1),
        input_tokens=processed_tokens,
        documents=len(documents),
    )


def _retry_sleep_seconds(error: Exception | None, *, attempt: int) -> float:
    if isinstance(error, urllib.error.HTTPError):
        retry_after = error.headers.get("Retry-After") if error.headers else None
        if retry_after:
            try:
                return max(0.0, min(float(retry_after), 300.0))
            except ValueError:
                pass
    return float(min(2**attempt, 30))


def _input_hash(
    query: str,
    documents: tuple[RerankInputDocument, ...],
    *,
    provider: str,
    model: str,
) -> str:
    payload = {
        "query": query,
        "provider": provider,
        "model": model,
        "documents": [
            {
                "index": document.index,
                "doc_id": document.doc_id,
                "bundle_key": document.bundle_key,
                "text_hash": _text_hash(document.text),
            }
            for document in documents
        ],
    }
    return _text_hash(json.dumps(payload, ensure_ascii=False, sort_keys=True))


def _bundle_key(hit: dict[str, Any]) -> str:
    tweet_id = hit.get("tweet_id")
    if tweet_id:
        return f"tweet:{tweet_id}"
    evidence = hit.get("evidence") if isinstance(hit.get("evidence"), dict) else {}
    url = evidence.get("url")
    if url:
        return f"url:{url}"
    return f"doc:{hit.get('doc_id') or ''}"


def _terms(value: str) -> set[str]:
    return {term.casefold() for term in re.findall(r"[\w一-龯ぁ-んァ-ヶー]+", value)}


def _text_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _hash_id(*parts: object) -> str:
    return hashlib.sha1("|".join(str(part) for part in parts).encode("utf-8")).hexdigest()


def _compact_error(value: str, *, limit: int = 500) -> str:
    text = " ".join(value.split())
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 3)].rstrip() + "..."


def _utc_now() -> str:
    return datetime.now(tz=UTC).isoformat()
