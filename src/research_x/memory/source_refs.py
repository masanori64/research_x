from __future__ import annotations

import hashlib
from dataclasses import dataclass


@dataclass(frozen=True)
class SourceRef:
    value: str
    namespace: str
    kind: str

    def __str__(self) -> str:
        return self.value


def x_tweet(tweet_id: object) -> str:
    return _source_ref("x", "tweet", _part(tweet_id))


def x_bookmark(account_id: object, tweet_id: object) -> str:
    return _source_ref("x", "bookmark", _part(account_id), _part(tweet_id))


def x_collection(collection_id: object, tweet_id: object) -> str:
    return _source_ref("x", "collection", _part(collection_id), _part(tweet_id))


def x_edge(relation: object, parent_tweet_id: object, child_tweet_id: object) -> str:
    return _source_ref(
        "x",
        "edge",
        _part(relation),
        _part(parent_tweet_id),
        _part(child_tweet_id),
    )


def x_media(media_id: object) -> str:
    return _source_ref("x", "media", _part(media_id))


def x_raw_payload(raw_id: object) -> str:
    return _source_ref("x", "raw_payload", _part(raw_id))


def x_provider_run(provider_run_id: object) -> str:
    return _source_ref("x", "provider_run", _part(provider_run_id))


def x_account(account_id: object) -> str:
    return _source_ref("x", "account", _part(account_id))


def note_local(vault_id: object, path: object) -> str:
    return _source_ref("note", "local", _part(vault_id), _hash_part(path))


def markdown_file(path: object) -> str:
    return _source_ref("markdown", "file", _hash_part(path))


def web_page(url: object) -> str:
    return _source_ref("web", "page", _hash_part(url))


def blog_page(site_id: object, url: object) -> str:
    return _source_ref("blog", "page", _part(site_id), _hash_part(url))


def youtube_video(video_id: object) -> str:
    return _source_ref("youtube", "video", _part(video_id))


def youtube_transcript(video_id: object, language: object) -> str:
    return _source_ref("youtube", "transcript", _part(video_id), _part(language))


def github_repo(owner: object, repo: object) -> str:
    return _source_ref("github", "repo", f"{_part(owner)}/{_part(repo)}")


def github_file(owner: object, repo: object, path: object, commit: object) -> str:
    return _source_ref(
        "github",
        "file",
        f"{_part(owner)}/{_part(repo)}:{_clean(path)}@{_clean(commit)}",
    )


def pdf_document(file_hash: object) -> str:
    return _source_ref("pdf", "document", _part(file_hash))


def parse_source_ref(value: str) -> SourceRef:
    parts = value.split(":")
    if len(parts) < 3 or not all(parts[:3]):
        raise ValueError(f"invalid source_ref: {value!r}")
    return SourceRef(value=value, namespace=parts[0], kind=parts[1])


def _source_ref(namespace: str, kind: str, *parts: str) -> str:
    cleaned = [_clean(part) for part in parts]
    if not namespace or not kind or any(not part for part in cleaned):
        raise ValueError("source_ref parts must be non-empty")
    return ":".join((namespace, kind, *cleaned))


def _part(value: object) -> str:
    return _clean(value)


def _hash_part(value: object) -> str:
    return hashlib.sha256(_clean(value).encode("utf-8")).hexdigest()


def _clean(value: object) -> str:
    text = str(value).strip()
    if not text:
        raise ValueError("source_ref parts must be non-empty")
    return text.replace("\r", " ").replace("\n", " ")
