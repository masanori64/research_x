from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from research_x.memory.corpus import build_memory_corpus
from research_x.memory.relations import build_memory_relations

CREATED_AT = "2026-06-27T00:00:00+00:00"


@pytest.fixture
def media_db_path(tmp_path: Path) -> Path:
    db_path = tmp_path / "media.sqlite3"
    seed_media_db(db_path)
    return db_path


@pytest.fixture
def media_file(tmp_path: Path) -> Path:
    path = tmp_path / "image.jpg"
    path.write_bytes(b"fake-image")
    return path


@pytest.fixture
def media_db_with_file(media_db_path: Path, media_file: Path) -> Path:
    attach_media_file(media_db_path, media_file)
    return media_db_path


def seed_media_db(db_path: Path) -> None:
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
            CREATE TABLE account_bookmarks (
                account_id TEXT,
                tweet_id TEXT,
                bookmark_index INTEGER,
                observed_at TEXT,
                providers_json TEXT,
                run_id TEXT,
                PRIMARY KEY(account_id, tweet_id)
            );
            CREATE TABLE tweet_edges (
                parent_tweet_id TEXT,
                child_tweet_id TEXT,
                relation TEXT,
                child_also_bookmarked INTEGER DEFAULT 0,
                PRIMARY KEY(parent_tweet_id, child_tweet_id, relation)
            );
            CREATE TABLE media (
                media_id TEXT PRIMARY KEY,
                tweet_id TEXT,
                type TEXT,
                url TEXT,
                alt_text TEXT,
                local_path TEXT,
                download_status TEXT,
                bytes INTEGER,
                content_type TEXT,
                download_error TEXT
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
        conn.execute(
            """
            INSERT INTO tweets (
                tweet_id, url, author_screen_name, text, created_at,
                first_observed_at, last_observed_at, role, collection_kind,
                providers_json, raw_json, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "tweet-1",
                "https://x.com/example/status/tweet-1",
                "robotics",
                "robot screenshot UI with visible text labels",
                CREATED_AT,
                CREATED_AT,
                CREATED_AT,
                "bookmark_root",
                "bookmarks",
                "[]",
                "{}",
                CREATED_AT,
            ),
        )
        conn.execute(
            """
            INSERT INTO account_bookmarks (
                account_id, tweet_id, bookmark_index, observed_at, providers_json, run_id
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            ("acct", "tweet-1", 0, CREATED_AT, "[]", "run"),
        )
        conn.execute(
            """
            INSERT INTO media (
                media_id, tweet_id, type, url, alt_text, local_path,
                download_status, bytes, content_type, download_error
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "media-1",
                "tweet-1",
                "photo",
                "https://example.test/image.jpg",
                "robot screenshot UI with visible labels",
                "",
                "ok",
                10,
                "image/jpeg",
                None,
            ),
        )
    build_memory_corpus(db_path)
    build_memory_relations(db_path)


def attach_media_file(db_path: Path, media_path: Path) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "UPDATE media SET local_path = ? WHERE media_id = ?",
            (str(media_path), "media-1"),
        )
