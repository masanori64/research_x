from __future__ import annotations

import importlib
import importlib.util
import sys
import tomllib
from pathlib import Path

import pytest

from research_x.codex_bridge import (
    bridge_contract,
    validate_codex_to_research_x_payload,
)

REPO_CODEX_IMPROVEMENT = Path("src/research_x/codex_improvement")
CODEX_FOUNDATION = Path("C:/Users/maasa/.codex/foundation")
CODEX_IMPROVEMENT = CODEX_FOUNDATION / "codex_improvement"
REGISTRY = Path(".codex/adoption_registry.toml")


def test_research_x_no_longer_owns_codex_improvement_package() -> None:
    assert not REPO_CODEX_IMPROVEMENT.exists()
    assert importlib.util.find_spec("research_x.codex_improvement") is None


def test_codex_foundation_package_exists_on_owner_machine_and_is_importable() -> None:
    if not CODEX_IMPROVEMENT.exists():
        pytest.skip("global .codex foundation package is outside the portable repository")

    for filename in (
        "__init__.py",
        "__main__.py",
        "cli.py",
        "pipeline.py",
        "signals.schema.json",
        "skill_lifecycle.py",
        "overimplementation_guard.py",
    ):
        assert (CODEX_IMPROVEMENT / filename).exists()

    sys.path.insert(0, str(CODEX_FOUNDATION))
    try:
        package = importlib.import_module("codex_improvement")
        pipeline = importlib.import_module("codex_improvement.pipeline")
        lifecycle = importlib.import_module("codex_improvement.skill_lifecycle")
    finally:
        sys.path.remove(str(CODEX_FOUNDATION))

    assert package.__name__ == "codex_improvement"
    assert pipeline.capture_signal.__name__ == "capture_signal"
    assert lifecycle.validate_skill_lifecycle_input.__name__ == "validate_skill_lifecycle_input"


def test_research_x_registry_points_codex_self_improvement_to_external_owner() -> None:
    registry = tomllib.loads(REGISTRY.read_text(encoding="utf-8"))
    candidates = {item["name"]: item for item in registry["candidates"]}
    self_improvement = candidates["codex_self_improvement_pack"]

    assert self_improvement["owner_surface"] == "codex_foundation"
    assert self_improvement["adoption_shape"] == "bridge"
    assert self_improvement["enabled"] is False
    assert self_improvement["source_url"] == (
        "C:/Users/maasa/.codex/foundation/codex-foundation-registry.toml"
    )
    assert self_improvement["active_artifact"] == (
        "C:/Users/maasa/.codex/foundation/codex_improvement/pipeline.py"
    )
    assert not self_improvement["active_artifact"].startswith("src/research_x/")


def test_research_x_bridge_stays_thin_without_codex_runtime_ownership() -> None:
    contract = bridge_contract()

    assert "query" in contract.codex_to_research_x_allowed_inputs
    assert "citation_ready_answer" in contract.research_x_to_codex_allowed_outputs
    assert validate_codex_to_research_x_payload(
        {
            "contract_version": contract.contract_version,
            "query": "引用可能な根拠だけを返して",
            "codex_transcript": "must not cross the bridge",
        }
    ) == ["codex_to_research_x: forbidden field 'codex_transcript'"]
