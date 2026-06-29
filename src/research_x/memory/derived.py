from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from research_x.memory.document_hashes import (
    memory_document_embedding_text_hash,
    memory_document_source_hash,
)
from research_x.memory.schema import ensure_memory_schema, memory_document_count

DERIVED_DOC_TYPES = ("place_card", "author_profile", "ticker_event", "topic_thread")
SOURCE_DOC_TYPES = ("tweet_doc", "bookmark_doc", "quote_tree_doc", "media_doc")

FOOD_TERMS = (
    "カフェ",
    "喫茶",
    "喫茶店",
    "居酒屋",
    "レストラン",
    "ラーメン",
    "ピザ",
    "イタリアン",
    "寿司",
    "焼肉",
    "自炊",
    "グルメ",
    "ランチ",
    "ディナー",
    "飯",
    "食事",
    "店",
)

VENUE_TERMS = (
    "美術館",
    "博物館",
    "ギャラリー",
    "展示",
    "会場",
    "劇場",
    "映画館",
    "ライブハウス",
    "ホール",
    "公園",
    "ホテル",
    "温泉",
    "サウナ",
    "書店",
    "本屋",
    "ショップ",
    "施設",
    "スポット",
    "場所",
    "行きたい",
)

PLACE_TERMS = tuple(dict.fromkeys((*FOOD_TERMS, *VENUE_TERMS)))
PLACE_LABEL_HINTS = (
    "place",
    "venue",
    "spot",
    "food",
    "restaurant",
    "cafe",
    "event",
    "travel",
    "飯",
    "食事",
    "グルメ",
    "店",
    "場所",
    "イベント",
)
PLACE_URL_DOMAINS = (
    "tabelog.com",
    "hotpepper.jp",
    "gnavi.co.jp",
    "retty.me",
    "tripadvisor",
    "google.com/maps",
    "maps.app.goo.gl",
    "map.yahoo.co.jp",
    "jalan.net",
    "ikyu.com",
)

AREA_TERMS = (
    "北千住",
    "渋谷",
    "新宿",
    "池袋",
    "上野",
    "秋葉原",
    "浅草",
    "銀座",
    "日本橋",
    "東京",
    "横浜",
    "大阪",
    "京都",
    "名古屋",
    "福岡",
    "札幌",
    "仙台",
)

FINANCE_TERMS = (
    "株価",
    "急騰",
    "急落",
    "決算",
    "上方修正",
    "下方修正",
    "業績",
    "銘柄",
    "投資",
    "市場",
    "半導体",
    "金利",
    "為替",
    "決算説明",
)

TOPIC_THREAD_TERMS = (
    "AI",
    "LLM",
    "RAG",
    "機械学習",
    "強化学習",
    "深層学習",
    "ロボット",
    "ネットワーク",
    "セキュリティ",
    "プログラミング",
    "Python",
    "論文",
    "資料",
    "実装",
    "物理",
    "宇宙",
    "数学",
    "金融",
    "投資",
    "漫画",
    "イラスト",
    "イベント",
)

TOPIC_THREAD_HINTS = (
    "勉強",
    "整理",
    "学習",
    "資料",
    "論文",
    "解説",
    "入門",
    "まとめ",
    "メモ",
)

KNOWN_COMPANY_TERMS = (
    "キオクシア",
    "ソニー",
    "トヨタ",
    "任天堂",
    "三菱重工",
    "日立",
    "ソフトバンク",
    "NVIDIA",
    "NVDA",
    "AMD",
    "TSMC",
    "Apple",
    "AAPL",
    "Microsoft",
    "MSFT",
    "Tesla",
    "TSLA",
)

DATE_RE = re.compile(r"\d{4}[-/年]\d{1,2}(?:[-/月]\d{1,2}日?)?|\d{1,2}/\d{1,2}")
CASHTAG_RE = re.compile(r"\$[A-Za-z][A-Za-z0-9.]{0,9}")
LATIN_TOKEN_RE = re.compile(r"[@#]?[A-Za-z][A-Za-z0-9_.-]{1,}")


@dataclass(frozen=True)
class DerivedBuildSummary:
    db_path: str
    source_documents: int
    documents: int
    place_cards: int
    author_profiles: int
    ticker_events: int
    topic_threads: int
    by_type: dict[str, int]


@dataclass(frozen=True)
class DerivedDocument:
    doc_id: str
    doc_type: str
    source_tweet_id: str | None
    account_id: str | None
    author_screen_name: str | None
    title: str
    body: str
    compact_text: str
    metadata: dict[str, Any]
    created_at: str | None
    observed_at: str | None
    updated_at: str | None


def build_derived_documents(
    db_path: str | Path,
    *,
    kinds: tuple[str, ...] | None = None,
    max_source_docs_per_card: int = 8,
    min_author_docs: int = 1,
    min_topic_docs: int = 2,
) -> DerivedBuildSummary:
    path = Path(db_path)
    if not path.exists():
        raise FileNotFoundError(f"database not found: {path}")
    selected_kinds = _selected_kinds(kinds)
    now = _utc_now()
    with sqlite3.connect(path, timeout=60) as conn:
        conn.row_factory = sqlite3.Row
        ensure_memory_schema(conn)
        if memory_document_count(conn) == 0:
            raise RuntimeError("memory_documents is empty; run memory build-corpus first")
        source_rows = _source_rows(conn)
        documents: list[DerivedDocument] = []
        if "place_card" in selected_kinds:
            documents.extend(
                _place_cards(
                    source_rows,
                    max_source_docs_per_card=max_source_docs_per_card,
                    now=now,
                )
            )
        if "author_profile" in selected_kinds:
            documents.extend(
                _author_profiles(
                    source_rows,
                    max_source_docs_per_card=max_source_docs_per_card,
                    min_author_docs=min_author_docs,
                    now=now,
                )
            )
        if "ticker_event" in selected_kinds:
            documents.extend(
                _ticker_events(
                    source_rows,
                    max_source_docs_per_card=max_source_docs_per_card,
                    now=now,
                )
            )
        if "topic_thread" in selected_kinds:
            documents.extend(
                _topic_threads(
                    source_rows,
                    max_source_docs_per_card=max_source_docs_per_card,
                    min_topic_docs=min_topic_docs,
                    now=now,
                )
            )
        old_doc_ids = _derived_doc_ids(conn, selected_kinds)
        new_doc_ids = tuple(document.doc_id for document in documents)
        _delete_documents(conn, old_doc_ids, selected_kinds)
        for document in documents:
            _insert_document(conn, document)
            _insert_fts(conn, document)
        _replace_derived_relations(conn, old_doc_ids + new_doc_ids, documents, now=now)

    by_type = Counter(document.doc_type for document in documents)
    return DerivedBuildSummary(
        db_path=str(path),
        source_documents=len(source_rows),
        documents=len(documents),
        place_cards=by_type.get("place_card", 0),
        author_profiles=by_type.get("author_profile", 0),
        ticker_events=by_type.get("ticker_event", 0),
        topic_threads=by_type.get("topic_thread", 0),
        by_type=dict(sorted(by_type.items())),
    )


def summary_as_dict(summary: DerivedBuildSummary) -> dict[str, Any]:
    return asdict(summary)


def _selected_kinds(kinds: tuple[str, ...] | None) -> tuple[str, ...]:
    if not kinds:
        return DERIVED_DOC_TYPES
    selected = tuple(dict.fromkeys(kind.strip() for kind in kinds if kind.strip()))
    unknown = sorted(set(selected) - set(DERIVED_DOC_TYPES))
    if unknown:
        raise ValueError(f"unknown derived document kind: {', '.join(unknown)}")
    return selected


def _source_rows(conn: sqlite3.Connection) -> tuple[sqlite3.Row, ...]:
    placeholders = ",".join("?" for _ in SOURCE_DOC_TYPES)
    return tuple(
        conn.execute(
            f"""
            SELECT
                doc_id, doc_type, source_tweet_id, account_id, author_screen_name,
                title, body, compact_text, metadata_json, created_at, observed_at, updated_at
            FROM memory_documents
            WHERE doc_type IN ({placeholders})
            ORDER BY observed_at DESC, created_at DESC, doc_id
            """,
            SOURCE_DOC_TYPES,
        ).fetchall()
    )


def _place_cards(
    rows: tuple[sqlite3.Row, ...],
    *,
    max_source_docs_per_card: int,
    now: str,
) -> list[DerivedDocument]:
    grouped: dict[str, list[sqlite3.Row]] = defaultdict(list)
    descriptors: dict[str, dict[str, tuple[str, ...]]] = {}
    for row in rows:
        text = _row_text(row)
        place_terms = _place_terms(row, text)
        if not place_terms:
            continue
        areas = _extract_areas(text)
        key = _place_key(row, areas=areas, place_terms=place_terms)
        grouped[key].append(row)
        descriptor = descriptors.setdefault(key, {"areas": (), "place_terms": ()})
        descriptor["areas"] = _merge_tuple(descriptor["areas"], areas)
        descriptor["place_terms"] = _merge_tuple(descriptor["place_terms"], place_terms)

    documents: list[DerivedDocument] = []
    for key, group in sorted(grouped.items()):
        all_source_rows = tuple(group)
        display_rows = _dedupe_sources(group, limit=max_source_docs_per_card)
        descriptor = descriptors[key]
        title_terms = _unique((*descriptor["areas"], *descriptor["place_terms"]))[:5]
        title = "place_card " + (" ".join(title_terms) if title_terms else key)
        body = _derived_body(
            "place_card",
            title=title,
            source_rows=display_rows,
            extra_lines=(
                f"place_key: {key}",
                f"areas: {', '.join(descriptor['areas'])}" if descriptor["areas"] else None,
                f"place_terms: {', '.join(descriptor['place_terms'])}",
            ),
        )
        metadata = _source_metadata(
            "place_card",
            all_source_rows,
            extra={
                "place_key": key,
                "areas": descriptor["areas"],
                "place_terms": descriptor["place_terms"],
                "food_terms": tuple(
                    term for term in descriptor["place_terms"] if term in FOOD_TERMS
                ),
                "display_source_doc_ids": [str(row["doc_id"]) for row in display_rows],
                "grouping_version": "place-card-provenance-v2",
            },
        )
        documents.append(
            _document(
                doc_id=f"place_card:{_stable_key(key)}",
                doc_type="place_card",
                title=title,
                body=body,
                metadata=metadata,
                source_rows=all_source_rows,
                now=now,
            )
        )
    return documents


def _author_profiles(
    rows: tuple[sqlite3.Row, ...],
    *,
    max_source_docs_per_card: int,
    min_author_docs: int,
    now: str,
) -> list[DerivedDocument]:
    grouped: dict[str, list[sqlite3.Row]] = defaultdict(list)
    display_names: dict[str, str] = {}
    for row in rows:
        author = str(row["author_screen_name"] or "").strip()
        if not author:
            continue
        key = author.casefold()
        grouped[key].append(row)
        display_names.setdefault(key, author)

    documents: list[DerivedDocument] = []
    for key, group in sorted(grouped.items()):
        all_source_rows = tuple(group)
        display_rows = _dedupe_sources(group, limit=max_source_docs_per_card)
        if len(all_source_rows) < max(1, min_author_docs):
            continue
        author = display_names[key]
        labels = _top_labels(all_source_rows)
        title = f"author_profile @{author}"
        body = _derived_body(
            "author_profile",
            title=title,
            source_rows=display_rows,
            extra_lines=(
                f"author: @{author}",
                f"top_labels: {', '.join(labels)}" if labels else None,
            ),
        )
        metadata = _source_metadata(
            "author_profile",
            all_source_rows,
            extra={
                "author": author,
                "top_labels": labels,
                "display_source_doc_ids": [str(row["doc_id"]) for row in display_rows],
                "grouping_version": "author-profile-v1",
            },
        )
        documents.append(
            _document(
                doc_id=f"author_profile:{_stable_key(key)}",
                doc_type="author_profile",
                title=title,
                body=body,
                metadata=metadata,
                source_rows=all_source_rows,
                now=now,
                author_screen_name=author,
            )
        )
    return documents


def _ticker_events(
    rows: tuple[sqlite3.Row, ...],
    *,
    max_source_docs_per_card: int,
    now: str,
) -> list[DerivedDocument]:
    grouped: dict[str, list[sqlite3.Row]] = defaultdict(list)
    descriptors: dict[str, dict[str, tuple[str, ...] | str]] = {}
    for row in rows:
        text = _row_text(row)
        finance_terms = _terms_in_text(FINANCE_TERMS, text)
        companies = _extract_companies(text)
        if not finance_terms or not companies:
            continue
        dates = tuple(DATE_RE.findall(text))
        company = companies[0]
        date_key = dates[0] if dates else "undated"
        key = f"{company}|{date_key}"
        grouped[key].append(row)
        descriptors[key] = {
            "company": company,
            "dates": dates,
            "finance_terms": finance_terms,
        }

    documents: list[DerivedDocument] = []
    for key, group in sorted(grouped.items()):
        all_source_rows = tuple(group)
        display_rows = _dedupe_sources(group, limit=max_source_docs_per_card)
        descriptor = descriptors[key]
        company = str(descriptor["company"])
        dates = tuple(str(value) for value in descriptor["dates"])
        finance_terms = tuple(str(value) for value in descriptor["finance_terms"])
        title_bits = [company, *(dates[:1]), *finance_terms[:3]]
        title = "ticker_event " + " ".join(bit for bit in title_bits if bit)
        body = _derived_body(
            "ticker_event",
            title=title,
            source_rows=display_rows,
            extra_lines=(
                f"company_or_ticker: {company}",
                f"dates: {', '.join(dates)}" if dates else None,
                f"finance_terms: {', '.join(finance_terms)}",
            ),
        )
        metadata = _source_metadata(
            "ticker_event",
            all_source_rows,
            extra={
                "company_or_ticker": company,
                "dates": dates,
                "finance_terms": finance_terms,
                "display_source_doc_ids": [str(row["doc_id"]) for row in display_rows],
                "grouping_version": "ticker-event-provenance-v2",
            },
        )
        documents.append(
            _document(
                doc_id=f"ticker_event:{_stable_key(key)}",
                doc_type="ticker_event",
                title=title,
                body=body,
                metadata=metadata,
                source_rows=all_source_rows,
                now=now,
            )
        )
    return documents


def _topic_threads(
    rows: tuple[sqlite3.Row, ...],
    *,
    max_source_docs_per_card: int,
    min_topic_docs: int,
    now: str,
) -> list[DerivedDocument]:
    grouped: dict[str, list[sqlite3.Row]] = defaultdict(list)
    for row in rows:
        text = _row_text(row)
        for topic in _topic_thread_terms(row, text):
            grouped[topic].append(row)

    documents: list[DerivedDocument] = []
    for topic, group in sorted(grouped.items()):
        unique_rows = _unique_source_rows(group)
        if len(unique_rows) < max(1, min_topic_docs):
            continue
        all_source_rows = tuple(unique_rows)
        display_rows = _dedupe_sources(unique_rows, limit=max_source_docs_per_card)
        top_labels = _top_labels(all_source_rows)
        title = f"topic_thread {topic}"
        body = _derived_body(
            "topic_thread",
            title=title,
            source_rows=display_rows,
            extra_lines=(
                f"topic: {topic}",
                f"top_labels: {', '.join(top_labels)}" if top_labels else None,
                f"source_doc_count: {len(all_source_rows)}",
            ),
        )
        metadata = _source_metadata(
            "topic_thread",
            all_source_rows,
            extra={
                "topic_key": topic.casefold(),
                "topic": topic,
                "top_labels": top_labels,
                "display_source_doc_ids": [str(row["doc_id"]) for row in display_rows],
                "grouping_version": "topic-thread-v1",
            },
        )
        documents.append(
            _document(
                doc_id=f"topic_thread:{_stable_key(topic)}",
                doc_type="topic_thread",
                title=title,
                body=body,
                metadata=metadata,
                source_rows=all_source_rows,
                now=now,
            )
        )
    return documents


def _document(
    *,
    doc_id: str,
    doc_type: str,
    title: str,
    body: str,
    metadata: dict[str, Any],
    source_rows: tuple[sqlite3.Row, ...],
    now: str,
    author_screen_name: str | None = None,
) -> DerivedDocument:
    tweet_ids = _unique(
        str(row["source_tweet_id"]) for row in source_rows if row["source_tweet_id"]
    )
    accounts = _unique(str(row["account_id"]) for row in source_rows if row["account_id"])
    compact = _compact(body, limit=720)
    return DerivedDocument(
        doc_id=doc_id,
        doc_type=doc_type,
        source_tweet_id=tweet_ids[0] if len(tweet_ids) == 1 else None,
        account_id=accounts[0] if len(accounts) == 1 else None,
        author_screen_name=author_screen_name,
        title=title,
        body=body,
        compact_text=compact,
        metadata=metadata,
        created_at=_min_datetime(row["created_at"] for row in source_rows),
        observed_at=_max_datetime(row["observed_at"] for row in source_rows),
        updated_at=now,
    )


def _source_metadata(
    derived_kind: str,
    source_rows: tuple[sqlite3.Row, ...],
    *,
    extra: dict[str, Any],
) -> dict[str, Any]:
    labels = _top_labels(source_rows)
    urls = _source_urls(source_rows)
    tweet_ids = _unique(
        str(row["source_tweet_id"]) for row in source_rows if row["source_tweet_id"]
    )
    return {
        "derived_kind": derived_kind,
        "source_doc_ids": list(_unique(str(row["doc_id"]) for row in source_rows)),
        "source_tweet_ids": tweet_ids,
        "source_doc_count": len(source_rows),
        "accounts": _unique(str(row["account_id"]) for row in source_rows if row["account_id"]),
        "authors": _unique(
            str(row["author_screen_name"])
            for row in source_rows
            if row["author_screen_name"]
        ),
        "labels": labels,
        "url": urls[0] if urls else None,
        "source_urls": urls,
        **extra,
    }


def _derived_body(
    derived_kind: str,
    *,
    title: str,
    source_rows: tuple[sqlite3.Row, ...],
    extra_lines: tuple[str | None, ...],
) -> str:
    parts = [
        f"derived_kind: {derived_kind}",
        f"title: {title}",
        *[line for line in extra_lines if line],
        "source_documents:",
    ]
    for index, row in enumerate(source_rows, start=1):
        metadata = _loads_json(row["metadata_json"])
        url = metadata.get("url")
        labels = metadata.get("labels") or ()
        parts.append(
            "\n".join(
                part
                for part in (
                    f"[{index}] doc_id: {row['doc_id']}",
                    f"doc_type: {row['doc_type']}",
                    f"tweet_id: {row['source_tweet_id']}" if row["source_tweet_id"] else None,
                    f"account: {row['account_id']}" if row["account_id"] else None,
                    f"author: @{row['author_screen_name']}" if row["author_screen_name"] else None,
                    f"url: {url}" if url else None,
                    f"labels: {', '.join(str(label) for label in labels)}" if labels else None,
                    f"text: {_compact(row['compact_text'] or row['body'] or '', limit=320)}",
                )
                if part
            )
        )
    return "\n\n".join(parts)


def _replace_derived_relations(
    conn: sqlite3.Connection,
    doc_ids: tuple[str, ...],
    documents: list[DerivedDocument],
    *,
    now: str,
) -> None:
    if doc_ids:
        placeholders = ",".join("?" for _ in doc_ids)
        conn.execute(
            f"""
            DELETE FROM memory_relations
            WHERE source_doc_id IN ({placeholders})
               OR target_doc_id IN ({placeholders})
            """,
            (*doc_ids, *doc_ids),
        )
    for document in documents:
        source_doc_ids = tuple(str(value) for value in document.metadata.get("source_doc_ids", ()))
        for source_doc_id in source_doc_ids:
            relation_id = _relation_id(document.doc_id, source_doc_id, "derived_from_source")
            conn.execute(
                """
                INSERT INTO memory_relations (
                    relation_id, source_doc_id, target_doc_id, relation_type,
                    strength, status, evidence_json, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    relation_id,
                    document.doc_id,
                    source_doc_id,
                    "derived_from_source",
                    0.65,
                    "derived",
                    json.dumps(
                        {
                            "derived_kind": document.doc_type,
                            "source_doc_id": source_doc_id,
                        },
                        ensure_ascii=False,
                        sort_keys=True,
                    ),
                    now,
                    now,
                ),
            )


def _delete_documents(
    conn: sqlite3.Connection,
    old_doc_ids: tuple[str, ...],
    kinds: tuple[str, ...],
) -> None:
    if old_doc_ids:
        placeholders = ",".join("?" for _ in old_doc_ids)
        conn.execute(
            f"DELETE FROM memory_document_fts WHERE doc_id IN ({placeholders})",
            old_doc_ids,
        )
        conn.execute(f"DELETE FROM memory_embeddings WHERE doc_id IN ({placeholders})", old_doc_ids)
    placeholders = ",".join("?" for _ in kinds)
    conn.execute(f"DELETE FROM memory_documents WHERE doc_type IN ({placeholders})", kinds)


def _derived_doc_ids(conn: sqlite3.Connection, kinds: tuple[str, ...]) -> tuple[str, ...]:
    placeholders = ",".join("?" for _ in kinds)
    rows = conn.execute(
        f"SELECT doc_id FROM memory_documents WHERE doc_type IN ({placeholders})",
        kinds,
    ).fetchall()
    return tuple(str(row["doc_id"]) for row in rows)


def _insert_document(conn: sqlite3.Connection, document: DerivedDocument) -> None:
    metadata_json = json.dumps(document.metadata, ensure_ascii=False, sort_keys=True)
    hash_row = {
        "doc_id": document.doc_id,
        "title": document.title,
        "body": document.body,
        "compact_text": document.compact_text,
        "metadata_json": metadata_json,
    }
    conn.execute(
        """
        INSERT INTO memory_documents (
            doc_id, doc_type, source_tweet_id, account_id, author_screen_name,
            title, body, compact_text, metadata_json,
            source_doc_hash, embedding_text_hash,
            created_at, observed_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            document.doc_id,
            document.doc_type,
            document.source_tweet_id,
            document.account_id,
            document.author_screen_name,
            document.title,
            document.body,
            document.compact_text,
            metadata_json,
            memory_document_source_hash(hash_row),
            memory_document_embedding_text_hash(hash_row),
            document.created_at,
            document.observed_at,
            document.updated_at,
        ),
    )


def _insert_fts(conn: sqlite3.Connection, document: DerivedDocument) -> None:
    conn.execute(
        """
        INSERT INTO memory_document_fts (
            doc_id, title, body, compact_text, author_screen_name, metadata_json
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            document.doc_id,
            document.title,
            document.body,
            document.compact_text,
            document.author_screen_name or "",
            json.dumps(document.metadata, ensure_ascii=False, sort_keys=True),
        ),
    )


def _dedupe_sources(rows: list[sqlite3.Row], *, limit: int) -> tuple[sqlite3.Row, ...]:
    def sort_key(row: sqlite3.Row) -> tuple[int, str]:
        priority = {"bookmark_doc": 4, "tweet_doc": 3, "quote_tree_doc": 2, "media_doc": 1}
        return (priority.get(str(row["doc_type"]), 0), str(row["observed_at"] or ""))

    selected: dict[str, sqlite3.Row] = {}
    for row in sorted(rows, key=sort_key, reverse=True):
        key = str(row["source_tweet_id"] or row["doc_id"])
        selected.setdefault(key, row)
        if len(selected) >= max(1, limit):
            break
    return tuple(selected.values())


def _row_text(row: sqlite3.Row) -> str:
    metadata = _loads_json(row["metadata_json"])
    return "\n".join(
        str(part)
        for part in (
            row["title"],
            row["body"],
            row["compact_text"],
            row["author_screen_name"],
            json.dumps(metadata, ensure_ascii=False),
        )
        if part
    )


def _terms_in_text(terms: tuple[str, ...], text: str) -> tuple[str, ...]:
    folded = text.casefold()
    return tuple(term for term in terms if term.casefold() in folded)


def _place_terms(row: sqlite3.Row, text: str) -> tuple[str, ...]:
    terms = list(_terms_in_text(PLACE_TERMS, text))
    metadata = _loads_json(row["metadata_json"])
    labels = tuple(str(label) for label in metadata.get("labels") or ())
    label_blob = " ".join(labels).casefold()
    if any(hint.casefold() in label_blob for hint in PLACE_LABEL_HINTS):
        terms.extend(label for label in labels[:6] if label)
    url = str(metadata.get("url") or "")
    domain = _domain(url)
    if domain and any(known in domain or known in url for known in PLACE_URL_DOMAINS):
        terms.append(domain)
    if _extract_areas(text) and any(
        token in text for token in ("行きたい", "行く", "場所", "スポット", "店", "会場", "展示")
    ):
        terms.append("place_hint")
    return _unique(terms)


def _extract_areas(text: str) -> tuple[str, ...]:
    values: list[str] = []
    for area in AREA_TERMS:
        if area.casefold() in text.casefold():
            values.append(area)
    patterns = (
        r"([一-龥ぁ-んァ-ンA-Za-z0-9ー・]{2,12})(?:の|にある|で)(?:カフェ|喫茶|居酒屋|レストラン|ラーメン|ピザ|イタリアン|店)",
        r"([一-龥ぁ-んァ-ンA-Za-z0-9ー・]{2,12})(?:駅|周辺|近く)",
    )
    for pattern in patterns:
        for match in re.findall(pattern, text):
            cleaned = _clean_candidate(match)
            if cleaned and cleaned not in values:
                values.append(cleaned)
    return tuple(values[:4])


def _place_key(
    row: sqlite3.Row,
    *,
    areas: tuple[str, ...],
    place_terms: tuple[str, ...],
) -> str:
    if areas:
        return "|".join(("area", areas[0]))
    metadata = _loads_json(row["metadata_json"])
    url = str(metadata.get("url") or "")
    domain = _domain(url)
    if domain:
        return "|".join(("domain", domain))
    return "|".join(("tweet", str(row["source_tweet_id"] or row["doc_id"]), *place_terms[:3]))


def _extract_companies(text: str) -> tuple[str, ...]:
    values: list[str] = []
    for token in CASHTAG_RE.findall(text):
        values.append(token.upper())
    for company in KNOWN_COMPANY_TERMS:
        if company.casefold() in text.casefold():
            values.append(company)
    patterns = (
        r"([A-Za-z0-9一-龥ぁ-んァ-ンー]{2,20})(?:の)?(?:株価|決算|急騰|急落|上方修正|下方修正)",
        r"(?:株価|決算|急騰|急落|上方修正|下方修正)(?:した|の)?([A-Za-z0-9一-龥ぁ-んァ-ンー]{2,20})",
    )
    for pattern in patterns:
        for match in re.findall(pattern, text):
            cleaned = _clean_candidate(match)
            if cleaned:
                values.append(cleaned)
    for token in LATIN_TOKEN_RE.findall(text):
        if token.startswith(("@", "#")):
            continue
        upper = token.upper()
        if 2 <= len(upper) <= 6 and any(term in text for term in FINANCE_TERMS):
            values.append(upper)
    return _unique(values)[:4]


def _top_labels(rows: tuple[sqlite3.Row, ...]) -> tuple[str, ...]:
    counter: Counter[str] = Counter()
    for row in rows:
        metadata = _loads_json(row["metadata_json"])
        for label in metadata.get("labels") or ():
            if label:
                counter[str(label)] += 1
    return tuple(label for label, _count in counter.most_common(8))


def _topic_thread_terms(row: sqlite3.Row, text: str) -> tuple[str, ...]:
    metadata = _loads_json(row["metadata_json"])
    labels = tuple(str(label) for label in metadata.get("labels") or () if label)
    terms = list(_terms_in_text(TOPIC_THREAD_TERMS, text))
    if labels and any(hint.casefold() in text.casefold() for hint in TOPIC_THREAD_HINTS):
        terms.extend(labels[:8])
    for label in labels:
        cleaned = _clean_topic_label(label)
        if cleaned and _topic_label_allowed(cleaned):
            terms.append(cleaned)
    return _unique(terms)[:8]


def _clean_topic_label(value: str) -> str:
    cleaned = _clean_candidate(value)
    if not cleaned:
        return ""
    return cleaned[:60]


def _topic_label_allowed(value: str) -> bool:
    lowered = value.casefold()
    if lowered in {"other", "その他", "unknown", "misc"}:
        return False
    return len(value) >= 2


def _source_urls(rows: tuple[sqlite3.Row, ...]) -> list[str]:
    urls: list[str] = []
    for row in rows:
        metadata = _loads_json(row["metadata_json"])
        url = metadata.get("url")
        if url and str(url) not in urls:
            urls.append(str(url))
    return urls[:8]


def _domain(url: str) -> str:
    if not url:
        return ""
    parsed = urlparse(url)
    return parsed.netloc.lower().removeprefix("www.")


def _stable_key(value: str) -> str:
    cleaned = re.sub(r"[^0-9A-Za-z一-龥ぁ-んァ-ンー_.-]+", "_", value).strip("_")
    if 1 <= len(cleaned) <= 80:
        return cleaned
    return hashlib.sha1(value.encode("utf-8"), usedforsecurity=False).hexdigest()[:20]


def _relation_id(source_doc_id: str, target_doc_id: str, relation_type: str) -> str:
    return hashlib.sha1(
        f"{source_doc_id}\0{target_doc_id}\0{relation_type}".encode(),
        usedforsecurity=False,
    ).hexdigest()[:24]


def _loads_json(value: str | None) -> dict[str, Any]:
    if not value:
        return {}
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _clean_candidate(value: str) -> str:
    return str(value).strip(" 　。、,.!?！？「」『』（）()[]【】").strip()


def _merge_tuple(left: tuple[str, ...], right: tuple[str, ...]) -> tuple[str, ...]:
    return _unique((*left, *right))


def _unique(values: Any) -> tuple[str, ...]:
    result: list[str] = []
    for value in values:
        text = str(value).strip()
        if text and text.casefold() not in {existing.casefold() for existing in result}:
            result.append(text)
    return tuple(result)


def _unique_source_rows(rows: list[sqlite3.Row]) -> list[sqlite3.Row]:
    seen: set[str] = set()
    result: list[sqlite3.Row] = []
    for row in rows:
        doc_id = str(row["doc_id"])
        if doc_id in seen:
            continue
        seen.add(doc_id)
        result.append(row)
    return result


def _min_datetime(values: Any) -> str | None:
    parsed = sorted(value for value in values if value)
    return str(parsed[0]) if parsed else None


def _max_datetime(values: Any) -> str | None:
    parsed = sorted(value for value in values if value)
    return str(parsed[-1]) if parsed else None


def _compact(value: str, *, limit: int) -> str:
    text = " ".join(str(value).split())
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 3)].rstrip() + "..."


def _utc_now() -> str:
    return datetime.now(tz=UTC).isoformat()
