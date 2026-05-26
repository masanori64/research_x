import json

from research_x.progress import progress_snapshot


def test_progress_snapshot_reads_cursor_and_media_progress(tmp_path) -> None:
    page_dir = tmp_path / "bookmark_pages" / "x_web_graphql"
    page_dir.mkdir(parents=True)
    (page_dir / "1.json").write_text("{}", encoding="utf-8")
    (page_dir / "2.json").write_text("{}", encoding="utf-8")
    (tmp_path / "bookmark_pages" / "x_web_graphql_cursor_state.json").write_text(
        json.dumps(
            {
                "item_count": 42,
                "finished": True,
                "rate_limited": False,
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "media_progress.json").write_text(
        json.dumps(
            {
                "total": 10,
                "done": 4,
                "remaining": 6,
                "ok": 4,
                "error": 0,
                "skipped": 0,
                "pending": 6,
                "finished": False,
                "elapsed_seconds": 12.5,
                "estimated_remaining_seconds": 18.5,
                "items_per_second": 0.32,
                "updated_at": "2026-05-26T00:00:00+00:00",
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "bookmarks_items.jsonl").write_text("{}\n{}\n", encoding="utf-8")

    snapshot = progress_snapshot(tmp_path)

    assert snapshot.output_exists is True
    assert snapshot.bookmarks_rows == 2
    assert snapshot.page_count == 2
    assert snapshot.cursor_item_count == 42
    assert snapshot.cursor_finished is True
    assert snapshot.media_total == 10
    assert snapshot.media_done == 4
    assert snapshot.media_estimated_remaining_seconds == 18.5
