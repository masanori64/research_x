from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from research_x.cli import main
from research_x.memory import media_embeddings
from research_x.memory.api_budget import api_budget_context, api_budget_status, upsert_api_price
from research_x.memory.audit import audit_memory_db
from research_x.memory.media_embeddings import (
    FIXTURE_MEDIA_PROVIDER,
    MEDIA_EMBEDDING_PROVIDER_ROLE,
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

    _assert_provider_policy_message(str(excinfo.value))
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

    _assert_provider_policy_message(str(excinfo.value))
    assert called is False


def test_media_embedding_fixture_provider_is_provider_free(media_db_with_file: Path) -> None:
    summary = build_media_embeddings(
        media_db_with_file,
        provider=FIXTURE_MEDIA_PROVIDER,
        dimensions=3,
        limit=1,
    )
    hits = search_media_embeddings(
        media_db_with_file,
        "robot image",
        provider=FIXTURE_MEDIA_PROVIDER,
        dimensions=3,
        limit=1,
    )

    assert summary.embedded == 1
    assert hits[0].media_id == "media-1"
    assert hits[0].evidence_role == "media_source_candidate_signal"
    assert hits[0].quality_scope == "media_signal_boundary_not_model_quality"

    audit = audit_memory_db(media_db_with_file)
    assert audit.fixture_artifacts["memory_media_embeddings.fixture_provider"] == 1
    assert audit.readiness["fixture_quarantine_warning_count"] == 1


def test_media_embedding_valid_approval_allows_monkeypatched_transport(
    media_db_with_file: Path,
    monkeypatch,
) -> None:
    called = False

    def fake_post_json(
        url: str,
        payload: dict[str, Any],
        *,
        headers: dict[str, str],
        timeout_seconds: float,
        retries: int = 3,
    ) -> dict[str, Any]:
        nonlocal called
        called = True
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

    with api_budget_context(
        db_path=media_db_with_file,
        run_id="authorized-media-build",
        provider_quota_approval=_provider_quota_approval(),
    ):
        summary = build_media_embeddings(
            media_db_with_file,
            dimensions=3,
            limit=1,
            allow_provider_quota=True,
        )

    assert summary.embedded == 1
    assert called is True
    status = api_budget_status(media_db_with_file, run_id="authorized-media-build")
    assert (
        status["recent_events"][0]["metadata"]["provider_policy_status"]
        == "authorized_by_provider_policy"
    )
    assert status["recent_events"][0]["provider_role"] == MEDIA_EMBEDDING_PROVIDER_ROLE
    assert (
        status["recent_provider_transport_events"][0]["provider_role"]
        == MEDIA_EMBEDDING_PROVIDER_ROLE
    )


def test_media_embedding_cli_budget_options_do_not_override_provider_policy(
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
    _assert_cli_provider_policy_error(capsys.readouterr().err)

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
    _assert_cli_provider_policy_error(capsys.readouterr().err)
    assert called is False


def test_media_embedding_cli_provider_quota_flag_requires_approval_object(
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
                "--allow-provider-quota",
            ]
        )
        == 1
    )
    assert "provider quota approval missing fields" in capsys.readouterr().err
    assert called is False


def test_media_embedding_cli_provider_quota_approval_allows_fake_transport(
    media_db_with_file: Path,
    monkeypatch,
    capsys,
) -> None:
    called = False

    def fake_post_json(
        url: str,
        payload: dict[str, Any],
        *,
        headers: dict[str, str],
        timeout_seconds: float,
        retries: int = 3,
    ) -> dict[str, Any]:
        nonlocal called
        called = True
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
                "--provider-quota-approval-id",
                "fixture-approval",
                "--provider-quota-provider",
                "gemini",
                "--provider-quota-model",
                "gemini-embedding-2",
                "--provider-quota-operation",
                "media_embedding",
                "--provider-quota-max-calls",
                "10",
                "--provider-quota-max-cost-usd",
                "0",
                "--provider-quota-price-source",
                "fixture://media-embedding-provider-gate",
                "--provider-quota-approved-scope",
                "memory:build-media-embeddings",
                "--provider-quota-approved-at",
                "2026-06-27T00:00:00+00:00",
            ]
        )
        == 0
    )
    assert '"embedded": 1' in capsys.readouterr().out

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
                "--provider-quota-approval-id",
                "fixture-approval",
                "--provider-quota-provider",
                "gemini",
                "--provider-quota-model",
                "gemini-embedding-2",
                "--provider-quota-operation",
                "media_embedding",
                "--provider-quota-max-calls",
                "10",
                "--provider-quota-max-cost-usd",
                "0",
                "--provider-quota-price-source",
                "fixture://media-embedding-provider-gate",
                "--provider-quota-approved-scope",
                "memory:media-search",
                "--provider-quota-approved-at",
                "2026-06-27T00:00:00+00:00",
            ]
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload[0]["media_id"] == "media-1"
    assert called is True


def _provider_quota_approval() -> dict[str, object]:
    return {
        "provider_quota_approval_id": "fixture-approval",
        "provider": "gemini",
        "model": "gemini-embedding-2",
        "operation": "media_embedding",
        "max_calls": 3,
        "max_cost_usd": 0.0,
        "price_source": "fixture://media-embedding-provider-gate",
        "approved_scope": "*",
        "approved_at": "2026-06-27T00:00:00+00:00",
    }


def _assert_provider_policy_message(message: str) -> None:
    assert message == MEDIA_PROVIDER_QUOTA_GATE_MESSAGE
    for term in (
        "ProviderExecutionPolicy",
        "API Budget Guard",
        "allow_provider_quota=True",
    ):
        assert term in message


def _assert_cli_provider_policy_error(stderr: str) -> None:
    assert stderr.startswith("error: ")
    _assert_provider_policy_message(stderr.removeprefix("error: ").strip())
