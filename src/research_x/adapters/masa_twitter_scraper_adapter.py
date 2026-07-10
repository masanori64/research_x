from __future__ import annotations

import asyncio
import json
import os
import shlex
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

from research_x.contracts import (
    AcquisitionTarget,
    AdapterConfig,
    FetchOutcome,
    OutcomeStatus,
    XItem,
    utc_now,
)


class MasaTwitterScraperAdapter:
    adapter_id = "masa_twitter_scraper"

    def __init__(self, config: AdapterConfig) -> None:
        self.config = config

    def fetch(self, target: AcquisitionTarget) -> FetchOutcome:
        return asyncio.run(self._fetch(target))

    async def _fetch(self, target: AcquisitionTarget) -> FetchOutcome:
        started_at = utc_now()
        settings = _MasaSettings.from_config(self.config)
        command = settings.command_for(target)
        if command is None:
            return FetchOutcome(
                adapter_id=self.adapter_id,
                target=target,
                status=OutcomeStatus.NOT_CONFIGURED,
                started_at=started_at,
                finished_at=utc_now(),
                error_type="MissingSidecar",
                error_message=(
                    "masa_twitter_scraper needs either a sidecar command, "
                    "MASA_TWITTER_SCRAPER_BIN, or a binary option implementing the JSONL "
                    "contract."
                ),
                metadata={
                    "go_available": shutil.which("go") is not None,
                    "cookies_file": str(settings.cookies_file) if settings.cookies_file else None,
                    "sidecar_contract": settings.sidecar_contract(),
                },
            )

        try:
            process = await asyncio.create_subprocess_exec(
                *command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=settings.request_timeout_seconds,
            )
        except TimeoutError:
            return FetchOutcome(
                adapter_id=self.adapter_id,
                target=target,
                status=OutcomeStatus.ERROR,
                started_at=started_at,
                finished_at=utc_now(),
                error_type="SidecarTimeout",
                error_message=f"masa sidecar timed out after {settings.request_timeout_seconds}s",
                metadata={"command": _redacted_command(command)},
            )
        except OSError as exc:
            return FetchOutcome(
                adapter_id=self.adapter_id,
                target=target,
                status=OutcomeStatus.NOT_CONFIGURED,
                started_at=started_at,
                finished_at=utc_now(),
                error_type=type(exc).__name__,
                error_message=str(exc),
                metadata={"command": _redacted_command(command)},
            )

        stderr_text = stderr.decode("utf-8", errors="replace")
        stdout_text = stdout.decode("utf-8", errors="replace")
        if process.returncode != 0:
            return FetchOutcome(
                adapter_id=self.adapter_id,
                target=target,
                status=OutcomeStatus.ERROR,
                started_at=started_at,
                finished_at=utc_now(),
                error_type="SidecarExit",
                error_message=stderr_text[:1000] or f"sidecar exited {process.returncode}",
                metadata={
                    "command": _redacted_command(command),
                    "returncode": process.returncode,
                },
            )

        items = tuple(_items_from_sidecar_stdout(stdout_text, target.limit))
        return FetchOutcome(
            adapter_id=self.adapter_id,
            target=target,
            status=OutcomeStatus.OK if items else OutcomeStatus.EMPTY,
            started_at=started_at,
            finished_at=utc_now(),
            items=items,
            metadata={
                "command": _redacted_command(command),
                "stderr": stderr_text[:1000],
                "sidecar_contract": settings.sidecar_contract(),
            },
        )


class _MasaSettings:
    def __init__(
        self,
        *,
        command_template: list[str] | None,
        binary: str | None,
        cookies_file: Path | None,
        request_timeout_seconds: float,
    ) -> None:
        self.command_template = command_template
        self.binary = binary
        self.cookies_file = cookies_file
        self.request_timeout_seconds = request_timeout_seconds

    @classmethod
    def from_config(cls, config: AdapterConfig) -> _MasaSettings:
        env_prefix = str(config.options.get("env_prefix", "RESEARCH_X"))
        command = config.options.get("command")
        command_template: list[str] | None
        if isinstance(command, list):
            command_template = [str(part) for part in command]
        elif command:
            command_template = shlex.split(str(command))
        else:
            command_template = None

        binary_option_present = "binary" in config.options
        binary = str(config.options.get("binary", ""))
        if not binary_option_present:
            binary = os.environ.get(
                f"{env_prefix}_MASA_TWITTER_SCRAPER_BIN",
                os.environ.get("MASA_TWITTER_SCRAPER_BIN", ""),
            )
        if not binary and not binary_option_present:
            default_binary = Path(".secrets/bin/masa-twitter-scraper.exe")
            binary = (
                str(default_binary)
                if default_binary.exists()
                else shutil.which("masa-twitter-scraper")
                or shutil.which("twitter-scraper")
                or ""
            )
        cookies_file = config.options.get("cookies_file")
        return cls(
            command_template=command_template,
            binary=binary or None,
            cookies_file=Path(str(cookies_file)) if cookies_file else None,
            request_timeout_seconds=float(config.options.get("request_timeout_seconds", 45)),
        )

    def command_for(self, target: AcquisitionTarget) -> list[str] | None:
        values = {
            "target_kind": target.kind.value,
            "target_value": target.value,
            "limit": str(max(1, target.limit)),
            "cookies_file": str(self.cookies_file) if self.cookies_file else "",
        }
        if self.command_template is not None:
            return [part.format(**values) for part in self.command_template]
        if self.binary is None:
            return None
        command = [
            self.binary,
            "--kind",
            values["target_kind"],
            "--target",
            values["target_value"],
            "--limit",
            values["limit"],
            "--format",
            "jsonl",
        ]
        if self.cookies_file is not None and self.cookies_file.exists():
            command.extend(["--cookies-file", str(self.cookies_file)])
        return command

    def sidecar_contract(self) -> dict[str, Any]:
        return {
            "input_args": [
                "--kind {profile|search|url}",
                "--target <value>",
                "--limit <n>",
                "--cookies-file <json>",
                "--format jsonl",
            ],
            "stdout": "JSONL tweet rows or a JSON object/list containing tweets/items/data",
            "tweet_fields": ["id|id_str|tweet_id", "url", "text|full_text", "user|author"],
        }


def _items_from_sidecar_stdout(stdout_text: str, limit: int) -> list[XItem]:
    records: list[Any] = []
    stripped = stdout_text.strip()
    if not stripped:
        return []
    try:
        payload = json.loads(stripped)
        records.extend(_records_from_payload(payload))
    except json.JSONDecodeError:
        for line in stripped.splitlines():
            line = line.strip()
            if not line:
                continue
            records.extend(_records_from_payload(json.loads(line)))
    return [
        _record_to_item(record)
        for record in records[: max(1, limit)]
        if isinstance(record, dict)
    ]


def _records_from_payload(payload: Any) -> list[Any]:
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for key in ("tweets", "items", "data", "results"):
            value = payload.get(key)
            if isinstance(value, list):
                return value
        return [payload]
    return []


def _record_to_item(record: dict[str, Any]) -> XItem:
    user = record.get("user") or record.get("author") or {}
    if not isinstance(user, dict):
        user = {"screen_name": str(user)}
    source_id = str(record.get("id") or record.get("id_str") or record.get("tweet_id") or "")
    author = (
        user.get("screen_name")
        or user.get("username")
        or record.get("screen_name")
        or record.get("username")
    )
    return XItem(
        source_id=source_id,
        url=record.get("url") or _tweet_url(author, source_id),
        author=str(author) if author else None,
        text=record.get("text") or record.get("full_text") or record.get("rawContent"),
        created_at=_parse_datetime(record.get("created_at") or record.get("timestamp")),
        observed_at=utc_now(),
        raw=record,
    )


def _parse_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _tweet_url(author: Any, source_id: str) -> str | None:
    if not author or not source_id:
        return None
    return f"https://x.com/{author}/status/{source_id}"


def _redacted_command(command: list[str]) -> list[str]:
    redacted: list[str] = []
    redact_next = False
    for part in command:
        if redact_next:
            redacted.append("<redacted>")
            redact_next = False
            continue
        redacted.append(part)
        if part in {"--cookies", "--cookie", "--cookie-header"}:
            redact_next = True
    return redacted
