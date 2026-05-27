# Authenticated Smoke Results

Run date: 2026-05-21 JST.

Login account used for smoke: `@sample_login`.
Target account: `@target_user`.

No password or live cookie value is stored in tracked files. Local auth artifacts, adapter state,
and built sidecar binaries stay under ignored `.secrets/`.

## Complete Pipeline Result

Command:

```powershell
uv run python -m research_x pipeline --config examples\x_pipeline.toml --out runs\x_pipeline_complete_2 --min-successful-providers 12
```

Result:

```text
profile:@target_user: ok items=5 providers=twscrape_raw,scweet,twikit,masa_twitter_scraper,playwright,scrapling,crawl4ai,camoufox,patchright,rebrowser_playwright,rebrowser_patches,scrapy
```

Every registered provider returned `ok` with 5 items in the final full-chain smoke.

| Adapter | Result |
| --- | --- |
| `twscrape_raw` | 5 tweets via authorized cookie-session GraphQL. |
| `scweet` | 5 tweets via Scweet and Playwright-derived cookies. |
| `twikit` | 5 tweets via Twikit cookie session. |
| `masa_twitter_scraper` | 5 tweets via the Go sidecar in `.secrets/bin/masa-twitter-scraper.exe`. |
| `playwright` | 5 tweet articles via authorized browser storage state. |
| `scrapling` | 5 tweets through Scrapling's PlayWrightFetcher render fallback. |
| `crawl4ai` | 5 tweets through Crawl4AI/rendered fallback extraction. |
| `camoufox` | 5 tweet articles with the local Playwright Firefox page-error guard. |
| `patchright` | 5 tweet articles through the shared browser extraction path. |
| `rebrowser_playwright` | 5 tweet articles through the shared browser extraction path. |
| `rebrowser_patches` | 5 tweet articles by delegating the patchset role to `rebrowser_playwright`. |
| `scrapy` | 5 tweets by parsing rendered HTML through Scrapy's selector layer. |

## Auth Input

The working path uses a normal browser login exported to:

```powershell
.secrets/playwright_x_state.json
```

That storage state is reused by browser adapters, converted to cookies for Twikit/Scweet/Masa,
and used as a cookie source for twscrape direct GraphQL.

If the storage state expires, refresh it with an interactive browser flow:

```powershell
uv run python -m research_x auth system-profile `
  --storage-state .secrets/playwright_x_state.json `
  --browser msedge `
  --profile-directory Default `
  --close-existing-browser
```
