from __future__ import annotations

import hashlib
import json
from pathlib import Path

CODEX_CONTEXT_OFFLOADS = Path(
    "C:/Users/maasa/.codex/foundation/context_offloads/research_x"
)
POINTER_MAP = CODEX_CONTEXT_OFFLOADS / "pointer-map.json"
HUMAN_INDEX = CODEX_CONTEXT_OFFLOADS / "visual-context-offload-map.md"


def test_pointer_map_entries_match_current_artifacts() -> None:
    data = json.loads(POINTER_MAP.read_text(encoding="utf-8"))
    entries = data["entries"]

    assert data["schema_version"] == 1
    assert entries
    assert len({entry["pointer_id"] for entry in entries}) == len(entries)

    for entry in entries:
        path = Path(entry["artifact_path"])
        assert path.exists(), entry["pointer_id"]
        assert entry["not_evidence"] is True
        assert entry["restore_hint"]
        assert entry["artifact_kind"]
        assert entry["owner_plane"]
        assert entry["sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
        assert entry["char_count"] == len(path.read_text(encoding="utf-8"))
        assert entry["byte_count"] == path.stat().st_size


def test_pointer_map_covers_canonical_wbs_presentation_plan_and_gpt_pro_input() -> None:
    data = json.loads(POINTER_MAP.read_text(encoding="utf-8"))
    paths = {entry["artifact_path"] for entry in data["entries"]}
    artifact_kinds = {entry["artifact_kind"] for entry in data["entries"]}
    retired_docs = "docs/" + "pdg/"
    retired_tool = "tools/" + "pdg" + "kit_canary/"
    retired_source_kind = "pdg" + "_source"
    retired_svg_kind = "pdg" + "_svg"

    assert "tools/wbs_viewer/projects/research-x-work-state.json" in paths
    assert "C:/Users/maasa/.codex/route_memory/route-memory.json" in paths
    assert "C:/Users/maasa/.codex/route_memory/route-memory.schema.json" in paths
    assert (
        "C:/Users/maasa/.codex/foundation/project_plans/research_x/2026-06-24-presentation-generation-flow.md"
        in paths
    )
    assert (
        "C:/Users/maasa/.codex/foundation/project_reviews/research_x_chatgpt_control/architecture-refresh-gpt-pro-20260623/gpt-pro-response.md"
        in paths
    )
    assert (
        "C:/Users/maasa/.codex/foundation/project_reviews/research_x_chatgpt_control/route-memory-pipeline-20260624/gpt-pro-response.md"
        in paths
    )
    assert not any(path.startswith(retired_docs) for path in paths)
    assert not any(path.startswith(retired_tool) for path in paths)
    assert retired_source_kind not in artifact_kinds
    assert retired_svg_kind not in artifact_kinds


def test_human_pointer_index_is_thin_and_defers_to_json() -> None:
    text = HUMAN_INDEX.read_text(encoding="utf-8")

    assert "pointer-map.json" in text
    assert "authoritative pointer map" in text
    assert "| pointer_id |" not in text
    assert "not citations or answer support" in text
