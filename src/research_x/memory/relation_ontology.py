from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

RELATION_ONTOLOGY_VERSION = "research-x-relation-ontology-v1"
RELATION_REQUIRED_DIMENSIONS = (
    "relation_type",
    "direction",
    "temporal_validity",
    "authority_source",
    "viewpoint",
    "access_scope",
    "citation_anchor",
    "candidate_only",
)


@dataclass(frozen=True)
class RelationTypeSpec:
    relation_type: str
    direction: str
    temporal_validity: str
    authority_source_required: bool
    viewpoint_allowed: bool
    access_scope_required: bool
    citation_anchor_required: bool
    answer_support_allowed: bool = False

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


RELATION_TYPE_SPECS: dict[str, RelationTypeSpec] = {
    "supports": RelationTypeSpec(
        "supports", "source_to_target", "as_of_required", True, True, False, True
    ),
    "contradicts": RelationTypeSpec(
        "contradicts", "source_to_target", "as_of_required", True, True, False, True
    ),
    "supersedes": RelationTypeSpec(
        "supersedes", "source_to_target", "valid_from_required", True, True, False, True
    ),
    "depends_on": RelationTypeSpec(
        "depends_on", "source_to_target", "optional", False, False, False, True
    ),
    "derived_from": RelationTypeSpec(
        "derived_from", "source_to_target", "required", False, False, False, True
    ),
    "derived_from_source": RelationTypeSpec(
        "derived_from_source", "source_to_target", "required", False, False, False, True
    ),
    "same_claim_as": RelationTypeSpec(
        "same_claim_as", "bidirectional", "as_of_required", True, True, False, True
    ),
    "can_view": RelationTypeSpec(
        "can_view", "principal_to_resource", "valid_from_required", True, False, True, False
    ),
    "bookmark_of_tweet": RelationTypeSpec(
        "bookmark_of_tweet", "source_to_target", "observed_at_required", False, False, True, True
    ),
    "has_media": RelationTypeSpec(
        "has_media", "source_to_target", "optional", False, False, False, True
    ),
    "quotes": RelationTypeSpec("quotes", "source_to_target", "optional", False, True, False, True),
    "quote_tree_includes": RelationTypeSpec(
        "quote_tree_includes", "source_to_target", "optional", False, True, False, True
    ),
    "has_quote_tree": RelationTypeSpec(
        "has_quote_tree", "source_to_target", "optional", False, False, False, True
    ),
    "same_bookmarked_tweet": RelationTypeSpec(
        "same_bookmarked_tweet", "bidirectional", "optional", False, False, True, True
    ),
    "same_url": RelationTypeSpec(
        "same_url", "bidirectional", "optional", False, False, False, True
    ),
    "same_topic": RelationTypeSpec(
        "same_topic", "bidirectional", "optional", False, True, False, True
    ),
    "newer_than": RelationTypeSpec(
        "newer_than", "source_to_target", "observed_at_required", False, False, False, True
    ),
    "older_than": RelationTypeSpec(
        "older_than", "source_to_target", "observed_at_required", False, False, False, True
    ),
    "obsolete_candidate": RelationTypeSpec(
        "obsolete_candidate", "source_to_target", "as_of_required", True, True, False, True
    ),
    "older_same_author_label": RelationTypeSpec(
        "older_same_author_label",
        "source_to_target",
        "observed_at_required",
        True,
        True,
        False,
        True,
    ),
}


def build_relation_ontology_trace(
    *,
    relations: list[dict[str, Any]],
    relation_counts: dict[str, int],
) -> dict[str, Any]:
    observed_types = _observed_relation_types(relations, relation_counts)
    unknown_types = sorted(
        relation_type
        for relation_type in observed_types
        if relation_type not in RELATION_TYPE_SPECS
    )
    missing_anchor_count = sum(
        1
        for relation in relations
        if _citation_anchor_required(relation) and not _has_citation_anchor(relation)
    )
    missing_temporal_count = sum(
        1
        for relation in relations
        if _temporal_required(relation) and not _has_temporal_validity(relation)
    )
    missing_authority_count = sum(
        1
        for relation in relations
        if _authority_required(relation) and not _has_authority_source(relation)
    )
    access_guard_count = sum(1 for relation in relations if _access_required(relation))
    return {
        "ontology_version": RELATION_ONTOLOGY_VERSION,
        "evidence_role": "control_plane_not_answer_evidence",
        "answer_support_allowed": False,
        "runtime_graph_adopted": False,
        "candidate_only": True,
        "required_dimensions": list(RELATION_REQUIRED_DIMENSIONS),
        "known_relation_type_count": len(RELATION_TYPE_SPECS),
        "observed_relation_types": sorted(observed_types),
        "unknown_relation_types": unknown_types,
        "coverage": {
            "relation_rows_seen": len(relations),
            "missing_citation_anchor_count": missing_anchor_count,
            "missing_temporal_validity_count": missing_temporal_count,
            "missing_authority_source_count": missing_authority_count,
            "access_guard_relation_count": access_guard_count,
        },
        "type_specs": {
            relation_type: RELATION_TYPE_SPECS[relation_type].as_dict()
            for relation_type in sorted(observed_types)
            if relation_type in RELATION_TYPE_SPECS
        },
        "promotion_boundary": (
            "Relation edges are traversal and review signals only. They require "
            "restored context chunks, citation annotations, and answer-authority "
            "checks before any claim can be answered."
        ),
    }


def relation_type_specs_as_dict() -> dict[str, dict[str, Any]]:
    return {
        relation_type: spec.as_dict() for relation_type, spec in sorted(RELATION_TYPE_SPECS.items())
    }


def _observed_relation_types(
    relations: list[dict[str, Any]],
    relation_counts: dict[str, int],
) -> set[str]:
    observed = {
        str(relation.get("relation_type") or "").strip()
        for relation in relations
        if str(relation.get("relation_type") or "").strip()
    }
    observed.update(
        str(relation_type or "").strip()
        for relation_type, count in relation_counts.items()
        if str(relation_type or "").strip() and int(count or 0) > 0
    )
    return observed


def _spec_for(relation: dict[str, Any]) -> RelationTypeSpec | None:
    return RELATION_TYPE_SPECS.get(str(relation.get("relation_type") or "").strip())


def _citation_anchor_required(relation: dict[str, Any]) -> bool:
    spec = _spec_for(relation)
    return bool(spec and spec.citation_anchor_required)


def _temporal_required(relation: dict[str, Any]) -> bool:
    spec = _spec_for(relation)
    return bool(spec and "required" in spec.temporal_validity)


def _authority_required(relation: dict[str, Any]) -> bool:
    spec = _spec_for(relation)
    return bool(spec and spec.authority_source_required)


def _access_required(relation: dict[str, Any]) -> bool:
    spec = _spec_for(relation)
    return bool(spec and spec.access_scope_required)


def _has_citation_anchor(relation: dict[str, Any]) -> bool:
    return any(
        relation.get(key)
        for key in (
            "citation_anchor",
            "citation_id",
            "chunk_id",
            "source_doc_id",
            "target_doc_id",
        )
    )


def _has_temporal_validity(relation: dict[str, Any]) -> bool:
    return any(
        relation.get(key) for key in ("as_of", "valid_from", "valid_to", "observed_at", "status")
    )


def _has_authority_source(relation: dict[str, Any]) -> bool:
    return any(
        relation.get(key)
        for key in ("authority_source", "source_doc_id", "citation_id", "chunk_id")
    )
