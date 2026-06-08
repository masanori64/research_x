---
name: research-x-skillization-intake
description: Use when adding recurring Codex behavior, improving native Skill invocation, reducing AGENTS.md bloat, creating or updating repo skills, or deciding whether an instruction belongs in prompt context, AGENTS.md, README.md, PROJECT.md, docs, a repo Skill, hook, plugin, MCP, automation, or no durable surface.
---

# research-x Skillization Intake

Use this skill before adding durable agent instructions or new repeatable workflows to this
repository. Its job is to keep `AGENTS.md` small and route new behavior to the narrowest durable
surface.

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

## Existing Repo Skills

- `research-x-decision-loop`: research, review, audit, design loop, and stop-condition mechanics.
- `research-x-doc-governance`: Markdown placement, archive, and drift checks.
- `research-x-goal-runner`: long goal phase loop and human-intervention gates.
- `research-x-chatgpt-control`: visible, user-directed ChatGPT web consultation from Codex.
- `research-x-memory-workflow`: memory-search architecture and implementation invariants.
- `research-x-observability-review`: hidden app/CLI/workflow state and trace visibility.
- `research-x-parallel-review`: sub-agent role design when sub-agent use is permitted.
- `research-x-provider-gate`: no-quota and provider-facing lane checks.

Prefer updating one of these before creating another adjacent skill.

## Guardrails

- Do not move no-quota freeze, `uv` command policy, completion notification, git publish policy,
  source-of-truth map, or sub-agent permission handling out of `AGENTS.md`.
- Do not create broad "do everything" skills.
- Do not install third-party skills, hooks, or plugins without review.
- Do not use hooks to silently force long reasoning workflows into context. Hooks are for short,
  deterministic checks or notifications.
- Keep `SKILL.md` concise. Move large references or examples to a direct `references/` file only
  when the skill truly needs them.
