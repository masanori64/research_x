---
name: research-x-skillization-intake
description: Use when adding recurring Codex behavior, reducing AGENTS.md bloat, creating or updating repo skills, or deciding whether a new instruction belongs in prompt context, AGENTS.md, README.md, PROJECT.md, docs/memory-pipeline-v2.md, docs/memory-pipeline-archive.md, a repo skill, hook, plugin, MCP, or automation.
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

## Guardrails

- Do not move no-quota freeze, `uv` command policy, completion notification, git publish policy,
  source-of-truth map, or sub-agent permission handling out of `AGENTS.md`.
- Do not create broad "do everything" skills.
- Do not install third-party skills, hooks, or plugins without review.
- Do not use hooks to silently force long reasoning workflows into context. Hooks are for short,
  deterministic checks or notifications.
- Keep `SKILL.md` concise. Move large references or examples to a direct `references/` file only
  when the skill truly needs them.
