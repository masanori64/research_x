# research-x

X acquisition framework for comparing adapters and composing them into a resilient tweet
acquisition pipeline.

The project has two execution modes:

- `run`: compare adapters under one normalized contract.
- `pipeline`: use adapters as staged providers with fallback, evidence, and reconciliation.
- `bookmarks` / `tweets`: production-shaped acquisition commands that write the same canonical
  tweet database.

The default setup is runnable without credentials using the `synthetic` adapter. Real providers
share the same interface and either return normalized tweets or a classified non-success outcome
with evidence.

This project does not implement protection bypassing or credential harvesting. Use only sources,
accounts, and APIs you are authorized to access, and keep adapter-specific limits in config.

## Quick start

```powershell
uv sync
uv run python -m research_x accounts add --account zvuvm6 --screen-name zvuvm6 --user-id 1630423227792244739
uv run python -m research_x auth auto --account zvuvm6 --channel msedge --no-headless
uv run patchright install chromium
uv run rebrowser_playwright install chromium
uv run python -m research_x run --config examples/smoke.toml --out runs/smoke
uv run python -m research_x pipeline --config examples/x_pipeline.toml --out runs/x_pipeline
uv run python -m research_x adapters --details
uv run pytest
uv run ruff check src tests
```

## Compare adapters

Edit `examples/smoke.toml` and add adapter ids from:

- `synthetic`
- `twscrape_raw`
- `scweet`
- `twikit`
- `masa_twitter_scraper`
- `crawl4ai`
- `camoufox`
- `patchright`
- `rebrowser_patches`
- `rebrowser_playwright`
- `scrapy`
- `playwright`
- `scrapling`

Registered adapters are concrete implementations. The full pipeline smoke currently exercises all
12 providers successfully against the authorized profile fixture.

The researched adapter catalog is available from:

```powershell
uv run python -m research_x adapters --details
uv run python -m research_x adapters --json
```

See [docs/adapter-research.md](docs/adapter-research.md) for the current source-backed findings
and implementation priority.

Authenticated smoke results for the provided target are tracked in
[docs/authenticated-smoke.md](docs/authenticated-smoke.md).

## Resilient pipeline

The pipeline mode is for production-style acquisition. It does not pick a single winning adapter.
It routes each target through a role-based chain:

```text
profile: twscrape_raw -> scweet -> twikit -> masa_twitter_scraper -> playwright -> browser/generic fallbacks
search:  scweet -> twscrape_raw -> twikit -> masa_twitter_scraper -> playwright -> browser/generic fallbacks
url:     twscrape_raw -> twikit -> masa_twitter_scraper -> playwright -> browser/generic fallbacks
bookmarks: twscrape_raw -> twikit -> raw Web GraphQL -> gallery-dl -> browser network -> browser/generic fallbacks
```

Each provider attempt writes evidence, failures are classified, and items are deduped by tweet id.
When `--account` is passed, session artifacts are isolated under `.secrets/accounts/<account>/`.

```powershell
uv run python -m research_x pipeline --config examples/x_pipeline.toml --out runs/x_pipeline --min-successful-providers 4
uv run python -m research_x pipeline --account zvuvm6 --config examples/x_pipeline.toml --out runs/x_pipeline_zvuvm6
```

The latest full-chain authenticated smoke forced all 12 registered providers to attempt the target:

```text
ok items=5 providers=twscrape_raw,scweet,twikit,masa_twitter_scraper,playwright,scrapling,crawl4ai,camoufox,patchright,rebrowser_playwright,rebrowser_patches,scrapy
```

Pipeline outputs:

- `pipeline_report.json`: target status, provider attempts, failure kinds, evidence paths.
- `pipeline_events.jsonl`: full per-target pipeline event.
- `items.jsonl`: final reconciled `XItem` rows.
- `evidence/*.json`: raw per-provider outcomes for diagnosis.

See [docs/pipeline.md](docs/pipeline.md) for provider roles and failure routing.

## Bookmarks

The bookmark command uses the logged-in X browser session and does not use the official X API.
It keeps only timeline-root bookmark tweets in `bookmarks_items.jsonl`; quoted tweets are stored as
child records and quote edges instead of being counted as extra bookmarks. It tries automatic
providers in order:

- `twscrape_raw`: direct cookie-session GraphQL through twscrape's bookmark methods.
- `twikit`: twikit `get_bookmarks`.
- `x_web_graphql_bookmarks`: direct replay of the web app's bookmark GraphQL request.
- `gallery_dl_bookmarks`: gallery-dl Twitter bookmark extractor with exported session cookies.
- `playwright_network_bookmarks`: browser opens bookmarks and captures GraphQL JSON responses.
- `playwright`, `scrapling`, `crawl4ai`: rendered fallback extraction.

## Automatic Auth

Manual browser login is no longer the only session path. `auth auto` tries these non-interactive
routes in order:

1. reuse an existing valid storage state,
2. build storage state from `auth_token` / `ct0` cookie env values,
3. run credential login from env values,
4. export cookies from an already running CDP browser.

Use environment variables so passwords are not written to command history or project files:

```powershell
$env:RESEARCH_X_X_USERNAME="zvuvm6"
$env:RESEARCH_X_X_PASSWORD="<password>"
$env:RESEARCH_X_X_EMAIL_OR_PHONE="<email-or-phone-if-X-asks>"
uv run python -m research_x auth auto --account zvuvm6 --channel msedge --no-headless
```

For fully headless operation, omit `--no-headless`. If the account has TOTP enabled, set
`RESEARCH_X_X_TOTP_SECRET`; if X sends a one-time verification code, set
`RESEARCH_X_X_VERIFICATION_CODE` for that run. CAPTCHA/security challenges are detected and routed
as auth failures; the project does not bypass them.

Run acquisition only:

```powershell
uv run python -m research_x bookmarks --out runs/bookmarks --limit 100 --no-classify
uv run python -m research_x bookmarks --account zvuvm6 --out runs/bookmarks_zvuvm6 --all --no-classify
```

Run acquisition plus AI genre grouping:

```powershell
$env:OPENAI_API_KEY="..."
uv run python -m research_x bookmarks --out runs/bookmarks --limit 100 --classify --model gpt-4o-mini
$env:GEMINI_API_KEY="..."
uv run python -m research_x bookmarks --account zvuvm6 --out runs/bookmarks_gemini --all --classify --classifier-provider gemini --categories examples/bookmark_categories.toml
```

OpenAI-compatible classifier providers are also supported:

```powershell
$env:QWEN_API_KEY="..."
uv run python -m research_x bookmarks --out runs/bookmarks_qwen --limit 100 --classify --classifier-provider qwen

$env:MOONSHOT_API_KEY="..."
uv run python -m research_x bookmarks --out runs/bookmarks_kimi --limit 100 --classify --classifier-provider kimi

$env:ZHIPU_API_KEY="..."
uv run python -m research_x bookmarks --out runs/bookmarks_glm --limit 100 --classify --classifier-provider glm

$env:GEMINI_API_KEY="..."
uv run python -m research_x bookmarks --out runs/bookmarks_gemini --limit 100 --classify --classifier-provider gemini
```

Outputs:

- `bookmarks_items.jsonl`: deduped fetched bookmarks.
- `bookmarks.jsonl`: root bookmark records.
- `account_bookmarks.jsonl`: account-to-bookmark relation rows.
- `collection_items.jsonl`: acquisition collection rows for bookmarks/profile/search/url runs.
- `tweets.jsonl`: canonical tweet records including quoted tweets.
- `tweet_edges.jsonl`: quote relationships between tweets.
- `media.jsonl` and `media/`: tweet media metadata and downloaded image files.
- `bookmark_trees.jsonl`: bookmark roots with nested quoted tweets.
- `bookmark_classifications.jsonl`: AI labels, tags, summaries, and confidence.
- `genres/*.jsonl`: bookmarks grouped by genre.
- `x_data.sqlite3`: canonical local SQLite database for UI and continued operation.
- `pipeline_report.json`: provider-by-provider acquisition evidence.

## Tweets

Profile/search/url tweet acquisition now writes into the same canonical store as bookmarks. The
tweet itself is keyed once by `tweet_id`; whether it appeared in bookmarks, a profile timeline, a
search, or a URL run is recorded in relation tables.

```powershell
uv run python -m research_x tweets --account zvuvm6 --kind profile --value @dogenzaka_pua --limit 100 --out runs/tweets_100 --db runs/x_data.sqlite3
uv run python -m research_x tweet-stages --account zvuvm6 --kind profile --value @dogenzaka_pua --stage-limits 100,200,300,400 --out runs/tweet_stages
```

`tweet-stages` is a stress/check command: it runs each limit in order and deletes per-stage
pipeline data by default, leaving only `tweet_stage_report.json`.

## Local Store

The shared SQLite store is intended as the stable base for later UI and repeated jobs:

- `tweets`: one canonical row per tweet id, shared by bookmarks and normal acquisition.
- `collection_items`: profile/search/url/bookmark run membership.
- `account_bookmarks`: per-login-account bookmark membership.
- `tweet_edges`: quote edges, keeping quote roots and quote children queryable.
- `media`: media metadata and local download paths.
- `provider_runs` and `raw_payloads`: evidence for debugging provider failures and schema drift.
- `ai_labels`: current AI genre labels; this replaces the earlier clustering direction.

## Outputs

Each run writes:

- `events.jsonl`: normalized per-adapter outcomes
- `report.json`: metrics, scores, and promotion decision

The promotion gate is configured in TOML and can require minimum score, success rate, freshness,
and item count before a candidate is promoted to `promoted`.

## What to provide for autonomous real-adapter work

- Test X accounts or API credentials explicitly authorized for the experiment.
- Allowed target set: search terms, usernames, URLs, expected volumes, and prohibited targets.
- Success definition: required fields, freshness window, dedupe rules, and acceptable loss.
- Operational limits: per-adapter rate limits, concurrency, timeouts, budgets, and stop conditions.
- Ground-truth fixtures: known tweets/users/searches with expected normalized output.
- Environment constraints: OS/browser availability, proxies only if you are authorized to use them,
  CI requirements, and where secrets should be stored.
- Promotion criteria: score weights and hard thresholds for moving a method to mainline.
