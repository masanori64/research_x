from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from research_x.memory.evidence import build_evidence_bundle


@dataclass(frozen=True)
class EvalCase:
    query: str
    required_any_terms: tuple[str, ...]
    preferred_doc_types: tuple[str, ...] = ()
    required_feature: str | None = None
    min_hit_score: float = 1.0


DEFAULT_EVAL_CASES = (
    EvalCase(
        query="あとで行きたくて保存したカフェ系を出して",
        required_any_terms=("カフェ", "喫茶", "居酒屋", "レストラン", "グルメ", "店"),
        preferred_doc_types=("bookmark_doc",),
        required_feature="bookmark_context",
    ),
    EvalCase(
        query="最近保存した強化学習とロボット系の情報を古いものを除いて出して",
        required_any_terms=("強化学習", "ロボット", "機械学習", "AI"),
        preferred_doc_types=("bookmark_doc", "tweet_doc"),
        required_feature="recent",
    ),
    EvalCase(
        query="成人向け漫画の公式リンク誘導っぽいブクマを作品名つきで出して",
        required_any_terms=("成人", "エロ", "R18", "漫画", "同人", "DLsite", "FANZA", "公式"),
        preferred_doc_types=("bookmark_doc", "media_doc"),
    ),
    EvalCase(
        query="この作者をなぜ何度も保存しているか説明して",
        required_any_terms=("作者", "author", "@"),
        preferred_doc_types=("bookmark_doc", "tweet_doc"),
        min_hit_score=0.5,
    ),
    EvalCase(
        query="引用元を見ないと意味が変わる投稿を根拠付きで出して",
        required_any_terms=("引用", "引用元", "quoted", "quote"),
        preferred_doc_types=("quote_tree_doc",),
        required_feature="quote_context",
    ),
    EvalCase(
        query="同じテーマで古くなった情報と新しい情報を比較して",
        required_any_terms=("古い", "新しい", "最近", "更新"),
        preferred_doc_types=("tweet_doc", "bookmark_doc"),
        required_feature="freshness",
        min_hit_score=0.5,
    ),
    EvalCase(
        query="画像付きで保存した技術資料っぽい投稿を出して",
        required_any_terms=("画像", "資料", "技術", "media", "photo"),
        preferred_doc_types=("media_doc", "bookmark_doc"),
        required_feature="media_context",
    ),
    EvalCase(
        query="イベント系で日付が近いものだけ出して",
        required_any_terms=("イベント", "開催", "日付", "期限", "予約"),
        preferred_doc_types=("bookmark_doc", "tweet_doc"),
        required_feature="event_dates",
        min_hit_score=0.5,
    ),
    EvalCase(
        query="複数アカウントで重複して保存しているテーマを出して",
        required_any_terms=("重複", "複数", "アカウント"),
        preferred_doc_types=("bookmark_doc", "tweet_doc"),
        required_feature="cross_account",
        min_hit_score=0.5,
    ),
    EvalCase(
        query="DB 全体で最近増えている関心領域を出して",
        required_any_terms=("関心", "領域", "最近", "保存"),
        preferred_doc_types=("tweet_doc", "bookmark_doc"),
        required_feature="recent",
        min_hit_score=0.5,
    ),
)


@dataclass(frozen=True)
class MemoryEvalResult:
    query: str
    status: str
    hits: int
    first_doc_id: str | None
    best_score: float
    matched_terms: tuple[str, ...]
    notes: tuple[str, ...]

    @property
    def ok(self) -> bool:
        return self.status == "ok"


def run_memory_eval(
    db_path: str | Path,
    *,
    limit: int = 3,
) -> tuple[MemoryEvalResult, ...]:
    results = []
    for case in DEFAULT_EVAL_CASES:
        bundle = build_evidence_bundle(db_path, case.query, limit=limit)
        hits = bundle.get("hits", [])
        results.append(_evaluate_case(case, hits))
    return tuple(results)


def eval_results_json(results: tuple[MemoryEvalResult, ...]) -> str:
    return json.dumps(
        [asdict(result) for result in results],
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    )


def format_eval_results(results: tuple[MemoryEvalResult, ...]) -> str:
    lines = []
    for result in results:
        notes = f" notes={'; '.join(result.notes)}" if result.notes else ""
        terms = ",".join(result.matched_terms[:6]) if result.matched_terms else "-"
        lines.append(
            f"{result.status}: hits={result.hits} best={result.best_score:.2f} "
            f"first={result.first_doc_id or '-'} terms={terms} query={result.query}{notes}"
        )
    return "\n".join(lines)


def _evaluate_case(case: EvalCase, hits: list[dict]) -> MemoryEvalResult:
    notes: list[str] = []
    if not hits:
        return MemoryEvalResult(
            query=case.query,
            status="fail",
            hits=0,
            first_doc_id=None,
            best_score=0.0,
            matched_terms=(),
            notes=("no hits",),
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

    status = "ok" if not notes else "needs_review"
    if "first hit is missing compact evidence" in notes or "required term family missing" in notes:
        status = "fail"

    return MemoryEvalResult(
        query=case.query,
        status=status,
        hits=len(hits),
        first_doc_id=first.get("doc_id"),
        best_score=best_score,
        matched_terms=matched_terms,
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
        if feature == "recent" and (hit.get("freshness") in {"active", "recent"}):
            return True
        if feature == "freshness" and hit.get("score_components", {}).get("freshness") is not None:
            return True
    return False


def _bookmark_account_count(hit: dict) -> int:
    evidence = hit.get("evidence") or {}
    metadata_count = hit.get("bookmark_account_count")
    if isinstance(metadata_count, int):
        return metadata_count
    account_id = evidence.get("account_id")
    return 1 if account_id else 0
