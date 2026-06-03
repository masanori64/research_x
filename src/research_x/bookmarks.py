from __future__ import annotations

from pathlib import Path

from research_x.accounts import read_account_profile, resolve_account_paths
from research_x.bookmark_classifier import (
    BookmarkClassificationRun,
    BookmarkClassifierSettings,
    classify_bookmarks,
    load_bookmark_categories,
    write_bookmark_outputs,
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
from research_x.x_store import write_label_store_outputs, write_x_store_outputs

EXHAUSTIVE_BOOKMARK_LIMIT = 1_000_000_000
EXHAUSTIVE_BOOKMARK_MAX_PAGES = 100_000


def run_bookmark_job(
    *,
    out_dir: str | Path,
    account: str | None = None,
    storage_state: str | Path | None = None,
    limit: int = 100,
    headless: bool = True,
    timeout_ms: float = 45000,
    max_scroll_steps: int = 20,
    classify: bool = True,
    model: str = "gpt-4o-mini",
    api_key_env: str = "OPENAI_API_KEY",
    categories_path: str | Path | None = None,
    batch_size: int = 20,
    min_successful_providers: int = 1,
    download_media: bool = True,
    media_timeout_seconds: float = 30.0,
    classifier_provider: str = "openai_responses",
    api_base_url: str | None = None,
    db_path: str | Path | None = None,
    exhaustive: bool = False,
    reasoning_effort: str | None = None,
) -> tuple[PipelineTargetResult, BookmarkClassificationRun]:
    output_path = Path(out_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    categories = load_bookmark_categories(categories_path)
    paths = resolve_account_paths(account, storage_state=storage_state)
    profile = read_account_profile(account)

    resolved_limit = EXHAUSTIVE_BOOKMARK_LIMIT if exhaustive else max(1, limit)
    target = AcquisitionTarget(TargetKind.BOOKMARKS, "me", limit=resolved_limit)
    config = ExperimentConfig(
        name="x-bookmarks",
        targets=(target,),
        adapters=_bookmark_adapters(
            storage_state=paths.storage_state,
            output_path=output_path,
            headless=headless,
            timeout_ms=timeout_ms,
            max_scroll_steps=max_scroll_steps,
            limit=target.limit,
            exhaustive=exhaustive,
        ),
        timeout_seconds=180,
        max_concurrency=1,
    )
    result = run_pipeline(
        config,
        output_path,
        storage_state=paths.storage_state,
        twikit_cookies_file=paths.twikit_cookies_file,
        scweet_cookies_file=paths.scweet_cookies_file,
        masa_cookies_file=paths.masa_cookies_file,
        twscrape_accounts_db=paths.twscrape_accounts_db,
        min_successful_providers=min_successful_providers,
        stop_after_first_success=False,
        ok_with_any_items=False,
    )
    target_result = result[0]
    store_summary = write_x_store_outputs(
        output_path,
        items=target_result.items,
        collection_kind="bookmarks",
        target=target,
        account_id=paths.account_id,
        account_profile=profile,
        attempts=target_result.attempts,
        db_path=db_path,
        download_media=download_media,
        media_timeout_seconds=media_timeout_seconds,
    )

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
        write_label_store_outputs(
            store_summary.db_path,
            classifications=classification_run.classifications,
            label_scope="bookmarks",
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
                "reason": "classification disabled" if not classify else "no bookmark items",
                "store": store_summary,
            },
        )

    write_bookmark_outputs(
        output_path,
        items=target_result.items,
        classification_run=classification_run,
        categories=categories,
        store_summary=store_summary,
    )
    return target_result, classification_run


def _bookmark_adapters(
    *,
    storage_state: str | Path,
    output_path: Path,
    headless: bool,
    timeout_ms: float,
    max_scroll_steps: int,
    limit: int,
    exhaustive: bool,
) -> tuple[AdapterConfig, ...]:
    storage_state_text = str(storage_state)
    cursor_max_pages = (
        EXHAUSTIVE_BOOKMARK_MAX_PAGES
        if exhaustive
        else max(20, (max(1, limit) + 99) // 100 + 5)
    )
    direct_max_pages = (
        EXHAUSTIVE_BOOKMARK_MAX_PAGES
        if exhaustive
        else max(3, (max(1, limit) + 99) // 100 + 1)
    )
    return (
        AdapterConfig(
            "twscrape_raw",
            options={
                "playwright_storage_state": storage_state_text,
                "direct_graphql": True,
                "max_pages": direct_max_pages,
                "request_timeout_seconds": 90,
            },
        ),
        AdapterConfig(
            "twikit",
            options={
                "playwright_storage_state": storage_state_text,
                "enable_ui_metrics": False,
                "bookmark_page_size": 100,
                "request_timeout_seconds": 90,
            },
        ),
        AdapterConfig(
            "x_web_graphql_bookmarks",
            options={
                "storage_state": storage_state_text,
                "page_size": 100,
                "request_timeout_seconds": 90,
                "max_pages": cursor_max_pages,
                "raw_pages_dir": str(output_path / "bookmark_pages" / "x_web_graphql"),
                "cursor_state_file": str(
                    output_path / "bookmark_pages" / "x_web_graphql_cursor_state.json"
                ),
                "resume": True,
            },
        ),
        AdapterConfig(
            "gallery_dl_bookmarks",
            options={
                "storage_state": storage_state_text,
                "work_dir": str(output_path / "_gallery_dl"),
                "request_timeout_seconds": 180,
                "exhaustive": exhaustive,
            },
        ),
        AdapterConfig(
            "playwright_network_bookmarks",
            options={
                "storage_state": storage_state_text,
                "headless": headless,
                "timeout_ms": timeout_ms,
                "max_scroll_steps": max_scroll_steps,
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
            "crawl4ai",
            options={
                "storage_state": storage_state_text,
                "headless": headless,
                "request_timeout_seconds": 45,
                "max_scroll_steps": max_scroll_steps,
            },
        ),
        AdapterConfig(
            "camoufox",
            options={
                "storage_state": storage_state_text,
                "headless": headless,
                "timeout_ms": timeout_ms,
                "max_scroll_steps": max_scroll_steps,
            },
        ),
        AdapterConfig(
            "patchright",
            options={
                "storage_state": storage_state_text,
                "headless": headless,
                "timeout_ms": timeout_ms,
                "max_scroll_steps": max_scroll_steps,
            },
        ),
        AdapterConfig(
            "rebrowser_playwright",
            options={
                "storage_state": storage_state_text,
                "headless": headless,
                "timeout_ms": timeout_ms,
                "max_scroll_steps": max_scroll_steps,
            },
        ),
        AdapterConfig(
            "rebrowser_patches",
            options={
                "storage_state": storage_state_text,
                "headless": headless,
                "timeout_ms": timeout_ms,
                "max_scroll_steps": max_scroll_steps,
            },
        ),
        AdapterConfig(
            "scrapy",
            options={
                "storage_state": storage_state_text,
                "render_fallback": True,
                "request_timeout_seconds": 45,
                "max_scroll_steps": max_scroll_steps,
            },
        ),
    )
