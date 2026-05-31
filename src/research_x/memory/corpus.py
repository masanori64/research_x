from __future__ import annotations

import json
import sqlite3
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from research_x.memory.schema import ensure_memory_schema


@dataclass(frozen=True)
class MemoryDocument:
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


@dataclass(frozen=True)
class CorpusBuildSummary:
    db_path: str
    documents: int
    tweet_docs: int
    bookmark_docs: int
    quote_tree_docs: int
    media_docs: int


@dataclass(frozen=True)
class Corpus2SkillBundleSummary:
    db_path: str
    out_dir: str
    corpus_path: str
    manifest_path: str
    documents: int
    by_doc_type: dict[str, int]


def build_memory_corpus(db_path: str | Path) -> CorpusBuildSummary:
    path = Path(db_path)
    if not path.exists():
        raise FileNotFoundError(f"database not found: {path}")
    with sqlite3.connect(path, timeout=60) as conn:
        conn.row_factory = sqlite3.Row
        ensure_memory_schema(conn)
        documents = _load_documents(conn)
        conn.execute("DELETE FROM memory_relations")
        conn.execute("DELETE FROM memory_document_fts")
        conn.execute("DELETE FROM memory_documents")
        for document in documents:
            _insert_document(conn, document)
            _insert_fts(conn, document)
        conn.execute(
            """
            DELETE FROM memory_embeddings
            WHERE doc_id NOT IN (SELECT doc_id FROM memory_documents)
            """
        )
        counts = _counts(documents)
    return CorpusBuildSummary(db_path=str(path), documents=len(documents), **counts)


def export_corpus2skill_jsonl(
    db_path: str | Path,
    out_path: str | Path,
    *,
    limit: int | None = None,
) -> int:
    path = Path(db_path)
    output = Path(out_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path, timeout=60) as conn, output.open("w", encoding="utf-8") as handle:
        conn.row_factory = sqlite3.Row
        ensure_memory_schema(conn)
        rows = _corpus2skill_rows(conn, limit=limit)
        for row in rows:
            handle.write(json.dumps(_corpus2skill_record(row), ensure_ascii=False) + "\n")
    return len(rows)


def export_corpus2skill_bundle(
    db_path: str | Path,
    out_dir: str | Path,
    *,
    limit: int | None = None,
) -> Corpus2SkillBundleSummary:
    path = Path(db_path)
    output = Path(out_dir)
    output.mkdir(parents=True, exist_ok=True)
    corpus_path = output / "corpus.jsonl"
    manifest_path = output / "manifest.json"
    with sqlite3.connect(path, timeout=60) as conn, corpus_path.open(
        "w",
        encoding="utf-8",
    ) as handle:
        conn.row_factory = sqlite3.Row
        ensure_memory_schema(conn)
        rows = _corpus2skill_rows(conn, limit=limit)
        for row in rows:
            handle.write(json.dumps(_corpus2skill_record(row), ensure_ascii=False) + "\n")
    by_doc_type = dict(sorted(Counter(str(row["doc_type"]) for row in rows).items()))
    manifest = {
        "format": "corpus2skill-jsonl-bundle-v1",
        "db_path": str(path),
        "corpus_path": str(corpus_path),
        "documents": len(rows),
        "by_doc_type": by_doc_type,
        "compile_hint": [
            "uv",
            "run",
            "python",
            "-m",
            "corpus2skill",
            "compile",
            "--input",
            str(corpus_path),
            "--output",
            str(output / "compiled"),
        ],
        "contract": {
            "id": "memory_documents.doc_id",
            "contents": "title + compact_text + body + metadata",
            "metadata": "trace data for research_x; Corpus2Skill may ignore extra fields",
        },
    }
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return Corpus2SkillBundleSummary(
        db_path=str(path),
        out_dir=str(output),
        corpus_path=str(corpus_path),
        manifest_path=str(manifest_path),
        documents=len(rows),
        by_doc_type=by_doc_type,
    )


def _load_documents(conn: sqlite3.Connection) -> tuple[MemoryDocument, ...]:
    documents: list[MemoryDocument] = []
    documents.extend(_tweet_documents(conn))
    documents.extend(_bookmark_documents(conn))
    documents.extend(_quote_tree_documents(conn))
    documents.extend(_media_documents(conn))
    return tuple(documents)


def _corpus2skill_rows(conn: sqlite3.Connection, *, limit: int | None) -> list[sqlite3.Row]:
    sql = """
        SELECT
            doc_id, doc_type, source_tweet_id, account_id, author_screen_name,
            title, compact_text, body, metadata_json, created_at, observed_at, updated_at
        FROM memory_documents
        ORDER BY doc_type, observed_at DESC, doc_id
    """
    params: tuple[Any, ...] = ()
    if limit is not None and limit > 0:
        sql += " LIMIT ?"
        params = (limit,)
    return conn.execute(sql, params).fetchall()


def _corpus2skill_record(row: sqlite3.Row) -> dict[str, Any]:
    contents = "\n".join(
        part
        for part in (
            row["title"] or "",
            row["compact_text"] or "",
            row["body"] or "",
            f"metadata: {row['metadata_json'] or '{}'}",
        )
        if part
    )
    return {
        "id": row["doc_id"],
        "contents": contents,
        "metadata": {
            "doc_type": row["doc_type"],
            "source_tweet_id": row["source_tweet_id"],
            "account_id": row["account_id"],
            "author_screen_name": row["author_screen_name"],
            "created_at": row["created_at"],
            "observed_at": row["observed_at"],
            "updated_at": row["updated_at"],
            "research_x_metadata": _loads_json(row["metadata_json"], default={}),
        },
    }


def _tweet_documents(conn: sqlite3.Connection) -> list[MemoryDocument]:
    rows = conn.execute(
        """
        SELECT
            t.tweet_id, t.url, t.author_screen_name, t.text, t.created_at,
            t.first_observed_at, t.last_observed_at, t.role, t.collection_kind,
            t.updated_at
        FROM tweets t
        ORDER BY t.last_observed_at DESC, t.tweet_id
        """
    ).fetchall()
    labels = _labels_by_tweet(conn)
    media = _media_count_by_tweet(conn)
    result = []
    for row in rows:
        tweet_id = str(row["tweet_id"])
        label_values = labels.get(tweet_id, ())
        metadata = {
            "url": row["url"],
            "role": row["role"],
            "collection_kind": row["collection_kind"],
            "labels": label_values,
            "media_count": media.get(tweet_id, 0),
        }
        body = _lines(
            f"tweet_id: {tweet_id}",
            f"author: @{row['author_screen_name']}" if row["author_screen_name"] else None,
            f"url: {row['url']}" if row["url"] else None,
            f"role: {row['role']}" if row["role"] else None,
            f"labels: {', '.join(label_values)}" if label_values else None,
            row["text"],
        )
        result.append(
            MemoryDocument(
                doc_id=f"tweet:{tweet_id}",
                doc_type="tweet_doc",
                source_tweet_id=tweet_id,
                account_id=None,
                author_screen_name=row["author_screen_name"],
                title=_title(row["author_screen_name"], tweet_id, row["created_at"]),
                body=body,
                compact_text=_compact(row["text"] or body),
                metadata=metadata,
                created_at=row["created_at"],
                observed_at=row["last_observed_at"] or row["first_observed_at"],
                updated_at=row["updated_at"],
            )
        )
    return result


def _bookmark_documents(conn: sqlite3.Connection) -> list[MemoryDocument]:
    rows = conn.execute(
        """
        SELECT
            ab.account_id, ab.tweet_id, ab.bookmark_index, ab.observed_at,
            t.url, t.author_screen_name, t.text, t.created_at, t.role, t.updated_at
        FROM account_bookmarks ab
        JOIN tweets t ON t.tweet_id = ab.tweet_id
        ORDER BY ab.account_id, ab.bookmark_index ASC, ab.observed_at DESC
        """
    ).fetchall()
    labels = _labels_by_scope(conn, "bookmarks")
    result = []
    for row in rows:
        tweet_id = str(row["tweet_id"])
        account_id = row["account_id"]
        label_values = labels.get((tweet_id, account_id), ()) or labels.get((tweet_id, None), ())
        title = _title(row["author_screen_name"], tweet_id, row["created_at"])
        metadata = {
            "url": row["url"],
            "bookmark_index": row["bookmark_index"],
            "labels": label_values,
            "role": row["role"],
        }
        body = _lines(
            f"bookmark_account: {account_id}",
            f"bookmark_index: {row['bookmark_index']}",
            f"tweet_id: {tweet_id}",
            f"author: @{row['author_screen_name']}" if row["author_screen_name"] else None,
            f"url: {row['url']}" if row["url"] else None,
            f"labels: {', '.join(label_values)}" if label_values else None,
            row["text"],
        )
        result.append(
            MemoryDocument(
                doc_id=f"bookmark:{account_id}:{tweet_id}",
                doc_type="bookmark_doc",
                source_tweet_id=tweet_id,
                account_id=account_id,
                author_screen_name=row["author_screen_name"],
                title=f"bookmark {account_id} {title}",
                body=body,
                compact_text=_compact(row["text"] or body),
                metadata=metadata,
                created_at=row["created_at"],
                observed_at=row["observed_at"],
                updated_at=row["updated_at"],
            )
        )
    return result


def _quote_tree_documents(conn: sqlite3.Connection) -> list[MemoryDocument]:
    rows = conn.execute(
        """
        SELECT
            e.parent_tweet_id, e.child_tweet_id, e.child_also_bookmarked,
            p.url AS parent_url, p.author_screen_name AS parent_author,
            p.text AS parent_text, p.created_at AS parent_created_at,
            p.last_observed_at AS parent_observed_at,
            c.url AS child_url, c.author_screen_name AS child_author,
            c.text AS child_text, c.created_at AS child_created_at
        FROM tweet_edges e
        JOIN tweets p ON p.tweet_id = e.parent_tweet_id
        JOIN tweets c ON c.tweet_id = e.child_tweet_id
        WHERE e.relation = 'quote'
        ORDER BY e.parent_tweet_id, e.child_tweet_id
        """
    ).fetchall()
    grouped: dict[str, list[sqlite3.Row]] = {}
    for row in rows:
        grouped.setdefault(str(row["parent_tweet_id"]), []).append(row)
    account_by_tweet = _first_bookmark_account_by_tweet(conn)
    result = []
    for parent_id, group in grouped.items():
        first = group[0]
        title = _title(first["parent_author"], parent_id, first["parent_created_at"])
        quotes = [
            _lines(
                f"quoted_tweet_id: {row['child_tweet_id']}",
                f"quoted_author: @{row['child_author']}" if row["child_author"] else None,
                f"quoted_url: {row['child_url']}" if row["child_url"] else None,
                row["child_text"],
            )
            for row in group
        ]
        body = _lines(
            f"root_tweet_id: {parent_id}",
            f"root_author: @{first['parent_author']}" if first["parent_author"] else None,
            f"root_url: {first['parent_url']}" if first["parent_url"] else None,
            "root_text:",
            first["parent_text"],
            "quoted_context:",
            "\n---\n".join(quotes),
        )
        result.append(
            MemoryDocument(
                doc_id=f"quote_tree:{parent_id}",
                doc_type="quote_tree_doc",
                source_tweet_id=parent_id,
                account_id=account_by_tweet.get(parent_id),
                author_screen_name=first["parent_author"],
                title=f"quote tree {title}",
                body=body,
                compact_text=_compact(body, limit=640),
                metadata={
                    "url": first["parent_url"],
                    "quoted_count": len(group),
                    "quoted_tweet_ids": [str(row["child_tweet_id"]) for row in group],
                },
                created_at=first["parent_created_at"],
                observed_at=first["parent_observed_at"],
                updated_at=None,
            )
        )
    return result


def _media_documents(conn: sqlite3.Connection) -> list[MemoryDocument]:
    rows = conn.execute(
        """
        SELECT
            m.media_id, m.tweet_id, m.type, m.url AS media_url, m.alt_text,
            m.local_path, m.download_status,
            t.url AS tweet_url, t.author_screen_name, t.text, t.created_at,
            t.last_observed_at, t.updated_at
        FROM media m
        JOIN tweets t ON t.tweet_id = m.tweet_id
        ORDER BY t.last_observed_at DESC, m.media_id
        """
    ).fetchall()
    account_by_tweet = _first_bookmark_account_by_tweet(conn)
    result = []
    for row in rows:
        title = _title(row["author_screen_name"], row["tweet_id"], row["created_at"])
        body = _lines(
            f"media_id: {row['media_id']}",
            f"media_type: {row['type']}",
            f"media_url: {row['media_url']}" if row["media_url"] else None,
            f"local_path: {row['local_path']}" if row["local_path"] else None,
            f"download_status: {row['download_status']}" if row["download_status"] else None,
            f"tweet_id: {row['tweet_id']}",
            f"author: @{row['author_screen_name']}" if row["author_screen_name"] else None,
            f"tweet_url: {row['tweet_url']}" if row["tweet_url"] else None,
            f"alt_text: {row['alt_text']}" if row["alt_text"] else None,
            row["text"],
        )
        result.append(
            MemoryDocument(
                doc_id=f"media:{row['media_id']}",
                doc_type="media_doc",
                source_tweet_id=str(row["tweet_id"]),
                account_id=account_by_tweet.get(str(row["tweet_id"])),
                author_screen_name=row["author_screen_name"],
                title=f"media {row['type'] or ''} {title}",
                body=body,
                compact_text=_compact(row["alt_text"] or row["text"] or body),
                metadata={
                    "url": row["tweet_url"],
                    "media_url": row["media_url"],
                    "local_path": row["local_path"],
                    "download_status": row["download_status"],
                    "type": row["type"],
                },
                created_at=row["created_at"],
                observed_at=row["last_observed_at"],
                updated_at=row["updated_at"],
            )
        )
    return result


def _insert_document(conn: sqlite3.Connection, document: MemoryDocument) -> None:
    conn.execute(
        """
        INSERT INTO memory_documents (
            doc_id, doc_type, source_tweet_id, account_id, author_screen_name,
            title, body, compact_text, metadata_json, created_at, observed_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(doc_id) DO UPDATE SET
            doc_type=excluded.doc_type,
            source_tweet_id=excluded.source_tweet_id,
            account_id=excluded.account_id,
            author_screen_name=excluded.author_screen_name,
            title=excluded.title,
            body=excluded.body,
            compact_text=excluded.compact_text,
            metadata_json=excluded.metadata_json,
            created_at=excluded.created_at,
            observed_at=excluded.observed_at,
            updated_at=excluded.updated_at
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
            json.dumps(document.metadata, ensure_ascii=False, sort_keys=True),
            document.created_at,
            document.observed_at,
            document.updated_at,
        ),
    )


def _insert_fts(conn: sqlite3.Connection, document: MemoryDocument) -> None:
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


def _counts(documents: tuple[MemoryDocument, ...]) -> dict[str, int]:
    return {
        "tweet_docs": sum(1 for doc in documents if doc.doc_type == "tweet_doc"),
        "bookmark_docs": sum(1 for doc in documents if doc.doc_type == "bookmark_doc"),
        "quote_tree_docs": sum(1 for doc in documents if doc.doc_type == "quote_tree_doc"),
        "media_docs": sum(1 for doc in documents if doc.doc_type == "media_doc"),
    }


def _labels_by_tweet(conn: sqlite3.Connection) -> dict[str, tuple[str, ...]]:
    rows = conn.execute(
        """
        SELECT tweet_id, category_label, category_id, tags_json
        FROM ai_labels
        ORDER BY generated_at DESC
        """
    ).fetchall()
    result: dict[str, list[str]] = {}
    for row in rows:
        values = result.setdefault(str(row["tweet_id"]), [])
        for value in (row["category_label"], row["category_id"]):
            if value and value not in values:
                values.append(str(value))
        for tag in _loads_json(row["tags_json"], default=[]):
            if tag and str(tag) not in values:
                values.append(str(tag))
    return {key: tuple(values) for key, values in result.items()}


def _labels_by_scope(
    conn: sqlite3.Connection,
    scope: str,
) -> dict[tuple[str, str | None], tuple[str, ...]]:
    rows = conn.execute(
        """
        SELECT tweet_id, account_id, category_label, category_id, tags_json
        FROM ai_labels
        WHERE label_scope = ?
        ORDER BY generated_at DESC
        """,
        (scope,),
    ).fetchall()
    result: dict[tuple[str, str | None], list[str]] = {}
    for row in rows:
        key = (str(row["tweet_id"]), row["account_id"])
        values = result.setdefault(key, [])
        for value in (row["category_label"], row["category_id"]):
            if value and value not in values:
                values.append(str(value))
        for tag in _loads_json(row["tags_json"], default=[]):
            if tag and str(tag) not in values:
                values.append(str(tag))
    return {key: tuple(values) for key, values in result.items()}


def _media_count_by_tweet(conn: sqlite3.Connection) -> dict[str, int]:
    rows = conn.execute("SELECT tweet_id, COUNT(*) FROM media GROUP BY tweet_id").fetchall()
    return {str(row[0]): int(row[1]) for row in rows}


def _first_bookmark_account_by_tweet(conn: sqlite3.Connection) -> dict[str, str]:
    rows = conn.execute(
        """
        SELECT tweet_id, MIN(account_id)
        FROM account_bookmarks
        GROUP BY tweet_id
        """
    ).fetchall()
    return {str(row[0]): str(row[1]) for row in rows if row[1]}


def _loads_json(value: str | None, *, default: Any) -> Any:
    if not value:
        return default
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return default


def _title(author: str | None, tweet_id: Any, created_at: str | None) -> str:
    author_text = f"@{author}" if author else "unknown_author"
    date_text = f" {created_at[:10]}" if created_at else ""
    return f"{author_text}{date_text} tweet {tweet_id}"


def _lines(*values: str | None) -> str:
    return "\n".join(str(value).strip() for value in values if value not in (None, ""))


def _compact(value: str, *, limit: int = 360) -> str:
    text = " ".join(str(value).split())
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "..."


def _utc_now() -> str:
    return datetime.now(tz=UTC).isoformat()


def summary_as_dict(summary: CorpusBuildSummary) -> dict[str, Any]:
    return asdict(summary)
