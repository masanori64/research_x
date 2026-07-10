from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from research_x.memory.embedding_input import (
    DEFAULT_CLASSIFICATION_VERSION,
    DEFAULT_PROJECTION_POLICY_VERSION,
    PROFILE_TARGET_SPACE,
    build_embedding_projections,
    classify_embedding_inputs,
    write_default_template_policies,
)
from research_x.memory.embedding_spaces import (
    FINAL_EMBEDDING_SPACE_DEFINITIONS,
    FINAL_EMBEDDING_SPACE_IDS,
    EmbeddingSpaceDefinition,
    plan_embedding_spaces,
)
from research_x.memory.embeddings import estimate_memory_embedding_build
from research_x.memory.media_embeddings import estimate_media_embedding_build

REAL_API_ARTIFACT_SCHEMA_VERSION = 1
DEFAULT_REAL_API_OUTPUT_ROOT = Path("runs") / "real_api"
DEFAULT_REAL_API_SELECTION_POLICY = "all-eligible"


@dataclass(frozen=True)
class RealApiEstimateArtifactsResult:
    run_id: str
    run_dir: str
    final_space_ids: tuple[str, ...]
    artifact_paths: tuple[str, ...]
    provider_requests_made: int

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def write_offline_estimate_artifacts(
    db_path: str | Path,
    *,
    run_id: str | None = None,
    output_root: str | Path = DEFAULT_REAL_API_OUTPUT_ROOT,
    space_ids: tuple[str, ...] | list[str] | None = None,
    batch_size: int = 64,
    limit: int | None = None,
    execution_stage: str = "auto",
    selection_policy: str = DEFAULT_REAL_API_SELECTION_POLICY,
    rebuild: bool = False,
    price_per_million_input_tokens: float | None = None,
    max_file_bytes: int = 20 * 1024 * 1024,
    mime_types: tuple[str, ...] | list[str] = (),
) -> RealApiEstimateArtifactsResult:
    """Write provider-free real API estimate artifacts.

    The estimates reuse existing local estimate functions only. This function
    never calls embedding, media embedding, budget, HTTP, or provider transports.
    """

    db = Path(db_path)
    resolved_run_id = _safe_run_id(run_id or _default_run_id())
    run_dir = Path(output_root) / resolved_run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    requested_policy = selection_policy
    resolved_selection_policy = resolve_real_api_selection_policy_alias(selection_policy)
    definitions = _select_final_space_definitions(space_ids)
    generated_at = _utc_now()
    projection_report_dir = run_dir / "embedding_input_reports"
    _prepare_text_projection_inputs(db, definitions=definitions, report_dir=projection_report_dir)

    base_context = {
        "schema_version": REAL_API_ARTIFACT_SCHEMA_VERSION,
        "run_id": resolved_run_id,
        "generated_at": generated_at,
        "stage": "offline_estimate",
        "db_path": str(db),
        "not_evidence": True,
        "provider_execution": _provider_execution_block(),
    }

    estimate_records: list[dict[str, Any]] = []
    for definition in definitions:
        estimate_records.append(
            _write_embedding_estimate_artifact(
                db,
                run_dir=run_dir,
                definition=definition,
                base_context=base_context,
                batch_size=batch_size,
                limit=limit,
                execution_stage=execution_stage,
                requested_selection_policy=requested_policy,
                resolved_selection_policy=resolved_selection_policy,
                rebuild=rebuild,
                price_per_million_input_tokens=price_per_million_input_tokens,
                max_file_bytes=max_file_bytes,
                mime_types=tuple(mime_types),
            )
        )

    plan_report = plan_embedding_spaces(db)
    plan_path = run_dir / "embedding_space_plan.json"
    plan_payload = {
        **base_context,
        "artifact_kind": "embedding_space_plan",
        "plan_status": plan_report.status,
        "final_space_count": plan_report.final_space_count,
        "registered_space_count": plan_report.registered_space_count,
        "missing_final_space_ids": list(plan_report.missing_final_space_ids),
        "selection_policy": {
            "requested": requested_policy,
            "resolved": resolved_selection_policy,
        },
        "final_spaces": [
            _space_plan_row(definition, estimate_records)
            for definition in FINAL_EMBEDDING_SPACE_DEFINITIONS
        ],
    }
    _write_json(plan_path, plan_payload)

    manifest_path = run_dir / "run_manifest.json"
    artifact_paths = tuple(
        str(path)
        for path in (
            manifest_path,
            plan_path,
            *(run_dir / record["artifact_path"] for record in estimate_records),
        )
    )
    manifest_payload = {
        **base_context,
        "artifact_kind": "run_manifest",
        "run_dir": str(run_dir),
        "layout": "runs/real_api/<run_id>/",
        "selected_final_space_ids": [definition.space_id for definition in definitions],
        "all_final_space_ids": list(FINAL_EMBEDDING_SPACE_IDS),
        "artifact_files": [
            _artifact_file_record(path, run_dir=run_dir)
            for path in (plan_path, *(run_dir / r["artifact_path"] for r in estimate_records))
        ],
        "provider_requests_made": 0,
    }
    _write_json(manifest_path, manifest_payload)

    return RealApiEstimateArtifactsResult(
        run_id=resolved_run_id,
        run_dir=str(run_dir),
        final_space_ids=tuple(definition.space_id for definition in definitions),
        artifact_paths=artifact_paths,
        provider_requests_made=0,
    )


def resolve_real_api_selection_policy_alias(policy: str | None) -> str:
    normalized = _clean_policy(policy)
    aliases = {
        "all_eligible": "sequential",
        "representative": "doc_type_round_robin",
        "doc_type_round_robin": "doc_type_round_robin",
        "sequential": "sequential",
        "auto": "auto",
    }
    if normalized not in aliases:
        raise ValueError(
            "real API estimate selection policy must be one of: "
            "auto, sequential, doc-type-round-robin, representative, all-eligible"
        )
    return aliases[normalized]


def real_api_estimate_artifacts_json(result: RealApiEstimateArtifactsResult) -> str:
    return json.dumps(result.as_dict(), ensure_ascii=False, indent=2, sort_keys=True)


def format_real_api_estimate_artifacts(result: RealApiEstimateArtifactsResult) -> str:
    return "\n".join(
        (
            f"real-api-estimate-artifacts: {result.run_dir}",
            f"run_id: {result.run_id}",
            f"final_spaces: {len(result.final_space_ids)}",
            f"artifacts: {len(result.artifact_paths)}",
            f"provider_requests_made: {result.provider_requests_made}",
        )
    )


def _write_embedding_estimate_artifact(
    db_path: Path,
    *,
    run_dir: Path,
    definition: EmbeddingSpaceDefinition,
    base_context: dict[str, Any],
    batch_size: int,
    limit: int | None,
    execution_stage: str,
    requested_selection_policy: str,
    resolved_selection_policy: str,
    rebuild: bool,
    price_per_million_input_tokens: float | None,
    max_file_bytes: int,
    mime_types: tuple[str, ...],
) -> dict[str, Any]:
    artifact_name = f"embedding_estimate_{_artifact_slug(definition.space_id)}.json"
    estimate_kind = (
        "media_embedding"
        if definition.modality == "media" or definition.provider_role == "media_embedding"
        else "text_embedding"
    )
    if estimate_kind == "media_embedding":
        estimate = estimate_media_embedding_build(
            db_path,
            provider=definition.provider,
            model=definition.model,
            dimensions=definition.dimensions,
            embedding_profile=definition.embedding_profile,
            input_template_version=definition.text_template_version,
            limit=limit,
            rebuild=rebuild,
            max_file_bytes=max_file_bytes,
            mime_types=mime_types,
        )
    else:
        projection_kwargs = _projection_estimate_kwargs(definition)
        estimate = estimate_memory_embedding_build(
            db_path,
            space_id=definition.space_id,
            provider=definition.provider,
            model=definition.model,
            dimensions=definition.dimensions,
            embedding_profile=definition.embedding_profile,
            text_template_version=definition.text_template_version,
            batch_size=batch_size,
            limit=limit,
            rebuild=rebuild,
            price_per_million_input_tokens=price_per_million_input_tokens,
            execution_stage=execution_stage,
            selection_policy=resolved_selection_policy,
            **projection_kwargs,
        )

    estimate_dict = asdict(estimate)
    payload = {
        **base_context,
        "artifact_kind": "embedding_estimate",
        "estimate_kind": estimate_kind,
        "space_id": definition.space_id,
        "final_space": asdict(definition),
        "selection_policy": {
            "requested": requested_selection_policy,
            "resolved": resolved_selection_policy,
            "applies_to_media": estimate_kind == "text_embedding",
        },
        "estimate": estimate_dict,
    }
    _write_json(run_dir / artifact_name, payload)
    return {
        "space_id": definition.space_id,
        "artifact_path": artifact_name,
        "estimate_kind": estimate_kind,
        "estimate_summary": _estimate_summary(estimate_dict, estimate_kind=estimate_kind),
    }


def _space_plan_row(
    definition: EmbeddingSpaceDefinition,
    estimate_records: list[dict[str, Any]],
) -> dict[str, Any]:
    estimate_record = next(
        (record for record in estimate_records if record["space_id"] == definition.space_id),
        None,
    )
    estimate_status = "written" if estimate_record else "not_requested"
    return {
        **asdict(definition),
        "estimate": {
            "status": estimate_status,
            "artifact_path": estimate_record["artifact_path"] if estimate_record else None,
            "summary": estimate_record["estimate_summary"] if estimate_record else None,
        },
        "authorization": {
            "status": "not_authorized",
            "provider_requests_allowed": False,
            "budget_guard_required_before_real_call": True,
            "wip_report_required_before_first_paid_or_quota_call": True,
        },
        "coverage": {
            "status": "offline_estimate_only",
            "full_selected_scope_required_before_promotion": True,
            "coverage_artifact_required_after_build": True,
        },
        "promotion": {
            "status": "not_promoted",
            "reason": "estimate_artifact_only",
            "required_gate": "source_bundle_context_citation_required",
        },
    }


def _prepare_text_projection_inputs(
    db_path: Path,
    *,
    definitions: tuple[EmbeddingSpaceDefinition, ...],
    report_dir: Path,
) -> None:
    if not any(_definition_requires_projection_estimate(definition) for definition in definitions):
        return
    classify_embedding_inputs(
        db_path,
        write=True,
        report_dir=report_dir,
        persistence="artifacts",
    )
    write_default_template_policies(
        db_path,
        report_dir=report_dir,
        persistence="artifacts",
    )
    build_embedding_projections(
        db_path,
        write=True,
        report_dir=report_dir,
        persistence="artifacts",
    )


def _projection_estimate_kwargs(definition: EmbeddingSpaceDefinition) -> dict[str, Any]:
    if not _definition_requires_projection_estimate(definition):
        return {}
    return {
        "projection_profile": definition.embedding_profile,
        "classification_version": DEFAULT_CLASSIFICATION_VERSION,
        "projection_policy_version": DEFAULT_PROJECTION_POLICY_VERSION,
        "require_projections": True,
    }


def _definition_requires_projection_estimate(definition: EmbeddingSpaceDefinition) -> bool:
    return (
        definition.provider_role == "text_embedding"
        and definition.modality == "text"
        and definition.embedding_profile in PROFILE_TARGET_SPACE
    )


def _estimate_summary(estimate: dict[str, Any], *, estimate_kind: str) -> dict[str, Any]:
    if estimate_kind == "media_embedding":
        return {
            "media": estimate.get("media"),
            "selected": estimate.get("selected"),
            "current": estimate.get("current"),
            "missing": estimate.get("missing"),
            "stale_file": estimate.get("stale_file"),
            "stale_metadata": estimate.get("stale_metadata"),
            "skipped": estimate.get("skipped"),
            "estimated_api_calls": estimate.get("estimated_api_calls"),
            "estimated_input_bytes": estimate.get("estimated_input_bytes"),
        }
    return {
        "documents": estimate.get("documents"),
        "selected": estimate.get("selected"),
        "eligible": estimate.get("eligible"),
        "ineligible": estimate.get("ineligible"),
        "missing": estimate.get("missing"),
        "stale_text": estimate.get("stale_text"),
        "stale_source": estimate.get("stale_source"),
        "current": estimate.get("current"),
        "estimated_batches": estimate.get("estimated_batches"),
        "estimated_input_tokens": estimate.get("estimated_input_tokens"),
    }


def _select_final_space_definitions(
    space_ids: tuple[str, ...] | list[str] | None,
) -> tuple[EmbeddingSpaceDefinition, ...]:
    if not space_ids:
        return FINAL_EMBEDDING_SPACE_DEFINITIONS
    requested = tuple(space_id for space_id in space_ids if space_id)
    definitions_by_id = {
        definition.space_id: definition for definition in FINAL_EMBEDDING_SPACE_DEFINITIONS
    }
    unknown = tuple(space_id for space_id in requested if space_id not in definitions_by_id)
    if unknown:
        raise ValueError(f"unknown final embedding space id(s): {', '.join(unknown)}")
    return tuple(definitions_by_id[space_id] for space_id in requested)


def _provider_execution_block() -> dict[str, Any]:
    return {
        "mode": "offline_estimate_only",
        "provider_requests_allowed": False,
        "provider_requests_made": 0,
        "network_allowed": False,
        "budget_guard_status": "not_entered",
        "real_provider_next_gate": "ProviderExecutionPolicy + API Budget Guard + WIP pause",
    }


def _artifact_file_record(path: Path, *, run_dir: Path) -> dict[str, Any]:
    return {
        "path": str(path.relative_to(run_dir)),
        "byte_count": path.stat().st_size,
        "sha256": _sha256(path),
    }


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _sha256(path: Path) -> str:
    import hashlib

    return hashlib.sha256(path.read_bytes()).hexdigest()


def _artifact_slug(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("._") or "space"


def _clean_policy(policy: str | None) -> str:
    return str(policy or "auto").strip().lower().replace("-", "_")


def _safe_run_id(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "-", value).strip(".-") or _default_run_id()


def _default_run_id() -> str:
    return "offline-estimate-" + datetime.now(tz=UTC).strftime("%Y%m%dT%H%M%SZ")


def _utc_now() -> str:
    return datetime.now(tz=UTC).isoformat()
