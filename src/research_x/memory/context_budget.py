from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

DEFAULT_CONTEXT_OFFLOAD_DIR = Path("runs") / "context_offloads"


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

    def as_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["citation_refs"] = list(self.citation_refs)
        return data


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
        restore_hint="Read artifact_path and verify sha256 before using the offloaded text.",
    )
    artifact = {
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
        f"{preview}\n"
        f"restore_from: {pointer.artifact_path}\n"
        f"sha256: {pointer.sha256}"
    )
    metadata = dict(chunk.get("metadata") or {})
    metadata["context_budgeted_output"] = True
    metadata["inline_char_count"] = len(chunk["chunk_text"])
    metadata["original_char_count"] = pointer.char_count
    metadata["offload_pointer"] = pointer.as_dict()
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


def _string_or_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text or None


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
