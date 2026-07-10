from __future__ import annotations

from typing import Any

from research_x.memory import source_refs
from research_x.memory.output_modes import OutputMode, normalize_output_mode
from research_x.memory.search import MemorySearchResult
from research_x.tool_interface.memory_tool_contract import (
    CONTRACT_VERSION_V2,
    ToolOutputItemV2,
    ToolOutputV2,
    validate_tool_output_v2,
)

SEARCH_OUTPUT_MODES = frozenset(
    {
        OutputMode.EXPLORE,
        OutputMode.COLLECT,
        OutputMode.WORKING_NOTE,
        OutputMode.SYNTHESIZE,
        OutputMode.EVIDENCE_PACKAGE,
    }
)


def search_results_tool_output_v2(
    *,
    query: str,
    results: tuple[MemorySearchResult, ...],
    output_mode: str | OutputMode = OutputMode.EXPLORE,
    tool_kind: str = "research_x.memory.search",
    working_note_id: str | None = None,
) -> ToolOutputV2:
    mode = normalize_output_mode(output_mode)
    if mode is OutputMode.ANSWER:
        raise ValueError(
            "search result conversion cannot build answer output_mode; "
            "use evidence_package and answer validation gates"
        )
    if mode not in SEARCH_OUTPUT_MODES:
        raise ValueError(f"unsupported search output_mode: {mode.value}")
    if mode is OutputMode.WORKING_NOTE and not working_note_id:
        raise ValueError("working_note output_mode requires working_note_id")
    eligible_results = tuple(
        result for result in results if _result_allowed_for_mode(result, mode)
    )
    items = tuple(_result_item(result, output_mode=mode) for result in eligible_results)
    output = ToolOutputV2(
        contract_version=CONTRACT_VERSION_V2,
        tool_kind=tool_kind,
        query=query,
        output_mode=mode.value,
        status=_status_for_mode(mode),
        answer_text=None,
        items=items,
        citations=(),
        claim_support=None,
        working_note_id=working_note_id,
        trace=_trace_for_mode(
            mode,
            results=results,
            items=items,
            filtered_count=len(results) - len(eligible_results),
            working_note_id=working_note_id,
        ),
    )
    errors = validate_tool_output_v2(output)
    if errors:
        raise ValueError("; ".join(errors))
    return output


def _result_item(
    result: MemorySearchResult,
    *,
    output_mode: OutputMode,
) -> ToolOutputItemV2:
    source_refs = _source_refs(result)
    authority_level = result.authority_level
    source_status = result.source_status
    if source_refs and authority_level == "candidate" and source_status == "unknown":
        authority_level = "source_backed"
        source_status = "available"
    return ToolOutputItemV2(
        item_id=result.doc_id,
        subject_kind="memory_document",
        subject_id=result.doc_id,
        artifact_role=result.artifact_role,
        authority_level=authority_level,
        source_refs=source_refs,
        source_status=source_status,
        projection_id=f"memory_document:{result.doc_id}",
        score=result.score,
        why_relevant=result.match_method,
        risk_flags=result.risk_flags,
        metadata=_metadata(result, output_mode=output_mode),
    )


def _result_allowed_for_mode(result: MemorySearchResult, mode: OutputMode) -> bool:
    snapshot = result.participation_snapshot
    if not isinstance(snapshot, dict) or not snapshot:
        return True
    if mode is OutputMode.EXPLORE:
        return _snapshot_allows(snapshot, "can_explore", "can_search")
    if mode in {OutputMode.COLLECT, OutputMode.SYNTHESIZE}:
        return _snapshot_allows(snapshot, "can_search")
    if mode is OutputMode.WORKING_NOTE:
        return _snapshot_allows(snapshot, "can_use_in_working_note")
    if mode is OutputMode.EVIDENCE_PACKAGE:
        return _snapshot_allows(snapshot, "can_use_as_evidence")
    return False


def _snapshot_allows(snapshot: dict[str, Any], *keys: str) -> bool:
    present = [key for key in keys if key in snapshot]
    if not present:
        return False
    return any(snapshot.get(key) is True for key in present)


def _source_refs(result: MemorySearchResult) -> tuple[str, ...]:
    if result.source_refs:
        return result.source_refs
    if result.source_tweet_id:
        return (source_refs.x_tweet(result.source_tweet_id),)
    return ()


def _status_for_mode(mode: OutputMode) -> str:
    if mode is OutputMode.EVIDENCE_PACKAGE:
        return "evidence_package"
    return "ok"


def _trace_for_mode(
    mode: OutputMode,
    *,
    results: tuple[MemorySearchResult, ...],
    items: tuple[ToolOutputItemV2, ...],
    filtered_count: int,
    working_note_id: str | None,
) -> dict[str, Any]:
    trace: dict[str, Any] = {
        "mode_aware_search": {
            "output_mode": mode.value,
            "result_count": len(results),
            "emitted_item_count": len(items),
            "participation_filtered_count": filtered_count,
            "search_results_are_candidates": True,
            "answer_assertion_allowed": False,
        }
    }
    if mode is OutputMode.WORKING_NOTE:
        trace["working_note_id"] = working_note_id
        trace["working_note_from_search_candidates"] = True
    if mode is OutputMode.SYNTHESIZE:
        trace["unsupported_claims"] = []
        trace["unresolved_items"] = [
            item.item_id
            for item in items
            if not item.source_refs or item.source_status != "available"
        ]
        trace["synthesis_is_not_answer"] = True
    if mode is OutputMode.EVIDENCE_PACKAGE:
        trace["citation_candidates"] = [
            {
                "item_id": item.item_id,
                "source_refs": list(item.source_refs),
                "projection_id": item.projection_id,
                "source_status": item.source_status,
            }
            for item in items
        ]
    return trace


def _metadata(
    result: MemorySearchResult,
    *,
    output_mode: OutputMode,
) -> dict[str, Any]:
    return {
        "account_id": result.account_id,
        "author_screen_name": result.author_screen_name,
        "doc_type": result.doc_type,
        "matched_terms": list(result.matched_terms),
        "score_components": result.score_components,
        "search_metadata": result.metadata,
        "output_mode": output_mode.value,
        "search_result_output_mode": result.output_mode,
        "participation_snapshot": result.participation_snapshot,
        "title": result.title,
    }
