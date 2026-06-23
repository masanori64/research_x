---
name: research-x-implementation-plan-flow
description: Use when turning GPT Pro/X URL analysis, source-intake results, candidate matrices, deferred-item reviews, or project-usability reviews into a reproducible research_x implementation-priority flow with gates, phases, stop conditions, and local-first execution order.
---

# research-x Implementation Plan Flow

Use this skill when a large set of research candidates, X/ChatGPT analysis results, source-intake
notes, or deferred implementation ideas must become a project-usable implementation plan.

This skill produces a planning artifact, not an architecture decision and not permission to install,
call providers, enable plugins/MCP, or implement every candidate. It keeps consultation material,
source-restoration work, local eval gates, and actual implementation phases separate.
For source/restoration decisions, also apply `../../skill-references/search-quality-contract.md`.
For Skill/docs placement decisions, also apply `../../skill-references/governance-quality-contract.md`.
For execution-ready phases, also apply `../../skill-references/execution-quality-contract.md`.

## Purpose

- Convert noisy or broad research material into a reproducible Markdown implementation flow.
- Separate `use now`, local eval, local dependency, source-review, provider-gated, reference-only,
  and not-actionable items without hiding why an item was not promoted.
- Make "deferred" transparent: name the missing gate, the condition that would promote it, and the
  first local step when one exists.
- Put shared local acceptance/eval gates before adopting candidate tools, models, providers, or
  third-party Skills.
- Produce an implementation order that can start safely under the current no-quota/provider freeze.

## Use When

- The user asks for an implementation-priority flow, implementation plan, execution order, WBS-like
  flow, or phase plan from a candidate list.
- The input includes GPT Pro analysis, X URL analysis, source-candidate summaries, community
  signals, "正本", "保留", "昇格", "優先順位", or "このプロジェクトで使えるか".
- A previous classification/review exists and the next step is to turn it into concrete local-first
  phases.
- The plan must preserve both high-priority candidates and lower-priority but still plausible
  deferred items.

## Do Not Use When

- The user only asks to implement one already-scoped code change.
- The task is final evidence-backed answering; use `research-x-memory-workflow` instead.
- The task is source discovery or primary-source restoration itself; use `research-x-research-intake`
  and, when appropriate, `research-x-decision-loop`.
- The task is provider/API/model execution, dependency installation, plugin/MCP enablement, or hook
  configuration; route through the relevant provider/source/dependency gate first.
- The input is a one-off opinion with no recurring candidate-to-plan workflow.

## Inputs

- `source_materials`: local Markdown, captured ChatGPT text, review matrix, source-intake output,
  project-usability review, or user-provided candidate list.
- `scope`: research_x memory workflow, Codex foundation, source intake, observability, provider
  lane, local dependency, or mixed.
- `current_project_anchors`: relevant files, tests, commands, docs, existing Skills, and policy
  gates.
- `candidate_judgments`: if available, prior verdicts such as `use-now`, `source-intake-only`,
  `local-dependency`, `provider-gated`, `reference-only`, or `not-actionable`.
- `constraints`: no-quota freeze, no install, no external provider calls, no automatic Skill edits,
  required sub-agent policy, and user-specified priority.

## Outputs

- A Markdown implementation-priority flow with date, inputs, status, planning principle, priority
  classes, per-phase work packages, stop gates, recommended execution order, and done criteria.
- A transparent mapping from candidate judgments to implementation phases.
- Local-first work packages with owner surfaces, tests/evals, and explicit gates.
- A list of deferred or rejected items with the reason and promotion condition.
- At least one end-to-end flow diagram when it helps preserve the decision logic.

## Steps

1. Preserve the input boundary.
   - Name every source file/thread/output used as input.
   - State whether the material is consultation, source-intake, project evidence, or durable
     architecture.
   - Do not treat ChatGPT/X/community summaries as citation-ready evidence.

2. Normalize candidate bands before planning.
   - Use clear bands: `use-now`, `use-now-narrow`, `local-eval-candidate`,
     `local-dependency-candidate`, `codex-foundation-candidate`, `source-review-required`,
     `source-intake-only`, `provider-gated`, `reference-only`, and `not-actionable`.
   - For every non-promotion that is not obvious, name the blocker and the condition that would
     change the decision.

3. Start with shared gates.
   - Create P0 only for reusable acceptance/eval/reporting gates that make later promotions
     measurable.
   - Prefer deterministic fixtures, fake/local providers, benchmark skeletons, manifest checks, and
     report fields before model downloads, installs, providers, or new backends.

4. Promote by local value and reversibility.
   - Rank candidates higher when they improve multiple workflows, need no external dependency,
     preserve source-bundle/citation boundaries, and can be verified locally.
   - Rank candidates lower when they require provider quota, hosted services, invasive hooks,
     native dependencies, source-rights review, or unresolved source context.

5. Write each phase as an actionable package.
   - Include reason, owner surface, implementation steps, tests/evals, and explicit `Do not` gates.
   - Use existing project files and commands when known.
   - Keep architecture-doc promotion out of the plan unless the phase itself has been accepted and
     verified.

6. Keep deferred items alive without smuggling them in.
   - Put real rejects and "not now" items in separate sections.
   - For each deferred but plausible item, define the first evidence-producing step:
     source restoration, local fixture, benchmark, source review, dependency canary, or provider
     gate.

7. End with execution order and stop gates.
   - Provide a numbered recommended order.
   - Name hard stop gates: provider/API/search/Reader/managed-RAG calls, model downloads,
     dependency installs, plugin/MCP/hook enablement, third-party Skill installation, automatic
     Skill edits, and architecture promotion without source restoration.
   - Include done criteria for the planning phase.

## Canonical Markdown Shape

Use this shape unless the user supplies a stricter template:

```markdown
# Implementation Priority Flow

Date: YYYY-MM-DD
Inputs:

- `path/or/thread`

## Status

Planning artifact status, evidence boundary, and explicit non-authorization statement.

## Planning Principle

Gate-first principle in one short section.

## Priority Classes

### P0: Shared Gates Before Candidate Adoption

Purpose, work packages, owner surfaces, gates, and expected output.

## P1: Highest-Value Local Implementation

Per-candidate reason, flow, implementation steps, and Do not list.

## P2..P6: Later Local Eval, Route Efficiency, Backend, Source Review, Observability

Only include phases that are justified by the input.

## Explicitly Deferred

Separate true rejects from lower-priority candidates.

## End-To-End Flow

Mermaid flow when useful.

## Recommended Execution Order

Numbered order.

## Stop Gates

Hard gates.

## Done Criteria For This Planning Phase

Concrete checks for plan quality.
```

## Priority Heuristics

- P0: reusable acceptance gates, deterministic fixtures, report fields, local baseline checks,
  source-bundle/citation-preserving measures.
- P1: no-provider, no-install, high-leverage local implementation that strengthens existing
  project surfaces.
- P2: evidence/answer/relevance quality gates and local eval candidates.
- P3: route efficiency, stop-condition metrics, context-policy evals, observability metrics.
- P4: local dependency/backend candidates, but only benchmark skeletons before dependency review.
- P5: source review, Skill/source review, plugin/MCP/hook risk review; no install.
- P6: renderers, diagrams, WBS, visual plans, and artifact patterns only after a concrete
  observability/output gap.
- P7+: explicitly deferred, provider-gated, reference-only, not-actionable, or rejected items.

## Safety Gates

- No real provider, API, external search, Reader, managed-RAG, or free-credit usage unless the user
  explicitly lifts the no-quota freeze and the provider gate passes.
- No model download, dependency install, native backend adoption, plugin/MCP/hook enablement, or
  third-party Skill installation from the plan itself.
- No automatic Skill edits or self-improvement loop without replay, qualifier, manifest validation,
  and human accept/reject.
- No architecture-doc promotion from consultation material without source restoration and a
  verified design change.
- No merging of `reference-only`, `source-intake-only`, and `not-actionable`; their promotion paths
  are different.

## Negative Triggers

- "Everything is interesting, implement all of it" must still become gated phases.
- "Deferred" must not mean "discarded" unless the blocker is permanent or the source is
  unrecoverable.
- "GPT Pro found it" is not evidence; it is consultation until sources are restored.
- "Free tier" or "keyless" is still provider/network usage when the repo freeze applies.
- "Render/diagram it" does not make the diagram evidence.
- "Self-improving Skill" does not permit automatic edits.

## Verification

- Confirm the output names all input materials and their evidence status.
- Confirm every promoted item has a local first step, owner surface, and verification path.
- Confirm every deferred item has a transparent blocker or promotion condition.
- Confirm stop gates include provider/API, installs, plugins/MCP/hooks, third-party Skills, and
  automatic Skill edits when relevant.
- For Skill/manifest edits related to this workflow, run:

```powershell
uv run python scripts/validate_skill_manifest.py
uv run pytest tests/test_skill_manifest.py
```

## Manifest Obligations

- Keep this repo Skill enabled only as repo-owned local behavior in `.codex/skill_manifest.lock`.
- Do not use this Skill to enable external Skills, plugins, MCPs, hooks, providers, or dependencies.
- Update the manifest entry if this Skill is renamed, moved, disabled, or split.
