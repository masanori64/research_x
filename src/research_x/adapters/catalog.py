from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class AdapterCatalogEntry:
    adapter_id: str
    display_name: str
    package_name: str
    language: str
    source_url: str
    acquisition_layer: str
    auth_model: str
    supported_targets: tuple[str, ...]
    readiness: str
    priority: int
    fit: str
    adapter_strategy: str
    blockers: tuple[str, ...]
    evidence: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


CATALOG: dict[str, AdapterCatalogEntry] = {
    "synthetic": AdapterCatalogEntry(
        adapter_id="synthetic",
        display_name="Synthetic",
        package_name="built-in",
        language="Python",
        source_url="local",
        acquisition_layer="fixture",
        auth_model="none",
        supported_targets=("search", "profile", "url"),
        readiness="implemented",
        priority=0,
        fit="contract and scoring smoke tests only",
        adapter_strategy="Keep as deterministic baseline and CI guardrail.",
        blockers=(),
        evidence=("Local deterministic adapter.",),
    ),
    "twscrape_raw": AdapterCatalogEntry(
        adapter_id="twscrape_raw",
        display_name="twscrape raw adapter",
        package_name="twscrape",
        language="Python",
        source_url="https://github.com/vladkens/twscrape",
        acquisition_layer="x_internal_graphql",
        auth_model="authorized X accounts or cookies in twscrape account DB",
        supported_targets=("search", "profile", "tweet_url", "bookmarks"),
        readiness="implemented_auth_blocked",
        priority=10,
        fit="strong first-line candidate for normalized tweet/search/profile reads",
        adapter_strategy=(
            "Use the async API raw methods first, then normalize Tweet/User payloads into XItem."
        ),
        blockers=(
            "Requires authorized account inventory or cookies.",
            "Undocumented X endpoints can break after platform changes.",
        ),
        evidence=(
            "README documents Search and GraphQL support, async functions, account sessions, "
            "raw responses, and account switching.",
            "README documents search, tweet details, replies, profiles, followers, media, "
            "and raw response methods.",
            "Installed twscrape API exposes bookmarks() and bookmarks_raw() using "
            "the Bookmarks GraphQL timeline.",
        ),
    ),
    "scweet": AdapterCatalogEntry(
        adapter_id="scweet",
        display_name="Scweet adapter",
        package_name="Scweet",
        language="Python",
        source_url="https://github.com/Altimis/Scweet",
        acquisition_layer="x_internal_graphql",
        auth_model="authorized browser auth_token/cookies or hosted Apify actor",
        supported_targets=("search", "profile", "followers", "following"),
        readiness="implemented_with_cookie_session",
        priority=20,
        fit="strong first-line candidate where resume, sync API, and file exports matter",
        adapter_strategy=(
            "Call Python API directly for local runs; optionally add a separate hosted-actor "
            "adapter later."
        ),
        blockers=(
            "Requires authorized cookies for local execution.",
            "Maintainer documents endpoint and cookie expiry risk.",
        ),
        evidence=(
            "README documents tweets, profile timelines, followers, following, user profiles, "
            "sync and async APIs.",
            "README states v5.0 release on Mar 20, 2026 and last verified working in Mar 2026.",
        ),
    ),
    "twikit": AdapterCatalogEntry(
        adapter_id="twikit",
        display_name="Twikit",
        package_name="twikit",
        language="Python",
        source_url="https://github.com/d60/twikit",
        acquisition_layer="x_internal_api",
        auth_model="authorized username/email/password or cookies file",
        supported_targets=("search", "profile", "tweet_url", "bookmarks"),
        readiness="implemented_upstream_blocked",
        priority=30,
        fit="capable read adapter, but isolate write-capable APIs from experiment scope",
        adapter_strategy=(
            "Wrap only read methods such as search_tweet and user lookup; block write methods "
            "in config."
        ),
        blockers=(
            "Requires authorized account credentials or stored cookies.",
            "Library includes write/DM/actions that must stay out of read-only experiments.",
        ),
        evidence=(
            "Docs describe an async Client, login, cookies_file support, proxy parameter, "
            "and search_tweet.",
            "Docs include get_bookmarks(count, cursor, folder_id) and bookmark folder APIs.",
        ),
    ),
    "x_web_graphql_bookmarks": AdapterCatalogEntry(
        adapter_id="x_web_graphql_bookmarks",
        display_name="X Web GraphQL Bookmarks",
        package_name="built-in/httpx+twikit constants",
        language="Python",
        source_url="local",
        acquisition_layer="x_internal_graphql",
        auth_model="authorized X cookies from Playwright storage state",
        supported_targets=("bookmarks",),
        readiness="implemented_with_cookie_session",
        priority=35,
        fit="direct raw Web GraphQL bookmark timeline cursor reader without official API",
        adapter_strategy=(
            "Replay the same authenticated GraphQL Bookmarks/BookmarkFolderTimeline requests "
            "used by the web app with cookie and csrf headers."
        ),
        blockers=(
            "Undocumented query ids and feature flags can drift.",
            "Requires valid auth_token and ct0 cookies.",
        ),
        evidence=(
            "Local twikit package exposes Bookmarks and BookmarkFolderTimeline GraphQL endpoints.",
            "Local twikit code shows cursor variables and bookmark timeline feature flags.",
        ),
    ),
    "gallery_dl_bookmarks": AdapterCatalogEntry(
        adapter_id="gallery_dl_bookmarks",
        display_name="gallery-dl Bookmarks",
        package_name="gallery-dl",
        language="Python",
        source_url="https://github.com/mikf/gallery-dl",
        acquisition_layer="third_party_x_extractor",
        auth_model="authorized X cookies exported to Netscape cookie file",
        supported_targets=("bookmarks",),
        readiness="implemented_optional_dependency",
        priority=36,
        fit="independent mature extractor path for X bookmark exports and media metadata",
        adapter_strategy=(
            "Run gallery-dl metadata-only against https://x.com/i/bookmarks, parse JSON output, "
            "and normalize tweet metadata."
        ),
        blockers=(
            "Extractor behavior depends on upstream gallery-dl's Twitter/X support.",
            "Cookie export must remain valid.",
        ),
        evidence=(
            "gallery-dl supported-sites documentation lists Twitter/X Bookmarks with cookies.",
            "gallery-dl source includes TwitterBookmarkExtractor for /i/bookmarks.",
        ),
    ),
    "masa_twitter_scraper": AdapterCatalogEntry(
        adapter_id="masa_twitter_scraper",
        display_name="masa-finance/masa-twitter-scraper",
        package_name="github.com/masa-finance/twitter-scraper",
        language="Go",
        source_url="https://github.com/masa-finance/twitter-scraper",
        acquisition_layer="x_frontend_api",
        auth_model="mixed; some public methods, authenticated search/profile search per README",
        supported_targets=("profile", "tweet_url", "search"),
        readiness="implemented_sidecar_contract",
        priority=40,
        fit="useful independent Go baseline, especially for tweet/profile reads",
        adapter_strategy=(
            "Run a configured Go/CLI sidecar that emits JSONL, then normalize sidecar "
            "output in Python."
        ),
        blockers=(
            "Requires Go toolchain or prebuilt binary.",
            "Search methods require authentication according to the README.",
        ),
        evidence=(
            "README describes frontend API scraping in Go and supported tweet/profile methods.",
            "README marks home timeline, search tweets, and search profiles as requiring "
            "authentication.",
        ),
    ),
    "crawl4ai": AdapterCatalogEntry(
        adapter_id="crawl4ai",
        display_name="Crawl4AI",
        package_name="crawl4ai",
        language="Python",
        source_url="https://docs.crawl4ai.com/",
        acquisition_layer="generic_browser_crawler",
        auth_model="authorized URL/session inputs",
        supported_targets=("url", "bookmarks"),
        readiness="implemented_generic_url",
        priority=80,
        fit="generic extraction fallback, not an X-specific first-line candidate",
        adapter_strategy=(
            "Use for URL-level extraction with CSS/XPath/markdown output, not for high-volume "
            "X search."
        ),
        blockers=(
            "X's dynamic app and access policy make it a fragile direct acquisition source.",
            "Needs per-page extraction schema and allowed URL fixtures.",
        ),
        evidence=(
            "Docs describe AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, markdown "
            "generation, and CSS/XPath extraction.",
            "Docs describe arun_many for multi-URL concurrency and dynamic page support.",
        ),
    ),
    "camoufox": AdapterCatalogEntry(
        adapter_id="camoufox",
        display_name="Camoufox",
        package_name="camoufox",
        language="Python",
        source_url="https://github.com/daijro/camoufox",
        acquisition_layer="browser_automation",
        auth_model="authorized browser sessions only",
        supported_targets=("url",),
        readiness="implemented_browser_variant",
        priority=90,
        fit="browser fallback for authorized UI-level experiments; high maintenance burden",
        adapter_strategy=(
            "Treat as an optional browser runner behind the same URL adapter contract."
        ),
        blockers=(
            "Browser build/runtime maintenance is heavier than API-style adapters.",
            "Repository notes performance and fingerprint-consistency caveats as of 2026.",
        ),
        evidence=(
            "README describes a Playwright-compatible Python interface and active browser "
            "development locations.",
            "README notes current maintenance/performance caveats and ongoing development in 2026.",
        ),
    ),
    "patchright": AdapterCatalogEntry(
        adapter_id="patchright",
        display_name="Patchright",
        package_name="patchright",
        language="Python",
        source_url="https://pypi.org/project/patchright/",
        acquisition_layer="browser_automation",
        auth_model="authorized browser sessions only",
        supported_targets=("url",),
        readiness="implemented_browser_variant",
        priority=95,
        fit="drop-in Playwright comparison runner; not X-specific",
        adapter_strategy=(
            "Keep as a browser execution variant for authorized URL fixtures, sharing "
            "Playwright extraction code."
        ),
        blockers=(
            "Chromium-only per package documentation.",
            "Patch behavior can drift with upstream Playwright versions.",
        ),
        evidence=(
            "PyPI describes Patchright as a Python Playwright drop-in replacement.",
            "PyPI metadata lists Python >=3.9 and Apache-2.0.",
        ),
    ),
    "rebrowser_patches": AdapterCatalogEntry(
        adapter_id="rebrowser_patches",
        display_name="rebrowser-patches",
        package_name="rebrowser-patches",
        language="Node.js",
        source_url="https://github.com/rebrowser/rebrowser-patches",
        acquisition_layer="browser_automation_patchset",
        auth_model="authorized browser sessions only",
        supported_targets=("url",),
        readiness="implemented_patchset_marker",
        priority=110,
        fit="patchset input for JS browser runner, not a standalone X adapter",
        adapter_strategy=(
            "Represent as a Node sidecar variant that patches Playwright/Puppeteer before "
            "running fixtures."
        ),
        blockers=(
            "Requires Node package management and patched dependency isolation.",
            "Not useful without a separate extraction runner.",
        ),
        evidence=(
            "README describes patches for Puppeteer and Playwright.",
            "Repository release list shows latest v1.0.19 on May 9, 2025.",
        ),
    ),
    "rebrowser_playwright": AdapterCatalogEntry(
        adapter_id="rebrowser_playwright",
        display_name="rebrowser-playwright",
        package_name="rebrowser-playwright",
        language="Node.js",
        source_url="https://www.npmjs.com/package/rebrowser-playwright",
        acquisition_layer="browser_automation",
        auth_model="authorized browser sessions only",
        supported_targets=("url",),
        readiness="implemented_browser_variant",
        priority=105,
        fit="Node Playwright variant for browser fixture comparison, not X-specific",
        adapter_strategy=(
            "Run a Node sidecar that emits normalized JSONL from authorized URL fixtures."
        ),
        blockers=(
            "Requires Node.js sidecar contract.",
            "npm package versions can lag upstream Playwright.",
        ),
        evidence=(
            "npm describes it as original Playwright patched with rebrowser-patches.",
            "npm package is a drop-in replacement for Playwright with matching major/minor "
            "versions.",
        ),
    ),
    "scrapy": AdapterCatalogEntry(
        adapter_id="scrapy",
        display_name="Scrapy",
        package_name="scrapy",
        language="Python",
        source_url="https://docs.scrapy.org/",
        acquisition_layer="generic_http_crawler",
        auth_model="authorized HTTP targets only",
        supported_targets=("url",),
        readiness="implemented_generic_http",
        priority=120,
        fit="excellent crawler baseline, weak direct fit for X's JS-heavy app",
        adapter_strategy=(
            "Use for static/HTTP fixtures and as a control against browser-based adapters."
        ),
        blockers=(
            "Needs browser integration or alternate feed source for dynamic X pages.",
            "Not an X-specific acquisition library.",
        ),
        evidence=(
            "Docs define Scrapy as a high-level crawling and scraping framework for "
            "structured data.",
            "Docs include feed exports, stats, AutoThrottle, jobs, asyncio, and dynamic "
            "content guidance.",
        ),
    ),
    "playwright": AdapterCatalogEntry(
        adapter_id="playwright",
        display_name="Playwright",
        package_name="playwright",
        language="Python",
        source_url="https://playwright.dev/python/docs/intro",
        acquisition_layer="browser_automation",
        auth_model="authorized browser sessions only",
        supported_targets=("url", "bookmarks"),
        readiness="implemented_promoted_with_manual_cdp_session",
        priority=70,
        fit="baseline browser automation adapter and shared extraction implementation",
        adapter_strategy=(
            "Implement first among browser adapters, then reuse extraction for "
            "Patchright/Camoufox variants."
        ),
        blockers=(
            "Requires browser install step and stable authorized fixtures.",
            "DOM selectors for X can drift frequently.",
        ),
        evidence=(
            "Official docs describe Chromium, WebKit, Firefox support and sync/async Python APIs.",
            "Official docs describe general-purpose browser automation beyond end-to-end tests.",
        ),
    ),
    "playwright_network_bookmarks": AdapterCatalogEntry(
        adapter_id="playwright_network_bookmarks",
        display_name="Playwright Network Bookmarks",
        package_name="playwright",
        language="Python",
        source_url="https://playwright.dev/python/docs/network",
        acquisition_layer="browser_network_capture",
        auth_model="authorized browser storage state",
        supported_targets=("bookmarks",),
        readiness="implemented_browser_network_fallback",
        priority=72,
        fit="fallback that captures bookmark GraphQL JSON responses from the logged-in browser",
        adapter_strategy=(
            "Open the bookmark timeline, listen to GraphQL network responses, and normalize "
            "responses instead of relying on DOM text."
        ),
        blockers=(
            "Still scrolls the UI, so it is not the first choice for very large exports.",
            "Depends on X web response structure.",
        ),
        evidence=(
            "Playwright supports response event handling and storage state reuse.",
            "X bookmark page loads GraphQL bookmark timeline responses in the browser session.",
        ),
    ),
    "scrapling": AdapterCatalogEntry(
        adapter_id="scrapling",
        display_name="Scrapling adapter",
        package_name="scrapling",
        language="Python",
        source_url="https://scrapling.readthedocs.io/en/latest/",
        acquisition_layer="adaptive_crawler",
        auth_model="authorized URL/session inputs",
        supported_targets=("url",),
        readiness="implemented_generic_url",
        priority=75,
        fit="strong generic crawler/browser fallback with adaptive selectors",
        adapter_strategy=(
            "Use DynamicFetcher or Spider for URL fixtures, returning normalized extraction "
            "evidence."
        ),
        blockers=(
            "Requires Python >=3.10 and optional fetcher/browser dependencies.",
            "Not an X-specific search/profile API adapter.",
        ),
        evidence=(
            "Docs describe adaptive scraping, Fetcher/StealthyFetcher/DynamicFetcher, "
            "and Scrapy-like spiders.",
            "PyPI lists version 0.4.8 released May 11, 2026 and Python >=3.10.",
        ),
    ),
}


def get_catalog_entry(adapter_id: str) -> AdapterCatalogEntry:
    return CATALOG[adapter_id]


def catalog_entries() -> tuple[AdapterCatalogEntry, ...]:
    return tuple(CATALOG[key] for key in sorted(CATALOG, key=lambda item: CATALOG[item].priority))
