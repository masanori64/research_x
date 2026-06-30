from __future__ import annotations

from pathlib import Path

MERMAID_DIR = Path("docs/presentation/mermaid")
EXPECTED = {
    "01-overall-architecture.mmd": "flowchart TB",
    "02-evidence-pipeline.mmd": "flowchart TB",
    "03-memory-query-sequence.mmd": "sequenceDiagram",
    "04-provider-quota-gate.mmd": "flowchart TB",
    "05-roadmap.mmd": "flowchart TB",
}


def test_presentation_mermaid_diagrams_exist_without_slide_binding() -> None:
    assert {path.name for path in MERMAID_DIR.glob("*.mmd")} == set(EXPECTED)

    slides = Path("docs/presentation/slides.md").read_text(encoding="utf-8")
    for name in EXPECTED:
        assert name not in slides


def test_presentation_mermaid_diagrams_are_native_mermaid_sources() -> None:
    for name, first_line in EXPECTED.items():
        path = MERMAID_DIR / name
        text = path.read_text(encoding="utf-8")
        assert text.startswith(first_line), path
        assert "direction:" not in text
        assert "shape:" not in text
        assert "style." not in text
        assert "D2" not in text


def test_presentation_mermaid_diagrams_cover_requested_topics() -> None:
    combined = "\n".join(path.read_text(encoding="utf-8") for path in MERMAID_DIR.glob("*.mmd"))

    for phrase in (
        "全体アーキテクチャ図",
        "証拠パイプライン図",
        "1回の memory query シーケンス図",
        "provider / quota guard 図",
        "WBS / ロードマップ図",
    ):
        assert phrase in combined


def test_mermaid_diagram_systems_document_presentation_mermaid_lane() -> None:
    text = Path("docs/presentation/diagram-systems.md").read_text(encoding="utf-8")

    assert "docs/presentation/mermaid/**/*.mmd" in text
    assert "presentation-review diagrams" in text
    assert "not by refactoring D2/SVG assets" in text
