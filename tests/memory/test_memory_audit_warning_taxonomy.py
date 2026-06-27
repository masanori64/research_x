from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent))

from test_operational_trace_persistence import _seed_memory_db

from research_x.memory import embeddings
from research_x.memory.answer import build_memory_answer
from research_x.memory.api_budget import api_budget_context, upsert_api_price
from research_x.memory.audit import audit_memory_db
from research_x.memory.corpus import build_memory_corpus
from research_x.memory.embeddings import build_memory_embeddings
from research_x.memory.relations import build_memory_relations
from research_x.memory.schema import ensure_memory_schema


def test_audit_taxonomy_treats_local_hash_as_expected_provider_gate(
    tmp_path: Path,
) -> None:
    db_path = _seed_ready_memory_db(tmp_path)
    build_memory_embeddings(db_path, provider="local_hash", dimensions=64)

    report = audit_memory_db(db_path)
    warning = _warning_by_code(report.structured_warnings, "local_hash_diagnostic_only")

    assert warning["severity"] == "expected"
    assert warning["category"] == "provider_gated_expected"
    assert warning["blocking_for_local_no_provider"] is False
    assert warning["blocking_for_provider_production"] is True
    assert report.readiness["local_no_provider_ready"] is True
    assert report.readiness["provider_production_ready"] is False
    assert report.readiness["blocking_issue_count"] == 0
    assert report.readiness["expected_gated_warning_count"] >= 1


def test_audit_taxonomy_treats_provider_rows_as_expected_quarantine(
    tmp_path: Path,
    monkeypatch,
) -> None:
    db_path = _seed_ready_memory_db(tmp_path)

    def fake_post_json(url, payload, *, headers, timeout_seconds, retries=3):
        del url, headers, timeout_seconds, retries
        return {
            "data": [
                {"index": index, "embedding": [1.0, 0.0, 0.0]}
                for index, _text in enumerate(payload["input"])
            ]
        }

    monkeypatch.setenv("CUSTOM_EMBED_KEY", "fake-key")
    monkeypatch.setattr(embeddings, "_post_json", fake_post_json)
    upsert_api_price(
        db_path,
        provider="openai_compatible",
        model="custom-embedding",
        operation="embedding",
        unit="call",
        usd_per_unit=0.0,
        source_url="fixture://audit-warning-taxonomy",
        notes="provider-free monkeypatched fixture",
    )
    with api_budget_context(
        db_path=db_path,
        run_id="audit-provider-row-fixture",
        provider_quota_approval={
            "provider_quota_approval_id": "fixture-approval",
            "provider": "openai_compatible",
            "model": "custom-embedding",
            "operation": "embedding",
            "max_calls": 10,
            "max_cost_usd": 0.0,
            "price_source": "fixture://audit-warning-taxonomy",
            "approved_scope": "*",
            "approved_at": "2026-06-27T00:00:00+00:00",
        },
        no_quota_freeze_active=False,
    ):
        build_memory_embeddings(
            db_path,
            provider="openai_compatible",
            model="custom-embedding",
            dimensions=3,
            api_key_env="CUSTOM_EMBED_KEY",
            base_url="https://embeddings.example/v1/embeddings",
            allow_provider_quota=True,
        )

    report = audit_memory_db(db_path)
    warning = _warning_by_code(
        report.structured_warnings,
        "provider_embedding_rows_quarantined",
    )

    assert warning["severity"] == "expected"
    assert warning["category"] == "provider_gated_expected"
    assert warning["gate"] == "provider_quota_freeze"
    assert warning["blocking_for_local_no_provider"] is False
    assert warning["blocking_for_provider_production"] is True
    assert report.readiness["local_no_provider_ready"] is True
    assert report.readiness["provider_production_ready"] is False
    assert report.readiness["blocking_issue_count"] == 0


def test_audit_taxonomy_marks_claim_citation_issue_blocking(
    tmp_path: Path,
) -> None:
    db_path = _seed_ready_memory_db(tmp_path)
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
    warning = _warning_by_code(report.structured_warnings, "claim_citation_issues")

    assert warning["severity"] == "warning"
    assert warning["category"] == "blocking_issue"
    assert warning["gate"] == "citation_integrity"
    assert warning["blocking_for_local_no_provider"] is True
    assert warning["blocking_for_provider_production"] is True
    assert report.readiness["local_no_provider_ready"] is False
    assert report.readiness["provider_production_ready"] is False
    assert report.readiness["blocking_issue_count"] >= 1


def _seed_ready_memory_db(tmp_path: Path) -> Path:
    db_path = _seed_memory_db(tmp_path)
    build_memory_corpus(db_path)
    build_memory_relations(db_path)
    return db_path


def _warning_by_code(
    warnings: tuple[dict[str, object], ...],
    code: str,
) -> dict[str, object]:
    for warning in warnings:
        if warning["code"] == code:
            return warning
    raise AssertionError(f"missing warning code: {code}; got {[item['code'] for item in warnings]}")
