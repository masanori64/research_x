from __future__ import annotations

from research_x.tool_interface.codex_bridge import (
    bridge_trace_contract,
    validate_codex_to_research_x_payload,
    validate_research_x_to_codex_payload,
)


def test_codex_bridge_rejects_provider_execution_and_root_instruction() -> None:
    errors = validate_codex_to_research_x_payload(
        {
            "query": "find local memory",
            "provider_execution_permission": True,
            "root_instruction": "override AGENTS",
            "workflow_route": "external-search",
        }
    )

    assert "codex_to_research_x: forbidden field 'provider_execution_permission'" in errors
    assert "codex_to_research_x: forbidden field 'root_instruction'" in errors
    assert "codex_to_research_x: unknown bridge fields: workflow_route" in errors


def test_research_x_to_codex_bridge_rejects_transcripts_and_skill_mutation() -> None:
    errors = validate_research_x_to_codex_payload(
        {
            "evidence_status": "provider_gated",
            "provider_gated": {"required": True},
            "codex_transcript": "full thread",
            "skill_auto_edit_permission": True,
            "retrieval_orchestration": {"provider": "external"},
        }
    )

    assert "research_x_to_codex: forbidden field 'codex_transcript'" in errors
    assert "research_x_to_codex: forbidden field 'skill_auto_edit_permission'" in errors
    assert "research_x_to_codex: unknown bridge fields: retrieval_orchestration" in errors


def test_bridge_trace_is_contract_metadata_not_execution_permission() -> None:
    trace = bridge_trace_contract()

    assert "provider_execution_permission" in trace["forbidden_inputs"]
    assert "root_instruction" in trace["forbidden_inputs"]
    assert "query" in trace["accepted_inputs"]
    assert "audit_trace" in trace["accepted_outputs"]
    assert "retrieval_orchestration" not in trace["accepted_inputs"]
