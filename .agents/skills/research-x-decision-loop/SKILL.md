---
name: research-x-decision-loop
description: Use for research_x architecture, provider, research, review, audit, or design decisions when the user asks to search, verify, loop, continue, re-evaluate, check counterarguments, avoid premature stopping, or decide whether enough evidence exists.
---

# research-x Decision Loop

Decision sufficiency review for `research_x`. This Skill decides whether a
project decision has enough evidence, counterargument coverage, and boundary
clarity to stop. It does not classify source candidates, execute provider
checks, convert candidates into implementation phases, or optimize Codex itself.

## Purpose

- Test whether a `research_x` architecture, provider, evidence, or workflow
  decision is justified.
- Force non-duplicate counterarguments and alternative designs before closing a
  decision.
- Preserve durable conclusions without turning transient review notes into
  source-of-truth sprawl.

## Use When

- A decision could change architecture, provider choices, evidence contracts,
  workflow behavior, or durable repository instructions.
- The user asks to verify, continue, re-evaluate, loop, audit, or check whether
  enough evidence exists.
- Prior research or implementation revealed a real unresolved alternative,
  contradiction, or risk.

## Do Not Use When

- A source candidate needs provenance/risk classification; use
  `research-x-research-intake`.
- Accepted candidates need execution order, owner surfaces, gates, and stop
  conditions; use `research-x-implementation-plan-flow`.
- Work may send provider HTTP requests, spend quota, or validate pricing;
  stop at `research-x-provider-gate`.
- The task is global Codex self-improvement; that belongs to `.codex`
  retrospective/sleep-cycle surfaces.

## Inputs

- Active question and latest user objective.
- Relevant source-of-truth docs, registry/source-lock state, tests, and local
  implementation facts.
- Prior loops, counterarguments, unresolved risks, and stop conditions.

## Outputs

- Decision status: `continue`, `ready`, `needs_source`, `provider_gated`,
  `blocked`, or `human_gate`.
- New information, overlap with prior information, counterarguments, gaps, and
  design/implementation deltas.
- Durable conclusion pointer when a repository document or registry needs an
  update.

## Steps

1. Inspect current repo state and relevant source-of-truth files before judging.
2. Separate source facts, local implementation facts, review judgments, and
   unknowns.
3. Compare alternatives against the user's stated goal, local data shape, cost
   and quota risk, reliability, provenance, citation quality, token efficiency,
   and maintenance cost.
4. If a new non-duplicate uncertainty appears, run another targeted loop.
5. Stop only when the next loop would repeat prior work or the remaining action
   is a human/provider/install/connector gate.

## Safety Gates

- Do not run provider/API/quota, browser, connector, plugin, MCP, install, or
  external search actions unless the current task explicitly permits that route.
- Do not treat search results, WBS, diagrams, summaries, or consultation captures
  as citation-ready evidence.
- Do not edit Skills automatically from decision output.

## Negative Triggers

- "It seems useful" is not enough for adoption.
- "We already looked once" is not enough to stop if a new counterargument is
  specific and non-duplicate.
- "A provider has a free tier" is still provider/quota gated.
- "This is a Codex behavior improvement" is outside `research_x` decision
  ownership.

## Verification

- Confirm the final state names why another loop is or is not justified.
- Confirm provider/API/install/connector gates are explicit when relevant.
- Record only durable conclusions in repository Markdown.
