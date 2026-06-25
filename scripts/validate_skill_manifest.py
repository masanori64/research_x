from __future__ import annotations

import argparse
import re
import sys
import tomllib
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = REPO_ROOT / ".codex" / "skill_manifest.lock"
DEFAULT_SOURCE_LOCK = REPO_ROOT / "control" / "vendor_sources.lock.md"

REQUIRED_ENTRY_FIELDS = {
    "name",
    "entry_type",
    "source",
    "source_ref",
    "scope",
    "decision",
    "enabled",
    "implicit_invocation",
    "review_status",
    "risk",
    "allowed_scripts",
    "commit",
    "negative_trigger_tests",
    "notes",
}
VALID_ENTRY_TYPES = {
    "repo_skill",
    "third_party_skill_candidate",
    "reference_source",
    "connector_candidate",
    "provider_candidate",
    "tool_candidate",
    "rejected_source",
}
VALID_RISKS = {"low", "medium", "high"}
VALID_ALLOWED_SCRIPTS = {"repo_policy", "disabled", "reviewed_only"}
UNPINNED_VALUES = {"", "TBD", "TBD_PINNED_COMMIT", "latest", "main", "master"}
SOURCE_REF_RE = re.compile(r"^(repo|docs|S\d{2})$")


def load_manifest(path: Path) -> dict[str, Any]:
    with path.open("rb") as handle:
        return tomllib.load(handle)


def validate_manifest(
    manifest_path: Path = DEFAULT_MANIFEST,
    *,
    repo_root: Path = REPO_ROOT,
    source_lock_path: Path | None = DEFAULT_SOURCE_LOCK,
) -> list[str]:
    errors: list[str] = []
    if not manifest_path.exists():
        return [f"manifest missing: {manifest_path}"]
    try:
        manifest = load_manifest(manifest_path)
    except tomllib.TOMLDecodeError as exc:
        return [f"manifest TOML parse failed: {exc}"]

    if manifest.get("lockfile_version") != 1:
        errors.append("lockfile_version must be 1")
    policy = manifest.get("policy")
    if not isinstance(policy, dict):
        errors.append("[policy] table is required")
        policy = {}
    _validate_policy(policy, errors)

    entries = manifest.get("entries")
    if not isinstance(entries, list) or not entries:
        errors.append("at least one [[entries]] item is required")
        entries = []

    names: set[str] = set()
    source_refs: set[str] = set()
    repo_skill_count = 0
    enabled_external = []
    for index, entry in enumerate(entries, start=1):
        if not isinstance(entry, dict):
            errors.append(f"entry {index}: must be a table")
            continue
        name = str(entry.get("name", f"<entry {index}>"))
        if name in names:
            errors.append(f"{name}: duplicate entry name")
        names.add(name)
        missing = sorted(REQUIRED_ENTRY_FIELDS - set(entry))
        if missing:
            errors.append(f"{name}: missing fields: {', '.join(missing)}")
            continue
        source_ref = str(entry["source_ref"])
        source_refs.add(source_ref)
        _validate_entry_basics(name, entry, errors)
        if entry["entry_type"] == "repo_skill":
            repo_skill_count += 1
            _validate_repo_skill(name, entry, repo_root, errors)
        else:
            if bool(entry["enabled"]):
                enabled_external.append(name)
            _validate_external_entry(name, entry, policy, errors)

    if repo_skill_count == 0:
        errors.append("manifest must include repo-local skills")
    if enabled_external:
        errors.append(
            "external entries must remain disabled until reviewed: "
            + ", ".join(sorted(enabled_external))
        )
    if source_lock_path is not None:
        _validate_source_lock(source_lock_path, source_refs, errors)
    return errors


def _validate_policy(policy: dict[str, Any], errors: list[str]) -> None:
    expected_false = {
        "default_external_enabled",
        "connector_global_enabled_allowed",
        "provider_quota_calls_allowed",
        "bulk_install_allowed",
        "auto_merge_guidance_allowed",
    }
    expected_true = {
        "require_commit_pin_for_external_enabled",
        "require_human_review_for_external_enabled",
        "require_negative_trigger_tests_for_external_enabled",
    }
    for key in expected_false:
        if policy.get(key) is not False:
            errors.append(f"policy.{key} must be false")
    for key in expected_true:
        if policy.get(key) is not True:
            errors.append(f"policy.{key} must be true")
    if policy.get("repo_skills_path") != ".agents/skills":
        errors.append("policy.repo_skills_path must be .agents/skills")


def _validate_entry_basics(name: str, entry: dict[str, Any], errors: list[str]) -> None:
    if entry["entry_type"] not in VALID_ENTRY_TYPES:
        errors.append(f"{name}: invalid entry_type {entry['entry_type']!r}")
    if entry["risk"] not in VALID_RISKS:
        errors.append(f"{name}: invalid risk {entry['risk']!r}")
    if entry["allowed_scripts"] not in VALID_ALLOWED_SCRIPTS:
        errors.append(f"{name}: invalid allowed_scripts {entry['allowed_scripts']!r}")
    if not isinstance(entry["enabled"], bool):
        errors.append(f"{name}: enabled must be a boolean")
    if not isinstance(entry["implicit_invocation"], bool):
        errors.append(f"{name}: implicit_invocation must be a boolean")
    if not SOURCE_REF_RE.match(str(entry["source_ref"])):
        errors.append(f"{name}: source_ref must be repo, docs, or SNN")
    if str(entry["source"]).startswith("http") and " " in str(entry["source"]):
        errors.append(f"{name}: source URL contains whitespace")


def _validate_repo_skill(
    name: str,
    entry: dict[str, Any],
    repo_root: Path,
    errors: list[str],
) -> None:
    if not entry["enabled"]:
        errors.append(f"{name}: repo_skill entries should be enabled")
    if not entry["implicit_invocation"]:
        errors.append(f"{name}: repo_skill implicit_invocation should be true")
    if entry["review_status"] != "repo_owned":
        errors.append(f"{name}: repo_skill review_status must be repo_owned")
    if entry["allowed_scripts"] != "repo_policy":
        errors.append(f"{name}: repo_skill allowed_scripts must be repo_policy")
    if entry["source_ref"] != "repo":
        errors.append(f"{name}: repo_skill source_ref must be repo")

    path = repo_root / str(entry["source"])
    if not path.exists():
        errors.append(f"{name}: repo skill path missing: {entry['source']}")
        return
    declared_name = _frontmatter_name(path)
    if declared_name != name:
        errors.append(
            f"{name}: SKILL.md frontmatter name mismatch "
            f"(manifest={name!r}, skill={declared_name!r})"
        )


def _validate_external_entry(
    name: str,
    entry: dict[str, Any],
    policy: dict[str, Any],
    errors: list[str],
) -> None:
    if bool(entry["enabled"]):
        if policy.get("default_external_enabled") is not False:
            errors.append(f"{name}: external enabling requires default_external_enabled=false")
        if str(entry["commit"]) in UNPINNED_VALUES:
            errors.append(f"{name}: enabled external entry requires a pinned commit")
        if str(entry["review_status"]) not in {"approved", "repo_owned"}:
            errors.append(f"{name}: enabled external entry requires approved review_status")
        if str(entry["negative_trigger_tests"]) != "present":
            errors.append(f"{name}: enabled external entry requires negative_trigger_tests=present")
    else:
        if entry["implicit_invocation"]:
            errors.append(f"{name}: disabled external entries cannot have implicit_invocation=true")
    if entry["entry_type"] == "connector_candidate" and bool(entry["enabled"]):
        errors.append(f"{name}: connector candidates cannot be enabled globally")
    if entry["entry_type"] == "provider_candidate" and bool(entry["enabled"]):
        errors.append(f"{name}: provider candidates cannot be enabled during no-quota freeze")
    if entry["entry_type"] == "rejected_source":
        if bool(entry["enabled"]):
            errors.append(f"{name}: rejected_source entries must be disabled")
        if str(entry["review_status"]) != "rejected":
            errors.append(f"{name}: rejected_source review_status must be rejected")


def _validate_source_lock(
    source_lock_path: Path,
    source_refs: set[str],
    errors: list[str],
) -> None:
    if not source_lock_path.exists():
        errors.append(f"source lock missing: {source_lock_path}")
        return
    text = source_lock_path.read_text(encoding="utf-8")
    for ref in sorted(source_refs - {"repo", "docs"}):
        if f"| {ref} |" not in text:
            errors.append(f"source lock missing row for {ref}")


def _frontmatter_name(path: Path) -> str | None:
    text = path.read_text(encoding="utf-8")
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
    parser = argparse.ArgumentParser(description="Validate research_x Skill/source manifest lock.")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--source-lock", type=Path, default=DEFAULT_SOURCE_LOCK)
    args = parser.parse_args(argv)

    errors = validate_manifest(args.manifest, source_lock_path=args.source_lock)
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print(f"skill manifest ok: {args.manifest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
