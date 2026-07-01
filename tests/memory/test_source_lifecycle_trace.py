from __future__ import annotations

from research_x.memory.source_lifecycle import build_source_lifecycle_trace


def test_source_lifecycle_trace_keeps_state_counts_without_runtime_mutation() -> None:
    trace = build_source_lifecycle_trace(
        discovered_ids=("tweet:1", "tweet:2"),
        eligible_ids=("tweet:1", "tweet:2"),
        fetched_ids=("tweet:1",),
        extracted_ids=("tweet:1",),
        source_bundled_ids=("tweet:1",),
        chunked_ids=("chunk:1",),
        indexed_ids=("tweet:1",),
        retrieved_ids=("tweet:1", "tweet:2"),
        included_ids=("tweet:1",),
        reflected_ids=("tweet:1",),
        cited_ids=("tweet:1",),
        citation_ready_ids=("tweet:1",),
        user_export_required_ids=("tweet:2",),
    )

    assert trace["evidence_role"] == "control_plane_not_answer_evidence"
    assert trace["answer_support_allowed"] is False
    assert trace["runtime_source_mutation_allowed"] is False
    assert trace["state_counts"]["source_bundled"] == 1
    assert trace["state_counts"]["citation_ready"] == 1
    assert trace["state_counts"]["user_export_required"] == 1
    assert trace["blocked_count"] == 1
    assert {(transition["from"], transition["to"]) for transition in trace["transitions"]} >= {
        ("extracted", "source_bundled"),
        ("source_bundled", "chunked"),
        ("cited", "citation_ready"),
    }
    assert all(
        transition["runtime_mutation_allowed"] is False for transition in trace["transitions"]
    )
