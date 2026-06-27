from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from research_x.memory.document_hashes import (
    memory_document_embedding_text_hash,
    memory_document_source_hash,
)
from research_x.memory.schema import ensure_memory_schema

CREATED_AT = "2026-06-27T00:00:00+00:00"


@pytest.fixture
def vector_db_path(tmp_path: Path) -> Path:
    db_path = tmp_path / "vector.sqlite3"
    seed_vector_memory_db(db_path)
    return db_path


def seed_vector_memory_db(db_path: Path) -> None:
    docs = (
        {
            "doc_id": "tweet:robot",
            "doc_type": "tweet_doc",
            "source_tweet_id": "robot",
            "account_id": None,
            "author_screen_name": "robotics",
            "title": "robot reinforcement learning note",
            "body": "tweet_id: robot\nrobot paper reinforcement learning source note",
            "compact_text": "robot paper reinforcement learning",
            "metadata_json": json.dumps(
                {"url": "https://x.com/example/status/robot"},
                ensure_ascii=False,
                sort_keys=True,
            ),
            "created_at": CREATED_AT,
            "observed_at": CREATED_AT,
            "updated_at": CREATED_AT,
        },
        {
            "doc_id": "tweet:coffee",
            "doc_type": "tweet_doc",
            "source_tweet_id": "coffee",
            "account_id": None,
            "author_screen_name": "places",
            "title": "coffee bookmark",
            "body": "tweet_id: coffee\nquiet cafe bookmark",
            "compact_text": "quiet cafe bookmark",
            "metadata_json": json.dumps(
                {"url": "https://x.com/example/status/coffee"},
                ensure_ascii=False,
                sort_keys=True,
            ),
            "created_at": CREATED_AT,
            "observed_at": CREATED_AT,
            "updated_at": CREATED_AT,
        },
    )
    with sqlite3.connect(db_path) as conn:
        ensure_memory_schema(conn)
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
                    "robot",
                    "https://x.com/example/status/robot",
                    "robotics",
                    "robot paper reinforcement learning source note",
                    CREATED_AT,
                    CREATED_AT,
                    CREATED_AT,
                    "bookmark_root",
                    "bookmarks",
                    "[]",
                    "{}",
                    CREATED_AT,
                ),
                (
                    "coffee",
                    "https://x.com/example/status/coffee",
                    "places",
                    "quiet cafe bookmark",
                    CREATED_AT,
                    CREATED_AT,
                    CREATED_AT,
                    "bookmark_root",
                    "bookmarks",
                    "[]",
                    "{}",
                    CREATED_AT,
                ),
            ],
        )
        for doc in docs:
            source_doc_hash = memory_document_source_hash(doc)
            embedding_text_hash = memory_document_embedding_text_hash(doc)
            conn.execute(
                """
                INSERT INTO memory_documents (
                    doc_id, doc_type, source_tweet_id, account_id, author_screen_name,
                    title, body, compact_text, metadata_json,
                    source_doc_hash, embedding_text_hash,
                    created_at, observed_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    doc["doc_id"],
                    doc["doc_type"],
                    doc["source_tweet_id"],
                    doc["account_id"],
                    doc["author_screen_name"],
                    doc["title"],
                    doc["body"],
                    doc["compact_text"],
                    doc["metadata_json"],
                    source_doc_hash,
                    embedding_text_hash,
                    doc["created_at"],
                    doc["observed_at"],
                    doc["updated_at"],
                ),
            )
            conn.execute(
                """
                INSERT INTO memory_document_fts (
                    doc_id, title, body, compact_text, author_screen_name, metadata_json
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    doc["doc_id"],
                    doc["title"],
                    doc["body"],
                    doc["compact_text"],
                    doc["author_screen_name"],
                    doc["metadata_json"],
                ),
            )
