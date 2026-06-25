from __future__ import annotations

from dataclasses import dataclass
from typing import Any

CODEX_TO_RESEARCH_X_ALLOWED_INPUTS = (
    "query",
    "objective",
    "context_budget",
    "source_candidate",
)
RESEARCH_X_TO_CODEX_ALLOWED_OUTPUTS = (
    "evidence_status",
    "citation_ready_answer",
    "abstain",
    "needs_review",
    "provider_gated",
    "audit_trace",
)
FORBIDDEN_BRIDGE_FIELDS = (
    "codex_transcript",
    "skill_auto_edit_permission",
    "provider_execution_permission",
    "root_instruction",
)
BRIDGE_CONTRACT_VERSION = "research-x-codex-bridge-v1"


@dataclass(frozen=True)
class BridgeContract:
    contract_version: str
    codex_to_research_x_allowed_inputs: tuple[str, ...]
    research_x_to_codex_allowed_outputs: tuple[str, ...]
    forbidden_fields: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "contract_version": self.contract_version,
            "codex_to_research_x_allowed_inputs": list(
                self.codex_to_research_x_allowed_inputs
            ),
            "research_x_to_codex_allowed_outputs": list(
                self.research_x_to_codex_allowed_outputs
            ),
            "forbidden_fields": list(self.forbidden_fields),
        }


def bridge_contract() -> BridgeContract:
    return BridgeContract(
        contract_version=BRIDGE_CONTRACT_VERSION,
        codex_to_research_x_allowed_inputs=CODEX_TO_RESEARCH_X_ALLOWED_INPUTS,
        research_x_to_codex_allowed_outputs=RESEARCH_X_TO_CODEX_ALLOWED_OUTPUTS,
        forbidden_fields=FORBIDDEN_BRIDGE_FIELDS,
    )


def bridge_trace_contract() -> dict[str, Any]:
    contract = bridge_contract()
    return {
        "contract_version": contract.contract_version,
        "accepted_inputs": list(contract.codex_to_research_x_allowed_inputs),
        "accepted_outputs": list(contract.research_x_to_codex_allowed_outputs),
        "forbidden_inputs": list(contract.forbidden_fields),
    }


def validate_codex_to_research_x_payload(payload: dict[str, Any]) -> list[str]:
    return _validate_payload(
        payload,
        allowed=CODEX_TO_RESEARCH_X_ALLOWED_INPUTS,
        direction="codex_to_research_x",
    )


def validate_research_x_to_codex_payload(payload: dict[str, Any]) -> list[str]:
    return _validate_payload(
        payload,
        allowed=RESEARCH_X_TO_CODEX_ALLOWED_OUTPUTS,
        direction="research_x_to_codex",
    )


def _validate_payload(
    payload: dict[str, Any],
    *,
    allowed: tuple[str, ...],
    direction: str,
) -> list[str]:
    errors: list[str] = []
    allowed_set = set(allowed)
    for field in FORBIDDEN_BRIDGE_FIELDS:
        if field in payload:
            errors.append(f"{direction}: forbidden field {field!r}")
    unknown = sorted(set(payload) - allowed_set - {"contract_version"})
    if unknown:
        errors.append(f"{direction}: unknown bridge fields: {', '.join(unknown)}")
    if payload.get("contract_version", BRIDGE_CONTRACT_VERSION) != BRIDGE_CONTRACT_VERSION:
        errors.append(f"{direction}: invalid contract_version")
    return errors
