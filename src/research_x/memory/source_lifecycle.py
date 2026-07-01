from __future__ import annotations

from typing import Any

SOURCE_LIFECYCLE_VERSION = "research-x-source-lifecycle-v1"
SOURCE_LIFECYCLE_STATES = (
    "discovered",
    "eligible",
    "fetched",
    "extracted",
    "source_bundled",
    "chunked",
    "indexed",
    "retrieved",
    "included",
    "reflected",
    "cited",
    "citation_ready",
    "excluded",
    "changed",
    "stale",
    "provider_gated",
    "user_export_required",
)
SOURCE_LIFECYCLE_TRANSITIONS = (
    ("discovered", "eligible"),
    ("eligible", "fetched"),
    ("fetched", "extracted"),
    ("extracted", "source_bundled"),
    ("source_bundled", "chunked"),
    ("chunked", "indexed"),
    ("indexed", "retrieved"),
    ("retrieved", "included"),
    ("included", "reflected"),
    ("reflected", "cited"),
    ("cited", "citation_ready"),
)


def build_source_lifecycle_trace(
    *,
    discovered_ids: list[str] | tuple[str, ...] = (),
    eligible_ids: list[str] | tuple[str, ...] = (),
    fetched_ids: list[str] | tuple[str, ...] = (),
    extracted_ids: list[str] | tuple[str, ...] = (),
    source_bundled_ids: list[str] | tuple[str, ...] = (),
    chunked_ids: list[str] | tuple[str, ...] = (),
    indexed_ids: list[str] | tuple[str, ...] = (),
    retrieved_ids: list[str] | tuple[str, ...] = (),
    included_ids: list[str] | tuple[str, ...] = (),
    reflected_ids: list[str] | tuple[str, ...] = (),
    cited_ids: list[str] | tuple[str, ...] = (),
    citation_ready_ids: list[str] | tuple[str, ...] = (),
    excluded_ids: list[str] | tuple[str, ...] = (),
    changed_ids: list[str] | tuple[str, ...] = (),
    stale_ids: list[str] | tuple[str, ...] = (),
    provider_gated_ids: list[str] | tuple[str, ...] = (),
    user_export_required_ids: list[str] | tuple[str, ...] = (),
) -> dict[str, Any]:
    states = {
        "discovered": _state(discovered_ids),
        "eligible": _state(eligible_ids),
        "fetched": _state(fetched_ids),
        "extracted": _state(extracted_ids),
        "source_bundled": _state(source_bundled_ids),
        "chunked": _state(chunked_ids),
        "indexed": _state(indexed_ids),
        "retrieved": _state(retrieved_ids),
        "included": _state(included_ids),
        "reflected": _state(reflected_ids),
        "cited": _state(cited_ids),
        "citation_ready": _state(citation_ready_ids),
        "excluded": _state(excluded_ids),
        "changed": _state(changed_ids),
        "stale": _state(stale_ids),
        "provider_gated": _state(provider_gated_ids),
        "user_export_required": _state(user_export_required_ids),
    }
    blocked_count = sum(
        states[state]["count"]
        for state in ("excluded", "stale", "provider_gated", "user_export_required")
    )
    return {
        "lifecycle_version": SOURCE_LIFECYCLE_VERSION,
        "evidence_role": "control_plane_not_answer_evidence",
        "answer_support_allowed": False,
        "runtime_source_mutation_allowed": False,
        "states": states,
        "state_counts": {state: states[state]["count"] for state in SOURCE_LIFECYCLE_STATES},
        "transitions": [
            {"from": source, "to": target, "runtime_mutation_allowed": False}
            for source, target in SOURCE_LIFECYCLE_TRANSITIONS
        ],
        "blocked_count": blocked_count,
        "promotion_boundary": (
            "Lifecycle states describe source-candidate progress only. They do "
            "not fetch, mutate, cite, or answer without restored source bundles, "
            "context chunks, citations, and answer-authority checks."
        ),
    }


def _state(values: list[str] | tuple[str, ...]) -> dict[str, Any]:
    cleaned = _clean_ids(values)
    return {
        "count": len(cleaned),
        "sample_ids": cleaned[:8],
    }


def _clean_ids(values: list[str] | tuple[str, ...]) -> list[str]:
    result: list[str] = []
    for value in values:
        clean = str(value or "").strip()
        if not clean or clean in result:
            continue
        result.append(clean)
    return result
