from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from test_embedding_input_taxonomy import _seed_taxonomy_db

from research_x.memory.embedding_input import (
    build_embedding_template_examples,
    classify_embedding_inputs,
    default_template_policies,
    render_template,
    write_default_template_policies,
)


def test_embedding_template_examples_are_stable_and_label_bookmarks(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "templates.sqlite3"
    report_dir = tmp_path / "reports"
    _seed_taxonomy_db(db_path)
    classify_embedding_inputs(db_path, write=True, report_dir=report_dir)
    policy = write_default_template_policies(db_path, report_dir=report_dir)

    first = build_embedding_template_examples(
        db_path,
        limit=50,
        write=True,
        report_dir=report_dir,
    )
    second = build_embedding_template_examples(
        db_path,
        limit=50,
        write=False,
        report_dir=report_dir,
    )

    assert policy["template_count"] >= 13
    assert [row["embedded_text_hash"] for row in first] == [
        row["embedded_text_hash"] for row in second
    ]
    bookmark = _example(first, doc_id="doc:bookmark", profile="bookmark_interest")
    assert "Bookmarking is not necessarily endorsement" in bookmark["embedded_text"]
    assert "not the user's authored opinion" in bookmark["embedded_text"]
    derived = _example(first, doc_id="doc:derived", profile="author_profile_route")
    assert "This derived projection is not evidence" in derived["embedded_text"]

    with sqlite3.connect(db_path) as conn:
        stored = conn.execute(
            "SELECT COUNT(*) FROM memory_embedding_template_examples"
        ).fetchone()[0]
    assert stored == len({row["example_id"] for row in first})


def test_embedding_template_renderer_redacts_secret_like_text() -> None:
    policy = next(
        item
        for item in default_template_policies()
        if item.template_version == "authored_tweet.embedding.v1"
    )
    taxonomy = {
        "source_kind": "x_authored_tweet",
        "ownership_kind": "authored_by_tracked_account",
        "content_role": "statement",
        "relation_role": "standalone",
        "author_id": "me",
        "tweet_id": "tweet-secret",
        "language": "en",
    }
    doc = {
        "title": "Secret-like source",
        "body": "api_key=abc123 should be hidden but the memory text remains",
        "compact_text": "api_key=abc123 should be hidden",
        "metadata_json": json.dumps({"cookie": "session=raw"}),
    }

    first = render_template(policy, taxonomy, doc)
    second = render_template(policy, taxonomy, doc)

    assert first["embedded_text_hash"] == second["embedded_text_hash"]
    assert "api_key=[REDACTED]" in first["embedded_text"]
    assert "abc123" not in first["embedded_text"]
    assert "session=raw" not in first["embedded_text"]


def _example(
    rows: list[dict[str, object]],
    *,
    doc_id: str,
    profile: str,
) -> dict[str, object]:
    for row in rows:
        if row["doc_id"] == doc_id and row["projection_profile"] == profile:
            return row
    raise AssertionError(f"missing example for {doc_id}/{profile}")
