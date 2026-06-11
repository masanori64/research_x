# research-x Codex Reference

This is the compact Codex-facing repository reference. Do not read `README.md` for routine Codex
work; it is the human/GitHub entry point.

## First Files

Read in this order:

1. `AGENTS.md`: mandatory rules, no-quota freeze, uv command policy, publish policy, notification,
   and native repo Skill dispatcher.
2. `PROJECT.md`: current milestone state and gates.
3. `docs/memory-pipeline-v2.md`: active memory/search architecture when changing the pipeline.
4. `docs/pipeline.md`: acquisition/auth/provider details when working on X collection.
5. `docs/memory-pipeline-archive.md`: only targeted archived sections when prior research matters.

## Current Mission

Build and operate a local, user-specific X data memory system:

```text
X acquisition DB
  -> normalized / derived documents
  -> relations / source bundles
  -> retrieval arms and route policy
  -> context chunks
  -> citations
  -> bounded workflows
  -> eval / feedback / audit
```

Core invariant:

```text
raw source != searchable document != search result != context chunk != citation != answer
```

No-spend foundation v1 is pinned as complete as of 2026-06-10. Post-v1 work must be classified
before implementation as future local hardening, provider-gated expansion, local-dependency
execution, or separate Codex foundation work. Use `PROJECT.md` for the short tracker and
`docs/memory-pipeline-v2.md` for detailed boundaries.

## Mandatory Runtime Rules

- Use `uv` command forms only:

```powershell
uv run python -m research_x ...
uv run pytest ...
uv run ruff check src\research_x tests
```

- No real provider API calls while the no-quota freeze is active. This includes free-tier,
  trial-credit, and zero-dollar quota.
- Fake/local providers, static inspection, offline estimates, and monkeypatched tests are allowed.
- Run completion notification at the end:

```powershell
uv run python -m research_x notify --message "作業が終了しました"
```

## Main CLI Surfaces

Top-level:

```text
run, pipeline, bookmarks, tweets, tweet-stages, db-show, label-existing,
accounts, auth, app, progress, notify, adapters, memory, test-diagnose
```

Memory-search:

```text
memory build-corpus
memory build-derived
memory search
memory evidence
memory context
memory citations
memory workflow
memory objective-routes
memory objective-execute
memory final-skeleton-preflight
memory api-lane-estimate
memory api-budget
memory api-usage
memory api-watch
memory audit
memory eval
memory portfolio-eval
memory build-embeddings
memory embedding-estimate
memory embedding-coverage
memory media-embedding-estimate
memory build-media-embeddings
memory media-embedding-coverage
memory media-search
memory ocr-estimate
memory build-ocr-evidence
memory ocr-coverage
memory ocr-promote-chunks
memory ocr-second-pass
memory ocr-search
memory media-role-estimate
memory media-role-build
memory media-role-coverage
memory media-observation-add
memory media-observation-import
memory media-observation-coverage
memory external-search
memory extract-url
memory llm-context
memory governance
memory export-corpus2skill
```

Context/output budget:

```powershell
uv run python -m research_x memory context --query "..." --context-budget-max-chars 32000 --context-offload-dir runs\context_offloads
uv run python -m research_x memory workflow --query "..." --json --context-budget-max-chars 32000
```

Source-backed memory governance:

```powershell
uv run python -m research_x memory governance add --type profile --subject-kind topic --subject-id "..." --statement "..." --source-kind memory_document --source-id "..."
uv run python -m research_x memory governance tombstone --artifact-kind memory_document --artifact-id "..." --reason "..." --source-kind manual --source-id "..."
uv run python -m research_x memory governance list --json
```

PromptContract/MNP deterministic checks:

```powershell
uv run pytest tests\test_prompt_contracts.py
uv run pytest tests\prompt_contracts
```

Codex improvement pipeline:

```powershell
uv run python -m research_x.codex_improvement capture ...
uv run python -m research_x.codex_improvement triage
uv run python -m research_x.codex_improvement propose
uv run python -m research_x.codex_improvement validate
```

Research intake dry-run:

```powershell
uv run python -m research_x.research_intake validate
uv run python -m research_x.research_intake discover --out runs\research_intake\discovery_run.json
uv run python -m research_x.research_intake brief --run runs\research_intake\discovery_run.json --out runs\research_intake\research_brief.md
uv run pytest tests\research_intake
```

Addendum policy docs:

```text
docs/research-intake.md
docs/context-budget-policy.md
docs/publishing-illustration-policy.md
prompt_contracts/research_x_*.yaml
```

## Repo Skills

Repo Skills live under `.agents/skills/` and use Codex native implicit invocation through
`agents/openai.yaml`.

- `research-x-skillization-intake`: recurring Codex behavior and instruction-surface placement.
- `research-x-decision-loop`: research/review/audit loops and stop-condition checks.
- `research-x-doc-governance`: Markdown placement, archival, and drift checks.
- `research-x-goal-runner`: long goal phase continuation.
- `research-x-memory-workflow`: memory-search architecture and implementation invariants.
- `research-x-observability-review`: app/CLI/workflow trace visibility.
- `research-x-parallel-review`: sub-agent role design when permitted or required for exploration.
- `research-x-provider-gate`: no-quota and provider-facing lane checks.
- `research-x-research-intake`: source candidate classification and source-bundle handoff.
- `research-x-context-budget`: context pack, compression, offload, and evidence-preserving budget.
- `research-x-prompt-contract`: prompt schema/status/tool-boundary contracts and prompt tests.
- `research-x-skill-source-review`: third-party source/Skill trust, pin, gate, reject, or reference
  decisions.
- `research-x-publishing-illustration`: visual briefs, shot lists, and storyboards outside evidence.

## Verification

Default checks:

```powershell
uv run ruff check src\research_x tests
uv run pytest
```

If full pytest is slow:

```powershell
uv run python -m research_x test-diagnose tests\test_memory.py --mode tests --timeout-seconds 60 --stop-on-fail
```
