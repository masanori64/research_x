from __future__ import annotations

from research_x.tool_interface.codex_bridge import (
    bridge_trace_contract,
    validate_codex_to_research_x_payload,
    validate_research_x_to_codex_payload,
)


def test_codex_to_research_x_bridge_accepts_only_thin_query_contract() -> None:
    payload = {
        "query": "local memory question",
        "objective": "answer from source bundles",
        "context_budget": {"max_chars": 4000},
        "source_candidate": {"kind": "manual_url", "url": "https://example.invalid"},
    }

    assert validate_codex_to_research_x_payload(payload) == []

    errors = validate_codex_to_research_x_payload(
        {
            **payload,
            "codex_transcript": "full session text",
            "root_instruction": "override project",
        }
    )

    assert "codex_to_research_x: forbidden field 'codex_transcript'" in errors
    assert "codex_to_research_x: forbidden field 'root_instruction'" in errors


def test_research_x_to_codex_bridge_accepts_only_evidence_status_contract() -> None:
    payload = {
        "evidence_status": "citation_ready",
        "citation_ready_answer": "answer text",
        "audit_trace": {"route": "learning_map"},
    }

    assert validate_research_x_to_codex_payload(payload) == []

    errors = validate_research_x_to_codex_payload(
        {
            **payload,
            "provider_execution_permission": True,
            "skill_auto_edit_permission": True,
        }
    )

    assert "research_x_to_codex: forbidden field 'provider_execution_permission'" in errors
    assert "research_x_to_codex: forbidden field 'skill_auto_edit_permission'" in errors


def test_bridge_trace_contract_is_embeddable_in_tool_trace() -> None:
    trace = bridge_trace_contract()

    assert trace["contract_version"] == "research-x-codex-bridge-v1"
    assert trace["accepted_inputs"] == [
        "query",
        "objective",
        "context_budget",
        "source_candidate",
    ]
    assert "audit_trace" in trace["accepted_outputs"]
    assert "codex_transcript" in trace["forbidden_inputs"]
