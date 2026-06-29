from __future__ import annotations

import hashlib
import json
import mimetypes
import sqlite3
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from research_x.memory.schema import ensure_memory_schema

MEDIA_ROLE_PROVIDER = "local_heuristic"
MEDIA_ROLE_MODEL = "media-role-heuristic-v1"
MEDIA_ROLE_EVIDENCE_LEVEL = "media_role_profile"

_FULL_BBOX = {"type": "full_media", "x": 0.0, "y": 0.0, "width": 1.0, "height": 1.0}


@dataclass(frozen=True)
class MediaRoleProfile:
    media_id: str
    source_tweet_id: str
    roles: tuple[str, ...]
    primary_role: str
    evidence_actions: tuple[str, ...]
    confidence: float
    reasons: tuple[str, ...]
    source_image_hash: str | None
    metadata: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["roles"] = list(self.roles)
        payload["evidence_actions"] = list(self.evidence_actions)
        payload["reasons"] = list(self.reasons)
        return payload


@dataclass(frozen=True)
class MediaRoleSummary:
    db_path: str
    media: int
    selected: int
    stored: int
    by_role: dict[str, int]
    by_action: dict[str, int]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class MediaRoleCoverage:
    db_path: str
    profiles: int
    by_role: dict[str, int]
    by_action: dict[str, int]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def estimate_media_roles(
    db_path: str | Path,
    *,
    limit: int | None = 100,
) -> MediaRoleSummary:
    profiles = _selected_profiles(_media_role_profiles(db_path), limit=limit)
    return MediaRoleSummary(
        db_path=str(Path(db_path)),
        media=len(_media_role_profiles(db_path)),
        selected=len(profiles),
        stored=0,
        by_role=_count_profiles(profiles, "roles"),
        by_action=_count_profiles(profiles, "evidence_actions"),
    )


def build_media_roles(
    db_path: str | Path,
    *,
    limit: int | None = 100,
) -> MediaRoleSummary:
    path = Path(db_path)
    profiles = _selected_profiles(_media_role_profiles(path), limit=limit)
    now = _utc_now()
    with sqlite3.connect(path, timeout=60) as conn:
        conn.row_factory = sqlite3.Row
        ensure_memory_schema(conn)
        for profile in profiles:
            _insert_media_role_profile(conn, profile, now=now)
        conn.commit()
    return MediaRoleSummary(
        db_path=str(path),
        media=len(_media_role_profiles(path)),
        selected=len(profiles),
        stored=len(profiles),
        by_role=_count_profiles(profiles, "roles"),
        by_action=_count_profiles(profiles, "evidence_actions"),
    )


def media_role_coverage(db_path: str | Path) -> MediaRoleCoverage:
    with sqlite3.connect(db_path, timeout=60) as conn:
        ensure_memory_schema(conn)
        rows = conn.execute(
            """
            SELECT metadata_json
            FROM memory_visual_recall_evidence
            WHERE evidence_level = ?
            """,
            (MEDIA_ROLE_EVIDENCE_LEVEL,),
        ).fetchall()
    profiles = [_loads_json(row[0]) for row in rows]
    return MediaRoleCoverage(
        db_path=str(Path(db_path)),
        profiles=len(profiles),
        by_role=_count_metadata(profiles, "roles"),
        by_action=_count_metadata(profiles, "evidence_actions"),
    )


def media_role_summary_json(summary: MediaRoleSummary | MediaRoleCoverage) -> str:
    return json.dumps(summary.as_dict(), ensure_ascii=False, indent=2, sort_keys=True)


def format_media_role_summary(summary: MediaRoleSummary | MediaRoleCoverage) -> str:
    if isinstance(summary, MediaRoleCoverage):
        return "\n".join(
            (
                f"db: {summary.db_path}",
                f"profiles: {summary.profiles}",
                f"by_role: {json.dumps(summary.by_role, ensure_ascii=False, sort_keys=True)}",
                f"by_action: {json.dumps(summary.by_action, ensure_ascii=False, sort_keys=True)}",
            )
        )
    return "\n".join(
        (
            f"db: {summary.db_path}",
            f"media: {summary.media}",
            f"selected: {summary.selected}",
            f"stored: {summary.stored}",
            f"by_role: {json.dumps(summary.by_role, ensure_ascii=False, sort_keys=True)}",
            f"by_action: {json.dumps(summary.by_action, ensure_ascii=False, sort_keys=True)}",
        )
    )


def _media_role_profiles(db_path: str | Path) -> tuple[MediaRoleProfile, ...]:
    path = Path(db_path)
    with sqlite3.connect(path, timeout=60) as conn:
        conn.row_factory = sqlite3.Row
        ensure_memory_schema(conn)
        rows = conn.execute(
            """
            SELECT
                m.media_id, m.tweet_id, m.type, m.url AS media_url, m.alt_text,
                m.local_path, m.download_status, m.content_type, m.bytes,
                t.url AS tweet_url, t.author_screen_name, t.text AS tweet_text
            FROM media m
            JOIN tweets t ON t.tweet_id = m.tweet_id
            ORDER BY t.last_observed_at DESC, m.media_id
            """
        ).fetchall()
    return tuple(_classify_media_role(row, db_path=path) for row in rows)


def _classify_media_role(row: sqlite3.Row, *, db_path: Path) -> MediaRoleProfile:
    text = " ".join(
        str(row[key] or "")
        for key in ("media_url", "alt_text", "tweet_text", "author_screen_name")
    ).casefold()
    mime_type = _mime_type(row)
    resolved_path = _resolve_media_path(str(row["local_path"] or ""), db_path=db_path)
    source_hash = _file_hash(resolved_path) if resolved_path else None
    roles: list[str] = []
    reasons: list[str] = []

    def add(role: str, reason: str) -> None:
        if role not in roles:
            roles.append(role)
        reasons.append(reason)

    if mime_type == "application/pdf":
        add("document_page", "mime:pdf")
    if _has_any(text, "slide", "スライド", "プレゼン", "資料"):
        add("slide_or_presentation", "text:slide")
    if _has_any(text, "paper", "論文", "arxiv", "研究", "学会"):
        add("scientific_figure", "text:research")
    if _has_any(text, "chart", "graph", "グラフ", "チャート", "株価", "決算"):
        add("chart_or_graph", "text:chart")
    if _has_any(text, "table", "表", "フォーム", "form", "帳票"):
        add("table_or_form", "text:table")
    if _has_any(text, "diagram", "図解", "architecture", "アーキテクチャ", "ネットワーク"):
        add("diagram_or_architecture", "text:diagram")
    if _has_any(text, "screenshot", "スクショ", "画面", "ui", "terminal", "設定"):
        add("screenshot_ui", "text:screenshot")
    if _has_any(text, "error", "エラー", "stacktrace", "traceback", "コード", "code", "api"):
        add("code_or_error_screenshot", "text:code-error")
    if _has_any(text, "map", "地図", "アクセス", "住所", "location"):
        add("map_or_location", "text:map-location")
    if _has_any(text, "meme", "ネタ", "面白", "画像マクロ", "大喜利"):
        add("meme_or_image_macro", "text:meme")
    if _has_any(text, "漫画", "manga", "吹き出し", "縦書", "同人"):
        add("manga_or_vertical_comic", "text:manga")
    if _has_any(text, "イラスト", "illust", "art", "二次元", "キャラ", "公式キャラクター"):
        add("illustration_or_art", "text:illustration")
    if _has_any(text, "カフェ", "cafe", "料理", "飯", "ランチ", "ピザ", "居酒屋", "ラーメン", "店"):
        add("photo_place_food", "text:place-food")
    if _has_any(text, "商品", "product", "ガジェット", "本", "服", "フィギュア"):
        add("photo_product_object", "text:product-object")
    if _has_any(text, "イベント", "登壇", "ライブ", "展示", "美術館", "人", "人物"):
        add("photo_person_event", "text:person-event")

    if not roles:
        if row["alt_text"]:
            add("unknown_media", "alt_text_present")
        else:
            add("decorative_or_reaction", "no_textual_media_signal")

    actions = _actions_for_roles(tuple(roles))
    confidence = min(0.95, 0.45 + (0.1 * min(len(reasons), 5)))
    metadata = {
        "provider": MEDIA_ROLE_PROVIDER,
        "model": MEDIA_ROLE_MODEL,
        "roles": roles,
        "primary_role": roles[0],
        "evidence_actions": list(actions),
        "confidence": round(confidence, 3),
        "reasons": reasons,
        "mime_type": mime_type,
        "media_url": row["media_url"],
        "tweet_url": row["tweet_url"],
        "tweet_text_chars": len(str(row["tweet_text"] or "")),
        "has_alt_text": bool(row["alt_text"]),
        "contract": "media_role_profile_is_routing_annotation_not_evidence",
    }
    return MediaRoleProfile(
        media_id=str(row["media_id"]),
        source_tweet_id=str(row["tweet_id"] or ""),
        roles=tuple(roles),
        primary_role=roles[0],
        evidence_actions=actions,
        confidence=round(confidence, 3),
        reasons=tuple(reasons),
        source_image_hash=source_hash,
        metadata=metadata,
    )


def _actions_for_roles(roles: tuple[str, ...]) -> tuple[str, ...]:
    actions: list[str] = []

    def add(action: str) -> None:
        if action not in actions:
            actions.append(action)

    if any(role in roles for role in ("document_page", "slide_or_presentation", "table_or_form")):
        add("ocr_layout_candidate")
    if any(role in roles for role in ("screenshot_ui", "code_or_error_screenshot")):
        add("ocr_candidate")
    if any(
        role in roles
        for role in ("chart_or_graph", "diagram_or_architecture", "scientific_figure")
    ):
        add("chart_or_visual_reasoning_candidate")
        add("hybrid_ocr_vlm_candidate")
    if any(role in roles for role in ("meme_or_image_macro", "manga_or_vertical_comic")):
        add("hybrid_ocr_vlm_candidate")
    if any(
        role in roles
        for role in (
            "photo_place_food",
            "photo_product_object",
            "photo_person_event",
            "illustration_or_art",
            "map_or_location",
        )
    ):
        add("caption_candidate")
    if "decorative_or_reaction" in roles:
        add("none_source_only")
    if not actions:
        add("caption_candidate")
    return tuple(actions)


def _insert_media_role_profile(
    conn: sqlite3.Connection,
    profile: MediaRoleProfile,
    *,
    now: str,
) -> None:
    visual_id = _stable_id("media-role", profile.media_id, MEDIA_ROLE_MODEL)
    conn.execute(
        """
        INSERT INTO memory_visual_recall_evidence (
            visual_evidence_id, media_id, source_tweet_id, evidence_level, page_index,
            region_index, pixel_bbox_json, normalized_bbox_json, citation_ready,
            source_image_hash, provider, model, created_at, metadata_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(visual_evidence_id) DO UPDATE SET
            source_tweet_id=excluded.source_tweet_id,
            source_image_hash=excluded.source_image_hash,
            provider=excluded.provider,
            model=excluded.model,
            metadata_json=excluded.metadata_json
        """,
        (
            visual_id,
            profile.media_id,
            profile.source_tweet_id,
            MEDIA_ROLE_EVIDENCE_LEVEL,
            0,
            0,
            json.dumps(_FULL_BBOX, ensure_ascii=False, sort_keys=True),
            json.dumps(_FULL_BBOX, ensure_ascii=False, sort_keys=True),
            0,
            profile.source_image_hash,
            MEDIA_ROLE_PROVIDER,
            MEDIA_ROLE_MODEL,
            now,
            json.dumps(profile.metadata, ensure_ascii=False, sort_keys=True),
        ),
    )


def _selected_profiles(
    profiles: tuple[MediaRoleProfile, ...],
    *,
    limit: int | None,
) -> tuple[MediaRoleProfile, ...]:
    if limit is None or limit < 0:
        return profiles
    return profiles[:limit]


def _count_profiles(profiles: tuple[MediaRoleProfile, ...], attr: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for profile in profiles:
        values = getattr(profile, attr)
        for value in values:
            counts[str(value)] = counts.get(str(value), 0) + 1
    return dict(sorted(counts.items()))


def _count_metadata(rows: list[dict[str, Any]], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        values = row.get(key) or ()
        if not isinstance(values, list):
            continue
        for value in values:
            counts[str(value)] = counts.get(str(value), 0) + 1
    return dict(sorted(counts.items()))


def _mime_type(row: sqlite3.Row) -> str:
    if row["content_type"]:
        return str(row["content_type"]).split(";")[0].strip().lower()
    guessed, _ = mimetypes.guess_type(str(row["local_path"] or row["media_url"] or ""))
    return guessed or "application/octet-stream"


def _resolve_media_path(local_path: str, *, db_path: Path) -> Path | None:
    if not local_path:
        return None
    raw = Path(local_path)
    candidates = [raw]
    if not raw.is_absolute():
        candidates.append(db_path.parent / raw)
        candidates.append(Path.cwd() / raw)
    for candidate in candidates:
        if candidate.exists() and candidate.is_file():
            return candidate
    return None


def _file_hash(path: Path | None) -> str | None:
    if path is None:
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _stable_id(*parts: object) -> str:
    return hashlib.sha256(
        "|".join(str(part) for part in parts).encode("utf-8")
    ).hexdigest()[:24]


def _has_any(text: str, *terms: str) -> bool:
    return any(term.casefold() in text for term in terms)


def _loads_json(value: str | bytes | None) -> dict[str, Any]:
    if not value:
        return {}
    try:
        loaded = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return loaded if isinstance(loaded, dict) else {}


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()
