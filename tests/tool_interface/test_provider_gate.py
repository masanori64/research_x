from __future__ import annotations

import pytest

from research_x.memory.api_budget import (
    ProviderOperationClass,
    classify_provider_operation,
    provider_operation_class_policy,
)

CANON_ITEMS = ("P14", "P19")
PURPOSE = "Guard provider operation classes without sending provider traffic."
pytestmark = [pytest.mark.canon(item) for item in CANON_ITEMS]


def test_upstream_review_and_adapter_work_are_non_runtime() -> None:
    upstream = provider_operation_class_policy("upstream_review")
    adapter = provider_operation_class_policy("adapter_development")

    assert classify_provider_operation("github_review") is ProviderOperationClass.UPSTREAM_REVIEW
    assert upstream.provider_budget_required is False
    assert upstream.explicit_approval_required is False
    assert upstream.api_budget_guard_required is False
    assert adapter.provider_budget_required is False
    assert adapter.explicit_approval_required is False


def test_dry_run_request_shape_is_allowed_but_not_quality_proof() -> None:
    policy = provider_operation_class_policy("dry_run_request_shape")

    assert policy.provider_budget_required is False
    assert policy.explicit_approval_required is False
    assert policy.api_budget_guard_required is False
    assert "not model-quality proof" in policy.notes


def test_runtime_provider_classes_require_budget_guard_and_approval() -> None:
    for operation in ("runtime_provider_call", "quota_consuming_runtime"):
        policy = provider_operation_class_policy(operation)

        assert policy.provider_budget_required is True
        assert policy.explicit_approval_required is True
        assert policy.api_budget_guard_required is True


@pytest.mark.parametrize(
    "operation",
    (
        "dependency_install",
        "model_download",
        "browser_automation",
        "connector_auth",
        "plugin_enablement",
        "mcp_enablement",
        "hook_enablement",
    ),
)
def test_external_enablement_classes_have_separate_gates(operation: str) -> None:
    policy = provider_operation_class_policy(operation)

    assert policy.explicit_approval_required is True
    assert policy.separate_gate == operation
