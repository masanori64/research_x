# Vendor Source Lock

Created: 2026-06-10

This lock records external source and candidate decisions for `research_x` as an AI-callable X
memory-search tool. It is a review artifact, not permission to install, clone, enable, or call any
third-party Skill, connector, provider, or tool.

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
- `control/adoption_registry.toml` is the machine-readable project adoption boundary. It must not
  enable, install, clone, call, or promote external sources by itself.

## Locked Sources

| Ref | Candidate | Source | Locked decision |
|---|---|---|---|
| repo | `research-x-*` repo Skills | `.agents/skills/*/SKILL.md` | Enabled repo-local only. |
| S01 | `firecrawl` | https://www.firecrawl.dev/ | Provider-gated external source candidate; no network/provider call without the provider gate. |
| S07 | `occ-rag` | https://github.com/optimal-cognitive-core/OCC-RAG | Retrieval-eval reference only; fixture shape may be adapted locally, runtime is not imported. |
| S10 | `archify` | https://github.com/tt-a1i/archify | Control-artifact renderer reference only; diagram outputs never become evidence. |
| S16 | `zvec` | https://github.com/alibaba/zvec | Staged local-backend candidate; dependency/source review required before install or default use. |
| S17 | `saas-stop-condition` | https://github.com/XMUDeepLIT/SAAS | Retrieval stop-condition eval reference only; no runtime import. |
| S21 | `serper` | https://serper.dev | Disabled; provider gate only. |
| S24 | `searxng`, `webshare` | https://docs.searxng.org/ and https://www.webshare.io/ | SearXNG optional discovery hint; Webshare rejected default. |
| S33 | `single-file-wbs` | https://github.com/piguo45/single-file-wbs | Pinned local WBS/progress visualization tool. MIT license and `v1.2.0` commit `322895a23f49028b53ae8c8a1710d6db45cdf726` checked 2026-06-23. Vendored unchanged under `tools/wbs_viewer/vendor/single-file-wbs-v1.2.0/`; allowed for local WBS JSON visual review only. No plugin, MCP, hook, provider, hosted service, or evidence promotion; do not edit vendored upstream in place. |
| S34 | `pdgkit` | https://github.com/shibayamalicht/pdgkit, https://note.com/nonoonenono/n/n0701699bbf3c, and npm `@shibayama/pdgkit` | Reference-only historical source. MIT license and npm version `0.1.2` were checked 2026-06-24 during the item 34/35 canary, but the local tool lane has been decommissioned and removed from active repo surfaces. Do not install, restore, invoke, register MCP, add a root dependency, use for presentation generation, or promote outputs as evidence. Current presentation generation uses the D2/Marp boundary in `C:/Users/maasa/.codex/foundation/project_plans/research_x/2026-06-24-presentation-generation-flow.md`. |
| S35 | `tavily` | https://docs.tavily.com/documentation/api-reference/introduction | Provider-gated external source/search candidate; official docs require API key authentication, so no call under no-quota freeze. |
| S36 | `exa` | https://exa.ai/docs/reference/search-api-guide | Provider-gated external source/search candidate; no API use until provider gate and source restoration path pass. |
| S37 | `perplexity-search-api` | https://docs.perplexity.ai/docs/search/quickstart | Provider-gated search/API candidate; raw results remain source candidates and no call is allowed under no-quota freeze. |
| S38 | `llm-oriented-ir` | https://arxiv.org/abs/2605.00505 | Retrieval-eval/design reference for denoising and distractor resistance; staged as local eval/report fields, not runtime import. |
| S39 | `bosun` | https://huggingface.co/blog/Hanno-Labs/bosun | Staged local-model/relevance-judge candidate. Source-locked for evaluation design only; model download/inference is not part of active research_x runtime. |
| S40 | `warrantbench` | https://github.com/Hanno-Labs/warrantbench | Staged benchmark/eval candidate for instruction-following relation judgment; fixture ideas may be adapted locally, benchmark runtime is not imported. |
| S41 | `paddleocr` | https://github.com/PaddlePaddle/PaddleOCR | Staged local OCR candidate; dependency/model review required before install or execution. |
| S42 | `paddleocr-vl` | https://huggingface.co/PaddlePaddle/PaddleOCR-VL | Staged local VLM/OCR candidate; model download/inference is gated and outputs must stay separate from citation-ready evidence. |
| S43 | `manga-ocr` | https://github.com/kha-white/manga-ocr | Staged local OCR candidate for Japanese manga-style text; dependency/model review required before install or execution. |

## Source Refs Not Manifest Entries

Codex foundation source locks live in
`C:/Users/maasa/.codex/foundation/vendor_sources.lock.md`. `research_x` keeps only project-candidate
source locks plus historical provenance needed by this tool.
