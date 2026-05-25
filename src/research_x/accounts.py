from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

DEFAULT_STORAGE_STATE = Path(".secrets/playwright_x_state.json")
DEFAULT_USER_DATA_DIR = Path(".secrets/playwright_profile")
DEFAULT_TWIKIT_COOKIES = Path(".secrets/twikit_cookies.json")
DEFAULT_SCWEET_COOKIES = Path(".secrets/scweet_cookies.json")
DEFAULT_MASA_COOKIES = Path(".secrets/masa_cookies.json")
DEFAULT_TWSCRAPE_DB = Path(".secrets/twscrape_accounts.db")


@dataclass(frozen=True)
class AccountPaths:
    account_id: str | None
    root: Path
    storage_state: Path
    user_data_dir: Path
    twikit_cookies_file: Path
    scweet_cookies_file: Path
    masa_cookies_file: Path
    twscrape_accounts_db: Path
    profile_file: Path


@dataclass(frozen=True)
class AccountProfile:
    account_id: str
    screen_name: str
    user_id: str | None = None
    display_name: str | None = None
    url: str | None = None
    metadata: dict[str, Any] | None = None


def resolve_account_paths(
    account: str | None = None,
    *,
    storage_state: str | Path | None = None,
    user_data_dir: str | Path | None = None,
) -> AccountPaths:
    account_id = normalize_account_id(account) if account else None
    if account_id is None:
        root = Path(".secrets")
        return AccountPaths(
            account_id=None,
            root=root,
            storage_state=Path(storage_state) if storage_state else DEFAULT_STORAGE_STATE,
            user_data_dir=Path(user_data_dir) if user_data_dir else DEFAULT_USER_DATA_DIR,
            twikit_cookies_file=DEFAULT_TWIKIT_COOKIES,
            scweet_cookies_file=DEFAULT_SCWEET_COOKIES,
            masa_cookies_file=DEFAULT_MASA_COOKIES,
            twscrape_accounts_db=DEFAULT_TWSCRAPE_DB,
            profile_file=root / "account.json",
        )

    root = Path(".secrets") / "accounts" / account_id
    return AccountPaths(
        account_id=account_id,
        root=root,
        storage_state=Path(storage_state) if storage_state else root / "playwright_x_state.json",
        user_data_dir=Path(user_data_dir) if user_data_dir else root / "playwright_profile",
        twikit_cookies_file=root / "twikit_cookies.json",
        scweet_cookies_file=root / "scweet_cookies.json",
        masa_cookies_file=root / "masa_cookies.json",
        twscrape_accounts_db=root / "twscrape_accounts.db",
        profile_file=root / "account.json",
    )


def normalize_account_id(value: str) -> str:
    normalized = value.strip().lstrip("@").lower()
    normalized = re.sub(r"[^a-z0-9_]+", "_", normalized)
    normalized = re.sub(r"_+", "_", normalized).strip("_")
    if not normalized:
        raise ValueError("account must contain at least one safe character")
    return normalized


def write_account_profile(
    *,
    account: str,
    screen_name: str | None = None,
    user_id: str | None = None,
    display_name: str | None = None,
    url: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> AccountProfile:
    account_id = normalize_account_id(account)
    profile = AccountProfile(
        account_id=account_id,
        screen_name=(screen_name or account_id).lstrip("@"),
        user_id=user_id,
        display_name=display_name,
        url=url or f"https://x.com/{account_id}",
        metadata=metadata or {},
    )
    paths = resolve_account_paths(account_id)
    paths.root.mkdir(parents=True, exist_ok=True)
    paths.profile_file.write_text(
        json.dumps(asdict(profile), ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return profile


def read_account_profile(account: str | None) -> AccountProfile | None:
    if not account:
        return None
    paths = resolve_account_paths(account)
    if not paths.profile_file.exists():
        account_id = normalize_account_id(account)
        return AccountProfile(
            account_id=account_id,
            screen_name=account_id,
            url=f"https://x.com/{account_id}",
            metadata={},
        )
    payload = json.loads(paths.profile_file.read_text(encoding="utf-8"))
    return AccountProfile(
        account_id=str(payload["account_id"]),
        screen_name=str(payload.get("screen_name") or payload["account_id"]),
        user_id=payload.get("user_id"),
        display_name=payload.get("display_name"),
        url=payload.get("url"),
        metadata=payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {},
    )
