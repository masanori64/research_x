import sqlite3
from types import SimpleNamespace

from research_x import local_app
from research_x.cli import main
from research_x.contracts import OutcomeStatus


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
