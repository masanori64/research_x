# research-x

`research-x` is an experimental local framework for collecting X/Twitter tweets and logged-in
bookmarks, storing them in a canonical SQLite database, and building a user-specific evidence search
layer over that data.

This is the human/GitHub README. Codex agents should not use this file as their routine working
reference. Use [README.codex.md](README.codex.md) and the source-of-truth docs listed there instead.

## What This Project Does

- Collects profile/search/url tweets and logged-in bookmarks without the official X API.
- Stores tweets, quote relationships, bookmark ownership, media metadata, and raw payloads in a
  local SQLite database.
- Provides a local app for account setup, acquisition jobs, media download, AI labeling, DB viewing,
  and run monitoring.
- Builds an AI-callable memory-search layer with source bundles, context chunks, citations,
  workflow traces, evals, OCR/media contracts, provider gates, and budget monitoring.

## Main Commands

Use `uv` for all Python tooling:

```powershell
uv sync
uv run python -m research_x app
uv run python -m research_x bookmarks --account my_account --all --db runs/x_data.sqlite3 --out runs/bookmarks_my_account
uv run python -m research_x tweets --account my_account --kind profile --value @target_user --limit 100 --db runs/x_data.sqlite3 --out runs/tweets_target_user
uv run python -m research_x memory --help
uv run pytest
uv run ruff check src\research_x tests
```

When tests appear slow or stuck:

```powershell
uv run python -m research_x test-diagnose tests\test_memory.py --mode tests --timeout-seconds 60 --stop-on-fail
```

## Local Data And Secrets

- Default DB: `runs/x_data.sqlite3`
- Account state: `.secrets/accounts/<account>/`
- Run outputs: `runs/`

Do not commit passwords, cookies, storage states, API keys, or real account secrets. `.secrets/` and
`runs/` are local-only.

## Documentation

- [README.codex.md](README.codex.md): compact Codex-facing repository reference.
- [AGENTS.md](AGENTS.md): always-read agent rules, no-quota freeze, command policy, and Skill routing.
- [PROJECT.md](PROJECT.md): short memory-search milestone tracker and current gates.
- [docs/memory-pipeline-v2.md](docs/memory-pipeline-v2.md): current AI-callable evidence pipeline
  architecture.
- [docs/memory-pipeline-archive.md](docs/memory-pipeline-archive.md): indexed historical decision
  notes; use targeted sections only.
- [docs/pipeline.md](docs/pipeline.md): acquisition/auth/provider pipeline details.

## Current Status

The acquisition base and local app are implemented. The memory-search foundation is implemented
through schema, derived documents, relations, source bundles, context chunks, citations, workflows,
evals, OCR/media contracts, provider gates, budget guard, and no-spend preflight surfaces.

Real external provider usage is intentionally gated. Provider API calls, including free-tier and
trial quota, are not allowed unless explicitly permitted in the current conversation and guarded by
the local API Budget Guard.
