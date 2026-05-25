import json

from research_x.adapters.bookmark_adapters import (
    GalleryDLBookmarksAdapter,
    XWebGraphQLBookmarksAdapter,
    _gallery_dl_items,
    _next_bottom_cursor,
    _web_graphql_items,
    _write_netscape_cookies,
    _XWebGraphQLBookmarkSettings,
)
from research_x.contracts import AcquisitionTarget, AdapterConfig, OutcomeStatus, TargetKind


def test_x_web_graphql_bookmarks_missing_storage_is_not_configured(tmp_path) -> None:
    adapter = XWebGraphQLBookmarksAdapter(
        AdapterConfig("x_web_graphql_bookmarks", options={"storage_state": tmp_path / "none.json"})
    )

    outcome = adapter.fetch(AcquisitionTarget(TargetKind.BOOKMARKS, "me", limit=1))

    assert outcome.status == OutcomeStatus.NOT_CONFIGURED


def test_gallery_dl_bookmarks_missing_storage_is_not_configured(tmp_path) -> None:
    adapter = GalleryDLBookmarksAdapter(
        AdapterConfig("gallery_dl_bookmarks", options={"storage_state": tmp_path / "none.json"})
    )

    outcome = adapter.fetch(AcquisitionTarget(TargetKind.BOOKMARKS, "me", limit=1))

    assert outcome.status == OutcomeStatus.NOT_CONFIGURED


def test_web_graphql_bookmark_items_extract_tweets_and_cursor() -> None:
    payload = {
        "data": {
            "bookmark_timeline": {
                "timeline": {
                    "instructions": [
                        {
                            "entries": [
                                {
                                    "entryId": "tweet-1",
                                    "content": {
                                        "itemContent": {
                                            "tweet_results": {
                                                "result": {
                                                    "__typename": "Tweet",
                                                    "rest_id": "123",
                                                    "legacy": {
                                                        "full_text": "hello",
                                                        "created_at": (
                                                            "Wed Jan 06 18:40:40 +0000 2021"
                                                        ),
                                                    },
                                                    "core": {
                                                        "user_results": {
                                                            "result": {
                                                                "legacy": {
                                                                    "screen_name": "alice"
                                                                }
                                                            }
                                                        }
                                                    },
                                                }
                                            }
                                        }
                                    },
                                },
                                {
                                    "entryId": "user-1",
                                    "content": {
                                        "itemContent": {
                                            "user_results": {
                                                "result": {
                                                    "__typename": "User",
                                                    "rest_id": "999",
                                                    "legacy": {
                                                        "id_str": "999",
                                                        "description": "bio",
                                                    },
                                                }
                                            }
                                        }
                                    },
                                },
                                {
                                    "entryId": "cursor-bottom-1",
                                    "content": {
                                        "cursorType": "Bottom",
                                        "value": "cursor-next",
                                    },
                                },
                            ]
                        }
                    ]
                }
            }
        }
    }

    items = _web_graphql_items(payload)

    assert items[0].source_id == "123"
    assert items[0].author == "alice"
    assert items[0].raw["bookmark_root"] is True
    assert len(items) == 1
    assert _next_bottom_cursor(payload) == "cursor-next"


def test_gallery_dl_items_parse_dump_json() -> None:
    text = json.dumps(
        {
            "tweet_id": "123",
            "content": "hello",
            "date": "2021-01-06T18:40:40+00:00",
            "author": {"name": "alice"},
        }
    )

    items = _gallery_dl_items(text, limit=5)

    assert items[0].source_id == "123"
    assert items[0].author == "alice"
    assert items[0].raw["source_api"] == "gallery_dl"


def test_gallery_dl_items_marks_quoted_leaf_as_non_root_bookmark() -> None:
    text = "\n".join(
        [
            json.dumps(
                {
                    "tweet_id": "root",
                    "content": "quoted post",
                    "quoted_status_result": {"result": {"rest_id": "leaf"}},
                }
            ),
            json.dumps(
                {
                    "tweet_id": "leaf",
                    "content": "quoted source",
                    "legacy": {"quoted_by_id_str": "root"},
                }
            ),
        ]
    )

    items = _gallery_dl_items(text, limit=5)

    assert [item.source_id for item in items] == ["root", "leaf"]
    assert items[0].raw["bookmark_root"] is True
    assert items[1].raw["bookmark_root"] is False
    assert items[1].raw["bookmark_relation"] == "quoted_tweet"


def test_write_netscape_cookies_from_playwright_state(tmp_path) -> None:
    state = tmp_path / "state.json"
    output = tmp_path / "cookies.txt"
    state.write_text(
        json.dumps(
            {
                "cookies": [
                    {
                        "name": "auth_token",
                        "value": "a",
                        "domain": ".x.com",
                        "path": "/",
                        "secure": True,
                        "expires": 2000000000,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    _write_netscape_cookies(state, output)

    assert "auth_token" in output.read_text(encoding="utf-8")


def test_x_web_graphql_bookmarks_persists_raw_pages_and_cursor_state(tmp_path) -> None:
    settings = _XWebGraphQLBookmarkSettings(
        storage_state=tmp_path / "state.json",
        folder_id=None,
        page_size=100,
        request_timeout_seconds=30,
        language="en",
        user_agent="ua",
        raw_pages_dir=tmp_path / "pages",
        cursor_state_file=tmp_path / "cursor.json",
        resume=True,
        max_pages=10,
    )

    settings.write_raw_page(
        0,
        {"data": {"ok": True}},
        endpoint="https://x.test/graphql",
        cursor=None,
        status_code=200,
    )
    settings.write_cursor_state(
        next_cursor="cursor-next",
        page_count=1,
        seen_cursors={"cursor-next"},
        item_count=100,
        finished=False,
        last_status_code=200,
        rate_limited=False,
    )

    page = json.loads((tmp_path / "pages" / "00000.json").read_text(encoding="utf-8"))
    state = settings.load_cursor_state()

    assert page["payload"]["data"]["ok"] is True
    assert state is not None
    assert state.next_cursor == "cursor-next"
    assert state.page_count == 1
