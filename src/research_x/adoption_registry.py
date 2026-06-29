from __future__ import annotations

import json
import re
import tomllib
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

DEFAULT_REGISTRY_PATH = Path("control") / "adoption_registry.toml"
DEFAULT_VENDOR_SOURCE_LOCK_PATH = Path("control") / "vendor_sources.lock.md"
SOURCE_REF_RE = re.compile(r"^S\d{2}$")
ALLOWED_ADOPTION_SHAPES = {
    "adopt",
    "bridge",
    "staging",
    "provider_gated",
    "historical",
}
ALLOWED_OWNER_SURFACES = {
    "codex_foundation",
    "research_x_tool",
    "research_x_bridge",
    "historical",
}
ALLOWED_STATUSES = {
    "implemented",
    "staged",
    "provider_gated",
    "historical",
    "external_owned",
}
PROVIDER_STOP_CONDITION_TOKENS = {
    "provider",
    "quota",
    "paid/free-tier",
    "trial-credit",
    "zero-dollar",
    "keyless",
    "external-network",
}


@dataclass(frozen=True)
class AdoptionCandidate:
    name: str
    category: str
    owner_surface: str
    adoption_shape: str
    status: str
    source_ref: str
    source_url: str
    active_artifact: str
    first_local_step: str
    promotion_gate: str
    stop_condition: str
    provider_or_quota: bool
    enabled: bool
    notes: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def load_adoption_registry(path: str | Path = DEFAULT_REGISTRY_PATH) -> dict[str, Any]:
    registry_path = Path(path)
    with registry_path.open("rb") as handle:
        return tomllib.load(handle)


def adoption_candidates(path: str | Path = DEFAULT_REGISTRY_PATH) -> tuple[AdoptionCandidate, ...]:
    registry = load_adoption_registry(path)
    return tuple(_candidate_from_raw(item) for item in registry.get("candidates", []))


def validate_adoption_registry(
    path: str | Path = DEFAULT_REGISTRY_PATH,
    *,
    repo_root: str | Path = ".",
    source_lock_path: str | Path | None = DEFAULT_VENDOR_SOURCE_LOCK_PATH,
) -> list[str]:
    registry_path = Path(path)
    root = Path(repo_root)
    errors: list[str] = []
    if not registry_path.exists():
        return [f"adoption registry missing: {registry_path}"]
    try:
        registry = load_adoption_registry(registry_path)
    except tomllib.TOMLDecodeError as exc:
        return [f"adoption registry TOML parse failed: {exc}"]

    if registry.get("registry_version") != 1:
        errors.append("registry_version must be 1")
    if registry.get("owner") != "research_x":
        errors.append("owner must be research_x")
    policy = registry.get("policy")
    if not isinstance(policy, dict):
        errors.append("[policy] table is required")
        policy = {}
    _validate_policy(policy, errors)

    raw_candidates = registry.get("candidates")
    if not isinstance(raw_candidates, list) or not raw_candidates:
        errors.append("at least one [[candidates]] item is required")
        raw_candidates = []

    names: set[str] = set()
    source_refs: set[str] = set()
    required_categories = {
        "tool_interface",
        "external_source_candidate",
        "retrieval_eval",
        "local_backend",
        "media_evidence",
        "control_artifact",
        "codex_foundation_bridge",
        "historical",
    }
    seen_categories: set[str] = set()
    for index, raw in enumerate(raw_candidates, start=1):
        if not isinstance(raw, dict):
            errors.append(f"candidate {index}: must be a table")
            continue
        name = str(raw.get("name") or f"<candidate {index}>")
        if name in names:
            errors.append(f"{name}: duplicate candidate name")
        names.add(name)
        seen_categories.add(str(raw.get("category") or ""))
        try:
            candidate = _candidate_from_raw(raw)
        except ValueError as exc:
            errors.append(f"{name}: {exc}")
            continue
        source_refs.add(candidate.source_ref)
        _validate_candidate(candidate, root, errors)

    missing_categories = sorted(required_categories - seen_categories)
    if missing_categories:
        errors.append("missing candidate categories: " + ", ".join(missing_categories))
    if source_lock_path is not None:
        _validate_source_lock(Path(source_lock_path), source_refs, errors)
    return errors


def adoption_audit(
    path: str | Path = DEFAULT_REGISTRY_PATH,
    *,
    repo_root: str | Path = ".",
) -> dict[str, Any]:
    errors = validate_adoption_registry(path, repo_root=repo_root)
    candidates = () if errors else adoption_candidates(path)
    summary: dict[str, Any] = {
        "status": "failed" if errors else "ok",
        "errors": errors,
        "counts": {},
        "candidates": [candidate.as_dict() for candidate in candidates],
    }
    for candidate in candidates:
        key = f"{candidate.owner_surface}:{candidate.adoption_shape}"
        summary["counts"][key] = int(summary["counts"].get(key, 0)) + 1
    return summary


def adoption_audit_json(
    path: str | Path = DEFAULT_REGISTRY_PATH,
    *,
    repo_root: str | Path = ".",
) -> str:
    return json.dumps(
        adoption_audit(path, repo_root=repo_root),
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    )


def format_adoption_audit(
    path: str | Path = DEFAULT_REGISTRY_PATH,
    *,
    repo_root: str | Path = ".",
) -> str:
    audit = adoption_audit(path, repo_root=repo_root)
    if audit["errors"]:
        lines = ["adoption registry failed:"]
        lines.extend(f"- {error}" for error in audit["errors"])
        return "\n".join(lines) + "\n"
    lines = ["adoption registry ok"]
    for key, count in sorted(audit["counts"].items()):
        lines.append(f"- {key}: {count}")
    return "\n".join(lines) + "\n"


def _candidate_from_raw(raw: dict[str, Any]) -> AdoptionCandidate:
    required = {
        "name",
        "category",
        "owner_surface",
        "adoption_shape",
        "status",
        "source_ref",
        "source_url",
        "active_artifact",
        "first_local_step",
        "promotion_gate",
        "stop_condition",
        "provider_or_quota",
        "enabled",
        "notes",
    }
    missing = sorted(required - set(raw))
    if missing:
        raise ValueError("missing fields: " + ", ".join(missing))
    return AdoptionCandidate(
        name=str(raw["name"]),
        category=str(raw["category"]),
        owner_surface=str(raw["owner_surface"]),
        adoption_shape=str(raw["adoption_shape"]),
        status=str(raw["status"]),
        source_ref=str(raw["source_ref"]),
        source_url=str(raw["source_url"]),
        active_artifact=str(raw["active_artifact"]),
        first_local_step=str(raw["first_local_step"]),
        promotion_gate=str(raw["promotion_gate"]),
        stop_condition=str(raw["stop_condition"]),
        provider_or_quota=bool(raw["provider_or_quota"]),
        enabled=bool(raw["enabled"]),
        notes=str(raw["notes"]),
    )


def _validate_policy(policy: dict[str, Any], errors: list[str]) -> None:
    expected = {
        "provider_api_only_hard_block": True,
        "research_x_is_codex_foundation": False,
        "codex_foundation_home": "C:/Users/maasa/.codex",
    }
    for key, value in expected.items():
        if policy.get(key) != value:
            errors.append(f"policy.{key} must be {value!r}")


def _validate_candidate(
    candidate: AdoptionCandidate,
    repo_root: Path,
    errors: list[str],
) -> None:
    if candidate.owner_surface not in ALLOWED_OWNER_SURFACES:
        errors.append(f"{candidate.name}: invalid owner_surface {candidate.owner_surface!r}")
    if candidate.adoption_shape not in ALLOWED_ADOPTION_SHAPES:
        errors.append(f"{candidate.name}: invalid adoption_shape {candidate.adoption_shape!r}")
    if candidate.status not in ALLOWED_STATUSES:
        errors.append(f"{candidate.name}: invalid status {candidate.status!r}")
    if not candidate.first_local_step.strip():
        errors.append(f"{candidate.name}: first_local_step is required")
    if not candidate.promotion_gate.strip():
        errors.append(f"{candidate.name}: promotion_gate is required")
    if not candidate.stop_condition.strip():
        errors.append(f"{candidate.name}: stop_condition is required")
    if candidate.provider_or_quota and candidate.adoption_shape != "provider_gated":
        errors.append(f"{candidate.name}: provider/quota candidate must be provider_gated")
    if candidate.provider_or_quota:
        normalized_stop = candidate.stop_condition.casefold()
        missing_tokens = sorted(
            token
            for token in PROVIDER_STOP_CONDITION_TOKENS
            if token not in normalized_stop
        )
        if missing_tokens:
            errors.append(
                f"{candidate.name}: provider stop_condition missing: "
                + ", ".join(missing_tokens)
            )
        notes_normalized = candidate.notes.casefold()
        if "not evidence" not in notes_normalized and "candidate" not in notes_normalized:
            errors.append(
                f"{candidate.name}: provider candidate notes must say output is candidate-only"
            )
    if candidate.adoption_shape == "provider_gated" and candidate.enabled:
        errors.append(f"{candidate.name}: provider_gated candidate cannot be enabled")
    if candidate.owner_surface == "codex_foundation":
        if candidate.adoption_shape != "bridge":
            errors.append(f"{candidate.name}: research_x may keep only bridge entries for .codex")
        if candidate.enabled:
            errors.append(f"{candidate.name}: .codex-owned entries cannot be enabled in research_x")
    if candidate.adoption_shape == "historical":
        if candidate.owner_surface != "historical":
            errors.append(f"{candidate.name}: historical entries must use historical owner_surface")
        if candidate.enabled:
            errors.append(f"{candidate.name}: historical entries cannot be enabled")
    if candidate.adoption_shape == "adopt":
        artifact_path = repo_root / candidate.active_artifact
        if not artifact_path.exists():
            errors.append(f"{candidate.name}: adopted active_artifact missing")


def _validate_source_lock(
    source_lock_path: Path,
    source_refs: set[str],
    errors: list[str],
) -> None:
    if not source_lock_path.exists():
        errors.append(f"source lock missing: {source_lock_path}")
        return
    text = source_lock_path.read_text(encoding="utf-8")
    for source_ref in sorted(ref for ref in source_refs if SOURCE_REF_RE.match(ref)):
        if f"| {source_ref} |" not in text:
            errors.append(f"source lock missing row for {source_ref}")
