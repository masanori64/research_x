from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

DEFAULT_CONTEXT_OFFLOAD_DIR = Path("runs") / "context_offloads"
DEFAULT_OFFLOAD_ARTIFACT_KIND = "context_offload"
DEFAULT_OFFLOAD_OWNER_PLANE = "research_x_runtime"
ALLOWED_POINTER_ARTIFACT_KINDS = frozenset(
    {
        DEFAULT_OFFLOAD_ARTIFACT_KIND,
        "gpt_pro_plan",
        "historical_index",
        "historical_wbs_archive",
        "human_index",
        "implementation_plan",
        "json_schema",
        "route_memory_registry",
        "source_code",
        "wbs_json",
        "chatgpt_consultation",
        "codex_review_capture",
        "compressed_summary",
        "context_offload_preview",
        "context_preview",
        "d2_source",
        "diagram_review",
        "html_structure_view",
        "presentation_svg",
        "review_artifact",
        "wbs_rendered_view",
    }
)
ALLOWED_POINTER_OWNER_PLANES = frozenset(
    {
        DEFAULT_OFFLOAD_OWNER_PLANE,
        "archive",
        "codex_foundation",
        "control_artifact",
        "decision_input",
        "operation_route_memory",
        "pointer",
        "work_state",
    }
)


@dataclass(frozen=True)
class ContextBudgetPolicy:
    policy_id: str = "context-budget-v1"
    max_output_chars: int = 32_000
    max_inline_chunk_chars: int = 8_000
    preview_chars: int = 1_200
    offload_dir: Path = DEFAULT_CONTEXT_OFFLOAD_DIR
    enabled: bool = True

    def normalized(self) -> ContextBudgetPolicy:
        return ContextBudgetPolicy(
            policy_id=self.policy_id,
            max_output_chars=max(1, int(self.max_output_chars)),
            max_inline_chunk_chars=max(1, int(self.max_inline_chunk_chars)),
            preview_chars=max(1, int(self.preview_chars)),
            offload_dir=Path(self.offload_dir),
            enabled=self.enabled,
        )

    def as_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["offload_dir"] = str(self.offload_dir)
        return data


@dataclass(frozen=True)
class OffloadPointer:
    pointer_id: str
    field_path: str
    artifact_path: str
    sha256: str
    char_count: int
    byte_count: int
    preview_chars: int
    chunk_id: str | None
    source_kind: str | None
    source_id: str | None
    source_url: str | None
    citation_refs: tuple[dict[str, Any], ...]
    restore_hint: str
    artifact_kind: str = DEFAULT_OFFLOAD_ARTIFACT_KIND
    owner_plane: str = DEFAULT_OFFLOAD_OWNER_PLANE
    not_evidence: bool = True

    def as_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["citation_refs"] = list(self.citation_refs)
        return data


@dataclass(frozen=True)
class PointerVerificationResult:
    pointer_id: str | None
    artifact_path: str | None
    status: str
    issues: tuple[str, ...]
    artifact_exists: bool
    sha256_match: bool | None
    char_count_match: bool | None
    byte_count_match: bool | None
    artifact_kind: str | None
    owner_plane: str | None
    not_evidence: bool | None
    expected_sha256: str | None
    actual_sha256: str | None
    expected_char_count: int | None
    actual_char_count: int | None
    expected_byte_count: int | None
    actual_byte_count: int | None
    restore_hint: str | None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class PointerAuditReport:
    source_path: str
    source_kind: str
    status: str
    results: tuple[PointerVerificationResult, ...]
    skipped_reason: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "source_path": self.source_path,
            "source_kind": self.source_kind,
            "status": self.status,
            "results": [result.as_dict() for result in self.results],
            "skipped_reason": self.skipped_reason,
        }


@dataclass(frozen=True)
class BudgetedPayload:
    payload: dict[str, Any]
    pointers: tuple[OffloadPointer, ...]
    original_char_count: int
    final_char_count: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "payload": self.payload,
            "pointers": [pointer.as_dict() for pointer in self.pointers],
            "original_char_count": self.original_char_count,
            "final_char_count": self.final_char_count,
        }


def budget_json_payload(
    payload: dict[str, Any],
    *,
    policy: ContextBudgetPolicy | None,
    payload_kind: str,
    run_id: str | None = None,
) -> BudgetedPayload:
    original = copy.deepcopy(payload)
    original_char_count = _json_char_count(original)
    if policy is None or not policy.enabled:
        return BudgetedPayload(
            payload=original,
            pointers=(),
            original_char_count=original_char_count,
            final_char_count=original_char_count,
        )

    normalized = policy.normalized()
    budgeted = copy.deepcopy(payload)
    candidates = _chunk_text_candidates(budgeted)
    pointers: list[OffloadPointer] = []

    while candidates:
        current_size = _json_char_count(budgeted)
        oversized_candidates = [
            item for item in candidates if len(str(item["parent"].get("chunk_text") or "")) >
            normalized.max_inline_chunk_chars
        ]
        if current_size <= normalized.max_output_chars and not oversized_candidates:
            break
        item = max(
            oversized_candidates or candidates,
            key=lambda candidate: len(str(candidate["parent"].get("chunk_text") or "")),
        )
        text = str(item["parent"].get("chunk_text") or "")
        if not text:
            candidates.remove(item)
            continue
        pointer = _write_offload_artifact(
            item["parent"],
            field_path=str(item["field_path"]),
            text=text,
            policy=normalized,
            payload_kind=payload_kind,
            run_id=run_id or _payload_run_id(budgeted),
            payload=budgeted,
        )
        _replace_chunk_text_with_pointer(item["parent"], text=text, pointer=pointer)
        pointers.append(pointer)
        candidates.remove(item)

    summary = {
        "policy": normalized.as_dict(),
        "payload_kind": payload_kind,
        "original_char_count": original_char_count,
        "final_char_count": 0,
        "offloaded_item_count": len(pointers),
        "offloaded_char_count": sum(pointer.char_count for pointer in pointers),
        "pointers": [pointer.as_dict() for pointer in pointers],
        "non_destructive": True,
        "scope": (
            "output payload only; stored context chunks, citation anchors, and "
            "answer-generation inputs are unchanged"
        ),
    }
    budgeted["context_budget"] = summary
    final_char_count = _json_char_count(budgeted)
    budgeted["context_budget"]["final_char_count"] = final_char_count
    return BudgetedPayload(
        payload=budgeted,
        pointers=tuple(pointers),
        original_char_count=original_char_count,
        final_char_count=final_char_count,
    )


def budgeted_json(
    payload: dict[str, Any],
    *,
    policy: ContextBudgetPolicy | None,
    payload_kind: str,
    run_id: str | None = None,
) -> str:
    budgeted = budget_json_payload(
        payload,
        policy=policy,
        payload_kind=payload_kind,
        run_id=run_id,
    )
    return json.dumps(budgeted.payload, ensure_ascii=False, indent=2, sort_keys=True)


def verify_offload_pointer(
    pointer: OffloadPointer | dict[str, Any],
    *,
    base_dir: str | Path | None = None,
) -> PointerVerificationResult:
    data = pointer.as_dict() if isinstance(pointer, OffloadPointer) else dict(pointer)
    pointer_id = _string_or_none(data.get("pointer_id"))
    artifact_path_text = _string_or_none(data.get("artifact_path"))
    artifact_kind = _string_or_none(data.get("artifact_kind"))
    owner_plane = _string_or_none(data.get("owner_plane"))
    restore_hint = _string_or_none(data.get("restore_hint"))
    expected_sha256 = _string_or_none(data.get("sha256"))
    expected_char_count = _int_or_none(data.get("char_count"))
    expected_byte_count = _int_or_none(data.get("byte_count"))
    not_evidence = _bool_or_none(data.get("not_evidence"))
    issues: list[str] = []

    required = (
        "pointer_id",
        "artifact_path",
        "sha256",
        "char_count",
        "byte_count",
        "restore_hint",
        "artifact_kind",
        "owner_plane",
        "not_evidence",
    )
    for key in required:
        if key not in data or data.get(key) in (None, ""):
            issues.append(f"missing_required_field:{key}")
    if artifact_kind == DEFAULT_OFFLOAD_ARTIFACT_KIND:
        for key in ("field_path", "chunk_id", "preview_chars"):
            if key not in data or data.get(key) in (None, ""):
                issues.append(f"missing_required_field:{key}")
    if not_evidence is not True:
        issues.append("not_evidence_violation")
    if artifact_kind not in ALLOWED_POINTER_ARTIFACT_KINDS:
        issues.append(f"unsupported_artifact_kind:{artifact_kind or 'missing'}")
    if owner_plane not in ALLOWED_POINTER_OWNER_PLANES:
        issues.append(f"unsupported_owner_plane:{owner_plane or 'missing'}")
    if (
        restore_hint
        and "citation" in restore_hint.casefold()
        and "not" not in restore_hint.casefold()
    ):
        issues.append("restore_hint_may_imply_citation")

    artifact_path = _resolve_pointer_path(artifact_path_text, base_dir=base_dir)
    artifact_exists = bool(artifact_path and artifact_path.exists() and artifact_path.is_file())
    actual_sha256: str | None = None
    actual_char_count: int | None = None
    actual_byte_count: int | None = None
    sha256_match: bool | None = None
    char_count_match: bool | None = None
    byte_count_match: bool | None = None
    if not artifact_exists:
        issues.append("missing_artifact")
    elif artifact_path is not None:
        actual_sha256, actual_char_count, actual_byte_count, artifact = (
            _artifact_measurements(artifact_path)
        )
        sha256_match = actual_sha256 == expected_sha256
        char_count_match = actual_char_count == expected_char_count
        byte_count_match = actual_byte_count == expected_byte_count
        if not sha256_match:
            issues.append("stale_hash")
        if not char_count_match:
            issues.append("stale_char_count")
        if not byte_count_match:
            issues.append("stale_byte_count")
        if isinstance(artifact, dict) and isinstance(artifact.get("pointer"), dict):
            artifact_pointer = artifact["pointer"]
            if _string_or_none(artifact_pointer.get("pointer_id")) != pointer_id:
                issues.append("artifact_pointer_id_mismatch")
            if artifact.get("not_evidence") is not True:
                issues.append("artifact_not_evidence_violation")
            if artifact_pointer.get("not_evidence") is not True:
                issues.append("artifact_pointer_not_evidence_violation")

    status = _pointer_status(issues)
    return PointerVerificationResult(
        pointer_id=pointer_id,
        artifact_path=str(artifact_path) if artifact_path is not None else artifact_path_text,
        status=status,
        issues=tuple(dict.fromkeys(issues)),
        artifact_exists=artifact_exists,
        sha256_match=sha256_match,
        char_count_match=char_count_match,
        byte_count_match=byte_count_match,
        artifact_kind=artifact_kind,
        owner_plane=owner_plane,
        not_evidence=not_evidence,
        expected_sha256=expected_sha256,
        actual_sha256=actual_sha256,
        expected_char_count=expected_char_count,
        actual_char_count=actual_char_count,
        expected_byte_count=expected_byte_count,
        actual_byte_count=actual_byte_count,
        restore_hint=restore_hint,
    )


def verify_pointer_map(
    pointer_map_path: str | Path,
    *,
    base_dir: str | Path | None = None,
) -> PointerAuditReport:
    path = Path(pointer_map_path)
    if not path.exists():
        return PointerAuditReport(
            source_path=str(path),
            source_kind="pointer_map",
            status="skipped_external_pointer_map_absent",
            results=(),
            skipped_reason="pointer_map_absent",
        )
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return PointerAuditReport(
            source_path=str(path),
            source_kind="pointer_map",
            status="failed",
            results=(
                PointerVerificationResult(
                    pointer_id=None,
                    artifact_path=str(path),
                    status="invalid_pointer_map",
                    issues=(f"invalid_json:{exc.msg}",),
                    artifact_exists=True,
                    sha256_match=None,
                    char_count_match=None,
                    byte_count_match=None,
                    artifact_kind=None,
                    owner_plane=None,
                    not_evidence=None,
                    expected_sha256=None,
                    actual_sha256=None,
                    expected_char_count=None,
                    actual_char_count=None,
                    expected_byte_count=None,
                    actual_byte_count=None,
                    restore_hint=None,
                ),
            ),
        )
    entries = payload.get("entries") if isinstance(payload, dict) else None
    if not isinstance(entries, list):
        return PointerAuditReport(
            source_path=str(path),
            source_kind="pointer_map",
            status="failed",
            results=(
                PointerVerificationResult(
                    pointer_id=None,
                    artifact_path=str(path),
                    status="invalid_pointer_map",
                    issues=("missing_entries",),
                    artifact_exists=True,
                    sha256_match=None,
                    char_count_match=None,
                    byte_count_match=None,
                    artifact_kind=None,
                    owner_plane=None,
                    not_evidence=None,
                    expected_sha256=None,
                    actual_sha256=None,
                    expected_char_count=None,
                    actual_char_count=None,
                    expected_byte_count=None,
                    actual_byte_count=None,
                    restore_hint=None,
                ),
            ),
        )
    root = Path(base_dir) if base_dir is not None else Path.cwd()
    results = tuple(
        verify_offload_pointer(entry, base_dir=root)
        for entry in entries
        if isinstance(entry, dict)
    )
    status = (
        "passed"
        if results and all(result.status == "usable_pointer" for result in results)
        else "failed"
    )
    if not results:
        status = "failed"
    return PointerAuditReport(
        source_path=str(path),
        source_kind="pointer_map",
        status=status,
        results=results,
    )


def verify_offload_directory(
    offload_dir: str | Path,
    *,
    base_dir: str | Path | None = None,
) -> PointerAuditReport:
    path = Path(offload_dir)
    if not path.exists():
        return PointerAuditReport(
            source_path=str(path),
            source_kind="offload_dir",
            status="skipped_offload_dir_absent",
            results=(),
            skipped_reason="offload_dir_absent",
        )
    root = Path(base_dir) if base_dir is not None else Path.cwd()
    results: list[PointerVerificationResult] = []
    for artifact_path in sorted(path.rglob("*.json")):
        try:
            artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        pointer = artifact.get("pointer") if isinstance(artifact, dict) else None
        if isinstance(pointer, dict):
            results.append(verify_offload_pointer(pointer, base_dir=root))
    if not results:
        status = "empty"
    else:
        status = (
            "passed"
            if all(result.status == "usable_pointer" for result in results)
            else "failed"
        )
    return PointerAuditReport(
        source_path=str(path),
        source_kind="offload_dir",
        status=status,
        results=tuple(results),
    )


def _chunk_text_candidates(payload: dict[str, Any]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []

    def walk(value: Any, path: str) -> None:
        if isinstance(value, dict):
            if "chunk_id" in value and "chunk_text" in value and isinstance(
                value.get("chunk_text"), str
            ):
                candidates.append({"parent": value, "field_path": f"{path}.chunk_text"})
            for key, child in value.items():
                child_path = f"{path}.{key}" if path else str(key)
                walk(child, child_path)
        elif isinstance(value, list):
            for index, child in enumerate(value):
                walk(child, f"{path}[{index}]")

    walk(payload, "")
    return candidates


def _write_offload_artifact(
    chunk: dict[str, Any],
    *,
    field_path: str,
    text: str,
    policy: ContextBudgetPolicy,
    payload_kind: str,
    run_id: str | None,
    payload: dict[str, Any],
) -> OffloadPointer:
    text_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
    pointer_id = _pointer_id(field_path, str(chunk.get("chunk_id") or ""), text_hash)
    safe_run_id = _safe_path_part(run_id or "no-run-id")
    artifact_dir = policy.offload_dir / safe_run_id
    artifact_path = artifact_dir / f"{pointer_id}.json"
    citation_refs = tuple(_citation_refs(payload, str(chunk.get("chunk_id") or "")))
    pointer = OffloadPointer(
        pointer_id=pointer_id,
        field_path=field_path,
        artifact_path=str(artifact_path),
        sha256=text_hash,
        char_count=len(text),
        byte_count=len(text.encode("utf-8")),
        preview_chars=min(policy.preview_chars, len(text)),
        chunk_id=_string_or_none(chunk.get("chunk_id")),
        source_kind=_string_or_none(chunk.get("source_kind")),
        source_id=_string_or_none(chunk.get("source_id")),
        source_url=_string_or_none(chunk.get("source_url")),
        citation_refs=citation_refs,
        restore_hint=(
            "Read artifact_path, verify sha256/size, and restore source context before use; "
            "this pointer, restore hint, and inline preview are not citations or answer evidence."
        ),
    )
    artifact = {
        "artifact_kind": pointer.artifact_kind,
        "owner_plane": pointer.owner_plane,
        "not_evidence": True,
        "answer_support_allowed": False,
        "evidence_status": "not_evidence",
        "citation_policy": "not_citation_restore_and_verify_source_context_first",
        "pointer": pointer.as_dict(),
        "payload_kind": payload_kind,
        "run_id": run_id,
        "content_type": "text/plain",
        "content": text,
        "created_at": _utc_now(),
        "source_anchor": {
            "chunk_id": chunk.get("chunk_id"),
            "source_kind": chunk.get("source_kind"),
            "source_id": chunk.get("source_id"),
            "source_url": chunk.get("source_url"),
            "citation_refs": list(citation_refs),
            "not_evidence": True,
            "answer_support_allowed": False,
        },
    }
    artifact_dir.mkdir(parents=True, exist_ok=True)
    artifact_path.write_text(
        json.dumps(artifact, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return pointer


def _replace_chunk_text_with_pointer(
    chunk: dict[str, Any],
    *,
    text: str,
    pointer: OffloadPointer,
) -> None:
    preview = _preview(text, pointer.preview_chars)
    chunk["chunk_text"] = (
        f"[context text offloaded: {pointer.pointer_id}]\n"
        "preview_only_not_evidence: true\n"
        f"{preview}\n"
        f"restore_from: {pointer.artifact_path}\n"
        f"sha256: {pointer.sha256}"
    )
    metadata = dict(chunk.get("metadata") or {})
    metadata["context_budgeted_output"] = True
    metadata["inline_char_count"] = len(chunk["chunk_text"])
    metadata["original_char_count"] = pointer.char_count
    metadata["offload_pointer"] = pointer.as_dict()
    metadata["not_evidence"] = True
    metadata["answer_support_allowed"] = False
    metadata["evidence_status"] = "preview_only"
    metadata["preview_kind"] = "context_offload_preview"
    metadata["artifact_kind"] = "context_offload_preview"
    metadata["owner_plane"] = pointer.owner_plane
    metadata["citation_policy"] = "not_citation_restore_pointer_and_source_chunk_first"
    metadata["restore_hint_status"] = "requires_pointer_verification"
    metadata["restore_hint"] = pointer.restore_hint
    chunk["metadata"] = metadata


def _preview(text: str, preview_chars: int) -> str:
    if len(text) <= preview_chars:
        return text
    head_chars = max(1, preview_chars // 2)
    tail_chars = max(1, preview_chars - head_chars)
    omitted = len(text) - head_chars - tail_chars
    return f"{text[:head_chars]}\n[... omitted_chars={omitted} ...]\n{text[-tail_chars:]}"


def _citation_refs(payload: dict[str, Any], chunk_id: str) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []

    def walk(value: Any) -> None:
        if isinstance(value, dict):
            if value.get("chunk_id") == chunk_id and value.get("citation_id"):
                refs.append(
                    {
                        "citation_id": value.get("citation_id"),
                        "source_kind": value.get("source_kind"),
                        "source_id": value.get("source_id"),
                        "source_url": value.get("source_url"),
                        "field_path": value.get("field_path"),
                        "evidence_status": value.get("evidence_status"),
                    }
                )
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    walk(payload)
    return refs


def _payload_run_id(payload: dict[str, Any]) -> str | None:
    if payload.get("run_id"):
        return str(payload["run_id"])
    if isinstance(payload.get("context_bundle"), dict):
        return _payload_run_id(payload["context_bundle"])
    return None


def _json_char_count(payload: dict[str, Any]) -> int:
    return len(json.dumps(payload, ensure_ascii=False, sort_keys=True))


def _pointer_id(field_path: str, chunk_id: str, text_hash: str) -> str:
    digest = hashlib.sha256(
        "\0".join([field_path, chunk_id, text_hash]).encode("utf-8")
    ).hexdigest()
    return f"ctxptr_{digest[:16]}"


def _safe_path_part(value: str) -> str:
    safe = "".join(char if char.isalnum() or char in {"-", "_"} else "_" for char in value)
    return safe[:120] or "no-run-id"


def _resolve_pointer_path(value: str | None, *, base_dir: str | Path | None) -> Path | None:
    if not value:
        return None
    path = Path(value)
    if path.is_absolute():
        return path
    root = Path(base_dir) if base_dir is not None else Path.cwd()
    return root / path


def _artifact_measurements(path: Path) -> tuple[str, int, int, dict[str, Any] | None]:
    raw = path.read_bytes()
    text = raw.decode("utf-8")
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return (
            hashlib.sha256(raw).hexdigest(),
            len(_logical_text(text)),
            len(raw),
            None,
        )
    if isinstance(payload, dict) and isinstance(payload.get("content"), str):
        content = str(payload["content"])
        encoded = content.encode("utf-8")
        return hashlib.sha256(encoded).hexdigest(), len(content), len(encoded), payload
    return (
        hashlib.sha256(raw).hexdigest(),
        len(_logical_text(text)),
        len(raw),
        payload if isinstance(payload, dict) else None,
    )


def _logical_text(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _pointer_status(issues: list[str]) -> str:
    if not issues:
        return "usable_pointer"
    if any(issue.startswith("missing_required_field") for issue in issues):
        return "invalid_pointer"
    if "missing_artifact" in issues:
        return "missing_artifact"
    if any("not_evidence_violation" in issue for issue in issues):
        return "not_evidence_violation"
    if any(issue.startswith("unsupported_artifact_kind") for issue in issues):
        return "unsupported_artifact_kind"
    if any(issue.startswith("unsupported_owner_plane") for issue in issues):
        return "unsupported_owner_plane"
    if "stale_hash" in issues:
        return "stale_hash"
    if "stale_char_count" in issues or "stale_byte_count" in issues:
        return "stale_size"
    return "invalid_pointer"


def _int_or_none(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _bool_or_none(value: Any) -> bool | None:
    return value if isinstance(value, bool) else None


def _string_or_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text or None


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
