from __future__ import annotations

import argparse
import sys
import tomllib
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_AUDIT = REPO_ROOT / "control" / "skill_quality_audit.toml"
DEFAULT_MANIFEST = REPO_ROOT / ".codex" / "skill_manifest.lock"


def load_toml(path: Path) -> dict[str, Any]:
    with path.open("rb") as handle:
        return tomllib.load(handle)


def validate_skill_quality_audit(
    audit_path: Path = DEFAULT_AUDIT,
    *,
    repo_root: Path = REPO_ROOT,
    manifest_path: Path = DEFAULT_MANIFEST,
) -> list[str]:
    errors: list[str] = []
    if not audit_path.exists():
        return [f"audit missing: {audit_path}"]
    try:
        audit = load_toml(audit_path)
    except tomllib.TOMLDecodeError as exc:
        return [f"audit TOML parse failed: {exc}"]

    if audit.get("audit_version") != 2:
        errors.append("audit_version must be 2")

    _validate_policy(audit.get("policy"), errors)
    canonical_sources = _validate_canonical_sources(audit, repo_root, errors)
    manifest_names = _manifest_names(manifest_path, errors)

    _validate_repo_skill_tree(repo_root, manifest_names, errors)
    _validate_repo_skill_groups(audit, manifest_names, errors)
    _validate_codex_watchlist(audit, errors)
    _validate_retired_project_skills(audit, repo_root, errors)
    _validate_not_second_registry(audit, errors)
    _validate_canonical_boundary_text(canonical_sources, errors)
    return errors


def _validate_policy(policy: object, errors: list[str]) -> None:
    if not isinstance(policy, dict):
        errors.append("[policy] table is required")
        return
    expected_false = {
        "auto_rewrite_allowed",
        "provider_or_external_action_allowed",
    }
    for key in expected_false:
        if policy.get(key) is not False:
            errors.append(f"policy.{key} must be false")
    expected_true = {
        "skills_are_audit_targets_not_instructions",
        "audit_is_not_registry",
        "repo_skills_must_be_manifested",
        "codex_foundation_details_are_external",
        "retired_project_skills_must_stay_out_of_research_x_agents",
    }
    for key in expected_true:
        if policy.get(key) is not True:
            errors.append(f"policy.{key} must be true")


def _validate_canonical_sources(
    audit: dict[str, Any],
    repo_root: Path,
    errors: list[str],
) -> dict[str, Path]:
    raw_sources = audit.get("canonical_sources")
    if not isinstance(raw_sources, dict):
        errors.append("[canonical_sources] table is required")
        return {}
    required = {
        "repo_skill_manifest",
        "research_x_adoption_registry",
        "research_x_vendor_sources",
        "codex_foundation_registry",
        "codex_foundation_vendor_sources",
        "retired_project_skill_archive",
    }
    missing = sorted(required - set(raw_sources))
    if missing:
        errors.append("canonical_sources missing: " + ", ".join(missing))

    resolved: dict[str, Path] = {}
    for key, value in raw_sources.items():
        path = _resolve_path(str(value), repo_root)
        resolved[str(key)] = path
        if not path.exists():
            errors.append(f"canonical_sources.{key} missing: {value}")
    return resolved


def _manifest_names(manifest_path: Path, errors: list[str]) -> set[str]:
    if not manifest_path.exists():
        errors.append(f"manifest missing: {manifest_path}")
        return set()
    manifest = load_toml(manifest_path)
    entries = manifest.get("entries", [])
    if not isinstance(entries, list):
        errors.append("manifest entries must be a list")
        return set()
    return {
        str(entry["name"])
        for entry in entries
        if isinstance(entry, dict) and entry.get("entry_type") == "repo_skill"
    }


def _validate_repo_skill_tree(
    repo_root: Path,
    manifest_names: set[str],
    errors: list[str],
) -> None:
    skill_root = repo_root / ".agents" / "skills"
    if not skill_root.exists():
        errors.append(f"research_x skill root missing: {skill_root}")
        return
    discovered: set[str] = set()
    for child in sorted(path for path in skill_root.iterdir() if path.is_dir()):
        skill_path = child / "SKILL.md"
        if not skill_path.exists():
            errors.append(f"{child.name}: directory under .agents/skills has no SKILL.md")
            continue
        discovered.add(child.name)
        if child.name not in manifest_names:
            errors.append(f"{child.name}: SKILL.md exists but manifest has no repo_skill entry")
        if "## Manifest Obligations" in skill_path.read_text(encoding="utf-8"):
            errors.append(
                f"{child.name}: manifest obligations belong in the manifest, not SKILL.md"
            )
    missing_from_tree = sorted(manifest_names - discovered)
    if missing_from_tree:
        errors.append(
            "manifest repo skills missing from .agents/skills: "
            + ", ".join(missing_from_tree)
        )


def _validate_repo_skill_groups(
    audit: dict[str, Any],
    manifest_names: set[str],
    errors: list[str],
) -> None:
    groups = audit.get("repo_skill_groups", [])
    if not isinstance(groups, list) or not groups:
        errors.append("at least one [[repo_skill_groups]] item is required")
        return

    grouped: set[str] = set()
    for group in groups:
        if not isinstance(group, dict):
            errors.append("repo_skill_groups item must be a table")
            continue
        name = str(group.get("name", ""))
        members = group.get("members", [])
        decision = str(group.get("decision", ""))
        preserve = str(group.get("preserve", ""))
        if not name:
            errors.append("repo_skill_groups item missing name")
        if not isinstance(members, list) or len(members) < 2:
            errors.append(f"{name}: repo_skill_groups.members needs at least two entries")
            continue
        grouped.update(str(member) for member in members)
        if not decision:
            errors.append(f"{name}: repo_skill_groups.decision is required")
        if not preserve:
            errors.append(f"{name}: repo_skill_groups.preserve is required")
        unknown = sorted(str(member) for member in members if str(member) not in manifest_names)
        if unknown:
            errors.append(f"{name}: unknown repo Skill members: {', '.join(unknown)}")

    missing_from_groups = sorted(manifest_names - grouped)
    if missing_from_groups:
        errors.append(
            "manifest repo skills missing from repo_skill_groups: "
            + ", ".join(missing_from_groups)
        )


def _validate_codex_watchlist(audit: dict[str, Any], errors: list[str]) -> None:
    watchlist = audit.get("codex_foundation_watchlist", [])
    if not isinstance(watchlist, list) or not watchlist:
        errors.append("at least one [[codex_foundation_watchlist]] item is required")
        return
    for item in watchlist:
        if not isinstance(item, dict):
            errors.append("codex_foundation_watchlist item must be a table")
            continue
        if not item.get("name"):
            errors.append("codex_foundation_watchlist item missing name")
        members = item.get("members", [])
        if not isinstance(members, list) or len(members) < 2:
            errors.append(f"{item.get('name', '<watchlist>')}: members needs at least two entries")
        if not str(item.get("decision", "")).strip():
            errors.append(f"{item.get('name', '<watchlist>')}: decision is required")


def _validate_retired_project_skills(
    audit: dict[str, Any],
    repo_root: Path,
    errors: list[str],
) -> None:
    retired = audit.get("retired_project_skills", [])
    if not isinstance(retired, list) or not retired:
        errors.append("at least one [[retired_project_skills]] item is required")
        return
    active_skill_root = repo_root / ".agents" / "skills"
    for item in retired:
        if not isinstance(item, dict):
            errors.append("retired_project_skills item must be a table")
            continue
        name = str(item.get("name", ""))
        path_value = str(item.get("path", ""))
        decision = str(item.get("decision", ""))
        if not name:
            errors.append("retired_project_skills item missing name")
        if "retired" not in decision:
            errors.append(f"{name}: retired decision must mention retired")
        path = _resolve_path(path_value, repo_root)
        if not path.exists():
            errors.append(f"{name}: retired Skill archive missing: {path_value}")
        if (active_skill_root / name / "SKILL.md").exists():
            errors.append(f"{name}: retired Skill must not reenter active .agents/skills")


def _validate_not_second_registry(audit: dict[str, Any], errors: list[str]) -> None:
    forbidden_top_level = {"entries", "required_fields", "quality_profiles", "overlap_groups"}
    present = sorted(forbidden_top_level & set(audit))
    if present:
        errors.append("audit must not recreate a full registry: " + ", ".join(present))


def _validate_canonical_boundary_text(
    canonical_sources: dict[str, Path],
    errors: list[str],
) -> None:
    vendor = canonical_sources.get("research_x_vendor_sources")
    if vendor and vendor.exists():
        text = vendor.read_text(encoding="utf-8")
        for phrase in (
            "not permission to install, clone, enable, or call",
            "Codex foundation candidates belong to `maasa/.codex`",
        ):
            if phrase not in text:
                errors.append(f"research_x_vendor_sources missing boundary phrase: {phrase}")


def _resolve_path(value: str, repo_root: Path) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return repo_root / path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate compact Skill boundary audit.")
    parser.add_argument("--audit", type=Path, default=DEFAULT_AUDIT)
    args = parser.parse_args(argv)

    errors = validate_skill_quality_audit(args.audit)
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print(f"skill boundary audit ok: {args.audit}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
