---
name: research-x-chatgpt-control
description: Use when Codex should consult or control a visible ChatGPT web session through the codex-chatgpt-control pattern, including planning prompts, threads, files, downloads, bridge blockers, and local diagnostics.
---

# research-x ChatGPT Control

Use this skill when a task would benefit from visible, user-directed ChatGPT web consultation from
Codex.

## Contract

- This is not an OpenAI API wrapper and not a hidden ChatGPT endpoint.
- Keep Codex as the local execution owner. ChatGPT web is a consultation lane for planning,
  second-opinion review, long-context critique, research synthesis, naming, or design feedback.
- Use visible ChatGPT sessions only, with user-approved prompts, files, downloads, and account-level
  actions.
- Treat ChatGPT output as a model judgment or exploration note. It is `citation_excluded` until any
  cited source is separately fetched, restored, chunked, and verified by the research_x evidence
  pipeline.
- Stop on login, captcha, rate-limit, permission, selector drift, missing browser bridge, or
  ambiguous confirmation blockers. Report the blocker; do not retry blindly.

## Local Tooling

Use the local no-provider helper before attempting any live browser workflow:

```powershell
uv run python -m research_x codex-chatgpt-control doctor
uv run python -m research_x codex-chatgpt-control capabilities
```

Create a redacted local consultation plan:

```powershell
uv run python -m research_x codex-chatgpt-control plan --workflow runner_run --prompt "..." --out runs\chatgpt_control
uv run python -m research_x codex-chatgpt-control render --plan runs\chatgpt_control\<plan>.json --language node
```

Use `--include-prompt` only when the user wants the prompt body stored in the local plan artifact.
Attach files only with explicit user approval via repeated `--file` arguments.
Use `--allow-visible-chatgpt` only after explicit user approval for a visible ChatGPT session.
Use `--allow-npx-package` only when the user accepts package resolution through `npx`; otherwise
provide an installed backend executable through repeated `--backend-command` tokens.

Supported local plan workflows are `runner_run`, `runner_plan`, `runner_stream`,
`responses_create`, `ask`, `ask_in_thread`, `ask_with_files`, `ask_and_download`, `run_messages`,
`open_thread`, `read_latest`, `copy_latest`, `download_latest`, and `doctor`. The helper records the
selected upstream command, expected blockers, run limits, redaction policy, and citation exclusion
policy.

## Runtime Requirements

Real browser-control runs require:

- Node.js 20 or newer and npm;
- the external `codex-chatgpt-control` runtime or source checkout;
- Chrome with a signed-in visible ChatGPT web session;
- a compatible Codex/browser bridge exposing `globalThis.agent`;
- permission to use or open a visible ChatGPT tab.

Ordinary shell checks should not operate ChatGPT web. A structured bridge blocker is safe and
expected when no compatible visible browser bridge is present.

## Negative Triggers

Do not use this skill for:

- routine memory-search evidence retrieval;
- hidden automation against ChatGPT or private endpoints;
- provider API calls;
- scraping private ChatGPT session data;
- replacing source-bundle restoration, context chunks, citations, or eval gates.
