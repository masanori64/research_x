import json

from research_x.cookies import (
    cookie_header,
    load_cookie_dict_from_playwright_state,
    require_x_session_cookies,
    write_cookie_dict,
)


def test_load_cookie_dict_from_playwright_state(tmp_path) -> None:
    state_path = tmp_path / "state.json"
    state_path.write_text(
        json.dumps(
            {
                "cookies": [
                    {"name": "auth_token", "value": "a", "domain": ".x.com"},
                    {"name": "ct0", "value": "c", "domain": ".x.com"},
                    {"name": "ignored", "value": "z", "domain": ".example.com"},
                ]
            }
        ),
        encoding="utf-8",
    )

    cookies = load_cookie_dict_from_playwright_state(state_path)

    assert cookies == {"auth_token": "a", "ct0": "c"}
    require_x_session_cookies(cookies)
    assert cookie_header(cookies) == "auth_token=a; ct0=c"


def test_write_cookie_dict(tmp_path) -> None:
    path = tmp_path / "cookies.json"

    write_cookie_dict(path, {"ct0": "c", "auth_token": "a"})

    assert json.loads(path.read_text(encoding="utf-8")) == {"auth_token": "a", "ct0": "c"}
