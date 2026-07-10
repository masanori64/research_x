from __future__ import annotations

from collections.abc import Callable

from research_x.adapters.bookmark_adapters import (
    GalleryDLBookmarksAdapter,
    PlaywrightNetworkBookmarksAdapter,
    XWebGraphQLBookmarksAdapter,
)
from research_x.adapters.browser_variant_adapters import (
    CamoufoxAdapter,
    PatchrightAdapter,
    RebrowserPlaywrightAdapter,
)
from research_x.adapters.generic_url_adapters import (
    Crawl4AIAdapter,
    ScraplingAdapter,
    ScrapyAdapter,
)
from research_x.adapters.masa_twitter_scraper_adapter import MasaTwitterScraperAdapter
from research_x.adapters.playwright_adapter import PlaywrightAdapter
from research_x.adapters.rebrowser_patches_adapter import RebrowserPatchesAdapter
from research_x.adapters.scweet_adapter import ScweetAdapter
from research_x.adapters.synthetic import SyntheticAdapter
from research_x.adapters.twikit_adapter import TwikitAdapter
from research_x.adapters.twscrape_raw_adapter import TwscrapeRawAdapter
from research_x.contracts import AdapterConfig, XAdapter

AdapterFactory = Callable[[AdapterConfig], XAdapter]


_FACTORIES: dict[str, AdapterFactory] = {
    "synthetic": SyntheticAdapter,
    "twscrape_raw": TwscrapeRawAdapter,
    "scweet": ScweetAdapter,
    "twikit": TwikitAdapter,
    "masa_twitter_scraper": MasaTwitterScraperAdapter,
    "crawl4ai": Crawl4AIAdapter,
    "camoufox": CamoufoxAdapter,
    "patchright": PatchrightAdapter,
    "rebrowser_patches": RebrowserPatchesAdapter,
    "rebrowser_playwright": RebrowserPlaywrightAdapter,
    "scrapy": ScrapyAdapter,
    "playwright": PlaywrightAdapter,
    "scrapling": ScraplingAdapter,
    "x_web_graphql_bookmarks": XWebGraphQLBookmarksAdapter,
    "gallery_dl_bookmarks": GalleryDLBookmarksAdapter,
    "playwright_network_bookmarks": PlaywrightNetworkBookmarksAdapter,
}


def build_adapter(config: AdapterConfig) -> XAdapter:
    try:
        return _FACTORIES[config.adapter_id](config)
    except KeyError as exc:
        known = ", ".join(known_adapter_ids())
        raise ValueError(f"unknown adapter '{config.adapter_id}'. Known adapters: {known}") from exc


def known_adapter_ids() -> tuple[str, ...]:
    return tuple(sorted(_FACTORIES))
