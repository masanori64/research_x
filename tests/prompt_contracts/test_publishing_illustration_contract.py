from __future__ import annotations

from pathlib import Path


def test_publishing_illustration_contract_keeps_generation_gated() -> None:
    text = Path("prompt_contracts/research_x_publishing_illustration_v1.yaml").read_text(
        encoding="utf-8"
    )

    assert "mode: visual_planning_only" in text
    assert "image_generation_allowed: false" in text
    assert "visual_outputs_are_not_evidence" in text
    assert "image_generation" in text
    assert "generated_image_as_evidence" in text
    assert "citation_from_visual" in text


def test_publishing_illustration_skill_requires_claim_map_and_sources() -> None:
    text = Path(".agents/skills/research-x-publishing-illustration/SKILL.md").read_text(
        encoding="utf-8"
    )

    assert "visual brief != source" in text
    assert "generated image != citation" in text
    assert "Factual visuals need a claim map" in text
    assert "Image generation is false by default" in text
    assert "ian-xiaohei-illustrations" in text
