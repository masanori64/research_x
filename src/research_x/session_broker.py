from __future__ import annotations

import json
from pathlib import Path

from research_x.cookies import (
    load_cookie_dict_from_playwright_state,
    require_x_session_cookies,
    write_cookie_dict,
)
from research_x.pipeline_contracts import SessionArtifacts


class SessionBroker:
    def __init__(
        self,
        *,
        storage_state: str | Path = ".secrets/playwright_x_state.json",
        twikit_cookies_file: str | Path = ".secrets/twikit_cookies.json",
        scweet_cookies_file: str | Path = ".secrets/scweet_cookies.json",
        masa_cookies_file: str | Path = ".secrets/masa_cookies.json",
        twscrape_accounts_db: str | Path = ".secrets/twscrape_accounts.db",
    ) -> None:
        self.storage_state = Path(storage_state)
        self.twikit_cookies_file = Path(twikit_cookies_file)
        self.scweet_cookies_file = Path(scweet_cookies_file)
        self.masa_cookies_file = Path(masa_cookies_file)
        self.twscrape_accounts_db = Path(twscrape_accounts_db)

    def materialize(self) -> SessionArtifacts:
        if not self.storage_state.exists():
            return SessionArtifacts(
                storage_state=self.storage_state,
                twikit_cookies_file=self.twikit_cookies_file,
                scweet_cookies_file=self.scweet_cookies_file,
                masa_cookies_file=self.masa_cookies_file,
                has_session=False,
                twscrape_accounts_db=self.twscrape_accounts_db,
            )

        cookies = load_cookie_dict_from_playwright_state(self.storage_state)
        require_x_session_cookies(cookies)
        write_cookie_dict(self.twikit_cookies_file, cookies)
        write_cookie_dict(self.scweet_cookies_file, cookies)
        self._write_masa_cookies(cookies)
        return SessionArtifacts(
            storage_state=self.storage_state,
            twikit_cookies_file=self.twikit_cookies_file,
            scweet_cookies_file=self.scweet_cookies_file,
            masa_cookies_file=self.masa_cookies_file,
            has_session=True,
            cookie_names=tuple(sorted(cookies)),
            twscrape_accounts_db=self.twscrape_accounts_db,
        )

    def _write_masa_cookies(self, cookies: dict[str, str]) -> None:
        payload = [
            {
                "Name": name,
                "Value": value,
                "Domain": ".x.com",
                "Path": "/",
                "Secure": True,
                "HttpOnly": name == "auth_token",
            }
            for name, value in sorted(cookies.items())
        ]
        self.masa_cookies_file.parent.mkdir(parents=True, exist_ok=True)
        self.masa_cookies_file.write_text(
            json.dumps(payload, indent=2, sort_keys=True),
            encoding="utf-8",
        )
