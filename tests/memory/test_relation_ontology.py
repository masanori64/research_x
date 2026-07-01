from __future__ import annotations

from research_x.memory.relation_ontology import build_relation_ontology_trace


def test_relation_ontology_trace_is_candidate_only_control_plane() -> None:
    trace = build_relation_ontology_trace(
        relations=[
            {
                "relation_type": "supports",
                "source_doc_id": "tweet:1",
                "target_doc_id": "tweet:2",
                "as_of": "2026-07-01",
                "authority_source": "local_fixture",
                "citation_anchor": "chunk:1",
            }
        ],
        relation_counts={"supports": 1},
    )

    assert trace["candidate_only"] is True
    assert trace["answer_support_allowed"] is False
    assert trace["runtime_graph_adopted"] is False
    assert trace["unknown_relation_types"] == []
    assert trace["type_specs"]["supports"]["citation_anchor_required"] is True
    assert trace["coverage"]["missing_citation_anchor_count"] == 0
    assert "restored context chunks" in trace["promotion_boundary"]


def test_relation_ontology_trace_exposes_unknown_and_missing_dimensions() -> None:
    trace = build_relation_ontology_trace(
        relations=[
            {
                "relation_type": "supports",
                "source_doc_id": "tweet:1",
                "target_doc_id": "tweet:2",
            },
            {
                "relation_type": "custom_edge",
                "source_doc_id": "tweet:3",
                "target_doc_id": "tweet:4",
            },
        ],
        relation_counts={"custom_edge": 1},
    )

    assert trace["unknown_relation_types"] == ["custom_edge"]
    assert trace["coverage"]["missing_temporal_validity_count"] == 1
    assert trace["coverage"]["missing_authority_source_count"] == 0
    assert trace["coverage"]["missing_citation_anchor_count"] == 0
