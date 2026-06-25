# Execution Quality Contract

This is a shared quality contract for `research_x` implementation phases, goal runs, and scoped
repository changes.

It is not a search, provider, evidence, or governance contract. Its job is to keep execution scoped,
verifiable, resumable, human-on-the-loop, and respectful of the shared worktree.

## Minimum Contract

1. Confirm scope and oversight gates.
   - Name the target state, current phase, owned files, expected behavior change, and oversight
     gates.
   - After the user launches the task, proceed through local safe implementation and verification
     without asking for step-by-step approval.
   - Stop before API keys, billing, external-service contracts, irreversible deletion, secrets,
     legal/ToS-sensitive choices, explicit user pause/stop, or unresolved high-impact design
     choices.

2. Protect the worktree.
   - Inspect `git status --short` before edits.
   - Do not revert, overwrite, move, or clean unrelated user or worker changes.
   - Keep edits scoped and use existing project patterns.

3. Keep progress visible.
   - Track phase status, worker/verifier ownership, failed checks, skipped checks, and next action.
   - Treat the step list Codex creates at implementation start as task-local execution boundaries.
     Keep durable gates, status, source-of-truth boundaries, and stop conditions separate from these
     mutable steps; regenerate, split, merge, or reorder steps from the current request, diff,
     relevant Markdown/Skills, test failures, and review findings.
   - Do not let sub-agents own the final decision; parent agent integrates and verifies.
   - Treat failed checks, boundary denials, dependency conflicts, and review findings as adaptation
     signals for repair unless they hit an oversight gate.

4. Verify with project commands.
   - Use only project-approved `uv` command forms for Python tooling.
   - Run targeted lint/tests/audits appropriate to the change; broaden checks when touching shared
     contracts or cross-module behavior.

5. Leave the repo resumable.
   - Commit and push completed scoped implementation work when separable.
   - Do not mark a goal complete merely because a phase was committed or a budget is nearly
     exhausted.
   - Run the completion notification at the end of the work session.

## Skill-Specific Ownership

- `AGENTS.md` owns repository execution gates, command policy, publish policy, and goal
  continuation defaults.
- `research-x-doc-governance` and `research-x-memory-workflow` own domain-specific
  source-of-truth or architecture gates before implementation edits.

## Do Not

- Do not use destructive git or filesystem commands unless explicitly requested.
- Do not stage `.secrets/` or `runs/`.
- Do not substitute a proposal for implementation when the user requested execution and the gate is
  open.
- Do not turn ordinary local failures into user questions before attempting diagnosis, repair, and
  re-verification.
- Do not stop with live helper sessions still running.
- Do not commit unrelated changes into the scoped phase.

## Verification

- For documentation or Skill edits, run `git diff --check`.
- For Skill/manifest edits, run:

```powershell
uv run python scripts/validate_skill_manifest.py
uv run pytest tests/test_skill_manifest.py
```

- For implementation work, run the relevant explicit `uv run pytest ...`, `uv run ruff check ...`,
  audit, or diagnostic command and report any skipped checks.
