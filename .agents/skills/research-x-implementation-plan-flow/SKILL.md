---
name: research-x-implementation-plan-flow
description: Use when checking or converting research_x candidate sets into local-first implementation phases with owner surfaces, gates, stop conditions, and verification paths.
---

# research-x Implementation Plan Flow

Candidate-to-execution planning for `research_x`. This Skill turns candidate
sets, WBS leaves, consultation captures, or review matrices into gated local
implementation phases. The output is a control artifact, not evidence and not
permission to install, call providers, enable tools, or edit Skills
automatically.

## Purpose

- Convert broad candidate material into local-first execution order.
- Keep adopted, staged, provider-gated, historical, reference-only, and rejected
  states separate.
- Require every promoted item to name owner surface, first local step,
  verification path, and stop condition.

## Use When

- A candidate matrix, WBS group, source-intake result, or deferred-item review
  needs to become executable phases.
- The user asks whether tools, sources, providers, renderers, or workflow ideas
  can be adopted into `research_x`.
- A broad review exists and the next work is readiness, ordering, or explaining
  why items remain staged.

## Do Not Use When

- The task is final evidence-backed answering.
- The task is source discovery or source-bundle restoration.
- The task is a single already-scoped code change with clear owner and tests.
- The next step would be provider/API usage, install, plugin/MCP/hook
  enablement, model download, connector change, or automatic Skill edit.

## Inputs

- Candidate names, source refs, current status, and intended value.
- Current anchors: code paths, docs, tests, WBS leaves, adoption registry,
  source lock, and `ProviderApiBudgetGuard` / provider guard state.
- Constraints such as no-quota freeze, no install, no external action, no
  automatic Skill edits, and user priority.

## Outputs

- Compact implementation-readiness flow or phase list.
- Per-candidate classification: `adopt`, `staging`, `provider_gated`,
  `historical`, `reference_only`, `rejected`, or `needs_review`.
- For promoted items: owner, first local step, local verification, stop
  condition, and evidence status.
- For non-promoted items: blocker and promotion condition.

## Steps

1. Preserve the input boundary: consultation captures, WBS, pointer maps,
   diagrams, and summaries are `not_evidence`.
2. Classify candidates before ordering them, using `control/adoption_registry.toml`
   where possible.
3. Put shared gates first: local fixtures, fake providers, schema checks, eval
   reports, source-bundle restoration tests, and budget guards.
4. Promote only locally verifiable work that strengthens source restoration,
   citations, evals, observability, provider safety, or AI-callable contracts.
5. End with first implementation unit, tests, stop gates, and deferred promotion
   conditions.

## Safety Gates

- No real provider/API/search/Reader/OCR/LLM/model call from the plan itself.
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

- Check every promoted item has owner, first local step, verification path, and
  stop condition.
- Check every deferred item has blocker or promotion condition.
- Check provider/API, install, plugin/MCP/hook, connector, and automatic
  Skill-edit gates are explicit when relevant.
- For manifest/source-lock changes, run the repository Skill governance checks.
