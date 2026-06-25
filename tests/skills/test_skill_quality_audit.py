from __future__ import annotations

import importlib.util
import shutil
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "validate_skill_quality_audit.py"


def _load_validator():
    spec = importlib.util.spec_from_file_location("validate_skill_quality_audit", SCRIPT_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_skill_quality_audit_is_valid() -> None:
    validator = _load_validator()

    errors = validator.validate_skill_quality_audit(
        REPO_ROOT / "control" / "skill_quality_audit.toml",
        repo_root=REPO_ROOT,
        manifest_path=REPO_ROOT / ".codex" / "skill_manifest.lock",
    )

    assert errors == []


def test_every_research_x_skill_directory_is_manifested_and_audited() -> None:
    validator = _load_validator()
    errors = validator.validate_skill_quality_audit(
        REPO_ROOT / "control" / "skill_quality_audit.toml",
        repo_root=REPO_ROOT,
        manifest_path=REPO_ROOT / ".codex" / "skill_manifest.lock",
    )

    assert "directory under .agents/skills has no SKILL.md" not in "\n".join(errors)
    assert "SKILL.md exists but manifest has no repo_skill entry" not in "\n".join(errors)
    assert "active research_x manifest skills missing from audit" not in "\n".join(errors)


def test_unregistered_active_research_x_skill_is_rejected(tmp_path: Path) -> None:
    validator = _load_validator()
    repo_copy = tmp_path / "repo"
    shutil.copytree(REPO_ROOT / ".agents", repo_copy / ".agents")
    shutil.copytree(REPO_ROOT / ".codex", repo_copy / ".codex")
    shutil.copytree(REPO_ROOT / "control", repo_copy / "control")

    rogue = repo_copy / ".agents" / "skills" / "research-x-rogue-skill"
    rogue.mkdir()
    (rogue / "SKILL.md").write_text(
        "---\nname: research-x-rogue-skill\n---\n# research-x Rogue Skill\n",
        encoding="utf-8",
    )

    errors = validator.validate_skill_quality_audit(
        repo_copy / "control" / "skill_quality_audit.toml",
        repo_root=repo_copy,
        manifest_path=repo_copy / ".codex" / "skill_manifest.lock",
    )

    assert any("SKILL.md exists but manifest has no repo_skill entry" in error for error in errors)


def test_missing_canonical_section_is_rejected(tmp_path: Path) -> None:
    validator = _load_validator()
    repo_copy = tmp_path / "repo"
    shutil.copytree(REPO_ROOT / ".agents", repo_copy / ".agents")
    shutil.copytree(REPO_ROOT / ".codex", repo_copy / ".codex")
    shutil.copytree(REPO_ROOT / "control", repo_copy / "control")

    skill_path = (
        repo_copy
        / ".agents"
        / "skills"
        / "research-x-prompt-contract"
        / "SKILL.md"
    )
    text = skill_path.read_text(encoding="utf-8").replace("## Safety Gates\n", "", 1)
    skill_path.write_text(text, encoding="utf-8")

    errors = validator.validate_skill_quality_audit(
        repo_copy / "control" / "skill_quality_audit.toml",
        repo_root=repo_copy,
        manifest_path=repo_copy / ".codex" / "skill_manifest.lock",
    )

    assert any(
        error == "research-x-prompt-contract: missing required section ## Safety Gates"
        for error in errors
    )


def test_retired_skill_cannot_reenter_active_skill_tree(tmp_path: Path) -> None:
    validator = _load_validator()
    repo_copy = tmp_path / "repo"
    shutil.copytree(REPO_ROOT / ".agents", repo_copy / ".agents")
    shutil.copytree(REPO_ROOT / ".codex", repo_copy / ".codex")
    shutil.copytree(REPO_ROOT / "control", repo_copy / "control")

    audit_path = repo_copy / "control" / "skill_quality_audit.toml"
    text = audit_path.read_text(encoding="utf-8").replace(
        "C:/Users/maasa/.codex/foundation/project_skills/research_x_retired_codex_ops/research-x-goal-runner/SKILL.md",
        ".agents/skills/research-x-goal-runner/SKILL.md",
        1,
    )
    audit_path.write_text(text, encoding="utf-8")

    errors = validator.validate_skill_quality_audit(
        audit_path,
        repo_root=repo_copy,
        manifest_path=repo_copy / ".codex" / "skill_manifest.lock",
    )

    assert any(
        "retired Skill must not live under active .agents/skills" in error
        for error in errors
    )
