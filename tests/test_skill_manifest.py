from __future__ import annotations

import importlib.util
import re
import shutil
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "validate_skill_manifest.py"
NEW_REPO_SKILLS = {
    "research-x-research-intake",
    "research-x-prompt-contract",
    "research-x-implementation-plan-flow",
}
REQUIRED_NEW_SKILL_SECTIONS = (
    "## Purpose",
    "## Use When",
    "## Do Not Use When",
    "## Inputs",
    "## Outputs",
    "## Steps",
    "## Safety Gates",
    "## Negative Triggers",
    "## Verification",
)


def _load_validator():
    spec = importlib.util.spec_from_file_location("validate_skill_manifest", SCRIPT_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_skill_manifest_lock_is_valid() -> None:
    validator = _load_validator()
    errors = validator.validate_manifest(
        REPO_ROOT / ".codex" / "skill_manifest.lock",
        repo_root=REPO_ROOT,
        source_lock_path=REPO_ROOT / "control" / "vendor_sources.lock.md",
    )
    assert errors == []


def test_new_repo_skills_are_manifested_and_complete() -> None:
    validator = _load_validator()
    manifest = validator.load_manifest(REPO_ROOT / ".codex" / "skill_manifest.lock")
    entries = {entry["name"]: entry for entry in manifest["entries"]}

    assert set(entries) >= NEW_REPO_SKILLS
    for name in NEW_REPO_SKILLS:
        entry = entries[name]
        assert entry["entry_type"] == "repo_skill"
        assert entry["enabled"] is True
        assert entry["implicit_invocation"] is True
        skill_path = REPO_ROOT / entry["source"]
        agent_path = skill_path.parent / "agents" / "openai.yaml"
        assert skill_path.exists()
        assert agent_path.exists()

        skill_text = skill_path.read_text(encoding="utf-8")
        for section in REQUIRED_NEW_SKILL_SECTIONS:
            assert section in skill_text, f"{name} is missing {section}"

        agent_text = agent_path.read_text(encoding="utf-8")
        assert "allow_implicit_invocation: true" in agent_text


def test_external_candidates_do_not_belong_in_skill_manifest(tmp_path: Path) -> None:
    validator = _load_validator()
    manifest = tmp_path / "skill_manifest.lock"
    source_lock = tmp_path / "vendor_sources.lock.md"
    shutil.copy2(REPO_ROOT / ".codex" / "skill_manifest.lock", manifest)
    shutil.copy2(REPO_ROOT / "control" / "vendor_sources.lock.md", source_lock)
    text = manifest.read_text(encoding="utf-8") + """

[[entries]]
name = "external-example"
entry_type = "third_party_skill_candidate"
source = "https://example.invalid/skill"
source_ref = "S11"
scope = "global_optional"
decision = "review_then_optional"
enabled = false
implicit_invocation = false
review_status = "unreviewed"
risk = "medium"
allowed_scripts = "disabled"
commit = "TBD_PINNED_COMMIT"
negative_trigger_tests = "required_before_enable"
notes = "External candidates belong in the source lock, not the repo Skill manifest."
"""
    manifest.write_text(text, encoding="utf-8")

    errors = validator.validate_manifest(
        manifest,
        repo_root=REPO_ROOT,
        source_lock_path=source_lock,
    )

    joined = "\n".join(errors)
    assert "non-repo entries belong in control/vendor_sources.lock.md" in joined


def test_repo_skill_path_and_frontmatter_are_checked(tmp_path: Path) -> None:
    validator = _load_validator()
    manifest = tmp_path / "skill_manifest.lock"
    source_lock = tmp_path / "vendor_sources.lock.md"
    shutil.copy2(REPO_ROOT / ".codex" / "skill_manifest.lock", manifest)
    shutil.copy2(REPO_ROOT / "control" / "vendor_sources.lock.md", source_lock)
    text = manifest.read_text(encoding="utf-8").replace(
        ".agents/skills/research-x-provider-gate/SKILL.md",
        ".agents/skills/research-x-provider-gate/MISSING.md",
        1,
    )
    manifest.write_text(text, encoding="utf-8")

    errors = validator.validate_manifest(
        manifest,
        repo_root=REPO_ROOT,
        source_lock_path=source_lock,
    )

    assert any("repo skill path missing" in error for error in errors)


def test_repo_skill_reference_links_exist() -> None:
    reference_re = re.compile(r"`(\.\./\.\./skill-references/[^`]+\.md)`")
    skill_paths = sorted((REPO_ROOT / ".agents" / "skills").glob("research-x-*/SKILL.md"))

    assert skill_paths
    for skill_path in skill_paths:
        text = skill_path.read_text(encoding="utf-8")
        for match in reference_re.finditer(text):
            target = (skill_path.parent / match.group(1)).resolve()
            assert target.exists(), f"{skill_path} references missing file {match.group(1)}"
