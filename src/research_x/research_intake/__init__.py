"""Local-only dry-run research intake."""

from research_x.research_intake.pipeline import (
    DEFAULT_BRIEF_PATH,
    DEFAULT_PROFILE_PATH,
    DEFAULT_REGISTRY_PATH,
    DEFAULT_RUN_PATH,
    DiscoveryRun,
    FetchSnapshot,
    InterestProfile,
    ResearchCandidate,
    SourceRegistry,
    SourceSubscription,
    discover_candidates,
    format_research_brief,
    load_profile,
    load_registry,
    validate_configuration,
    validate_run,
)

__all__ = [
    "DEFAULT_BRIEF_PATH",
    "DEFAULT_PROFILE_PATH",
    "DEFAULT_REGISTRY_PATH",
    "DEFAULT_RUN_PATH",
    "DiscoveryRun",
    "FetchSnapshot",
    "InterestProfile",
    "ResearchCandidate",
    "SourceRegistry",
    "SourceSubscription",
    "discover_candidates",
    "format_research_brief",
    "load_profile",
    "load_registry",
    "validate_configuration",
    "validate_run",
]
