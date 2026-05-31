# research-x

AI-oriented project reference for the X acquisition and local knowledge-store codebase.

`research-x` is an experimental framework for collecting X/Twitter tweets and bookmarks without
the official X API, comparing multiple acquisition providers under one normalized contract, and
storing the results in a canonical local SQLite database. The current production-shaped surface is
bookmark/tweet acquisition, account-scoped browser session handling, media capture, AI labeling,
and a local web app for running and monitoring jobs.

## Documentation Map

- `AGENTS.md`: short always-read agent rules and command policy.
- `README.md`: repository entry point and current CLI surface.
- `PROJECT.md`: memory-search implementation checklist.
- `docs/memory-pipeline-v2.md`: single detailed architecture source for the AI-callable evidence
  pipeline.
- `docs/pipeline.md`: acquisition/auth/provider pipeline details.

Do not add new memory-architecture Markdown files unless explicitly requested. Update the existing
source-of-truth file instead.

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
memory          Build/search/audit the AI-callable local evidence layer.
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

- `docs/pipeline.md`

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
Stored browser state is treated as usable only when non-empty, non-expired X session cookies
(`auth_token` and `ct0`) are present.

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
resumed. `--all` uses cursor exhaustion, not "any items were found", as the completion signal; a
cursor provider that reaches the end of the bookmark timeline can mark the pipeline complete even
when the total is below the internal high-water limit.

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

The next major branch builds an AI-callable, user-specific evidence system over the existing X DB.
The detailed architecture source is [docs/memory-pipeline-v2.md](docs/memory-pipeline-v2.md).
The implementation checklist is [PROJECT.md](PROJECT.md).

The current `research_x.memory` package is the lower retrieval foundation, not disposable work. The
next phase keeps the raw X DB, `memory_documents`, FTS, production embeddings, relations, evidence,
audit, feedback, and evals, then adds explicit context chunks, citations, answer artifacts, and
workflow traces above them.

Target architecture:

```text
Raw X DB
  -> Normalized / Derived Views
  -> Retrieval Engines
  -> LLM-Ready Context Chunks
  -> Citation Metadata
  -> Bounded Workflows / Orchestrator
  -> Answer Artifacts
  -> Feedback / Eval / Audit / Rebuild
```

Core invariant:

```text
raw source != searchable document != search result != context chunk != citation != answer
```

The V2 surface has explicit `search_runs`, `search_results`, `tool_calls`, `context_chunks`,
`citation_annotations`, `answer_runs`, and bounded `workflow` traces while keeping existing memory
commands working.

External URL discovery has started behind an explicit provider role. The deterministic fake provider
is useful for tests and wiring, while Serper is available as an optional Google SERP
`web-search` / `index_provider`:

```powershell
uv run python -m research_x memory external-search `
  --db runs/x_data.sqlite3 `
  --query "北千住 ピザ" `
  --provider fake `
  --no-store
```

For Serper, set `SERPER_API_KEY` and switch `--provider serper`. Serper results are URL discovery
signals, not citation-ready evidence; reader/extract or LLM-context providers must produce grounded
chunks before answers cite them.

Local context generation is now split from raw retrieval. Use `memory context` when an AI caller
needs LLM-ready chunks and citation-ready source metadata:

```powershell
uv run python -m research_x memory context `
  --db runs/x_data.sqlite3 `
  --query "強化学習 ロボット" `
  --limit 5
```

This stores a search run, context chunks, and citation annotations without turning generated labels
or answers into evidence.

Derived memory documents are optional but recommended before embedding or workflow evaluation. They
preserve raw X rows while adding higher-level searchable cards for places, authors, and finance
events:

```powershell
uv run python -m research_x memory build-derived `
  --db runs/x_data.sqlite3
```

This currently creates `place_card`, `author_profile`, and `ticker_event` rows in
`memory_documents`, keeps source row provenance in metadata, and links each derived row back to its
source documents with `derived_from_source` relations.

`memory build-relations` also builds deterministic graph edges for quote/media/bookmark context,
duplicate bookmarks, shared URLs, shared topics, newer/older same-author topic neighbors, and
`obsolete_candidate` freshness hints. Those freshness hints are ranking signals, not proof that old
content is wrong.

Use `memory judge-relations` after deterministic freshness edges exist when you want reviewed
`supports` / `contradicts` edges for stale-information checks. The fake provider is deterministic
and no-network; real runs can use `gemini`, `openai_chat`, or `openai_compatible`:

```powershell
uv run python -m research_x memory judge-relations `
  --db runs/x_data.sqlite3 `
  --provider gemini `
  --model gemini-2.5-flash `
  --candidate-relation-type obsolete_candidate
```

Judged relation edges are still derived artifacts. They link evidence documents to assessed
documents and store judge/provider metadata in `evidence_json`; they do not overwrite raw X rows or
turn old/new date ordering into proof by itself.

Reader/extract is separate from URL discovery. Use `memory extract-url` to turn a known URL, or URLs
from an external-search run, into external context chunks:

```powershell
uv run python -m research_x memory extract-url `
  --db runs/x_data.sqlite3 `
  --url "https://example.com/article" `
  --provider http
```

Use `--provider fake --no-store` for deterministic no-network tests, or add
`--allow-fixture-provider` when intentionally writing fixture rows to a test DB. The HTTP reader
stores extracted text as external context, while raw HTML is not stored in the DB.

To combine local X evidence and extracted external context in one bundle, pass a stored
external-search run to `memory context`:

```powershell
uv run python -m research_x memory context `
  --db runs/x_data.sqlite3 `
  --query "キオクシア 急騰 分析" `
  --external-run-id "<run_id>" `
  --external-provider http
```

For machine-oriented Web grounding in one call, `memory llm-context` can store pre-extracted
external context chunks. The Brave provider uses Brave Search LLM Context
(`BRAVE_SEARCH_API_KEY`, `X-Subscription-Token`, `/res/v1/llm/context`) and stores extracted
snippets plus source URLs, not raw HTML:

```powershell
uv run python -m research_x memory llm-context `
  --db runs/x_data.sqlite3 `
  --query "昔保存したこの技術情報、今も正しい？" `
  --provider brave `
  --search-lang ja `
  --country JP `
  --max-tokens 8192
```

To produce a generated answer artifact from the same context contract, use `memory answer`.
The default `fake` answer engine is deterministic and no-network; switch to `gemini`,
`openai_chat`, or `openai_compatible` only when an API key is configured. Stored fake answers
require explicit fixture opt-in:

```powershell
uv run python -m research_x memory answer `
  --db runs/x_data.sqlite3 `
  --query "北千住で保存したピザ店を教えて" `
  --answer-provider fake `
  --allow-fixture-provider
```

Generated answers are stored as derived artifacts in `memory_answer_runs`. Answer citations are
stored as `memory_citation_annotations` rows with `answer_id`, text offsets, and source chunk links;
the cited context chunks remain traceable back to local X rows or extracted external Web pages.

For AI-callable orchestration, use `memory workflow`. It plans a route, writes bounded step logs,
records a stop reason, builds context, and can optionally generate an answer. By default it only
builds context so fixture answer rows are not accidentally written:

```powershell
uv run python -m research_x memory workflow `
  --db runs/x_data.sqlite3 `
  --query "強化学習とロボットで後から勉強に使えるもの" `
  --semantic-provider auto
```

Add `--answer-provider gemini --answer-model gemini-2.5-flash` when a stored answer artifact is
wanted. Add `--llm-context-provider brave --llm-context-search-lang ja --llm-context-country JP`
when the route needs current external grounding before answering. The LLM-context chunks are stored
under the same context run and cited like other chunks; they do not replace local X evidence.
`workflow` stop reasons include `enough_evidence`, `no_local_evidence`,
`external_context_needed`, `needs_user_review`, `budget_exhausted`, and `provider_error`.
`memory eval` uses the same route planner, so eval output includes route, stop reason, context
chunk count, source kinds, no-store answer status, answer citation count, and top evidence health
rather than only raw hit shape.
Pass `--semantic-provider`, `--semantic-profile`, and `--semantic-template-version` to evaluate a
specific embedding index. Pass `--cases path\to\cases.jsonl` to run project-specific regression
queries instead of only the built-in route cases.
External chunks classify `source_kind` as `official`, `secondary`, or `user_generated`; the broader
transport type `external_web` is retained as metadata. Local X chunks remain `local_x_db`.

Do not start by deleting or refactoring acquisition code. The memory-search layer should treat the
current store as its source of truth.

Semantic indexes are versioned artifacts, not anonymous vectors. `memory_embeddings` tracks
provider, model, dimensions, `embedding_profile`, `text_template_version`, `embedded_text_hash`,
and `source_doc_hash`; the default profile/template is `general_memory` /
`memory-doc-embedding-v1`.

Memory command surface:

```text
memory build-corpus       Build memory_documents and FTS from the canonical X DB.
memory build-derived      Build place_card, author_profile, and ticker_event views.
memory build-relations    Build explicit graph/relation edges.
memory judge-relations    Judge supports/contradicts edges from freshness candidates.
memory build-embeddings   Build versioned semantic indexes with OpenAI/Gemini or diagnostic local_hash.
memory audit              Check production readiness and diagnostic/fake artifacts.
memory search             Hybrid retrieval with lexical, metadata, relation expansion, semantic.
memory context            Build LLM-ready chunks and citation metadata.
memory external-search    URL discovery provider role, fake or Serper.
memory extract-url        Reader/extract provider role, fake or HTTP.
memory llm-context        Pre-extracted Web context provider role, fake or Brave.
memory answer             Generated answer artifact with source chunk citations.
memory workflow           Bounded route/context/answer orchestration with stop reasons.
memory eval               Route-oriented memory checks.
memory export-corpus2skill Export JSONL or a corpus.jsonl/manifest bundle for Corpus2Skill.
```

Production memory runbook:

```powershell
uv run python -m research_x memory build-corpus --db runs/x_data.sqlite3
uv run python -m research_x memory build-derived --db runs/x_data.sqlite3
uv run python -m research_x memory build-relations --db runs/x_data.sqlite3
uv run python -m research_x memory judge-relations `
  --db runs/x_data.sqlite3 `
  --provider gemini `
  --model gemini-2.5-flash
uv run python -m research_x memory build-embeddings `
  --db runs/x_data.sqlite3 `
  --provider gemini `
  --model gemini-embedding-2 `
  --dimensions 768 `
  --embedding-profile general_memory `
  --text-template-version memory-doc-embedding-v1
uv run python -m research_x memory audit --db runs/x_data.sqlite3 --strict
uv run python -m research_x memory eval `
  --db runs/x_data.sqlite3 `
  --semantic-provider auto `
  --strict
uv run python -m research_x memory eval `
  --db runs/x_data.sqlite3 `
  --cases examples/memory_eval_cases.jsonl `
  --semantic-provider auto `
  --strict
uv run python -m research_x memory export-corpus2skill `
  --db runs/x_data.sqlite3 `
  --bundle-dir runs/corpus2skill_x_memory
uv run python -m research_x memory context `
  --db runs/x_data.sqlite3 `
  --query "北千住で保存したピザ店" `
  --semantic-provider auto
uv run python -m research_x memory answer `
  --db runs/x_data.sqlite3 `
  --query "北千住で保存したピザ店を教えて" `
  --semantic-provider auto `
  --answer-provider gemini `
  --answer-model gemini-2.5-flash
uv run python -m research_x memory workflow `
  --db runs/x_data.sqlite3 `
  --query "昔保存したこの技術情報、今も正しい？" `
  --semantic-provider auto `
  --llm-context-provider brave `
  --llm-context-search-lang ja `
  --llm-context-country JP `
  --answer-provider gemini `
  --answer-model gemini-2.5-flash
```

`fake` providers are for deterministic wiring tests only. `memory audit --strict` flags stored
fake/fixture artifacts, diagnostic-only `local_hash` embeddings, missing relations, incomplete
semantic indexes, missing embedding source hashes, V2 orphan rows, invalid V2 JSON/enums, and other
states that should not be treated as production evidence.

Operational rule: build the memory corpus explicitly before searching or indexing. Search,
relations, and embeddings should not silently rebuild empty memory tables, because that hides stale
or missing index state from audits.

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
docs/                    Acquisition pipeline docs and memory architecture.
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
