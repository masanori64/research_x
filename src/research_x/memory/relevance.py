from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import asdict, dataclass
from typing import Any

LOCAL_JUDGE_CANDIDATE = "local_judge_candidate"
RELEVANCE_LABELS = {
    "relevant",
    "irrelevant",
    "duplicate",
    "conflict",
    "supports_claim",
    "does_not_support_claim",
}


@dataclass(frozen=True)
class RelevanceFixture:
    fixture_id: str
    query: str
    candidate_id: str
    candidate_text: str
    expected_label: str
    claim: str | None = None
    duplicate_of: str | None = None
    metadata: dict[str, Any] | None = None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class LocalJudgeResult:
    fixture_id: str
    candidate_id: str
    judge_id: str
    label: str
    expected_label: str
    status: str
    score: float
    reason: str
    metadata: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RelevanceFixtureReport:
    judge_id: str
    status: str
    results: tuple[LocalJudgeResult, ...]
    label_counts: dict[str, int]
    status_counts: dict[str, int]
    metadata: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["results"] = [result.as_dict() for result in self.results]
        return data


def default_relevance_fixtures() -> tuple[RelevanceFixture, ...]:
    return (
        RelevanceFixture(
            fixture_id="relevant_robot_memory",
            query="強化学習 ロボット",
            candidate_id="doc:robot",
            candidate_text="強化学習 ロボット 実験メモ。制御と学習の保存投稿。",
            expected_label="relevant",
        ),
        RelevanceFixture(
            fixture_id="irrelevant_food_memory",
            query="強化学習 ロボット",
            candidate_id="doc:food",
            candidate_text="北千住のピザ店とカフェの予約候補。",
            expected_label="irrelevant",
        ),
        RelevanceFixture(
            fixture_id="duplicate_same_source",
            query="強化学習 ロボット",
            candidate_id="doc:robot-copy",
            candidate_text="強化学習 ロボット 実験メモ。制御と学習の保存投稿。",
            expected_label="duplicate",
            duplicate_of="doc:robot",
        ),
        RelevanceFixture(
            fixture_id="conflict_claim",
            query="同じ話で反対意見や矛盾している保存投稿",
            candidate_id="doc:conflict",
            candidate_text="同じ主張に反対する投稿。前の結論とは矛盾する注意点がある。",
            expected_label="conflict",
            claim="前の結論はそのまま正しい",
            metadata={"relation_type": "contradicts"},
        ),
        RelevanceFixture(
            fixture_id="supports_claim",
            query="保存投稿はロボット実験を説明しているか",
            candidate_id="doc:supports",
            candidate_text="保存投稿は ロボット 実験 の手順と強化学習の結果を 説明 している。",
            expected_label="supports_claim",
            claim="ロボット 実験 説明",
        ),
        RelevanceFixture(
            fixture_id="does_not_support_claim",
            query="保存投稿はロボット実験を説明しているか",
            candidate_id="doc:not-supporting",
            candidate_text="保存投稿は イベント 日程 とチケット販売について説明している。",
            expected_label="does_not_support_claim",
            claim="ロボット 実験 説明",
        ),
    )


def judge_relevance_fixture(
    fixture: RelevanceFixture,
    *,
    judge_id: str = LOCAL_JUDGE_CANDIDATE,
) -> LocalJudgeResult:
    _validate_fixture(fixture)
    label, score, reason = _deterministic_label(fixture)
    status = "ok" if label == fixture.expected_label else "fail"
    return LocalJudgeResult(
        fixture_id=fixture.fixture_id,
        candidate_id=fixture.candidate_id,
        judge_id=judge_id,
        label=label,
        expected_label=fixture.expected_label,
        status=status,
        score=score,
        reason=reason,
        metadata={
            "fixture_metadata": dict(fixture.metadata or {}),
            "query_terms": _terms(fixture.query),
            "claim_terms": _terms(fixture.claim or ""),
            "candidate_terms": _terms(fixture.candidate_text),
        },
    )


def run_relevance_fixture_report(
    fixtures: tuple[RelevanceFixture, ...] | None = None,
    *,
    judge_id: str = LOCAL_JUDGE_CANDIDATE,
) -> RelevanceFixtureReport:
    resolved = fixtures or default_relevance_fixtures()
    results = tuple(judge_relevance_fixture(fixture, judge_id=judge_id) for fixture in resolved)
    label_counts = Counter(result.label for result in results)
    status_counts = Counter(result.status for result in results)
    return RelevanceFixtureReport(
        judge_id=judge_id,
        status="ok" if not status_counts.get("fail") else "fail",
        results=results,
        label_counts=dict(sorted(label_counts.items())),
        status_counts=dict(sorted(status_counts.items())),
        metadata={
            "fixture_count": len(results),
            "fixture_labels": sorted(RELEVANCE_LABELS),
            "provider_policy": "provider_execution_policy_required",
            "future_adapter_slot": LOCAL_JUDGE_CANDIDATE,
        },
    )


def relevance_fixture_report_json(report: RelevanceFixtureReport) -> str:
    return json.dumps(report.as_dict(), ensure_ascii=False, indent=2, sort_keys=True)


def _deterministic_label(fixture: RelevanceFixture) -> tuple[str, float, str]:
    metadata = fixture.metadata or {}
    if fixture.duplicate_of:
        return "duplicate", 1.0, "duplicate_of is set"
    if _is_conflict(fixture.candidate_text, metadata):
        return "conflict", 0.95, "candidate carries conflict or contradiction marker"
    if fixture.claim:
        if _claim_supported(fixture.claim, fixture.candidate_text):
            return "supports_claim", 0.9, "candidate covers all claim content terms"
        return "does_not_support_claim", 0.1, "candidate does not cover claim content terms"
    if _overlap_score(fixture.query, fixture.candidate_text) > 0.0:
        return "relevant", 0.8, "query and candidate share content terms"
    return "irrelevant", 0.0, "query and candidate share no content terms"


def _validate_fixture(fixture: RelevanceFixture) -> None:
    if fixture.expected_label not in RELEVANCE_LABELS:
        raise ValueError(f"unknown relevance fixture label: {fixture.expected_label}")
    if not fixture.fixture_id.strip():
        raise ValueError("fixture_id is required")
    if not fixture.candidate_id.strip():
        raise ValueError("candidate_id is required")
    if not fixture.candidate_text.strip() and fixture.expected_label != "irrelevant":
        raise ValueError("candidate_text is required for non-irrelevant fixtures")


def _claim_supported(claim: str, candidate_text: str) -> bool:
    claim_terms = _terms(claim)
    if not claim_terms:
        return False
    candidate_terms = set(_terms(candidate_text))
    return all(term in candidate_terms for term in claim_terms)


def _overlap_score(query: str, candidate_text: str) -> float:
    query_terms = set(_terms(query))
    if not query_terms:
        return 0.0
    candidate_terms = set(_terms(candidate_text))
    return len(query_terms & candidate_terms) / len(query_terms)


def _is_conflict(candidate_text: str, metadata: dict[str, Any]) -> bool:
    markers = {
        "conflict",
        "conflicting",
        "contradict",
        "contradicts",
        "contradiction",
        "反対",
        "矛盾",
    }
    values = [
        candidate_text,
        str(metadata.get("relation_type") or ""),
        str(metadata.get("support_type") or ""),
        str(metadata.get("label") or ""),
    ]
    normalized_values = [value.casefold() for value in values]
    return any(marker.casefold() in value for marker in markers for value in normalized_values)


def _terms(text: str) -> tuple[str, ...]:
    words = [
        token.casefold()
        for token in re.findall(r"[A-Za-z0-9_]+|[\u3040-\u30ff\u3400-\u9fff]+", text)
    ]
    stop_terms = {"は", "を", "に", "と", "の", "か", "いる", "している", "保存投稿"}
    return tuple(term for term in words if term and term not in stop_terms)
