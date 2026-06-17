---
name: research-x-skillization-intake
description: Use when adding recurring Codex behavior, improving native Skill invocation, reducing AGENTS.md bloat, creating or updating repo skills, or deciding whether an instruction belongs in prompt context, AGENTS.md, README.md, PROJECT.md, docs, a repo Skill, hook, plugin, MCP, automation, or no durable surface.
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
- `research-x-safe-sync`: routine GitHub sync across VS Code, Codex App, and multiple PCs, with uv
  environment refresh only when needed.
- `research-x-private-sync`: explicit-only one-way sync of secrets, Codex home, DBs, and other
  local/private state.
- `research-x-prompt-contract`: prompt/schema/status/tool-boundary contracts and prompt tests.
- `research-x-skill-source-review`: third-party or internal source/Skill trust, pin, gate, reject,
  or reference-only decisions.
- `research-x-publishing-illustration`: output-layer visual briefs, shot lists, and storyboards that
  do not replace evidence.
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
| Article visual brief, storyboard, Xiaohei-style explanatory plan | `research-x-publishing-illustration` |
| Memory/source-bundle invariant, retrieval route, citation, evidence workflow | `research-x-memory-workflow` |
| Provider/API/network permission, quota, budget, external search | `research-x-provider-gate` |
| Markdown source-of-truth placement or archive drift | `research-x-doc-governance` |

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
- Do not use hooks to silently force long reasoning workflows into context. Hooks are for short,
  deterministic checks or notifications.
- Keep `SKILL.md` concise. Move large references or examples to a direct `references/` file only
  when the skill truly needs them.
