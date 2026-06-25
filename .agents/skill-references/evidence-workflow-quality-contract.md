# Evidence Workflow Quality Contract

This is a shared quality contract for `research_x` memory-search, source-bundle restoration,
context chunks, citations, workflow traces, observability, context budgeting, and factual publishing
outputs.

It is not a search contract and not a provider-call contract. Its job is to keep evidence,
candidate signals, derived outputs, and answer claims separated across local memory workflows.

## Minimum Contract

1. Classify the artifact layer.
   - Identify whether each item is raw source, searchable document, search result, context chunk,
     citation annotation, answer, workflow trace, offload pointer, visual plan, generated summary,
     OCR/VLM observation, or hint.
   - Preserve the invariant:
     `raw source != searchable document != search result != context chunk != citation != answer`.

2. Preserve restoration paths.
   - Keep tweet, quote, media, author, bookmark account, URL, relation, time, source hash, run ID,
     and artifact path where applicable.
   - Offloaded or compressed context must keep a restorable pointer and hash.

3. Keep claims tied to support.
   - Answer claims need citation-ready context chunks and citation annotations.
   - Visual briefs, compressed summaries, OCR text, VLM observations, route scores, and generated
     labels remain derived artifacts unless promoted through explicit evidence contracts.

4. Expose workflow state.
   - Route choice, fallback, provider skip, evidence level, citation support, budget/offload state,
     OCR/media status, failure state, and stop reason must be inspectable through CLI/app/run
     surfaces when the task depends on them.

5. Preserve answer boundaries.
   - Use `answer`, `abstain`, `needs_review`, `citation_missing`, `source_not_restored`,
     `provider_gated`, or `blocked` when evidence is incomplete.
   - Do not make unsupported generated text look like completed evidence.

## Skill-Specific Ownership

- `research-x-memory-workflow`: owns source restoration, retrieval routes, context chunks,
  citations, answer/abstain behavior, and route-level evals.
- `research-x-observability-review`: owns making hidden run state and evidence gaps inspectable.
- `research-x-context-budget`: owns evidence-preserving compression, offload pointers, hashes, and
  handoff capsules.
- Global `research-x-publishing-illustration`: consumes visual claim maps and keeps generated
  visuals outside evidence/citation workflows.
- `research-x-provider-gate`: owns provider quota before provider-derived observations can enter
  this workflow.

## Do Not

- Do not cite compressed summaries, generated labels, visual drafts, route scores, or sub-agent
  notes as evidence.
- Do not drop source refs, hashes, run IDs, or restore hints to save tokens.
- Do not promote OCR/VLM/media observations to image-content evidence without citation-ready chunks
  or another explicit evidence contract.
- Do not hide route gaps, unsupported chunks, citation misses, stale projections, or provider skips.

## Verification

- For documentation or Skill edits, run `git diff --check`.
- For Skill/manifest edits, run:

```powershell
uv run python scripts/validate_skill_manifest.py
uv run pytest tests/test_skill_manifest.py
```

- For implementation paths, run the relevant local/fake eval, audit, context, citation, workflow,
  OCR/media coverage, or observability tests without real provider calls while frozen.
