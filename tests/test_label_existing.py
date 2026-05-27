from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from research_x import label_existing
from research_x.bookmark_classifier import BookmarkClassification, BookmarkClassificationRun


def test_load_existing_label_candidates_skips_labeled_bookmarks(tmp_path: Path) -> None:
    db_path = tmp_path / "x.sqlite3"
    _seed_db(db_path)

    candidates = label_existing.load_existing_label_candidates(
        db_path,
        account="acct",
        kind="bookmarks",
        limit=None,
        include_labeled=False,
    )

    assert [candidate.item.source_id for candidate in candidates] == ["tweet-2"]
    assert candidates[0].account_id == "acct"
    assert candidates[0].label_scope == "bookmarks"
    assert candidates[0].item.raw["_db"]["account_id"] == "acct"


def test_label_existing_items_writes_only_missing_labels(monkeypatch, tmp_path: Path) -> None:
    db_path = tmp_path / "x.sqlite3"
    _seed_db(db_path)

    def fake_classify(items, *, settings, categories):
        item_tuple = tuple(items)
        return BookmarkClassificationRun(
            status="ok",
            model="fake-model",
            generated_at=datetime(2026, 5, 26, tzinfo=UTC),
            classifications=tuple(
                BookmarkClassification(
                    source_id=item.source_id,
                    category_id="software_dev",
                    category_label="Software Development",
                    confidence=0.91,
                    tags=("test",),
                    summary="summary",
                    rationale="rationale",
                )
                for item in item_tuple
            ),
        )

    monkeypatch.setattr(label_existing, "classify_bookmarks", fake_classify)

    report, classification = label_existing.label_existing_items(
        db_path=db_path,
        account="acct",
        kind="bookmarks",
        limit=None,
        categories_path=None,
        out_dir=tmp_path / "labels",
    )

    assert report.status == "ok"
    assert report.selected_items == 1
    assert report.unique_tweets == 1
    assert report.written_labels == 1
    assert classification.model == "fake-model"

    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            "SELECT tweet_id, category_id, account_id, label_scope FROM ai_labels "
            "ORDER BY tweet_id"
        ).fetchall()

    assert rows == [
        ("tweet-1", "already", "acct", "bookmarks"),
        ("tweet-2", "software_dev", "acct", "bookmarks"),
    ]
    assert (tmp_path / "labels" / "existing_label_report.json").exists()


def test_label_existing_splits_retryable_batches(monkeypatch, tmp_path: Path) -> None:
    db_path = tmp_path / "x.sqlite3"
    _seed_db(db_path)

    def fake_classify(items, *, settings, categories):
        item_tuple = tuple(items)
        if len(item_tuple) > 1:
            return BookmarkClassificationRun(
                status="error",
                model="fake-model",
                generated_at=datetime(2026, 5, 26, tzinfo=UTC),
                classifications=(),
                error_type="TimeoutError",
                error_message="The read operation timed out",
            )
        return BookmarkClassificationRun(
            status="ok",
            model="fake-model",
            generated_at=datetime(2026, 5, 26, tzinfo=UTC),
            classifications=(
                BookmarkClassification(
                    source_id=item_tuple[0].source_id,
                    category_id="software_dev",
                    category_label="Software Development",
                    confidence=0.91,
                    tags=("test",),
                    summary="summary",
                    rationale="rationale",
                ),
            ),
        )

    monkeypatch.setattr(label_existing, "classify_bookmarks", fake_classify)

    report, classification = label_existing.label_existing_items(
        db_path=db_path,
        account="acct",
        kind="bookmarks",
        limit=None,
        include_labeled=True,
        categories_path=None,
        out_dir=tmp_path / "labels",
        batch_size=2,
        retry_attempts=0,
    )

    assert report.status == "ok"
    assert report.written_labels == 2
    assert len(classification.classifications) == 2


def test_label_existing_cancels_before_next_batch(monkeypatch, tmp_path: Path) -> None:
    db_path = tmp_path / "x.sqlite3"
    _seed_db(db_path)
    calls = 0

    def fake_classify(items, *, settings, categories):
        nonlocal calls
        calls += 1
        item_tuple = tuple(items)
        return BookmarkClassificationRun(
            status="ok",
            model="fake-model",
            generated_at=datetime(2026, 5, 26, tzinfo=UTC),
            classifications=tuple(
                BookmarkClassification(
                    source_id=item.source_id,
                    category_id="software_dev",
                    category_label="Software Development",
                    confidence=0.91,
                    tags=("test",),
                    summary="summary",
                    rationale="rationale",
                )
                for item in item_tuple
            ),
        )

    monkeypatch.setattr(label_existing, "classify_bookmarks", fake_classify)

    report, classification = label_existing.label_existing_items(
        db_path=db_path,
        account="acct",
        kind="bookmarks",
        limit=None,
        include_labeled=True,
        categories_path=None,
        out_dir=tmp_path / "labels",
        batch_size=1,
        cancel_check=lambda: calls >= 1,
    )

    assert report.status == "canceled"
    assert classification.status == "canceled"
    assert report.written_labels == 1
    assert calls == 1


def test_label_existing_can_stop_on_rate_limit(monkeypatch, tmp_path: Path) -> None:
    db_path = tmp_path / "x.sqlite3"
    _seed_db(db_path)

    def fake_classify(items, *, settings, categories):
        return BookmarkClassificationRun(
            status="error",
            model="fake-model",
            generated_at=datetime(2026, 5, 26, tzinfo=UTC),
            classifications=(),
            error_type="RuntimeError",
            error_message=(
                "Classifier API HTTP 429: quota exceeded for model; "
                "Please retry in 4.2s."
            ),
        )

    monkeypatch.setattr(label_existing, "classify_bookmarks", fake_classify)

    report, classification = label_existing.label_existing_items(
        db_path=db_path,
        account="acct",
        kind="bookmarks",
        limit=1,
        categories_path=None,
        out_dir=tmp_path / "labels",
        stop_on_rate_limit=True,
    )

    assert report.status == "quota_exhausted"
    assert classification.status == "quota_exhausted"
    assert report.written_labels == 0


def test_label_existing_paces_adaptive_split_requests(monkeypatch, tmp_path: Path) -> None:
    db_path = tmp_path / "x.sqlite3"
    _seed_db(db_path)
    sleep_seconds: list[float] = []

    def fake_sleep(seconds, cancel_check):
        sleep_seconds.append(seconds)
        return bool(cancel_check and cancel_check())

    def fake_classify(items, *, settings, categories):
        item_tuple = tuple(items)
        if len(item_tuple) > 1:
            return BookmarkClassificationRun(
                status="error",
                model="fake-model",
                generated_at=datetime(2026, 5, 26, tzinfo=UTC),
                classifications=(),
                error_type="TimeoutError",
                error_message="The read operation timed out",
            )
        return BookmarkClassificationRun(
            status="ok",
            model="fake-model",
            generated_at=datetime(2026, 5, 26, tzinfo=UTC),
            classifications=(
                BookmarkClassification(
                    source_id=item_tuple[0].source_id,
                    category_id="software_dev",
                    category_label="Software Development",
                    confidence=0.91,
                    tags=("test",),
                    summary="summary",
                    rationale="rationale",
                ),
            ),
        )

    monkeypatch.setattr(label_existing, "classify_bookmarks", fake_classify)
    monkeypatch.setattr(label_existing, "_sleep_until_cancel_or_timeout", fake_sleep)

    report, classification = label_existing.label_existing_items(
        db_path=db_path,
        account="acct",
        kind="bookmarks",
        limit=None,
        include_labeled=True,
        categories_path=None,
        out_dir=tmp_path / "labels",
        batch_size=2,
        retry_attempts=0,
        min_request_interval_seconds=10.0,
    )

    assert report.status == "ok"
    assert classification.status == "ok"
    assert report.written_labels == 2
    assert len(sleep_seconds) >= 2
    assert all(seconds > 9.0 for seconds in sleep_seconds[:2])


def _seed_db(db_path: Path) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE tweets (
                tweet_id TEXT PRIMARY KEY,
                url TEXT,
                author_screen_name TEXT,
                text TEXT,
                created_at TEXT,
                first_observed_at TEXT,
                last_observed_at TEXT,
                role TEXT,
                collection_kind TEXT,
                providers_json TEXT,
                raw_json TEXT,
                updated_at TEXT
            );
            CREATE TABLE collection_items (
                collection_id TEXT,
                collection_kind TEXT,
                account_id TEXT,
                target_kind TEXT,
                target_value TEXT,
                tweet_id TEXT,
                position INTEGER,
                observed_at TEXT,
                providers_json TEXT,
                run_id TEXT,
                PRIMARY KEY(collection_id, tweet_id)
            );
            CREATE TABLE account_bookmarks (
                account_id TEXT,
                tweet_id TEXT,
                bookmark_index INTEGER,
                observed_at TEXT,
                providers_json TEXT,
                run_id TEXT,
                PRIMARY KEY(account_id, tweet_id)
            );
            CREATE TABLE ai_labels (
                label_id TEXT PRIMARY KEY,
                account_id TEXT,
                tweet_id TEXT,
                label_scope TEXT,
                category_id TEXT,
                category_label TEXT,
                confidence REAL,
                tags_json TEXT,
                summary TEXT,
                rationale TEXT,
                model TEXT,
                run_id TEXT,
                generated_at TEXT
            );
            """
        )
        conn.executemany(
            """
            INSERT INTO tweets (
                tweet_id, url, author_screen_name, text, created_at,
                first_observed_at, last_observed_at, role, collection_kind,
                providers_json, raw_json, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    "tweet-1",
                    "https://x.com/a/status/tweet-1",
                    "a",
                    "already labeled",
                    None,
                    "2026-05-26T00:00:00+00:00",
                    "2026-05-26T00:00:00+00:00",
                    "bookmark_root",
                    "bookmarks",
                    "[]",
                    "{}",
                    "2026-05-26T00:00:00+00:00",
                ),
                (
                    "tweet-2",
                    "https://x.com/b/status/tweet-2",
                    "b",
                    "needs label",
                    None,
                    "2026-05-26T00:00:01+00:00",
                    "2026-05-26T00:00:01+00:00",
                    "bookmark_root",
                    "bookmarks",
                    "[]",
                    "{}",
                    "2026-05-26T00:00:01+00:00",
                ),
            ],
        )
        conn.executemany(
            """
            INSERT INTO account_bookmarks (
                account_id, tweet_id, bookmark_index, observed_at, providers_json, run_id
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            [
                ("acct", "tweet-1", 0, "2026-05-26T00:00:00+00:00", "[]", "run"),
                ("acct", "tweet-2", 1, "2026-05-26T00:00:01+00:00", "[]", "run"),
            ],
        )
        conn.execute(
            """
            INSERT INTO ai_labels (
                label_id, account_id, tweet_id, label_scope, category_id,
                category_label, confidence, tags_json, summary, rationale,
                model, run_id, generated_at
            )
            VALUES (
                'existing', 'acct', 'tweet-1', 'bookmarks', 'already',
                'Already', 1.0, '[]', '', '', 'fake-model', 'run',
                '2026-05-26T00:00:00+00:00'
            )
            """
        )
