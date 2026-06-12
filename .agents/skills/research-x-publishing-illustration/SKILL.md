---
name: research-x-publishing-illustration
description: Use when converting research_x articles, knowledge notes, briefs, or technical explanations into visual briefs, shot lists, storyboards, or image prompt packs while keeping images outside evidence/citation workflows.
---

# research-x Publishing Illustration

Use this skill for output-layer visual planning: turning an article, knowledge note, technical
brief, or research synthesis into a visual brief, shot list, storyboard, or image prompt pack.

This skill is not the image-generation owner. It does not create citation evidence, and it does not
replace source bundles.

## Purpose

- Convert factual or explanatory content into a structured visual plan.
- Preserve claim/source boundaries through a visual claim map.
- Keep image generation explicit, optional, and gated.
- Keep the boundary explicit:
  `visual brief != source`, `generated image != citation`, and
  `style reference != factual support`.

## Use When

- The user asks to make an article, note, design, or research result into a diagram, storyboard,
  visual brief, shot list, or Xiaohei-style explanation plan.
- A publishing output needs visuals while core evidence remains in source bundles.
- The task needs prompts for later image generation but image generation is not yet approved.

## Do Not Use When

- The task is core memory search, evidence creation, source-bundle restoration, or final citation
  checking.
- The user asks for actual bitmap generation; use the image-generation owner only after explicit
  permission and normal image policy.
- The requested visual would imply unsupported factual claims.
- The source material lacks citations and the output would be presented as factual.

## Inputs

- Article, brief, source-backed claims, or local path.
- Optional source-bundle references for factual claims.
- Style reference: neutral explanatory, ian-xiaohei-like, or custom.
- Output type: visual brief, shot list, storyboard, or image prompt pack.

## Outputs

- Visual claim map with claim, source reference, visual role, and unsupported-claim warnings.
- Shot list or storyboard with scene purpose, composition, text overlay, and "must not imply" notes.
- Generation gate stating whether image generation is allowed. Default is false.
- Handoff to `imagegen` only when the user explicitly requests generation and policy allows it.

## Claim Map

Factual visuals need a claim map:

- `claim`: factual statement or explanatory claim.
- `source_ref`: source bundle or local document reference.
- `visual_role`: how the claim is represented visually.
- `must_not_imply`: unsupported inference the visual must avoid.

If source references are absent, the output must be marked draft-only or non-factual.

## Steps

1. Identify whether the requested visual is explanatory, editorial, promotional, or evidence-like.
2. Extract claims and attach source references where factual content is used.
3. Mark unsupported claims as draft-only or remove them from factual visual plans.
4. Produce a scene-by-scene visual plan with constraints and "must not imply" notes.
5. Keep style references optional and creative; do not import third-party assets or code.
6. Stop before actual image generation unless the user explicitly requested it.

## Safety Gates

- Generated images are not evidence or citations.
- Visual plans cannot replace source bundles, citations, or answer support.
- Image generation is false by default.
- A visual brief can be produced locally, but actual bitmap generation requires explicit user
  intent and the normal image-generation workflow.
- ian-xiaohei-style work remains explicit optional creative output, not a core `research_x` evidence
  lane. `ian-xiaohei-illustrations` remains creative optional/reference material and must not be
  installed or enabled without source review.

## Negative Triggers

- "Use this image as proof" is rejected.
- "Do not use an image as proof" remains the default.
- "Make a factual infographic without sources" needs source refs or must be marked draft-only.
- "Generate the images too" requires explicit image-generation approval.
- "Ignore the sources and capture the vibe" can produce only non-factual visual drafts.

## Verification

- Check the output has a visual claim map or explicitly states there are no factual claims.
- Check image generation remains disabled unless explicitly approved.
- Check source-backed claims retain source references.
- `uv run python scripts/validate_skill_manifest.py`
- `uv run pytest tests/test_skill_manifest.py`

## Manifest Obligations

- Keep this Skill repo-owned and enabled in `.codex/skill_manifest.lock`.
- Keep `ian-xiaohei-illustrations` disabled or creative-optional in source locks unless a separate
  review and enablement task approves it.
