from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from research_x import bookmark_classifier
from research_x.memory import (
    answer,
    embeddings,
    external,
    judge_relations,
    llm_context,
    media_embeddings,
    ocr,
    reader,
    rerank,
)
from research_x.memory.api_budget import api_units, budgeted_api_call

FREEZE_MATCH = "provider_gated_by_no_quota_freeze"


def test_budgeted_api_call_blocks_real_provider_without_context() -> None:
    with pytest.raises(RuntimeError, match=FREEZE_MATCH), budgeted_api_call(
        provider="openai",
        model="gpt-4o-mini",
        provider_role="answer_engine",
        operation="answer",
        units=api_units(calls=1),
        request_payload={"messages": []},
    ):
        raise AssertionError("provider execution should not enter request body")


def test_budgeted_api_call_allows_local_and_fixture_providers_without_context() -> None:
    for provider in ("fake", "local", "local_hash", "fixture_media"):
        with budgeted_api_call(
            provider=provider,
            model=f"{provider}-model",
            provider_role="fixture",
            operation="fixture",
            units=api_units(calls=1),
            request_payload={"fixture": True},
        ):
            pass


@pytest.mark.parametrize(
    ("module", "kwargs"),
    (
        (
            answer,
            {
                "headers": {"Authorization": "Bearer test"},
                "timeout_seconds": 1.0,
                "budget_provider": "gemini",
                "budget_model": "gemini-2.5-flash",
                "budget_units": api_units(calls=1, input_tokens=1),
            },
        ),
        (
            rerank,
            {
                "headers": {"Authorization": "Bearer test"},
                "timeout_seconds": 1.0,
                "budget_provider": "cohere",
                "budget_model": "rerank-v4.0-pro",
                "budget_units": api_units(calls=1, input_tokens=1),
            },
        ),
        (
            llm_context,
            {
                "headers": {"X-Subscription-Token": "test"},
                "timeout_seconds": 1.0,
                "budget_provider": "brave",
                "budget_model": "brave-llm-context",
                "budget_units": api_units(calls=1, input_tokens=1),
            },
        ),
        (
            embeddings,
            {
                "headers": {"Authorization": "Bearer test"},
                "timeout_seconds": 1.0,
                "budget_provider": "openai",
                "budget_model": "text-embedding-3-small",
                "budget_units": api_units(calls=1, input_tokens=1),
            },
        ),
        (
            external,
            {
                "headers": {"X-API-KEY": "test"},
                "timeout_seconds": 1.0,
                "budget_provider": "serper",
                "budget_model": "serper-search",
                "budget_units": api_units(calls=1, input_tokens=1),
            },
        ),
        (
            judge_relations,
            {
                "headers": {"Authorization": "Bearer test"},
                "timeout_seconds": 1.0,
                "budget_provider": "gemini",
                "budget_model": "gemini-2.5-flash",
                "budget_units": api_units(calls=1, input_tokens=1),
            },
        ),
    ),
)
def test_json_provider_send_wrappers_block_before_http(
    monkeypatch: pytest.MonkeyPatch,
    module: Any,
    kwargs: dict[str, Any],
) -> None:
    called = False

    def fail_post_json(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        nonlocal called
        called = True
        raise AssertionError("provider request should be blocked before HTTP send")

    monkeypatch.setattr(module, "_post_json", fail_post_json)

    with pytest.raises(RuntimeError, match=FREEZE_MATCH):
        module._post_json_budgeted(  # noqa: SLF001
            "https://provider.example/api",
            {"model": kwargs["budget_model"], "input": "x"},
            **kwargs,
        )

    assert called is False


def test_media_embedding_send_wrapper_blocks_before_http(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called = False

    def fail_post_json(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        nonlocal called
        called = True
        raise AssertionError("provider request should be blocked before HTTP send")

    monkeypatch.setattr(media_embeddings, "_post_json", fail_post_json)

    with pytest.raises(RuntimeError, match=FREEZE_MATCH):
        media_embeddings._post_json_budgeted(  # noqa: SLF001
            "https://generativelanguage.googleapis.com/v1beta/models/gemini-embedding-2",
            {"model": "models/gemini-embedding-2", "content": {"parts": []}},
            headers={"x-goog-api-key": "test"},
            timeout_seconds=1.0,
            budget_provider="gemini",
            budget_model="gemini-embedding-2",
            budget_operation="media_embedding",
            budget_units=api_units(calls=1, media_bytes=1),
        )

    assert called is False


def test_reader_provider_blocks_before_network_fetch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called = False

    def fail_read_url(*_args: Any, **_kwargs: Any) -> Any:
        nonlocal called
        called = True
        raise AssertionError("reader request should be blocked before network fetch")

    monkeypatch.setattr(reader, "_read_url", fail_read_url)

    with pytest.raises(RuntimeError, match=FREEZE_MATCH):
        reader.JinaReaderProvider(timeout_seconds=1.0).extract(
            "https://example.com/page",
            query="query",
            title=None,
            max_chars=100,
        )

    assert called is False


def test_direct_http_reader_provider_blocks_before_network_fetch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called = False

    def fail_read_url(*_args: Any, **_kwargs: Any) -> Any:
        nonlocal called
        called = True
        raise AssertionError("direct reader request should be blocked before network fetch")

    monkeypatch.setattr(reader, "_read_url", fail_read_url)

    with pytest.raises(RuntimeError, match=FREEZE_MATCH):
        reader.HttpReaderProvider(timeout_seconds=1.0).extract(
            "https://example.com/page",
            query="query",
            title=None,
            max_chars=100,
        )

    assert called is False


def test_ocr_provider_blocks_before_http_send(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match=FREEZE_MATCH):
        ocr.build_ocr_evidence(
            tmp_path / "x.sqlite3",
            provider="mistral",
            allow_provider_quota=True,
        )


def test_classifier_provider_send_wrapper_blocks_before_http(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called = False

    def fail_post_json_unbudgeted(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        nonlocal called
        called = True
        raise AssertionError("classifier request should be blocked before HTTP send")

    monkeypatch.setattr(bookmark_classifier, "_post_json_unbudgeted", fail_post_json_unbudgeted)

    with pytest.raises(RuntimeError, match=FREEZE_MATCH):
        bookmark_classifier._post_json_budgeted(  # noqa: SLF001
            "https://api.openai.com/v1/chat/completions",
            {"model": "gpt-4o-mini", "messages": []},
            api_key="test",
            timeout_seconds=1.0,
            budget_provider="openai",
            budget_model="gpt-4o-mini",
            budget_units=api_units(calls=1, input_tokens=1),
        )

    assert called is False
