from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import Any

READ_ONLY_CONTRACT_ID = "memory-read-only-mnp-v1"


@dataclass(frozen=True)
class MNPVirtualEndpoint:
    endpoint_id: str
    tool_id: str
    side_effect: str
    provider_gate: bool
    evidence_role: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class PromptContract:
    contract_id: str
    mode: str
    allowed_tools: tuple[str, ...]
    forbidden_tools: tuple[str, ...]
    provider_gated_tools: tuple[str, ...]
    injection_markers: tuple[str, ...]
    write_intent_markers: tuple[str, ...]
    required_guards: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class PromptContractEvaluation:
    contract_id: str
    prompt: str
    route: str
    read_only: bool
    allowed_tools: tuple[str, ...]
    forbidden_tools: tuple[str, ...]
    requested_tools: tuple[str, ...]
    blocked_tools: tuple[str, ...]
    provider_gate_hits: tuple[str, ...]
    injection_hits: tuple[str, ...]
    write_intent_hits: tuple[str, ...]
    status: str
    notes: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


MNP_VIRTUAL_ENDPOINTS = (
    MNPVirtualEndpoint(
        endpoint_id="mnp.memory.search",
        tool_id="memory.search",
        side_effect="read_only",
        provider_gate=False,
        evidence_role="search_signal_not_citation",
    ),
    MNPVirtualEndpoint(
        endpoint_id="mnp.memory.evidence",
        tool_id="memory.evidence",
        side_effect="read_only",
        provider_gate=False,
        evidence_role="source_restore_restoration",
    ),
    MNPVirtualEndpoint(
        endpoint_id="mnp.memory.context",
        tool_id="memory.context",
        side_effect="read_only",
        provider_gate=False,
        evidence_role="context_chunks_and_citation_metadata",
    ),
    MNPVirtualEndpoint(
        endpoint_id="mnp.memory.citations",
        tool_id="memory.citations",
        side_effect="read_only",
        provider_gate=False,
        evidence_role="citation_annotation_inspection",
    ),
    MNPVirtualEndpoint(
        endpoint_id="mnp.memory.workflow.inspect",
        tool_id="memory.workflow:inspect",
        side_effect="read_only",
        provider_gate=False,
        evidence_role="workflow_trace_inspection",
    ),
    MNPVirtualEndpoint(
        endpoint_id="mnp.memory.governance.check",
        tool_id="memory.governance.check",
        side_effect="read_only",
        provider_gate=False,
        evidence_role="governance_state_inspection",
    ),
    MNPVirtualEndpoint(
        endpoint_id="mnp.memory.governance.tombstone",
        tool_id="memory.governance.tombstone",
        side_effect="write",
        provider_gate=False,
        evidence_role="governance_mutation",
    ),
    MNPVirtualEndpoint(
        endpoint_id="mnp.memory.governance.restore",
        tool_id="memory.governance.restore",
        side_effect="write",
        provider_gate=False,
        evidence_role="governance_mutation",
    ),
    MNPVirtualEndpoint(
        endpoint_id="mnp.memory.feedback",
        tool_id="memory.feedback",
        side_effect="write",
        provider_gate=False,
        evidence_role="ranking_signal_mutation",
    ),
    MNPVirtualEndpoint(
        endpoint_id="mnp.memory.external_search",
        tool_id="memory.external-search",
        side_effect="provider_or_network",
        provider_gate=True,
        evidence_role="external_discovery_candidate",
    ),
    MNPVirtualEndpoint(
        endpoint_id="mnp.memory.extract_url",
        tool_id="memory.extract-url",
        side_effect="provider_or_network",
        provider_gate=True,
        evidence_role="external_context_extraction",
    ),
    MNPVirtualEndpoint(
        endpoint_id="mnp.memory.llm_context",
        tool_id="memory.llm-context",
        side_effect="provider_or_network",
        provider_gate=True,
        evidence_role="external_grounding_candidate",
    ),
    MNPVirtualEndpoint(
        endpoint_id="mnp.memory.build_embeddings",
        tool_id="memory.build-embeddings",
        side_effect="write_or_provider",
        provider_gate=True,
        evidence_role="projection_build",
    ),
    MNPVirtualEndpoint(
        endpoint_id="mnp.memory.api_budget.override",
        tool_id="memory.api-budget.override",
        side_effect="policy_mutation",
        provider_gate=True,
        evidence_role="provider_policy_mutation",
    ),
)


READ_ONLY_MEMORY_PROMPT_CONTRACT = PromptContract(
    contract_id=READ_ONLY_CONTRACT_ID,
    mode="read_only_memory_navigation",
    allowed_tools=tuple(
        endpoint.tool_id
        for endpoint in MNP_VIRTUAL_ENDPOINTS
        if endpoint.side_effect == "read_only"
    ),
    forbidden_tools=tuple(
        endpoint.tool_id
        for endpoint in MNP_VIRTUAL_ENDPOINTS
        if endpoint.side_effect != "read_only"
    ),
    provider_gated_tools=tuple(
        endpoint.tool_id for endpoint in MNP_VIRTUAL_ENDPOINTS if endpoint.provider_gate
    ),
    injection_markers=(
        "ignore previous",
        "ignore the contract",
        "bypass",
        "override",
        "developer mode",
        "system prompt",
        "--allow-unpriced-api",
    ),
    write_intent_markers=(
        "add feedback",
        "clear",
        "db write",
        "delete",
        "drop",
        "erase",
        "forget",
        "insert",
        "mark as",
        "mutate",
        "purge",
        "record feedback",
        "remove",
        "restore",
        "save feedback",
        "store result",
        "suppress",
        "tombstone",
        "update",
        "write to db",
    ),
    required_guards=(
        "source_restore_restoration",
        "citation_required_before_answer",
        "provider_execution_policy_required",
        "no_raw_source_mutation",
        "no_governance_mutation",
        "no_feedback_mutation",
        "operational_trace_write_allowed_when_persistence_permits",
    ),
)

TOOL_ALIASES = {
    "memory search": "memory.search",
    "memory evidence": "memory.evidence",
    "memory context": "memory.context",
    "memory citations": "memory.citations",
    "memory workflow": "memory.workflow:inspect",
    "memory governance check": "memory.governance.check",
    "memory governance tombstone": "memory.governance.tombstone",
    "memory governance restore": "memory.governance.restore",
    "memory feedback": "memory.feedback",
    "memory external-search": "memory.external-search",
    "external search": "memory.external-search",
    "memory extract-url": "memory.extract-url",
    "extract url": "memory.extract-url",
    "memory llm-context": "memory.llm-context",
    "llm context": "memory.llm-context",
    "build embeddings": "memory.build-embeddings",
    "memory build-embeddings": "memory.build-embeddings",
    "allow-unpriced-api": "memory.api-budget.override",
}


def evaluate_prompt_contract(
    prompt: str,
    *,
    contract: PromptContract = READ_ONLY_MEMORY_PROMPT_CONTRACT,
) -> PromptContractEvaluation:
    normalized = _normalize(prompt)
    requested_tools = _requested_tools(normalized)
    blocked_tools = tuple(
        tool for tool in requested_tools if tool in set(contract.forbidden_tools)
    )
    provider_gate_hits = tuple(
        tool for tool in requested_tools if tool in set(contract.provider_gated_tools)
    )
    injection_hits = tuple(
        marker for marker in contract.injection_markers if marker in normalized
    )
    write_intent_hits = tuple(
        marker for marker in contract.write_intent_markers if marker in normalized
    )
    route = _route_prompt(
        normalized,
        blocked_tools=blocked_tools,
        write_intent_hits=write_intent_hits,
    )
    notes = _notes(
        blocked_tools=blocked_tools,
        provider_gate_hits=provider_gate_hits,
        injection_hits=injection_hits,
        write_intent_hits=write_intent_hits,
    )
    status = "rejected" if blocked_tools or injection_hits or write_intent_hits else "ok"
    return PromptContractEvaluation(
        contract_id=contract.contract_id,
        prompt=prompt,
        route=route,
        read_only=True,
        allowed_tools=contract.allowed_tools,
        forbidden_tools=contract.forbidden_tools,
        requested_tools=requested_tools,
        blocked_tools=blocked_tools,
        provider_gate_hits=provider_gate_hits,
        injection_hits=injection_hits,
        write_intent_hits=write_intent_hits,
        status=status,
        notes=notes,
    )


def validate_read_only_mnp_manifest(
    *,
    contract: PromptContract = READ_ONLY_MEMORY_PROMPT_CONTRACT,
    endpoints: tuple[MNPVirtualEndpoint, ...] = MNP_VIRTUAL_ENDPOINTS,
) -> list[str]:
    errors: list[str] = []
    by_tool = {endpoint.tool_id: endpoint for endpoint in endpoints}
    for tool in contract.allowed_tools:
        endpoint = by_tool.get(tool)
        if endpoint is None:
            errors.append(f"allowed tool missing endpoint: {tool}")
            continue
        if endpoint.side_effect != "read_only":
            errors.append(f"allowed tool is not read-only: {tool}")
        if endpoint.provider_gate:
            errors.append(f"allowed tool is provider-gated: {tool}")
    for tool in contract.forbidden_tools:
        endpoint = by_tool.get(tool)
        if endpoint is None:
            errors.append(f"forbidden tool missing endpoint: {tool}")
            continue
        if endpoint.side_effect == "read_only" and not endpoint.provider_gate:
            errors.append(f"read-only non-provider endpoint is forbidden: {tool}")
    for endpoint in endpoints:
        in_allowed = endpoint.tool_id in contract.allowed_tools
        in_forbidden = endpoint.tool_id in contract.forbidden_tools
        if in_allowed == in_forbidden:
            errors.append(f"tool must be in exactly one policy set: {endpoint.tool_id}")
    return errors


def prompt_contract_json(evaluation: PromptContractEvaluation) -> str:
    return json.dumps(evaluation.as_dict(), ensure_ascii=False, indent=2, sort_keys=True)


def mnp_manifest_json() -> str:
    return json.dumps(
        [endpoint.as_dict() for endpoint in MNP_VIRTUAL_ENDPOINTS],
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    )


def _requested_tools(normalized_prompt: str) -> tuple[str, ...]:
    tools: list[str] = []
    for pattern, tool_id in _tool_patterns().items():
        if pattern in normalized_prompt and tool_id not in tools:
            tools.append(tool_id)
    return tuple(tools)


def _tool_patterns() -> dict[str, str]:
    patterns: dict[str, str] = {}
    for endpoint in MNP_VIRTUAL_ENDPOINTS:
        for pattern in (
            endpoint.tool_id,
            endpoint.endpoint_id,
            endpoint.tool_id.replace("-", "_"),
            endpoint.endpoint_id.replace("-", "_"),
        ):
            patterns[_normalize(pattern)] = endpoint.tool_id
    for alias, tool_id in TOOL_ALIASES.items():
        patterns[_normalize(alias)] = tool_id
    return patterns


def _route_prompt(
    normalized_prompt: str,
    *,
    blocked_tools: tuple[str, ...],
    write_intent_hits: tuple[str, ...],
) -> str:
    if blocked_tools or write_intent_hits:
        return "needs_human_review"
    if any(term in normalized_prompt for term in ("citation", "cite", "source restoration")):
        return "read_only_citation_context"
    if any(term in normalized_prompt for term in ("context", "evidence", "why")):
        return "read_only_context_bundle"
    if any(term in normalized_prompt for term in ("tombstone", "forget", "delete", "restore")):
        return "needs_human_review"
    return "read_only_memory_search"


def _notes(
    *,
    blocked_tools: tuple[str, ...],
    provider_gate_hits: tuple[str, ...],
    injection_hits: tuple[str, ...],
    write_intent_hits: tuple[str, ...],
) -> tuple[str, ...]:
    notes: list[str] = [
        "PromptContract/MNP checks are deterministic local guardrail tests.",
        "They do not replace auth, DB transactions, provider policy, or source restoration.",
    ]
    if blocked_tools:
        notes.append("Forbidden tool request detected.")
    if provider_gate_hits:
        notes.append(
            "Provider-controlled tool request detected without scoped ProviderExecutionPolicy."
        )
    if injection_hits:
        notes.append("Prompt-injection marker detected.")
    if write_intent_hits:
        notes.append("Write intent detected in a read-only prompt contract.")
    return tuple(notes)


def _normalize(value: str) -> str:
    return " ".join(value.casefold().replace("_", "-").split())
