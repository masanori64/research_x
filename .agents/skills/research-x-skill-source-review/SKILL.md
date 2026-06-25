---
name: research-x-skill-source-review
description: Use when reviewing third-party or internal Skill/source/adoption candidates for research_x trust, pinning, enablement, rejection, reference-only use, gates, scripts, network, connector, provider, or manifest risk.
---

# research-x Skill Source Review

Use this skill before enabling, adapting, importing, or trusting a third-party Skill, repository,
tool, connector, catalog, prompt package, or source-derived workflow in `research_x`.
Also apply `../../skill-references/governance-quality-contract.md` for manifest, source-lock,
trigger-overlap, and enablement decisions.

This skill decides whether a source can be trusted, pinned, enabled, rejected, gated, or used only
as reference. It does not create or install Skills.

## Purpose

- Review source provenance, license, commit pin, scripts, assets, network behavior, provider calls,
  connector/MCP use, hooks, auth, and trigger overlap.
- Keep external sources disabled until review, pinning, negative triggers, and smoke checks pass.
- Protect `research_x` from broad instruction-surface and supply-chain risk.

## Use When

- The task mentions Superpowers, Headroom, SearXNG, Supermemory, Composio, Vercel skills,
  Anthropic skills, MiniMax skills, skill catalogs, or similar external sources.
- `.codex/skill_manifest.lock` or `control/vendor_sources.lock.md` needs a source decision.
- A new repo-local Skill is proposed from imported material.
- The user asks whether a source should be installed, enabled, adapted, rejected, or kept as
  reference.

## Do Not Use When

- The task is only writing a repo-owned Skill from already approved local design.
- The user explicitly asks to create a Skill after source review has already been completed and
  recorded.
- The candidate requires provider, connector, browser, MCP, GitHub write, or install actions before
  review.

## Inputs

- Candidate name, source URL/path, source type, owner, and intended use.
- License, commit or version, scripts/assets, dependency and hook surface, if known.
- Desired trigger scope and expected output.
- Existing owner overlap and negative trigger cases.

## Outputs

- Classification: trusted, pinned_disabled, enabled, reference_only, gated, or rejected.
- Risk flags: instruction surface, scripts present, network/provider, connector/auth, supply chain,
  abandoned repo, license unknown, trigger overlap, or evidence-boundary risk.
- Manifest or vendor-lock update plan.
- Required tests and smoke checks before enablement.

## Steps

1. Identify the source, owner, license, version, and provenance.
2. Check whether scripts, hooks, dependencies, network, provider, connector, MCP, auth, or browser
   actions are present or implied.
3. Check overlap with existing global and repo-local Skills.
4. Decide the state: reference-only, gated, pinned-disabled, enabled, or rejected.
5. Require explicit negative triggers before any implicit invocation.
6. Update manifest and vendor lock only for durable decisions.
7. Do not install, clone, or enable external code unless the current task explicitly authorizes it.

## Safety Gates

- Third-party Skills stay disabled until pinned, reviewed, and covered by negative triggers.
- Connector and credential-bearing sources are never global defaults.
- Provider-backed sources remain blocked while no-quota freeze is active.
- Catalogs are reference-only and must not be bulk-installed.

## Negative Triggers

- "It is popular, install it" is rejected.
- "Claude-oriented Skill can be copied into Codex global unchanged" is reference/adapt only.
- "Connector catalog should be enabled globally" is rejected or project-gated.
- "License or commit is unknown, but it is useful" remains gated.

## Verification

- `uv run python scripts/validate_skill_manifest.py`
- `uv run pytest tests/test_skill_manifest.py`
- Confirm source lock rows exist for all non-repo manifest source refs.
- Confirm no external entry is enabled without a pinned commit, approved review, and negative
  trigger tests.

## Manifest Obligations

- Keep source decisions in `control/vendor_sources.lock.md`.
- Keep enablement state in `.codex/skill_manifest.lock`.
- Never treat a source review entry as install permission.
