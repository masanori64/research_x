from __future__ import annotations

import json
from pathlib import Path

PACKAGE_JSON = Path("package.json")
PACKAGE_LOCK = Path("package-lock.json")
PRESENTATION_CONFIG = Path("docs/presentation/presentation.config.yaml")
DIAGRAM_SYSTEMS = Path("docs/presentation/diagram-systems.md")
DIAGRAM_DESIGN_HARNESS = Path("docs/presentation/diagram-design-harness.md")
PREFLIGHT = Path("scripts/presentation/preflight.mjs")
RENDER_D2 = Path("scripts/presentation/render-d2.mjs")
BUILD = Path("scripts/presentation/build.mjs")


def test_stage1_package_surface_is_limited_to_presentation_renderers() -> None:
    package = json.loads(PACKAGE_JSON.read_text(encoding="utf-8"))

    assert package["name"] == "research-x-presentation-tools"
    assert package["private"] is True
    assert package["type"] == "module"
    assert package["scripts"] == {
        "presentation:preflight": "node scripts/presentation/preflight.mjs",
        "presentation:render-d2": "node scripts/presentation/render-d2.mjs",
        "presentation:build": "node scripts/presentation/build.mjs",
    }
    assert package["devDependencies"] == {
        "@marp-team/marp-cli": "4.4.0",
        "@mermaid-js/mermaid-cli": "^11.16.0",
        "@terrastruct/d2": "0.1.33",
    }


def test_stage1_lockfile_pins_selected_packages() -> None:
    lock = json.loads(PACKAGE_LOCK.read_text(encoding="utf-8"))
    root = lock["packages"][""]

    assert root["devDependencies"]["@marp-team/marp-cli"] == "4.4.0"
    assert root["devDependencies"]["@mermaid-js/mermaid-cli"] == "^11.16.0"
    assert root["devDependencies"]["@terrastruct/d2"] == "0.1.33"
    assert lock["packages"]["node_modules/@marp-team/marp-cli"]["version"] == "4.4.0"
    assert lock["packages"]["node_modules/@mermaid-js/mermaid-cli"]["version"] == "11.16.0"
    assert lock["packages"]["node_modules/@terrastruct/d2"]["version"] == "0.1.33"


def test_stage1_scripts_keep_provider_plugin_and_extra_tooling_out() -> None:
    combined = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (PREFLIGHT, RENDER_D2, BUILD)
    )

    assert "PptxGenJS" not in combined
    assert "Structurizr" not in combined
    assert "Repomix" not in combined
    assert "providerApi: false" in combined
    assert "plugin: false" in combined
    assert "mcp: false" in combined
    assert "hook: false" in combined
    assert "@terrastruct/d2" in combined
    assert "@marp-team/marp-cli" in combined


def test_presentation_config_names_d2_marp_and_stage2_sources() -> None:
    config = PRESENTATION_CONFIG.read_text(encoding="utf-8")

    assert "diagram_source: d2" in config
    assert "diagram_systems: docs/presentation/diagram-systems.md" in config
    assert "diagram_design_harness: docs/presentation/diagram-design-harness.md" in config
    assert "slide_renderer: marp" in config
    assert "facts_source: docs/presentation/project-facts.json" in config
    assert "slides_source: docs/presentation/slides.md" in config
    assert "PptxGenJS" not in config
    assert "Structurizr" not in config


def test_diagram_design_harness_preserves_human_readability_intent() -> None:
    text = DIAGRAM_DESIGN_HARNESS.read_text(encoding="utf-8")

    for phrase in (
        "Create diagrams for first-time human readers",
        "without zooming",
        "stable reading order",
        "crossing arrows",
        "proper nouns",
        "ordinary explanation is Japanese",
        "not like an automatic inventory",
        "Passing automated checks is not enough",
    ):
        assert phrase in text

    assert "These are examples of what to avoid. They are not the whole rule." in text
    assert "diagramDesignHarness" in PREFLIGHT.read_text(encoding="utf-8")
    assert "diagramSystems" in PREFLIGHT.read_text(encoding="utf-8")


def test_diagram_systems_route_by_creation_system_and_retire_custom_uml() -> None:
    text = DIAGRAM_SYSTEMS.read_text(encoding="utf-8")
    normalized = " ".join(text.split())
    normalized_without_backticks = normalized.replace("`", "")

    for phrase in (
        "diagram creation-system routing",
        "D2",
        "Marp",
        "Mermaid",
        "WBS Viewer",
        "Mermaid UML requests",
        "sequenceDiagram",
        "classDiagram",
        "stateDiagram-v2",
        "The previous custom UML lane was removed",
        "Do not recreate a custom SVG generator",
        "Do not call a flowchart UML",
        "Mermaid can own that lane",
    ):
        assert phrase in normalized_without_backticks

    assert "scripts/uml/build-research-x-uml.mjs" in text
    assert "docs/uml/" in text
    assert not Path("scripts/uml").exists()
    assert not Path("docs/uml").exists()
    assert not Path("tests/test_uml_assets.py").exists()
