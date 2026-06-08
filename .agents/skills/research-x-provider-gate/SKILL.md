---
name: research-x-provider-gate
description: Use before provider-facing work involving embeddings, rerank, OCR, Reader, external search, LLM context, classifiers, answer engines, managed RAG, budget guard, no-quota freeze, or API lane estimates.
---

# research-x Provider Gate

Use this skill before implementing, estimating, or running provider-facing lanes.

## Rules

- The no-quota provider freeze is active unless the user explicitly lifts it in the current
  conversation.
- Free-tier, trial-credit, and zero-dollar provider quota are still prohibited while frozen.
- Estimates and coverage are allowed only when they do not send provider HTTP requests.
- Fake/local providers and monkeypatched tests are allowed.
- `--allow-unpriced-api` is disallowed while frozen.

## Workflow

1. Identify provider, model, operation, and whether the path can send HTTP.
2. If quota is frozen, block real provider execution and use fake/local verification.
3. If quota is explicitly permitted, keep API Budget Guard enabled, run offline estimates first,
   start with the smallest limit, and stop before the next provider call if pricing, quota, or
   budget evidence is unclear.
4. Record provider decisions only as durable conclusions when they affect architecture or command
   surface.

## Verification

- Tests must monkeypatch provider calls.
- Commands must not call Gemini, OpenAI, Voyage, Jina, Cohere, Mistral, Serper, Brave, or similar
  services unless the freeze is explicitly lifted.
