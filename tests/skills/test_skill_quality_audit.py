from __future__ import annotations

import importlib.util
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "validate_skill_quality_audit.py"


def _load_validator():
    spec = importlib.util.spec_from_file_location("validate_skill_quality_audit", SCRIPT_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _copy_minimal_skill_audit_repo(tmp_path: Path) -> Path:
    repo_copy = tmp_path / "repo"
    for path in (
        "control/skill_quality_audit.toml",
        "control/vendor_sources.lock.md",
        ".codex/skill_manifest.lock",
    ):
        source = REPO_ROOT / path
        target = repo_copy / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")

    for source in sorted((REPO_ROOT / ".agents" / "skills").glob("*/SKILL.md")):
        target = repo_copy / source.relative_to(REPO_ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
    return repo_copy


def test_skill_boundary_audit_is_valid() -> None:
    validator = _load_validator()

    errors = validator.validate_skill_quality_audit(
        REPO_ROOT / "control" / "skill_quality_audit.toml",
        repo_root=REPO_ROOT,
        manifest_path=REPO_ROOT / ".codex" / "skill_manifest.lock",
    )

    assert errors == []


def test_audit_is_not_a_second_skill_registry() -> None:
    audit_text = (REPO_ROOT / "control" / "skill_quality_audit.toml").read_text(
        encoding="utf-8"
    )

    assert "[[entries]]" not in audit_text
    assert "quality_profiles" not in audit_text
    assert "full_canonical" not in audit_text
    assert "source_lock =" not in audit_text


def test_every_research_x_skill_directory_is_manifested_and_grouped() -> None:
    validator = _load_validator()

    errors = validator.validate_skill_quality_audit(
        REPO_ROOT / "control" / "skill_quality_audit.toml",
        repo_root=REPO_ROOT,
        manifest_path=REPO_ROOT / ".codex" / "skill_manifest.lock",
    )
    joined = "\n".join(errors)

    assert "SKILL.md exists but manifest has no repo_skill entry" not in joined
    assert "manifest repo skills missing from repo_skill_groups" not in joined


def test_unmanifested_repo_skill_is_rejected(tmp_path: Path) -> None:
    validator = _load_validator()
    repo_copy = _copy_minimal_skill_audit_repo(tmp_path)
    extra_skill = repo_copy / ".agents" / "skills" / "unmanifested-skill"
    extra_skill.mkdir(parents=True)
    (extra_skill / "SKILL.md").write_text(
        "---\nname: unmanifested-skill\n---\n\n# Unmanifested\n",
        encoding="utf-8",
    )

    errors = validator.validate_skill_quality_audit(
        repo_copy / "control" / "skill_quality_audit.toml",
        repo_root=repo_copy,
        manifest_path=repo_copy / ".codex" / "skill_manifest.lock",
    )

    assert any(
        "SKILL.md exists but manifest has no repo_skill entry" in error for error in errors
    )


def test_retired_skill_cannot_reenter_active_skill_tree(tmp_path: Path) -> None:
    validator = _load_validator()
    repo_copy = _copy_minimal_skill_audit_repo(tmp_path)
    active_retired = repo_copy / ".agents" / "skills" / "research-x-goal-runner"
    active_retired.mkdir(parents=True)
    (active_retired / "SKILL.md").write_text(
        "---\nname: research-x-goal-runner\n---\n\n# Retired Copy\n",
        encoding="utf-8",
    )

    errors = validator.validate_skill_quality_audit(
        repo_copy / "control" / "skill_quality_audit.toml",
        repo_root=repo_copy,
        manifest_path=repo_copy / ".codex" / "skill_manifest.lock",
    )

    assert any(
        "retired Skill must not reenter active .agents/skills" in error for error in errors
    )


def test_manifest_obligations_do_not_live_in_active_skill_text() -> None:
    for skill_path in sorted((REPO_ROOT / ".agents" / "skills").glob("*/SKILL.md")):
        text = skill_path.read_text(encoding="utf-8")
        assert "## Manifest Obligations" not in text, skill_path
