from __future__ import annotations

import hashlib
import json
import sqlite3
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from research_x.memory.schema import ensure_memory_schema, memory_document_count


@dataclass(frozen=True)
class RelationBuildSummary:
    db_path: str
    relations: int
    by_type: dict[str, int]


@dataclass(frozen=True)
class MemoryRelation:
    relation_id: str
    source_doc_id: str
    target_doc_id: str
    relation_type: str
    strength: float
    status: str
    evidence: dict[str, Any]


def build_memory_relations(db_path: str | Path) -> RelationBuildSummary:
    path = Path(db_path)
    if not path.exists():
        raise FileNotFoundError(f"database not found: {path}")
    now = _utc_now()
    with sqlite3.connect(path, timeout=60) as conn:
        conn.row_factory = sqlite3.Row
        ensure_memory_schema(conn)
        if memory_document_count(conn) == 0:
            raise RuntimeError("memory_documents is empty; run memory build-corpus first")
        relations: dict[str, MemoryRelation] = {}
        _bookmark_of_tweet_relations(conn, relations)
        _media_relations(conn, relations)
        _quote_relations(conn, relations)
        _same_bookmarked_tweet_relations(conn, relations)
        _older_same_author_label_relations(conn, relations)
        _derived_document_relations(conn, relations)

        conn.execute("DELETE FROM memory_relations")
        for relation in relations.values():
            _insert_relation(conn, relation, now=now)
        by_type = Counter(relation.relation_type for relation in relations.values())
    return RelationBuildSummary(
        db_path=str(path),
        relations=len(relations),
        by_type=dict(sorted(by_type.items())),
    )


def relation_summary_for_docs(
    conn: sqlite3.Connection,
    doc_ids: tuple[str, ...],
) -> dict[str, dict[str, int]]:
    if not doc_ids:
        return {}
    placeholders = ",".join("?" for _ in doc_ids)
    rows = conn.execute(
        f"""
        SELECT source_doc_id AS doc_id, relation_type, COUNT(*) AS count
        FROM memory_relations
        WHERE source_doc_id IN ({placeholders})
        GROUP BY source_doc_id, relation_type
        UNION ALL
        SELECT
            target_doc_id AS doc_id,
            'incoming:' || relation_type AS relation_type,
            COUNT(*) AS count
        FROM memory_relations
        WHERE target_doc_id IN ({placeholders})
        GROUP BY target_doc_id, relation_type
        """,
        (*doc_ids, *doc_ids),
    ).fetchall()
    result: dict[str, dict[str, int]] = {doc_id: {} for doc_id in doc_ids}
    for row in rows:
        result.setdefault(row["doc_id"], {})[row["relation_type"]] = int(row["count"])
    return result


def relations_for_doc(
    db_path: str | Path,
    doc_id: str,
    *,
    limit: int = 20,
) -> tuple[MemoryRelation, ...]:
    path = Path(db_path)
    with sqlite3.connect(path, timeout=60) as conn:
        conn.row_factory = sqlite3.Row
        ensure_memory_schema(conn)
        rows = conn.execute(
            """
            SELECT
                relation_id, source_doc_id, target_doc_id, relation_type,
                strength, status, evidence_json
            FROM memory_relations
            WHERE source_doc_id = ? OR target_doc_id = ?
            ORDER BY strength DESC, relation_type, target_doc_id
            LIMIT ?
            """,
            (doc_id, doc_id, max(1, limit)),
        ).fetchall()
    return tuple(_relation_from_row(row) for row in rows)


def format_relations(relations: tuple[MemoryRelation, ...], *, json_output: bool = False) -> str:
    if json_output:
        return json.dumps(
            [asdict(relation) for relation in relations],
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    if not relations:
        return "(no memory relations)"
    lines = []
    for relation in relations:
        lines.append(
            " ".join(
                [
                    relation.relation_type,
                    f"{relation.strength:.2f}",
                    relation.status,
                    relation.source_doc_id,
                    "->",
                    relation.target_doc_id,
                ]
            )
        )
    return "\n".join(lines)


def summary_as_dict(summary: RelationBuildSummary) -> dict[str, Any]:
    return asdict(summary)


def _bookmark_of_tweet_relations(
    conn: sqlite3.Connection,
    relations: dict[str, MemoryRelation],
) -> None:
    rows = conn.execute(
        """
        SELECT account_id, tweet_id, bookmark_index, observed_at
        FROM account_bookmarks
        ORDER BY account_id, bookmark_index
        """
    ).fetchall()
    for row in rows:
        tweet_id = str(row["tweet_id"])
        _add_relation(
            relations,
            f"bookmark:{row['account_id']}:{tweet_id}",
            f"tweet:{tweet_id}",
            "bookmark_of_tweet",
            strength=1.0,
            evidence={
                "tweet_id": tweet_id,
                "account_id": row["account_id"],
                "bookmark_index": row["bookmark_index"],
                "observed_at": row["observed_at"],
            },
        )


def _media_relations(conn: sqlite3.Connection, relations: dict[str, MemoryRelation]) -> None:
    rows = conn.execute(
        """
        SELECT media_id, tweet_id, type, local_path, download_status
        FROM media
        ORDER BY tweet_id, media_id
        """
    ).fetchall()
    for row in rows:
        tweet_id = str(row["tweet_id"])
        media_id = str(row["media_id"])
        _add_relation(
            relations,
            f"tweet:{tweet_id}",
            f"media:{media_id}",
            "has_media",
            strength=0.8,
            evidence={
                "tweet_id": tweet_id,
                "media_id": media_id,
                "type": row["type"],
                "local_path": row["local_path"],
                "download_status": row["download_status"],
            },
        )


def _quote_relations(conn: sqlite3.Connection, relations: dict[str, MemoryRelation]) -> None:
    rows = conn.execute(
        """
        SELECT parent_tweet_id, child_tweet_id, child_also_bookmarked
        FROM tweet_edges
        WHERE relation = 'quote'
        ORDER BY parent_tweet_id, child_tweet_id
        """
    ).fetchall()
    parent_ids = set()
    for row in rows:
        parent_id = str(row["parent_tweet_id"])
        child_id = str(row["child_tweet_id"])
        parent_ids.add(parent_id)
        evidence = {
            "parent_tweet_id": parent_id,
            "child_tweet_id": child_id,
            "child_also_bookmarked": bool(row["child_also_bookmarked"]),
        }
        _add_relation(
            relations,
            f"tweet:{parent_id}",
            f"tweet:{child_id}",
            "quotes",
            strength=0.9,
            evidence=evidence,
        )
        _add_relation(
            relations,
            f"quote_tree:{parent_id}",
            f"tweet:{child_id}",
            "quote_tree_includes",
            strength=1.1,
            evidence=evidence,
        )
    for parent_id in parent_ids:
        _add_relation(
            relations,
            f"tweet:{parent_id}",
            f"quote_tree:{parent_id}",
            "has_quote_tree",
            strength=0.9,
            evidence={"parent_tweet_id": parent_id},
        )


def _same_bookmarked_tweet_relations(
    conn: sqlite3.Connection,
    relations: dict[str, MemoryRelation],
) -> None:
    rows = conn.execute(
        """
        SELECT tweet_id, account_id
        FROM account_bookmarks
        ORDER BY tweet_id, account_id
        """
    ).fetchall()
    by_tweet: dict[str, list[str]] = defaultdict(list)
    for row in rows:
        by_tweet[str(row["tweet_id"])].append(str(row["account_id"]))
    for tweet_id, accounts in by_tweet.items():
        unique_accounts = sorted(set(accounts))
        if len(unique_accounts) < 2:
            continue
        for account_id in unique_accounts:
            _add_relation(
                relations,
                f"bookmark:{account_id}:{tweet_id}",
                f"tweet:{tweet_id}",
                "same_bookmarked_tweet",
                strength=0.7,
                evidence={"tweet_id": tweet_id, "accounts": unique_accounts},
            )


def _older_same_author_label_relations(
    conn: sqlite3.Connection,
    relations: dict[str, MemoryRelation],
) -> None:
    rows = conn.execute(
        """
        SELECT
            d.doc_id, d.source_tweet_id, d.author_screen_name, d.created_at, d.observed_at,
            d.metadata_json
        FROM memory_documents d
        WHERE d.doc_type IN ('tweet_doc', 'bookmark_doc')
          AND d.author_screen_name IS NOT NULL
        ORDER BY d.author_screen_name, d.created_at, d.observed_at, d.doc_id
        """
    ).fetchall()
    grouped: dict[tuple[str, str], list[sqlite3.Row]] = defaultdict(list)
    for row in rows:
        labels = _loads_json(row["metadata_json"]).get("labels") or ()
        for label in labels:
            grouped[(str(row["author_screen_name"]).casefold(), str(label).casefold())].append(row)

    for (author, label), group in grouped.items():
        previous: sqlite3.Row | None = None
        previous_tweet_id: str | None = None
        for row in group:
            tweet_id = str(row["source_tweet_id"])
            if previous is not None and previous_tweet_id != tweet_id:
                _add_relation(
                    relations,
                    previous["doc_id"],
                    row["doc_id"],
                    "older_same_author_label",
                    strength=0.35,
                    status="stale_candidate",
                    evidence={
                        "author": author,
                        "label": label,
                        "older_date": previous["created_at"] or previous["observed_at"],
                        "newer_date": row["created_at"] or row["observed_at"],
                    },
                )
            previous = row
            previous_tweet_id = tweet_id


def _derived_document_relations(
    conn: sqlite3.Connection,
    relations: dict[str, MemoryRelation],
) -> None:
    rows = conn.execute(
        """
        SELECT doc_id, doc_type, metadata_json
        FROM memory_documents
        WHERE doc_type IN ('place_card', 'author_profile', 'ticker_event')
        ORDER BY doc_type, doc_id
        """
    ).fetchall()
    for row in rows:
        metadata = _loads_json(row["metadata_json"])
        for source_doc_id in metadata.get("source_doc_ids") or ():
            if not source_doc_id:
                continue
            _add_relation(
                relations,
                str(row["doc_id"]),
                str(source_doc_id),
                "derived_from_source",
                strength=0.65,
                status="derived",
                evidence={
                    "derived_kind": row["doc_type"],
                    "source_doc_id": str(source_doc_id),
                },
            )


def _add_relation(
    relations: dict[str, MemoryRelation],
    source_doc_id: str,
    target_doc_id: str,
    relation_type: str,
    *,
    strength: float,
    evidence: dict[str, Any],
    status: str = "active",
) -> None:
    if source_doc_id == target_doc_id:
        return
    relation_id = _relation_id(source_doc_id, target_doc_id, relation_type)
    relation = MemoryRelation(
        relation_id=relation_id,
        source_doc_id=source_doc_id,
        target_doc_id=target_doc_id,
        relation_type=relation_type,
        strength=strength,
        status=status,
        evidence=evidence,
    )
    current = relations.get(relation_id)
    if current is None or relation.strength > current.strength:
        relations[relation_id] = relation


def _insert_relation(conn: sqlite3.Connection, relation: MemoryRelation, *, now: str) -> None:
    conn.execute(
        """
        INSERT INTO memory_relations (
            relation_id, source_doc_id, target_doc_id, relation_type,
            strength, status, evidence_json, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            relation.relation_id,
            relation.source_doc_id,
            relation.target_doc_id,
            relation.relation_type,
            relation.strength,
            relation.status,
            json.dumps(relation.evidence, ensure_ascii=False, sort_keys=True),
            now,
            now,
        ),
    )


def _relation_from_row(row: sqlite3.Row) -> MemoryRelation:
    return MemoryRelation(
        relation_id=row["relation_id"],
        source_doc_id=row["source_doc_id"],
        target_doc_id=row["target_doc_id"],
        relation_type=row["relation_type"],
        strength=float(row["strength"]),
        status=row["status"],
        evidence=_loads_json(row["evidence_json"]),
    )


def _relation_id(source_doc_id: str, target_doc_id: str, relation_type: str) -> str:
    digest = hashlib.sha1(f"{source_doc_id}\0{target_doc_id}\0{relation_type}".encode()).hexdigest()
    return digest[:24]


def _loads_json(value: str | None) -> dict[str, Any]:
    if not value:
        return {}
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _utc_now() -> str:
    return datetime.now(tz=UTC).isoformat()
