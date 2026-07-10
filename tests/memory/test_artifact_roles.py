from __future__ import annotations

import pytest

from research_x.memory.artifact_roles import (
    ArtifactRole,
    artifact_role_allows_answer_support,
    artifact_role_is_source,
    normalize_artifact_role,
    validate_artifact_role_transition,
)

CANON_ITEM = "P1"
PURPOSE = "Artifact roles control promotion; names alone do not grant authority."
pytestmark = pytest.mark.canon(CANON_ITEM)


def test_artifact_role_normalization_accepts_human_variants() -> None:
    assert normalize_artifact_role("raw-source") is ArtifactRole.RAW_SOURCE
    assert normalize_artifact_role(" Evidence View ") is ArtifactRole.EVIDENCE_VIEW
    assert normalize_artifact_role(ArtifactRole.PROJECTION) is ArtifactRole.PROJECTION


def test_only_evidence_view_can_directly_support_answer() -> None:
    assert artifact_role_allows_answer_support("evidence_view")
    assert not artifact_role_allows_answer_support("raw_source")
    assert not artifact_role_allows_answer_support("projection")
    assert not artifact_role_allows_answer_support("working_note")
    assert not artifact_role_allows_answer_support("derived_signal")
    assert not artifact_role_allows_answer_support("control_state")


def test_source_roles_are_explicit() -> None:
    assert artifact_role_is_source("raw_source")
    assert artifact_role_is_source("curated_source")
    assert artifact_role_is_source("imported_source")
    assert not artifact_role_is_source("projection")
    assert not artifact_role_is_source("evidence_view")


def test_artifact_role_transitions_block_spoofed_promotion() -> None:
    assert validate_artifact_role_transition("raw_source", "projection")
    assert validate_artifact_role_transition("projection", "derived_signal")
    assert not validate_artifact_role_transition("projection", "raw_source")
    assert not validate_artifact_role_transition("working_note", "curated_source")
    assert validate_artifact_role_transition(
        "working_note",
        "curated_source",
        explicit_promotion=True,
    )
    assert not validate_artifact_role_transition("derived_signal", "evidence_view")
    assert not validate_artifact_role_transition("control_state", "evidence_view")
    assert not validate_artifact_role_transition("projection", "evidence_view")
    assert validate_artifact_role_transition(
        "raw_source",
        "evidence_view",
        source_restored=True,
    )


def test_unknown_artifact_role_is_rejected() -> None:
    with pytest.raises(ValueError, match="unknown artifact_role"):
        normalize_artifact_role("answer")
