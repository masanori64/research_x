---
name: research-x-doc-governance
description: Use when updating or reorganizing research_x Markdown such as AGENTS.md, README.md, README.codex.md, PROJECT.md, docs/memory-pipeline-v2.md, docs/memory-pipeline-archive.md, or docs/pipeline.md, especially for Markdown bloat, source-of-truth drift, archive moves, git savepoint placement, or scope cleanup.
---

# research-x Doc Governance

Markdown placement and source-of-truth control for `research_x`. This Skill keeps
durable repository docs sparse and correctly owned. It does not create Skills,
run source reviews, or manage global Codex context exports.

## Purpose

- Put durable rules, architecture, milestones, historical notes, and public docs
  in the correct existing file.
- Prevent duplicate explanations across AGENTS, README, PROJECT, docs, WBS,
  source locks, and Skill text.
- Archive obsolete architecture notes with index pointers instead of letting
  active docs bloat.

## Use When

- Editing or reorganizing `AGENTS.md`, `README.codex.md`, `README.md`,
  `PROJECT.md`, `docs/memory-pipeline-v2.md`,
  `docs/memory-pipeline-archive.md`, or `docs/pipeline.md`.
- Markdown bloat, source-of-truth drift, archive moves, savepoint placement, or
  scope cleanup is part of the task.
- Skill/source-lock/registry docs need a short pointer from repository docs.

## Do Not Use When

- The task is a final handoff ZIP; use `context-handoff-export`.
- The task is active context compression; use `context-budget`.
- The task is Skill trust review or third-party source adoption; use the
  foundation governance owner and source locks.
- The task asks to create or rewrite Skills automatically. Skill edits require
  an explicit Skill-editing task and source-of-truth checks.

## Inputs

- Target Markdown file and reason for change.
- Existing docs and owner surfaces.
- Current WBS, registry, source-lock, or boundary-audit references when relevant.
- User instruction about public vs Codex-facing audience.

## Outputs

- Minimal doc edits in the owning file.
- Archive/index entries when moving historical material.
- Pointers to registry, source lock, WBS, boundary audit, or detailed docs instead
  of duplicated prose.

## Steps

1. Classify the change: durable rule, compact reference, public README,
   milestone, active architecture, historical note, or pointer.
2. Update the narrowest existing file.
3. Move bulky or obsolete architecture notes to
   `docs/memory-pipeline-archive.md` with an index entry.
4. Keep `PROJECT.md` short and current.
5. Keep `AGENTS.md` limited to always-on policy and routing.
6. For git savepoints, prefer commit/tag metadata or one small status pointer;
   do not create new architecture Markdown unless explicitly requested.

## Safety Gates

- Do not duplicate the same design text across multiple docs.
- Do not create new memory-architecture docs unless the user explicitly asks.
- Do not move project-specific command policy, no-quota freeze, or evidence
  invariants out of always-read surfaces without another durable owner.
- Do not turn WBS, diagrams, screenshots, or source reviews into evidence docs.

## Negative Triggers

- "This is useful context" is not enough to add Markdown.
- "Make a new doc for clarity" is rejected when an existing owner fits.
- "Archive it" must keep an index and restore pointer.
- "Create a Skill for this procedure" is outside doc governance unless the user
  explicitly requested Skill editing.

## Verification

- Run `git diff --check`.
- Confirm the changed file matches its role.
- Confirm no new memory-architecture Markdown file was created unless explicitly
  requested.
- Confirm stale or historical content has an archive index pointer.
