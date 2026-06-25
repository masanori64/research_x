from __future__ import annotations

from pathlib import Path

CONTRACT = Path(
    "C:/Users/maasa/.codex/foundation/prompt_contracts/"
    "research_x_publishing_illustration_v1.yaml"
)
SKILL = Path("C:/Users/maasa/.codex/skills/research-x-publishing-illustration/SKILL.md")
REPO_SKILL = Path(".agents/skills/research-x-publishing-illustration/SKILL.md")
REPO_CONTRACT = Path("prompt_contracts/research_x_publishing_illustration_v1.yaml")


def test_publishing_illustration_contract_keeps_generation_gated() -> None:
    assert not REPO_CONTRACT.exists()
    text = CONTRACT.read_text(encoding="utf-8")

    assert "mode: visual_planning_only" in text
    assert "image_generation_allowed: false" in text
    assert "visual_outputs_are_not_evidence" in text
    assert "image_generation" in text
    assert "generated_image_as_evidence" in text
    assert "citation_from_visual" in text


def test_publishing_illustration_skill_requires_claim_map_and_sources() -> None:
    assert not REPO_SKILL.exists()
    text = SKILL.read_text(encoding="utf-8")

    assert "visual brief != source" in text
    assert "generated image != citation" in text
    assert "Factual visuals need a claim map" in text
    assert "Image generation is false by default" in text
    assert "global `.codex` output helper" in text
    assert "ian-xiaohei-illustrations" in text
