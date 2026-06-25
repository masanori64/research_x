---
name: research-x-research-intake
description: Use when classifying external or internal source candidates for research_x source-bundle intake, research expansion, source review, or dry-run discovery; do not use for final citation answers or real provider search.
---

# research-x Research Intake

Use this skill when a source candidate should be classified before it enters the `research_x`
source-bundle pipeline. The source can be a URL, local file, uploaded export, GitHub repository,
paper, article, documentation page, community thread, or manually supplied note.

This skill is not permission to browse, call a search API, use a provider, or treat discovery output
as evidence. It turns candidate material into a bounded intake decision and handoff.
For discovery or source-review outputs, also apply
`../../skill-references/search-quality-contract.md` before accepting a candidate.

## Purpose

- Classify source candidates as `accept_candidate`, `defer`, `reject`, or `reference_only`.
- Preserve provenance, access boundary, privacy boundary, and risk flags before any source-bundle
  handoff.
- Keep discovery results separate from citation-ready evidence.
- Keep the intake path local and dry-run by default:
  `candidate locator != fetched source != source bundle != context chunk != citation`.

## Use When

- The user asks to add, widen, revisit, or inventory source material for `research_x`.
- A task mentions research intake, source registry, source review matrix, community signal,
  documentation source, paper, repository, export, or article ingestion.
- Code or docs change source types, intake policy, dry-run discovery, or source-bundle registration
  handoff.

## Do Not Use When

- The task is only local memory search over already indexed source bundles.
- The task is final answer generation with citations; use `research-x-memory-workflow` instead.
- The task requires live external search, provider calls, browser automation, or connector access
  without explicit approval.
- The candidate is only a generated summary that lacks a restorable original source.

## Inputs

- `source_locator`: URL, local path, uploaded-file identifier, repository identifier, or note.
- `source_type_hint`: article, paper, repository, docs, community, media, export, or unknown.
- `objective`: discovery, intake, source-bundle registration handoff, or brief preparation.
- `provider_policy`: no network, user-approved network, or provider gate open.
- `privacy_boundary`: project-local, user-private, public, or unknown.

## Outputs

- Intake decision: `accept_candidate`, `defer`, `reject`, or `reference_only`.
- Source class: primary, official docs, repository, paper, community signal, marketing, unsafe, or
  unknown.
- Provenance: locator, observed timestamp when known, hash when available, and source owner.
- Risk flags: provider quota, network required, credential boundary, license unknown, prompt
  injection risk, community reliability, or ToS/legal concern.
- Handoff target: source registry, source review matrix, memory workflow, or rejected/deferred list.

## Default Mode

- Default network mode is `dry-run`.
- Default fetch mode is `metadata_only`.
- `allow_network` must be false.
- `allow_provider` must be false.
- Provider-backed sources must stay disabled while the no-quota freeze is active.
- Allowed dry-run source types are `manual_url`, `local_note`, and `fake_search`.
- Provider-gated source types such as `serper`, `brave`, `jina`, `openai`, `gemini`, and managed
  RAG can be recorded only as disabled future entries.

## Required Provenance

Every accepted candidate needs:

- locator or local path;
- source type;
- source owner or registry source ID where known;
- source quality hint;
- storage-rights decision;
- prompt-injection review state;
- source-bundle restoration gate.

Use explicit risk flags rather than burying risk in prose: `not_evidence`,
`untrusted_url_not_fetched`, `synthetic_candidate`, `local_note_not_source_bundle`,
`provider_freeze`, `network_required`, `license_unknown`, and
`prompt_injection_review_required`.

## Steps

1. Identify the locator, source type, objective, and privacy boundary.
2. Check whether the task would require network, provider, browser, connector, MCP, or install
   actions. If so, stop at the gate unless the user explicitly approved that action.
3. Classify the source and reliability level. Community and marketing sources can be signals, not
   primary evidence.
4. Record risk flags before any acceptance decision.
5. If accepted, define the exact source-bundle handoff point and required provenance fields.
6. If deferred or rejected, record the reason and the condition that would change the decision.
7. Keep generated labels, summaries, and search hits as hints until the original source is restored.

## Safety Gates

- No real provider, external search API, browser, connector, MCP, or install action without explicit
  approval.
- No hidden ChatGPT/GPT backend API. Use visible sessions or official exports only when separately
  approved.
- No proxy scraping default.
- No source-bundle promotion without restorable original source, provenance, and citation path.
- Dry-run candidates and research briefs remain review/control artifacts until
  `research-x-memory-workflow` can restore source bundles and context chunks.

## Negative Triggers

- "Use this search hit as evidence" requires source-bundle restoration first.
- "Reddit says it, so it is true" remains community signal only.
- "Use a proxy to collect everything" is rejected or gated.
- "Free-tier search API is fine" is blocked while the no-quota freeze is active.
- "Import this ChatGPT history through the backend API" is rejected.

## Verification

- `uv run python -m research_x.research_intake validate`
- `uv run pytest tests/test_research_intake.py`
- `uv run python scripts/validate_skill_manifest.py`
- `uv run pytest tests/test_skill_manifest.py`

## Manifest Obligations

- Keep this repo Skill enabled only as repo-owned local behavior in `.codex/skill_manifest.lock`.
- Do not enable external source candidates from intake without global `skill-security-review` or an
  equivalent source-lock review.
- Record rejected/gated provider or connector candidates in `control/vendor_sources.lock.md` when the
  decision is durable.
