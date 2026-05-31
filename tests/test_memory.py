import io
import json
import sqlite3
import urllib.error
from pathlib import Path

from research_x.cli import main
from research_x.memory import embeddings
from research_x.memory.answer import build_memory_answer
from research_x.memory.audit import audit_memory_db
from research_x.memory.context import build_context_bundle
from research_x.memory.corpus import (
    build_memory_corpus,
    export_corpus2skill_bundle,
    export_corpus2skill_jsonl,
)
from research_x.memory.derived import build_derived_documents
from research_x.memory.embeddings import (
    build_memory_embeddings,
    embedding_coverage_report,
    estimate_memory_embedding_build,
)
from research_x.memory.evals import (
    list_memory_eval_runs,
    load_eval_cases,
    load_memory_eval_run,
    run_memory_eval,
    store_memory_eval_results,
)
from research_x.memory.evidence import build_evidence_bundle
from research_x.memory.external import search_external_evidence
from research_x.memory.feedback import add_feedback, feedback_scores_for_docs
from research_x.memory.judge_relations import judge_memory_relations
from research_x.memory.llm_context import fetch_llm_context_to_context
from research_x.memory.query import build_query_plan
from research_x.memory.reader import (
    HttpResponse,
    extract_external_run_to_context,
    extract_url_to_context,
)
from research_x.memory.relations import build_memory_relations, relations_for_doc
from research_x.memory.schema import ensure_memory_schema
from research_x.memory.search import search_memory
from research_x.memory.source_kinds import classify_external_source_kind
from research_x.memory.workflow import plan_workflow_route, run_memory_workflow


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
    place_plan = build_query_plan("北千住にあるピザの店")
    assert "北千住" in place_plan.exact_terms
    finance_plan = build_query_plan("5/29のキオクシアの株価急騰")
    assert "5/29" in finance_plan.exact_terms
    assert "キオクシア" in finance_plan.exact_terms
    current_plan = build_query_plan("昔保存した技術情報が今も正しいか確認したい")
    assert "freshness" in current_plan.intents
    assert current_plan.prefers_recent is True
    author_plan = build_query_plan("Aさんの過去発言から2026年のAIの展望について教えて")
    assert author_plan.doc_type_weights["author_profile"] > author_plan.doc_type_weights.get(
        "topic_thread",
        0.0,
    )


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
    bundle = export_corpus2skill_bundle(db_path, tmp_path / "c2s_bundle")
    filtered_bundle = export_corpus2skill_bundle(
        db_path,
        tmp_path / "c2s_bookmarks",
        doc_types=("bookmark_doc",),
    )

    assert feedback_id
    assert exported == 5
    rows = [json.loads(line) for line in out_path.read_text(encoding="utf-8").splitlines()]
    assert rows[0]["id"]
    assert rows[0]["contents"]
    assert rows[0]["metadata"]["doc_type"]
    bundle_rows = [
        json.loads(line)
        for line in Path(bundle.corpus_path).read_text(encoding="utf-8").splitlines()
    ]
    manifest = json.loads(Path(bundle.manifest_path).read_text(encoding="utf-8"))
    filtered_manifest = json.loads(
        Path(filtered_bundle.manifest_path).read_text(encoding="utf-8")
    )
    assert bundle.documents == 5
    assert bundle_rows[0]["metadata"]["research_x_metadata"]
    assert manifest["format"] == "corpus2skill-jsonl-bundle-v1"
    assert manifest["compile_hint"][:3] == ["uv", "run", "python"]
    assert filtered_bundle.documents == 1
    assert filtered_manifest["filters"]["doc_types"] == ["bookmark_doc"]

    with sqlite3.connect(db_path) as conn:
        count = conn.execute("SELECT COUNT(*) FROM memory_feedback").fetchone()[0]
        terms_json, intents_json = conn.execute(
            """
            SELECT query_terms_json, intents_json
            FROM memory_feedback
            WHERE feedback_id = ?
            """,
            (feedback_id,),
        ).fetchone()
    assert count == 1
    assert "強化学習" in json.loads(terms_json)
    assert json.loads(intents_json)


def test_memory_feedback_scores_are_query_aware(tmp_path: Path) -> None:
    db_path = tmp_path / "x.sqlite3"
    _seed_db(db_path)
    build_memory_corpus(db_path)

    add_feedback(
        db_path,
        query="居酒屋",
        doc_id="bookmark:acct:tweet-1",
        label="wrong_topic",
    )
    add_feedback(
        db_path,
        query="強化学習 ロボット",
        doc_id="bookmark:acct:tweet-1",
        label="useful",
        route="technical_learning",
    )

    current_plan = build_query_plan("強化学習 ロボット")
    unrelated_plan = build_query_plan("居酒屋")
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        ensure_memory_schema(conn)
        current_scores = feedback_scores_for_docs(
            conn,
            ("bookmark:acct:tweet-1",),
            plan=current_plan,
            route="technical_learning",
        )
        unrelated_scores = feedback_scores_for_docs(
            conn,
            ("bookmark:acct:tweet-1",),
            plan=unrelated_plan,
            route="place_recall",
        )

    assert current_scores["bookmark:acct:tweet-1"] > 0
    assert unrelated_scores["bookmark:acct:tweet-1"] < current_scores["bookmark:acct:tweet-1"]


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
    assert summary.embedding_profile == "general_memory"
    assert summary.text_template_version == "memory-doc-embedding-v1"
    assert rerun.embedded == 0
    assert rerun.selected == 0
    assert results
    assert any(result.score_components["semantic"] > 0 for result in results)
    assert any(
        result.metadata["semantic"]["embedding_profile"] == "general_memory"
        for result in results
        if "semantic" in result.metadata
    )

    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            """
            SELECT embedding_profile, text_template_version, source_doc_hash
            FROM memory_embeddings
            LIMIT 1
            """
        ).fetchone()

    assert row[:2] == ("general_memory", "memory-doc-embedding-v1")
    assert row[2]


def test_memory_embedding_coverage_reports_missing_doc_types(tmp_path: Path) -> None:
    db_path = tmp_path / "x.sqlite3"
    _seed_db(db_path)
    build_memory_corpus(db_path)
    build_memory_embeddings(db_path, provider="local_hash", dimensions=64)
    build_derived_documents(db_path, kinds=("topic_thread",), min_topic_docs=2)

    report = embedding_coverage_report(
        db_path,
        provider="local_hash",
        dimensions=64,
    )
    by_type = {row.doc_type: row for row in report.by_doc_type}

    assert report.current == 5
    assert report.missing == report.documents - 5
    assert by_type["topic_thread"].missing >= 1
    assert by_type["bookmark_doc"].current == 1


def test_memory_embedding_estimate_reports_selection_and_cost(tmp_path: Path) -> None:
    db_path = tmp_path / "x.sqlite3"
    _seed_db(db_path)
    build_memory_corpus(db_path)

    estimate = estimate_memory_embedding_build(
        db_path,
        provider="gemini",
        model="gemini-embedding-2",
        dimensions=768,
        batch_size=2,
        price_per_million_input_tokens=0.15,
    )

    assert estimate.provider == "gemini"
    assert estimate.documents == 5
    assert estimate.selected == 5
    assert estimate.missing == 5
    assert estimate.estimated_batches == 3
    assert estimate.estimated_input_tokens > 0
    assert estimate.estimated_input_cost is not None


def test_memory_embedding_schema_migrates_legacy_rows(tmp_path: Path) -> None:
    db_path = tmp_path / "legacy.sqlite3"
    with sqlite3.connect(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE memory_embeddings (
                doc_id TEXT NOT NULL,
                provider TEXT NOT NULL,
                model TEXT NOT NULL,
                dimensions INTEGER NOT NULL,
                embedding BLOB NOT NULL,
                embedded_text_hash TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY(doc_id, provider, model, dimensions)
            );
            INSERT INTO memory_embeddings (
                doc_id, provider, model, dimensions, embedding,
                embedded_text_hash, created_at, updated_at
            )
            VALUES (
                'doc-1', 'local_hash', 'local-hash-v1', 4, zeroblob(16),
                'old-hash', '2026-05-26T00:00:00+00:00',
                '2026-05-26T00:00:00+00:00'
            );
            """
        )
        ensure_memory_schema(conn)
        columns = {
            row[1]: row[5]
            for row in conn.execute("PRAGMA table_info(memory_embeddings)").fetchall()
        }
        migrated = conn.execute(
            """
            SELECT
                embedding_profile,
                text_template_version,
                source_doc_hash,
                embedded_text_hash
            FROM memory_embeddings
            """
        ).fetchone()

    assert columns["embedding_profile"] == 5
    assert columns["text_template_version"] == 6
    assert migrated == (
        "general_memory",
        "memory-doc-embedding-v1",
        None,
        "old-hash",
    )


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


def test_memory_audit_accepts_openai_compatible_embeddings_as_production(
    tmp_path: Path,
    monkeypatch,
) -> None:
    db_path = tmp_path / "x.sqlite3"
    _seed_db(db_path)
    build_memory_corpus(db_path)
    build_memory_relations(db_path)

    def fake_post_json(url, payload, *, headers, timeout_seconds, retries=3):
        return {
            "data": [
                {"index": index, "embedding": [1.0, 0.0, 0.0]}
                for index, _text in enumerate(payload["input"])
            ]
        }

    monkeypatch.setenv("CUSTOM_EMBED_KEY", "fake-key")
    monkeypatch.setattr(embeddings, "_post_json", fake_post_json)

    build_memory_embeddings(
        db_path,
        provider="openai_compatible",
        model="custom-embedding",
        dimensions=3,
        api_key_env="CUSTOM_EMBED_KEY",
        base_url="https://embeddings.example/v1/embeddings",
    )

    report = audit_memory_db(db_path)

    assert not report.warnings


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


def test_memory_corpus_rebuild_preserves_manual_relations(tmp_path: Path) -> None:
    db_path = tmp_path / "x.sqlite3"
    _seed_db(db_path)
    build_memory_corpus(db_path)
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
                "manual-support-edge",
                "bookmark:acct:tweet-1",
                "tweet:tweet-1",
                "supports",
                0.8,
                "manual",
                "{}",
                "2026-05-26T00:00:00+00:00",
                "2026-05-26T00:00:00+00:00",
            ),
        )

    build_memory_corpus(db_path)

    with sqlite3.connect(db_path) as conn:
        manual_count = conn.execute(
            "SELECT COUNT(*) FROM memory_relations WHERE relation_id = ?",
            ("manual-support-edge",),
        ).fetchone()[0]

    assert manual_count == 1


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
        conn.execute(
            """
            INSERT INTO memory_search_runs (
                run_id, query, query_plan_json, parameters_json, status,
                result_count, started_at, finished_at, error
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "bad-search-run",
                "bad query",
                '{"ok": true}',
                "{bad",
                "ok",
                0,
                "2026-05-26T00:00:00+00:00",
                "2026-05-26T00:00:00+00:00",
                None,
            ),
        )
        conn.execute(
            """
            INSERT INTO memory_search_results (
                result_id, run_id, rank, doc_id, doc_type, source_kind, source_id,
                source_url, score, snippet, provider, provider_role, match_method,
                evidence_status, metadata_json, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "bad-search-result",
                "missing-run",
                1,
                "missing-doc",
                "tweet_doc",
                "external_web",
                "missing-doc",
                None,
                0.0,
                "bad result",
                "local_memory",
                "index_provider",
                "test",
                "fact",
                '{"ok": true}',
                "2026-05-26T00:00:00+00:00",
            ),
        )
        conn.execute(
            """
            INSERT INTO memory_citation_annotations (
                citation_id, answer_id, chunk_id, source_kind, source_id,
                source_url, title, answer_start_index, answer_end_index,
                field_path, support_type, evidence_status, confidence,
                created_at, metadata_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "bad-citation",
                None,
                "missing-chunk",
                "local_x_db",
                "tweet:tweet-1",
                None,
                "Bad Citation",
                None,
                None,
                "context_chunks[0]",
                "background",
                "fact",
                0.5,
                "2026-05-26T00:00:00+00:00",
                '{"ok": true}',
            ),
        )

    report = audit_memory_db(db_path)

    assert report.orphaned_relations == 1
    assert report.invalid_json_by_field["memory_documents.metadata_json"] == 1
    assert report.invalid_json_by_field["memory_relations.evidence_json"] == 1
    assert report.invalid_json_by_field["memory_search_runs.parameters_json"] == 1
    assert report.v2_orphans["memory_search_results.run_id"] == 1
    assert report.v2_orphans["memory_search_results.doc_id"] == 1
    assert report.v2_orphans["memory_citation_annotations.chunk_id"] == 1
    assert report.invalid_enums_by_field["memory_search_results.source_kind"] == 1
    assert any("invalid JSON" in warning for warning in report.warnings)
    assert any("V2 evidence graph has orphan rows" in warning for warning in report.warnings)
    assert any("invalid enum values" in warning for warning in report.warnings)


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
    expanded = search_memory(
        db_path,
        "引用元リンク",
        limit=5,
        doc_type="tweet_doc",
    )
    bundle = build_evidence_bundle(db_path, "引用元を見たい", limit=3)

    assert summary.by_type["bookmark_of_tweet"] == 1
    assert summary.by_type["has_media"] == 1
    assert summary.by_type["quotes"] == 1
    assert summary.by_type["has_quote_tree"] == 1
    assert any(relation.relation_type == "has_quote_tree" for relation in relations)
    assert any(result.score_components["relations"] > 0 for result in results)
    assert any(
        result.source_tweet_id == "tweet-1" and "relation_expansion" in result.match_method
        for result in expanded
    )
    assert bundle["hits"][0]["evidence"]["relations"]


def test_memory_relations_build_url_topic_and_freshness_edges(tmp_path: Path) -> None:
    db_path = tmp_path / "x.sqlite3"
    _seed_db(db_path)
    with sqlite3.connect(db_path) as conn:
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
                    "tweet-old",
                    "https://x.com/a/status/tweet-old",
                    "a",
                    "古い強化学習とロボットのメモ。",
                    "2025-01-01T00:00:00+00:00",
                    "2025-01-01T00:00:00+00:00",
                    "2025-01-01T00:00:00+00:00",
                    "profile",
                    "profile",
                    "[]",
                    "{}",
                    "2025-01-01T00:00:00+00:00",
                ),
                (
                    "tweet-new",
                    "https://x.com/a/status/tweet-new",
                    "a",
                    "新しい強化学習とロボットの更新メモ。",
                    "2026-06-01T00:00:00+00:00",
                    "2026-06-01T00:00:00+00:00",
                    "2026-06-01T00:00:00+00:00",
                    "profile",
                    "profile",
                    "[]",
                    "{}",
                    "2026-06-01T00:00:00+00:00",
                ),
            ],
        )
        conn.executemany(
            """
            INSERT INTO ai_labels (
                label_id, account_id, tweet_id, label_scope, category_id,
                category_label, confidence, tags_json, summary, rationale,
                model, run_id, generated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    "label-old",
                    None,
                    "tweet-old",
                    "tweets",
                    "tech",
                    "Technology",
                    0.9,
                    '["強化学習", "ロボット"]',
                    "old summary",
                    "rationale",
                    "fake-model",
                    "run",
                    "2026-05-26T00:00:00+00:00",
                ),
                (
                    "label-new",
                    None,
                    "tweet-new",
                    "tweets",
                    "tech",
                    "Technology",
                    0.9,
                    '["強化学習", "ロボット"]',
                    "new summary",
                    "rationale",
                    "fake-model",
                    "run",
                    "2026-05-26T00:00:00+00:00",
                ),
            ],
        )
    build_memory_corpus(db_path)

    summary = build_memory_relations(db_path)
    bookmark_relations = relations_for_doc(db_path, "bookmark:acct:tweet-1", limit=20)
    old_relations = relations_for_doc(db_path, "tweet:tweet-old", limit=20)
    new_relations = relations_for_doc(db_path, "tweet:tweet-new", limit=20)
    results = search_memory(
        db_path,
        "最近保存した強化学習とロボット系の情報を古いものを除いて出して",
        limit=5,
    )

    assert summary.by_type["same_url"] >= 1
    assert summary.by_type["same_topic"] >= 1
    assert summary.by_type["newer_than"] >= 1
    assert summary.by_type["older_than"] >= 1
    assert summary.by_type["obsolete_candidate"] >= 1
    assert any(relation.relation_type == "same_url" for relation in bookmark_relations)
    assert any(relation.relation_type == "older_than" for relation in old_relations)
    assert any(relation.relation_type == "obsolete_candidate" for relation in old_relations)
    assert any(relation.relation_type == "newer_than" for relation in new_relations)
    assert any(
        (result.metadata.get("relation_counts") or {}).get("newer_than")
        for result in results
    )


def test_memory_relation_rebuild_preserves_manual_edges(tmp_path: Path) -> None:
    db_path = tmp_path / "x.sqlite3"
    _seed_db(db_path)
    build_memory_corpus(db_path)
    build_memory_relations(db_path)
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
                "manual-support-edge",
                "tweet:tweet-1",
                "tweet:tweet-2",
                "supports",
                0.8,
                "manual",
                "{}",
                "2026-05-26T00:00:00+00:00",
                "2026-05-26T00:00:00+00:00",
            ),
        )

    build_memory_relations(db_path)

    with sqlite3.connect(db_path) as conn:
        manual_count = conn.execute(
            "SELECT COUNT(*) FROM memory_relations WHERE relation_id = ?",
            ("manual-support-edge",),
        ).fetchone()[0]

    assert manual_count == 1


def test_memory_relation_judge_adds_support_or_contradict_edges(tmp_path: Path) -> None:
    db_path = tmp_path / "x.sqlite3"
    _seed_db(db_path)
    with sqlite3.connect(db_path) as conn:
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
                    "tweet-stale-old",
                    "https://x.com/a/status/tweet-stale-old",
                    "staleauthor",
                    "強化学習とロボットの古い実装メモ。",
                    "2025-01-01T00:00:00+00:00",
                    "2025-01-01T00:00:00+00:00",
                    "2025-01-01T00:00:00+00:00",
                    "profile",
                    "profile",
                    "[]",
                    "{}",
                    "2025-01-01T00:00:00+00:00",
                ),
                (
                    "tweet-stale-new",
                    "https://x.com/a/status/tweet-stale-new",
                    "staleauthor",
                    "強化学習とロボットの古い実装は非推奨。新しい方法に更新。",
                    "2026-06-01T00:00:00+00:00",
                    "2026-06-01T00:00:00+00:00",
                    "2026-06-01T00:00:00+00:00",
                    "profile",
                    "profile",
                    "[]",
                    "{}",
                    "2026-06-01T00:00:00+00:00",
                ),
            ],
        )
        conn.executemany(
            """
            INSERT INTO ai_labels (
                label_id, account_id, tweet_id, label_scope, category_id,
                category_label, confidence, tags_json, summary, rationale,
                model, run_id, generated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    "label-stale-old",
                    None,
                    "tweet-stale-old",
                    "tweets",
                    "tech",
                    "Technology",
                    0.9,
                    '["強化学習", "ロボット"]',
                    "old summary",
                    "rationale",
                    "fake-model",
                    "run",
                    "2026-05-26T00:00:00+00:00",
                ),
                (
                    "label-stale-new",
                    None,
                    "tweet-stale-new",
                    "tweets",
                    "tech",
                    "Technology",
                    0.9,
                    '["強化学習", "ロボット"]',
                    "new summary",
                    "rationale",
                    "fake-model",
                    "run",
                    "2026-05-26T00:00:00+00:00",
                ),
            ],
        )
    build_memory_corpus(db_path)
    build_memory_relations(db_path)

    summary = judge_memory_relations(db_path, provider="fake", limit=10)
    old_relations = relations_for_doc(db_path, "tweet:tweet-stale-old", limit=20)
    fresh_results = search_memory(
        db_path,
        "昔保存した強化学習とロボットの技術情報が今も正しいか",
        limit=5,
    )

    assert summary.inserted >= 1
    assert summary.by_type["contradicts"] >= 1
    assert any(relation.relation_type == "contradicts" for relation in old_relations)
    assert any(
        (result.metadata.get("relation_counts") or {}).get("contradicts")
        for result in fresh_results
    )


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
    report = audit_memory_db(db_path)
    assert report.fixture_artifacts["memory_external_runs.fake_provider"] == 1
    assert any("fixture/fake memory artifacts" in warning for warning in report.warnings)


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
        search_results = conn.execute("SELECT COUNT(*) FROM memory_search_results").fetchone()[0]
        first_result = conn.execute(
            """
            SELECT rank, doc_id, source_kind, provider_role, evidence_status
            FROM memory_search_results
            WHERE run_id = ?
            ORDER BY rank
            LIMIT 1
            """,
            (bundle.run_id,),
        ).fetchone()
        chunks = conn.execute("SELECT COUNT(*) FROM memory_context_chunks").fetchone()[0]
        citations = conn.execute(
            "SELECT COUNT(*) FROM memory_citation_annotations"
        ).fetchone()[0]
        answers = conn.execute("SELECT COUNT(*) FROM memory_answer_runs").fetchone()[0]
        workflows = conn.execute("SELECT COUNT(*) FROM memory_workflow_runs").fetchone()[0]

    assert search_runs == 1
    assert search_results == len(bundle.retrieved_hits)
    assert first_result == (
        1,
        bundle.retrieved_hits[0]["doc_id"],
        "local_x_db",
        "index_provider",
        "fact",
    )
    assert chunks == len(bundle.context_chunks)
    assert citations == len(bundle.citation_annotations)
    assert answers == 0
    assert workflows == 0


def test_memory_context_can_include_external_run_chunks(tmp_path: Path) -> None:
    db_path = tmp_path / "x.sqlite3"
    _seed_db(db_path)
    build_memory_corpus(db_path)
    external = search_external_evidence(
        db_path,
        "北千住 ピザ",
        provider="fake",
        limit=2,
    )

    bundle = build_context_bundle(
        db_path,
        "強化学習 ロボット",
        limit=1,
        external_run_id=external.run_id,
        external_reader_provider="fake",
        external_limit=1,
    )

    source_kinds = {chunk.source_kind for chunk in bundle.context_chunks}
    assert "local_x_db" in source_kinds
    assert "secondary" in source_kinds
    external_chunk = next(
        chunk
        for chunk in bundle.context_chunks
        if chunk.metadata.get("source_medium") == "external_web"
    )
    assert external_chunk.run_id == bundle.run_id
    assert external_chunk.metadata["external_run_id"] == external.run_id

    with sqlite3.connect(db_path) as conn:
        tool_run_id = conn.execute(
            "SELECT run_id FROM memory_tool_calls WHERE provider_role = 'fetch_agent'"
        ).fetchone()[0]
        chunk_count = conn.execute(
            "SELECT COUNT(*) FROM memory_context_chunks WHERE run_id = ?",
            (bundle.run_id,),
        ).fetchone()[0]

    assert tool_run_id == bundle.run_id
    assert chunk_count == len(bundle.context_chunks)


def test_memory_answer_stores_answer_artifact_and_citations(tmp_path: Path) -> None:
    db_path = tmp_path / "x.sqlite3"
    _seed_db(db_path)
    build_memory_corpus(db_path)
    build_memory_relations(db_path)

    answer = build_memory_answer(
        db_path,
        "強化学習 ロボット",
        limit=2,
        doc_type="bookmark_doc",
        answer_provider="fake",
        max_context_chars=40,
    )

    assert answer.answer_id
    assert answer.status == "ok"
    assert "[1]" in answer.answer_text
    assert answer.citation_annotations
    citation = answer.citation_annotations[0]
    assert citation.answer_id == answer.answer_id
    assert citation.answer_start_index is not None
    assert citation.support_type == "supports_answer"
    assert answer.structured["context_selection"]["truncated_chunk_ids"]
    assert answer.selected_context_chunks[0].metadata["truncated_for_answer"] is True

    with sqlite3.connect(db_path) as conn:
        answer_rows = conn.execute("SELECT COUNT(*) FROM memory_answer_runs").fetchone()[0]
        answer_citations = conn.execute(
            "SELECT COUNT(*) FROM memory_citation_annotations WHERE answer_id = ?",
            (answer.answer_id,),
        ).fetchone()[0]
        context_citations = conn.execute(
            "SELECT COUNT(*) FROM memory_citation_annotations WHERE answer_id IS NULL"
        ).fetchone()[0]
        answer_tool_calls = conn.execute(
            """
            SELECT COUNT(*)
            FROM memory_tool_calls
            WHERE provider_role = 'answer_engine' AND action = 'answer'
            """
        ).fetchone()[0]
        selected_chunk_rows = conn.execute(
            """
            SELECT COUNT(*)
            FROM memory_context_chunks
            WHERE chunk_id = ?
            """,
            (answer.selected_context_chunks[0].chunk_id,),
        ).fetchone()[0]

    assert answer_rows == 1
    assert answer_citations == len(answer.citation_annotations)
    assert context_citations == len(answer.context_bundle.citation_annotations)
    assert answer_tool_calls == 1
    assert selected_chunk_rows == 1


def test_memory_workflow_stores_route_steps_and_stop_reason(tmp_path: Path) -> None:
    db_path = tmp_path / "x.sqlite3"
    _seed_db(db_path)
    build_memory_corpus(db_path)
    build_memory_relations(db_path)

    workflow = run_memory_workflow(db_path, "カフェで読む強化学習", limit=2)

    assert workflow.route == "place_recall"
    assert workflow.status == "ok"
    assert workflow.stop_reason == "enough_evidence"
    assert [step.action for step in workflow.steps] == ["plan", "context"]
    assert workflow.context_bundle is not None
    assert workflow.context_bundle.context_chunks
    assert workflow.answer is None

    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            "SELECT route, status, stop_reason FROM memory_workflow_runs WHERE workflow_id = ?",
            (workflow.workflow_id,),
        ).fetchone()
        step_count = conn.execute(
            "SELECT COUNT(*) FROM memory_workflow_steps WHERE workflow_id = ?",
            (workflow.workflow_id,),
        ).fetchone()[0]

    assert row == ("place_recall", "ok", "enough_evidence")
    assert step_count == 2


def test_memory_workflow_can_attach_generated_answer_to_workflow(tmp_path: Path) -> None:
    db_path = tmp_path / "x.sqlite3"
    _seed_db(db_path)
    build_memory_corpus(db_path)
    build_memory_relations(db_path)

    workflow = run_memory_workflow(
        db_path,
        "強化学習 ロボット",
        limit=2,
        answer_provider="fake",
        max_context_chars=80,
    )

    assert workflow.answer is not None
    assert workflow.answer.workflow_id == workflow.workflow_id
    assert [step.action for step in workflow.steps] == ["plan", "context", "answer"]

    with sqlite3.connect(db_path) as conn:
        answer_workflow_id = conn.execute(
            "SELECT workflow_id FROM memory_answer_runs WHERE answer_id = ?",
            (workflow.answer.answer_id,),
        ).fetchone()[0]

    assert answer_workflow_id == workflow.workflow_id


def test_memory_workflow_can_merge_llm_context_into_route(tmp_path: Path) -> None:
    db_path = tmp_path / "x.sqlite3"
    _seed_db(db_path)
    build_memory_corpus(db_path)
    build_memory_relations(db_path)

    workflow = run_memory_workflow(
        db_path,
        "強化学習 ロボット 今も正しい？",
        limit=2,
        llm_context_provider="fake",
    )

    assert workflow.route == "current_fact_check"
    assert workflow.status == "ok"
    assert workflow.stop_reason == "enough_evidence"
    assert [step.action for step in workflow.steps] == ["plan", "context", "llm_context"]
    assert workflow.context_bundle is not None
    assert "local_x_db" in {
        chunk.source_kind for chunk in workflow.context_bundle.context_chunks
    }
    assert "secondary" in {chunk.source_kind for chunk in workflow.context_bundle.context_chunks}
    assert any(
        chunk.provider_role == "llm_context_provider"
        for chunk in workflow.context_bundle.context_chunks
    )

    with sqlite3.connect(db_path) as conn:
        tool_run_id = conn.execute(
            """
            SELECT run_id
            FROM memory_tool_calls
            WHERE action = 'llm_context'
            """
        ).fetchone()[0]

    assert tool_run_id == workflow.context_bundle.run_id


def test_memory_workflow_answer_uses_merged_llm_context(tmp_path: Path) -> None:
    db_path = tmp_path / "x.sqlite3"
    _seed_db(db_path)
    build_memory_corpus(db_path)
    build_memory_relations(db_path)

    workflow = run_memory_workflow(
        db_path,
        "強化学習 ロボット 今も正しい？",
        limit=1,
        llm_context_provider="fake",
        answer_provider="fake",
        max_context_chunks=4,
    )

    assert workflow.answer is not None
    assert [step.action for step in workflow.steps] == [
        "plan",
        "context",
        "llm_context",
        "answer",
    ]
    assert any(
        chunk.provider_role == "llm_context_provider"
        for chunk in workflow.answer.selected_context_chunks
    )
    assert workflow.answer.retrieval_config["context_parameters"]["llm_context"][
        "provider_role"
    ] == "llm_context_provider"


def test_memory_workflow_route_does_not_treat_recent_as_fact_check() -> None:
    recent_learning = plan_workflow_route(
        build_query_plan("最近保存した強化学習とロボット系の情報を出して")
    )
    current_fact = plan_workflow_route(build_query_plan("昔保存したこの技術情報、今も正しい？"))

    assert recent_learning.route == "learning_map"
    assert current_fact.route == "current_fact_check"
    assert current_fact.wants_external_context is True


def test_memory_eval_records_route_level_fields(tmp_path: Path) -> None:
    db_path = tmp_path / "x.sqlite3"
    _seed_db(db_path)
    build_memory_corpus(db_path)
    build_memory_relations(db_path)

    results = run_memory_eval(db_path, limit=2)
    by_route = {result.route: result for result in results}

    assert by_route["place_recall"].expected_route == "place_recall"
    assert by_route["place_recall"].context_chunks > 0
    assert "local_x_db" in by_route["place_recall"].source_kinds
    assert by_route["place_recall"].answer_status == "ok"
    assert by_route["place_recall"].answer_citations > 0
    assert by_route["learning_map"].expected_route == "learning_map"
    assert by_route["company_event"].expected_route == "company_event"
    assert by_route["current_fact_check"].stop_reason in {
        "external_context_needed",
        "no_local_evidence",
    }
    no_answer_results = run_memory_eval(db_path, limit=1, answer_provider="none")
    assert all(result.answer_status is None for result in no_answer_results)
    build_memory_embeddings(db_path, provider="local_hash", dimensions=64)
    semantic_results = run_memory_eval(
        db_path,
        limit=1,
        answer_provider="none",
        semantic_provider="local_hash",
        semantic_dimensions=64,
        semantic_profile="general_memory",
        semantic_template_version="memory-doc-embedding-v1",
    )
    assert any(
        "semantic" in engine
        for result in semantic_results
        for engine in result.retrieval_engines
    )
    cases_path = tmp_path / "memory_eval_cases.jsonl"
    cases_path.write_text(
        json.dumps(
            {
                "query": "引用元を見ないと意味が変わる投稿を根拠付きで出して",
                "required_any_terms": ["引用", "引用元", "quote"],
                "preferred_doc_types": ["quote_tree_doc"],
                "required_feature": "quote_context",
                "expected_route": "quote_context",
                "min_hit_score": 0.5,
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    custom_results = run_memory_eval(
        db_path,
        cases=load_eval_cases(cases_path),
        limit=2,
        answer_provider="none",
    )
    stored_run_id = store_memory_eval_results(
        db_path,
        custom_results,
        cases_path=str(cases_path),
        parameters={"limit": 2, "answer_provider": "none"},
    )

    assert len(custom_results) == 1
    assert custom_results[0].route == "quote_context"
    with sqlite3.connect(db_path) as conn:
        stored_run = conn.execute(
            "SELECT status, case_count FROM memory_eval_runs WHERE run_id = ?",
            (stored_run_id,),
        ).fetchone()
        stored_results = conn.execute(
            "SELECT COUNT(*) FROM memory_eval_results WHERE run_id = ?",
            (stored_run_id,),
        ).fetchone()[0]
    listed_runs = list_memory_eval_runs(db_path)
    loaded_run = load_memory_eval_run(db_path, stored_run_id)
    assert stored_run[1] == 1
    assert stored_results == 1
    assert listed_runs[0]["run_id"] == stored_run_id
    assert loaded_run["results"][0]["route"] == "quote_context"


def test_memory_answer_gemini_provider_uses_openai_compatible_chat(
    tmp_path: Path,
    monkeypatch,
) -> None:
    db_path = tmp_path / "x.sqlite3"
    _seed_db(db_path)
    build_memory_corpus(db_path)
    captured = {}

    def fake_post_json(url, payload, *, headers, timeout_seconds, retries=3):
        captured["url"] = url
        captured["payload"] = payload
        captured["headers"] = headers
        captured["timeout_seconds"] = timeout_seconds
        captured["retries"] = retries
        return {"choices": [{"message": {"content": "根拠に基づく回答です [1]"}}]}

    monkeypatch.setenv("GEMINI_API_KEY", "fake-key")
    monkeypatch.setattr("research_x.memory.answer._post_json", fake_post_json)

    answer = build_memory_answer(
        db_path,
        "強化学習 ロボット",
        limit=1,
        answer_provider="gemini",
        answer_model="gemini-2.5-flash",
        answer_timeout_seconds=7.0,
    )

    assert answer.model == "gemini-2.5-flash"
    assert answer.provider == "gemini"
    assert answer.answer_text == "根拠に基づく回答です [1]"
    assert captured["url"].endswith("/v1beta/openai/chat/completions")
    assert captured["payload"]["model"] == "gemini-2.5-flash"
    assert captured["headers"]["Authorization"] == "Bearer fake-key"
    assert captured["timeout_seconds"] == 7.0
    assert "fake-key" not in json.dumps(answer.as_dict(), ensure_ascii=False)


def test_memory_answer_marks_uncited_generated_text_for_review(
    tmp_path: Path,
    monkeypatch,
) -> None:
    db_path = tmp_path / "x.sqlite3"
    _seed_db(db_path)
    build_memory_corpus(db_path)

    def fake_post_json(url, payload, *, headers, timeout_seconds, retries=3):
        del url, payload, headers, timeout_seconds, retries
        return {"choices": [{"message": {"content": "根拠はありますが番号を付けません。"}}]}

    monkeypatch.setenv("GEMINI_API_KEY", "fake-key")
    monkeypatch.setattr("research_x.memory.answer._post_json", fake_post_json)

    answer = build_memory_answer(
        db_path,
        "強化学習 ロボット",
        limit=1,
        answer_provider="gemini",
    )

    assert answer.status == "needs_review"
    assert answer.structured["missing_citation_markers"] == ["[1]"]
    assert answer.citation_annotations[0].support_type == "uncited_context"
    report = audit_memory_db(db_path)
    assert report.answer_status_counts["needs_review"] == 1
    assert any("stored answer artifacts need review" in warning for warning in report.warnings)


def test_memory_build_derived_documents_creates_searchable_cards(tmp_path: Path) -> None:
    db_path = tmp_path / "x.sqlite3"
    _seed_db(db_path)
    _seed_derived_source_rows(db_path)
    build_memory_corpus(db_path)

    summary = build_derived_documents(db_path, max_source_docs_per_card=2)
    build_memory_relations(db_path)

    assert summary.place_cards >= 1
    assert summary.author_profiles >= 1
    assert summary.ticker_events == 1

    place_results = search_memory(db_path, "北千住 ピザ", limit=3)
    venue_results = search_memory(db_path, "横浜 ギャラリー 展示", limit=3)
    finance_results = search_memory(db_path, "5/29 キオクシア 株価 急騰", limit=3)
    author_results = search_memory(db_path, "@foodie ピザ", limit=5)
    place_bundle = build_evidence_bundle(
        db_path,
        "北千住 ピザ",
        limit=1,
        doc_type="place_card",
    )

    assert any(result.doc_type == "place_card" for result in place_results)
    assert any(result.doc_type == "place_card" for result in venue_results)
    assert finance_results[0].doc_type == "ticker_event"
    assert any(result.doc_type == "author_profile" for result in author_results)
    assert place_bundle["hits"][0]["evidence"]["derived"]["source_doc_count"] > 2

    with sqlite3.connect(db_path) as conn:
        doc_count = conn.execute("SELECT COUNT(*) FROM memory_documents").fetchone()[0]
        fts_count = conn.execute("SELECT COUNT(*) FROM memory_document_fts").fetchone()[0]
        derived_relations = conn.execute(
            """
            SELECT COUNT(*)
            FROM memory_relations
            WHERE relation_type = 'derived_from_source'
            """
        ).fetchone()[0]
        ticker_metadata = conn.execute(
            """
            SELECT metadata_json
            FROM memory_documents
            WHERE doc_type = 'ticker_event'
            """
        ).fetchone()[0]
        place_metadata = json.loads(
            conn.execute(
                """
                SELECT metadata_json
                FROM memory_documents
                WHERE doc_type = 'place_card'
                  AND metadata_json LIKE '%北千住%'
                """
            ).fetchone()[0]
        )

    assert fts_count == doc_count
    assert derived_relations >= place_metadata["source_doc_count"]
    assert place_metadata["source_doc_count"] > len(place_metadata["display_source_doc_ids"])
    assert len(place_metadata["source_doc_ids"]) == place_metadata["source_doc_count"]
    assert "キオクシア" in ticker_metadata


def test_memory_build_topic_thread_documents(tmp_path: Path) -> None:
    db_path = tmp_path / "x.sqlite3"
    _seed_db(db_path)
    build_memory_corpus(db_path)

    summary = build_derived_documents(
        db_path,
        kinds=("topic_thread",),
        min_topic_docs=2,
    )
    results = search_memory(
        db_path,
        "強化学習とロボットで後から勉強に使える情報を整理して",
        limit=5,
    )

    assert summary.topic_threads >= 1
    assert summary.by_type["topic_thread"] == summary.topic_threads
    assert any(result.doc_type == "topic_thread" for result in results)


def test_reader_extract_fake_provider_stores_external_context(tmp_path: Path) -> None:
    db_path = tmp_path / "x.sqlite3"

    bundle = extract_url_to_context(
        db_path,
        "https://example.com/pizza",
        provider="fake",
        query="北千住 ピザ",
    )

    assert bundle.provider == "fake"
    assert bundle.provider_role == "fetch_agent"
    assert bundle.context_chunk["source_kind"] == "secondary"
    assert bundle.context_chunk["metadata"]["source_medium"] == "external_web"
    assert bundle.context_chunk["source_url"] == "https://example.com/pizza"
    assert "Fake extracted page" in bundle.context_chunk["chunk_text"]
    assert bundle.citation_annotation["evidence_status"] == "unconfirmed"

    with sqlite3.connect(db_path) as conn:
        tool_calls = conn.execute("SELECT COUNT(*) FROM memory_tool_calls").fetchone()[0]
        chunks = conn.execute("SELECT COUNT(*) FROM memory_context_chunks").fetchone()[0]
        citations = conn.execute(
            "SELECT COUNT(*) FROM memory_citation_annotations"
        ).fetchone()[0]

    assert tool_calls == 1
    assert chunks == 1
    assert citations == 1


def test_reader_extract_http_provider_normalizes_html(
    tmp_path: Path,
    monkeypatch,
) -> None:
    db_path = tmp_path / "x.sqlite3"

    def fake_read_url(url, *, timeout_seconds, user_agent, max_bytes):
        assert timeout_seconds == 5.0
        assert user_agent == "test-agent"
        assert max_bytes == 1024
        return HttpResponse(
            final_url=url,
            status_code=200,
            content_type="text/html; charset=utf-8",
            body=(
                b"<html><head><title>Pizza Place</title><script>ignore()</script></head>"
                b"<body><h1>North Senju</h1><p>Wood fired pizza.</p></body></html>"
            ),
        )

    monkeypatch.setattr("research_x.memory.reader._read_url", fake_read_url)

    bundle = extract_url_to_context(
        db_path,
        "https://example.com/pizza",
        provider="http",
        timeout_seconds=5.0,
        user_agent="test-agent",
        max_bytes=1000,
    )

    assert bundle.page.title == "Pizza Place"
    assert "North Senju" in bundle.page.text
    assert "ignore" not in bundle.page.text
    assert bundle.context_chunk["provider"] == "http"
    assert bundle.context_chunk["source_kind"] == "secondary"
    assert bundle.citation_annotation["evidence_status"] == "fact"


def test_reader_extract_external_run_uses_stored_urls(tmp_path: Path) -> None:
    db_path = tmp_path / "x.sqlite3"
    external = search_external_evidence(
        db_path,
        "北千住 ピザ",
        provider="fake",
        limit=2,
    )

    bundles = extract_external_run_to_context(
        db_path,
        external.run_id,
        provider="fake",
        limit=1,
        query="北千住 ピザ",
    )

    assert len(bundles) == 1
    assert bundles[0].context_chunk["metadata"]["external_run_id"] == external.run_id


def test_llm_context_fake_provider_stores_chunks_and_citations(tmp_path: Path) -> None:
    db_path = tmp_path / "x.sqlite3"

    bundle = fetch_llm_context_to_context(
        db_path,
        "北千住 ピザ",
        provider="fake",
    )

    assert bundle.provider == "fake"
    assert bundle.context_chunks
    assert bundle.citation_annotations
    assert bundle.context_chunks[0]["provider_role"] == "llm_context_provider"
    assert bundle.context_chunks[0]["source_kind"] == "secondary"
    assert bundle.context_chunks[0]["metadata"]["source_medium"] == "external_web"
    assert bundle.citation_annotations[0]["evidence_status"] == "unconfirmed"
    assert bundle.retention_policy == "extracted_context_with_source_urls"

    with sqlite3.connect(db_path) as conn:
        tool_calls = conn.execute(
            "SELECT COUNT(*) FROM memory_tool_calls WHERE action = 'llm_context'"
        ).fetchone()[0]
        chunks = conn.execute(
            "SELECT COUNT(*) FROM memory_context_chunks WHERE provider = 'fake'"
        ).fetchone()[0]
        citations = conn.execute(
            """
            SELECT COUNT(*)
            FROM memory_citation_annotations
            WHERE json_extract(metadata_json, '$.source_medium') = 'external_web'
            """
        ).fetchone()[0]

    assert tool_calls == 1
    assert chunks == len(bundle.context_chunks)
    assert citations == len(bundle.citation_annotations)


def test_llm_context_brave_provider_parses_generic_grounding(
    tmp_path: Path,
    monkeypatch,
) -> None:
    captured = {}

    def fake_post_json(url, payload, *, headers, timeout_seconds):
        captured["url"] = url
        captured["payload"] = payload
        captured["headers"] = headers
        captured["timeout_seconds"] = timeout_seconds
        return {
            "grounding": {
                "generic": [
                    {
                        "url": "https://example.com/pizza",
                        "title": "Pizza page",
                        "snippets": ["北千住のピザ店", "予約情報"],
                    }
                ]
            },
            "sources": {
                "https://example.com/pizza": {
                    "title": "Pizza page",
                    "hostname": "example.com",
                }
            },
        }

    monkeypatch.setenv("BRAVE_SEARCH_API_KEY", "brave-key")
    monkeypatch.setattr("research_x.memory.llm_context._post_json", fake_post_json)

    bundle = fetch_llm_context_to_context(
        tmp_path / "x.sqlite3",
        "北千住 ピザ",
        provider="brave",
        count=99,
        maximum_number_of_urls=99,
        maximum_number_of_tokens=999999,
        maximum_number_of_snippets=999,
        search_lang="ja",
        country="JP",
    )

    assert captured["url"] == "https://api.search.brave.com/res/v1/llm/context"
    assert captured["headers"]["X-Subscription-Token"] == "brave-key"
    assert captured["payload"]["q"] == "北千住 ピザ"
    assert captured["payload"]["count"] == 50
    assert captured["payload"]["maximum_number_of_urls"] == 50
    assert captured["payload"]["maximum_number_of_tokens"] == 32768
    assert captured["payload"]["maximum_number_of_snippets"] == 256
    assert bundle.sources[0].url == "https://example.com/pizza"
    assert bundle.context_chunks[0]["source_kind"] == "secondary"
    assert "北千住" in bundle.context_chunks[0]["chunk_text"]
    assert "brave-key" not in json.dumps(bundle.as_dict(), ensure_ascii=False)


def test_external_source_kind_classification() -> None:
    assert classify_external_source_kind("https://x.com/alice/status/1") == "user_generated"
    assert classify_external_source_kind("https://www.sec.gov/filing") == "official"
    assert classify_external_source_kind("https://example.com/article") == "secondary"


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


def test_openai_compatible_embedding_request_uses_custom_endpoint(monkeypatch) -> None:
    captured = {}

    def fake_post_json(url, payload, *, headers, timeout_seconds, retries=3):
        captured["url"] = url
        captured["payload"] = payload
        captured["headers"] = headers
        return {"data": [{"index": 0, "embedding": [0.1, 0.2, 0.3]}]}

    monkeypatch.setenv("CUSTOM_EMBED_KEY", "fake-key")
    monkeypatch.setattr(embeddings, "_post_json", fake_post_json)

    spec = embeddings.resolve_embedding_spec(
        provider="openai_compatible",
        model="custom-embedding",
        dimensions=3,
        api_key_env="CUSTOM_EMBED_KEY",
        base_url="https://embeddings.example/v1/embeddings",
    )
    vector = embeddings._OpenAICompatibleEmbedder(spec).embed_texts(  # noqa: SLF001
        ["robot learning"],
        task_type="RETRIEVAL_DOCUMENT",
    )[0]

    assert vector
    assert captured["url"] == "https://embeddings.example/v1/embeddings"
    assert captured["headers"]["Authorization"] == "Bearer fake-key"
    assert captured["payload"] == {
        "model": "custom-embedding",
        "input": ["robot learning"],
        "encoding_format": "float",
        "dimensions": 3,
    }


def test_embedding_post_json_uses_retry_after(monkeypatch) -> None:
    calls = []
    sleeps = []

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return None

        def read(self):
            return b'{"ok": true}'

    def fake_urlopen(request, *, timeout):
        calls.append((request, timeout))
        if len(calls) == 1:
            raise urllib.error.HTTPError(
                url="https://embeddings.example/v1/embeddings",
                code=429,
                msg="Too Many Requests",
                hdrs={"Retry-After": "0.25"},
                fp=io.BytesIO(b"busy"),
            )
        return FakeResponse()

    monkeypatch.setattr(embeddings.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(embeddings.time, "sleep", lambda seconds: sleeps.append(seconds))

    response = embeddings._post_json(  # noqa: SLF001
        "https://embeddings.example/v1/embeddings",
        {"input": ["hello"]},
        headers={"Authorization": "Bearer fake"},
        timeout_seconds=30,
        retries=2,
    )

    assert response == {"ok": True}
    assert len(calls) == 2
    assert sleeps == [0.25]


def test_memory_cli_commands(tmp_path: Path, capsys) -> None:
    db_path = tmp_path / "x.sqlite3"
    _seed_db(db_path)

    assert main(["memory", "build-corpus", "--db", str(db_path)]) == 0
    assert main(["memory", "build-derived", "--db", str(db_path)]) == 0
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
    assert (
        main(
            [
                "memory",
                "embedding-estimate",
                "--db",
                str(db_path),
                "--provider",
                "gemini",
                "--dimensions",
                "768",
                "--batch-size",
                "2",
            ]
        )
        == 0
    )
    assert main(["memory", "embedding-specs", "--db", str(db_path)]) == 0
    assert (
        main(
            [
                "memory",
                "embedding-coverage",
                "--db",
                str(db_path),
                "--provider",
                "local_hash",
                "--dimensions",
                "64",
            ]
        )
        == 0
    )
    assert (
        main(
            [
                "memory",
                "export-corpus2skill",
                "--db",
                str(db_path),
                "--bundle-dir",
                str(tmp_path / "c2s_cli_bundle"),
                "--doc-type",
                "bookmark_doc",
                "--limit",
                "2",
            ]
        )
        == 0
    )
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
    assert (
        main(
            [
                "memory",
                "judge-relations",
                "--db",
                str(db_path),
                "--provider",
                "fake",
                "--no-store",
            ]
        )
        == 0
    )
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
    external_output_start = capsys.readouterr().out
    assert (
        main(
            [
                "memory",
                "extract-url",
                "--db",
                str(db_path),
                "--url",
                "https://example.com/pizza",
                "--provider",
                "fake",
                "--allow-fixture-provider",
            ]
        )
        == 0
    )
    extract_output = capsys.readouterr().out
    assert (
        main(
            [
                "memory",
                "llm-context",
                "--db",
                str(db_path),
                "--query",
                "北千住 ピザ",
                "--provider",
                "fake",
                "--allow-fixture-provider",
            ]
        )
        == 0
    )
    llm_context_output = capsys.readouterr().out
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
                "--allow-fixture-provider",
            ]
        )
        == 0
    )
    external_output = capsys.readouterr().out
    external_payload = json.loads(external_output)
    assert (
        main(
            [
                "memory",
                "context",
                "--db",
                str(db_path),
                "--query",
                "北千住 ピザ",
                "--external-run-id",
                external_payload["run_id"],
                "--external-provider",
                "fake",
                "--external-limit",
                "1",
                "--allow-fixture-provider",
            ]
        )
        == 0
    )
    assert (
        main(
            [
                "memory",
                "answer",
                "--db",
                str(db_path),
                "--query",
                "ロボット",
                "--allow-fixture-provider",
            ]
        )
        == 0
    )
    assert main(["memory", "workflow", "--db", str(db_path), "--query", "ロボット"]) == 0
    assert (
        main(
            [
                "memory",
                "workflow",
                "--db",
                str(db_path),
                "--query",
                "ロボット 今も正しい？",
                "--llm-context-provider",
                "fake",
                "--allow-fixture-provider",
            ]
        )
        == 0
    )
    cli_eval_cases = tmp_path / "memory_eval_cases.jsonl"
    cli_eval_cases.write_text(
        json.dumps(
            {
                "query": "強化学習 ロボット",
                "required_any_terms": ["強化学習", "ロボット"],
                "preferred_doc_types": ["bookmark_doc", "tweet_doc"],
                "min_hit_score": 0.5,
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    assert (
        main(
            [
                "memory",
                "eval",
                "--db",
                str(db_path),
                "--cases",
                str(cli_eval_cases),
                "--limit",
                "1",
                "--semantic-provider",
                "local_hash",
                "--semantic-dimensions",
                "64",
                "--store",
            ]
        )
        == 0
    )
    with sqlite3.connect(db_path) as conn:
        eval_run_id = conn.execute("SELECT run_id FROM memory_eval_runs LIMIT 1").fetchone()[0]
    assert main(["memory", "eval-runs", "--db", str(db_path)]) == 0
    assert (
        main(
            [
                "memory",
                "eval-show",
                "--db",
                str(db_path),
                "--run-id",
                eval_run_id,
            ]
        )
        == 0
    )

    output = (
        external_output_start
        + extract_output
        + llm_context_output
        + external_output
        + capsys.readouterr().out
    )
    assert "tweet-1" in output
    assert "place_cards" in output
    assert "hits" in output
    assert "context_chunks" in output
    assert "answer_text" in output
    assert "workflow:" in output
    assert "external_web" in output
    assert "reader_extract" in output
    assert "llm_context" in output
    assert "memory://fake-external-search" in output


def test_memory_cli_requires_fixture_opt_in_for_stored_fake_provider(
    tmp_path: Path,
    capsys,
) -> None:
    db_path = tmp_path / "x.sqlite3"

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
            ]
        )
        == 1
    )
    captured = capsys.readouterr()
    assert "diagnostic-only" in captured.err
    assert (
        main(
            [
                "memory",
                "llm-context",
                "--db",
                str(db_path),
                "--query",
                "ロボット",
                "--provider",
                "fake",
            ]
        )
        == 1
    )
    captured = capsys.readouterr()
    assert "diagnostic-only" in captured.err
    assert "Traceback" not in captured.err
    with sqlite3.connect(db_path) as conn:
        tables = conn.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE name = 'memory_external_runs'"
        ).fetchone()[0]
    assert tables == 0

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
                "--no-store",
            ]
        )
        == 0
    )
    assert (
        main(
            [
                "memory",
                "workflow",
                "--db",
                str(db_path),
                "--query",
                "ロボット",
                "--answer-provider",
                "fake",
            ]
        )
        == 1
    )
    captured = capsys.readouterr()
    assert "diagnostic-only" in captured.err
    assert (
        main(
            [
                "memory",
                "workflow",
                "--db",
                str(db_path),
                "--query",
                "ロボット 今も正しい？",
                "--llm-context-provider",
                "fake",
            ]
        )
        == 1
    )
    captured = capsys.readouterr()
    assert "diagnostic-only" in captured.err
    assert (
        main(
            [
                "memory",
                "judge-relations",
                "--db",
                str(db_path),
                "--provider",
                "fake",
            ]
        )
        == 1
    )
    captured = capsys.readouterr()
    assert "diagnostic-only" in captured.err


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


def _seed_derived_source_rows(db_path: Path) -> None:
    with sqlite3.connect(db_path) as conn:
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
                    "tweet-place",
                    "https://x.com/foodie/status/tweet-place",
                    "foodie",
                    "北千住のピザ店。イタリアンのランチが良かったのであとで行きたい。",
                    "2026-05-27T00:00:00+00:00",
                    "2026-05-27T00:00:00+00:00",
                    "2026-05-27T00:00:00+00:00",
                    "bookmark_root",
                    "bookmarks",
                    "[]",
                    "{}",
                    "2026-05-27T00:00:00+00:00",
                ),
                (
                    "tweet-finance",
                    "https://x.com/market/status/tweet-finance",
                    "marketwatcher",
                    "5/29 キオクシアの株価が急騰。半導体と決算の分析メモ。",
                    "2026-05-29T00:00:00+00:00",
                    "2026-05-29T00:00:00+00:00",
                    "2026-05-29T00:00:00+00:00",
                    "bookmark_root",
                    "bookmarks",
                    "[]",
                    "{}",
                    "2026-05-29T00:00:00+00:00",
                ),
                (
                    "tweet-place-2",
                    "https://x.com/foodie/status/tweet-place-2",
                    "foodie",
                    "北千住でピザとカフェを探すメモ。予約候補。",
                    "2026-05-28T00:00:00+00:00",
                    "2026-05-28T00:00:00+00:00",
                    "2026-05-28T00:00:00+00:00",
                    "bookmark_root",
                    "bookmarks",
                    "[]",
                    "{}",
                    "2026-05-28T00:00:00+00:00",
                ),
                (
                    "tweet-place-3",
                    "https://x.com/foodie/status/tweet-place-3",
                    "foodie",
                    "北千住のイタリアン。ピザ店リストの追加。",
                    "2026-05-29T01:00:00+00:00",
                    "2026-05-29T01:00:00+00:00",
                    "2026-05-29T01:00:00+00:00",
                    "bookmark_root",
                    "bookmarks",
                    "[]",
                    "{}",
                    "2026-05-29T01:00:00+00:00",
                ),
                (
                    "tweet-venue",
                    "https://x.com/art/status/tweet-venue",
                    "artguide",
                    "横浜のギャラリーで展示。週末に行きたい場所。",
                    "2026-05-30T00:00:00+00:00",
                    "2026-05-30T00:00:00+00:00",
                    "2026-05-30T00:00:00+00:00",
                    "bookmark_root",
                    "bookmarks",
                    "[]",
                    "{}",
                    "2026-05-30T00:00:00+00:00",
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
                ("acct", "tweet-place", 1, "2026-05-27T00:00:00+00:00", "[]", "run"),
                ("acct", "tweet-finance", 2, "2026-05-29T00:00:00+00:00", "[]", "run"),
                ("acct", "tweet-place-2", 3, "2026-05-28T00:00:00+00:00", "[]", "run"),
                ("acct", "tweet-place-3", 4, "2026-05-29T01:00:00+00:00", "[]", "run"),
                ("acct", "tweet-venue", 5, "2026-05-30T00:00:00+00:00", "[]", "run"),
            ],
        )


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
