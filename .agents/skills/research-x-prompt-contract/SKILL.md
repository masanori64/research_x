---
name: research-x-prompt-contract
description: Use when creating, changing, or reviewing research_x prompts, MNP-like contracts, allowed/forbidden tool boundaries, schema/status behavior, or prompt regression tests.
---

# research-x Prompt Contract

Use this skill when prompts or agent instructions need to become testable artifacts rather than
informal prose. It applies the useful parts of prompt-as-server and MNP patterns while keeping
auth, DB writes, provider budget, and security policy in code and repository gates.
Also apply `../../skill-references/governance-quality-contract.md` when prompt or instruction
changes affect durable repository behavior.

## Purpose

- Define prompt contracts with scope, schema, status behavior, allowed tools, forbidden tools, and
  negative cases.
- Make provider and source-bundle boundaries explicit in prompt artifacts.
- Prevent prompt wording from silently replacing backend validation or repository policy.

## Use When

- A task changes routing prompts, answer prompts, research brief prompts, improvement prompts, or
  publishing illustration prompts.
- Allowed tools, forbidden tools, provider policy, or side-effect policy must be encoded.
- Prompt regression tests, injection cases, or MNP-like frames are needed.

## Do Not Use When

- The task only edits ordinary prose with no workflow or tool boundary.
- The request tries to replace backend validation, database writes, auth checks, or provider budget
  enforcement with prompt text.
- The prompt would permit real providers, browser automation, connector auth, or GitHub writes while
  gates are closed.

## Inputs

- Prompt or instruction text.
- Intended task scope and output schema.
- Allowed and forbidden operations.
- Provider, network, side-effect, evidence, and source-bundle policies.
- Positive, negative, and injection examples.

## Outputs

- Prompt contract or review notes with scope, status codes, allowed tools, forbidden tools, and
  expected outputs.
- Negative cases that should fail under the contract.
- Required tests or existing test references.
- Handoff to `research-x-provider-gate` or `research-x-memory-workflow` when needed.

## Steps

1. Identify the prompt's scope, caller, outputs, and side effects.
2. List allowed operations and forbidden operations explicitly.
3. Add source-bundle and provider policy constraints.
4. Define positive, negative, and injection cases.
5. Route provider-facing or evidence-sensitive cases through their owning Skills.
6. Treat prompt changes without tests or static checks as incomplete.

## Safety Gates

- Prompts cannot authorize actions forbidden by `AGENTS.md`, provider freeze, or manifest locks.
- Prompts cannot convert generated text into source evidence.
- Prompt contracts cannot replace code-side validation for writes, auth, budget, or provider calls.

## Negative Triggers

- "Make the prompt stronger; tests are unnecessary" is incomplete.
- "Let the model decide whether DB writes are safe" is rejected.
- "Backend validation can be prompt-only" is rejected.
- "Forbidden tools are obvious" is incomplete.

## Verification

- `uv run pytest tests/test_prompt_contracts.py`
- `uv run python scripts/validate_skill_manifest.py`
- `uv run pytest tests/test_skill_manifest.py`

## Manifest Obligations

- Keep this Skill repo-owned and enabled in `.codex/skill_manifest.lock`.
- Record external prompt-contract tools or imported prompt frameworks as disabled or reference-only
  source candidates until reviewed.
