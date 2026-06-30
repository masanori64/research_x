from __future__ import annotations

import re
from pathlib import Path

REDESIGN_DIR = Path("docs/presentation/mermaid/redesign")

EXPECTED = {
    "current": {
        "01-overall-architecture.mmd": "flowchart",
        "02-evidence-pipeline.mmd": "stateDiagram-v2",
        "03-memory-query-sequence.mmd": "sequenceDiagram",
        "04-provider-quota-gate.mmd": "stateDiagram-v2",
        "05-roadmap.mmd": "flowchart",
    },
    "final": {
        "01-overall-architecture.mmd": "flowchart",
        "02-evidence-pipeline.mmd": "stateDiagram-v2",
        "03-memory-query-sequence.mmd": "sequenceDiagram",
        "04-provider-quota-gate.mmd": "stateDiagram-v2",
        "05-roadmap.mmd": "flowchart",
    },
}

MONOCHROME_HEX = {"#ffffff", "#111111"}

TOPIC_MARKERS = (
    "全体アーキテクチャ図",
    "証拠パイプライン図",
    "1回の memory query シーケンス図",
    "provider / quota guard 図",
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

            assert any(line.startswith(first_line) for line in text.splitlines()[:3]), path
            assert name not in slides
            assert ".svg" not in text
            assert ".d2" not in text
            assert "D2" not in text
            if first_line == "flowchart":
                assert "UML" not in text
            else:
                assert "Mermaid UML" in text
            assert "direction:" not in text
            assert "shape:" not in text
            assert "style." not in text


def test_redesign_mermaid_diagrams_are_monochrome() -> None:
    for set_name, expected_files in EXPECTED.items():
        for name in expected_files:
            path = REDESIGN_DIR / set_name / name
            text = path.read_text(encoding="utf-8").lower()
            hex_values = {match.group(0) for match in re.finditer(r"#[0-9a-f]{6}", text)}

            assert hex_values <= MONOCHROME_HEX, f"{path} uses chromatic colors: {hex_values}"


def test_redesign_current_and_final_sets_cover_same_five_topics() -> None:
    for set_name in EXPECTED:
        combined = "\n".join(
            (REDESIGN_DIR / set_name / name).read_text(encoding="utf-8")
            for name in EXPECTED[set_name]
        )
        for marker in TOPIC_MARKERS:
            assert marker in combined, f"{set_name} missing {marker}"


def test_redesign_diagrams_keep_project_specific_depth() -> None:
    combined = "\n".join(
        path.read_text(encoding="utf-8")
        for set_name in EXPECTED
        for path in (REDESIGN_DIR / set_name).glob("*.mmd")
    )

    for marker in (
        "Route Portfolio [wide]",
        "SQLite FTS / BM25",
        "metadata",
        "relation",
        "semantic",
        "Corpus2Skill",
        "OCR",
        "Reader",
        "LLM-context",
        "managed RAG",
        "ProviderApiBudgetGuard",
        "provider_gated",
        "Source Bundle",
        "Context Chunk",
        "Citation",
        "AnswerAuthorityGatekeeper",
        "Answer Boundary",
        "Workflow Trace",
        "restoration rate",
        "citation coverage",
    ):
        assert marker in combined


def test_redesign_readme_records_source_basis_and_loop() -> None:
    text = (REDESIGN_DIR / "README.md").read_text(encoding="utf-8")
    normalized = " ".join(text.split())

    assert "must follow the final flow docs and project requirements" in normalized
    assert "not existing D2/SVG assets" in normalized
    assert "docs/presentation/diagram-systems.md" in normalized
    assert "Mermaid-supported diagram type boundary" in normalized
    assert "Self-review loop" in text
    assert "Decision: write the diagrams." in text
    assert "current/01-overall-architecture.mmd" in text
    assert "final/01-overall-architecture.mmd" in text


def test_diagram_design_harness_records_fixed_mermaid_contract() -> None:
    text = Path("docs/presentation/diagram-design-harness.md").read_text(encoding="utf-8")
    normalized = " ".join(text.split())

    assert "Fixed Mermaid Harness" in text
    expected_path = (
        "request -> SearchLens / ObjectiveRoutePolicy -> Route Portfolio "
        "-> local candidates -> provider-backed branch -> ProviderApiBudgetGuard "
        "-> candidate or provider_gated -> source bundle / context chunk / citation "
        "-> AnswerAuthorityGatekeeper -> Answer Boundary"
    )
    assert expected_path in normalized
    assert "source bundle, context chunk, citation, and AnswerAuthorityGatekeeper" in normalized
    assert "Do not give every fact the same weight" in normalized
    assert (
        "Do not start writing the diagram while this loop still finds material issues"
        in normalized
    )
    assert "Calling a flowchart or boxes-and-arrows drawing UML" in normalized
    assert "real Mermaid UML-capable syntax" in normalized
    assert "do not label an ordinary flowchart as UML" in normalized.replace("`", "")
