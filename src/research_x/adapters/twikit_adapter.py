from __future__ import annotations

import asyncio
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
from research_x.cookies import (
    load_cookie_dict_from_playwright_state,
    require_x_session_cookies,
    write_cookie_dict,
)


class TwikitAdapter:
    adapter_id = "twikit"

    def __init__(self, config: AdapterConfig) -> None:
        self.config = config

    def fetch(self, target: AcquisitionTarget) -> FetchOutcome:
        return asyncio.run(self._fetch(target))

    async def _fetch(self, target: AcquisitionTarget) -> FetchOutcome:
        started_at = utc_now()
        settings = _TwikitSettings.from_config(self.config)
        readiness = settings.readiness_error()
        if readiness is not None:
            return FetchOutcome(
                adapter_id=self.adapter_id,
                target=target,
                status=OutcomeStatus.NOT_CONFIGURED,
                started_at=started_at,
                finished_at=utc_now(),
                error_type="NotConfigured",
                error_message=readiness,
                metadata={"required_env": settings.required_env_names()},
            )

        try:
            from twikit import Client
        except ImportError as exc:
            return FetchOutcome(
                adapter_id=self.adapter_id,
                target=target,
                status=OutcomeStatus.NOT_CONFIGURED,
                started_at=started_at,
                finished_at=utc_now(),
                error_type="MissingDependency",
                error_message="Install twikit to enable this adapter.",
                metadata={"dependency": "twikit", "detail": str(exc)},
            )

        _patch_twikit_user_defaults()
        cookie_path = settings.cookie_path
        if cookie_path is not None:
            cookie_path.parent.mkdir(parents=True, exist_ok=True)
        settings.ensure_cookie_file()

        client = Client(
            settings.language,
            proxy=settings.proxy,
            user_agent=settings.user_agent,
        )
        if settings.disable_client_transaction:
            _disable_twikit_client_transaction(client)
        await client.login(
            auth_info_1=settings.username or "cookie",
            auth_info_2=settings.email,
            password=settings.password or "cookie",
            totp_secret=settings.totp_secret,
            cookies_file=str(cookie_path) if cookie_path is not None else None,
            enable_ui_metrics=settings.enable_ui_metrics,
        )
        if settings.disable_client_transaction:
            _disable_twikit_client_transaction(client)

        items = await asyncio.wait_for(
            self._fetch_items(client, target),
            timeout=settings.request_timeout_seconds,
        )
        status = OutcomeStatus.OK if items else OutcomeStatus.EMPTY
        transaction_mode = "disabled" if settings.disable_client_transaction else "enabled"
        return FetchOutcome(
            adapter_id=self.adapter_id,
            target=target,
            status=status,
            started_at=started_at,
            finished_at=utc_now(),
            items=tuple(items),
            metadata={
                "auth": settings.auth_mode(),
                "client_transaction": transaction_mode,
                "library": "twikit",
            },
        )

    async def _fetch_items(self, client: Any, target: AcquisitionTarget) -> list[XItem]:
        limit = max(1, target.limit)
        if target.kind == TargetKind.SEARCH:
            result = await client.search_tweet(
                target.value,
                str(self.config.options.get("product", "Latest")),
                count=min(limit, 20),
            )
            return [_tweet_to_item(tweet) for tweet in list(result)[:limit]]

        if target.kind == TargetKind.PROFILE:
            screen_name = _screen_name(target.value)
            user = await client.get_user_by_screen_name(screen_name)
            result = await client.get_user_tweets(
                str(user.id),
                str(self.config.options.get("tweet_type", "Tweets")),
                count=min(limit, 40),
            )
            return [_tweet_to_item(tweet, target_user=user) for tweet in list(result)[:limit]]

        if target.kind == TargetKind.URL:
            tweet_id = _tweet_id(target.value)
            tweet = await client.get_tweet_by_id(tweet_id)
            return [_tweet_to_item(tweet)]

        if target.kind == TargetKind.BOOKMARKS:
            return await self._fetch_bookmarks(client, target)

        raise ValueError(f"unsupported target kind for twikit: {target.kind}")

    async def _fetch_bookmarks(self, client: Any, target: AcquisitionTarget) -> list[XItem]:
        limit = max(1, target.limit)
        folder_id = self.config.options.get("folder_id")
        folder_id = str(folder_id) if folder_id is not None and folder_id != "" else None
        page_size = max(
            1,
            min(limit, int(self.config.options.get("bookmark_page_size", 100))),
        )
        result = await client.get_bookmarks(count=page_size, folder_id=folder_id)
        items: list[XItem] = []
        seen: set[str] = set()
        seen_cursors: set[str] = set()

        while result and len(items) < limit:
            for tweet in result:
                item = _tweet_to_item(tweet)
                if not item.source_id or item.source_id in seen:
                    continue
                seen.add(item.source_id)
                items.append(_with_bookmark_metadata(item, len(items), folder_id))
                if len(items) >= limit:
                    break
            cursor = getattr(result, "next_cursor", None)
            if len(items) >= limit or not cursor or cursor in seen_cursors:
                break
            seen_cursors.add(cursor)
            result = await result.next()
        return items


class _TwikitSettings:
    def __init__(
        self,
        *,
        username: str | None,
        email: str | None,
        password: str | None,
        totp_secret: str | None,
        cookie_path: Path | None,
        playwright_storage_state: Path | None,
        language: str,
        proxy: str | None,
        user_agent: str | None,
        enable_ui_metrics: bool,
        disable_client_transaction: bool,
        request_timeout_seconds: float,
        env_prefix: str,
    ) -> None:
        self.username = username
        self.email = email
        self.password = password
        self.totp_secret = totp_secret
        self.cookie_path = cookie_path
        self.playwright_storage_state = playwright_storage_state
        self.language = language
        self.proxy = proxy
        self.user_agent = user_agent
        self.enable_ui_metrics = enable_ui_metrics
        self.disable_client_transaction = disable_client_transaction
        self.request_timeout_seconds = request_timeout_seconds
        self.env_prefix = env_prefix

    @classmethod
    def from_config(cls, config: AdapterConfig) -> _TwikitSettings:
        env_prefix = str(config.options.get("env_prefix", "RESEARCH_X"))
        cookie_value = str(
            config.options.get(
                "cookies_file",
                os.environ.get(f"{env_prefix}_TWIKIT_COOKIES", ".secrets/twikit_cookies.json"),
            )
        )
        return cls(
            username=_env(config, "username_env", f"{env_prefix}_X_USERNAME"),
            email=_env(config, "email_env", f"{env_prefix}_X_EMAIL"),
            password=_env(config, "password_env", f"{env_prefix}_X_PASSWORD"),
            totp_secret=_env(config, "totp_secret_env", f"{env_prefix}_X_TOTP_SECRET"),
            cookie_path=Path(cookie_value) if cookie_value else None,
            playwright_storage_state=_path_option(config, "playwright_storage_state"),
            language=str(config.options.get("language", "en-US")),
            proxy=_env(config, "proxy_env", f"{env_prefix}_X_PROXY"),
            user_agent=_env(config, "user_agent_env", f"{env_prefix}_X_USER_AGENT"),
            enable_ui_metrics=bool(config.options.get("enable_ui_metrics", True)),
            disable_client_transaction=bool(config.options.get("disable_client_transaction", True)),
            request_timeout_seconds=float(config.options.get("request_timeout_seconds", 45)),
            env_prefix=env_prefix,
        )

    def readiness_error(self) -> str | None:
        if self.cookie_path is not None and self.cookie_path.exists():
            return None
        if self.playwright_storage_state is not None and self.playwright_storage_state.exists():
            return None
        missing = [
            name
            for name, value in (
                (f"{self.env_prefix}_X_USERNAME", self.username),
                (f"{self.env_prefix}_X_PASSWORD", self.password),
            )
            if not value
        ]
        if missing:
            return "Twikit needs an existing cookies file or env credentials: " + ", ".join(missing)
        return None

    def required_env_names(self) -> list[str]:
        return [
            f"{self.env_prefix}_X_USERNAME",
            f"{self.env_prefix}_X_EMAIL",
            f"{self.env_prefix}_X_PASSWORD",
            f"{self.env_prefix}_X_TOTP_SECRET",
        ]

    def auth_mode(self) -> str:
        if self.cookie_path is not None and self.cookie_path.exists():
            return "cookies_file"
        if self.playwright_storage_state is not None and self.playwright_storage_state.exists():
            return "playwright_storage_state"
        return "credentials"

    def ensure_cookie_file(self) -> None:
        if self.cookie_path is None or self.cookie_path.exists():
            return
        if self.playwright_storage_state is None or not self.playwright_storage_state.exists():
            return
        cookies = load_cookie_dict_from_playwright_state(self.playwright_storage_state)
        require_x_session_cookies(cookies)
        write_cookie_dict(self.cookie_path, cookies)


def _disable_twikit_client_transaction(client: Any) -> None:
    client.client_transaction.home_page_response = True
    client.client_transaction.generate_transaction_id = lambda *args, **kwargs: ""


def _patch_twikit_user_defaults() -> None:
    from twikit.user import User

    if getattr(User, "_research_x_defaults_patched", False):
        return
    original_init = User.__init__

    def patched_init(self, client, data):
        legacy = data.setdefault("legacy", {})
        entities = legacy.setdefault("entities", {})
        entities.setdefault("description", {}).setdefault("urls", [])
        entities.setdefault("url", {}).setdefault("urls", [])
        legacy.setdefault("withheld_in_countries", [])
        legacy.setdefault("want_retweets", False)
        return original_init(self, client, data)

    User.__init__ = patched_init
    User._research_x_defaults_patched = True


def _env(config: AdapterConfig, option_name: str, default_env_name: str) -> str | None:
    env_name = str(config.options.get(option_name, default_env_name))
    value = os.environ.get(env_name)
    if value is None or value == "":
        return None
    return value


def _path_option(config: AdapterConfig, option_name: str) -> Path | None:
    value = config.options.get(option_name)
    if value is None or value == "":
        return None
    return Path(str(value))


def _tweet_to_item(tweet: Any, target_user: Any | None = None) -> XItem:
    author = getattr(getattr(tweet, "user", None), "screen_name", None)
    if author is None and target_user is not None:
        author = getattr(target_user, "screen_name", None)
    source_id = str(getattr(tweet, "id", ""))
    return XItem(
        source_id=source_id,
        url=_tweet_url(tweet, author, source_id),
        author=author,
        text=getattr(tweet, "text", None) or getattr(tweet, "full_text", None),
        created_at=_created_at(tweet),
        observed_at=utc_now(),
        raw=_raw_tweet(tweet),
    )


def _with_bookmark_metadata(item: XItem, index: int, folder_id: str | None) -> XItem:
    raw = dict(item.raw)
    raw["source_timeline"] = "bookmarks"
    raw["bookmark_root"] = True
    raw["bookmark_index"] = index
    if folder_id:
        raw["bookmark_folder_id"] = folder_id
    return XItem(
        source_id=item.source_id,
        url=item.url,
        author=item.author,
        text=item.text,
        created_at=item.created_at,
        observed_at=item.observed_at,
        raw=raw,
    )


def _created_at(tweet: Any) -> datetime | None:
    value = getattr(tweet, "created_at_datetime", None)
    if isinstance(value, datetime):
        return value
    value = getattr(tweet, "created_at", None)
    if isinstance(value, datetime):
        return value
    if isinstance(value, str) and value:
        try:
            return parsedate_to_datetime(value)
        except (TypeError, ValueError):
            return None
    return None


def _raw_tweet(tweet: Any) -> dict[str, Any]:
    raw = getattr(tweet, "_data", None)
    if isinstance(raw, dict):
        return raw
    return {
        "id": getattr(tweet, "id", None),
        "text": getattr(tweet, "text", None),
        "created_at": getattr(tweet, "created_at", None),
    }


def _tweet_url(tweet: Any, author: str | None, source_id: str) -> str | None:
    value = getattr(tweet, "url", None)
    if value:
        return str(value)
    if author and source_id:
        return f"https://x.com/{author}/status/{source_id}"
    return None


def _screen_name(value: str) -> str:
    value = value.strip()
    if value.startswith("@"):
        return value[1:]
    match = re.search(r"x\.com/([^/?#]+)", value)
    if match:
        return match.group(1)
    return value


def _tweet_id(value: str) -> str:
    match = re.search(r"/status/(\d+)", value)
    if match:
        return match.group(1)
    if value.isdigit():
        return value
    raise ValueError(f"URL target is not a tweet URL or tweet id: {value}")
