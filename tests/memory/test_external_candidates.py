from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from research_x.memory import external as memory_external
from research_x.memory.api_budget import (
    PROVIDER_EXECUTION_POLICY_REQUIRED_STATUS,
    ProviderExecutionPolicy,
    api_budget_context,
)
from research_x.memory.external import (
    CANDIDATE_EVIDENCE_STATUS,
    build_external_search_request,
    normalize_external_source_candidates,
    search_external_candidates,
)


@pytest.mark.parametrize(
    ("provider", "expected_key", "expected_value"),
    [
        ("serper", "num", 3),
        ("tavily", "max_results", 3),
        ("exa", "numResults", 3),
        ("perplexity", "max_results", 3),
        ("firecrawl", "limit", 3),
    ],
)
def test_external_provider_request_shapes_are_candidate_only(
    provider: str,
    expected_key: str,
    expected_value: int,
) -> None:
    request = build_external_search_request(
        provider,
        query="source restoration",
        limit=3,
        api_key="test-key",
    )

    assert request["provider"] == provider
    assert request["provider_role"] == "index_provider"
    assert request["operation"] == "external_search"
    assert request["method"] == "POST"
    assert request["payload"][expected_key] == expected_value
    assert request["request_shape_only"] is True
    assert request["provider_quality_proof"] is False
    assert request["source_candidate_only"] is True


def test_searxng_request_shape_uses_local_get_candidate_query() -> None:
    request = build_external_search_request(
        "searxng",
        query="source restoration",
        limit=3,
        endpoint="http://127.0.0.1:8080/search",
        language="ja",
    )

    assert request["provider"] == "searxng"
    assert request["method"] == "GET"
    assert request["params"] == {
        "q": "source restoration",
        "format": "json",
        "language": "ja",
    }
    assert request["api_key_required"] is False
    assert request["request_shape_only"] is True


@pytest.mark.parametrize(
    ("provider", "raw"),
    [
        (
            "serper",
            {
                "organic": [
                    {
                        "title": "Serper result",
                        "link": "https://example.com/serper",
                        "snippet": "SERP snippet",
                        "date": "2026-07-01",
                        "position": 1,
                    }
                ]
            },
        ),
        (
            "tavily",
            {
                "results": [
                    {
                        "title": "Tavily result",
                        "url": "https://example.com/tavily",
                        "content": "Tavily content",
                        "published_date": "2026-07-02",
                        "score": 0.72,
                    }
                ]
            },
        ),
        (
            "exa",
            {
                "results": [
                    {
                        "title": "Exa result",
                        "url": "https://example.com/exa",
                        "text": "Exa text",
                        "publishedDate": "2026-07-03",
                        "score": 0.63,
                    }
                ]
            },
        ),
        (
            "perplexity",
            {
                "results": [
                    {
                        "title": "Perplexity result",
                        "url": "https://example.com/perplexity",
                        "snippet": "Perplexity snippet",
                        "date": "2026-07-04",
                    }
                ]
            },
        ),
        (
            "firecrawl",
            {
                "data": [
                    {
                        "url": "https://example.com/firecrawl",
                        "markdown": "# Firecrawl result",
                        "metadata": {
                            "title": "Firecrawl result",
                            "publishedDate": "2026-07-05",
                        },
                    }
                ]
            },
        ),
        (
            "searxng",
            {
                "results": [
                    {
                        "title": "SearXNG result",
                        "url": "https://example.com/searxng",
                        "content": "SearXNG content",
                        "publishedDate": "2026-07-06",
                    }
                ]
            },
        ),
    ],
)
def test_external_provider_raw_items_normalize_to_candidate_schema(
    provider: str,
    raw: dict,
) -> None:
    items = normalize_external_source_candidates(
        provider,
        raw,
        limit=1,
        query="source restoration",
        run_id="external-run",
    )

    assert len(items) == 1
    item = items[0]
    payload = item.as_dict()
    assert item.provider == provider
    assert item.run_id == "external-run"
    assert item.source_id.startswith("external_candidate_")
    assert payload["provider"] == provider
    assert payload["raw_payload"]
    assert payload["citation_excluded"] is True
    assert payload["evidence_status"] == CANDIDATE_EVIDENCE_STATUS
    assert item.metadata["raw_payload_is_not_evidence"] is True
    assert item.metadata["source_candidate_policy"] == "requires_fetch_extract_chunk_citation"


def test_external_provider_default_does_not_send_network(monkeypatch, tmp_path: Path) -> None:
    calls: list[object] = []

    def fail_urlopen(*args, **kwargs):
        calls.append((args, kwargs))
        raise AssertionError("network should not be called")

    monkeypatch.setattr(memory_external.urllib.request, "urlopen", fail_urlopen)

    bundle = search_external_candidates(
        tmp_path / "x.sqlite3",
        "source restoration",
        provider="tavily",
        limit=2,
        store=False,
    )

    assert calls == []
    assert bundle.status == PROVIDER_EXECUTION_POLICY_REQUIRED_STATUS
    assert bundle.provider_policy_status == PROVIDER_EXECUTION_POLICY_REQUIRED_STATUS
    assert bundle.items == ()
    assert bundle.as_dict()["source_candidate_policy"][
        "raw_provider_response_is_answer_support"
    ] is False


def test_external_provider_requires_api_key_before_authorized_transport(
    monkeypatch,
    tmp_path: Path,
) -> None:
    calls: list[object] = []

    def fail_urlopen(*args, **kwargs):
        calls.append((args, kwargs))
        raise AssertionError("network should not be called")

    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    monkeypatch.setattr(memory_external.urllib.request, "urlopen", fail_urlopen)

    with api_budget_context(
        db_path=tmp_path / "budget.sqlite3",
        run_id="external-run",
        provider_execution_policy=ProviderExecutionPolicy(
            policy_id="policy-external",
            authorization_id="auth-external",
            provider="tavily",
            model="tavily-search",
            operation="external_search",
            provider_role="index_provider",
            allowed=True,
            max_calls=1,
            max_cost_usd=0.01,
            approved_scope="external-run",
        ),
        provider_quota_current_scope="external-run",
    ), pytest.raises(RuntimeError, match="TAVILY_API_KEY is not set"):
        search_external_candidates(
            tmp_path / "x.sqlite3",
            "source restoration",
            provider="tavily",
            limit=1,
            store=False,
        )

    assert calls == []


def test_external_provider_fake_transport_normalizes_and_stores_candidates(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("EXA_API_KEY", "test-exa-key")
    db_path = tmp_path / "x.sqlite3"
    seen_requests: list[dict] = []

    def fake_transport(request: dict) -> dict:
        seen_requests.append(request)
        return {
            "results": [
                {
                    "title": "Restoration result",
                    "url": "https://example.com/restoration",
                    "text": "A fake Exa transport result.",
                    "publishedDate": "2026-07-07",
                    "score": 0.91,
                }
            ]
        }

    bundle = search_external_candidates(
        db_path,
        "source restoration",
        provider="exa",
        limit=1,
        transport=fake_transport,
    )

    assert len(seen_requests) == 1
    assert bundle.status == "ok"
    assert bundle.items[0].provider == "exa"
    assert bundle.items[0].raw_payload["url"] == "https://example.com/restoration"
    assert bundle.as_dict()["request_shape"]["headers"]["x-api-key"] == "<redacted>"
    assert bundle.as_dict()["source_candidate_policy"][
        "raw_provider_response_is_answer_support"
    ] is False

    with sqlite3.connect(db_path) as conn:
        run_status = conn.execute("SELECT status FROM memory_external_runs").fetchone()[0]
        item_metadata = json.loads(
            conn.execute("SELECT metadata_json FROM memory_external_items").fetchone()[0]
        )

    assert run_status == "ok"
    assert item_metadata["citation_excluded"] is True
    assert item_metadata["evidence_status"] == CANDIDATE_EVIDENCE_STATUS
    assert item_metadata["raw_payload"]["url"] == "https://example.com/restoration"
    assert item_metadata["raw_payload_is_not_evidence"] is True
