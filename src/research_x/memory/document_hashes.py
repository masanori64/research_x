from __future__ import annotations

import hashlib
import json
from typing import Any


def memory_document_source_hash(row: Any) -> str:
    payload = {
        "doc_id": _get(row, "doc_id"),
        "title": _get(row, "title"),
        "compact_text": _get(row, "compact_text"),
        "body": _get(row, "body"),
        "metadata_json": _get(row, "metadata_json"),
    }
    return text_hash(json.dumps(payload, ensure_ascii=False, sort_keys=True))


def memory_document_embedding_text(row: Any) -> str:
    metadata = _compact_metadata(_get(row, "metadata_json"))
    compact_text = _get(row, "compact_text") or ""
    body = _get(row, "body") or ""
    body_extra = body[:1200] if compact_text not in body else ""
    text = "\n".join(
        part
        for part in (
            _get(row, "title") or "",
            compact_text,
            body_extra,
            metadata,
        )
        if part
    )
    return text[:2400]


def memory_document_embedding_text_hash(row: Any) -> str:
    return text_hash(memory_document_embedding_text(row))


def text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _get(row: Any, key: str) -> Any:
    if isinstance(row, dict):
        return row.get(key)
    return row[key]


def _compact_metadata(value: str | None) -> str:
    if not value:
        return ""
    try:
        metadata = json.loads(value)
    except json.JSONDecodeError:
        return ""
    if not isinstance(metadata, dict):
        return ""
    useful = {
        key: metadata.get(key)
        for key in ("url", "role", "collection_kind", "labels", "type", "download_status")
        if metadata.get(key)
    }
    return f"metadata: {json.dumps(useful, ensure_ascii=False, sort_keys=True)}" if useful else ""
