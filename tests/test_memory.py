import json
import sqlite3
from pathlib import Path

from research_x.cli import main
from research_x.memory import embeddings
from research_x.memory.audit import audit_memory_db
from research_x.memory.context import build_context_bundle
from research_x.memory.corpus import build_memory_corpus, export_corpus2skill_jsonl
from research_x.memory.embeddings import build_memory_embeddings
from research_x.memory.evidence import build_evidence_bundle
from research_x.memory.external import search_external_evidence
from research_x.memory.feedback import add_feedback
from research_x.memory.query import build_query_plan
from research_x.memory.relations import build_memory_relations, relations_for_doc
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


def test_memory_semantic_auto_rejects_diagnostic_only_index(tmp_path: Path) -> None:
    db_path = tmp_path / "x.sqlite3"
    _seed_db(db_path)
    build_memory_corpus(db_path)
    build_memory_embeddings(db_path, provider="local_hash", dimensions=64)

    try:
        search_memory(
            db_path,
            "robot paper",
            limit=3,
            semantic_provider="auto",
            semantic_dimensions=64,
        )
    except RuntimeError as exc:
        assert "diagnostic local_hash" in str(exc)
    else:
        raise AssertionError("semantic auto should not silently use local_hash embeddings")


def test_memory_semantic_explicit_provider_requires_existing_index(tmp_path: Path) -> None:
    db_path = tmp_path / "x.sqlite3"
    _seed_db(db_path)
    build_memory_corpus(db_path)

    try:
        search_memory(db_path, "robot paper", limit=3, semantic_provider="local_hash")
    except RuntimeError as exc:
        assert "embedding index not found" in str(exc)
    else:
        raise AssertionError("explicit semantic provider should require a matching index")


def test_memory_semantic_provider_requires_complete_scope_index(tmp_path: Path) -> None:
    db_path = tmp_path / "x.sqlite3"
    _seed_db(db_path)
    build_memory_corpus(db_path)
    build_memory_embeddings(db_path, provider="local_hash", dimensions=64, limit=1)

    try:
        search_memory(
            db_path,
            "robot paper",
            limit=3,
            semantic_provider="local_hash",
            semantic_dimensions=64,
        )
    except RuntimeError as exc:
        assert "semantic index is incomplete" in str(exc)
    else:
        raise AssertionError("semantic search should not continue with a partial index")


def test_memory_audit_flags_local_hash_as_diagnostic(tmp_path: Path) -> None:
    db_path = tmp_path / "x.sqlite3"
    _seed_db(db_path)
    build_memory_corpus(db_path)
    build_memory_relations(db_path)
    build_memory_embeddings(db_path, provider="local_hash", dimensions=64)

    report = audit_memory_db(db_path)

    assert report.documents == 5
    assert report.relation_covered_documents == 5
    assert not report.isolated_documents_by_type
    assert any("only local_hash embeddings" in warning for warning in report.warnings)


def test_memory_commands_do_not_implicitly_rebuild_corpus(tmp_path: Path) -> None:
    db_path = tmp_path / "x.sqlite3"
    _seed_db(db_path)

    for action in (
        lambda: search_memory(db_path, "ロボット"),
        lambda: build_memory_embeddings(db_path, provider="local_hash", dimensions=64),
        lambda: build_memory_relations(db_path),
    ):
        try:
            action()
        except RuntimeError as exc:
            assert "memory_documents is empty" in str(exc)
        else:
            raise AssertionError("memory command should require explicit build-corpus first")


def test_memory_corpus_rebuild_clears_stale_indexes(tmp_path: Path) -> None:
    db_path = tmp_path / "x.sqlite3"
    _seed_db(db_path)
    build_memory_corpus(db_path)
    build_memory_relations(db_path)
    build_memory_embeddings(db_path, provider="local_hash", dimensions=64)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO memory_embeddings (
                doc_id, provider, model, dimensions, embedding,
                embedded_text_hash, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "missing-doc",
                "local_hash",
                "local-hash-v1",
                64,
                embeddings.pack_embedding([0.0] * 64),
                "stale",
                "2026-05-26T00:00:00+00:00",
                "2026-05-26T00:00:00+00:00",
            ),
        )

    build_memory_corpus(db_path)

    with sqlite3.connect(db_path) as conn:
        relation_count = conn.execute("SELECT COUNT(*) FROM memory_relations").fetchone()[0]
        stale_embedding_count = conn.execute(
            "SELECT COUNT(*) FROM memory_embeddings WHERE doc_id = 'missing-doc'"
        ).fetchone()[0]
    assert relation_count == 0
    assert stale_embedding_count == 0


def test_memory_audit_reports_orphans_and_invalid_json(tmp_path: Path) -> None:
    db_path = tmp_path / "x.sqlite3"
    _seed_db(db_path)
    build_memory_corpus(db_path)
    build_memory_relations(db_path)
    build_memory_embeddings(db_path, provider="local_hash", dimensions=64)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO memory_relations (
                relation_id, source_doc_id, target_doc_id, relation_type,
                strength, status, evidence_json, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "stale-relation",
                "tweet:tweet-1",
                "missing-doc",
                "stale",
                0.1,
                "candidate",
                "{bad",
                "2026-05-26T00:00:00+00:00",
                "2026-05-26T00:00:00+00:00",
            ),
        )
        conn.execute(
            """
            UPDATE memory_documents
            SET metadata_json = '{bad'
            WHERE doc_id = 'tweet:tweet-1'
            """
        )

    report = audit_memory_db(db_path)

    assert report.orphaned_relations == 1
    assert report.invalid_json_by_field["memory_documents.metadata_json"] == 1
    assert report.invalid_json_by_field["memory_relations.evidence_json"] == 1
    assert any("invalid JSON" in warning for warning in report.warnings)


def test_embedding_build_rejects_wrong_vector_dimensions(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "x.sqlite3"
    _seed_db(db_path)
    build_memory_corpus(db_path)

    class WrongSizeEmbedder:
        def embed_texts(self, texts: list[str], *, task_type: str) -> list[list[float]]:
            return [[0.1, 0.2, 0.3] for _ in texts]

    monkeypatch.setattr(embeddings, "_embedder", lambda spec: WrongSizeEmbedder())

    try:
        build_memory_embeddings(db_path, provider="local_hash", dimensions=64)
    except RuntimeError as exc:
        assert "expected 64" in str(exc)
    else:
        raise AssertionError("embedding build should reject provider dimension mismatches")


def test_embedding_auto_requires_production_api_key(monkeypatch) -> None:
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    try:
        embeddings.resolve_embedding_spec(provider="auto")
    except RuntimeError as exc:
        assert "local_hash" in str(exc)
    else:
        raise AssertionError("auto embedding provider should require a production key")


def test_memory_relations_feed_search_and_evidence(tmp_path: Path) -> None:
    db_path = tmp_path / "x.sqlite3"
    _seed_db(db_path)
    build_memory_corpus(db_path)

    summary = build_memory_relations(db_path)
    relations = relations_for_doc(db_path, "tweet:tweet-1")
    results = search_memory(db_path, "引用元を見たい", limit=5)
    bundle = build_evidence_bundle(db_path, "引用元を見たい", limit=3)

    assert summary.by_type["bookmark_of_tweet"] == 1
    assert summary.by_type["has_media"] == 1
    assert summary.by_type["quotes"] == 1
    assert summary.by_type["has_quote_tree"] == 1
    assert any(relation.relation_type == "has_quote_tree" for relation in relations)
    assert any(result.score_components["relations"] > 0 for result in results)
    assert bundle["hits"][0]["evidence"]["relations"]


def test_external_evidence_fake_provider_is_stored(tmp_path: Path) -> None:
    db_path = tmp_path / "x.sqlite3"

    bundle = search_external_evidence(
        db_path,
        "北千住 ピザ",
        provider="fake",
        limit=2,
    )

    assert bundle.provider == "fake"
    assert bundle.provider_role == "index_provider"
    assert bundle.status == "ok"
    assert bundle.raw_response_hash
    assert len(bundle.items) == 2
    assert bundle.items[0].url.startswith("https://example.invalid/")

    with sqlite3.connect(db_path) as conn:
        run_count = conn.execute("SELECT COUNT(*) FROM memory_external_runs").fetchone()[0]
        item_count = conn.execute("SELECT COUNT(*) FROM memory_external_items").fetchone()[0]
        role = conn.execute("SELECT provider_role FROM memory_external_runs").fetchone()[0]

    assert run_count == 1
    assert item_count == 2
    assert role == "index_provider"


def test_external_evidence_serper_provider_uses_key_and_normalizes(
    tmp_path: Path,
    monkeypatch,
) -> None:
    db_path = tmp_path / "x.sqlite3"
    captured = {}

    def fake_post_json(url, payload, *, headers, timeout_seconds):
        captured["url"] = url
        captured["payload"] = payload
        captured["headers"] = headers
        captured["timeout_seconds"] = timeout_seconds
        return {
            "organic": [
                {
                    "title": "Kitaseju Pizza",
                    "link": "https://example.com/pizza",
                    "snippet": "A saved-looking pizza place.",
                    "position": 1,
                }
            ]
        }

    monkeypatch.setenv("SERPER_API_KEY", "secret-key")
    monkeypatch.setattr("research_x.memory.external._post_json", fake_post_json)

    bundle = search_external_evidence(
        db_path,
        "北千住 ピザ",
        provider="serper",
        limit=1,
        country="jp",
        language="ja",
        timeout_seconds=12.0,
    )

    assert captured["url"] == "https://google.serper.dev/search"
    assert captured["payload"] == {"q": "北千住 ピザ", "num": 1, "gl": "jp", "hl": "ja"}
    assert captured["headers"]["X-API-KEY"] == "secret-key"
    assert bundle.parameters["api_key_env"] == "SERPER_API_KEY"
    assert "secret-key" not in json.dumps(bundle.as_dict(), ensure_ascii=False)
    assert bundle.items[0].source == "example.com"


def test_memory_context_chunks_and_citations_are_stored(tmp_path: Path) -> None:
    db_path = tmp_path / "x.sqlite3"
    _seed_db(db_path)
    build_memory_corpus(db_path)
    build_memory_relations(db_path)

    bundle = build_context_bundle(
        db_path,
        "強化学習 ロボット",
        limit=2,
        doc_type="bookmark_doc",
    )

    assert bundle.run_id
    assert bundle.retrieved_hits
    assert bundle.context_chunks
    assert bundle.citation_annotations
    chunk = bundle.context_chunks[0]
    citation = bundle.citation_annotations[0]
    assert chunk.source_kind == "local_x_db"
    assert chunk.provider_role == "context_builder"
    assert "Quoted tweets:" in chunk.chunk_text
    assert citation.chunk_id == chunk.chunk_id
    assert citation.source_url == "https://x.com/a/status/tweet-1"
    assert citation.evidence_status == "fact"

    with sqlite3.connect(db_path) as conn:
        search_runs = conn.execute("SELECT COUNT(*) FROM memory_search_runs").fetchone()[0]
        chunks = conn.execute("SELECT COUNT(*) FROM memory_context_chunks").fetchone()[0]
        citations = conn.execute(
            "SELECT COUNT(*) FROM memory_citation_annotations"
        ).fetchone()[0]
        answers = conn.execute("SELECT COUNT(*) FROM memory_answer_runs").fetchone()[0]
        workflows = conn.execute("SELECT COUNT(*) FROM memory_workflow_runs").fetchone()[0]

    assert search_runs == 1
    assert chunks == len(bundle.context_chunks)
    assert citations == len(bundle.citation_annotations)
    assert answers == 0
    assert workflows == 0


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


def test_memory_cli_commands(tmp_path: Path, capsys) -> None:
    db_path = tmp_path / "x.sqlite3"
    _seed_db(db_path)

    assert main(["memory", "build-corpus", "--db", str(db_path)]) == 0
    assert main(
        [
            "memory",
            "build-embeddings",
            "--db",
            str(db_path),
            "--provider",
            "local_hash",
            "--dimensions",
            "64",
        ]
    ) == 0
    assert main(["memory", "audit", "--db", str(db_path)]) == 0
    assert main(["memory", "audit", "--db", str(db_path), "--strict"]) == 2
    assert main(["memory", "embedding-specs", "--db", str(db_path)]) == 0
    assert main(["memory", "build-relations", "--db", str(db_path)]) == 0
    assert main(
        [
            "memory",
            "relations",
            "--db",
            str(db_path),
            "--doc-id",
            "tweet:tweet-1",
        ]
    ) == 0
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
    assert main(["memory", "context", "--db", str(db_path), "--query", "ロボット"]) == 0
    assert (
        main(
            [
                "memory",
                "external-search",
                "--db",
                str(db_path),
                "--query",
                "北千住 ピザ",
                "--provider",
                "fake",
                "--limit",
                "1",
            ]
        )
        == 0
    )
    assert main(["memory", "eval", "--db", str(db_path), "--limit", "1"]) == 0

    output = capsys.readouterr().out
    assert "tweet-1" in output
    assert "hits" in output
    assert "context_chunks" in output
    assert "memory://fake-external-search" in output


def test_memory_cli_reports_runtime_errors_without_traceback(tmp_path: Path, capsys) -> None:
    db_path = tmp_path / "x.sqlite3"
    _seed_db(db_path)
    build_memory_corpus(db_path)
    build_memory_embeddings(db_path, provider="local_hash", dimensions=64)

    assert (
        main(
            [
                "memory",
                "search",
                "--db",
                str(db_path),
                "--query",
                "robot paper",
                "--semantic-provider",
                "auto",
            ]
        )
        == 1
    )

    captured = capsys.readouterr()
    assert "diagnostic local_hash" in captured.err
    assert "Traceback" not in captured.err


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
