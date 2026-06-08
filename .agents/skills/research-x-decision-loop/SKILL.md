---
name: research-x-decision-loop
description: Use for architecture, provider, research, review, audit, or design decisions that require repo inspection, primary/secondary evidence, counterarguments, repeated loop checks, and explicit stop-condition evaluation.
---

# research-x Decision Loop

Use this skill when a decision could change architecture, provider choices, evidence contracts,
workflow behavior, or durable repository instructions.

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
