---
name: research-x-research-intake
description: Use when classifying external or internal source candidates for research_x source-bundle intake, research expansion, source review, or dry-run discovery; do not use for final citation answers or real provider search.
---

# research-x Research Intake

Source-candidate intake for `research_x`. This Skill classifies candidate
material before it enters the source-bundle pipeline. It does not browse, call
search APIs, use providers, or make discovery output evidence.

## Purpose

- Classify candidate material as `accept_candidate`, `defer`, `reject`, or
  `reference_only`.
- Preserve provenance, access/privacy boundaries, and risk flags before
  source-bundle handoff.
- Keep `candidate locator != fetched source != source bundle != context chunk !=
  citation`.

## Use When

- The user asks to add, widen, revisit, or inventory source material for
  `research_x`.
- A task mentions source registry, source review matrix, community signal,
  documentation, paper, repository, export, or article ingestion.
- Code or docs change intake policy, source types, or source-bundle registration
  handoff.

## Do Not Use When

- The task is local memory search over already indexed source bundles.
- The task is final answering with citations; use the evidence workflow.
- The task requires live external search, provider calls, browser automation, or
  connector access without explicit approval.
- The candidate is only a generated summary with no restorable original source.

## Inputs

- Source locator: URL, local path, uploaded-file identifier, repository ID, or
  manually supplied note.
- Source type hint, objective, provider/network policy, and privacy boundary.
- Any known owner, timestamp, hash, license, or access constraints.

## Outputs

- Intake decision and source class.
- Provenance fields: locator, source owner, timestamp/hash when known, and
  storage-rights state.
- Risk flags such as `not_evidence`, `untrusted_url_not_fetched`,
  `synthetic_candidate`, `provider_freeze`, `network_required`,
  `license_unknown`, or `prompt_injection_review_required`.
- Handoff target: source registry, source review matrix, evidence workflow, or
  deferred/rejected list.

## Steps

1. Identify locator, source type, objective, and privacy boundary.
2. Stop if the task would require network, provider, browser, connector, MCP, or
   install actions without explicit approval.
3. Classify reliability before acceptance. Community and marketing sources are
   signals, not primary evidence.
4. Record risk flags and the exact source-bundle restoration gate.
5. For deferred/rejected candidates, record the reason and promotion condition.

## Safety Gates

- Default mode is dry-run metadata review. `allow_network` must be false and
  `allow_provider` must be false unless explicitly approved.
- Provider-backed sources must stay disabled while the no-quota freeze is
  active.
- No real provider, external search API, browser, connector, MCP, or install
  action without explicit approval.
- No proxy scraping default and no hidden ChatGPT/GPT backend API.
- No source-bundle promotion without restorable original source, provenance, and
  citation path.

## Negative Triggers

- "Use this search hit as evidence" requires source-bundle restoration first.
- "Reddit says it, so it is true" remains community signal only.
- "Free-tier search API is fine" is blocked while the no-quota freeze is active.
- "Import this ChatGPT history through the backend API" is rejected.

## Verification

- `uv run python -m research_x.research_intake validate`
- `uv run pytest tests/test_research_intake.py`
- For manifest/source-lock changes, run the repository Skill governance checks.
