from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from research_x.memory.api_budget import rough_text_tokens, upsert_api_price
from research_x.memory.document_hashes import (
    memory_document_embedding_text,
    memory_document_source_hash,
    text_hash,
)
from research_x.memory.embeddings import DEFAULT_TEXT_TEMPLATE_VERSION
from research_x.memory.media_embeddings import (
    MediaEmbeddingEstimate,
    estimate_media_embedding_build,
)
from research_x.memory.schema import ensure_memory_schema

SOURCE_GEMINI_PRICING = "https://ai.google.dev/gemini-api/docs/pricing"
SOURCE_OPENAI_PRICING = "https://platform.openai.com/pricing"
SOURCE_VOYAGE_MODELS = "https://www.mongodb.com/docs/voyageai/models/"
SOURCE_JINA_MODELS = "https://api.jina.ai/docs"
SOURCE_JINA_OMNI = "https://jina.ai/models/jina-embeddings-v5-omni-small/"
SOURCE_COHERE_PRICING = "https://cohere.com/pricing"
SOURCE_COHERE_PRICING_DOCS = "https://docs.cohere.com/docs/how-does-cohere-pricing-work"
SOURCE_LITELLM_PRICES = (
    "https://raw.githubusercontent.com/BerriAI/litellm/main/"
    "model_prices_and_context_window.json"
)
SOURCE_MISTRAL_PRICING = "https://mistral.ai/pricing/"
SOURCE_MISTRAL_CODESTRAL = "https://docs.mistral.ai/models/model-cards/codestral-embed-25-05"
SOURCE_MISTRAL_OCR = "https://docs.mistral.ai/studio-api/document-processing/basic_ocr"

_URL_RE = re.compile(r"https?://[^\s<>'\"()]+", re.IGNORECASE)
_X_HOSTS = {"x.com", "www.x.com", "twitter.com", "www.twitter.com", "mobile.twitter.com"}


@dataclass(frozen=True)
class PriceCatalogRow:
    provider: str
    model: str
    operation: str
    unit: str
    usd_per_unit: float
    source_url: str
    notes: str


@dataclass(frozen=True)
class ApiLaneEstimateRow:
    lane: str
    name: str
    provider: str
    model: str
    operation: str
    status: str
    selected_units: int
    unit: str
    estimated_cost_usd: float | None
    cost_basis: str
    source_url: str
    notes: str
    extra: dict[str, Any]


@dataclass(frozen=True)
class ApiLaneEstimateReport:
    db_path: str
    checked_at: str
    rows: tuple[ApiLaneEstimateRow, ...]
    totals: dict[str, Any]
    assumptions: tuple[str, ...]


@dataclass(frozen=True)
class _TextArm:
    lane: str
    name: str
    provider: str
    model: str
    dimensions: int
    embedding_profile: str
    price_per_million_input_tokens: float | None
    source_url: str
    status: str = "estimate_ready"
    notes: str = ""


@dataclass(frozen=True)
class _OperationArm:
    lane: str
    name: str
    provider: str
    model: str
    operation: str
    unit: str
    price_per_unit: float | None
    source_url: str
    status: str
    notes: str


@dataclass(frozen=True)
class _TextDocumentEstimate:
    doc_id: str
    source_doc_hash: str
    embedded_text_hash: str
    input_chars: int
    input_tokens: int


@dataclass(frozen=True)
class _PreparedTextCorpus:
    db_path: str
    documents: tuple[_TextDocumentEstimate, ...]
    embeddings: dict[tuple[str, str, int, str, str, str], tuple[str, str]]


@dataclass(frozen=True)
class _TextEmbeddingEstimate:
    documents: int
    selected: int
    missing: int
    stale_text: int
    stale_source: int
    current: int
    estimated_input_chars: int
    estimated_input_tokens: int
    estimated_input_cost: float | None


DEFAULT_PRICE_CATALOG_ROWS: tuple[PriceCatalogRow, ...] = (
    PriceCatalogRow(
        "gemini",
        "gemini-embedding-2",
        "embedding",
        "input_token",
        0.20 / 1_000_000,
        SOURCE_GEMINI_PRICING,
        "Gemini Embedding 2 Standard text input price.",
    ),
    PriceCatalogRow(
        "gemini",
        "gemini-embedding-2",
        "media_embedding",
        "document",
        0.00012,
        SOURCE_GEMINI_PRICING,
        "Gemini Embedding 2 Standard image input price, stored as one document per media call.",
    ),
    PriceCatalogRow(
        "openai",
        "text-embedding-3-small",
        "embedding",
        "input_token",
        0.02 / 1_000_000,
        SOURCE_OPENAI_PRICING,
        "OpenAI text embedding input price.",
    ),
    PriceCatalogRow(
        "openai",
        "text-embedding-3-large",
        "embedding",
        "input_token",
        0.13 / 1_000_000,
        SOURCE_OPENAI_PRICING,
        "OpenAI text embedding input price.",
    ),
    PriceCatalogRow(
        "voyage",
        "voyage-4",
        "embedding",
        "input_token",
        0.06 / 1_000_000,
        SOURCE_VOYAGE_MODELS,
        "Voyage text embedding price.",
    ),
    PriceCatalogRow(
        "voyage",
        "voyage-4-large",
        "embedding",
        "input_token",
        0.12 / 1_000_000,
        SOURCE_VOYAGE_MODELS,
        "Voyage text embedding price.",
    ),
    PriceCatalogRow(
        "voyage",
        "voyage-code-3",
        "embedding",
        "input_token",
        0.18 / 1_000_000,
        SOURCE_VOYAGE_MODELS,
        "Voyage domain-specific code embedding price.",
    ),
    PriceCatalogRow(
        "voyage",
        "voyage-context-4",
        "embedding",
        "input_token",
        0.12 / 1_000_000,
        SOURCE_VOYAGE_MODELS,
        "Voyage contextual chunk embedding price; local contextual input contract is separate.",
    ),
    PriceCatalogRow(
        "voyage",
        "rerank-2.5",
        "rerank",
        "input_token",
        0.05 / 1_000_000,
        SOURCE_VOYAGE_MODELS,
        "Voyage reranker token price.",
    ),
    PriceCatalogRow(
        "jina",
        "jina-embeddings-v5-text-small",
        "embedding",
        "input_token",
        0.05 / 1_000_000,
        SOURCE_JINA_MODELS,
        "Jina Search Foundation API token price for embeddings.",
    ),
    PriceCatalogRow(
        "jina",
        "jina-embeddings-v5-omni-small",
        "embedding",
        "input_token",
        0.05 / 1_000_000,
        SOURCE_JINA_MODELS,
        "Jina v5 omni text-only estimate; native media URL ingestion remains a separate contract.",
    ),
    PriceCatalogRow(
        "jina",
        "jina-reranker-v3",
        "rerank",
        "input_token",
        0.05 / 1_000_000,
        SOURCE_JINA_MODELS,
        "Jina Reranker API follows Search Foundation token pricing.",
    ),
    PriceCatalogRow(
        "jina",
        "reader",
        "reader_extract",
        "input_token",
        0.05 / 1_000_000,
        SOURCE_JINA_MODELS,
        (
            "Reader estimate uses extracted-context token upper bound; actual billing is "
            "provider-side."
        ),
    ),
    PriceCatalogRow(
        "cohere",
        "embed-v4.0",
        "embedding",
        "input_token",
        0.12 / 1_000_000,
        SOURCE_LITELLM_PRICES,
        (
            "Secondary estimate from LiteLLM price file. Cohere official docs confirm "
            "embedding billing is token-based, but the public Cohere page may require dashboard "
            "or deployment context for exact PAYG display."
        ),
    ),
    PriceCatalogRow(
        "cohere",
        "rerank-v4.0-pro",
        "rerank",
        "call",
        0.0025,
        SOURCE_LITELLM_PRICES,
        (
            "Secondary estimate from LiteLLM/Azure Cohere route. Cohere official docs define "
            "one search as one query with up to 100 documents."
        ),
    ),
    PriceCatalogRow(
        "cohere",
        "rerank-v4.0-fast",
        "rerank",
        "call",
        0.002,
        SOURCE_LITELLM_PRICES,
        (
            "Secondary estimate from LiteLLM/Azure Cohere route. Cohere official docs define "
            "one search as one query with up to 100 documents."
        ),
    ),
    PriceCatalogRow(
        "mistral",
        "mistral-embed",
        "embedding",
        "input_token",
        0.10 / 1_000_000,
        SOURCE_MISTRAL_PRICING,
        "Mistral text embedding price.",
    ),
    PriceCatalogRow(
        "mistral",
        "codestral-embed-2505",
        "embedding",
        "input_token",
        0.15 / 1_000_000,
        SOURCE_MISTRAL_PRICING,
        "Mistral Codestral Embed price.",
    ),
    PriceCatalogRow(
        "mistral",
        "codestral-embed",
        "embedding",
        "input_token",
        0.15 / 1_000_000,
        SOURCE_MISTRAL_PRICING,
        "Mistral Codestral Embed alias price.",
    ),
    PriceCatalogRow(
        "mistral",
        "mistral-ocr-2512",
        "ocr",
        "page",
        3.0 / 1_000,
        SOURCE_MISTRAL_PRICING,
        "Mistral Libraries/Document AI OCR price per 1K pages; fixed OCR 2512 evaluation row.",
    ),
    PriceCatalogRow(
        "mistral",
        "mistral-ocr-latest",
        "ocr",
        "page",
        3.0 / 1_000,
        SOURCE_MISTRAL_PRICING,
        "Mistral latest OCR alias; use only when intentional latest tracking is desired.",
    ),
)


def seed_default_api_price_catalog(db_path: str | Path) -> int:
    for row in DEFAULT_PRICE_CATALOG_ROWS:
        upsert_api_price(
            db_path,
            provider=row.provider,
            model=row.model,
            operation=row.operation,
            unit=row.unit,
            usd_per_unit=row.usd_per_unit,
            source_url=row.source_url,
            checked_at=_utc_now(),
            notes=row.notes,
        )
    return len(DEFAULT_PRICE_CATALOG_ROWS)


def build_api_lane_estimate_report(
    db_path: str | Path,
    *,
    include_reference_managed_rag: bool = False,
    include_latest_ocr: bool = False,
    ocr_scope: str = "sample",
    ocr_limit: int = 100,
    reader_url_limit: int = 100,
    reader_max_chars: int = 4000,
    rerank_query_count: int = 5,
    rerank_candidate_limit: int = 20,
    rerank_avg_candidate_tokens: int = 250,
    max_file_bytes: int = 20 * 1024 * 1024,
) -> ApiLaneEstimateReport:
    rows: list[ApiLaneEstimateRow] = []
    rows.extend(_text_embedding_rows(db_path))
    media_estimate = estimate_media_embedding_build(
        db_path,
        provider="gemini",
        model="gemini-embedding-2",
        dimensions=1536,
        embedding_profile="native_multimodal_media",
        max_file_bytes=max_file_bytes,
    )
    rows.extend(_media_embedding_rows(media_estimate))
    rows.extend(
        _rerank_rows(
            rerank_query_count=rerank_query_count,
            rerank_candidate_limit=rerank_candidate_limit,
            rerank_avg_candidate_tokens=rerank_avg_candidate_tokens,
        )
    )
    rows.extend(
        _reader_rows(
            db_path,
            reader_url_limit=reader_url_limit,
            reader_max_chars=reader_max_chars,
        )
    )
    rows.extend(
        _ocr_rows(
            scope=ocr_scope,
            limit=ocr_limit,
            include_latest=include_latest_ocr,
            media_estimate=media_estimate,
        )
    )
    rows.extend(
        _managed_rag_rows(
            db_path,
            include_reference_managed_rag=include_reference_managed_rag,
        )
    )
    priced_rows = [row for row in rows if row.estimated_cost_usd is not None]
    total_priced_cost = sum(float(row.estimated_cost_usd or 0.0) for row in priced_rows)
    totals = {
        "rows": len(rows),
        "priced_rows": len(priced_rows),
        "unpriced_rows": len(rows) - len(priced_rows),
        "estimated_priced_cost_usd": round(total_priced_cost, 6),
        "by_lane": _totals_by_lane(rows),
        "recommended_plans": _recommended_plans(rows),
    }
    return ApiLaneEstimateReport(
        db_path=str(Path(db_path)),
        checked_at=_utc_now(),
        rows=tuple(rows),
        totals=totals,
        assumptions=(
            "This command does not call provider APIs and does not write embeddings.",
            (
                "Costs are local safety estimates; provider dashboards remain the billing "
                "source of truth."
            ),
            (
                "Different provider vectors remain separate candidate engines and are not "
                "mixed directly."
            ),
            (
                "Cohere v4 unit prices are included as secondary estimates; verify in your "
                "Cohere dashboard before high-volume use."
            ),
            (
                "Jina Reader and OCR estimates are upper/lower bounds because URL output "
                "size and PDF pages vary."
            ),
            (
                "OCR defaults to stratified calibration; full OCR over all media requires "
                "--ocr-scope all."
            ),
            (
                "Managed RAG references are not local X DB replacements and are costed only "
                "when explicitly included."
            ),
        ),
    )


def api_lane_estimate_json(report: ApiLaneEstimateReport) -> str:
    return json.dumps(asdict(report), ensure_ascii=False, indent=2, sort_keys=True)


def format_api_lane_estimate(report: ApiLaneEstimateReport) -> str:
    lines = [
        f"db: {report.db_path}",
        f"checked_at: {report.checked_at}",
        (
            "summary: "
            f"rows={report.totals['rows']} priced={report.totals['priced_rows']} "
            f"unpriced={report.totals['unpriced_rows']} "
            f"estimated_priced_cost_usd={report.totals['estimated_priced_cost_usd']:.6f}"
        ),
        "by_lane:",
    ]
    for lane, summary in sorted(report.totals["by_lane"].items()):
        cost = summary["estimated_priced_cost_usd"]
        lines.append(
            f"  {lane}: rows={summary['rows']} priced={summary['priced_rows']} cost~=${cost:.6f}"
        )
    lines.append("recommended_plans:")
    for plan in report.totals["recommended_plans"]:
        cost = plan.get("estimated_cost_usd")
        cost_text = "unpriced" if cost is None else f"${float(cost):.6f}"
        lines.append(
            "  - "
            f"{plan['plan_id']}: rows={plan['rows']} cost~={cost_text} "
            f"status={plan['status']}"
        )
        lines.append(f"    purpose: {plan['purpose']}")
        if plan.get("notes"):
            lines.append(f"    notes: {plan['notes']}")
    lines.append("rows:")
    for row in report.rows:
        cost = "unpriced" if row.estimated_cost_usd is None else f"${row.estimated_cost_usd:.6f}"
        lines.append(
            "  - "
            f"{row.lane}/{row.name}: {row.provider}/{row.model} "
            f"op={row.operation} status={row.status} "
            f"{row.selected_units} {row.unit} cost~={cost}"
        )
        lines.append(f"    basis: {row.cost_basis}")
        if row.notes:
            lines.append(f"    notes: {row.notes}")
    lines.append("assumptions:")
    for assumption in report.assumptions:
        lines.append(f"  - {assumption}")
    return "\n".join(lines)


def _text_embedding_rows(
    db_path: str | Path,
) -> tuple[ApiLaneEstimateRow, ...]:
    corpus = _prepare_text_embedding_corpus(db_path)
    arms = [
        _TextArm(
            "embedding_general_memory",
            "gemini2_general_text",
            "gemini",
            "gemini-embedding-2",
            768,
            "general_memory",
            0.20,
            SOURCE_GEMINI_PRICING,
        ),
        _TextArm(
            "embedding_general_memory",
            "openai_small_general",
            "openai",
            "text-embedding-3-small",
            1536,
            "general_memory",
            0.02,
            SOURCE_OPENAI_PRICING,
        ),
        _TextArm(
            "embedding_learning_long",
            "openai_large_learning",
            "openai",
            "text-embedding-3-large",
            3072,
            "learning_long",
            0.13,
            SOURCE_OPENAI_PRICING,
            status="eval_challenger",
        ),
        _TextArm(
            "embedding_jp_multilingual",
            "voyage4_multilingual",
            "voyage",
            "voyage-4",
            1024,
            "jp_multilingual",
            0.06,
            SOURCE_VOYAGE_MODELS,
        ),
        _TextArm(
            "embedding_learning_long",
            "voyage4_large_learning",
            "voyage",
            "voyage-4-large",
            1024,
            "learning_long",
            0.12,
            SOURCE_VOYAGE_MODELS,
            status="eval_challenger",
        ),
        _TextArm(
            "embedding_code_technical",
            "voyage_code_3",
            "voyage",
            "voyage-code-3",
            1024,
            "code_technical",
            0.18,
            SOURCE_VOYAGE_MODELS,
            status="route_specific",
        ),
        _TextArm(
            "embedding_contextual_learning",
            "voyage_context_4_learning",
            "voyage",
            "voyage-context-4",
            1024,
            "learning_contextual",
            0.12,
            SOURCE_VOYAGE_MODELS,
            status="contract_required_lower_bound",
            notes=(
                "Requires contextual chunk input contract; token count is lower-bound from "
                "current docs."
            ),
        ),
        _TextArm(
            "embedding_jp_multilingual",
            "jina_v5_text_multilingual",
            "jina",
            "jina-embeddings-v5-text-small",
            1024,
            "jp_multilingual",
            0.05,
            SOURCE_JINA_MODELS,
        ),
        _TextArm(
            "embedding_jp_multilingual",
            "gemini2_multilingual",
            "gemini",
            "gemini-embedding-2",
            1536,
            "jp_multilingual",
            0.20,
            SOURCE_GEMINI_PRICING,
            status="eval_challenger",
        ),
        _TextArm(
            "embedding_learning_long",
            "jina_v5_text_learning",
            "jina",
            "jina-embeddings-v5-text-small",
            1024,
            "learning_long",
            0.05,
            SOURCE_JINA_MODELS,
            status="eval_challenger",
        ),
        _TextArm(
            "embedding_media_text_bridge",
            "jina_v5_omni_media_text",
            "jina",
            "jina-embeddings-v5-omni-small",
            1024,
            "media_text_bridge",
            0.05,
            SOURCE_JINA_OMNI,
            status="media_text_bridge_text_only",
            notes=(
                "Text-only outputs are documented as compatible with v5 text; native media URL "
                "ingestion remains separate from local file evidence."
            ),
        ),
        _TextArm(
            "embedding_media_text_bridge",
            "cohere_v4_media_text",
            "cohere",
            "embed-v4.0",
            1536,
            "media_text_bridge",
            0.12,
            SOURCE_LITELLM_PRICES,
            status="secondary_priced_estimate",
            notes=(
                "Cohere official docs confirm embed is token-billed; $0.12/M token comes from "
                "LiteLLM/secondary price indexes because the public Cohere page did not expose "
                "a stable PAYG unit price in plain text."
            ),
        ),
        _TextArm(
            "embedding_code_technical",
            "mistral_text_code_docs",
            "mistral",
            "codestral-embed-2505",
            1024,
            "code_technical",
            0.15,
            SOURCE_MISTRAL_CODESTRAL,
            status="route_specific",
            notes="Mistral model card confirms codestral-embed-2505 and $0.15/M tokens.",
        ),
    ]
    rows = []
    for arm in arms:
        estimate = _estimate_text_embedding_arm(corpus, arm)
        rows.append(
            ApiLaneEstimateRow(
                lane=arm.lane,
                name=arm.name,
                provider=arm.provider,
                model=arm.model,
                operation="embedding",
                status=arm.status,
                selected_units=estimate.estimated_input_tokens,
                unit="input_token",
                estimated_cost_usd=estimate.estimated_input_cost,
                cost_basis=(
                    "current memory_documents embedding text tokens"
                    if arm.price_per_million_input_tokens is not None
                    else "provider public PAYG unit price not pinned"
                ),
                source_url=arm.source_url,
                notes=arm.notes,
                extra={
                    "documents": estimate.documents,
                    "selected_docs": estimate.selected,
                    "dimensions": arm.dimensions,
                    "embedding_profile": arm.embedding_profile,
                    "missing": estimate.missing,
                    "stale_text": estimate.stale_text,
                    "stale_source": estimate.stale_source,
                    "current": estimate.current,
                    "execution_stage": "production_scope_estimate",
                    "canary_sequence": (
                        "limit 1 -> 10 -> 100 technical_canary before production build"
                    ),
                    "production_contract": (
                        "adopted text embedding arms must cover their full selected document scope"
                    ),
                },
            )
        )
    return tuple(rows)


def _prepare_text_embedding_corpus(db_path: str | Path) -> _PreparedTextCorpus:
    path = Path(db_path)
    if not path.exists():
        raise FileNotFoundError(f"database not found: {path}")
    with sqlite3.connect(path, timeout=60) as conn:
        conn.row_factory = sqlite3.Row
        ensure_memory_schema(conn)
        doc_rows = conn.execute(
            """
            SELECT doc_id, title, compact_text, body, metadata_json
            FROM memory_documents
            ORDER BY observed_at DESC, doc_id
            """
        ).fetchall()
        if not doc_rows:
            raise RuntimeError("memory_documents is empty; run memory build-corpus first")
        embedding_rows = conn.execute(
            """
            SELECT
                doc_id, provider, model, dimensions, embedding_profile,
                text_template_version, source_doc_hash, embedded_text_hash
            FROM memory_embeddings
            """
        ).fetchall()
    documents: list[_TextDocumentEstimate] = []
    for row in doc_rows:
        text = memory_document_embedding_text(row)
        documents.append(
            _TextDocumentEstimate(
                doc_id=str(row["doc_id"]),
                source_doc_hash=memory_document_source_hash(row),
                embedded_text_hash=text_hash(text),
                input_chars=len(text),
                input_tokens=rough_text_tokens(text),
            )
        )
    embeddings = {
        (
            str(row["provider"]),
            str(row["model"]),
            int(row["dimensions"]),
            str(row["embedding_profile"]),
            str(row["text_template_version"]),
            str(row["doc_id"]),
        ): (str(row["source_doc_hash"] or ""), str(row["embedded_text_hash"] or ""))
        for row in embedding_rows
    }
    return _PreparedTextCorpus(
        db_path=str(path),
        documents=tuple(documents),
        embeddings=embeddings,
    )


def _estimate_text_embedding_arm(
    corpus: _PreparedTextCorpus,
    arm: _TextArm,
) -> _TextEmbeddingEstimate:
    counts = {"missing": 0, "stale_text": 0, "stale_source": 0, "current": 0}
    input_chars = 0
    input_tokens = 0
    spec_prefix = (
        arm.provider,
        arm.model,
        arm.dimensions,
        arm.embedding_profile,
        DEFAULT_TEXT_TEMPLATE_VERSION,
    )
    for doc in corpus.documents:
        existing = corpus.embeddings.get((*spec_prefix, doc.doc_id))
        if existing is None:
            status = "missing"
        elif existing[0] != doc.source_doc_hash:
            status = "stale_source"
        elif existing[1] != doc.embedded_text_hash:
            status = "stale_text"
        else:
            status = "current"
        counts[status] += 1
        if status != "current":
            input_chars += doc.input_chars
            input_tokens += doc.input_tokens
    estimated_cost = None
    if arm.price_per_million_input_tokens is not None:
        estimated_cost = (input_tokens / 1_000_000) * arm.price_per_million_input_tokens
    return _TextEmbeddingEstimate(
        documents=len(corpus.documents),
        selected=len(corpus.documents) - counts["current"],
        missing=counts["missing"],
        stale_text=counts["stale_text"],
        stale_source=counts["stale_source"],
        current=counts["current"],
        estimated_input_chars=input_chars,
        estimated_input_tokens=input_tokens,
        estimated_input_cost=estimated_cost,
    )


def _media_embedding_rows(
    estimate: MediaEmbeddingEstimate,
) -> tuple[ApiLaneEstimateRow, ...]:
    image_count = sum(
        count
        for mime, count in estimate.by_mime_type.items()
        if mime in {"image/jpeg", "image/png", "image/webp"}
    )
    online_cost = image_count * 0.00012
    batch_cost = image_count * 0.00006
    return (
        ApiLaneEstimateRow(
            lane="media_embedding",
            name="gemini_embedding_2_native_media",
            provider="gemini",
            model="gemini-embedding-2",
            operation="media_embedding",
            status="requires_explicit_eval",
            selected_units=image_count,
            unit="image",
            estimated_cost_usd=online_cost,
            cost_basis="Gemini Embedding 2 Standard image input price; PDFs are not costed here.",
            source_url=SOURCE_GEMINI_PRICING,
            notes=(
                "Native media vectors remain recall signals. The estimate counts image files only; "
                f"batch image lower-bound would be ${batch_cost:.6f}."
            ),
            extra={
                "media": estimate.media,
                "selected_media": estimate.selected,
                "api_calls": estimate.estimated_api_calls,
                "input_bytes": estimate.estimated_input_bytes,
                "by_mime_type": estimate.by_mime_type,
                "skipped_reasons": estimate.skipped_reasons,
            },
        ),
    )


def _rerank_rows(
    *,
    rerank_query_count: int,
    rerank_candidate_limit: int,
    rerank_avg_candidate_tokens: int,
) -> tuple[ApiLaneEstimateRow, ...]:
    query_count = max(0, rerank_query_count)
    candidate_limit = max(1, rerank_candidate_limit)
    avg_tokens = max(1, rerank_avg_candidate_tokens)
    tokens = query_count * candidate_limit * avg_tokens
    arms = (
        _OperationArm(
            "rerank",
            "voyage_rerank_2_5",
            "voyage",
            "rerank-2.5",
            "rerank",
            "input_token",
            0.05 / 1_000_000,
            SOURCE_VOYAGE_MODELS,
            "estimate_ready",
            "Voyage bills processed query/document tokens for rerank.",
        ),
        _OperationArm(
            "rerank",
            "cohere_rerank_v4_0_pro",
            "cohere",
            "rerank-v4.0-pro",
            "rerank",
            "search",
            0.0025,
            SOURCE_LITELLM_PRICES,
            "secondary_priced_estimate",
            (
                "Cohere defines one search as one query with up to 100 documents; $0.0025/search "
                "comes from LiteLLM/Azure Cohere route and should be checked against your "
                "Cohere dashboard before high-volume use."
            ),
        ),
        _OperationArm(
            "rerank",
            "cohere_rerank_v4_0_fast",
            "cohere",
            "rerank-v4.0-fast",
            "rerank",
            "search",
            0.002,
            SOURCE_LITELLM_PRICES,
            "secondary_priced_estimate",
            (
                "Cohere defines one search as one query with up to 100 documents; $0.002/search "
                "comes from LiteLLM/Azure Cohere route and should be checked against your "
                "Cohere dashboard before high-volume use."
            ),
        ),
        _OperationArm(
            "rerank",
            "jina_reranker_v3",
            "jina",
            "jina-reranker-v3",
            "rerank",
            "input_token",
            0.05 / 1_000_000,
            SOURCE_JINA_MODELS,
            "estimate_ready",
            "Jina reranker pricing is aligned with Search Foundation token pricing.",
        ),
    )
    rows = []
    for arm in arms:
        selected_units = query_count if arm.unit == "search" else tokens
        cost = None if arm.price_per_unit is None else selected_units * arm.price_per_unit
        rows.append(
            ApiLaneEstimateRow(
                lane=arm.lane,
                name=arm.name,
                provider=arm.provider,
                model=arm.model,
                operation=arm.operation,
                status=arm.status,
                selected_units=selected_units,
                unit=arm.unit,
                estimated_cost_usd=cost,
                cost_basis=(
                    f"{query_count} queries * {candidate_limit} candidates * "
                    f"{avg_tokens} avg tokens"
                    if arm.unit == "input_token"
                    else f"{query_count} bounded rerank searches"
                ),
                source_url=arm.source_url,
                notes=arm.notes,
                extra={
                    "query_count": query_count,
                    "candidate_limit": candidate_limit,
                    "avg_candidate_tokens": avg_tokens,
                },
            )
        )
    return tuple(rows)


def _reader_rows(
    db_path: str | Path,
    *,
    reader_url_limit: int,
    reader_max_chars: int,
) -> tuple[ApiLaneEstimateRow, ...]:
    resolved_limit = max(0, reader_url_limit)
    urls = () if resolved_limit == 0 else discover_external_urls(db_path, limit=resolved_limit)
    selected = min(len(urls), resolved_limit)
    # Jina Reader billing is token-based in the Search Foundation API family. Use a conservative
    # extracted-context upper bound so URL fanout is visible before a network request.
    tokens = selected * max(1, (max(0, reader_max_chars) + 1) // 2)
    cost = tokens * (0.05 / 1_000_000)
    return (
        ApiLaneEstimateRow(
            lane="reader",
            name="jina_reader_extract",
            provider="jina",
            model="reader",
            operation="reader_extract",
            status="url_fanout_estimate_ready",
            selected_units=tokens,
            unit="input_token",
            estimated_cost_usd=cost,
            cost_basis=(
                f"min({len(urls)} discovered external URLs, limit={resolved_limit}) "
                f"* max_chars={reader_max_chars} / 2 rough tokens"
            ),
            source_url=SOURCE_JINA_MODELS,
            notes=(
                "URL discovery is not evidence; Reader output must become context "
                "chunks/citations."
            ),
            extra={
                "discovered_external_urls": len(urls),
                "selected_urls": selected,
                "sample_urls": urls[:10],
                "reader_max_chars": reader_max_chars,
                "url_discovery_limit": resolved_limit,
                "url_discovery_capped": resolved_limit > 0 and len(urls) >= resolved_limit,
            },
        ),
    )


def _ocr_rows(
    *,
    scope: str,
    limit: int,
    include_latest: bool,
    media_estimate: MediaEmbeddingEstimate,
) -> tuple[ApiLaneEstimateRow, ...]:
    estimate = media_estimate
    full_page_lower_bound = estimate.selected
    normalized_scope = scope.strip().lower().replace("-", "_")
    if normalized_scope not in {"none", "sample", "candidate_set", "all"}:
        raise ValueError("ocr_scope must be one of: none, sample, candidate-set, all")
    if normalized_scope == "none":
        page_lower_bound = 0
        status_suffix = "not_selected"
    elif normalized_scope in {"sample", "candidate_set"}:
        page_lower_bound = min(full_page_lower_bound, max(0, limit))
        status_suffix = (
            "candidate_set_estimate"
            if normalized_scope == "candidate_set"
            else "sample_estimate"
        )
    else:
        page_lower_bound = full_page_lower_bound
        status_suffix = "full_lower_bound"
    model_rows = [("mistral_ocr_2512", "mistral-ocr-2512", "fixed_eval_candidate")]
    if include_latest:
        model_rows.append(("mistral_ocr_latest", "mistral-ocr-latest", "latest_alias_optional"))
    return tuple(
        ApiLaneEstimateRow(
            lane="media_to_text_ocr",
            name=name,
            provider="mistral",
            model=model,
            operation="ocr",
            status=f"{status}:{status_suffix}",
            selected_units=page_lower_bound,
            unit="page_lower_bound",
            estimated_cost_usd=page_lower_bound * (3.0 / 1_000),
            cost_basis=(
                "OCR selected media counted as at least one OCR page each; "
                f"scope={normalized_scope}"
            ),
            source_url=SOURCE_MISTRAL_PRICING,
            notes=(
                "OCR is media-to-text evidence preparation, not native vector recall. "
                "Default is stratified calibration because OCR all-media is expensive and "
                "flat random samples are weak for heterogeneous media. "
                "PDF page counts can make actual full cost higher than this lower bound."
            ),
            extra={
                "ocr_scope": normalized_scope,
                "ocr_limit": max(0, limit),
                "sample_policy": "stratified_calibration",
                "media_selected": estimate.selected,
                "full_page_lower_bound": full_page_lower_bound,
                "full_cost_lower_bound_usd": full_page_lower_bound * (3.0 / 1_000),
                "by_mime_type": estimate.by_mime_type,
                "fixed_model": model == "mistral-ocr-2512",
            },
        )
        for name, model, status in model_rows
    )


def _managed_rag_rows(
    db_path: str | Path,
    *,
    include_reference_managed_rag: bool,
) -> tuple[ApiLaneEstimateRow, ...]:
    docs = _memory_document_count(db_path)
    status = "reference_only_not_costed"
    cost: float | None = None
    if include_reference_managed_rag:
        status = "reference_enabled_still_not_auto_ingested"
    return (
        ApiLaneEstimateRow(
            lane="managed_rag_reference",
            name="openai_file_search_vector_stores",
            provider="openai",
            model="file_search",
            operation="managed_rag_reference",
            status=status,
            selected_units=docs,
            unit="document",
            estimated_cost_usd=cost,
            cost_basis="not costed because managed RAG does not replace the local X DB by default",
            source_url="https://platform.openai.com/docs/guides/tools-file-search/",
            notes=(
                "Use only as an eval reference for UX/citation behavior, not as canonical "
                "storage."
            ),
            extra={"documents": docs},
        ),
        ApiLaneEstimateRow(
            lane="managed_rag_reference",
            name="gemini_file_search_embedding_2",
            provider="gemini",
            model="gemini-file-search",
            operation="managed_rag_reference",
            status=status,
            selected_units=docs,
            unit="document",
            estimated_cost_usd=cost,
            cost_basis="not costed because managed RAG does not replace the local X DB by default",
            source_url="https://ai.google.dev/gemini-api/docs/file-search",
            notes=(
                "Gemini File Search can use gemini-embedding-2 but remains a managed "
                "reference lane."
            ),
            extra={"documents": docs},
        ),
    )


def discover_external_urls(db_path: str | Path, *, limit: int | None = None) -> tuple[str, ...]:
    path = Path(db_path)
    if not path.exists():
        return ()
    resolved_limit = None if limit is None or limit < 0 else limit
    if resolved_limit == 0:
        return ()
    urls: set[str] = set()
    with sqlite3.connect(path, timeout=60) as conn:
        conn.row_factory = sqlite3.Row
        ensure_memory_schema(conn)
        if _table_exists(conn, "memory_external_items"):
            for row in conn.execute("SELECT url FROM memory_external_items WHERE url IS NOT NULL"):
                _add_external_url(urls, row["url"])
                if _limit_reached(urls, resolved_limit):
                    break
        if _table_exists(conn, "memory_documents"):
            for row in conn.execute(
                """
                SELECT body, compact_text, metadata_json
                FROM memory_documents
                WHERE body LIKE '%http%'
                   OR compact_text LIKE '%http%'
                   OR metadata_json LIKE '%http%'
                """
            ):
                _extract_urls(urls, row["body"], limit=resolved_limit)
                if _limit_reached(urls, resolved_limit):
                    break
                _extract_urls(urls, row["compact_text"], limit=resolved_limit)
                if _limit_reached(urls, resolved_limit):
                    break
                _extract_urls(urls, row["metadata_json"], limit=resolved_limit)
                if _limit_reached(urls, resolved_limit):
                    break
        if _table_exists(conn, "tweets"):
            for row in conn.execute(
                """
                SELECT url, text, raw_json
                FROM tweets
                WHERE url LIKE '%http%' OR text LIKE '%http%' OR raw_json LIKE '%http%'
                """
            ):
                # tweet.url is usually an X source URL and is intentionally filtered out.
                _extract_urls(urls, row["url"], limit=resolved_limit)
                if _limit_reached(urls, resolved_limit):
                    break
                _extract_urls(urls, row["text"], limit=resolved_limit)
                if _limit_reached(urls, resolved_limit):
                    break
                _extract_urls(urls, row["raw_json"], limit=resolved_limit)
                if _limit_reached(urls, resolved_limit):
                    break
    return tuple(sorted(urls)[:resolved_limit])


def _extract_urls(urls: set[str], text: Any, *, limit: int | None = None) -> None:
    if not text:
        return
    for match in _URL_RE.findall(str(text)):
        _add_external_url(urls, match.rstrip(".,;:!?]}>"))
        if _limit_reached(urls, limit):
            return


def _add_external_url(urls: set[str], url: Any) -> None:
    if not url:
        return
    value = str(url).strip().rstrip(".,;:!?]}>")
    try:
        parsed = urlparse(value)
    except ValueError:
        return
    if parsed.scheme.lower() not in {"http", "https"}:
        return
    if parsed.netloc.lower() in _X_HOSTS:
        return
    if parsed.netloc.lower().endswith(".x.com") or parsed.netloc.lower().endswith(".twitter.com"):
        return
    urls.add(value)


def _limit_reached(urls: set[str], limit: int | None) -> bool:
    return limit is not None and len(urls) >= limit


def _memory_document_count(db_path: str | Path) -> int:
    with sqlite3.connect(db_path, timeout=60) as conn:
        ensure_memory_schema(conn)
        return int(conn.execute("SELECT COUNT(*) FROM memory_documents").fetchone()[0])


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    return (
        conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type IN ('table', 'view') AND name = ?",
            (table,),
        ).fetchone()
        is not None
    )


def _totals_by_lane(rows: list[ApiLaneEstimateRow]) -> dict[str, dict[str, Any]]:
    totals: dict[str, dict[str, Any]] = {}
    for row in rows:
        bucket = totals.setdefault(
            row.lane,
            {"rows": 0, "priced_rows": 0, "estimated_priced_cost_usd": 0.0},
        )
        bucket["rows"] += 1
        if row.estimated_cost_usd is not None:
            bucket["priced_rows"] += 1
            bucket["estimated_priced_cost_usd"] += float(row.estimated_cost_usd)
    for bucket in totals.values():
        bucket["estimated_priced_cost_usd"] = round(bucket["estimated_priced_cost_usd"], 6)
    return totals


def _recommended_plans(rows: list[ApiLaneEstimateRow]) -> list[dict[str, Any]]:
    row_by_name = {row.name: row for row in rows}
    plans = [
        _plan_from_names(
            "objective_fit_router_baseline",
            "recommended_first_pass",
            (
                "Build the broad answer-correctness foundation: general semantic recall, bounded "
                "rerank, limited URL Reader grounding, and stratified OCR calibration. Add route "
                "expansions only when the input needs them."
            ),
            (
                "This is the default performance shape: not cheapest, not all-in. It maximizes "
                "the chance of correct answers without prebuilding every specialist lane."
            ),
            row_by_name,
            (
                "gemini2_general_text",
                "openai_small_general",
                "voyage_rerank_2_5",
                "cohere_rerank_v4_0_fast",
                "jina_reranker_v3",
                "jina_reader_extract",
                "mistral_ocr_2512",
            ),
        ),
        _plan_from_names(
            "jp_multilingual_route",
            "route_expansion",
            (
                "Use when the question needs Japanese/cross-lingual semantic recall, translated "
                "terms, or mixed-language saved sources."
            ),
            "Incremental route expansion; do not run for exact-anchor-only questions.",
            row_by_name,
            ("voyage4_multilingual", "jina_v5_text_multilingual", "gemini2_multilingual"),
        ),
        _plan_from_names(
            "learning_long_route",
            "route_expansion",
            (
                "Use when the answer requires concept synthesis, academic/technical threads, "
                "or multi-hop learning-map evidence."
            ),
            "Adds high-capacity and contextual recall only for concept-heavy questions.",
            row_by_name,
            (
                "openai_large_learning",
                "voyage4_large_learning",
                "voyage_context_4_learning",
                "jina_v5_text_learning",
            ),
        ),
        _plan_from_names(
            "code_technical_route",
            "route_expansion",
            (
                "Use when the input asks for code, APIs, repositories, implementation details, "
                "or technical documentation recall."
            ),
            "Specialist code/documentation embeddings should not replace broad memory recall.",
            row_by_name,
            ("voyage_code_3", "mistral_text_code_docs"),
        ),
        _plan_from_names(
            "media_grounded_route",
            "route_expansion",
            (
                "Use when the answer depends on images/PDFs/media context. First retrieve media, "
                "then OCR/caption only the candidate set needed for citation-ready content."
            ),
            "This is a targeted media path, not full OCR over every saved image.",
            row_by_name,
            (
                "jina_v5_omni_media_text",
                "cohere_v4_media_text",
                "gemini_embedding_2_native_media",
                "mistral_ocr_2512",
            ),
        ),
    ]
    ocr = row_by_name.get("mistral_ocr_2512")
    if ocr is not None:
        full_pages = int(ocr.extra.get("full_page_lower_bound", 0) or 0)
        full_cost = float(ocr.extra.get("full_cost_lower_bound_usd", 0.0) or 0.0)
        plans.append(
            {
                "plan_id": "targeted_media_ocr_after_recall",
                "status": "recommended_media_evidence_path",
                "rows": 1,
                "estimated_cost_usd": ocr.estimated_cost_usd,
                "purpose": (
                    "Use native media embedding and media_text_bridge recall to select likely "
                    "useful media first, then OCR only the candidate set needed for citation-ready "
                    "image/PDF content evidence."
                ),
                "notes": (
                    f"Full OCR lower-bound would be {full_pages} pages / ${full_cost:.6f}; "
                    "that is intentionally not part of the default performance core."
                ),
            }
        )
        plans.append(
            {
                "plan_id": "full_ocr_lower_bound",
                "status": "expensive_explicit_only",
                "rows": 1,
                "estimated_cost_usd": full_cost,
                "purpose": (
                    "Price full OCR over every selected media item. Use only after targeted OCR "
                    "is proven insufficient for media-grounded evals."
                ),
                "notes": (
                    "PDF page counts can make real full OCR cost higher than this lower "
                    "bound."
                ),
            }
        )
    latest_ocr = row_by_name.get("mistral_ocr_latest")
    if latest_ocr is not None:
        plans.append(
            {
                "plan_id": "optional_latest_ocr_alias",
                "status": "latest_tracking_only",
                "rows": 1,
                "estimated_cost_usd": latest_ocr.estimated_cost_usd,
                "purpose": (
                    "Track the latest OCR alias only when model drift is intentionally being "
                    "measured. It is not part of repeatable performance eval."
                ),
                "notes": latest_ocr.notes,
            }
        )
    return plans


def _plan_from_names(
    plan_id: str,
    status: str,
    purpose: str,
    notes: str,
    row_by_name: dict[str, ApiLaneEstimateRow],
    names: tuple[str, ...],
) -> dict[str, Any]:
    selected = [row_by_name[name] for name in names if name in row_by_name]
    return {
        "plan_id": plan_id,
        "status": status,
        "rows": len(selected),
        "estimated_cost_usd": _sum_cost(selected),
        "purpose": purpose,
        "notes": notes,
        "row_names": tuple(row.name for row in selected),
        "lanes": tuple(sorted({row.lane for row in selected})),
    }


def _sum_cost(rows: list[ApiLaneEstimateRow]) -> float:
    return round(sum(float(row.estimated_cost_usd or 0.0) for row in rows), 6)


def _utc_now() -> str:
    return datetime.now(tz=UTC).isoformat()
