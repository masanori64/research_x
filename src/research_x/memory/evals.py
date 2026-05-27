from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from research_x.memory.evidence import build_evidence_bundle

DEFAULT_EVAL_QUERIES = (
    "あとで行きたくて保存したカフェ系を出して",
    "最近保存した強化学習とロボット系の情報を古いものを除いて出して",
    "成人向け漫画の公式リンク誘導っぽいブクマを作品名つきで出して",
    "この作者をなぜ何度も保存しているか説明して",
    "引用元を見ないと意味が変わる投稿を根拠付きで出して",
    "同じテーマで古くなった情報と新しい情報を比較して",
    "画像付きで保存した技術資料っぽい投稿を出して",
    "イベント系で日付が近いものだけ出して",
    "複数アカウントで重複して保存しているテーマを出して",
    "DB 全体で最近増えている関心領域を出して",
)


@dataclass(frozen=True)
class MemoryEvalResult:
    query: str
    hits: int
    ok: bool
    first_doc_id: str | None


def run_memory_eval(
    db_path: str | Path,
    *,
    limit: int = 3,
) -> tuple[MemoryEvalResult, ...]:
    results = []
    for query in DEFAULT_EVAL_QUERIES:
        bundle = build_evidence_bundle(db_path, query, limit=limit)
        hits = bundle.get("hits", [])
        first = hits[0]["doc_id"] if hits else None
        results.append(
            MemoryEvalResult(
                query=query,
                hits=len(hits),
                ok=bool(hits) and all(_valid_hit(hit) for hit in hits),
                first_doc_id=first,
            )
        )
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
        status = "ok" if result.ok else "bad"
        lines.append(
            f"{status}: hits={result.hits} first={result.first_doc_id or '-'} query={result.query}"
        )
    return "\n".join(lines)


def _valid_hit(hit: dict) -> bool:
    return bool(hit.get("doc_id") and hit.get("compact_text") and hit.get("evidence"))
