from __future__ import annotations

import copy
import json

from research_x.control_artifacts import render_control_artifact_html
from research_x.control_artifacts.sanitize import validate_safe_review_html
from research_x.memory.objective_routes import plan_objective_routes
from research_x.memory.research_artifacts import (
    build_query_plan_visualization_payload,
    validate_query_plan_visualization_payload,
)


def test_query_plan_visualization_is_review_only_and_redacts_raw_query_text() -> None:
    plan = plan_objective_routes(
        "DROP TABLE users; mysql password dsn https://example.com source search"
    )

    payload = build_query_plan_visualization_payload(plan)
    html = render_control_artifact_html(payload)
    payload_text = json.dumps(payload, ensure_ascii=False).casefold()

    assert validate_query_plan_visualization_payload(payload) == []
    assert validate_safe_review_html(html) == []
    assert payload["view_kind"] == "query_plan_review"
    assert payload["not_evidence"] is True
    assert payload["answer_support_allowed"] is False
    assert payload["source_artifacts"][0]["artifact_kind"] == "search_plan_graph"
    assert "text_redacted=true" in payload_text
    assert "drop table" not in payload_text
    assert "mysql password dsn" not in payload_text
    assert "https://example.com" not in payload_text
    assert "Not evidence / Review artifact only" in html


def test_query_plan_visualization_rejects_sql_or_credential_shaped_fields() -> None:
    plan = plan_objective_routes("source search")
    payload = build_query_plan_visualization_payload(plan)
    unsafe = copy.deepcopy(payload)
    unsafe["sections"][0]["sql"] = "select * from memory"
    unsafe["sections"][0]["dsn"] = "mysql://user:password@example/db"

    errors = validate_query_plan_visualization_payload(unsafe)

    assert any("sections[0].sql" in error for error in errors)
    assert any("sections[0].dsn" in error for error in errors)


def test_query_plan_visualization_rejects_remote_script_or_mutation_text() -> None:
    plan = plan_objective_routes("source search")
    payload = build_query_plan_visualization_payload(plan)
    unsafe = copy.deepcopy(payload)
    unsafe["sections"][0]["items"].extend(
        [
            "https://example.com/remote.js",
            "<script>alert(1)</script>",
            "DROP TABLE memory_documents",
        ]
    )

    errors = validate_query_plan_visualization_payload(unsafe)

    assert "query_plan_visualization contains executable or SQL text" in errors


def test_query_plan_visualization_rejects_nested_list_sql_fields() -> None:
    plan = plan_objective_routes("source search")
    payload = build_query_plan_visualization_payload(plan)
    unsafe = copy.deepcopy(payload)
    unsafe["sections"][0]["items"].append({"sql": "select * from memory"})

    errors = validate_query_plan_visualization_payload(unsafe)

    assert any(
        "sections[0].items[" in error and "].sql" in error for error in errors
    )


def test_query_plan_visualization_rejects_script_keys_and_neutral_sql_text() -> None:
    plan = plan_objective_routes("source search")
    payload = build_query_plan_visualization_payload(plan)
    unsafe = copy.deepcopy(payload)
    unsafe["sections"][0]["script_url"] = "memory://local-script"
    unsafe["sections"][0]["items"].extend(
        [
            "SELECT * FROM memory_documents",
            "mysql route adapter",
        ]
    )

    errors = validate_query_plan_visualization_payload(unsafe)

    assert any("sections[0].script_url" in error for error in errors)
    assert "query_plan_visualization contains executable or SQL text" in errors
