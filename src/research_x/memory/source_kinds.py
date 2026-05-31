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


def _metadata_source_kind(metadata: dict[str, Any] | None) -> str | None:
    if not metadata:
        return None
    value = metadata.get("source_kind") or metadata.get("evidence_source_kind")
    if isinstance(value, str) and value in ALLOWED_SOURCE_KINDS:
        return value
    return None


def _domain_matches(domain: str, candidates: tuple[str, ...]) -> bool:
    return any(domain == candidate or domain.endswith(f".{candidate}") for candidate in candidates)
