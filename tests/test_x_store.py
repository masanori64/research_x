import hashlib
import json
import sqlite3

from research_x.accounts import AccountProfile
from research_x.contracts import AcquisitionTarget, TargetKind, XItem, utc_now
from research_x.memory.corpus import build_memory_corpus
from research_x.x_store import _stable_digest, write_x_store_outputs


def test_x_store_dedupes_bookmarks_and_profile_tweets_in_same_db(tmp_path) -> None:
    db_path = tmp_path / "x.sqlite3"
    profile = AccountProfile(account_id="sampleuser", screen_name="sampleuser")
    bookmark_item = _item(
        "1",
        raw={
            "bookmark_root": True,
            "bookmark_index": 0,
            "quotedTweet": {
                "id": "2",
                "rawContent": "quoted source",
                "user": {"username": "quote_author"},
            },
        },
    )
    profile_item = _item("1", text="same tweet from profile")

    bookmark_summary = write_x_store_outputs(
        tmp_path / "bookmarks",
        items=(bookmark_item,),
        collection_kind="bookmarks",
        target=AcquisitionTarget(TargetKind.BOOKMARKS, "me", limit=10),
        account_id="sampleuser",
        account_profile=profile,
        db_path=db_path,
        download_media=False,
    )
    tweet_summary = write_x_store_outputs(
        tmp_path / "tweets",
        items=(profile_item,),
        collection_kind="profile",
        target=AcquisitionTarget(TargetKind.PROFILE, "@someone", limit=10),
        account_id="sampleuser",
        account_profile=profile,
        db_path=db_path,
        download_media=False,
    )

    assert bookmark_summary.bookmarks == 1
    assert bookmark_summary.tweets == 2
    assert tweet_summary.collection_items == 1
    with sqlite3.connect(db_path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM tweets").fetchone()[0] == 2
        assert conn.execute("SELECT COUNT(*) FROM account_bookmarks").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM collection_items").fetchone()[0] == 2

    build_memory_corpus(db_path)
    with sqlite3.connect(db_path) as conn:
        metadata = json.loads(
            conn.execute(
                "SELECT metadata_json FROM memory_documents WHERE doc_id = 'tweet:1'"
            ).fetchone()[0]
        )
    assert metadata["collection_kinds"] == ["bookmarks", "profile"]


def test_x_store_writes_db_friendly_jsonl_outputs(tmp_path) -> None:
    write_x_store_outputs(
        tmp_path,
        items=(_item("1"),),
        collection_kind="profile",
        target=AcquisitionTarget(TargetKind.PROFILE, "@a", limit=1),
        download_media=False,
    )

    rows = (tmp_path / "collection_items.jsonl").read_text(encoding="utf-8").splitlines()
    assert json.loads(rows[0])["tweet_id"] == "1"
    assert (tmp_path / "x_data.sqlite3").exists()


def test_x_store_stable_digest_uses_blake2b_with_expected_lengths() -> None:
    value = "account|bookmarks|profile|@example"

    assert _stable_digest(value) == hashlib.blake2b(
        value.encode("utf-8"), digest_size=20
    ).hexdigest()
    assert len(_stable_digest(value, digest_size=8)) == 16


def _item(source_id: str, text: str = "hello", raw=None) -> XItem:
    return XItem(
        source_id=source_id,
        url=f"https://x.com/a/status/{source_id}",
        author="a",
        text=text,
        created_at=None,
        observed_at=utc_now(),
        raw=raw or {},
    )
