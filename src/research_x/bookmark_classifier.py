from __future__ import annotations

import json
import os
import re
import tomllib
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import asdict, dataclass, is_dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from research_x.contracts import XItem, utc_now
from research_x.memory.api_budget import (
    BUDGET_EXHAUSTED_STATUS,
    ApiBudgetExceededError,
    api_units,
    budgeted_api_call,
    require_provider_transport_send_allowed,
    rough_text_tokens,
)

OPENAI_RESPONSES_URL = "https://api.openai.com/v1/responses"
OTHER_CATEGORY_ID = "other"
OPENAI_COMPATIBLE_PRESETS = {
    "openai_chat": {
        "api_base_url": "https://api.openai.com/v1",
        "api_key_env": "OPENAI_API_KEY",
        "model": "gpt-4o-mini",
    },
    "qwen": {
        "api_base_url": "https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
        "api_key_env": "QWEN_API_KEY",
        "model": "qwen-turbo-latest",
    },
    "kimi": {
        "api_base_url": "https://api.moonshot.ai/v1",
        "api_key_env": "MOONSHOT_API_KEY",
        "model": "kimi-latest",
    },
    "glm": {
        "api_base_url": "https://open.bigmodel.cn/api/paas/v4",
        "api_key_env": "ZHIPU_API_KEY",
        "model": "glm-4-flash",
    },
    "gemini": {
        "api_base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
        "api_key_env": "GEMINI_API_KEY",
        "model": "gemini-2.5-flash",
    },
}


@dataclass(frozen=True)
class BookmarkCategory:
    category_id: str
    label: str
    description: str = ""
    cues: tuple[str, ...] = ()
    examples: tuple[str, ...] = ()


@dataclass(frozen=True)
class BookmarkClassification:
    source_id: str
    category_id: str
    category_label: str
    confidence: float
    tags: tuple[str, ...]
    summary: str
    rationale: str


@dataclass(frozen=True)
class BookmarkClassificationRun:
    status: str
    model: str
    generated_at: datetime
    classifications: tuple[BookmarkClassification, ...]
    error_type: str | None = None
    error_message: str | None = None
    metadata: dict[str, Any] | None = None


@dataclass(frozen=True)
class BookmarkClassifierSettings:
    model: str = "gpt-4o-mini"
    api_key_env: str = "OPENAI_API_KEY"
    batch_size: int = 20
    max_tags: int = 5
    request_timeout_seconds: float = 120.0
    provider: str = "openai_responses"
    api_base_url: str | None = None
    reasoning_effort: str | None = None


def default_bookmark_categories() -> tuple[BookmarkCategory, ...]:
    return (
        BookmarkCategory("ai_ml", "AI / Machine Learning", "AI, LLM, ML, agents, automation"),
        BookmarkCategory("software_dev", "Software Development", "Programming, infra, tools"),
        BookmarkCategory("business", "Business / Marketing", "Growth, sales, startups, offers"),
        BookmarkCategory("finance_crypto", "Finance / Crypto", "Markets, investing, crypto"),
        BookmarkCategory("productivity", "Productivity", "Workflows, note-taking, habits"),
        BookmarkCategory("writing_content", "Writing / Content", "Copywriting, threads, media"),
        BookmarkCategory("design_creative", "Design / Creative", "UI, visuals, creative work"),
        BookmarkCategory("security_privacy", "Security / Privacy", "Security, privacy, safety"),
        BookmarkCategory("research_learning", "Research / Learning", "Papers, study, explainers"),
        BookmarkCategory("politics_society", "Politics / Society", "News, policy, social topics"),
        BookmarkCategory("entertainment", "Entertainment", "Culture, humor, sports, fandom"),
        BookmarkCategory(OTHER_CATEGORY_ID, "Other", "Anything that does not fit above"),
    )


def load_bookmark_categories(path: str | Path | None) -> tuple[BookmarkCategory, ...]:
    if path is None:
        return default_bookmark_categories()
    category_path = Path(path)
    with category_path.open("rb") as handle:
        raw = tomllib.load(handle)
    categories = tuple(_category_from_raw(item) for item in raw.get("categories", []))
    if not categories:
        raise ValueError(f"{category_path} must include at least one [[categories]] entry")
    if OTHER_CATEGORY_ID not in {category.category_id for category in categories}:
        categories += (BookmarkCategory(OTHER_CATEGORY_ID, "Other"),)
    return categories


def classify_bookmarks(
    items: Iterable[XItem],
    *,
    settings: BookmarkClassifierSettings | None = None,
    categories: tuple[BookmarkCategory, ...] | None = None,
) -> BookmarkClassificationRun:
    settings = settings or BookmarkClassifierSettings()
    settings = _resolve_classifier_settings(settings)
    categories = categories or default_bookmark_categories()
    item_tuple = tuple(items)
    metadata = {
        "api_key_env": settings.api_key_env,
        "provider": settings.provider,
        "api_base_url": settings.api_base_url,
        "batch_size": settings.batch_size,
        "category_count": len(categories),
        "reasoning_effort": settings.reasoning_effort,
    }
    if not item_tuple:
        return BookmarkClassificationRun(
            status="empty",
            model=settings.model,
            generated_at=utc_now(),
            classifications=(),
            metadata=metadata,
        )

    api_key = os.environ.get(settings.api_key_env)
    if not api_key:
        return BookmarkClassificationRun(
            status="not_configured",
            model=settings.model,
            generated_at=utc_now(),
            classifications=(),
            error_type="MissingClassifierAPIKey",
            error_message=f"Set {settings.api_key_env} to enable AI bookmark classification.",
            metadata=metadata,
        )

    classifications: list[BookmarkClassification] = []
    try:
        for batch in _chunks(item_tuple, max(1, settings.batch_size)):
            request = _classifier_request(
                batch,
                settings=settings,
                categories=categories,
                api_key=api_key,
            )
            response = _post_json_budgeted(
                request["url"],
                request["payload"],
                api_key=request["api_key"],
                timeout_seconds=request["timeout_seconds"],
                budget_provider=request["budget_provider"],
                budget_model=request["budget_model"],
                budget_units=request["budget_units"],
            )
            classifications.extend(
                _classifications_from_response(response, batch, categories, settings.max_tags)
            )
    except ApiBudgetExceededError as exc:
        return BookmarkClassificationRun(
            status=BUDGET_EXHAUSTED_STATUS,
            model=settings.model,
            generated_at=utc_now(),
            classifications=tuple(classifications),
            error_type=type(exc).__name__,
            error_message=str(exc),
            metadata=metadata,
        )
    except Exception as exc:  # noqa: BLE001 - classification must not discard fetched bookmarks.
        status = "partial" if classifications else "error"
        return BookmarkClassificationRun(
            status=status,
            model=settings.model,
            generated_at=utc_now(),
            classifications=tuple(classifications),
            error_type=type(exc).__name__,
            error_message=str(exc),
            metadata=metadata,
        )

    classifications = _with_missing_classifications(item_tuple, classifications, categories)
    return BookmarkClassificationRun(
        status="ok",
        model=settings.model,
        generated_at=utc_now(),
        classifications=tuple(classifications),
        metadata=metadata,
    )


def write_bookmark_outputs(
    out_dir: str | Path,
    *,
    items: Iterable[XItem],
    classification_run: BookmarkClassificationRun,
    categories: tuple[BookmarkCategory, ...],
    store_summary: Any | None = None,
) -> None:
    write_label_outputs(
        out_dir,
        items=items,
        classification_run=classification_run,
        categories=categories,
        item_filename="bookmarks_items.jsonl",
        classification_filename="bookmark_classifications.jsonl",
        report_filename="bookmarks_report.json",
        store_summary=store_summary,
        report_outputs={
            "bookmarks": "bookmarks.jsonl",
            "tweets": "tweets.jsonl",
            "tweet_edges": "tweet_edges.jsonl",
            "media": "media.jsonl",
            "bookmark_trees": "bookmark_trees.jsonl",
            "account_bookmarks": "account_bookmarks.jsonl",
            "database": "x_data.sqlite3",
        },
    )


def write_label_outputs(
    out_dir: str | Path,
    *,
    items: Iterable[XItem],
    classification_run: BookmarkClassificationRun,
    categories: tuple[BookmarkCategory, ...],
    item_filename: str,
    classification_filename: str,
    report_filename: str,
    genres_dir_name: str = "genres",
    store_summary: Any | None = None,
    report_outputs: dict[str, str] | None = None,
) -> None:
    output_path = Path(out_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    genres_path = output_path / genres_dir_name
    genres_path.mkdir(parents=True, exist_ok=True)

    item_tuple = tuple(items)
    classification_by_id = {
        classification.source_id: classification
        for classification in classification_run.classifications
    }

    _write_jsonl(output_path / item_filename, (_jsonable(item) for item in item_tuple))
    _write_jsonl(
        output_path / classification_filename,
        (_jsonable(item) for item in classification_run.classifications),
    )

    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in item_tuple:
        classification = classification_by_id.get(item.source_id)
        category_id = classification.category_id if classification else "unclassified"
        grouped[category_id].append(
            {
                "item": item,
                "classification": classification,
            }
        )

    for category_id, rows in grouped.items():
        _write_jsonl(genres_path / f"{_safe_filename(category_id)}.jsonl", map(_jsonable, rows))

    report = {
        "generated_at": utc_now(),
        "items": len(item_tuple),
        "classification": classification_run,
        "store": store_summary,
        "categories": categories,
        "counts": {category_id: len(rows) for category_id, rows in grouped.items()},
        "outputs": {
            "items": str(output_path / item_filename),
            "classifications": str(output_path / classification_filename),
            "genres": str(genres_path),
            **{
                key: str(output_path / value)
                for key, value in (report_outputs or {}).items()
            },
        },
    }
    (output_path / report_filename).write_text(
        json.dumps(_jsonable(report), ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def _category_from_raw(raw: dict[str, Any]) -> BookmarkCategory:
    category_id = _normalize_category_id(str(raw["id"]))
    cues = _string_tuple(raw.get("cues") or raw.get("aliases") or raw.get("tags"))
    examples = _string_tuple(raw.get("examples"))
    return BookmarkCategory(
        category_id=category_id,
        label=str(raw.get("label", category_id)),
        description=str(raw.get("description", "")),
        cues=cues,
        examples=examples,
    )


def _resolve_classifier_settings(
    settings: BookmarkClassifierSettings,
) -> BookmarkClassifierSettings:
    preset = OPENAI_COMPATIBLE_PRESETS.get(settings.provider)
    if preset is None:
        return settings
    return BookmarkClassifierSettings(
        model=settings.model if settings.model != "gpt-4o-mini" else str(preset["model"]),
        api_key_env=(
            settings.api_key_env
            if settings.api_key_env != "OPENAI_API_KEY"
            else str(preset["api_key_env"])
        ),
        batch_size=settings.batch_size,
        max_tags=settings.max_tags,
        request_timeout_seconds=settings.request_timeout_seconds,
        provider="openai_compatible",
        api_base_url=settings.api_base_url or str(preset["api_base_url"]),
        reasoning_effort=settings.reasoning_effort,
    )


def _classifier_payload(
    items: tuple[XItem, ...],
    settings: BookmarkClassifierSettings,
    categories: tuple[BookmarkCategory, ...],
) -> dict[str, Any]:
    if settings.provider == "openai_responses":
        return _openai_responses_payload(items, settings, categories)
    return _openai_compatible_chat_payload(items, settings, categories)


def _classifier_request(
    items: tuple[XItem, ...],
    *,
    settings: BookmarkClassifierSettings,
    categories: tuple[BookmarkCategory, ...],
    api_key: str,
) -> dict[str, Any]:
    payload = _classifier_payload(items, settings, categories)
    return {
        "url": _classifier_url(settings),
        "payload": payload,
        "api_key": api_key,
        "timeout_seconds": settings.request_timeout_seconds,
        "budget_provider": _budget_provider_for_settings(settings),
        "budget_model": settings.model,
        "budget_units": api_units(
            calls=1,
            input_tokens=rough_text_tokens(payload),
            documents=len(items),
        ),
        "request_shape_only": True,
        "provider_quality_proof": False,
    }


def _openai_responses_payload(
    items: tuple[XItem, ...],
    settings: BookmarkClassifierSettings,
    categories: tuple[BookmarkCategory, ...],
) -> dict[str, Any]:
    category_payload = [
        {
            "id": category.category_id,
            "label": category.label,
            "description": category.description,
            "cues": list(category.cues),
            "examples": list(category.examples),
        }
        for category in categories
    ]
    item_payload = [_classification_item_payload(item, items) for item in items]
    return {
        "model": settings.model,
        "input": [
            {
                "role": "system",
                "content": (
                    "You classify a user's own X bookmarks into exactly one genre. "
                    "Use only the provided category_id values. "
                    "Custom category cues and examples are strong hints. "
                    "Use author profile, quoted tweet, and same-author context when present. "
                    "Return concise Japanese summaries and rationales. "
                    "Prefer concrete topic labels over vague labels."
                ),
            },
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "categories": category_payload,
                        "items": item_payload,
                        "max_tags": settings.max_tags,
                    },
                    ensure_ascii=False,
                ),
            },
        ],
        "text": {
            "format": {
                "type": "json_schema",
                "name": "bookmark_classification_batch",
                "strict": True,
                "schema": _classification_schema(categories),
            }
        },
    }


def _openai_compatible_chat_payload(
    items: tuple[XItem, ...],
    settings: BookmarkClassifierSettings,
    categories: tuple[BookmarkCategory, ...],
) -> dict[str, Any]:
    content = json.dumps(
        {
            "categories": [
                {
                    "id": category.category_id,
                    "label": category.label,
                    "description": category.description,
                    "cues": list(category.cues),
                    "examples": list(category.examples),
                }
                for category in categories
            ],
            "items": [_classification_item_payload(item, items) for item in items],
            "max_tags": settings.max_tags,
            "output_schema": _classification_schema(categories),
        },
        ensure_ascii=False,
    )
    payload = {
        "model": settings.model,
        "temperature": 0,
        "messages": [
            {
                "role": "system",
                "content": (
                    "Classify each X bookmark into exactly one category_id. "
                    "Return only valid JSON with a top-level items array. "
                    "Use custom category cues and any provided author/context fields. "
                    "Use Japanese for summary and rationale."
                ),
            },
            {"role": "user", "content": content},
        ],
        "response_format": {"type": "json_object"},
    }
    reasoning_effort = _openai_compatible_reasoning_effort(settings)
    if reasoning_effort:
        payload["reasoning_effort"] = reasoning_effort
    return payload


def _openai_compatible_reasoning_effort(settings: BookmarkClassifierSettings) -> str | None:
    if not settings.model.startswith("gemini-"):
        return None
    if settings.reasoning_effort is None:
        return "low"
    value = settings.reasoning_effort.strip().lower()
    if value in {"", "default", "none"}:
        return None
    if value not in {"minimal", "low", "medium", "high"}:
        raise ValueError("reasoning_effort must be one of default, minimal, low, medium, high")
    return value


def _classifier_url(settings: BookmarkClassifierSettings) -> str:
    if settings.provider == "openai_responses":
        return OPENAI_RESPONSES_URL
    base_url = (settings.api_base_url or "").rstrip("/")
    if not base_url:
        raise ValueError("api_base_url is required for openai_compatible classifiers")
    return f"{base_url}/chat/completions"


def _budget_provider_for_settings(settings: BookmarkClassifierSettings) -> str:
    api_key_env = settings.api_key_env.upper()
    base_hostname = _api_base_hostname(settings.api_base_url)
    if "GEMINI" in api_key_env or base_hostname == "generativelanguage.googleapis.com":
        return "gemini"
    if "OPENAI" in api_key_env or base_hostname == "api.openai.com":
        return "openai"
    if "QWEN" in api_key_env or base_hostname.endswith(".aliyuncs.com"):
        return "qwen"
    if "MOONSHOT" in api_key_env or base_hostname.endswith(".moonshot.ai"):
        return "kimi"
    if "ZHIPU" in api_key_env or base_hostname == "open.bigmodel.cn":
        return "glm"
    return settings.provider


def _api_base_hostname(api_base_url: str | None) -> str:
    if not api_base_url:
        return ""
    parsed = urlparse(api_base_url)
    if parsed.scheme not in {"http", "https"}:
        return ""
    return (parsed.hostname or "").lower().rstrip(".")


def _classification_item_payload(item: XItem, batch: tuple[XItem, ...]) -> dict[str, Any]:
    return {
        "source_id": item.source_id,
        "author": item.author,
        "url": item.url,
        "text": _truncate(item.text or "", 2400),
        "author_profile": _author_profile(item.raw),
        "quoted_tweets": _quoted_contexts(item.raw),
        "same_author_context": _same_author_context(item, batch),
    }


def _author_profile(raw: dict[str, Any]) -> dict[str, Any]:
    candidates = []
    user = raw.get("user")
    if isinstance(user, dict):
        candidates.append(user)
    core_user = raw.get("core", {}).get("user_results", {}).get("result", {})
    if isinstance(core_user, dict):
        candidates.append(core_user)
        legacy = core_user.get("legacy")
        if isinstance(legacy, dict):
            candidates.append(legacy)
    for provider_raw in _provider_raw_values(raw):
        candidates.append(_author_profile(provider_raw))

    merged: dict[str, Any] = {}
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        for source, dest in (
            ("name", "name"),
            ("displayname", "name"),
            ("screen_name", "screen_name"),
            ("username", "screen_name"),
            ("description", "description"),
            ("bio", "description"),
            ("verified", "verified"),
            ("followers_count", "followers_count"),
            ("friends_count", "following_count"),
        ):
            value = candidate.get(source)
            if value not in (None, "", []) and dest not in merged:
                merged[dest] = value
    if "description" in merged:
        merged["description"] = _truncate(str(merged["description"]), 600)
    return merged


def _quoted_contexts(raw: dict[str, Any]) -> list[dict[str, Any]]:
    contexts: list[dict[str, Any]] = []
    for quote in _quoted_tweets_from_raw(raw):
        contexts.append(
            {
                "tweet_id": _tweet_id(quote),
                "author": _author(quote),
                "text": _truncate(_text(quote) or "", 1200),
                "author_profile": _author_profile(quote),
            }
        )
    return contexts[:3]


def _same_author_context(item: XItem, batch: tuple[XItem, ...]) -> list[dict[str, str]]:
    if not item.author:
        return []
    rows: list[dict[str, str]] = []
    for other in batch:
        if other.source_id == item.source_id or other.author != item.author or not other.text:
            continue
        rows.append({"source_id": other.source_id, "text": _truncate(other.text, 600)})
        if len(rows) >= 3:
            break
    return rows


def _classification_schema(categories: tuple[BookmarkCategory, ...]) -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["items"],
        "properties": {
            "items": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": [
                        "source_id",
                        "category_id",
                        "confidence",
                        "tags",
                        "summary",
                        "rationale",
                    ],
                    "properties": {
                        "source_id": {"type": "string"},
                        "category_id": {
                            "type": "string",
                            "enum": [category.category_id for category in categories],
                        },
                        "confidence": {"type": "number"},
                        "tags": {"type": "array", "items": {"type": "string"}},
                        "summary": {"type": "string"},
                        "rationale": {"type": "string"},
                    },
                },
            }
        },
    }

def _post_json(
    url: str,
    payload: dict[str, Any],
    *,
    api_key: str,
    timeout_seconds: float,
    budget_provider: str | None = None,
    budget_model: str | None = None,
    budget_units: dict[str, int | float] | None = None,
) -> dict[str, Any]:
    def send() -> dict[str, Any]:
        return _post_json_unbudgeted(
            url,
            payload,
            api_key=api_key,
            timeout_seconds=timeout_seconds,
        )

    if budget_provider is None and budget_model is None and budget_units is None:
        return send()
    with budgeted_api_call(
        provider=budget_provider or "unknown",
        model=budget_model or str(payload.get("model") or "unknown"),
        provider_role="classifier",
        operation="classification",
        units=budget_units or api_units(calls=1),
        request_payload=payload,
        metadata={"url": url},
    ):
        return send()


def _post_json_budgeted(
    url: str,
    payload: dict[str, Any],
    *,
    api_key: str,
    timeout_seconds: float,
    budget_provider: str,
    budget_model: str,
    budget_units: dict[str, int | float] | None = None,
) -> dict[str, Any]:
    with budgeted_api_call(
        provider=budget_provider,
        model=budget_model,
        provider_role="classifier",
        operation="classification",
        units=budget_units or api_units(calls=1),
        request_payload=payload,
        metadata={"url": url},
    ):
        return _post_json(
            url,
            payload,
            api_key=api_key,
            timeout_seconds=timeout_seconds,
        )


def _post_json_unbudgeted(
    url: str,
    payload: dict[str, Any],
    *,
    api_key: str,
    timeout_seconds: float,
) -> dict[str, Any]:
    require_provider_transport_send_allowed(url)
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = Request(
        url,
        data=data,
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urlopen(request, timeout=timeout_seconds) as response:  # noqa: S310
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Classifier API HTTP {exc.code}: {body[:600]}") from exc


def _classifications_from_response(
    response: dict[str, Any],
    batch: tuple[XItem, ...],
    categories: tuple[BookmarkCategory, ...],
    max_tags: int,
) -> list[BookmarkClassification]:
    text = _extract_output_text(response)
    payload = json.loads(text)
    rows = payload.get("items", [])
    if not isinstance(rows, list):
        raise ValueError("OpenAI response JSON must contain an items array")

    category_by_id = {category.category_id: category for category in categories}
    source_ids = {item.source_id for item in batch}
    classifications: list[BookmarkClassification] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        source_id = str(row.get("source_id", ""))
        if source_id not in source_ids:
            continue
        category_id = str(row.get("category_id", OTHER_CATEGORY_ID))
        if category_id not in category_by_id:
            category_id = OTHER_CATEGORY_ID
        category = category_by_id[category_id]
        raw_tags = row.get("tags", [])
        if not isinstance(raw_tags, list):
            raw_tags = []
        tags = tuple(str(tag)[:60] for tag in raw_tags[: max(0, max_tags)])
        classifications.append(
            BookmarkClassification(
                source_id=source_id,
                category_id=category.category_id,
                category_label=category.label,
                confidence=float(row.get("confidence", 0.0)),
                tags=tags,
                summary=str(row.get("summary", "")),
                rationale=str(row.get("rationale", "")),
            )
        )
    return classifications


def _extract_output_text(response: dict[str, Any]) -> str:
    choices = response.get("choices")
    if isinstance(choices, list) and choices:
        message = choices[0].get("message") if isinstance(choices[0], dict) else None
        if isinstance(message, dict) and isinstance(message.get("content"), str):
            return message["content"]
    output_text = response.get("output_text")
    if isinstance(output_text, str) and output_text:
        return output_text
    parts: list[str] = []
    for output_item in response.get("output", []):
        if not isinstance(output_item, dict):
            continue
        for content in output_item.get("content", []):
            if not isinstance(content, dict):
                continue
            text = content.get("text")
            if isinstance(text, str):
                parts.append(text)
    if parts:
        return "\n".join(parts)
    raise ValueError("OpenAI response did not include output text")


def _with_missing_classifications(
    items: tuple[XItem, ...],
    classifications: list[BookmarkClassification],
    categories: tuple[BookmarkCategory, ...],
) -> list[BookmarkClassification]:
    seen = {classification.source_id for classification in classifications}
    category_by_id = {category.category_id: category for category in categories}
    category = category_by_id.get(OTHER_CATEGORY_ID, categories[0])
    for item in items:
        if item.source_id in seen:
            continue
        classifications.append(
            BookmarkClassification(
                source_id=item.source_id,
                category_id=category.category_id,
                category_label=category.label,
                confidence=0.0,
                tags=(),
                summary="",
                rationale="model_did_not_return_this_item",
            )
        )
    return classifications


def _quoted_tweets_from_raw(raw: dict[str, Any]) -> list[dict[str, Any]]:
    quotes: list[dict[str, Any]] = []
    _append_quote(quotes, raw.get("quotedTweet"))
    _append_quote(quotes, raw.get("quoted_tweet"))
    _append_quote(quotes, raw.get("quoted_status"))
    quoted_status_result = raw.get("quoted_status_result")
    if isinstance(quoted_status_result, dict):
        _append_quote(quotes, quoted_status_result.get("result"))
    for provider_raw in _provider_raw_values(raw):
        quotes.extend(_quoted_tweets_from_raw(provider_raw))
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for quote in quotes:
        tweet_id = _tweet_id(quote)
        if tweet_id is None or tweet_id in seen:
            continue
        seen.add(tweet_id)
        result.append(quote)
    return result


def _append_quote(quotes: list[dict[str, Any]], value: Any) -> None:
    if not isinstance(value, dict):
        return
    if value.get("__typename") == "TweetWithVisibilityResults" and isinstance(
        value.get("tweet"), dict
    ):
        value = value["tweet"]
    if isinstance(value.get("result"), dict):
        value = value["result"]
    if isinstance(value, dict) and _tweet_id(value):
        quotes.append(value)


def _provider_raw_values(raw: dict[str, Any]):
    provider_raw = raw.get("_provider_raw")
    if isinstance(provider_raw, dict):
        for value in provider_raw.values():
            if isinstance(value, dict):
                yield value


def _tweet_id(raw: dict[str, Any]) -> str | None:
    for key in ("id", "id_str", "rest_id", "tweet_id"):
        value = raw.get(key)
        if value not in (None, ""):
            return str(value)
    legacy = raw.get("legacy")
    if isinstance(legacy, dict):
        for key in ("id_str", "id"):
            value = legacy.get(key)
            if value not in (None, ""):
                return str(value)
    return None


def _author(raw: dict[str, Any]) -> str | None:
    user = raw.get("user")
    if isinstance(user, dict):
        value = user.get("username") or user.get("screen_name")
        if value:
            return str(value)
    core_user = raw.get("core", {}).get("user_results", {}).get("result", {})
    if isinstance(core_user, dict):
        legacy = core_user.get("legacy", {})
        value = legacy.get("screen_name") if isinstance(legacy, dict) else None
        value = value or core_user.get("screen_name")
        if value:
            return str(value)
    return None


def _text(raw: dict[str, Any]) -> str | None:
    for key in ("rawContent", "text", "full_text", "content"):
        value = raw.get(key)
        if value not in (None, ""):
            return str(value)
    legacy = raw.get("legacy")
    if isinstance(legacy, dict):
        value = legacy.get("full_text") or legacy.get("text")
        if value:
            return str(value)
    return None


def _string_tuple(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,)
    if isinstance(value, list | tuple):
        return tuple(str(item) for item in value if item not in (None, ""))
    return (str(value),)


def _chunks(items: tuple[XItem, ...], size: int):
    for index in range(0, len(items), size):
        yield items[index : index + size]


def _truncate(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    return value[: limit - 1] + "..."

def _normalize_category_id(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9_]+", "_", value.strip().lower())
    normalized = re.sub(r"_+", "_", normalized).strip("_")
    if normalized:
        return normalized
    return OTHER_CATEGORY_ID


def _safe_filename(value: str) -> str:
    return _normalize_category_id(value) or "category"


def _write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def _jsonable(value: Any):
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if is_dataclass(value) and not isinstance(value, type):
        return _jsonable(asdict(value))
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if hasattr(value, "value"):
        return value.value
    return value
