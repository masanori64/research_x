from __future__ import annotations

import pytest

from research_x.tool_interface.memory_tool_contract import (
    CONTRACT_VERSION_V2,
    ToolCitation,
    ToolOutputItemV2,
    ToolOutputV2,
    validate_tool_output_v2,
)

CANON_ITEMS = ("P10", "L7")
PURPOSE = "Guard strict answer assertion fields and non-answer mode boundaries."
pytestmark = [pytest.mark.canon(item) for item in CANON_ITEMS]


@pytest.mark.parametrize("mode", ("explore", "collect", "working_note", "synthesize"))
def test_non_answer_modes_reject_answer_assertion_shape(mode: str) -> None:
    output = _output(
        output_mode=mode,
        answer_text="This is an answer.",
        item=_item(authority_level="answer_assertion"),
        working_note_id="note-1" if mode == "working_note" else None,
    )

    errors = validate_tool_output_v2(output)

    assert any(f"{mode} output must not include answer_text" in error for error in errors)
    assert any(f"{mode} items cannot be answer_assertion" in error for error in errors)


def test_evidence_package_rejects_answer_assertion() -> None:
    output = _output(
        output_mode="evidence_package",
        status="evidence_package",
        item=_item(artifact_role="evidence_view", authority_level="answer_assertion"),
        trace={"citation_candidates": []},
    )

    assert any(
        "evidence_package items require evidence_view authority" in error
        for error in validate_tool_output_v2(output)
    )


@pytest.mark.parametrize(
    ("field", "expected_error"),
    (
        ("citations", "answer output requires citations"),
        ("claim_support", "answer output requires claim_support"),
        ("db_backed_validation", "answer output requires passed db_backed_validation"),
    ),
)
def test_answer_requires_citation_claim_support_and_db_validation(
    field: str,
    expected_error: str,
) -> None:
    kwargs = {
        "output_mode": "answer",
        "status": "answer",
        "answer_text": "Supported answer.",
        "item": _item(artifact_role="evidence_view", authority_level="answer_assertion"),
        "citations": (_citation(),),
        "claim_support": _claim_support(),
        "trace": {"db_backed_validation": {"status": "passed"}},
    }
    if field == "citations":
        kwargs["citations"] = ()
    elif field == "claim_support":
        kwargs["claim_support"] = None
    else:
        kwargs["trace"] = {}

    errors = validate_tool_output_v2(_output(**kwargs))

    assert any(expected_error in error for error in errors)


def test_answer_with_strict_fields_is_valid() -> None:
    output = _output(
        output_mode="answer",
        status="answer",
        answer_text="Supported answer.",
        item=_item(artifact_role="evidence_view", authority_level="answer_assertion"),
        citations=(_citation(),),
        claim_support=_claim_support(),
        trace={"db_backed_validation": {"status": "passed"}},
    )

    assert validate_tool_output_v2(output) == []


def _output(
    *,
    output_mode: str,
    item: ToolOutputItemV2,
    status: str = "ok",
    answer_text: str | None = None,
    citations: tuple[ToolCitation, ...] = (),
    claim_support: dict[str, object] | None = None,
    working_note_id: str | None = None,
    trace: dict[str, object] | None = None,
) -> ToolOutputV2:
    return ToolOutputV2(
        contract_version=CONTRACT_VERSION_V2,
        tool_kind=f"research_x.memory.{output_mode}",
        query="fixture",
        output_mode=output_mode,
        status=status,
        answer_text=answer_text,
        items=(item,),
        citations=citations,
        claim_support=claim_support,
        working_note_id=working_note_id,
        trace=trace or {},
    )


def _item(
    *,
    artifact_role: str = "projection",
    authority_level: str = "candidate",
) -> ToolOutputItemV2:
    return ToolOutputItemV2(
        item_id="item-1",
        subject_kind="memory_document",
        subject_id="doc-1",
        artifact_role=artifact_role,
        authority_level=authority_level,
        source_refs=("x:tweet:tweet-1",),
        source_status="available",
        projection_id=None,
        score=0.8,
        why_relevant="fixture",
        risk_flags=(),
        metadata={},
    )


def _citation() -> ToolCitation:
    return ToolCitation(
        citation_id="citation-1",
        chunk_id="chunk-1",
        source_kind="tweet",
        source_id="tweet-1",
        source_url="https://x.example/status/tweet-1",
        title="Tweet",
        evidence_status="citation_ready",
        citation_ready=True,
        restore={"lineage_status": "restored"},
    )


def _claim_support() -> dict[str, object]:
    return {
        "status": "supported",
        "claims": [
            {
                "claim_id": "claim-1",
                "support_status": "supported",
                "citation_ids": ["citation-1"],
            }
        ],
    }
