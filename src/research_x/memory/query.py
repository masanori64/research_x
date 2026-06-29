from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class IntentProfile:
    intent_id: str
    label: str
    triggers: tuple[str, ...]
    expansions: tuple[str, ...]
    doc_type_weights: dict[str, float]


@dataclass(frozen=True)
class QueryPlan:
    original_query: str
    normalized_query: str
    search_terms: tuple[str, ...]
    exact_terms: tuple[str, ...]
    intents: tuple[str, ...]
    doc_type_weights: dict[str, float]
    prefers_recent: bool
    excludes_old: bool
    requires_bookmark_context: bool
    requires_quote_context: bool
    requires_media_context: bool
    wants_cross_account: bool
    wants_event_dates: bool
    author_terms: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


INTENT_PROFILES: tuple[IntentProfile, ...] = (
    IntentProfile(
        intent_id="food",
        label="food/place",
        triggers=(
            "飯",
            "食事",
            "カフェ",
            "喫茶",
            "居酒屋",
            "レストラン",
            "ラーメン",
            "ピザ",
            "イタリアン",
            "自炊",
        ),
        expansions=(
            "カフェ",
            "喫茶",
            "居酒屋",
            "レストラン",
            "ラーメン",
            "自炊",
            "グルメ",
            "店",
            "予約",
        ),
        doc_type_weights={"place_card": 2.2, "bookmark_doc": 1.2, "media_doc": 0.4},
    ),
    IntentProfile(
        intent_id="finance",
        label="finance/company-event",
        triggers=("株価", "急騰", "急落", "決算", "銘柄", "投資", "金融", "半導体", "キオクシア"),
        expansions=(
            "株価",
            "急騰",
            "急落",
            "決算",
            "銘柄",
            "投資",
            "金融",
            "半導体",
            "市場",
            "業績",
            "分析",
        ),
        doc_type_weights={"ticker_event": 2.2, "author_profile": 0.5, "bookmark_doc": 0.7},
    ),
    IntentProfile(
        intent_id="technology",
        label="technology/research",
        triggers=(
            "技術",
            "情報系",
            "機械学習",
            "強化学習",
            "LLM",
            "AI",
            "ロボット",
            "ネットワーク",
            "論文",
            "資料",
            "勉強",
            "整理",
            "学習",
        ),
        expansions=(
            "技術",
            "機械学習",
            "強化学習",
            "ロボット",
            "ネットワーク",
            "LLM",
            "AI",
            "論文",
            "資料",
            "実装",
            "勉強",
            "整理",
        ),
        doc_type_weights={
            "topic_thread": 2.0,
            "bookmark_doc": 0.9,
            "tweet_doc": 0.5,
            "media_doc": 0.5,
        },
    ),
    IntentProfile(
        intent_id="author",
        label="author/stance",
        triggers=("作者", "この人", "発言", "見解", "展望", "意見", "スタンス"),
        expansions=("作者", "author", "発言", "見解", "展望", "意見", "スタンス"),
        doc_type_weights={"author_profile": 2.0, "bookmark_doc": 0.5, "tweet_doc": 0.5},
    ),
    IntentProfile(
        intent_id="science",
        label="science",
        triggers=("物理", "宇宙", "数学", "科学", "ロケット"),
        expansions=("物理", "宇宙", "数学", "科学", "ロケット", "研究", "論文"),
        doc_type_weights={
            "topic_thread": 1.6,
            "tweet_doc": 0.5,
            "bookmark_doc": 0.7,
            "media_doc": 0.3,
        },
    ),
    IntentProfile(
        intent_id="adult_comic",
        label="adult/comic",
        triggers=("成人", "エロ", "R18", "漫画", "同人", "DLsite", "FANZA", "イラスト"),
        expansions=(
            "成人",
            "エロ",
            "R18",
            "漫画",
            "同人",
            "DLsite",
            "FANZA",
            "イラスト",
            "公式",
            "リンク",
            "作品",
        ),
        doc_type_weights={"bookmark_doc": 1.1, "media_doc": 0.9},
    ),
    IntentProfile(
        intent_id="event",
        label="event/date",
        triggers=("イベント", "開催", "日付", "期限", "締切", "展示", "ライブ", "コミケ", "予約"),
        expansions=("イベント", "開催", "日付", "期限", "締切", "展示", "ライブ", "予約"),
        doc_type_weights={"ticker_event": 0.5, "bookmark_doc": 1.0, "tweet_doc": 0.2},
    ),
    IntentProfile(
        intent_id="quote_context",
        label="quote/context",
        triggers=("引用", "引用元", "文脈", "元ツイ", "リツイート", "RT"),
        expansions=("引用", "引用元", "文脈", "quoted", "quote", "root_text", "quoted_context"),
        doc_type_weights={"quote_tree_doc": 2.5, "bookmark_doc": 0.4},
    ),
    IntentProfile(
        intent_id="media",
        label="media",
        triggers=("画像", "写真", "動画", "イラスト", "スクショ", "図表"),
        expansions=("画像", "写真", "動画", "イラスト", "図表", "media", "photo", "video"),
        doc_type_weights={"media_doc": 2.0, "bookmark_doc": 0.4},
    ),
    IntentProfile(
        intent_id="cross_account",
        label="cross-account/duplicate",
        triggers=("重複", "複数アカウント", "全アカウント", "同じデータ", "横断"),
        expansions=("重複", "複数", "アカウント", "全アカウント", "横断"),
        doc_type_weights={"tweet_doc": 0.8, "bookmark_doc": 0.8},
    ),
    IntentProfile(
        intent_id="freshness",
        label="freshness",
        triggers=(
            "最近",
            "新しい",
            "古い",
            "最新",
            "古くなった",
            "昔",
            "今も",
            "正しい",
            "除いて",
            "矛盾",
            "反対意見",
            "反対",
            "同じ話",
            "contradict",
            "contradiction",
            "support",
        ),
        expansions=("最近", "新しい", "最新", "古い", "昔", "更新", "obsolete", "freshness"),
        doc_type_weights={"bookmark_doc": 0.4, "tweet_doc": 0.4},
    ),
)


_LATIN_TOKEN_RE = re.compile(r"[@#]?[A-Za-z0-9_][A-Za-z0-9_.:/-]{1,}")
_DATE_RE = re.compile(
    r"(?:\d{4}[-/年]\d{1,2}(?:[-/月]\d{1,2}日?)?|\d{1,2}/\d{1,2})"
)
_CJK_TOKEN_RE = re.compile(r"[一-龥ぁ-んァ-ンー]{2,}")
_CJK_STOP_TOKENS = {
    "これ",
    "それ",
    "あれ",
    "この人",
    "について",
    "教えて",
    "お願い",
    "ください",
    "できる",
    "ほしい",
    "保存した",
    "出して",
    "見たい",
    "知りたい",
    "わかる",
    "どこ",
}


def build_query_plan(query: str) -> QueryPlan:
    normalized = _normalize(query)
    terms: list[str] = []
    exact_terms: list[str] = []
    intents: list[str] = []
    doc_type_weights: dict[str, float] = {}

    for token in _LATIN_TOKEN_RE.findall(normalized):
        _append(terms, token)
        _append(exact_terms, token)
    for token in _DATE_RE.findall(normalized):
        if token:
            _append(terms, token)
            _append(exact_terms, token)
    for token in _cjk_tokens(normalized):
        _append(terms, token)
        _append(exact_terms, token)

    for profile in INTENT_PROFILES:
        matched_triggers = tuple(
            trigger for trigger in profile.triggers if _contains(normalized, trigger)
        )
        if (
            profile.intent_id == "author"
            and _looks_like_contradiction_check(normalized)
        ):
            matched_triggers = tuple(
                trigger
                for trigger in matched_triggers
                if trigger not in {"意見", "発言"}
            )
        if matched_triggers:
            intents.append(profile.intent_id)
            for trigger in matched_triggers:
                _append(terms, trigger)
                _append(exact_terms, trigger)
            for expansion in profile.expansions:
                _append(terms, expansion)
            for doc_type, weight in profile.doc_type_weights.items():
                doc_type_weights[doc_type] = doc_type_weights.get(doc_type, 0.0) + weight

    for phrase in _quoted_phrases(query):
        _append(terms, phrase)
        _append(exact_terms, phrase)

    if not terms:
        stripped = normalized.strip()
        if stripped:
            _append(terms, stripped)
            _append(exact_terms, stripped)

    prefers_recent = any(
        _contains(normalized, term)
        for term in (
            "最近",
            "新しい",
            "最新",
            "今も",
            "現在",
            "現時点",
            "矛盾",
            "反対意見",
            "反対",
            "同じ話",
            "contradict",
            "contradiction",
            "support",
        )
    )
    excludes_old = any(
        _contains(normalized, term)
        for term in ("古いものを除", "古いのを除", "古い情報を除", "古いデータを除", "除外")
    )
    requires_bookmark = any(_contains(normalized, term) for term in ("保存", "ブクマ", "bookmark"))
    requires_quote = "quote_context" in intents
    requires_media = "media" in intents
    wants_cross_account = "cross_account" in intents
    wants_event_dates = "event" in intents
    author_terms = tuple(token[1:] for token in terms if token.startswith("@") and len(token) > 1)
    if author_terms:
        doc_type_weights["author_profile"] = doc_type_weights.get("author_profile", 0.0) + 2.0
    if "author" in intents:
        doc_type_weights["author_profile"] = doc_type_weights.get("author_profile", 0.0) + 1.5
        if "topic_thread" in doc_type_weights:
            doc_type_weights["topic_thread"] = min(doc_type_weights["topic_thread"], 0.4)

    if requires_bookmark:
        doc_type_weights["bookmark_doc"] = doc_type_weights.get("bookmark_doc", 0.0) + 1.0
    if prefers_recent or excludes_old:
        doc_type_weights["bookmark_doc"] = doc_type_weights.get("bookmark_doc", 0.0) + 0.3
    if excludes_old:
        _remove_terms(terms, "古い", "古くなった", "obsolete", "除いて", "除外")
        _remove_terms(exact_terms, "古い", "古くなった", "obsolete", "除いて", "除外")
    if _looks_like_broad_topic_map(normalized):
        _remove_terms(terms, "DB")
        _remove_terms(exact_terms, "DB")
        for term in ("関心", "領域", "保存"):
            _append(terms, term)
        doc_type_weights["topic_thread"] = doc_type_weights.get("topic_thread", 0.0) + 3.0

    return QueryPlan(
        original_query=query,
        normalized_query=normalized,
        search_terms=tuple(terms),
        exact_terms=tuple(exact_terms),
        intents=tuple(intents),
        doc_type_weights=dict(sorted(doc_type_weights.items())),
        prefers_recent=prefers_recent,
        excludes_old=excludes_old,
        requires_bookmark_context=requires_bookmark,
        requires_quote_context=requires_quote,
        requires_media_context=requires_media,
        wants_cross_account=wants_cross_account,
        wants_event_dates=wants_event_dates,
        author_terms=author_terms,
    )


def query_plan_json(plan: QueryPlan) -> str:
    return json.dumps(plan.as_dict(), ensure_ascii=False, indent=2, sort_keys=True)


def _normalize(value: str) -> str:
    return unicodedata.normalize("NFKC", value or "").strip()


def _contains(text: str, term: str) -> bool:
    return _normalize(term).casefold() in text.casefold()


def _looks_like_contradiction_check(text: str) -> bool:
    return any(
        _contains(text, term)
        for term in (
            "矛盾",
            "反対意見",
            "反対",
            "同じ話",
            "contradict",
            "contradiction",
            "support",
        )
    )


def _looks_like_broad_topic_map(text: str) -> bool:
    return any(
        _contains(text, term)
        for term in ("関心領域", "db 全体", "db全体", "DB 全体", "DB全体")
    )


def _append(values: list[str], value: str) -> None:
    cleaned = _normalize(value).strip().strip("。、,.!?！？「」『』（）()[]【】")
    if not cleaned:
        return
    if cleaned.casefold() in {existing.casefold() for existing in values}:
        return
    values.append(cleaned)


def _remove_terms(values: list[str], *terms: str) -> None:
    banned = {_normalize(term).casefold() for term in terms}
    values[:] = [value for value in values if value.casefold() not in banned]


def _quoted_phrases(query: str) -> tuple[str, ...]:
    phrases: list[str] = []
    for pattern in (r'"([^"]+)"', r"「([^」]+)」", r"『([^』]+)』"):
        for match in re.findall(pattern, query):
            _append(phrases, match)
    return tuple(phrases)


def _cjk_tokens(query: str) -> tuple[str, ...]:
    tokens: list[str] = []
    for raw in _CJK_TOKEN_RE.findall(query):
        token = raw.strip(" 　。、,.!?！？「」『』（）()[]【】")
        if len(token) < 2:
            continue
        if token.endswith("について") and len(token) > 6:
            token = token.removesuffix("について")
        if token.casefold() not in {value.casefold() for value in _CJK_STOP_TOKENS}:
            _append(tokens, token)
        for subtoken in _split_cjk_token(token):
            if subtoken.casefold() in {value.casefold() for value in _CJK_STOP_TOKENS}:
                continue
            _append(tokens, subtoken)
    return tuple(tokens)


def _split_cjk_token(token: str) -> tuple[str, ...]:
    separators = r"(?:について|にある|にいる|では|には|から|まで|なら|で|の|を|が|は|と)"
    parts = re.split(separators, token)
    return tuple(part for part in parts if len(part) >= 2)
