from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from research_x.memory.schema import ensure_memory_schema
from research_x.memory.workflow import MemoryWorkflow, run_memory_workflow


@dataclass(frozen=True)
class EvalCase:
    query: str
    required_any_terms: tuple[str, ...]
    preferred_doc_types: tuple[str, ...] = ()
    required_feature: str | None = None
    expected_route: str | None = None
    expected_stop_reasons: tuple[str, ...] = ()
    min_hit_score: float = 1.0


DEFAULT_EVAL_CASES = (
    EvalCase(
        query="あとで行きたくて保存したカフェ系を出して",
        required_any_terms=("カフェ", "喫茶", "居酒屋", "レストラン", "グルメ", "店"),
        preferred_doc_types=("bookmark_doc",),
        required_feature="bookmark_context",
        expected_route="place_recall",
    ),
    EvalCase(
        query="最近保存した強化学習とロボット系の情報を古いものを除いて出して",
        required_any_terms=("強化学習", "ロボット", "機械学習", "AI"),
        preferred_doc_types=("topic_thread", "bookmark_doc", "tweet_doc"),
        required_feature="recent",
        expected_route="learning_map",
    ),
    EvalCase(
        query="5/29のキオクシアの株価急騰について保存している人たちの見方から分析して",
        required_any_terms=("5/29", "キオクシア", "株価", "急騰", "分析"),
        preferred_doc_types=("ticker_event", "author_profile", "bookmark_doc", "tweet_doc"),
        expected_route="company_event",
        min_hit_score=0.5,
    ),
    EvalCase(
        query="成人向け漫画の公式リンク誘導っぽいブクマを作品名つきで出して",
        required_any_terms=("成人", "エロ", "R18", "漫画", "同人", "DLsite", "FANZA", "公式"),
        preferred_doc_types=("bookmark_doc", "media_doc"),
        expected_route="adult_comic",
    ),
    EvalCase(
        query="この作者をなぜ何度も保存しているか説明して",
        required_any_terms=("作者", "author", "@"),
        preferred_doc_types=("bookmark_doc", "tweet_doc"),
        expected_route="author_stance",
        min_hit_score=0.5,
    ),
    EvalCase(
        query="引用元を見ないと意味が変わる投稿を根拠付きで出して",
        required_any_terms=("引用", "引用元", "quoted", "quote"),
        preferred_doc_types=("quote_tree_doc",),
        required_feature="quote_context",
        expected_route="quote_context",
    ),
    EvalCase(
        query="同じテーマで古くなった情報と新しい情報を比較して",
        required_any_terms=("古い", "新しい", "最近", "更新"),
        preferred_doc_types=("tweet_doc", "bookmark_doc"),
        required_feature="freshness",
        expected_route="current_fact_check",
        expected_stop_reasons=("external_context_needed", "no_local_evidence"),
        min_hit_score=0.5,
    ),
    EvalCase(
        query="画像付きで保存した技術資料っぽい投稿を出して",
        required_any_terms=("画像", "資料", "技術", "media", "photo"),
        preferred_doc_types=("media_doc", "bookmark_doc"),
        required_feature="media_context",
        expected_route="media_context",
    ),
    EvalCase(
        query="イベント系で日付が近いものだけ出して",
        required_any_terms=("イベント", "開催", "日付", "期限", "予約"),
        preferred_doc_types=("bookmark_doc", "tweet_doc"),
        required_feature="event_dates",
        expected_route="event_recall",
        min_hit_score=0.5,
    ),
    EvalCase(
        query="複数アカウントで重複して保存しているテーマを出して",
        required_any_terms=("重複", "複数", "アカウント"),
        preferred_doc_types=("bookmark_doc", "tweet_doc"),
        required_feature="cross_account",
        expected_route="cross_account",
        min_hit_score=0.5,
    ),
    EvalCase(
        query="DB 全体で最近増えている関心領域を出して",
        required_any_terms=("関心", "領域", "最近", "保存"),
        preferred_doc_types=("tweet_doc", "bookmark_doc"),
        required_feature="recent",
        expected_route="learning_map",
        min_hit_score=0.5,
    ),
)


def load_eval_cases(path: str | Path) -> tuple[EvalCase, ...]:
    case_path = Path(path)
    text = case_path.read_text(encoding="utf-8")
    if case_path.suffix.lower() == ".jsonl":
        records = [
            json.loads(line)
            for line in text.splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        ]
    else:
        payload = json.loads(text)
        records = payload.get("cases", payload) if isinstance(payload, dict) else payload
    if not isinstance(records, list):
        raise ValueError("eval cases file must contain a JSON list or an object with a cases list")
    return tuple(_eval_case_from_mapping(record) for record in records)


@dataclass(frozen=True)
class MemoryEvalResult:
    query: str
    status: str
    route: str
    expected_route: str | None
    stop_reason: str
    hits: int
    context_chunks: int
    first_doc_id: str | None
    best_score: float
    matched_terms: tuple[str, ...]
    retrieval_engines: tuple[str, ...]
    source_kinds: tuple[str, ...]
    answer_status: str | None
    answer_citations: int
    notes: tuple[str, ...]

    @property
    def ok(self) -> bool:
        return self.status == "ok"


def run_memory_eval(
    db_path: str | Path,
    *,
    cases: tuple[EvalCase, ...] | None = None,
    limit: int = 3,
    semantic_provider: str | None = None,
    semantic_model: str | None = None,
    semantic_dimensions: int | None = None,
    semantic_profile: str | None = None,
    semantic_template_version: str | None = None,
    semantic_api_key_env: str | None = None,
    semantic_base_url: str | None = None,
    semantic_weight: float = 3.0,
    semantic_candidates: int = 80,
    answer_provider: str = "fake",
    answer_model: str | None = None,
    answer_api_key_env: str | None = None,
    answer_base_url: str | None = None,
    answer_timeout_seconds: float = 90.0,
) -> tuple[MemoryEvalResult, ...]:
    results = []
    for case in cases or DEFAULT_EVAL_CASES:
        workflow = run_memory_workflow(
            db_path,
            case.query,
            limit=limit,
            semantic_provider=semantic_provider,
            semantic_model=semantic_model,
            semantic_dimensions=semantic_dimensions,
            semantic_profile=semantic_profile,
            semantic_template_version=semantic_template_version,
            semantic_api_key_env=semantic_api_key_env,
            semantic_base_url=semantic_base_url,
            semantic_weight=semantic_weight,
            semantic_candidates=semantic_candidates,
            answer_provider=answer_provider,
            answer_model=answer_model,
            answer_api_key_env=answer_api_key_env,
            answer_base_url=answer_base_url,
            answer_timeout_seconds=answer_timeout_seconds,
            store=False,
        )
        hits = workflow.context_bundle.retrieved_hits if workflow.context_bundle else []
        results.append(_evaluate_case(case, workflow, hits))
    return tuple(results)


def eval_results_json(results: tuple[MemoryEvalResult, ...]) -> str:
    return json.dumps(
        [asdict(result) for result in results],
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    )


def store_memory_eval_results(
    db_path: str | Path,
    results: tuple[MemoryEvalResult, ...],
    *,
    parameters: dict[str, Any],
    cases_path: str | None = None,
    run_id: str | None = None,
) -> str:
    path = Path(db_path)
    if not path.exists():
        raise FileNotFoundError(f"database not found: {path}")
    now = _utc_now()
    resolved_run_id = run_id or _eval_run_id(results, parameters, now)
    counts = {
        "ok": sum(1 for result in results if result.status == "ok"),
        "needs_review": sum(1 for result in results if result.status == "needs_review"),
        "fail": sum(1 for result in results if result.status == "fail"),
    }
    status = "fail" if counts["fail"] else "needs_review" if counts["needs_review"] else "ok"
    with sqlite3.connect(path, timeout=60) as conn:
        ensure_memory_schema(conn)
        conn.execute(
            """
            INSERT INTO memory_eval_runs (
                run_id, cases_path, case_count, parameters_json, status,
                ok_count, needs_review_count, fail_count, started_at, finished_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(run_id) DO UPDATE SET
                parameters_json=excluded.parameters_json,
                status=excluded.status,
                ok_count=excluded.ok_count,
                needs_review_count=excluded.needs_review_count,
                fail_count=excluded.fail_count,
                finished_at=excluded.finished_at
            """,
            (
                resolved_run_id,
                cases_path,
                len(results),
                json.dumps(parameters, ensure_ascii=False, sort_keys=True),
                status,
                counts["ok"],
                counts["needs_review"],
                counts["fail"],
                now,
                now,
            ),
        )
        conn.execute("DELETE FROM memory_eval_results WHERE run_id = ?", (resolved_run_id,))
        for index, result in enumerate(results):
            conn.execute(
                """
                INSERT INTO memory_eval_results (
                    result_id, run_id, case_index, query, status, route,
                    expected_route, stop_reason, hits, context_chunks, first_doc_id,
                    best_score, matched_terms_json, retrieval_engines_json,
                    source_kinds_json, answer_status, answer_citations,
                    notes_json, metadata_json, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    _eval_result_id(resolved_run_id, index, result),
                    resolved_run_id,
                    index,
                    result.query,
                    result.status,
                    result.route,
                    result.expected_route,
                    result.stop_reason,
                    result.hits,
                    result.context_chunks,
                    result.first_doc_id,
                    result.best_score,
                    json.dumps(result.matched_terms, ensure_ascii=False),
                    json.dumps(result.retrieval_engines, ensure_ascii=False),
                    json.dumps(result.source_kinds, ensure_ascii=False),
                    result.answer_status,
                    result.answer_citations,
                    json.dumps(result.notes, ensure_ascii=False),
                    json.dumps(asdict(result), ensure_ascii=False, sort_keys=True),
                    now,
                ),
            )
    return resolved_run_id


def format_eval_results(results: tuple[MemoryEvalResult, ...]) -> str:
    lines = []
    for result in results:
        notes = f" notes={'; '.join(result.notes)}" if result.notes else ""
        terms = ",".join(result.matched_terms[:6]) if result.matched_terms else "-"
        lines.append(
            f"{result.status}: route={result.route} stop={result.stop_reason} "
            f"hits={result.hits} chunks={result.context_chunks} best={result.best_score:.2f} "
            f"answer={result.answer_status or '-'} citations={result.answer_citations} "
            f"first={result.first_doc_id or '-'} terms={terms} query={result.query}{notes}"
        )
    return "\n".join(lines)


def _eval_case_from_mapping(record: Any) -> EvalCase:
    if not isinstance(record, dict):
        raise ValueError("each eval case must be a JSON object")
    query = record.get("query")
    if not isinstance(query, str) or not query.strip():
        raise ValueError("each eval case requires a non-empty query")
    return EvalCase(
        query=query,
        required_any_terms=_tuple_field(record, "required_any_terms"),
        preferred_doc_types=_tuple_field(record, "preferred_doc_types"),
        required_feature=_optional_string(record.get("required_feature")),
        expected_route=_optional_string(record.get("expected_route")),
        expected_stop_reasons=_tuple_field(record, "expected_stop_reasons"),
        min_hit_score=float(record.get("min_hit_score", 1.0)),
    )


def _tuple_field(record: dict[str, Any], key: str) -> tuple[str, ...]:
    value = record.get(key, ())
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,)
    if isinstance(value, list | tuple):
        return tuple(str(item) for item in value if str(item))
    raise ValueError(f"{key} must be a string or list of strings")


def _optional_string(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _evaluate_case(
    case: EvalCase,
    workflow: MemoryWorkflow,
    hits: list[dict],
) -> MemoryEvalResult:
    notes: list[str] = []
    source_kinds = _source_kinds(workflow)
    context_chunks = len(workflow.context_bundle.context_chunks) if workflow.context_bundle else 0
    if case.expected_route and workflow.route != case.expected_route:
        notes.append(f"route mismatch: expected {case.expected_route}, got {workflow.route}")
    if case.expected_stop_reasons and workflow.stop_reason not in case.expected_stop_reasons:
        notes.append(
            "stop reason mismatch: expected "
            f"{', '.join(case.expected_stop_reasons)}, got {workflow.stop_reason}"
        )
    if not hits:
        notes.append("no hits")
        return MemoryEvalResult(
            query=case.query,
            status="fail",
            route=workflow.route,
            expected_route=case.expected_route,
            stop_reason=workflow.stop_reason,
            hits=0,
            context_chunks=context_chunks,
            first_doc_id=None,
            best_score=0.0,
            matched_terms=(),
            retrieval_engines=(),
            source_kinds=source_kinds,
            answer_status=workflow.answer.status if workflow.answer else None,
            answer_citations=(
                len(workflow.answer.citation_annotations) if workflow.answer else 0
            ),
            notes=tuple(notes),
        )

    first = hits[0]
    best_score = float(first.get("score") or 0.0)
    matched_terms = _matched_terms(hits)
    preferred_found = any(hit.get("doc_type") in case.preferred_doc_types for hit in hits)
    required_term_found = any(
        _term_matches(term, hit)
        for term in case.required_any_terms
        for hit in hits
    )
    feature_found = _feature_found(case.required_feature, hits)

    if not _valid_hit(first):
        notes.append("first hit is missing compact evidence")
    if best_score < case.min_hit_score:
        notes.append(f"best score below threshold {case.min_hit_score:.1f}")
    if case.preferred_doc_types and not preferred_found:
        notes.append(f"preferred doc type missing: {', '.join(case.preferred_doc_types)}")
    if case.required_any_terms and not required_term_found:
        notes.append("required term family missing")
    if case.required_feature and not feature_found:
        notes.append(f"required feature missing: {case.required_feature}")
    if workflow.status == "error":
        notes.append(f"workflow error stop reason: {workflow.stop_reason}")
    if workflow.answer is not None:
        if workflow.answer.status != "ok":
            notes.append(f"answer status is {workflow.answer.status}")
        if hits and not workflow.answer.citation_annotations:
            notes.append("answer has no citations")

    status = "ok" if not notes else "needs_review"
    if (
        "first hit is missing compact evidence" in notes
        or "required term family missing" in notes
        or any(note.startswith("route mismatch") for note in notes)
    ):
        status = "fail"

    return MemoryEvalResult(
        query=case.query,
        status=status,
        route=workflow.route,
        expected_route=case.expected_route,
        stop_reason=workflow.stop_reason,
        hits=len(hits),
        context_chunks=context_chunks,
        first_doc_id=first.get("doc_id"),
        best_score=best_score,
        matched_terms=matched_terms,
        retrieval_engines=_retrieval_engines(hits),
        source_kinds=source_kinds,
        answer_status=workflow.answer.status if workflow.answer else None,
        answer_citations=len(workflow.answer.citation_annotations) if workflow.answer else 0,
        notes=tuple(notes),
    )


def _valid_hit(hit: dict) -> bool:
    evidence = hit.get("evidence") or {}
    return bool(
        hit.get("doc_id")
        and hit.get("compact_text")
        and (evidence.get("url") or hit.get("tweet_id"))
    )


def _matched_terms(hits: list[dict]) -> tuple[str, ...]:
    terms: list[str] = []
    for hit in hits:
        for term in hit.get("matched_terms") or ():
            if term not in terms:
                terms.append(str(term))
    return tuple(terms)


def _term_matches(term: str, hit: dict) -> bool:
    needle = term.casefold()
    haystack = "\n".join(
        [
            str(hit.get("title") or ""),
            str(hit.get("compact_text") or ""),
            " ".join(str(value) for value in hit.get("matched_terms") or ()),
            json.dumps(hit.get("evidence") or {}, ensure_ascii=False),
        ]
    ).casefold()
    return needle in haystack


def _feature_found(feature: str | None, hits: list[dict]) -> bool:
    if feature is None:
        return True
    for hit in hits:
        evidence = hit.get("evidence") or {}
        if feature == "bookmark_context" and hit.get("doc_type") == "bookmark_doc":
            return True
        if feature == "quote_context" and evidence.get("quoted_tweets"):
            return True
        if feature == "media_context" and evidence.get("media"):
            return True
        if feature == "cross_account" and _bookmark_account_count(hit) > 1:
            return True
        if feature == "event_dates" and _term_matches("202", hit):
            return True
        if feature == "recent" and hit.get("freshness") == "recent":
            return True
        freshness_score = float((hit.get("score_components") or {}).get("freshness") or 0.0)
        if feature == "freshness" and abs(freshness_score) > 0.0001:
            return True
    return False


def _bookmark_account_count(hit: dict) -> int:
    evidence = hit.get("evidence") or {}
    metadata_count = hit.get("bookmark_account_count")
    if isinstance(metadata_count, int):
        return metadata_count
    account_id = evidence.get("account_id")
    return 1 if account_id else 0


def _retrieval_engines(hits: list[dict]) -> tuple[str, ...]:
    engines: list[str] = []
    for hit in hits:
        why = str(hit.get("why_relevant") or "")
        engine = why.split(" match:", 1)[0].strip()
        if engine and engine not in engines:
            engines.append(engine)
    return tuple(engines)


def _source_kinds(workflow: MemoryWorkflow) -> tuple[str, ...]:
    if workflow.context_bundle is None:
        return ()
    kinds = sorted(
        {
            str(chunk.metadata.get("evidence_source_kind") or chunk.source_kind)
            for chunk in workflow.context_bundle.context_chunks
        }
    )
    return tuple(kinds)


def _eval_run_id(
    results: tuple[MemoryEvalResult, ...],
    parameters: dict[str, Any],
    created_at: str,
) -> str:
    payload = {
        "created_at": created_at,
        "parameters": parameters,
        "queries": [result.query for result in results],
        "statuses": [result.status for result in results],
    }
    return _hash_id("memory-eval-run", json.dumps(payload, ensure_ascii=False, sort_keys=True))[:24]


def _eval_result_id(run_id: str, index: int, result: MemoryEvalResult) -> str:
    return _hash_id("memory-eval-result", run_id, str(index), result.query, result.status)[:24]


def _hash_id(*parts: str) -> str:
    return hashlib.sha256("\0".join(parts).encode("utf-8")).hexdigest()


def _utc_now() -> str:
    return datetime.now(tz=UTC).isoformat(timespec="seconds")
