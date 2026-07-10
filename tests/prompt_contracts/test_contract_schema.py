from __future__ import annotations

from pathlib import Path

CONTRACT_DIR = Path("prompt_contracts")
CONTRACTS = {
    "research_x_memory_search_v1.yaml",
    "research_x_research_intake_v1.yaml",
    "research_x_bridge_signal_v1.yaml",
}
REQUIRED_KEYS = (
    "contract_id:",
    "version:",
    "scope: research_x",
    "mode:",
    "provider_policy:",
    "allowed_tools:",
    "forbidden_tools:",
    "status_codes:",
    "negative_cases:",
)
EXPECTED_PROVIDER_POLICIES = {
    "research_x_memory_search_v1.yaml": "provider_policy: no_real_provider_calls",
    "research_x_research_intake_v1.yaml": (
        "provider_policy: provider_execution_policy_required"
    ),
    "research_x_bridge_signal_v1.yaml": (
        "provider_policy: provider_execution_policy_required"
    ),
}


def test_prompt_contract_artifacts_exist_and_have_required_sections() -> None:
    paths = {path.name for path in CONTRACT_DIR.glob("research_x_*.yaml")}

    assert paths >= CONTRACTS
    for name in CONTRACTS:
        text = (CONTRACT_DIR / name).read_text(encoding="utf-8")
        for key in REQUIRED_KEYS:
            assert key in text, f"{name} missing {key}"
        assert EXPECTED_PROVIDER_POLICIES[name] in text
        assert (
            "github_write" in text
            or name == "research_x_memory_search_v1.yaml"
        )


def test_contract_ids_match_file_names() -> None:
    for name in CONTRACTS:
        text = (CONTRACT_DIR / name).read_text(encoding="utf-8")
        expected_id = name.removesuffix(".yaml")

        assert f"contract_id: {expected_id}" in text
