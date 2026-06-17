---
name: research-x-private-sync
description: >-
  Use only when the user explicitly asks to sync, migrate, copy, replace, back up, or inspect
  private/local research_x state such as .secrets, .env, C:\Users\maasa\.codex, auth.json, cookies,
  tokens, local DB files, runs, caches, large backups, LAN/SSD transfer shares, or one-way PC
  migration. This is the dangerous sync path, including explicit secret sync when requested: gate
  direction, source of truth, backups, app shutdown, and dry-run behavior before copying.
---

# research_x Private Sync

Use this skill for private/local state that must not go through GitHub. Treat it as a gated,
one-way transfer workflow, not routine sync.

If the user explicitly asks to sync secrets or local private state, do it through this skill after
the direction and source of truth are clear. "Dangerous" means guarded and one-way, not refused.

## Hard Rules

- Use only after the user explicitly asks for private/local sync, migration, backup, or replacement.
- Never print secret, cookie, token, auth, or env contents. Use existence, size, timestamps, and
  path checks instead.
- Never upload private state to GitHub, even temporarily, even to a private repository, and even if
  the plan is to delete it right after pulling. Git history, object storage, caches, forks, logs,
  secret scanning, and local clones can retain it.
- Never do automatic bidirectional sync for `.secrets`, `.codex`, DBs, cookies, tokens, or caches.
- Pick one source of truth for each run and copy one way only.
- Do not use `/MIR` unless the user explicitly wants destination-only files deleted.
- Prefer a dry run (`robocopy /L`) before broad or destructive copies.
- Close Codex App, VS Code, terminals, browser automation, and any app using the target DB before
  replacing `.codex`, `.secrets`, or DB files.

## Allowed Private Sync Paths

Use one of these when the user explicitly authorizes private sync:

- LAN share with `robocopy`, authenticated to a temporary local transfer account.
- Tailscale + Syncthing for routine PC-to-PC diff sync of non-DB local state; keep SQLite DBs,
  WAL/SHM files, caches, and active auth/cookie/token files excluded unless the user explicitly
  chooses a one-way migration for those files.
- Direct-attached SSD/USB storage, preferably BitLocker-protected or otherwise encrypted.
- An encrypted archive handed over out of band, with the password/key not committed or printed.
- Manual copy through a trusted local channel when the user is supervising the transfer.

Do not route private state through GitHub, PR attachments, issue comments, gists, public paste sites,
or any hosted service that preserves version history unless the user is deliberately creating an
encrypted offsite backup and the payload is encrypted before upload.

## Decide Direction

Before copying, determine:

- Source PC/path and destination PC/path.
- Whether source or destination is the current source of truth.
- Which categories are in scope: `.secrets`, `.env`, `.codex`, DB, runs, cache, backups.
- Whether the destination should be merged, backed up then replaced, or left untouched.

If both PCs may have independently updated the same private state, stop and ask the user which one
is authoritative. Do not attempt to merge secrets, cookies, auth files, or SQLite DBs.

## Safe Copy Patterns

For LAN shares, authenticate without embedding passwords in commands:

```powershell
net use \\<source-ip> /user:<source-ip>\transfer *
```

Dry-run a private copy first:

```powershell
robocopy "\\<source-ip>\research-x-raw\.secrets" C:\Users\maasa\research_x\.secrets /E /COPY:DAT /DCOPY:DAT /XJ /R:2 /W:2 /L
```

Then run the same command without `/L` if the direction and destination are correct:

```powershell
robocopy "\\<source-ip>\research-x-raw\.secrets" C:\Users\maasa\research_x\.secrets /E /COPY:DAT /DCOPY:DAT /XJ /R:2 /W:2
```

For a full Codex home replacement, close Codex App first and preserve a backup:

```powershell
cd C:\Users\maasa
Rename-Item .codex ".codex_backup_before_private_sync"
robocopy "\\<source-ip>\codex-home-raw" C:\Users\maasa\.codex /E /COPY:DAT /DCOPY:DAT /XJ /R:2 /W:2 /MT:16
```

For merge-style Codex home copy, do not delete destination-only files:

```powershell
robocopy "\\<source-ip>\codex-home-raw" C:\Users\maasa\.codex /E /COPY:DAT /DCOPY:DAT /XJ /R:2 /W:2 /MT:16
```

## Post-Copy Checks

Check only non-secret facts:

```powershell
Test-Path C:\Users\maasa\research_x\.secrets
Test-Path C:\Users\maasa\.codex\auth.json
Get-ChildItem C:\Users\maasa\research_x\.secrets -Force | Select-Object Name,Length,LastWriteTime
```

For the project runtime, switch back to `research-x-safe-sync` and run:

```powershell
cd C:\Users\maasa\research_x
uv sync --python 3.12
uv run python --version
uv run python -m research_x --help
```

## Cleanup

After a one-time LAN migration, offer cleanup of temporary shares/users only after the user confirms
the destination works:

```powershell
Remove-SmbShare -Name research-x-raw -Force
Remove-SmbShare -Name codex-home-raw -Force
net user transfer /delete
```
