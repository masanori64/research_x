from __future__ import annotations

import importlib.util
import sys
import tomllib
from pathlib import Path


def test_pytest_marker_registry_covers_research_x_test_lanes() -> None:
    pyproject = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
    marker_entries = pyproject["tool"]["pytest"]["ini_options"]["markers"]
    marker_names = {entry.split(":", 1)[0] for entry in marker_entries}

    assert {
        "contract",
        "fast",
        "local_fixture",
        "retrieval_eval",
        "provider_gate",
        "static_guard",
        "review_package",
        "wbs_control",
        "packaging",
        "slow",
        "nightly",
        "manual_provider_gated",
        "control_artifact",
    } <= marker_names


def test_lane_marker_mapping_covers_first_operational_lanes() -> None:
    conftest = _load_conftest()

    cases = {
        "tests/test_review_context_zip.py": {
            "contract",
            "control_artifact",
            "fast",
            "review_package",
            "static_guard",
        },
        "tests/provider_gate/test_static_network_send_guard.py": {
            "fast",
            "provider_gate",
            "static_guard",
        },
        "tests/provider_gate/test_provider_request_builders.py": {
            "fast",
            "provider_gate",
        },
        "tests/memory/test_retrieval_quality_eval.py": {
            "contract",
            "local_fixture",
            "retrieval_eval",
        },
        "tests/tool_interface/test_memory_tool_contract_strictness.py": {
            "contract",
            "fast",
            "local_fixture",
        },
        "tests/test_research_x_work_state_wbs.py": {
            "contract",
            "control_artifact",
            "wbs_control",
        },
    }

    for path, expected_markers in cases.items():
        assert expected_markers <= conftest.lane_markers_for_path(path)


def _load_conftest():
    spec = importlib.util.spec_from_file_location(
        "research_x_tests_conftest",
        Path("tests/conftest.py"),
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module
