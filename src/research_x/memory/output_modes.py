from __future__ import annotations

from enum import StrEnum

from research_x.memory.authority_levels import AuthorityLevel, normalize_authority_level


class OutputMode(StrEnum):
    """KnowledgeOps output mode for mode-aware tool and CLI responses."""

    EXPLORE = "explore"
    COLLECT = "collect"
    WORKING_NOTE = "working_note"
    SYNTHESIZE = "synthesize"
    EVIDENCE_PACKAGE = "evidence_package"
    ANSWER = "answer"


OUTPUT_MODE_MIN_AUTHORITY = {
    OutputMode.EXPLORE: AuthorityLevel.NAVIGATION_SIGNAL,
    OutputMode.COLLECT: AuthorityLevel.CANDIDATE,
    OutputMode.WORKING_NOTE: AuthorityLevel.CANDIDATE,
    OutputMode.SYNTHESIZE: AuthorityLevel.CANDIDATE,
    OutputMode.EVIDENCE_PACKAGE: AuthorityLevel.EVIDENCE_VIEW,
    OutputMode.ANSWER: AuthorityLevel.ANSWER_ASSERTION,
}

OUTPUT_MODE_ALLOWED_AUTHORITIES = {
    OutputMode.EXPLORE: frozenset(AuthorityLevel),
    OutputMode.COLLECT: frozenset(AuthorityLevel),
    OutputMode.WORKING_NOTE: frozenset(AuthorityLevel),
    OutputMode.SYNTHESIZE: frozenset(AuthorityLevel),
    OutputMode.EVIDENCE_PACKAGE: frozenset(
        {
            AuthorityLevel.EVIDENCE_VIEW,
            AuthorityLevel.CLAIM_SUPPORTED,
        }
    ),
    OutputMode.ANSWER: frozenset({AuthorityLevel.ANSWER_ASSERTION}),
}


def normalize_output_mode(value: str | OutputMode) -> OutputMode:
    if isinstance(value, OutputMode):
        return value
    normalized = str(value).strip().casefold().replace("-", "_").replace(" ", "_")
    try:
        return OutputMode(normalized)
    except ValueError as exc:
        allowed = ", ".join(mode.value for mode in OutputMode)
        raise ValueError(f"unknown output_mode {value!r}; expected one of: {allowed}") from exc


def output_mode_min_authority(value: str | OutputMode) -> AuthorityLevel:
    return OUTPUT_MODE_MIN_AUTHORITY[normalize_output_mode(value)]


def output_mode_allows_answer_text(value: str | OutputMode) -> bool:
    return normalize_output_mode(value) is OutputMode.ANSWER


def allowed_authority_for_mode(
    output_mode: str | OutputMode,
) -> frozenset[AuthorityLevel]:
    return OUTPUT_MODE_ALLOWED_AUTHORITIES[normalize_output_mode(output_mode)]


def mode_requires_source_restore(value: str | OutputMode) -> bool:
    return normalize_output_mode(value) in {
        OutputMode.EVIDENCE_PACKAGE,
        OutputMode.ANSWER,
    }


def mode_requires_evidence_package(value: str | OutputMode) -> bool:
    return normalize_output_mode(value) is OutputMode.ANSWER


def mode_requires_citation(value: str | OutputMode) -> bool:
    return normalize_output_mode(value) is OutputMode.ANSWER


def mode_requires_claim_support(value: str | OutputMode) -> bool:
    return normalize_output_mode(value) is OutputMode.ANSWER


def output_mode_accepts_authority(
    output_mode: str | OutputMode,
    authority_level: str | AuthorityLevel,
) -> bool:
    mode = normalize_output_mode(output_mode)
    level = normalize_authority_level(authority_level)
    return level in allowed_authority_for_mode(mode)
