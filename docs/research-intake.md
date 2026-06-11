# Research Intake Policy

This document records the local `research_x` policy for turning source candidates into review
signals and source-bundle handoff inputs.

## Boundary

Research intake is a candidate-classification lane. It is not citation evidence, answer generation,
or permission to call external providers.

```text
candidate locator != fetched source != source bundle != context chunk != citation
```

## Default Mode

- Default network mode is `dry-run`.
- Default fetch mode is `metadata_only`.
- `allow_network` must be false.
- `allow_provider` must be false.
- Provider-backed sources must stay disabled while the no-quota freeze is active.

Allowed source types in the dry-run path:

- `manual_url`
- `local_note`
- `fake_search`

Provider-gated source types, such as `serper`, `brave`, `jina`, `openai`, `gemini`, and managed RAG,
can be recorded as future candidates only when disabled.

## Intake Decisions

| Decision | Meaning |
|---|---|
| `accept_candidate` | Candidate is worth local review and may receive a source-bundle handoff later. |
| `defer` | Candidate may be useful, but a gate, source right, or provenance item is missing. |
| `reject` | Candidate is unsafe, out of scope, or conflicts with source/provider policy. |
| `reference_only` | Candidate can inform design but must not become runtime behavior or evidence. |

## Required Provenance

Every accepted candidate needs:

- locator or local path;
- source type;
- source owner or registry source ID where known;
- source quality hint;
- storage-rights decision;
- prompt-injection review state;
- source-bundle restoration gate.

## Risk Flags

Use explicit risk flags rather than burying risk in prose:

- `not_evidence`
- `untrusted_url_not_fetched`
- `synthetic_candidate`
- `local_note_not_source_bundle`
- `provider_freeze`
- `network_required`
- `license_unknown`
- `prompt_injection_review_required`

## Handoff

`research-x-research-intake` hands candidates to `research-x-memory-workflow` only after the next
stage can restore source bundles and context chunks. Dry-run candidates and research briefs remain
review/control artifacts.

## Verification

- `uv run python -m research_x.research_intake validate`
- `uv run pytest tests/test_research_intake.py tests/research_intake`
