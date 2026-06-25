---
name: research-x-provider-gate
description: "Use before any provider-facing or quota-sensitive work in research_x: embeddings, rerank, OCR, Reader, external search, LLM context, classifiers, answer engines, managed RAG, API lane estimates, budget guard, no-quota freeze, pricing, or real API verification."
---

# research-x Provider Gate

No-quota and provider/API boundary for `research_x`. This Skill decides whether a
path may send provider/network requests or spend quota; it does not choose the
architecture by itself and does not make provider output citation-ready.

## Purpose

- Prevent accidental provider/API/quota use while the no-quota freeze is active.
- Separate fake/local implementation from real provider execution.
- Require budget, pricing, and smallest-limit evidence before any approved
  provider call.

## Use When

- Work may send HTTP requests to embedding, rerank, OCR, Reader, external search,
  LLM, classifier, answer-engine, or managed-RAG providers.
- A command, test, smoke check, estimate, or benchmark mentions provider pricing,
  quota, API keys, free tier, trial credit, or `--allow-unpriced-api`.
- A fake/local provider path could accidentally fall through to a real provider.

## Do Not Use When

- The task is purely local code editing and cannot send provider/network
  requests.
- The issue is source-bundle/citation integrity; use `research-x-memory-workflow`.
- The issue is app/CLI visibility; use `research-x-observability-review`.
- The issue is whether an architecture decision is justified; use
  `research-x-decision-loop`.

## Inputs

- Provider, model, operation, command path, and environment variables involved.
- Whether the path can send HTTP or consume free/paid/trial quota.
- Current user approval state and project no-quota freeze state.
- Fake/local/monkeypatched verification option.

## Outputs

- Gate status: `local_allowed`, `provider_gated`, `needs_budget_evidence`,
  `approved_smallest_limit`, or `blocked`.
- Skip reason, allowed local substitute, and required approval/evidence.
- Budget guard and verification notes when provider use is explicitly approved.

## Steps

1. Identify provider, model, operation, command, and HTTP/quota risk.
2. If the no-quota freeze is active, block real provider execution.
3. Use fake/local providers, static inspection, monkeypatched tests, or offline
   estimates where possible.
4. If the user explicitly permits provider use in the current task, keep the API
   Budget Guard enabled, run offline estimates first, start with the smallest
   limit, and stop before the next provider call if pricing or quota evidence is
   unclear.
5. Record durable provider decisions only when they affect architecture,
   command surface, or registry/source-lock state.

## Safety Gates

- The no-quota provider freeze is active unless the user explicitly lifts it in
  the current conversation.
- Free-tier, trial-credit, and zero-dollar quota are still prohibited while
  frozen.
- `--allow-unpriced-api` is disallowed while frozen.
- Tests must monkeypatch provider calls unless the freeze is explicitly lifted.
- Provider output is a candidate signal until restored to source bundles and
  citations by the memory workflow.

## Negative Triggers

- "Just a tiny smoke test" is still provider use.
- "Free tier" is still provider/quota use.
- "The API key is already configured" is not approval.
- "Provider answer looks good" is not citation-ready evidence.

## Verification

- Confirm no command contacted Gemini, OpenAI, Voyage, Jina, Cohere, Mistral,
  Serper, Brave, or similar services while frozen.
- Confirm tests use fake/local/monkeypatched providers.
- Confirm approved provider runs have budget guard, smallest limit, and stop
  condition.
