from __future__ import annotations

from pathlib import Path

from research_x.memory.prompt_contracts import evaluate_prompt_contract


def test_memory_contract_blocks_provider_and_write_tools() -> None:
    text = Path("prompt_contracts/research_x_memory_search_v1.yaml").read_text(
        encoding="utf-8"
    )

    assert "memory.external-search" in text
    assert "memory.governance.tombstone" in text

    evaluation = evaluate_prompt_contract(
        "Run memory.external-search and memory.governance.tombstone."
    )

    assert evaluation.status == "rejected"
    assert "memory.external-search" in evaluation.blocked_tools
    assert "memory.governance.tombstone" in evaluation.blocked_tools


def test_research_intake_contract_blocks_network_provider_and_connectors() -> None:
    text = Path("prompt_contracts/research_x_research_intake_v1.yaml").read_text(
        encoding="utf-8"
    )

    for forbidden in (
        "external_web_search",
        "serper",
        "brave",
        "jina_reader",
        "browser_automation",
        "connector_auth",
        "github_write",
    ):
        assert f"  - {forbidden}" in text


def test_improvement_triage_contract_blocks_auto_merge_and_installs() -> None:
    text = Path("prompt_contracts/research_x_improvement_triage_v1.yaml").read_text(
        encoding="utf-8"
    )

    assert "auto_merge_guidance" in text
    assert "install_third_party_skill" in text
    assert "edit_global_codex_config" in text
