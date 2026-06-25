from __future__ import annotations

import json
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

    for name in {
        "skillopt",
        "skilladaptor",
        "muse-autoskill",
        "evoskill",
        "gepa",
        "textgrad",
        "trace2skill",
        "skillgrad",
        "skillsmith",
        "basic-memory",
        "agentmemory",
        "supermemory",
        "mem0",
        "core",
        "automem",
        "memoryoss",
        "memories-sh",
        "codex-memory",
        "route-memory",
        "ian-xiaohei-illustrations",
        "research-x-publishing-illustration",
    }:
        assert name in candidates
    assert candidates["research_x_bridge"]["adoption_shape"] == "adopt"
    assert registry["policy"]["auto_apply_allowed"] is False
