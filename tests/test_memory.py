import io
import json
import sqlite3
import urllib.error
from dataclasses import replace
from pathlib import Path

import pytest

from research_x.cli import main
from research_x.memory import api_lane_estimate as memory_api_lane_estimate
from research_x.memory import embeddings
from research_x.memory import evals as memory_evals
from research_x.memory import portfolio as memory_portfolio
from research_x.memory import rerank as memory_rerank
from research_x.memory.answer import answer_json, assess_answerability, build_memory_answer
from research_x.memory.api_lane_estimate import (
    build_api_lane_estimate_report,
    discover_external_urls,
)
from research_x.memory.audit import audit_memory_db
from research_x.memory.context import (
    CitationAnnotation,
    ContextBundle,
    ContextChunk,
    build_context_bundle,
    context_bundle_json,
)
from research_x.memory.context_budget import ContextBudgetPolicy, budget_json_payload
from research_x.memory.context_policy import (
    context_policy_eval_json,
    evaluate_route_context_policy,
)
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
    pack_embedding,
)
from research_x.memory.evals import (
    DEFAULT_EVAL_CASES,
    EvalCase,
    list_memory_eval_runs,
    load_eval_cases,
    load_memory_eval_run,
    run_memory_eval,
    store_memory_eval_results,
)
from research_x.memory.evidence import build_evidence_bundle
from research_x.memory.external import search_external_evidence
from research_x.memory.feedback import add_feedback, feedback_scores_for_docs
from research_x.memory.final_skeleton import run_final_skeleton_preflight
from research_x.memory.governance import (
    add_governance_record,
    add_tombstone,
    is_artifact_tombstoned,
    list_governance_records,
    restore_governance_record,
)
from research_x.memory.judge_relations import judge_memory_relations
from research_x.memory.llm_context import fetch_llm_context_to_context
from research_x.memory.media_embeddings import (
    FIXTURE_MEDIA_PROVIDER,
    build_media_embeddings,
    estimate_media_embedding_build,
    media_embedding_coverage_report,
    restore_media_source_bundle,
    search_media_embeddings,
)
from research_x.memory.media_roles import (
    build_media_roles,
    estimate_media_roles,
    media_role_coverage,
)
from research_x.memory.objective_executor import (
    ObjectiveRouteArmResult,
    format_objective_route_execution,
    run_objective_route_execution,
)
from research_x.memory.objective_routes import plan_objective_routes
from research_x.memory.observability import (
    format_research_run,
    list_research_runs,
    show_research_run,
)
from research_x.memory.ocr import (
    add_media_observation,
    build_ocr_evidence,
    estimate_ocr_evidence,
    mark_ocr_second_pass_candidates,
    media_observation_coverage,
    ocr_coverage,
    ocr_search,
    promote_ocr_chunks,
)
from research_x.memory.portfolio import (
    parse_portfolio_reranker_spec,
    parse_portfolio_semantic_spec,
    run_portfolio_eval,
)
from research_x.memory.query import build_query_plan
from research_x.memory.question_types import known_question_type_ids, question_types_as_dicts
from research_x.memory.reader import (
    HttpResponse,
    extract_external_run_to_context,
    extract_url_to_context,
)
from research_x.memory.relations import build_memory_relations, relations_for_doc
from research_x.memory.relevance import (
    LOCAL_JUDGE_CANDIDATE,
    RelevanceFixture,
    default_relevance_fixtures,
    judge_relevance_fixture,
    relevance_fixture_report_json,
    run_relevance_fixture_report,
)
from research_x.memory.rerank import rerank_evidence_query, rerank_hits
from research_x.memory.research_artifacts import build_execution_artifacts
from research_x.memory.retrieval_strategy import (
    DEFAULT_RETRIEVAL_STRATEGIES,
    reranker_spec_strings_for_strategies,
    retrieval_strategies_as_dicts,
    semantic_spec_strings_for_strategies,
)
from research_x.memory.retrieval_text import (
    build_retrieval_text_profiles,
    retrieval_text_coverage,
)
from research_x.memory.schema import ensure_memory_schema
from research_x.memory.search import (
    search_memory,
    search_memory_retrieval_text_only,
    strong_anchor_terms_for_query,
)
from research_x.memory.source_kinds import classify_external_source_kind
from research_x.memory.vector_projection import (
    benchmark_json,
    benchmark_vector_backends,
    build_vector_projection,
    vector_projection_coverage,
)
from research_x.memory.workflow import (
    MemoryWorkflow,
    format_workflow,
    plan_workflow_route,
    run_memory_workflow,
    workflow_json,
)
from research_x.tool_interface.memory_tool_contract import (
    validate_tool_output,
    validate_tool_output_against_db,
    workflow_tool_output,
    workflow_tool_output_json,
)


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
    assert results[0].metadata["engine_contributions"]
    assert "rrf" in results[0].score_components
    assert any(result.source_tweet_id == "tweet-1" for result in natural_results)
    assert natural_results[0].score_components["doc_type"] > 0
    assert "カフェ" in natural_results[0].matched_terms

    plan = build_query_plan("画像付きで保存した技術資料っぽい投稿を出して")
    assert plan.requires_media_context is True
    assert "media_doc" in plan.doc_type_weights
    docs_plan = build_query_plan(
        "日本語で聞くけど、保存した英語論文や公式docsから強化学習の資料を出して"
    )
    assert "technology" in docs_plan.intents
    assert "media" not in docs_plan.intents
    contradiction_plan = build_query_plan("同じ話で反対意見や矛盾している保存投稿はある？")
    assert "freshness" in contradiction_plan.intents
    assert contradiction_plan.prefers_recent is True
    exclude_plan = build_query_plan("最近保存した強化学習を古いものを除いて出して")
    assert exclude_plan.excludes_old is True
    assert "古い" not in exclude_plan.search_terms
    place_plan = build_query_plan("北千住にあるピザの店")
    assert "北千住" in place_plan.exact_terms
    finance_plan = build_query_plan("5/29のキオクシアの株価急騰")
    assert "5/29" in finance_plan.exact_terms
    assert "キオクシア" in finance_plan.exact_terms
    assert "5/29" not in strong_anchor_terms_for_query("5/29のキオクシアの株価急騰")
    assert not strong_anchor_terms_for_query("2026年5月29日のキオクシア")
    assert not strong_anchor_terms_for_query("2026.05.29のキオクシア")
    assert "1755992165371789312" in strong_anchor_terms_for_query(
        "tweet 1755992165371789312 を出して"
    )
    assert "ZZZ_NO_SUCH_TOPIC_6f3a" in strong_anchor_terms_for_query(
        "保存したはずのZZZ_NO_SUCH_TOPIC_6f3aを出して"
    )
    current_plan = build_query_plan("昔保存した技術情報が今も正しいか確認したい")
    assert "freshness" in current_plan.intents
    assert current_plan.prefers_recent is True
    author_plan = build_query_plan("Aさんの過去発言から2026年のAIの展望について教えて")
    assert author_plan.doc_type_weights["author_profile"] > author_plan.doc_type_weights.get(
        "topic_thread",
        0.0,
    )


def test_memory_retrieval_text_profiles_are_search_only_projection(tmp_path: Path) -> None:
    db_path = tmp_path / "x.sqlite3"
    _seed_db(db_path)
    build_memory_corpus(db_path)
    build_memory_relations(db_path)
    build_retrieval_text_profiles(db_path)

    summary = build_retrieval_text_profiles(db_path)
    coverage = retrieval_text_coverage(db_path)
    projection_results = search_memory_retrieval_text_only(db_path, "type", limit=5)
    hybrid_results = search_memory(db_path, "type", limit=5)
    report = audit_memory_db(db_path)

    assert summary.documents == 5
    assert summary.profile_rows == 10
    assert coverage.profile_rows == 10
    assert coverage.fts_rows == 10
    assert coverage.citation_included_rows == 0
    assert coverage.orphaned_fts_rows == 0
    assert coverage.profiles_missing_fts_rows == 0
    assert not coverage.missing_by_profile
    assert projection_results
    assert any(
        contribution["engine"] == "retrieval_text"
        for result in projection_results
        for contribution in result.metadata["engine_contributions"]
    )
    assert any(
        contribution["engine"] == "retrieval_text"
        for result in hybrid_results
        for contribution in result.metadata["engine_contributions"]
    )
    assert "no_spend_gap" not in report.strategy_gap_counts


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
    assert hit["metadata"]["engine_contributions"]
    assert hit["evidence"]["url"] == "https://x.com/a/status/tweet-1"
    assert hit["evidence"]["quoted_tweets"][0]["tweet_id"] == "tweet-2"
    assert hit["evidence"]["quoted_tweets"][0]["child_also_bookmarked"] is False
    assert hit["evidence"]["media"][0]["media_id"] == "media-1"
    assert hit["evidence"]["media"][0]["url"] == "https://example.test/image.jpg"


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
    advisory_bundle = export_corpus2skill_bundle(
        db_path,
        tmp_path / "c2s_advisory",
        include_openai_agent=True,
        include_hook_advisory=True,
    )
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
    advisory_manifest = json.loads(
        Path(advisory_bundle.manifest_path).read_text(encoding="utf-8")
    )
    filtered_manifest = json.loads(
        Path(filtered_bundle.manifest_path).read_text(encoding="utf-8")
    )
    assert bundle.documents == 5
    assert bundle.openai_agent_path is None
    assert bundle.hook_advisory_path is None
    assert not (Path(bundle.out_dir) / "agents").exists()
    assert bundle_rows[0]["metadata"]["research_x_metadata"]
    assert manifest["format"] == "corpus2skill-jsonl-bundle-v1"
    assert manifest["compile_hint"][:3] == ["uv", "run", "python"]
    assert manifest["agent_advisory"]["openai_agent_path"] is None
    assert advisory_bundle.openai_agent_path
    assert advisory_bundle.hook_advisory_path
    openai_agent_text = Path(advisory_bundle.openai_agent_path).read_text(encoding="utf-8")
    hook_advisory_text = Path(advisory_bundle.hook_advisory_path).read_text(
        encoding="utf-8"
    )
    assert "allow_implicit_invocation: false" in openai_agent_text
    assert "skill_name: \"research-x-memory-navigation\"" in openai_agent_text
    assert "navigation_hint_only_not_citation_evidence" in openai_agent_text
    assert "api_key" not in openai_agent_text.lower()
    assert "This file is inert" in hook_advisory_text
    assert "does not install a hook" in hook_advisory_text
    assert not (Path(advisory_bundle.out_dir) / "hooks.json").exists()
    assert not (Path(advisory_bundle.out_dir) / "hooks").exists()
    assert advisory_manifest["agent_advisory"]["provider_quota"] == "no_provider_calls"
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


def test_source_backed_governance_record_is_stored_and_listed(tmp_path: Path) -> None:
    db_path = tmp_path / "x.sqlite3"
    _seed_db(db_path)
    build_memory_corpus(db_path)

    record = add_governance_record(
        db_path,
        governance_type="profile",
        subject_kind="topic",
        subject_id="reinforcement-learning",
        statement="User repeatedly saves reinforcement-learning robot examples.",
        source_kind="memory_document",
        source_id="bookmark:acct:tweet-1",
        source_url="https://x.com/a/status/tweet-1",
        source_hash="hash-1",
        source_anchor={"doc_id": "bookmark:acct:tweet-1"},
        confidence=0.8,
        retention_policy="source_lifetime",
    )
    records = list_governance_records(
        db_path,
        governance_type="profile",
        subject_kind="topic",
        subject_id="reinforcement-learning",
    )

    assert records == (record,)
    assert records[0].metadata["citation_excluded"] is True
    assert records[0].source_anchor["source_backed"] is True
    assert records[0].source_anchor["restore_required_before_answer_use"] is True


def test_source_backed_governance_records_cover_non_tombstone_types(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "x.sqlite3"
    _seed_db(db_path)
    build_memory_corpus(db_path)

    records = [
        add_governance_record(
            db_path,
            governance_type="contradiction",
            subject_kind="memory_document",
            subject_id="bookmark:acct:tweet-1",
            statement="Newer source may contradict this saved post.",
            source_kind="memory_document",
            source_id="tweet:tweet-2",
            source_anchor={"doc_id": "tweet:tweet-2"},
            confidence=0.7,
        ),
        add_governance_record(
            db_path,
            governance_type="retention",
            subject_kind="memory_document",
            subject_id="bookmark:acct:tweet-1",
            statement="Keep while source tweet remains in the local project corpus.",
            source_kind="memory_document",
            source_id="bookmark:acct:tweet-1",
            source_anchor={"doc_id": "bookmark:acct:tweet-1"},
            retention_policy="source_lifetime",
        ),
        add_governance_record(
            db_path,
            governance_type="forgetting",
            subject_kind="memory_document",
            subject_id="bookmark:acct:tweet-1",
            statement="User asked to review this local memory for possible suppression.",
            source_kind="manual",
            source_id="forget-review",
            source_anchor={"request_id": "forget-review"},
        ),
    ]

    listed = list_governance_records(
        db_path,
        subject_kind="memory_document",
        subject_id="bookmark:acct:tweet-1",
        limit=10,
    )

    assert {record.governance_type for record in listed} >= {
        "contradiction",
        "retention",
        "forgetting",
    }
    assert {record.record_id for record in records}.issubset(
        {record.record_id for record in listed}
    )


def test_governance_requires_source_backing(tmp_path: Path) -> None:
    db_path = tmp_path / "x.sqlite3"
    _seed_db(db_path)
    build_memory_corpus(db_path)

    with pytest.raises(ValueError, match="source_id is required"):
        add_governance_record(
            db_path,
            governance_type="profile",
            subject_kind="topic",
            subject_id="missing-source",
            statement="invalid",
            source_kind="memory_document",
            source_id="",
        )


def test_governance_tombstone_suppresses_search_without_deleting_source(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "x.sqlite3"
    _seed_db(db_path)
    build_memory_corpus(db_path)

    before = search_memory(db_path, "強化学習 ロボット", limit=5)
    target_doc_id = before[0].doc_id
    tombstone = add_tombstone(
        db_path,
        artifact_kind="memory_document",
        artifact_id=target_doc_id,
        reason="user requested suppression for this local memory artifact",
        source_kind="manual",
        source_id="test-request",
        source_anchor={"test": "tombstone"},
    )
    after = search_memory(db_path, "強化学習 ロボット", limit=5)

    assert is_artifact_tombstoned(
        db_path,
        artifact_kind="memory_document",
        artifact_id=target_doc_id,
    )
    assert target_doc_id not in {result.doc_id for result in after}
    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            "SELECT doc_id FROM memory_documents WHERE doc_id = ?",
            (target_doc_id,),
        ).fetchone()
    assert row is not None

    restored = restore_governance_record(
        db_path,
        record_id=tombstone.record_id,
        reason="test restore",
    )
    restored_results = search_memory(db_path, "強化学習 ロボット", limit=5)

    assert restored.status == "restored"
    assert target_doc_id in {result.doc_id for result in restored_results}


def test_governance_tweet_tombstone_suppresses_source_tweet_candidates(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "x.sqlite3"
    _seed_db(db_path)
    build_memory_corpus(db_path)

    before = search_memory(db_path, "強化学習 ロボット", limit=10)
    assert "tweet-1" in {result.source_tweet_id for result in before}

    add_tombstone(
        db_path,
        artifact_kind="tweet",
        artifact_id="tweet-1",
        reason="suppress all local memory artifacts sourced from tweet-1",
        source_kind="manual",
        source_id="tweet-suppression-test",
        source_anchor={"tweet_id": "tweet-1"},
    )
    after = search_memory(db_path, "強化学習 ロボット", limit=10)

    assert "tweet-1" not in {result.source_tweet_id for result in after}


def test_expired_governance_tombstone_does_not_suppress_search(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "x.sqlite3"
    _seed_db(db_path)
    build_memory_corpus(db_path)

    before = search_memory(db_path, "強化学習 ロボット", limit=5)
    target_doc_id = before[0].doc_id
    add_governance_record(
        db_path,
        governance_type="tombstone",
        subject_kind="artifact:memory_document",
        subject_id=target_doc_id,
        statement="expired suppression should not affect current search",
        source_kind="manual",
        source_id="expired-test",
        source_anchor={"doc_id": target_doc_id},
        expires_at="2000-01-01T00:00:00Z",
    )

    after = search_memory(db_path, "強化学習 ロボット", limit=5)

    assert target_doc_id in {result.doc_id for result in after}


def test_memory_governance_cli_round_trip(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    db_path = tmp_path / "x.sqlite3"
    _seed_db(db_path)
    build_memory_corpus(db_path)

    exit_code = main(
        [
            "memory",
            "governance",
            "tombstone",
            "--db",
            str(db_path),
            "--artifact-kind",
            "memory_document",
            "--artifact-id",
            "bookmark:acct:tweet-1",
            "--reason",
            "cli suppression",
            "--source-kind",
            "manual",
            "--source-id",
            "cli-test",
            "--source-anchor",
            "doc_id=bookmark:acct:tweet-1",
            "--json",
        ]
    )
    created = json.loads(capsys.readouterr().out)
    list_code = main(
        [
            "memory",
            "governance",
            "list",
            "--db",
            str(db_path),
            "--type",
            "tombstone",
            "--json",
        ]
    )
    listed = json.loads(capsys.readouterr().out)
    check_code = main(
        [
            "memory",
            "governance",
            "check",
            "--db",
            str(db_path),
            "--artifact-kind",
            "memory_document",
            "--artifact-id",
            "bookmark:acct:tweet-1",
            "--json",
        ]
    )
    checked = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert list_code == 0
    assert check_code == 0
    assert created["governance_type"] == "tombstone"
    assert listed[0]["record_id"] == created["record_id"]
    assert checked["tombstoned"] is True


def test_memory_governance_cli_restore_is_visible_with_include_inactive(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    db_path = tmp_path / "x.sqlite3"
    _seed_db(db_path)
    build_memory_corpus(db_path)

    assert (
        main(
            [
                "memory",
                "governance",
                "tombstone",
                "--db",
                str(db_path),
                "--artifact-kind",
                "memory_document",
                "--artifact-id",
                "bookmark:acct:tweet-1",
                "--reason",
                "temporary cli suppression",
                "--source-kind",
                "manual",
                "--source-id",
                "cli-restore-test",
                "--json",
            ]
        )
        == 0
    )
    created = json.loads(capsys.readouterr().out)

    assert (
        main(
            [
                "memory",
                "governance",
                "restore",
                "--db",
                str(db_path),
                "--record-id",
                created["record_id"],
                "--reason",
                "restore for test",
                "--json",
            ]
        )
        == 0
    )
    restored = json.loads(capsys.readouterr().out)

    assert (
        main(
            [
                "memory",
                "governance",
                "list",
                "--db",
                str(db_path),
                "--include-inactive",
                "--json",
            ]
        )
        == 0
    )
    listed = json.loads(capsys.readouterr().out)

    assert restored["status"] == "restored"
    assert {
        (record["record_id"], record["status"]) for record in listed
    } >= {(created["record_id"], "restored")}


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
    assert any(result.score_components["rrf"] > 0 for result in results)
    assert any(
        result.metadata["semantic"]["embedding_profile"] == "general_memory"
        for result in results
        if "semantic" in result.metadata
    )
    assert any(
        contribution["engine"] in {"semantic", "semantic_rerank"}
        for result in results
        for contribution in result.metadata["engine_contributions"]
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


def test_memory_vector_projection_backend_searches_existing_embeddings(tmp_path: Path) -> None:
    db_path = tmp_path / "x.sqlite3"
    _seed_db(db_path)
    build_memory_corpus(db_path)
    build_memory_embeddings(db_path, provider="local_hash", dimensions=64)

    summary = build_vector_projection(
        db_path,
        provider="local_hash",
        dimensions=64,
        backend="numpy",
        out_dir=tmp_path / "vector-indexes",
    )
    coverage = vector_projection_coverage(
        db_path,
        provider="local_hash",
        dimensions=64,
        backend="numpy",
    )
    results = search_memory(
        db_path,
        "robot paper",
        limit=3,
        semantic_provider="local_hash",
        semantic_dimensions=64,
        semantic_backend="projection",
    )

    assert summary.backend == "numpy"
    assert summary.documents == 5
    assert Path(summary.index_path).exists()
    assert Path(summary.mapping_path).exists()
    assert coverage.status == "ok"
    assert coverage.current_memberships == 5
    assert results
    assert any(result.score_components["semantic"] > 0 for result in results)
    assert any(
        contribution["engine"] in {"semantic", "semantic_rerank"}
        for result in results
        for contribution in result.metadata["engine_contributions"]
    )


def test_memory_vector_backend_benchmark_gates_candidate_dependency(tmp_path: Path) -> None:
    db_path = tmp_path / "x.sqlite3"
    _seed_db(db_path)
    build_memory_corpus(db_path)
    build_memory_embeddings(db_path, provider="local_hash", dimensions=64)

    report = benchmark_vector_backends(
        db_path,
        provider="local_hash",
        dimensions=64,
        backends=("numpy", "zvec"),
        queries=("robot paper",),
        limit=3,
        out_dir=tmp_path / "vector-benchmark",
    )
    results = {result.backend: result for result in report.results}
    payload = json.loads(benchmark_json(report))

    assert report.status == "needs_review"
    assert results["numpy"].status == "ok"
    assert results["numpy"].documents == 5
    assert results["numpy"].recall_at_limit == 1.0
    assert results["numpy"].source_restoration_ok is True
    assert results["numpy"].memory_bytes_per_vector == 256
    assert Path(results["numpy"].index_path or "").exists()
    assert Path(results["numpy"].mapping_path or "").exists()
    assert results["zvec"].status == "dependency_review_required"
    assert results["zvec"].index_path is None
    assert results["zvec"].notes == ("backend is candidate-only; no import/install attempted",)
    assert payload["metadata"]["dependency_gate"]


def test_memory_vector_backend_benchmark_blocks_non_local_provider(tmp_path: Path) -> None:
    report = benchmark_vector_backends(
        tmp_path / "missing.sqlite3",
        provider="openai",
        dimensions=1536,
        backends=("numpy", "zvec"),
        queries=("robot paper",),
        out_dir=tmp_path / "should-not-exist",
    )
    results = {result.backend: result for result in report.results}

    assert report.status == "needs_review"
    assert results["numpy"].status == "provider_gated"
    assert results["numpy"].notes == ("non-local query embeddings require provider gate approval",)
    assert results["zvec"].status == "provider_gated"
    assert not (tmp_path / "should-not-exist").exists()


def test_memory_vector_backend_benchmark_cli_reports_candidate_gate(
    tmp_path: Path,
    capsys,
) -> None:
    db_path = tmp_path / "x.sqlite3"
    _seed_db(db_path)
    build_memory_corpus(db_path)
    build_memory_embeddings(db_path, provider="local_hash", dimensions=64)

    assert (
        main(
            [
                "memory",
                "vector-backend-benchmark",
                "--db",
                str(db_path),
                "--provider",
                "local_hash",
                "--dimensions",
                "64",
                "--backend",
                "numpy",
                "--backend",
                "zvec",
                "--query",
                "robot paper",
                "--limit",
                "3",
                "--out-dir",
                str(tmp_path / "vector-benchmark-cli"),
                "--json",
            ]
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)
    results = {result["backend"]: result for result in payload["results"]}

    assert payload["status"] == "needs_review"
    assert results["numpy"]["status"] == "ok"
    assert results["zvec"]["status"] == "dependency_review_required"


def test_memory_vector_projection_coverage_detects_stale_source_hash(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "x.sqlite3"
    _seed_db(db_path)
    build_memory_corpus(db_path)
    build_memory_embeddings(db_path, provider="local_hash", dimensions=64)
    build_vector_projection(
        db_path,
        provider="local_hash",
        dimensions=64,
        backend="numpy",
        out_dir=tmp_path / "vector-indexes",
    )

    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            UPDATE memory_documents
            SET source_doc_hash = 'changed-source-hash'
            WHERE doc_id = (
                SELECT doc_id
                FROM memory_documents
                ORDER BY doc_id
                LIMIT 1
            )
            """
        )

    coverage = vector_projection_coverage(
        db_path,
        provider="local_hash",
        dimensions=64,
        backend="numpy",
    )

    assert coverage.status == "stale"
    assert coverage.stale_memberships == 1


def test_memory_vector_projection_coverage_respects_doc_type_scope(tmp_path: Path) -> None:
    db_path = tmp_path / "x.sqlite3"
    _seed_db(db_path)
    build_memory_corpus(db_path)
    build_memory_embeddings(db_path, provider="local_hash", dimensions=64)

    summary = build_vector_projection(
        db_path,
        provider="local_hash",
        dimensions=64,
        backend="numpy",
        doc_type="tweet_doc",
        out_dir=tmp_path / "vector-indexes",
    )
    coverage = vector_projection_coverage(
        db_path,
        provider="local_hash",
        dimensions=64,
        backend="numpy",
    )

    assert summary.documents == 2
    assert coverage.status == "ok"
    assert coverage.expected_documents == 2
    assert coverage.current_memberships == 2
    assert coverage.missing_memberships == 0


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
        model="gemini-embedding-001",
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
    assert estimate.execution_stage == "production_scope"
    assert estimate.selection_policy == "sequential"


def test_memory_embedding_limited_estimates_are_not_production_scope(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "x.sqlite3"
    _seed_db(db_path)
    build_memory_corpus(db_path)

    canary = estimate_memory_embedding_build(
        db_path,
        provider="gemini",
        dimensions=768,
        limit=1,
    )
    eval_slice = estimate_memory_embedding_build(
        db_path,
        provider="gemini",
        dimensions=768,
        limit=3,
        execution_stage="eval-slice",
    )

    assert canary.execution_stage == "technical_canary"
    assert canary.selection_policy == "sequential"
    assert "not a production index" in canary.selection_contract
    assert eval_slice.execution_stage == "eval_slice"
    assert eval_slice.selection_policy == "doc_type_round_robin"
    assert "full selected-scope coverage" in eval_slice.selection_contract
    with pytest.raises(ValueError, match="production_scope embedding builds must not use --limit"):
        estimate_memory_embedding_build(
            db_path,
            provider="gemini",
            dimensions=768,
            limit=1,
            execution_stage="production-scope",
        )


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


def test_memory_semantic_explicit_provider_uses_available_dimensions(tmp_path: Path) -> None:
    db_path = tmp_path / "x.sqlite3"
    _seed_db(db_path)
    build_memory_corpus(db_path)
    build_memory_embeddings(db_path, provider="local_hash", dimensions=64)

    results = search_memory(db_path, "robot paper", limit=3, semantic_provider="local_hash")

    assert results
    semantic_meta = [
        result.metadata.get("semantic")
        for result in results
        if result.metadata.get("semantic")
    ]
    assert semantic_meta
    assert {row["dimensions"] for row in semantic_meta} == {64}


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


def test_memory_portfolio_eval_fuses_multiple_semantic_arms(tmp_path: Path) -> None:
    db_path = tmp_path / "x.sqlite3"
    _seed_db(db_path)
    build_memory_corpus(db_path)
    build_memory_relations(db_path)
    build_retrieval_text_profiles(db_path)
    build_memory_embeddings(db_path, provider="local_hash", dimensions=64)
    build_memory_embeddings(
        db_path,
        provider="local_hash",
        dimensions=32,
        embedding_profile="alt_memory",
    )

    case = load_eval_cases(
        _write_cases(
            tmp_path,
            [
                {
                    "query": "robot paper",
                    "required_any_terms": ["ロボット", "robot"],
                    "question_type": "multi_hop_evidence",
                    "preferred_doc_types": ["bookmark_doc", "quote_tree_doc"],
                }
            ],
        )
    )[0]
    report = run_portfolio_eval(
        db_path,
        cases=(case,),
        semantic_specs=(
            parse_portfolio_semantic_spec(
                "provider=local_hash,dimensions=64,name=hash64"
            ),
            parse_portfolio_semantic_spec(
                "provider=local_hash,dimensions=32,profile=alt_memory,name=hash32"
            ),
        ),
        limit=3,
        arm_limit=5,
    )
    result = report.cases[0]

    assert result.status == "needs_review"
    assert any("denoising gate" in note for note in result.notes)
    assert {
        "fts_only",
        "exact_anchor",
        "retrieval_text",
        "relation_expansion",
        "corpus2skill_navigation",
        "source_bundle_context",
        "workflow_route",
        "local_hybrid",
        "hash64",
        "hash32",
    }.issubset({arm.name for arm in result.arms})
    assert {
        "fts_only",
        "exact_anchor",
        "retrieval_text",
        "relation_expansion",
        "navigation_map",
        "source_bundle_context",
        "bounded_workflow",
    }.issubset({arm.mode for arm in result.arms})
    assert "semantic_only" in {arm.mode for arm in result.arms}
    assert {arm.name: arm.case_status for arm in result.arms}["local_hybrid"] == "ok"
    assert {
        "fts_only",
        "exact_anchor",
        "retrieval_text",
        "relation_expansion",
        "corpus2skill_navigation",
        "source_bundle_context",
        "workflow_route",
        "local_hybrid",
        "hash64",
        "hash32",
    }.issubset({summary.name for summary in report.arm_summaries})
    assert report.verdict.status == "hold"
    assert not report.verdict.promotable
    assert any("diagnostic embedding providers" in blocker for blocker in report.verdict.blockers)
    assert any("does not beat" in blocker for blocker in report.verdict.blockers)
    assert result.fused_hits
    assert result.fused_hits[0].bundle_key.startswith("tweet:")
    contribution_arms = {
        contribution["arm"]
        for hit in result.fused_hits
        for contribution in hit.contributions
    }
    assert {
        "lexical_exploration",
        "local_hybrid",
        "source_bundle_context",
        "hash64",
        "hash32",
    }.issubset(contribution_arms)
    assert result.denoising.candidate_count >= result.denoising.unique_candidate_count
    assert result.denoising.unique_candidate_count >= result.denoising.fused_count
    assert report.denoising_summary.candidate_count >= result.denoising.candidate_count


def test_memory_portfolio_eval_case_limit_limits_default_cases(tmp_path: Path) -> None:
    db_path = tmp_path / "x.sqlite3"
    _seed_db(db_path)
    build_memory_corpus(db_path)
    build_memory_relations(db_path)

    report = run_portfolio_eval(db_path, case_limit=1, fast=True, limit=1, arm_limit=2)

    assert len(report.cases) == 1
    assert report.cases[0].query == DEFAULT_EVAL_CASES[0].query
    assert report.parameters["case_limit"] == 1
    assert report.parameters["fast"] is True
    assert [arm.name for arm in report.cases[0].arms] == [
        "fts_only",
        "retrieval_text",
        "local_hybrid",
    ]


def test_memory_portfolio_eval_tracks_lexical_exploration_denoising(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "x.sqlite3"
    _seed_db(db_path)
    build_memory_corpus(db_path)
    build_memory_relations(db_path)

    report = run_portfolio_eval(
        db_path,
        cases=(DEFAULT_EVAL_CASES[0],),
        limit=2,
        arm_limit=4,
    )
    result = report.cases[0]
    arm_by_name = {arm.name: arm for arm in result.arms}
    payload = json.loads(memory_portfolio.portfolio_eval_json(report))
    plain = memory_portfolio.format_portfolio_eval(report)

    assert arm_by_name["lexical_exploration"].mode == "lexical_exploration"
    assert arm_by_name["lexical_exploration"].status == "ok"
    assert result.denoising.candidate_count >= result.denoising.unique_candidate_count
    assert result.denoising.unique_candidate_count >= result.denoising.fused_count
    assert result.denoising.source_restorable_count >= result.denoising.citation_ready_count
    assert report.denoising_summary.candidate_count == result.denoising.candidate_count
    assert payload["denoising_summary"]["candidate_count"] == result.denoising.candidate_count
    assert "denoising:" in plain
    assert "denoise=" in plain


def test_memory_portfolio_semantic_spec_rejects_unknown_fields() -> None:
    try:
        parse_portfolio_semantic_spec("provider=local_hash,dimensions=64,bad=value")
    except ValueError as exc:
        assert "unknown portfolio semantic spec field" in str(exc)
    else:
        raise AssertionError("portfolio semantic spec should reject unknown fields")


def test_memory_portfolio_semantic_spec_accepts_arm_modes() -> None:
    semantic_only = parse_portfolio_semantic_spec("provider=local_hash,dimensions=64")
    hybrid = parse_portfolio_semantic_spec(
        "provider=local_hash,dimensions=64,mode=hybrid"
    )

    assert semantic_only.mode == "semantic_only"
    assert hybrid.mode == "hybrid"


def test_memory_portfolio_semantic_spec_normalizes_provider() -> None:
    spec = parse_portfolio_semantic_spec("provider=LOCAL-HASH,dimensions=64")

    assert spec.provider == "local_hash"


def test_memory_retrieval_strategies_auto_keeps_semantic_challengers_explicit() -> None:
    strategies = retrieval_strategies_as_dicts(
        query="日本語で聞くけど保存した英語論文や公式docsから強化学習の資料を出して"
    )
    ids = {strategy["strategy_id"] for strategy in strategies}
    baseline = next(
        strategy
        for strategy in strategies
        if strategy["strategy_id"] == "baseline_hybrid_foundation"
    )
    baseline_candidates = {candidate["name"] for candidate in baseline["candidates"]}
    specs = semantic_spec_strings_for_strategies(
        ("jp_multilingual", "learning_long", "code_technical")
    )
    portfolio_specs = semantic_spec_strings_for_strategies(("api_embedding_portfolio",))

    assert "baseline_hybrid_foundation" in ids
    assert "lexical_exploration" in ids
    assert "general_memory" not in ids
    assert "corpus2skill_navigation" in ids
    assert "bounded_workflow_orchestration" in ids
    assert "jp_multilingual" not in ids
    assert "learning_long" not in ids
    assert "code_technical" not in ids
    assert "media_text_bridge" not in ids
    assert "contextual_bm25" in ids
    assert "relation_engine" in baseline_candidates
    lexical = next(
        strategy for strategy in strategies if strategy["strategy_id"] == "lexical_exploration"
    )
    lexical_candidates = {candidate["name"]: candidate for candidate in lexical["candidates"]}
    assert lexical["adoption"] == "always_on_baseline"
    assert lexical_candidates["lexical_exploration"]["route_role"] == "candidate_exploration"
    assert any("model=voyage-4" in spec for spec in specs)
    assert any("profile=jp_multilingual" in spec for spec in specs)
    assert any("profile=learning_long" in spec for spec in specs)
    assert any("provider=mistral" in spec for spec in specs)
    assert any("provider=gemini" in spec for spec in portfolio_specs)
    assert any("provider=openai" in spec for spec in portfolio_specs)
    assert any("provider=voyage" in spec for spec in portfolio_specs)
    assert any("provider=jina" in spec for spec in portfolio_specs)
    assert any("provider=cohere" in spec for spec in portfolio_specs)
    assert any(
        "provider=mistral" in spec and "model=codestral-embed-2505" in spec
        for spec in portfolio_specs
    )
    assert any("model=jina-embeddings-v5-omni-small" in spec for spec in portfolio_specs)
    assert all("provider=local_hash" not in spec for spec in portfolio_specs)


def test_memory_retrieval_strategies_keep_general_memory_explicit() -> None:
    strategies = retrieval_strategies_as_dicts(strategy_ids=("general_memory",))
    specs = semantic_spec_strings_for_strategies(("general_memory",))

    assert [strategy["strategy_id"] for strategy in strategies] == ["general_memory"]
    assert any("provider=gemini" in spec for spec in specs)
    assert any("provider=openai" in spec for spec in specs)
    assert all("provider=local_hash" not in spec for spec in specs)


def test_memory_retrieval_strategy_semantic_specs_are_deduped() -> None:
    specs = semantic_spec_strings_for_strategies(
        ("api_embedding_portfolio", "jp_multilingual", "learning_long")
    )

    assert len(specs) == len(set(specs))


def test_memory_retrieval_strategy_reranker_specs_are_explicit() -> None:
    strategies = retrieval_strategies_as_dicts(strategy_ids=("rerank_stage",))
    candidates = {candidate["name"]: candidate for candidate in strategies[0]["candidates"]}
    specs = reranker_spec_strings_for_strategies(("rerank_stage",))

    assert "voyage_rerank_2_5" in candidates
    assert candidates["cohere_rerank_v4_0_pro"]["model"] == "rerank-v4.0-pro"
    assert candidates["cohere_rerank_v4_0_fast"]["model"] == "rerank-v4.0-fast"
    assert candidates["jina_reranker_v3"]["model"] == "jina-reranker-v3"
    assert any("provider=voyage" in spec and "model=rerank-2.5" in spec for spec in specs)
    assert any("provider=cohere" in spec and "model=rerank-v4.0-pro" in spec for spec in specs)
    assert any("provider=jina" in spec and "model=jina-reranker-v3" in spec for spec in specs)


def test_memory_retrieval_strategies_keep_native_media_deferred() -> None:
    strategies = retrieval_strategies_as_dicts(strategy_ids=("media_text_bridge",))
    media = strategies[0]
    candidates = {candidate["name"]: candidate for candidate in media["candidates"]}
    specs = semantic_spec_strings_for_strategies(("media_text_bridge",))

    assert candidates["gemini_embedding_2_native_media"]["portfolio_eligible"] is False
    assert (
        candidates["gemini_embedding_2_native_media"]["status"]
        == "requires_explicit_eval"
    )
    assert candidates["gemini_embedding_2_native_media"]["candidate_kind"] == "media_embedding"
    assert candidates["vertex_multimodal_embedding_001"]["provider"] == "vertex_ai"
    assert candidates["jina_v5_omni_media_text"]["portfolio_eligible"] is True
    assert candidates["mistral_ocr_2512"]["model"] == "mistral-ocr-2512"
    assert candidates["mistral_ocr_latest"]["candidate_kind"] == "ocr"
    assert any("provider=cohere" in spec for spec in specs)
    assert any("model=jina-embeddings-v5-omni-small" in spec for spec in specs)
    assert all("native_multimodal_media" not in spec for spec in specs)


def test_memory_retrieval_strategy_exposes_context4_and_managed_reference() -> None:
    learning = retrieval_strategies_as_dicts(strategy_ids=("learning_long",))[0]
    learning_candidates = {candidate["name"]: candidate for candidate in learning["candidates"]}
    managed = retrieval_strategies_as_dicts(strategy_ids=("managed_rag_reference",))[0]
    managed_candidates = {candidate["name"]: candidate for candidate in managed["candidates"]}

    assert learning_candidates["voyage_context_4_learning"]["model"] == "voyage-context-4"
    assert "voyage_context_3_learning" not in learning_candidates
    assert managed["adoption"] == "eval_only_explicit"
    assert managed_candidates["openai_file_search_vector_stores"]["status"] == "reference_only"
    assert managed_candidates["gemini_file_search_embedding_2"]["provider"] == "gemini"


def test_memory_native_multimodal_media_strategy_is_explicit_only() -> None:
    automatic = retrieval_strategies_as_dicts(query="保存した画像付き投稿を探して")
    explicit = retrieval_strategies_as_dicts(strategy_ids=("native_multimodal_media",))
    candidates = {candidate["name"]: candidate for candidate in explicit[0]["candidates"]}

    assert "native_multimodal_media" not in {
        strategy["strategy_id"] for strategy in automatic
    }
    assert explicit[0]["adoption"] == "requires_explicit_eval"
    assert candidates["gemini_embedding_2_native_media"]["candidate_kind"] == "media_embedding"
    assert candidates["gemini_embedding_2_native_media"]["model"] == "gemini-embedding-2"


def test_memory_media_embedding_schema_estimate_build_and_search(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "x.sqlite3"
    media_path = tmp_path / "image.jpg"
    media_path.write_bytes(b"fake-image")
    _seed_db(db_path)
    build_memory_corpus(db_path)
    build_memory_relations(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        ensure_memory_schema(conn)
        conn.execute(
            "UPDATE media SET local_path = ? WHERE media_id = ?",
            (str(media_path), "media-1"),
        )
        assert (
            conn.execute(
                "SELECT COUNT(*) FROM sqlite_master WHERE name = 'memory_media_embeddings'"
            ).fetchone()[0]
            == 1
        )

    estimate = estimate_media_embedding_build(
        db_path,
        provider=FIXTURE_MEDIA_PROVIDER,
        dimensions=3,
    )
    summary = build_media_embeddings(
        db_path,
        provider=FIXTURE_MEDIA_PROVIDER,
        dimensions=3,
        limit=1,
    )
    coverage = media_embedding_coverage_report(
        db_path,
        provider=FIXTURE_MEDIA_PROVIDER,
        dimensions=3,
    )
    hits = search_media_embeddings(
        db_path,
        "robot image",
        provider=FIXTURE_MEDIA_PROVIDER,
        dimensions=3,
        limit=1,
    )

    assert estimate.media == 1
    assert estimate.selected == 1
    assert estimate.skipped == 0
    assert summary.embedded == 1
    assert coverage.current == 1
    assert hits[0].media_id == "media-1"
    assert hits[0].evidence_status == "unconfirmed_media_match"
    assert hits[0].bundle["doc_id"] == "media:media-1"
    assert hits[0].bundle["tweet_id"] == "tweet-1"
    assert hits[0].bundle["media_content_evidence"] is False
    assert any(
        relation["relation_type"] == "has_media"
        for relation in hits[0].bundle["relations"]
    )

    media_path.write_bytes(b"changed-image")
    stale = media_embedding_coverage_report(
        db_path,
        provider=FIXTURE_MEDIA_PROVIDER,
        dimensions=3,
    )
    assert stale.stale_file == 1


def test_memory_objective_routes_include_primary_fallback_and_ocr_escalation() -> None:
    plan = plan_objective_routes("画像の図表にあったネットワーク資料っぽい投稿を出して")

    assert plan.primary_route == "media_evidence"
    assert "exact_metadata_social" in plan.fallback_routes
    assert "semantic_embedding_portfolio" in plan.fallback_routes
    assert "ocr_quality_pipeline" in plan.escalation_triggers
    assert "no_unsupported_media_content_claims" in plan.must_run_guards
    assert "ocr" in plan.planned_provider_roles
    assert plan.workflow_route.route == "media_context"
    assert plan.as_dict()["primary_route"] == "media_evidence"
    payload = plan.as_dict()
    assert payload["research_task_frame"]["local_x_db_primary"] is True
    assert payload["research_task_frame"]["evidence_policy"][
        "snippet_rank_ai_summary_are_evidence"
    ] is False
    assert payload["search_plan_graph"]["contract"] == (
        "plan_graph_controls_search_but_is_not_evidence"
    )
    providers = {
        row["provider"]: row
        for row in payload["provider_capability_matrix"]["rows"]
    }
    assert providers["serper"]["provider_role"] == "index_provider"
    assert providers["serper"]["evidence_policy"] == "not_evidence_until_fetched_and_chunked"
    assert providers["subagent_or_deep_research_notes"]["evidence_policy"] == (
        "citation_excluded_until_source_recovered"
    )


def test_memory_objective_execute_records_no_spend_media_trace(tmp_path: Path) -> None:
    db_path = tmp_path / "x.sqlite3"
    _seed_db(db_path)
    build_memory_corpus(db_path)
    build_memory_relations(db_path)

    execution = run_objective_route_execution(
        db_path,
        "画像 robot image",
        limit=2,
        max_route_arms=4,
    )

    assert execution.plan.primary_route == "media_evidence"
    assert execution.selected_routes == ("media_evidence",)
    assert execution.arm_results[0].route_arm == "media_evidence"
    assert execution.arm_results[0].provider_quota_skipped is False
    assert execution.arm_results[0].output["ocr_estimate"]["sample_policy"] == "candidate_set"
    assert execution.metadata["provider_quota_frozen"] is True
    coverage = execution.metadata["result_coverage_map"]
    assert coverage["candidate_total"] >= 1
    assert coverage["evidence_total"] >= 1
    assert "citation_ready_yield" in coverage
    assert "unsupported_context_total" in coverage
    assert coverage["route_rows"][0]["candidate_count"] >= 1
    assert "citation_ready_yield" in coverage["route_rows"][0]
    assert execution.metadata["claim_support_check"]["deterministic_checks"][
        "snippet_or_rank_used_as_evidence"
    ] is False
    assert "unsupported_context_absent" in execution.metadata["claim_support_check"][
        "deterministic_checks"
    ]
    assert execution.metadata["research_brief"]["candidate_total"] >= 1
    assert execution.metadata["search_episode_trace"]["contract"] == (
        "episode_trace_explains_execution_but_is_not_source_evidence"
    )
    assert execution.metadata["serp_flattening_audit"]["checks"][
        "snippet_used_as_evidence"
    ] is False
    assert execution.metadata["research_brief"]["citation_policy"] == "brief_is_not_evidence"
    assert any(
        gap["gap_id"] == "media_content_evidence_missing"
        for gap in execution.metadata["evidence_gap"]["gaps"]
    )
    with sqlite3.connect(db_path) as conn:
        route_rows = conn.execute(
            "SELECT COUNT(*) FROM memory_objective_route_runs WHERE route_run_id = ?",
            (execution.route_run_id,),
        ).fetchone()[0]
        step_rows = conn.execute(
            "SELECT COUNT(*) FROM memory_objective_route_steps WHERE route_run_id = ?",
            (execution.route_run_id,),
        ).fetchone()[0]
    assert route_rows == 1
    assert step_rows == 1


def test_memory_research_run_observability_surfaces_objective_artifacts(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "x.sqlite3"
    _seed_db(db_path)
    build_memory_corpus(db_path)
    build_memory_relations(db_path)

    execution = run_objective_route_execution(
        db_path,
        "画像 robot image",
        limit=2,
        max_route_arms=4,
    )
    runs = list_research_runs(db_path, run_kind="objective", limit=5)
    detail = show_research_run(db_path, execution.route_run_id, run_kind="objective")
    plain_execution = format_objective_route_execution(execution)
    plain_detail = format_research_run(detail)

    assert runs[0].run_id == execution.route_run_id
    assert runs[0].detail_counts["gaps"] >= 1
    assert detail.metadata["research_brief"]["citation_policy"] == "brief_is_not_evidence"
    assert detail.metadata["serp_flattening_audit"]["checks"]["rank_used_as_evidence"] is False
    assert "research_task_frame:" in plain_execution
    assert "search_plan_graph:" in plain_execution
    assert "provider_capability_matrix:" in plain_execution
    assert "personalization_policy:" in plain_execution
    assert "user_signal_policy:" in plain_execution
    assert "result_coverage:" in plain_execution
    assert "search_episode_trace:" in plain_execution
    assert "reader_quality_profile:" in plain_execution
    assert "research_brief:" in plain_execution
    assert "evidence_gaps:" in plain_execution
    assert "serp_flattening:" in plain_execution
    assert "research_task_frame:" in plain_detail
    assert "search_plan_graph:" in plain_detail
    assert "provider_capability_matrix:" in plain_detail
    assert "personalization_policy:" in plain_detail
    assert "user_signal_policy:" in plain_detail
    assert "result_coverage:" in plain_detail
    assert "search_episode_trace:" in plain_detail
    assert "reader_quality_profile:" in plain_detail
    assert "claim_support:" in plain_detail
    assert "source_quality:" in plain_detail


def test_memory_workflow_plain_output_shows_route_plan(tmp_path: Path) -> None:
    db_path = tmp_path / "x.sqlite3"
    _seed_db(db_path)
    build_memory_corpus(db_path)

    workflow = run_memory_workflow(
        db_path,
        "ロボットの投稿を探して",
        limit=2,
        answer_provider="none",
    )
    plain = format_workflow(workflow)
    runs = list_research_runs(db_path, run_kind="workflow", limit=5)
    detail = show_research_run(db_path, workflow.workflow_id, run_kind="workflow")
    plain_detail = format_research_run(detail)

    assert runs[0].detail_counts["chunks"] > 0
    assert runs[0].detail_counts["citations"] > 0
    assert "route_plan:" in plain
    assert "objective_route_plan:" in plain
    assert "doc_types=" in plain
    assert "quality=local_primary_archive" in plain_detail


def test_memory_objective_execute_records_provider_gated_external_gap(tmp_path: Path) -> None:
    db_path = tmp_path / "x.sqlite3"
    _seed_db(db_path)
    build_memory_corpus(db_path)
    build_memory_relations(db_path)

    execution = run_objective_route_execution(
        db_path,
        "昔保存したロボット情報は今も正しい？",
        limit=2,
        max_route_arms=3,
    )

    assert "external_web_context" in execution.selected_routes
    assert "external_web_context" in execution.metadata["skipped_provider_roles"]
    assert "external_web_context" in execution.metadata["result_coverage_map"][
        "provider_quota_skipped_routes"
    ]
    assert any(
        gap["gap_id"] == "provider_quota_gate"
        for gap in execution.metadata["evidence_gap"]["gaps"]
    )
    assert execution.metadata["reader_quality_profile"]["status"] == (
        "blocked_by_provider_quota_gate"
    )
    assert execution.metadata["serp_flattening_audit"]["provider_quota_skipped"] is True
    assert execution.metadata["source_quality_signals"][-1]["citation_policy"] in {
        "blocked_until_fetch_extract_hash_and_chunk",
        "citation_excluded",
    }


def test_research_artifacts_classify_external_url_quality() -> None:
    plan = plan_objective_routes("最新の開示と評判を確認して")
    result = ObjectiveRouteArmResult(
        route_arm="external_web_context",
        status="needs_review",
        evidence_count=0,
        citation_count=0,
        stop_condition=None,
        escalation_trigger="needs_current_external_grounding",
        provider_quota_skipped=False,
        output={
            "source_urls": [
                "https://www.sec.gov/filing",
                "https://tabelog.com/tokyo/A1324/rstLst/?utm_source=test",
                "https://qiita.com/example/items/1",
            ],
        },
    )

    artifacts = build_execution_artifacts(
        plan,
        (result,),
        selected_routes=("external_web_context",),
        status="needs_review",
        stop_reason="external_context_needed",
    )

    signals = artifacts["source_quality_signals"]
    assert any(
        signal["source_kind"] == "official"
        and signal["quality_class"] == "official_or_primary_candidate"
        for signal in signals
    )
    assert any(
        signal["quality_class"] == "affiliate_or_leadgen_candidate"
        for signal in signals
    )
    assert any(
        "community_or_user_generated" in signal["risk_flags"]
        for signal in signals
    )
    assert artifacts["reader_quality_profile"]["source_kind_counts"]["official"] == 1
    assert artifacts["serp_flattening_audit"]["risk_flag_counts"][
        "leadgen_or_listing_site"
    ] == 1


def test_memory_media_roles_are_no_spend_annotations(tmp_path: Path) -> None:
    db_path = tmp_path / "x.sqlite3"
    media_path = tmp_path / "image.jpg"
    media_path.write_bytes(b"fake-image")
    _seed_db(db_path)
    with sqlite3.connect(db_path) as conn:
        ensure_memory_schema(conn)
        conn.execute(
            "UPDATE media SET local_path = ? WHERE media_id = ?",
            (str(media_path), "media-1"),
        )

    estimate = estimate_media_roles(db_path, limit=10)
    summary = build_media_roles(db_path, limit=10)
    coverage = media_role_coverage(db_path)

    assert estimate.selected == 1
    assert estimate.stored == 0
    assert "photo_place_food" in estimate.by_role
    assert "caption_candidate" in estimate.by_action
    assert summary.stored == 1
    assert coverage.profiles == 1
    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            """
            SELECT evidence_level, citation_ready, metadata_json
            FROM memory_visual_recall_evidence
            WHERE media_id = 'media-1'
              AND evidence_level = 'media_role_profile'
            """
        ).fetchone()
    assert row is not None
    assert row[0] == "media_role_profile"
    assert row[1] == 0
    assert (
        json.loads(row[2])["contract"]
        == "media_role_profile_is_routing_annotation_not_evidence"
    )


def test_memory_candidate_set_ocr_limits_media_scope(tmp_path: Path) -> None:
    db_path = tmp_path / "x.sqlite3"
    media_path = tmp_path / "image.jpg"
    media_path.write_bytes(b"fake-image")
    _seed_db(db_path)
    with sqlite3.connect(db_path) as conn:
        ensure_memory_schema(conn)
        conn.execute(
            "UPDATE media SET local_path = ? WHERE media_id = ?",
            (str(media_path), "media-1"),
        )

    missing = estimate_ocr_evidence(
        db_path,
        sample_policy="candidate_set",
        media_ids=("missing-media",),
        limit=10,
    )
    estimate = estimate_ocr_evidence(
        db_path,
        sample_policy="candidate_set",
        media_ids=("media-1",),
        limit=10,
    )
    summary = build_ocr_evidence(
        db_path,
        provider="fake",
        sample_policy="candidate_set",
        media_ids=("media-1",),
        limit=10,
    )

    assert missing.media == 0
    assert missing.selected == 0
    assert estimate.media == 1
    assert estimate.selected == 1
    assert summary.processed == 1
    assert summary.promoted_chunks == 1


def test_memory_objective_execute_can_run_explicit_fake_candidate_ocr(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "x.sqlite3"
    media_path = tmp_path / "image.jpg"
    media_path.write_bytes(b"fake-image")
    _seed_db(db_path)
    build_memory_corpus(db_path)
    build_memory_relations(db_path)
    with sqlite3.connect(db_path) as conn:
        ensure_memory_schema(conn)
        conn.execute(
            "UPDATE media SET local_path = ? WHERE media_id = ?",
            (str(media_path), "media-1"),
        )

    execution = run_objective_route_execution(
        db_path,
        "画像 OCR robot",
        limit=2,
        max_route_arms=1,
        ocr_mode="fake",
        ocr_limit=1,
        ocr_sample_policy="candidate_set",
    )

    assert execution.status == "ok"
    assert execution.arm_results[0].output["ocr_mode"] == "fake"
    assert execution.arm_results[0].output["ocr_build"]["processed"] == 1
    assert execution.arm_results[0].stop_condition == (
        "media_content_evidence_with_citation_ready_chunk"
    )
    coverage = execution.metadata["result_coverage_map"]
    route_row = coverage["route_rows"][0]
    assert coverage["candidate_total"] >= coverage["citation_total"]
    assert route_row["candidate_count"] >= route_row["citation_count"]
    assert 0.0 <= coverage["citation_ready_yield"] <= 1.0
    assert 0.0 <= route_row["citation_ready_yield"] <= 1.0


def test_memory_objective_execute_skips_provider_freshness_fallbacks(tmp_path: Path) -> None:
    db_path = tmp_path / "x.sqlite3"
    _seed_db(db_path)
    build_memory_corpus(db_path)
    build_memory_relations(db_path)

    execution = run_objective_route_execution(
        db_path,
        "最新のロボット論文リンクは今も正しいか確認して",
        limit=2,
        max_route_arms=3,
    )

    assert execution.plan.primary_route == "candidate_a_current_baseline"
    assert execution.arm_results[0].route_arm == "candidate_a_current_baseline"
    assert execution.arm_results[0].stop_condition == "external_context_needed"
    external = next(
        result
        for result in execution.arm_results
        if result.route_arm == "external_web_context"
    )
    assert external.status == "skipped"
    assert external.provider_quota_skipped is True
    assert external.output["reason"] == "no_quota_provider_freeze"


def test_memory_ocr_evidence_promotes_media_content_chunks(tmp_path: Path) -> None:
    db_path = tmp_path / "x.sqlite3"
    media_path = tmp_path / "image.jpg"
    media_path.write_bytes(b"fake-image")
    _seed_db(db_path)
    build_memory_corpus(db_path)
    build_memory_relations(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        ensure_memory_schema(conn)
        conn.execute(
            "UPDATE media SET local_path = ? WHERE media_id = ?",
            (str(media_path), "media-1"),
        )
        before = restore_media_source_bundle(conn, "media-1")

    estimate = estimate_ocr_evidence(db_path, limit=100)
    summary = build_ocr_evidence(db_path, provider="fake", limit=1)
    coverage = ocr_coverage(db_path)
    hits = ocr_search(db_path, "OCR robot", limit=5)

    assert before["media_content_evidence"] is False
    assert estimate.selected == 1
    assert estimate.sample_policy == "stratified"
    assert summary.provider == "fake"
    assert summary.processed == 1
    assert summary.promoted_chunks == 1
    assert coverage.texts == 1
    assert coverage.context_chunks == 1
    assert hits
    assert hits[0]["media_id"] == "media-1"
    assert hits[0]["bundle"]["tweet_id"] == "tweet-1"
    assert hits[0]["bundle"]["media_content_evidence"] is True
    with sqlite3.connect(db_path) as conn:
        raw_text, normalized_text, corrected_text = conn.execute(
            """
            SELECT raw_ocr_text, normalized_text, corrected_text
            FROM memory_ocr_texts
            LIMIT 1
            """
        ).fetchone()
    assert "Fake OCR text" in raw_text
    assert "OCR robot diagram label" in normalized_text
    assert corrected_text is None


def test_memory_codex_media_observation_is_inference_annotation(tmp_path: Path) -> None:
    db_path = tmp_path / "x.sqlite3"
    _seed_db(db_path)
    build_memory_corpus(db_path)
    build_memory_relations(db_path)

    summary = add_media_observation(
        db_path,
        media_id="media-1",
        observation_text="Codex observation: 店内写真ではなくロボット図解に見える。",
        observation_kind="codex_interpretation",
        provider="codex_interactive",
        model="gpt-5.5",
        confidence=0.72,
        prompt="この画像は何か",
    )
    coverage = media_observation_coverage(db_path)
    hits = ocr_search(db_path, "ロボット図解", limit=5)

    assert summary.imported == 1
    assert summary.promoted_chunks == 1
    assert coverage.texts == 1
    assert coverage.chunks == 1
    assert coverage.visual_annotations == 1
    assert hits[0]["text_profile"] == "codex_observation"
    assert hits[0]["evidence_status"] == "inference"
    with sqlite3.connect(db_path) as conn:
        citation = conn.execute(
            """
            SELECT support_type, evidence_status, field_path
            FROM memory_citation_annotations
            WHERE field_path = 'media.ocr_text.codex_observation'
            """
        ).fetchone()
    assert citation == ("supports_search_helper", "inference", "media.ocr_text.codex_observation")


def test_memory_ocr_blocks_provider_quota_calls(tmp_path: Path) -> None:
    db_path = tmp_path / "x.sqlite3"
    _seed_db(db_path)
    build_memory_corpus(db_path)

    with pytest.raises(RuntimeError, match="provider OCR API use is frozen"):
        build_ocr_evidence(db_path, provider="mistral", limit=1)


def test_memory_ocr_quality_regions_second_pass_and_promote(tmp_path: Path) -> None:
    from PIL import Image

    db_path = tmp_path / "x.sqlite3"
    media_path = tmp_path / "screen.png"
    Image.new("RGB", (900, 900), color="white").save(media_path)
    _seed_db(db_path)
    build_memory_corpus(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            UPDATE media
            SET local_path = ?, content_type = ?, alt_text = ?
            WHERE media_id = ?
            """,
            (str(media_path), "image/png", "スクショ 画面 文字", "media-1"),
        )

    before_regions = _count_table(db_path, "memory_ocr_regions")
    estimate = estimate_ocr_evidence(db_path, limit=10)
    after_regions = _count_table(db_path, "memory_ocr_regions")
    summary = build_ocr_evidence(db_path, provider="fake", limit=3)
    second_pass = mark_ocr_second_pass_candidates(db_path)
    promotion = promote_ocr_chunks(
        db_path,
        include_profiles=("raw_ocr", "caption", "vlm_caption", "corrected_text"),
    )
    coverage = ocr_coverage(db_path)

    assert before_regions == after_regions == 0
    assert estimate.selected >= 3
    assert "screenshot_or_ui" in estimate.by_strata
    assert estimate.by_quality_flag["text_density:high"] >= 3
    assert summary.processed == 3
    assert summary.second_pass_candidates == 3
    assert second_pass.candidates == 3
    assert second_pass.corrected_profiles == 3
    assert promotion.promoted_chunks >= 3
    assert coverage.by_text_profile["raw_ocr"] == 3
    assert coverage.by_text_profile["corrected_text"] == 3
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT reading_order, bbox_json, crop_path, detector_version
            FROM memory_ocr_regions
            ORDER BY reading_order
            """
        ).fetchall()
        raw_text, corrected_parent = conn.execute(
            """
            SELECT raw_ocr_text, parent_text_id
            FROM memory_ocr_texts
            WHERE text_profile = 'corrected_text'
            LIMIT 1
            """
        ).fetchone()
    assert [row[0] for row in rows] == [0, 1, 2]
    assert all(json.loads(row[1])["type"].endswith("band") for row in rows)
    assert all(row[2] for row in rows)
    assert all(Path(row[2]).exists() for row in rows)
    assert all(row[3] == "ocr-local-region-v1" for row in rows)
    assert "Fake OCR text" in raw_text
    assert corrected_parent


def test_memory_objective_routes_and_ocr_cli(tmp_path: Path, capsys) -> None:
    db_path = tmp_path / "x.sqlite3"
    media_path = tmp_path / "image.jpg"
    media_path.write_bytes(b"fake-image")
    _seed_db(db_path)
    build_memory_corpus(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "UPDATE media SET local_path = ? WHERE media_id = ?",
            (str(media_path), "media-1"),
        )

    assert (
        main(
            [
                "memory",
                "objective-routes",
                "--db",
                str(db_path),
                "--query",
                "画像の図表を探して",
                "--json",
            ]
        )
        == 0
    )
    objective_output = capsys.readouterr().out
    assert '"primary_route": "media_evidence"' in objective_output
    assert "ocr_quality_pipeline" in objective_output
    assert (
        main(
            [
                "memory",
                "objective-execute",
                "--db",
                str(db_path),
                "--query",
                "画像の図表を探して",
                "--limit",
                "2",
                "--max-route-arms",
                "2",
                "--json",
            ]
        )
        == 0
    )
    execution_output = capsys.readouterr().out
    assert '"route_arm": "media_evidence"' in execution_output
    assert '"provider_quota_frozen": true' in execution_output
    assert '"guarded_fusion"' in execution_output
    assert '"source_bundle_restoration_failures"' in execution_output
    assert (
        main(
            [
                "memory",
                "ocr-estimate",
                "--db",
                str(db_path),
                "--limit",
                "100",
            ]
        )
        == 0
    )
    estimate_output = capsys.readouterr().out
    assert "sample_policy: stratified" in estimate_output
    assert "selected=1" in estimate_output
    assert (
        main(
            [
                "memory",
                "build-ocr-evidence",
                "--db",
                str(db_path),
                "--provider",
                "fake",
                "--limit",
                "1",
            ]
        )
        == 0
    )
    build_output = capsys.readouterr().out
    assert "provider: fake/mistral-ocr-2512" in build_output
    assert (
        main(
            [
                "memory",
                "build-ocr-evidence",
                "--db",
                str(db_path),
                "--provider",
                "mistral",
                "--allow-real-api",
                "--limit",
                "1",
            ]
        )
        == 1
    )
    blocked_output = capsys.readouterr()
    assert "does not override" in blocked_output.err
    assert "promoted_chunks=1" in build_output
    assert main(["memory", "ocr-coverage", "--db", str(db_path)]) == 0
    coverage_output = capsys.readouterr().out
    assert "texts=1" in coverage_output
    assert "context_chunks=1" in coverage_output


def test_memory_final_skeleton_preflight_writes_no_spend_contracts(tmp_path: Path) -> None:
    db_path = tmp_path / "x.sqlite3"
    _seed_db(db_path)
    build_memory_corpus(db_path)

    report = run_final_skeleton_preflight(
        db_path,
        "画像付きで保存した強化学習の資料を出して",
        limit=3,
    )

    assert report.provider_quota_blocked is True
    assert report.query_transforms >= 2
    assert report.retrieval_text_profiles >= 2
    assert report.eval_gates == 6
    assert report.index_memberships >= 1
    assert report.security_boundaries >= report.query_transforms
    assert report.visual_recall_evidence == 1
    assert report.user_ranking_signals == 1
    assert "provider-backed" in report.next_paid_gate

    with sqlite3.connect(db_path) as conn:
        ensure_memory_schema(conn)
        query_transform = conn.execute(
            """
            SELECT citation_excluded, drift_flags_json
            FROM memory_query_transforms
            WHERE transform_kind = 'media_grounded_query'
            """
        ).fetchone()
        assert query_transform is not None
        assert query_transform[0] == 1
        assert "generated_search_text" in json.loads(query_transform[1])

        retrieval_profile = conn.execute(
            """
            SELECT citation_excluded, metadata_json
            FROM memory_retrieval_text_profiles
            WHERE retrieval_text_profile = 'contextual_bm25'
            LIMIT 1
            """
        ).fetchone()
        assert retrieval_profile is not None
        assert retrieval_profile[0] == 1
        assert (
            json.loads(retrieval_profile[1])["contract"]
            == "retrieval_text_profile_is_projection_not_source"
        )
        missing_fts = conn.execute(
            """
            SELECT COUNT(*)
            FROM memory_retrieval_text_profiles p
            LEFT JOIN memory_retrieval_text_fts f ON f.profile_id = p.profile_id
            WHERE f.profile_id IS NULL
            """
        ).fetchone()[0]
        assert missing_fts == 0

        gate_names = {
            row[0]
            for row in conn.execute(
                "SELECT gate_name FROM memory_eval_gate_results WHERE route_run_id = ?",
                (report.preflight_id,),
            ).fetchall()
        }
        assert gate_names == {
            "route_eval",
            "retrieval_eval",
            "context_eval",
            "citation_eval",
            "answer_eval",
            "abstention_eval",
        }

        visual = conn.execute(
            """
            SELECT evidence_level, citation_ready, metadata_json
            FROM memory_visual_recall_evidence
            WHERE media_id = 'media-1'
            """
        ).fetchone()
        assert visual is not None
        assert visual[0] == "visual_recall_evidence"
        assert visual[1] == 0
        assert (
            json.loads(visual[2])["contract"]
            == "visual_recall_candidate_not_media_content_evidence"
        )

        signal = conn.execute(
            """
            SELECT evidence_status, route_scope
            FROM memory_user_ranking_signals
            WHERE subject_id = 'tweet-1'
            """
        ).fetchone()
        assert signal == (
            "ranking_hint_not_evidence",
            "refinding,subjective_preference,exploratory_learning",
        )

        projection = conn.execute(
            "SELECT status, coverage_json FROM memory_projection_generations"
        ).fetchone()
        assert projection is not None
        assert projection[0] == "ready"
        assert json.loads(projection[1])["provider_quota_blocked"] is True


def test_memory_final_skeleton_preflight_cli_json_no_store(
    tmp_path: Path,
    capsys,
) -> None:
    db_path = tmp_path / "x.sqlite3"
    _seed_db(db_path)
    build_memory_corpus(db_path)

    assert (
        main(
            [
                "memory",
                "final-skeleton-preflight",
                "--db",
                str(db_path),
                "--query",
                "北千住のピザ店を保存から探して",
                "--no-store",
                "--json",
            ]
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload["stored"] is False
    assert payload["provider_quota_blocked"] is True
    assert payload["eval_gates"] == 6

    with sqlite3.connect(db_path) as conn:
        ensure_memory_schema(conn)
        assert conn.execute("SELECT COUNT(*) FROM memory_query_transforms").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM memory_eval_gate_results").fetchone()[0] == 0


def test_memory_media_embedding_resolver_skips_invalid_media(tmp_path: Path) -> None:
    db_path = tmp_path / "x.sqlite3"
    media_path = tmp_path / "note.txt"
    media_path.write_text("not media", encoding="utf-8")
    _seed_db(db_path)
    with sqlite3.connect(db_path) as conn:
        ensure_memory_schema(conn)
        conn.execute(
            "UPDATE media SET local_path = ?, content_type = ? WHERE media_id = ?",
            (str(media_path), "text/plain", "media-1"),
        )

    estimate = estimate_media_embedding_build(db_path, dimensions=3)

    assert estimate.media == 1
    assert estimate.selected == 0
    assert estimate.skipped == 1
    assert estimate.skipped_reasons["unsupported_mime_type"] == 1


def test_memory_media_embedding_cli_estimate_is_read_only(tmp_path: Path) -> None:
    db_path = tmp_path / "x.sqlite3"
    media_path = tmp_path / "image.jpg"
    media_path.write_bytes(b"fake-image")
    _seed_db(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "UPDATE media SET local_path = ? WHERE media_id = ?",
            (str(media_path), "media-1"),
        )

    assert (
        main(
            [
                "memory",
                "media-embedding-estimate",
                "--db",
                str(db_path),
                "--dimensions",
                "3",
                "--json",
            ]
        )
        == 0
    )
    with sqlite3.connect(db_path) as conn:
        ensure_memory_schema(conn)
        count = conn.execute("SELECT COUNT(*) FROM memory_media_embeddings").fetchone()[0]
    assert count == 0


def test_memory_api_lane_estimate_covers_planned_lanes_and_url_dependency(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "x.sqlite3"
    media_path = tmp_path / "image.jpg"
    media_path.write_bytes(b"fake-image")
    _seed_db(db_path)
    build_memory_corpus(db_path)
    with sqlite3.connect(db_path) as conn:
        ensure_memory_schema(conn)
        conn.execute(
            "UPDATE media SET local_path = ? WHERE media_id = ?",
            (str(media_path), "media-1"),
        )
        conn.execute(
            """
            INSERT INTO memory_external_runs (
                run_id, provider, provider_role, query, endpoint, parameters_json,
                status, retrieved_at, raw_response_hash, retention_policy, error
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "external-run",
                "serper",
                "index_provider",
                "pizza",
                "https://google.serper.dev/search",
                "{}",
                "ok",
                "2026-05-26T00:00:00+00:00",
                "hash",
                "metadata_only",
                None,
            ),
        )
        conn.execute(
            """
            INSERT INTO memory_external_items (
                item_id, run_id, position, title, url, snippet, source, metadata_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "external-item",
                "external-run",
                1,
                "Pizza",
                "https://example.com/pizza",
                "pizza snippet",
                "example",
                "{}",
            ),
        )

    report = build_api_lane_estimate_report(
        db_path,
        include_latest_ocr=True,
        reader_url_limit=10,
        reader_max_chars=1000,
        rerank_query_count=2,
        rerank_candidate_limit=10,
        rerank_avg_candidate_tokens=100,
    )
    rows = {row.name: row for row in report.rows}
    estimate_row_names = set(rows)
    gated_statuses = {
        "legacy_comparison_only",
        "deferred_endpoint_required",
        "deferred_local_or_compatible",
        "deferred_gcp_vertex_auth_required",
    }
    runnable_strategy_names = {
        candidate.name
        for strategy in DEFAULT_RETRIEVAL_STRATEGIES
        for candidate in strategy.candidates
        if candidate.provider and candidate.model and candidate.status not in gated_statuses
    }

    assert rows["gemini2_general_text"].estimated_cost_usd is not None
    assert rows["cohere_v4_media_text"].status == "secondary_priced_estimate"
    assert rows["cohere_v4_media_text"].lane == "embedding_media_text_bridge"
    assert rows["voyage4_multilingual"].lane == "embedding_jp_multilingual"
    assert rows["gemini2_multilingual"].lane == "embedding_jp_multilingual"
    assert rows["jina_v5_text_learning"].lane == "embedding_learning_long"
    assert rows["mistral_text_code_docs"].lane == "embedding_code_technical"
    assert rows["cohere_rerank_v4_0_pro"].estimated_cost_usd == 0.005
    assert rows["jina_reader_extract"].extra["discovered_external_urls"] == 2
    assert rows["jina_reader_extract"].estimated_cost_usd is not None
    assert rows["serper_external_search"].estimated_cost_usd == 0.001
    assert rows["brave_llm_context"].estimated_cost_usd == 0.005
    assert rows["openai_web_search_tool"].status == "reference_only_not_wired"
    assert rows["openai_web_search_tool"].estimated_cost_usd is None
    assert rows["gemini_google_search_grounding"].extra["unit_price_usd"] == 0.014
    assert rows["mistral_ocr_2512"].lane == "media_to_text_ocr"
    assert rows["mistral_ocr_2512"].selected_units == 1
    assert rows["mistral_ocr_2512"].estimated_cost_usd == 0.002
    assert rows["voyage_context_4_learning"].status == "contract_required_lower_bound"
    assert rows["voyage_context_4_learning"].lane == "embedding_contextual_learning"
    assert "voyage_context_3_learning" not in rows
    assert rows["openai_file_search_vector_stores"].estimated_cost_usd is None
    plans = {plan["plan_id"]: plan for plan in report.totals["recommended_plans"]}
    assert plans["objective_fit_router_baseline"]["status"] == "recommended_first_pass"
    assert (
        plans["objective_fit_router_baseline"]["estimated_cost_usd"]
        < report.totals["estimated_priced_cost_usd"]
    )
    assert "gemini2_general_text" in plans["objective_fit_router_baseline"]["row_names"]
    assert "voyage4_multilingual" in plans["jp_multilingual_route"]["row_names"]
    assert "gemini2_multilingual" in plans["jp_multilingual_route"]["row_names"]
    assert "voyage_context_4_learning" in plans["learning_long_route"]["row_names"]
    assert "jina_v5_text_learning" in plans["learning_long_route"]["row_names"]
    assert "mistral_text_code_docs" in plans["code_technical_route"]["row_names"]
    assert "gemini_embedding_2_native_media" in plans["media_grounded_route"]["row_names"]
    assert "serper_external_search" in plans["current_external_grounding_route"]["row_names"]
    assert "brave_llm_context" in plans["current_external_grounding_route"]["row_names"]
    assert plans["full_ocr_lower_bound"]["status"] == "expensive_explicit_only"
    assert runnable_strategy_names <= estimate_row_names


def test_memory_api_lane_estimate_cli_and_price_seed(
    tmp_path: Path,
    capsys,
) -> None:
    db_path = tmp_path / "x.sqlite3"
    _seed_db(db_path)
    build_memory_corpus(db_path)

    assert main(["memory", "api-budget", "seed-default-prices", "--db", str(db_path)]) == 0
    assert (
        main(
            [
                "memory",
                "api-lane-estimate",
                "--db",
                str(db_path),
                "--reader-url-limit",
                "5",
                "--rerank-query-count",
                "1",
                "--external-search-query-count",
                "2",
                "--llm-context-query-count",
                "2",
            ]
        )
        == 0
    )

    output = capsys.readouterr().out
    assert "seeded default API prices" in output
    assert "cohere_v4_media_text" in output
    assert "external_grounding/serper_external_search" in output
    assert "external_grounding/brave_llm_context" in output
    assert "objective_fit_router_baseline" in output
    assert "managed_rag_reference/openai_file_search_vector_stores" in output
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT provider, model, operation, unit, usd_per_unit
            FROM memory_api_price_catalog
            WHERE provider = 'cohere'
            ORDER BY model, operation, unit
            """
        ).fetchall()
    assert ("cohere", "embed-v4.0", "embedding", "input_token", 0.00000012) in rows
    assert ("cohere", "rerank-v4.0-pro", "rerank", "call", 0.0025) in rows
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT provider, model, operation, unit, usd_per_unit
            FROM memory_api_price_catalog
            WHERE provider IN ('serper', 'brave', 'openai', 'gemini', 'mistral')
            ORDER BY provider, model, operation, unit
            """
        ).fetchall()
    assert ("serper", "serper-search", "external_search", "call", 0.001) in rows
    assert ("brave", "llm-context", "llm_context", "call", 0.005) in rows
    assert ("openai", "file_search", "file_search_tool_call", "call", 0.0025) in rows
    assert ("openai", "file_search", "file_search_storage", "gb_day", 0.1) in rows
    assert ("openai", "web_search", "web_search", "call", 0.01) in rows
    assert ("gemini", "google-search-grounding", "grounding_search", "call", 0.014) in rows
    assert ("mistral", "mistral-ocr-latest", "ocr", "page", 0.002) in rows


def test_memory_api_lane_estimate_ocr_requires_explicit_full_scope(tmp_path: Path) -> None:
    db_path = tmp_path / "x.sqlite3"
    _seed_db(db_path)
    build_memory_corpus(db_path)

    default_report = build_api_lane_estimate_report(db_path)
    all_report = build_api_lane_estimate_report(
        db_path,
        ocr_scope="all",
        include_latest_ocr=True,
    )
    managed_report = build_api_lane_estimate_report(
        db_path,
        include_reference_managed_rag=True,
    )
    default_rows = {row.name: row for row in default_report.rows}
    all_rows = {row.name: row for row in all_report.rows}
    managed_rows = {row.name: row for row in managed_report.rows}

    assert default_rows["mistral_ocr_2512"].selected_units == 0
    assert "mistral_ocr_latest" not in default_rows
    assert all_rows["mistral_ocr_2512"].selected_units >= 0
    assert "mistral_ocr_latest" in all_rows
    assert managed_rows["openai_file_search_vector_stores"].estimated_cost_usd == 0.1
    assert managed_rows["openai_file_search_tool_call"].estimated_cost_usd == 0.0025


def test_memory_api_lane_estimate_zero_reader_limit_skips_url_discovery(
    tmp_path: Path,
    monkeypatch,
) -> None:
    db_path = tmp_path / "x.sqlite3"
    _seed_db(db_path)
    build_memory_corpus(db_path)

    def fail_discovery(_db_path: str | Path, *, limit: int | None = None) -> tuple[str, ...]:
        raise AssertionError("reader URL discovery should be skipped when limit is zero")

    monkeypatch.setattr(memory_api_lane_estimate, "discover_external_urls", fail_discovery)

    report = build_api_lane_estimate_report(
        db_path,
        reader_url_limit=0,
        ocr_scope="none",
    )
    rows = {row.name: row for row in report.rows}

    assert rows["jina_reader_extract"].extra["discovered_external_urls"] == 0
    assert rows["jina_reader_extract"].selected_units == 0


def test_memory_discover_external_urls_filters_x_sources(tmp_path: Path) -> None:
    db_path = tmp_path / "x.sqlite3"
    _seed_db(db_path)
    build_memory_corpus(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            UPDATE tweets
            SET text = text || ' https://example.com/article https://[broken'
            WHERE tweet_id = ?
            """,
            ("tweet-1",),
        )

    urls = discover_external_urls(db_path)

    assert "https://example.com/article" in urls
    assert all("x.com" not in urlparse_netloc for urlparse_netloc in urls)


def test_memory_restore_media_source_bundle_without_media_row(tmp_path: Path) -> None:
    db_path = tmp_path / "x.sqlite3"
    _seed_db(db_path)
    with sqlite3.connect(db_path) as conn:
        ensure_memory_schema(conn)
        bundle = restore_media_source_bundle(conn, "missing-media")

    assert bundle["restored"] is False
    assert bundle["evidence_status"] == "unconfirmed_media_match"


def test_memory_portfolio_guarded_fusion_defers_semantic_only_noise() -> None:
    lexical_arm = memory_portfolio.PortfolioArmResult(
        name="local_hybrid",
        status="ok",
        mode="local_hybrid",
        provider=None,
        model=None,
        dimensions=None,
        embedding_profile=None,
        text_template_version=None,
        weight=1.0,
        hit_count=1,
        top_doc_ids=("tweet:lexical",),
        top_bundle_keys=("tweet:lexical",),
        error=None,
    )
    semantic_arm = memory_portfolio.PortfolioArmResult(
        name="hash256",
        status="ok",
        mode="semantic_only",
        provider="local_hash",
        model="local-hash-v1",
        dimensions=256,
        embedding_profile="general_memory",
        text_template_version="memory-doc-embedding-v1",
        weight=10.0,
        hit_count=1,
        top_doc_ids=("tweet:semantic",),
        top_bundle_keys=("tweet:semantic",),
        error=None,
    )
    lexical_hit = {
        "doc_id": "tweet:lexical",
        "doc_type": "tweet_doc",
        "tweet_id": "lexical",
        "title": "lexical",
        "compact_text": "lexical exact match",
        "metadata": {},
        "evidence": {},
        "score_components": {},
    }
    semantic_hit = {
        "doc_id": "tweet:semantic",
        "doc_type": "tweet_doc",
        "tweet_id": "semantic",
        "title": "semantic",
        "compact_text": "semantic only high weight",
        "metadata": {},
        "evidence": {},
        "score_components": {},
    }

    raw_rrf = memory_portfolio._fuse_hits(  # noqa: SLF001
        [(lexical_arm, [lexical_hit]), (semantic_arm, [semantic_hit])],
        limit=2,
        rrf_k=60.0,
        fusion_mode="rrf",
        min_agreement=2,
    )
    guarded = memory_portfolio._fuse_hits(  # noqa: SLF001
        [(lexical_arm, [lexical_hit]), (semantic_arm, [semantic_hit])],
        limit=2,
        rrf_k=60.0,
        fusion_mode="guarded_rrf",
        min_agreement=2,
    )

    assert raw_rrf[0].doc_id == "tweet:semantic"
    assert guarded[0].doc_id == "tweet:lexical"


def test_memory_rerank_fake_provider_stores_tool_call(tmp_path: Path) -> None:
    db_path = tmp_path / "x.sqlite3"
    _seed_db(db_path)
    build_memory_corpus(db_path)

    report = rerank_evidence_query(
        db_path,
        "強化学習 ロボット",
        provider="fake",
        limit=5,
        top_n=2,
        store=True,
    )

    assert report.tool_call_id
    assert report.results
    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            """
            SELECT provider, provider_role, action, output_json
            FROM memory_tool_calls
            WHERE tool_call_id = ?
            """,
            (report.tool_call_id,),
        ).fetchone()
    assert row[0] == "fake"
    assert row[1] == "reranker"
    assert row[2] == "rerank"
    assert json.loads(row[3])["results"][0]["provider"] == "fake"


def test_memory_rerank_real_provider_payloads(monkeypatch) -> None:
    captured = []

    def fake_post_json(url, payload, *, headers, timeout_seconds, retries=3):
        captured.append((url, payload, headers))
        return {"results": [{"index": 0, "relevance_score": 0.9}]}

    monkeypatch.setenv("COHERE_API_KEY", "cohere-key")
    monkeypatch.setenv("JINA_API_KEY", "jina-key")
    monkeypatch.setenv("VOYAGE_API_KEY", "voyage-key")
    monkeypatch.setattr(memory_rerank, "_post_json", fake_post_json)
    hits = [
        {
            "doc_id": "doc:1",
            "doc_type": "tweet_doc",
            "tweet_id": "1",
            "title": "robot",
            "compact_text": "強化学習 ロボット",
            "metadata": {},
            "evidence": {},
        }
    ]

    rerank_hits("強化学習", hits, provider="cohere", model="rerank-v4.0-pro")
    rerank_hits("強化学習", hits, provider="jina", model="jina-reranker-v3")
    rerank_hits("強化学習", hits, provider="voyage", model="rerank-2.5")

    assert captured[0][0] == "https://api.cohere.com/v2/rerank"
    assert captured[0][1]["top_n"] == 5
    assert captured[1][0] == "https://api.jina.ai/v1/rerank"
    assert isinstance(captured[1][1]["documents"][0], dict)
    assert captured[2][0] == "https://api.voyageai.com/v1/rerank"
    assert captured[2][1]["top_k"] == 5


def test_memory_portfolio_eval_accepts_fake_reranker_arm(tmp_path: Path) -> None:
    db_path = tmp_path / "x.sqlite3"
    _seed_db(db_path)
    build_memory_corpus(db_path)

    report = run_portfolio_eval(
        db_path,
        cases=(DEFAULT_EVAL_CASES[0],),
        reranker_specs=(parse_portfolio_reranker_spec("provider=fake,name=fake_rerank"),),
        limit=3,
        arm_limit=5,
    )

    arm_names = {arm.name for arm in report.cases[0].arms}
    assert "fake_rerank" in arm_names
    assert report.parameters["reranker_specs"]


def test_memory_portfolio_preferred_doc_type_checks_bundle_doc_types() -> None:
    case = EvalCase(
        query="event",
        required_any_terms=(),
        preferred_doc_types=("tweet_doc",),
    )
    hit = memory_portfolio.PortfolioHit(
        rank=1,
        bundle_key="tweet:1",
        doc_id="media:1",
        doc_type="media_doc",
        tweet_id="1",
        score=1.0,
        title="media representative",
        compact_text="media representative",
        contributions=(),
        metadata={"portfolio_doc_types": ["media_doc", "tweet_doc"]},
    )

    assert memory_portfolio._preferred_doc_type_found(case, [hit])  # noqa: SLF001


def test_memory_portfolio_strict_blocks_diagnostic_provider(tmp_path: Path) -> None:
    db_path = tmp_path / "x.sqlite3"
    _seed_db(db_path)
    build_memory_corpus(db_path)
    build_memory_embeddings(db_path, provider="local_hash", dimensions=64)

    assert (
        main(
            [
                "memory",
                "portfolio-eval",
                "--db",
                str(db_path),
                "--semantic-spec",
                "provider=local_hash,dimensions=64,name=hash64",
                "--limit",
                "1",
                "--arm-limit",
                "2",
                "--strict",
            ]
        )
        == 2
    )


def test_memory_portfolio_abstention_case_accepts_no_hits(tmp_path: Path) -> None:
    db_path = tmp_path / "x.sqlite3"
    _seed_db(db_path)
    build_memory_corpus(db_path)
    build_memory_embeddings(db_path, provider="local_hash", dimensions=64)
    case = EvalCase(
        query="保存したはずのZZZ_NO_SUCH_TOPIC_6f3aを出して。なければないと言って",
        required_any_terms=("ZZZ_NO_SUCH_TOPIC_6f3a",),
        question_type="abstention_false_premise",
        expected_stop_reasons=("no_local_evidence",),
        min_hit_score=0.0,
    )

    report = run_portfolio_eval(
        db_path,
        cases=(case,),
        semantic_specs=(
            parse_portfolio_semantic_spec(
                "provider=local_hash,dimensions=64,name=hash64"
            ),
        ),
        limit=3,
        arm_limit=5,
    )
    result = report.cases[0]

    assert result.status == "ok"
    assert result.fused_hits == ()
    assert all(arm.case_status == "ok" for arm in result.arms)


def test_memory_portfolio_required_term_gap_is_review_only_for_unanswerable_cases() -> None:
    hit = memory_portfolio.PortfolioHit(
        rank=1,
        bundle_key="tweet:1",
        doc_id="tweet:1",
        doc_type="tweet_doc",
        tweet_id="1",
        score=1.0,
        title="unrelated",
        compact_text="unrelated saved item",
        contributions=(),
        metadata={},
    )
    answerable = EvalCase(
        query="robot",
        required_any_terms=("robot",),
        question_type="single_fact_conditioned",
    )
    conditionally_answerable = EvalCase(
        query="同じ話で反対意見や矛盾している保存投稿はある？",
        required_any_terms=("反対", "矛盾"),
        question_type="contradiction_support",
        expected_stop_reasons=("external_context_needed", "no_local_evidence"),
    )

    answerable_notes = memory_portfolio._case_notes(answerable, [hit])  # noqa: SLF001
    conditional_notes = memory_portfolio._case_notes(  # noqa: SLF001
        conditionally_answerable,
        [hit],
    )

    assert memory_portfolio._case_status(answerable, answerable_notes, [hit]) == "fail"  # noqa: SLF001
    assert (  # noqa: SLF001
        memory_portfolio._case_status(conditionally_answerable, conditional_notes, [hit])
        == "needs_review"
    )


def test_memory_portfolio_denoising_gate_blocks_promotion() -> None:
    hit = memory_portfolio.PortfolioHit(
        rank=1,
        bundle_key="tweet:1",
        doc_id="tweet:1",
        doc_type="tweet_doc",
        tweet_id="1",
        score=1.0,
        title="candidate",
        compact_text="candidate",
        contributions=({"arm": "semantic_candidate", "rank": 1},),
        metadata={},
    )
    summary = memory_portfolio.PortfolioDenoisingSummary(
        candidate_count=1,
        unique_candidate_count=1,
        fused_count=1,
        filtered_candidate_count=0,
        source_restorable_count=1,
        citation_ready_count=0,
        unsupported_context_count=1,
        single_arm_only_count=1,
        multi_arm_agreement_count=0,
        baseline_backed_count=0,
        deferred_single_arm_count=0,
        noisy_survivor_count=1,
        drop_reasons={},
    )
    case = memory_portfolio.PortfolioCaseResult(
        query="robot",
        question_type="single_fact_conditioned",
        status="ok",
        notes=tuple(memory_portfolio._denoising_notes(summary)),  # noqa: SLF001
        best_arm_name=None,
        best_arm_status=None,
        fusion_improved=False,
        fusion_regressed=False,
        arms=(),
        fused_hits=(hit,),
        required_terms_found=True,
        preferred_doc_type_found=True,
        required_feature_found=True,
        denoising=summary,
    )

    assert memory_portfolio._case_status(  # noqa: SLF001
        EvalCase(query="robot", required_any_terms=()),
        list(case.notes),
        [hit],
    ) == "needs_review"
    verdict = memory_portfolio._promotion_verdict(  # noqa: SLF001
        (case,),
        (),
        (memory_portfolio.PortfolioSemanticSpec(provider="candidate"),),
        (),
    )

    assert verdict.status == "hold"
    assert not verdict.promotable
    assert any("denoising gate" in blocker for blocker in verdict.blockers)


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


def test_memory_audit_allows_evidence_first_without_embeddings(tmp_path: Path) -> None:
    db_path = tmp_path / "x.sqlite3"
    _seed_db(db_path)
    build_memory_corpus(db_path)
    build_memory_relations(db_path)

    report = audit_memory_db(db_path)

    assert report.documents == 5
    assert not report.warnings
    assert "no_spend_gap" not in report.strategy_gap_counts
    assert main(["memory", "audit", "--db", str(db_path), "--strict"]) == 0


def test_memory_audit_flags_claim_citation_integrity_issues(tmp_path: Path) -> None:
    db_path = tmp_path / "x.sqlite3"
    _seed_db(db_path)
    build_memory_corpus(db_path)
    build_memory_relations(db_path)
    answer = build_memory_answer(
        db_path,
        "強化学習 ロボット",
        limit=1,
        answer_provider="fake",
    )

    with sqlite3.connect(db_path) as conn:
        ensure_memory_schema(conn)
        conn.execute(
            """
            UPDATE memory_answer_runs
            SET answer_text = ?
            WHERE answer_id = ?
            """,
            (
                "根拠に基づく回答です [2]\n"
                "これは追加された確認不能な事実説明です。",
                answer.answer_id,
            ),
        )

    report = audit_memory_db(db_path)

    assert report.claim_citation_issues["ok_answer_with_unmapped_citation_markers"] == 1
    assert report.claim_citation_issues["ok_answer_with_unrendered_citation_markers"] == 1
    assert report.claim_citation_issues["ok_answer_with_invalid_citation_spans"] >= 1
    assert report.claim_citation_issues["ok_answer_with_uncited_claim_lines"] == 1


def test_memory_audit_flags_retrieval_text_lineage_issues(tmp_path: Path) -> None:
    db_path = tmp_path / "x.sqlite3"
    _seed_db(db_path)
    build_memory_corpus(db_path)
    build_memory_relations(db_path)
    build_retrieval_text_profiles(db_path)

    with sqlite3.connect(db_path) as conn:
        ensure_memory_schema(conn)
        profile_id = conn.execute(
            """
            SELECT profile_id
            FROM memory_retrieval_text_profiles
            ORDER BY profile_id
            LIMIT 1
            """
        ).fetchone()[0]
        conn.execute(
            """
            UPDATE memory_retrieval_text_profiles
            SET citation_excluded = 0,
                source_doc_hash = 'stale'
            WHERE profile_id = ?
            """,
            (profile_id,),
        )
        conn.execute(
            "DELETE FROM memory_retrieval_text_fts WHERE profile_id = ?",
            (profile_id,),
        )

    report = audit_memory_db(db_path)

    assert report.freshness_lineage_issues["retrieval_text_not_citation_excluded"] == 1
    assert report.freshness_lineage_issues["retrieval_text_stale_source_doc_hash"] == 1
    assert report.freshness_lineage_issues["retrieval_text_profiles_missing_fts"] == 1


def test_memory_audit_quarantines_openai_compatible_embeddings_under_freeze(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "x.sqlite3"
    _seed_db(db_path)
    build_memory_corpus(db_path)
    build_memory_relations(db_path)

    _insert_provider_embedding_row(
        db_path,
        provider="openai_compatible",
        model="custom-embedding",
        dimensions=3,
    )

    report = audit_memory_db(db_path)
    spec = next(
        item
        for item in report.embedding_specs
        if item["provider"] == "openai_compatible"
    )

    assert spec["provider_gated"] is True
    assert spec["quarantined"] is True
    assert spec["production_eligible"] is False
    assert any("provider embedding rows are quarantined" in item for item in report.warnings)


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
    monkeypatch.delenv("VOYAGE_API_KEY", raising=False)
    monkeypatch.delenv("COHERE_API_KEY", raising=False)
    monkeypatch.delenv("MISTRAL_API_KEY", raising=False)
    monkeypatch.delenv("JINA_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_COMPATIBLE_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_COMPATIBLE_EMBEDDINGS_URL", raising=False)

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
    assert bundle.as_dict()["evidence_policy"]["snippet_is_not_evidence"] is True
    assert bundle.items[0].as_dict()["citation_excluded"] is True
    assert bundle.items[0].metadata["evidence_status"] == "not_evidence_until_reader_chunk"

    with sqlite3.connect(db_path) as conn:
        run_count = conn.execute("SELECT COUNT(*) FROM memory_external_runs").fetchone()[0]
        item_count = conn.execute("SELECT COUNT(*) FROM memory_external_items").fetchone()[0]
        role = conn.execute("SELECT provider_role FROM memory_external_runs").fetchone()[0]
        item_metadata = json.loads(
            conn.execute("SELECT metadata_json FROM memory_external_items").fetchone()[0]
        )

    assert run_count == 1
    assert item_count == 2
    assert role == "index_provider"
    assert item_metadata["citation_excluded"] is True
    assert item_metadata["rank_is_not_evidence"] is True
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
    assert bundle.items[0].metadata["snippet_is_not_evidence"] is True


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
    assert "also_bookmarked=False" in chunk.chunk_text
    assert "id=media-1" in chunk.chunk_text
    assert "url=https://example.test/image.jpg" in chunk.chunk_text
    assert citation.chunk_id == chunk.chunk_id
    assert citation.source_url == "https://x.com/a/status/tweet-1"
    assert citation.evidence_status == "fact"
    assert chunk.metadata["document_id"] == chunk.source_id
    assert chunk.metadata["source_id"] == chunk.source_id
    assert chunk.metadata["source_kind"] == "local_x_db"
    assert chunk.metadata["source_url"] == chunk.source_url
    assert chunk.metadata["source_doc_hash"]
    assert chunk.metadata["source_bundle_id"]
    assert chunk.metadata["freshness_status"] in {"active", "recent", "possibly_stale"}
    assert citation.metadata["document_id"] == chunk.metadata["document_id"]
    assert citation.metadata["source_doc_hash"] == chunk.metadata["source_doc_hash"]
    assert citation.metadata["source_bundle_id"] == chunk.metadata["source_bundle_id"]

    with sqlite3.connect(db_path) as conn:
        search_runs = conn.execute("SELECT COUNT(*) FROM memory_search_runs").fetchone()[0]
        search_results = conn.execute("SELECT COUNT(*) FROM memory_search_results").fetchone()[0]
        first_result = conn.execute(
            """
            SELECT rank, doc_id, source_kind, provider_role, evidence_status, metadata_json
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
        first_result[5],
    )
    assert json.loads(first_result[5])["engine_contributions"]
    assert chunks == len(bundle.context_chunks)
    assert citations == len(bundle.citation_annotations)
    assert answers == 0
    assert workflows == 0


def test_context_budget_offloads_large_chunk_text_with_restore_pointer(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "x.sqlite3"
    _seed_db(db_path)
    build_memory_corpus(db_path)

    bundle = build_context_bundle(
        db_path,
        "強化学習 ロボット",
        limit=1,
        doc_type="bookmark_doc",
        store=False,
    )
    long_text = bundle.context_chunks[0].chunk_text + "\n" + ("long context " * 200)
    long_chunk = replace(bundle.context_chunks[0], chunk_text=long_text)
    long_bundle = replace(bundle, context_chunks=(long_chunk,))
    policy = ContextBudgetPolicy(
        max_output_chars=900,
        max_inline_chunk_chars=120,
        preview_chars=40,
        offload_dir=tmp_path / "offloads",
    )

    payload = json.loads(context_bundle_json(long_bundle, budget_policy=policy))
    pointer = payload["context_chunks"][0]["metadata"]["offload_pointer"]
    artifact = json.loads(Path(pointer["artifact_path"]).read_text(encoding="utf-8"))

    assert payload["context_budget"]["offloaded_item_count"] == 1
    assert payload["context_budget"]["non_destructive"] is True
    assert "context text offloaded" in payload["context_chunks"][0]["chunk_text"]
    assert pointer["sha256"] == artifact["pointer"]["sha256"]
    assert pointer["artifact_kind"] == "context_offload"
    assert pointer["owner_plane"] == "research_x_runtime"
    assert pointer["not_evidence"] is True
    assert payload["context_chunks"][0]["metadata"]["not_evidence"] is True
    assert payload["context_chunks"][0]["metadata"]["evidence_status"] == "preview_only"
    assert artifact["not_evidence"] is True
    assert artifact["content"] == long_text
    assert artifact["source_anchor"]["chunk_id"] == long_chunk.chunk_id
    assert artifact["source_anchor"]["citation_refs"][0]["citation_id"]
    assert long_bundle.context_chunks[0].chunk_text == long_text


def test_context_budget_noops_without_policy(tmp_path: Path) -> None:
    db_path = tmp_path / "x.sqlite3"
    _seed_db(db_path)
    build_memory_corpus(db_path)

    bundle = build_context_bundle(db_path, "強化学習 ロボット", limit=1, store=False)

    payload = json.loads(context_bundle_json(bundle))

    assert "context_budget" not in payload
    assert payload["context_chunks"][0]["chunk_text"] == bundle.context_chunks[0].chunk_text


def test_context_budget_can_budget_nested_workflow_like_payload(tmp_path: Path) -> None:
    payload = {
        "workflow_id": "workflow-test",
        "context_bundle": {
            "run_id": "context-test",
            "context_chunks": [
                {
                    "chunk_id": "chunk-test",
                    "source_kind": "local_x_db",
                    "source_id": "doc-1",
                    "source_url": "https://x.com/a/status/1",
                    "chunk_text": "nested context " * 120,
                    "metadata": {},
                }
            ],
            "citation_annotations": [
                {
                    "citation_id": "citation-test",
                    "chunk_id": "chunk-test",
                    "source_kind": "local_x_db",
                    "source_id": "doc-1",
                    "source_url": "https://x.com/a/status/1",
                    "field_path": "context_chunks[0]",
                    "evidence_status": "fact",
                }
            ],
        },
    }
    policy = ContextBudgetPolicy(
        max_output_chars=500,
        max_inline_chunk_chars=80,
        preview_chars=30,
        offload_dir=tmp_path / "offloads",
    )

    budgeted = budget_json_payload(payload, policy=policy, payload_kind="memory_workflow")
    pointer = budgeted.payload["context_bundle"]["context_chunks"][0]["metadata"][
        "offload_pointer"
    ]

    assert budgeted.payload["context_budget"]["payload_kind"] == "memory_workflow"
    assert pointer["artifact_kind"] == "context_offload"
    assert pointer["not_evidence"] is True
    assert pointer["citation_refs"][0]["citation_id"] == "citation-test"
    assert Path(pointer["artifact_path"]).exists()


def test_memory_context_cli_writes_budgeted_output(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    db_path = tmp_path / "x.sqlite3"
    _seed_db(db_path)
    build_memory_corpus(db_path)

    exit_code = main(
        [
            "memory",
            "context",
            "--db",
            str(db_path),
            "--query",
            "強化学習 ロボット",
            "--limit",
            "1",
            "--no-store",
            "--context-budget-max-chars",
            "900",
            "--context-budget-chunk-chars",
            "80",
            "--context-budget-preview-chars",
            "30",
            "--context-offload-dir",
            str(tmp_path / "offloads"),
        ]
    )
    output = capsys.readouterr().out
    payload = json.loads(output)
    pointer = payload["context_chunks"][0]["metadata"]["offload_pointer"]

    assert exit_code == 0
    assert payload["context_budget"]["offloaded_item_count"] >= 1
    assert pointer["artifact_kind"] == "context_offload"
    assert pointer["not_evidence"] is True
    assert Path(pointer["artifact_path"]).exists()


def test_answer_and_workflow_json_accept_context_budget_policy(tmp_path: Path) -> None:
    db_path = tmp_path / "x.sqlite3"
    _seed_db(db_path)
    build_memory_corpus(db_path)
    policy = ContextBudgetPolicy(
        max_output_chars=900,
        max_inline_chunk_chars=80,
        preview_chars=30,
        offload_dir=tmp_path / "offloads",
    )

    answer = build_memory_answer(
        db_path,
        "強化学習 ロボット",
        limit=1,
        answer_provider="fake",
        store=False,
    )
    workflow = run_memory_workflow(
        db_path,
        "強化学習 ロボット",
        limit=1,
        answer_provider="none",
        store=False,
    )

    answer_payload = json.loads(answer_json(answer, budget_policy=policy))
    workflow_payload = json.loads(workflow_json(workflow, budget_policy=policy))

    assert answer_payload["context_budget"]["payload_kind"] == "memory_answer"
    assert workflow_payload["context_budget"]["payload_kind"] == "memory_workflow"
    assert answer_payload["context_budget"]["offloaded_item_count"] >= 1
    assert workflow_payload["context_budget"]["offloaded_item_count"] >= 1


def test_route_context_policy_compares_stale_observation_variants() -> None:
    report = evaluate_route_context_policy(route="local_memory_search")
    payload = json.loads(context_policy_eval_json(report))
    variants = {variant.variant: variant for variant in report.variants}

    assert report.status == "ok"
    assert report.baseline_variant == "full_history"
    assert report.recommended_variant == "masked_history"
    assert report.global_masking_allowed is False
    assert payload["metadata"]["fixture"] == "stale_observation_context_policy"

    assert variants["full_history"].answer_status == "needs_review"
    assert variants["full_history"].unsupported_context_count == 1
    assert variants["summary_history"].stale_observation_count == 2
    assert variants["offloaded_history"].source_refs_preserved is True
    assert variants["masked_history"].answer_status == "ok"
    assert variants["masked_history"].route_specific_masking_candidate is True
    assert (
        "masking_is_route_specific_candidate_not_global_policy"
        in variants["masked_history"].notes
    )


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
    assert external_chunk.metadata["source_quality_class"] == "independent_secondary_candidate"
    assert "secondary_needs_cross_check" in external_chunk.metadata["source_risk_flags"]

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
    assert citation.metadata["document_id"]
    assert citation.metadata["source_doc_hash"]
    assert citation.metadata["source_bundle_id"]
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


def test_memory_answer_records_answerability_fixture_outcomes(tmp_path: Path) -> None:
    db_path = tmp_path / "x.sqlite3"
    answerable_bundle = _answerability_fixture_bundle("answerable")
    unanswerable_bundle = _answerability_fixture_bundle("unanswerable")
    conflicting_bundle = _answerability_fixture_bundle("conflicting")

    assessment = assess_answerability(
        question="ロボットについて説明して",
        chunks=answerable_bundle.context_chunks,
        citations=answerable_bundle.citation_annotations,
    )
    answerable = build_memory_answer(
        db_path,
        "ロボットについて説明して",
        context_bundle=answerable_bundle,
        answer_provider="fake",
        store=False,
    )
    unanswerable = build_memory_answer(
        db_path,
        "存在しない保存情報について説明して",
        context_bundle=unanswerable_bundle,
        answer_provider="fake",
        store=False,
    )
    conflicting = build_memory_answer(
        db_path,
        "同じ話の矛盾を確認して",
        context_bundle=conflicting_bundle,
        answer_provider="fake",
        store=False,
    )

    assert assessment.status == "answerable"
    assert answerable.status == "ok"
    assert answerable.structured["answerability"]["status"] == "answerable"
    assert answerable.citation_annotations

    assert unanswerable.status == "needs_review"
    assert unanswerable.structured["answerability"]["status"] == "unanswerable"
    assert unanswerable.structured["answerability"]["missing"] == ["context_chunks"]
    assert "根拠になるコンテキストが見つかりませんでした" in unanswerable.answer_text

    assert conflicting.status == "needs_review"
    assert conflicting.structured["answerability"]["status"] == "conflicting"
    assert conflicting.structured["answerability"]["conflicting_chunk_ids"]
    assert "矛盾または反対関係" in conflicting.answer_text
    assert len(conflicting.citation_annotations) == 2


def test_memory_relevance_support_fixture_lane_is_deterministic() -> None:
    fixtures = default_relevance_fixtures()
    report = run_relevance_fixture_report(fixtures)
    payload = json.loads(relevance_fixture_report_json(report))

    assert report.judge_id == LOCAL_JUDGE_CANDIDATE
    assert report.status == "ok"
    assert report.status_counts == {"ok": 6}
    assert set(report.label_counts) == {
        "relevant",
        "irrelevant",
        "duplicate",
        "conflict",
        "supports_claim",
        "does_not_support_claim",
    }
    assert payload["metadata"]["future_adapter_slot"] == LOCAL_JUDGE_CANDIDATE
    assert all(result.status == "ok" for result in report.results)
    assert all(result.judge_id == LOCAL_JUDGE_CANDIDATE for result in report.results)

    by_fixture = {result.fixture_id: result for result in report.results}
    assert by_fixture["supports_claim"].label == "supports_claim"
    assert by_fixture["does_not_support_claim"].label == "does_not_support_claim"
    assert by_fixture["conflict_claim"].label == "conflict"
    assert by_fixture["duplicate_same_source"].metadata["fixture_metadata"] == {}


def test_memory_relevance_fixture_rejects_unknown_labels() -> None:
    fixture = RelevanceFixture(
        fixture_id="bad",
        query="robot",
        candidate_id="doc:bad",
        candidate_text="robot",
        expected_label="bosun_specific_label",
    )

    with pytest.raises(ValueError, match="unknown relevance fixture label"):
        judge_relevance_fixture(fixture)


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
    assert workflow.metadata["stop_condition_audit"] == {
        "stop_reason": "enough_evidence",
        "local_evidence_sufficient": True,
        "searched_after_sufficient_evidence": False,
        "redundant_search_count": 0,
        "wants_external_context": False,
        "has_local_context": True,
        "has_external_context": False,
        "answer_status": None,
    }
    assert "stop_audit:" in format_workflow(workflow)

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


def test_memory_workflow_flags_redundant_search_after_sufficient_evidence(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "x.sqlite3"
    _seed_db(db_path)
    build_memory_corpus(db_path)
    build_memory_relations(db_path)

    workflow = run_memory_workflow(
        db_path,
        "強化学習 ロボット",
        limit=2,
        llm_context_provider="fake",
        store=False,
    )
    audit = workflow.metadata["stop_condition_audit"]

    assert workflow.stop_reason == "enough_evidence"
    assert workflow.route != "current_fact_check"
    assert [step.action for step in workflow.steps] == ["plan", "context", "llm_context"]
    assert audit["local_evidence_sufficient"] is True
    assert audit["searched_after_sufficient_evidence"] is True
    assert audit["redundant_search_count"] == 1


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
    assert workflow.metadata["stop_condition_audit"]["wants_external_context"] is True
    assert workflow.metadata["stop_condition_audit"]["redundant_search_count"] == 0
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


def test_memory_workflow_json_accepts_semantic_scores(tmp_path: Path) -> None:
    db_path = tmp_path / "x.sqlite3"
    _seed_db(db_path)
    build_memory_corpus(db_path)
    build_memory_relations(db_path)
    build_memory_embeddings(db_path, provider="local_hash", dimensions=64)

    workflow = run_memory_workflow(
        db_path,
        "強化学習 ロボット",
        limit=2,
        semantic_provider="local_hash",
        answer_provider="none",
    )
    payload = json.loads(workflow_json(workflow))

    assert payload["context_bundle"]["context_chunks"]
    assert payload["context_bundle"]["retrieved_hits"][0]["metadata"]["semantic"][
        "dimensions"
    ] == 64


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


def test_memory_workflow_tool_output_is_stable_ai_contract(tmp_path: Path) -> None:
    db_path = tmp_path / "x.sqlite3"
    _seed_db(db_path)
    build_memory_corpus(db_path)
    build_memory_relations(db_path)
    build_retrieval_text_profiles(db_path)

    workflow = run_memory_workflow(
        db_path,
        "強化学習 ロボット",
        limit=2,
        answer_provider="fake",
        max_context_chars=240,
    )
    output = workflow_tool_output(workflow)
    unvalidated_ai_payload = json.loads(workflow_tool_output_json(workflow))
    db_validated_payload = json.loads(workflow_tool_output_json(workflow, db_path=db_path))

    assert validate_tool_output(output) == []
    assert validate_tool_output(unvalidated_ai_payload) == []
    assert validate_tool_output_against_db(output, db_path) == []
    assert validate_tool_output(db_validated_payload) == []
    assert validate_tool_output_against_db(db_validated_payload, db_path) == []
    assert output.status == "answer"
    assert unvalidated_ai_payload["contract_version"] == "research-x-ai-tool-v1"
    assert unvalidated_ai_payload["tool_kind"] == "research_x.memory.workflow"
    assert unvalidated_ai_payload["status"] == "source_not_restored"
    assert unvalidated_ai_payload["evidence_level"] == "context_chunk"
    assert unvalidated_ai_payload["answer_text"] is None
    assert unvalidated_ai_payload["citations"]
    assert unvalidated_ai_payload["trace"]["route"] == workflow.route
    assert unvalidated_ai_payload["trace"]["provider_gate"]["required"] is False
    assert unvalidated_ai_payload["trace"]["db_backed_restoration_validation"][
        "status"
    ] == "missing_db_path"
    assert unvalidated_ai_payload["trace"]["codex_bridge"][
        "contract_version"
    ] == "research-x-codex-bridge-v1"
    assert "codex_transcript_included" not in unvalidated_ai_payload["trace"]
    assert db_validated_payload["status"] == "answer"
    assert db_validated_payload["evidence_level"] == "citation_ready"
    assert db_validated_payload["answer_text"]
    assert all(citation["citation_ready"] for citation in db_validated_payload["citations"])
    assert db_validated_payload["trace"]["db_backed_restoration_validation"] == {
        "status": "passed",
        "required_for_answer": True,
        "error_count": 0,
        "errors": [],
    }


def test_memory_workflow_tool_output_marks_provider_gap_without_citation_promotion(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "x.sqlite3"
    _seed_db(db_path)
    build_memory_corpus(db_path)
    build_memory_relations(db_path)

    workflow = run_memory_workflow(
        db_path,
        "強化学習 ロボット 今も正しい？",
        limit=2,
        answer_provider="none",
        llm_context_provider="none",
    )
    payload = workflow_tool_output(workflow).as_dict()

    assert validate_tool_output(payload) == []
    assert payload["status"] == "provider_gated"
    assert payload["evidence_level"] == "context_chunk"
    assert payload["trace"]["provider_gate"]["required"] is True
    assert payload["trace"]["skip_reason"] == "external_context_needed"


def test_memory_workflow_cli_can_emit_tool_json(tmp_path: Path, capsys) -> None:
    db_path = tmp_path / "x.sqlite3"
    _seed_db(db_path)
    build_memory_corpus(db_path)
    build_memory_relations(db_path)
    build_retrieval_text_profiles(db_path)

    assert (
        main(
            [
                "memory",
                "workflow",
                "--db",
                str(db_path),
                "--query",
                "強化学習 ロボット",
                "--answer-provider",
                "fake",
                "--store",
                "--allow-fixture-provider",
                "--tool-json",
            ]
        )
        == 0
    )

    payload = json.loads(capsys.readouterr().out)
    assert validate_tool_output(payload) == []
    assert validate_tool_output_against_db(payload, db_path) == []
    assert payload["contract_version"] == "research-x-ai-tool-v1"
    assert payload["status"] == "answer"
    assert payload["trace"]["db_backed_restoration_validation"]["status"] == "passed"


def test_memory_workflow_route_does_not_treat_recent_as_fact_check() -> None:
    recent_learning = plan_workflow_route(
        build_query_plan("最近保存した強化学習とロボット系の情報を出して")
    )
    current_fact = plan_workflow_route(build_query_plan("昔保存したこの技術情報、今も正しい？"))
    contradiction_fact = plan_workflow_route(
        build_query_plan("同じ話で反対意見や矛盾している保存投稿はある？")
    )
    media_quote = plan_workflow_route(
        build_query_plan("引用tweetの中にある画像付き投稿を引用関係ごと出して")
    )

    assert recent_learning.route == "learning_map"
    assert recent_learning.recommended_doc_types[0] == "topic_thread"
    assert current_fact.route == "current_fact_check"
    assert current_fact.wants_external_context is True
    assert contradiction_fact.route == "current_fact_check"
    assert media_quote.route == "media_context"


def test_memory_query_plan_handles_broad_topic_scope_and_contradiction_anchors() -> None:
    broad_plan = build_query_plan("DB 全体で最近増えている関心領域を出して")
    contradiction_anchors = strong_anchor_terms_for_query(
        "同じ話で反対意見や矛盾している保存投稿はある？"
    )

    assert "DB" not in broad_plan.search_terms
    assert "DB" not in broad_plan.exact_terms
    assert broad_plan.doc_type_weights["topic_thread"] >= 3.0
    assert {"関心", "領域", "保存"}.issubset(set(broad_plan.search_terms))
    assert {"反対", "矛盾"}.issubset(set(contradiction_anchors))


def test_memory_eval_records_route_level_fields(tmp_path: Path) -> None:
    db_path = tmp_path / "x.sqlite3"
    _seed_db(db_path)
    build_memory_corpus(db_path)
    build_memory_relations(db_path)

    results = run_memory_eval(db_path, limit=2)
    by_route = {result.route: result for result in results}

    assert by_route["place_recall"].expected_route == "place_recall"
    assert by_route["place_recall"].question_type == "set_recall"
    assert by_route["place_recall"].context_chunks > 0
    assert "local_x_db" in by_route["place_recall"].source_kinds
    assert by_route["place_recall"].answer_status == "ok"
    assert by_route["place_recall"].answerability_status == "answerable"
    assert by_route["place_recall"].answer_citations > 0
    assert by_route["place_recall"].searched_after_sufficient_evidence is False
    assert by_route["place_recall"].redundant_search_count == 0
    assert by_route["learning_map"].expected_route == "learning_map"
    assert by_route["company_event"].expected_route == "company_event"
    assert by_route["current_fact_check"].stop_reason in {
        "external_context_needed",
        "no_local_evidence",
    }
    no_answer_results = run_memory_eval(db_path, limit=1, answer_provider="none")
    assert all(result.answer_status is None for result in no_answer_results)
    assert all(result.answerability_status is None for result in no_answer_results)
    false_premise = next(
        result
        for result in results
        if result.question_type == "abstention_false_premise"
    )
    assert false_premise.answer_status == "needs_review"
    assert false_premise.answerability_status == "unanswerable"
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
                "question_type": "multi_hop_evidence",
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
    assert custom_results[0].question_type == "multi_hop_evidence"
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
    assert loaded_run["results"][0]["question_type"] == "multi_hop_evidence"


def test_memory_eval_loads_source_adoption_contract_fields(tmp_path: Path) -> None:
    cases_path = tmp_path / "cases.jsonl"
    cases_path.write_text(
        json.dumps(
            {
                "query": "根拠tweetと引用元を明示して説明して",
                "question_type": "citation_required",
                "required_any_terms": ["根拠", "tweet"],
                "expected_answerability_status": "answerable",
                "min_answer_citations": 1,
                "required_source_kinds": ["local_x_db"],
                "allow_search_after_sufficient_evidence": False,
                "max_redundant_search_count": 0,
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    case = load_eval_cases(cases_path)[0]

    assert case.expected_answerability_status == "answerable"
    assert case.min_answer_citations == 1
    assert case.required_source_kinds == ("local_x_db",)
    assert case.allow_search_after_sufficient_evidence is False
    assert case.max_redundant_search_count == 0

    for status in ("partially_supported", "stale_only", "citation_missing"):
        status_path = tmp_path / f"{status}.jsonl"
        status_path.write_text(
            json.dumps(
                {
                    "query": status,
                    "required_any_terms": [],
                    "expected_answerability_status": status,
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        assert load_eval_cases(status_path)[0].expected_answerability_status == status

    bad_path = tmp_path / "bad-cases.jsonl"
    bad_path.write_text(
        json.dumps(
            {
                "query": "bad",
                "required_any_terms": [],
                "expected_answerability_status": "maybe",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="expected_answerability_status"):
        load_eval_cases(bad_path)


def test_memory_eval_enforces_answerability_fixture_contracts(tmp_path: Path) -> None:
    db_path = tmp_path / "x.sqlite3"
    answerable_bundle = _answerability_fixture_bundle("answerable")
    unanswerable_bundle = _answerability_fixture_bundle("unanswerable")
    conflicting_bundle = _answerability_fixture_bundle("conflicting")
    answerable = build_memory_answer(
        db_path,
        "ロボットについて説明して",
        context_bundle=answerable_bundle,
        store=False,
    )
    unanswerable = build_memory_answer(
        db_path,
        "存在しない保存情報について説明して",
        context_bundle=unanswerable_bundle,
        store=False,
    )
    conflicting = build_memory_answer(
        db_path,
        "同じ話の矛盾を確認して",
        context_bundle=conflicting_bundle,
        store=False,
    )
    answerable_case = EvalCase(
        query="ロボットについて説明して",
        required_any_terms=("ロボット",),
        question_type="citation_required",
        expected_answerability_status="answerable",
        min_answer_citations=1,
        required_source_kinds=("local_x_db",),
        allow_search_after_sufficient_evidence=False,
        max_redundant_search_count=0,
        min_hit_score=0.5,
    )
    unanswerable_case = EvalCase(
        query="存在しない保存情報について説明して",
        required_any_terms=(),
        question_type="abstention_false_premise",
        expected_stop_reasons=("no_local_evidence",),
        expected_answerability_status="unanswerable",
        min_answer_citations=0,
        min_hit_score=0.0,
    )
    conflicting_case = EvalCase(
        query="同じ話の矛盾を確認して",
        required_any_terms=("ロボット",),
        question_type="contradiction_support",
        expected_answerability_status="conflicting",
        min_answer_citations=2,
        required_source_kinds=("local_x_db",),
        min_hit_score=0.5,
    )

    answerable_result = memory_evals._evaluate_case(  # noqa: SLF001
        answerable_case,
        _fixture_workflow(answerable_case.query, answerable_bundle, answerable),
        _valid_fixture_hits(answerable_bundle),
    )
    unanswerable_result = memory_evals._evaluate_case(  # noqa: SLF001
        unanswerable_case,
        _fixture_workflow(
            unanswerable_case.query,
            unanswerable_bundle,
            unanswerable,
            stop_reason="no_local_evidence",
        ),
        [],
    )
    conflicting_result = memory_evals._evaluate_case(  # noqa: SLF001
        conflicting_case,
        _fixture_workflow(conflicting_case.query, conflicting_bundle, conflicting),
        _valid_fixture_hits(conflicting_bundle),
    )

    assert answerable_result.status == "ok"
    assert answerable_result.answerability_status == "answerable"
    assert answerable_result.answer_citations == 1

    assert unanswerable_result.status == "ok"
    assert unanswerable_result.answerability_status == "unanswerable"
    assert unanswerable_result.answer_citations == 0

    assert conflicting_result.status == "needs_review"
    assert conflicting_result.answerability_status == "conflicting"
    assert conflicting_result.answer_citations == 2
    assert not any(
        note.startswith("answerability mismatch") for note in conflicting_result.notes
    )


def test_memory_eval_fails_source_adoption_contract_mismatches(tmp_path: Path) -> None:
    db_path = tmp_path / "x.sqlite3"
    answerable_bundle = _answerability_fixture_bundle("answerable")
    answerable = build_memory_answer(
        db_path,
        "ロボットについて説明して",
        context_bundle=answerable_bundle,
        store=False,
    )
    case = EvalCase(
        query="ロボットについて説明して",
        required_any_terms=("ロボット",),
        question_type="citation_required",
        expected_answerability_status="unanswerable",
        min_answer_citations=9,
        required_source_kinds=("external_reader",),
        allow_search_after_sufficient_evidence=False,
        max_redundant_search_count=0,
        min_hit_score=0.5,
    )

    result = memory_evals._evaluate_case(  # noqa: SLF001
        case,
        _fixture_workflow(
            case.query,
            answerable_bundle,
            answerable,
            metadata={
                "stop_condition_audit": {
                    "searched_after_sufficient_evidence": True,
                    "redundant_search_count": 1,
                }
            },
        ),
        _valid_fixture_hits(answerable_bundle),
    )

    assert result.status == "fail"
    assert any(note.startswith("answerability mismatch") for note in result.notes)
    assert any(note.startswith("answer citations below threshold") for note in result.notes)
    assert any(note.startswith("required source kind missing") for note in result.notes)
    assert "searched after sufficient evidence" in result.notes
    assert any(note.startswith("redundant search count above threshold") for note in result.notes)


def test_memory_eval_requires_answer_citations_to_restore_to_chunks(tmp_path: Path) -> None:
    db_path = tmp_path / "x.sqlite3"
    answerable_bundle = _answerability_fixture_bundle("answerable")
    answerable = build_memory_answer(
        db_path,
        "ロボットについて説明して",
        context_bundle=answerable_bundle,
        store=False,
    )
    broken_citation = replace(
        answerable.citation_annotations[0],
        chunk_id="missing:chunk",
        source_kind="external_reader",
    )
    answer = replace(answerable, citation_annotations=(broken_citation,))
    case = EvalCase(
        query="ロボットについて説明して",
        required_any_terms=("ロボット",),
        question_type="citation_required",
        expected_answerability_status="answerable",
        min_answer_citations=1,
        required_source_kinds=("local_x_db",),
        min_hit_score=0.5,
    )

    result = memory_evals._evaluate_case(  # noqa: SLF001
        case,
        _fixture_workflow(case.query, answerable_bundle, answer),
        _valid_fixture_hits(answerable_bundle),
    )

    assert result.status == "fail"
    assert any(note.startswith("citation source not restored") for note in result.notes)
    assert any(note.startswith("required source kind missing") for note in result.notes)


def test_memory_eval_has_real_partial_stale_and_citation_missing_fixtures(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "x.sqlite3"
    fixture_specs = (
        ("partially_supported", "needs_review", 1),
        ("stale_only", "needs_review", 1),
        ("citation_missing", "needs_review", 0),
    )

    for expected_status, expected_answer_status, min_citations in fixture_specs:
        bundle = _answerability_fixture_bundle(expected_status)
        assessment = assess_answerability(
            question=f"fixture {expected_status}",
            chunks=bundle.context_chunks,
            citations=bundle.citation_annotations,
        )
        answer = build_memory_answer(
            db_path,
            f"fixture {expected_status}",
            context_bundle=bundle,
            store=False,
        )
        case = EvalCase(
            query=f"fixture {expected_status}",
            required_any_terms=("ロボット",),
            question_type="citation_required",
            expected_answerability_status=expected_status,
            min_answer_citations=min_citations,
            required_source_kinds=("local_x_db",) if min_citations else (),
            min_hit_score=0.5,
        )

        result = memory_evals._evaluate_case(  # noqa: SLF001
            case,
            _fixture_workflow(case.query, bundle, answer),
            _valid_fixture_hits(bundle),
        )

        assert assessment.status == expected_status
        assert answer.structured["answerability"]["status"] == expected_status
        assert answer.status == expected_answer_status
        assert result.answerability_status == expected_status
        assert result.answer_citations == min_citations


def test_memory_question_type_catalog_is_machine_readable() -> None:
    ids = known_question_type_ids()
    rows = question_types_as_dicts()

    assert "single_fact_conditioned" in ids
    assert "media_grounded" in ids
    assert "abstention_false_premise" in ids
    assert len(ids) == len(set(ids))
    assert all(row["required_capabilities"] for row in rows)


def test_memory_default_eval_cases_cover_question_catalog() -> None:
    expected = set(known_question_type_ids())
    covered = {case.question_type for case in DEFAULT_EVAL_CASES}

    assert covered == expected


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
    assert place_bundle["hits"][0]["evidence"]["derived"]["source_tweet_ids"]

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


def test_reader_extract_jina_provider_uses_reader_endpoint(
    tmp_path: Path,
    monkeypatch,
) -> None:
    db_path = tmp_path / "x.sqlite3"
    captured = {}

    def fake_read_url(url, *, timeout_seconds, user_agent, max_bytes, extra_headers=None):
        captured["url"] = url
        captured["headers"] = extra_headers or {}
        return HttpResponse(
            final_url=url,
            status_code=200,
            content_type="text/plain",
            body=b"Jina extracted markdown for pizza.",
        )

    monkeypatch.setenv("JINA_API_KEY", "jina-key")
    monkeypatch.setattr("research_x.memory.reader._read_url", fake_read_url)

    bundle = extract_url_to_context(
        db_path,
        "https://example.com/pizza",
        provider="jina",
        title="Pizza",
    )

    assert captured["url"] == "https://r.jina.ai/https://example.com/pizza"
    assert captured["headers"]["Authorization"] == "Bearer jina-key"
    assert bundle.provider == "jina"
    assert bundle.page.url == "https://example.com/pizza"
    assert "Jina extracted markdown" in bundle.page.text


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
    assert bundles[0].context_chunk["metadata"]["external_snippet_citation_excluded"] is True
    assert bundles[0].context_chunk["metadata"]["external_rank_citation_excluded"] is True


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
    assert request["content"]["parts"][0]["text"].startswith(
        "task: question answering | query:"
    )


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


def test_voyage_embedding_request_uses_retrieval_input_type(monkeypatch) -> None:
    captured = {}

    def fake_post_json(url, payload, *, headers, timeout_seconds, retries=3):
        captured["url"] = url
        captured["payload"] = payload
        captured["headers"] = headers
        return {"data": [{"index": 0, "embedding": [0.1, 0.2, 0.3]}]}

    monkeypatch.setenv("VOYAGE_API_KEY", "fake-key")
    monkeypatch.setattr(embeddings, "_post_json", fake_post_json)

    spec = embeddings.resolve_embedding_spec(
        provider="voyage",
        model="voyage-3.5",
        dimensions=3,
    )
    vector = embeddings._VoyageEmbedder(spec).embed_texts(  # noqa: SLF001
        ["robot learning"],
        task_type="RETRIEVAL_QUERY",
    )[0]

    assert vector
    assert captured["url"] == "https://api.voyageai.com/v1/embeddings"
    assert captured["headers"]["Authorization"] == "Bearer fake-key"
    assert captured["payload"] == {
        "model": "voyage-3.5",
        "input": ["robot learning"],
        "input_type": "query",
        "truncation": True,
        "output_dtype": "float",
        "output_dimension": 3,
    }


def test_cohere_embedding_request_uses_v2_embed_shape(monkeypatch) -> None:
    captured = {}

    def fake_post_json(url, payload, *, headers, timeout_seconds, retries=3):
        captured["url"] = url
        captured["payload"] = payload
        captured["headers"] = headers
        return {"embeddings": {"float": [[0.1, 0.2, 0.3]]}}

    monkeypatch.setenv("COHERE_API_KEY", "fake-key")
    monkeypatch.setattr(embeddings, "_post_json", fake_post_json)

    spec = embeddings.resolve_embedding_spec(
        provider="cohere",
        model="embed-v4.0",
        dimensions=3,
    )
    vector = embeddings._CohereEmbedder(spec).embed_texts(  # noqa: SLF001
        ["robot learning"],
        task_type="RETRIEVAL_DOCUMENT",
    )[0]

    assert vector
    assert captured["url"] == "https://api.cohere.com/v2/embed"
    assert captured["headers"]["Authorization"] == "Bearer fake-key"
    assert captured["payload"] == {
        "model": "embed-v4.0",
        "texts": ["robot learning"],
        "input_type": "search_document",
        "embedding_types": ["float"],
        "truncate": "END",
        "output_dimension": 3,
    }


def test_mistral_embedding_request_omits_unsupported_output_dimension(monkeypatch) -> None:
    captured = {}

    def fake_post_json(url, payload, *, headers, timeout_seconds, retries=3):
        captured["url"] = url
        captured["payload"] = payload
        captured["headers"] = headers
        return {"data": [{"index": 0, "embedding": [0.1, 0.2, 0.3]}]}

    monkeypatch.setenv("MISTRAL_API_KEY", "fake-key")
    monkeypatch.setattr(embeddings, "_post_json", fake_post_json)

    spec = embeddings.resolve_embedding_spec(
        provider="mistral",
        model="mistral-embed",
        dimensions=3,
    )
    vector = embeddings._MistralEmbedder(spec).embed_texts(  # noqa: SLF001
        ["robot learning"],
        task_type="RETRIEVAL_DOCUMENT",
    )[0]

    assert vector
    assert captured["url"] == "https://api.mistral.ai/v1/embeddings"
    assert captured["headers"]["Authorization"] == "Bearer fake-key"
    assert captured["payload"] == {
        "model": "mistral-embed",
        "input": ["robot learning"],
        "encoding_format": "float",
    }


def test_jina_embedding_request_sets_retrieval_task(monkeypatch) -> None:
    captured = {}

    def fake_post_json(url, payload, *, headers, timeout_seconds, retries=3):
        captured["url"] = url
        captured["payload"] = payload
        captured["headers"] = headers
        return {"data": [{"index": 0, "embedding": [0.1, 0.2, 0.3]}]}

    monkeypatch.setenv("JINA_API_KEY", "fake-key")
    monkeypatch.setattr(embeddings, "_post_json", fake_post_json)

    spec = embeddings.resolve_embedding_spec(
        provider="jina",
        model="jina-embeddings-v3",
        dimensions=3,
    )
    vector = embeddings._JinaEmbedder(spec).embed_texts(  # noqa: SLF001
        ["robot learning"],
        task_type="RETRIEVAL_QUERY",
    )[0]

    assert vector
    assert captured["url"] == "https://api.jina.ai/v1/embeddings"
    assert captured["headers"]["Authorization"] == "Bearer fake-key"
    assert captured["headers"]["User-Agent"].startswith("research-x/")
    assert captured["payload"] == {
        "model": "jina-embeddings-v3",
        "input": ["robot learning"],
        "task": "retrieval.query",
        "embedding_type": "float",
        "normalized": True,
        "truncate": True,
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
    assert (
        main(
            [
                "memory",
                "embedding-estimate",
                "--db",
                str(db_path),
                "--provider",
                "voyage",
                "--dimensions",
                "1024",
                "--limit",
                "1",
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
    cli_bundle_dir = tmp_path / "c2s_cli_bundle"
    assert (
        main(
            [
                "memory",
                "export-corpus2skill",
                "--db",
                str(db_path),
                "--bundle-dir",
                str(cli_bundle_dir),
                "--doc-type",
                "bookmark_doc",
                "--limit",
                "2",
                "--openai-agent-yaml",
                "--hook-advisory",
            ]
        )
        == 0
    )
    assert (cli_bundle_dir / "agents" / "openai.yaml").exists()
    assert (cli_bundle_dir / "agents" / "hook_advisory.md").exists()
    assert (
        main(
            [
                "memory",
                "export-corpus2skill",
                "--db",
                str(db_path),
                "--out",
                str(tmp_path / "bad-corpus.jsonl"),
                "--openai-agent-yaml",
            ]
        )
        == 1
    )
    assert (
        main(
            [
                "memory",
                "export-corpus2skill",
                "--db",
                str(db_path),
                "--bundle-dir",
                str(tmp_path / "bad-c2s"),
                "--openai-agent-name",
                "custom-agent",
            ]
        )
        == 1
    )
    assert (
        main(
            [
                "memory",
                "export-corpus2skill",
                "--db",
                str(db_path),
                "--bundle-dir",
                str(tmp_path / "bad-agent-name"),
                "--openai-agent-yaml",
                "--openai-agent-name",
                "bad agent name",
            ]
        )
        == 1
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
    assert main(["memory", "question-types"]) == 0
    assert main(["memory", "retrieval-strategies", "--query", "英語論文 強化学習"]) == 0
    assert (
        main(
            [
                "memory",
                "retrieval-strategies",
                "--strategy",
                "api_embedding_portfolio",
            ]
        )
        == 0
    )
    assert (
        main(
            [
                "memory",
                "portfolio-eval",
                "--db",
                str(db_path),
                "--cases",
                str(cli_eval_cases),
                "--case-limit",
                "1",
                "--fast",
                "--limit",
                "1",
                "--arm-limit",
                "2",
                "--strategy",
                "general_memory",
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
    assert "single_fact_conditioned" in output
    assert "general_memory" in output
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
        == 0
    )
    captured = capsys.readouterr()
    assert "memory://fake-external-search" in captured.out
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
        == 0
    )
    captured = capsys.readouterr()
    assert "fake-llm-context" in captured.out
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
                "--store",
            ]
        )
        == 1
    )
    captured = capsys.readouterr()
    assert "diagnostic-only" in captured.err
    assert "Traceback" not in captured.err

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
                "--store",
            ]
        )
        == 1
    )
    captured = capsys.readouterr()
    assert "diagnostic-only" in captured.err

    _seed_db(db_path)
    build_memory_corpus(db_path)
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
                "--store",
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
                "--store",
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
                "--store",
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


def _answerability_fixture_bundle(kind: str) -> ContextBundle:
    run_id = f"answerability:{kind}"
    created_at = "2026-06-22T00:00:00+00:00"
    def _lineage(source_id: str) -> dict[str, str]:
        suffix = source_id.removeprefix("tweet:")
        return {
            "source_doc_hash": f"hash-{suffix}",
            "embedding_text_hash": f"embedding-{suffix}",
            "retrieval_text_hash": f"retrieval-{suffix}",
            "retrieval_text_profile": "full_text",
            "retrieval_profile_kind": "full_text",
            "retrieval_text_profile_id": f"profile-{suffix}",
            "source_bundle_id": f"bundle-{suffix}",
            "lineage_status": "restored",
            "restored_at": created_at,
        }

    if kind == "unanswerable":
        return ContextBundle(
            run_id=run_id,
            query="fixture unanswerable",
            query_plan={"fixture": "answerability"},
            parameters={"fixture_kind": kind},
            retrieved_hits=[],
            context_chunks=(),
            citation_annotations=(),
        )

    first_chunk_metadata = {
        "answerability_fixture": "answerable",
        **_lineage("tweet:answerable"),
    }
    if kind == "stale_only":
        first_chunk_metadata = {
            "answerability_fixture": "stale_only",
            "freshness_status": "stale",
            **_lineage("tweet:answerable"),
        }
    chunks = [
        ContextChunk(
            chunk_id=f"{run_id}:chunk:1",
            run_id=run_id,
            source_kind="local_x_db",
            source_id="tweet:answerable",
            source_url="https://x.com/a/status/answerable",
            provider="fixture",
            provider_role="context_builder",
            chunk_text="Text: ロボット実験の保存投稿には強化学習のメモが含まれます。",
            chunk_index=0,
            token_count=24,
            relevance_score=1.0,
            extractor_version="answerability-fixture-v1",
            created_at=created_at,
            metadata=first_chunk_metadata,
        )
    ]
    if kind in {"conflicting", "partially_supported"}:
        second_fixture = "conflicting" if kind == "conflicting" else "partially_supported"
        chunks.append(
            ContextChunk(
                chunk_id=f"{run_id}:chunk:2",
                run_id=run_id,
                source_kind="local_x_db",
                source_id="tweet:conflicting",
                source_url="https://x.com/b/status/conflicting",
                provider="fixture",
                provider_role="context_builder",
                chunk_text="Text: 別の保存投稿は同じ結論に反対する注意点を述べています。",
                chunk_index=1,
                token_count=25,
                relevance_score=0.9,
                extractor_version="answerability-fixture-v1",
                created_at=created_at,
                metadata={
                    "answerability_fixture": second_fixture,
                    **_lineage("tweet:conflicting"),
                },
            )
        )

    citations = tuple(
        CitationAnnotation(
            citation_id=f"{chunk.chunk_id}:citation",
            answer_id=None,
            chunk_id=chunk.chunk_id,
            source_kind=chunk.source_kind,
            source_id=chunk.source_id,
            source_url=chunk.source_url,
            title=chunk.source_id,
            field_path=f"context_chunks[{index}]",
            support_type=(
                "contradicts"
                if chunk.metadata["answerability_fixture"] == "conflicting"
                else "background"
            ),
            evidence_status=(
                "stale" if chunk.metadata["answerability_fixture"] == "stale_only" else "fact"
            ),
            confidence=1.0,
            created_at=created_at,
            metadata={
                "answerability_fixture": chunk.metadata["answerability_fixture"],
                **{
                    key: chunk.metadata[key]
                    for key in (
                        "source_doc_hash",
                        "embedding_text_hash",
                        "retrieval_text_hash",
                        "retrieval_text_profile",
                        "retrieval_profile_kind",
                        "retrieval_text_profile_id",
                        "source_bundle_id",
                        "lineage_status",
                        "restored_at",
                    )
                    if key in chunk.metadata
                },
            },
        )
        for index, chunk in enumerate(chunks)
        if kind not in {"citation_missing"}
        and not (
            kind == "partially_supported"
            and chunk.metadata["answerability_fixture"] == "partially_supported"
        )
    )
    return ContextBundle(
        run_id=run_id,
        query=f"fixture {kind}",
        query_plan={"fixture": "answerability"},
        parameters={"fixture_kind": kind},
        retrieved_hits=[
            {"doc_id": chunk.source_id, "compact_text": chunk.chunk_text}
            for chunk in chunks
        ],
        context_chunks=tuple(chunks),
        citation_annotations=citations,
    )


def _fixture_workflow(
    query: str,
    bundle: ContextBundle,
    answer,
    *,
    stop_reason: str = "enough_evidence",
    metadata: dict[str, object] | None = None,
) -> MemoryWorkflow:
    created_at = "2026-06-22T00:00:00+00:00"
    return MemoryWorkflow(
        workflow_id=f"{bundle.run_id}:workflow",
        query=query,
        route="local_memory_search",
        status="ok" if stop_reason == "enough_evidence" else "needs_review",
        stop_reason=stop_reason,
        started_at=created_at,
        finished_at=created_at,
        metadata=metadata or {},
        steps=(),
        context_bundle=bundle,
        answer=answer,
    )


def _valid_fixture_hits(bundle: ContextBundle) -> list[dict[str, object]]:
    hits: list[dict[str, object]] = []
    for chunk in bundle.context_chunks:
        hits.append(
            {
                "doc_id": chunk.source_id,
                "tweet_id": chunk.source_id.removeprefix("tweet:"),
                "doc_type": "tweet_doc",
                "title": chunk.source_id,
                "compact_text": chunk.chunk_text,
                "score": chunk.relevance_score,
                "matched_terms": ["ロボット"],
                "evidence": {"url": chunk.source_url},
                "metadata": {},
            }
        )
    return hits


def _write_cases(tmp_path: Path, cases: list[dict]) -> Path:
    path = tmp_path / "cases.json"
    path.write_text(json.dumps({"cases": cases}, ensure_ascii=False), encoding="utf-8")
    return path


def _count_table(db_path: Path, table: str) -> int:
    with sqlite3.connect(db_path) as conn:
        ensure_memory_schema(conn)
        return int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])


def _insert_provider_embedding_row(
    db_path: Path,
    *,
    provider: str,
    model: str,
    dimensions: int,
) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        ensure_memory_schema(conn)
        row = conn.execute(
            """
            SELECT doc_id, source_doc_hash, embedding_text_hash
            FROM memory_documents
            ORDER BY doc_id
            LIMIT 1
            """
        ).fetchone()
        assert row is not None
        now = "2026-06-27T00:00:00+00:00"
        conn.execute(
            """
            INSERT INTO memory_embeddings (
                doc_id, provider, model, dimensions, embedding_profile,
                text_template_version, embedding, source_doc_hash,
                embedded_text_hash, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                row["doc_id"],
                provider,
                model,
                dimensions,
                "general_memory",
                "memory-doc-embedding-v1",
                pack_embedding(_fixture_embedding(dimensions)),
                row["source_doc_hash"],
                row["embedding_text_hash"],
                now,
                now,
            ),
        )


def _fixture_embedding(dimensions: int) -> list[float]:
    vector = [0.0] * dimensions
    vector[0] = 1.0
    return vector


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
