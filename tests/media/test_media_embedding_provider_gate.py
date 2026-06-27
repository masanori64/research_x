from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from research_x.cli import main
from research_x.memory import media_embeddings
from research_x.memory.api_budget import upsert_api_price
from research_x.memory.media_embeddings import (
    MEDIA_PROVIDER_QUOTA_GATE_MESSAGE,
    build_media_embeddings,
    search_media_embeddings,
)


def test_build_media_embeddings_blocks_provider_calls_by_default(
    media_db_with_file: Path,
    monkeypatch,
) -> None:
    called = False

    def fail_post_json(
        url: str,
        payload: dict[str, Any],
        *,
        headers: dict[str, str],
        timeout_seconds: float,
        retries: int = 3,
    ) -> dict[str, Any]:
        nonlocal called
        called = True
        raise AssertionError("provider media embedding call should be gated")

    monkeypatch.setattr(media_embeddings, "_post_json", fail_post_json)

    with pytest.raises(RuntimeError) as excinfo:
        build_media_embeddings(media_db_with_file, dimensions=3, limit=1)

    _assert_freeze_message(str(excinfo.value))
    assert called is False


def test_search_media_embeddings_blocks_query_embedding_by_default(
    media_db_with_file: Path,
    monkeypatch,
) -> None:
    called = False

    def fail_post_json(
        url: str,
        payload: dict[str, Any],
        *,
        headers: dict[str, str],
        timeout_seconds: float,
        retries: int = 3,
    ) -> dict[str, Any]:
        nonlocal called
        called = True
        raise AssertionError("provider media embedding query should be gated")

    monkeypatch.setattr(media_embeddings, "_post_json", fail_post_json)

    with pytest.raises(RuntimeError) as excinfo:
        search_media_embeddings(media_db_with_file, "robot image", dimensions=3, limit=1)

    _assert_freeze_message(str(excinfo.value))
    assert called is False


def test_media_embedding_fake_fixture_requires_explicit_provider_quota_flag(
    media_db_with_file: Path,
    monkeypatch,
) -> None:
    payloads: list[dict[str, Any]] = []

    def fake_post_json(
        url: str,
        payload: dict[str, Any],
        *,
        headers: dict[str, str],
        timeout_seconds: float,
        retries: int = 3,
    ) -> dict[str, Any]:
        payloads.append(payload)
        return {"embeddings": [{"values": [0.1, 0.2, 0.3]}]}

    monkeypatch.setenv("GEMINI_API_KEY", "fake-key")
    monkeypatch.setattr(media_embeddings, "_post_json", fake_post_json)

    summary = build_media_embeddings(
        media_db_with_file,
        dimensions=3,
        limit=1,
        allow_provider_quota=True,
    )
    hits = search_media_embeddings(
        media_db_with_file,
        "robot image",
        dimensions=3,
        limit=1,
        allow_provider_quota=True,
    )

    assert summary.embedded == 1
    assert len(payloads) == 2
    assert hits[0].media_id == "media-1"
    assert hits[0].evidence_role == "media_source_candidate_signal"
    assert hits[0].quality_scope == "media_signal_boundary_not_model_quality"


def test_media_embedding_cli_budget_options_do_not_override_provider_freeze(
    media_db_with_file: Path,
    monkeypatch,
    capsys,
) -> None:
    called = False

    def fail_post_json(
        url: str,
        payload: dict[str, Any],
        *,
        headers: dict[str, str],
        timeout_seconds: float,
        retries: int = 3,
    ) -> dict[str, Any]:
        nonlocal called
        called = True
        raise AssertionError("provider media embedding call should be gated")

    monkeypatch.setattr(media_embeddings, "_post_json", fail_post_json)

    assert (
        main(
            [
                "memory",
                "build-media-embeddings",
                "--db",
                str(media_db_with_file),
                "--dimensions",
                "3",
                "--limit",
                "1",
                "--allow-unpriced-api",
            ]
        )
        == 1
    )
    _assert_cli_freeze_error(capsys.readouterr().err)

    assert (
        main(
            [
                "memory",
                "media-search",
                "--db",
                str(media_db_with_file),
                "--query",
                "robot image",
                "--dimensions",
                "3",
                "--limit",
                "1",
                "--allow-unpriced-api",
            ]
        )
        == 1
    )
    _assert_cli_freeze_error(capsys.readouterr().err)
    assert called is False


def test_media_embedding_cli_allows_explicit_fake_provider_fixture(
    media_db_with_file: Path,
    monkeypatch,
    capsys,
) -> None:
    def fake_post_json(
        url: str,
        payload: dict[str, Any],
        *,
        headers: dict[str, str],
        timeout_seconds: float,
        retries: int = 3,
    ) -> dict[str, Any]:
        return {"embeddings": [{"values": [0.1, 0.2, 0.3]}]}

    monkeypatch.setenv("GEMINI_API_KEY", "fake-key")
    monkeypatch.setattr(media_embeddings, "_post_json", fake_post_json)
    upsert_api_price(
        media_db_with_file,
        provider="gemini",
        model="gemini-embedding-2",
        operation="media_embedding",
        unit="call",
        usd_per_unit=0.0,
        source_url="fixture://media-embedding-provider-gate",
        notes="provider-free monkeypatched fixture",
    )

    assert (
        main(
            [
                "memory",
                "build-media-embeddings",
                "--db",
                str(media_db_with_file),
                "--dimensions",
                "3",
                "--limit",
                "1",
                "--allow-provider-quota",
            ]
        )
        == 0
    )
    build_payload = json.loads(capsys.readouterr().out)
    assert build_payload["embedded"] == 1

    assert (
        main(
            [
                "memory",
                "media-search",
                "--db",
                str(media_db_with_file),
                "--query",
                "robot image",
                "--dimensions",
                "3",
                "--limit",
                "1",
                "--json",
                "--allow-provider-quota",
            ]
        )
        == 0
    )
    hits = json.loads(capsys.readouterr().out)
    assert hits[0]["media_id"] == "media-1"
    assert hits[0]["answer_support_allowed"] is False
    assert hits[0]["quality_scope"] == "media_signal_boundary_not_model_quality"


def _assert_freeze_message(message: str) -> None:
    assert message == MEDIA_PROVIDER_QUOTA_GATE_MESSAGE
    for term in (
        "paid/free-tier",
        "trial-credit",
        "zero-dollar",
        "keyless",
        "API Budget Guard",
    ):
        assert term in message


def _assert_cli_freeze_error(stderr: str) -> None:
    assert stderr.startswith("error: ")
    _assert_freeze_message(stderr.removeprefix("error: ").strip())
