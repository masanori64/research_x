from __future__ import annotations

import importlib.util
import shutil
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "validate_skill_manifest.py"


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
        source_lock_path=REPO_ROOT / ".codex" / "vendor_sources.lock.md",
    )
    assert errors == []


def test_external_enabled_requires_pin_review_and_negative_tests(tmp_path: Path) -> None:
    validator = _load_validator()
    manifest = tmp_path / "skill_manifest.lock"
    source_lock = tmp_path / "vendor_sources.lock.md"
    shutil.copy2(REPO_ROOT / ".codex" / "skill_manifest.lock", manifest)
    shutil.copy2(REPO_ROOT / ".codex" / "vendor_sources.lock.md", source_lock)
    text = manifest.read_text(encoding="utf-8")
    text = text.replace('enabled = false', 'enabled = true', 9)
    text = text.replace('implicit_invocation = false', 'implicit_invocation = true', 1)
    manifest.write_text(text, encoding="utf-8")

    errors = validator.validate_manifest(
        manifest,
        repo_root=REPO_ROOT,
        source_lock_path=source_lock,
    )

    joined = "\n".join(errors)
    assert "enabled external entry requires a pinned commit" in joined
    assert "enabled external entry requires approved review_status" in joined
    assert "enabled external entry requires negative_trigger_tests=present" in joined


def test_repo_skill_path_and_frontmatter_are_checked(tmp_path: Path) -> None:
    validator = _load_validator()
    manifest = tmp_path / "skill_manifest.lock"
    source_lock = tmp_path / "vendor_sources.lock.md"
    shutil.copy2(REPO_ROOT / ".codex" / "skill_manifest.lock", manifest)
    shutil.copy2(REPO_ROOT / ".codex" / "vendor_sources.lock.md", source_lock)
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
