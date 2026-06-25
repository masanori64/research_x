# Vendor Source Lock

Created: 2026-06-10

This lock records source decisions used by `.codex/skill_manifest.lock`. It is a review artifact,
not permission to install, clone, enable, or call any third-party Skill, connector, provider, or
tool.

## Policy

- Repo-local Skills under `.agents/skills/` are the only enabled entries.
- Third-party Skills and tools are disabled until pinned, reviewed, scanned, and covered by negative
  trigger tests, but disabled does not mean discarded. Durable candidates are assigned an adoption
  shape: `adopt`, `bridge`, `staging`, `provider_gated`, or `historical`.
- Connector and credential-bearing sources must not be enabled globally.
- Provider-backed sources remain blocked by the no-quota freeze unless the user explicitly lifts it
  in the current conversation and API Budget Guard preflight passes.
- Catalogs are reference-only and must never be bulk-installed.
- Hook, MCP, plugin, connector, dependency, and local-model risks route to isolated staging,
  dry-run, source/dependency review, and manual promotion. Only paid/quota provider execution is a
  hard execution block by this lock.
- Codex foundation candidates belong to `maasa/.codex`; `research_x` keeps only thin bridge
  contracts needed by the AI-callable X memory-search tool.

## Locked Sources

| Ref | Manifest entry | Source | Locked decision |
|---|---|---|---|
| repo | `research-x-*` repo Skills | `.agents/skills/*/SKILL.md` | Enabled repo-local only. |
| S08 | `headroom` | https://github.com/chopratejas/headroom | Disabled; security/local-dependency gate. |
| S09 | `supermemory` | https://github.com/supermemoryai/supermemory | Disabled; architecture reference only. |
| S11 | `superpowers` | https://github.com/obra/superpowers | Disabled; review then optional. MIT license and `v5.1.0` peeled commit `f2cbfbefebbfef77321e4c9abc9e949826bea9d7` checked 2026-06-12; no full source/script/hook audit yet. |
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
| S26 | `ian-xiaohei-illustrations` | https://github.com/helloianneo/ian-xiaohei-illustrations | Creative optional/reference; MIT license and `v1.0.0` ref `686575741a61e2c0be5e4c6d3615ebf6217dd322` checked 2026-06-12; explicit visual-planning only, not research_x core or evidence, and no image generation without gate. |
| S28 | `matt-pocock-skills` | https://github.com/mattpocock/skills | Reference only. |
| S32 | `agentmemory` | https://github.com/rohitg00/agentmemory | Disabled; source-review-required. Apache-2.0 license and `v0.9.27` peeled commit `25158519d5d68b9060a97ba5bdcccc3e1aba6d79` checked 2026-06-22. GPT Pro raw and follow-up classified it as source-review priority but "no install now": useful comparison target for hook/MCP/auto-capture/decay/search/inject design, blocked by plugin/MCP/hook enablement, prompt/tool-output capture, retention/deletion/redaction, version-drift, provider/key, local server, and overlap with Basic Memory/context handoff/planning files/research_x memory surfaces. |
| S33 | `single-file-wbs` | https://github.com/piguo45/single-file-wbs | Pinned local tool canary for item 11 WBS/progress visualization. MIT license and `v1.2.0` commit `322895a23f49028b53ae8c8a1710d6db45cdf726` checked 2026-06-23. Vendored unchanged under `tools/wbs_viewer/vendor/single-file-wbs-v1.2.0/`; allowed for local WBS JSON visual review only. No plugin, MCP, hook, provider, hosted service, or evidence promotion; do not edit vendored upstream in place. |
| S34 | `pdgkit` | https://github.com/shibayamalicht/pdgkit, https://note.com/nonoonenono/n/n0701699bbf3c, and npm `@shibayama/pdgkit` | Reference-only historical source. MIT license and npm version `0.1.2` were checked 2026-06-24 during the item 34/35 canary, but the local tool lane has been decommissioned and removed from active repo surfaces. Do not install, restore, invoke, register MCP, add a root dependency, use for presentation generation, or promote outputs as evidence. Current presentation generation uses the D2/Marp boundary in `.codex/implementation-plans/2026-06-24-presentation-generation-flow.md`. |

## Source Refs Not Manifest Entries

S01-S07, S10, S27, S29-S31 are design or evidence references rather than installable Skill/tool
candidates. Their durable conclusions are reflected in `docs/memory-pipeline-v2.md`,
`docs/pipeline.md`, and `docs/memory-pipeline-archive.md`.
