from __future__ import annotations

import json
from pathlib import Path

import pytest

from research_x.cli import main
from research_x.memory.embeddings import build_memory_embeddings
from research_x.memory.objective_routes import (
    CANONICAL_RETRIEVAL_ROUTE_TAGS,
    plan_route_aware_retrieval,
)
from research_x.memory.search import format_search_results, search_memory


def test_route_aware_retrieval_tags_match_canonical_plan() -> None:
    assert CANONICAL_RETRIEVAL_ROUTE_TAGS == (
        "general_semantic",
        "japanese_or_crosslingual",
        "technical_or_code",
        "relation_heavy",
        "media_content",
        "time_sensitive",
        "external_needed",
        "exact_identifier",
        "account_specific",
        "conflict_sensitive",
    )


def test_multi_space_route_is_metadata_only_without_explicit_space(
    vector_db_path: Path,
) -> None:
    build_memory_embeddings(vector_db_path, provider="local_hash", dimensions=32)

    plan = plan_route_aware_retrieval(
        "ロボット paper",
        requested_route="japanese_or_crosslingual",
    )
    results = search_memory(
        vector_db_path,
        "robot paper",
        limit=2,
        route="japanese_or_crosslingual",
        semantic_provider="local_hash",
        semantic_dimensions=32,
    )

    assert plan.semantic_space_ids == (
        "text.general_memory.v1",
        "text.jp_multilingual.v1",
    )
    assert len({choice.engine_run_id for choice in plan.semantic_engine_choices}) == 2
    assert plan.as_dict()["fusion_contract"]["raw_score_fusion_allowed"] is False
    assert results
    route_metadata = results[0].metadata["route_plan"]
    semantic_execution = results[0].metadata["route_semantic_execution"]
    assert route_metadata["multiple_semantic_spaces"] == "separate_engine_runs_only"
    assert route_metadata["raw_score_fusion_allowed"] is False
    assert semantic_execution["status"] == "skipped_requires_explicit_single_space"
    assert all("semantic" not in result.metadata for result in results)


def test_external_needed_route_skips_provider_gated_semantic_choices(
    vector_db_path: Path,
) -> None:
    build_memory_embeddings(vector_db_path, provider="local_hash", dimensions=32)

    plan = plan_route_aware_retrieval(
        "最新 web robot paper",
        requested_route="external_needed",
    )
    results = search_memory(
        vector_db_path,
        "latest web robot paper",
        limit=2,
        route="external_needed",
        semantic_provider="local_hash",
        semantic_dimensions=32,
    )

    assert plan.semantic_space_ids == ("external.fetch_text.v1",)
    assert plan.executable_semantic_space_ids == ()
    assert results
    semantic_execution = results[0].metadata["route_semantic_execution"]
    assert semantic_execution["status"] == "skipped_no_executable_route_semantic_choice"
    assert semantic_execution["executable_semantic_space_ids"] == ()
    assert semantic_execution["blocked_semantic_space_ids"] == ("external.fetch_text.v1",)
    assert all("semantic" not in result.metadata for result in results)


def test_route_semantic_space_and_profile_must_match_selected_route(
    vector_db_path: Path,
) -> None:
    summary = build_memory_embeddings(vector_db_path, provider="local_hash", dimensions=32)

    with pytest.raises(ValueError, match="outside route"):
        search_memory(
            vector_db_path,
            "robot paper",
            route="technical_or_code",
            semantic_provider="local_hash",
            semantic_space_id=summary.space_id,
            semantic_dimensions=32,
        )
    with pytest.raises(ValueError, match="outside route"):
        search_memory(
            vector_db_path,
            "robot paper",
            route="technical_or_code",
            semantic_provider="local_hash",
            semantic_profile="general_memory",
            semantic_dimensions=32,
        )
    with pytest.raises(ValueError, match="provider-gated or unavailable"):
        search_memory(
            vector_db_path,
            "latest web robot paper",
            route="external_needed",
            semantic_provider="local_hash",
            semantic_space_id="external.fetch_text.v1",
            semantic_dimensions=32,
        )


def test_route_default_semantic_profile_is_used_without_user_profile(
    vector_db_path: Path,
) -> None:
    build_memory_embeddings(vector_db_path, provider="local_hash", dimensions=32)

    results = search_memory(
        vector_db_path,
        "robot paper",
        limit=2,
        route="general_semantic",
        semantic_provider="local_hash",
        semantic_dimensions=32,
    )

    assert results
    semantic_execution = results[0].metadata["route_semantic_execution"]
    assert semantic_execution["status"] == "route_default_single_semantic_profile"
    assert semantic_execution["route_semantic_space_id"] == "text.general_memory.v1"
    assert semantic_execution["effective_embedding_profile"] == "general_memory"
    semantic_rows = [
        result.metadata["semantic"] for result in results if "semantic" in result.metadata
    ]
    assert semantic_rows
    assert {row["embedding_profile"] for row in semantic_rows} == {"general_memory"}


def test_explicit_provider_specific_space_is_validated_against_route_profile(
    vector_db_path: Path,
) -> None:
    summary = build_memory_embeddings(vector_db_path, provider="local_hash", dimensions=32)

    results = search_memory(
        vector_db_path,
        "robot paper",
        limit=2,
        route="general_semantic",
        semantic_provider="local_hash",
        semantic_space_id=summary.space_id,
        semantic_dimensions=32,
    )

    assert results
    semantic_execution = results[0].metadata["route_semantic_execution"]
    assert semantic_execution["route_semantic_space_id"] == "text.general_memory.v1"
    assert semantic_execution["effective_semantic_space_id"] == summary.space_id
    semantic_rows = [
        result.metadata["semantic"] for result in results if "semantic" in result.metadata
    ]
    assert semantic_rows
    assert {row["space_id"] for row in semantic_rows} == {summary.space_id}


def test_handle_auto_route_is_account_specific_not_exact_identifier() -> None:
    plan = plan_route_aware_retrieval("@robotics robot paper", requested_route="auto")

    assert plan.route_tag == "account_specific"
    assert plan.reasoning["selection"] == "author_or_account_signal"


def test_memory_search_route_json_exposes_engine_choices_and_candidate_policy(
    vector_db_path: Path,
    capsys,
) -> None:
    build_memory_embeddings(vector_db_path, provider="local_hash", dimensions=32)

    assert (
        main(
            [
                "memory",
                "search",
                "--db",
                str(vector_db_path),
                "--query",
                "robot paper",
                "--route",
                "general_semantic",
                "--semantic-provider",
                "local_hash",
                "--semantic-dimensions",
                "32",
                "--json",
            ]
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)
    semantic_choices = [
        choice
        for choice in payload["route_plan"]["engine_choices"]
        if choice["engine"] == "semantic"
    ]
    semantic_metadata = [
        result["metadata"]["semantic"]
        for result in payload["results"]
        if "semantic" in result["metadata"]
    ]
    semantic_components = [
        result["score_components"]["semantic"]
        for result in payload["results"]
        if "semantic" in result["metadata"]
    ]

    assert payload["route_plan"]["route_tag"] == "general_semantic"
    assert semantic_choices
    assert semantic_choices[0]["semantic_space_id"] == "text.general_memory.v1"
    assert semantic_choices[0]["candidate_only"] is True
    assert semantic_choices[0]["answer_support_allowed"] is False
    assert (
        payload["route_plan"]["engine_choices_role"]
        == "advisory_route_choices_not_an_execution_log"
    )
    assert payload["route_plan"]["search_execution_contract"]["local_baseline_engines"] == [
        "fts",
        "like",
        "metadata",
        "retrieval_text",
        "relation_expansion",
    ]
    assert payload["route_plan"]["fusion_contract"]["raw_score_fusion_allowed"] is False
    assert payload["results"]
    first_route_execution = payload["results"][0]["metadata"]["route_execution"]
    assert "local_baseline_engines" in first_route_execution
    assert first_route_execution["advisory_engine_choice_ids"]
    assert semantic_metadata
    for row in semantic_metadata:
        assert row["provider"] == "local_hash"
        assert row["candidate_only"] is True
        assert row["evidence_role"] == "retrieval_candidate_signal"
        assert row["answer_support_allowed"] is False
        assert row["raw_score_fusion_allowed"] is False
        assert row["promotion_gate"] == "source_bundle_context_citation_required"
        assert row["weight"] == 0.0
        assert row["legacy_raw_score_component"] is False
    assert semantic_components
    assert all(component == 0.0 for component in semantic_components)


def test_plain_route_output_marks_choices_as_advisory(
    vector_db_path: Path,
) -> None:
    build_memory_embeddings(vector_db_path, provider="local_hash", dimensions=32)
    plan = plan_route_aware_retrieval("robot paper", requested_route="general_semantic")
    results = search_memory(
        vector_db_path,
        "robot paper",
        limit=1,
        route="general_semantic",
        semantic_provider="local_hash",
        semantic_dimensions=32,
    )

    plain = format_search_results(results, route_plan=plan)

    assert "route_choices(advisory):" in plain
    assert (
        "local_baseline(executed): fts, like, metadata, retrieval_text, relation_expansion"
        in plain
    )
