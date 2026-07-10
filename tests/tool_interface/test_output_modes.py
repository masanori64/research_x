from __future__ import annotations

import pytest

from research_x.memory.objective_routes import plan_objective_routes
from research_x.memory.output_modes import (
    OutputMode,
    mode_requires_citation,
    mode_requires_claim_support,
    mode_requires_evidence_package,
    mode_requires_source_restore,
    normalize_output_mode,
    output_mode_accepts_authority,
    output_mode_allows_answer_text,
)
from research_x.memory.search import MemorySearchResult
from research_x.tool_interface.memory_tool_contract import validate_tool_output_v2
from research_x.tool_interface.mode_aware_search import search_results_tool_output_v2

CANON_ITEMS = ("P5", "P7")
PURPOSE = "Guard mode routing so broad modes cannot silently become answers."
pytestmark = [pytest.mark.canon(item) for item in CANON_ITEMS]


def test_output_modes_have_strict_answer_only_requirements() -> None:
    for mode in (
        OutputMode.EXPLORE,
        OutputMode.COLLECT,
        OutputMode.WORKING_NOTE,
        OutputMode.SYNTHESIZE,
        OutputMode.EVIDENCE_PACKAGE,
    ):
        assert not output_mode_allows_answer_text(mode)
        assert not mode_requires_evidence_package(mode)
        assert not mode_requires_citation(mode)
        assert not mode_requires_claim_support(mode)

    assert mode_requires_source_restore("evidence_package")
    assert mode_requires_source_restore("answer")
    assert output_mode_allows_answer_text("answer")
    assert mode_requires_evidence_package("answer")
    assert mode_requires_citation("answer")
    assert mode_requires_claim_support("answer")


def test_output_mode_authority_boundary_is_mode_specific() -> None:
    assert output_mode_accepts_authority("explore", "candidate")
    assert output_mode_accepts_authority("collect", "source_backed")
    assert output_mode_accepts_authority("working_note", "candidate")
    assert output_mode_accepts_authority("synthesize", "claim_supported")
    assert output_mode_accepts_authority("evidence_package", "evidence_view")
    assert not output_mode_accepts_authority("evidence_package", "answer_assertion")
    assert output_mode_accepts_authority("answer", "answer_assertion")
    assert not output_mode_accepts_authority("answer", "claim_supported")


def test_objective_route_and_output_mode_are_independent_axes() -> None:
    explore = plan_objective_routes("robot note", output_mode="explore")
    answer = plan_objective_routes("robot note", output_mode="answer")

    assert explore.primary_route == answer.primary_route
    assert explore.fallback_routes == answer.fallback_routes
    assert explore.output_mode == "explore"
    assert "no_answer_assertion" in explore.must_run_guards
    assert "citation_required" not in explore.must_run_guards
    assert answer.output_mode == "answer"
    assert "source_restoration_required" in answer.must_run_guards
    assert "citation_required" in answer.must_run_guards
    assert "evidence_package_required" in answer.must_run_guards
    assert "claim_support_required" in answer.must_run_guards


def test_mode_aware_search_builds_non_answer_tool_outputs() -> None:
    for mode in ("explore", "collect", "synthesize"):
        output = search_results_tool_output_v2(
            query="robot",
            results=(_result(),),
            output_mode=mode,
        )

        assert output.output_mode == normalize_output_mode(mode).value
        assert output.answer_text is None
        assert validate_tool_output_v2(output) == []


def test_mode_aware_search_requires_working_note_id_and_rejects_answer() -> None:
    with pytest.raises(ValueError, match="working_note output_mode requires working_note_id"):
        search_results_tool_output_v2(
            query="robot",
            results=(_result(),),
            output_mode="working_note",
        )

    with pytest.raises(ValueError, match="cannot build answer output_mode"):
        search_results_tool_output_v2(
            query="robot",
            results=(_result(),),
            output_mode="answer",
        )


def test_mode_aware_search_accepts_evidence_view_package_only() -> None:
    output = search_results_tool_output_v2(
        query="robot",
        results=(
            _result(
                artifact_role="evidence_view",
                authority_level="evidence_view",
                source_status="available",
                risk_flags=(),
            ),
        ),
        output_mode="evidence_package",
    )

    assert output.status == "evidence_package"
    assert output.trace["citation_candidates"][0]["source_refs"] == ["x:tweet:tweet-1"]
    assert validate_tool_output_v2(output) == []

    with pytest.raises(ValueError, match="evidence_package items require evidence_view"):
        search_results_tool_output_v2(
            query="robot",
            results=(_result(),),
            output_mode="evidence_package",
        )


def _result(
    *,
    doc_id: str = "doc-1",
    artifact_role: str = "projection",
    authority_level: str = "candidate",
    source_status: str = "unknown",
    risk_flags: tuple[str, ...] = ("search_result_not_evidence",),
) -> MemorySearchResult:
    return MemorySearchResult(
        doc_id=doc_id,
        doc_type="tweet_doc",
        source_tweet_id="tweet-1",
        account_id="acct",
        author_screen_name="author",
        title="Robot note",
        compact_text="robot compact",
        score=1.5,
        match_method="fts",
        matched_terms=("robot",),
        score_components={"fts": 1.5},
        metadata={"route": "fixture"},
        source_refs=(),
        artifact_role=artifact_role,
        authority_level=authority_level,
        source_status=source_status,
        participation_snapshot=None,
        risk_flags=risk_flags,
    )
