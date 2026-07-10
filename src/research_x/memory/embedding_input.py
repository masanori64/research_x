from __future__ import annotations

import json
import re
import sqlite3
from collections import Counter
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from research_x.memory.document_hashes import memory_document_source_hash, text_hash
from research_x.memory.persistence import PersistenceMode, normalize_persistence_mode
from research_x.memory.schema import ensure_memory_schema
from research_x.memory.source_identity import source_bundle_id

DEFAULT_CLASSIFICATION_VERSION = "embedding-taxonomy-v1"
DEFAULT_TEMPLATE_POLICY_VERSION = "embedding-template-policy-v1"
DEFAULT_PROJECTION_POLICY_VERSION = "embedding-projection-policy-v1"
DEFAULT_METADATA_FILTER_POLICY_VERSION = "embedding-metadata-filter-policy-v1"
DEFAULT_CONTROL_ARTIFACT_DIR = Path("runs") / "control_artifacts" / "embedding_input"

SOURCE_KINDS = (
    "x_authored_tweet",
    "x_bookmarked_tweet",
    "x_reply",
    "x_quote_comment",
    "x_quoted_source",
    "x_thread_root",
    "x_thread_member",
    "x_media_attachment",
    "x_media_ocr_text",
    "x_media_caption",
    "x_media_vlm_observation",
    "external_search_candidate",
    "external_fetch_text",
    "derived_author_profile",
    "derived_topic_event_card",
    "derived_relation_card",
    "derived_preference_stance_card",
    "derived_temporal_event_card",
    "operational_control_artifact",
    "unknown",
)
OWNERSHIP_KINDS = (
    "authored_by_tracked_account",
    "authored_by_external_account",
    "bookmarked_by_user",
    "bookmarked_by_tracked_account",
    "collected_by_user",
    "media_attached_to_restored_source",
    "external_public_reference",
    "derived_from_restored_sources",
    "operational_owned",
    "ambiguous_ownership",
    "unknown",
)
CONTENT_ROLES = (
    "statement",
    "opinion",
    "question",
    "answer",
    "link_share",
    "reply_context",
    "quote_commentary",
    "quoted_material",
    "thread_context",
    "evidence_reference",
    "technical_note",
    "event_update",
    "preference_signal",
    "media_text",
    "external_article_text",
    "author_profile_summary",
    "topic_summary",
    "relation_summary",
    "temporal_summary",
    "route_hint",
    "control_or_review_note",
    "unknown",
)
RELATION_ROLES = (
    "standalone",
    "reply_child",
    "reply_parent_context",
    "quote_comment",
    "quoted_source",
    "thread_root",
    "thread_member",
    "bookmark_target",
    "bookmark_relation",
    "media_child",
    "external_child",
    "derived_from_single_source",
    "derived_from_multiple_sources",
    "operational",
    "unknown",
)
MODALITY_KINDS = (
    "text",
    "image",
    "video",
    "audio",
    "pdf",
    "webpage",
    "mixed_media",
    "metadata_only",
    "unknown",
)
TEMPORAL_SCOPES = (
    "point_in_time",
    "event_window",
    "evergreen",
    "historical_snapshot",
    "rapidly_stale",
    "derived_current_profile",
    "unknown",
)
SENSITIVITY_KINDS = (
    "public_source",
    "account_specific_bookmark",
    "private_account_derived",
    "auth_sensitive",
    "external_public",
    "contains_personal_data",
    "secret_or_token_like",
    "operational_not_for_embedding",
    "unknown",
)

PROJECTION_PROFILES = (
    "general_memory",
    "bookmark_interest",
    "authored_stance",
    "relation_context",
    "temporal_event",
    "preference_stance",
    "media_text_bridge",
    "external_fetch_text",
    "author_profile_route",
    "topic_event_route",
    "code_technical",
)

PROFILE_TARGET_SPACE = {
    "general_memory": "text.general_memory.v1",
    "bookmark_interest": "text.bookmark_interest.v1",
    "authored_stance": "text.authored_stance.v1",
    "relation_context": "text.relation_context.v1",
    "temporal_event": "text.temporal_event.v1",
    "preference_stance": "text.preference_stance.v1",
    "media_text_bridge": "media.text_bridge.v1",
    "external_fetch_text": "external.fetch_text.v1",
    "author_profile_route": "text.author_profile_route.v1",
    "topic_event_route": "text.topic_event_route.v1",
    "code_technical": "text.code_technical.v1",
}

RETRIEVAL_INTENTS = (
    "who_said",
    "what_did_user_say",
    "what_did_user_bookmark",
    "bookmark_interest",
    "author_history",
    "topic_recall",
    "technical_recall",
    "temporal_event_recall",
    "reply_or_conversation_context",
    "quote_relation_recall",
    "media_content_recall",
    "external_context_recall",
    "preference_or_stance",
    "general_semantic_recall",
)

TAXONOMY_COLUMNS = (
    "doc_id",
    "source_doc_hash",
    "source_bundle_id",
    "source_kind",
    "ownership_kind",
    "content_role",
    "relation_role",
    "modality_kind",
    "temporal_scope",
    "sensitivity_kind",
    "account_id",
    "viewer_account_id",
    "author_id",
    "bookmark_owner_account_id",
    "tweet_id",
    "conversation_id",
    "replied_to_tweet_id",
    "quoted_tweet_id",
    "thread_id",
    "media_id",
    "external_artifact_id",
    "collection_run_id",
    "language",
    "detected_language_confidence",
    "created_at_source",
    "observed_at",
    "embedding_eligible",
    "embedding_exclusion_reason",
    "answer_support_possible",
    "answer_support_block_reason",
    "classification_version",
    "classification_method",
    "classification_confidence",
    "needs_review",
    "review_reason",
    "source_restore_status",
    "source_restore_path_json",
    "created_at",
    "updated_at",
)

PROJECTION_COLUMNS = (
    "projection_id",
    "doc_id",
    "source_doc_hash",
    "source_bundle_id",
    "classification_version",
    "projection_policy_version",
    "projection_profile",
    "target_space_id",
    "text_template_version",
    "embedded_text",
    "embedded_text_hash",
    "embedded_text_char_count",
    "estimated_input_tokens",
    "included_fields_json",
    "excluded_fields_json",
    "evidence_role",
    "answer_support_allowed",
    "candidate_signal_type",
    "source_restore_path_json",
    "contributing_source_hashes_json",
    "projection_status",
    "stale_status",
    "stale_reason",
    "created_at",
    "updated_at",
)

SECRET_RE = re.compile(
    r"(?i)(api[_-]?key|authorization|bearer|cookie|session|token|secret)\s*[:=]\s*\S+"
)
TECHNICAL_RE = re.compile(
    r"(?i)\b(api|cli|pytest|ruff|uv|python|json|sqlite|schema|provider|embedding|error)\b"
)
DATE_RE = re.compile(r"\b\d{4}[-/]\d{1,2}(?:[-/]\d{1,2})?\b")


@dataclass(frozen=True)
class TemplatePolicy:
    template_version: str
    projection_profile: str
    target_space_id: str
    source_kind_allowlist: tuple[str, ...]
    ownership_allowlist: tuple[str, ...]
    content_role_allowlist: tuple[str, ...]
    template_body: str
    max_input_chars: int
    field_policy: dict[str, Any]
    evidence_role: str
    status: str = "active"


@dataclass(frozen=True)
class FilterResult:
    results: tuple[Any, ...]
    explanation: dict[str, Any]


def classify_embedding_inputs(
    db_path: str | Path,
    *,
    classification_version: str = DEFAULT_CLASSIFICATION_VERSION,
    write: bool = False,
    doc_id: str | None = None,
    source_kind: str | None = None,
    limit: int | None = None,
    report_dir: str | Path = DEFAULT_CONTROL_ARTIFACT_DIR,
    persistence: str | PersistenceMode = PersistenceMode.NONE,
) -> dict[str, Any]:
    path = Path(db_path)
    with sqlite3.connect(path, timeout=60) as conn:
        conn.row_factory = sqlite3.Row
        ensure_memory_schema(conn)
        _ensure_classification_source_indexes(conn)
        rows = [
            _classify_document(conn, row, classification_version=classification_version)
            for row in _document_rows(conn, doc_id=doc_id, limit=limit)
        ]
        if source_kind:
            rows = [row for row in rows if row["source_kind"] == source_kind]
        if write:
            _upsert_taxonomy_rows(conn, rows)
            conn.commit()
        report = taxonomy_report(rows, classification_version=classification_version)
    if _stores_control_artifacts(persistence):
        _write_taxonomy_reports(report, report_dir=Path(report_dir))
    return report


def taxonomy_report(
    rows: list[dict[str, Any]],
    *,
    classification_version: str = DEFAULT_CLASSIFICATION_VERSION,
) -> dict[str, Any]:
    counters = {
        "by_source_kind": Counter(row["source_kind"] for row in rows),
        "by_ownership_kind": Counter(row["ownership_kind"] for row in rows),
        "by_content_role": Counter(row["content_role"] for row in rows),
        "by_relation_role": Counter(row["relation_role"] for row in rows),
        "by_modality_kind": Counter(row["modality_kind"] for row in rows),
        "by_sensitivity_kind": Counter(row["sensitivity_kind"] for row in rows),
    }
    bookmark_rows = [row for row in rows if row["source_kind"] == "x_bookmarked_tweet"]
    media_rows = [row for row in rows if str(row["source_kind"]).startswith("x_media")]
    external_rows = [row for row in rows if str(row["source_kind"]).startswith("external")]
    unknown_rows = [row for row in rows if row["source_kind"] == "unknown"]
    blocking_issues: list[str] = []
    if unknown_rows:
        blocking_issues.append("unknown_documents_excluded_from_production_embedding")
    missing_bookmark_owner = [
        row for row in bookmark_rows if not row.get("bookmark_owner_account_id")
    ]
    if missing_bookmark_owner:
        blocking_issues.append("bookmark_documents_missing_owner")
    return {
        "classification_version": classification_version,
        "total_documents_seen": len(rows),
        "classified_documents": len(rows),
        "embedding_eligible_documents": sum(int(row["embedding_eligible"]) for row in rows),
        "excluded_documents": sum(1 for row in rows if not int(row["embedding_eligible"])),
        "needs_review_documents": sum(int(row["needs_review"]) for row in rows),
        "unknown_documents": len(unknown_rows),
        **{key: dict(sorted(value.items())) for key, value in counters.items()},
        "bookmark_documents": {
            "count": len(bookmark_rows),
            "with_bookmark_owner": sum(
                1 for row in bookmark_rows if row.get("bookmark_owner_account_id")
            ),
            "missing_bookmark_owner": len(missing_bookmark_owner),
        },
        "media_documents": {
            "count": len(media_rows),
            "with_local_path_or_hash": sum(
                1
                for row in media_rows
                if _restore_path(row).get("media_hash") or _restore_path(row).get("local_path")
            ),
            "missing_local_path_or_hash": sum(
                1
                for row in media_rows
                if not (
                    _restore_path(row).get("media_hash")
                    or _restore_path(row).get("local_path")
                )
            ),
        },
        "external_documents": {
            "candidates": sum(
                1 for row in external_rows if row["source_kind"] == "external_search_candidate"
            ),
            "fetch_artifacts": sum(
                1 for row in external_rows if row["source_kind"] == "external_fetch_text"
            ),
            "fetch_artifacts_embedding_eligible": sum(
                1
                for row in external_rows
                if row["source_kind"] == "external_fetch_text" and row["embedding_eligible"]
            ),
        },
        "operational_artifacts_excluded": sum(
            1 for row in rows if row["source_kind"] == "operational_control_artifact"
        ),
        "blocking_issues": blocking_issues,
    }


def write_default_template_policies(
    db_path: str | Path,
    *,
    policy_version: str = DEFAULT_TEMPLATE_POLICY_VERSION,
    write: bool = True,
    report_dir: str | Path = DEFAULT_CONTROL_ARTIFACT_DIR,
    persistence: str | PersistenceMode = PersistenceMode.NONE,
) -> dict[str, Any]:
    policies = default_template_policies()
    path = Path(db_path)
    with sqlite3.connect(path, timeout=60) as conn:
        ensure_memory_schema(conn)
        if write:
            now = _utc_now()
            for policy in policies:
                conn.execute(
                    """
                    INSERT INTO memory_embedding_template_policies (
                        template_version, projection_profile, target_space_id,
                        source_kind_allowlist_json, ownership_allowlist_json,
                        content_role_allowlist_json, template_body, max_input_chars,
                        field_policy_json, evidence_role, created_at, status
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(template_version) DO UPDATE SET
                        projection_profile=excluded.projection_profile,
                        target_space_id=excluded.target_space_id,
                        source_kind_allowlist_json=excluded.source_kind_allowlist_json,
                        ownership_allowlist_json=excluded.ownership_allowlist_json,
                        content_role_allowlist_json=excluded.content_role_allowlist_json,
                        template_body=excluded.template_body,
                        max_input_chars=excluded.max_input_chars,
                        field_policy_json=excluded.field_policy_json,
                        evidence_role=excluded.evidence_role,
                        status=excluded.status
                    """,
                    (
                        policy.template_version,
                        policy.projection_profile,
                        policy.target_space_id,
                        _json(policy.source_kind_allowlist),
                        _json(policy.ownership_allowlist),
                        _json(policy.content_role_allowlist),
                        policy.template_body,
                        policy.max_input_chars,
                        _json(policy.field_policy),
                        policy.evidence_role,
                        now,
                        policy.status,
                    ),
                )
            conn.commit()
    report = projection_policy_report(policies, policy_version=policy_version)
    if _stores_control_artifacts(persistence):
        _write_projection_policy_reports(report, report_dir=Path(report_dir))
    return report


def build_embedding_template_examples(
    db_path: str | Path,
    *,
    policy_version: str = DEFAULT_TEMPLATE_POLICY_VERSION,
    classification_version: str = DEFAULT_CLASSIFICATION_VERSION,
    limit: int = 50,
    write: bool = True,
    report_dir: str | Path = DEFAULT_CONTROL_ARTIFACT_DIR,
    persistence: str | PersistenceMode = PersistenceMode.NONE,
) -> list[dict[str, Any]]:
    path = Path(db_path)
    policies = {policy.template_version: policy for policy in default_template_policies()}
    examples: list[dict[str, Any]] = []
    with sqlite3.connect(path, timeout=60) as conn:
        conn.row_factory = sqlite3.Row
        ensure_memory_schema(conn)
        rows = _input_taxonomy_doc_rows(
            conn,
            classification_version=classification_version,
            allow_write=write,
        )
        for tax, doc in rows:
            for profile in required_projection_profiles(tax):
                policy = policies.get(template_for_projection(tax, profile))
                if not policy:
                    continue
                rendered = render_template(policy, tax, doc)
                examples.append(
                    {
                        "example_id": _stable_id(
                            "template-example",
                            policy.template_version,
                            tax["doc_id"],
                            rendered["embedded_text_hash"],
                        ),
                        "template_version": policy.template_version,
                        "doc_id": tax["doc_id"],
                        "projection_profile": profile,
                        "target_space_id": PROFILE_TARGET_SPACE[profile],
                        **rendered,
                        "policy_version": policy_version,
                    }
                )
                if len(examples) >= limit:
                    break
            if len(examples) >= limit:
                break
        if write:
            now = _utc_now()
            for example in examples:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO memory_embedding_template_examples (
                        example_id, template_version, doc_id, projection_profile,
                        target_space_id, embedded_text, embedded_text_hash,
                        included_fields_json, excluded_fields_json, created_at,
                        metadata_json
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        example["example_id"],
                        example["template_version"],
                        example["doc_id"],
                        example["projection_profile"],
                        example["target_space_id"],
                        example["embedded_text"],
                        example["embedded_text_hash"],
                        _json(example["included_fields"]),
                        _json(example["excluded_fields"]),
                        now,
                        _json({"policy_version": policy_version}),
                    ),
                )
            conn.commit()
    if _stores_control_artifacts(persistence):
        _write_examples_jsonl(examples, report_dir=Path(report_dir))
    return examples


def build_embedding_projections(
    db_path: str | Path,
    *,
    classification_version: str = DEFAULT_CLASSIFICATION_VERSION,
    projection_policy_version: str = DEFAULT_PROJECTION_POLICY_VERSION,
    projection_profile: str | None = None,
    space_id: str | None = None,
    doc_id: str | None = None,
    source_kind: str | None = None,
    limit: int | None = None,
    write: bool = False,
    report_dir: str | Path = DEFAULT_CONTROL_ARTIFACT_DIR,
    persistence: str | PersistenceMode = PersistenceMode.NONE,
) -> dict[str, Any]:
    path = Path(db_path)
    policies = {policy.template_version: policy for policy in default_template_policies()}
    projections: list[dict[str, Any]] = []
    with sqlite3.connect(path, timeout=60) as conn:
        conn.row_factory = sqlite3.Row
        ensure_memory_schema(conn)
        rows = _input_taxonomy_doc_rows(
            conn,
            classification_version=classification_version,
            doc_id=doc_id,
            source_kind=source_kind,
            allow_write=write,
        )
        for tax, doc in rows:
            if not int(tax["embedding_eligible"]):
                continue
            profiles = required_projection_profiles(tax)
            if projection_profile:
                profiles = tuple(profile for profile in profiles if profile == projection_profile)
            for profile in profiles:
                target_space_id = PROFILE_TARGET_SPACE[profile]
                if space_id and target_space_id != space_id:
                    continue
                policy = policies.get(template_for_projection(tax, profile))
                if not policy:
                    continue
                rendered = render_template(policy, tax, doc)
                if not rendered["embedded_text"].strip():
                    continue
                projections.append(
                    _projection_row_for_rendered(
                        tax,
                        policy=policy,
                        profile=profile,
                        target_space_id=target_space_id,
                        rendered=rendered,
                        projection_policy_version=projection_policy_version,
                    )
                )
                if limit is not None and len(projections) >= max(0, limit):
                    break
            if limit is not None and len(projections) >= max(0, limit):
                break
        if write:
            _mark_stale_projection_rows(
                conn,
                projections,
                projection_policy_version=projection_policy_version,
            )
            _upsert_projection_rows(conn, projections)
            conn.commit()
        coverage = projection_coverage_report_from_rows(
            conn,
            projections,
            classification_version=classification_version,
            projection_policy_version=projection_policy_version,
            classified_taxonomy_rows=tuple(tax for tax, _doc in rows),
        )
    if _stores_control_artifacts(persistence):
        _write_projection_coverage_reports(coverage, projections, report_dir=Path(report_dir))
    return coverage


def projection_coverage_report(
    db_path: str | Path,
    *,
    classification_version: str = DEFAULT_CLASSIFICATION_VERSION,
    projection_policy_version: str = DEFAULT_PROJECTION_POLICY_VERSION,
    report_dir: str | Path = DEFAULT_CONTROL_ARTIFACT_DIR,
    persistence: str | PersistenceMode = PersistenceMode.NONE,
) -> dict[str, Any]:
    path = Path(db_path)
    with sqlite3.connect(path, timeout=60) as conn:
        conn.row_factory = sqlite3.Row
        ensure_memory_schema(conn)
        rows = conn.execute(
            """
            SELECT *
            FROM memory_embedding_projections
            WHERE classification_version = ?
              AND projection_policy_version = ?
            """,
            (classification_version, projection_policy_version),
        ).fetchall()
        report = _projection_coverage_from_stored_rows(
            conn,
            rows,
            classification_version=classification_version,
            projection_policy_version=projection_policy_version,
        )
    if _stores_control_artifacts(persistence):
        _write_projection_coverage_reports(
            report,
            [dict(row) for row in rows],
            report_dir=Path(report_dir),
        )
    return report


def metadata_filter_policy_report(
    *,
    policy_version: str = DEFAULT_METADATA_FILTER_POLICY_VERSION,
    report_dir: str | Path = DEFAULT_CONTROL_ARTIFACT_DIR,
    persistence: str | PersistenceMode = PersistenceMode.NONE,
) -> dict[str, Any]:
    report = {
        "policy_version": policy_version,
        "intent_classes": list(RETRIEVAL_INTENTS),
        "filter_rules": _filter_rules(),
        "answer_wording_constraints": _answer_wording_constraints(),
        "excluded_by_default": {
            "source_kind": ["external_search_candidate", "operational_control_artifact"],
            "sensitivity_kind": ["secret_or_token_like", "operational_not_for_embedding"],
        },
        "not_evidence_rules": [
            "bookmark_interest_alone_is_not_endorsement",
            "derived_card_is_not_evidence",
            "vector_hit_is_not_evidence",
            "search_candidate_snippet_is_not_evidence",
        ],
    }
    if _stores_control_artifacts(persistence):
        _write_metadata_filter_reports(report, report_dir=Path(report_dir))
    return report


def apply_metadata_filters(
    db_path: str | Path,
    results: tuple[Any, ...],
    *,
    query: str,
    intent: str | None = None,
    author_id: str | None = None,
    bookmark_owner_account_id: str | None = None,
    source_kind: str | None = None,
    ownership_kind: str | None = None,
    content_role: str | None = None,
    relation_role: str | None = None,
    language: str | None = None,
    modality_kind: str | None = None,
    sensitivity_kind: str | None = None,
    projection_profile: str | None = None,
    space_id: str | None = None,
    require_projections: bool = False,
) -> FilterResult:
    resolved_intent = resolve_retrieval_intent(query, explicit_intent=intent)
    before = len(results)
    doc_ids = tuple(str(result.doc_id) for result in results)
    taxonomy = _latest_taxonomy_by_doc_id(db_path, doc_ids)
    projection_docs = _projection_doc_ids(
        db_path,
        doc_ids,
        projection_profile=projection_profile,
        space_id=space_id,
    )
    filtered = []
    excluded_counts: Counter[str] = Counter()
    warnings: list[str] = []
    for result in results:
        tax = taxonomy.get(str(result.doc_id), {})
        reason = _filter_exclusion_reason(
            tax,
            intent=resolved_intent,
            author_id=author_id,
            bookmark_owner_account_id=bookmark_owner_account_id,
            source_kind=source_kind,
            ownership_kind=ownership_kind,
            content_role=content_role,
            relation_role=relation_role,
            language=language,
            modality_kind=modality_kind,
            sensitivity_kind=sensitivity_kind,
            require_projections=require_projections,
            has_projection=str(result.doc_id) in projection_docs,
        )
        if reason:
            excluded_counts[reason] += 1
            continue
        if resolved_intent in {"what_did_user_bookmark", "bookmark_interest"}:
            warnings.append("bookmark_interest_alone_is_not_endorsement")
        if resolved_intent == "preference_or_stance" and tax.get("ownership_kind", "").startswith(
            "bookmarked"
        ):
            warnings.append("bookmark_interest_is_weak_stance_signal_only")
        filtered.append(_result_with_taxonomy(result, tax))
    explanation = {
        "intent": resolved_intent,
        "applied_filters": {
            "author_id": author_id,
            "bookmark_owner_account_id": bookmark_owner_account_id,
            "source_kind": source_kind,
            "ownership_kind": ownership_kind,
            "content_role": content_role,
            "relation_role": relation_role,
            "language": language,
            "modality_kind": modality_kind,
            "sensitivity_kind": sensitivity_kind,
            "projection_profile": projection_profile,
            "space_id": space_id,
            "require_projections": require_projections,
        },
        "excluded_source_kinds": _filter_rules().get(resolved_intent, {}).get(
            "exclude_source_kind",
            [],
        ),
        "excluded_ownership_kinds": _filter_rules().get(resolved_intent, {}).get(
            "exclude_ownership_kind",
            [],
        ),
        "candidate_counts_before_filter": {"total": before},
        "candidate_counts_after_filter": {"total": len(filtered)},
        "excluded_candidate_counts": dict(sorted(excluded_counts.items())),
        "warnings": sorted(set(warnings)),
    }
    filtered = [_result_with_filter_explanation(result, explanation) for result in filtered]
    return FilterResult(results=tuple(filtered), explanation=explanation)


def resolve_retrieval_intent(query: str, *, explicit_intent: str | None = None) -> str:
    if explicit_intent:
        normalized = explicit_intent.strip().replace("-", "_")
        if normalized not in RETRIEVAL_INTENTS:
            raise ValueError(
                "retrieval intent must be one of: " + ", ".join(RETRIEVAL_INTENTS)
            )
        return normalized
    text = query.casefold()
    if any(marker in text for marker in ("what did i say", "i said", "私が言", "自分が言")):
        return "what_did_user_say"
    if any(marker in text for marker in ("bookmark", "bookmarked", "saved", "ブクマ", "保存")):
        return "what_did_user_bookmark"
    if any(marker in text for marker in ("stance", "believe", "preference", "好み", "スタンス")):
        return "preference_or_stance"
    if any(marker in text for marker in ("quote", "quoted", "引用")):
        return "quote_relation_recall"
    if any(marker in text for marker in ("reply", "conversation", "thread", "返信", "会話")):
        return "reply_or_conversation_context"
    if any(marker in text for marker in ("media", "image", "video", "ocr", "画像", "動画")):
        return "media_content_recall"
    if any(marker in text for marker in ("external", "web", "url", "article", "外部")):
        return "external_context_recall"
    if any(marker in text for marker in ("author", "who said", "誰が", "発言")):
        return "who_said"
    if any(marker in text for marker in ("code", "api", "error", "pytest", "実装")):
        return "technical_recall"
    if DATE_RE.search(text) or any(marker in text for marker in ("when", "latest", "最近")):
        return "temporal_event_recall"
    return "general_semantic_recall"


def default_template_policies() -> tuple[TemplatePolicy, ...]:
    return (
        _policy(
            "authored_tweet.embedding.v1",
            "general_memory",
            ("x_authored_tweet",),
            "Source type: X authored tweet.\nAuthorship: tracked account authored this text.",
        ),
        _policy(
            "bookmarked_tweet.embedding.v1",
            "bookmark_interest",
            ("x_bookmarked_tweet",),
            (
                "Source type: X bookmarked tweet.\n"
                "Important: Bookmarking is not necessarily endorsement."
            ),
        ),
        _policy(
            "reply.embedding.v1",
            "relation_context",
            ("x_reply",),
            "Source type: X reply.\nRelation: reply in a conversation.",
        ),
        _policy(
            "quote_comment.embedding.v1",
            "relation_context",
            ("x_quote_comment",),
            "Source type: X quote tweet comment.\nRelation: quoting author's comment.",
        ),
        _policy(
            "quoted_source.embedding.v1",
            "relation_context",
            ("x_quoted_source",),
            "Source type: Quoted X source.\nRelation: quoted author's source content.",
        ),
        _policy(
            "thread_context.embedding.v1",
            "relation_context",
            ("x_thread_root", "x_thread_member"),
            "Source type: X thread context.\nThread-positioned content.",
        ),
        _policy(
            "media_text_bridge.embedding.v1",
            "media_text_bridge",
            ("x_media_ocr_text", "x_media_caption", "x_media_vlm_observation"),
            "Source type: Media-derived text.\nThis is candidate text, not media evidence.",
        ),
        _policy(
            "external_fetch_text.embedding.v1",
            "external_fetch_text",
            ("external_fetch_text",),
            "Source type: External fetched text.\nRequires fetch artifact restoration.",
        ),
        _policy(
            "derived_author_profile.embedding.v1",
            "author_profile_route",
            ("derived_author_profile",),
            "Source type: Derived author profile.\nThis is not evidence.",
            evidence_role="derived_not_evidence",
        ),
        _policy(
            "derived_topic_event_card.embedding.v1",
            "topic_event_route",
            ("derived_topic_event_card", "derived_temporal_event_card"),
            "Source type: Derived topic/event card.\nThis is not evidence.",
            evidence_role="derived_not_evidence",
        ),
        _policy(
            "relation_context.embedding.v1",
            "relation_context",
            ("derived_relation_card",),
            "Source type: Relation context projection.\nThis is not evidence by itself.",
            evidence_role="derived_not_evidence",
        ),
        _policy(
            "preference_stance_candidate.embedding.v1",
            "preference_stance",
            ("derived_preference_stance_card", "x_bookmarked_tweet"),
            (
                "Source type: Preference or stance candidate.\n"
                "This is not proof of belief."
            ),
        ),
        _policy(
            "code_technical.embedding.v1",
            "code_technical",
            SOURCE_KINDS,
            "Source type: Technical/code-related memory.\nCandidate-only retrieval text.",
        ),
    )


def required_projection_profiles(taxonomy: dict[str, Any] | sqlite3.Row) -> tuple[str, ...]:
    source_kind = _value(taxonomy, "source_kind")
    relation_role = _value(taxonomy, "relation_role")
    content_role = _value(taxonomy, "content_role")
    text = " ".join((_value(taxonomy, "doc_id"), content_role, relation_role)).lower()
    profiles: list[str] = []
    if source_kind == "x_authored_tweet":
        profiles.append("general_memory")
        if content_role in {"opinion", "statement"}:
            profiles.append("authored_stance")
        if relation_role != "standalone":
            profiles.append("relation_context")
        if _has_temporal_signal(taxonomy):
            profiles.append("temporal_event")
        if TECHNICAL_RE.search(text):
            profiles.append("code_technical")
    elif source_kind == "x_bookmarked_tweet":
        profiles.extend(("general_memory", "bookmark_interest", "preference_stance"))
        if _has_temporal_signal(taxonomy):
            profiles.append("temporal_event")
    elif source_kind in {"x_reply", "x_quote_comment"}:
        profiles.extend(("general_memory", "relation_context"))
    elif source_kind == "x_quoted_source":
        profiles.append("relation_context")
        if _value(taxonomy, "source_restore_status") != "source_not_restored":
            profiles.append("general_memory")
    elif source_kind in {"x_thread_root", "x_thread_member"}:
        profiles.extend(("general_memory", "relation_context"))
        if _has_temporal_signal(taxonomy):
            profiles.append("temporal_event")
    elif source_kind in {"x_media_ocr_text", "x_media_caption", "x_media_vlm_observation"}:
        profiles.append("media_text_bridge")
    elif source_kind == "external_fetch_text":
        profiles.append("external_fetch_text")
        if _has_temporal_signal(taxonomy):
            profiles.append("temporal_event")
    elif source_kind == "derived_author_profile":
        profiles.append("author_profile_route")
    elif source_kind == "derived_topic_event_card":
        profiles.extend(("topic_event_route", "temporal_event"))
    elif source_kind == "derived_relation_card":
        profiles.append("relation_context")
    elif source_kind == "derived_preference_stance_card":
        profiles.append("preference_stance")
    elif source_kind == "derived_temporal_event_card":
        profiles.extend(("temporal_event", "topic_event_route"))
    return tuple(dict.fromkeys(profiles[:5]))


def template_for_projection(
    taxonomy: dict[str, Any] | sqlite3.Row,
    projection_profile: str,
) -> str:
    source_kind = _value(taxonomy, "source_kind")
    if projection_profile == "code_technical":
        return "code_technical.embedding.v1"
    if projection_profile == "preference_stance":
        return "preference_stance_candidate.embedding.v1"
    if source_kind == "x_authored_tweet":
        return "authored_tweet.embedding.v1"
    if source_kind == "x_bookmarked_tweet":
        return "bookmarked_tweet.embedding.v1"
    if source_kind == "x_reply":
        return "reply.embedding.v1"
    if source_kind == "x_quote_comment":
        return "quote_comment.embedding.v1"
    if source_kind == "x_quoted_source":
        return "quoted_source.embedding.v1"
    if source_kind in {"x_thread_root", "x_thread_member"}:
        return "thread_context.embedding.v1"
    if source_kind in {"x_media_ocr_text", "x_media_caption", "x_media_vlm_observation"}:
        return "media_text_bridge.embedding.v1"
    if source_kind == "external_fetch_text":
        return "external_fetch_text.embedding.v1"
    if source_kind == "derived_author_profile":
        return "derived_author_profile.embedding.v1"
    if source_kind in {"derived_topic_event_card", "derived_temporal_event_card"}:
        return "derived_topic_event_card.embedding.v1"
    if source_kind == "derived_relation_card":
        return "relation_context.embedding.v1"
    return "authored_tweet.embedding.v1"


def render_template(
    policy: TemplatePolicy,
    taxonomy: dict[str, Any] | sqlite3.Row,
    doc: dict[str, Any] | sqlite3.Row,
) -> dict[str, Any]:
    metadata = _metadata(doc)
    body = _redact(str(_value(doc, "body") or _value(doc, "compact_text") or ""))
    title = _redact(_value(doc, "title"))
    template_version = policy.template_version
    source_kind = _value(taxonomy, "source_kind")
    fields = {
        "Source type": _source_label(template_version),
        "Source kind": source_kind,
        "Ownership": _value(taxonomy, "ownership_kind"),
        "Content role": _value(taxonomy, "content_role"),
        "Relation role": _value(taxonomy, "relation_role"),
        "Author account": _value(taxonomy, "author_id") or _value(doc, "author_screen_name"),
        "Bookmark owner account": _value(taxonomy, "bookmark_owner_account_id"),
        "Tweet id": _value(taxonomy, "tweet_id"),
        "Created at": _value(taxonomy, "created_at_source"),
        "Observed at": _value(taxonomy, "observed_at"),
        "Language": _value(taxonomy, "language") or "unknown",
        "Conversation id": _value(taxonomy, "conversation_id"),
        "Thread id": _value(taxonomy, "thread_id"),
        "Quoted tweet id": _value(taxonomy, "quoted_tweet_id"),
        "Media id": _value(taxonomy, "media_id"),
        "External artifact id": _value(taxonomy, "external_artifact_id"),
        "Title": title,
        "Text": body,
        "Metadata": _json(_metadata_subset(metadata)),
        "Embedding note": _embedding_note(template_version, source_kind),
    }
    lines: list[str] = [f"Template version: {template_version}"]
    if template_version == "bookmarked_tweet.embedding.v1":
        lines.append(
            "Important: Bookmarking is not necessarily endorsement and is not the user's "
            "authored opinion."
        )
    if template_version.startswith("derived_") or source_kind.startswith("derived_"):
        lines.append("Important: This derived projection is not evidence.")
    for key in sorted(fields):
        value = str(fields[key] or "").strip()
        if value:
            lines.append(f"{key}: {value}")
    embedded_text = canonicalize_text("\n".join(lines))[: policy.max_input_chars]
    included_fields = tuple(key for key, value in fields.items() if str(value or "").strip())
    excluded_fields = (
        "cookies",
        "session state",
        "provider raw request",
        "provider raw response",
        "secret values",
        "unrestored external snippets",
    )
    return {
        "embedded_text": embedded_text,
        "embedded_text_hash": text_hash(embedded_text),
        "included_fields": included_fields,
        "excluded_fields": excluded_fields,
    }


def canonicalize_text(text: str) -> str:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    normalized = "\n".join(line.rstrip() for line in normalized.split("\n"))
    normalized = re.sub(r"\n{3,}", "\n\n", normalized).strip()
    return normalized


def projection_policy_report(
    policies: tuple[TemplatePolicy, ...],
    *,
    policy_version: str = DEFAULT_TEMPLATE_POLICY_VERSION,
) -> dict[str, Any]:
    return {
        "policy_version": policy_version,
        "projection_policy_version": DEFAULT_PROJECTION_POLICY_VERSION,
        "template_count": len(policies),
        "templates": [asdict(policy) for policy in policies],
        "projection_profiles": list(PROJECTION_PROFILES),
        "profile_target_spaces": PROFILE_TARGET_SPACE,
        "source_to_projection_matrix": _source_to_projection_matrix(),
        "evidence_roles_allowed": [
            "candidate_only",
            "derived_not_evidence",
            "operational_not_evidence",
        ],
        "evidence_roles_disallowed": ["citation_ready", "answer_support"],
        "not_evidence": True,
    }


def old_embedding_lineage_report(db_path: str | Path) -> dict[str, Any]:
    path = Path(db_path)
    with sqlite3.connect(path, timeout=60) as conn:
        ensure_memory_schema(conn)
        total = int(conn.execute("SELECT COUNT(*) FROM memory_embeddings").fetchone()[0])
        if total == 0:
            return {
                "total_embeddings": 0,
                "with_projection_id": 0,
                "without_projection_id": 0,
                "status": "no_existing_embeddings",
            }
        columns = _columns(conn, "memory_embeddings")
        projection_column = "projection_id" in columns
        with_projection = 0
        current_without_projection = 0
        quarantined_without_projection = 0
        if projection_column:
            with_projection = int(
                conn.execute(
                    """
                    SELECT COUNT(*)
                    FROM memory_embeddings
                    WHERE projection_id IS NOT NULL AND TRIM(projection_id) != ''
                    """
                ).fetchone()[0]
            )
            current_without_projection = int(
                conn.execute(
                    """
                    SELECT COUNT(*)
                    FROM memory_embeddings
                    WHERE (projection_id IS NULL OR TRIM(projection_id) = '')
                      AND stale_status = 'current'
                    """
                ).fetchone()[0]
            )
            quarantined_without_projection = int(
                conn.execute(
                    """
                    SELECT COUNT(*)
                    FROM memory_embeddings
                    WHERE (projection_id IS NULL OR TRIM(projection_id) = '')
                      AND stale_status = 'legacy_without_projection_lineage'
                    """
                ).fetchone()[0]
            )
        without_projection = total - with_projection
    status = (
        "lineage_complete"
        if current_without_projection == 0
        else "blocked_existing_embeddings_without_projection_lineage"
    )
    return {
        "total_embeddings": total,
        "with_projection_id": with_projection,
        "without_projection_id": without_projection,
        "current_without_projection_id": current_without_projection,
        "quarantined_without_projection_id": quarantined_without_projection,
        "status": status,
    }


def quarantine_legacy_embedding_lineage(db_path: str | Path) -> dict[str, Any]:
    path = Path(db_path)
    now = _utc_now()
    with sqlite3.connect(path, timeout=60) as conn:
        ensure_memory_schema(conn)
        cursor = conn.execute(
            """
            UPDATE memory_embeddings
            SET stale_status = 'legacy_without_projection_lineage',
                updated_at = ?
            WHERE (projection_id IS NULL OR TRIM(projection_id) = '')
              AND stale_status = 'current'
            """,
            (now,),
        )
        conn.commit()
    report = old_embedding_lineage_report(path)
    return {
        "quarantined_rows": int(cursor.rowcount if cursor.rowcount is not None else 0),
        "stale_status": "legacy_without_projection_lineage",
        "lineage_report": report,
    }


def write_full_run_readiness(
    db_path: str | Path,
    *,
    report_dir: str | Path = DEFAULT_CONTROL_ARTIFACT_DIR,
    tests_passed: bool = False,
    quarantine_legacy_embeddings: bool = False,
    persistence: str | PersistenceMode = PersistenceMode.NONE,
) -> dict[str, Any]:
    report_path = Path(report_dir)
    path = Path(db_path)
    with sqlite3.connect(path, timeout=60) as conn:
        conn.row_factory = sqlite3.Row
        ensure_memory_schema(conn)
        taxonomy_total = int(
            conn.execute("SELECT COUNT(*) FROM memory_document_taxonomy").fetchone()[0]
        )
        unknown = int(
            conn.execute(
                "SELECT COUNT(*) FROM memory_document_taxonomy WHERE source_kind = 'unknown'"
            ).fetchone()[0]
        )
        eligible_doc_keys = {
            (str(row["doc_id"]), str(row["classification_version"]))
            for row in conn.execute(
                """
                SELECT doc_id, classification_version
                FROM memory_document_taxonomy
                WHERE embedding_eligible = 1
                """
            ).fetchall()
        }
        projected_doc_keys = {
            (str(row["doc_id"]), str(row["classification_version"]))
            for row in conn.execute(
                """
                SELECT DISTINCT doc_id, classification_version
                FROM memory_embedding_projections
                WHERE projection_status = 'active'
                  AND stale_status = 'current'
                """
            ).fetchall()
        }
        eligible_missing_projection = len(eligible_doc_keys - projected_doc_keys)
    quarantine_report = (
        quarantine_legacy_embedding_lineage(path)
        if quarantine_legacy_embeddings
        else None
    )
    old_lineage = old_embedding_lineage_report(path)
    old_lineage_ok = old_lineage["status"] in {
        "no_existing_embeddings",
        "lineage_complete",
    }
    projection_ready = eligible_missing_projection == 0 and taxonomy_total > 0
    filter_policy_exists = _report_exists(report_path, "embedding_metadata_filter_policy.json")
    answers = {
        "all_embedding_eligible_documents_classified": taxonomy_total > 0,
        "unknown_documents_excluded": unknown == 0,
        "bookmarks_separated_from_authored": taxonomy_total > 0,
        "quote_comments_separated_from_quoted_sources": taxonomy_total > 0,
        "media_derived_text_and_native_media_separated": taxonomy_total > 0,
        "external_candidates_blocked_until_fetch_restoration": taxonomy_total > 0,
        "operational_artifacts_excluded": taxonomy_total > 0,
        "required_templates_installed": _report_exists(
            report_path,
            "embedding_projection_policy.json",
        ),
        "projection_rows_built": projection_ready,
        "projection_rows_current": eligible_missing_projection == 0,
        "embedding_estimate_uses_projection_rows": tests_passed and projection_ready,
        "build_embeddings_requires_projection_rows_for_eval_and_production": tests_passed,
        "metadata_filters_protect_core_intents": filter_policy_exists,
        "workflow_traces_expose_filters_and_exclusions": tests_passed and filter_policy_exists,
        "all_a_d_tests_passed": tests_passed,
        "existing_limit100_embeddings_lineage_disposition": old_lineage_ok,
    }
    blockers = [key for key, value in answers.items() if value is not True]
    status = "ready_for_embedding_expansion" if not blockers else "blocked"
    report = {
        "status": status,
        "answers": answers,
        "blocking_issues": blockers,
        "old_embedding_lineage": old_lineage,
        "quarantine_report": quarantine_report,
    }
    if _stores_control_artifacts(persistence):
        _write_readiness_report(report, report_dir=report_path)
    return report


def _classify_document(
    conn: sqlite3.Connection,
    doc: sqlite3.Row,
    *,
    classification_version: str,
) -> dict[str, Any]:
    now = _utc_now()
    metadata = _metadata(doc)
    doc_id = _value(doc, "doc_id")
    tweet_id = _value(doc, "source_tweet_id") or _metadata_text(
        metadata,
        "tweet_id",
        "source_tweet_id",
    )
    source_doc_hash = _value(doc, "source_doc_hash") or memory_document_source_hash(doc)
    tweet = _tweet_row(conn, tweet_id)
    bookmark = _bookmark_row(conn, tweet_id, account_id=_value(doc, "account_id"))
    media = _media_row(conn, metadata=metadata, tweet_id=tweet_id)
    edge = _edge_row(conn, tweet_id)
    explicit_source_kind = _explicit_source_kind(doc, metadata)
    source_kind = explicit_source_kind or _infer_source_kind(
        doc,
        metadata=metadata,
        bookmark=bookmark,
        media=media,
        edge=edge,
    )
    classification = _classification_defaults(
        source_kind,
        doc=doc,
        metadata=metadata,
        bookmark=bookmark,
        media=media,
        edge=edge,
    )
    sensitivity_kind = classification["sensitivity_kind"]
    text = " ".join((_value(doc, "title"), _value(doc, "body"), _value(doc, "compact_text")))
    if SECRET_RE.search(text):
        sensitivity_kind = "secret_or_token_like"
    embedding_eligible, exclusion_reason = _embedding_eligibility(
        source_kind,
        sensitivity_kind=sensitivity_kind,
        ownership_kind=classification["ownership_kind"],
    )
    answer_support_possible = _answer_support_possible(source_kind, embedding_eligible)
    needs_review, review_reason = _review_state(
        source_kind,
        bookmark=bookmark,
        edge=edge,
        metadata=metadata,
    )
    restore = _source_restore_path(
        doc,
        metadata=metadata,
        tweet=tweet,
        bookmark=bookmark,
        media=media,
        edge=edge,
        source_doc_hash=source_doc_hash,
        source_kind=source_kind,
    )
    source_restore_status = restore["status"]
    if source_restore_status == "source_not_restored":
        answer_support_possible = 0
    row = {
        "doc_id": doc_id,
        "source_doc_hash": source_doc_hash,
        "source_bundle_id": (
            source_bundle_id(doc_id, source_doc_hash)
            if source_restore_status != "source_not_restored"
            else None
        ),
        "source_kind": source_kind,
        "ownership_kind": classification["ownership_kind"],
        "content_role": classification["content_role"],
        "relation_role": classification["relation_role"],
        "modality_kind": classification["modality_kind"],
        "temporal_scope": _temporal_scope(doc, metadata=metadata, source_kind=source_kind),
        "sensitivity_kind": sensitivity_kind,
        "account_id": _value(doc, "account_id"),
        "viewer_account_id": _metadata_text(metadata, "viewer_account_id"),
        "author_id": _author_id(doc, tweet=tweet, metadata=metadata),
        "bookmark_owner_account_id": _bookmark_owner(bookmark, doc, metadata),
        "tweet_id": tweet_id,
        "conversation_id": _metadata_text(metadata, "conversation_id"),
        "replied_to_tweet_id": _reply_parent(edge, metadata),
        "quoted_tweet_id": _metadata_text(metadata, "quoted_tweet_id", "quote_tweet_id"),
        "thread_id": _metadata_text(metadata, "thread_id"),
        "media_id": _media_id(media, metadata),
        "external_artifact_id": _metadata_text(metadata, "external_artifact_id", "artifact_id"),
        "collection_run_id": _bookmark_run(bookmark, metadata),
        "language": (
            _value(doc, "language")
            or _metadata_text(metadata, "language", "lang")
            or "unknown"
        ),
        "detected_language_confidence": _float_or_none(
            metadata.get("detected_language_confidence")
        ),
        "created_at_source": _created_at_source(doc, tweet=tweet, metadata=metadata),
        "observed_at": _value(doc, "observed_at") or _metadata_text(metadata, "observed_at"),
        "embedding_eligible": int(embedding_eligible),
        "embedding_exclusion_reason": exclusion_reason,
        "answer_support_possible": int(answer_support_possible),
        "answer_support_block_reason": None
        if answer_support_possible
        else _answer_support_block_reason(source_kind),
        "classification_version": classification_version,
        "classification_method": "deterministic_rules",
        "classification_confidence": 1.0 if source_kind != "unknown" else 0.0,
        "needs_review": int(needs_review),
        "review_reason": review_reason,
        "source_restore_status": source_restore_status,
        "source_restore_path_json": _json(restore),
        "created_at": now,
        "updated_at": now,
    }
    return row


def _document_rows(
    conn: sqlite3.Connection,
    *,
    doc_id: str | None,
    limit: int | None,
) -> tuple[sqlite3.Row, ...]:
    filters: list[str] = []
    params: list[Any] = []
    if doc_id:
        filters.append("doc_id = ?")
        params.append(doc_id)
    where = f"WHERE {' AND '.join(filters)}" if filters else ""
    sql = f"SELECT * FROM memory_documents {where} ORDER BY observed_at DESC, doc_id"
    if limit is not None:
        sql += " LIMIT ?"
        params.append(max(0, limit))
    return tuple(conn.execute(sql, params).fetchall())


def _upsert_taxonomy_rows(conn: sqlite3.Connection, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    placeholders = ", ".join(":" + column for column in TAXONOMY_COLUMNS)
    updates = ", ".join(
        f"{column}=excluded.{column}"
        for column in TAXONOMY_COLUMNS
        if column not in {"doc_id", "classification_version", "created_at"}
    )
    conn.executemany(
        f"""
        INSERT INTO memory_document_taxonomy ({", ".join(TAXONOMY_COLUMNS)})
        VALUES ({placeholders})
        ON CONFLICT(doc_id, classification_version) DO UPDATE SET {updates}
        """,
        rows,
    )


def _upsert_projection_rows(conn: sqlite3.Connection, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    placeholders = ", ".join(":" + column for column in PROJECTION_COLUMNS)
    updates = ", ".join(
        f"{column}=excluded.{column}"
        for column in PROJECTION_COLUMNS
        if column not in {"projection_id", "created_at"}
    )
    conn.executemany(
        f"""
        INSERT INTO memory_embedding_projections ({", ".join(PROJECTION_COLUMNS)})
        VALUES ({placeholders})
        ON CONFLICT(projection_id) DO UPDATE SET {updates}
        """,
        rows,
    )


def _mark_stale_projection_rows(
    conn: sqlite3.Connection,
    rows: list[dict[str, Any]],
    *,
    projection_policy_version: str,
) -> None:
    for row in rows:
        conn.execute(
            """
            UPDATE memory_embedding_projections
            SET stale_status = CASE
                    WHEN source_doc_hash != ? THEN 'stale_source_changed'
                    WHEN text_template_version != ? THEN 'stale_template_changed'
                    WHEN projection_policy_version != ? THEN 'stale_policy_changed'
                    ELSE stale_status
                END,
                stale_reason = 'superseded_by_current_projection',
                updated_at = ?
            WHERE doc_id = ?
              AND projection_profile = ?
              AND target_space_id = ?
              AND projection_id != ?
              AND stale_status = 'current'
            """,
            (
                row["source_doc_hash"],
                row["text_template_version"],
                projection_policy_version,
                _utc_now(),
                row["doc_id"],
                row["projection_profile"],
                row["target_space_id"],
                row["projection_id"],
            ),
        )


def _ensure_taxonomy_rows(
    conn: sqlite3.Connection,
    *,
    classification_version: str,
) -> None:
    _ensure_classification_source_indexes(conn)
    count = int(
        conn.execute(
            """
            SELECT COUNT(*)
            FROM memory_document_taxonomy
            WHERE classification_version = ?
            """,
            (classification_version,),
        ).fetchone()[0]
    )
    if count:
        return
    rows = [
        _classify_document(conn, row, classification_version=classification_version)
        for row in _document_rows(conn, doc_id=None, limit=None)
    ]
    _upsert_taxonomy_rows(conn, rows)
    conn.commit()


def _ensure_classification_source_indexes(conn: sqlite3.Connection) -> None:
    if _table_exists(conn, "account_bookmarks"):
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_embedding_input_account_bookmarks_tweet
                ON account_bookmarks(tweet_id)
            """
        )
    if _table_exists(conn, "media"):
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_embedding_input_media_tweet
                ON media(tweet_id)
            """
        )
    if _table_exists(conn, "tweet_edges"):
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_embedding_input_tweet_edges_child
                ON tweet_edges(child_tweet_id)
            """
        )


def _input_taxonomy_doc_rows(
    conn: sqlite3.Connection,
    *,
    classification_version: str,
    doc_id: str | None = None,
    source_kind: str | None = None,
    allow_write: bool,
) -> tuple[tuple[dict[str, Any], dict[str, Any]], ...]:
    stored_rows = _taxonomy_doc_rows(
        conn,
        classification_version=classification_version,
        doc_id=doc_id,
        source_kind=source_kind,
    )
    if stored_rows:
        return tuple((dict(tax), dict(doc)) for tax, doc in stored_rows)
    if allow_write:
        _ensure_taxonomy_rows(conn, classification_version=classification_version)
        return tuple(
            (dict(tax), dict(doc))
            for tax, doc in _taxonomy_doc_rows(
                conn,
                classification_version=classification_version,
                doc_id=doc_id,
                source_kind=source_kind,
            )
        )
    rows: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for doc in _document_rows(conn, doc_id=doc_id, limit=None):
        taxonomy = _classify_document(
            conn,
            doc,
            classification_version=classification_version,
        )
        if source_kind and taxonomy["source_kind"] != source_kind:
            continue
        rows.append((taxonomy, dict(doc)))
    return tuple(rows)


def _taxonomy_doc_rows(
    conn: sqlite3.Connection,
    *,
    classification_version: str,
    doc_id: str | None = None,
    source_kind: str | None = None,
) -> tuple[tuple[sqlite3.Row, sqlite3.Row], ...]:
    filters = ["t.classification_version = ?"]
    params: list[Any] = [classification_version]
    if doc_id:
        filters.append("t.doc_id = ?")
        params.append(doc_id)
    if source_kind:
        filters.append("t.source_kind = ?")
        params.append(source_kind)
    rows = conn.execute(
        f"""
        SELECT t.*, d.*
        FROM memory_document_taxonomy t
        JOIN memory_documents d ON d.doc_id = t.doc_id
        WHERE {" AND ".join(filters)}
        ORDER BY d.observed_at DESC, d.doc_id
        """,
        params,
    ).fetchall()
    result = []
    for row in rows:
        row_keys = set(row.keys())
        tax = {
            column: row[column]
            for column in TAXONOMY_COLUMNS
            if column in row_keys
        }
        doc = dict(row)
        result.append((tax, doc))
    return tuple(result)


def _projection_row_for_rendered(
    taxonomy: dict[str, Any] | sqlite3.Row,
    *,
    policy: TemplatePolicy,
    profile: str,
    target_space_id: str,
    rendered: dict[str, Any],
    projection_policy_version: str,
) -> dict[str, Any]:
    now = _utc_now()
    source_hash = _value(taxonomy, "source_doc_hash")
    projection_id = text_hash(
        "\n".join(
            (
                _value(taxonomy, "doc_id"),
                source_hash,
                profile,
                target_space_id,
                policy.template_version,
                projection_policy_version,
                rendered["embedded_text_hash"],
            )
        )
    )
    evidence_role = policy.evidence_role
    return {
        "projection_id": projection_id,
        "doc_id": _value(taxonomy, "doc_id"),
        "source_doc_hash": source_hash,
        "source_bundle_id": _value(taxonomy, "source_bundle_id"),
        "classification_version": _value(taxonomy, "classification_version"),
        "projection_policy_version": projection_policy_version,
        "projection_profile": profile,
        "target_space_id": target_space_id,
        "text_template_version": policy.template_version,
        "embedded_text": rendered["embedded_text"],
        "embedded_text_hash": rendered["embedded_text_hash"],
        "embedded_text_char_count": len(rendered["embedded_text"]),
        "estimated_input_tokens": _rough_tokens(rendered["embedded_text"]),
        "included_fields_json": _json(rendered["included_fields"]),
        "excluded_fields_json": _json(rendered["excluded_fields"]),
        "evidence_role": evidence_role,
        "answer_support_allowed": 0,
        "candidate_signal_type": (
            "derived_route_signal" if evidence_role == "derived_not_evidence" else "candidate"
        ),
        "source_restore_path_json": _value(taxonomy, "source_restore_path_json"),
        "contributing_source_hashes_json": _json(
            _contributing_source_hashes(taxonomy, rendered)
        ),
        "projection_status": "active",
        "stale_status": "current",
        "stale_reason": None,
        "created_at": now,
        "updated_at": now,
    }


def projection_coverage_report_from_rows(
    conn: sqlite3.Connection,
    rows: list[dict[str, Any]],
    *,
    classification_version: str,
    projection_policy_version: str,
    classified_taxonomy_rows: tuple[dict[str, Any], ...] | None = None,
) -> dict[str, Any]:
    stored_rows = [
        dict(row)
        for row in conn.execute(
            """
            SELECT *
            FROM memory_embedding_projections
            WHERE classification_version = ?
              AND projection_policy_version = ?
            """,
            (classification_version, projection_policy_version),
        ).fetchall()
    ]
    if rows:
        by_id = {row["projection_id"]: row for row in stored_rows}
        for row in rows:
            by_id[row["projection_id"]] = row
        stored_rows = list(by_id.values())
    return _projection_coverage_from_stored_rows(
        conn,
        stored_rows,
        classification_version=classification_version,
        projection_policy_version=projection_policy_version,
        classified_taxonomy_rows=classified_taxonomy_rows,
    )


def _projection_coverage_from_stored_rows(
    conn: sqlite3.Connection,
    rows: list[dict[str, Any]] | tuple[sqlite3.Row, ...],
    *,
    classification_version: str,
    projection_policy_version: str,
    classified_taxonomy_rows: tuple[dict[str, Any], ...] | None = None,
) -> dict[str, Any]:
    row_dicts = [dict(row) for row in rows]
    if classified_taxonomy_rows is None:
        total_classified = int(
            conn.execute(
                """
                SELECT COUNT(*)
                FROM memory_document_taxonomy
                WHERE classification_version = ?
                """,
                (classification_version,),
            ).fetchone()[0]
        )
        eligible_documents = int(
            conn.execute(
                """
                SELECT COUNT(*)
                FROM memory_document_taxonomy
                WHERE classification_version = ?
                  AND embedding_eligible = 1
                """,
                (classification_version,),
            ).fetchone()[0]
        )
        eligible_doc_ids = {
            str(row["doc_id"])
            for row in conn.execute(
                """
                SELECT doc_id
                FROM memory_document_taxonomy
                WHERE classification_version = ?
                  AND embedding_eligible = 1
                """,
                (classification_version,),
            ).fetchall()
        }
    else:
        total_classified = len(classified_taxonomy_rows)
        eligible_doc_ids = {
            str(row["doc_id"])
            for row in classified_taxonomy_rows
            if int(row.get("embedding_eligible") or 0)
        }
        eligible_documents = len(eligible_doc_ids)
    active = [row for row in row_dicts if row["projection_status"] == "active"]
    stale = [row for row in row_dicts if row["stale_status"] != "current"]
    docs_with_projection = {row["doc_id"] for row in active if row["stale_status"] == "current"}
    missing = sorted(eligible_doc_ids - docs_with_projection)
    return {
        "classification_version": classification_version,
        "projection_policy_version": projection_policy_version,
        "total_classified_documents": total_classified,
        "embedding_eligible_documents": eligible_documents,
        "active_projections": len(active),
        "stale_projections": len(stale),
        "by_projection_profile": _count_by(row_dicts, "projection_profile"),
        "by_target_space_id": _count_by(row_dicts, "target_space_id"),
        "by_source_kind": _projection_source_kind_counts(conn, row_dicts),
        "by_ownership_kind": _projection_ownership_counts(conn, row_dicts),
        "by_template_version": _count_by(row_dicts, "text_template_version"),
        "documents_without_required_projection": missing,
        "blocking_issues": ["missing_required_projection_rows"] if missing else [],
    }


def _infer_source_kind(
    doc: sqlite3.Row,
    *,
    metadata: dict[str, Any],
    bookmark: sqlite3.Row | None,
    media: sqlite3.Row | None,
    edge: sqlite3.Row | None,
) -> str:
    doc_type = _value(doc, "doc_type")
    source_subkind = _value(doc, "source_subkind")
    if _is_operational_doc(doc, metadata):
        return "operational_control_artifact"
    if doc_type in {"author_profile"}:
        return "derived_author_profile"
    if doc_type in {"topic_thread", "place_card"}:
        return "derived_topic_event_card"
    if doc_type == "ticker_event":
        return "derived_temporal_event_card"
    if doc_type in {"relation_card"}:
        return "derived_relation_card"
    if doc_type in {"preference_stance_card"}:
        return "derived_preference_stance_card"
    if doc_type in {"external_search_candidate"}:
        return "external_search_candidate"
    if doc_type in {"external_fetch_section", "external_fetch_text"} or _has_external_fetch_fields(
        metadata
    ):
        if _external_fetch_restorable(metadata):
            return "external_fetch_text"
        return "external_search_candidate"
    if doc_type == "media_doc" or media is not None or "media" in source_subkind:
        text_profile = _metadata_text(metadata, "text_profile", "ocr_source", "source_type")
        if "vlm" in text_profile:
            return "x_media_vlm_observation"
        if "ocr" in text_profile:
            return "x_media_ocr_text"
        return "x_media_caption"
    relation = _value(edge, "relation") if edge is not None else ""
    if (
        _metadata_text(metadata, "quoted_tweet_id", "quote_tweet_id")
        or doc_type == "quote_tree_doc"
    ):
        return "x_quote_comment"
    if _metadata_text(metadata, "thread_id"):
        return "x_thread_member"
    if relation == "reply" or _metadata_text(metadata, "replied_to_tweet_id", "reply_to_tweet_id"):
        return "x_reply"
    if (
        bookmark is not None
        or doc_type == "bookmark_doc"
        or _metadata_text(metadata, "collection_kind") == "bookmarks"
    ):
        return "x_bookmarked_tweet"
    if doc_type in {"tweet_doc", "tweet"}:
        return "x_authored_tweet"
    return "unknown"


def _classification_defaults(
    source_kind: str,
    *,
    doc: sqlite3.Row,
    metadata: dict[str, Any],
    bookmark: sqlite3.Row | None,
    media: sqlite3.Row | None,
    edge: sqlite3.Row | None,
) -> dict[str, str]:
    if source_kind == "x_bookmarked_tweet":
        return {
            "ownership_kind": "bookmarked_by_user"
            if _bookmark_owner(bookmark, doc, metadata)
            else "ambiguous_ownership",
            "content_role": "preference_signal",
            "relation_role": "bookmark_target",
            "modality_kind": "text",
            "sensitivity_kind": "account_specific_bookmark",
        }
    if source_kind == "x_reply":
        return _role("authored_by_tracked_account", "reply_context", "reply_child")
    if source_kind == "x_quote_comment":
        return _role("authored_by_tracked_account", "quote_commentary", "quote_comment")
    if source_kind == "x_quoted_source":
        return _role("authored_by_external_account", "quoted_material", "quoted_source")
    if source_kind in {"x_thread_root", "x_thread_member"}:
        return _role(
            "authored_by_tracked_account",
            "thread_context",
            "thread_root" if source_kind == "x_thread_root" else "thread_member",
        )
    if source_kind.startswith("x_media"):
        modality = _media_modality(media, metadata)
        return {
            "ownership_kind": "media_attached_to_restored_source",
            "content_role": "media_text",
            "relation_role": "media_child",
            "modality_kind": modality,
            "sensitivity_kind": "contains_personal_data",
        }
    if source_kind == "external_search_candidate":
        return _role(
            "external_public_reference",
            "external_article_text",
            "external_child",
            modality_kind="webpage",
            sensitivity_kind="external_public",
        )
    if source_kind == "external_fetch_text":
        return _role(
            "external_public_reference",
            "external_article_text",
            "external_child",
            modality_kind="webpage",
            sensitivity_kind="external_public",
        )
    if source_kind.startswith("derived_"):
        content_role = {
            "derived_author_profile": "author_profile_summary",
            "derived_topic_event_card": "topic_summary",
            "derived_relation_card": "relation_summary",
            "derived_preference_stance_card": "preference_signal",
            "derived_temporal_event_card": "temporal_summary",
        }.get(source_kind, "route_hint")
        return _role(
            "derived_from_restored_sources",
            content_role,
            "derived_from_multiple_sources",
            sensitivity_kind="private_account_derived",
        )
    if source_kind == "operational_control_artifact":
        return _role(
            "operational_owned",
            "control_or_review_note",
            "operational",
            sensitivity_kind="operational_not_for_embedding",
        )
    if source_kind == "x_authored_tweet":
        return _role("authored_by_tracked_account", "statement", "standalone")
    return _role("unknown", "unknown", "unknown", sensitivity_kind="unknown")


def _role(
    ownership_kind: str,
    content_role: str,
    relation_role: str,
    *,
    modality_kind: str = "text",
    sensitivity_kind: str = "public_source",
) -> dict[str, str]:
    return {
        "ownership_kind": ownership_kind,
        "content_role": content_role,
        "relation_role": relation_role,
        "modality_kind": modality_kind,
        "sensitivity_kind": sensitivity_kind,
    }


def _embedding_eligibility(
    source_kind: str,
    *,
    sensitivity_kind: str,
    ownership_kind: str,
) -> tuple[bool, str | None]:
    if sensitivity_kind in {
        "secret_or_token_like",
        "operational_not_for_embedding",
        "auth_sensitive",
    }:
        return False, f"sensitivity_kind:{sensitivity_kind}"
    if source_kind in {
        "external_search_candidate",
        "operational_control_artifact",
        "unknown",
        "x_media_attachment",
    }:
        return False, {
            "external_search_candidate": "external_candidate_not_restored",
            "operational_control_artifact": "operational_control_artifact",
            "unknown": "unknown_classification",
            "x_media_attachment": "native_media_requires_media_specific_contract",
        }[source_kind]
    if ownership_kind in {"ambiguous_ownership", "unknown"}:
        return False, f"ownership_kind:{ownership_kind}"
    return True, None


def _answer_support_possible(source_kind: str, embedding_eligible: bool) -> bool:
    if not embedding_eligible:
        return False
    if source_kind.startswith("derived_"):
        return False
    if source_kind in {"x_media_ocr_text", "x_media_caption", "x_media_vlm_observation"}:
        return False
    return source_kind not in {
        "external_search_candidate",
        "operational_control_artifact",
        "unknown",
    }


def _answer_support_block_reason(source_kind: str) -> str:
    if source_kind.startswith("derived_"):
        return "derived_card_requires_underlying_citations"
    if source_kind.startswith("x_media"):
        return "media_text_requires_media_source_context_citation"
    if source_kind == "external_search_candidate":
        return "external_candidate_not_restored"
    if source_kind == "operational_control_artifact":
        return "operational_artifact_not_answer_support"
    return "source_restoration_or_citation_required"


def _review_state(
    source_kind: str,
    *,
    bookmark: sqlite3.Row | None,
    edge: sqlite3.Row | None,
    metadata: dict[str, Any],
) -> tuple[bool, str | None]:
    if source_kind == "x_bookmarked_tweet" and bookmark is None:
        return True, "missing_bookmark_owner"
    if source_kind == "x_reply" and edge is None and not _metadata_text(
        metadata,
        "replied_to_tweet_id",
        "reply_to_tweet_id",
        "parent_tweet_id",
    ):
        return True, "missing_reply_parent_context"
    if source_kind == "unknown":
        return True, "unknown_classification"
    return False, None


def _source_restore_path(
    doc: sqlite3.Row,
    *,
    metadata: dict[str, Any],
    tweet: sqlite3.Row | None,
    bookmark: sqlite3.Row | None,
    media: sqlite3.Row | None,
    edge: sqlite3.Row | None,
    source_doc_hash: str,
    source_kind: str,
) -> dict[str, Any]:
    status = "restorable"
    if source_kind in {"external_search_candidate", "unknown", "operational_control_artifact"}:
        status = "source_not_restored"
    if source_kind == "external_fetch_text" and not _external_fetch_restorable(metadata):
        status = "source_not_restored"
    return {
        "status": status,
        "doc_id": _value(doc, "doc_id"),
        "source_kind": source_kind,
        "source_doc_hash": source_doc_hash,
        "tweet_id": _value(doc, "source_tweet_id") or _metadata_text(metadata, "tweet_id"),
        "tweet_restored": tweet is not None,
        "bookmark_owner_account_id": _bookmark_owner(bookmark, doc, metadata),
        "bookmark_restored": bookmark is not None,
        "edge_relation": _value(edge, "relation") if edge is not None else None,
        "media_id": _media_id(media, metadata),
        "media_hash": _value(media, "content_hash") if media is not None else None,
        "local_path": _value(media, "local_path") if media is not None else None,
        "external_artifact_id": _metadata_text(metadata, "external_artifact_id", "artifact_id"),
        "content_hash": _metadata_text(metadata, "content_hash", "response_hash"),
        "text_hash": _metadata_text(metadata, "text_hash", "extracted_text_hash"),
        "not_evidence": True,
    }


def _filter_exclusion_reason(
    tax: dict[str, Any],
    *,
    intent: str,
    author_id: str | None,
    bookmark_owner_account_id: str | None,
    source_kind: str | None,
    ownership_kind: str | None,
    content_role: str | None,
    relation_role: str | None,
    language: str | None,
    modality_kind: str | None,
    sensitivity_kind: str | None,
    require_projections: bool,
    has_projection: bool,
) -> str | None:
    if not tax:
        return "missing_taxonomy"
    if tax.get("source_kind") in {"external_search_candidate", "operational_control_artifact"}:
        return f"excluded_source_kind:{tax.get('source_kind')}"
    if tax.get("sensitivity_kind") in {"secret_or_token_like", "operational_not_for_embedding"}:
        return f"excluded_sensitivity_kind:{tax.get('sensitivity_kind')}"
    requested = {
        "source_kind": source_kind,
        "ownership_kind": ownership_kind,
        "content_role": content_role,
        "relation_role": relation_role,
        "language": language,
        "modality_kind": modality_kind,
        "sensitivity_kind": sensitivity_kind,
    }
    for key, value in requested.items():
        if value and tax.get(key) != value:
            return f"{key}_mismatch"
    if author_id and tax.get("author_id") != author_id:
        return "author_id_mismatch"
    if (
        bookmark_owner_account_id
        and tax.get("bookmark_owner_account_id") != bookmark_owner_account_id
    ):
        return "bookmark_owner_account_id_mismatch"
    if require_projections and not has_projection:
        return "missing_required_projection"
    rule = _filter_rules().get(intent, {})
    allowed_source = set(rule.get("source_kind", []))
    allowed_owner = set(rule.get("ownership_kind", []))
    allowed_relation = set(rule.get("relation_role", []))
    if allowed_source and tax.get("source_kind") not in allowed_source:
        return f"intent_source_kind_excluded:{tax.get('source_kind')}"
    if allowed_owner and tax.get("ownership_kind") not in allowed_owner:
        return f"intent_ownership_kind_excluded:{tax.get('ownership_kind')}"
    if allowed_relation and tax.get("relation_role") not in allowed_relation:
        return f"intent_relation_role_excluded:{tax.get('relation_role')}"
    return None


def _result_with_taxonomy(result: Any, tax: dict[str, Any]) -> Any:
    metadata = dict(result.metadata)
    metadata["embedding_input_taxonomy"] = {
        key: tax.get(key)
        for key in (
            "source_kind",
            "ownership_kind",
            "content_role",
            "relation_role",
            "modality_kind",
            "temporal_scope",
            "sensitivity_kind",
            "language",
            "author_id",
            "bookmark_owner_account_id",
            "tweet_id",
            "conversation_id",
            "quoted_tweet_id",
            "media_id",
            "external_artifact_id",
            "source_doc_hash",
            "source_bundle_id",
        )
    }
    return replace(result, metadata=metadata)


def _result_with_filter_explanation(result: Any, explanation: dict[str, Any]) -> Any:
    metadata = dict(result.metadata)
    metadata["embedding_filter_explanation"] = explanation
    return replace(result, metadata=metadata)


def _latest_taxonomy_by_doc_id(
    db_path: str | Path,
    doc_ids: tuple[str, ...],
) -> dict[str, dict[str, Any]]:
    if not doc_ids:
        return {}
    path = Path(db_path)
    placeholders = ",".join("?" for _ in doc_ids)
    with sqlite3.connect(path, timeout=60) as conn:
        conn.row_factory = sqlite3.Row
        ensure_memory_schema(conn)
        rows = conn.execute(
            f"""
            SELECT *
            FROM memory_document_taxonomy
            WHERE doc_id IN ({placeholders})
            ORDER BY classification_version DESC, updated_at DESC
            """,
            doc_ids,
        ).fetchall()
    out: dict[str, dict[str, Any]] = {}
    for row in rows:
        out.setdefault(str(row["doc_id"]), dict(row))
    return out


def _projection_doc_ids(
    db_path: str | Path,
    doc_ids: tuple[str, ...],
    *,
    projection_profile: str | None,
    space_id: str | None,
) -> set[str]:
    if not doc_ids:
        return set()
    filters = ["doc_id IN (" + ",".join("?" for _ in doc_ids) + ")"]
    params: list[Any] = list(doc_ids)
    if projection_profile:
        filters.append("projection_profile = ?")
        params.append(projection_profile)
    if space_id:
        filters.append("target_space_id = ?")
        params.append(space_id)
    filters.append("projection_status = 'active'")
    filters.append("stale_status = 'current'")
    with sqlite3.connect(db_path, timeout=60) as conn:
        ensure_memory_schema(conn)
        rows = conn.execute(
            f"""
            SELECT DISTINCT doc_id
            FROM memory_embedding_projections
            WHERE {" AND ".join(filters)}
            """,
            params,
        ).fetchall()
    return {str(row[0]) for row in rows}


def _filter_rules() -> dict[str, dict[str, Any]]:
    return {
        "what_did_user_say": {
            "ownership_kind": ["authored_by_tracked_account"],
            "source_kind": [
                "x_authored_tweet",
                "x_reply",
                "x_quote_comment",
                "x_thread_root",
                "x_thread_member",
            ],
            "exclude_source_kind": ["x_bookmarked_tweet"],
        },
        "what_did_user_bookmark": {
            "ownership_kind": ["bookmarked_by_user", "bookmarked_by_tracked_account"],
            "relation_role": ["bookmark_target", "bookmark_relation"],
        },
        "bookmark_interest": {
            "ownership_kind": ["bookmarked_by_user", "bookmarked_by_tracked_account"],
            "relation_role": ["bookmark_target", "bookmark_relation"],
        },
        "who_said": {
            "source_kind": [
                "x_authored_tweet",
                "x_reply",
                "x_quote_comment",
                "x_thread_root",
                "x_thread_member",
            ],
        },
        "author_history": {
            "source_kind": [
                "x_authored_tweet",
                "x_reply",
                "x_quote_comment",
                "x_thread_root",
                "x_thread_member",
            ],
        },
        "reply_or_conversation_context": {
            "relation_role": [
                "reply_child",
                "reply_parent_context",
                "thread_root",
                "thread_member",
            ],
        },
        "quote_relation_recall": {
            "relation_role": ["quote_comment", "quoted_source"],
        },
        "media_content_recall": {
            "source_kind": ["x_media_ocr_text", "x_media_caption", "x_media_vlm_observation"],
        },
        "external_context_recall": {"source_kind": ["external_fetch_text"]},
    }


def _answer_wording_constraints() -> dict[str, list[str]]:
    return {
        "what_did_user_bookmark": [
            "Use bookmarked, saved, collected, or showed interest in.",
            "Do not use believed, claimed, agreed, or said without authored evidence.",
        ],
        "bookmark_interest": [
            "Bookmark interest alone is not endorsement.",
        ],
        "preference_or_stance": [
            "Bookmark-interest-only evidence must be weak wording or needs_review.",
        ],
    }


def _source_to_projection_matrix() -> dict[str, dict[str, list[str]]]:
    return {
        "x_authored_tweet": {
            "required": ["general_memory"],
            "conditional": [
                "authored_stance",
                "relation_context",
                "temporal_event",
                "code_technical",
            ],
            "prohibited": ["bookmark_interest unless bookmark relation also exists"],
        },
        "x_bookmarked_tweet": {
            "required": ["general_memory", "bookmark_interest"],
            "conditional": ["preference_stance", "temporal_event", "code_technical"],
            "prohibited": ["authored_stance as user's stance"],
        },
        "x_reply": {
            "required": ["general_memory", "relation_context"],
            "conditional": ["temporal_event", "code_technical"],
            "prohibited": ["preference_stance unless explicit stance"],
        },
        "x_quote_comment": {
            "required": ["general_memory", "relation_context"],
            "conditional": ["authored_stance", "temporal_event", "code_technical"],
            "prohibited": ["merge with quoted_source"],
        },
        "x_quoted_source": {
            "required": ["relation_context"],
            "conditional": ["general_memory", "temporal_event", "code_technical"],
            "prohibited": ["authored_stance for quoting author"],
        },
        "x_media_attachment": {
            "required": [],
            "conditional": ["media_text_bridge only if text exists"],
            "prohibited": ["raw text embedding of binary metadata as evidence"],
        },
        "external_search_candidate": {
            "required": [],
            "conditional": [],
            "prohibited": ["all production embedding projections"],
        },
        "external_fetch_text": {
            "required": ["external_fetch_text"],
            "conditional": ["general_memory", "temporal_event", "code_technical"],
            "prohibited": ["citation-ready projection"],
        },
        "operational_control_artifact": {
            "required": [],
            "conditional": ["operational index only if separate"],
            "prohibited": ["user-memory embedding"],
        },
    }


def _policy(
    template_version: str,
    projection_profile: str,
    source_kinds: tuple[str, ...],
    template_body: str,
    *,
    evidence_role: str = "candidate_only",
) -> TemplatePolicy:
    return TemplatePolicy(
        template_version=template_version,
        projection_profile=projection_profile,
        target_space_id=PROFILE_TARGET_SPACE[projection_profile],
        source_kind_allowlist=source_kinds,
        ownership_allowlist=OWNERSHIP_KINDS,
        content_role_allowlist=CONTENT_ROLES,
        template_body=template_body,
        max_input_chars=3600,
        field_policy={
            "include": [
                "source labels",
                "authorship",
                "bookmark owner",
                "relation role",
                "restore path",
                "body text",
            ],
            "exclude": [
                "cookies",
                "session state",
                "provider raw request",
                "provider raw response",
                "secret values",
            ],
        },
        evidence_role=evidence_role,
    )


def _write_taxonomy_reports(report: dict[str, Any], *, report_dir: Path) -> None:
    _ensure_report_dir(report_dir)
    _write_json(report_dir / "embedding_input_taxonomy.json", report)
    lines = [
        "# Embedding Input Taxonomy",
        "",
        f"classification_version: {report['classification_version']}",
        f"total_documents_seen: {report['total_documents_seen']}",
        f"embedding_eligible_documents: {report['embedding_eligible_documents']}",
        f"excluded_documents: {report['excluded_documents']}",
        f"needs_review_documents: {report['needs_review_documents']}",
        f"unknown_documents: {report['unknown_documents']}",
        "",
        "## Blocking Issues",
        "",
        *[f"- {item}" for item in report["blocking_issues"]],
    ]
    _write_text(report_dir / "embedding_input_taxonomy.md", "\n".join(lines).rstrip() + "\n")


def _write_projection_policy_reports(report: dict[str, Any], *, report_dir: Path) -> None:
    _ensure_report_dir(report_dir)
    _write_json(report_dir / "embedding_projection_policy.json", report)
    lines = [
        "# Embedding Projection Policy",
        "",
        f"policy_version: {report['policy_version']}",
        f"projection_policy_version: {report['projection_policy_version']}",
        f"template_count: {report['template_count']}",
        "",
        "## Templates",
        "",
    ]
    for template in report["templates"]:
        lines.append(f"- {template['template_version']} -> {template['projection_profile']}")
    _write_text(report_dir / "embedding_projection_policy.md", "\n".join(lines).rstrip() + "\n")


def _write_projection_coverage_reports(
    report: dict[str, Any],
    projections: list[dict[str, Any]],
    *,
    report_dir: Path,
) -> None:
    _ensure_report_dir(report_dir)
    _write_json(report_dir / "embedding_projection_coverage.json", report)
    example_path = report_dir / "embedding_projection_examples.jsonl"
    with example_path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in projections[:100]:
            handle.write(_json(row) + "\n")


def _write_examples_jsonl(examples: list[dict[str, Any]], *, report_dir: Path) -> None:
    _ensure_report_dir(report_dir)
    with (report_dir / "embedding_projection_examples.jsonl").open(
        "w",
        encoding="utf-8",
        newline="\n",
    ) as handle:
        for example in examples:
            handle.write(_json(example) + "\n")


def _write_metadata_filter_reports(report: dict[str, Any], *, report_dir: Path) -> None:
    _ensure_report_dir(report_dir)
    _write_json(report_dir / "embedding_metadata_filter_policy.json", report)
    lines = [
        "# Embedding Metadata Filter Policy",
        "",
        f"policy_version: {report['policy_version']}",
        "",
        "## Intent Classes",
        "",
        *[f"- {intent}" for intent in report["intent_classes"]],
        "",
        "## Not Evidence Rules",
        "",
        *[f"- {rule}" for rule in report["not_evidence_rules"]],
    ]
    _write_text(
        report_dir / "embedding_metadata_filter_policy.md",
        "\n".join(lines).rstrip() + "\n",
    )


def _write_readiness_report(report: dict[str, Any], *, report_dir: Path) -> None:
    _ensure_report_dir(report_dir)
    lines = ["# Embedding Full Run Readiness", "", f"status: {report['status']}", ""]
    for key, value in report["answers"].items():
        lines.append(f"- {key}: {value}")
    if report["blocking_issues"]:
        lines.extend(["", "## Blocking Issues", ""])
        lines.extend(f"- {item}" for item in report["blocking_issues"])
    _write_text(report_dir / "embedding_full_run_readiness.md", "\n".join(lines).rstrip() + "\n")


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(_json(payload) + "\n", encoding="utf-8", newline="\n")


def _write_text(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8", newline="\n")


def _ensure_report_dir(report_dir: Path) -> None:
    report_dir.mkdir(parents=True, exist_ok=True)


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True)


def _stable_id(*parts: object) -> str:
    return text_hash("\0".join(str(part) for part in parts))[:32]


def _utc_now() -> str:
    return datetime.now(tz=UTC).isoformat()


def _value(row: Any, key: str) -> str:
    if row is None:
        return ""
    try:
        value = row.get(key) if isinstance(row, dict) else row[key]
    except (KeyError, IndexError):
        value = None
    return str(value or "").strip()


def _metadata(row: Any) -> dict[str, Any]:
    raw = _value(row, "metadata_json")
    if not raw:
        return {}
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _metadata_text(metadata: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = metadata.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def _metadata_subset(metadata: dict[str, Any]) -> dict[str, Any]:
    allowed = (
        "url",
        "role",
        "collection_kind",
        "labels",
        "type",
        "download_status",
        "media_id",
        "thread_id",
        "conversation_id",
        "quoted_tweet_id",
        "content_hash",
        "text_hash",
        "storage_rights",
        "prompt_injection_review_state",
    )
    return {key: metadata[key] for key in allowed if metadata.get(key)}


def _explicit_source_kind(doc: sqlite3.Row, metadata: dict[str, Any]) -> str | None:
    for value in (
        _metadata_text(metadata, "embedding_source_kind", "taxonomy_source_kind"),
        _value(doc, "source_kind"),
    ):
        if value in SOURCE_KINDS:
            return value
    return None


def _is_operational_doc(doc: sqlite3.Row, metadata: dict[str, Any]) -> bool:
    text = " ".join(
        (
            _value(doc, "doc_type"),
            _value(doc, "source_kind"),
            _value(doc, "source_subkind"),
            _metadata_text(metadata, "artifact_kind", "source_kind", "type"),
        )
    ).casefold()
    return any(
        marker in text
        for marker in (
            "operational",
            "control_artifact",
            "review_artifact",
            "wbs",
            "route_memory",
            "prompt_contract",
            "handoff",
        )
    )


def _has_external_fetch_fields(metadata: dict[str, Any]) -> bool:
    return any(
        metadata.get(key)
        for key in (
            "requested_url",
            "final_url",
            "fetched_at",
            "content_hash",
            "text_hash",
            "extracted_text_hash",
        )
    )


def _external_fetch_restorable(metadata: dict[str, Any]) -> bool:
    content_hash = _metadata_text(metadata, "content_hash", "response_hash")
    text_hash_value = _metadata_text(metadata, "text_hash", "extracted_text_hash")
    fetched_at = _metadata_text(metadata, "fetched_at", "retrieved_at")
    storage_rights = _metadata_text(metadata, "storage_rights")
    review = _metadata_text(
        metadata,
        "prompt_injection_review_state",
        "prompt_injection_status",
    )
    return bool(
        content_hash
        and text_hash_value
        and fetched_at
        and storage_rights
        and review not in {"blocking", "review_required"}
    )


def _tweet_row(conn: sqlite3.Connection, tweet_id: str) -> sqlite3.Row | None:
    if not tweet_id or not _table_exists(conn, "tweets"):
        return None
    return conn.execute("SELECT * FROM tweets WHERE tweet_id = ?", (tweet_id,)).fetchone()


def _bookmark_row(
    conn: sqlite3.Connection,
    tweet_id: str,
    *,
    account_id: str,
) -> sqlite3.Row | None:
    if not tweet_id or not _table_exists(conn, "account_bookmarks"):
        return None
    if account_id:
        row = conn.execute(
            """
            SELECT *
            FROM account_bookmarks
            WHERE tweet_id = ? AND account_id = ?
            ORDER BY observed_at DESC
            LIMIT 1
            """,
            (tweet_id, account_id),
        ).fetchone()
        if row is not None:
            return row
    return conn.execute(
        """
        SELECT *
        FROM account_bookmarks
        WHERE tweet_id = ?
        ORDER BY observed_at DESC
        LIMIT 1
        """,
        (tweet_id,),
    ).fetchone()


def _edge_row(conn: sqlite3.Connection, tweet_id: str) -> sqlite3.Row | None:
    if not tweet_id or not _table_exists(conn, "tweet_edges"):
        return None
    return conn.execute(
        """
        SELECT *
        FROM tweet_edges
        WHERE child_tweet_id = ? OR parent_tweet_id = ?
        ORDER BY relation
        LIMIT 1
        """,
        (tweet_id, tweet_id),
    ).fetchone()


def _media_row(
    conn: sqlite3.Connection,
    *,
    metadata: dict[str, Any],
    tweet_id: str,
) -> sqlite3.Row | None:
    if not _table_exists(conn, "media"):
        return None
    media_id = _metadata_text(metadata, "media_id")
    if media_id:
        row = conn.execute("SELECT * FROM media WHERE media_id = ?", (media_id,)).fetchone()
        if row is not None:
            return row
    if tweet_id:
        return conn.execute(
            "SELECT * FROM media WHERE tweet_id = ? ORDER BY media_id LIMIT 1",
            (tweet_id,),
        ).fetchone()
    return None


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    return (
        conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
            (table,),
        ).fetchone()
        is not None
    )


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def _author_id(
    doc: sqlite3.Row,
    *,
    tweet: sqlite3.Row | None,
    metadata: dict[str, Any],
) -> str:
    return (
        _metadata_text(metadata, "author_id", "author_screen_name", "author")
        or _value(tweet, "author_screen_name")
        or _value(doc, "author_screen_name")
    )


def _bookmark_owner(
    bookmark: sqlite3.Row | None,
    doc: sqlite3.Row,
    metadata: dict[str, Any],
) -> str:
    return (
        _value(bookmark, "account_id")
        or _metadata_text(metadata, "bookmark_owner_account_id", "viewer_account_id")
        or (_value(doc, "account_id") if _value(doc, "doc_type") == "bookmark_doc" else "")
    )


def _bookmark_run(bookmark: sqlite3.Row | None, metadata: dict[str, Any]) -> str:
    return _value(bookmark, "run_id") or _metadata_text(metadata, "collection_run_id", "run_id")


def _reply_parent(edge: sqlite3.Row | None, metadata: dict[str, Any]) -> str:
    return (
        _metadata_text(metadata, "replied_to_tweet_id", "reply_to_tweet_id", "parent_tweet_id")
        or (_value(edge, "parent_tweet_id") if _value(edge, "relation") == "reply" else "")
    )


def _media_id(media: sqlite3.Row | None, metadata: dict[str, Any]) -> str:
    return _metadata_text(metadata, "media_id") or _value(media, "media_id")


def _media_modality(media: sqlite3.Row | None, metadata: dict[str, Any]) -> str:
    value = (_metadata_text(metadata, "modality", "media_type") or _value(media, "type")).lower()
    if value in {"photo", "image", "jpg", "jpeg", "png", "gif"}:
        return "image"
    if value in {"video", "mp4"}:
        return "video"
    if value in {"audio", "mp3", "wav"}:
        return "audio"
    if value == "pdf":
        return "pdf"
    return "mixed_media" if value else "text"


def _created_at_source(
    doc: sqlite3.Row,
    *,
    tweet: sqlite3.Row | None,
    metadata: dict[str, Any],
) -> str:
    return (
        _metadata_text(metadata, "created_at_source", "created_at")
        or _value(tweet, "created_at")
        or _value(doc, "created_at")
    )


def _temporal_scope(
    doc: sqlite3.Row,
    *,
    metadata: dict[str, Any],
    source_kind: str,
) -> str:
    if source_kind.startswith("derived_") and "temporal" in source_kind:
        return "derived_current_profile"
    if _metadata_text(metadata, "event_at", "event_window", "valid_until"):
        return "event_window"
    if DATE_RE.search(_value(doc, "body")) or _value(doc, "created_at"):
        return "point_in_time"
    return "unknown"


def _has_temporal_signal(taxonomy: dict[str, Any] | sqlite3.Row) -> bool:
    return _value(taxonomy, "temporal_scope") in {
        "point_in_time",
        "event_window",
        "rapidly_stale",
        "derived_current_profile",
    }


def _float_or_none(value: Any) -> float | None:
    if value in {None, ""}:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _restore_path(row: dict[str, Any]) -> dict[str, Any]:
    try:
        payload = json.loads(str(row.get("source_restore_path_json") or "{}"))
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _source_label(template_version: str) -> str:
    return {
        "authored_tweet.embedding.v1": "X authored tweet",
        "bookmarked_tweet.embedding.v1": "X bookmarked tweet",
        "reply.embedding.v1": "X reply",
        "quote_comment.embedding.v1": "X quote tweet comment",
        "quoted_source.embedding.v1": "Quoted X source",
        "thread_context.embedding.v1": "X thread context",
        "media_text_bridge.embedding.v1": "Media-derived text",
        "external_fetch_text.embedding.v1": "External fetched text",
        "derived_author_profile.embedding.v1": "Derived author profile",
        "derived_topic_event_card.embedding.v1": "Derived topic/event card",
        "relation_context.embedding.v1": "Relation context projection",
        "preference_stance_candidate.embedding.v1": "Preference or stance candidate",
        "code_technical.embedding.v1": "Technical/code-related memory",
    }.get(template_version, template_version)


def _embedding_note(template_version: str, source_kind: str) -> str:
    if template_version == "bookmarked_tweet.embedding.v1":
        return (
            "Saved/reference material only; do not use as belief without separate "
            "authored stance evidence."
        )
    if source_kind.startswith("derived_"):
        return "Derived route/search surface only; answers cite underlying restored sources."
    if source_kind.startswith("x_media"):
        return "Media-derived candidate text; citation requires media source restoration."
    if source_kind.startswith("external"):
        return "External candidate text; citation requires fetch artifact restoration."
    return "Retrieval candidate until restored to source bundle and citation-validated."


def _contributing_source_hashes(
    taxonomy: dict[str, Any] | sqlite3.Row,
    rendered: dict[str, Any],
) -> tuple[str, ...]:
    source_hash = _value(taxonomy, "source_doc_hash")
    if not source_hash:
        return ()
    return (source_hash,)


def _redact(text: str) -> str:
    return SECRET_RE.sub(lambda match: f"{match.group(1)}=[REDACTED]", text)


def _rough_tokens(text: str) -> int:
    return max(1, (len(text) + 3) // 4)


def _count_by(rows: list[dict[str, Any]], key: str) -> dict[str, int]:
    return dict(sorted(Counter(str(row.get(key) or "") for row in rows).items()))


def _projection_source_kind_counts(
    conn: sqlite3.Connection,
    rows: list[dict[str, Any]],
) -> dict[str, int]:
    return _projection_taxonomy_counts(conn, rows, "source_kind")


def _projection_ownership_counts(
    conn: sqlite3.Connection,
    rows: list[dict[str, Any]],
) -> dict[str, int]:
    return _projection_taxonomy_counts(conn, rows, "ownership_kind")


def _projection_taxonomy_counts(
    conn: sqlite3.Connection,
    rows: list[dict[str, Any]],
    key: str,
) -> dict[str, int]:
    if not rows:
        return {}
    doc_ids = tuple(sorted({str(row["doc_id"]) for row in rows}))
    taxonomy: dict[str, str] = {}
    for chunk in _chunks(doc_ids, 500):
        placeholders = ",".join("?" for _ in chunk)
        taxonomy.update(
            {
                str(row["doc_id"]): str(row[key])
                for row in conn.execute(
                    f"""
                    SELECT doc_id, {key}
                    FROM memory_document_taxonomy
                    WHERE doc_id IN ({placeholders})
                    """,
                    chunk,
                ).fetchall()
            }
        )
    return dict(sorted(Counter(taxonomy.get(str(row["doc_id"]), "") for row in rows).items()))


def _chunks(values: tuple[str, ...], size: int) -> tuple[tuple[str, ...], ...]:
    return tuple(
        values[index : index + size]
        for index in range(0, len(values), max(1, size))
    )


def _report_exists(report_dir: Path, filename: str) -> bool:
    return (report_dir / filename).exists()


def _stores_control_artifacts(value: str | PersistenceMode) -> bool:
    return normalize_persistence_mode(value).stores_artifacts
