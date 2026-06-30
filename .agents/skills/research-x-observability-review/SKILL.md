---
name: research-x-observability-review
description: Use when the user says app, CLI, job, workflow, route, evidence, gap, source-quality, citation, budget, media, OCR, or run state is unclear, black-box, missing progress, hard to inspect, or needs a better monitoring/review surface.
---

# research-x Observability Review

Visibility review for `research_x` runtime state. This Skill checks whether a
user or Codex can inspect what happened; it does not own evidence semantics,
provider permission, or architecture decisions.

## Purpose

- Expose hidden progress, route choices, skip reasons, evidence level, citation
  support, provider guard state, budgets, media/OCR state, and completion state.
- Treat unclear state as an implementation or interface gap, not just wording.
- Keep app, CLI, and trace surfaces consistent over the same stored state.

## Use When

- The user says the app, CLI, job, workflow, run, evidence, citation, budget,
  media, OCR, or route state is unclear or black-box.
- A result cannot be reviewed because trace, status, or skip reason is missing.
- A prior workflow has enough data internally but no inspectable surface.

## Do Not Use When

- The issue is whether evidence is citation-ready; use
  `research-x-memory-workflow`.
- The issue is whether a provider/API call is allowed; use
  `research-x-provider-gate`.
- The issue is source candidate classification; use `research-x-research-intake`.
- The task only needs copy changes and the underlying state is already visible.

## Inputs

- User-visible symptom and target surface: app, CLI, JSON, trace, log, or run
  view.
- Existing stored state, workflow metadata, eval/audit output, and provider
  skip/budget records.
- Expected review question the user needs to answer.

## Outputs

- Visibility gap report or implementation delta.
- Required state fields, trace entries, status labels, or inspection commands.
- Verification path showing the user can inspect current, finished, failed,
  skipped, and provider-gated states.

## Steps

1. Identify the hidden state: progress, route choice, fallback, evidence level,
   citation support, provider skip, budget, media/OCR status, or completion.
2. Inspect existing CLI/app/JSON/trace surfaces before adding new UI.
3. Find the stored source of truth for the hidden state.
4. Propose or implement the smallest state field, trace entry, status label, or
   inspection command that makes the state reviewable.
5. Keep answer claims tied to stored trace/evidence fields.

## Safety Gates

- Do not invent status from missing data.
- Do not hide provider/API/quota skips behind generic "not available" wording.
- Do not make generated summaries, WBS, screenshots, or UI labels evidence.
- Do not add a second source of truth when an existing trace/run state can be
  exposed.

## Negative Triggers

- "Make the UI sound better" is not observability unless state is actually
  hidden.
- "Provider skipped" must remain visible as provider-gated, not success.
- "No results" must distinguish empty evidence, unsearched route, error, and
  blocked provider.

## Verification

- Confirm a user can see current, finished, failed, skipped, and provider-gated
  state without manual reconstruction.
- Confirm app and CLI agree on the same underlying state.
- Confirm stale or incomplete progress does not overwrite known prior values.
