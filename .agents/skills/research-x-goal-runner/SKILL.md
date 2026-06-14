---
name: research-x-goal-runner
description: Use when the user defines or resumes a /goal, goal-like target, or long autonomous run where Codex should continue phase by phase through implementation, review, repair, verification, commit, and push until the target state or an oversight gate is reached.
---

# research-x Goal Runner

Use this skill for long-running implementation goals.
Global handoff and session-hygiene skills handle context export and session upkeep; this skill
governs `research_x` phase execution toward a target state under the repository's human-on-the-loop
default.
Also apply `../../skill-references/execution-quality-contract.md` for scoped implementation,
verification, commit/push, and resumability rules.

## Workflow

1. Confirm the active target state and oversight gates from the user's request and repository
   source-of-truth files. If the target is clear enough to execute safely, proceed instead of asking
   for a more detailed prompt.
2. For each phase:
   - implement the next scoped change;
   - review for narrowed behavior, weak fallbacks, unjustified shortcuts, brittle assumptions, and
     missing entry points;
   - fix issues found by that review;
   - run relevant lint, tests, or runtime checks;
   - commit and push the completed scoped phase when separable.
3. Do not mark the goal complete only because a phase was committed.
4. Treat failed checks, boundary denials, dependency conflicts, context-budget pressure, and review
   findings as adaptation signals. Diagnose, update the phase plan, repair, and verify again unless
   the signal hits an oversight gate.
5. If session limits approach, leave the repository resumable:
   - commit and push completed phases;
   - keep uncommitted changes small;
   - make the next action visible only when the milestone state changes.
6. Stop only at a true oversight gate: API keys, billing, external-service contracts,
   irreversible deletion, secret handling, legal/ToS-sensitive choices, explicit user stop/pause, or
   unresolved high-impact design choices after the decision loop.
