# Search Quality Contract

This is a shared quality contract for `research_x` search, research, source discovery, external
fact checks, benchmark/community scans, and read-only exploration. It is not a new entry-point
Skill. Task Skills keep their own routing and specialization, but they must preserve this baseline
when their output could influence a user decision, architecture decision, source intake, or research
direction.

Use the other domain contracts instead of widening this file when the main risk is provider quota,
local evidence/citation promotion, repository governance, or implementation execution.

## Minimum Contract

1. State the task frame.
   - Identify the question, scope, freshness need, target corpus, and whether the work is local,
     public Web, source-intake, or read-only repo exploration.
   - Name blocked actions such as provider quota, network fetch, connector use, install, browser
     automation, or DB writes when they matter, then hand off to the owning domain contract.

2. Separate source classes.
   - Keep primary, official, secondary, benchmark, paper, community, local DB, generated summary,
     and sub-agent note categories distinct.
   - Community reports and generated summaries are failure-mode or review signals, not proof.

3. Preserve a visible search trace.
   - Record or report the queries, files, commands, source locators, sub-agent roles, and major
     inclusion or exclusion choices that materially affected the result.
   - A full transcript is not required, but the user must be able to see why the result was reached.

4. Classify evidence level.
   - Mark each important item as evidence, candidate, hint, inference, blocked, or not evidence.
   - Search hits, snippets, provider summaries, benchmark headlines, and sub-agent notes are
     candidates or hints until the owning evidence workflow promotes them.

5. Apply gates before promotion.
   - Provider or quota-sensitive work uses `provider-quality-contract.md`.
   - Source candidates must pass `research-x-research-intake` before source-bundle handoff.
   - Local evidence/citation promotion uses `evidence-workflow-quality-contract.md`.
   - Skill, docs, prompt, manifest, or source-adoption decisions use
     `governance-quality-contract.md`.

6. Name gaps and counterarguments.
   - State missing source classes, stale or uncertain pricing, known benchmark limits, community
     caveats, failed searches, skipped provider lanes, and any reason the result should remain
     `needs_review`.
   - Do not convert unknowns into confidence.

7. End with a status.
   - Use a clear status such as `decision-ready`, `needs_review`, `provider-gated`,
     `source-intake-only`, `local-only`, or `blocked`.
   - If a next action exists, it must be concrete and tied to the remaining gate.

## Skill-Specific Ownership

- `research-x-decision-loop`: owns comparison, counterarguments, loop-stop judgment, and whether a
  durable design decision is justified.
- `research-x-research-intake`: owns source candidate classification, provenance, risk flags, and
  source-bundle handoff readiness.
- `AGENTS.md` owns any explicitly permitted sub-agent policy; sub-agent notes remain hints until
  the parent agent verifies them through the relevant evidence workflow.

## Do Not

- Do not treat a search hit, SERP rank, snippet, benchmark headline, provider claim, community
  comment, or sub-agent summary as citation-ready evidence by itself.
- Do not hide failed searches, source-class gaps, or sub-agent disagreements.
- Do not merge source classes, benchmark rankings, community reports, and model outputs into one
  confidence claim unless a domain-specific eval supports that fusion.
- Do not add a new Skill just to enforce this contract. Update the narrowest existing Skill or this
  shared reference instead.

## Verification

- For documentation or Skill edits, run `git diff --check`.
- For Skill/manifest edits, run:

```powershell
uv run python scripts/validate_skill_manifest.py
uv run pytest tests/test_skill_manifest.py
```

- For code paths that implement these contracts, use the relevant local/fake tests and keep
  provider calls monkeypatched while the no-quota freeze is active.
