from __future__ import annotations

import ast
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from research_x import bookmark_classifier
from research_x.memory import answer, embeddings, external, llm_context, rerank
from research_x.memory.api_budget import (
    active_provider_transport_send,
    api_budget_context,
    api_units,
    upsert_api_price,
)

TRANSPORT_BLOCK_MATCH = "provider_transport_send_guard_required"


class _FakeJsonResponse:
    def __init__(self, payload: dict[str, Any]) -> None:
        self._body = json.dumps(payload).encode("utf-8")

    def __enter__(self) -> _FakeJsonResponse:
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        return None

    def read(self, *_args: object) -> bytes:
        return self._body


@pytest.mark.parametrize(
    ("name", "send", "urlopen_target"),
    (
        (
            "answer",
            lambda: answer._post_json(  # noqa: SLF001
                "https://api.openai.com/v1/chat/completions",
                {"model": "gpt-4o-mini", "messages": []},
                headers={"Authorization": "Bearer test"},
                timeout_seconds=1.0,
                retries=1,
            ),
            "urllib.request.urlopen",
        ),
        (
            "rerank",
            lambda: rerank._post_json(  # noqa: SLF001
                "https://api.cohere.com/v2/rerank",
                {"model": "rerank-v4.0", "query": "x", "documents": ["x"]},
                headers={"Authorization": "Bearer test"},
                timeout_seconds=1.0,
                retries=1,
            ),
            "urllib.request.urlopen",
        ),
        (
            "llm_context",
            lambda: llm_context._post_json(  # noqa: SLF001
                "https://api.search.brave.com/res/v1/llm/context",
                {"q": "x"},
                headers={"X-Subscription-Token": "test"},
                timeout_seconds=1.0,
            ),
            "urllib.request.urlopen",
        ),
        (
            "external",
            lambda: external._post_json(  # noqa: SLF001
                "https://google.serper.dev/search",
                {"q": "x"},
                headers={"X-API-KEY": "test"},
                timeout_seconds=1.0,
            ),
            "urllib.request.urlopen",
        ),
        (
            "embeddings",
            lambda: embeddings._post_json(  # noqa: SLF001
                "https://api.openai.com/v1/embeddings",
                {"model": "text-embedding-3-small", "input": ["x"]},
                headers={"Authorization": "Bearer test"},
                timeout_seconds=1.0,
                retries=1,
            ),
            "urllib.request.urlopen",
        ),
        (
            "classifier",
            lambda: bookmark_classifier._post_json(  # noqa: SLF001
                "https://api.openai.com/v1/chat/completions",
                {"model": "gpt-4o-mini", "messages": []},
                api_key="test",
                timeout_seconds=1.0,
            ),
            "research_x.bookmark_classifier.urlopen",
        ),
    ),
)
def test_private_provider_http_helpers_block_without_transport_guard(
    monkeypatch: pytest.MonkeyPatch,
    name: str,
    send: Callable[[], dict[str, Any]],
    urlopen_target: str,
) -> None:
    called = False

    def fail_urlopen(*_args: Any, **_kwargs: Any) -> _FakeJsonResponse:
        nonlocal called
        called = True
        raise AssertionError(f"{name} provider HTTP should be blocked before urlopen")

    monkeypatch.setattr(urlopen_target, fail_urlopen)

    with pytest.raises(RuntimeError, match=TRANSPORT_BLOCK_MATCH):
        send()

    assert called is False


def test_budgeted_provider_transport_guard_allows_send_after_reservation(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "x.sqlite3"
    upsert_api_price(
        db_path,
        provider="openai",
        model="text-embedding-3-small",
        operation="embedding",
        unit="call",
        usd_per_unit=0.0,
        source_url="fixture://transport-guard",
    )
    observed = []

    def fake_urlopen(request: Any, *, timeout: float) -> _FakeJsonResponse:
        observed.append(
            {
                "url": request.full_url,
                "timeout": timeout,
                "transport": active_provider_transport_send(),
            }
        )
        return _FakeJsonResponse({"data": [{"embedding": [0.0]}]})

    monkeypatch.setattr(embeddings.urllib.request, "urlopen", fake_urlopen)

    with api_budget_context(db_path=db_path, run_id="run", no_quota_freeze_active=False):
        response = embeddings._post_json(  # noqa: SLF001
            "https://api.openai.com/v1/embeddings",
            {"model": "text-embedding-3-small", "input": ["x"]},
            headers={"Authorization": "Bearer test"},
            timeout_seconds=1.0,
            retries=1,
            budget_provider="openai",
            budget_model="text-embedding-3-small",
            budget_units=api_units(calls=1),
        )

    assert response == {"data": [{"embedding": [0.0]}]}
    assert len(observed) == 1
    assert observed[0]["url"] == "https://api.openai.com/v1/embeddings"
    assert observed[0]["timeout"] == 1.0
    transport = observed[0]["transport"]
    assert transport is not None
    assert transport.provider == "openai"
    assert transport.model == "text-embedding-3-small"
    assert transport.operation == "embedding"
    assert active_provider_transport_send() is None


def test_budgeted_provider_transport_guard_resets_after_send_error(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "x.sqlite3"
    upsert_api_price(
        db_path,
        provider="openai",
        model="text-embedding-3-small",
        operation="embedding",
        unit="call",
        usd_per_unit=0.0,
        source_url="fixture://transport-guard",
    )
    observed = []

    def fail_urlopen(_request: Any, *, timeout: float) -> _FakeJsonResponse:
        del timeout
        observed.append(active_provider_transport_send())
        raise RuntimeError("synthetic transport failure")

    monkeypatch.setattr(embeddings.urllib.request, "urlopen", fail_urlopen)

    with (
        api_budget_context(db_path=db_path, run_id="run", no_quota_freeze_active=False),
        pytest.raises(RuntimeError, match="synthetic transport failure"),
    ):
        embeddings._post_json(  # noqa: SLF001
            "https://api.openai.com/v1/embeddings",
            {"model": "text-embedding-3-small", "input": ["x"]},
            headers={"Authorization": "Bearer test"},
            timeout_seconds=1.0,
            retries=1,
            budget_provider="openai",
            budget_model="text-embedding-3-small",
            budget_units=api_units(calls=1),
        )

    assert len(observed) == 1
    assert observed[0] is not None
    assert active_provider_transport_send() is None


def test_private_post_json_helpers_require_transport_guard() -> None:
    helper_paths = (
        Path("src/research_x/memory/answer.py"),
        Path("src/research_x/memory/rerank.py"),
        Path("src/research_x/memory/llm_context.py"),
        Path("src/research_x/memory/external.py"),
        Path("src/research_x/memory/embeddings.py"),
        Path("src/research_x/bookmark_classifier.py"),
    )

    for path in helper_paths:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
        helper = next(
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef) and node.name == "_post_json_unbudgeted"
        )
        calls_transport_guard = any(
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "require_provider_transport_send_allowed"
            for node in ast.walk(helper)
        )
        assert calls_transport_guard, path


def test_jina_reader_provider_guards_transport_before_reading_url() -> None:
    source = Path("src/research_x/memory/reader.py").read_text(encoding="utf-8")
    guard_index = source.index('require_provider_transport_send_allowed(request["url"])')
    read_index = source.index("response = _read_url(", guard_index)

    assert guard_index < read_index
