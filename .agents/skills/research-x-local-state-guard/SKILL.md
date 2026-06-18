---
name: research-x-local-state-guard
description: >-
  Use when a request touches research_x private, machine-local, generated, or large state such as
  .secrets, .env, .codex, auth.json, cookies, tokens, DB files, runs, caches, backups, .venv, or
  local migration/sync artifacts. Default posture: do not inspect, edit, copy, sync, stage, commit,
  or delete these paths unless the user explicitly authorizes a narrow one-off operation.
---

# research_x Local State Guard

Use this skill to keep local-only state out of routine Codex work. GitHub carries shareable project
state; local private and generated state is not part of the normal edit/sync surface.

## Boundary

Guarded paths and data include:

- `.secrets`, `.env`, `auth.json`, cookies, tokens, keys, credentials, and account state.
- `C:\Users\maasa\.codex` and repo-local `.codex` content that may contain sessions, auth, logs, or
  machine-local Codex state.
- SQLite/DB files, WAL/SHM sidecars, local app state, browser state, and generated run databases.
- `runs`, backups, archives, caches, `.venv`, Playwright/browser caches, large generated artifacts,
  and local migration/sync artifacts.

Safe routine work excludes those paths. Use `research-x-safe-sync` for GitHub-visible source,
docs, tests, lockfiles, and repo skills.

## Default Rules

- Do not read secret values or print private contents.
- Do not copy, sync, migrate, mirror, or restore guarded paths.
- Do not stage or commit guarded paths.
- Do not install or configure Tailscale, Syncthing, rclone, restic, SOPS, age, hooks, or background
  sync automation for these paths as part of routine work.
- Do not delete guarded paths or generated local state unless the user explicitly names the target
  and asks for deletion.
- If a task can be completed through GitHub-tracked files, stay in `research-x-safe-sync`.

## Allowed Narrow Exceptions

Proceed only when the user explicitly asks for a specific guarded-path action in the current turn.
Even then:

- Confirm the exact path, action, and direction before acting if the operation can overwrite,
  delete, reveal, or move private data.
- Prefer metadata-only checks such as existence, size, timestamp, and path names.
- Use dry-run or non-destructive checks before broad copy/delete/migration operations.
- Keep secret values out of logs, terminal output, commits, and chat.
- Stop if the requested action would route private state through GitHub or public services.

## Response Pattern

When this skill triggers during ordinary development work:

1. State that the path is local/private/generated and outside routine GitHub sync.
2. Continue with the GitHub-trackable part of the task if possible.
3. If the guarded state is actually required, ask for a narrow explicit operation rather than
   proposing broad sync or migration.

## Negative Triggers

- Do not use this skill for tracked source, docs, tests, prompt contracts, or lockfiles unless the
  request also touches guarded local state.
- Do not use this skill as a reason to avoid ordinary verification that runs against temp test
  directories.
