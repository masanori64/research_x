# Publishing Illustration Policy

This document records the output-layer visual policy for `research_x`.

## Boundary

Publishing illustration is for explanation and communication. It is not an evidence lane.

```text
visual brief != source
generated image != citation
style reference != factual support
```

## Allowed Outputs

- visual brief;
- shot list;
- storyboard;
- image prompt pack;
- claim-to-visual map.

## Claim Map

Factual visuals need a claim map:

| Field | Meaning |
|---|---|
| `claim` | The factual statement or explanatory claim. |
| `source_ref` | Source bundle or local document reference. |
| `visual_role` | How the claim is represented visually. |
| `must_not_imply` | Unsupported inference the visual must avoid. |

If source references are absent, the output must be marked draft-only or non-factual.

## Image Generation Gate

Image generation is false by default. A visual brief can be produced locally, but actual bitmap
generation requires explicit user intent and the normal image-generation workflow.

## Style References

`ian-xiaohei-illustrations` remains creative optional/reference material. It does not become
`research_x` core evidence, and it must not be installed or enabled without source review.

## Rejections

- Do not use an image as proof.
- Do not create factual infographics without sources.
- Do not generate images unless generation is explicitly requested.
- Do not use style references to imply factual authority.

## Verification

- `uv run pytest tests/prompt_contracts/test_publishing_illustration_contract.py`
- `uv run pytest tests/skills/test_vendor_sources_lock.py`
