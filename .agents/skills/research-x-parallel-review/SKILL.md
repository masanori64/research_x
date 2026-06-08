---
name: research-x-parallel-review
description: Use when sub-agent work is permitted and the task can be split into independent research, code inspection, implementation, or verification roles without blocking the main critical path.
---

# research-x Parallel Review

Use this skill only when the latest explicit user instruction permits sub-agents and the task has
independent work that can proceed without conflicting edits.

## Workflow

1. Classify current sub-agent policy from the latest explicit user instruction in this conversation.
2. Keep the parent agent on the critical path.
3. Spawn sub-agents only for bounded, independent work:
   - explorer: read-only codebase inspection or gap analysis;
   - research sidecar: external primary/secondary source investigation;
   - worker: disjoint code changes with named file ownership;
   - verifier: tests, audit commands, or patch review.
4. Give each sub-agent:
   - narrow role;
   - ownership or read-only scope;
   - expected output;
   - whether it may edit files.
5. Integrate results yourself. Do not let sub-agents own the final decision.
6. Close completed sub-agents unless an immediate follow-up needs retained context.
7. If a result is shallow, send a targeted follow-up naming the missing axis or counterargument.
