# Diagram Design Harness

This harness is for diagrams made in the `research_x` presentation lane. It is a
human-review contract, not a claim source and not answer evidence.

## Goal

Create diagrams for first-time human readers.

The diagram should help a person understand the project faster than reading the
repository. It should not merely prove that the repository has many files,
classes, tables, commands, or implementation details.

## Core Rule

Before drawing, decide what the reader should understand after 10 seconds and
after 60 seconds.

- 10 seconds: the main responsibility, boundary, or flow is visible without
  zooming.
- 60 seconds: the reader can explain the diagram back in ordinary language.

If a diagram fails either test, simplify the message or split the diagram.

## Human Readability

Use these as review questions, not as a narrow checklist:

- Can the diagram be read without zooming on a normal slide?
- Does the layout have a stable reading order?
- Do arrows mostly move in one direction instead of bouncing around?
- Are crossing arrows rare and meaningful?
- Are related components grouped by what they do, not by source-tree placement?
- Are labels written for a first-time reader?
- Are implementation names used only when they are truly useful names?
- Are English terms kept for proper nouns and established product/domain terms,
  while ordinary explanation is Japanese?
- Is the diagram explaining the system, rather than dumping facts from the code?
- Does the diagram look like something a person prepared for another person,
  not like an automatic inventory?

## Failure Examples

These are examples of what to avoid. They are not the whole rule.

- A very tall or very wide diagram that requires zooming.
- Arrows that cross repeatedly or move back and forth without a clear reading
  path.
- Class names, file names, table names, or command names copied directly into the
  diagram without explaining what they mean.
- English labels used for ordinary explanation when a Japanese label would be
  clearer.
- A diagram that is technically accurate but unreadable for someone seeing the
  project for the first time.

## Acceptable Use Of Concrete Names

Use concrete names when they anchor the reader:

- product or repository names, such as `research_x`;
- established domain terms, such as `Source Bundle` or `Citation`;
- runtime or tool names, such as `SQLite`, `D2`, `Marp`, or `API Budget Guard`.

Do not use concrete names as a substitute for explanation. If a file, class,
table, or command name appears, the surrounding label must say what role it plays
for the reader.

## Review Loop

For each diagram:

1. State the one sentence the diagram should communicate.
2. Draft the diagram at slide size, not canvas size.
3. Remove labels and arrows that do not support the one sentence.
4. Replace implementation inventory with role-based language.
5. Check whether the slide can be understood without zooming.
6. If the diagram still feels crowded, split it instead of shrinking it.

Passing automated checks is not enough. The final gate is whether a human reader
can follow the diagram without knowing the repository internals.
