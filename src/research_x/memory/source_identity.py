from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from typing import Any

from research_x.memory.document_hashes import text_hash

SELF_DESCRIBING_MANIFEST_REQUIRED_FIELDS = {
    "artifact_locator",
    "content_hash",
    "schema_name",
    "schema_version",
    "decoder_reference",
}
SELF_DESCRIBING_FORBIDDEN_KEYS = {
    "allow_execution",
    "base64",
    "base64_decoder",
    "decoder_bytes",
    "decoder_command",
    "embedded_wasm",
    "execute",
    "execution_command",
    "inline_decoder",
    "inline_wasm",
    "load_wasm",
    "python_import",
    "runtime_import",
    "subprocess",
    "subprocess_command",
    "wasm_bytes",
}
SELF_DESCRIBING_FORBIDDEN_EVIDENCE_FIELDS = {
    "answer_support",
    "citation",
    "citations",
    "context_chunk",
    "evidence",
    "source_bundle",
}
SELF_DESCRIBING_FORBIDDEN_VALUE_TOKENS = (
    "base64,",
    "data:application/wasm",
    "data:wasm",
    "importlib",
    "subprocess",
    "webassembly.instantiate",
    "wasm_exec",
)
SELF_DESCRIBING_NOT_EVIDENCE_STATUS = "not_evidence"


@dataclass(frozen=True)
class SelfDescribingArtifactManifest:
    artifact_locator: str
    content_hash: str
    schema_name: str
    schema_version: str
    decoder_reference: dict[str, Any]
    restore_hint: str = ""
    not_evidence: bool = True
    answer_support_allowed: bool = False
    evidence_status: str = SELF_DESCRIBING_NOT_EVIDENCE_STATUS

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def source_bundle_id(doc_id: str, source_doc_hash: str) -> str:
    """Canonical identity for a restored source bundle."""

    return text_hash("|".join(("source-bundle", str(doc_id), str(source_doc_hash))))[:24]


def artifact_manifest_id(manifest: Mapping[str, Any] | SelfDescribingArtifactManifest) -> str:
    """Canonical identity for an inert self-describing artifact manifest."""

    payload = _manifest_dict(manifest)
    errors = validate_self_describing_artifact_manifest(payload)
    if errors:
        raise ValueError("; ".join(errors))
    safe_payload = {
        key: payload.get(key)
        for key in (
            "artifact_locator",
            "content_hash",
            "schema_name",
            "schema_version",
            "decoder_reference",
            "restore_hint",
        )
    }
    return text_hash(
        json.dumps(safe_payload, ensure_ascii=False, sort_keys=True)
    )[:24]


def validate_self_describing_artifact_manifest(
    manifest: Mapping[str, Any] | SelfDescribingArtifactManifest,
) -> list[str]:
    payload = _manifest_dict(manifest)
    errors: list[str] = []

    missing = sorted(SELF_DESCRIBING_MANIFEST_REQUIRED_FIELDS - set(payload))
    if missing:
        errors.append(f"manifest missing fields: {', '.join(missing)}")

    for key in ("artifact_locator", "content_hash", "schema_name", "schema_version"):
        if not str(payload.get(key, "")).strip():
            errors.append(f"manifest.{key} is required")

    decoder_reference = payload.get("decoder_reference")
    if not isinstance(decoder_reference, Mapping) or not decoder_reference:
        errors.append("manifest.decoder_reference must be a non-empty object")
    elif decoder_reference.get("execution_allowed", False) is not False:
        errors.append("manifest.decoder_reference.execution_allowed must be false")

    if payload.get("not_evidence") is not True:
        errors.append("manifest.not_evidence must be true")
    if payload.get("answer_support_allowed") is not False:
        errors.append("manifest.answer_support_allowed must be false")
    if payload.get("evidence_status") != SELF_DESCRIBING_NOT_EVIDENCE_STATUS:
        errors.append("manifest.evidence_status must be not_evidence")
    for field in sorted(SELF_DESCRIBING_FORBIDDEN_EVIDENCE_FIELDS & set(payload)):
        errors.append(f"manifest must not carry {field!r}")

    for path in _forbidden_manifest_key_paths(payload):
        errors.append(f"manifest contains executable or inline decoder field: {path}")
    for value in _manifest_string_values(payload):
        lowered = value.casefold()
        if any(token in lowered for token in SELF_DESCRIBING_FORBIDDEN_VALUE_TOKENS):
            errors.append("manifest contains executable or inline decoder value")
            break

    return errors


def _manifest_dict(
    manifest: Mapping[str, Any] | SelfDescribingArtifactManifest,
) -> dict[str, Any]:
    if isinstance(manifest, SelfDescribingArtifactManifest):
        return manifest.as_dict()
    return dict(manifest)


def _forbidden_manifest_key_paths(value: Any, *, prefix: str = "") -> list[str]:
    if isinstance(value, list | tuple):
        return [
            path
            for index, item in enumerate(value)
            for path in _forbidden_manifest_key_paths(item, prefix=f"{prefix}[{index}]")
        ]
    if not isinstance(value, Mapping):
        return []
    paths: list[str] = []
    for key, item in value.items():
        key_text = str(key)
        path = f"{prefix}.{key_text}" if prefix else key_text
        normalized = key_text.strip().casefold().replace("-", "_")
        if normalized in SELF_DESCRIBING_FORBIDDEN_KEYS:
            paths.append(path)
        paths.extend(_forbidden_manifest_key_paths(item, prefix=path))
    return paths


def _manifest_string_values(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, Mapping):
        return [
            item
            for child in value.values()
            for item in _manifest_string_values(child)
        ]
    if isinstance(value, list | tuple | set):
        return [item for child in value for item in _manifest_string_values(child)]
    return []
