from research_x.bookmark_store import write_bookmark_store_outputs
from research_x.contracts import XItem, utc_now


def test_bookmark_store_writes_quote_tree_without_duplicate_tweets(tmp_path) -> None:
    item = XItem(
        source_id="1",
        url="https://x.com/a/status/1",
        author="a",
        text="quote post",
        created_at=None,
        observed_at=utc_now(),
        raw={
            "bookmark_root": True,
            "bookmark_index": 0,
            "quotedTweet": {
                "id": 2,
                "url": "https://x.com/b/status/2",
                "rawContent": "quoted source",
                "user": {"username": "b"},
                "media": {"photos": [{"url": "https://pbs.twimg.com/media/a.jpg"}]},
            },
        },
    )

    summary = write_bookmark_store_outputs(tmp_path, items=(item,), download_media=False)

    assert summary.bookmarks == 1
    assert summary.tweets == 2
    assert summary.edges == 1
    assert summary.media == 1
    assert (tmp_path / "bookmarks.jsonl").exists()
    assert (tmp_path / "tweets.jsonl").exists()
    assert (tmp_path / "tweet_edges.jsonl").exists()
    assert (tmp_path / "media.jsonl").exists()
    assert (tmp_path / "bookmark_trees.jsonl").exists()
