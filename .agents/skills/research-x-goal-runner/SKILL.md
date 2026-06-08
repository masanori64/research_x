---
name: research-x-goal-runner
description: Use when the user defines or resumes a /goal, goal-like target, or long autonomous run where Codex should continue phase by phase through implementation, review, verification, commit, and push until the target state or a human-intervention gate is reached.
---

# research-x Goal Runner

Use this skill for long-running implementation goals.

## Workflow

1. Confirm the active target state and human-intervention gates.
2. For each phase:
   - implement the next scoped change;
   - review for narrowed behavior, weak fallbacks, unjustified shortcuts, brittle assumptions, and
     missing entry points;
   - fix issues found by that review;
   - run relevant lint, tests, or runtime checks;
   - commit and push the completed scoped phase when separable.
3. Do not mark the goal complete only because a phase was committed.
4. If session limits approach, leave the repository resumable:
   - commit and push completed phases;
   - keep uncommitted changes small;
   - make the next action visible only when the milestone state changes.
5. Stop only at a true human-intervention gate: API keys, billing, external-service contracts,
   irreversible deletion, secret handling, legal/ToS-sensitive choices, explicit user stop/pause, or
   unresolved high-impact design choices after the decision loop.
