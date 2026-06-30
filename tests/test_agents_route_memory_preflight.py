from __future__ import annotations

import json
from pathlib import Path

import pytest

AGENTS = Path("AGENTS.md")
ROUTE_MEMORY = Path("C:/Users/maasa/.codex/route_memory/route-memory.json")


def test_agents_has_route_memory_preflight_dispatcher_without_permission_grant() -> None:
    text = AGENTS.read_text(encoding="utf-8")
    normalized = " ".join(text.split())

    assert "Route Memory Preflight" in text
    assert "C:/Users/maasa/.codex/route_memory/route-memory.json" in text
    assert "known failed" in text
    assert "canonical first action" in text
    assert "Prefer a matching canonical first action over rediscovery" in normalized
    assert "does not grant" in text
    assert "provider/API" in text
    assert "browser" in text
    assert "ChatGPT" in text
    assert "MCP" in text
    assert "connector" in text
    assert "install" in text
    assert "evidence permission" in text


def test_x_private_route_memory_is_negative_source_restoration_route() -> None:
    if not ROUTE_MEMORY.exists():
        pytest.skip("global .codex route memory is outside the portable repository")

    data = json.loads(ROUTE_MEMORY.read_text(encoding="utf-8"))
    routes = {route["route_id"]: route for route in data["routes"]}
    route = routes["research_x.x_private_source_restoration.metadata_only_boundary.v1"]
    route_text = " ".join(
        [
            route["canonical_first_action"],
            *route["positive_triggers"],
            *route["known_failed_routes"],
            *route["success_verification"],
            *route["gates"],
        ]
    )

    assert route["status"] == "active"
    assert route["not_evidence"] is True
    assert "x.com/i/bookmarks" in route["positive_triggers"]
    assert "source_not_restored" in route_text
    assert "snippet" in route_text
    assert "citation-ready evidence" in route_text
    assert "Does not grant browser login" in route_text
    assert "provider Reader" in route_text
    assert "extension install" in route_text
