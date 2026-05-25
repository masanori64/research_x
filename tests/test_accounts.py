import json

from research_x.accounts import normalize_account_id, resolve_account_paths, write_account_profile


def test_account_paths_are_scoped_by_account() -> None:
    paths = resolve_account_paths("@SampleUser")

    assert paths.account_id == "sampleuser"
    assert paths.storage_state.parts[-3:] == (
        "accounts",
        "sampleuser",
        "playwright_x_state.json",
    )
    assert paths.twikit_cookies_file.parts[-3:] == (
        "accounts",
        "sampleuser",
        "twikit_cookies.json",
    )


def test_account_profile_does_not_store_password(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    profile = write_account_profile(
        account="@sampleuser",
        user_id="1234567890",
        display_name="sample",
    )

    payload = json.loads(
        (tmp_path / ".secrets" / "accounts" / "sampleuser" / "account.json").read_text(
            encoding="utf-8"
        )
    )
    assert profile.account_id == "sampleuser"
    assert payload["user_id"] == "1234567890"
    assert "password" not in payload


def test_normalize_account_id_rejects_empty() -> None:
    try:
        normalize_account_id("@@@")
    except ValueError as exc:
        assert "account" in str(exc)
    else:
        raise AssertionError("expected ValueError")
