# Auto Skill Routing Diff Plan

Date: 2026-06-11
Repository: `C:\Users\maasa\research_x`
Status: draft only; production `AGENTS.md` was not edited by this draft.

Current status note: this is historical design provenance. Auto Skill Routing was later adopted in
production `AGENTS.md` and refined in `research-x-skillization-intake`. Do not use this draft as
the current routing rule or Skill inventory.

## Objective

Allow Codex to route short continuation requests such as "next", "continue", "do this", and "next
phase" to the applicable repo-local Skill without requiring the user to remember or type Skill
names.

## Scope

Planned production target:

- `AGENTS.md`

Draft artifacts created in this step:

- `.codex/auto_skill_routing.diff_plan.md`
- `.codex/AGENTS.auto_skill_routing.candidate.md`

Files intentionally left unchanged:

- `AGENTS.md`
- `README.codex.md`
- `.agents/skills/**`
- `.codex/skill_manifest.lock`
- source code, tests, scripts, source bundles, archives, and `_codex_inbox`

No provider, network, browser, GitHub, ChatGPT connector, MCP, connector, install, or external
write action is part of this plan.

## Existing Context Used

- Global `.codex` `AGENTS.md` G10/G11 is already reflected in the active global context.
- `research_x` `AGENTS.md` already has a `Native Skill Invocation` dispatcher.
- `C:/Users/maasa/.codex/foundation/reviews/research-x-global-skill-alignment-20260611.md`
  classified the then-reviewed repo-local Skill set as
  aligned with global context and `agents/openai.yaml` implicit invocation as `KEEP with watch`.
- `.codex/skill_manifest.lock` recorded the then-reviewed repo-local Skill set as enabled and
  implicitly invocable.
- `research-x-skillization-intake` says AGENTS should stay a small dispatcher and should hold rules
  that must be visible before any Skill can fire.

## Proposed Placement

Insert a short `Auto Skill Routing` section inside `AGENTS.md`, immediately after the introductory
paragraphs in `## Native Skill Invocation` and before `Always-on triggers:`.

Reason:

- This behavior must be visible before the correct repo-local Skill is selected.
- It is a routing rule, not a detailed workflow.
- It does not require a new Skill and should not edit existing Skill descriptions or
  `agents/openai.yaml`.

## Proposed Section

````markdown
## Auto Skill Routing

When the user gives a short continuation request such as "next", "continue", "do this", "next
phase", "次", "続き", "これやって", "次お願いします", "続きお願いします", or
"次のphaseをお願いします", infer the current task from `README.codex.md`, active plan/review
Markdown, current git/worktree state, and recent project context.

Do not ask the user to name a Skill. Select the applicable repo-local Skill or Skills automatically,
then emit one line before work starts:

```text
route: <selected skill(s)>; external actions: <none / needs approval>
```

If provider/API/quota, network, browser, GitHub write, MCP, connector, or install actions are
needed, stop before executing them and ask for explicit approval. Otherwise proceed through the
local, project-approved path.
````

## Behavioral Effect

- Short user requests can be resolved from project context instead of bouncing back for a Skill
  name.
- Codex still uses `README.codex.md`, active plan/review Markdown, git/worktree state, and recent
  project context before choosing a route.
- The selected route is made visible before work starts with:
  `route: <selected skill(s)>; external actions: <none / needs approval>`.
- Local/project-approved work proceeds without extra ceremony.
- Provider/API/quota/network/browser/GitHub write/MCP/connector/install actions remain explicit
  approval gates.

## Non-Goals

- Do not create a new Skill.
- Do not modify existing `SKILL.md` files.
- Do not modify `agents/openai.yaml`.
- Do not widen or narrow `.codex/skill_manifest.lock`.
- Do not change provider freeze, uv command policy, completion notification, git publish policy, or
  sub-agent policy.
- Do not execute external actions while drafting this plan.

## Candidate File

The full candidate is:

- `.codex/AGENTS.auto_skill_routing.candidate.md`

It is the current `AGENTS.md` plus only the proposed `Auto Skill Routing` section.

## Review Checklist Before Production Apply

- Confirm the section is still short enough for `AGENTS.md`.
- Confirm it does not duplicate detailed Skill workflows.
- Confirm the approval gate is at least as strict as the existing no-quota provider freeze.
- Confirm no unrelated project rules are changed.
- Re-read current `AGENTS.md` before any future production apply to avoid overwriting intervening
  edits.
