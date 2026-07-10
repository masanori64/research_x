from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]

PATH_MARKERS: dict[str, tuple[str, ...]] = {
    "tests/canon/test_markdown_canon.py": ("contract", "static_guard"),
    "tests/canon/test_project_control.py": (
        "contract",
        "provider_gate",
        "static_guard",
    ),
    "tests/canon/test_prompt_contracts.py": ("contract", "provider_gate"),
    "tests/memory/test_schema_migration.py": ("contract", "local_fixture"),
    "tests/memory/test_source_observation.py": ("contract", "local_fixture"),
    "tests/memory/test_artifact_roles.py": ("contract", "unit"),
    "tests/memory/test_participation_policy.py": ("contract", "local_fixture"),
    "tests/memory/test_projection_lifecycle.py": (
        "contract",
        "local_fixture",
        "provider_gate",
    ),
    "tests/memory/test_working_notes.py": ("contract", "local_fixture"),
    "tests/memory/test_evidence_package.py": ("contract", "local_fixture"),
    "tests/memory/test_eval_v2.py": ("contract", "local_fixture", "retrieval_eval"),
    "tests/memory/test_reconciliation.py": ("contract", "local_fixture"),
    "tests/tool_interface/test_output_modes.py": ("contract", "unit"),
    "tests/tool_interface/test_answer_boundary.py": ("contract", "unit"),
    "tests/tool_interface/test_provider_gate.py": ("contract", "provider_gate"),
    "tests/tool_interface/test_human_oversight.py": ("contract", "provider_gate"),
}

UNMARKED_TEST_ALLOWLIST: dict[str, str] = {}


def lane_markers_for_path(path: str | Path) -> frozenset[str]:
    return frozenset(PATH_MARKERS.get(_normalize_test_path(path), ()))


def lane_marker_report(paths: Iterable[str | Path] | None = None) -> tuple[dict[str, object], ...]:
    selected_paths = tuple(paths) if paths is not None else _iter_test_files()
    return tuple(
        {
            "path": _normalize_test_path(path),
            "markers": tuple(sorted(lane_markers_for_path(path))),
            "allowlist_reason": UNMARKED_TEST_ALLOWLIST.get(_normalize_test_path(path)),
        }
        for path in selected_paths
    )


def unclassified_test_paths(paths: Iterable[str | Path] | None = None) -> tuple[str, ...]:
    return tuple(
        str(entry["path"])
        for entry in lane_marker_report(paths)
        if not entry["markers"] and not entry["allowlist_reason"]
    )


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


def _iter_test_files() -> tuple[Path, ...]:
    return tuple(sorted((PROJECT_ROOT / "tests").rglob("test_*.py")))
