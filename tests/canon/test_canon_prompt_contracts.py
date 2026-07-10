from __future__ import annotations

from pathlib import Path

import pytest

CANON_ITEM = "P15"
PURPOSE = "Guard mode-specific prompt contracts without re-creating prompt policy."
pytestmark = pytest.mark.canon(CANON_ITEM)

CONTRACT_DIR = Path("prompt_contracts")
MODE_CONTRACTS = {
    "research_x_memory_explore_v1.yaml": ("output_mode: explore", "no_answer_assertion"),
    "research_x_memory_collect_v1.yaml": ("output_mode: collect", "source_status_required"),
    "research_x_memory_working_note_v1.yaml": (
        "output_mode: working_note",
        "memory.working_note.promote_without_user_approval",
    ),
    "research_x_memory_synthesize_v1.yaml": (
        "output_mode: synthesize",
        "unsupported_claims_disclosed",
    ),
    "research_x_memory_evidence_package_v1.yaml": (
        "output_mode: evidence_package",
        "evidence_view_required",
    ),
    "research_x_memory_answer_v1.yaml": (
        "output_mode: answer",
        "evidence_package_required",
        "citation_ready_required",
        "claim_support_required",
        "db_backed_validation_required",
    ),
    "research_x_source_intake_v2.yaml": (
        "mode: source_intake",
        "discovery_is_not_evidence",
        "hidden_backend_api",
    ),
    "research_x_upstream_review_v1.yaml": (
        "operation_class: upstream_review",
        "upstream_review_not_runtime_provider_call",
    ),
    "research_x_bridge_signal_v2.yaml": (
        "mode: bridge_signal",
        "bridge_signal_only",
    ),
}


def test_mode_specific_contracts_exist_and_match_file_ids() -> None:
    for name, required_fragments in MODE_CONTRACTS.items():
        text = (CONTRACT_DIR / name).read_text(encoding="utf-8")

        assert f"contract_id: {name.removesuffix('.yaml')}" in text
        assert "scope: research_x" in text
        assert "provider_policy: no_real_provider_calls" in text
        assert "knowledgeops_policy: docs/research_x_canon.md" in text
        assert "allowed_tools:" in text
        assert "forbidden_tools:" in text
        assert "negative_cases:" in text
        for fragment in required_fragments:
            assert fragment in text


def test_legacy_search_contract_is_deprecated_to_explore_default() -> None:
    text = (CONTRACT_DIR / "research_x_memory_search_v1.yaml").read_text(
        encoding="utf-8"
    )

    assert "compatibility_note: deprecated legacy v1 contract maps to explore by default" in text
    assert "default_output_mode: explore" in text


def test_answer_contract_blocks_non_evidence_sources() -> None:
    text = (CONTRACT_DIR / "research_x_memory_answer_v1.yaml").read_text(
        encoding="utf-8"
    )

    for negative_case in (
        "memory.answer_from_candidate_only",
        "memory.answer_from_working_note_only",
        "memory.answer_from_derived_signal_only",
    ):
        assert negative_case in text
