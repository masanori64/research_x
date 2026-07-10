from __future__ import annotations

from enum import StrEnum


class AuthorityLevel(StrEnum):
    """How far an item has been promoted toward answer authority."""

    NAVIGATION_SIGNAL = "navigation_signal"
    CANDIDATE = "candidate"
    SOURCE_BACKED = "source_backed"
    EVIDENCE_VIEW = "evidence_view"
    CLAIM_SUPPORTED = "claim_supported"
    ANSWER_ASSERTION = "answer_assertion"


AUTHORITY_ORDER: tuple[AuthorityLevel, ...] = (
    AuthorityLevel.NAVIGATION_SIGNAL,
    AuthorityLevel.CANDIDATE,
    AuthorityLevel.SOURCE_BACKED,
    AuthorityLevel.EVIDENCE_VIEW,
    AuthorityLevel.CLAIM_SUPPORTED,
    AuthorityLevel.ANSWER_ASSERTION,
)


def normalize_authority_level(value: str | AuthorityLevel) -> AuthorityLevel:
    if isinstance(value, AuthorityLevel):
        return value
    normalized = str(value).strip().casefold().replace("-", "_").replace(" ", "_")
    try:
        return AuthorityLevel(normalized)
    except ValueError as exc:
        allowed = ", ".join(level.value for level in AuthorityLevel)
        raise ValueError(
            f"unknown authority_level {value!r}; expected one of: {allowed}"
        ) from exc


def authority_rank(value: str | AuthorityLevel) -> int:
    return AUTHORITY_ORDER.index(normalize_authority_level(value))


def authority_at_least(
    value: str | AuthorityLevel,
    required: str | AuthorityLevel,
) -> bool:
    return authority_rank(value) >= authority_rank(required)


def authority_level_allows_answer_assertion(value: str | AuthorityLevel) -> bool:
    return normalize_authority_level(value) is AuthorityLevel.ANSWER_ASSERTION
