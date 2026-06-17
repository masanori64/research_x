---
name: research-x-safe-sync
description: >-
  Use for safe routine synchronization of the research_x repository across VS Code, Codex App, and
  multiple PCs: before-work latest pulls, after-work commit/push handoff, GitHub code sync, uv
  dependency sync, branch/status checks, and keeping the local Python environment current. Do not
  use for .secrets, .env, .codex, auth.json, cookies, tokens, DB files, runs, caches, or other
  private/local data; use research-x-private-sync for those.
---

# research_x Safe Sync

Use this skill for ordinary, repeatable sync that is safe to run often: Git state, tracked source
files, tracked docs, dependency lock files, and the local uv environment.

## Boundary

Safe sync includes:

- `git status`, `git fetch`, `git pull --ff-only`, commit, and push when the user asked to sync or
  the repo publish policy applies.
- `uv sync --python 3.12` and `uv run python --version`.
- Verification that does not call external providers, X/Twitter, or secret-bearing workflows.

Safe sync excludes:

- `.secrets`, `.env`, cookies, tokens, `auth.json`, `C:\Users\maasa\.codex`, local DB files,
  backups, `runs`, caches, and `.venv`.
- Bidirectional merge of local private state.
- Any command that prints secret contents.

## Before Work

1. Inspect state:

```powershell
git status --short --branch
git branch --show-current
```

2. If there are uncommitted changes, identify whether they are task-related. Do not overwrite,
   reset, stash, or discard them without explicit user intent.
3. If the worktree is clean or the user explicitly wants latest code, update from GitHub:

```powershell
git fetch origin
git pull --ff-only
uv sync --python 3.12
uv run python --version
```

4. Confirm the interpreter is Python 3.12.x. If `.venv` is broken or linked to the wrong Python,
   remove only `.venv` and rebuild it with `uv sync --python 3.12`.

## After Work

1. Re-check the diff:

```powershell
git status --short --branch
git diff --check
```

2. Run task-appropriate verification with uv command forms only.
3. Commit and push scoped implementation work when complete and separable:

```powershell
git add <explicit-files>
git commit -m "<concise message>"
git push
```

4. On the other PC or editor, use the before-work sequence to catch up.

## Failure Rules

- If `git pull --ff-only` fails, stop and inspect the divergence; do not merge or rebase blindly.
- If dependency sync fails due to Python version or wheels, prefer Python 3.12 and rebuild `.venv`.
- If the user asks about secrets, Codex home, DB, cookies, auth, or large local state, switch to
  `research-x-private-sync`.
