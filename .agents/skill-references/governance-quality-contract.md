# Governance Quality Contract

This is a shared quality contract for `research_x` Markdown governance, Skill routing, prompt
contracts, source/Skill adoption review, manifest locks, vendor/source locks, and instruction
surface placement.

It is not an evidence contract and not an implementation workflow. Its job is to keep durable
instructions, docs, prompts, Skills, and external-source decisions narrow, auditable, and
non-duplicative.

## Minimum Contract

1. Classify the surface.
   - Decide whether the change belongs in prompt/thread context, `AGENTS.md`, `README.codex.md`,
     `README.md`, `PROJECT.md`, `docs/memory-pipeline-v2.md`, `docs/memory-pipeline-archive.md`,
     `docs/pipeline.md`, `.agents/skills`, `.agents/skill-references`, hooks/plugins/MCP/apps, or
     no durable surface.

2. Check the existing owner first.
   - Prefer the narrowest existing Skill, shared reference, docs file, test, or lock entry before
     creating a new Skill or new architecture Markdown.
   - Keep `AGENTS.md` as a dispatcher, not a full workflow manual.

3. Preserve boundaries.
   - Separate durable rules, historical notes, implementation status, public references, source
     decisions, prompt contracts, and repeatable workflows.
   - Do not duplicate the same rule across multiple files unless one file is only a pointer.

4. Keep enablement explicit.
   - Third-party Skills, tools, providers, connectors, hooks, and prompt frameworks remain disabled,
     gated, rejected, or reference-only until reviewed, pinned, and tested.
   - Source-lock and manifest entries are review artifacts, not install permission.

5. End with a governance status.
   - Use `no-durable-surface`, `doc-updated`, `skill-updated`, `reference-updated`,
     `manifest-updated`, `source-locked`, `reference-only`, `gated`, `rejected`, or `needs_review`.

## Skill-Specific Ownership

- `research-x-doc-governance`: owns Markdown placement, archive moves, drift checks, and source of
  truth boundaries.
- `research-x-skillization-intake`: owns whether behavior belongs in prompt context, docs, a Skill,
  hook/plugin/MCP/app, automation, or no durable surface.
- `research-x-prompt-contract`: owns prompt schema/status/tool-boundary contracts and prompt
  regression cases.
- `research-x-skill-source-review`: owns external or internal source trust, pinning, enable/reject,
  reference-only, and manifest/vendor-lock risk.

## Do Not

- Do not create a Skill for a one-off note or research result.
- Do not add new memory-architecture Markdown unless explicitly requested.
- Do not turn a source review into permission to install, clone, enable, call, or connect.
- Do not rely on prompt prose to replace code-side auth, DB-write, provider-budget, or safety gates.
- Do not hide trigger overlap, removal path, source provenance, or negative trigger gaps.

## Verification

- For documentation or Skill edits, run `git diff --check`.
- For Skill/manifest/source-lock edits, run:

```powershell
uv run python scripts/validate_skill_manifest.py
uv run pytest tests/test_skill_manifest.py
uv run pytest tests/skills/test_vendor_sources_lock.py
```

- For prompt-contract changes, run the relevant prompt-contract tests.
