from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass, replace
from datetime import datetime
from pathlib import Path
from typing import Any

from research_x.adapters import build_adapter
from research_x.contracts import (
    AcquisitionTarget,
    AdapterConfig,
    ExperimentConfig,
    FetchOutcome,
    OutcomeStatus,
    TargetKind,
    XItem,
    utc_now,
)
from research_x.evidence import EvidenceStore
from research_x.pipeline_contracts import (
    PipelineStatus,
    PipelineTargetResult,
    ProviderAttempt,
    ProviderFailureKind,
    SessionArtifacts,
)
from research_x.session_broker import SessionBroker

DEFAULT_CHAINS: dict[TargetKind, tuple[str, ...]] = {
    TargetKind.PROFILE: (
        "twscrape_raw",
        "scweet",
        "twikit",
        "masa_twitter_scraper",
        "playwright",
        "scrapling",
        "crawl4ai",
        "camoufox",
        "patchright",
        "rebrowser_playwright",
        "rebrowser_patches",
        "scrapy",
    ),
    TargetKind.SEARCH: (
        "scweet",
        "twscrape_raw",
        "twikit",
        "masa_twitter_scraper",
        "playwright",
        "scrapling",
        "crawl4ai",
        "camoufox",
        "patchright",
        "rebrowser_playwright",
        "rebrowser_patches",
        "scrapy",
    ),
    TargetKind.URL: (
        "twscrape_raw",
        "twikit",
        "masa_twitter_scraper",
        "playwright",
        "scrapling",
        "crawl4ai",
        "camoufox",
        "patchright",
        "rebrowser_playwright",
        "rebrowser_patches",
        "scrapy",
    ),
    TargetKind.BOOKMARKS: (
        "twscrape_raw",
        "twikit",
        "x_web_graphql_bookmarks",
        "gallery_dl_bookmarks",
        "playwright_network_bookmarks",
        "playwright",
        "scrapling",
        "crawl4ai",
        "camoufox",
        "patchright",
        "rebrowser_playwright",
        "rebrowser_patches",
        "scrapy",
    ),
}


def run_pipeline(
    config: ExperimentConfig,
    out_dir: str | Path,
    *,
    storage_state: str | Path = ".secrets/playwright_x_state.json",
    twikit_cookies_file: str | Path = ".secrets/twikit_cookies.json",
    scweet_cookies_file: str | Path = ".secrets/scweet_cookies.json",
    masa_cookies_file: str | Path = ".secrets/masa_cookies.json",
    twscrape_accounts_db: str | Path = ".secrets/twscrape_accounts.db",
    min_successful_providers: int = 2,
    stop_after_first_success: bool = False,
    ok_with_any_items: bool = False,
) -> list[PipelineTargetResult]:
    output_path = Path(out_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    artifacts = SessionBroker(
        storage_state=storage_state,
        twikit_cookies_file=twikit_cookies_file,
        scweet_cookies_file=scweet_cookies_file,
        masa_cookies_file=masa_cookies_file,
        twscrape_accounts_db=twscrape_accounts_db,
    ).materialize()
    evidence = EvidenceStore(output_path / "evidence")

    enabled_configs = [adapter for adapter in config.adapters if adapter.enabled]
    configured_ids = tuple(adapter.adapter_id for adapter in enabled_configs)
    config_by_id = {
        adapter.adapter_id: _with_session_defaults(adapter, artifacts)
        for adapter in enabled_configs
    }

    results: list[PipelineTargetResult] = []
    attempt_index = 0
    for target in config.targets:
        chain = provider_chain_for(target.kind, configured_ids)
        merged: dict[str, XItem] = {}
        attempts: list[ProviderAttempt] = []
        successful_providers: list[str] = []

        for provider_id in chain:
            adapter_config = config_by_id.get(provider_id, AdapterConfig(provider_id))
            adapter = build_adapter(adapter_config)
            outcome = _safe_fetch(adapter, target)
            attempt_index += 1
            evidence_path = evidence.write_attempt(attempt_index, outcome)
            attempt = ProviderAttempt(
                provider_id=provider_id,
                target=target,
                outcome=outcome,
                failure_kind=classify_outcome(outcome),
                evidence_path=evidence_path,
            )
            attempts.append(attempt)

            mergeable_items = _items_for_target(target.kind, outcome.items)
            if mergeable_items:
                successful_providers.append(provider_id)
                _merge_items(merged, mergeable_items, provider_id)

            if stop_after_first_success and successful_providers:
                break

            if (
                len(merged) >= max(1, target.limit)
                and len(successful_providers) >= min_successful_providers
            ):
                break

        items = tuple(list(merged.values())[: max(1, target.limit)])
        provider_exhausted = any(_outcome_exhausted(attempt.outcome) for attempt in attempts)
        if (
            len(items) >= max(1, target.limit)
            or (provider_exhausted and items)
            or (ok_with_any_items and items)
        ):
            status = PipelineStatus.OK
        elif items:
            status = PipelineStatus.PARTIAL
        else:
            status = PipelineStatus.FAILED
        results.append(
            PipelineTargetResult(
                target=target,
                status=status,
                items=items,
                attempts=tuple(attempts),
                providers_used=tuple(successful_providers),
                metadata={
                    "chain": chain,
                    "session": _session_metadata(artifacts),
                    "min_successful_providers": min_successful_providers,
                    "stop_after_first_success": stop_after_first_success,
                    "ok_with_any_items": ok_with_any_items,
                    "provider_exhausted": provider_exhausted,
                },
            )
        )

    _write_pipeline_events(output_path / "pipeline_events.jsonl", results)
    _write_pipeline_items(output_path / "items.jsonl", results)
    _write_pipeline_report(output_path / "pipeline_report.json", config.name, results)
    return results


def provider_chain_for(kind: TargetKind, configured_ids: tuple[str, ...]) -> tuple[str, ...]:
    defaults = DEFAULT_CHAINS[kind]
    chain = [provider_id for provider_id in defaults if provider_id in configured_ids]
    extras = [provider_id for provider_id in configured_ids if provider_id not in chain]
    return tuple(chain + extras)


def classify_outcome(outcome: FetchOutcome) -> ProviderFailureKind:
    if outcome.status in (OutcomeStatus.OK, OutcomeStatus.PARTIAL):
        return ProviderFailureKind.NONE
    if outcome.status == OutcomeStatus.NOT_CONFIGURED:
        return ProviderFailureKind.NOT_CONFIGURED
    if outcome.status == OutcomeStatus.UNSUPPORTED:
        return ProviderFailureKind.UNSUPPORTED
    if outcome.status == OutcomeStatus.EMPTY:
        return ProviderFailureKind.EMPTY

    text = " ".join(
        item
        for item in (outcome.error_type or "", outcome.error_message or "")
        if item
    ).lower()
    if "timeout" in text:
        return ProviderFailureKind.TIMEOUT
    if "rate" in text or "429" in text:
        return ProviderFailureKind.RATE_LIMITED
    if "auth" in text or "login" in text or "403" in text or "401" in text:
        return ProviderFailureKind.AUTH_FAILED
    if "key_byte" in text or "transaction" in text or "xclid" in text:
        return ProviderFailureKind.TRANSACTION_FAILED
    if "graphql" in text or "schema" in text or "features cannot be null" in text:
        return ProviderFailureKind.SCHEMA_DRIFT
    if "selector" in text or "locator" in text or "article" in text:
        return ProviderFailureKind.DOM_DRIFT
    return ProviderFailureKind.ERROR


def _outcome_exhausted(outcome: FetchOutcome) -> bool:
    if outcome.status != OutcomeStatus.OK:
        return False
    metadata = outcome.metadata or {}
    return bool(
        metadata.get("cursor_exhausted")
        or metadata.get("timeline_exhausted")
        or metadata.get("finished")
    )


def _safe_fetch(adapter, target: AcquisitionTarget) -> FetchOutcome:
    try:
        return adapter.fetch(target)
    except Exception as exc:  # noqa: BLE001 - pipeline must isolate providers.
        now = utc_now()
        return FetchOutcome(
            adapter_id=adapter.adapter_id,
            target=target,
            status=OutcomeStatus.ERROR,
            started_at=now,
            finished_at=utc_now(),
            error_type=type(exc).__name__,
            error_message=str(exc),
        )


def _with_session_defaults(
    adapter_config: AdapterConfig,
    artifacts: SessionArtifacts,
) -> AdapterConfig:
    options = dict(adapter_config.options)
    if adapter_config.adapter_id in {
        "playwright",
        "x_web_graphql_bookmarks",
        "gallery_dl_bookmarks",
        "playwright_network_bookmarks",
        "crawl4ai",
        "camoufox",
        "patchright",
        "rebrowser_playwright",
        "rebrowser_patches",
        "scrapling",
        "scrapy",
    }:
        options.setdefault("storage_state", str(artifacts.storage_state))
    elif adapter_config.adapter_id == "twikit":
        options.setdefault("cookies_file", str(artifacts.twikit_cookies_file))
        options.setdefault("playwright_storage_state", str(artifacts.storage_state))
        options.setdefault("enable_ui_metrics", False)
    elif adapter_config.adapter_id == "scweet":
        options.setdefault("cookies_file", str(artifacts.scweet_cookies_file))
        options.setdefault("playwright_storage_state", str(artifacts.storage_state))
        options.setdefault("db_path", ".secrets/scweet_state.db")
    elif adapter_config.adapter_id == "twscrape_raw":
        options.setdefault("playwright_storage_state", str(artifacts.storage_state))
        options.setdefault("accounts_db", str(artifacts.twscrape_accounts_db))
    elif adapter_config.adapter_id == "masa_twitter_scraper":
        options.setdefault("cookies_file", str(artifacts.masa_cookies_file))
    return replace(adapter_config, options=options)


def _merge_items(merged: dict[str, XItem], items: tuple[XItem, ...], provider_id: str) -> None:
    for item in items:
        key = item.source_id or item.url or item.text or f"{provider_id}:{len(merged)}"
        if key not in merged:
            merged[key] = _with_provider(item, provider_id)
            continue
        merged[key] = _combine_item(merged[key], item, provider_id)


def _items_for_target(kind: TargetKind, items: tuple[XItem, ...]) -> tuple[XItem, ...]:
    if kind != TargetKind.BOOKMARKS:
        return items
    return tuple(item for item in items if item.raw.get("bookmark_root") is True)


def _combine_item(existing: XItem, incoming: XItem, provider_id: str) -> XItem:
    raw = dict(existing.raw)
    providers = list(raw.get("_providers", []))
    if provider_id not in providers:
        providers.append(provider_id)
    raw["_providers"] = providers
    raw.setdefault("_provider_raw", {})
    if isinstance(raw["_provider_raw"], dict):
        raw["_provider_raw"][provider_id] = incoming.raw
    return XItem(
        source_id=existing.source_id or incoming.source_id,
        url=existing.url or incoming.url,
        author=existing.author or incoming.author,
        text=existing.text or incoming.text,
        created_at=existing.created_at or incoming.created_at,
        observed_at=existing.observed_at,
        raw=raw,
    )


def _with_provider(item: XItem, provider_id: str) -> XItem:
    raw = dict(item.raw)
    raw["_providers"] = [provider_id]
    raw["_provider_raw"] = {provider_id: item.raw}
    return XItem(
        source_id=item.source_id,
        url=item.url,
        author=item.author,
        text=item.text,
        created_at=item.created_at,
        observed_at=item.observed_at,
        raw=raw,
    )


def _session_metadata(artifacts: SessionArtifacts) -> dict[str, Any]:
    return {
        "has_session": artifacts.has_session,
        "storage_state": str(artifacts.storage_state),
        "twikit_cookies_file": str(artifacts.twikit_cookies_file),
        "scweet_cookies_file": str(artifacts.scweet_cookies_file),
        "masa_cookies_file": str(artifacts.masa_cookies_file),
        "twscrape_accounts_db": str(artifacts.twscrape_accounts_db),
        "cookie_names": artifacts.cookie_names,
    }


def _write_pipeline_events(path: Path, results: list[PipelineTargetResult]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for result in results:
            handle.write(json.dumps(_jsonable(result), ensure_ascii=False, sort_keys=True) + "\n")


def _write_pipeline_items(path: Path, results: list[PipelineTargetResult]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for result in results:
            for item in result.items:
                handle.write(json.dumps(_jsonable(item), ensure_ascii=False, sort_keys=True) + "\n")


def _write_pipeline_report(
    path: Path,
    experiment_name: str,
    results: list[PipelineTargetResult],
) -> None:
    payload = {
        "experiment": experiment_name,
        "generated_at": utc_now(),
        "targets": [
            {
                "target": result.target,
                "status": result.status,
                "items": len(result.items),
                "providers_used": result.providers_used,
                "attempts": [
                    {
                        "provider_id": attempt.provider_id,
                        "status": attempt.outcome.status,
                        "failure_kind": attempt.failure_kind,
                        "items": len(attempt.outcome.items),
                        "latency_ms": attempt.outcome.latency_ms,
                        "evidence_path": attempt.evidence_path,
                    }
                    for attempt in result.attempts
                ],
            }
            for result in results
        ],
    }
    path.write_text(
        json.dumps(_jsonable(payload), ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def _jsonable(value: Any):
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if is_dataclass(value) and not isinstance(value, type):
        return _jsonable(asdict(value))
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if hasattr(value, "value"):
        return value.value
    return value
