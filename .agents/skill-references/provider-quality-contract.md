# Provider Quality Contract

This is a shared quality contract for `research_x` provider-facing and quota-sensitive work:
embeddings, rerank, OCR, Reader, external search, LLM context, classifiers, answer engines, relation
judges, managed RAG, pricing, budget guards, API lane estimates, and real-provider verification.

It is not permission to call a provider. While the no-quota freeze is active, provider work is
limited to static inspection, local/fake providers, monkeypatched tests, and offline estimates.

## Minimum Contract

1. Identify the provider lane.
   - Name the provider, model or service, operation, unit of billing, expected input scope, and
     whether the code path can send HTTP.
   - Mark the lane as `local`, `fake`, `offline-estimate`, `provider-gated`, or `real-provider`.

2. State the active gate.
   - Confirm whether the no-quota freeze is active.
   - Treat free-tier, trial-credit, and zero-dollar quota as real provider quota.
   - Stop before HTTP unless the user explicitly lifts the freeze in the current conversation.

3. Preserve pricing and budget visibility.
   - Record price source, price confidence, unit conversion, assumptions, projected run/day/month
     cost, unknown-price behavior, and kill-switch behavior.
   - Unknown or dashboard-only prices are not free.

4. Separate quality evidence from provider claims.
   - Keep primary docs, provider benchmarks, independent benchmarks, community failures, and local
     eval results separate.
   - Provider claims can shortlist a lane; they cannot promote it.

5. Use fake/local verification first.
   - Tests must monkeypatch provider calls.
   - Offline estimates and coverage checks must not send provider HTTP requests.
   - Real canaries must start with the smallest useful limit after explicit approval.

6. End with a provider status.
   - Use `provider-gated`, `estimate-ready`, `price-missing`, `quality-unevaluated`,
     `canary-ready`, `blocked`, or `promoted`.
   - Promotion requires route-level eval improvement after source restoration and citation checks,
     not just lower cost or a benchmark win.

## Skill-Specific Ownership

- `research-x-provider-gate`: owns quota freeze, API Budget Guard, pricing checks, and fake/local
  provider boundaries.
- `research-x-decision-loop`: owns whether provider evidence is enough to justify a design or
  promotion decision.
- `research-x-memory-workflow`: owns downstream evidence restoration before any provider recall arm
  can support answers.
- `research-x-skill-source-review`: owns third-party provider/tool enablement and source-lock risk
  when an external package or connector is being considered.

## Do Not

- Do not run small real-provider smoke tests while the no-quota freeze is active.
- Do not treat a free tier as no-spend local work.
- Do not use `--allow-unpriced-api` while frozen.
- Do not treat provider snippets, rankings, OCR, VLM observations, embeddings, reranker scores, or
  generated answers as citation-ready evidence by themselves.
- Do not hide skipped provider lanes or failed price checks from the final result.

## Verification

- For documentation or Skill edits, run `git diff --check`.
- For Skill/manifest edits, run:

```powershell
uv run python scripts/validate_skill_manifest.py
uv run pytest tests/test_skill_manifest.py
```

- For provider implementation paths, use local/fake providers or monkeypatched tests until the
  no-quota freeze is explicitly lifted.
