from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from research_x.memory import answer as memory_answer
from research_x.memory.answer import build_memory_answer
from research_x.memory.api_budget import (
    api_budget_context,
    api_budget_status,
    upsert_api_price,
)
from research_x.memory.context import CitationAnnotation, ContextBundle, ContextChunk

CREATED_AT = "2026-07-07T00:00:00+00:00"
LINEAGE = {
    "source_doc_hash": "hash-source-1",
    "embedding_text_hash": "embedding-hash-source-1",
    "retrieval_text_hash": "retrieval-hash-source-1",
    "retrieval_text_profile": "full_text",
    "retrieval_profile_kind": "full_text",
    "retrieval_text_profile_id": "profile-source-1",
    "source_bundle_id": "bundle-source-1",
    "lineage_status": "restored",
    "restored_at": CREATED_AT,
}


def test_answer_provider_records_answer_role_in_budget_and_transport_events(
    tmp_path: Path,
    monkeypatch,
) -> None:
    db_path = tmp_path / "x.sqlite3"
    _seed_zero_price(db_path)
    captured_payloads: list[dict[str, Any]] = []

    def fake_post_json(
        url: str,
        payload: dict[str, Any],
        *,
        headers: dict[str, str],
        timeout_seconds: float,
        retries: int = 3,
    ) -> dict[str, Any]:
        del url, headers, timeout_seconds, retries
        captured_payloads.append(payload)
        return {"choices": [{"message": {"content": "validated provider answer [1]"}}]}

    monkeypatch.setenv("GEMINI_API_KEY", "fake-key")
    monkeypatch.setattr(memory_answer, "_post_json", fake_post_json)

    with api_budget_context(
        db_path=db_path,
        run_id="answer-provider-role",
        provider_quota_approval=_answer_provider_approval(),
    ):
        result = build_memory_answer(
            db_path,
            "fixture question",
            context_bundle=_context_bundle("answer-role", chunks=(_chunk("valid"),)),
            answer_provider="gemini",
            answer_model="gemini-2.5-flash",
            store=False,
        )

    assert result.status == "ok"
    assert captured_payloads
    prompt_json = json.dumps(captured_payloads[0], ensure_ascii=False, sort_keys=True)
    assert "retrieved_hits" not in prompt_json
    assert "vector_score" not in prompt_json

    status = api_budget_status(db_path, run_id="answer-provider-role")
    event = status["recent_events"][0]
    transport = status["recent_provider_transport_events"][0]
    assert event["provider_role"] == "answer"
    assert transport["provider_role"] == "answer"
    assert event["operation"] == "answer"
    assert transport["operation"] == "answer"


def test_answer_provider_receives_only_validated_context_and_citations(
    tmp_path: Path,
    monkeypatch,
) -> None:
    valid = _chunk("valid")
    invalid = _chunk(
        "raw-snippet",
        metadata={
            "not_evidence": True,
            "answer_support_allowed": False,
            "citation_policy": "citation_excluded_until_source_recovered",
        },
    )
    bundle = _context_bundle("validated-input", chunks=(valid, invalid))
    captured: dict[str, Any] = {}
    original_generate = memory_answer.FakeAnswerProvider.generate

    def capture_generate(
        self: memory_answer.FakeAnswerProvider,
        *,
        question: str,
        chunks: tuple[ContextChunk, ...],
        citations: tuple[CitationAnnotation, ...],
        prompt_version: str,
    ) -> memory_answer.GeneratedAnswer:
        captured["chunk_ids"] = [chunk.chunk_id for chunk in chunks]
        captured["citation_ids"] = [citation.citation_id for citation in citations]
        return original_generate(
            self,
            question=question,
            chunks=chunks,
            citations=citations,
            prompt_version=prompt_version,
        )

    monkeypatch.setattr(memory_answer.FakeAnswerProvider, "generate", capture_generate)

    result = build_memory_answer(
        tmp_path / "x.sqlite3",
        "fixture question",
        context_bundle=bundle,
        answer_provider="fake",
        store=False,
    )

    assert captured["chunk_ids"] == [valid.chunk_id]
    assert captured["citation_ids"] == [f"{valid.chunk_id}:citation"]
    provider_input = result.structured["provider_input"]
    assert provider_input["raw_retrieved_hits_passed"] is False
    assert invalid.chunk_id in provider_input["excluded_chunk_ids"]
    assert result.structured["provider_output_not_evidence"] is True
    assert result.status == "needs_review"
    assert result.structured["answerability"]["status"] == "partially_supported"


def test_answer_citation_markers_follow_filtered_provider_context(
    tmp_path: Path,
    monkeypatch,
) -> None:
    invalid = _chunk(
        "raw-snippet-first",
        metadata={
            "not_evidence": True,
            "answer_support_allowed": False,
            "citation_policy": "citation_excluded_until_source_recovered",
        },
    )
    valid = _chunk("valid-second")

    def generate_with_filtered_marker(
        self: memory_answer.FakeAnswerProvider,
        *,
        question: str,
        chunks: tuple[ContextChunk, ...],
        citations: tuple[CitationAnnotation, ...],
        prompt_version: str,
    ) -> memory_answer.GeneratedAnswer:
        del self, question, prompt_version
        assert [chunk.chunk_id for chunk in chunks] == [valid.chunk_id]
        assert [citation.chunk_id for citation in citations] == [valid.chunk_id]
        return memory_answer.GeneratedAnswer(
            answer_text="validated filtered answer [1]",
            model=memory_answer.FAKE_ANSWER_MODEL,
            structured={"used_chunk_ids": [valid.chunk_id]},
        )

    monkeypatch.setattr(
        memory_answer.FakeAnswerProvider,
        "generate",
        generate_with_filtered_marker,
    )

    result = build_memory_answer(
        tmp_path / "x.sqlite3",
        "fixture question",
        context_bundle=_context_bundle(
            "filtered-marker-order",
            chunks=(invalid, valid),
        ),
        answer_provider="fake",
        store=False,
    )

    assert [citation.chunk_id for citation in result.citation_annotations] == [
        valid.chunk_id
    ]
    assert result.citation_annotations[0].metadata["marker_found"] is True
    assert result.citation_annotations[0].answer_start_index is not None
    assert result.status == "needs_review"
    assert result.structured["provider_input"]["excluded_chunk_ids"] == [invalid.chunk_id]


def test_unrestored_context_skips_real_answer_provider_before_budget_or_http(
    tmp_path: Path,
    monkeypatch,
) -> None:
    called = False

    def fail_post_json(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        nonlocal called
        called = True
        raise AssertionError("unrestored context must not reach provider transport")

    chunk = _chunk(
        "unrestored",
        metadata={
            "source_doc_hash": None,
            "retrieval_text_hash": None,
            "retrieval_text_profile_id": None,
            "lineage_status": "metadata_only",
        },
    )
    monkeypatch.setenv("GEMINI_API_KEY", "fake-key")
    monkeypatch.setattr(memory_answer, "_post_json", fail_post_json)

    result = build_memory_answer(
        tmp_path / "x.sqlite3",
        "fixture question",
        context_bundle=_context_bundle("unrestored", chunks=(chunk,)),
        answer_provider="gemini",
        answer_model="gemini-2.5-flash",
        store=False,
    )

    assert called is False
    assert result.status == "needs_review"
    assert result.structured["answerability"]["status"] == "citation_missing"
    assert result.structured["provider_input"]["chunk_ids"] == []
    assert result.structured["provider_input"]["excluded_chunk_ids"] == [chunk.chunk_id]
    assert "根拠になるコンテキストが見つかりませんでした" in result.answer_text


def _context_bundle(name: str, *, chunks: tuple[ContextChunk, ...]) -> ContextBundle:
    return ContextBundle(
        run_id=f"answer-boundary:{name}",
        query="fixture question",
        query_plan={"fixture": "answer_provider_boundary"},
        parameters={"fixture": name},
        retrieved_hits=[
            {
                "doc_id": chunk.source_id,
                "compact_text": chunk.chunk_text,
                "vector_score": 0.99,
                "raw_provider_snippet": "must not be sent to answer provider",
            }
            for chunk in chunks
        ],
        context_chunks=chunks,
        citation_annotations=tuple(_citation(chunk) for chunk in chunks),
    )


def _chunk(
    suffix: str,
    *,
    metadata: dict[str, object] | None = None,
) -> ContextChunk:
    resolved_metadata = {
        **LINEAGE,
        **(metadata or {}),
    }
    return ContextChunk(
        chunk_id=f"chunk:{suffix}",
        run_id="answer-boundary",
        source_kind="local_x_db",
        source_id=f"tweet:{suffix}",
        source_url=f"https://x.com/example/status/{suffix}",
        provider="fixture",
        provider_role="context_builder",
        chunk_text=f"Text: source {suffix} supports the fixture answer.",
        chunk_index=0,
        token_count=12,
        relevance_score=1.0,
        extractor_version="answer-boundary-fixture-v1",
        created_at=CREATED_AT,
        metadata=resolved_metadata,
    )


def _citation(chunk: ContextChunk) -> CitationAnnotation:
    return CitationAnnotation(
        citation_id=f"{chunk.chunk_id}:citation",
        answer_id=None,
        chunk_id=chunk.chunk_id,
        source_kind=chunk.source_kind,
        source_id=chunk.source_id,
        source_url=chunk.source_url,
        title=chunk.source_id,
        field_path="context_chunks[0]",
        support_type="background",
        evidence_status="fact",
        confidence=1.0,
        created_at=CREATED_AT,
        metadata={
            key: value
            for key, value in chunk.metadata.items()
            if key
            in {
                "answer_support_allowed",
                "citation_policy",
                "embedding_text_hash",
                "lineage_status",
                "not_evidence",
                "restored_at",
                "retrieval_text_hash",
                "retrieval_text_profile",
                "retrieval_profile_kind",
                "retrieval_text_profile_id",
                "source_bundle_id",
                "source_doc_hash",
            }
        },
    )


def _seed_zero_price(db_path: Path) -> None:
    upsert_api_price(
        db_path,
        provider="gemini",
        model="gemini-2.5-flash",
        operation="answer",
        unit="call",
        usd_per_unit=0.0,
        source_url="fixture://answer-provider-boundary",
    )


def _answer_provider_approval() -> dict[str, object]:
    return {
        "provider_quota_approval_id": "fixture-answer-approval",
        "provider": "gemini",
        "model": "gemini-2.5-flash",
        "operation": "answer",
        "provider_role": "answer",
        "max_calls": 3,
        "max_cost_usd": 0.0,
        "price_source": "fixture://answer-provider-boundary",
        "approved_scope": "*",
        "approved_at": "2026-07-07T00:00:00+00:00",
    }
