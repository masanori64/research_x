# research-x Codex Reference

This is the compact Codex-facing repository reference. `README.md` is the
human/GitHub entry point; do not read it for routine Codex orientation.

## Reduced Read Path

Read in this order:

1. `AGENTS.md`: mandatory rules, no-quota freeze, uv command policy, publish
   policy, notification, and native repo Skill dispatcher.
2. `README.codex.md`: this compact orientation.
3. `.codex/route_memory/route-memory.json`: only when choosing a recurring
   browser/upload/download/tool-bridge/provider/search route or avoiding a known
   failure class.
4. `.codex/context_offloads/pointer-map.json`: authoritative pointer/hash/restore
   index for offloaded Codex work context.
5. `tools/wbs_viewer/projects/research-x-work-state.json`: only when operational
   state, candidate bands, dates, gates, or remaining work are needed.
6. `docs/memory-pipeline-v2.md`: only when the memory evidence contract or active
   architecture boundary changes.
7. `docs/memory-pipeline-archive.md`: only after inspecting its index and only when
   historical rationale is needed.

Avoid routine reads of `.codex/chatgpt-control/x-url-analysis-20260622/*.md`; that
folder is a historical consultation capture, not the active plan or evidence source.

## Current Mission

Build and operate a local, user-specific X data memory system that an AI can call
as an external search tool:

```text
X acquisition DB -> searchable documents -> source bundles
-> context chunks -> citations -> bounded workflows -> eval/audit
```

Core invariant:

```text
raw source != searchable document != search result != source bundle
!= context chunk != citation != answer
```

WBS, rendered diagrams, screenshots, pointer maps, ChatGPT captures, sub-agent
notes, route-memory registries, and compressed summaries are control or review
artifacts. They are not evidence or answer support.

## Codex Foundation Boundary

`maasa/.codex` and `maasa/research_x` are separate foundations.

- `.codex` owns Codex-wide Skills, self-improvement, local Codex memory,
  retrospectives, session hygiene, Skill/Plugin/MCP governance, and source-locked
  Codex foundation candidates.
- `research_x` owns only the AI-callable X memory-search tool and its evidence,
  retrieval, citation, eval, observability, and provider-budget contracts.
- The bridge is query/objective/context-budget/source-candidate in, and
  `answer|abstain|needs_review|provider_gated|blocked` plus citations and audit
  trace out. Codex transcripts, Skill auto-edit authority, provider execution
  permission, and root instructions do not cross into `research_x`.
- For AI-facing workflow output, prefer `memory workflow --tool-json` over the
  internal `--json` shape.

## Mandatory Runtime Rules

- Use `uv` command forms only:

```powershell
uv run python -m research_x ...
uv run pytest ...
uv run ruff check <explicit-targets>
```

- No real provider API calls while the no-quota freeze is active, including
  free-tier, trial-credit, and zero-dollar quota.
- Fake/local providers, static inspection, offline estimates, and monkeypatched
  tests are allowed.
- Continue through local planning, implementation, review, repair, verification,
  and scoped commit/push unless an oversight gate is hit.
- Run the completion notification at the end:

```powershell
uv run python -m research_x notify --message "作業が終了しました"
```

## Command Discovery

Do not maintain long command inventories in this file. Use the live CLI help:

```powershell
uv run python -m research_x --help
uv run python -m research_x memory --help
uv run python -m research_x test-diagnose --help
```

Common local/fake verification families include memory audit/eval/portfolio checks,
research-intake dry-runs, prompt-contract tests, Skill manifest validation, WBS
structure checks, D2/Marp build-boundary checks, and pointer-map hash checks. Keep
provider-backed commands gated.

## Work-State And Structure

- Operational state source: `tools/wbs_viewer/projects/research-x-work-state.json`
- WBS viewer: `tools/wbs_viewer/vendor/single-file-wbs-v1.2.0/wbs_viewer.html`
- Presentation generation flow:
  `.codex/implementation-plans/2026-06-24-presentation-generation-flow.md`
- Operation route memory: `.codex/route_memory/route-memory.json`

Use WBS for phase/candidate/gate/status data. Use Route Memory for recurring
operation-route success/failure selection. Use Pointer Map for path/hash/size/
restore hints. Use D2 + Marp for presentation diagram and deck generation after
the Stage 1 build-tool boundary is in place. Keep Markdown for durable reasons,
invariants, stop conditions, and pointers.

## Repo Skills

Repo Skills live under `.agents/skills/` and are enabled by
`.codex/skill_manifest.lock`. Let Codex native Skill selection choose the narrowest
applicable Skill, then read that Skill and its directly referenced contracts before
acting.

Do not duplicate the Skill catalog here. Use the manifest and Skill files for the
current list.

## Verification

Default broad checks, when appropriate:

```powershell
uv run ruff check src\research_x tests
uv run pytest
```

For slow or stuck pytest runs:

```powershell
uv run python -m research_x test-diagnose tests\test_memory.py --mode tests --timeout-seconds 60 --stop-on-fail
```
