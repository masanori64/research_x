from __future__ import annotations

from enum import StrEnum


class ArtifactRole(StrEnum):
    """KnowledgeOps role for any source, projection, signal, or control artifact."""

    RAW_SOURCE = "raw_source"
    CURATED_SOURCE = "curated_source"
    IMPORTED_SOURCE = "imported_source"
    PROJECTION = "projection"
    DERIVED_SIGNAL = "derived_signal"
    WORKING_NOTE = "working_note"
    CONTROL_STATE = "control_state"
    EVIDENCE_VIEW = "evidence_view"


SEARCHABLE_ARTIFACT_ROLES = frozenset(
    {
        ArtifactRole.RAW_SOURCE,
        ArtifactRole.CURATED_SOURCE,
        ArtifactRole.IMPORTED_SOURCE,
        ArtifactRole.PROJECTION,
        ArtifactRole.DERIVED_SIGNAL,
        ArtifactRole.WORKING_NOTE,
        ArtifactRole.EVIDENCE_VIEW,
    }
)

ANSWER_ELIGIBLE_ARTIFACT_ROLES = frozenset({ArtifactRole.EVIDENCE_VIEW})

SOURCE_ARTIFACT_ROLES = frozenset(
    {
        ArtifactRole.RAW_SOURCE,
        ArtifactRole.CURATED_SOURCE,
        ArtifactRole.IMPORTED_SOURCE,
    }
)

CONTROL_ONLY_ARTIFACT_ROLES = frozenset(
    {
        ArtifactRole.CONTROL_STATE,
        ArtifactRole.WORKING_NOTE,
        ArtifactRole.DERIVED_SIGNAL,
        ArtifactRole.PROJECTION,
    }
)


def validate_artifact_role_transition(
    source_role: str | ArtifactRole,
    target_role: str | ArtifactRole,
    *,
    explicit_promotion: bool = False,
    source_restored: bool = False,
) -> bool:
    """Return whether an artifact may be promoted without role spoofing."""

    source = normalize_artifact_role(source_role)
    target = normalize_artifact_role(target_role)
    if source is target:
        return True
    if source is ArtifactRole.WORKING_NOTE and target is ArtifactRole.CURATED_SOURCE:
        return explicit_promotion
    if target in SOURCE_ARTIFACT_ROLES:
        return False
    if target is ArtifactRole.EVIDENCE_VIEW:
        return source in SOURCE_ARTIFACT_ROLES and source_restored
    if target in {ArtifactRole.PROJECTION, ArtifactRole.DERIVED_SIGNAL}:
        return source in {
            ArtifactRole.RAW_SOURCE,
            ArtifactRole.CURATED_SOURCE,
            ArtifactRole.IMPORTED_SOURCE,
            ArtifactRole.PROJECTION,
            ArtifactRole.EVIDENCE_VIEW,
        }
    if target is ArtifactRole.CONTROL_STATE:
        return source in {ArtifactRole.CONTROL_STATE, ArtifactRole.PROJECTION}
    return False


def normalize_artifact_role(value: str | ArtifactRole) -> ArtifactRole:
    if isinstance(value, ArtifactRole):
        return value
    normalized = str(value).strip().casefold().replace("-", "_").replace(" ", "_")
    try:
        return ArtifactRole(normalized)
    except ValueError as exc:
        allowed = ", ".join(role.value for role in ArtifactRole)
        raise ValueError(f"unknown artifact_role {value!r}; expected one of: {allowed}") from exc


def artifact_role_allows_answer_support(value: str | ArtifactRole) -> bool:
    return normalize_artifact_role(value) in ANSWER_ELIGIBLE_ARTIFACT_ROLES


def artifact_role_is_source(value: str | ArtifactRole) -> bool:
    return normalize_artifact_role(value) in SOURCE_ARTIFACT_ROLES
