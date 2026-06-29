from __future__ import annotations

import pytest

from research_x.memory.api_budget import (
    api_units,
    budgeted_api_call,
    provider_is_quota_exempt,
)

FREEZE_MATCH = "provider_gated_by_no_quota_freeze"


def test_registered_fixture_provider_is_quota_exempt_without_context() -> None:
    assert provider_is_quota_exempt("fixture_media") is True

    with budgeted_api_call(
        provider="fixture_media",
        model="fixture-media-v1",
        provider_role="embedding",
        operation="media_embedding",
        units=api_units(calls=1, media_bytes=1),
        request_payload={"fixture": True},
    ):
        pass


def test_unknown_fixture_prefix_provider_is_not_quota_exempt() -> None:
    assert provider_is_quota_exempt("fixture_openai") is False

    with pytest.raises(RuntimeError, match=FREEZE_MATCH), budgeted_api_call(
        provider="fixture_openai",
        model="fixture-openai-model",
        provider_role="answer_engine",
        operation="answer",
        units=api_units(calls=1),
        request_payload={"fixture": True},
    ):
        raise AssertionError("unknown fixture provider should not enter request body")
