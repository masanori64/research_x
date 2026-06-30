from __future__ import annotations

from pathlib import Path

REDESIGN_DIR = Path("docs/presentation/mermaid/redesign")

EXPECTED = {
    "current": {
        "01-overall-architecture.mmd": "flowchart TB",
        "02-evidence-pipeline.mmd": "flowchart TB",
        "03-memory-query-sequence.mmd": "sequenceDiagram",
        "04-provider-quota-gate.mmd": "flowchart TB",
        "05-roadmap.mmd": "flowchart TB",
    },
    "final": {
        "01-overall-architecture.mmd": "flowchart TB",
        "02-evidence-pipeline.mmd": "flowchart TB",
        "03-memory-query-sequence.mmd": "sequenceDiagram",
        "04-provider-quota-gate.mmd": "flowchart TB",
        "05-roadmap.mmd": "flowchart TB",
    },
}

TOPIC_MARKERS = (
    "全体アーキテクチャ図",
    "証拠パイプライン図",
    "1回の memory query シーケンス図",
    "provider / quota gate 図",
    "WBS / ロードマップ図",
)


def test_redesign_mermaid_diagrams_exist_as_two_five_diagram_sets() -> None:
    for set_name, expected_files in EXPECTED.items():
        directory = REDESIGN_DIR / set_name
        assert {path.name for path in directory.glob("*.mmd")} == set(expected_files)


def test_redesign_mermaid_diagrams_are_not_bound_to_slides_or_d2_assets() -> None:
    slides = Path("docs/presentation/slides.md").read_text(encoding="utf-8")

    for set_name, expected_files in EXPECTED.items():
        for name, first_line in expected_files.items():
            path = REDESIGN_DIR / set_name / name
            text = path.read_text(encoding="utf-8")

            assert text.startswith(first_line), path
            assert name not in slides
            assert ".svg" not in text
            assert ".d2" not in text
            assert "D2" not in text
            assert "direction:" not in text
            assert "shape:" not in text
            assert "style." not in text


def test_redesign_current_and_final_sets_cover_same_five_topics() -> None:
    for set_name in EXPECTED:
        combined = "\n".join(
            (REDESIGN_DIR / set_name / name).read_text(encoding="utf-8")
            for name in EXPECTED[set_name]
        )
        for marker in TOPIC_MARKERS:
            assert marker in combined, f"{set_name} missing {marker}"


def test_redesign_readme_records_source_basis_and_loop() -> None:
    text = (REDESIGN_DIR / "README.md").read_text(encoding="utf-8")
    normalized = " ".join(text.split())

    assert "not from the existing D2/SVG assets" in normalized
    assert "Self-review loop" in text
    assert "Decision: write the diagrams." in text
    assert "current/01-overall-architecture.mmd" in text
    assert "final/01-overall-architecture.mmd" in text


def test_diagram_design_harness_records_fixed_mermaid_contract() -> None:
    text = Path("docs/presentation/diagram-design-harness.md").read_text(encoding="utf-8")
    normalized = " ".join(text.split())

    assert "Fixed Mermaid Harness" in text
    assert (
        "request -> source/search -> evidence restoration -> citation decision -> answer/stop"
        in normalized
    )
    assert "Do not give every fact the same weight" in normalized
    assert (
        "Do not start writing the diagram while this loop still finds material issues"
        in normalized
    )
