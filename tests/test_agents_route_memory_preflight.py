from __future__ import annotations

from pathlib import Path

AGENTS = Path("AGENTS.md")


def test_agents_has_route_memory_preflight_dispatcher_without_permission_grant() -> None:
    text = AGENTS.read_text(encoding="utf-8")
    normalized = " ".join(text.split())

    assert "Route Memory Preflight" in text
    assert ".codex/route_memory/route-memory.json" in text
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
