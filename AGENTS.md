# Agent Working Rules

This repository is a shared workspace. Before editing, check the current diff and do not revert or
overwrite uncommitted changes made by other workers.

## No-Quota Provider Freeze

External provider API calls are prohibited unless the user explicitly lifts this no-quota freeze in
the current conversation. This includes paid usage, free-tier usage, trial credits, and any
zero-dollar quota consumption. Do not run commands or code paths that can send provider HTTP
requests to Gemini, OpenAI, Voyage, Jina, Cohere, Mistral, Serper, Brave, or similar services.

Allowed while the freeze is active:

- local/fake providers;
- read-only estimates and coverage commands that do not send provider HTTP requests;
- tests that monkeypatch provider calls;
- static code inspection and documentation work;
- implementation of provider integrations when verification uses fake/local providers only.

Disallowed while the freeze is active:

- real embedding, OCR, rerank, classifier, answer, reader, external search, LLM-context, or
  managed-RAG calls;
- commands using `--allow-unpriced-api`;
- "small smoke tests" against real providers;
- free-tier, trial-credit, or zero-dollar provider calls.

If the user later explicitly permits provider quota use, keep the API Budget Guard enabled, run
offline estimates first, start with the smallest limit, and stop before the next provider call if
pricing, quota, or budget evidence is unclear.

## Commands

Use the project's `uv` environment for Python tooling. Do not run global `python`, `pytest`, or
`ruff` directly.

Preferred command forms:

```powershell
uv sync
uv run python -m research_x ...
uv run pytest ...
uv run ruff check src\research_x tests
```

Keep lint targets explicit and consistent with `README.md` and `PROJECT.md`.
If `uv run pytest` appears slow or stuck, do not keep guessing manually. Use the repository
diagnostic runner to isolate the slow unit:

```powershell
uv run python -m research_x test-diagnose tests\test_memory.py --mode tests --timeout-seconds 60 --stop-on-fail
```

The diagnostic runner executes pytest through `uv`, bounds each file or test node, kills timed-out
child process trees, and reports the exact slow/failed target. Use it before narrowing the suite in
an ad hoc way.

## Native Skill Invocation

This repository uses Codex native Skill selection as the main recurring-workflow mechanism. At the
start of each request, let the available Skill descriptions guide whether a repo Skill applies; if
the native Skill is not loaded but the task clearly matches a listed workflow, read the referenced
`SKILL.md` directly.

Use this section as a small dispatcher, not as a full algorithm. The detailed workflow belongs in
the Skill file so `AGENTS.md` stays short and Codex can rely on progressive disclosure.

Always-on triggers:

- no-quota provider freeze: active unless the current conversation explicitly lifts it;
- command policy: use `uv` command forms for Python tooling;
- completion notification: run the notify command at the end of the work session;
- git publish policy: commit and push scoped implementation work when complete and separable.

Prompt-dependent triggers:

- implementation or code-change request: inspect `git status`, preserve unrelated changes, make the
  change, verify it, then commit/push when scoped work is complete;
- design, architecture, provider, or memory-search change: update the relevant Markdown source of
  truth before code, then use `.agents/skills/research-x-memory-workflow/SKILL.md` when applicable;
- research, review, audit, "もう一度", "loop", "徹底", "終わっていない", or similar continuation
  language: use `.agents/skills/research-x-decision-loop/SKILL.md`;
- recurring Codex behavior, skillization, AGENTS.md bloat, or instruction-surface placement: use
  `research-x-skillization-intake` or
  `.agents/skills/research-x-skillization-intake/SKILL.md` to decide whether the behavior belongs in
  prompt context, `AGENTS.md`, repository docs, a repo skill, hook, plugin, MCP, or automation;
- `/goal` or goal-like target state: activate Goal Continuation and continue phase by phase until the
  target or a real human-intervention gate is reached, using
  `.agents/skills/research-x-goal-runner/SKILL.md` for the detailed loop;
- sub-agent policy prompt: when the user permits, bans, pauses, mentions, or asks to follow/check
  agent, sub-agent, エージェント, parallel, or 並列-agent behavior, update the current sub-agent
  policy from the latest explicit user instruction in this conversation, not only the newest
  message. Mentioning the topic fires the policy check; spawning still requires explicit
  permission. Use `.agents/skills/research-x-parallel-review/SKILL.md` when sub-agent work is
  permitted and useful;
- app/UI observability concern: treat hidden workflow state as an implementation gap, not just a UI
  wording issue. Use `.agents/skills/research-x-observability-review/SKILL.md` to expose the
  relevant trace or evidence state before considering the task done;
- provider-facing work: use `.agents/skills/research-x-provider-gate/SKILL.md` before any embedding,
  rerank, OCR, Reader, external search, LLM-context, classifier, answer, or managed-RAG action.

Before sending a final answer, re-check the newest user request and any active repo Skill. If a
matched Skill still has unfinished non-duplicate work, continue instead of finalizing.

## Project Architecture

For the memory-search project, read `docs/memory-pipeline-v2.md` before making design changes. It is
the current source of truth for the AI-callable evidence pipeline. `PROJECT.md` tracks the
implementation milestones, and `README.md` is the high-level repository reference.

The memory-search architecture is Evidence/Skill/Workflow first. Real API embeddings are optional
recall arms inside a workflow-gated portfolio, not the top-level system objective. Diagnostic
`local_hash` embeddings are wiring checks only and must not be treated as production evidence or a
promotion candidate.

For Gemini Embedding 2, keep text recall and native media recall as separate contracts. Text
embedding uses `memory_embeddings`; raw image/PDF/video/audio embedding must use a media-specific
contract that can restore `media_id -> tweet_id -> source bundle -> citation` before it can be
eligible for workflow promotion. A raw media vector match is a candidate signal, not image-content
evidence unless OCR/caption/VLM text has been turned into citation-ready context chunks.

Do not create additional memory-architecture Markdown files unless the user explicitly asks. Update
the existing source-of-truth file instead, so Codex does not have to scan a spreading design surface.

## Markdown Governance

Keep Markdown stable and sparse:

- `AGENTS.md`: durable agent rules and repository working policy.
- `README.md`: high-level human/repository reference and implemented CLI surface.
- `PROJECT.md`: short milestone tracker only.
- `docs/memory-pipeline-v2.md`: detailed memory/search architecture and decision notes.
- `docs/memory-pipeline-archive.md`: indexed historical notes; inspect the index first and read
  only targeted sections when prior research is needed.
- `docs/pipeline.md`: acquisition/auth/provider pipeline details.

Use `.agents/skills/research-x-doc-governance/SKILL.md` for detailed Markdown placement, archival,
and drift checks. Before implementing a design or architecture change, update the relevant
Markdown source of truth first. Do not scatter transient notes into new Markdown files.

## Decision Quality

Do not make architecture or provider decisions just because one plausible source, benchmark, or
implementation path appears. First evaluate whether the decision itself is justified.

Use `.agents/skills/research-x-decision-loop/SKILL.md` for detailed research, review, audit, and
loop-stop mechanics. Record only durable conclusions in Markdown. Keep transient exploration out of
the docs unless it changes a design decision.

## Git Publish Policy

When the user asks for implementation work in this repository, commit and push the completed scoped
changes unless the worktree contains unrelated edits that need separation.

## Goal Continuation

When a user-provided `/goal` or goal-like context defines a target state, use
`.agents/skills/research-x-goal-runner/SKILL.md`. Continue autonomously until the goal is complete
or a real human-intervention gate is reached.

## Completion Notification

At the end of every work session, run:

```powershell
uv run python -m research_x notify --message "作業が終了しました"
```

## Parallel Work

Use the latest explicit user instruction for sub-agent permission. Do not spawn sub-agents when the
current conversation bans or pauses them; compensate with local code inspection, parallel shell
reads, web research, and focused review loops instead.

When sub-agent use is explicitly permitted and a task can be split into independent parts, use
`.agents/skills/research-x-parallel-review/SKILL.md` for role design and integration. The parent
agent remains responsible for checking outputs, integrating changes, verification, notification, and
publish steps.
