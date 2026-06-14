---
name: research-x-decision-loop
description: Use for research_x architecture, provider, research, review, audit, or design decisions when the user asks to search, verify, loop, continue, re-evaluate, check counterarguments, avoid premature stopping, or decide whether enough evidence exists.
---

# research-x Decision Loop

Use this skill when a decision could change architecture, provider choices, evidence contracts,
workflow behavior, or durable repository instructions.
Global retrospective and sleep-cycle skills optimize Codex behavior over time; this skill is for
current `research_x` architecture, review, audit, and design decisions.
For search or research outputs, also apply
`../../skill-references/search-quality-contract.md` before final judgment.
For provider-facing decisions, also apply
`../../skill-references/provider-quality-contract.md`.

## Workflow

1. Inspect the current repo state and the relevant source-of-truth files before deciding.
2. Search primary sources first when the answer depends on current external facts. Use
   secondary/community sources only to fill gaps, test practical risk, or find counterexamples.
3. Treat search results as evidence inputs, not as automatic truth.
4. Compare alternatives against:
   - the user's stated goal;
   - local data shape;
   - cost and quota risk;
   - reliability and failure modes;
   - provenance and citation quality;
   - token efficiency;
   - implementation and maintenance cost.
5. If the evaluation exposes a new uncertainty, run another targeted loop instead of finalizing.
6. At the end of each loop, ask: if the user now said "not finished, continue", is there a
   non-duplicate issue, counterargument, design difference, or implementation difference to pursue?
   If yes, run it. Stop only when the next loop would be a rephrasing or the remaining work is a
   human-intervention gate.

## Output Shape

- State the active question.
- List new information.
- Mark overlap with prior information.
- Name counterarguments or gaps.
- State design or implementation deltas.
- State whether another loop is justified.

Record only durable conclusions in repository Markdown.
