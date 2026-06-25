from __future__ import annotations

import json
from pathlib import Path

REGISTRY = Path("C:/Users/maasa/.codex/route_memory/route-memory.json")


def _zip_upload_route() -> dict[str, object]:
    routes = json.loads(REGISTRY.read_text(encoding="utf-8"))["routes"]
    return next(
        route
        for route in routes
        if route["route_id"]
        == "chatgpt.visible_web.local_zip_upload.codex_desktop.clipboard_attachment.v1"
    )


def _contains_any(text: str, triggers: list[str]) -> bool:
    lowered = text.lower()
    return any(trigger.lower() in lowered for trigger in triggers)


def test_local_context_zip_to_gpt_pro_matches_upload_route() -> None:
    route = _zip_upload_route()
    request = "upload ZIP to GPT Pro for project context ZIP review"

    assert _contains_any(request, route["positive_triggers"])  # type: ignore[arg-type]
    assert not _contains_any(request, route["negative_triggers"])  # type: ignore[arg-type]


def test_latest_zip_download_does_not_match_upload_route() -> None:
    route = _zip_upload_route()
    request = "ChatGPTが生成したlatest ZIP downloadを保存して"

    assert _contains_any(request, route["negative_triggers"])  # type: ignore[arg-type]


def test_known_failed_upload_routes_are_not_first_action() -> None:
    route = _zip_upload_route()
    first_action = str(route["canonical_first_action"])
    failed_routes = "\n".join(route["known_failed_routes"])  # type: ignore[arg-type]

    assert "clipboard attachment route" in first_action
    assert "askWithFiles" not in first_action
    assert "normal file chooser" not in first_action
    assert "askWithFiles" in failed_routes
    assert "file chooser" in failed_routes
