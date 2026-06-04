from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import Any

from research_x.memory.query import build_query_plan

EXPLICIT_RETRIEVAL_STRATEGY_ADOPTIONS = {
    "eval_only_explicit",
    "eval_only",
    "conditional_eval",
    "requires_explicit_eval",
}


@dataclass(frozen=True)
class PortfolioCandidate:
    name: str
    candidate_kind: str
    provider: str | None = None
    model: str | None = None
    dimensions: int | None = None
    embedding_profile: str | None = None
    text_template_version: str = "memory-doc-embedding-v1"
    mode: str = "semantic_only"
    candidates: int = 80
    weight: float = 1.0
    modality: str = "text"
    vector_space_kind: str = "none"
    route_role: str = "first_stage_recall"
    portfolio_eligible: bool = False
    status: str = "candidate"
    purpose: str = ""
    preconditions: tuple[str, ...] = ()
    source_refs: tuple[str, ...] = ()

    def semantic_spec(self) -> str:
        if self.candidate_kind != "semantic" or not self.portfolio_eligible:
            raise ValueError(f"{self.name} is not eligible for portfolio semantic specs")
        if not (self.provider and self.model and self.dimensions and self.embedding_profile):
            raise ValueError(f"{self.name} is missing semantic provider/model/dim/profile")
        return ",".join(
            (
                f"provider={self.provider}",
                f"model={self.model}",
                f"dimensions={self.dimensions}",
                f"profile={self.embedding_profile}",
                f"template={self.text_template_version}",
                f"name={self.name}",
                f"mode={self.mode}",
                f"candidates={self.candidates}",
                f"weight={self.weight:g}",
            )
        )

    def reranker_spec(self) -> str:
        if self.candidate_kind != "reranker" or not self.portfolio_eligible:
            raise ValueError(f"{self.name} is not eligible for portfolio reranker specs")
        if not (self.provider and self.model):
            raise ValueError(f"{self.name} is missing reranker provider/model")
        return ",".join(
            (
                f"provider={self.provider}",
                f"model={self.model}",
                f"name={self.name}",
                f"top_n={self.candidates}",
                f"weight={self.weight:g}",
            )
        )


@dataclass(frozen=True)
class RetrievalStrategy:
    strategy_id: str
    label: str
    stage: str
    adoption: str
    purpose: str
    question_types: tuple[str, ...]
    intents: tuple[str, ...]
    routes: tuple[str, ...]
    doc_types: tuple[str, ...]
    candidates: tuple[PortfolioCandidate, ...] = ()
    promotion_gate: tuple[str, ...] = ()
    rejection_gate: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()
    source_refs: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return asdict(self) | {
            "semantic_specs": [
                candidate.semantic_spec()
                for candidate in self.candidates
                if candidate.candidate_kind == "semantic" and candidate.portfolio_eligible
            ],
            "reranker_specs": [
                candidate.reranker_spec()
                for candidate in self.candidates
                if candidate.candidate_kind == "reranker" and candidate.portfolio_eligible
            ],
        }


GEMINI2_GENERAL_TEXT = PortfolioCandidate(
    name="gemini2_general_text",
    candidate_kind="semantic",
    provider="gemini",
    model="gemini-embedding-2",
    dimensions=768,
    embedding_profile="general_memory",
    vector_space_kind="dense",
    portfolio_eligible=True,
    purpose=(
        "Gemini real API recall arm for broad memory cases. Gemini Embedding 2 is "
        "multimodal-capable, but this arm indexes citation-ready text only."
    ),
    source_refs=("Google Gemini Embedding 2 GA", "Google Gemini API embeddings docs"),
)
GEMINI001_LEGACY_TEXT = PortfolioCandidate(
    name="gemini001_legacy_text",
    candidate_kind="semantic",
    provider="gemini",
    model="gemini-embedding-001",
    dimensions=768,
    embedding_profile="general_memory_legacy",
    vector_space_kind="dense",
    portfolio_eligible=False,
    status="legacy_comparison_only",
    purpose=(
        "Legacy Gemini text embedding reference. Keep available for regression checks, "
        "but do not include in the default real API portfolio."
    ),
    source_refs=("Google Gemini API embeddings docs",),
)
OPENAI_SMALL_GENERAL = PortfolioCandidate(
    name="openai_small_general",
    candidate_kind="semantic",
    provider="openai",
    model="text-embedding-3-small",
    dimensions=1536,
    embedding_profile="general_memory",
    vector_space_kind="dense",
    portfolio_eligible=True,
    purpose="Cheap, stable real API text recall arm for full-corpus indexing.",
    source_refs=("OpenAI embeddings docs",),
)
VOYAGE4_MULTILINGUAL = PortfolioCandidate(
    name="voyage4_multilingual",
    candidate_kind="semantic",
    provider="voyage",
    model="voyage-4",
    dimensions=1024,
    embedding_profile="jp_multilingual",
    candidates=120,
    vector_space_kind="dense",
    portfolio_eligible=True,
    purpose="Japanese and cross-lingual semantic recall challenger.",
    source_refs=("Voyage embeddings docs", "MTEB/MMTEB"),
)
JINA_V5_TEXT_MULTILINGUAL = PortfolioCandidate(
    name="jina_v5_text_multilingual",
    candidate_kind="semantic",
    provider="jina",
    model="jina-embeddings-v5-text-small",
    dimensions=1024,
    embedding_profile="jp_multilingual",
    candidates=120,
    vector_space_kind="dense",
    portfolio_eligible=True,
    purpose="Long-context multilingual text recall challenger.",
    source_refs=("Jina embeddings v5 text docs",),
)
VOYAGE4_LARGE_LEARNING = PortfolioCandidate(
    name="voyage4_large_learning",
    candidate_kind="semantic",
    provider="voyage",
    model="voyage-4-large",
    dimensions=1024,
    embedding_profile="learning_long",
    candidates=140,
    weight=1.1,
    vector_space_kind="dense",
    portfolio_eligible=True,
    purpose="High-capacity concept and learning-map recall challenger.",
    source_refs=("Voyage embeddings docs",),
)
OPENAI_LARGE_LEARNING = PortfolioCandidate(
    name="openai_large_learning",
    candidate_kind="semantic",
    provider="openai",
    model="text-embedding-3-large",
    dimensions=3072,
    embedding_profile="learning_long",
    candidates=140,
    weight=1.05,
    vector_space_kind="dense",
    portfolio_eligible=True,
    purpose="High-capacity text recall arm for concept-heavy cases.",
    source_refs=("OpenAI embeddings docs",),
)
MISTRAL_TEXT_CODE_DOCS = PortfolioCandidate(
    name="mistral_text_code_docs",
    candidate_kind="semantic",
    provider="mistral",
    model="mistral-embed",
    dimensions=1024,
    embedding_profile="code_technical",
    candidates=100,
    vector_space_kind="dense",
    portfolio_eligible=True,
    purpose="Technical/API/documentation recall challenger.",
    source_refs=("Mistral embeddings docs",),
)
VOYAGE_CODE_3 = PortfolioCandidate(
    name="voyage_code_3",
    candidate_kind="semantic",
    provider="voyage",
    model="voyage-code-3",
    dimensions=1024,
    embedding_profile="code_technical",
    candidates=100,
    vector_space_kind="dense",
    portfolio_eligible=True,
    purpose="Code-specialist recall challenger for repository/API docs.",
    source_refs=("Voyage embeddings docs",),
)
COHERE_V4_MEDIA_TEXT = PortfolioCandidate(
    name="cohere_v4_media_text",
    candidate_kind="semantic",
    provider="cohere",
    model="embed-v4.0",
    dimensions=1536,
    embedding_profile="media_text_bridge",
    candidates=120,
    modality="text_from_media",
    vector_space_kind="dense",
    portfolio_eligible=True,
    purpose="Media-derived text recall arm after OCR/caption/VLM text exists.",
    preconditions=("media_doc must include OCR/caption/alt_text or VLM text.",),
    source_refs=("Cohere Embed v4 docs",),
)
VOYAGE_CONTEXT_3_LEARNING = PortfolioCandidate(
    name="voyage_context_3_learning",
    candidate_kind="contextual_embedding",
    provider="voyage",
    model="voyage-context-3",
    dimensions=1024,
    embedding_profile="learning_contextual",
    vector_space_kind="contextual_dense",
    status="needs_contextual_chunk_implementation",
    purpose=(
        "Contextual chunk embedding candidate for topic/thread bundles where chunk-level "
        "vectors need surrounding document context."
    ),
    preconditions=(
        "Group source-bundle chunks by parent document before embedding.",
        "Store contextual input hashes separately from standard embedding text hashes.",
    ),
    source_refs=("Voyage contextualized chunk embeddings docs",),
)


DEFAULT_RETRIEVAL_STRATEGIES: tuple[RetrievalStrategy, ...] = (
    RetrievalStrategy(
        strategy_id="baseline_hybrid_foundation",
        label="implemented lexical, metadata, relation foundation",
        stage="production foundation",
        adoption="always_on_baseline",
        purpose=(
            "Keep exact lexical search, metadata filters, relation expansion, derived views, "
            "and source-bundle restoration as the baseline that challengers must beat."
        ),
        question_types=(
            "single_fact_conditioned",
            "set_recall",
            "aggregation_count_rank",
            "temporal_freshness",
            "citation_required",
        ),
        intents=("food", "finance", "technology", "science", "author", "event"),
        routes=("local_memory_search", "place_recall", "author_stance", "learning_map"),
        doc_types=(
            "tweet_doc",
            "bookmark_doc",
            "quote_tree_doc",
            "media_doc",
            "place_card",
            "author_profile",
            "ticker_event",
            "topic_thread",
        ),
        candidates=(
            PortfolioCandidate(
                name="fts_only",
                candidate_kind="retrieval_engine",
                status="implemented_eval_baseline",
                purpose="Lexical first-stage recall with SQLite FTS5/BM25.",
                source_refs=("SQLite FTS5",),
            ),
            PortfolioCandidate(
                name="local_hybrid",
                candidate_kind="retrieval_engine",
                status="implemented_eval_baseline",
                purpose="Current combined FTS/LIKE/metadata/semantic/relation local search.",
                source_refs=("Azure RRF", "BEIR"),
            ),
            PortfolioCandidate(
                name="exact_anchor_engine",
                candidate_kind="retrieval_engine",
                status="partially_implemented",
                purpose=(
                    "Handles, URLs, long IDs, dates, tickers, and place names should be a "
                    "separate auditable candidate engine instead of only a filter/boost."
                ),
                source_refs=("SQLite FTS5",),
            ),
            PortfolioCandidate(
                name="relation_engine",
                candidate_kind="retrieval_engine",
                status="partially_implemented",
                purpose=(
                    "Quote, media, duplicate-bookmark, same-url, same-topic, and freshness "
                    "relations should be independently visible in portfolio comparisons."
                ),
                source_refs=("GraphRAG", "Azure RRF"),
            ),
        ),
        promotion_gate=(
            "Any new embedding/provider arm must beat this baseline after source-bundle "
            "restoration, not only on raw vector recall.",
            "Exact entity/date/URL/account routes must not regress.",
        ),
        source_refs=(
            "SQLite FTS5",
            "Azure AI Search RRF",
            "BEIR",
        ),
    ),
    RetrievalStrategy(
        strategy_id="contextual_bm25",
        label="generated retrieval-only context for lexical recall",
        stage="high-value non-embedding challenger",
        adoption="requires_eval",
        purpose=(
            "Add short generated context/doc2query-style text to a search-only field so FTS "
            "can recover decontextualized tweets and chunks. The generated text is never "
            "citation-ready evidence."
        ),
        question_types=("multi_hop_evidence", "exploratory_map", "multilingual_source"),
        intents=("technology", "science", "author"),
        routes=("learning_map", "author_stance", "local_memory_search"),
        doc_types=("tweet_doc", "bookmark_doc", "topic_thread", "author_profile"),
        candidates=(
            PortfolioCandidate(
                name="contextual_bm25_search_text",
                candidate_kind="derived_retrieval_text",
                status="needs_implementation",
                purpose=(
                    "Store 50-100 token search-only context beside source docs, index it in "
                    "FTS, and cite only the original source/context chunks."
                ),
                preconditions=(
                    "Mark generated retrieval text as derived/search-only.",
                    "Add audit coverage so generated hints cannot become evidence.",
                ),
                source_refs=("Anthropic Contextual Retrieval", "doc2query", "HyDE"),
            ),
        ),
        promotion_gate=(
            "Must improve route recall without increasing unsupported citations.",
            "Generated retrieval text must never appear as a source_kind=fact citation.",
        ),
        rejection_gate=(
            "Reject if fielded FTS, exact anchors, or relation expansion solve the same miss.",
        ),
        source_refs=("Anthropic Contextual Retrieval", "doc2query", "HyDE"),
    ),
    RetrievalStrategy(
        strategy_id="corpus2skill_navigation",
        label="Corpus2Skill navigation map and route hints",
        stage="navigation layer",
        adoption="workflow_hint_not_evidence",
        purpose=(
            "Expose the Corpus2Skill export/compile boundary as a skill/navigation surface. "
            "It can suggest routes, concepts, and missing-neighbor searches, but final context "
            "must return to source documents and citation chunks."
        ),
        question_types=(
            "exploratory_map",
            "set_recall",
            "multi_hop_evidence",
            "personal_preference",
        ),
        intents=("technology", "science", "author", "food", "event"),
        routes=("learning_map", "author_stance", "place_recall", "local_memory_search"),
        doc_types=(
            "topic_thread",
            "author_profile",
            "bookmark_doc",
            "tweet_doc",
            "place_card",
        ),
        candidates=(
            PortfolioCandidate(
                name="corpus2skill_export_bundle",
                candidate_kind="navigation_map",
                status="implemented_export_boundary",
                route_role="route_hint",
                purpose=(
                    "Use exported corpus/manifest as a compact map for route selection and "
                    "concept discovery; never cite the map itself as fact evidence."
                ),
                preconditions=(
                    "Compile/evaluate outside this repo before promoting as a route hint.",
                    "Restore original source bundle before context or citation generation.",
                ),
                source_refs=("Corpus2Skill",),
            ),
        ),
        promotion_gate=(
            "Must improve exploratory-map or learning-map route choice while citations still "
            "point to source chunks.",
            "Generated skills/maps must remain derived navigation metadata, not evidence.",
        ),
        rejection_gate=(
            "Reject if normal topic_thread, relation, or FTS routes already recover the needed "
            "source bundle.",
        ),
        source_refs=("Corpus2Skill",),
    ),
    RetrievalStrategy(
        strategy_id="bounded_workflow_orchestration",
        label="bounded workflow tool routing with stop reasons",
        stage="workflow control plane",
        adoption="always_on_control_surface",
        purpose=(
            "Keep query planning, route selection, tool calls, stop reasons, and evidence "
            "assembly as the center of the pipeline. Retrieval arms are tools selected by "
            "workflow, not the definition of memory quality."
        ),
        question_types=(
            "single_fact_conditioned",
            "set_recall",
            "aggregation_count_rank",
            "comparison",
            "multi_hop_evidence",
            "temporal_freshness",
            "false_premise_abstention",
            "citation_required",
            "multilingual_source",
            "media_grounded",
            "exploratory_map",
        ),
        intents=("food", "finance", "technology", "science", "author", "event", "media"),
        routes=(
            "local_memory_search",
            "place_recall",
            "company_event",
            "author_stance",
            "learning_map",
            "current_fact_check",
            "external_context",
            "media_context",
        ),
        doc_types=("context_chunk", "citation_annotation", "workflow_trace"),
        candidates=(
            PortfolioCandidate(
                name="bounded_route_planner",
                candidate_kind="workflow_orchestrator",
                status="implemented_foundation",
                route_role="control_plane",
                purpose=(
                    "Select exact/FTS/relation/external/context/embedding tools by route and "
                    "record stop reasons before answer generation."
                ),
                source_refs=("ADW", "agentic workflow", "MCP"),
            ),
        ),
        promotion_gate=(
            "Every new retrieval provider must enter through an auditable workflow route.",
            "Open-ended agent loops must not replace bounded stop reasons.",
        ),
        notes=(
            "This strategy intentionally emits no semantic arm; it governs when arms are used.",
        ),
        source_refs=("ADW", "MCP", "GraphRAG"),
    ),
    RetrievalStrategy(
        strategy_id="api_embedding_portfolio",
        label="real API embedding portfolio candidates",
        stage="explicit recall-arm portfolio",
        adoption="eval_only_explicit",
        purpose=(
            "Collect the real API embedding arms into one explicit strategy for portfolio "
            "evaluation. Providers stay in separate vector spaces and are fused only by "
            "rank/route contribution after source-bundle restoration."
        ),
        question_types=(
            "multilingual_source",
            "learning_map",
            "exploratory_map",
            "multi_hop_evidence",
            "code_or_api_lookup",
            "media_grounded",
        ),
        intents=("technology", "science", "media", "author"),
        routes=("learning_map", "local_memory_search", "media_context", "current_fact_check"),
        doc_types=("tweet_doc", "bookmark_doc", "topic_thread", "media_doc", "quote_tree_doc"),
        candidates=(
            GEMINI2_GENERAL_TEXT,
            OPENAI_SMALL_GENERAL,
            VOYAGE4_MULTILINGUAL,
            JINA_V5_TEXT_MULTILINGUAL,
            VOYAGE4_LARGE_LEARNING,
            OPENAI_LARGE_LEARNING,
            MISTRAL_TEXT_CODE_DOCS,
            VOYAGE_CODE_3,
            COHERE_V4_MEDIA_TEXT,
        ),
        promotion_gate=(
            "No provider/vector space can promote without route-level portfolio wins over "
            "lexical, relation, and workflow-gated baselines.",
            "Fusion must use rank/route contribution and then restore parent source bundles.",
            "Diagnostic providers such as local_hash are excluded from this strategy.",
        ),
        rejection_gate=(
            "Reject provider fanout if document views, relations, reranking, or workflow routing "
            "solve the miss with less complexity.",
        ),
        source_refs=(
            "OpenAI embeddings docs",
            "Google Gemini API embeddings docs",
            "Voyage embeddings docs",
            "Jina embeddings v5 text",
            "Cohere Embed v4 docs",
            "Mistral embeddings docs",
            "Azure AI Search RRF",
        ),
    ),
    RetrievalStrategy(
        strategy_id="rerank_stage",
        label="bounded rerank after source-bundle restoration",
        stage="high-value non-index challenger",
        adoption="requires_eval",
        purpose=(
            "Rerank a small restored candidate bundle after lexical/semantic/relation fusion. "
            "This can improve context precision without adding persistent vector spaces."
        ),
        question_types=("comparison", "multi_hop_evidence", "citation_required"),
        intents=("technology", "science", "finance", "author"),
        routes=("learning_map", "company_event", "author_stance", "current_fact_check"),
        doc_types=("topic_thread", "bookmark_doc", "quote_tree_doc", "author_profile"),
        candidates=(
            PortfolioCandidate(
                name="voyage_rerank_2_5",
                candidate_kind="reranker",
                provider="voyage",
                model="rerank-2.5",
                candidates=5,
                portfolio_eligible=True,
                status="needs_real_api_eval",
                purpose="Multilingual long-context reranker over restored evidence bundles.",
                preconditions=("Restore quote/media/author/bookmark bundle before rerank.",),
                source_refs=("Voyage reranker docs",),
            ),
            PortfolioCandidate(
                name="cohere_rerank_v4_0_pro",
                candidate_kind="reranker",
                provider="cohere",
                model="rerank-v4.0-pro",
                candidates=5,
                portfolio_eligible=True,
                status="needs_real_api_eval",
                purpose="High-quality production reranker candidate for metadata-rich bundles.",
                preconditions=("Rerank only bounded top-k candidates.",),
                source_refs=("Cohere rerank docs",),
            ),
            PortfolioCandidate(
                name="cohere_rerank_v4_0_fast",
                candidate_kind="reranker",
                provider="cohere",
                model="rerank-v4.0-fast",
                candidates=5,
                weight=0.95,
                portfolio_eligible=True,
                status="needs_real_api_eval",
                purpose="Lower-latency Cohere reranker candidate for bounded bundles.",
                preconditions=("Rerank only bounded top-k candidates.",),
                source_refs=("Cohere rerank docs",),
            ),
            PortfolioCandidate(
                name="jina_reranker_v3",
                candidate_kind="reranker",
                provider="jina",
                model="jina-reranker-v3",
                candidates=5,
                portfolio_eligible=True,
                status="needs_real_api_eval",
                purpose="Multilingual listwise reranker candidate for restored bundles.",
                preconditions=("Rerank only bounded top-k candidates.",),
                source_refs=("Jina reranker v3 docs",),
            ),
            PortfolioCandidate(
                name="qwen3_local_reranker",
                candidate_kind="reranker",
                provider="openai_compatible",
                model="Qwen3-Reranker-0.6B",
                status="deferred_local_or_compatible",
                purpose="Open-weight reranker candidate when local/private serving is needed.",
                preconditions=("Configure an explicit local or OpenAI-compatible endpoint.",),
                source_refs=("Qwen3-Embedding GitHub",),
            ),
        ),
        promotion_gate=(
            "Must improve citation/context precision with acceptable latency.",
            "Must store provider/model/prompt/version and per-candidate score metadata.",
        ),
        rejection_gate=("Reject if first-stage recall is the real failure.",),
        source_refs=("Cohere rerank docs", "Voyage reranker docs", "Jina reranker docs"),
    ),
    RetrievalStrategy(
        strategy_id="claim_citation_verification",
        label="claim-level support checking for generated answers",
        stage="post-answer evidence audit",
        adoption="requires_implementation",
        purpose=(
            "Verify whether each factual answer claim is supported, contradicted, or "
            "insufficiently supported by cited chunks."
        ),
        question_types=("citation_required", "false_premise_abstention", "temporal_freshness"),
        intents=("finance", "technology", "science", "freshness"),
        routes=("current_fact_check", "company_event", "author_stance"),
        doc_types=("context_chunk", "citation_annotation", "answer_artifact_doc"),
        candidates=(
            PortfolioCandidate(
                name="atomic_claim_support_gate",
                candidate_kind="verifier",
                status="needs_implementation",
                purpose=(
                    "Extract atomic claims, map claims to cited chunks, and force "
                    "needs_review when support is absent."
                ),
                source_refs=("FActScore", "ALCE"),
            ),
        ),
        promotion_gate=(
            "Unsupported factual claims must become needs_review or abstention.",
            "Verifier output must be derived metadata, not new evidence.",
        ),
        source_refs=("FActScore", "ALCE"),
    ),
    RetrievalStrategy(
        strategy_id="freshness_lineage",
        label="source version and freshness lineage",
        stage="dynamic-source reliability layer",
        adoption="requires_implementation",
        purpose=(
            "Make source versions, content hashes, last-seen times, supersession, and "
            "retention rules first-class so stale/newer queries do not rely only on ranking."
        ),
        question_types=("temporal_freshness", "current_fact_check", "citation_required"),
        intents=("freshness", "finance", "event", "technology"),
        routes=("current_fact_check", "company_event", "external_context"),
        doc_types=("tweet_doc", "topic_thread", "external_context_chunk"),
        candidates=(
            PortfolioCandidate(
                name="source_version_lineage",
                candidate_kind="lineage",
                status="partially_implemented",
                purpose=(
                    "Existing source_doc_hash and freshness relations are a start; saved URLs "
                    "and external chunks still need explicit version/supersession lineage."
                ),
                source_refs=("VersionRAG", "FRESCO"),
            ),
        ),
        promotion_gate=(
            "Changed source hash must mark derived docs, embeddings, relations, context, and "
            "citations stale or needing revalidation.",
        ),
        source_refs=("VersionRAG", "FRESCO"),
    ),
    RetrievalStrategy(
        strategy_id="general_memory",
        label="broad real API text semantic recall arm",
        stage="explicit semantic recall candidate",
        adoption="eval_only_explicit",
        purpose=(
            "Test one stable broad text embedding space as an optional recall arm. It is not "
            "the production center; exact/FTS/metadata/relations/workflow remain the default."
        ),
        question_types=(
            "single_fact_conditioned",
            "set_recall",
            "personal_preference",
            "temporal_freshness",
            "multi_hop_evidence",
        ),
        intents=("food", "finance", "technology", "science", "author", "event"),
        routes=("local_memory_search", "place_recall", "author_stance", "learning_map"),
        doc_types=("tweet_doc", "bookmark_doc", "quote_tree_doc", "media_doc", "topic_thread"),
        candidates=(
            GEMINI2_GENERAL_TEXT,
            OPENAI_SMALL_GENERAL,
        ),
        promotion_gate=(
            "Promote a broad text recall arm only after portfolio-eval beats evidence-first "
            "baselines without route regression.",
            "Preserve source-bundle restoration before answer generation.",
        ),
        rejection_gate=(
            "Reject default multi-provider fanout until eval coverage proves its value.",
            "Reject if exact-token and metadata routes regress.",
        ),
        source_refs=("Google Gemini API embeddings docs", "OpenAI embeddings docs", "BEIR"),
    ),
    RetrievalStrategy(
        strategy_id="jp_multilingual",
        label="Japanese and cross-lingual semantic recall",
        stage="explicit semantic challenger",
        adoption="eval_only",
        purpose=(
            "Test whether Japanese queries over English docs/papers and multilingual aliases "
            "need a specialist text space beyond the broad baseline."
        ),
        question_types=("multilingual_source", "learning_map", "single_fact_conditioned"),
        intents=("technology", "science"),
        routes=("learning_map", "local_memory_search"),
        doc_types=("tweet_doc", "bookmark_doc", "topic_thread"),
        candidates=(
            VOYAGE4_MULTILINGUAL,
            JINA_V5_TEXT_MULTILINGUAL,
            PortfolioCandidate(
                name="gemini2_multilingual",
                candidate_kind="semantic",
                provider="gemini",
                model="gemini-embedding-2",
                dimensions=1536,
                embedding_profile="jp_multilingual",
                candidates=120,
                vector_space_kind="dense",
                portfolio_eligible=True,
                purpose="Gemini Embedding 2 multilingual text recall arm for parity tests.",
                source_refs=("Google Gemini Embedding 2 GA", "Google Gemini API embeddings docs"),
            ),
            PortfolioCandidate(
                name="qwen3_embedding_openai_compatible",
                candidate_kind="semantic",
                provider="openai_compatible",
                model="Qwen3-Embedding-0.6B",
                dimensions=1024,
                embedding_profile="jp_multilingual",
                vector_space_kind="dense",
                portfolio_eligible=False,
                status="deferred_endpoint_required",
                purpose="Open-weight multilingual candidate through explicit compatible endpoint.",
                preconditions=("Configure local/OpenAI-compatible embeddings endpoint.",),
                source_refs=("Qwen3-Embedding GitHub",),
            ),
        ),
        promotion_gate=(
            "Must improve multilingual_source or learning_map cases after bundle restoration.",
            "Must not degrade exact-token, citation, or false-premise cases.",
        ),
        rejection_gate=(
            "Reject if gain is only raw recall and disappears after context/citation truncation.",
        ),
        source_refs=("Voyage embeddings docs", "Jina embeddings v5 text", "MTEB"),
    ),
    RetrievalStrategy(
        strategy_id="learning_long",
        label="long-form learning and technical concepts",
        stage="explicit semantic challenger",
        adoption="eval_only",
        purpose=(
            "Test whether papers, technical docs, topic maps, and concept-heavy saved tweets "
            "need a higher-capacity or long-context text space."
        ),
        question_types=("exploratory_map", "multi_hop_evidence", "comparison"),
        intents=("technology", "science"),
        routes=("learning_map", "current_fact_check"),
        doc_types=("topic_thread", "bookmark_doc", "tweet_doc"),
        candidates=(
            VOYAGE4_LARGE_LEARNING,
            OPENAI_LARGE_LEARNING,
            VOYAGE_CONTEXT_3_LEARNING,
            PortfolioCandidate(
                name="jina_v5_text_learning",
                candidate_kind="semantic",
                provider="jina",
                model="jina-embeddings-v5-text-small",
                dimensions=1024,
                embedding_profile="learning_long",
                candidates=140,
                vector_space_kind="dense",
                portfolio_eligible=True,
                purpose="Long-context multilingual text challenger.",
                source_refs=("Jina embeddings v5 text docs",),
            ),
        ),
        promotion_gate=(
            "Must improve exploratory_map or multi_hop_evidence cases, not just "
            "similar-topic recall.",
            "Must preserve quote/media/source-bundle provenance.",
        ),
        rejection_gate=(
            "Reject if topic_thread derived documents or relation expansion fix the issue "
            "without a new vector space.",
        ),
        source_refs=("OpenAI embeddings docs", "Voyage embeddings docs", "Jina embeddings v5 text"),
    ),
    RetrievalStrategy(
        strategy_id="code_technical",
        label="code and implementation-heavy saved docs",
        stage="narrow semantic challenger",
        adoption="eval_only",
        purpose=(
            "Use code-specialist embeddings only for implementation/API/repository material, "
            "not as a broad X memory index."
        ),
        question_types=("code_or_api_lookup", "learning_map", "comparison"),
        intents=("technology",),
        routes=("learning_map", "current_fact_check"),
        doc_types=("topic_thread", "bookmark_doc", "tweet_doc"),
        candidates=(
            MISTRAL_TEXT_CODE_DOCS,
            PortfolioCandidate(
                name="mistral_codestral_embed",
                candidate_kind="semantic",
                provider="mistral",
                model="codestral-embed-2505",
                dimensions=None,
                embedding_profile="code_technical",
                vector_space_kind="dense",
                portfolio_eligible=False,
                status="deferred_dimension_and_dtype_required",
                purpose=(
                    "Code-specialist Mistral candidate; keep deferred until output_dimension "
                    "and dtype policy are pinned for this repo."
                ),
                source_refs=("Mistral Codestral Embed",),
            ),
            VOYAGE_CODE_3,
        ),
        promotion_gate=(
            "Only promote on code/API/documentation route evals.",
            "Must not replace the evidence/workflow baseline or broad semantic recall arm.",
        ),
        rejection_gate=("Reject if regular learning_long or fielded FTS wins.",),
        source_refs=("Mistral embeddings docs", "Voyage embeddings docs"),
    ),
    RetrievalStrategy(
        strategy_id="media_text_bridge",
        label="media/OCR/caption bridge before native multimodal search",
        stage="requires media-derived text",
        adoption="conditional_eval",
        purpose=(
            "Use media-specialist providers only after media documents expose citation-ready OCR, "
            "captions, alt text, VLM summaries, or raw media references."
        ),
        question_types=("media_grounded", "citation_required"),
        intents=("media", "adult_comic"),
        routes=("media_context", "quote_context"),
        doc_types=("media_doc", "bookmark_doc", "quote_tree_doc"),
        candidates=(
            COHERE_V4_MEDIA_TEXT,
            PortfolioCandidate(
                name="jina_v5_omni_media_text",
                candidate_kind="semantic",
                provider="jina",
                model="jina-embeddings-v5-omni-small",
                dimensions=1024,
                embedding_profile="media_text_bridge",
                candidates=120,
                modality="text_from_media",
                vector_space_kind="dense",
                portfolio_eligible=False,
                status="deferred_native_or_api_confirmation",
                purpose=(
                    "Current Jina omni candidate; defer until media input/citation contracts "
                    "exist."
                ),
                preconditions=("Native image vector ingestion is not enabled in this repo yet.",),
                source_refs=("Jina embeddings v5 omni",),
            ),
            PortfolioCandidate(
                name="gemini_embedding_2_native_media",
                candidate_kind="media_embedding",
                provider="gemini",
                model="gemini-embedding-2",
                dimensions=1536,
                embedding_profile="native_multimodal_media",
                modality="native_multimodal",
                vector_space_kind="multimodal_dense",
                route_role="media_recall",
                portfolio_eligible=False,
                status="requires_explicit_eval",
                purpose=(
                    "Gemini Embedding 2 native multimodal recall candidate. The model is now "
                    "confirmed and uses the separate memory_media_embeddings contract instead "
                    "of the text-only memory_embeddings contract."
                ),
                preconditions=(
                    "Build media vectors with memory build-media-embeddings.",
                    "Restore media hits to tweet/media source bundles before evidence use.",
                    "Do not treat raw media matches as image-content claims without OCR/caption.",
                ),
                source_refs=(
                    "Google Gemini Embedding 2 GA",
                    "Gemini Embedding 2 paper",
                    "Google Gemini API embeddings docs",
                ),
            ),
            PortfolioCandidate(
                name="vertex_multimodal_embedding_001",
                candidate_kind="media_embedding",
                provider="vertex_ai",
                model="multimodalembedding@001",
                dimensions=1408,
                embedding_profile="native_multimodal_media",
                modality="native_multimodal",
                vector_space_kind="multimodal_dense",
                route_role="deferred_media_recall",
                portfolio_eligible=False,
                status="deferred_gcp_vertex_auth_required",
                purpose=(
                    "Google Vertex AI native multimodal embedding reference for image/text/video "
                    "search; not available through a plain Gemini API key."
                ),
                preconditions=(
                    "Configure GCP project, location, and Vertex auth.",
                    "Implement raw media input handling and media citation restoration.",
                ),
                source_refs=("Vertex AI multimodal embeddings docs",),
            ),
            PortfolioCandidate(
                name="mistral_ocr_latest",
                candidate_kind="ocr",
                provider="mistral",
                model="mistral-ocr-latest",
                modality="pdf_or_image",
                route_role="media_to_citation_text",
                portfolio_eligible=False,
                status="needs_media_ocr_contract",
                purpose=(
                    "Convert PDF/image/screenshot media into citation-ready text before "
                    "media_text_bridge or normal text retrieval."
                ),
                preconditions=(
                    "Define media file input, OCR output hashes, and source URL/local path "
                    "citation mapping.",
                ),
                source_refs=("Mistral OCR docs",),
            ),
        ),
        promotion_gate=(
            "Must improve media_grounded cases with citations pointing to original tweet/media.",
            "Native image retrieval cannot promote until image evidence can be cited safely.",
        ),
        rejection_gate=(
            "Reject if OCR/caption quality, not embedding model, is the limiting factor.",
        ),
        source_refs=(
            "Cohere Embed v4 docs",
            "Jina embeddings v5 omni",
            "Google Gemini Embedding 2 GA",
            "Vertex AI multimodal embeddings docs",
            "Mistral OCR docs",
        ),
    ),
    RetrievalStrategy(
        strategy_id="native_multimodal_media",
        label="Gemini Embedding 2 native media recall",
        stage="explicit media recall candidate",
        adoption="requires_explicit_eval",
        purpose=(
            "Search saved local image/PDF media files with Gemini Embedding 2, then restore hits "
            "to media/tweet/bookmark/quote source bundles. Raw media matches are candidate "
            "signals, not image-content evidence."
        ),
        question_types=("media_grounded", "citation_required"),
        intents=("media", "adult_comic", "technology"),
        routes=("media_context", "quote_context"),
        doc_types=("media_doc", "bookmark_doc", "quote_tree_doc", "tweet_doc"),
        candidates=(
            PortfolioCandidate(
                name="gemini_embedding_2_native_media",
                candidate_kind="media_embedding",
                provider="gemini",
                model="gemini-embedding-2",
                dimensions=1536,
                embedding_profile="native_multimodal_media",
                modality="native_multimodal",
                vector_space_kind="multimodal_dense",
                route_role="media_recall",
                status="requires_explicit_eval",
                purpose=(
                    "Native media recall over saved local image/PDF files using "
                    "memory_media_embeddings."
                ),
                preconditions=(
                    "Run media-embedding-estimate before writing real API rows.",
                    "Start builds with --limit 1, then 10, then 100.",
                    "Restore every hit to media_source_evidence before answer context.",
                ),
                source_refs=("Google Gemini Embedding 2 GA", "Google Gemini API embeddings docs"),
            ),
        ),
        promotion_gate=(
            "Must restore 100% of media hits to source bundles.",
            "Must keep raw_media_match, media_source_evidence, and "
            "media_content_evidence distinct.",
            "Must improve media_grounded evals without unsupported image-content claims.",
        ),
        rejection_gate=(
            "Reject if media_text_bridge OCR/caption text solves the same cases with "
            "clearer citations.",
            "Reject if missing/stale/skipped coverage is not visible.",
        ),
        source_refs=("Google Gemini Embedding 2 GA", "Google Gemini API embeddings docs"),
    ),
    RetrievalStrategy(
        strategy_id="exact_metadata_first",
        label="exact entities, places, tickers, dates",
        stage="non-embedding guard",
        adoption="always_on_guard",
        purpose=(
            "Protect restaurant/place recall, tickers, dates, handles, URLs, and bookmark "
            "ownership with FTS, metadata, relations, and derived cards before dense-provider "
            "complexity."
        ),
        question_types=("single_fact_conditioned", "aggregation_count_rank", "temporal_freshness"),
        intents=("food", "finance", "event", "cross_account", "freshness"),
        routes=("place_recall", "company_event", "cross_account", "current_fact_check"),
        doc_types=("place_card", "ticker_event", "bookmark_doc", "author_profile"),
        candidates=(),
        promotion_gate=(
            "Embedding challengers must not reorder exact lexical/metadata hits unless eval "
            "improves.",
        ),
        rejection_gate=(
            "Do not solve exact ID/date/entity misses with more dense providers before "
            "FTS/metadata.",
        ),
        notes=("This strategy intentionally emits no semantic arm.",),
        source_refs=("SQLite FTS5", "Azure hybrid/RRF docs"),
    ),
)


def retrieval_strategies_as_dicts(
    *,
    query: str | None = None,
    question_types: tuple[str, ...] = (),
    strategy_ids: tuple[str, ...] = (),
) -> list[dict[str, Any]]:
    strategies = select_retrieval_strategies(
        query=query,
        question_types=question_types,
        strategy_ids=strategy_ids,
    )
    return [strategy.as_dict() for strategy in strategies]


def retrieval_strategies_json(
    *,
    query: str | None = None,
    question_types: tuple[str, ...] = (),
    strategy_ids: tuple[str, ...] = (),
) -> str:
    return json.dumps(
        retrieval_strategies_as_dicts(
            query=query,
            question_types=question_types,
            strategy_ids=strategy_ids,
        ),
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    )


def format_retrieval_strategies(
    *,
    query: str | None = None,
    question_types: tuple[str, ...] = (),
    strategy_ids: tuple[str, ...] = (),
) -> str:
    strategies = select_retrieval_strategies(
        query=query,
        question_types=question_types,
        strategy_ids=strategy_ids,
    )
    if not strategies:
        return "(no retrieval strategies matched)"
    lines: list[str] = []
    if query:
        plan = build_query_plan(query)
        lines.append(f"query: {query}")
        lines.append(f"intents: {', '.join(plan.intents) or '-'}")
    for strategy in strategies:
        lines.append(
            f"{strategy.strategy_id}: {strategy.label} "
            f"[stage={strategy.stage} adoption={strategy.adoption}]"
        )
        lines.append(f"  purpose: {strategy.purpose}")
        if strategy.question_types:
            lines.append(f"  question_types: {', '.join(strategy.question_types)}")
        if strategy.intents:
            lines.append(f"  intents: {', '.join(strategy.intents)}")
        if strategy.routes:
            lines.append(f"  routes: {', '.join(strategy.routes)}")
        if strategy.doc_types:
            lines.append(f"  doc_types: {', '.join(strategy.doc_types)}")
        if strategy.candidates:
            lines.append("  candidates:")
            for candidate in strategy.candidates:
                provider = candidate.provider or "-"
                model = candidate.model or "-"
                dims = str(candidate.dimensions) if candidate.dimensions is not None else "-"
                lines.append(
                    "    - "
                    f"{candidate.name}: kind={candidate.candidate_kind} "
                    f"provider={provider} model={model} dims={dims} "
                    f"profile={candidate.embedding_profile or '-'} "
                    f"modality={candidate.modality} status={candidate.status} "
                    f"portfolio={'yes' if candidate.portfolio_eligible else 'no'}"
                )
                if candidate.candidate_kind == "semantic" and candidate.portfolio_eligible:
                    lines.append(f"      semantic_spec: {candidate.semantic_spec()}")
                if candidate.purpose:
                    lines.append(f"      purpose: {candidate.purpose}")
                if candidate.preconditions:
                    lines.append(f"      preconditions: {'; '.join(candidate.preconditions)}")
        else:
            lines.append("  candidates: none")
        if strategy.promotion_gate:
            lines.append(f"  promotion_gate: {'; '.join(strategy.promotion_gate)}")
        if strategy.rejection_gate:
            lines.append(f"  rejection_gate: {'; '.join(strategy.rejection_gate)}")
    return "\n".join(lines)


def semantic_spec_strings_for_strategies(strategy_ids: tuple[str, ...]) -> tuple[str, ...]:
    specs: list[str] = []
    seen: set[str] = set()
    for strategy in select_retrieval_strategies(strategy_ids=strategy_ids):
        for candidate in strategy.candidates:
            if candidate.candidate_kind != "semantic" or not candidate.portfolio_eligible:
                continue
            spec = candidate.semantic_spec()
            if spec in seen:
                continue
            seen.add(spec)
            specs.append(spec)
    return tuple(specs)


def reranker_spec_strings_for_strategies(strategy_ids: tuple[str, ...]) -> tuple[str, ...]:
    specs: list[str] = []
    seen: set[str] = set()
    for strategy in select_retrieval_strategies(strategy_ids=strategy_ids):
        for candidate in strategy.candidates:
            if candidate.candidate_kind != "reranker" or not candidate.portfolio_eligible:
                continue
            spec = candidate.reranker_spec()
            if spec in seen:
                continue
            seen.add(spec)
            specs.append(spec)
    return tuple(specs)


def select_retrieval_strategies(
    *,
    query: str | None = None,
    question_types: tuple[str, ...] = (),
    strategy_ids: tuple[str, ...] = (),
) -> tuple[RetrievalStrategy, ...]:
    if strategy_ids:
        by_id = {strategy.strategy_id: strategy for strategy in DEFAULT_RETRIEVAL_STRATEGIES}
        unknown = sorted(set(strategy_ids) - set(by_id))
        if unknown:
            raise ValueError(f"unknown retrieval strategy id(s): {', '.join(unknown)}")
        return tuple(by_id[strategy_id] for strategy_id in strategy_ids)
    selected: list[RetrievalStrategy] = [
        _strategy_by_id("baseline_hybrid_foundation"),
        _strategy_by_id("exact_metadata_first"),
        _strategy_by_id("corpus2skill_navigation"),
        _strategy_by_id("bounded_workflow_orchestration"),
    ]
    target_question_types = set(question_types)
    intents: set[str] = set()
    normalized_query = ""
    if query:
        plan = build_query_plan(query)
        intents.update(plan.intents)
        normalized_query = plan.normalized_query.casefold()
        if plan.requires_media_context:
            target_question_types.add("media_grounded")
        if "technology" in intents or "science" in intents:
            target_question_types.add("exploratory_map")
            target_question_types.add("multi_hop_evidence")
        if "finance" in intents or "event" in intents or plan.excludes_old:
            target_question_types.add("temporal_freshness")
        if any(term in normalized_query for term in ("英語", "english", "docs", "論文")):
            target_question_types.add("multilingual_source")
        if any(term in normalized_query for term in ("api", "github", "コード", "実装", "cli")):
            target_question_types.add("code_or_api_lookup")
    for strategy in DEFAULT_RETRIEVAL_STRATEGIES[1:]:
        if strategy.strategy_id in {item.strategy_id for item in selected}:
            continue
        if strategy.adoption in EXPLICIT_RETRIEVAL_STRATEGY_ADOPTIONS:
            continue
        if target_question_types.intersection(strategy.question_types) or intents.intersection(
            strategy.intents
        ):
            selected.append(strategy)
    needs_evidence_audit = (
        "citation_required" in target_question_types
        or "temporal_freshness" in target_question_types
    )
    if query and needs_evidence_audit:
        selected.append(_strategy_by_id("claim_citation_verification"))
    return tuple(_dedupe_strategies(selected))


def _strategy_by_id(strategy_id: str) -> RetrievalStrategy:
    for strategy in DEFAULT_RETRIEVAL_STRATEGIES:
        if strategy.strategy_id == strategy_id:
            return strategy
    raise ValueError(f"unknown retrieval strategy id: {strategy_id}")


def _dedupe_strategies(strategies: list[RetrievalStrategy]) -> list[RetrievalStrategy]:
    seen: set[str] = set()
    result: list[RetrievalStrategy] = []
    for strategy in strategies:
        if strategy.strategy_id in seen:
            continue
        seen.add(strategy.strategy_id)
        result.append(strategy)
    return result
