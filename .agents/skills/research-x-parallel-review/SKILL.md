---
name: research-x-parallel-review
description: Use when the active user policy permits sub-agents, requires exploration sidecars, or asks for parallel agents, and the task can be split into independent research, code inspection, implementation, verification, explorer, worker, or sidecar roles without blocking the main critical path.
---

# research-x Parallel Review

Use this skill only when the active user policy permits sub-agents, requires exploration sidecars,
or asks for parallel agents, and the task has independent work that can proceed without conflicting
edits. If the active user policy says exploration must use sub-agents, apply this skill to every
non-trivial exploration or research task even when another Skill is the primary workflow.
For exploration or research sidecars, also apply
`../../skill-references/search-quality-contract.md` when integrating their results.

## Workflow

1. Classify current sub-agent policy from the latest explicit user instruction in this conversation.
2. Keep the parent agent on the critical path.
3. For exploration/research under an active "sub-agents required" policy, spawn at least one
   bounded read-only explorer or research sidecar before final judgment.
4. Spawn sub-agents only for bounded, independent work:
   - explorer: read-only codebase inspection or gap analysis;
   - research sidecar: external primary/secondary source investigation;
   - worker: disjoint code changes with named file ownership;
   - verifier: tests, audit commands, or patch review.
5. Give each sub-agent:
   - narrow role;
   - ownership or read-only scope;
   - expected output;
   - whether it may edit files.
6. Integrate results yourself. Do not let sub-agents own the final decision.
7. Close completed sub-agents unless an immediate follow-up needs retained context.
8. If a result is shallow, send a targeted follow-up naming the missing axis or counterargument.

## Trigger Examples

- Positive: "sub-agents allowed", "parallel agents permitted",
  "エージェントを並列で使って".
- Standing exploration requirement: "skillにかかわらず探索は必ずサブエージェント使って".
- Policy audit only: "エージェント仕様を確認して",
  "loopとエージェントに関して仕様書通り従って".
- Negative: do not spawn sub-agents when the latest explicit instruction bans, pauses, or does not
  permit them.
