from __future__ import annotations

from pathlib import Path

PDG_DIR = Path("docs/pdg")
PDG_OUT = PDG_DIR / "out"

REQUIRED_STEMS = {
    "memory-evidence-pipeline",
    "objective-route-policy",
    "source-intake-gate-flow",
    "visual-context-offload-lane",
}


def test_project_pdg_sources_are_split_from_canary_fixture() -> None:
    sources = {path.stem for path in PDG_DIR.glob("*.pdg")}

    assert sources == REQUIRED_STEMS
    assert not Path("tools/pdgkit_canary/canaries/visual-context-offload-lane.pdg").exists()


def test_project_pdg_sources_are_flow_sources() -> None:
    for stem in REQUIRED_STEMS:
        source = (PDG_DIR / f"{stem}.pdg").read_text(encoding="utf-8")
        assert source.startswith("#! kind: flow"), stem
        assert "->" in source, stem


def test_memory_evidence_pdg_preserves_evidence_transitions() -> None:
    source = (PDG_DIR / "memory-evidence-pipeline.pdg").read_text(encoding="utf-8")

    assert "Raw source" in source
    assert "Searchable document" in source
    assert "Search result" in source
    assert "Source bundle restored" in source
    assert "Context chunks" in source
    assert "Citation annotations" in source
    assert "Answer" in source
    assert "Stop: source not restored" in source
    assert "Stop: citation missing" in source


def test_source_intake_pdg_preserves_stop_gates() -> None:
    source = (PDG_DIR / "source-intake-gate-flow.pdg").read_text(encoding="utf-8")

    for text in ("Dependency install gate", "Provider or API gate", "MCP", "hook"):
        assert text in source
    assert "Stop: explicit approval required" in source
    assert "Reference-only or disabled lock" in source


def test_visual_context_pdg_preserves_wbs_pdg_pointer_and_evidence_gates() -> None:
    source = (PDG_DIR / "visual-context-offload-lane.pdg").read_text(encoding="utf-8")

    assert "Update canonical WBS JSON" in source
    assert "Update project PDG source" in source
    assert "Update pointer-map JSON" in source
    assert "Restore source bundle, context chunks, and citations" in source
    assert "Keep visual artifact as review only" in source


def test_project_pdg_svgs_are_generated_review_artifacts() -> None:
    for stem in REQUIRED_STEMS:
        svg = (PDG_OUT / f"{stem}.svg").read_text(encoding="utf-8")
        assert "<svg" in svg
        assert "</svg>" in svg
