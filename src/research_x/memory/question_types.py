from __future__ import annotations

import json
from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class QuestionType:
    question_type: str
    label: str
    description: str
    example: str
    required_capabilities: tuple[str, ...]
    current_readiness: str
    risk: str
    benchmark_sources: tuple[str, ...]


QUESTION_TYPES: tuple[QuestionType, ...] = (
    QuestionType(
        question_type="single_fact_conditioned",
        label="conditioned recall",
        description=(
            "Recover one saved item under concrete entity, place, date, author, or URL constraints."
        ),
        example="北千住にある、ピザが食べられる店だったと思うんだけどどこ？",
        required_capabilities=("exact", "lexical", "metadata", "bookmark_context"),
        current_readiness="strong",
        risk="Fails when the saved clue appears only in an image or external URL title.",
        benchmark_sources=("CRAG simple", "BEIR entity retrieval"),
    ),
    QuestionType(
        question_type="set_recall",
        label="set recall",
        description=(
            "Return a deduplicated set of all matching saved items, not just a top-k answer."
        ),
        example="保存した居酒屋候補を全部出して",
        required_capabilities=("lexical", "semantic", "deduplication", "account_scope"),
        current_readiness="weak",
        risk="The current path is top-k oriented and can miss long-tail matches.",
        benchmark_sources=("CRAG set", "KILT slot filling"),
    ),
    QuestionType(
        question_type="aggregation_count_rank",
        label="aggregation and ranking",
        description=(
            "Count, group, sort, or rank saved evidence by author, topic, account, date, "
            "or frequency."
        ),
        example="最近保存数が増えている関心領域を多い順に出して",
        required_capabilities=("metadata", "grouping", "deduplication", "post_processing"),
        current_readiness="weak",
        risk="Search results are not the same as a complete aggregate over the corpus.",
        benchmark_sources=("CRAG aggregation", "MTEB clustering"),
    ),
    QuestionType(
        question_type="comparison",
        label="comparison",
        description="Compare two or more saved entities, authors, claims, events, or time periods.",
        example="AさんとBさんのAI観の違いを保存投稿から比較して",
        required_capabilities=("semantic", "author_profile", "relation_expansion", "citation"),
        current_readiness="medium",
        risk=(
            "Generated author profiles can over-summarize unless citations return to source tweets."
        ),
        benchmark_sources=("HotpotQA comparison", "2WikiMultiHopQA comparison"),
    ),
    QuestionType(
        question_type="multi_hop_evidence",
        label="multi-hop evidence",
        description=(
            "Answer by chaining author, topic, quote/source, URL, date, and relation evidence."
        ),
        example="この引用投稿は引用元を踏まえると何を主張してる？",
        required_capabilities=("relation_expansion", "quote_context", "source_restore", "citation"),
        current_readiness="medium",
        risk=(
            "Relation expansion exists, but hop-by-hop decomposition and failure reporting "
            "are thin."
        ),
        benchmark_sources=("HotpotQA supporting facts", "MuSiQue", "FRAMES"),
    ),
    QuestionType(
        question_type="temporal_freshness",
        label="temporal freshness",
        description=(
            "Separate old, newer, current, obsolete-candidate, and externally grounded evidence."
        ),
        example="昔保存したこの技術情報、今も正しい？",
        required_capabilities=("freshness_relations", "external_context", "citation", "abstention"),
        current_readiness="medium",
        risk=(
            "Date ordering is only a candidate signal unless a judge or external source "
            "confirms it."
        ),
        benchmark_sources=("CRAG dynamism", "LongMemEval updates", "FRAMES temporal"),
    ),
    QuestionType(
        question_type="contradiction_support",
        label="support and contradiction",
        description=(
            "Find saved evidence that supports, contradicts, or weakly contextualizes a claim."
        ),
        example="同じ話で反対意見や矛盾している保存投稿はある？",
        required_capabilities=("relation_judge", "same_topic", "citation", "review_status"),
        current_readiness="weak",
        risk="Deterministic same-topic edges are not proof of contradiction.",
        benchmark_sources=("FEVER", "KILT fact verification", "ARES"),
    ),
    QuestionType(
        question_type="abstention_false_premise",
        label="abstention and false premise",
        description="Detect missing or false premises and return a bounded no-evidence result.",
        example="保存したはずの札幌のピザ店を出して。なければないと言って",
        required_capabilities=(
            "coverage_check",
            "negative_evidence",
            "external_context",
            "stop_reason",
        ),
        current_readiness="weak",
        risk="No-local-evidence and false-premise are not yet strongly separated.",
        benchmark_sources=("CRAG false premise", "LongMemEval abstention"),
    ),
    QuestionType(
        question_type="citation_required",
        label="citation required",
        description=(
            "Evaluate whether the final context and answer cite stable source chunks, "
            "not just plausible text."
        ),
        example="根拠tweetと引用元を明示して説明して",
        required_capabilities=("context_chunks", "citation_annotations", "source_restore"),
        current_readiness="strong",
        risk="Derived summaries must not become citation-ready without source links.",
        benchmark_sources=("RAGAS", "ARES", "DeepEval", "KILT provenance"),
    ),
    QuestionType(
        question_type="multilingual_source",
        label="multilingual source",
        description=(
            "Use Japanese queries to recover English or mixed-language saved URLs, papers, "
            "docs, and tweets."
        ),
        example="日本語で聞くけど、保存した英語論文や公式docsから強化学習の資料を出して",
        required_capabilities=("multilingual_embedding", "lexical", "external_reader", "citation"),
        current_readiness="unknown",
        risk=(
            "Needs production embedding evaluation; lexical Japanese terms alone are insufficient."
        ),
        benchmark_sources=("MIRACL", "MTEB retrieval"),
    ),
    QuestionType(
        question_type="media_grounded",
        label="media grounded",
        description=(
            "Use image, screenshot, chart, menu, or visual context attached to a saved tweet."
        ),
        example="画像の図表にあったネットワーク資料っぽい投稿を出して",
        required_capabilities=("media_context", "ocr_or_caption", "source_restore", "citation"),
        current_readiness="weak",
        risk="Current media docs preserve metadata but not OCR/VLM image content.",
        benchmark_sources=("M-BEIR", "MMEB", "LoCoMo multimodal"),
    ),
    QuestionType(
        question_type="personal_preference",
        label="personal preference memory",
        description=(
            "Infer recurring user interests from repeated saves while keeping evidence "
            "separate from inference."
        ),
        example="自分が何度も保存している作者やテーマの傾向を教えて",
        required_capabilities=("feedback", "cross_account", "author_profile", "aggregation"),
        current_readiness="medium",
        risk="Preference is an inference and must not overwrite raw bookmark evidence.",
        benchmark_sources=("LongMemEval", "LoCoMo"),
    ),
    QuestionType(
        question_type="exploratory_map",
        label="exploratory map",
        description=(
            "Build a study or exploration map over saved material without pretending the map "
            "is evidence."
        ),
        example="強化学習、ロボット、ネットワークを勉強順に整理して",
        required_capabilities=(
            "topic_thread",
            "corpus2skill_map",
            "relation_expansion",
            "citation",
        ),
        current_readiness="medium",
        risk="Navigation maps help discovery but final facts still need source citations.",
        benchmark_sources=("Corpus2Skill", "GraphRAG global search", "MTEB clustering"),
    ),
)


def question_types_as_dicts() -> list[dict[str, object]]:
    return [asdict(question_type) for question_type in QUESTION_TYPES]


def question_types_json() -> str:
    return json.dumps(question_types_as_dicts(), ensure_ascii=False, indent=2, sort_keys=True)


def format_question_types() -> str:
    lines = []
    for item in QUESTION_TYPES:
        lines.append(
            "\n".join(
                [
                    f"{item.question_type}: {item.label}",
                    f"  readiness: {item.current_readiness}",
                    f"  example: {item.example}",
                    f"  capabilities: {', '.join(item.required_capabilities)}",
                    f"  risk: {item.risk}",
                ]
            )
        )
    return "\n\n".join(lines)


def known_question_type_ids() -> tuple[str, ...]:
    return tuple(item.question_type for item in QUESTION_TYPES)
