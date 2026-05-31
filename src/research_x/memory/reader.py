from __future__ import annotations

import hashlib
import html
import json
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

from research_x.memory.schema import ensure_memory_schema

FETCH_AGENT_ROLE = "fetch_agent"
READER_EXTRACTOR_VERSION = "reader-extract-v1"
DEFAULT_USER_AGENT = "research-x/0.1"


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
            metadata={"fixture": True},
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
    chunk = _context_chunk(
        tool_call_id=tool_call_id,
        provider=provider_impl.provider_id,
        provider_role=provider_impl.provider_role,
        page=page,
        run_id=run_id,
        query=query,
        metadata=metadata or {},
    )
    citation = _citation_annotation(
        tool_call_id=tool_call_id,
        chunk=chunk,
        page=page,
        metadata=metadata or {},
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
            metadata=metadata or {},
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
) -> dict[str, Any]:
    source_id = _hash_id("external-web", page.url)[:24]
    chunk_text = _reader_chunk_text(page=page, query=query)
    chunk_id = _hash_id("external-chunk", tool_call_id, page.url, _text_hash(chunk_text))
    return {
        "chunk_id": chunk_id,
        "run_id": run_id,
        "source_kind": "external_web",
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
            "page_metadata": page.metadata,
            **metadata,
        },
    }


def _citation_annotation(
    *,
    tool_call_id: str,
    chunk: dict[str, Any],
    page: ReaderPage,
    metadata: dict[str, Any],
) -> dict[str, Any]:
    citation_id = _hash_id("external-citation", tool_call_id, chunk["chunk_id"], page.url)
    return {
        "citation_id": citation_id,
        "answer_id": None,
        "chunk_id": chunk["chunk_id"],
        "source_kind": "external_web",
        "source_id": chunk["source_id"],
        "source_url": page.url,
        "title": page.title,
        "field_path": "context_chunks[external]",
        "support_type": "background",
        "evidence_status": "unconfirmed",
        "confidence": 0.7,
        "created_at": page.retrieved_at,
        "metadata": {
            "provider_role": chunk["provider_role"],
            "tool_call_id": tool_call_id,
            **metadata,
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
    raise ValueError(f"unknown reader provider: {provider}")


def _read_url(
    url: str,
    *,
    timeout_seconds: float,
    user_agent: str,
    max_bytes: int,
) -> HttpResponse:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError(f"unsupported URL scheme for reader provider: {parsed.scheme}")
    request = urllib.request.Request(url, headers={"User-Agent": user_agent})
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


def _compact_error(value: str, *, limit: int = 500) -> str:
    text = " ".join(value.split())
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 3)].rstrip() + "..."
