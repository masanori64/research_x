---
name: research-x-doc-governance
description: Use when updating or reorganizing research_x Markdown such as AGENTS.md, README.md, PROJECT.md, docs/memory-pipeline-v2.md, or docs/memory-pipeline-archive.md, especially for Markdown bloat, source-of-truth drift, archive moves, or scope cleanup.
---

# research-x Doc Governance

Use this skill before editing repository Markdown.

## File Roles

- `AGENTS.md`: always-read agent rules, command policy, safety freezes, trigger routing, publish
  policy, and completion notification.
- `README.codex.md`: compact Codex-facing repository reference. Use this for routine agent
  orientation instead of `README.md`.
- `README.md`: human/GitHub repository entry point only.
- `PROJECT.md`: short milestone tracker and current gates.
- `docs/memory-pipeline-v2.md`: detailed current memory/search architecture and durable decisions.
- `docs/memory-pipeline-archive.md`: indexed historical notes. Inspect the index first and read only
  targeted sections.
- `docs/pipeline.md`: acquisition/auth/provider pipeline details.
- `.agents/skills`: repeatable Codex workflows that would bloat `AGENTS.md`.

## Workflow

1. Identify whether the change is a durable rule, public reference, milestone, active architecture,
   or historical note.
2. Update the narrowest file. Do not duplicate the same design text across files.
3. If active architecture notes become bulky or obsolete, move them to
   `docs/memory-pipeline-archive.md` with an index entry instead of leaving them in
   `docs/memory-pipeline-v2.md`.
4. Keep `PROJECT.md` short. It should show current state and gates, not rationale history.
5. Keep `AGENTS.md` short. If the text is a repeatable procedure rather than always-on policy,
   create or update a repo skill.

## Verification

- Run `git diff --check`.
- Confirm the changed file matches its role.
- Confirm no new memory-architecture Markdown file was created unless explicitly requested.
