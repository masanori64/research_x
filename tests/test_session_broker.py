import json

from research_x.session_broker import SessionBroker


def test_session_broker_materializes_cookie_files(tmp_path) -> None:
    storage_state = tmp_path / "state.json"
    storage_state.write_text(
        json.dumps(
            {
                "cookies": [
                    {"name": "auth_token", "value": "a", "domain": ".x.com"},
                    {"name": "ct0", "value": "c", "domain": ".x.com"},
                ]
            }
        ),
        encoding="utf-8",
    )

    artifacts = SessionBroker(
        storage_state=storage_state,
        twikit_cookies_file=tmp_path / "twikit.json",
        scweet_cookies_file=tmp_path / "scweet.json",
        masa_cookies_file=tmp_path / "masa.json",
    ).materialize()

    assert artifacts.has_session is True
    assert artifacts.cookie_names == ("auth_token", "ct0")
    assert json.loads((tmp_path / "twikit.json").read_text(encoding="utf-8")) == {
        "auth_token": "a",
        "ct0": "c",
    }
    masa = json.loads((tmp_path / "masa.json").read_text(encoding="utf-8"))
    assert masa[0]["Name"] == "auth_token"


def test_session_broker_without_state_reports_missing(tmp_path) -> None:
    artifacts = SessionBroker(storage_state=tmp_path / "missing.json").materialize()

    assert artifacts.has_session is False
    assert artifacts.cookie_names == ()
