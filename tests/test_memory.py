import json
import sqlite3
from pathlib import Path

from research_x.cli import main
from research_x.memory import embeddings
from research_x.memory.corpus import build_memory_corpus, export_corpus2skill_jsonl
from research_x.memory.embeddings import build_memory_embeddings
from research_x.memory.evidence import build_evidence_bundle
from research_x.memory.feedback import add_feedback
from research_x.memory.query import build_query_plan
from research_x.memory.search import search_memory


def test_build_memory_corpus_and_search(tmp_path: Path) -> None:
    db_path = tmp_path / "x.sqlite3"
    _seed_db(db_path)

    summary = build_memory_corpus(db_path)

    assert summary.tweet_docs == 2
    assert summary.bookmark_docs == 1
    assert summary.quote_tree_docs == 1
    assert summary.media_docs == 1
    assert summary.documents == 5

    results = search_memory(db_path, "強化学習 ロボット", limit=5)
    natural_results = search_memory(
        db_path,
        "あとで行きたくて保存したカフェ系を出して",
        limit=5,
    )

    assert results
    assert any(result.source_tweet_id == "tweet-1" for result in results)
    assert all(result.compact_text for result in results)
    assert any(result.source_tweet_id == "tweet-1" for result in natural_results)
    assert natural_results[0].score_components["doc_type"] > 0
    assert "カフェ" in natural_results[0].matched_terms

    plan = build_query_plan("画像付きで保存した技術資料っぽい投稿を出して")
    assert plan.requires_media_context is True
    assert "media_doc" in plan.doc_type_weights
    exclude_plan = build_query_plan("最近保存した強化学習を古いものを除いて出して")
    assert exclude_plan.excludes_old is True
    assert "古い" not in exclude_plan.search_terms


def test_memory_evidence_includes_quote_and_media(tmp_path: Path) -> None:
    db_path = tmp_path / "x.sqlite3"
    _seed_db(db_path)
    build_memory_corpus(db_path)

    bundle = build_evidence_bundle(
        db_path,
        "強化学習 ロボット",
        limit=3,
        doc_type="bookmark_doc",
    )

    assert bundle["query"] == "強化学習 ロボット"
    assert bundle["query_plan"]["search_terms"]
    assert bundle["hits"]
    hit = bundle["hits"][0]
    assert hit["tweet_id"] == "tweet-1"
    assert hit["compact_text"]
    assert hit["matched_terms"]
    assert hit["score_components"]
    assert hit["evidence"]["url"] == "https://x.com/a/status/tweet-1"
    assert hit["evidence"]["quoted_tweets"][0]["tweet_id"] == "tweet-2"
    assert hit["evidence"]["media"][0]["media_id"] == "media-1"


def test_memory_feedback_and_corpus2skill_export(tmp_path: Path) -> None:
    db_path = tmp_path / "x.sqlite3"
    out_path = tmp_path / "corpus.jsonl"
    _seed_db(db_path)
    build_memory_corpus(db_path)

    feedback_id = add_feedback(
        db_path,
        query="強化学習",
        doc_id="bookmark:acct:tweet-1",
        label="useful",
        note="good result",
    )
    exported = export_corpus2skill_jsonl(db_path, out_path)

    assert feedback_id
    assert exported == 5
    rows = [json.loads(line) for line in out_path.read_text(encoding="utf-8").splitlines()]
    assert rows[0]["id"]
    assert rows[0]["contents"]

    with sqlite3.connect(db_path) as conn:
        count = conn.execute("SELECT COUNT(*) FROM memory_feedback").fetchone()[0]
    assert count == 1


def test_memory_local_embeddings_and_semantic_search(tmp_path: Path) -> None:
    db_path = tmp_path / "x.sqlite3"
    _seed_db(db_path)
    build_memory_corpus(db_path)

    summary = build_memory_embeddings(
        db_path,
        provider="local_hash",
        dimensions=64,
        batch_size=2,
    )
    results = search_memory(
        db_path,
        "robot paper",
        limit=3,
        semantic_provider="local_hash",
        semantic_dimensions=64,
    )
    rerun = build_memory_embeddings(
        db_path,
        provider="local_hash",
        dimensions=64,
        batch_size=2,
    )

    assert summary.embedded == 5
    assert rerun.embedded == 0
    assert rerun.selected == 0
    assert results
    assert any(result.score_components["semantic"] > 0 for result in results)


def test_gemini_embedding_2_request_uses_current_config(monkeypatch) -> None:
    captured = {}

    def fake_post_json(url, payload, *, headers, timeout_seconds, retries=3):
        captured["url"] = url
        captured["payload"] = payload
        captured["headers"] = headers
        return {"embeddings": [{"values": [0.1, 0.2, 0.3]}]}

    monkeypatch.setenv("GEMINI_API_KEY", "fake-key")
    monkeypatch.setattr(embeddings, "_post_json", fake_post_json)

    spec = embeddings.resolve_embedding_spec(
        provider="gemini",
        model="gemini-embedding-2",
        dimensions=3,
    )
    vector = embeddings._GeminiEmbedder(spec).embed_texts(  # noqa: SLF001
        ["robot learning"],
        task_type="RETRIEVAL_QUERY",
    )[0]

    request = captured["payload"]["requests"][0]
    assert vector
    assert "taskType" not in request
    assert request["embedContentConfig"]["outputDimensionality"] == 3
    assert "Represent this search query" in request["content"]["parts"][0]["text"]


def test_memory_cli_smoke(tmp_path: Path, capsys) -> None:
    db_path = tmp_path / "x.sqlite3"
    _seed_db(db_path)

    assert main(["memory", "build-corpus", "--db", str(db_path)]) == 0
    assert main(
        [
            "memory",
            "build-embeddings",
            "--db",
            str(db_path),
            "--dimensions",
            "64",
        ]
    ) == 0
    assert main(["memory", "embedding-specs", "--db", str(db_path)]) == 0
    assert main(["memory", "search", "--db", str(db_path), "--query", "ロボット"]) == 0
    assert main(
        [
            "memory",
            "search",
            "--db",
            str(db_path),
            "--query",
            "robot paper",
            "--semantic-provider",
            "local_hash",
            "--semantic-dimensions",
            "64",
        ]
    ) == 0
    assert main(["memory", "plan", "--query", "引用元を見たい"]) == 0
    assert main(["memory", "evidence", "--db", str(db_path), "--query", "ロボット"]) == 0
    assert main(["memory", "eval", "--db", str(db_path), "--limit", "1"]) == 0

    output = capsys.readouterr().out
    assert "tweet-1" in output
    assert "hits" in output


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
                    "強化学習とロボットの実験メモ。カフェで読む。",
                    "2026-05-26T00:00:00+00:00",
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
                    "引用元のロボット論文リンク。",
                    "2026-05-25T00:00:00+00:00",
                    "2026-05-26T00:00:00+00:00",
                    "2026-05-26T00:00:00+00:00",
                    "quoted_tweet",
                    None,
                    "[]",
                    "{}",
                    "2026-05-26T00:00:00+00:00",
                ),
            ],
        )
        conn.execute(
            """
            INSERT INTO account_bookmarks (
                account_id, tweet_id, bookmark_index, observed_at, providers_json, run_id
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            ("acct", "tweet-1", 0, "2026-05-26T00:00:00+00:00", "[]", "run"),
        )
        conn.execute(
            """
            INSERT INTO tweet_edges (
                parent_tweet_id, child_tweet_id, relation, child_also_bookmarked
            )
            VALUES (?, ?, ?, ?)
            """,
            ("tweet-1", "tweet-2", "quote", 0),
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
                "robot image",
                "runs/media/image.jpg",
                "ok",
                123,
                "image/jpeg",
                None,
            ),
        )
        conn.execute(
            """
            INSERT INTO ai_labels (
                label_id, account_id, tweet_id, label_scope, category_id,
                category_label, confidence, tags_json, summary, rationale,
                model, run_id, generated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "label-1",
                "acct",
                "tweet-1",
                "bookmarks",
                "tech",
                "Technology",
                0.9,
                '["強化学習", "ロボット"]',
                "summary",
                "rationale",
                "fake-model",
                "run",
                "2026-05-26T00:00:00+00:00",
            ),
        )
