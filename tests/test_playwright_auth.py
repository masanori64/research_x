import asyncio
import json

import pytest

import research_x.playwright_auth as auth
from research_x.cli import main
from research_x.playwright_auth import (
    _totp_code,
    capture_storage_state_auto,
    capture_storage_state_from_cdp,
    capture_storage_state_with_credentials,
    storage_state_has_x_auth_cookies,
    write_storage_state_from_cookie_env,
)


def test_cli_cdp_no_defaults_is_a_single_boolean_flag(tmp_path, monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_capture_storage_state_from_cdp(**kwargs: object) -> bool:
        captured.update(kwargs)
        return True

    monkeypatch.setattr(
        "research_x.cli.capture_storage_state_from_cdp",
        fake_capture_storage_state_from_cdp,
    )

    assert (
        main(
            [
                "auth",
                "cdp",
                "--storage-state",
                str(tmp_path / "state.json"),
                "--no-defaults",
                "--timeout-seconds",
                "1",
            ]
        )
        == 0
    )
    assert captured["no_defaults"] is True


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


def test_storage_state_has_x_auth_cookies_rejects_empty_or_expired(tmp_path) -> None:
    path = tmp_path / "state.json"
    path.write_text(
        json.dumps(
            {
                "cookies": [
                    {"name": "auth_token", "value": "", "domain": ".x.com"},
                    {"name": "ct0", "value": "c", "domain": ".x.com", "expires": 1},
                ]
            }
        ),
        encoding="utf-8",
    )

    assert not storage_state_has_x_auth_cookies(path)


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


def test_auto_auth_can_use_standard_system_profile(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("RESEARCH_X_X_USERNAME", "screen_name")
    monkeypatch.setenv("RESEARCH_X_X_PASSWORD", "password")
    calls = []

    def fake_system_profile(**kwargs) -> bool:
        calls.append(("system_profile", kwargs["profile_directory"]))
        return True

    def fake_system_browser(**kwargs) -> bool:
        raise AssertionError("custom system browser login should not run after profile succeeds")

    monkeypatch.setattr(
        auth,
        "capture_storage_state_from_system_browser_profile",
        fake_system_profile,
    )
    monkeypatch.setattr(
        auth,
        "capture_storage_state_with_system_browser_credentials",
        fake_system_browser,
    )

    assert auth.capture_storage_state_auto(
        storage_state=tmp_path / "state.json",
        user_data_dir=tmp_path / "missing-profile",
        try_cdp=False,
        try_system_browser_profile=True,
        system_browser_profile_directory="Default",
    )
    assert calls == [("system_profile", "Default")]


def test_system_profile_launch_omits_user_data_dir_and_uses_daily_browser_cdp(
    tmp_path,
    monkeypatch,
) -> None:
    popen_calls = []
    poll_calls = []

    class Process:
        pass

    def fake_popen(args):
        popen_calls.append(args)
        return Process()

    async def fake_poll(**kwargs) -> bool:
        poll_calls.append(kwargs)
        return True

    monkeypatch.setattr(auth.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(auth, "_poll_storage_state_from_cdp", fake_poll)

    assert auth.capture_storage_state_from_system_browser_profile(
        storage_state=tmp_path / "state.json",
        executable_path=tmp_path / "msedge.exe",
        profile_directory="Profile 1",
        debugging_port=9333,
    )

    assert not any(arg.startswith("--user-data-dir") for arg in popen_calls[0])
    assert "--profile-directory=Profile 1" in popen_calls[0]
    assert poll_calls == [
        {
            "storage_state": tmp_path / "state.json",
            "endpoint_url": "http://127.0.0.1:9333",
            "timeout_seconds": 30,
            "no_defaults": True,
        }
    ]


def test_password_submit_accepts_continue_button(monkeypatch) -> None:
    calls = []

    async def fake_click_named_button(_page, patterns) -> None:
        calls.append(patterns)

    async def fake_has_visible_locator(_page, _selectors) -> bool:
        return False

    async def fake_needs_verification_code(_page) -> bool:
        return False

    class Keyboard:
        async def press(self, key: str) -> None:
            calls.append(("press", key))

    class Page:
        keyboard = Keyboard()

        async def wait_for_timeout(self, _milliseconds: int) -> None:
            return None

    monkeypatch.setattr(auth, "_click_named_button", fake_click_named_button)
    monkeypatch.setattr(auth, "_has_visible_locator", fake_has_visible_locator)
    monkeypatch.setattr(auth, "_needs_verification_code", fake_needs_verification_code)

    asyncio.run(auth._submit_password_and_wait(Page()))

    assert any(pattern.startswith("^(Continue") for pattern in calls[0])


def test_totp_code_uses_rfc_6238_vector() -> None:
    secret = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"

    assert _totp_code(secret, timestamp=59) == "287082"


@pytest.mark.parametrize(
    "url",
    [
        "https://x.com/i/flow/login",
        "https://mobile.twitter.com/home",
        "https://subdomain.x.com/path",
        "https://twitter.com./home",
    ],
)
def test_x_hostname_url_accepts_x_hosts(url: str) -> None:
    assert auth._is_x_hostname_url(url)


@pytest.mark.parametrize(
    "url",
    [
        "https://x.com.evil.example/home",
        "https://example.com/redirect?next=https://x.com",
        "https://twitter.com.attacker.test",
        "about:blank",
    ],
)
def test_x_hostname_url_rejects_substring_spoofing(url: str) -> None:
    assert not auth._is_x_hostname_url(url)


def test_cdp_requires_running_browser(tmp_path) -> None:
    assert not capture_storage_state_from_cdp(
        storage_state=tmp_path / "state.json",
        endpoint_url="http://127.0.0.1:1",
        timeout_seconds=0.01,
    )
