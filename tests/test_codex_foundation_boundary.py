from __future__ import annotations

import importlib
import importlib.util
import sys
import tomllib
from pathlib import Path

import pytest

from research_x.tool_interface.codex_bridge import (
    bridge_contract,
    validate_codex_to_research_x_payload,
)

REPO_CODEX_IMPROVEMENT = Path("src/research_x/codex_improvement")
CODEX_FOUNDATION = Path("C:/Users/maasa/.codex/foundation")
CODEX_IMPROVEMENT = CODEX_FOUNDATION / "codex_improvement"
CODEX_FOUNDATION_REGISTRY = CODEX_FOUNDATION / "codex-foundation-registry.toml"
CODEX_FOUNDATION_SOURCE_LOCK = CODEX_FOUNDATION / "vendor_sources.lock.md"
REGISTRY = Path("control/adoption_registry.toml")


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


def test_research_x_registry_points_codex_details_to_external_owner() -> None:
    registry = tomllib.loads(REGISTRY.read_text(encoding="utf-8"))
    candidates = {item["name"]: item for item in registry["candidates"]}
    bridge = candidates["codex_foundation_registry_bridge"]

    assert bridge["owner_surface"] == "codex_foundation"
    assert bridge["adoption_shape"] == "bridge"
    assert bridge["enabled"] is False
    assert bridge["source_url"] == (
        "C:/Users/maasa/.codex/foundation/codex-foundation-registry.toml"
    )
    assert bridge["active_artifact"] == "src/research_x/tool_interface/codex_bridge.py"


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


def test_agent_control_links_stay_in_codex_foundation_registry_only() -> None:
    if not CODEX_FOUNDATION_REGISTRY.exists() or not CODEX_FOUNDATION_SOURCE_LOCK.exists():
        pytest.skip("global .codex foundation registry is outside the portable repository")

    registry = tomllib.loads(CODEX_FOUNDATION_REGISTRY.read_text(encoding="utf-8"))
    source_lock = CODEX_FOUNDATION_SOURCE_LOCK.read_text(encoding="utf-8")
    candidates = {item["name"]: item for item in registry["candidates"]}
    expected = {
        "headroom-context-observability": "codex_operations",
        "loop-engineering": "codex_operations",
        "peerd": "external_tool_governance",
        "lighthouse-agentic-browsing-audit": "external_tool_governance",
        "edge-addons-governance": "external_tool_governance",
        "x-private-source-routing": "codex_operations",
    }
    staged_expected = expected.keys() - {
        "edge-addons-governance",
        "x-private-source-routing",
    }

    for name, group in expected.items():
        candidate = candidates[name]

        assert candidate["group"] == group
        assert name in source_lock

    for name in staged_expected:
        candidate = candidates[name]
        assert candidate["adoption_shape"] == "staging"
        assert candidate["enabled"] is False

    assert "No install or runtime hook" in candidates[
        "headroom-context-observability"
    ]["promotion_gate"]
    assert "context-budget" in candidates[
        "headroom-context-observability"
    ]["first_local_step"]
    assert "codex-fluent" in candidates[
        "headroom-context-observability"
    ]["first_local_step"]
    assert "long-loop-executor" in candidates["loop-engineering"]["promotion_gate"]
    assert "planning-files" in candidates["loop-engineering"]["promotion_gate"]
    assert "No MCP server" in candidates["peerd"]["promotion_gate"]
    assert "Browser automation" in candidates[
        "lighthouse-agentic-browsing-audit"
    ]["promotion_gate"]
    edge_governance = candidates["edge-addons-governance"]
    assert edge_governance["adoption_shape"] == "adopt"
    assert edge_governance["enabled"] is False
    assert edge_governance["active_surface"] == (
        "C:/Users/maasa/.codex/foundation/pipeline/engine/"
        "codex_pipeline/edge_addons_governance.py"
    )
    assert "store listing alone is not trust" in edge_governance["promotion_gate"]
    assert "no action permission" in edge_governance["promotion_gate"]
    assert "not an enabled runnable external-source surface" in edge_governance["notes"]
    x_route = candidates["x-private-source-routing"]
    assert x_route["adoption_shape"] == "adopt"
    assert x_route["enabled"] is False
    assert x_route["active_surface"] == (
        "C:/Users/maasa/.codex/route_memory/route-memory.json"
    )
    assert "No login bypass" in x_route["promotion_gate"]
    assert "source promotion from snippets" in x_route["promotion_gate"]
    assert "negative route-memory" in x_route["notes"]
    assert "not an enabled runnable surface" in x_route["notes"]


def test_agent_control_links_do_not_create_research_x_runtime_or_skill_surfaces() -> None:
    candidate_names = (
        "headroom-context-observability",
        "loop-engineering",
        "peerd",
        "lighthouse-agentic-browsing-audit",
        "edge-addons-governance",
        "x-private-source-routing",
    )
    repo_text = REGISTRY.read_text(encoding="utf-8")

    for name in candidate_names:
        assert name not in repo_text
        assert not Path(".agents/skills", name, "SKILL.md").exists()
