import hashlib
import json
import sqlite3
from types import SimpleNamespace

from research_x.accounts import AccountProfile
from research_x.contracts import (
    AcquisitionTarget,
    FetchOutcome,
    OutcomeStatus,
    TargetKind,
    XItem,
    utc_now,
)
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


def test_x_store_records_media_download_policy_without_download(tmp_path) -> None:
    db_path = tmp_path / "x.sqlite3"
    item = _item(
        "1",
        raw={
            "media": {
                "photos": [
                    {
                        "url": "https://example.test/media/1.jpg",
                        "altText": "diagram",
                    }
                ]
            }
        },
    )

    summary = write_x_store_outputs(
        tmp_path / "store",
        items=(item,),
        collection_kind="bookmarks",
        target=AcquisitionTarget(TargetKind.BOOKMARKS, "me", limit=1),
        db_path=db_path,
        download_media=True,
        media_download_policy="metadata_only",
    )

    assert summary.media_download_policy == "metadata_only"
    assert summary.downloaded_media == 0
    media_rows = (tmp_path / "store" / "media.jsonl").read_text(encoding="utf-8").splitlines()
    media = json.loads(media_rows[0])
    assert media["download_status"] == "metadata_only"
    assert media["media_download_policy"] == "metadata_only"
    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            "SELECT download_status, media_download_policy FROM media"
        ).fetchone()
    assert row == ("metadata_only", "metadata_only")


def test_x_store_records_downloaded_media_hash(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "x.sqlite3"
    payload = b"image-bytes"

    class FakeResponse:
        headers = {"content-type": "image/jpeg"}

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

        def read(self) -> bytes:
            return payload

    def fake_urlopen(request, timeout):
        assert timeout == 5.0
        return FakeResponse()

    monkeypatch.setattr("research_x.x_store.urlopen", fake_urlopen)

    item = _item(
        "1",
        raw={
            "media": {
                "photos": [
                    {
                        "url": "https://example.test/media/1.jpg",
                        "altText": "diagram",
                    }
                ]
            }
        },
    )

    write_x_store_outputs(
        tmp_path / "store",
        items=(item,),
        collection_kind="bookmarks",
        target=AcquisitionTarget(TargetKind.BOOKMARKS, "me", limit=1),
        db_path=db_path,
        download_media=True,
        media_download_policy="full_media_allowed",
        media_timeout_seconds=5.0,
    )

    expected_hash = hashlib.sha256(payload).hexdigest()
    media_rows = (tmp_path / "store" / "media.jsonl").read_text(encoding="utf-8").splitlines()
    media = json.loads(media_rows[0])
    assert media["download_status"] == "ok"
    assert media["media_sha256"] == expected_hash
    with sqlite3.connect(db_path) as conn:
        row = conn.execute("SELECT media_sha256 FROM media").fetchone()
    assert row == (expected_hash,)


def test_x_store_provider_run_metadata_has_account_and_no_secret_values(tmp_path) -> None:
    db_path = tmp_path / "x.sqlite3"
    now = utc_now()
    target = AcquisitionTarget(TargetKind.BOOKMARKS, "me", limit=1)
    outcome = FetchOutcome(
        adapter_id="metadata_provider",
        target=target,
        status=OutcomeStatus.OK,
        started_at=now,
        finished_at=now,
        items=(_item("1", raw={"bookmark_root": True}),),
        metadata={
            "provider_route": "metadata_provider",
            "storage_state": ".secrets/playwright_x_state.json",
            "auth_token": "secret-token",
            "request_count": 2,
        },
    )
    attempt = SimpleNamespace(
        provider_id="metadata_provider",
        outcome=outcome,
        evidence_path=tmp_path / "attempt.json",
    )

    write_x_store_outputs(
        tmp_path / "store",
        items=outcome.items,
        collection_kind="bookmarks",
        target=target,
        account_id="sampleuser",
        account_profile=AccountProfile(
            account_id="sampleuser",
            screen_name="sampleuser",
            metadata={"api_token": "do-not-store"},
        ),
        attempts=(attempt,),
        db_path=db_path,
        download_media=False,
    )

    with sqlite3.connect(db_path) as conn:
        metadata = json.loads(
            conn.execute("SELECT metadata_json FROM provider_runs").fetchone()[0]
        )
    assert metadata["account_id"] == "sampleuser"
    assert metadata["account_profile"]["screen_name"] == "sampleuser"
    assert metadata["auth_token"] == "[redacted]"
    assert metadata["account_profile"]["metadata"]["api_token"] == "[redacted]"
    assert metadata["storage_state_path"] == ".secrets/playwright_x_state.json"


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
