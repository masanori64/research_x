from __future__ import annotations

import urllib.parse
from typing import Any

LOCAL_X_DB = "local_x_db"
OFFICIAL = "official"
SECONDARY = "secondary"
USER_GENERATED = "user_generated"
EXTERNAL_WEB_MEDIUM = "external_web"
ALLOWED_SOURCE_KINDS = {LOCAL_X_DB, OFFICIAL, SECONDARY, USER_GENERATED}

_USER_GENERATED_DOMAINS = (
    "x.com",
    "twitter.com",
    "reddit.com",
    "youtube.com",
    "youtu.be",
    "tiktok.com",
    "instagram.com",
    "facebook.com",
    "github.com",
    "gist.github.com",
    "note.com",
    "qiita.com",
    "zenn.dev",
    "medium.com",
)
_OFFICIAL_DOMAINS = (
    "arxiv.org",
    "pubmed.ncbi.nlm.nih.gov",
    "sec.gov",
    "federalreserve.gov",
    "boj.or.jp",
    "jpx.co.jp",
    "tdnet.info",
    "release.tdnet.info",
    "openai.com",
    "anthropic.com",
    "ai.google.dev",
    "developers.google.com",
    "api-dashboard.search.brave.com",
)
_OFFICIAL_SUFFIXES = (
    ".gov",
    ".mil",
    ".edu",
    ".go.jp",
    ".lg.jp",
    ".ac.jp",
)


def classify_external_source_kind(
    url: str | None,
    *,
    metadata: dict[str, Any] | None = None,
) -> str:
    override = _metadata_source_kind(metadata)
    if override:
        return override
    if not url:
        return SECONDARY
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme == "memory":
        return SECONDARY
    host = parsed.hostname or ""
    domain = host.lower().removeprefix("www.")
    if _domain_matches(domain, _USER_GENERATED_DOMAINS):
        return USER_GENERATED
    if _domain_matches(domain, _OFFICIAL_DOMAINS) or domain.endswith(_OFFICIAL_SUFFIXES):
        return OFFICIAL
    return SECONDARY


def evidence_status_for_source(
    url: str | None,
    *,
    provider: str,
) -> str:
    if not url or provider == "fake" or url.startswith("memory://"):
        return "unconfirmed"
    return "fact"


def source_risk_flags(url: str | None, *, source_kind: str) -> list[str]:
    parsed = urllib.parse.urlparse(url or "")
    domain = (parsed.hostname or "").lower().removeprefix("www.")
    query = parsed.query.casefold()
    path = parsed.path.casefold()
    flags: list[str] = []
    if source_kind == SECONDARY:
        flags.append("secondary_needs_cross_check")
    if source_kind == USER_GENERATED:
        flags.append("community_or_user_generated")
    if any(token in domain for token in ("tabelog", "hotpepper", "gnavi", "gurunavi")):
        flags.append("leadgen_or_listing_site")
    if any(token in query for token in ("utm_", "affiliate", "ref=", "clickid")):
        flags.append("tracking_or_affiliate_parameter")
    if any(token in path for token in ("sponsored", "advertorial", "affiliate", "ranking")):
        flags.append("possible_sponsored_or_ranking_content")
    if any(token in domain for token in ("perplexity", "you.com", "chatgpt", "gemini.google")):
        flags.append("ai_generated_or_ai_intermediated")
    if not flags:
        flags.append("no_static_risk_flag")
    return flags


def source_quality_class(url: str | None, *, source_kind: str) -> str:
    if source_kind == LOCAL_X_DB:
        return "local_primary_archive"
    if source_kind == OFFICIAL:
        return "official_or_primary_candidate"
    if source_kind == USER_GENERATED:
        return "community_observation_candidate"
    risks = set(source_risk_flags(url, source_kind=source_kind))
    if "leadgen_or_listing_site" in risks:
        return "affiliate_or_leadgen_candidate"
    if "ai_generated_or_ai_intermediated" in risks:
        return "ai_suspected_candidate"
    return "independent_secondary_candidate"


def _metadata_source_kind(metadata: dict[str, Any] | None) -> str | None:
    if not metadata:
        return None
    value = metadata.get("source_kind") or metadata.get("evidence_source_kind")
    if isinstance(value, str) and value in ALLOWED_SOURCE_KINDS:
        return value
    return None


def _domain_matches(domain: str, candidates: tuple[str, ...]) -> bool:
    return any(domain == candidate or domain.endswith(f".{candidate}") for candidate in candidates)
