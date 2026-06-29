from __future__ import annotations

from pathlib import Path

REPO_SKILL = Path(".agents/skills/research-x-publishing-illustration/SKILL.md")
REPO_CONTRACT = Path("prompt_contracts/research_x_publishing_illustration_v1.yaml")


def test_publishing_illustration_contract_is_not_repo_local() -> None:
    assert not REPO_CONTRACT.exists()
    assert not REPO_SKILL.exists()
