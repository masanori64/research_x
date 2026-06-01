# Agent Working Rules

This repository is a shared workspace. Before editing, check the current diff and do not revert or
overwrite uncommitted changes made by other workers.

## Commands

Use the project's `uv` environment for Python tooling. Do not run global `python`, `pytest`, or
`ruff` directly.

Preferred command forms:

```powershell
uv sync
uv run python -m research_x ...
uv run pytest ...
uv run ruff check src\research_x tests
```

Keep lint targets explicit and consistent with `README.md` and `PROJECT.md`.

## Project Architecture

For the memory-search project, read `docs/memory-pipeline-v2.md` before making design changes. It is
the current source of truth for the AI-callable evidence pipeline. `PROJECT.md` tracks the
implementation milestones, and `README.md` is the high-level repository reference.

Do not create additional memory-architecture Markdown files unless the user explicitly asks. Update
the existing source-of-truth file instead, so Codex does not have to scan a spreading design surface.

## Markdown Governance

Keep Markdown stable and sparse:

- `AGENTS.md`: durable agent rules and repository working policy.
- `README.md`: high-level human/repository reference and implemented CLI surface.
- `PROJECT.md`: short milestone tracker only.
- `docs/memory-pipeline-v2.md`: detailed memory/search architecture and decision notes.
- `docs/pipeline.md`: acquisition/auth/provider pipeline details.

When research changes a design decision, add a short dated decision note to the existing source file
instead of creating a new Markdown file. A good decision note states: decision, rationale, rejected
alternatives, implementation impact, and source links. Avoid duplicating the same design text across
multiple files.

## Git Publish Policy

When the user asks for implementation work in this repository, commit and push the completed scoped
changes unless the worktree contains unrelated edits that need separation.

## Goal Continuation

When a user-provided `/goal` or goal context defines a target state, keep working phase by phase
until that target state is reached or a true blocker repeats. A normal phase is:

1. implement the next scoped change;
2. review for narrowed behavior, weak fallbacks, unjustified shortcuts, brittle assumptions, and
   missing entry points;
3. fix the issues found by that review;
4. run the relevant lint/tests or runtime checks;
5. commit and push the completed phase.

Do not stop merely because one phase was committed if the goal still has remaining phases. Continue
to the next aligned phase. Do not redefine completion around the work already done; verify the
current state against the stated goal before considering it complete.

## Completion Notification

At the end of every work session, run:

```powershell
uv run python -m research_x notify --message "作業が終了しました"
```

## Parallel Work

When a task can be split into independent parts, the user permits optional sub-agent use. If the
user asks to use sub-agents, or if a goal phase has independent research/review/test tracks, spawn an
appropriate number of sub-agents instead of defaulting to one. Use sub-agents for work that can
proceed without touching the same files or otherwise conflicting with active work in the repository.

Sub-agents are scoped helpers, not owners of the final change. The parent agent remains responsible
for checking their outputs, integrating the final diff, running verification, and completing
notification/publish steps.

Recommended roles include:

- explorer: read-only codebase inspection, risk review, gap analysis;
- research sidecar: external primary/secondary source investigation while implementation continues;
- worker: bounded code changes with a disjoint file ownership scope;
- verifier: tests, audit commands, or review of a completed patch.

For each spawned sub-agent, give a narrow role, clear ownership, expected output, and whether it may
edit files. Keep the main agent on the critical path; do not delegate the immediate blocking step if
waiting would stall implementation. When sub-agents finish, integrate their findings into the main
decision, then close them unless another immediate follow-up needs their retained context. Completed
sub-agents left open consume the limited parallel-agent slots and can prevent new agents from being
created.
