import sqlite3

from research_x.db_view import format_display_rows, load_display_rows


def test_load_display_rows_reads_bookmark_text(tmp_path) -> None:
    db_path = tmp_path / "x.sqlite3"
    with sqlite3.connect(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE account_bookmarks (
                account_id TEXT,
                tweet_id TEXT,
                bookmark_index INTEGER,
                observed_at TEXT,
                providers_json TEXT,
                run_id TEXT
            );
            CREATE TABLE tweets (
                tweet_id TEXT PRIMARY KEY,
                url TEXT,
                author_screen_name TEXT,
                text TEXT
            );
            CREATE TABLE ai_labels (
                account_id TEXT,
                tweet_id TEXT,
                label_scope TEXT,
                category_label TEXT,
                generated_at TEXT
            );
            """
        )
        conn.execute(
            "INSERT INTO account_bookmarks VALUES (?, ?, ?, ?, ?, ?)",
            ("mcreatefuture_3", "1", 0, "2026-05-22", "[]", "run"),
        )
        conn.execute(
            "INSERT INTO tweets VALUES (?, ?, ?, ?)",
            ("1", "https://x.com/a/status/1", "a", "hello"),
        )
        conn.execute(
            "INSERT INTO ai_labels VALUES (?, ?, ?, ?, ?)",
            ("mcreatefuture_3", "1", "bookmarks", "AI", "2026-05-22"),
        )

    rows = load_display_rows(
        db_path,
        account="mcreatefuture_3",
        kind="bookmarks",
        limit=20,
    )

    assert rows[0].text == "hello"
    assert rows[0].category == "AI"
    assert "hello" in format_display_rows(rows)
