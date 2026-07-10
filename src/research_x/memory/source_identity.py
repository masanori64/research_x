from __future__ import annotations

from research_x.memory.document_hashes import text_hash


def source_bundle_id(doc_id: str, source_doc_hash: str) -> str:
    """Stable identity for the legacy citation-ready source bundle."""

    return text_hash("|".join(("source-bundle", str(doc_id), str(source_doc_hash))))[:24]


def source_restore_id(doc_id: str, source_doc_hash: str) -> str:
    """Canonical identity for a restored source view."""

    return text_hash("|".join(("source-restore", str(doc_id), str(source_doc_hash))))[:24]


def source_lineage_ids(doc_id: str, source_doc_hash: str) -> dict[str, str]:
    """Return both supported names for one restored source lineage.

    ``source_bundle_id`` is the evidence-first contract name and
    ``source_restore_id`` is the KnowledgeOps contract name.  They are distinct
    deterministic identifiers for the same ``doc_id``/source-hash pair, so new
    records emit both while readers may accept either compatible identifier.
    """

    return {
        "source_bundle_id": source_bundle_id(doc_id, source_doc_hash),
        "source_restore_id": source_restore_id(doc_id, source_doc_hash),
    }
