# Resilient X Acquisition Pipeline

This mode uses the adapters as cooperating providers instead of selecting one winner.

## Provider Roles

| Provider | Pipeline role |
| --- | --- |
| `twscrape_raw` | Fast primary GraphQL acquisition and raw normalization. |
| `scweet` | Resume/backfill provider with its own SQLite state and account pool model. |
| `twikit` | Supplemental read provider for user/tweet/search checks and rich field comparison. |
| `masa_twitter_scraper` | Independent Go sidecar fallback for Python-library/schema failures. |
| `playwright` | Session source, browser/network evidence provider, and DOM fallback. |
| `scrapling` | Scrapling static fetch first, then PlayWrightFetcher rendered fallback. |
| `crawl4ai` | Browser crawler fallback that extracts status URLs from authorized rendered HTML, then shared browser fallback if needed. |
| `scrapy` | Static HTTP fetch first, then Scrapy selector parsing over rendered HTML. |
| `camoufox`, `patchright`, `rebrowser-*` | Browser variants when normal Playwright launch/runtime behavior is the blocker. |

## Default Chains

```text
profile:
  twscrape_raw -> scweet -> twikit -> masa_twitter_scraper -> playwright
  -> scrapling -> crawl4ai -> camoufox -> patchright -> rebrowser_playwright
  -> rebrowser_patches -> scrapy

search:
  scweet -> twscrape_raw -> twikit -> masa_twitter_scraper -> playwright
  -> scrapling -> crawl4ai -> camoufox -> patchright -> rebrowser_playwright
  -> rebrowser_patches -> scrapy

url:
  twscrape_raw -> twikit -> masa_twitter_scraper -> playwright
  -> scrapling -> crawl4ai -> camoufox -> patchright -> rebrowser_playwright
  -> rebrowser_patches -> scrapy

bookmarks:
  twscrape_raw -> twikit -> x_web_graphql_bookmarks -> gallery_dl_bookmarks
  -> playwright_network_bookmarks -> playwright -> scrapling -> crawl4ai
  -> camoufox -> patchright -> rebrowser_playwright -> rebrowser_patches -> scrapy
```

The chain stops when the target has enough deduped items and the configured minimum number of
successful providers has been reached.

## Session Broker

`SessionBroker` takes `.secrets/playwright_x_state.json` as canonical session input and
materializes provider-specific files:

- `.secrets/twikit_cookies.json`
- `.secrets/scweet_cookies.json`
- `.secrets/masa_cookies.json`

Reports include only cookie names and file paths, not live cookie values.

For account switching, pass `--account <id>`. The broker then uses:

- `.secrets/accounts/<id>/playwright_x_state.json`
- `.secrets/accounts/<id>/twikit_cookies.json`
- `.secrets/accounts/<id>/scweet_cookies.json`
- `.secrets/accounts/<id>/masa_cookies.json`
- `.secrets/accounts/<id>/twscrape_accounts.db`

Only non-password account metadata is stored by `accounts add`.

## Automatic Auth Routes

`auth auto` removes the normal human login step from the pipeline. It attempts:

1. existing storage state,
2. cookie env values,
3. saved persistent Playwright profile,
4. CDP export from a running browser,
5. optional normal Edge/Chrome profile export,
6. username/password env login.

```powershell
$env:RESEARCH_X_X_USERNAME="my_screen_name"
$env:RESEARCH_X_X_PASSWORD="<password>"
$env:RESEARCH_X_X_EMAIL_OR_PHONE="<email-or-phone-if-required>"
uv run python -m research_x auth auto `
  --account my_account `
  --try-system-browser-profile `
  --system-browser-profile-directory Default `
  --system-browser-profile-close-existing `
  --channel msedge `
  --no-headless
```

For a PC-standard Edge profile that is already logged in to X, close all Edge windows first
and export through CDP without passing a separate `--user-data-dir`:

```powershell
uv run python -m research_x auth system-profile `
  --account my_account `
  --browser msedge `
  --profile-directory Default `
  --close-existing-browser
```

If Edge was launched manually with `--remote-debugging-port=9222`, use the existing CDP
route:

```powershell
uv run python -m research_x auth cdp `
  --account my_account `
  --endpoint-url http://127.0.0.1:9222
```

The credential route can also be called directly:

```powershell
uv run python -m research_x auth credentials --account my_account --channel msedge --no-headless
```

Credentials are read only from env vars by default. CAPTCHA or hard security challenges are
detected and reported as auth failures, then `auth auto` continues to the next configured route.

## Failure Classification

Provider attempts are classified as:

- `not_configured`
- `unsupported`
- `empty`
- `timeout`
- `rate_limited`
- `auth_failed`
- `transaction_failed`
- `schema_drift`
- `dom_drift`
- `error`

Every attempt writes an evidence JSON file under `runs/<run>/evidence/`.

## Bookmark Pipeline

Bookmark acquisition is separate because bookmarks require the logged-in user's private session and
the official X API is intentionally not used. The final merged item list keeps only bookmark
timeline roots. Quoted tweets are saved as child tweet records and `quote` edges, so a quoted tweet
that is also independently bookmarked has one canonical tweet row, one bookmark row, and one quote
edge from the quoting tweet. The automatic routes are:

| Provider | Route |
| --- | --- |
| `twscrape_raw` | twscrape `bookmarks()` / `bookmarks_raw()` with the saved cookie session. |
| `twikit` | twikit `get_bookmarks(count, cursor, folder_id)`. |
| `x_web_graphql_bookmarks` | Direct Web GraphQL `Bookmarks` / `BookmarkFolderTimeline` replay. |
| `gallery_dl_bookmarks` | gallery-dl `TwitterBookmarkExtractor` with Netscape cookies. |
| `playwright_network_bookmarks` | Browser opens `/i/bookmarks` and captures GraphQL JSON responses. |
| `playwright`, `scrapling`, `crawl4ai` | Rendered fallback extraction. |

```powershell
uv run python -m research_x bookmarks --out runs\bookmarks --limit 100 --no-classify
uv run python -m research_x bookmarks --out runs\bookmarks --limit 100 --classify --model gpt-4o-mini
```

The command also writes DB-friendly files:

- `account_bookmarks.jsonl`
- `collection_items.jsonl`
- `bookmarks.jsonl`
- `tweets.jsonl`
- `tweet_edges.jsonl`
- `media.jsonl`
- `media/`
- `bookmark_trees.jsonl`
- `x_data.sqlite3`

Classifier provider presets use OpenAI-compatible Chat Completions for small classification models:
`qwen`, `kimi`, `glm`, and `gemini`.

## Shared Store

Bookmarks and normal tweet acquisition now converge into the same local SQLite schema. `tweets` is
the canonical table keyed by `tweet_id`; `account_bookmarks` records which login account bookmarked
that tweet; `collection_items` records which profile/search/url/bookmark acquisition run saw it.
This prevents the same tweet from becoming two separate records when it is found both through
bookmarks and through profile/search retrieval.

The current AI labeling result is stored as `ai_labels`. No clustering pipeline is assumed.

```powershell
uv run python -m research_x bookmarks --account my_account --out runs\bookmarks_my_account --all --db runs\x_data.sqlite3 --classifier-provider gemini --categories examples\bookmark_categories.toml
uv run python -m research_x tweets --account my_account --kind profile --value @target_user --limit 100 --out runs\tweets_100 --db runs\x_data.sqlite3
uv run python -m research_x tweet-stages --account my_account --kind profile --value @target_user --stage-limits 100,200,300,400 --out runs\tweet_stages
```

## Verified Smoke

Command:

```powershell
uv run python -m research_x pipeline --config examples\x_pipeline.toml --out runs\x_pipeline_complete_2 --min-successful-providers 12
```

Observed result:

```text
profile:@target_user: ok items=5 providers=twscrape_raw,scweet,twikit,masa_twitter_scraper,playwright,scrapling,crawl4ai,camoufox,patchright,rebrowser_playwright,rebrowser_patches,scrapy
```

Final full-chain provider states:

| Provider | Status | Items |
| --- | --- | ---: |
| `twscrape_raw` | `ok` | 5 |
| `scweet` | `ok` | 5 |
| `twikit` | `ok` | 5 |
| `masa_twitter_scraper` | `ok` | 5 |
| `playwright` | `ok` | 5 |
| `scrapling` | `ok` | 5 |
| `crawl4ai` | `ok` | 5 |
| `camoufox` | `ok` | 5 |
| `patchright` | `ok` | 5 |
| `rebrowser_playwright` | `ok` | 5 |
| `rebrowser_patches` | `ok` | 5 |
| `scrapy` | `ok` | 5 |
