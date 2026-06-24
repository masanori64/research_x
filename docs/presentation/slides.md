---
marp: true
theme: default
paginate: true
size: 16:9
style: |
  section {
    color: #1f2933;
    font-family: "Aptos", "Segoe UI", sans-serif;
    letter-spacing: 0;
  }
  h1 {
    color: #244766;
    font-size: 44px;
  }
  p, li {
    font-size: 25px;
    line-height: 1.35;
  }
  code {
    font-size: 0.82em;
  }
  section.diagram img {
    display: block;
    margin: 8px auto 0;
    max-height: 450px;
    max-width: 100%;
  }
---

# research_x

Local evidence-first memory for X data

<!-- claim: claim-local-x-memory -->

- Goal: AI-callable local search over an existing X collection database
- Constraint: provenance, account ownership, quote/media context, and subjective interest must survive retrieval
- Boundary: generated decks, diagrams, WBS, pointer maps, and ChatGPT captures are not evidence

---

# Problem

<!-- claim: claim-search-results-are-candidates -->

Local X collections are useful only if an agent can search them without flattening provenance.

- Bookmarks are account-specific, not generic web pages
- Quote and media context change what a tweet means
- Search hits are candidates until restored to source-backed context

---

# Evidence Pipeline

<!-- claim: claim-evidence-first -->
<!-- _class: diagram -->

![Evidence pipeline](assets/memory-evidence-flow.svg)

---

# Runtime Surface

<!-- claim: claim-cli-entrypoint -->
<!-- _class: diagram -->

![Runtime boundary](assets/runtime-boundary.svg)

---

# Provider Gate

<!-- claim: claim-provider-gated -->

- Real embeddings, OCR, rerank, Reader, classifier, answer, external search, and managed RAG are blocked by default
- Local/fake providers and deterministic tests are allowed
- Budget guard preflight is required before any explicitly approved provider run

---

# Local Data Model

<!-- claim: claim-memory-schema -->

- `memory_documents` and `memory_document_fts` are rebuildable searchable projections
- `memory_workflow_runs` and `memory_workflow_steps` expose route and stop state
- `memory_api_usage_events` records provider-facing budget events
- Context chunks, citation annotations, answer runs, evals, relations, and governance records remain separate tables

---

# Presentation Build Boundary

<!-- claim: claim-presentation-stage-boundary -->
<!-- _class: diagram -->

![Presentation generation flow](assets/presentation-facts-flow.svg)

---

# Deck Rule

<!-- claim: claim-generated-artifacts-not-evidence -->

Every slide-worthy claim must map back to `project-facts.json`, and every fact must point to repository files.

- Generated PPTX/SVG/HTML is presentation output, not evidence
- Unknowns stay in `unknowns[]` until supported
- D2 and Marp are renderer choices, not architecture truth

---

# Current Open Questions

- Whether editable PowerPoint objects are required later
- Final narrative polish and diagram count after this first fixed-layout deck
- Whether another renderer is justified after the D2/Marp lane is evaluated
