from __future__ import annotations

from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]

PATH_MARKERS: dict[str, tuple[str, ...]] = {
    "tests/cli/test_memory_tool_json_db_restoration.py": (
        "contract",
        "integration",
        "local_fixture",
    ),
    "tests/media/test_media_embedding_provider_gate.py": ("provider_gate",),
    "tests/memory/test_retrieval_quality_eval.py": (
        "contract",
        "integration",
        "local_fixture",
        "retrieval_eval",
    ),
    "tests/provider_gate/test_provider_request_builders.py": (
        "fast",
        "provider_gate",
    ),
    "tests/provider_gate/test_static_network_send_guard.py": (
        "fast",
        "provider_gate",
        "static_guard",
    ),
    "tests/test_adoption_registry.py": ("contract", "control_artifact"),
    "tests/test_github_pipeline_contract.py": ("contract", "control_artifact"),
    "tests/test_pytest_lane_markers.py": ("contract", "control_artifact", "fast"),
    "tests/test_research_x_work_state_wbs.py": (
        "contract",
        "control_artifact",
        "wbs_control",
    ),
    "tests/test_review_context_zip.py": (
        "contract",
        "control_artifact",
        "fast",
        "review_package",
        "static_guard",
    ),
    "tests/test_wbs_viewer_canary.py": ("control_artifact", "wbs_control"),
    "tests/tool_interface/test_codex_bridge_boundary.py": (
        "contract",
        "control_artifact",
        "fast",
    ),
    "tests/tool_interface/test_db_backed_tool_restoration.py": (
        "integration",
        "local_fixture",
    ),
    "tests/tool_interface/test_memory_tool_contract_strictness.py": (
        "contract",
        "fast",
        "local_fixture",
    ),
    "tests/tool_interface/test_preview_cannot_be_citation.py": (
        "contract",
        "control_artifact",
        "fast",
        "local_fixture",
    ),
    "tests/vector/test_nonlocal_provider_vector_rows_are_gated.py": ("provider_gate",),
}

PREFIX_MARKERS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("tests/prompt_contracts/", ("contract", "provider_gate")),
    ("tests/provider_gate/", ("provider_gate",)),
)


def lane_markers_for_path(path: str | Path) -> frozenset[str]:
    normalized = _normalize_test_path(path)
    markers: set[str] = set(PATH_MARKERS.get(normalized, ()))
    for prefix, prefix_markers in PREFIX_MARKERS:
        if normalized.startswith(prefix):
            markers.update(prefix_markers)
    return frozenset(markers)


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    for item in items:
        for marker in sorted(lane_markers_for_path(item.path)):
            item.add_marker(getattr(pytest.mark, marker))


def _normalize_test_path(path: str | Path) -> str:
    raw = str(path).replace("\\", "/")
    root = PROJECT_ROOT.as_posix()
    if raw.startswith(root + "/"):
        raw = raw[len(root) + 1 :]
    if raw.startswith("./"):
        raw = raw[2:]
    return raw
