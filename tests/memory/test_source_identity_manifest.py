from __future__ import annotations

import pytest

from research_x.memory.source_identity import (
    SelfDescribingArtifactManifest,
    artifact_manifest_id,
    validate_self_describing_artifact_manifest,
)


def _manifest() -> SelfDescribingArtifactManifest:
    return SelfDescribingArtifactManifest(
        artifact_locator="memory://fixtures/f3/reference-only-artifact",
        content_hash="sha256:fixture-content",
        schema_name="future-file-format-reference",
        schema_version="0.0-reference",
        decoder_reference={
            "kind": "decoder_reference_metadata",
            "name": "f3 research prototype reference",
            "execution_allowed": False,
        },
        restore_hint="Review source registry before any fetch or decoder work.",
    )


def test_self_describing_artifact_manifest_is_inert_identity_only() -> None:
    manifest = _manifest()

    assert validate_self_describing_artifact_manifest(manifest) == []
    assert artifact_manifest_id(manifest) == artifact_manifest_id(manifest.as_dict())
    assert len(artifact_manifest_id(manifest)) == 24
    assert manifest.not_evidence is True
    assert manifest.answer_support_allowed is False
    assert manifest.evidence_status == "not_evidence"


def test_self_describing_artifact_manifest_rejects_decoder_execution_surfaces() -> None:
    payload = _manifest().as_dict()
    payload["decoder_reference"] = {
        "kind": "inline_decoder",
        "execution_allowed": True,
        "inline_wasm": "data:application/wasm;base64,AAAA",
        "subprocess_command": "wasm_exec artifact.f3",
    }

    errors = validate_self_describing_artifact_manifest(payload)

    assert "manifest.decoder_reference.execution_allowed must be false" in errors
    assert any("inline_wasm" in error for error in errors)
    assert any("subprocess_command" in error for error in errors)
    assert "manifest contains executable or inline decoder value" in errors


def test_self_describing_artifact_manifest_rejects_nested_list_decoder_fields() -> None:
    payload = _manifest().as_dict()
    payload["decoder_reference"]["adapters"] = [
        {
            "inline_wasm": "sha256:not-inline-content",
            "subprocess_command": "wasm_exec artifact.f3",
        }
    ]

    errors = validate_self_describing_artifact_manifest(payload)

    assert any("decoder_reference.adapters[0].inline_wasm" in error for error in errors)
    assert any(
        "decoder_reference.adapters[0].subprocess_command" in error
        for error in errors
    )


def test_self_describing_artifact_manifest_rejects_evidence_promotion() -> None:
    payload = _manifest().as_dict()
    payload["not_evidence"] = False
    payload["answer_support_allowed"] = True
    payload["evidence_status"] = "citation_ready"
    payload["citation"] = {"source_id": "source:1"}
    payload["source_bundle"] = "bundle:1"

    errors = validate_self_describing_artifact_manifest(payload)

    assert "manifest.not_evidence must be true" in errors
    assert "manifest.answer_support_allowed must be false" in errors
    assert "manifest.evidence_status must be not_evidence" in errors
    assert "manifest must not carry 'citation'" in errors
    assert "manifest must not carry 'source_bundle'" in errors


def test_self_describing_artifact_manifest_id_rejects_invalid_payload() -> None:
    payload = _manifest().as_dict()
    payload["decoder_reference"]["inline_wasm"] = "data:application/wasm;base64,AAAA"

    with pytest.raises(ValueError, match="inline_wasm"):
        artifact_manifest_id(payload)
