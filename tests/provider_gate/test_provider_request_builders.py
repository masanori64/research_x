from __future__ import annotations

from research_x.memory import answer, external, llm_context, reader, rerank
from research_x.memory.context import CitationAnnotation, ContextChunk
from research_x.memory.rerank import RerankInputDocument


def test_answer_request_builder_shapes_openai_compatible_chat() -> None:
    request = answer._openai_compatible_chat_request(  # noqa: SLF001
        base_url="https://generativelanguage.googleapis.com/v1beta/openai",
        api_key="fake-key",
        model="gemini-2.5-flash",
        question="強化学習 ロボット",
        chunks=(_context_chunk(),),
        citations=(_citation(),),
        prompt_version="memory-answer-v1",
        timeout_seconds=7.0,
    )

    assert request["url"].endswith("/v1beta/openai/chat/completions")
    assert request["payload"]["model"] == "gemini-2.5-flash"
    assert request["headers"]["Authorization"] == "Bearer fake-key"
    assert request["timeout_seconds"] == 7.0
    assert request["request_shape_only"] is True
    assert request["provider_quality_proof"] is False


def test_rerank_request_builder_shapes_provider_payloads() -> None:
    documents = (
        RerankInputDocument(
            index=0,
            doc_id="doc:1",
            bundle_key="tweet:1",
            text="強化学習 ロボット",
            metadata={},
        ),
    )

    cohere = rerank._rerank_provider_request(  # noqa: SLF001
        provider="cohere",
        base_url="https://api.cohere.com/v2/rerank",
        api_key="cohere-key",
        model="rerank-v4.0-pro",
        query="強化学習",
        documents=documents,
        top_n=5,
        timeout_seconds=60.0,
    )
    jina = rerank._rerank_provider_request(  # noqa: SLF001
        provider="jina",
        base_url="https://api.jina.ai/v1/rerank",
        api_key="jina-key",
        model="jina-reranker-v3",
        query="強化学習",
        documents=documents,
        top_n=5,
        timeout_seconds=60.0,
    )
    voyage = rerank._rerank_provider_request(  # noqa: SLF001
        provider="voyage",
        base_url="https://api.voyageai.com/v1/rerank",
        api_key="voyage-key",
        model="rerank-2.5",
        query="強化学習",
        documents=documents,
        top_n=5,
        timeout_seconds=60.0,
    )

    assert cohere["payload"]["top_n"] == 5
    assert cohere["headers"]["Authorization"] == "Bearer cohere-key"
    assert isinstance(jina["payload"]["documents"][0], dict)
    assert jina["payload"]["documents"][0]["text"] == "強化学習 ロボット"
    assert voyage["payload"]["top_k"] == 5
    assert voyage["payload"]["truncation"] is True
    assert all(
        request["request_shape_only"] is True and request["provider_quality_proof"] is False
        for request in (cohere, jina, voyage)
    )


def test_llm_context_request_builder_shapes_brave_payload() -> None:
    parameters = llm_context._request_parameters(  # noqa: SLF001
        country="JP",
        search_lang="ja",
        count=99,
        maximum_number_of_urls=99,
        maximum_number_of_tokens=999999,
        maximum_number_of_snippets=999,
        context_threshold_mode="balanced",
        maximum_number_of_tokens_per_url=4096,
        maximum_number_of_snippets_per_url=50,
        freshness=None,
        enable_local=None,
        goggles=None,
    )
    request = llm_context._brave_llm_context_request(  # noqa: SLF001
        endpoint="https://api.search.brave.com/res/v1/llm/context",
        api_key="brave-key",
        query="北千住 ピザ",
        parameters=parameters,
        timeout_seconds=30.0,
    )

    assert request["url"] == "https://api.search.brave.com/res/v1/llm/context"
    assert request["headers"]["X-Subscription-Token"] == "brave-key"
    assert request["payload"]["q"] == "北千住 ピザ"
    assert request["payload"]["count"] == 50
    assert request["payload"]["maximum_number_of_urls"] == 50
    assert request["payload"]["maximum_number_of_tokens"] == 32768
    assert request["payload"]["maximum_number_of_snippets"] == 256
    assert request["request_shape_only"] is True
    assert request["provider_quality_proof"] is False


def test_external_search_request_builder_shapes_serper_payload() -> None:
    request = external._serper_search_request(  # noqa: SLF001
        endpoint="https://google.serper.dev/search",
        api_key="serper-key",
        query="北千住 ピザ",
        limit=3,
        country="jp",
        language="ja",
        location=None,
        timeout_seconds=12.0,
    )

    assert request["url"] == "https://google.serper.dev/search"
    assert request["payload"] == {"q": "北千住 ピザ", "num": 3, "gl": "jp", "hl": "ja"}
    assert request["headers"]["X-API-KEY"] == "serper-key"
    assert request["request_shape_only"] is True
    assert request["provider_quality_proof"] is False


def test_reader_request_builder_shapes_jina_endpoint() -> None:
    request = reader._jina_reader_request(  # noqa: SLF001
        endpoint_base="https://r.jina.ai",
        url="https://example.com/pizza",
        api_key="jina-key",
        timeout_seconds=30.0,
        user_agent="research-x/0.1",
        max_bytes=2_000_000,
    )

    assert request["url"] == "https://r.jina.ai/https://example.com/pizza"
    assert request["headers"]["Authorization"] == "Bearer jina-key"
    assert request["api_key_used"] is True
    assert request["request_shape_only"] is True
    assert request["provider_quality_proof"] is False


def test_reader_request_builder_shapes_firecrawl_extract_payload() -> None:
    request = reader._firecrawl_reader_request(  # noqa: SLF001
        endpoint="https://api.firecrawl.dev/v1/scrape",
        url="https://example.com/pizza",
        api_key="firecrawl-key",
        timeout_seconds=30.0,
    )

    assert request["url"] == "https://api.firecrawl.dev/v1/scrape"
    assert request["provider"] == "firecrawl"
    assert request["model"] == "firecrawl-extract"
    assert request["operation"] == "reader_extract"
    assert request["payload"] == {
        "url": "https://example.com/pizza",
        "formats": ["markdown"],
        "onlyMainContent": True,
    }
    assert request["headers"]["Authorization"] == "Bearer firecrawl-key"
    assert request["api_key_required"] is True
    assert request["api_key_used"] is True
    assert request["request_shape_only"] is True
    assert request["provider_quality_proof"] is False


def _context_chunk() -> ContextChunk:
    return ContextChunk(
        chunk_id="chunk:1",
        run_id="run:1",
        source_kind="local_x_db",
        source_id="tweet:1",
        source_url="https://x.com/a/status/1",
        provider="fixture",
        provider_role="context_builder",
        chunk_text="Text: ロボット実験の保存投稿には強化学習のメモが含まれます。",
        chunk_index=0,
        token_count=24,
        relevance_score=1.0,
        extractor_version="request-builder-fixture-v1",
        created_at="2026-06-22T00:00:00+00:00",
        metadata={"source_bundle_id": "bundle:1"},
    )


def _citation() -> CitationAnnotation:
    return CitationAnnotation(
        citation_id="citation:1",
        answer_id=None,
        chunk_id="chunk:1",
        source_kind="local_x_db",
        source_id="tweet:1",
        source_url="https://x.com/a/status/1",
        title="tweet:1",
        field_path="chunk_text",
        support_type="supports_answer",
        evidence_status="supported",
        confidence=1.0,
        created_at="2026-06-22T00:00:00+00:00",
        metadata={"marker": "[1]"},
    )
