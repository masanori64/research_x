import json

from research_x import bookmark_classifier
from research_x.bookmark_classifier import (
    BookmarkClassification,
    BookmarkClassificationRun,
    BookmarkClassifierSettings,
    classify_bookmarks,
    default_bookmark_categories,
    load_bookmark_categories,
    write_bookmark_outputs,
)
from research_x.contracts import XItem, utc_now


def test_bookmark_classifier_reports_missing_api_key(monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    run = classify_bookmarks([_item("1", "LLM agent tips")])

    assert run.status == "not_configured"
    assert run.error_type == "MissingClassifierAPIKey"


def test_bookmark_classifier_parses_structured_openai_response() -> None:
    item = _item("1", "LLM agent tips")
    settings = BookmarkClassifierSettings(batch_size=1)
    categories = default_bookmark_categories()
    request = bookmark_classifier._classifier_request(  # noqa: SLF001
        (item,),
        settings=settings,
        categories=categories,
        api_key="test-key",
    )
    classifications = bookmark_classifier._classifications_from_response(  # noqa: SLF001
        {
            "output": [
                {
                    "content": [
                        {
                            "type": "output_text",
                            "text": json.dumps(
                                {
                                    "items": [
                                        {
                                            "source_id": "1",
                                            "category_id": "ai_ml",
                                            "confidence": 0.92,
                                            "tags": ["LLM", "agents"],
                                            "summary": "AIエージェントの話題",
                                            "rationale": "LLM関連の内容だから",
                                        }
                                    ]
                                },
                                ensure_ascii=False,
                            ),
                        }
                    ]
                }
            ]
        },
        (item,),
        categories,
        settings.max_tags,
    )

    assert request["url"] == "https://api.openai.com/v1/responses"
    assert request["request_shape_only"] is True
    assert request["provider_quality_proof"] is False
    assert classifications[0].category_id == "ai_ml"
    assert classifications[0].tags == ("LLM", "agents")


def test_bookmark_classifier_supports_openai_compatible_chat() -> None:
    settings = bookmark_classifier._resolve_classifier_settings(  # noqa: SLF001
        BookmarkClassifierSettings(provider="qwen", batch_size=1)
    )
    request = bookmark_classifier._classifier_request(  # noqa: SLF001
        (_item("1", "LLM agent tips"),),
        settings=settings,
        categories=default_bookmark_categories(),
        api_key="test-key",
    )

    assert request["url"].endswith("/chat/completions")
    assert request["payload"]["model"] == "qwen-turbo-latest"
    assert "reasoning_effort" not in request["payload"]
    assert settings.api_key_env == "QWEN_API_KEY"
    assert request["budget_provider"] == "qwen"
    assert request["request_shape_only"] is True


def test_bookmark_classifier_uses_gemini_openai_compatible_preset() -> None:
    settings = bookmark_classifier._resolve_classifier_settings(  # noqa: SLF001
        BookmarkClassifierSettings(provider="gemini", batch_size=1)
    )
    request = bookmark_classifier._classifier_request(  # noqa: SLF001
        (_item("1", "LLM agent tips"),),
        settings=settings,
        categories=default_bookmark_categories(),
        api_key="test-key",
    )

    assert request["url"].endswith("/openai/chat/completions")
    assert request["payload"]["model"] == "gemini-2.5-flash"
    assert request["payload"]["reasoning_effort"] == "low"
    assert settings.provider == "openai_compatible"
    assert settings.api_key_env == "GEMINI_API_KEY"
    assert request["budget_provider"] == "gemini"
    assert request["provider_quality_proof"] is False


def test_write_bookmark_outputs_groups_by_genre(tmp_path) -> None:
    items = [_item("1", "LLM agent tips"), _item("2", "startup growth")]
    categories = default_bookmark_categories()
    run = BookmarkClassificationRun(
        status="ok",
        model="gpt-4o-mini",
        generated_at=utc_now(),
        classifications=(
            BookmarkClassification(
                source_id="1",
                category_id="ai_ml",
                category_label="AI / Machine Learning",
                confidence=0.9,
                tags=("LLM",),
                summary="AI",
                rationale="AI topic",
            ),
            BookmarkClassification(
                source_id="2",
                category_id="business",
                category_label="Business / Marketing",
                confidence=0.8,
                tags=("growth",),
                summary="事業",
                rationale="business topic",
            ),
        ),
    )

    write_bookmark_outputs(tmp_path, items=items, classification_run=run, categories=categories)

    assert (tmp_path / "bookmarks_items.jsonl").exists()
    assert (tmp_path / "bookmark_classifications.jsonl").exists()
    assert (tmp_path / "genres" / "ai_ml.jsonl").exists()
    report = json.loads((tmp_path / "bookmarks_report.json").read_text(encoding="utf-8"))
    assert report["counts"] == {"ai_ml": 1, "business": 1}


def test_load_bookmark_categories_adds_other(tmp_path) -> None:
    path = tmp_path / "categories.toml"
    path.write_text(
        """
[[categories]]
id = "dev"
label = "Development"
description = "Programming topics"
cues = ["python", "infra"]
examples = ["A post about a library release."]
""".strip(),
        encoding="utf-8",
    )

    categories = load_bookmark_categories(path)

    assert [category.category_id for category in categories] == ["dev", "other"]
    assert categories[0].cues == ("python", "infra")
    assert categories[0].examples == ("A post about a library release.",)


def _item(source_id: str, text: str) -> XItem:
    return XItem(
        source_id=source_id,
        url=f"https://x.com/a/status/{source_id}",
        author="a",
        text=text,
        created_at=None,
        observed_at=utc_now(),
        raw={},
    )
