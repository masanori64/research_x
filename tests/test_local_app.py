import json
import sqlite3
from pathlib import Path
from types import SimpleNamespace

from research_x import local_app
from research_x.cli import main
from research_x.contracts import OutcomeStatus
from research_x.memory.schema import ensure_memory_schema


class InterruptingServer:
    def __init__(self, _address, _handler_cls) -> None:
        self.closed = False

    def serve_forever(self) -> None:
        raise KeyboardInterrupt()

    def server_close(self) -> None:
        self.closed = True


def test_app_keyboard_interrupt_closes_server_and_returns_zero(monkeypatch, capsys) -> None:
    servers = []

    def fake_server(address, handler_cls):
        server = InterruptingServer(address, handler_cls)
        servers.append(server)
        return server

    monkeypatch.setattr(local_app, "ThreadingHTTPServer", fake_server)

    assert main(["app", "--host", "127.0.0.1", "--port", "0", "--no-open-browser"]) == 0
    assert servers[0].closed is True

    output = capsys.readouterr()
    assert "research_x app: shutting down" in output.out
    assert "Traceback" not in output.err
    assert "KeyboardInterrupt" not in output.err


def test_app_reuses_existing_storage_state_without_auth(monkeypatch, tmp_path) -> None:
    app = local_app.CollectionApp()
    job = local_app.AppJob(
        job_id="job",
        account_id="tpq9e",
        out_dir=tmp_path / "out",
        db_path=tmp_path / "x.sqlite3",
    )
    paths = SimpleNamespace(
        storage_state=tmp_path / "state.json",
        user_data_dir=tmp_path / "profile",
    )

    monkeypatch.setattr(local_app, "write_account_profile", lambda **_kwargs: None)
    monkeypatch.setattr(local_app, "resolve_account_paths", lambda _account: paths)
    monkeypatch.setattr(local_app, "storage_state_has_x_auth_cookies", lambda _path: True)

    def fail_auth(**_kwargs):
        raise AssertionError("auth should not run when storage_state already has X cookies")

    def fake_bookmarks(**_kwargs):
        result = SimpleNamespace(
            status=OutcomeStatus.OK,
            items=(),
            providers_used=("twscrape_raw",),
        )
        classification = SimpleNamespace(status="disabled")
        return result, classification

    monkeypatch.setattr(local_app, "capture_storage_state_auto", fail_auth)
    monkeypatch.setattr(local_app, "run_bookmark_job", fake_bookmarks)

    app._run_job(
        job,
        {
            "account": "tpq9e",
            "screen_name": "tpq9e",
            "use_standard_browser_profile": "on",
            "close_existing_browser": "on",
            "limit": "1",
        },
    )

    assert job.status == "done"
    assert any("storage_state" in line for line in job.logs)


def test_app_can_restore_db_to_start_snapshot(tmp_path) -> None:
    db_path = tmp_path / "x.sqlite3"
    with sqlite3.connect(db_path) as conn:
        conn.execute("CREATE TABLE rows (value TEXT)")
        conn.execute("INSERT INTO rows VALUES ('before')")

    app = local_app.CollectionApp()
    job = local_app.AppJob(
        job_id="job",
        account_id="acct",
        out_dir=tmp_path / "out",
        db_path=db_path,
        status="done",
    )
    app.jobs[job.job_id] = job
    app._prepare_db_backup(job)

    with sqlite3.connect(db_path) as conn:
        conn.execute("DELETE FROM rows")
        conn.execute("INSERT INTO rows VALUES ('after')")

    app.rollback_job(job.job_id)

    with sqlite3.connect(db_path) as conn:
        rows = conn.execute("SELECT value FROM rows").fetchall()

    assert rows == [("before",)]
    assert job.status == "rolled_back"
    assert job.rollback_applied is True


def test_app_cancel_with_rollback_marks_running_job(tmp_path) -> None:
    app = local_app.CollectionApp()
    job = local_app.AppJob(
        job_id="job",
        account_id="acct",
        out_dir=tmp_path / "out",
        db_path=tmp_path / "x.sqlite3",
        status="labeling",
    )
    app.jobs[job.job_id] = job

    app.request_cancel(job.job_id, rollback=True)

    assert job.status == "canceling"
    assert job.cancel_requested is True
    assert job.rollback_requested is True


def test_app_research_run_pages_surface_gap_and_citation_state(tmp_path) -> None:
    db_path = tmp_path / "x.sqlite3"
    with sqlite3.connect(db_path) as conn:
        ensure_memory_schema(conn)
        conn.execute(
            """
            INSERT INTO memory_objective_route_runs (
                route_run_id, query, objective_route_version, eval_question_type,
                primary_route, fallback_routes_json, must_run_guards_json,
                escalation_triggers_json, stop_conditions_json, budget_policy,
                planned_provider_roles_json, selected_routes_json, stop_reason, status,
                created_at, updated_at, metadata_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "run-app",
                "find source",
                "objective-route-v1",
                "known_item",
                "exact_metadata",
                "[]",
                "[]",
                "[]",
                "[]",
                "default",
                "[]",
                '["exact_metadata"]',
                "needs_review",
                "needs_review",
                "2026-06-08T00:00:00+00:00",
                "2026-06-08T00:00:01+00:00",
                json.dumps(
                    {
                        "metadata": {
                            "research_brief": {
                                "evidence_total": 0,
                                "citation_total": 0,
                                "gap_count": 1,
                                "claim_support_status": "insufficient_evidence",
                            },
                            "research_task_frame": {
                                "objective_type": "known_item",
                                "local_x_db_primary": True,
                                "primary_goal": "find a saved source",
                            },
                            "search_plan_graph": {
                                "nodes": [
                                    {
                                        "route_arm": "exact_metadata",
                                        "provider_roles": ["index_provider"],
                                        "quota_policy": "local_or_fake_only",
                                    }
                                ],
                                "query_variants": [
                                    {
                                        "variant_id": "original_query",
                                        "citation_excluded": True,
                                    }
                                ],
                                "contract": "plan_graph_controls_search_but_is_not_evidence",
                            },
                            "provider_capability_matrix": {
                                "rows": [
                                    {
                                        "provider": "serper",
                                        "provider_role": "index_provider",
                                        "status": "gated",
                                    }
                                ],
                                "contract": (
                                    "provider_output_role_must_match_allowed_evidence_policy"
                                ),
                            },
                            "personalization_policy": {
                                "mode": "weak_ranking_hint",
                                "always_on_personal_boost": False,
                                "disallowed_uses": ["citation", "fact_claim"],
                            },
                            "user_signal_policy": {
                                "route_scope": "exact_metadata",
                                "evidence_status": "ranking_hint_not_evidence",
                            },
                            "result_coverage_map": {
                                "executed_routes": ["exact_metadata"],
                                "evidence_total": 0,
                                "citation_total": 0,
                                "provider_quota_skipped_routes": [],
                            },
                            "search_episode_trace": {
                                "events": [
                                    {
                                        "step_index": 0,
                                        "route_arm": "exact_metadata",
                                        "status": "needs_review",
                                    }
                                ],
                                "stop_reason": "needs_review",
                                "contract": (
                                    "episode_trace_explains_execution_but_is_not_source_evidence"
                                ),
                            },
                            "reader_quality_profile": {
                                "status": "not_requested",
                                "external_route_count": 0,
                                "discovered_url_count": 0,
                            },
                            "evidence_gap": {
                                "gaps": [
                                    {
                                        "gap_id": "no_context_chunk",
                                        "message": "context chunk missing",
                                    }
                                ]
                            },
                            "serp_flattening_audit": {
                                "status": "ok",
                                "checks": {
                                    "rank_used_as_evidence": False,
                                    "snippet_used_as_evidence": False,
                                },
                            },
                            "source_quality_signals": [
                                {
                                    "source_kind": "local_x_db",
                                    "quality_class": "primary_saved_record",
                                    "evidence_status": "fact",
                                }
                            ],
                            "claim_support_check": {
                                "status": "insufficient_evidence",
                                "citation_count": 0,
                                "evidence_count": 0,
                            },
                        }
                    },
                    ensure_ascii=False,
                ),
            ),
        )
        conn.execute(
            """
            INSERT INTO memory_objective_route_steps (
                route_step_id, route_run_id, step_index, route_arm, status,
                evidence_count, citation_count, stop_condition, escalation_trigger,
                provider_quota_skipped, output_json, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "step-app",
                "run-app",
                0,
                "exact_metadata",
                "needs_review",
                0,
                0,
                "no_context_chunk",
                None,
                0,
                "{}",
                "2026-06-08T00:00:01+00:00",
            ),
        )

    list_page = local_app._research_runs_page(db=str(db_path), kind="objective", limit=5)
    detail_page = local_app._research_run_page(db=str(db_path), run_id="run-app", kind="auto")

    assert "run-app" in list_page
    assert "/research-run?" in list_page
    assert "research_task_frame:" in detail_page
    assert "search_plan_graph:" in detail_page
    assert "provider_capability_matrix:" in detail_page
    assert "personalization_policy:" in detail_page
    assert "user_signal_policy:" in detail_page
    assert "result_coverage:" in detail_page
    assert "search_episode_trace:" in detail_page
    assert "reader_quality_profile:" in detail_page
    assert "research_brief:" in detail_page
    assert "evidence_gaps:" in detail_page
    assert "serp_flattening:" in detail_page
    assert "source_quality:" in detail_page
    assert "claim_support:" in detail_page


def test_local_app_http_db_path_is_restricted_to_runs() -> None:
    assert (
        local_app._safe_local_app_db_path("runs/x_data.sqlite3")  # noqa: SLF001
        == Path("runs/x_data.sqlite3")
    )
    assert (
        local_app._safe_local_app_db_path("runs/nested/custom.db")  # noqa: SLF001
        == Path("runs/nested/custom.db")
    )
    assert (
        local_app._safe_local_app_db_path("../secret.sqlite3")  # noqa: SLF001
        == Path(local_app.DEFAULT_DB_PATH)
    )
    assert (
        local_app._safe_local_app_db_path("C:/Users/maasa/secret.sqlite3")  # noqa: SLF001
        == Path(local_app.DEFAULT_DB_PATH)
    )
    assert (
        local_app._safe_local_app_db_path("docs/control.json")  # noqa: SLF001
        == Path(local_app.DEFAULT_DB_PATH)
    )


def test_local_app_redirect_job_id_rejects_header_breaks() -> None:
    assert local_app._safe_redirect_job_id("job_123-ABC") == "job_123-ABC"  # noqa: SLF001
    assert local_app._safe_redirect_job_id("job\r\nX-Test: injected") == ""  # noqa: SLF001
    assert local_app._safe_redirect_job_id("../job") == ""  # noqa: SLF001


def test_local_app_status_location_urlencodes_server_job_id(tmp_path: Path) -> None:
    job = local_app.AppJob(
        job_id="job\r\nX-Test: injected",
        account_id="tpq9e",
        out_dir=tmp_path / "out",
        db_path=tmp_path / "x.sqlite3",
    )

    location = local_app._status_location_for_job(job)  # noqa: SLF001

    assert "\r" not in location
    assert "\n" not in location
    assert location == "/status?job=job%0D%0AX-Test%3A+injected"
