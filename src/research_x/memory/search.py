from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from research_x.memory.corpus import build_memory_corpus
from research_x.memory.schema import ensure_memory_schema, memory_document_count

QUERY_HINTS = (
    "カフェ",
    "居酒屋",
    "自炊",
    "強化学習",
    "機械学習",
    "ロボット",
    "ネットワーク",
    "物理",
    "宇宙",
    "漫画",
    "動画",
    "イラスト",
    "成人",
    "エロ",
    "公式",
    "リンク",
    "イベント",
    "日付",
    "作者",
    "引用",
    "引用元",
    "画像",
    "技術",
    "資料",
    "重複",
    "アカウント",
    "関心",
    "領域",
    "保存",
    "ブクマ",
    "古い",
    "新しい",
)


@dataclass(frozen=True)
class MemorySearchResult:
    doc_id: str
    doc_type: str
    source_tweet_id: str | None
    account_id: str | None
    author_screen_name: str | None
    title: str
    compact_text: str
    score: float
    match_method: str
    metadata: dict[str, Any]


def search_memory(
    db_path: str | Path,
    query: str,
    *,
    limit: int = 10,
    doc_type: str | None = None,
    account: str | None = None,
    rebuild_if_empty: bool = True,
) -> tuple[MemorySearchResult, ...]:
    path = Path(db_path)
    if not path.exists():
        raise FileNotFoundError(f"database not found: {path}")
    resolved_limit = max(1, limit)
    with sqlite3.connect(path, timeout=60) as conn:
        conn.row_factory = sqlite3.Row
        ensure_memory_schema(conn)
        if rebuild_if_empty and memory_document_count(conn) == 0:
            build_memory_corpus(path)
        terms = _query_terms(query)
        rows = _fts_search(
            conn,
            terms,
            limit=resolved_limit,
            doc_type=doc_type,
            account=account,
        )
        if not rows:
            rows = _like_search(
                conn,
                terms,
                limit=resolved_limit,
                doc_type=doc_type,
                account=account,
            )
    return tuple(_result_from_row(row) for row in rows)


def results_as_dicts(results: tuple[MemorySearchResult, ...]) -> list[dict[str, Any]]:
    return [asdict(result) for result in results]


def format_search_results(
    results: tuple[MemorySearchResult, ...],
    *,
    json_output: bool = False,
) -> str:
    if json_output:
        return json.dumps(results_as_dicts(results), ensure_ascii=False, indent=2, sort_keys=True)
    if not results:
        return "(no memory search results)"
    blocks = []
    for index, result in enumerate(results, start=1):
        parts = [
            f"#{index}",
            f"score={result.score:.3f}",
            f"method={result.match_method}",
            f"type={result.doc_type}",
            f"id={result.doc_id}",
        ]
        if result.author_screen_name:
            parts.append(f"@{result.author_screen_name}")
        if result.account_id:
            parts.append(f"account={result.account_id}")
        blocks.append(
            "\n".join(
                [
                    " ".join(parts),
                    f"title: {result.title}",
                    f"text: {result.compact_text}",
                    f"tweet_id: {result.source_tweet_id or ''}",
                    f"url: {result.metadata.get('url') or ''}",
                ]
            )
        )
    return "\n\n".join(blocks)


def _fts_search(
    conn: sqlite3.Connection,
    terms: tuple[str, ...],
    *,
    limit: int,
    doc_type: str | None,
    account: str | None,
) -> list[sqlite3.Row]:
    fts_query = _fts_query(terms)
    if not fts_query:
        return []
    filters, params = _filters(doc_type=doc_type, account=account)
    sql = f"""
        SELECT
            d.doc_id, d.doc_type, d.source_tweet_id, d.account_id,
            d.author_screen_name, d.title, d.compact_text, d.metadata_json,
            bm25(memory_document_fts) AS score,
            'fts' AS match_method
        FROM memory_document_fts
        JOIN memory_documents d ON d.doc_id = memory_document_fts.doc_id
        WHERE memory_document_fts MATCH ?
        {filters}
        ORDER BY score ASC, d.observed_at DESC
        LIMIT ?
    """
    try:
        return conn.execute(sql, (fts_query, *params, limit)).fetchall()
    except sqlite3.OperationalError:
        return []


def _like_search(
    conn: sqlite3.Connection,
    terms: tuple[str, ...],
    *,
    limit: int,
    doc_type: str | None,
    account: str | None,
) -> list[sqlite3.Row]:
    if not terms:
        return []
    filters, params = _filters(doc_type=doc_type, account=account)
    like_filters = []
    like_params: list[Any] = []
    for term in terms:
        pattern = f"%{term}%"
        like_filters.append(
            """
            (
                d.title LIKE ?
                OR d.body LIKE ?
                OR d.compact_text LIKE ?
                OR d.author_screen_name LIKE ?
                OR d.metadata_json LIKE ?
            )
            """
        )
        like_params.extend([pattern, pattern, pattern, pattern, pattern])
    sql = f"""
        SELECT
            d.doc_id, d.doc_type, d.source_tweet_id, d.account_id,
            d.author_screen_name, d.title, d.compact_text, d.metadata_json,
            CAST(-1 * ({len(terms)}) AS REAL) AS score,
            'like' AS match_method
        FROM memory_documents d
        WHERE ({' OR '.join(like_filters)})
        {filters}
        ORDER BY d.observed_at DESC, d.doc_id
        LIMIT ?
    """
    return conn.execute(sql, (*like_params, *params, limit)).fetchall()


def _filters(*, doc_type: str | None, account: str | None) -> tuple[str, tuple[Any, ...]]:
    parts = []
    params: list[Any] = []
    if doc_type:
        parts.append("AND d.doc_type = ?")
        params.append(doc_type)
    if account:
        parts.append("AND d.account_id = ?")
        params.append(account)
    return "\n".join(parts), tuple(params)


def _query_terms(query: str) -> tuple[str, ...]:
    values: list[str] = []
    for term in query.split():
        _append_term(values, term)
    for hint in QUERY_HINTS:
        if hint in query:
            _append_term(values, hint)
    if not values:
        _append_term(values, query)
    return tuple(values)


def _append_term(values: list[str], term: str) -> None:
    value = term.strip().strip("。、,.!?！？「」『』（）()[]【】")
    if not value or value in values:
        return
    values.append(value)


def _fts_query(terms: tuple[str, ...]) -> str:
    terms = tuple(term.strip().replace('"', '""') for term in terms if term.strip())
    if not terms:
        return ""
    return " OR ".join(f'"{term}"' for term in terms)


def _result_from_row(row: sqlite3.Row) -> MemorySearchResult:
    return MemorySearchResult(
        doc_id=row["doc_id"],
        doc_type=row["doc_type"],
        source_tweet_id=row["source_tweet_id"],
        account_id=row["account_id"],
        author_screen_name=row["author_screen_name"],
        title=row["title"] or "",
        compact_text=row["compact_text"] or "",
        score=float(row["score"]),
        match_method=row["match_method"],
        metadata=_loads_json(row["metadata_json"]),
    )


def _loads_json(value: str | None) -> dict[str, Any]:
    if not value:
        return {}
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}
