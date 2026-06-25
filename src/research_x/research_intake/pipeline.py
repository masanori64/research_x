from __future__ import annotations

import hashlib
import json
import re
import tomllib
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

DEFAULT_BASE_DIR = Path("control") / "research_intake"
DEFAULT_PROFILE_PATH = DEFAULT_BASE_DIR / "codex_ai_tools.profile.toml"
DEFAULT_REGISTRY_PATH = DEFAULT_BASE_DIR / "source_registry.toml"
DEFAULT_RUN_PATH = Path("runs") / "research_intake" / "discovery_run.json"
DEFAULT_BRIEF_PATH = Path("runs") / "research_intake" / "research_brief.md"

ALLOWED_NETWORK_MODES = {"dry-run", "local-only"}
LOCAL_SOURCE_TYPES = {"manual_url", "local_note", "fake_search"}
PROVIDER_SOURCE_TYPES = {
    "serper",
    "brave",
    "jina",
    "jina_reader",
    "openai",
    "gemini",
    "voyage",
    "cohere",
    "mistral",
    "managed_rag",
    "external_search_provider",
}
DISABLED_VALUES = {"disabled", "never", "false", "off"}
QUALITY_SCORES = {
    "official": 1.0,
    "high": 0.85,
    "medium": 0.65,
    "unknown": 0.5,
    "low": 0.35,
}


@dataclass(frozen=True)
class InterestProfile:
    profile_id: str
    title: str
    include_topics: tuple[str, ...]
    exclude_topics: tuple[str, ...] = field(default_factory=tuple)
    preferred_sources: tuple[str, ...] = field(default_factory=tuple)
    recency_half_life_days: int = 45
    minimum_source_quality: str = "unknown"
    privacy_boundary: str = "project_local_only"
    network_mode: str = "dry-run"

    def as_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["include_topics"] = list(self.include_topics)
        data["exclude_topics"] = list(self.exclude_topics)
        data["preferred_sources"] = list(self.preferred_sources)
        return data


@dataclass(frozen=True)
class SourcePolicy:
    fetch_mode: str = "metadata_only"
    allow_network: bool = False
    allow_provider: bool = False
    storage_rights: str = "review_before_fetch"
    prompt_injection_review: str = "required_before_fetch"

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SourceSubscription:
    source_id: str
    source_type: str
    locator: str
    enabled_when: str = "always"
    title: str = ""
    quality_hint: str = "unknown"
    topics: tuple[str, ...] = field(default_factory=tuple)
    policy: SourcePolicy = field(default_factory=SourcePolicy)

    def as_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["topics"] = list(self.topics)
        return data


@dataclass(frozen=True)
class SourceRegistry:
    registry_id: str
    sources: tuple[SourceSubscription, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "registry_id": self.registry_id,
            "sources": [source.as_dict() for source in self.sources],
        }


@dataclass(frozen=True)
class SkippedSource:
    source_id: str
    source_type: str
    reason: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ResearchCandidate:
    candidate_id: str
    run_id: str
    source_id: str
    source_type: str
    canonical_url: str
    title: str
    raw_snippet: str
    discovered_at: str
    dedupe_key: str
    source_quality_hint: str
    status: str
    scores: dict[str, float]
    risk_flags: tuple[str, ...]
    citation_excluded: bool
    evidence_status: str

    def as_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["risk_flags"] = list(self.risk_flags)
        return data


@dataclass(frozen=True)
class FetchSnapshot:
    snapshot_id: str
    candidate_id: str
    snapshot_at: str
    fetched_at: str | None
    fetch_method: str
    fetch_status: str
    content_hash: str
    raw_content_path: str | None
    source_bundle_ref: str | None
    storage_rights: str
    prompt_injection_review: str
    promotion_gate: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class DiscoveryRun:
    run_id: str
    created_at: str
    profile: dict[str, Any]
    source_registry: dict[str, Any]
    network_mode: str
    limit: int
    provider_freeze_compliant: bool
    network_calls_attempted: int
    provider_calls_attempted: int
    candidates: tuple[ResearchCandidate, ...]
    snapshots: tuple[FetchSnapshot, ...]
    skipped_sources: tuple[SkippedSource, ...]
    notes: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["candidates"] = [candidate.as_dict() for candidate in self.candidates]
        data["snapshots"] = [snapshot.as_dict() for snapshot in self.snapshots]
        data["skipped_sources"] = [source.as_dict() for source in self.skipped_sources]
        data["notes"] = list(self.notes)
        return data


def load_profile(path: Path) -> InterestProfile:
    data = _read_toml(path)
    raw = data.get("profile", data)
    return InterestProfile(
        profile_id=str(raw.get("profile_id", "")).strip(),
        title=str(raw.get("title", "")).strip(),
        include_topics=_string_tuple(raw.get("include_topics")),
        exclude_topics=_string_tuple(raw.get("exclude_topics")),
        preferred_sources=_string_tuple(raw.get("preferred_sources")),
        recency_half_life_days=int(raw.get("recency_half_life_days", 45)),
        minimum_source_quality=str(raw.get("minimum_source_quality", "unknown")).strip(),
        privacy_boundary=str(raw.get("privacy_boundary", "project_local_only")).strip(),
        network_mode=str(raw.get("network_mode", "dry-run")).strip(),
    )


def load_registry(path: Path) -> SourceRegistry:
    data = _read_toml(path)
    registry_id = str(data.get("registry_id", path.stem)).strip()
    sources = tuple(_source_from_dict(source) for source in data.get("sources", []))
    return SourceRegistry(registry_id=registry_id, sources=sources)


def validate_profile(profile: InterestProfile) -> list[str]:
    errors: list[str] = []
    if not profile.profile_id:
        errors.append("profile_id is required")
    if not profile.title:
        errors.append("title is required")
    if not profile.include_topics:
        errors.append("include_topics must contain at least one topic")
    if profile.network_mode not in ALLOWED_NETWORK_MODES:
        errors.append(
            f"network_mode must be one of {sorted(ALLOWED_NETWORK_MODES)}: "
            f"{profile.network_mode}"
        )
    if profile.recency_half_life_days <= 0:
        errors.append("recency_half_life_days must be positive")
    if profile.minimum_source_quality not in QUALITY_SCORES:
        errors.append(
            f"minimum_source_quality must be one of {sorted(QUALITY_SCORES)}: "
            f"{profile.minimum_source_quality}"
        )
    if profile.privacy_boundary != "project_local_only":
        errors.append("dry-run intake currently requires privacy_boundary=project_local_only")
    return errors


def validate_registry(registry: SourceRegistry) -> list[str]:
    errors: list[str] = []
    if not registry.registry_id:
        errors.append("registry_id is required")
    if not registry.sources:
        errors.append("registry must contain at least one source")

    seen: set[str] = set()
    for source in registry.sources:
        if not source.source_id:
            errors.append("source_id is required")
            continue
        if source.source_id in seen:
            errors.append(f"duplicate source_id: {source.source_id}")
        seen.add(source.source_id)

        if source.source_type not in LOCAL_SOURCE_TYPES | PROVIDER_SOURCE_TYPES:
            errors.append(
                f"{source.source_id}: source_type must be local/dry-run or known "
                f"provider-gated type: {source.source_type}"
            )
        if source.source_type in PROVIDER_SOURCE_TYPES and _source_enabled(source):
            errors.append(
                f"{source.source_id}: provider-backed sources cannot be enabled "
                "for dry-run intake"
            )
        if source.policy.allow_network:
            errors.append(f"{source.source_id}: policy.allow_network must be false")
        if source.policy.allow_provider:
            errors.append(f"{source.source_id}: policy.allow_provider must be false")
        if source.policy.fetch_mode != "metadata_only":
            errors.append(f"{source.source_id}: policy.fetch_mode must be metadata_only")
        if source.source_type == "manual_url" and not _looks_like_url(source.locator):
            errors.append(f"{source.source_id}: manual_url locator must be http(s)")
        if source.quality_hint not in QUALITY_SCORES:
            errors.append(
                f"{source.source_id}: quality_hint must be one of {sorted(QUALITY_SCORES)}"
            )
    return errors


def validate_configuration(profile: InterestProfile, registry: SourceRegistry) -> list[str]:
    errors = validate_profile(profile)
    errors.extend(validate_registry(registry))

    source_ids = {source.source_id for source in registry.sources}
    for source_id in profile.preferred_sources:
        if source_id not in source_ids:
            errors.append(f"preferred source is not in registry: {source_id}")
    return errors


def discover_candidates(
    profile: InterestProfile,
    registry: SourceRegistry,
    *,
    limit: int = 10,
    created_at: str | None = None,
) -> DiscoveryRun:
    errors = validate_configuration(profile, registry)
    if errors:
        raise ValueError("; ".join(errors))
    if limit < 0:
        raise ValueError("limit must be non-negative")

    timestamp = created_at or _utc_now()
    run_id = "research_run_" + _stable_id(profile.profile_id, registry.registry_id, timestamp)
    selected_sources = set(profile.preferred_sources)
    candidates: list[ResearchCandidate] = []
    snapshots: list[FetchSnapshot] = []
    skipped: list[SkippedSource] = []

    for source in registry.sources:
        if selected_sources and source.source_id not in selected_sources:
            continue
        if not _source_enabled(source):
            skipped.append(
                SkippedSource(
                    source_id=source.source_id,
                    source_type=source.source_type,
                    reason="disabled_by_registry",
                )
            )
            continue
        if source.source_type in PROVIDER_SOURCE_TYPES:
            skipped.append(
                SkippedSource(
                    source_id=source.source_id,
                    source_type=source.source_type,
                    reason="provider_freeze",
                )
            )
            continue

        for title, url, snippet in _candidate_inputs(profile, source):
            if len(candidates) >= limit:
                break
            candidate = _make_candidate(
                profile=profile,
                source=source,
                run_id=run_id,
                title=title,
                canonical_url=url,
                snippet=snippet,
                discovered_at=timestamp,
                sequence=len(candidates) + 1,
            )
            snapshot = _make_snapshot(candidate, source, snapshot_at=timestamp)
            candidates.append(candidate)
            snapshots.append(snapshot)
        if len(candidates) >= limit:
            break

    notes = (
        "dry-run only: no URL fetch, provider search, Reader, LLM, embedding, or rerank calls",
        "candidates and research briefs are review signals, not citation-ready evidence",
    )
    if not candidates:
        notes += ("no candidates produced from enabled local/dry-run sources",)

    return DiscoveryRun(
        run_id=run_id,
        created_at=timestamp,
        profile=profile.as_dict(),
        source_registry={
            "registry_id": registry.registry_id,
            "source_ids": [source.source_id for source in registry.sources],
            "digest": _hash_dict(registry.as_dict()),
        },
        network_mode=profile.network_mode,
        limit=limit,
        provider_freeze_compliant=True,
        network_calls_attempted=0,
        provider_calls_attempted=0,
        candidates=tuple(candidates),
        snapshots=tuple(snapshots),
        skipped_sources=tuple(skipped),
        notes=notes,
    )


def validate_run(run: DiscoveryRun | dict[str, Any]) -> list[str]:
    data = _run_dict(run)
    errors: list[str] = []
    if data.get("network_calls_attempted") != 0:
        errors.append("network_calls_attempted must be 0 for dry-run intake")
    if data.get("provider_calls_attempted") != 0:
        errors.append("provider_calls_attempted must be 0 for dry-run intake")
    if data.get("provider_freeze_compliant") is not True:
        errors.append("provider_freeze_compliant must be true")
    for candidate in data.get("candidates", []):
        if candidate.get("citation_excluded") is not True:
            errors.append(f"{candidate.get('candidate_id')}: citation_excluded must be true")
        if candidate.get("evidence_status") != "not_evidence_until_fetched_and_chunked":
            errors.append(f"{candidate.get('candidate_id')}: invalid evidence_status")
    for snapshot in data.get("snapshots", []):
        if snapshot.get("fetch_status") != "not_fetched_dry_run":
            errors.append(f"{snapshot.get('snapshot_id')}: fetch_status must be dry-run")
        if snapshot.get("fetch_method") != "metadata_only_no_network":
            errors.append(f"{snapshot.get('snapshot_id')}: fetch_method must be no-network")
        if snapshot.get("raw_content_path") is not None:
            errors.append(f"{snapshot.get('snapshot_id')}: raw_content_path must be null")
        if snapshot.get("source_bundle_ref") is not None:
            errors.append(f"{snapshot.get('snapshot_id')}: source_bundle_ref must be null")
    return errors


def format_research_brief(run: DiscoveryRun | dict[str, Any], *, objective: str = "") -> str:
    data = _run_dict(run)
    candidates = sorted(
        data.get("candidates", []),
        key=lambda candidate: candidate.get("scores", {}).get("total", 0.0),
        reverse=True,
    )
    lines = [
        "# Research Intake Brief",
        "",
        f"- Run: `{data.get('run_id', '')}`",
        f"- Profile: `{data.get('profile', {}).get('profile_id', '')}`",
        f"- Network mode: `{data.get('network_mode', '')}`",
        f"- Provider calls attempted: {data.get('provider_calls_attempted', 0)}",
        f"- Network calls attempted: {data.get('network_calls_attempted', 0)}",
        "- Evidence status: candidate review signals only; not citation-ready evidence.",
    ]
    if objective:
        lines.append(f"- Objective: {objective}")
    lines.extend(["", "## Top Candidates", ""])
    if candidates:
        for index, candidate in enumerate(candidates, start=1):
            total = candidate.get("scores", {}).get("total", 0.0)
            lines.extend(
                [
                    f"{index}. `{candidate.get('candidate_id', '')}` "
                    f"score={total:.3f}",
                    f"   - Title: {candidate.get('title', '')}",
                    f"   - Source: `{candidate.get('source_id', '')}` "
                    f"({candidate.get('source_type', '')})",
                    f"   - Locator: {candidate.get('canonical_url', '')}",
                    f"   - Gate: {candidate.get('evidence_status', '')}",
                ]
            )
    else:
        lines.append("No candidates produced.")

    skipped = data.get("skipped_sources", [])
    if skipped:
        lines.extend(["", "## Skipped Sources", ""])
        for source in skipped:
            lines.append(
                f"- `{source.get('source_id', '')}` ({source.get('source_type', '')}): "
                f"{source.get('reason', '')}"
            )

    lines.extend(["", "## Notes", ""])
    for note in data.get("notes", []):
        lines.append(f"- {note}")
    return "\n".join(lines) + "\n"


def write_run_json(path: Path, run: DiscoveryRun) -> None:
    _write_json(path, run.as_dict())


def read_run_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _source_from_dict(raw: dict[str, Any]) -> SourceSubscription:
    return SourceSubscription(
        source_id=str(raw.get("source_id", "")).strip(),
        source_type=str(raw.get("source_type", "")).strip(),
        locator=str(raw.get("locator", "")).strip(),
        enabled_when=str(raw.get("enabled_when", "always")).strip(),
        title=str(raw.get("title", "")).strip(),
        quality_hint=str(raw.get("quality_hint", "unknown")).strip(),
        topics=_string_tuple(raw.get("topics")),
        policy=_policy_from_dict(raw.get("policy", {})),
    )


def _policy_from_dict(raw: dict[str, Any]) -> SourcePolicy:
    return SourcePolicy(
        fetch_mode=str(raw.get("fetch_mode", "metadata_only")).strip(),
        allow_network=bool(raw.get("allow_network", False)),
        allow_provider=bool(raw.get("allow_provider", False)),
        storage_rights=str(raw.get("storage_rights", "review_before_fetch")).strip(),
        prompt_injection_review=str(
            raw.get("prompt_injection_review", "required_before_fetch")
        ).strip(),
    )


def _candidate_inputs(
    profile: InterestProfile, source: SourceSubscription
) -> tuple[tuple[str, str, str], ...]:
    if source.source_type == "manual_url":
        title = source.title or source.locator
        snippet = "Manual URL registered for dry-run review; content was not fetched."
        return ((title, source.locator, snippet),)
    if source.source_type == "local_note":
        title = source.title or f"Local research note: {source.source_id}"
        url = f"memory://research-intake/{source.source_id}"
        snippet = source.locator or "Local note registered for dry-run review."
        return ((title, url, snippet),)
    if source.source_type == "fake_search":
        topics = source.topics or profile.include_topics
        rows: list[tuple[str, str, str]] = []
        for index, topic in enumerate(topics, start=1):
            slug = _slugify(topic)
            url = f"https://example.invalid/research-intake/{profile.profile_id}/{slug}/{index}"
            title = f"Dry-run discovery candidate: {topic}"
            snippet = (
                "Synthetic search result generated from the InterestProfile; "
                "no provider or network search was called."
            )
            rows.append((title, url, snippet))
        return tuple(rows)
    return ()


def _make_candidate(
    *,
    profile: InterestProfile,
    source: SourceSubscription,
    run_id: str,
    title: str,
    canonical_url: str,
    snippet: str,
    discovered_at: str,
    sequence: int,
) -> ResearchCandidate:
    dedupe_key = _dedupe_key(canonical_url)
    candidate_id = "candidate_" + _stable_id(run_id, source.source_id, dedupe_key, str(sequence))
    risk_flags = _risk_flags(source)
    return ResearchCandidate(
        candidate_id=candidate_id,
        run_id=run_id,
        source_id=source.source_id,
        source_type=source.source_type,
        canonical_url=canonical_url,
        title=title,
        raw_snippet=snippet,
        discovered_at=discovered_at,
        dedupe_key=dedupe_key,
        source_quality_hint=source.quality_hint,
        status="candidate_signal_only",
        scores=_score_candidate(profile, source, title=title, snippet=snippet),
        risk_flags=risk_flags,
        citation_excluded=True,
        evidence_status="not_evidence_until_fetched_and_chunked",
    )


def _make_snapshot(
    candidate: ResearchCandidate,
    source: SourceSubscription,
    *,
    snapshot_at: str,
) -> FetchSnapshot:
    metadata = {
        "candidate_id": candidate.candidate_id,
        "canonical_url": candidate.canonical_url,
        "title": candidate.title,
        "source_id": candidate.source_id,
        "source_type": candidate.source_type,
        "snapshot_at": snapshot_at,
    }
    content_hash = _hash_dict(metadata)
    return FetchSnapshot(
        snapshot_id="snapshot_" + _stable_id(candidate.candidate_id, content_hash),
        candidate_id=candidate.candidate_id,
        snapshot_at=snapshot_at,
        fetched_at=None,
        fetch_method="metadata_only_no_network",
        fetch_status="not_fetched_dry_run",
        content_hash=content_hash,
        raw_content_path=None,
        source_bundle_ref=None,
        storage_rights=source.policy.storage_rights,
        prompt_injection_review=source.policy.prompt_injection_review,
        promotion_gate="requires_fetch_extract_chunk_citation",
    )


def _score_candidate(
    profile: InterestProfile,
    source: SourceSubscription,
    *,
    title: str,
    snippet: str,
) -> dict[str, float]:
    text = " ".join([title, snippet, source.locator, *source.topics]).lower()
    include_hits = sum(1 for topic in profile.include_topics if topic.lower() in text)
    exclude_hits = sum(1 for topic in profile.exclude_topics if topic.lower() in text)
    topic_affinity = include_hits / max(len(profile.include_topics), 1)
    source_quality = QUALITY_SCORES.get(source.quality_hint, QUALITY_SCORES["unknown"])
    safety = 1.0 if not source.policy.allow_network and not source.policy.allow_provider else 0.0
    total = (topic_affinity * 0.55) + (source_quality * 0.35) + (safety * 0.10)
    total = max(0.0, min(1.0, total - (exclude_hits * 0.25)))
    return {
        "topic_affinity": round(topic_affinity, 3),
        "source_quality": round(source_quality, 3),
        "policy_safety": round(safety, 3),
        "exclude_penalty": round(exclude_hits * 0.25, 3),
        "total": round(total, 3),
    }


def _risk_flags(source: SourceSubscription) -> tuple[str, ...]:
    flags = ["not_evidence"]
    if source.source_type == "manual_url":
        flags.append("untrusted_url_not_fetched")
    if source.source_type == "fake_search":
        flags.append("synthetic_candidate")
    if source.source_type == "local_note":
        flags.append("local_note_not_source_bundle")
    return tuple(flags)


def _run_dict(run: DiscoveryRun | dict[str, Any]) -> dict[str, Any]:
    if isinstance(run, DiscoveryRun):
        return run.as_dict()
    return run


def _source_enabled(source: SourceSubscription) -> bool:
    return source.enabled_when.strip().lower() not in DISABLED_VALUES


def _looks_like_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _dedupe_key(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme and parsed.netloc:
        path = parsed.path.rstrip("/") or "/"
        return f"{parsed.scheme}://{parsed.netloc.lower()}{path}"
    return value.strip().lower()


def _string_tuple(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        values = (value,)
    elif isinstance(value, list | tuple):
        values = tuple(value)
    else:
        values = (str(value),)
    return tuple(str(item).strip() for item in values if str(item).strip())


def _read_toml(path: Path) -> dict[str, Any]:
    with path.open("rb") as handle:
        return tomllib.load(handle)


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _hash_dict(data: dict[str, Any]) -> str:
    payload = json.dumps(data, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _stable_id(*parts: str) -> str:
    payload = "\0".join(parts).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()[:16]


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "topic"


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
