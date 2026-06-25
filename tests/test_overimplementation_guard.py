from __future__ import annotations

from research_x.codex_improvement.overimplementation_guard import (
    evaluate_overimplementation_guard,
    validate_overimplementation_guard_input,
)


def _record() -> dict[str, object]:
    return {
        "requested_change": "Add a report-only renderer extension.",
        "existing_surfaces_checked": True,
        "stdlib_or_native_checked": True,
        "existing_dependency_checked": True,
        "delete_or_simplify_option": False,
        "why_new_code_is_needed": "Existing renderer lacks lifecycle report fields.",
        "risk_exception": "none",
        "decision": "implement_new",
    }


def test_guard_accepts_checked_local_new_code() -> None:
    record = _record()

    assert validate_overimplementation_guard_input(record) == []
    result = evaluate_overimplementation_guard(record)

    assert result.decision == "implement_new"
    assert result.adoption_shape == "adopt"
    assert result.report_only is True


def test_guard_moves_unchecked_new_module_to_needs_review() -> None:
    record = _record()
    record["existing_surfaces_checked"] = False

    result = evaluate_overimplementation_guard(record)

    assert result.decision == "needs_review"
    assert "existing surfaces were not checked" in result.reasons[0]


def test_guard_stages_new_dependency_without_existing_surface_checks() -> None:
    record = _record()
    record["requested_change"] = "Install a new dependency for rendering."
    record["stdlib_or_native_checked"] = False

    result = evaluate_overimplementation_guard(record)

    assert result.decision == "staging"
    assert result.adoption_shape == "staging"
    assert "dependency-review staging" in result.reasons[0]


def test_guard_stages_plugin_hook_or_mcp_adoption() -> None:
    record = _record()
    record["requested_change"] = "Enable Ponytail plugin hook for every Codex run."

    result = evaluate_overimplementation_guard(record)

    assert result.decision == "staging"
    assert result.adoption_shape == "staging"
    assert "plugin/hook/MCP adoption requires isolated staging" in result.reasons[0]


def test_security_or_accessibility_exception_cannot_be_removed_as_yagni() -> None:
    record = _record()
    record["risk_exception"] = "security"
    record["decision"] = "simplify"

    result = evaluate_overimplementation_guard(record)

    assert result.decision == "needs_review"
    assert "risk exception cannot be removed as YAGNI" in result.reasons


def test_existing_renderer_reuse_is_allowed() -> None:
    record = _record()
    record["requested_change"] = "Reuse the existing control artifact renderer."
    record["decision"] = "reuse_existing"

    result = evaluate_overimplementation_guard(record)

    assert result.decision == "reuse_existing"
    assert result.adoption_shape == "adopt"
