from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

from research_x.memory import evals as memory_evals
from research_x.memory.answer import build_memory_answer, store_memory_answer
from research_x.memory.audit import audit_memory_db
from research_x.memory.context import CitationAnnotation, ContextBundle, ContextChunk
from research_x.memory.dedup_policy import (
    DEDUP_CONFLICT_VARIANT_POLICY,
    DEDUP_LINEAGE_POLICY,
    DEDUP_LINEAGE_POLICY_SCOPE,
    DEDUP_SOURCE_HASH_VARIANT_POLICY,
    DEDUP_STALE_VARIANT_POLICY,
)
from research_x.memory.evals import EvalCase, load_eval_cases
from research_x.memory.workflow import MemoryWorkflow
from research_x.tool_interface.memory_tool_contract import (
    validate_tool_output,
    workflow_tool_output,
)

FIXTURE_CASES = Path("tests/fixtures/memory_eval_quality/retrieval_quality_cases.jsonl")
CREATED_AT = "2026-06-27T00:00:00+00:00"
LINEAGE_METADATA = {
    "source_doc_hash": "hash-source-1",
    "embedding_text_hash": "embedding-hash-source-1",
    "retrieval_text_hash": "retrieval-hash-source-1",
    "retrieval_text_profile": "full_text",
    "retrieval_profile_kind": "full_text",
    "retrieval_text_profile_id": "profile-source-1",
    "source_bundle_id": "bundle-source-1",
    "lineage_status": "restored",
    "restored_at": CREATED_AT,
    "dedup_lineage_policy": DEDUP_LINEAGE_POLICY,
    "dedup_lineage_policy_scope": DEDUP_LINEAGE_POLICY_SCOPE,
    "dedup_lineage_source_hash_variant_policy": DEDUP_SOURCE_HASH_VARIANT_POLICY,
    "dedup_lineage_stale_variant_policy": DEDUP_STALE_VARIANT_POLICY,
    "dedup_lineage_conflict_variant_policy": DEDUP_CONFLICT_VARIANT_POLICY,
    "dedup_lineage_policy_action": "no_lineage_variant",
}


def test_retrieval_quality_fixture_manifest_covers_required_families() -> None:
    cases = load_eval_cases(FIXTURE_CASES)

    assert {case.fixture_family for case in cases} >= {
        "answerability",
        "unanswerable",
        "conflict",
        "citation_support",
        "stop_condition",
        "dedup",
        "stale_judgment",
        "preview_search_result_only",
        "provider_free_limitation",
    }
    assert all(case.provider_free_fixture for case in cases)
    assert all(case.quality_scope == "boundary_wiring_not_model_quality" for case in cases)


def test_dedup_fixture_does_not_inflate_support(tmp_path: Path) -> None:
    positive_bundle = _bundle(
        "deduped",
        citation_metadata={
            "source_doc_hash": "hash-source-1",
            "duplicate_sources": ["bookmark:acct-a:source-1", "bookmark:acct-b:source-1"],
            "bookmark_accounts": ["acct-a", "acct-b"],
        },
    )
    duplicate_bundle = _bundle(
        "duplicate",
        duplicate_second_source=True,
        citation_metadata={"source_doc_hash": "hash-source-1"},
    )
    case = EvalCase(
        query="fixture dedup",
        required_any_terms=("fixture",),
        question_type="aggregation_count_rank",
        expected_answerability_status="answerable",
        min_answer_citations=1,
        required_source_kinds=("local_x_db",),
        require_citation_ready=True,
        expected_unique_evidence_count=1,
        max_duplicate_support_count=0,
        require_provenance_preserved=True,
        forbid_duplicate_citation_support=True,
        expected_dedup_lineage_policy=DEDUP_LINEAGE_POLICY,
        min_hit_score=0.0,
    )

    positive_answer = build_memory_answer(
        tmp_path / "positive.sqlite3",
        case.query,
        context_bundle=positive_bundle,
        store=False,
    )
    duplicate_answer = build_memory_answer(
        tmp_path / "duplicate.sqlite3",
        case.query,
        context_bundle=duplicate_bundle,
        store=False,
    )

    positive_result = memory_evals._evaluate_case(  # noqa: SLF001
        case,
        _workflow(case.query, positive_bundle, positive_answer),
        _hits(positive_bundle),
    )
    duplicate_result = memory_evals._evaluate_case(  # noqa: SLF001
        case,
        _workflow(case.query, duplicate_bundle, duplicate_answer),
        _hits(duplicate_bundle),
    )

    assert positive_result.status == "ok"
    assert positive_result.dedup_lineage_policy_violation_count == 0
    assert positive_result.dedup_lineage_policy_actions == ("no_lineage_variant",)
    assert positive_result.unique_evidence_count == 1
    assert positive_result.duplicate_support_count == 0
    assert duplicate_result.status == "fail"
    assert duplicate_result.unique_evidence_count == 1
    assert duplicate_result.duplicate_support_count == 1
    assert any(
        note.startswith("duplicate citation support forbidden")
        for note in duplicate_result.notes
    )


def test_dedup_policy_expected_fixture_fails_on_metadata_mismatch(
    tmp_path: Path,
) -> None:
    bundle = _bundle("dedup-policy")
    answer = build_memory_answer(
        tmp_path / "dedup_policy.sqlite3",
        "fixture dedup policy",
        context_bundle=bundle,
        store=False,
    )
    case = EvalCase(
        query="fixture dedup policy",
        required_any_terms=("fixture",),
        question_type="aggregation_count_rank",
        expected_answerability_status="answerable",
        min_answer_citations=1,
        required_source_kinds=("local_x_db",),
        require_citation_ready=True,
        expected_unique_evidence_count=1,
        max_duplicate_support_count=0,
        expected_dedup_lineage_policy=DEDUP_LINEAGE_POLICY,
        min_hit_score=0.0,
    )
    broken_answer = replace(
        answer,
        citation_annotations=(
            replace(
                answer.citation_annotations[0],
                metadata={
                    **answer.citation_annotations[0].metadata,
                    "dedup_lineage_policy": "visible_warning_only",
                },
            ),
        ),
    )

    positive_result = memory_evals._evaluate_case(  # noqa: SLF001
        case,
        _workflow(case.query, bundle, answer),
        _hits(bundle),
    )
    broken_result = memory_evals._evaluate_case(  # noqa: SLF001
        case,
        _workflow(case.query, bundle, broken_answer),
        _hits(bundle),
    )

    assert positive_result.status == "ok"
    assert positive_result.dedup_lineage_policy_violation_count == 0
    assert broken_result.status == "fail"
    assert broken_result.dedup_lineage_policy_violation_count == 1
    assert any(
        note.startswith("dedup lineage policy mismatch on answer_citation")
        for note in broken_result.notes
    )


def test_dedup_stale_variant_policy_mismatch_fails_eval_contract(
    tmp_path: Path,
) -> None:
    stale_bundle = _bundle(
        "dedup-stale-policy",
        citation_metadata={
            "source_hash_variant_count": 2,
            "stale_lineage_variant_present": True,
            "lineage_variant_warning": "stale",
            "freshness_status": "stale",
            "dedup_lineage_policy_action": DEDUP_SOURCE_HASH_VARIANT_POLICY,
        },
    )
    answer = build_memory_answer(
        tmp_path / "stale_policy.sqlite3",
        "fixture stale policy",
        context_bundle=stale_bundle,
        store=False,
    )
    case = EvalCase(
        query="fixture stale policy",
        required_any_terms=("fixture",),
        question_type="temporal_freshness",
        expected_dedup_lineage_policy=DEDUP_LINEAGE_POLICY,
        require_citation_ready=False,
        min_hit_score=0.0,
    )

    result = memory_evals._evaluate_case(  # noqa: SLF001
        case,
        _workflow(case.query, stale_bundle, answer),
        _hits(stale_bundle),
    )

    assert result.status == "fail"
    assert result.dedup_lineage_policy_violation_count >= 1
    assert any(
        note.startswith("dedup lineage policy action mismatch")
        and DEDUP_STALE_VARIANT_POLICY in note
        for note in result.notes
    )


def test_stale_and_preview_fixtures_block_answer_promotion(tmp_path: Path) -> None:
    fresh_bundle = _bundle("fresh")
    fresh_answer = build_memory_answer(
        tmp_path / "fresh.sqlite3",
        "fixture quality",
        context_bundle=fresh_bundle,
        store=False,
    )
    stale_answer = replace(
        fresh_answer,
        citation_annotations=(
            replace(
                fresh_answer.citation_annotations[0],
                metadata={
                    **fresh_answer.citation_annotations[0].metadata,
                    "freshness_status": "stale",
                },
            ),
        ),
    )
    preview_bundle = _bundle(
        "preview",
        citation_metadata={
            "not_evidence": True,
            "artifact_kind": "context_preview",
            "citation_policy": "citation_excluded",
        },
    )
    preview_answer = build_memory_answer(
        tmp_path / "preview.sqlite3",
        "fixture preview",
        context_bundle=preview_bundle,
        store=False,
    )

    stale_case = EvalCase(
        query="fixture stale",
        required_any_terms=("fixture",),
        question_type="temporal_freshness",
        forbid_stale_evidence_support=True,
        require_citation_ready=True,
        min_hit_score=0.0,
    )
    preview_case = EvalCase(
        query="fixture preview",
        required_any_terms=("fixture",),
        question_type="citation_required",
        forbid_not_evidence_support=True,
        require_citation_ready=True,
        min_hit_score=0.0,
    )

    stale_output = workflow_tool_output(_workflow(stale_case.query, fresh_bundle, stale_answer))
    stale_result = memory_evals._evaluate_case(  # noqa: SLF001
        stale_case,
        _workflow(stale_case.query, fresh_bundle, stale_answer),
        _hits(fresh_bundle),
    )
    preview_output = workflow_tool_output(
        _workflow(preview_case.query, preview_bundle, preview_answer)
    )
    preview_result = memory_evals._evaluate_case(  # noqa: SLF001
        preview_case,
        _workflow(preview_case.query, preview_bundle, preview_answer),
        _hits(preview_bundle),
    )

    assert stale_output.status == "needs_review"
    assert stale_output.trace["citation_quality"]["stale_evidence_count"] == 1
    assert stale_result.status == "fail"
    assert any(note.startswith("stale evidence support forbidden") for note in stale_result.notes)
    assert preview_answer.status == "needs_review"
    assert preview_answer.structured["answerability"]["status"] == "citation_missing"
    assert preview_output.status == "needs_review"
    assert preview_output.trace["citation_quality"]["not_evidence_count"] == 1
    assert preview_result.status == "fail"
    assert any(
        note.startswith("not-evidence support forbidden") for note in preview_result.notes
    )


def test_conflict_fixture_needs_review_and_preserves_both_sides(tmp_path: Path) -> None:
    bundle = _bundle("conflict", conflicting_second_source=True)
    answer = build_memory_answer(
        tmp_path / "conflict.sqlite3",
        "fixture conflict",
        context_bundle=bundle,
        store=False,
    )
    case = EvalCase(
        query="fixture conflict",
        required_any_terms=("fixture",),
        question_type="contradiction_support",
        expected_answerability_status="conflicting",
        min_answer_citations=2,
        required_source_kinds=("local_x_db",),
        min_hit_score=0.0,
    )

    output = workflow_tool_output(_workflow(case.query, bundle, answer))
    result = memory_evals._evaluate_case(  # noqa: SLF001
        case,
        _workflow(case.query, bundle, answer),
        _hits(bundle),
    )

    assert answer.structured["answerability"]["status"] == "conflicting"
    assert len(answer.citation_annotations) == 2
    assert output.status == "needs_review"
    assert output.trace["citation_quality"]["conflict_evidence_count"] == 1
    assert result.status == "needs_review"
    assert result.answerability_status == "conflicting"


def test_stop_condition_fixture_keeps_provider_gate_without_answer_promotion() -> None:
    bundle = _bundle("stop")
    workflow = _workflow(
        "fixture stop",
        bundle,
        None,
        stop_reason="external_context_needed",
        metadata={
            "parameters": {
                "answer_provider": "none",
                "llm_context_provider": "none",
                "external_reader_provider": "fake",
            },
            "stop_condition_audit": {
                "searched_after_sufficient_evidence": False,
                "redundant_search_count": 0,
            },
        },
    )
    case = EvalCase(
        query="fixture stop",
        required_any_terms=(),
        question_type="temporal_freshness",
        expected_stop_reasons=("external_context_needed",),
        allow_search_after_sufficient_evidence=False,
        min_hit_score=0.0,
    )

    payload = workflow_tool_output(workflow).as_dict()
    result = memory_evals._evaluate_case(  # noqa: SLF001
        case,
        workflow,
        _hits(bundle),
    )

    assert validate_tool_output(payload) == []
    assert payload["status"] == "provider_gated"
    assert payload["answer_text"] is None
    assert payload["trace"]["provider_gate"]["required"] is True
    assert result.status == "ok"
    assert result.stop_reason == "external_context_needed"


def test_provider_free_fixture_declares_boundary_only_scope(tmp_path: Path) -> None:
    bundle = _bundle("provider-free")
    answer = build_memory_answer(
        tmp_path / "provider_free.sqlite3",
        "fixture provider free",
        context_bundle=bundle,
        store=False,
    )
    valid_case = EvalCase(
        query="fixture provider free",
        required_any_terms=("fixture",),
        question_type="citation_required",
        provider_free_fixture=True,
        quality_scope="boundary_wiring_not_model_quality",
        min_hit_score=0.0,
    )
    invalid_case = replace(valid_case, quality_scope="model_quality_verified")

    valid_result = memory_evals._evaluate_case(  # noqa: SLF001
        valid_case,
        _workflow(valid_case.query, bundle, answer),
        _hits(bundle),
    )
    invalid_result = memory_evals._evaluate_case(  # noqa: SLF001
        invalid_case,
        _workflow(invalid_case.query, bundle, answer),
        _hits(bundle),
    )

    assert valid_result.status == "ok"
    assert valid_result.provider_free_fixture is True
    assert valid_result.quality_scope == "boundary_wiring_not_model_quality"
    assert invalid_result.status == "fail"
    assert any(
        note.startswith("provider-free fixture missing boundary-only quality scope")
        for note in invalid_result.notes
    )


def test_citation_support_negative_aligns_with_audit(tmp_path: Path) -> None:
    db_path = tmp_path / "audit.sqlite3"
    bundle = _bundle("unsupported")
    answer = build_memory_answer(db_path, "fixture unsupported", context_bundle=bundle, store=False)
    unsupported_citation = replace(
        answer.citation_annotations[0],
        support_type="uncited_context",
    )
    unsupported_answer = replace(
        answer,
        status="ok",
        citation_annotations=(unsupported_citation,),
    )
    case = EvalCase(
        query="fixture unsupported",
        required_any_terms=("fixture",),
        question_type="citation_required",
        require_citation_ready=True,
        min_hit_score=0.0,
    )

    result = memory_evals._evaluate_case(  # noqa: SLF001
        case,
        _workflow(case.query, bundle, unsupported_answer),
        _hits(bundle),
    )
    store_memory_answer(db_path, unsupported_answer)
    audit = audit_memory_db(db_path)

    assert result.status == "fail"
    assert result.non_ready_citation_count == 1
    assert any(note.startswith("citation support not ready") for note in result.notes)
    assert audit.claim_citation_issues["ok_answer_with_uncited_context"] == 1
    assert audit.claim_citation_issues["ok_answer_cites_non_ready_evidence"] == 1


def _bundle(
    name: str,
    *,
    duplicate_second_source: bool = False,
    conflicting_second_source: bool = False,
    citation_metadata: dict[str, object] | None = None,
) -> ContextBundle:
    run_id = f"fixture:{name}"
    base_metadata = {
        "answerability_fixture": "answerable",
        **LINEAGE_METADATA,
    }
    base_metadata.update(citation_metadata or {})
    chunks = [
        _chunk(
            run_id=run_id,
            chunk_id=f"{run_id}:chunk:1",
            source_id="tweet:source-1",
            source_url="https://x.com/example/status/source-1",
            text="Text: fixture source one supports the local answer.",
            metadata={"answerability_fixture": "answerable", **LINEAGE_METADATA},
        )
    ]
    if duplicate_second_source or conflicting_second_source:
        second_source_id = "tweet:source-1" if duplicate_second_source else "tweet:source-2"
        chunks.append(
            _chunk(
                run_id=run_id,
                chunk_id=f"{run_id}:chunk:2",
                source_id=second_source_id,
                source_url=f"https://x.com/example/status/{second_source_id.removeprefix('tweet:')}",
                text="Text: fixture source two is either duplicate or contradicting evidence.",
                index=1,
                metadata={
                    **LINEAGE_METADATA,
                    "answerability_fixture": (
                        "conflicting" if conflicting_second_source else "answerable"
                    ),
                },
            )
        )
    citations = []
    for index, chunk in enumerate(chunks):
        metadata = dict(base_metadata)
        if index == 1 and conflicting_second_source:
            metadata["answerability_fixture"] = "conflicting"
            metadata["relation_type"] = "contradicts"
        support_type = (
            "contradicts" if index == 1 and conflicting_second_source else "background"
        )
        citations.append(
            CitationAnnotation(
                citation_id=f"{chunk.chunk_id}:citation",
                answer_id=None,
                chunk_id=chunk.chunk_id,
                source_kind=chunk.source_kind,
                source_id=chunk.source_id,
                source_url=chunk.source_url,
                title=chunk.source_id,
                field_path=f"context_chunks[{index}]",
                support_type=support_type,
                evidence_status="fact",
                confidence=1.0,
                created_at=CREATED_AT,
                metadata=metadata,
            )
        )
    return ContextBundle(
        run_id=run_id,
        query=f"fixture {name}",
        query_plan={"fixture": "retrieval_quality"},
        parameters={"fixture": name},
        retrieved_hits=_hits_from_chunks(chunks),
        context_chunks=tuple(chunks),
        citation_annotations=tuple(citations),
    )


def _chunk(
    *,
    run_id: str,
    chunk_id: str,
    source_id: str,
    source_url: str,
    text: str,
    metadata: dict[str, object],
    index: int = 0,
) -> ContextChunk:
    return ContextChunk(
        chunk_id=chunk_id,
        run_id=run_id,
        source_kind="local_x_db",
        source_id=source_id,
        source_url=source_url,
        provider="fixture",
        provider_role="context_builder",
        chunk_text=text,
        chunk_index=index,
        token_count=16,
        relevance_score=1.0,
        extractor_version="retrieval-quality-fixture-v1",
        created_at=CREATED_AT,
        metadata=metadata,
    )


def _workflow(
    query: str,
    bundle: ContextBundle,
    answer,
    *,
    stop_reason: str = "enough_evidence",
    metadata: dict[str, object] | None = None,
) -> MemoryWorkflow:
    return MemoryWorkflow(
        workflow_id=f"{bundle.run_id}:workflow",
        query=query,
        route="local_memory_search",
        status="ok" if stop_reason == "enough_evidence" else "needs_review",
        stop_reason=stop_reason,
        started_at=CREATED_AT,
        finished_at=CREATED_AT,
        metadata=metadata or {},
        steps=(),
        context_bundle=bundle,
        answer=answer,
    )


def _hits(bundle: ContextBundle) -> list[dict[str, object]]:
    return _hits_from_chunks(list(bundle.context_chunks))


def _hits_from_chunks(chunks: list[ContextChunk]) -> list[dict[str, object]]:
    return [
        {
            "doc_id": chunk.source_id,
            "tweet_id": chunk.source_id.removeprefix("tweet:"),
            "doc_type": "tweet_doc",
            "title": chunk.source_id,
            "compact_text": chunk.chunk_text,
            "score": chunk.relevance_score,
            "matched_terms": ["fixture"],
            "evidence": {"url": chunk.source_url},
            "metadata": {},
        }
        for chunk in chunks
    ]


def test_fixture_cases_file_is_jsonl() -> None:
    rows = [
        json.loads(line)
        for line in FIXTURE_CASES.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]

    assert len(rows) >= 9
    assert all("fixture_family" in row for row in rows)
