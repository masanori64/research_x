import json

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


def test_bookmark_classifier_parses_structured_openai_response(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    def fake_post_json(*args, **kwargs):
        return {
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
        }

    monkeypatch.setattr("research_x.bookmark_classifier._post_json", fake_post_json)

    run = classify_bookmarks(
        [_item("1", "LLM agent tips")],
        settings=BookmarkClassifierSettings(batch_size=1),
    )

    assert run.status == "ok"
    assert run.classifications[0].category_id == "ai_ml"
    assert run.classifications[0].tags == ("LLM", "agents")


def test_bookmark_classifier_supports_openai_compatible_chat(monkeypatch) -> None:
    monkeypatch.setenv("QWEN_API_KEY", "test-key")
    captured = {}

    def fake_post_json(url, payload, **kwargs):
        captured["url"] = url
        captured["payload"] = payload
        return {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "items": [
                                    {
                                        "source_id": "1",
                                        "category_id": "ai_ml",
                                        "confidence": 0.8,
                                        "tags": ["LLM"],
                                        "summary": "AI",
                                        "rationale": "AI topic",
                                    }
                                ]
                            }
                        )
                    }
                }
            ]
        }

    monkeypatch.setattr("research_x.bookmark_classifier._post_json", fake_post_json)

    run = classify_bookmarks(
        [_item("1", "LLM agent tips")],
        settings=BookmarkClassifierSettings(provider="qwen", batch_size=1),
    )

    assert run.status == "ok"
    assert captured["url"].endswith("/chat/completions")
    assert captured["payload"]["model"] == "qwen-turbo-latest"
    assert "reasoning_effort" not in captured["payload"]
    assert run.metadata["api_key_env"] == "QWEN_API_KEY"


def test_bookmark_classifier_uses_gemini_openai_compatible_preset(monkeypatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    captured = {}

    def fake_post_json(url, payload, **kwargs):
        captured["url"] = url
        captured["payload"] = payload
        captured["kwargs"] = kwargs
        return {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "items": [
                                    {
                                        "source_id": "1",
                                        "category_id": "ai_ml",
                                        "confidence": 0.8,
                                        "tags": ["LLM"],
                                        "summary": "AI",
                                        "rationale": "AI topic",
                                    }
                                ]
                            }
                        )
                    }
                }
            ]
        }

    monkeypatch.setattr("research_x.bookmark_classifier._post_json", fake_post_json)

    run = classify_bookmarks(
        [_item("1", "LLM agent tips")],
        settings=BookmarkClassifierSettings(provider="gemini", batch_size=1),
    )

    assert run.status == "ok"
    assert captured["url"].endswith("/openai/chat/completions")
    assert captured["payload"]["model"] == "gemini-2.5-flash"
    assert captured["payload"]["reasoning_effort"] == "low"
    assert run.metadata["provider"] == "openai_compatible"
    assert run.metadata["api_key_env"] == "GEMINI_API_KEY"


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
