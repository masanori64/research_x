from __future__ import annotations

from enum import StrEnum


class PersistenceMode(StrEnum):
    """Persistence boundary for a local memory operation.

    ``trace`` keeps only the operational run/step audit. ``artifacts`` also
    stores search results, context chunks, citations, and answers. The split
    prevents a request for observability from silently becoming permission to
    retain derived content.
    """

    NONE = "none"
    TRACE = "trace"
    ARTIFACTS = "artifacts"

    @property
    def stores_trace(self) -> bool:
        return self in {PersistenceMode.TRACE, PersistenceMode.ARTIFACTS}

    @property
    def stores_artifacts(self) -> bool:
        return self is PersistenceMode.ARTIFACTS


def normalize_persistence_mode(value: str | PersistenceMode) -> PersistenceMode:
    if isinstance(value, PersistenceMode):
        return value
    normalized = str(value).strip().casefold().replace("-", "_")
    aliases = {
        "full": PersistenceMode.ARTIFACTS,
        "store": PersistenceMode.ARTIFACTS,
        "no_store": PersistenceMode.NONE,
        "off": PersistenceMode.NONE,
        "audit": PersistenceMode.TRACE,
        "audit_only": PersistenceMode.TRACE,
    }
    if normalized in aliases:
        return aliases[normalized]
    try:
        return PersistenceMode(normalized)
    except ValueError as exc:
        allowed = ", ".join(mode.value for mode in PersistenceMode)
        raise ValueError(
            f"unknown persistence mode {value!r}; expected one of: {allowed}"
        ) from exc


def resolve_persistence_mode(
    *,
    store: bool,
    persistence: str | PersistenceMode | None,
) -> PersistenceMode:
    """Resolve the explicit mode, retaining the legacy ``store`` contract."""

    if persistence is not None:
        return normalize_persistence_mode(persistence)
    return PersistenceMode.ARTIFACTS if store else PersistenceMode.NONE
