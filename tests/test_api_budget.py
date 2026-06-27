import json
import sqlite3
from pathlib import Path

from research_x.cli import main
from research_x.memory.api_budget import (
    ApiBudgetExceededError,
    api_budget_context,
    api_budget_status,
    api_units,
    budgeted_api_call,
    provider_quota_preflight,
    set_api_budget_policy,
    set_api_kill_switch,
    upsert_api_price,
)
from research_x.memory.embeddings import _post_json
from research_x.memory.schema import ensure_memory_schema


def test_api_budget_schema_creates_safe_default_policy(tmp_path: Path) -> None:
    db_path = tmp_path / "x.sqlite3"

    with sqlite3.connect(db_path) as conn:
        ensure_memory_schema(conn)
        row = conn.execute(
            """
            SELECT max_run_usd, max_day_usd, max_month_usd,
                   unknown_price_action, kill_switch_enabled
            FROM memory_api_budget_policies
            WHERE policy_id = 'default'
            """
        ).fetchone()

    assert row == (1.0, 5.0, 25.0, "block", 0)


def test_unpriced_provider_blocks_before_http(monkeypatch, tmp_path: Path) -> None:
    db_path = tmp_path / "x.sqlite3"
    called = False

    def fake_urlopen(*_args, **_kwargs):
        nonlocal called
        called = True
        raise AssertionError("HTTP should not be sent for unpriced API")

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    with api_budget_context(db_path=db_path, run_id="run"):
        try:
            _post_json(
                "https://api.openai.com/v1/embeddings",
                {"model": "text-embedding-3-small", "input": ["x"]},
                headers={"Authorization": "Bearer test"},
                timeout_seconds=1,
                budget_provider="openai",
                budget_model="text-embedding-3-small",
                budget_units=api_units(calls=1, input_tokens=1),
            )
        except ApiBudgetExceededError as exc:
            assert "budget_exhausted" in str(exc)
        else:
            raise AssertionError("unpriced API should be blocked")

    assert called is False
    status = api_budget_status(db_path)
    assert status["recent_events"][0]["status"] == "blocked"
    assert "price catalog missing" in status["recent_events"][0]["error"]


def test_priced_api_reserves_and_finishes_ok(tmp_path: Path) -> None:
    db_path = tmp_path / "x.sqlite3"
    upsert_api_price(
        db_path,
        provider="openai",
        model="text-embedding-3-small",
        operation="embedding",
        unit="input_token",
        usd_per_unit=0.00000002,
        source_url="https://platform.openai.com/docs/pricing",
        checked_at="2026-06-04T00:00:00+00:00",
    )

    with (
        api_budget_context(db_path=db_path, run_id="run"),
        budgeted_api_call(
            provider="openai",
            model="text-embedding-3-small",
            provider_role="embedding",
            operation="embedding",
            units=api_units(calls=1, input_tokens=100),
            request_payload={"input": "x"},
        ),
    ):
        pass

    status = api_budget_status(db_path, run_id="run")
    assert status["usage"]["run"]["calls"] == 1
    assert status["usage"]["run"]["input_tokens"] == 100
    assert status["usage"]["run"]["estimated_cost_usd"] > 0
    assert status["recent_events"][0]["status"] == "ok"


def test_run_budget_includes_reserved_cost(tmp_path: Path) -> None:
    db_path = tmp_path / "x.sqlite3"
    upsert_api_price(
        db_path,
        provider="openai",
        model="m",
        operation="answer",
        unit="input_token",
        usd_per_unit=1.0,
        source_url="https://example.test/pricing",
        checked_at="2026-06-04T00:00:00+00:00",
    )
    set_api_budget_policy(db_path, max_run_usd=5.0)

    with api_budget_context(db_path=db_path, run_id="run"):
        reservation = budgeted_api_call(
            provider="openai",
            model="m",
            provider_role="answer_engine",
            operation="answer",
            units=api_units(calls=1, input_tokens=4),
            request_payload={"n": 1},
        )
        with reservation:
            try:
                with budgeted_api_call(
                    provider="openai",
                    model="m",
                    provider_role="answer_engine",
                    operation="answer",
                    units=api_units(calls=1, input_tokens=2),
                    request_payload={"n": 2},
                ):
                    pass
            except ApiBudgetExceededError:
                pass
            else:
                raise AssertionError("reserved cost should count against run cap")

    report = api_budget_status(db_path, run_id="run")
    assert {event["status"] for event in report["recent_events"]} == {"ok", "blocked"}


def test_kill_switch_blocks_next_call(tmp_path: Path) -> None:
    db_path = tmp_path / "x.sqlite3"
    upsert_api_price(
        db_path,
        provider="openai",
        model="m",
        operation="answer",
        unit="input_token",
        usd_per_unit=0.0,
        source_url="https://example.test/pricing",
        checked_at="2026-06-04T00:00:00+00:00",
    )
    set_api_kill_switch(db_path, enabled=True)

    with api_budget_context(db_path=db_path, run_id="run"):
        try:
            with budgeted_api_call(
                provider="openai",
                model="m",
                provider_role="answer_engine",
                operation="answer",
                units=api_units(calls=1, input_tokens=1),
                request_payload={"n": 1},
            ):
                pass
        except ApiBudgetExceededError as exc:
            assert "kill switch" in str(exc)
        else:
            raise AssertionError("kill switch should block")


def test_fake_and_local_providers_are_exempt(tmp_path: Path) -> None:
    db_path = tmp_path / "x.sqlite3"

    with api_budget_context(db_path=db_path, run_id="run"):
        with budgeted_api_call(
            provider="fake",
            model="fake-model",
            provider_role="answer_engine",
            operation="answer",
            units=api_units(calls=1, input_tokens=999999),
            request_payload={"fake": True},
        ):
            pass
        with budgeted_api_call(
            provider="local_hash",
            model="local-hash-v1",
            provider_role="embedding",
            operation="embedding",
            units=api_units(calls=1, input_tokens=999999),
            request_payload={"local": True},
        ):
            pass

    with sqlite3.connect(db_path) as conn:
        ensure_memory_schema(conn)
        rows = conn.execute("SELECT COUNT(*) FROM memory_api_usage_events").fetchone()[0]

    assert rows == 0


def test_api_budget_status_is_json_serializable(tmp_path: Path) -> None:
    db_path = tmp_path / "x.sqlite3"
    payload = api_budget_status(db_path)

    assert json.dumps(payload, ensure_ascii=False)


def test_api_budget_cli_accepts_db_after_nested_command(tmp_path: Path, capsys) -> None:
    db_path = tmp_path / "x.sqlite3"

    assert (
        main(
            [
                "memory",
                "api-budget",
                "price-set",
                "--db",
                str(db_path),
                "--provider",
                "gemini",
                "--model",
                "gemini-embedding-2",
                "--operation",
                "embedding",
                "--unit",
                "input_tokens",
                "--usd-per-unit",
                "0.001",
            ]
        )
        == 0
    )
    assert (
        main(
            [
                "memory",
                "api-budget",
                "status",
                "--db",
                str(db_path),
            ]
        )
        == 0
    )

    output = capsys.readouterr().out
    assert "api price set: gemini/gemini-embedding-2 embedding input_tokens" in output
    assert "input_token" in output


def test_provider_quota_preflight_requires_approval_and_sends_zero_requests(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "x.sqlite3"

    report = provider_quota_preflight(
        db_path,
        provider="gemini",
        model="gemini-embedding-2",
        operation="media_embedding",
        units=api_units(calls=1),
    )

    assert report["status"] == "approval_required"
    assert report["provider_call_allowed"] is False
    assert report["provider_requests_sent"] == 0
    assert report["approval_contract"]["valid"] is False
    assert "provider quota approval object is required" in report["approval_contract"]["errors"]


def test_provider_quota_preflight_valid_approval_remains_gated_by_freeze(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "x.sqlite3"
    upsert_api_price(
        db_path,
        provider="gemini",
        model="gemini-embedding-2",
        operation="media_embedding",
        unit="call",
        usd_per_unit=0.0,
        source_url="fixture://provider-quota-preflight",
        notes="provider-free dry-run fixture",
    )

    report = provider_quota_preflight(
        db_path,
        provider="gemini",
        model="gemini-embedding-2",
        operation="media_embedding",
        units=api_units(calls=1),
        approval=_provider_quota_approval(),
        approved_scope="memory:build-media-embeddings",
    )

    assert report["status"] == "provider_gated_by_no_quota_freeze"
    assert report["dry_run"] is True
    assert report["provider_call_allowed"] is False
    assert report["provider_requests_sent"] == 0
    assert report["budget_guard"]["status"] == "passed"
    assert report["approval_contract"]["valid"] is True
    assert json.dumps(report, ensure_ascii=False)


def test_provider_quota_preflight_cli_outputs_json(tmp_path: Path, capsys) -> None:
    db_path = tmp_path / "x.sqlite3"
    upsert_api_price(
        db_path,
        provider="gemini",
        model="gemini-embedding-2",
        operation="media_embedding",
        unit="call",
        usd_per_unit=0.0,
        source_url="fixture://provider-quota-preflight",
        notes="provider-free dry-run fixture",
    )

    assert (
        main(
            [
                "memory",
                "api-budget",
                "preflight",
                "--db",
                str(db_path),
                "--provider",
                "gemini",
                "--model",
                "gemini-embedding-2",
                "--operation",
                "media_embedding",
                "--limit",
                "1",
                "--current-scope",
                "memory:build-media-embeddings",
                "--provider-quota-approval-id",
                "fixture-approval",
                "--provider-quota-provider",
                "gemini",
                "--provider-quota-model",
                "gemini-embedding-2",
                "--provider-quota-operation",
                "media_embedding",
                "--provider-quota-max-calls",
                "1",
                "--provider-quota-max-cost-usd",
                "0",
                "--provider-quota-price-source",
                "fixture://provider-quota-preflight",
                "--provider-quota-approved-scope",
                "memory:build-media-embeddings",
                "--provider-quota-approved-at",
                "2026-06-27T00:00:00+00:00",
                "--json",
            ]
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "provider_gated_by_no_quota_freeze"
    assert payload["provider_requests_sent"] == 0
    assert payload["approval_contract"]["valid"] is True


def _provider_quota_approval() -> dict[str, object]:
    return {
        "provider_quota_approval_id": "fixture-approval",
        "provider": "gemini",
        "model": "gemini-embedding-2",
        "operation": "media_embedding",
        "max_calls": 1,
        "max_cost_usd": 0.0,
        "price_source": "fixture://provider-quota-preflight",
        "approved_scope": "memory:build-media-embeddings",
        "approved_at": "2026-06-27T00:00:00+00:00",
    }
