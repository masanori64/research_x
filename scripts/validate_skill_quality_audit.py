from __future__ import annotations

import argparse
import sys
import tomllib
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_AUDIT = REPO_ROOT / "control" / "skill_quality_audit.toml"
DEFAULT_MANIFEST = REPO_ROOT / ".codex" / "skill_manifest.lock"
DEFAULT_FOUNDATION_REGISTRY = Path(
    "C:/Users/maasa/.codex/foundation/codex-foundation-registry.toml"
)


def load_toml(path: Path) -> dict[str, Any]:
    with path.open("rb") as handle:
        return tomllib.load(handle)


def validate_skill_quality_audit(
    audit_path: Path = DEFAULT_AUDIT,
    *,
    repo_root: Path = REPO_ROOT,
    manifest_path: Path = DEFAULT_MANIFEST,
    foundation_registry_path: Path = DEFAULT_FOUNDATION_REGISTRY,
) -> list[str]:
    errors: list[str] = []
    if not audit_path.exists():
        return [f"audit missing: {audit_path}"]
    try:
        audit = load_toml(audit_path)
    except tomllib.TOMLDecodeError as exc:
        return [f"audit TOML parse failed: {exc}"]

    _validate_policy(audit, errors)
    required_fields = set(audit.get("required_fields", {}).get("entry", []))
    if not required_fields:
        errors.append("required_fields.entry must be defined")

    profiles = audit.get("quality_profiles", {})
    if not isinstance(profiles, dict) or not profiles:
        errors.append("quality_profiles must be defined")
        profiles = {}

    overlap_groups = _load_overlap_groups(audit, errors)
    entries = audit.get("entries", [])
    if not isinstance(entries, list) or not entries:
        errors.append("at least one [[entries]] item is required")
        entries = []

    manifest_names = _manifest_names(manifest_path, errors)
    foundation_names, foundation_surfaces = _foundation_registry_index(
        foundation_registry_path,
        errors,
    )

    names: set[str] = set()
    active_research_x_names: set[str] = set()
    for index, entry in enumerate(entries, start=1):
        if not isinstance(entry, dict):
            errors.append(f"entry {index}: must be a table")
            continue
        name = str(entry.get("name", f"<entry {index}>"))
        if name in names:
            errors.append(f"{name}: duplicate audit entry")
        names.add(name)
        missing = sorted(required_fields - set(entry))
        if missing:
            errors.append(f"{name}: missing audit fields: {', '.join(missing)}")
            continue
        _validate_entry(
            name,
            entry,
            profiles,
            overlap_groups,
            repo_root,
            manifest_names,
            foundation_names,
            foundation_surfaces,
            active_research_x_names,
            errors,
        )

    if manifest_names:
        missing_from_audit = sorted(manifest_names - active_research_x_names)
        extra_in_audit = sorted(active_research_x_names - manifest_names)
        if missing_from_audit:
            errors.append(
                "active research_x manifest skills missing from audit: "
                + ", ".join(missing_from_audit)
            )
        if extra_in_audit:
            errors.append(
                "active research_x audit skills missing from manifest: "
                + ", ".join(extra_in_audit)
            )

    _validate_research_x_skill_tree(repo_root, manifest_names, errors)
    return errors


def _validate_policy(audit: dict[str, Any], errors: list[str]) -> None:
    policy = audit.get("policy")
    if not isinstance(policy, dict):
        errors.append("[policy] table is required")
        return
    expected_false = {
        "conservative_minimalism_allowed",
        "auto_rewrite_allowed",
        "provider_or_external_action_allowed",
    }
    for key in expected_false:
        if policy.get(key) is not False:
            errors.append(f"policy.{key} must be false")
    expected_true = {
        "skills_are_audit_targets_not_instructions",
        "active_research_x_skills_must_be_manifested",
        "codex_foundation_skills_are_external_owner",
        "retired_project_skills_must_stay_out_of_research_x_agents",
    }
    for key in expected_true:
        if policy.get(key) is not True:
            errors.append(f"policy.{key} must be true")


def _load_overlap_groups(
    audit: dict[str, Any],
    errors: list[str],
) -> dict[str, set[str]]:
    groups: dict[str, set[str]] = {}
    raw_groups = audit.get("overlap_groups", [])
    if not isinstance(raw_groups, list) or not raw_groups:
        errors.append("at least one [[overlap_groups]] item is required")
        return groups
    for group in raw_groups:
        if not isinstance(group, dict):
            errors.append("overlap group must be a table")
            continue
        name = str(group.get("name", ""))
        members = group.get("members", [])
        judgment = str(group.get("judgment", ""))
        if not name:
            errors.append("overlap group missing name")
            continue
        if not isinstance(members, list) or len(members) < 2:
            errors.append(f"{name}: overlap group needs at least two members")
            continue
        if not judgment:
            errors.append(f"{name}: overlap group needs judgment")
        groups[name] = {str(member) for member in members}
    return groups


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


def _foundation_registry_index(
    registry_path: Path,
    errors: list[str],
) -> tuple[set[str], set[str]]:
    if not registry_path.exists():
        return set(), set()
    registry = load_toml(registry_path)
    entries = registry.get("candidates", [])
    if not isinstance(entries, list):
        errors.append("foundation registry candidates must be a list")
        return set(), set()
    names = {str(entry["name"]) for entry in entries if isinstance(entry, dict)}
    surfaces = {
        str(entry["active_surface"]).replace("\\", "/")
        for entry in entries
        if isinstance(entry, dict) and entry.get("active_surface")
    }
    return names, surfaces


def _validate_entry(
    name: str,
    entry: dict[str, Any],
    profiles: dict[str, Any],
    overlap_groups: dict[str, set[str]],
    repo_root: Path,
    manifest_names: set[str],
    foundation_names: set[str],
    foundation_surfaces: set[str],
    active_research_x_names: set[str],
    errors: list[str],
) -> None:
    owner = str(entry["owner_surface"])
    status = str(entry["lifecycle_status"])
    profile_name = str(entry["quality_profile"])
    decision = str(entry["decision"])
    group_name = str(entry["overlap_group"])
    path = _resolve_path(str(entry["path"]), repo_root)

    if profile_name not in profiles:
        errors.append(f"{name}: unknown quality_profile {profile_name!r}")
        return
    if group_name not in overlap_groups:
        errors.append(f"{name}: unknown overlap_group {group_name!r}")
    elif name not in overlap_groups[group_name]:
        errors.append(f"{name}: not listed as member of overlap_group {group_name}")

    if not str(entry["role"]).strip():
        errors.append(f"{name}: role must not be empty")
    if not str(entry["primary_trigger"]).strip():
        errors.append(f"{name}: primary_trigger must not be empty")
    if not str(entry["audit_rationale"]).strip():
        errors.append(f"{name}: audit_rationale must not be empty")
    if decision in {"keep", "active", "todo"}:
        errors.append(f"{name}: decision is too generic: {decision!r}")

    if owner == "research_x" and status == "active":
        active_research_x_names.add(name)
        if name not in manifest_names:
            errors.append(f"{name}: active research_x Skill missing from manifest")
        if not str(entry["path"]).startswith(".agents/skills/"):
            errors.append(f"{name}: active research_x Skill must live under .agents/skills")
    elif owner.startswith("codex_foundation") and status.startswith("active"):
        if not path.is_absolute():
            errors.append(f"{name}: active codex foundation Skill path must be absolute")
        registry_has_entry = (
            name in foundation_names
            or str(path).replace("\\", "/") in foundation_surfaces
        )
        if (
            foundation_names
            and not registry_has_entry
            and "bridge" not in profile_name
            and "bridge" not in decision
        ):
            errors.append(f"{name}: active codex foundation Skill missing from registry")
    elif status == "retired":
        if str(entry["path"]).startswith(".agents/skills/"):
            errors.append(f"{name}: retired Skill must not live under active .agents/skills")
        if "retired" not in decision:
            errors.append(f"{name}: retired Skill decision must mention retired")
    else:
        errors.append(f"{name}: unsupported owner/status combination {owner}/{status}")

    if not path.exists():
        errors.append(f"{name}: audited SKILL.md path missing: {entry['path']}")
        return
    text = path.read_text(encoding="utf-8")
    declared_name = _frontmatter_name(text)
    if declared_name and declared_name != name:
        errors.append(
            f"{name}: SKILL.md frontmatter name mismatch "
            f"(audit={name!r}, skill={declared_name!r})"
        )

    required_sections = profiles[profile_name].get("required_sections", [])
    if not isinstance(required_sections, list):
        errors.append(f"{name}: quality profile required_sections must be a list")
        required_sections = []
    for section in required_sections:
        if str(section) not in text:
            errors.append(f"{name}: missing required section {section}")


def _validate_research_x_skill_tree(
    repo_root: Path,
    manifest_names: set[str],
    errors: list[str],
) -> None:
    skill_root = repo_root / ".agents" / "skills"
    if not skill_root.exists():
        errors.append(f"research_x skill root missing: {skill_root}")
        return
    for child in sorted(path for path in skill_root.iterdir() if path.is_dir()):
        skill_path = child / "SKILL.md"
        if not skill_path.exists():
            errors.append(f"{child.name}: directory under .agents/skills has no SKILL.md")
            continue
        if child.name not in manifest_names:
            errors.append(f"{child.name}: SKILL.md exists but manifest has no repo_skill entry")


def _resolve_path(value: str, repo_root: Path) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return repo_root / path


def _frontmatter_name(text: str) -> str | None:
    if not text.startswith("---"):
        return None
    parts = text.split("---", 2)
    if len(parts) < 3:
        return None
    for line in parts[1].splitlines():
        if line.startswith("name:"):
            return line.split(":", 1)[1].strip().strip('"').strip("'")
    return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate unified Skill quality audit.")
    parser.add_argument("--audit", type=Path, default=DEFAULT_AUDIT)
    args = parser.parse_args(argv)

    errors = validate_skill_quality_audit(args.audit)
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print(f"skill quality audit ok: {args.audit}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
