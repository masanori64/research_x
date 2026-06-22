# Global Skill Alignment Review

Date: 2026-06-11

Post-install audit addendum: 2026-06-12

Scope: alignment review between the production global `AGENTS.md` skill context and
`research_x` repo-local Skill context.

This is a review artifact. The original 2026-06-11 review did not authorize edits to
`AGENTS.md`, `README.codex.md`, `.agents/skills`, `.codex/skill_manifest.lock`, source code, tests,
scripts, source bundles, archives, or `_codex_inbox`. The 2026-06-12 addendum updates only
lock/test/review metadata for the installed repo-local Skill set and external source pins; it does
not authorize changing production repo-local Skill behavior.

Current status note: this file is historical review provenance, not the current Skill inventory.
It predates later repo-local Skill additions such as `research-x-implementation-plan-flow`. Use
`README.codex.md`, `PROJECT.md`, `.codex/skill_manifest.lock`, and `.agents/skills/*/SKILL.md` for
current routing and inventory.

## Reviewed Inputs

- Global comparison context:
  - `C:\Users\maasa\.codex\AGENTS.md`
  - Sections confirmed: Codex-Wide Skill Hygiene, Global / Project Scope, Imported Sources And
    Execution Boundary, Existing Capability First, Provider And External Action Gate
- Repo-local review targets:
  - `AGENTS.md`
  - `README.codex.md`
  - `.agents/skills/*/SKILL.md`
  - `.agents/skills/*/agents/openai.yaml`
  - `.codex/skill_manifest.lock`
  - `.codex/vendor_sources.lock.md`

No provider, browser, GitHub write, ChatGPT connector, or install action was used for the original
review. The 2026-06-12 addendum used read-only upstream LICENSE/ref checks for `superpowers` and
`ian-xiaohei-illustrations`; no external code was cloned, imported, enabled, or executed.

## Executive Judgment

There is no hard conflict between the global Skill context and the `research_x` repo-local Skill
context.

The repo-local rules reviewed at the time were mostly project-specific and should remain in place.
The main alignment risk is not contradiction; it is gradual duplication of general Codex-wide policy
inside `AGENTS.md`, `README.codex.md`, and `research-x-skillization-intake`. Future thinning should
remove only generic restatements after confirming that the project-specific owner, command form,
provider freeze, architecture invariant, manifest lock, and validation behavior remain visible.

The 2026-06-12 post-install audit confirms the production repo-local Skill folders are lean:
each installed Skill directory contains only `SKILL.md` and `agents/openai.yaml`, and no stale
candidate, install-pending, or `_foundation_work` wording was detected in `.agents/skills`.

## Classification Summary

| Area | Classification | Reason |
|---|---|---|
| no-quota provider freeze in `AGENTS.md` | DO_NOT_TOUCH | Project-specific hard safety gate; stricter and more concrete than global external action gate. |
| `uv` command policy in `AGENTS.md` / `README.codex.md` | DO_NOT_TOUCH | Project runtime rule; removing it risks global Python/pytest/ruff use. |
| completion notification rule | DO_NOT_TOUCH | Project workflow rule with exact command. |
| memory/search architecture invariants | DO_NOT_TOUCH | Core `research_x` project behavior, not global Codex behavior. |
| Skill dispatcher in `AGENTS.md` | KEEP | Repo-specific trigger routing for the reviewed local Skill set at the time; use current inventory files for current count. |
| repeated Skill hygiene language | THIN | Global `Codex-Wide Skill Hygiene` now owns general Skill creation/install criteria. |
| `research-x-skillization-intake` | KEEP / CLARIFY | Repo owner for instruction-surface placement; should explicitly remain project-local. |
| `research-x-provider-gate` | DO_NOT_TOUCH / CLARIFY | Repo owner for no-quota and provider lane mechanics; global owns general external-action default. |
| `research-x-memory-workflow` | DO_NOT_TOUCH | Evidence/Source Bundle First and X memory pipeline are project-local. |
| `research-x-decision-loop` | KEEP / CLARIFY | Repo architecture/review loop; should not be confused with global retrospective/sleep workflows. |
| `research-x-goal-runner` | KEEP / CLARIFY | Repo execution continuation; should not be confused with handoff/session hygiene Skills. |
| `research-x-doc-governance` | KEEP / CLARIFY | Repo Markdown source-of-truth routing; overlaps with context hygiene but has project file ownership. |
| `research-x-observability-review` | KEEP | Project-specific app/CLI/workflow trace visibility. |
| `research-x-parallel-review` | KEEP | Repo-specific sub-agent policy adapter; bounded by explicit user permission. |
| all `agents/openai.yaml` implicit invocation flags | KEEP with watch | Broad but constrained by `research_x` naming, descriptions, and `AGENTS.md` dispatcher. |
| `.codex/skill_manifest.lock` | DO_NOT_TOUCH | Manifest lock and third-party enablement gate. |
| `.codex/vendor_sources.lock.md` | DO_NOT_TOUCH | Source decisions are review artifacts, not install permissions. |

## Boundary Review

### Global Skill Hygiene vs `research-x-skillization-intake`

Classification: KEEP / CLARIFY

Global owner:

- Whether adding or installing a Skill is generally justified.
- Repeated use, distinct trigger, right surface, evidence of value, and removal path.
- Existing-capability-first checks across global Skills, plugins, connectors, prompts, and
  `vendor_imports`.

Repo-local owner:

- Where a `research_x` instruction belongs: prompt context, `AGENTS.md`, repo docs, repo Skill,
  hook, plugin, MCP/app, automation, or no durable surface.
- How to keep `research_x` `AGENTS.md` small while preserving no-quota freeze, `uv` policy,
  completion notification, source-of-truth map, and sub-agent permission handling.
- Which existing repo Skill should absorb adjacent behavior before creating a new local Skill.

Recommended future clarification:

- Add one sentence, if this Skill is edited later: "Global Skill Hygiene decides whether a Skill is
  worth adding at all; this repo Skill decides the narrowest `research_x` surface for behavior that
  remains project-local."

Thin candidates:

- Generic criteria such as "do not create broad skills" and "do not install third-party skills
  without review" repeat global policy, but they are still useful as local guardrails until the
  boundary sentence exists.

Do not touch:

- Guardrails that keep no-quota freeze, `uv` command policy, completion notification, source map,
  git publish policy, and sub-agent permission handling in `AGENTS.md`.

### Global Provider And External Action Gate vs `research-x-provider-gate`

Classification: DO_NOT_TOUCH / CLARIFY

Global owner:

- General rule: do not call paid, quota-consuming, or network providers; do not install tools,
  enable connectors, or change MCP/plugin/provider configuration from planning or review sources
  unless explicitly requested and permitted by the target project.

Repo-local owner:

- `research_x` no-quota provider freeze.
- Concrete blocked provider lanes: embeddings, rerank, OCR, Reader, external search, LLM context,
  classifiers, answer engines, managed RAG, pricing/budget verification, and real API smoke tests.
- Allowed fake/local/monkeypatched verification.
- `--allow-unpriced-api` disallowance while frozen.
- API Budget Guard behavior after explicit user permission.

Recommended future clarification:

- Add one sentence, if this Skill is edited later: "Global policy blocks external actions by
  default; this repo Skill applies the stricter `research_x` no-quota freeze and API Budget Guard
  rules to provider lanes."

Do not touch:

- All no-quota freeze details in `AGENTS.md`.
- `research-x-provider-gate` rules and verification bullets.
- `.codex/vendor_sources.lock.md` provider/candidate disabled decisions.

### `basic-memory-cli` vs `research-x-memory-workflow`

Classification: KEEP / CLARIFY

Global/basic-memory owner:

- User's local Basic Memory knowledge base.
- General memory recall/write/search outside the `research_x` X evidence pipeline.

Repo-local owner:

- `research_x` memory-search architecture.
- Evidence/Source Bundle First, source restoration, context chunks, citations, route policy,
  OCR/media gates, evals, workflow traces, and AI-callable local search.

Boundary judgment:

- No conflict. Names both include "memory", but they operate on different stores and different
  evidence contracts.

Recommended future clarification:

- If confusion appears, add one sentence to `research-x-memory-workflow`: "`basic-memory-cli`
  handles personal Basic Memory recall; this Skill governs the `research_x` X evidence pipeline and
  citation-ready memory workflow."

Do not touch:

- The invariant `raw source != searchable document != search result != context chunk != citation != answer`.
- Source-bundle restoration requirements.
- Provider-gated media/OCR/retrieval statements.

### `codex-retrospective` / `skillopt-sleep` vs `research-x-decision-loop`

Classification: KEEP / CLARIFY

Global owners:

- `codex-retrospective`: review Codex's recent history and improve long-term behavior.
- `skillopt-sleep`: offline self-evolution, replay, and consolidation behind a held-out gate.

Repo-local owner:

- `research_x` architecture, provider, research, review, audit, and design decision loops.
- Stop-condition checks for project decisions where evidence, counterarguments, provider risk, or
  implementation differences remain.

Boundary judgment:

- No conflict. Global tools optimize Codex behavior over time; `research-x-decision-loop` decides
  project architecture/review questions in the current repo.

Recommended future clarification:

- Add one sentence, if edited later: "This Skill is for current `research_x` design/review
  decisions, not for global Codex self-retrospective or sleep-cycle optimization."

Thin candidates:

- General wording about "evidence" and "counterarguments" overlaps with global decision quality, but
  the repo-local comparison axes are project-specific enough to keep.

### `context-handoff-export` / `codex-fluent` vs `research-x-goal-runner` / `research-x-doc-governance`

Classification: KEEP / CLARIFY

Global owners:

- `context-handoff-export`: portable context export for another agent.
- `codex-fluent`: session hygiene, archive strategy, responsiveness, and handoff discipline.

Repo-local owners:

- `research-x-goal-runner`: phase-by-phase implementation/review/test/commit continuation until a
  target state or human gate.
- `research-x-doc-governance`: project Markdown placement, source-of-truth drift, archive moves,
  and sparse docs.

Boundary judgment:

- No conflict. Global handoff/session Skills manage transferable context and conversation hygiene.
  Repo Skills manage `research_x` execution and document ownership.

Recommended future clarification:

- In `research-x-goal-runner`, if edited later: "Use global handoff/session Skills for context
  export or session hygiene; this Skill governs project phase execution."
- In `research-x-doc-governance`, if edited later: "This Skill governs repository Markdown
  placement, not general context export packaging."

## Repo-Local Skill Invocation Width

All 13 repo-local `agents/openai.yaml` files set `policy.allow_implicit_invocation: true` and have
empty tool dependencies.

| Skill | Current width | Review |
|---|---|---|
| `research-x-context-budget` | Medium | Acceptable. Owns context packs, compression, offload, source pointers, and handoff-ready state without replacing evidence or durable docs. |
| `research-x-decision-loop` | Medium | Acceptable. Description is broad but scoped to `research_x` and explicit loop/review language. |
| `research-x-doc-governance` | Medium | Acceptable. Broad over Markdown, but constrained to named repo files and drift/archive tasks. |
| `research-x-goal-runner` | Medium | Acceptable. Goal-like wording is broad, but workflow requires target state/human gate. |
| `research-x-memory-workflow` | Medium | Acceptable. Broad memory/search terms are necessary for this repo's core domain. |
| `research-x-observability-review` | Medium | Acceptable. Many trigger nouns, but all map to hidden app/CLI/workflow state. |
| `research-x-parallel-review` | Low/Medium | Safe enough because it requires active user permission or standing sub-agent policy. |
| `research-x-prompt-contract` | Medium | Acceptable. Owns prompt schema, status, tool-boundary, and injection-resistance contract checks. |
| `research-x-provider-gate` | Medium | Should remain implicit because provider mistakes are high-risk. |
| `research-x-publishing-illustration` | Low/Medium | Acceptable. Output-layer visual planning only; image generation and evidence replacement remain gated. |
| `research-x-research-intake` | Medium | Acceptable. Owns source candidate classification and source-bundle handoff; not final citation answers or real provider search. |
| `research-x-skill-source-review` | Medium | Acceptable. Owns trust, pin, enable/reject/reference-only decisions; distinct from Skill creation or installation. |
| `research-x-skillization-intake` | Medium | Acceptable, but most likely to overlap with global Skill Hygiene; future clarification would reduce ambiguity. |

No immediate `allow_implicit_invocation` change is recommended. The broadest Skill is
`research-x-skillization-intake`, but its role is intentionally repo-local placement after the
global "existing capability first" check.

Production folder check:

- All 13 repo-local Skill directories contain exactly `SKILL.md` and `agents/openai.yaml`.
- No stale candidate, install-pending, `_foundation_work`, `SMOKE_CHECK`, or rollback-note wording
  was detected in `.agents/skills`.
- The five addendum Skills added after the original review have the expected required sections and
  scoped negative boundaries in `SKILL.md`.

## Over-Repetition Review

### `AGENTS.md`

Classification:

- DO_NOT_TOUCH:
  - no-quota provider freeze
  - `uv` command policy
  - diagnostic pytest runner
  - native repo Skill dispatcher
  - project architecture invariants
  - Markdown source-of-truth map
  - git publish policy
  - completion notification
  - sub-agent permission handling
- THIN:
  - general "do not decide too early" language now partly overlaps with global Skill Hygiene and
    general decision-quality expectations.
  - general "keep Markdown stable and sparse" language partly overlaps with global/project scope,
    but file-role details are project-specific and should remain.
- CLARIFY:
  - It may eventually help to say that global policy owns general Skill creation/install hygiene,
    while this file owns `research_x` safety, command, architecture, and dispatcher rules.

### `README.codex.md`

Classification:

- KEEP:
  - compact repo entry point
  - current mission
  - CLI surfaces
  - repo Skill inventory
- DO_NOT_TOUCH:
  - mandatory runtime rules
  - no-spend foundation v1 state
  - provider-freeze reminder
  - completion notification
- THIN:
  - some runtime rules duplicate `AGENTS.md`, but `README.codex.md` is intentionally a compact
    orientation file. Thin only if `AGENTS.md` remains mandatory first read.
- CLARIFY:
  - The repo Skill list could later note that global Skills/plugins still own cross-project
    handoff, memory, retrospective, browser, GitHub, OpenAI docs, image generation, and
    Skill/plugin creation or installation.

### `.agents/skills/*/SKILL.md`

Classification:

- KEEP:
  - project-specific workflows, source files, invariants, verification expectations, and stop
    conditions.
- THIN:
  - generic Skill hygiene phrasing in `research-x-skillization-intake`.
  - generic provider caution wording if it is fully covered by global policy, but only after keeping
    `research_x` no-quota details intact.
- CLARIFY:
  - boundary sentences listed above for skillization, provider gate, memory workflow, decision loop,
    goal runner, and doc governance.
- DO_NOT_TOUCH:
  - provider freeze mechanics
  - memory/search evidence invariants
  - source-of-truth file roles
  - sub-agent permission checks
  - verification commands and `uv` expectations

### `.agents/skills/*/agents/openai.yaml`

Classification: KEEP with watch

All repo-local Skills are implicitly invocable and tool-free. This is acceptable because each name
and default prompt is prefixed with `research_x` and the dispatcher in `AGENTS.md` scopes them to
project work. No immediate narrowing is required.

Future risk:

- If a global Skill with a similar trigger becomes more authoritative, the local `default_prompt`
  can add a one-sentence project-scope qualifier instead of disabling implicit invocation.

### `.codex/skill_manifest.lock`

Classification: DO_NOT_TOUCH

This file is a repo-local lock for enabled repo Skills and disabled third-party Skill/tool/provider
candidates. It directly implements the global Existing Capability First and Provider And External
Action Gate principles in a project-owned artifact.

Do not thin:

- disabled external entries
- human review requirements
- commit pin requirements
- negative trigger test requirements
- provider quota disabled settings
- connector/global enablement disabled settings

### `.codex/vendor_sources.lock.md`

Classification: DO_NOT_TOUCH

This file states that source decisions are review artifacts, not permission to install, clone,
enable, or call third-party Skills, connectors, providers, or tools. It aligns with global Imported
Sources And Execution Boundary and Provider And External Action Gate.

Do not thin:

- no bulk install language
- provider freeze language
- connector/credential-bearing source restrictions
- reference-only source decisions

## External Source Pin Addendum

The 2026-06-12 post-install audit checked source pin metadata for external Skill/source candidates
that affected the repo-local addendum package.

| Source | State | Review |
|---|---|---|
| `superpowers` | `pinned_license_checked`, disabled | MIT license and `v5.1.0` peeled commit `f2cbfbefebbfef77321e4c9abc9e949826bea9d7` checked. It remains disabled; full source/script/hook audit and negative trigger tests are still required before any enablement. |
| `ian-xiaohei-illustrations` | `pinned_license_checked`, disabled | MIT license and `v1.0.0` ref `686575741a61e2c0be5e4c6d3615ebf6217dd322` checked. It remains creative optional/reference only, not `research_x` evidence, and image generation still requires the normal gate. |

These pin checks are not install permission and do not authorize importing external code into
production repo-local Skills.

Not completed in this addendum:

- Full source/script/hook audit for `superpowers`.
- Pin/license review for the remaining disabled, reference-only, blocked, or rejected external
  manifest entries that still have blank or `TBD_PINNED_COMMIT` commit values.
- Any production behavior change to `.agents/skills`.

## Future Edit Candidates

The 2026-06-12 addendum made only lock/test/review-artifact updates. If a later task asks for
alignment edits, the lowest-risk order is:

1. Add short CLARIFY boundary sentences to relevant repo Skills.
2. Thin generic Skill hygiene repetition from `research-x-skillization-intake` only after those
   boundary sentences exist.
3. Thin only generic repetition from `AGENTS.md`; keep all project-specific safety, command,
   architecture, dispatcher, and notification rules.
4. Leave manifest lock and vendor source lock intact unless the review/validation process itself
   changes.

## Final Assessment

The repo-local Skill set reviewed in this artifact was aligned with global G10/G11 context. The
project Skills should remain enabled and implicitly invocable unless a later manifest/source review
changes that decision. The main future work remains documentation thinning and boundary
clarification, not functional Skill changes.
