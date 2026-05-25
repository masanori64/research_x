from __future__ import annotations

import asyncio
import os
import re
from contextlib import aclosing
from dataclasses import asdict, is_dataclass
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
    cookie_header,
    load_cookie_dict_from_playwright_state,
    parse_cookie_header,
    require_x_session_cookies,
)


class TwscrapeRawAdapter:
    adapter_id = "twscrape_raw"

    def __init__(self, config: AdapterConfig) -> None:
        self.config = config

    def fetch(self, target: AcquisitionTarget) -> FetchOutcome:
        return asyncio.run(self._fetch(target))

    async def _fetch(self, target: AcquisitionTarget) -> FetchOutcome:
        started_at = utc_now()
        settings = _TwscrapeSettings.from_config(self.config)

        try:
            from twscrape import API, AccountsPool
        except ImportError as exc:
            return FetchOutcome(
                adapter_id=self.adapter_id,
                target=target,
                status=OutcomeStatus.NOT_CONFIGURED,
                started_at=started_at,
                finished_at=utc_now(),
                error_type="MissingDependency",
                error_message="Install twscrape to enable this adapter.",
                metadata={"dependency": "twscrape", "detail": str(exc)},
            )

        direct_error: Exception | None = None
        direct_cookies = settings.direct_cookie_dict()
        if settings.direct_graphql and direct_cookies is not None:
            try:
                items = await asyncio.wait_for(
                    self._fetch_items_direct(settings, target, direct_cookies),
                    timeout=settings.request_timeout_seconds,
                )
                status = OutcomeStatus.OK if items else OutcomeStatus.EMPTY
                return FetchOutcome(
                    adapter_id=self.adapter_id,
                    target=target,
                    status=status,
                    started_at=started_at,
                    finished_at=utc_now(),
                    items=tuple(items),
                    metadata={
                        "auth": "cookie_session",
                        "direct_graphql": True,
                        "library": "twscrape",
                    },
                )
            except Exception as exc:  # noqa: BLE001 - keep the adapter comparison running.
                direct_error = exc

        settings.accounts_db.parent.mkdir(parents=True, exist_ok=True)
        if not settings.bootstrap_account and not settings.accounts_db.exists():
            if direct_error is not None:
                return FetchOutcome(
                    adapter_id=self.adapter_id,
                    target=target,
                    status=OutcomeStatus.ERROR,
                    started_at=started_at,
                    finished_at=utc_now(),
                    error_type=type(direct_error).__name__,
                    error_message=str(direct_error),
                    metadata={"direct_graphql": True},
                )
            return FetchOutcome(
                adapter_id=self.adapter_id,
                target=target,
                status=OutcomeStatus.NOT_CONFIGURED,
                started_at=started_at,
                finished_at=utc_now(),
                error_type="NoAccountsDatabase",
                error_message=(
                    "twscrape accounts database is missing. Provide an active accounts DB "
                    "or enable bootstrap_account with authorized credentials/cookies."
                ),
                metadata={"accounts_db": str(settings.accounts_db)},
            )
        pool = AccountsPool(str(settings.accounts_db), raise_when_no_account=True)
        bootstrap_error = await settings.bootstrap(pool)
        if bootstrap_error is not None:
            return FetchOutcome(
                adapter_id=self.adapter_id,
                target=target,
                status=OutcomeStatus.NOT_CONFIGURED,
                started_at=started_at,
                finished_at=utc_now(),
                error_type="NotConfigured",
                error_message=bootstrap_error,
                metadata={"accounts_db": str(settings.accounts_db)},
            )

        active_count = await _active_account_count(pool)
        if active_count == 0:
            return FetchOutcome(
                adapter_id=self.adapter_id,
                target=target,
                status=OutcomeStatus.NOT_CONFIGURED,
                started_at=started_at,
                finished_at=utc_now(),
                error_type="NoActiveAccounts",
                error_message="twscrape has no active accounts in its accounts database.",
                metadata={"accounts_db": str(settings.accounts_db)},
            )

        api = API(pool, raise_when_no_account=True)
        items = await asyncio.wait_for(
            self._fetch_items(api, target),
            timeout=settings.request_timeout_seconds,
        )
        status = OutcomeStatus.OK if items else OutcomeStatus.EMPTY
        metadata: dict[str, Any] = {
            "accounts_db": str(settings.accounts_db),
            "active_accounts": active_count,
            "library": "twscrape",
        }
        if direct_error is not None:
            metadata["direct_graphql_error"] = {
                "type": type(direct_error).__name__,
                "message": str(direct_error),
            }
        return FetchOutcome(
            adapter_id=self.adapter_id,
            target=target,
            status=status,
            started_at=started_at,
            finished_at=utc_now(),
            items=tuple(items),
            metadata=metadata,
        )

    async def _fetch_items(self, api: Any, target: AcquisitionTarget) -> list[XItem]:
        limit = max(1, target.limit)
        if target.kind == TargetKind.SEARCH:
            return [
                _twscrape_tweet_to_item(tweet)
                async for tweet in api.search(target.value, limit=limit)
            ]

        if target.kind == TargetKind.PROFILE:
            login = _screen_name(target.value)
            user = await api.user_by_login(login)
            if user is None:
                return []
            return [
                _twscrape_tweet_to_item(tweet)
                async for tweet in api.user_tweets(int(user.id), limit=limit)
            ]

        if target.kind == TargetKind.URL:
            tweet = await api.tweet_details(int(_tweet_id(target.value)))
            return [_twscrape_tweet_to_item(tweet)] if tweet is not None else []

        if target.kind == TargetKind.BOOKMARKS:
            from twscrape.models import parse_tweets

            items: list[XItem] = []
            seen: set[str] = set()
            async with aclosing(api.bookmarks_raw(limit=limit)) as pages:
                async for response in pages:
                    payload = response.json()
                    root_ids = _bookmark_root_tweet_ids(payload)
                    for tweet in parse_tweets(payload, limit * 3):
                        source_id = str(getattr(tweet, "id", ""))
                        if source_id not in root_ids or source_id in seen:
                            continue
                        seen.add(source_id)
                        items.append(
                            _with_bookmark_metadata(_twscrape_tweet_to_item(tweet), len(items))
                        )
                        if len(items) >= limit:
                            return items
            return items

        raise ValueError(f"unsupported target kind for twscrape_raw: {target.kind}")

    async def _fetch_items_direct(
        self,
        settings: _TwscrapeSettings,
        target: AcquisitionTarget,
        cookies: dict[str, str],
    ) -> list[XItem]:
        import httpx
        from twscrape.account import TOKEN
        from twscrape.api import (
            GQL_FEATURES,
            GQL_URL,
            OP_Bookmarks,
            OP_SearchTimeline,
            OP_TweetDetail,
            OP_UserByScreenName,
            OP_UserTweets,
        )
        from twscrape.models import parse_tweet, parse_tweets, parse_user

        limit = max(1, target.limit)
        headers = {
            "authorization": TOKEN,
            "content-type": "application/json",
            "user-agent": settings.user_agent,
            "x-csrf-token": cookies["ct0"],
            "x-twitter-active-user": "yes",
            "x-twitter-client-language": "en",
        }
        async with httpx.AsyncClient(
            cookies=cookies,
            follow_redirects=True,
            headers=headers,
            timeout=settings.request_timeout_seconds,
        ) as client:
            if target.kind == TargetKind.SEARCH:
                variables = {
                    "rawQuery": target.value,
                    "count": min(max(limit, 20), 100),
                    "product": str(self.config.options.get("product", "Latest")),
                    "querySource": "typed_query",
                }
                pages = _direct_tweet_pages(
                    client=client,
                    gql_url=GQL_URL,
                    op=OP_SearchTimeline,
                    variables=variables,
                    features=GQL_FEATURES,
                    field_toggles={"withArticleRichContentState": False},
                    limit=limit,
                    max_pages=settings.max_pages,
                    parse_tweets=parse_tweets,
                )
                return [_twscrape_tweet_to_item(tweet) async for tweet in pages]

            if target.kind == TargetKind.PROFILE:
                screen_name = _screen_name(target.value)
                user_obj = await _direct_gql_get(
                    client=client,
                    gql_url=GQL_URL,
                    op=OP_UserByScreenName,
                    variables={
                        "screen_name": screen_name,
                        "withSafetyModeUserFields": True,
                    },
                    features={**GQL_FEATURES, **_user_by_screen_name_features()},
                )
                user = parse_user(user_obj)
                if user is None:
                    return []
                variables = {
                    "userId": str(user.id),
                    "count": min(max(limit, 40), 100),
                    "includePromotedContent": True,
                    "withQuickPromoteEligibilityTweetFields": True,
                    "withVoice": True,
                    "withV2Timeline": True,
                }
                pages = _direct_tweet_pages(
                    client=client,
                    gql_url=GQL_URL,
                    op=OP_UserTweets,
                    variables=variables,
                    features=GQL_FEATURES,
                    field_toggles=None,
                    limit=limit,
                    max_pages=settings.max_pages,
                    parse_tweets=parse_tweets,
                )
                return [_twscrape_tweet_to_item(tweet) async for tweet in pages]

            if target.kind == TargetKind.URL:
                tweet_id = int(_tweet_id(target.value))
                tweet_obj = await _direct_gql_get(
                    client=client,
                    gql_url=GQL_URL,
                    op=OP_TweetDetail,
                    variables={
                        "focalTweetId": str(tweet_id),
                        "with_rux_injections": True,
                        "includePromotedContent": True,
                        "withCommunity": True,
                        "withQuickPromoteEligibilityTweetFields": True,
                        "withBirdwatchNotes": True,
                        "withVoice": True,
                        "withV2Timeline": True,
                    },
                    features=GQL_FEATURES,
                )
                tweet = parse_tweet(tweet_obj, tweet_id)
                return [_twscrape_tweet_to_item(tweet)] if tweet is not None else []

            if target.kind == TargetKind.BOOKMARKS:
                return await _direct_bookmark_items(
                    client=client,
                    gql_url=GQL_URL,
                    op_bookmarks=OP_Bookmarks,
                    gql_features=GQL_FEATURES,
                    limit=limit,
                    max_pages=settings.max_pages,
                    parse_tweets=parse_tweets,
                )

        raise ValueError(f"unsupported target kind for twscrape_raw: {target.kind}")


class _TwscrapeSettings:
    def __init__(
        self,
        *,
        accounts_db: Path,
        username: str | None,
        password: str | None,
        email: str | None,
        email_password: str | None,
        cookies: str | None,
        playwright_storage_state: Path | None,
        mfa_code: str | None,
        proxy: str | None,
        bootstrap_account: bool,
        keep_failed_bootstrap_account: bool,
        direct_graphql: bool,
        request_timeout_seconds: float,
        max_pages: int,
        user_agent: str,
        env_prefix: str,
    ) -> None:
        self.accounts_db = accounts_db
        self.username = username
        self.password = password
        self.email = email
        self.email_password = email_password
        self.cookies = cookies
        self.playwright_storage_state = playwright_storage_state
        self.mfa_code = mfa_code
        self.proxy = proxy
        self.bootstrap_account = bootstrap_account
        self.keep_failed_bootstrap_account = keep_failed_bootstrap_account
        self.direct_graphql = direct_graphql
        self.request_timeout_seconds = request_timeout_seconds
        self.max_pages = max_pages
        self.user_agent = user_agent
        self.env_prefix = env_prefix

    @classmethod
    def from_config(cls, config: AdapterConfig) -> _TwscrapeSettings:
        env_prefix = str(config.options.get("env_prefix", "RESEARCH_X"))
        accounts_db = Path(
            str(
                config.options.get(
                    "accounts_db",
                    os.environ.get(
                        f"{env_prefix}_TWSCRAPE_ACCOUNTS_DB",
                        ".secrets/twscrape_accounts.db",
                    ),
                )
            )
        )
        return cls(
            accounts_db=accounts_db,
            username=_option_or_env(config, "username", "username_env", f"{env_prefix}_X_USERNAME"),
            password=_env(config, "password_env", f"{env_prefix}_X_PASSWORD"),
            email=_env(config, "email_env", f"{env_prefix}_X_EMAIL"),
            email_password=_env(config, "email_password_env", f"{env_prefix}_EMAIL_PASSWORD"),
            cookies=_env(config, "cookies_env", f"{env_prefix}_TWSCRAPE_COOKIES"),
            playwright_storage_state=_path_option(config, "playwright_storage_state"),
            mfa_code=_env(config, "mfa_code_env", f"{env_prefix}_X_MFA_CODE"),
            proxy=_env(config, "proxy_env", f"{env_prefix}_X_PROXY"),
            bootstrap_account=bool(config.options.get("bootstrap_account", False)),
            keep_failed_bootstrap_account=bool(
                config.options.get("keep_failed_bootstrap_account", False)
            ),
            direct_graphql=bool(config.options.get("direct_graphql", True)),
            request_timeout_seconds=float(config.options.get("request_timeout_seconds", 45)),
            max_pages=int(config.options.get("max_pages", 3)),
            user_agent=str(
                config.options.get(
                    "user_agent",
                    os.environ.get(
                        f"{env_prefix}_X_USER_AGENT",
                        (
                            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                            "AppleWebKit/537.36 (KHTML, like Gecko) "
                            "Chrome/125.0.0.0 Safari/537.36"
                        ),
                    ),
                )
            ),
            env_prefix=env_prefix,
        )

    async def bootstrap(self, pool: Any) -> str | None:
        if not self.bootstrap_account:
            return None
        if not self.username:
            return f"twscrape bootstrap requires {self.env_prefix}_X_USERNAME."
        cookies = self.resolved_cookies()
        if not self.password and not cookies:
            return (
                "twscrape bootstrap requires either "
                f"{self.env_prefix}_X_PASSWORD, {self.env_prefix}_TWSCRAPE_COOKIES, "
                "or playwright_storage_state."
            )
        await pool.add_account(
            username=self.username,
            password=self.password or "",
            email=self.email or "",
            email_password=self.email_password or "",
            cookies=cookies,
            mfa_code=self.mfa_code,
            proxy=self.proxy,
        )
        if cookies:
            return None
        counter = await pool.login_all([self.username])
        if counter.get("success", 0) < 1:
            if not self.keep_failed_bootstrap_account:
                await pool.delete_accounts([self.username])
                if not await pool.accounts_info() and self.accounts_db.exists():
                    self.accounts_db.unlink()
            return (
                "twscrape account bootstrap did not produce an active account. "
                "Provide cookies, MFA, or email mailbox credentials if X challenges the login."
            )
        return None

    def resolved_cookies(self) -> str | None:
        if self.cookies:
            return self.cookies
        if self.playwright_storage_state is None:
            return None
        if not self.playwright_storage_state.exists():
            return None
        cookies = load_cookie_dict_from_playwright_state(self.playwright_storage_state)
        require_x_session_cookies(cookies)
        return cookie_header(cookies)

    def direct_cookie_dict(self) -> dict[str, str] | None:
        if self.cookies:
            cookies = parse_cookie_header(self.cookies)
            require_x_session_cookies(cookies)
            return cookies
        if self.playwright_storage_state is None or not self.playwright_storage_state.exists():
            return None
        cookies = load_cookie_dict_from_playwright_state(self.playwright_storage_state)
        require_x_session_cookies(cookies)
        return cookies


async def _active_account_count(pool: Any) -> int:
    info = await pool.accounts_info()
    return sum(1 for item in info if item.get("active"))


async def _direct_tweet_pages(
    *,
    client: Any,
    gql_url: str,
    op: str,
    variables: dict[str, Any],
    features: dict[str, Any],
    field_toggles: dict[str, Any] | None,
    limit: int,
    max_pages: int,
    parse_tweets: Any,
):
    cursor: str | None = None
    seen: set[str] = set()
    pages = 0
    while pages < max_pages and len(seen) < limit:
        page_variables = {**variables}
        if cursor is not None:
            page_variables["cursor"] = cursor
        obj = await _direct_gql_get(
            client=client,
            gql_url=gql_url,
            op=op,
            variables=page_variables,
            features=features,
            field_toggles=field_toggles,
        )
        for tweet in parse_tweets(obj, limit):
            source_id = str(getattr(tweet, "id", ""))
            if not source_id or source_id in seen:
                continue
            seen.add(source_id)
            yield tweet
            if len(seen) >= limit:
                return
        cursor = _bottom_cursor(obj)
        if cursor is None:
            return
        pages += 1


async def _direct_bookmark_items(
    *,
    client: Any,
    gql_url: str,
    op_bookmarks: str,
    gql_features: dict[str, Any],
    limit: int,
    max_pages: int,
    parse_tweets: Any,
) -> list[XItem]:
    variables = {
        "count": min(max(limit, 20), 100),
        "includePromotedContent": False,
        "withClientEventToken": False,
        "withBirdwatchNotes": False,
        "withVoice": True,
        "withV2Timeline": True,
    }
    features = {
        **gql_features,
        "graphql_timeline_v2_bookmark_timeline": True,
    }
    items: list[XItem] = []
    seen: set[str] = set()
    cursor: str | None = None
    pages = 0
    while pages < max_pages and len(items) < limit:
        page_variables = dict(variables)
        if cursor is not None:
            page_variables["cursor"] = cursor
        payload = await _direct_gql_get(
            client=client,
            gql_url=gql_url,
            op=op_bookmarks,
            variables=page_variables,
            features=features,
            field_toggles=None,
        )
        root_ids = _bookmark_root_tweet_ids(payload)
        for tweet in parse_tweets(payload, limit * 3):
            source_id = str(getattr(tweet, "id", ""))
            if source_id not in root_ids or source_id in seen:
                continue
            seen.add(source_id)
            items.append(_with_bookmark_metadata(_twscrape_tweet_to_item(tweet), len(items)))
            if len(items) >= limit:
                return items
        cursor = _bottom_cursor(payload)
        if cursor is None:
            break
        pages += 1
    return items


async def _direct_gql_get(
    *,
    client: Any,
    gql_url: str,
    op: str,
    variables: dict[str, Any],
    features: dict[str, Any],
    field_toggles: dict[str, Any] | None = None,
) -> dict[str, Any]:
    from twscrape.api import encode_params

    payload: dict[str, Any] = {"variables": variables, "features": features}
    if field_toggles is not None:
        payload["fieldToggles"] = field_toggles
    response = await client.get(f"{gql_url}/{op}", params=encode_params(payload))
    if response.status_code != 200:
        raise RuntimeError(
            f"X GraphQL {op} returned HTTP {response.status_code}: {response.text[:300]}"
        )
    obj = response.json()
    if obj.get("errors") and not obj.get("data"):
        raise RuntimeError(f"X GraphQL {op} returned errors: {obj['errors'][:3]}")
    return obj


def _bottom_cursor(value: Any) -> str | None:
    if isinstance(value, dict):
        if value.get("cursorType") == "Bottom":
            cursor = value.get("value")
            return cursor if isinstance(cursor, str) and cursor else None
        for item in value.values():
            cursor = _bottom_cursor(item)
            if cursor is not None:
                return cursor
    if isinstance(value, list):
        for item in value:
            cursor = _bottom_cursor(item)
            if cursor is not None:
                return cursor
    return None


def _bookmark_root_tweet_ids(value: Any) -> set[str]:
    return {
        str(tweet["rest_id"])
        for tweet in _iter_bookmark_tweet_results(value)
        if isinstance(tweet.get("rest_id"), str) and tweet.get("rest_id")
    }


def _iter_bookmark_tweet_results(value: Any):
    for entry in _iter_timeline_entries(value):
        yield from _tweet_results_from_entry(entry)


def _iter_timeline_entries(value: Any):
    if isinstance(value, dict):
        if isinstance(value.get("content"), dict) and isinstance(value.get("entryId"), str):
            yield value
        for item in value.values():
            yield from _iter_timeline_entries(item)
    elif isinstance(value, list):
        for item in value:
            yield from _iter_timeline_entries(item)


def _tweet_results_from_entry(entry: dict[str, Any]):
    content = entry.get("content")
    if not isinstance(content, dict):
        return
    item_content = content.get("itemContent")
    if isinstance(item_content, dict):
        tweet = _unwrap_tweet_result(item_content.get("tweet_results"))
        if tweet is not None:
            yield tweet
    items = content.get("items")
    if isinstance(items, list):
        for item in items:
            if not isinstance(item, dict):
                continue
            nested_content = item.get("item", {}).get("itemContent")
            if not isinstance(nested_content, dict):
                nested_content = item.get("itemContent")
            if isinstance(nested_content, dict):
                tweet = _unwrap_tweet_result(nested_content.get("tweet_results"))
                if tweet is not None:
                    yield tweet


def _unwrap_tweet_result(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    result = value.get("result", value)
    if not isinstance(result, dict):
        return None
    if result.get("__typename") == "TweetWithVisibilityResults":
        result = result.get("tweet")
    if (
        isinstance(result, dict)
        and result.get("__typename") in (None, "Tweet")
        and isinstance(result.get("legacy"), dict)
        and result.get("rest_id")
    ):
        return result
    return None


def _user_by_screen_name_features() -> dict[str, bool]:
    return {
        "highlights_tweets_tab_ui_enabled": True,
        "hidden_profile_likes_enabled": True,
        "creator_subscriptions_tweet_preview_api_enabled": True,
        "hidden_profile_subscriptions_enabled": True,
        "subscriptions_verification_info_verified_since_enabled": True,
        "subscriptions_verification_info_is_identity_verified_enabled": False,
        "responsive_web_twitter_article_notes_tab_enabled": False,
        "subscriptions_feature_can_gift_premium": False,
        "profile_label_improvements_pcf_label_in_post_enabled": False,
    }


def _env(config: AdapterConfig, option_name: str, default_env_name: str) -> str | None:
    env_name = str(config.options.get(option_name, default_env_name))
    value = os.environ.get(env_name)
    if value is None or value == "":
        return None
    return value


def _option_or_env(
    config: AdapterConfig,
    direct_option_name: str,
    env_option_name: str,
    default_env_name: str,
) -> str | None:
    direct_value = config.options.get(direct_option_name)
    if direct_value not in (None, ""):
        return str(direct_value)
    return _env(config, env_option_name, default_env_name)


def _path_option(config: AdapterConfig, option_name: str) -> Path | None:
    value = config.options.get(option_name)
    if value is None or value == "":
        return None
    return Path(str(value))


def _twscrape_tweet_to_item(tweet: Any) -> XItem:
    author = getattr(getattr(tweet, "user", None), "username", None)
    source_id = str(getattr(tweet, "id", ""))
    return XItem(
        source_id=source_id,
        url=getattr(tweet, "url", None),
        author=author,
        text=getattr(tweet, "rawContent", None),
        created_at=getattr(tweet, "date", None),
        observed_at=utc_now(),
        raw=_raw(tweet),
    )


def _with_bookmark_metadata(item: XItem, index: int) -> XItem:
    raw = dict(item.raw)
    raw["source_timeline"] = "bookmarks"
    raw["bookmark_root"] = True
    raw["bookmark_index"] = index
    raw["source_api"] = "twscrape"
    return XItem(
        source_id=item.source_id,
        url=item.url,
        author=item.author,
        text=item.text,
        created_at=item.created_at,
        observed_at=item.observed_at,
        raw=raw,
    )


def _raw(value: Any) -> dict[str, Any]:
    if is_dataclass(value):
        return asdict(value)
    if isinstance(value, dict):
        return value
    return {
        "id": getattr(value, "id", None),
        "url": getattr(value, "url", None),
        "rawContent": getattr(value, "rawContent", None),
    }


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
