from __future__ import annotations

import json
from pathlib import Path

from research_x.cli import main
from research_x.presentation.slides import validate_presentation_slides

FACTS = Path("docs/presentation/project-facts.json")
SLIDES = Path("docs/presentation/deck.marp")


def test_presentation_slides_map_to_fact_claims_before_assets_are_rendered() -> None:
    result = validate_presentation_slides(
        SLIDES,
        facts_path=FACTS,
        allow_missing_assets=True,
    )

    assert result.ok, result.errors
    assert result.summary["claim_markers"] >= 6
    assert set(result.summary["asset_paths"]) == {
        "assets/c4-container.svg",
        "assets/memory-evidence-flow.svg",
        "assets/memory-query-sequence.svg",
        "assets/roadmap.svg",
        "assets/runtime-boundary.svg",
    }


def test_presentation_slides_reject_unknown_claim_markers(tmp_path: Path) -> None:
    slides = tmp_path / "slides.md"
    slides.write_text(
        "---\nmarp: true\n---\n\n# Bad\n\n<!-- claim: missing-claim -->\n",
        encoding="utf-8",
    )

    result = validate_presentation_slides(
        slides,
        facts_path=FACTS,
        allow_missing_assets=True,
        require_slide_candidates=False,
    )

    assert not result.ok
    assert any("unknown claim ids" in error for error in result.errors)


def test_presentation_slides_reject_external_assets(tmp_path: Path) -> None:
    slides = tmp_path / "slides.md"
    slides.write_text(
        (
            "---\nmarp: true\n---\n\n# Bad\n\n"
            "<!-- claim: claim-local-x-memory -->\n\n"
            "![external](https://example.com/image.svg)\n"
        ),
        encoding="utf-8",
    )

    result = validate_presentation_slides(
        slides,
        facts_path=FACTS,
        require_slide_candidates=False,
    )

    assert not result.ok
    assert any("external assets" in error for error in result.errors)


def test_presentation_validate_slides_cli_json(capsys) -> None:
    exit_code = main(
        [
            "presentation",
            "validate-slides",
            "--facts",
            str(FACTS),
            "--slides",
            str(SLIDES),
            "--allow-missing-assets",
            "--json",
        ]
    )

    output = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert output["ok"] is True
    assert output["summary"]["claim_markers"] >= 6
