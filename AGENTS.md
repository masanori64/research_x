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

When research changes a design decision, add the durable current conclusion to
`docs/memory-pipeline-v2.md`. Move superseded or bulky historical notes to
`docs/memory-pipeline-archive.md` only when they would otherwise bloat the active source. Avoid
duplicating the same design text across multiple files.

Before implementing a design or architecture change, update the relevant Markdown source of truth
first. When Plan Mode or the user provides a concrete implementation plan, record the durable parts
of that plan before code: for memory-search design changes, update `docs/memory-pipeline-v2.md`;
for durable agent behavior changes, update `AGENTS.md`; for public commands or milestone state,
update `README.md` and/or `PROJECT.md`. This rule is about preventing implementation drift; do not
scatter transient notes into new Markdown files.

## Decision Quality

Do not make architecture or provider decisions just because one plausible source, benchmark, or
implementation path appears. First evaluate whether the decision itself is justified.

When an important decision is uncertain:

1. inspect the repo state and current source-of-truth documents;
2. search primary sources first, then secondary/community sources if primary sources are
   insufficient;
3. treat search results as evidence inputs, not as automatic truth;
4. compare alternatives against the user's goal, local data shape, cost, reliability, provenance,
   token efficiency, and failure modes;
5. if the evaluation exposes a new uncertainty, repeat the search/evaluation loop before deciding.

Record only durable conclusions in Markdown. Keep transient exploration out of the docs unless it
changes a design decision.

## Git Publish Policy

When the user asks for implementation work in this repository, commit and push the completed scoped
changes unless the worktree contains unrelated edits that need separation.

## Goal Continuation

When a user-provided `/goal` or goal context defines a target state, keep working phase by phase
until that target state is reached or a true blocker repeats. A normal phase is:

1. implement the next scoped change;
2. review for narrowed behavior, weak fallbacks, unjustified shortcuts, brittle assumptions, and
   missing entry points;
3. fix the issues found by that review;
4. run the relevant lint/tests or runtime checks;
5. commit and push the completed phase.

Do not stop merely because one phase was committed if the goal still has remaining phases. Continue
to the next aligned phase. Do not redefine completion around the work already done; verify the
current state against the stated goal before considering it complete.

For long goals that may hit session or token limits, leave the project resumable before the limit is
reached: commit and push completed phases, keep uncommitted changes small, and make the next action
visible in `PROJECT.md` only when the milestone itself changes. On resume, check `git status`,
`PROJECT.md`, `docs/memory-pipeline-v2.md`, and the active goal before choosing the next phase.

Continue autonomously until the goal is complete or a real human-intervention gate is reached.
Human-intervention gates are limited to API keys, billing or external-service contracts,
irreversible deletion, secret handling, legal/ToS-sensitive choices, explicit user stop/pause
messages, or high-impact design choices that remain unresolved after the decision-quality loop.

## Completion Notification

At the end of every work session, run:

```powershell
uv run python -m research_x notify --message "作業が終了しました"
```

## Parallel Work

Use the latest explicit user instruction for sub-agent permission. Do not spawn sub-agents when the
current conversation bans or pauses them; compensate with local code inspection, parallel shell
reads, web research, and focused review loops instead.

When sub-agent use is explicitly permitted and a task can be split into independent parts, use an
appropriate number of sub-agents instead of defaulting to one. Use sub-agents for work that can
proceed without touching the same files or otherwise conflicting with active work in the repository.

Sub-agents are scoped helpers, not owners of the final change. The parent agent remains responsible
for checking their outputs, integrating the final diff, running verification, and completing
notification/publish steps.

Recommended roles include:

- explorer: read-only codebase inspection, risk review, gap analysis;
- research sidecar: external primary/secondary source investigation while implementation continues;
- worker: bounded code changes with a disjoint file ownership scope;
- verifier: tests, audit commands, or review of a completed patch.

For each spawned sub-agent, give a narrow role, clear ownership, expected output, and whether it may
edit files. Keep the main agent on the critical path; do not delegate the immediate blocking step if
waiting would stall implementation. When sub-agents finish, integrate their findings into the main
decision, then close them unless another immediate follow-up needs their retained context. Completed
sub-agents left open consume the limited parallel-agent slots and can prevent new agents from being
created.

If a completed sub-agent result is too shallow, too generic, or misses an important axis, the parent
agent may send a follow-up task to that same agent before closing it. The follow-up must name the
specific missing axis or counterargument to investigate, rather than asking for a broad repeat of the
same work. Do not treat the first sub-agent answer as sufficient when the task requires strong
research quality and the returned evidence does not yet justify the decision.
