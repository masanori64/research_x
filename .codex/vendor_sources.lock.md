# Vendor Source Lock

Created: 2026-06-10

This lock records source decisions used by `.codex/skill_manifest.lock`. It is a review artifact,
not permission to install, clone, enable, or call any third-party Skill, connector, provider, or
tool.

## Policy

- Repo-local Skills under `.agents/skills/` are the only enabled entries.
- Third-party Skills and tools are disabled until pinned, reviewed, scanned, and covered by negative
  trigger tests.
- Connector and credential-bearing sources must not be enabled globally.
- Provider-backed sources remain blocked by the no-quota freeze unless the user explicitly lifts it
  in the current conversation and API Budget Guard preflight passes.
- Catalogs are reference-only and must never be bulk-installed.

## Locked Sources

| Ref | Manifest entry | Source | Locked decision |
|---|---|---|---|
| repo | `research-x-*` repo Skills | `.agents/skills/*/SKILL.md` | Enabled repo-local only. |
| S08 | `headroom` | https://github.com/chopratejas/headroom | Disabled; security/local-dependency gate. |
| S09 | `supermemory` | https://github.com/supermemoryai/supermemory | Disabled; architecture reference only. |
| S11 | `superpowers` | https://github.com/obra/superpowers | Disabled; review then optional. |
| S12 | `superclaude-framework` | https://github.com/SuperClaude-Org/SuperClaude_Framework | Reference only for Codex. |
| S13 | `minimax-skills` | https://github.com/MiniMax-AI/skills | Disabled; stack-specific optional. |
| S14 | `anthropic-official-skills` | https://github.com/anthropics/skills | Format reference only. |
| S15 | `vercel-agent-skills` | https://github.com/vercel-labs/agent-skills | Disabled; frontend optional only. |
| S16 | `planning-with-files` | https://github.com/OthmanAdi/planning-with-files | Disabled; adapt only if no duplicate tracker. |
| S17 | `context-engineering-skills` | https://github.com/muratcankoylan/Agent-Skills-for-Context-Engineering | Disabled; reference/adapt after review. |
| S18 | `composio-skills` | https://github.com/ComposioHQ/skills | Disabled; do not global install. |
| S19 | `antfu-skills` | https://github.com/antfu/skills | Reference only. |
| S20 | `awesome-agent-skills` | https://github.com/VoltAgent/awesome-agent-skills | Catalog only; no bulk install. |
| S21 | `serper` | https://serper.dev | Disabled; provider gate only. |
| S22 | `chatgpt-backend-api` | https://help.openai.com/en/articles/7260999-how-do-i-export-my-chatgpt-history-and-data | Unofficial backend rejected; official export only. |
| S23 | `gpt-backend-api` | official OpenAI docs checked instead | Unofficial backend rejected. |
| S24 | `searxng`, `webshare` | https://docs.searxng.org/ and https://www.webshare.io/ | SearXNG optional discovery hint; Webshare rejected default. |
| S25 | `ai-assistant-workspace` | https://github.com/karaage0703/ai-assistant-workspace | Reference only. |
| S26 | `ian-xiaohei-illustrations` | https://github.com/helloianneo/ian-xiaohei-illustrations | Creative optional/reference; explicit visual-planning only, not research_x core or evidence, and no image generation without gate. |
| S28 | `matt-pocock-skills` | https://github.com/mattpocock/skills | Reference only. |

## Source Refs Not Manifest Entries

S01-S07, S10, S27, S29-S31 are design or evidence references rather than installable Skill/tool
candidates. Their durable conclusions are reflected in `docs/memory-pipeline-v2.md`,
`docs/pipeline.md`, and `docs/memory-pipeline-archive.md`.
