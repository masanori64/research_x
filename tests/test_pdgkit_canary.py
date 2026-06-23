from __future__ import annotations

import json
from pathlib import Path

PDGKIT_DIR = Path("tools/pdgkit_canary")
PDG_SOURCE = PDGKIT_DIR / "canaries" / "item-11-35-flow.pdg"
SVG_OUTPUT = PDGKIT_DIR / "out" / "item-11-35-flow.svg"
PACKAGE_LOCK = PDGKIT_DIR / "package-lock.json"


def test_pdgkit_canary_package_is_pinned() -> None:
    lock = json.loads(PACKAGE_LOCK.read_text(encoding="utf-8"))

    assert lock["packages"][""]["dependencies"]["@shibayama/pdgkit"] == "0.1.2"
    assert lock["packages"]["node_modules/@shibayama/pdgkit"]["version"] == "0.1.2"
    assert lock["packages"]["node_modules/@shibayama/pdgkit"]["license"] == "MIT"


def test_pdgkit_canary_source_and_svg_are_recorded() -> None:
    source = PDG_SOURCE.read_text(encoding="utf-8")
    svg = SVG_OUTPUT.read_text(encoding="utf-8")

    assert source.startswith("#! kind: flow")
    assert "S150 = Start item 35 pdgkit adoption" in source
    assert "<svg" in svg
    assert "Start item 35 pdgkit adoption" in svg
