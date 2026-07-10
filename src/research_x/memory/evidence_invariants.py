from __future__ import annotations

from collections import Counter
from typing import Any

from research_x.memory.artifact_roles import artifact_role_allows_answer_support
from research_x.memory.authority_levels import AuthorityLevel, authority_at_least
from research_x.memory.context import CitationAnnotation, ContextChunk
from research_x.memory.output_modes import OutputMode, normalize_output_mode

CONFLICT_MARKERS = {
    "conflict",
    "conflicting",
    "conflicting_evidence",
    "contradict",
    "contradicts",
    "contradiction",
    "opposes",
}

STALE_MARKERS = {
    "old",
    "obsolete",
    "outdated",
    "stale",
    "stale_only",
    "stale-only",
}

LEGACY_METADATA_COMPAT_NON_EVIDENCE_MARKERS = {
    "answer_support_blocked",
    "answer_support_disallowed",
    "answer_support_not_allowed",
    "candidate",
    "candidate_only",
    "citation_excluded",
    "citation_excluded_role",
    "citation_not_allowed",
    "control_artifact",
    "control_artifact_view",
    "control_plane",
    "derived_signal",
    "diagnostic_only",
    "diagnosis_only",
    "fetch_extract_hash_context_chunk_required",
    "generated_artifact",
    "navigation_hint",
    "not_answer_support",
    "not_citation",
    "not_evidence",
    "not_evidence_until_fetched_and_chunked",
    "offload_pointer",
    "operation_trace",
    "pointer",
    "pointer_only",
    "preview",
    "preview_only",
    "projection",
    "projection_only",
    "ranking_hint",
    "restore_hint",
    "review_artifact",
    "search_result",
    "search_result_only",
    "snippet",
    "snippet_only",
    "synthetic",
    "unsupported",
    "working_note",
    "workflow_hint",
    "score_is_not_evidence",
    "ranking_hint_not_evidence",
    "workflow_hint_not_evidence",
    "brief_is_not_evidence",
    "context_offload",
    "media_source_only_until_content_chunk",
}

NON_READY_SUPPORT_TYPES = {
    "uncited_context",
    "contradicts",
    "does_not_support",
    "unsupported",
    "search_result",
    "preview",
    "ranking_hint",
    "supports_search_helper",
}

NON_EVIDENCE_METADATA_KEYS = (
    "not_evidence",
    "citation_excluded",
    "artifact_role",
    "owner_plane",
    "evidence_role",
    "evidence_status",
    "citation_policy",
    "support_policy",
    "answer_support_policy",
    "authority_role",
    "authority_level",
    "content_role",
    "output_mode",
    "output_role",
)

LEGACY_METADATA_COMPAT_KEYS = (
    "artifact_kind",
    "artifact_type",
    "field_kind",
    "preview_kind",
    "restore_hint_kind",
    "source_kind",
    "source_role",
    "summary_kind",
)

STALE_METADATA_KEYS = (
    "answerability",
    "answerability_status",
    "evidence_status",
    "freshness",
    "freshness_status",
    "source_hash_status",
    "source_doc_hash_status",
    "lineage_variant_warning",
    "retrieval_text_status",
    "retrieval_text_freshness",
    "pointer_status",
    "restore_hint_status",
    "summary_status",
    "preview_status",
    "context_offload_pointer_status",
    "stale",
    "stale_only",
    "stale_pointer",
    "stale_restore_hint",
)

CONFLICT_METADATA_KEYS = (
    "answerability",
    "answerability_status",
    "answerability_fixture",
    "evidence_relation",
    "relation",
    "relation_type",
    "source_doc_hash_status",
    "lineage_variant_warning",
    "support_type",
)

PROVENANCE_METADATA_KEYS = (
    "provenance_sources",
    "lineage_variants",
    "duplicate_sources",
    "bookmark_accounts",
    "source_accounts",
    "source_doc_ids",
    "source_tweet_ids",
    "raw_payload_ids",
)


def citation_is_citation_ready(citation: CitationAnnotation) -> bool:
    return not citation_block_reasons(citation)


def citation_block_reasons(citation: CitationAnnotation) -> tuple[str, ...]:
    reasons: list[str] = []
    if citation.metadata.get("marker_found", True) is False:
        reasons.append("missing_answer_marker")
    if not str(citation.chunk_id or "").strip():
        reasons.append("missing_chunk_id")
    if not str(citation.source_kind or "").strip():
        reasons.append("missing_source_kind")
    if not str(citation.source_id or "").strip():
        reasons.append("missing_source_id")
    if citation.evidence_status != "fact":
        reasons.append(f"non_fact_evidence:{citation.evidence_status or 'missing'}")
    if _normalized(citation.support_type) in NON_READY_SUPPORT_TYPES:
        reasons.append(f"unsupported_support_type:{citation.support_type}")
    if citation_marks_conflict(citation):
        reasons.append("conflicting_evidence")
    if citation_is_stale(citation):
        reasons.append("stale_evidence")
    if citation_is_not_evidence(citation):
        reasons.append("not_evidence")
    reasons.extend(_local_x_db_lineage_block_reasons(citation))
    return tuple(_dedupe_preserve_order(reasons))


def citation_marks_conflict(citation: CitationAnnotation) -> bool:
    values = [
        citation.support_type,
        citation.evidence_status,
        *(_metadata_values(citation.metadata, CONFLICT_METADATA_KEYS)),
    ]
    return any(_is_marker(value, CONFLICT_MARKERS) for value in values)


def chunk_marks_conflict(chunk: ContextChunk) -> bool:
    return any(
        _is_marker(value, CONFLICT_MARKERS)
        for value in _metadata_values(chunk.metadata, CONFLICT_METADATA_KEYS)
    )


def citation_is_stale(citation: CitationAnnotation) -> bool:
    values = [
        citation.evidence_status,
        *(_metadata_values(citation.metadata, STALE_METADATA_KEYS)),
    ]
    return any(_is_marker(value, STALE_MARKERS) for value in values)


def chunk_is_stale(chunk: ContextChunk) -> bool:
    return any(
        _is_marker(value, STALE_MARKERS)
        for value in _metadata_values(chunk.metadata, STALE_METADATA_KEYS)
    )


def citation_is_not_evidence(citation: CitationAnnotation) -> bool:
    if citation.metadata.get("not_evidence") is True:
        return True
    if citation.metadata.get("citation_excluded") is True:
        return True
    if citation.metadata.get("answer_support_allowed") is False:
        return True
    if _structured_metadata_blocks_answer_support(citation.metadata):
        return True
    values = [
        citation.evidence_status,
        citation.support_type,
        citation.field_path,
        *(_metadata_values(citation.metadata, NON_EVIDENCE_METADATA_KEYS)),
    ]
    if any(_is_policy_block_value(value) for value in values):
        return True
    if citation.metadata.get("legacy_metadata_compat") is True:
        legacy_values = [
            citation.source_kind,
            *(_metadata_values(citation.metadata, LEGACY_METADATA_COMPAT_KEYS)),
        ]
        return any(_is_legacy_non_evidence_value(value) for value in legacy_values)
    return False


def _local_x_db_lineage_block_reasons(citation: CitationAnnotation) -> list[str]:
    if str(citation.source_kind or "").strip() != "local_x_db":
        return []
    metadata = citation.metadata
    reasons: list[str] = []
    if not _lineage_value(metadata, "source_doc_hash"):
        reasons.append("missing_source_doc_hash")
    if not (
        _lineage_value(metadata, "source_bundle_id")
        or _lineage_value(metadata, "source_restore_id")
    ):
        reasons.append("missing_source_lineage_id")
    if _lineage_value(metadata, "lineage_status") != "restored":
        reasons.append("source_not_restored")
    if not (
        _lineage_value(metadata, "retrieval_text_hash")
        or _lineage_value(metadata, "retrieval_text_profile_id")
    ):
        reasons.append("missing_retrieval_text_lineage")
    return reasons


def _lineage_value(metadata: dict[str, Any], key: str) -> str:
    direct = metadata.get(key)
    if direct is None:
        lineage = metadata.get("source_lineage")
        if isinstance(lineage, dict):
            direct = lineage.get(key)
    return str(direct or "").strip()


def chunk_is_not_evidence(chunk: ContextChunk) -> bool:
    if chunk.metadata.get("not_evidence") is True:
        return True
    if chunk.metadata.get("citation_excluded") is True:
        return True
    if chunk.metadata.get("answer_support_allowed") is False:
        return True
    if _structured_metadata_blocks_answer_support(chunk.metadata):
        return True
    values = [
        *(_metadata_values(chunk.metadata, NON_EVIDENCE_METADATA_KEYS)),
    ]
    if any(_is_policy_block_value(value) for value in values):
        return True
    if chunk.metadata.get("legacy_metadata_compat") is True:
        legacy_values = [
            chunk.source_kind,
            *(_metadata_values(chunk.metadata, LEGACY_METADATA_COMPAT_KEYS)),
        ]
        return any(_is_legacy_non_evidence_value(value) for value in legacy_values)
    return False


def citation_evidence_key(citation: CitationAnnotation) -> tuple[str, str, str]:
    metadata = citation.metadata
    identity = metadata.get("primary_evidence_identity")
    if isinstance(identity, dict):
        source_kind = str(identity.get("source_kind") or citation.source_kind or "")
        source_id = str(
            identity.get("source_id")
            or metadata.get("primary_evidence_source_id")
            or citation.source_id
            or ""
        )
        identity_hash = str(
            identity.get("identity_hash")
            or identity.get("identity_key")
            or metadata.get("primary_evidence_hash")
            or metadata.get("primary_evidence_key")
            or ""
        )
        if source_id and identity_hash:
            return (source_kind, source_id, identity_hash)
    primary_key = metadata.get("primary_evidence_key")
    primary_source_id = metadata.get("primary_evidence_source_id")
    primary_hash = metadata.get("primary_evidence_hash")
    if primary_key and primary_source_id:
        return (
            str(metadata.get("primary_evidence_source_kind") or citation.source_kind or ""),
            str(primary_source_id),
            str(primary_hash or primary_key),
        )
    source_hash = (
        metadata.get("source_doc_hash")
        or metadata.get("source_hash")
        or metadata.get("content_hash")
        or metadata.get("raw_payload_hash")
        or ""
    )
    return (
        str(citation.source_kind or ""),
        str(citation.source_id or ""),
        str(source_hash or ""),
    )


def duplicate_evidence_count(citations: tuple[CitationAnnotation, ...]) -> int:
    counts = Counter(
        key for citation in citations if (key := citation_evidence_key(citation))[1]
    )
    return sum(max(0, count - 1) for count in counts.values())


def unique_evidence_count(citations: tuple[CitationAnnotation, ...]) -> int:
    return len(
        {
            key
            for citation in citations
            if (key := citation_evidence_key(citation))[1]
        }
    )


def citation_preserves_duplicate_provenance(citation: CitationAnnotation) -> bool:
    for key in PROVENANCE_METADATA_KEYS:
        value = citation.metadata.get(key)
        if isinstance(value, list | tuple | set | dict) and len(value) > 0:
            return True
        if isinstance(value, str) and value.strip():
            return True
    return False


def _metadata_values(metadata: dict[str, Any], keys: tuple[str, ...]) -> list[Any]:
    values: list[Any] = []
    for key in keys:
        if key in metadata:
            values.append(metadata.get(key))
    return values


def _is_marker(value: Any, markers: set[str]) -> bool:
    if value is None:
        return False
    if isinstance(value, bool):
        return value
    if isinstance(value, list | tuple | set):
        return any(_is_marker(item, markers) for item in value)
    if isinstance(value, dict):
        return any(_is_marker(item, markers) for item in value.values())
    return _normalized(value) in markers


def _structured_metadata_blocks_answer_support(metadata: dict[str, Any]) -> bool:
    artifact_role = metadata.get("artifact_role")
    if artifact_role not in {None, ""}:
        try:
            if not artifact_role_allows_answer_support(str(artifact_role)):
                return True
        except ValueError:
            return True

    authority_level = metadata.get("authority_level")
    if authority_level not in {None, ""}:
        try:
            if not authority_at_least(str(authority_level), AuthorityLevel.EVIDENCE_VIEW):
                return True
        except ValueError:
            return True

    output_mode = metadata.get("output_mode")
    if output_mode not in {None, ""}:
        try:
            mode = normalize_output_mode(str(output_mode))
        except ValueError:
            return True
        if mode not in {OutputMode.EVIDENCE_PACKAGE, OutputMode.ANSWER}:
            return True

    for key in ("participation_decision", "participation_snapshot"):
        participation = metadata.get(key)
        if not isinstance(participation, dict):
            continue
        if participation.get("can_use_as_evidence") is False:
            return True
        if participation.get("can_use_in_answer") is False:
            return True
    return False


def _is_policy_block_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, bool):
        return value is True
    if isinstance(value, list | tuple | set):
        return any(_is_policy_block_value(item) for item in value)
    if isinstance(value, dict):
        return any(_is_policy_block_value(item) for item in value.values())
    normalized = _normalized(value)
    return (
        normalized.endswith("_not_evidence")
        or normalized.startswith("not_evidence")
        or "not_evidence" in normalized
        or "not_citation" in normalized
        or "citation_excluded" in normalized
        or "answer_support_disallowed" in normalized
        or "answer_support_blocked" in normalized
    )


def _is_legacy_non_evidence_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, bool):
        return value is True
    if isinstance(value, list | tuple | set):
        return any(_is_legacy_non_evidence_value(item) for item in value)
    if isinstance(value, dict):
        return any(_is_legacy_non_evidence_value(item) for item in value.values())
    normalized = _normalized(value)
    return normalized in LEGACY_METADATA_COMPAT_NON_EVIDENCE_MARKERS


def _normalized(value: Any) -> str:
    return str(value).strip().casefold().replace("-", "_").replace(" ", "_")


def _dedupe_preserve_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result
