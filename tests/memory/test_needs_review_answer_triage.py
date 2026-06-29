from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from research_x.memory.audit import audit_memory_db, audit_report_json, format_audit_report
from research_x.memory.schema import ensure_memory_schema


def test_memory_audit_triages_stored_needs_review_answers(tmp_path: Path) -> None:
    db_path = tmp_path / "x.sqlite3"
    with sqlite3.connect(db_path) as conn:
        ensure_memory_schema(conn)
        _insert_answer(
            conn,
            answer_id="answer:missing-citation",
            question="Why does this answer need citation review?",
            status="needs_review",
            structured={"answerability": {"status": "citation_missing"}},
        )
        _insert_answer(
            conn,
            answer_id="answer:conflict",
            question="Which conflicting source should win?",
            status="needs_review",
            structured={"answerability": {"status": "conflicting"}},
        )
        _insert_citation(conn, answer_id="answer:conflict")
        _insert_answer(
            conn,
            answer_id="answer:answerable-review",
            question="Why is this answerable row still marked needs_review?",
            status="needs_review",
            structured={"answerability": {"status": "answerable"}},
        )
        _insert_citation(
            conn,
            answer_id="answer:answerable-review",
            citation_id="citation:answerable-review",
            support_type="supports_answer",
        )
        _insert_answer(
            conn,
            answer_id="answer:ok",
            question="This stored answer is not part of needs_review triage",
            status="ok",
            structured={"answerability": {"status": "answerable"}},
        )

    report = audit_memory_db(db_path)

    triage = report.needs_review_answer_triage
    assert report.answer_status_counts["needs_review"] == 3
    assert triage["total"] == 3
    assert triage["reason_counts"]["answerability:citation_missing"] == 1
    assert triage["reason_counts"]["answerability:conflicting"] == 1
    assert triage["reason_counts"]["answerability:answerable"] == 1
    assert triage["reason_counts"]["citation_missing"] == 1
    assert triage["reason_counts"]["citation_not_ready"] == 1
    assert triage["reason_counts"]["needs_review_status_without_detected_blocker"] == 1
    assert len(triage["samples"]) == 3
    samples_by_id = {sample["answer_id"]: sample for sample in triage["samples"]}
    assert samples_by_id["answer:conflict"]["citation_count"] == 1
    assert "answer:ok" not in json.dumps(triage, ensure_ascii=False)

    payload = json.loads(audit_report_json(report))
    assert payload["needs_review_answer_triage"]["total"] == 3
    text = format_audit_report(report)
    assert "needs_review answer triage: total=3" in text


def _insert_answer(
    conn: sqlite3.Connection,
    *,
    answer_id: str,
    question: str,
    status: str,
    structured: dict[str, object],
) -> None:
    conn.execute(
        """
        INSERT INTO memory_answer_runs (
            answer_id, question, workflow_id, model, prompt_version,
            retrieval_config_json, answer_text, structured_json, status, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            answer_id,
            question,
            "workflow:triage",
            "fake-answer-v1",
            "memory-answer-v1",
            "{}",
            "Needs review [1]",
            json.dumps(structured, ensure_ascii=False, sort_keys=True),
            status,
            f"2026-06-27T00:00:0{0 if status == 'ok' else 1}+00:00",
        ),
    )


def _insert_citation(
    conn: sqlite3.Connection,
    *,
    answer_id: str,
    citation_id: str = "citation:conflict",
    support_type: str = "contradicts",
) -> None:
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
            citation_id,
            answer_id,
            f"chunk:{answer_id}",
            "external_web",
            f"source:{answer_id}",
            "https://example.test/conflict",
            "Conflict fixture",
            13,
            16,
            "chunk_text",
            support_type,
            "fact",
            1.0,
            "2026-06-27T00:00:01+00:00",
            json.dumps({"marker": "[1]"}, ensure_ascii=False, sort_keys=True),
        ),
    )
