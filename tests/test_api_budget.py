import json
import sqlite3
from pathlib import Path

from research_x.cli import main
from research_x.memory import api_budget
from research_x.memory.api_budget import (
    ApiBudgetExceededError,
    active_api_budget_context,
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
        provider_tables = {
            row[0]
            for row in conn.execute(
                """
                SELECT name
                FROM sqlite_master
                WHERE type = 'table'
                  AND name LIKE 'memory_provider_%'
                """
            ).fetchall()
        }

    assert row == (1.0, 5.0, 25.0, "block", 0)
    assert {
        "memory_provider_authorizations",
        "memory_provider_execution_policies",
        "memory_provider_preflights",
        "memory_provider_transport_events",
    }.issubset(provider_tables)


def test_unpriced_provider_blocks_before_http(monkeypatch, tmp_path: Path) -> None:
    db_path = tmp_path / "x.sqlite3"
    called = False

    def fake_urlopen(*_args, **_kwargs):
        nonlocal called
        called = True
        raise AssertionError("HTTP should not be sent for unpriced API")

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    with api_budget_context(
        db_path=db_path,
        run_id="run",
        provider_quota_approval=_provider_quota_approval(
            provider="openai",
            model="text-embedding-3-small",
            operation="embedding",
            max_cost_usd=0.01,
        ),
    ):
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
    assert (
        status["recent_events"][0]["metadata"]["provider_policy_status"]
        == "authorized_by_provider_policy"
    )


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
        api_budget_context(
            db_path=db_path,
            run_id="run",
            provider_quota_approval=_provider_quota_approval(
                provider="openai",
                model="text-embedding-3-small",
                operation="embedding",
                max_cost_usd=0.01,
            ),
        ),
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
    assert status["recent_provider_transport_events"][0]["status"] == "ok"
    assert status["provider_execution_policies"][0]["authorization_id"] == "fixture-approval"


def test_role_scoped_provider_policy_allows_matching_text_embedding_role(tmp_path: Path) -> None:
    db_path = tmp_path / "x.sqlite3"
    upsert_api_price(
        db_path,
        provider="gemini",
        model="gemini-embedding-2",
        operation="embedding",
        unit="call",
        usd_per_unit=0.0,
        source_url="fixture://role-scoped-policy",
    )
    execution_policy = {
        "policy_id": "approval:role-scoped-text-embedding",
        "authorization_id": "role-scoped-text-embedding",
        "provider": "gemini",
        "model": "gemini-embedding-2",
        "operation": "embedding",
        "provider_role": "text_embedding",
        "allowed": True,
        "max_calls": 1,
        "max_cost_usd": 0.0,
        "approved_scope": "memory:build-embeddings",
        "storage_rights": "local-db-derived-text",
        "rollback_scope": "delete_canary_embeddings",
    }

    with (
        api_budget_context(
            db_path=db_path,
            run_id="run",
            provider_execution_policy=execution_policy,
            provider_quota_current_scope="memory:build-embeddings",
        ),
        budgeted_api_call(
            provider="gemini",
            model="gemini-embedding-2",
            provider_role="text_embedding",
            operation="embedding",
            units=api_units(calls=1),
            request_payload={"requests": []},
        ),
    ):
        pass

    status = api_budget_status(db_path, run_id="run")
    assert status["recent_events"][0]["status"] == "ok"
    assert status["recent_events"][0]["provider_role"] == "text_embedding"


def test_embedding_provider_gate_uses_text_embedding_role_for_saved_policy(
    tmp_path: Path,
) -> None:
    from research_x.memory.embeddings import require_embedding_provider_quota_allowed

    db_path = tmp_path / "x.sqlite3"
    execution_policy = {
        "policy_id": "approval:role-scoped-text-embedding",
        "authorization_id": "role-scoped-text-embedding",
        "provider": "gemini",
        "model": "gemini-embedding-2",
        "operation": "embedding",
        "provider_role": "text_embedding",
        "allowed": True,
        "max_calls": 1,
        "max_cost_usd": 0.0,
        "approved_scope": "memory:build-embeddings",
        "storage_rights": "local-db-derived-text",
        "rollback_scope": "delete_canary_embeddings",
    }

    with api_budget_context(
        db_path=db_path,
        run_id="run",
        provider_execution_policy=execution_policy,
        provider_quota_current_scope="memory:build-embeddings",
    ):
        require_embedding_provider_quota_allowed(
            "gemini",
            allow_provider_quota=True,
            model="gemini-embedding-2",
        )


def test_provider_execution_policy_max_calls_blocks_second_call(tmp_path: Path) -> None:
    db_path = tmp_path / "x.sqlite3"
    upsert_api_price(
        db_path,
        provider="openai",
        model="m",
        operation="answer",
        unit="call",
        usd_per_unit=0.0,
        source_url="fixture://provider-execution-policy",
    )

    with api_budget_context(
        db_path=db_path,
        run_id="run",
        provider_quota_approval=_provider_quota_approval(
            provider="openai",
            model="m",
            operation="answer",
            max_calls=1,
            max_cost_usd=0.0,
        ),
    ):
        with budgeted_api_call(
            provider="openai",
            model="m",
            provider_role="answer_engine",
            operation="answer",
            units=api_units(calls=1),
            request_payload={"n": 1},
        ):
            pass
        try:
            with budgeted_api_call(
                provider="openai",
                model="m",
                provider_role="answer_engine",
                operation="answer",
                units=api_units(calls=1),
                request_payload={"n": 2},
            ):
                pass
        except ApiBudgetExceededError as exc:
            assert "policy calls limit exceeded" in str(exc)
        else:
            raise AssertionError("authorization max_calls should block the second call")

    report = api_budget_status(db_path, run_id="run")
    assert [event["status"] for event in report["recent_events"]] == ["blocked", "ok"]


def test_authorized_unpriced_provider_can_pass_with_explicit_override(tmp_path: Path) -> None:
    db_path = tmp_path / "x.sqlite3"

    with (
        api_budget_context(
            db_path=db_path,
            run_id="run",
            allow_unpriced_api=True,
            provider_quota_approval=_provider_quota_approval(
                provider="openai",
                model="m",
                operation="answer",
                max_calls=1,
                max_cost_usd=0.0,
                price_source="manual-unpriced-override",
            ),
        ),
        budgeted_api_call(
            provider="openai",
            model="m",
            provider_role="answer_engine",
            operation="answer",
            units=api_units(calls=1),
            request_payload={"n": 1},
        ),
    ):
        pass

    report = api_budget_status(db_path, run_id="run")
    event = report["recent_events"][0]
    assert event["status"] == "ok"
    assert event["metadata"]["price_status"] == "unpriced_override"
    assert "price catalog missing" in event["metadata"]["price_warning"]


def test_unauthorized_budgeted_api_call_blocks_even_with_price(tmp_path: Path) -> None:
    db_path = tmp_path / "x.sqlite3"
    upsert_api_price(
        db_path,
        provider="openai",
        model="text-embedding-3-small",
        operation="embedding",
        unit="call",
        usd_per_unit=0.0,
        source_url="fixture://provider-policy-required",
    )

    with api_budget_context(db_path=db_path, run_id="run"):
        try:
            with budgeted_api_call(
                provider="openai",
                model="text-embedding-3-small",
                provider_role="embedding",
                operation="embedding",
                units=api_units(calls=1),
                request_payload={"input": "x"},
            ):
                pass
        except ApiBudgetExceededError as exc:
            assert "provider execution policy is required" in str(exc)
        else:
            raise AssertionError("unauthorized provider execution should block")

    status = api_budget_status(db_path, run_id="run")
    assert status["recent_events"][0]["status"] == "blocked"
    assert "provider execution policy is required" in status["recent_events"][0]["error"]
    assert (
        status["recent_events"][0]["metadata"]["provider_policy_status"]
        == "provider_execution_policy_required"
    )


def test_provider_policy_required_blocks_budgeted_api_call_without_active_context() -> None:
    try:
        with budgeted_api_call(
            provider="openai",
            model="text-embedding-3-small",
            provider_role="embedding",
            operation="embedding",
            units=api_units(calls=1),
            request_payload={"input": "x"},
        ):
            pass
    except RuntimeError as exc:
        assert "provider_execution_policy_required" in str(exc)
    else:
        raise AssertionError("provider policy should block provider execution without context")


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

    with api_budget_context(
        db_path=db_path,
        run_id="run",
        provider_quota_approval=_provider_quota_approval(
            provider="openai",
            model="m",
            operation="answer",
            max_calls=3,
            max_cost_usd=10.0,
        ),
    ):
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

    with api_budget_context(
        db_path=db_path,
        run_id="run",
        provider_quota_approval=_provider_quota_approval(
            provider="openai",
            model="m",
            operation="answer",
            max_cost_usd=1.0,
        ),
    ):
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

    with api_budget_context(db_path=db_path, run_id="run", provider_policy_required=False):
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
        with budgeted_api_call(
            provider="fixture_media",
            model="fixture-media-v1",
            provider_role="embedding",
            operation="embedding",
            units=api_units(calls=1, input_tokens=999999),
            request_payload={"fixture": True},
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


def test_api_budget_status_aggregates_all_api_units_and_filters_run_id(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "x.sqlite3"
    _seed_zero_api_prices(db_path, provider="openai", model="gpt-test", operation="answer")
    _seed_zero_api_prices(db_path, provider="gemini", model="embed-test", operation="embedding")

    with (
        api_budget_context(
            db_path=db_path,
            run_id="run-a",
            provider_quota_approval=_provider_quota_approval(
                approval_id="auth-openai-answer",
                provider="openai",
                model="gpt-test",
                operation="answer",
                max_calls=5,
                max_cost_usd=1.0,
            ),
        ),
        budgeted_api_call(
            provider="openai",
            model="gpt-test",
            provider_role="answer_engine",
            operation="answer",
            units=api_units(
                calls=1,
                retries=2,
                input_tokens=10,
                output_tokens=5,
                media_bytes=256,
                documents=1,
                pages=3,
            ),
            request_payload={"input": "x"},
        ),
    ):
        pass

    with (
        api_budget_context(
            db_path=db_path,
            run_id="other-run",
            provider_quota_approval=_provider_quota_approval(
                approval_id="auth-gemini-embedding",
                provider="gemini",
                model="embed-test",
                operation="embedding",
                max_calls=5,
                max_cost_usd=1.0,
            ),
        ),
        budgeted_api_call(
            provider="gemini",
            model="embed-test",
            provider_role="embedding",
            operation="embedding",
            units=api_units(calls=1, input_tokens=99),
            request_payload={"input": "other"},
        ),
    ):
        pass

    provider_quota_preflight(
        db_path,
        provider="openai",
        model="gpt-test",
        operation="answer",
        provider_role="answer_engine",
        units=api_units(calls=1, input_tokens=1),
        approval=_provider_quota_approval(
            approval_id="preflight-openai-answer",
            provider="openai",
            model="gpt-test",
            operation="answer",
            max_calls=5,
            max_cost_usd=1.0,
        ),
        run_id="run-a",
    )
    provider_quota_preflight(
        db_path,
        provider="gemini",
        model="embed-test",
        operation="embedding",
        units=api_units(calls=1, input_tokens=1),
        approval=_provider_quota_approval(
            approval_id="preflight-gemini-embedding",
            provider="gemini",
            model="embed-test",
            operation="embedding",
            max_calls=5,
            max_cost_usd=1.0,
        ),
        run_id="other-run",
    )

    set_api_kill_switch(db_path, enabled=True)
    with api_budget_context(
        db_path=db_path,
        run_id="run-a",
        provider_quota_approval=_provider_quota_approval(
            approval_id="auth-openai-answer-blocked",
            provider="openai",
            model="gpt-test",
            operation="answer",
            max_calls=5,
            max_cost_usd=1.0,
        ),
    ):
        try:
            with budgeted_api_call(
                provider="openai",
                model="gpt-test",
                provider_role="answer_engine",
                operation="answer",
                units=api_units(calls=1, input_tokens=1),
                request_payload={"input": "blocked"},
            ):
                pass
        except ApiBudgetExceededError:
            pass
        else:
            raise AssertionError("kill switch should write a blocked event")

    status = api_budget_status(db_path, run_id="run-a", recent_limit=10)
    provider_usage = status["provider_usage"]

    assert len(provider_usage) == 1
    usage = provider_usage[0]
    assert usage["provider"] == "openai"
    assert usage["model"] == "gpt-test"
    assert usage["operation"] == "answer"
    assert usage["calls"] == 1
    assert usage["retries"] == 2
    assert usage["input_tokens"] == 10
    assert usage["output_tokens"] == 5
    assert usage["media_bytes"] == 256
    assert usage["documents"] == 1
    assert usage["pages"] == 3
    assert usage["status_counts"]["ok"] == 1
    assert usage["status_counts"]["blocked"] == 1
    assert {event["run_id"] for event in status["recent_events"]} == {"run-a"}
    assert {row["run_id"] for row in status["recent_provider_preflights"]} == {"run-a"}
    assert {row["run_id"] for row in status["recent_provider_transport_events"]} == {"run-a"}
    coverage = status["price_catalog_coverage"]
    assert coverage["unpriced_observed_api_count"] == 0
    assert {
        "provider": "openai",
        "model": "gpt-test",
        "operation": "answer",
    } in coverage["priced_api_keys"]
    assert all(
        set(item) == {"provider", "model", "operation"}
        for item in coverage["priced_api_keys"]
    )


def test_api_budget_status_exposes_active_reserved_exposure(tmp_path: Path) -> None:
    db_path = tmp_path / "x.sqlite3"
    upsert_api_price(
        db_path,
        provider="openai",
        model="gpt-test",
        operation="answer",
        unit="call",
        usd_per_unit=0.25,
        source_url="fixture://price",
    )
    upsert_api_price(
        db_path,
        provider="openai",
        model="gpt-test",
        operation="answer",
        unit="input_token",
        usd_per_unit=0.0,
        source_url="fixture://price",
    )

    with api_budget_context(
        db_path=db_path,
        run_id="run-active",
        provider_quota_approval=_provider_quota_approval(
            approval_id="auth-openai-active",
            provider="openai",
            model="gpt-test",
            operation="answer",
            max_calls=5,
            max_cost_usd=1.0,
        ),
    ):
        context = active_api_budget_context()
        assert context is not None
        api_budget.reserve_api_budget(
            context,
            provider="openai",
            model="gpt-test",
            provider_role="answer_engine",
            operation="answer",
            units=api_units(calls=1, input_tokens=10),
            request_payload={"input": "active"},
        )

    status = api_budget_status(db_path, run_id="run-active")
    active = status["active_exposure"]

    assert active["active_count"] == 1
    assert active["estimated_cost_usd"] == 0.25
    assert active["units"]["calls"] == 1
    assert active["units"]["input_tokens"] == 10
    assert active["events"][0]["status"] == "reserved"
    assert active["events"][0]["finished_at"] is None


def test_api_dashboard_cli_serves_until_keyboard_interrupt(
    monkeypatch,
    tmp_path: Path,
    capsys,
) -> None:
    db_path = tmp_path / "x.sqlite3"
    captured: dict[str, object] = {}

    class FakeServer:
        def __init__(self, address, handler_cls):
            captured["address"] = address
            captured["handler_cls"] = handler_cls

        def serve_forever(self):
            captured["served"] = True
            raise KeyboardInterrupt

        def server_close(self):
            captured["closed"] = True

    monkeypatch.setattr(api_budget, "ThreadingHTTPServer", FakeServer)
    monkeypatch.setattr(api_budget.webbrowser, "open", lambda url: captured.setdefault("open", url))

    assert (
        main(
            [
                "memory",
                "api-dashboard",
                "--db",
                str(db_path),
                "--host",
                "127.0.0.1",
                "--port",
                "0",
                "--no-open-browser",
                "--policy-id",
                "default",
                "--run-id",
                "run-a",
                "--recent-limit",
                "5",
            ]
        )
        == 0
    )

    output = capsys.readouterr().out
    assert captured["address"] == ("127.0.0.1", 0)
    assert captured["served"] is True
    assert captured["closed"] is True
    assert "open" not in captured
    assert "research_x api-dashboard: http://127.0.0.1:0" in output
    assert "research_x api-dashboard: shutting down" in output


def test_watch_page_includes_all_api_dashboard_sections() -> None:
    page = api_budget._watch_page("runs/x.sqlite3", policy_id="default", run_id="run-a")

    assert "Policy / Kill Switch / Warnings / Last Update" in page
    assert "Run / Day / Month Budget Usage" in page
    assert "Active API Exposure" in page
    assert "All API Usage" in page
    assert "Recent Usage Events" in page
    assert "Provider Preflights" in page
    assert "Provider Transport Events" in page
    assert "Saved Authorizations / Execution Policies / Price Catalog Coverage" in page
    assert ".scroll-panel .table-wrap" in page
    assert '<div id="events" class="scroll-panel"></div>' in page
    assert '<div id="preflights" class="scroll-panel"></div>' in page
    assert '<div id="active-events" class="scroll-panel"></div>' in page
    assert "function renderActiveExposure" in page
    assert "payload.active_exposure" in page
    assert "const scrollTop = existingWrap ? existingWrap.scrollTop : 0;" in page
    assert "nextWrap.scrollTop = scrollTop;" in page
    assert "const POLL_INTERVAL_MS = 1000;" in page
    assert "const tableRenderKeys = {};" in page
    assert "const tableStates = {};" in page
    assert "function setHtmlIfChanged" in page
    assert "if (tableRenderKeys[targetId] === renderKey)" in page
    assert "state.rowNodes[rowKey]" in page
    assert "rowNode.innerHTML = cellHtml;" in page
    assert "pollTimer = setTimeout(poll, POLL_INTERVAL_MS);" in page
    assert 'document.addEventListener("visibilitychange"' in page
    assert 'timeZone: "Asia/Tokyo"' in page
    assert "Asia/Tokyo (UTC+9)" in page
    assert "setInterval(" not in page


def test_api_budget_request_hash_uses_payload_shape_not_secret_value() -> None:
    first = {"password": "alpha", "input": [{"text": "same"}]}
    second = {"password": "bravo", "input": [{"text": "same"}]}
    different_shape = {"password": "bravo", "input": [{"text": "same"}, {"text": "extra"}]}

    assert first["password"] != second["password"]
    assert api_budget._request_hash(first) == api_budget._request_hash(second)  # noqa: SLF001
    assert (
        api_budget._request_hash(second)  # noqa: SLF001
        != api_budget._request_hash(different_shape)  # noqa: SLF001
    )


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


def test_provider_quota_preflight_valid_approval_is_authorized_by_policy(
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

    assert report["status"] == "approved_smallest_limit"
    assert report["dry_run"] is True
    assert report["provider_call_allowed"] is True
    assert report["provider_requests_sent"] == 0
    assert report["provider_policy_status"] == "authorized_by_provider_policy"
    assert report["budget_guard"]["status"] == "passed"
    assert report["approval_contract"]["valid"] is True
    assert report["execution_policy_contract"]["valid"] is True
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
    assert payload["status"] == "approved_smallest_limit"
    assert payload["provider_requests_sent"] == 0
    assert payload["provider_call_allowed"] is True
    assert payload["provider_policy_status"] == "authorized_by_provider_policy"
    assert payload["approval_contract"]["valid"] is True
    assert payload["execution_policy_contract"]["valid"] is True


def test_provider_authorize_cli_records_policy(tmp_path: Path, capsys) -> None:
    db_path = tmp_path / "x.sqlite3"

    assert (
        main(
            [
                "memory",
                "api-budget",
                "authorize",
                "--db",
                str(db_path),
                "--authorization-id",
                "auth-openai-answer",
                "--provider",
                "openai",
                "--model",
                "gpt-test",
                "--operation",
                "answer",
                "--provider-role",
                "answer_engine",
                "--max-calls",
                "1",
                "--max-cost-usd",
                "0",
                "--approved-scope",
                "memory:answer",
                "--approval-source",
                "fixture://authorization-cli",
                "--storage-rights",
                "stored_for_user_research",
                "--rollback-scope",
                "delete_provider_outputs_and_usage_events",
                "--json",
            ]
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "authorized"
    assert payload["execution_policy"]["authorization_id"] == "auth-openai-answer"
    assert payload["execution_policy"]["storage_rights"] == "stored_for_user_research"
    assert (
        payload["execution_policy"]["rollback_scope"]
        == "delete_provider_outputs_and_usage_events"
    )

    status = api_budget_status(db_path)
    assert status["provider_execution_policies"][0]["policy_id"] == "approval:auth-openai-answer"


def test_provider_quota_preflight_cli_loads_saved_authorization(
    tmp_path: Path,
    capsys,
) -> None:
    db_path = tmp_path / "x.sqlite3"
    upsert_api_price(
        db_path,
        provider="gemini",
        model="gemini-embedding-2",
        operation="media_embedding",
        unit="call",
        usd_per_unit=0.0,
        source_url="fixture://saved-preflight-price",
    )
    _authorize_provider_policy_cli(
        capsys,
        db_path,
        authorization_id="auth-gemini-media-preflight",
        provider="gemini",
        model="gemini-embedding-2",
        operation="media_embedding",
        approved_scope="memory:build-media-embeddings",
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
                "--current-scope",
                "memory:build-media-embeddings",
                "--provider-authorization-id",
                "auth-gemini-media-preflight",
                "--json",
            ]
        )
        == 0
    )

    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "approved_smallest_limit"
    assert payload["authorization_loaded"] is True
    assert payload["execution_policy_loaded"] is True
    assert payload["price_known"] is True
    assert payload["unknown_price_action"] == "block"
    assert payload["scope_match"] is True
    assert payload["kill_switch"] is False
    assert payload["provider_requests_sent"] == 0
    assert payload["estimated_calls"] == 1
    assert payload["estimated_documents"] == 0
    assert payload["budget_guard"]["status"] == "passed"
    assert payload["approval_contract"]["valid"] is True
    assert payload["execution_policy_contract"]["valid"] is True


def test_provider_quota_preflight_cli_saved_authorization_missing_governance_fields_fails(
    tmp_path: Path,
    capsys,
) -> None:
    db_path = tmp_path / "x.sqlite3"
    upsert_api_price(
        db_path,
        provider="gemini",
        model="gemini-embedding-2",
        operation="media_embedding",
        unit="call",
        usd_per_unit=0.0,
        source_url="fixture://saved-preflight-price",
    )
    _authorize_provider_policy_cli(
        capsys,
        db_path,
        authorization_id="auth-gemini-media-missing-governance",
        provider="gemini",
        model="gemini-embedding-2",
        operation="media_embedding",
        approved_scope="memory:build-media-embeddings",
    )
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            UPDATE memory_provider_authorizations
            SET storage_rights = NULL, rollback_scope = NULL
            WHERE authorization_id = ?
            """,
            ("auth-gemini-media-missing-governance",),
        )
        conn.execute(
            """
            UPDATE memory_provider_execution_policies
            SET storage_rights = NULL, rollback_scope = NULL
            WHERE authorization_id = ?
            """,
            ("auth-gemini-media-missing-governance",),
        )
        conn.commit()

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
                "--current-scope",
                "memory:build-media-embeddings",
                "--provider-authorization-id",
                "auth-gemini-media-missing-governance",
                "--json",
            ]
        )
        == 0
    )

    payload = json.loads(capsys.readouterr().out)
    errors = "\n".join(payload["execution_policy_contract"]["errors"])
    assert payload["status"] == "execution_policy_required"
    assert payload["status"] != "approved_smallest_limit"
    assert payload["provider_call_allowed"] is False
    assert payload["provider_requests_sent"] == 0
    assert payload["authorization_loaded"] is True
    assert payload["execution_policy_loaded"] is True
    assert payload["approval_contract"]["valid"] is True
    assert payload["execution_policy_contract"]["valid"] is False
    assert "policy storage_rights is required for saved provider execution" in errors
    assert "policy rollback_scope is required for saved provider execution" in errors


def test_provider_quota_preflight_cli_saved_authorization_wrong_scope_and_cap_fails(
    tmp_path: Path,
    capsys,
) -> None:
    db_path = tmp_path / "x.sqlite3"
    upsert_api_price(
        db_path,
        provider="gemini",
        model="gemini-embedding-2",
        operation="media_embedding",
        unit="call",
        usd_per_unit=0.0,
        source_url="fixture://saved-preflight-price",
    )
    _authorize_provider_policy_cli(
        capsys,
        db_path,
        authorization_id="auth-gemini-media-scope-cap",
        provider="gemini",
        model="gemini-embedding-2",
        operation="media_embedding",
        approved_scope="memory:build-media-embeddings",
        max_calls=1,
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
                "--calls",
                "2",
                "--current-scope",
                "memory:other",
                "--provider-authorization-id",
                "auth-gemini-media-scope-cap",
                "--json",
            ]
        )
        == 0
    )

    payload = json.loads(capsys.readouterr().out)
    errors = "\n".join(
        [
            *payload["approval_contract"]["errors"],
            *payload["execution_policy_contract"]["errors"],
        ]
    )
    assert payload["status"] == "approval_required"
    assert payload["provider_call_allowed"] is False
    assert payload["authorization_loaded"] is True
    assert payload["execution_policy_loaded"] is True
    assert payload["scope_match"] is False
    assert payload["price_known"] is True
    assert payload["unknown_price_action"] == "block"
    assert payload["kill_switch"] is False
    assert payload["provider_requests_sent"] == 0
    assert payload["estimated_calls"] == 2
    assert payload["estimated_documents"] == 0
    assert "scope mismatch" in errors
    assert "planned calls exceed approval max_calls: 2 > 1" in errors
    assert "policy calls limit exceeded: 2 > 1" in errors


def test_provider_quota_preflight_cli_saved_authorization_missing_price_needs_evidence(
    tmp_path: Path,
    capsys,
) -> None:
    db_path = tmp_path / "x.sqlite3"
    _authorize_provider_policy_cli(
        capsys,
        db_path,
        authorization_id="auth-gemini-media-no-price",
        provider="gemini",
        model="gemini-embedding-2",
        operation="media_embedding",
        approved_scope="memory:build-media-embeddings",
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
                "--current-scope",
                "memory:build-media-embeddings",
                "--provider-authorization-id",
                "auth-gemini-media-no-price",
                "--json",
            ]
        )
        == 0
    )

    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "needs_price_evidence"
    assert payload["provider_call_allowed"] is False
    assert payload["authorization_loaded"] is True
    assert payload["execution_policy_loaded"] is True
    assert payload["price_known"] is False
    assert payload["unknown_price_action"] == "block"
    assert payload["scope_match"] is True
    assert payload["kill_switch"] is False
    assert payload["provider_requests_sent"] == 0
    assert payload["estimated_calls"] == 1
    assert payload["estimated_documents"] == 0
    assert payload["budget_guard"]["status"] == "needs_price_evidence"
    assert "price catalog missing" in payload["budget_guard"]["block_reason"]
    assert payload["approval_contract"]["valid"] is True
    assert payload["execution_policy_contract"]["valid"] is True


def test_provider_quota_preflight_cli_saved_policy_id_sends_zero_provider_requests(
    tmp_path: Path,
    capsys,
) -> None:
    db_path = tmp_path / "x.sqlite3"
    upsert_api_price(
        db_path,
        provider="gemini",
        model="gemini-embedding-2",
        operation="media_embedding",
        unit="call",
        usd_per_unit=0.0,
        source_url="fixture://saved-preflight-price",
    )
    _authorize_provider_policy_cli(
        capsys,
        db_path,
        authorization_id="auth-gemini-media-policy-id",
        provider="gemini",
        model="gemini-embedding-2",
        operation="media_embedding",
        approved_scope="memory:build-media-embeddings",
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
                "--current-scope",
                "memory:build-media-embeddings",
                "--provider-execution-policy-id",
                "approval:auth-gemini-media-policy-id",
                "--json",
            ]
        )
        == 0
    )

    payload = json.loads(capsys.readouterr().out)
    status = api_budget_status(db_path)
    assert payload["status"] == "approved_smallest_limit"
    assert payload["provider_requests_sent"] == 0
    assert payload["authorization_loaded"] is True
    assert payload["execution_policy_loaded"] is True
    assert payload["unknown_price_action"] == "block"
    assert payload["kill_switch"] is False
    assert payload["estimated_calls"] == 1
    assert payload["estimated_documents"] == 0
    assert status["recent_events"] == []
    assert status["recent_provider_transport_events"] == []
    assert status["recent_provider_preflights"][0]["provider_requests_sent"] == 0


def test_build_embeddings_cli_temp_quota_gate_passes_allow_provider_quota(
    monkeypatch,
    tmp_path: Path,
    capsys,
) -> None:
    db_path = tmp_path / "x.sqlite3"
    captured: dict[str, object] = {}
    from research_x.memory import embeddings as memory_embeddings

    def fake_build_memory_embeddings(db_path_arg: str, **kwargs):
        context = active_api_budget_context()
        captured["db_path"] = db_path_arg
        captured["allow_provider_quota"] = kwargs["allow_provider_quota"]
        captured["authorization_id"] = (
            context.provider_execution_policy.authorization_id
            if context and context.provider_execution_policy
            else None
        )
        return object()

    monkeypatch.setattr(memory_embeddings, "build_memory_embeddings", fake_build_memory_embeddings)
    monkeypatch.setattr(memory_embeddings, "summary_as_dict", lambda _summary: {"ok": True})

    assert (
        main(
            [
                "memory",
                "build-embeddings",
                "--db",
                str(db_path),
                "--provider",
                "gemini",
                "--model",
                "gemini-embedding-2",
                "--allow-provider-quota",
                "--provider-quota-approval-id",
                "tmp-gemini-embedding",
                "--provider-quota-provider",
                "gemini",
                "--provider-quota-model",
                "gemini-embedding-2",
                "--provider-quota-operation",
                "embedding",
                "--provider-quota-max-calls",
                "1",
                "--provider-quota-max-cost-usd",
                "0",
                "--provider-quota-price-source",
                "fixture://embedding-cli",
                "--provider-quota-approved-scope",
                "memory:build-embeddings",
                "--provider-quota-approved-at",
                "2026-07-08T00:00:00+00:00",
            ]
        )
        == 0
    )

    assert json.loads(capsys.readouterr().out) == {"ok": True}
    assert captured["db_path"] == str(db_path)
    assert captured["allow_provider_quota"] is True
    assert captured["authorization_id"] == "tmp-gemini-embedding"


def test_build_embeddings_cli_loads_saved_provider_policy(
    monkeypatch,
    tmp_path: Path,
    capsys,
) -> None:
    db_path = tmp_path / "x.sqlite3"
    _authorize_provider_policy_cli(
        capsys,
        db_path,
        authorization_id="auth-gemini-embedding",
        provider="gemini",
        model="gemini-embedding-2",
        operation="embedding",
        approved_scope="memory:build-embeddings",
    )
    captured: dict[str, object] = {}
    from research_x.memory import embeddings as memory_embeddings

    def fake_build_memory_embeddings(_db_path_arg: str, **kwargs):
        context = active_api_budget_context()
        captured["allow_provider_quota"] = kwargs["allow_provider_quota"]
        captured["provider_quota_approval"] = context.provider_quota_approval if context else None
        captured["authorization_id"] = (
            context.provider_execution_policy.authorization_id
            if context and context.provider_execution_policy
            else None
        )
        captured["policy_id"] = (
            context.provider_execution_policy.policy_id
            if context and context.provider_execution_policy
            else None
        )
        return object()

    monkeypatch.setattr(memory_embeddings, "build_memory_embeddings", fake_build_memory_embeddings)
    monkeypatch.setattr(memory_embeddings, "summary_as_dict", lambda _summary: {"ok": True})

    assert (
        main(
            [
                "memory",
                "build-embeddings",
                "--db",
                str(db_path),
                "--provider",
                "gemini",
                "--model",
                "gemini-embedding-2",
                "--allow-provider-quota",
                "--provider-authorization-id",
                "auth-gemini-embedding",
            ]
        )
        == 0
    )

    assert json.loads(capsys.readouterr().out) == {"ok": True}
    assert captured["allow_provider_quota"] is True
    assert captured["provider_quota_approval"] is None
    assert captured["authorization_id"] == "auth-gemini-embedding"
    assert captured["policy_id"] == "approval:auth-gemini-embedding"


def test_build_embeddings_cli_api_run_id_does_not_override_provider_scope(
    monkeypatch,
    tmp_path: Path,
    capsys,
) -> None:
    db_path = tmp_path / "x.sqlite3"
    _authorize_provider_policy_cli(
        capsys,
        db_path,
        authorization_id="auth-gemini-embedding-run-id",
        provider="gemini",
        model="gemini-embedding-2",
        operation="embedding",
        approved_scope="memory:build-embeddings",
    )
    captured: dict[str, object] = {}
    from research_x.memory import embeddings as memory_embeddings

    def fake_build_memory_embeddings(_db_path_arg: str, **kwargs):
        context = active_api_budget_context()
        assert context is not None
        memory_embeddings.require_embedding_provider_quota_allowed(
            "gemini",
            allow_provider_quota=kwargs["allow_provider_quota"],
            model="gemini-embedding-2",
        )
        captured["run_id"] = context.run_id
        captured["provider_quota_current_scope"] = context.provider_quota_current_scope
        return object()

    monkeypatch.setattr(memory_embeddings, "build_memory_embeddings", fake_build_memory_embeddings)
    monkeypatch.setattr(memory_embeddings, "summary_as_dict", lambda _summary: {"ok": True})

    assert (
        main(
            [
                "memory",
                "build-embeddings",
                "--db",
                str(db_path),
                "--provider",
                "gemini",
                "--model",
                "gemini-embedding-2",
                "--limit",
                "100",
                "--api-run-id",
                "embedding-limit100-test",
                "--allow-provider-quota",
                "--provider-authorization-id",
                "auth-gemini-embedding-run-id",
            ]
        )
        == 0
    )

    assert json.loads(capsys.readouterr().out) == {"ok": True}
    assert captured["run_id"] == "embedding-limit100-test"
    assert captured["provider_quota_current_scope"] == "memory:build-embeddings"


def test_build_embeddings_cli_loads_saved_provider_policy_by_policy_id(
    monkeypatch,
    tmp_path: Path,
    capsys,
) -> None:
    db_path = tmp_path / "x.sqlite3"
    _authorize_provider_policy_cli(
        capsys,
        db_path,
        authorization_id="auth-gemini-embedding-policy-id",
        provider="gemini",
        model="gemini-embedding-2",
        operation="embedding",
        approved_scope="memory:build-embeddings",
    )
    captured: dict[str, object] = {}
    from research_x.memory import embeddings as memory_embeddings

    def fake_build_memory_embeddings(_db_path_arg: str, **kwargs):
        context = active_api_budget_context()
        captured["allow_provider_quota"] = kwargs["allow_provider_quota"]
        captured["provider_quota_approval"] = context.provider_quota_approval if context else None
        captured["authorization_id"] = (
            context.provider_execution_policy.authorization_id
            if context and context.provider_execution_policy
            else None
        )
        captured["policy_id"] = (
            context.provider_execution_policy.policy_id
            if context and context.provider_execution_policy
            else None
        )
        return object()

    monkeypatch.setattr(memory_embeddings, "build_memory_embeddings", fake_build_memory_embeddings)
    monkeypatch.setattr(memory_embeddings, "summary_as_dict", lambda _summary: {"ok": True})

    assert (
        main(
            [
                "memory",
                "build-embeddings",
                "--db",
                str(db_path),
                "--provider",
                "gemini",
                "--model",
                "gemini-embedding-2",
                "--allow-provider-quota",
                "--provider-execution-policy-id",
                "approval:auth-gemini-embedding-policy-id",
            ]
        )
        == 0
    )

    assert json.loads(capsys.readouterr().out) == {"ok": True}
    assert captured["allow_provider_quota"] is True
    assert captured["provider_quota_approval"] is None
    assert captured["authorization_id"] == "auth-gemini-embedding-policy-id"
    assert captured["policy_id"] == "approval:auth-gemini-embedding-policy-id"


def test_build_embeddings_cli_without_provider_policy_blocks_before_http(
    monkeypatch,
    tmp_path: Path,
    capsys,
) -> None:
    db_path = tmp_path / "x.sqlite3"
    from research_x.memory import embeddings as memory_embeddings

    def fail_build_memory_embeddings(*_args, **_kwargs):
        raise AssertionError("provider embedding build should not start without policy")

    def fail_post_json(*_args, **_kwargs):
        raise AssertionError("provider HTTP should not be attempted without policy")

    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setattr(memory_embeddings, "build_memory_embeddings", fail_build_memory_embeddings)
    monkeypatch.setattr(memory_embeddings, "_post_json", fail_post_json)

    assert (
        main(
            [
                "memory",
                "build-embeddings",
                "--db",
                str(db_path),
                "--provider",
                "gemini",
                "--model",
                "gemini-embedding-2",
                "--allow-provider-quota",
            ]
        )
        == 1
    )

    blocked_output = capsys.readouterr()
    assert "provider quota approval missing fields" in blocked_output.err


def test_build_ocr_evidence_cli_allow_real_api_loads_saved_provider_policy(
    monkeypatch,
    tmp_path: Path,
    capsys,
) -> None:
    db_path = tmp_path / "x.sqlite3"
    _authorize_provider_policy_cli(
        capsys,
        db_path,
        authorization_id="auth-mistral-ocr",
        provider="mistral",
        model="mistral-ocr-2512",
        operation="ocr",
        approved_scope="memory:build-ocr-evidence",
    )
    captured: dict[str, object] = {}
    from research_x.memory import ocr as memory_ocr

    def fake_build_ocr_evidence(_db_path_arg: str, **kwargs):
        context = active_api_budget_context()
        captured["allow_provider_quota"] = kwargs["allow_provider_quota"]
        captured["authorization_id"] = (
            context.provider_execution_policy.authorization_id
            if context and context.provider_execution_policy
            else None
        )
        return object()

    monkeypatch.setattr(memory_ocr, "build_ocr_evidence", fake_build_ocr_evidence)
    monkeypatch.setattr(memory_ocr, "summary_json", lambda _summary: json.dumps({"ok": True}))
    monkeypatch.setattr(memory_ocr, "format_summary", lambda _summary: "ok")

    assert (
        main(
            [
                "memory",
                "build-ocr-evidence",
                "--db",
                str(db_path),
                "--provider",
                "mistral",
                "--model",
                "mistral-ocr-2512",
                "--allow-real-api",
                "--provider-authorization-id",
                "auth-mistral-ocr",
                "--json",
            ]
        )
        == 0
    )

    assert json.loads(capsys.readouterr().out) == {"ok": True}
    assert captured["allow_provider_quota"] is True
    assert captured["authorization_id"] == "auth-mistral-ocr"


def _authorize_provider_policy_cli(
    capsys,
    db_path: Path,
    *,
    authorization_id: str,
    provider: str,
    model: str,
    operation: str,
    approved_scope: str,
    max_calls: int = 1,
    max_cost_usd: float = 0.0,
    storage_rights: str = "stored_for_user_research",
    rollback_scope: str = "delete_provider_outputs_and_usage_events",
) -> None:
    assert (
        main(
            [
                "memory",
                "api-budget",
                "authorize",
                "--db",
                str(db_path),
                "--authorization-id",
                authorization_id,
                "--provider",
                provider,
                "--model",
                model,
                "--operation",
                operation,
                "--max-calls",
                str(max_calls),
                "--max-cost-usd",
                str(max_cost_usd),
                "--approved-scope",
                approved_scope,
                "--approval-source",
                "fixture://saved-policy-cli",
                "--storage-rights",
                storage_rights,
                "--rollback-scope",
                rollback_scope,
                "--json",
            ]
        )
        == 0
    )
    capsys.readouterr()


def _provider_quota_approval(
    *,
    approval_id: str = "fixture-approval",
    provider: str = "gemini",
    model: str = "gemini-embedding-2",
    operation: str = "media_embedding",
    max_calls: int = 1,
    max_cost_usd: float = 0.0,
    price_source: str = "fixture://provider-quota-preflight",
    approved_scope: str = "memory:build-media-embeddings",
) -> dict[str, object]:
    return {
        "provider_quota_approval_id": approval_id,
        "provider": provider,
        "model": model,
        "operation": operation,
        "max_calls": max_calls,
        "max_cost_usd": max_cost_usd,
        "price_source": price_source,
        "approved_scope": approved_scope,
        "approved_at": "2026-06-27T00:00:00+00:00",
    }


def _seed_zero_api_prices(
    db_path: Path,
    *,
    provider: str,
    model: str,
    operation: str,
) -> None:
    for unit in ("call", "input_token", "output_token", "media_byte", "document", "page"):
        upsert_api_price(
            db_path,
            provider=provider,
            model=model,
            operation=operation,
            unit=unit,
            usd_per_unit=0.0,
            source_url="fixture://zero-price",
        )
