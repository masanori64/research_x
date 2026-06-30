from __future__ import annotations

import json
import shutil
import tomllib
from pathlib import Path

import pytest

from research_x.adoption_registry import (
    adoption_audit,
    adoption_candidates,
    validate_adoption_registry,
)
from research_x.cli import main

REGISTRY = Path("control/adoption_registry.toml")
CODEX_FOUNDATION_REGISTRY = Path("C:/Users/maasa/.codex/foundation/codex-foundation-registry.toml")


def test_research_x_adoption_registry_is_valid() -> None:
    assert validate_adoption_registry(REGISTRY) == []

    audit = adoption_audit(REGISTRY)
    assert audit["status"] == "ok"
    assert audit["counts"]["research_x_tool:adopt"] >= 4
    assert audit["counts"]["research_x_tool:provider_gated"] >= 5
    assert audit["counts"]["codex_foundation:bridge"] == 1


def test_adoption_registry_policy_keeps_external_action_gates_machine_readable() -> None:
    registry = tomllib.loads(REGISTRY.read_text(encoding="utf-8"))
    policy = registry["policy"]

    assert policy["provider_api_only_hard_block"] is True
    assert policy["external_action_requires_approval"] is True
    assert policy["install_mcp_connector_extension_gate"] is True


def test_research_x_registry_covers_plan_candidate_families() -> None:
    text = REGISTRY.read_text(encoding="utf-8").casefold()
    required_names = {
        "firecrawl",
        "jina",
        "brave",
        "serper",
        "searxng",
        "tavily",
        "exa",
        "perplexity",
        "occ-rag",
        "saas",
        "bosun",
        "warrantbench",
        "zvec",
        "turbovec",
        "paddleocr",
        "mistral",
        "manga",
        "gemini",
        "wbs",
        "d2",
        "marp",
        "archify",
        "yaml",
        "pdgkit",
    }

    missing = sorted(name for name in required_names if name not in text)
    assert missing == []


def test_research_x_registry_has_no_unresolved_source_locks() -> None:
    text = REGISTRY.read_text(encoding="utf-8")

    assert "needs_source_lock" not in text
    assert "source-lock-needed:" not in text


def test_adoption_candidates_have_stop_conditions() -> None:
    candidates = adoption_candidates(REGISTRY)

    assert candidates
    assert all(item.stop_condition.strip() for item in candidates)
    provider_entries = [item for item in candidates if item.provider_or_quota]
    assert all("provider" in item.stop_condition.lower() for item in provider_entries)


def test_adoption_registry_source_refs_must_exist_in_vendor_lock(tmp_path: Path) -> None:
    registry = tmp_path / "adoption_registry.toml"
    source_lock = tmp_path / "vendor_sources.lock.md"
    shutil.copy2(REGISTRY, registry)
    shutil.copy2(Path("control/vendor_sources.lock.md"), source_lock)

    source_lock.write_text(
        source_lock.read_text(encoding="utf-8").replace(
            "| S39 | `bosun` | https://huggingface.co/blog/Hanno-Labs/bosun | "
            "Staged local-model/relevance-judge candidate. Source-locked for evaluation design "
            "only; model download/inference is not part of active research_x runtime. |\n",
            "",
        ),
        encoding="utf-8",
    )

    errors = validate_adoption_registry(registry, source_lock_path=source_lock)

    assert "source lock missing row for S39" in errors


def test_codex_foundation_entries_are_bridge_only_in_research_x() -> None:
    candidates = adoption_candidates(REGISTRY)
    codex_entries = [item for item in candidates if item.owner_surface == "codex_foundation"]

    assert [item.name for item in codex_entries] == ["codex_foundation_registry_bridge"]
    assert all(item.adoption_shape == "bridge" for item in codex_entries)
    assert all(item.enabled is False for item in codex_entries)
    assert all(
        item.source_url == "C:/Users/maasa/.codex/foundation/codex-foundation-registry.toml"
        for item in codex_entries
    )


def test_provider_candidates_are_disabled_and_provider_gated() -> None:
    candidates = adoption_candidates(REGISTRY)
    provider_entries = [item for item in candidates if item.provider_or_quota]

    assert provider_entries
    assert all(item.adoption_shape == "provider_gated" for item in provider_entries)
    assert all(item.enabled is False for item in provider_entries)
    assert all("paid/free-tier" in item.stop_condition for item in provider_entries)
    assert all("trial-credit" in item.stop_condition for item in provider_entries)
    assert all("zero-dollar" in item.stop_condition for item in provider_entries)
    assert all("keyless external-network" in item.stop_condition for item in provider_entries)
    assert all(
        any(
            token in item.first_local_step.casefold()
            for token in ("estimate", "fake", "source-lock", "source candidate")
        )
        for item in provider_entries
    )


def test_okf_metadata_candidate_is_adopted_without_evidence_promotion() -> None:
    candidates = {item.name: item for item in adoption_candidates(REGISTRY)}
    item = candidates["okf_source_metadata_shape"]

    assert item.adoption_shape == "adopt"
    assert item.status == "implemented"
    assert item.enabled is True
    assert item.provider_or_quota is False
    assert item.active_artifact == "src/research_x/research_intake/pipeline.py"
    assert "candidate-only" in item.stop_condition
    assert "source-bundled" in item.stop_condition
    assert "OKF-style files are not evidence" in item.notes


def test_agent_safety_trace_is_contract_visibility_not_runtime_permission() -> None:
    candidates = {item.name: item for item in adoption_candidates(REGISTRY)}
    item = candidates["agent_safety_tool_trace"]

    assert item.adoption_shape == "adopt"
    assert item.status == "implemented"
    assert item.enabled is True
    assert item.provider_or_quota is False
    assert item.source_ref == "S56"
    assert item.active_artifact == "src/research_x/tool_interface/memory_tool_contract.py"
    assert "trace visibility does not grant permissions" in item.promotion_gate
    assert "provider, network, browser, install" in item.stop_condition
    assert "no agent framework" in item.notes
    assert "prompt-only safety model" in item.notes


def test_agent_control_source_ownership_is_intake_metadata_only() -> None:
    candidates = {item.name: item for item in adoption_candidates(REGISTRY)}
    item = candidates["agent_control_source_ownership_coverage"]

    assert item.adoption_shape == "adopt"
    assert item.status == "implemented"
    assert item.enabled is True
    assert item.provider_or_quota is False
    assert item.owner_surface == "research_intake"
    assert item.source_ref == "S57"
    assert item.active_artifact == "src/research_x/research_intake/pipeline.py"
    assert "source_governance" in item.first_local_step
    assert "citation-ready" in item.promotion_gate
    assert "browser/MCP/provider/install authority" in item.stop_condition
    assert "not adopted as runtime behavior" in item.notes


def test_f3_and_sqljoiner_references_stay_staged_disabled() -> None:
    candidates = {item.name: item for item in adoption_candidates(REGISTRY)}
    expected = {
        "f3_self_describing_artifact_reference": "src/research_x/memory/source_identity.py",
        "sqljoiner_query_visualization_reference": (
            "src/research_x/memory/research_artifacts.py"
        ),
    }

    for name, active_artifact in expected.items():
        item = candidates[name]

        assert item.adoption_shape == "staging"
        assert item.status == "staged"
        assert item.enabled is False
        assert item.provider_or_quota is False
        assert item.active_artifact == active_artifact
        assert "dependency install" in item.stop_condition
        assert "runtime import" in item.stop_condition
        assert "evidence promotion" in item.stop_condition

    assert "no F3 archive reader or Wasm decoder is adopted" in candidates[
        "f3_self_describing_artifact_reference"
    ].notes
    assert "no code reuse or DB connection handling is adopted" in candidates[
        "sqljoiner_query_visualization_reference"
    ].notes


def test_slidev_visual_review_lane_adopts_local_evaluator_only() -> None:
    candidates = {item.name: item for item in adoption_candidates(REGISTRY)}
    item = candidates["slidev_visual_review_lane"]

    assert item.adoption_shape == "adopt"
    assert item.status == "implemented"
    assert item.enabled is True
    assert item.provider_or_quota is False
    assert item.active_artifact == "src/research_x/control_artifacts/visual_review.py"
    assert "dependency-free visual-review evaluation" in item.first_local_step
    assert "already-rendered local deck/snapshot artifacts" in item.first_local_step
    assert "renderer/browser" in item.stop_condition
    assert "installs dependencies" in item.stop_condition
    assert "Slidev/Playwright/ppt-master runtime code" in item.stop_condition
    assert "evidence promotion" in item.stop_condition
    assert "Local visual QA evaluator is implemented" in item.notes
    assert "renderer/browser/dependency capture remains staged" in item.notes


def test_cognee_reference_is_local_invariant_coverage_without_runtime_adoption() -> None:
    candidates = {item.name: item for item in adoption_candidates(REGISTRY)}
    item = candidates["cognee_graph_memory_reference"]

    assert item.adoption_shape == "provider_gated"
    assert item.status == "provider_gated"
    assert item.enabled is False
    assert item.provider_or_quota is True
    assert item.active_artifact == "src/research_x/memory/evidence_invariants.py"
    assert "local evidence-invariant fixtures" in item.first_local_step
    assert "source bundle, context chunk, citation" in item.promotion_gate
    assert "MCP, plugin, Docker, cloud, and LLM_API_KEY" in item.promotion_gate
    assert "Cognee runtime remains disabled" in item.notes


def test_provider_stop_condition_tokens_are_validation_errors(tmp_path: Path) -> None:
    registry = tmp_path / "adoption_registry.toml"
    shutil.copy2(REGISTRY, registry)
    text = registry.read_text(encoding="utf-8")
    registry.write_text(text.replace("zero-dollar, or ", "", 1), encoding="utf-8")

    errors = validate_adoption_registry(registry, source_lock_path=None)

    assert any("provider stop_condition missing: zero-dollar" in error for error in errors)


def test_staging_candidates_stay_disabled_and_unimplemented() -> None:
    candidates = adoption_candidates(REGISTRY)
    staging = [item for item in candidates if item.adoption_shape == "staging"]

    assert staging
    assert all(item.status == "staged" for item in staging)
    assert all(item.enabled is False for item in staging)
    assert all("evidence promotion" in item.stop_condition for item in staging)


def test_media_ocr_provider_and_install_lanes_stay_gated() -> None:
    candidates = {item.name: item for item in adoption_candidates(REGISTRY)}

    for name in ("paddleocr", "paddleocr_vl", "manga_ocr"):
        item = candidates[name]
        assert item.status == "staged"
        assert item.enabled is False
        assert item.provider_or_quota is False
        assert "dependency install" in item.stop_condition
        assert "model download" in item.stop_condition
        assert "evidence promotion" in item.stop_condition

    for name in ("mistral_ocr", "gemini_media_embedding"):
        item = candidates[name]
        assert item.status == "provider_gated"
        assert item.enabled is False
        assert item.provider_or_quota is True
        assert "paid/free-tier" in item.stop_condition
        assert "zero-dollar" in item.stop_condition


def test_adopted_research_x_artifacts_exist_and_pdgkit_is_historical() -> None:
    candidates = adoption_candidates(REGISTRY)
    adopted = [
        item
        for item in candidates
        if item.owner_surface == "research_x_tool" and item.adoption_shape == "adopt"
    ]
    pdgkit = next(item for item in candidates if item.name == "pdgkit")

    assert adopted
    assert all(Path(item.active_artifact).exists() for item in adopted)
    assert pdgkit.owner_surface == "historical"
    assert pdgkit.adoption_shape == "historical"
    assert pdgkit.enabled is False


def test_adoption_audit_cli_emits_json(capsys) -> None:
    assert main(["adoption", "audit", "--json"]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "ok"
    assert payload["counts"]["research_x_tool:staging"] >= 8


def test_global_codex_foundation_registry_exists_when_running_on_owner_machine() -> None:
    if not CODEX_FOUNDATION_REGISTRY.exists():
        pytest.skip("global .codex foundation registry is outside the portable repository")

    registry = tomllib.loads(CODEX_FOUNDATION_REGISTRY.read_text(encoding="utf-8"))
    candidates = {item["name"]: item for item in registry["candidates"]}

    assert candidates["research_x_bridge"]["adoption_shape"] == "adopt"
    assert candidates["research_x_bridge"]["source_state"] == "local_project_bridge"
    assert candidates["research_x_bridge"]["enabled"] is True
    assert registry["policy"]["auto_apply_allowed"] is False
