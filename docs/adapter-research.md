# Adapter Research

Research date: 2026-05-20.

This document records the implementation posture for the requested acquisition methods. The
experiment harness keeps one normalized contract and treats each method as a candidate that must
earn promotion through the same metrics.

Important boundary: X's current Terms of Service state that crawling or scraping the service
without prior written consent is prohibited. Use this harness only with sources, accounts, APIs,
sessions, and targets you are authorized to access.

## Pipeline Role Order

The current implementation no longer treats these as one winner-takes-all promotion candidates.
They are composed as a staged acquisition pipeline:

1. `twscrape_raw`: fast primary GraphQL acquisition and raw normalization.
2. `scweet`: resume/backfill provider with its own state and account-pool model.
3. `twikit`: supplemental read provider for verification and rich-field comparison.
4. `masa_twitter_scraper`: independent Go sidecar fallback after Python-library/schema failures.
5. `playwright`: session source, network evidence, and DOM fallback.
6. `crawl4ai`, `camoufox`, `patchright`, `rebrowser_playwright`: browser/generic rendered
   fallbacks that can now acquire status links or tweet articles from the authorized session.
7. `scrapling`, `scrapy`, `rebrowser_patches`: generic/parser/patchset roles that now delegate
   to rendered fallback paths when static acquisition alone is insufficient.

## Findings

| Adapter | Layer | Auth/session model | Direct X fit | Implementation strategy |
| --- | --- | --- | --- | --- |
| `twscrape_raw` | X internal GraphQL/Search | Authorized accounts or cookies in twscrape DB | High | Wrap async raw methods, normalize payloads to `XItem`, score by search/profile/tweet fixtures. |
| `scweet` | X internal GraphQL | Authorized `auth_token`/cookies locally, or hosted Apify actor | High | Direct Python API adapter first; hosted actor can be separate later. |
| `twikit` | X internal API/web scraping | Authorized username/email/password or cookies file | Medium-high | Read-only wrapper around search/user/tweet methods; forbid writes in adapter scope. |
| `masa_twitter_scraper` | X frontend API | Mixed; README marks search as authenticated | Medium | Implemented as configurable Go sidecar JSONL contract; current local binary is `.secrets/bin/masa-twitter-scraper.exe`. |
| `crawl4ai` | Generic browser crawler | Authorized URL/session inputs | Low-medium | Implemented URL extraction fallback using authorized rendered HTML/markdown status links. |
| `camoufox` | Browser automation | Authorized browser sessions | Low-medium | Implemented browser runner variant sharing Playwright extraction; applies a local Firefox page-error guard for X. |
| `patchright` | Browser automation | Authorized browser sessions | Low-medium | Implemented Playwright-like runner variant, Chromium-only. |
| `rebrowser_patches` | Browser patchset | Authorized browser sessions | Low | Implemented by delegating the patchset role to the runnable `rebrowser_playwright` runtime. |
| `rebrowser_playwright` | Browser automation | Authorized browser sessions | Low-medium | Implemented Python Playwright-compatible runner sharing browser extraction. |
| `scrapy` | Generic HTTP crawler | Authorized HTTP targets | Low for X app | Implemented static HTTP first, then Scrapy selector parsing over rendered HTML. |
| `playwright` | Browser automation | Authorized browser sessions | Medium | Baseline browser implementation reused by browser variants. |
| `scrapling` | Adaptive crawler/browser | Authorized URL/session inputs | Medium | Implemented static Scrapling first, then PlayWrightFetcher rendered fallback. |

## Source Notes

- `twscrape`: GitHub README documents install, async API, login/session support, raw Twitter API
  responses, Search/GraphQL support, account switching, and many tweet/user methods.
  Source: https://github.com/vladkens/twscrape
- `Scweet`: GitHub README documents local Python/CLI use, auth-token cookie auth, profile
  timelines, followers/following, sync/async methods, resume, hosted Apify option, and release
  `Scweet v5.0` on 2026-03-20.
  Source: https://github.com/Altimis/Scweet
- `Twikit`: docs describe an async client, login, cookies file, proxy parameter, `search_tweet`,
  user lookup, tweet/user models, and broad automation features.
  Sources: https://twikit.readthedocs.io/en/latest/twikit.html and
  https://d60-twikit.mintlify.app/
- `masa-finance/twitter-scraper`: GitHub README describes Go frontend API scraping. Supported
  methods include tweet/profile reads; home timeline, tweet search, and profile search are marked
  as requiring authentication.
  Source: https://github.com/masa-finance/twitter-scraper
- `Crawl4AI`: docs describe `AsyncWebCrawler`, `BrowserConfig`, `CrawlerRunConfig`, markdown
  generation, CSS/XPath extraction, dynamic content handling, and `arun_many()`.
  Source: https://docs.crawl4ai.com/
- `Camoufox`: README describes a Playwright-compatible Python interface and current 2026
  maintenance/performance caveats.
  Source: https://github.com/daijro/camoufox
- `Patchright`: PyPI describes it as a Python Playwright drop-in replacement, Python >=3.9, with
  Chromium-only support.
  Source: https://pypi.org/project/patchright/
- `rebrowser-patches`: GitHub README describes patches for Puppeteer and Playwright.
  Source: https://github.com/rebrowser/rebrowser-patches
- `rebrowser-playwright`: npm describes it as original Playwright patched with
  `rebrowser-patches`.
  Source: https://www.npmjs.com/package/rebrowser-playwright
- `Scrapy`: official docs describe it as a high-level crawling/scraping framework for structured
  data, with feed exports, stats, AutoThrottle, jobs, and asyncio support.
  Source: https://docs.scrapy.org/
- `Playwright`: official Python docs describe modern browser-engine support and sync/async Python
  automation APIs.
  Source: https://playwright.dev/python/docs/intro
- `Scrapling`: docs describe adaptive scraping, fetchers, dynamic browser fetchers, and Scrapy-like
  spiders. PyPI lists version `0.4.8` released on 2026-05-11 and Python >=3.10.
  Sources: https://scrapling.readthedocs.io/en/latest/ and https://pypi.org/project/scrapling/
- X policy reference: current X Terms of Service prohibit crawling/scraping without prior written
  consent; X developer policy and guidelines govern API/content use.
  Sources: https://x.com/en/tos and https://docs.x.com/developer-guidelines

## Required Inputs Before Real Adapter Promotion

- Authorized credentials/sessions for each X-specific adapter under test.
- Allowed target fixtures: search queries, usernames, tweet URLs, and expected item counts.
- Ground-truth output fixtures for normalization and dedupe tests.
- Explicit per-adapter budgets: timeout, concurrency, daily caps, and stop conditions.
- Decision thresholds for promotion: minimum score, success rate, item yield, freshness, and
  maximum latency/error rate.
