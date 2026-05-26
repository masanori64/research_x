import json

import pytest

import research_x.playwright_auth as auth
from research_x.playwright_auth import (
    _totp_code,
    capture_storage_state_auto,
    capture_storage_state_from_cdp,
    capture_storage_state_with_credentials,
    storage_state_has_x_auth_cookies,
    write_storage_state_from_cookie_env,
)


def test_write_storage_state_from_cookie_env(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("RESEARCH_X_X_AUTH_TOKEN", "auth-token-value")
    monkeypatch.setenv("RESEARCH_X_X_CT0", "ct0-value")
    path = tmp_path / "state.json"

    assert write_storage_state_from_cookie_env(storage_state=path)

    payload = json.loads(path.read_text(encoding="utf-8"))
    cookies = {cookie["name"]: cookie for cookie in payload["cookies"]}
    assert cookies["auth_token"]["value"] == "auth-token-value"
    assert cookies["ct0"]["value"] == "ct0-value"
    assert cookies["auth_token"]["domain"] == ".x.com"


def test_cookie_env_missing_values_raise(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("RESEARCH_X_X_AUTH_TOKEN", raising=False)
    monkeypatch.delenv("RESEARCH_X_X_CT0", raising=False)

    with pytest.raises(RuntimeError, match="RESEARCH_X_X_AUTH_TOKEN"):
        write_storage_state_from_cookie_env(storage_state=tmp_path / "state.json")


def test_storage_state_has_x_auth_cookies(tmp_path) -> None:
    path = tmp_path / "state.json"
    path.write_text(
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

    assert storage_state_has_x_auth_cookies(path)


def test_credentials_auth_requires_env_values(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("RESEARCH_X_X_USERNAME", raising=False)
    monkeypatch.delenv("RESEARCH_X_X_PASSWORD", raising=False)

    with pytest.raises(RuntimeError, match="RESEARCH_X_X_USERNAME"):
        capture_storage_state_with_credentials(storage_state=tmp_path / "state.json")


def test_auto_auth_uses_cookie_env(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("RESEARCH_X_X_AUTH_TOKEN", "auth-token-value")
    monkeypatch.setenv("RESEARCH_X_X_CT0", "ct0-value")

    assert capture_storage_state_auto(
        storage_state=tmp_path / "state.json",
        try_cdp=False,
    )
    assert storage_state_has_x_auth_cookies(tmp_path / "state.json")


def test_auto_auth_prefers_system_browser_before_headless_credentials(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setenv("RESEARCH_X_X_USERNAME", "screen_name")
    monkeypatch.setenv("RESEARCH_X_X_PASSWORD", "password")
    calls = []

    def fake_system_browser(**kwargs) -> bool:
        calls.append("system_browser")
        return True

    def fake_credentials(**kwargs) -> bool:
        raise AssertionError("headless credentials should not run first")

    monkeypatch.setattr(
        auth,
        "capture_storage_state_with_system_browser_credentials",
        fake_system_browser,
    )
    monkeypatch.setattr(auth, "capture_storage_state_with_credentials", fake_credentials)

    assert auth.capture_storage_state_auto(
        storage_state=tmp_path / "state.json",
        user_data_dir=tmp_path / "missing-profile",
        try_cdp=False,
    )
    assert calls == ["system_browser"]


def test_totp_code_uses_rfc_6238_vector() -> None:
    secret = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"

    assert _totp_code(secret, timestamp=59) == "287082"


def test_cdp_requires_running_browser(tmp_path) -> None:
    assert not capture_storage_state_from_cdp(
        storage_state=tmp_path / "state.json",
        endpoint_url="http://127.0.0.1:1",
        timeout_seconds=0.01,
    )
