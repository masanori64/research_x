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
| S01 | `firecrawl` | https://www.firecrawl.dev/ | Provider-gated external source candidate; no network/provider call without `ProviderApiBudgetGuard` approval. |
| S07 | `occ-rag` | https://github.com/optimal-cognitive-core/OCC-RAG | Retrieval-eval reference only; fixture shape may be adapted locally, runtime is not imported. |
| S10 | `archify` | https://github.com/tt-a1i/archify | Control-artifact renderer reference only; diagram outputs never become evidence. |
| S16 | `zvec` | https://github.com/alibaba/zvec | Staged local-backend candidate; dependency/source review required before install or default use. |
| S17 | `saas-stop-condition` | https://github.com/XMUDeepLIT/SAAS | Retrieval stop-condition eval reference only; no runtime import. |
| S21 | `serper` | https://serper.dev | Disabled; `ProviderApiBudgetGuard` only. |
| S24 | `searxng`, `webshare` | https://docs.searxng.org/ and https://www.webshare.io/ | SearXNG optional discovery hint; Webshare rejected default. |
| S33 | `single-file-wbs` | https://github.com/piguo45/single-file-wbs | Pinned local WBS/progress visualization tool. MIT license and `v1.3.0` tag object `06ab5981baa68a6a938f236691bc642ec7d670a9` pointing to commit `b1ef3d7e175dedfd9f4f34a9984437b174469c76` checked 2026-06-29. Release asset `wbs_viewer.html` SHA-256 `c92b71b83075d2c6ae1108166ccceb90590e901914e7b57ce9843a5c885bea97`; vendored unchanged under `tools/wbs_viewer/vendor/single-file-wbs-v1.3.0/`. Allowed for local WBS JSON visual review and viewer-only `holidays` calendar display only. No plugin, MCP, hook, provider, hosted service, or evidence promotion; do not edit vendored upstream in place. |
| S34 | `pdgkit` | https://github.com/shibayamalicht/pdgkit, https://note.com/nonoonenono/n/n0701699bbf3c, and npm `@shibayama/pdgkit` | Reference-only historical source. MIT license and npm version `0.1.2` were checked 2026-06-24 during the item 34/35 canary, but the local tool lane has been decommissioned and removed from active repo surfaces. Do not install, restore, invoke, register MCP, add a root dependency, use for presentation generation, or promote outputs as evidence. Current final flow authority lives in `docs/presentation/final-runtime-flow.md` and `docs/presentation/final-design-flow.md`; D2/Marp remain build-tool boundaries, with the old `C:/Users/maasa/.codex/foundation/project_plans/research_x/2026-06-24-presentation-generation-flow.md` retained as historical build-lane rationale. |
| S35 | `tavily` | https://docs.tavily.com/documentation/api-reference/introduction | Provider-gated external source/search candidate; official docs require API key authentication, so no call under no-quota freeze. |
| S36 | `exa` | https://exa.ai/docs/reference/search-api-guide | Provider-gated external source/search candidate; no API use until `ProviderApiBudgetGuard` approval. Results remain candidates and need a documented source-restoration path before evidence promotion. |
| S37 | `perplexity-search-api` | https://docs.perplexity.ai/docs/search/quickstart | Provider-gated search/API candidate; raw results remain source candidates and no call is allowed under no-quota freeze. |
| S38 | `llm-oriented-ir` | https://arxiv.org/abs/2605.00505 | Retrieval-eval/design reference for denoising and distractor resistance; staged as local eval/report fields, not runtime import. |
| S39 | `bosun` | https://huggingface.co/blog/Hanno-Labs/bosun | Staged local-model/relevance-judge candidate. Source-locked for evaluation design only; model download/inference is not part of active research_x runtime. |
| S40 | `warrantbench` | https://github.com/Hanno-Labs/warrantbench | Staged benchmark/eval candidate for instruction-following relation judgment; fixture ideas may be adapted locally, benchmark runtime is not imported. |
| S41 | `paddleocr` | https://github.com/PaddlePaddle/PaddleOCR | Staged local OCR candidate; dependency/model review required before install or execution. |
| S42 | `paddleocr-vl` | https://huggingface.co/PaddlePaddle/PaddleOCR-VL | Staged local VLM/OCR candidate; model download/inference is gated and outputs must stay separate from citation-ready evidence. |
| S43 | `manga-ocr` | https://github.com/kha-white/manga-ocr | Staged local OCR candidate for Japanese manga-style text; dependency/model review required before install or execution. |
| S44 | `kg-puzzle-agent-langgraph` | https://zenn.dev/knowledge_graph/articles/kg-puzzle-agent-langgraph | Design-reference source for typed relation, authority, temporal, and contradiction checks in evidence workflows. Community article; no runtime, dependency, provider, or graph-store adoption. |
| S45 | `cognee` | https://github.com/topoteretes/cognee | Reference/provider-gated AI memory and Graph RAG platform candidate. Apache-2.0 license was reported from the upstream page during 2026-07-01 intake, but install, MCP/plugin setup, Docker, LLM_API_KEY usage, cloud use, and provider calls remain disabled. Cognee or external memory-platform output is not a source bundle, context chunk, citation, evidence, or answer support unless restored through the `research_x` source-bundle and citation pipeline. |
| S46 | `open-knowledge-format` | https://cloud.google.com/blog/products/data-analytics/how-the-open-knowledge-format-can-improve-data-sharing and https://zenn.dev/knowledgesense/articles/14a874a9f423bb | Metadata-shape reference for Markdown plus YAML-frontmatter knowledge entries. Use only as a schema-design source candidate; OKF notes are not source bundles or citation evidence. |
| S47 | `rag-knowledge-ops-agent-search` | https://zenn.dev/yottayoshida/articles/rag-knowledge-ops-agent-search | Observability and Knowledge Ops design reference. Cloud Agent Search, GCS, Slack, or managed search execution is not adopted and remains outside local/no-quota verification. |
| S48 | `claude-ontology-knowledge-structuring` | https://zenn.dev/takupeso/articles/claude-ontology-knowledge-structuring | Ontology/typed-edge design reference only. Use as comparison material for relation traversal and abstention, not as an active MCP memory or ontology runtime. |
| S49 | `databricks-rag-workflow` | https://www.databricks.com/jp/blog/rag-workflow | Vendor RAG workflow/governance checklist reference for provenance, freshness, evaluation, and context-budget concepts. Databricks products and managed services are not adopted. |
| S50 | `cc-rsg` | https://zenn.dev/daishiro/articles/cc-rsg-web-release and https://github.com/daishir0/cc-rsg | Reverse-specification and verification-loop reference. Treat generated specifications as review/control artifacts, not evidence. No Claude Code Skill import or external model execution is adopted. |
| S51 | `marp-slidev` | https://tech-lab.sios.jp/archives/52940, https://marp.app/, and https://sli.dev/ | Presentation-artifact workflow reference. Marp is already the owned deck assembly boundary; Slidev remains staged behind dependency/install and visual-QA review. Generated decks remain non-evidence artifacts. |
| S52 | `f3` | https://github.com/future-file-format/f3 | Reference-only self-describing data-file format candidate. Upstream README describes it as a research prototype and not for production use; no Wasm decoder execution, dependency install, or archive-format adoption. |
| S53 | `sqljoiner` | https://github.com/webofmarius/SQLJoiner | Visual SQL/query-builder UX reference only. GPL-3.0, MySQL focus, credential storage, PHP/Electron dependencies, and SQL execution risks block direct adoption. |
| S54 | `line-embedding-stabilization` | https://techblog.lycorp.co.jp/ja/techverse2026-62 | Official tech-blog case study for embedding stabilization, cold-start, and drift-aware reranking evaluation. Use only for provider-free synthetic/local eval design unless real embedding provider use is later approved. |
| S55 | `x-bookmarks-and-unrestored-x-posts` | https://x.com/i/bookmarks, https://help.x.com/en/using-x/bookmarks, and the four user-provided X post URLs | Private/login-required and snippet-only source-restoration boundary reference. X bookmarks and unfetched posts cannot become source bundles or citations without user-provided export or restorable public source content. |
| S56 | `agent-guardrail-design` | https://qiita.com/ryuichi000persol/items/27789cbca88bd4bf11e0 and https://zenn.dev/nrs/articles/e4a2ae8a9fb785 | Agent safety and loop-control design references. Adopt only as local trace/contract visibility for tool boundaries, forbidden external actions, provider gates, parameter validation, and bounded stop reasons; no agent framework, dependency, MCP/plugin, browser automation, or prompt-only safety claim is adopted. |
| S57 | `agent-control-source-ownership` | https://zenn.dev/tan_go238/articles/783a3fc3f11f8d, https://qiita.com/mellowlaunch/items/3ad3dd2812d6bf1cad58, and https://zenn.dev/keitayamamoto/articles/d053a6cc096287 | Metadata-only agent-control and AI-test-quality source candidates. They are source-registry ownership coverage inputs, not runtime adoption, browser/MCP/tool permission, unit-test policy by themselves, evidence, citations, or source bundles. |

## Source Refs Not Manifest Entries

Codex foundation source locks live in
`C:/Users/maasa/.codex/foundation/vendor_sources.lock.md`. `research_x` keeps only project-candidate
source locks plus historical provenance needed by this tool.
