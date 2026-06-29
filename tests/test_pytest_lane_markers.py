from __future__ import annotations

import importlib.util
import sys
import tomllib
from pathlib import Path


def test_pytest_marker_registry_covers_research_x_test_lanes() -> None:
    conftest = _load_conftest()
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
    assert marker_names >= conftest.LANE_POLICY_MARKERS


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


def test_lane_marker_report_has_no_silent_unclassified_tests() -> None:
    conftest = _load_conftest()

    assert conftest.unclassified_test_paths() == ()


def test_lane_marker_allowlist_requires_reasons() -> None:
    conftest = _load_conftest()

    assert all(reason.strip() for reason in conftest.UNMARKED_TEST_ALLOWLIST.values())


def test_lane_marker_prefixes_do_not_hide_root_test_files() -> None:
    conftest = _load_conftest()

    assert "tests/" not in dict(conftest.PREFIX_MARKERS)
    assert "tests/test_" not in dict(conftest.PREFIX_MARKERS)


def test_lane_marker_report_exposes_machine_readable_coverage() -> None:
    conftest = _load_conftest()

    report = conftest.lane_marker_report(
        [
            "tests/test_review_context_zip.py",
            "tests/test_memory.py",
            "tests/unknown/test_future.py",
        ]
    )

    assert report == (
        {
            "allowlist_reason": None,
            "markers": (
                "contract",
                "control_artifact",
                "fast",
                "review_package",
                "static_guard",
            ),
            "path": "tests/test_review_context_zip.py",
        },
        {
            "allowlist_reason": None,
            "markers": ("integration", "slow"),
            "path": "tests/test_memory.py",
        },
        {
            "allowlist_reason": None,
            "markers": (),
            "path": "tests/unknown/test_future.py",
        },
    )


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
