from __future__ import annotations

import tomllib
from pathlib import Path

LOCK = Path("control/vendor_sources.lock.toml")


def _payload() -> dict[str, object]:
    return tomllib.loads(LOCK.read_text(encoding="utf-8"))


def _sources() -> dict[str, dict[str, object]]:
    return {str(row["name"]): row for row in _payload()["sources"]}


def test_vendor_lock_is_machine_readable_provenance_not_permission() -> None:
    payload = _payload()
    rows = list(payload["sources"])

    assert payload["artifact_kind"] == "research_x_vendor_sources_lock"
    assert rows
    assert all(row["install_permission"] is False for row in rows)
    assert all(row["runtime_permission"] is False for row in rows)
    assert all(row["evidence_permission"] is False for row in rows)


def test_retired_diagram_tool_is_historical_only() -> None:
    row = _sources()["pdgkit"]

    assert row["decision"] == "historical"
    assert row["status"] == "historical"
    assert row["role"] == "source_lock_only"
    assert row["active_artifact"] == "control/vendor_sources.lock.toml"


def test_codex_foundation_candidates_stay_out_of_project_vendor_lock() -> None:
    names = set(_sources())

    for candidate in (
        "superpowers",
        "superclaude-framework",
        "minimax-skills",
        "ian-xiaohei-illustrations",
        "agentmemory",
    ):
        assert candidate not in names
