from __future__ import annotations

import json
from pathlib import Path

UML_DIR = Path("docs/uml")
MANIFEST = UML_DIR / "manifest.json"


def test_research_x_uml_manifest_lists_eight_selected_diagrams() -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))

    selected = manifest["selected"]
    assert len(selected) == 8
    assert {entry["file"] for entry in selected} == {
        "01-use-case",
        "02-component",
        "03-package",
        "04-deployment",
        "05-class-core",
        "06-activity-acquisition",
        "07-state-workflow",
        "08-sequence-memory-query",
    }


def test_research_x_uml_svg_and_png_assets_exist() -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))

    for entry in manifest["selected"]:
        svg = UML_DIR / entry["svg"]
        png = UML_DIR / entry["png"]
        assert svg.exists(), svg
        assert png.exists(), png
        assert svg.read_text(encoding="utf-8").startswith("<?xml")
        assert png.stat().st_size > 10_000


def test_research_x_uml_manifest_excludes_over_detailed_diagrams() -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))

    excluded = {entry["type"] for entry in manifest["excluded"]}
    assert {
        "Object",
        "Communication",
        "Timing",
        "Interaction Overview",
        "Profile",
        "Composite Structure",
    }.issubset(excluded)
