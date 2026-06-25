---
name: research-x-implementation-plan-flow
description: Use when checking or converting research_x candidate sets into local-first implementation phases with owner surfaces, gates, stop conditions, and verification paths.
---

# research-x Implementation Plan Flow

Use this skill to turn a candidate set into an implementation-readiness flow for
`research_x`. The input may be source-intake output, a review matrix, a
consultation capture, WBS state, or a user-supplied candidate list, but the output
is a control artifact. It is not evidence, not an architecture decision by itself,
and not permission to install dependencies, call providers, enable plugins/MCP,
or edit Skills automatically.

Also apply `../../skill-references/search-quality-contract.md` when source
candidate quality matters, `../../skill-references/governance-quality-contract.md`
for docs/lock placement, and `../../skill-references/execution-quality-contract.md`
before implementing the resulting phases.

## Purpose

- Convert broad candidate material into a gated local-first execution order.
- Keep adopted, staged, provider-gated, historical, and rejected candidates
  visibly separate.
- Require every promoted item to name an owner surface, first local step,
  verification path, and stop condition.
- Preserve the boundary between consultation/control artifacts and
  citation-ready evidence.

## Use When

- A candidate matrix, WBS group, source-intake result, deferred-item review, or
  project-usability review needs to become executable phases.
- The user asks whether a set of tools, sources, providers, renderers, or
  workflow ideas can be adopted into `research_x`.
- A prior broad review exists and the next task is to check readiness, order the
  work, or expose why some items remain staged.

## Do Not Use When

- The task is final evidence-backed answering; use `research-x-memory-workflow`.
- The task is source discovery or source-bundle restoration; use
  `research-x-research-intake` and the evidence workflow.
- The task is a single already-scoped code change with clear owner and tests.
- The next step would be provider/API usage, install, plugin/MCP/hook enablement,
  model download, connector change, or automatic Skill edit.

## Inputs

- Candidate names, source refs, current status, and intended value.
- Current project anchors: code paths, docs, tests, WBS leaves, adoption registry,
  source lock, and provider gates.
- Constraints: no-quota freeze, no install, no external network/provider calls,
  no automatic Skill edits, and any user priority.

## Outputs

- A compact implementation-readiness flow or phase list.
- Per-candidate classification: `adopt`, `staging`, `provider_gated`,
  `historical`, `reference_only`, `rejected`, or `needs_review`.
- For each promoted item: owner surface, first local step, verification command,
  stop condition, and evidence status.
- For each non-promoted item: blocker and promotion condition.

## Steps

1. Preserve the input boundary.
   - Name the input artifacts and mark consultation, WBS, pointer maps, generated
     diagrams, and summaries as `not_evidence`.
   - Do not use model or community summaries as citation-ready support.
2. Classify candidates before ordering them.
   - Use the adoption shapes in `control/adoption_registry.toml` where possible.
   - Do not merge provider-gated, reference-only, historical, and staged states.
3. Put shared gates first.
   - Prefer local fixtures, fake providers, schema checks, eval reports,
     source-bundle restoration tests, and budget guards before new runtime work.
4. Promote only locally verifiable work.
   - Rank higher when it strengthens source restoration, citations, evals,
     observability, provider safety, or AI-callable tool contracts.
   - Rank lower when it depends on quota, network fetches, hosted services,
     native dependencies, unresolved source rights, hooks, plugins, or MCP.
5. End with execution boundaries.
   - Name the first implementation unit, relevant tests, and hard stop gates.
   - Keep deferred items alive with a concrete promotion condition.

## Safety Gates

- No real provider/API/search/Reader/OCR/LLM/model calls from the plan itself.
- No dependency install, model download, plugin/MCP/hook enablement, connector
  change, or third-party Skill installation from the plan itself.
- No generated diagram, WBS, pointer map, ChatGPT capture, or summary becomes
  evidence or answer support.
- No automatic Skill edit or self-improvement promotion.

## Negative Triggers

- "Interesting" does not mean adopted.
- "Deferred" does not mean discarded unless the blocker is permanent.
- "Free tier" still counts as provider/quota or network use.
- "A diagram explains it" does not make the diagram evidence.

## Verification

- Check that every promoted item has an owner, first local step, local
  verification path, and stop condition.
- Check that every deferred item has a blocker or promotion condition.
- Check that provider/API, install, plugin/MCP/hook, connector, and automatic
  Skill-edit gates are explicit when relevant.
- For manifest or source-lock changes, run:

```powershell
uv run python scripts/validate_skill_manifest.py
uv run pytest tests/test_skill_manifest.py
```

## Manifest Obligations

- Keep this repo Skill enabled only as repo-owned local behavior in
  `.codex/skill_manifest.lock`.
- External source decisions belong in `control/vendor_sources.lock.md` and
  `control/adoption_registry.toml`.
