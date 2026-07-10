from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from research_x.accounts import read_account_profile, resolve_account_paths
from research_x.bookmark_classifier import (
    BookmarkClassificationRun,
    BookmarkClassifierSettings,
    classify_bookmarks,
    load_bookmark_categories,
    write_label_outputs,
)
from research_x.contracts import (
    AcquisitionTarget,
    AdapterConfig,
    ExperimentConfig,
    TargetKind,
    utc_now,
)
from research_x.pipeline import run_pipeline
from research_x.pipeline_contracts import PipelineTargetResult
from research_x.x_store import XStoreSummary, write_label_store_outputs, write_x_store_outputs


def run_tweet_job(
    *,
    out_dir: str | Path,
    kind: str,
    value: str,
    account: str | None = None,
    storage_state: str | Path | None = None,
    limit: int = 100,
    headless: bool = True,
    timeout_ms: float = 45000,
    max_scroll_steps: int = 20,
    min_successful_providers: int = 1,
    download_media: bool = False,
    media_download_policy: str | None = None,
    media_timeout_seconds: float = 30.0,
    db_path: str | Path | None = None,
    persist: bool = True,
    classify: bool = False,
    model: str = "gpt-4o-mini",
    api_key_env: str = "OPENAI_API_KEY",
    categories_path: str | Path | None = None,
    batch_size: int = 20,
    classifier_provider: str = "openai_responses",
    api_base_url: str | None = None,
    reasoning_effort: str | None = None,
) -> tuple[PipelineTargetResult, XStoreSummary | None, BookmarkClassificationRun]:
    output_path = Path(out_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    target_kind = TargetKind(kind)
    if target_kind == TargetKind.BOOKMARKS:
        raise ValueError("Use the bookmarks command for bookmark acquisition")
    target = AcquisitionTarget(target_kind, value, limit=max(1, limit))
    paths = resolve_account_paths(account, storage_state=storage_state)
    profile = read_account_profile(account)

    config = ExperimentConfig(
        name="x-tweets",
        targets=(target,),
        adapters=_tweet_adapters(
            storage_state=paths.storage_state,
            headless=headless,
            timeout_ms=timeout_ms,
            max_scroll_steps=max_scroll_steps,
        ),
        timeout_seconds=180,
        max_concurrency=1,
    )
    results = run_pipeline(
        config,
        output_path,
        storage_state=paths.storage_state,
        twikit_cookies_file=paths.twikit_cookies_file,
        scweet_cookies_file=paths.scweet_cookies_file,
        masa_cookies_file=paths.masa_cookies_file,
        twscrape_accounts_db=paths.twscrape_accounts_db,
        min_successful_providers=min_successful_providers,
        account_id=paths.account_id,
        account_profile=profile,
    )
    target_result = results[0]

    store_summary = None
    if persist:
        store_summary = write_x_store_outputs(
            output_path,
            items=target_result.items,
            collection_kind=target_kind.value,
            target=target,
            account_id=paths.account_id,
            account_profile=profile,
            attempts=target_result.attempts,
            db_path=db_path,
            download_media=download_media,
            media_download_policy=media_download_policy,
            media_timeout_seconds=media_timeout_seconds,
        )

    categories = load_bookmark_categories(categories_path)
    if classify and target_result.items:
        classification_run = classify_bookmarks(
            target_result.items,
            settings=BookmarkClassifierSettings(
                model=model,
                api_key_env=api_key_env,
                batch_size=batch_size,
                provider=classifier_provider,
                api_base_url=api_base_url,
                reasoning_effort=reasoning_effort,
            ),
            categories=categories,
        )
        write_label_outputs(
            output_path,
            items=target_result.items,
            classification_run=classification_run,
            categories=categories,
            item_filename="tweet_items.jsonl",
            classification_filename="tweet_classifications.jsonl",
            report_filename="tweet_label_report.json",
        )
        if store_summary is not None:
            write_label_store_outputs(
                store_summary.db_path,
                classifications=classification_run.classifications,
                label_scope=target_kind.value,
                account_id=paths.account_id,
                model=classification_run.model,
                generated_at=classification_run.generated_at,
            )
    else:
        classification_run = BookmarkClassificationRun(
            status="disabled" if not classify else "empty",
            model=model,
            generated_at=utc_now(),
            classifications=(),
            metadata={
                "api_key_env": api_key_env,
                "reason": "classification disabled" if not classify else "no tweet items",
            },
        )

    return target_result, store_summary, classification_run


def run_tweet_stage_job(
    *,
    out_dir: str | Path,
    kind: str,
    value: str,
    stage_limits: tuple[int, ...] = (100, 200, 300, 400),
    discard_stage_data: bool = True,
    **kwargs: Any,
) -> list[dict[str, Any]]:
    output_path = Path(out_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    stage_reports: list[dict[str, Any]] = []
    for limit in stage_limits:
        stage_dir = output_path / f"stage_{limit}"
        result, store_summary, classification = run_tweet_job(
            out_dir=stage_dir,
            kind=kind,
            value=value,
            limit=limit,
            persist=not discard_stage_data,
            classify=False,
            download_media=False,
            **kwargs,
        )
        stage_reports.append(
            {
                "limit": limit,
                "status": result.status.value,
                "items": len(result.items),
                "providers_used": result.providers_used,
                "classification": classification.status,
                "store": store_summary,
            }
        )
        if discard_stage_data and stage_dir.exists():
            shutil.rmtree(stage_dir)
    (output_path / "tweet_stage_report.json").write_text(
        json.dumps(_jsonable(stage_reports), ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return stage_reports


def _tweet_adapters(
    *,
    storage_state: str | Path,
    headless: bool,
    timeout_ms: float,
    max_scroll_steps: int,
) -> tuple[AdapterConfig, ...]:
    storage_state_text = str(storage_state)
    return (
        AdapterConfig(
            "twscrape_raw",
            options={
                "playwright_storage_state": storage_state_text,
                "direct_graphql": True,
                "request_timeout_seconds": 90,
            },
        ),
        AdapterConfig(
            "scweet",
            options={
                "playwright_storage_state": storage_state_text,
                "display_type": "Latest",
                "max_empty_pages": 1,
                "request_timeout_seconds": 75,
            },
        ),
        AdapterConfig(
            "twikit",
            options={
                "playwright_storage_state": storage_state_text,
                "enable_ui_metrics": False,
                "request_timeout_seconds": 90,
            },
        ),
        AdapterConfig(
            "masa_twitter_scraper",
            options={
                "request_timeout_seconds": 45,
            },
        ),
        AdapterConfig(
            "playwright",
            options={
                "storage_state": storage_state_text,
                "login": False,
                "headless": headless,
                "timeout_ms": timeout_ms,
                "max_scroll_steps": max_scroll_steps,
            },
        ),
        AdapterConfig(
            "scrapling",
            options={
                "storage_state": storage_state_text,
                "render_fallback": True,
                "request_timeout_seconds": 45,
            },
        ),
        AdapterConfig(
            "camoufox",
            options={
                "storage_state": storage_state_text,
                "headless": headless,
                "timeout_ms": timeout_ms,
            },
        ),
        AdapterConfig(
            "patchright",
            options={
                "storage_state": storage_state_text,
                "headless": headless,
                "timeout_ms": timeout_ms,
            },
        ),
        AdapterConfig(
            "rebrowser_playwright",
            options={
                "storage_state": storage_state_text,
                "headless": headless,
                "timeout_ms": timeout_ms,
            },
        ),
        AdapterConfig(
            "rebrowser_patches",
            options={
                "storage_state": storage_state_text,
                "headless": headless,
                "timeout_ms": timeout_ms,
            },
        ),
        AdapterConfig(
            "scrapy",
            options={
                "storage_state": storage_state_text,
                "request_timeout_seconds": 30,
                "render_fallback": True,
            },
        ),
    )


def _jsonable(value: Any):
    if isinstance(value, Path):
        return str(value)
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if hasattr(value, "__dataclass_fields__"):
        from dataclasses import asdict

        return _jsonable(asdict(value))
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if hasattr(value, "value"):
        return value.value
    return value
