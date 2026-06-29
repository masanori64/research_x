from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
LANE_POLICY_MARKERS = frozenset(
    {
        "browser",
        "contract",
        "control_artifact",
        "e2e",
        "fast",
        "integration",
        "local_fixture",
        "manual_provider_gated",
        "nightly",
        "packaging",
        "provider_gate",
        "retrieval_eval",
        "review_package",
        "slow",
        "static_guard",
        "unit",
        "wbs_control",
    }
)

PATH_MARKERS: dict[str, tuple[str, ...]] = {
    "tests/cli/test_memory_tool_json_db_restoration.py": (
        "contract",
        "integration",
        "local_fixture",
    ),
    "tests/memory/test_citation_ready_requires_lineage.py": (
        "contract",
        "local_fixture",
    ),
    "tests/memory/test_context_offload_pointer_audit.py": (
        "contract",
        "control_artifact",
    ),
    "tests/memory/test_evidence_invariant_fixtures.py": (
        "contract",
        "local_fixture",
    ),
    "tests/memory/test_memory_audit_warning_taxonomy.py": (
        "contract",
        "local_fixture",
    ),
    "tests/memory/test_needs_review_answer_triage.py": (
        "contract",
        "local_fixture",
    ),
    "tests/memory/test_operational_trace_persistence.py": (
        "integration",
        "local_fixture",
    ),
    "tests/memory/test_pointer_map_stale_guard.py": (
        "contract",
        "control_artifact",
    ),
    "tests/memory/test_preview_not_evidence.py": (
        "contract",
        "control_artifact",
    ),
    "tests/memory/test_retrieval_dedup_provenance.py": (
        "contract",
        "local_fixture",
        "retrieval_eval",
    ),
    "tests/media/test_media_embedding_provider_gate.py": ("provider_gate",),
    "tests/memory/test_retrieval_quality_eval.py": (
        "contract",
        "integration",
        "local_fixture",
        "retrieval_eval",
    ),
    "tests/memory/test_source_restoration_lineage.py": (
        "contract",
        "local_fixture",
    ),
    "tests/memory/test_stale_lineage_blocks_answer.py": (
        "contract",
        "local_fixture",
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
    "tests/test_accounts.py": ("browser", "integration"),
    "tests/test_adoption_registry.py": ("contract", "control_artifact"),
    "tests/test_adapter_completion.py": ("unit",),
    "tests/test_agents_route_memory_preflight.py": (
        "contract",
        "control_artifact",
    ),
    "tests/test_api_budget.py": ("contract", "provider_gate"),
    "tests/test_bookmark_adapters.py": ("browser", "integration"),
    "tests/test_bookmark_classifier.py": ("unit",),
    "tests/test_catalog.py": ("integration",),
    "tests/test_codex_bridge.py": ("contract", "control_artifact"),
    "tests/test_codex_foundation_boundary.py": (
        "contract",
        "control_artifact",
    ),
    "tests/test_config.py": ("unit",),
    "tests/test_control_artifact_boundaries.py": (
        "contract",
        "control_artifact",
    ),
    "tests/test_control_artifact_structure_view.py": (
        "contract",
        "control_artifact",
    ),
    "tests/test_cookies.py": ("browser", "unit"),
    "tests/test_db_view.py": ("integration",),
    "tests/test_dependency_security_contract.py": ("contract", "static_guard"),
    "tests/test_diagram_review_boundary.py": ("contract", "control_artifact"),
    "tests/test_doc_budget_audit.py": (
        "contract",
        "control_artifact",
        "review_package",
    ),
    "tests/test_github_pipeline_contract.py": ("contract", "control_artifact"),
    "tests/test_label_existing.py": ("integration",),
    "tests/test_local_app.py": ("integration",),
    "tests/test_markdown_information_architecture.py": (
        "contract",
        "control_artifact",
    ),
    "tests/test_memory.py": ("integration", "slow"),
    "tests/test_notify.py": ("unit",),
    "tests/test_pipeline.py": ("integration",),
    "tests/test_playwright_adapter.py": ("browser", "integration"),
    "tests/test_playwright_auth.py": ("browser", "integration"),
    "tests/test_presentation_facts.py": ("contract", "control_artifact"),
    "tests/test_presentation_slides.py": ("control_artifact", "integration"),
    "tests/test_presentation_stage1.py": ("control_artifact", "integration"),
    "tests/test_progress.py": ("unit",),
    "tests/test_prompt_contracts.py": ("contract", "provider_gate"),
    "tests/test_pytest_lane_markers.py": ("contract", "control_artifact", "fast"),
    "tests/test_research_intake.py": ("contract", "static_guard"),
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
    "tests/test_runner.py": ("integration",),
    "tests/test_scoring.py": ("unit",),
    "tests/test_scweet_adapter.py": ("browser", "integration"),
    "tests/test_session_broker.py": ("integration", "unit"),
    "tests/test_skill_manifest.py": ("contract", "control_artifact"),
    "tests/test_test_diagnostics.py": ("contract", "unit"),
    "tests/test_twikit_adapter.py": ("browser", "integration"),
    "tests/test_twscrape_raw_adapter.py": ("browser", "integration"),
    "tests/test_uml_assets.py": ("contract", "control_artifact"),
    "tests/test_wbs_viewer_canary.py": ("control_artifact", "wbs_control"),
    "tests/test_x_store.py": ("integration",),
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
    "tests/vector/test_local_hash_diagnostic_only.py": ("local_fixture",),
    "tests/vector/test_nonlocal_provider_vector_rows_are_gated.py": ("provider_gate",),
    "tests/vector/test_vector_result_not_citation_ready.py": (
        "contract",
        "local_fixture",
    ),
}

PREFIX_MARKERS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("tests/harness/", ("contract", "control_artifact")),
    ("tests/media/", ("contract", "local_fixture")),
    ("tests/prompt_contracts/", ("contract", "provider_gate")),
    ("tests/provider_gate/", ("provider_gate",)),
    ("tests/research_intake/", ("contract", "static_guard")),
    ("tests/skills/", ("contract", "control_artifact")),
    ("tests/tool_interface/", ("contract",)),
    ("tests/vector/", ("local_fixture",)),
)

UNMARKED_TEST_ALLOWLIST: dict[str, str] = {}


def lane_markers_for_path(path: str | Path) -> frozenset[str]:
    normalized = _normalize_test_path(path)
    markers: set[str] = set(PATH_MARKERS.get(normalized, ()))
    for prefix, prefix_markers in PREFIX_MARKERS:
        if normalized.startswith(prefix):
            markers.update(prefix_markers)
    return frozenset(markers)


def lane_marker_report(paths: Iterable[str | Path] | None = None) -> tuple[dict[str, object], ...]:
    selected_paths = tuple(paths) if paths is not None else _iter_test_files()
    report = []
    for path in selected_paths:
        normalized = _normalize_test_path(path)
        markers = lane_markers_for_path(normalized)
        report.append(
            {
                "path": normalized,
                "markers": tuple(sorted(markers)),
                "allowlist_reason": UNMARKED_TEST_ALLOWLIST.get(normalized),
            }
        )
    return tuple(report)


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
