---
name: research-x-skillization-intake
description: Use when adding recurring Codex behavior, improving native Skill invocation or Skill Router Preflight, reducing AGENTS.md bloat, creating or updating repo skills, or deciding whether an instruction belongs in prompt context, AGENTS.md, README.md, PROJECT.md, docs, a repo Skill, hook, plugin, MCP, automation, or no durable surface.
---

# research-x Skillization Intake

Use this skill before adding durable agent instructions or new repeatable workflows to this
repository. Its job is to keep `AGENTS.md` small and route new behavior to the narrowest durable
surface.
Global Skill Hygiene decides whether a Skill is worth adding at all; this skill decides the
narrowest project-local `research_x` surface for behavior that belongs in this repository.
Also apply `../../skill-references/governance-quality-contract.md` for instruction-surface,
Skill-reference, manifest, and docs placement decisions.

## Workflow

1. Inspect `git status --short` before edits.
2. Identify the requested behavior and whether it is one-off, always-on, repeated, mechanical, or
   tool-backed.
3. Place it in the smallest matching surface:
   - one-off constraint: prompt/thread context only;
   - always-on safety, command, publish, notification, or source-of-truth rule: `AGENTS.md`;
   - memory-search architecture decision: `docs/memory-pipeline-v2.md`;
   - short milestone or current implementation state: `PROJECT.md`;
   - public command or user-facing repository reference: `README.md`;
   - bulky historical research or superseded decision notes: `docs/memory-pipeline-archive.md`;
   - repeated workflow with task-specific steps: `.agents/skills/<skill-name>/SKILL.md`;
   - deterministic lifecycle enforcement: hook or plugin-bundled hook;
   - live external data, private workspace data, or external actions: MCP, app connector, or plugin;
   - scheduled follow-up or monitor: automation.
4. Keep `AGENTS.md` as a dispatcher. Add trigger pointers there only when the behavior must be
   visible before any skill can fire.
5. If a new skill is needed, propose:
   - skill name;
   - exact trigger description;
   - source-of-truth files to read;
   - what must not be duplicated in the skill;
   - positive and negative trigger examples when the boundary is risky.
6. Before creating or enabling a Skill from third-party material, route through
   `research-x-skill-source-review` and require a manifest/source-lock decision.

## Skill Router Preflight

Use this procedure when route selection itself is unclear, when a short continuation prompt needs
prior context, or when a Skill failed to invoke automatically.

1. Collect the route inputs:
   - newest user request;
   - recent thread context and previous route line;
   - active plan/review Markdown or implementation-priority artifact;
   - current git/worktree state and unrelated-change notes;
   - `README.codex.md`, `PROJECT.md`, and active repository gates when relevant.
2. Generate candidate Skills from the request text and from context. Short prompts such as "next",
   "continue", "次", or "続き" inherit the active task only when the current context still supports
   that route.
3. Reverse-check each nearby Skill against the task:
   - does the task match the Skill's `Use When` or front-matter description?
   - does it hit the Skill's `Do Not Use`, safety gates, or negative triggers?
   - is the Skill the owner, or only a secondary gate such as provider, context, or parallel review?
   - is another Skill narrower for the same request?
4. Classify selected Skills:
   - `primary`: owns the main work;
   - `secondary`: applies as a gate, quality contract, or companion workflow;
   - `not_selected`: close enough to mention only when omission could be surprising.
5. Emit the route before work starts:

```text
route: <selected skill(s)>; external actions: <none / needs approval>
```

For ambiguous or multi-Skill work, add:

```text
route detail: primary=<skill>; secondary=<skill(s)>; not selected=<skill: reason>
```

6. If route selection needs durable improvement, update the narrowest surface:
   - `AGENTS.md`: only small dispatcher rules needed before any Skill can fire;
   - `agents/openai.yaml` or `SKILL.md` front matter: concise trigger/description changes;
   - this Skill: reusable routing audit mechanics;
   - no durable surface: one-off clarification that should not persist.

Do not solve missed invocation by stuffing every Japanese synonym into `AGENTS.md`. Prefer a small
dispatcher plus Skill-owned trigger descriptions, and keep close-but-not-selected reasons available
for ambiguous cases.

## Phase-Boundary Skill Check

Run this lightweight check when the work's category changes. It is not a full re-selection after
every tool call.

Trigger it at these boundaries:

- after context expansion reveals a different task type than the initial route;
- when moving between planning, implementation, verification, docs update, publish, or review;
- when Codex creates, completes, splits, or replaces task-local implementation steps after work
  starts; these steps are mutable execution boundaries, not durable workflow terminology;
- when a new gate appears: provider/API/quota, external source, third-party tool or Skill, prompt
  contract, Markdown placement, context budget, image generation, connector/MCP, install, or
  sub-agent policy;
- before final response, to ensure the active primary or secondary Skills have no unfinished
  non-duplicate obligations.

Checkpoint behavior:

1. Keep the current primary Skill unless the owner of the main artifact or code change has changed.
2. Check only nearby Skills using the Functional Skill Groups; do not reread every Skill by
   default.
3. Add new gate or quality Skills as `secondary`.
4. Change `primary` only when the requested output or phase owner changes.
5. Emit `route update: ...` only when the selected primary or secondary Skills change; otherwise
   keep the check internal.

## Functional Skill Groups

Use these groups during Skill Router Preflight when multiple Skills look similar. The groups are
not replacement Skills. They are shared function tags that make overlap explicit before choosing
the narrower owner.

| Group | Function | Skills |
|---|---|---|
| Router and surface selection | Choose the active workflow or durable instruction surface. | `research-x-skillization-intake`, `research-x-doc-governance`, `research-x-decision-loop`, `research-x-implementation-plan-flow` |
| Governance and contracts | Keep docs, Skills, prompts, source locks, and instruction boundaries narrow and auditable. | `research-x-skillization-intake`, `research-x-doc-governance`, `research-x-prompt-contract`, `research-x-skill-source-review` |
| Gates and risk control | Stop or narrow provider, install, connector, sub-agent, image, or external-source actions. | `research-x-provider-gate`, `research-x-skill-source-review`, `research-x-research-intake`, `research-x-parallel-review`, global `research-x-publishing-illustration` |
| Intake and classification | Classify candidate sources, tools, Skills, repositories, or implementation candidates before adoption. | `research-x-research-intake`, `research-x-skill-source-review`, `research-x-implementation-plan-flow`, `research-x-skillization-intake` |
| Evidence preservation | Preserve source bundles, citations, context chunks, hashes, traces, and offload pointers. | `research-x-memory-workflow`, `research-x-context-budget`, `research-x-research-intake`, global `research-x-publishing-illustration` |
| Decision and review loops | Compare alternatives, counterarguments, stop conditions, and promotion criteria. | `research-x-decision-loop`, `research-x-implementation-plan-flow`, `research-x-skill-source-review`, `research-x-provider-gate` |
| Execution orchestration | Continue phases, split independent work, verify, and keep the repo resumable. | `research-x-goal-runner`, `research-x-parallel-review`, `research-x-implementation-plan-flow` |
| Observability and trace visibility | Make progress, route choices, run state, evidence state, and budget state inspectable. | `research-x-observability-review`, `research-x-memory-workflow`, `research-x-context-budget`, `research-x-provider-gate` |
| Output transformation | Convert inputs into implementation plans, prompt contracts, visual briefs, or context packs. | `research-x-implementation-plan-flow`, `research-x-prompt-contract`, global `research-x-publishing-illustration`, `research-x-context-budget` |

When Skills share a group, choose by owner boundary:

- pick the Skill whose output is the user's requested artifact or code change;
- add gate Skills as secondary instead of making them primary;
- prefer the narrower Skill when one candidate is a special case of another;
- mention `not_selected` only when a nearby Skill could reasonably be expected.

## Existing Repo Skills

- `research-x-decision-loop`: research, review, audit, design loop, and stop-condition mechanics.
- `research-x-doc-governance`: Markdown placement, archive, and drift checks.
- `research-x-goal-runner`: long goal phase loop and human-intervention gates.
- `research-x-memory-workflow`: memory-search architecture and implementation invariants.
- `research-x-observability-review`: hidden app/CLI/workflow state and trace visibility.
- `research-x-parallel-review`: sub-agent role design when sub-agent use is permitted or required
  for exploration.
- `research-x-provider-gate`: no-quota and provider-facing lane checks.
- `research-x-research-intake`: source candidate classification and source-bundle intake handoff.
- `research-x-context-budget`: context pack, offload, compression, and evidence-preservation
  budgeting.
- `research-x-prompt-contract`: prompt/schema/status/tool-boundary contracts and prompt tests.
- `research-x-skill-source-review`: third-party or internal source/Skill trust, pin, gate, reject,
  or reference-only decisions.
- Global `research-x-publishing-illustration`: output-layer visual briefs, shot lists, and
  storyboards that do not replace evidence.
- `research-x-implementation-plan-flow`: GPT/X/source-candidate review to gated local-first
  implementation priority flow.
- `.agents/skill-references/search-quality-contract.md`: shared baseline for search/research/source
  discovery output quality.
- `.agents/skill-references/provider-quality-contract.md`: shared baseline for provider, quota,
  pricing, and API lane quality.
- `.agents/skill-references/evidence-workflow-quality-contract.md`: shared baseline for evidence,
  citation, context, trace, observability, and factual output quality.
- `.agents/skill-references/governance-quality-contract.md`: shared baseline for docs, Skills,
  prompts, source locks, manifests, and instruction-surface quality.
- `.agents/skill-references/execution-quality-contract.md`: shared baseline for implementation
  phase, worker/verifier, verification, commit/push, and resumability quality.

Prefer updating one of these before creating another adjacent skill.

## Routing Table

| Request type | Route |
|---|---|
| External source intake, source registry, community signal, research candidate | `research-x-research-intake` |
| Context pack, compression, offload, budget, Headroom candidate | `research-x-context-budget` |
| Git savepoint, checkpoint, current-state pin, milestone state marker | `research-x-context-budget` plus `research-x-doc-governance` |
| Prompt schema, MNP-like contract, allowed/forbidden tools, prompt tests | `research-x-prompt-contract` |
| Third-party Skill/source adoption, import, trust, pin, install decision | `research-x-skill-source-review` |
| Article visual brief, storyboard, Xiaohei-style explanatory plan | global `research-x-publishing-illustration` |
| GPT/X/source-candidate review to implementation-priority flow | `research-x-implementation-plan-flow` |
| Memory/source-bundle invariant, retrieval route, citation, evidence workflow | `research-x-memory-workflow` |
| Provider/API/network permission, quota, budget, external search | `research-x-provider-gate` |
| Markdown source-of-truth placement or archive drift | `research-x-doc-governance` |
| Recurring operation route, known failure class, route-memory registry placement | `research-x-skillization-intake` plus `C:/Users/maasa/.codex/route_memory/route-memory.json` |
| Skill routing ambiguity, missed automatic invocation, short prompt route recovery | `research-x-skillization-intake` |

## Skill Creation Precheck

- Check existing owner overlap before creating a new Skill.
- Require a distinct trigger, outputs, negative triggers, and verification path.
- Require source review when the idea comes from third-party material.
- Require a manifest entry for repo-owned Skills and source-lock entries for durable external
  candidates.
- Keep publishing/illustration as an output-layer route; do not dismiss it as duplicate of bitmap
  generation when the request is for visual planning.

## Guardrails

- Do not move no-quota freeze, `uv` command policy, completion notification, git publish policy,
  source-of-truth map, or sub-agent permission handling out of `AGENTS.md`.
- Do not create broad "do everything" skills.
- Do not install third-party skills, hooks, or plugins without review.
- Do not recreate cross-PC sync or local-state migration Skills while the desktop-as-canonical
  Remote SSH policy is active.
- Do not use hooks to silently force long reasoning workflows into context. Hooks are for short,
  deterministic checks or notifications.
- Keep `SKILL.md` concise. Move large references or examples to a direct `references/` file only
  when the skill truly needs them.
