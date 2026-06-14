---
name: research-x-observability-review
description: Use when the user says app, CLI, job, workflow, route, evidence, gap, source-quality, citation, budget, media, OCR, or run state is unclear, black-box, missing progress, hard to inspect, or needs a better monitoring/review surface.
---

# research-x Observability Review

Use this skill when hidden workflow state prevents the user or Codex from knowing what happened.
For evidence, route, citation, workflow, budget, OCR/media, or provider-skip visibility, use
`../../skill-references/evidence-workflow-quality-contract.md` as the baseline for what must be
visible before the result is treated as reviewed.

## Workflow

1. Identify the hidden state: progress, route choice, fallback, evidence level, citation support,
   provider skip, budget, media/OCR status, or run completion.
2. Inspect existing CLI/app surfaces before adding UI:
   - run lists and show-run surfaces;
   - workflow steps and metadata;
   - context chunks and citation annotations;
   - API budget and usage ledgers;
   - OCR/media coverage;
   - eval and audit commands.
3. Treat missing visibility as an implementation gap, not just a wording issue.
4. Add the smallest trace, status field, or inspection command that makes the state verifiable.
5. Keep answer claims tied to stored trace/evidence fields.

## Verification

- Check that a user can see current/finished/failed state without manual arithmetic.
- Check stale or incomplete progress does not flash as zero/unknown when previous values exist.
- Check the app and CLI agree on the same underlying state.
