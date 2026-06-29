from __future__ import annotations

from research_x.memory.document_hashes import text_hash


def source_bundle_id(doc_id: str, source_doc_hash: str) -> str:
    """Canonical identity for a restored source bundle."""

    return text_hash("|".join(("source-bundle", str(doc_id), str(source_doc_hash))))[:24]
