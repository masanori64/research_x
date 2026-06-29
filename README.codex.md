# research-x Codex Reference

This is the compact Codex-facing repository reference. `README.md` is the
human/GitHub entry point; do not read it for routine Codex orientation.

## Reduced Read Path

Read in this order:

1. `AGENTS.md`: mandatory rules, no-quota freeze, uv command policy, publish
   policy, notification, and native repo Skill dispatcher.
2. `README.codex.md`: this compact orientation.
3. `C:/Users/maasa/.codex/route_memory/route-memory.json`: only when choosing a recurring
   browser/upload/download/tool-bridge/provider/search route or avoiding a known
   failure class.
4. `C:/Users/maasa/.codex/foundation/context_offloads/research_x/pointer-map.json`: authoritative pointer/hash/restore
   index for offloaded Codex work context.
5. `tools/wbs_viewer/projects/research-x-work-state.json`: only when current
   Source/Evidence/Retrieval-Eval/Tool Interface layer state, gates, stop
   conditions, or next actions are needed.
6. `docs/memory-pipeline-v2.md`: only when the memory evidence contract or active
   architecture boundary changes.
7. `docs/memory-pipeline-archive.md`: only after inspecting its index and only when
   historical rationale is needed.

Avoid routine reads of `C:/Users/maasa/.codex/foundation/project_reviews/research_x_chatgpt_control/x-url-analysis-20260622/*.md`; that
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
- Proposal-only Codex self-improvement implementation lives at
  `C:/Users/maasa/.codex/foundation/codex_improvement`; there must be no
  `src/research_x/codex_improvement` package.
- For AI-facing workflow output, prefer `memory workflow --tool-json` over the
  internal `--json` shape.
- The machine-readable `research_x` adoption boundary is `control/adoption_registry.toml`;
  validate it with `uv run python -m research_x adoption audit`. The Codex foundation
  registry lives outside this repo at `C:/Users/maasa/.codex/foundation/codex-foundation-registry.toml`.
  Tool-interface code lives under `src/research_x/tool_interface/`.

## Mandatory Runtime Rules

- Use `uv` command forms only:

```powershell
uv run python -m research_x ...
uv run pytest ...
uv run ruff check <explicit-targets>
```

- No real provider API calls while the no-quota freeze is active, including
  free-tier, trial-credit, zero-dollar, keyless, or otherwise quota-consuming
  calls.
- Fake/local providers, static inspection, offline estimates, and monkeypatched
  tests are allowed.
- `store=True` memory workflow runs may write operational trace rows only; they
  do not authorize raw source, governance, feedback, provider, or answer-support
  mutation.
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
structure checks, D2/Marp build-boundary checks, pointer-map hash checks, review ZIP
branch provenance validation, command-manifest required-artifact coverage/API-budget
observed-zero deltas, optional non-evidence GitHub Actions status artifacts, CI review-package gates, and static provider/network send guard scans. Keep provider-backed commands gated.

## Work-State And Structure

- Operational state source: `tools/wbs_viewer/projects/research-x-work-state.json`
- Codex foundation work-state archive:
  `C:/Users/maasa/.codex/foundation/work_state/research-x-codex-foundation-adjuncts.json`
- Historical mixed WBS archive:
  `C:/Users/maasa/.codex/foundation/work_state/research-x-pre-layer-wbs-archive-20260625.json`
- WBS viewer: `tools/wbs_viewer/vendor/single-file-wbs-v1.3.0/wbs_viewer.html`
- Presentation generation flow:
  `C:/Users/maasa/.codex/foundation/project_plans/research_x/2026-06-24-presentation-generation-flow.md`
- Operation route memory: `C:/Users/maasa/.codex/route_memory/route-memory.json`

Use research_x WBS only for current 4-layer runtime work state; viewer-only
display settings stay there as display config, not evidence. Keep historical
35-item consultation lists, candidate inventories, source-review prose, and Codex
foundation tasks out of it. Use adoption/source-lock files for candidate
decisions, the Codex foundation work-state archive for externalized Skill
lifecycle/self-improvement/route-memory leaves, Route Memory for recurring
operation-route success/failure selection, and Pointer Map for path/hash/size
restore hints. D2 + Marp remains the presentation/deck boundary. Keep Markdown for
durable reasons, invariants, stop conditions, and pointers.

## Repo Skills

Repo Skills live under `.agents/skills/` and are enabled by
`.codex/skill_manifest.lock`. Let Codex native Skill selection choose the narrowest
applicable Skill, then read that Skill and its directly referenced contracts before
acting.

Do not duplicate the Skill catalog here. Use the manifest and Skill files for the
current list. Cross-Skill audit belongs to the Codex foundation at
`C:/Users/maasa/.codex/foundation/skill_audit.py`; `research_x` is the audit
target, not the audit owner.

## Verification

```powershell
uv run ruff check src\research_x tests
uv run pytest
```

GitHub workflow ownership:

- `.github/workflows/research-x-ci.yml`: product gate for lint, tests with
  report-only coverage, local fixture E2E, adoption audit, boundary type check,
  and build. Full-source type coverage is a ratchet target, not yet a hard gate.
- `.github/workflows/research-x-build-artifacts.yml`: build-only release
  artifact lane; it uploads `dist/` and does not publish or deploy.
- `.github/workflows/research-x-dependency-review.yml`, `.github/workflows/research-x-codeql.yml`,
  and `.github/dependabot.yml`: dependency/security surfaces; `crawl4ai` stays explicit/lazy but
  outside the default lock/chain while it requires `lxml <6` and unpatched `nltk`.
- `.github/workflows/codex-*.yml`: Codex control artifact lanes only. They are
  not product evidence, research evidence, citations, or answer support.

Skill governance checks:

```powershell
uv run python scripts\validate_skill_manifest.py
uv run pytest tests\test_skill_manifest.py tests\skills\test_vendor_sources_lock.py tests\test_codex_foundation_boundary.py
```

For slow or stuck pytest runs:

```powershell
uv run python -m research_x test-diagnose tests\test_memory.py --mode tests --timeout-seconds 60 --stop-on-fail
```
