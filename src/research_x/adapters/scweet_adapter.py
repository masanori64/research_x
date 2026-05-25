from __future__ import annotations

import asyncio
import json
import os
import re
from datetime import datetime
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any

from research_x.contracts import (
    AcquisitionTarget,
    AdapterConfig,
    FetchOutcome,
    OutcomeStatus,
    TargetKind,
    XItem,
    utc_now,
)
from research_x.cookies import load_cookie_dict_from_playwright_state, require_x_session_cookies


class ScweetAdapter:
    adapter_id = "scweet"

    def __init__(self, config: AdapterConfig) -> None:
        self.config = config

    def fetch(self, target: AcquisitionTarget) -> FetchOutcome:
        return asyncio.run(self._fetch(target))

    async def _fetch(self, target: AcquisitionTarget) -> FetchOutcome:
        started_at = utc_now()
        settings = _ScweetSettings.from_config(self.config)
        cookies = settings.cookie_payload()
        if cookies is None:
            return FetchOutcome(
                adapter_id=self.adapter_id,
                target=target,
                status=OutcomeStatus.NOT_CONFIGURED,
                started_at=started_at,
                finished_at=utc_now(),
                error_type="NotConfigured",
                error_message=(
                    "Scweet requires auth_token/ct0 cookies, a cookies_file, "
                    "or playwright_storage_state."
                ),
                metadata={"db_path": str(settings.db_path)},
            )

        if target.kind == TargetKind.URL:
            return FetchOutcome(
                adapter_id=self.adapter_id,
                target=target,
                status=OutcomeStatus.UNSUPPORTED,
                started_at=started_at,
                finished_at=utc_now(),
                error_type="UnsupportedTarget",
                error_message="Scweet adapter currently supports search and profile targets.",
                metadata={"library": "Scweet"},
            )

        try:
            from Scweet import Scweet, ScweetConfig
        except ImportError as exc:
            return FetchOutcome(
                adapter_id=self.adapter_id,
                target=target,
                status=OutcomeStatus.NOT_CONFIGURED,
                started_at=started_at,
                finished_at=utc_now(),
                error_type="MissingDependency",
                error_message="Install Scweet to enable this adapter.",
                metadata={"dependency": "Scweet", "detail": str(exc)},
            )

        settings.db_path.parent.mkdir(parents=True, exist_ok=True)
        config = ScweetConfig(
            db_path=str(settings.db_path),
            daily_requests_limit=settings.daily_requests_limit,
            daily_tweets_limit=settings.daily_tweets_limit,
            max_empty_pages=settings.max_empty_pages,
            api_page_size=settings.api_page_size,
            min_delay_s=settings.min_delay_seconds,
            manifest_update_on_init=settings.manifest_update_on_init,
            manifest_scrape_on_init=settings.manifest_scrape_on_init,
            api_user_agent=settings.user_agent,
            api_http_impersonate=settings.api_http_impersonate,
        )
        client = Scweet(
            cookies=cookies,
            db_path=str(settings.db_path),
            proxy=settings.proxy,
            config=config,
            provision=True,
        )

        records = await asyncio.wait_for(
            self._fetch_records(client, target, settings),
            timeout=settings.request_timeout_seconds,
        )
        items = [_record_to_item(record) for record in records[: max(1, target.limit)]]
        status = OutcomeStatus.OK if items else OutcomeStatus.EMPTY
        return FetchOutcome(
            adapter_id=self.adapter_id,
            target=target,
            status=status,
            started_at=started_at,
            finished_at=utc_now(),
            items=tuple(items),
            metadata={
                "auth": settings.auth_mode(),
                "db_path": str(settings.db_path),
                "library": "Scweet",
            },
        )

    async def _fetch_records(
        self,
        client: Any,
        target: AcquisitionTarget,
        settings: _ScweetSettings,
    ) -> list[dict[str, Any]]:
        limit = max(1, target.limit)
        if target.kind == TargetKind.SEARCH:
            return await client.asearch(
                target.value,
                since=settings.since,
                until=settings.until,
                display_type=settings.display_type,
                limit=limit,
                max_empty_pages=settings.max_empty_pages,
                save=False,
            )

        if target.kind == TargetKind.PROFILE:
            return await client.aget_profile_tweets(
                [_screen_name(target.value)],
                limit=limit,
                max_empty_pages=settings.max_empty_pages,
                save=False,
            )

        raise ValueError(f"unsupported target kind for Scweet: {target.kind}")


class _ScweetSettings:
    def __init__(
        self,
        *,
        db_path: Path,
        cookies_file: Path | None,
        playwright_storage_state: Path | None,
        auth_token: str | None,
        ct0: str | None,
        proxy: str | None,
        user_agent: str | None,
        api_http_impersonate: str | None,
        since: str | None,
        until: str | None,
        display_type: str,
        request_timeout_seconds: float,
        max_empty_pages: int,
        daily_requests_limit: int,
        daily_tweets_limit: int,
        api_page_size: int,
        min_delay_seconds: float,
        manifest_update_on_init: bool,
        manifest_scrape_on_init: bool,
    ) -> None:
        self.db_path = db_path
        self.cookies_file = cookies_file
        self.playwright_storage_state = playwright_storage_state
        self.auth_token = auth_token
        self.ct0 = ct0
        self.proxy = proxy
        self.user_agent = user_agent
        self.api_http_impersonate = api_http_impersonate
        self.since = since
        self.until = until
        self.display_type = display_type
        self.request_timeout_seconds = request_timeout_seconds
        self.max_empty_pages = max_empty_pages
        self.daily_requests_limit = daily_requests_limit
        self.daily_tweets_limit = daily_tweets_limit
        self.api_page_size = api_page_size
        self.min_delay_seconds = min_delay_seconds
        self.manifest_update_on_init = manifest_update_on_init
        self.manifest_scrape_on_init = manifest_scrape_on_init

    @classmethod
    def from_config(cls, config: AdapterConfig) -> _ScweetSettings:
        env_prefix = str(config.options.get("env_prefix", "RESEARCH_X"))
        return cls(
            db_path=Path(str(config.options.get("db_path", ".secrets/scweet_state.db"))),
            cookies_file=_path_option(config, "cookies_file"),
            playwright_storage_state=_path_option(config, "playwright_storage_state"),
            auth_token=_env(config, "auth_token_env", f"{env_prefix}_X_AUTH_TOKEN"),
            ct0=_env(config, "ct0_env", f"{env_prefix}_X_CT0"),
            proxy=_env(config, "proxy_env", f"{env_prefix}_X_PROXY"),
            user_agent=_env(config, "user_agent_env", f"{env_prefix}_X_USER_AGENT"),
            api_http_impersonate=_option(config, "api_http_impersonate"),
            since=_option(config, "since"),
            until=_option(config, "until"),
            display_type=str(config.options.get("display_type", "Latest")),
            request_timeout_seconds=float(config.options.get("request_timeout_seconds", 75)),
            max_empty_pages=int(config.options.get("max_empty_pages", 1)),
            daily_requests_limit=int(config.options.get("daily_requests_limit", 30)),
            daily_tweets_limit=int(config.options.get("daily_tweets_limit", 600)),
            api_page_size=int(config.options.get("api_page_size", 20)),
            min_delay_seconds=float(config.options.get("min_delay_seconds", 0)),
            manifest_update_on_init=bool(config.options.get("manifest_update_on_init", False)),
            manifest_scrape_on_init=bool(config.options.get("manifest_scrape_on_init", False)),
        )

    def cookie_payload(self) -> dict[str, str] | list[dict[str, Any]] | None:
        if self.cookies_file is not None and self.cookies_file.exists():
            payload = json.loads(self.cookies_file.read_text(encoding="utf-8"))
            if isinstance(payload, dict):
                require_x_session_cookies(payload)
                return payload
            if isinstance(payload, list):
                return payload
        if self.playwright_storage_state is not None and self.playwright_storage_state.exists():
            cookies = load_cookie_dict_from_playwright_state(self.playwright_storage_state)
            require_x_session_cookies(cookies)
            return cookies
        if self.auth_token:
            cookies = {"auth_token": self.auth_token}
            if self.ct0:
                cookies["ct0"] = self.ct0
            return cookies
        return None

    def auth_mode(self) -> str:
        if self.cookies_file is not None and self.cookies_file.exists():
            return "cookies_file"
        if self.playwright_storage_state is not None and self.playwright_storage_state.exists():
            return "playwright_storage_state"
        if self.auth_token:
            return "auth_token"
        return "unknown"


def _record_to_item(record: dict[str, Any]) -> XItem:
    user = record.get("user")
    user = user if isinstance(user, dict) else {}
    source_id = str(record.get("tweet_id") or record.get("id") or "")
    author = user.get("screen_name") or record.get("screen_name") or record.get("username")
    return XItem(
        source_id=source_id,
        url=record.get("tweet_url") or _tweet_url(author, source_id),
        author=str(author) if author else None,
        text=record.get("text") or record.get("full_text"),
        created_at=_parse_timestamp(record.get("timestamp") or record.get("created_at")),
        observed_at=utc_now(),
        raw=record,
    )


def _parse_timestamp(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        pass
    try:
        return parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None


def _tweet_url(author: Any, source_id: str) -> str | None:
    if not author or not source_id:
        return None
    return f"https://x.com/{author}/status/{source_id}"


def _screen_name(value: str) -> str:
    value = value.strip()
    if value.startswith("@"):
        return value[1:]
    match = re.search(r"x\.com/([^/?#]+)", value)
    if match:
        return match.group(1)
    return value


def _env(config: AdapterConfig, option_name: str, default_env_name: str) -> str | None:
    env_name = str(config.options.get(option_name, default_env_name))
    value = os.environ.get(env_name)
    if value is None or value == "":
        return None
    return value


def _option(config: AdapterConfig, option_name: str) -> str | None:
    value = config.options.get(option_name)
    if value is None or value == "":
        return None
    return str(value)


def _path_option(config: AdapterConfig, option_name: str) -> Path | None:
    value = config.options.get(option_name)
    if value is None or value == "":
        return None
    return Path(str(value))
