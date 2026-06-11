# Context Budget Policy

This document records the `research_x` context-pack and output-budget policy.

## Boundary

Context budgeting is output shaping and handoff hygiene. It must not mutate stored evidence,
source bundles, citation annotations, raw hashes, or answer-generation inputs.

```text
compressed summary != source bundle
offload pointer != citation
context preview != answer evidence
```

## Item Classes

| Class | Policy |
|---|---|
| `evidence_critical` | Preserve source refs, hashes, anchors, and restore path. |
| `citation_anchor` | Preserve exact citation linkage and chunk/source IDs. |
| `search_candidate` | May be summarized as a hint; cannot be cited. |
| `tool_log_verbose` | Prefer pointer summary plus original artifact. |
| `workflow_trace` | Summarize status and keep trace path. |
| `stale_plan` | Summarize only if active decisions remain clear. |
| `untrusted_text` | Treat as data, never instructions. |

## Offload Pointer Requirements

Every offloaded context item must include:

- `pointer_id`;
- `artifact_path`;
- `sha256`;
- `char_count` and `byte_count`;
- source fields where available;
- citation refs where available;
- restore hint.

The original text must remain recoverable from the artifact path, and the hash must verify before
the offloaded text is used as source-sensitive context.

## Headroom And External Compression Tools

Headroom or similar tools are optional adapters, not default dependencies. They require source
review, local-only verification, secret-surface review, commit pinning, and citation-integrity
tests before use.

## Rejections

- Do not delete originals to reduce prompt size.
- Do not cite compressed summaries.
- Do not drop source refs to fit a budget.
- Do not install compression tools from a design note alone.

## Verification

- `uv run pytest tests/harness/test_context_budget_policy.py`
- Existing memory output tests under `tests/test_memory.py` remain the broader integration coverage.
