# research-x

AI-oriented project reference for the X acquisition and local knowledge-store codebase.

`research-x` is an experimental framework for collecting X/Twitter tweets and bookmarks without
the official X API, comparing multiple acquisition providers under one normalized contract, and
storing the results in a canonical local SQLite database. The current production-shaped surface is
bookmark/tweet acquisition, account-scoped browser session handling, media capture, AI labeling,
and a local web app for running and monitoring jobs.

## Current Mission

The repository has two phases:

1. **Acquisition base, current state**  
   Collect profile/search/url tweets and logged-in bookmarks, preserve raw evidence, normalize
   tweet/media/quote relationships, and keep account-specific bookmark membership in one local DB.

2. **Local AI memory search, next project**  
   Build a local, user-specific search tool over the collected X DB. This should behave more like
   an AI-callable local research tool than a simple viewer: compact evidence bundles, hybrid
   retrieval, Corpus2Skill navigation, freshness/obsolete handling, and feedback-driven growth.

This README describes the current acquisition base accurately so future agents can work from it
without losing context.

## Safety and Scope

- Do not commit passwords, cookies, storage states, API keys, or real account secrets.
- `.secrets/` and `runs/` are ignored and should remain local.
- Use only accounts, browser sessions, and targets the operator is authorized to access.
- The project does not implement CAPTCHA/security-challenge bypassing. Challenge states should be
  reported as auth failures.
- Prefer extending the canonical DB and CLI over one-off scripts.

## Required Commands

This project uses `uv`. Do not run global `python`, `pytest`, or `ruff` directly.

```powershell
uv sync
uv run python -m research_x run --config examples/smoke.toml --out runs/smoke
uv run pytest
uv run ruff check src\research_x tests
```

## Main CLI Surfaces

```text
run             Compare adapters under one normalized contract.
pipeline        Run staged acquisition providers with fallback and evidence.
bookmarks       Fetch logged-in X bookmarks into the canonical store.
tweets          Fetch profile/search/url tweets into the canonical store.
tweet-stages    Run staged tweet-limit checks, usually discarding stage outputs.
db-show         Display stored bookmark/tweet text from the SQLite DB.
label-existing  Classify already stored, unlabeled DB rows.
accounts        Manage account metadata and account-scoped session paths.
auth            Capture or reuse authorized browser/session state.
app             Start the local browser app.
progress        Start a standalone live progress monitor for an output directory.
notify          Play/speak a local completion notification.
adapters        List provider catalog and source-backed adapter notes.
```

## Providers

Registered acquisition adapters include:

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

Use:

```powershell
uv run python -m research_x adapters --details
uv run python -m research_x adapters --json
```

See also:

- `docs/adapter-research.md`
- `docs/pipeline.md`
- `docs/authenticated-smoke.md`

## Canonical Store

The stable local store is SQLite, normally `runs/x_data.sqlite3`.

Current tables:

- `accounts`: non-secret account metadata.
- `provider_runs`: provider attempt evidence and status.
- `tweets`: one canonical row per tweet id.
- `collection_items`: profile/search/url/bookmark run membership.
- `account_bookmarks`: per-login-account bookmark membership.
- `tweet_edges`: quote relationships and future tweet graph edges.
- `media`: image/media metadata and local download state.
- `raw_payloads`: raw provider payloads for debugging and schema drift.
- `ai_labels`: current AI labeling output.

Important invariant: quote tweets are stored as child tweets/edges, not counted as separate
bookmark roots unless they are also independently bookmarked.

## Account and Auth Model

Account-specific files live under `.secrets/accounts/<account>/`.

Useful commands:

```powershell
uv run python -m research_x accounts add `
  --account my_account `
  --screen-name my_screen_name `
  --user-id 1234567890 `
  --display-name "My Account" `
  --url https://x.com/my_screen_name
```

Reuse a normal Edge/Chrome profile that is already logged in:

```powershell
uv run python -m research_x auth system-profile `
  --account my_account `
  --browser msedge `
  --profile-directory Default `
  --close-existing-browser
```

Attach to an already CDP-enabled browser:

```powershell
uv run python -m research_x auth cdp `
  --account my_account `
  --endpoint-url http://127.0.0.1:9222
```

Non-interactive auth attempts are routed through `auth auto`. Passwords and one-time values should
be passed through environment variables, never committed.

## Bookmark Acquisition

Full bookmark run:

```powershell
uv run python -m research_x bookmarks `
  --account my_account `
  --out runs/bookmarks_my_account `
  --all `
  --no-classify `
  --db runs/x_data.sqlite3 `
  --download-media
```

The bookmark chain can use direct web GraphQL replay, exported session cookies, browser network
capture, and rendered fallbacks. Cursor state and raw GraphQL pages are kept so long runs can be
resumed.

Main outputs:

```text
bookmarks_items.jsonl
bookmarks.jsonl
account_bookmarks.jsonl
collection_items.jsonl
tweets.jsonl
tweet_edges.jsonl
media.jsonl
media/
bookmark_trees.jsonl
raw_payloads.jsonl
bookmark_pages/
pipeline_report.json
x_store_report.json
```

## Tweet Acquisition

Profile/search/url tweet acquisition writes into the same store:

```powershell
uv run python -m research_x tweets `
  --account my_account `
  --kind profile `
  --value @target_user `
  --limit 100 `
  --out runs/tweets_target_user `
  --db runs/x_data.sqlite3
```

Staged checks:

```powershell
uv run python -m research_x tweet-stages `
  --account my_account `
  --kind profile `
  --value @target_user `
  --stage-limits 100,200,300,400 `
  --out runs/tweet_stages
```

## Displaying Stored Data

```powershell
uv run python -m research_x db-show `
  --db runs/x_data.sqlite3 `
  --account my_account `
  --kind bookmarks `
  --limit 20
```

JSON mode:

```powershell
uv run python -m research_x db-show `
  --db runs/x_data.sqlite3 `
  --account my_account `
  --kind bookmarks `
  --limit 20 `
  --json
```

## AI Labeling

There are two labeling routes:

1. Label during acquisition with `bookmarks --classify` or `tweets --classify`.
2. Label existing DB rows later with `label-existing`.

Post-hoc labeling:

```powershell
$env:GEMINI_API_KEY="..."
uv run python -m research_x label-existing `
  --db runs/x_data.sqlite3 `
  --kind bookmarks `
  --all `
  --classifier-provider gemini `
  --model gemini-2.5-flash `
  --categories examples/bookmark_categories.toml `
  --out runs/labels_all_accounts
```

Supported classifier routes include OpenAI Responses, OpenAI-compatible chat, Gemini via the
OpenAI-compatible endpoint, Qwen, Kimi, and GLM presets.

Operational notes:

- Labels are annotations, not canonical truth.
- Gemini free-tier quota can be exhausted quickly on tens of thousands of rows.
- `label-existing` supports request pacing, retry metadata, cancellation checks, and
  `--stop-on-rate-limit`.
- The local app can stop jobs and restore the DB to a pre-job backup.

## Local App

Start:

```powershell
uv run python -m research_x app
```

Default URL:

```text
http://127.0.0.1:8765
```

Current app capabilities:

- account metadata input,
- standard browser profile auth path,
- bookmark acquisition,
- media download,
- AI labeling provider/model controls,
- post-hoc DB labeling,
- live progress bars for acquisition/media/labeling,
- job stop and stop-with-rollback,
- DB viewer form,
- quota/rate-limit terminal states.

Standalone progress monitor:

```powershell
uv run python -m research_x progress `
  --out runs/bookmarks_my_account `
  --host 127.0.0.1 `
  --port 8766 `
  --no-open-browser
```

## Next Project: AI-Callable Memory Search

The next major branch should build on the existing DB, not replace it.

Target architecture:

```text
Raw X DB
  -> Living Corpus Layer
  -> Hybrid Retrieval Core
  -> Temporal / Obsolescence Layer
  -> Corpus2Skill Navigation Layer
  -> Evidence Bundle API
  -> Lightweight Agentic Search Tool
  -> Feedback / Eval / Rebuild Loop
```

Initial implementation should be a separate `research_x.memory` package, with commands such as:

```text
research_x memory build-corpus
research_x memory build-embeddings
research_x memory embedding-specs
research_x memory plan
research_x memory search
research_x memory evidence
research_x memory export-corpus2skill
research_x memory feedback
research_x memory eval
```

Do this in stages:

1. canonical/living documents from the current SQLite DB,
2. SQLite FTS5 search,
3. compact evidence bundles,
4. feedback table,
5. fixed evaluation queries,
6. natural-language query planning,
7. local hybrid ranking from FTS/substring/metadata/feedback/freshness signals,
8. embedding index and semantic reranking,
9. Corpus2Skill export/navigation,
10. freshness/obsolete edges.

Do not start by deleting or refactoring acquisition code. The memory-search layer should treat the
current store as its source of truth.

## Project Layout

```text
src/research_x/
  adapters/              Acquisition provider implementations.
  accounts.py            Account metadata and session path management.
  bookmarks.py           Bookmark acquisition job orchestration.
  tweets.py              Profile/search/url acquisition jobs.
  x_store.py             SQLite and JSONL canonical store writer.
  bookmark_classifier.py AI label generation.
  label_existing.py      Post-hoc labeling for stored DB rows.
  local_app.py           Local browser app.
  progress.py            Live progress monitor.
  notify.py              Local completion notification.
  cli.py                 CLI entrypoint.

examples/                Config and taxonomy examples.
docs/                    Research notes and pipeline documentation.
tests/                   Unit tests.
```

## Verification

Before commits that affect behavior:

```powershell
uv run ruff check src\research_x tests
uv run pytest
```

Before public pushes:

- confirm `.secrets/` and `runs/` are not staged,
- scan README/docs for real passwords, cookies, email addresses, and API keys,
- avoid committing local account-specific output,
- keep generated run data outside Git.
