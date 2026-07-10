from __future__ import annotations

import pytest

from research_x.memory.human_oversight import (
    HumanOversightLevel,
    classify_human_oversight,
)

CANON_ITEMS = ("P8", "P13", "P14", "P19")
PURPOSE = "Guard human oversight gates for promotion, alerts, routes, DB, and providers."
pytestmark = [pytest.mark.canon(item) for item in CANON_ITEMS]


@pytest.mark.parametrize("operation", ("explore", "collect", "working_note_create"))
def test_local_read_and_working_note_create_need_no_human(operation: str) -> None:
    decision = classify_human_oversight(operation)

    assert decision.oversight_level is HumanOversightLevel.NO_HUMAN_REQUIRED
    assert decision.requires_explicit_approval is False


@pytest.mark.parametrize(
    "operation",
    ("synthesize", "evidence_package_review", "eval_review", "audit_review"),
)
def test_review_operations_are_human_on_the_loop(operation: str) -> None:
    decision = classify_human_oversight(operation)

    assert decision.oversight_level is HumanOversightLevel.HUMAN_ON_THE_LOOP
    assert decision.requires_explicit_approval is False


@pytest.mark.parametrize(
    "operation",
    (
        "working_note_promote",
        "external_alert_sink_enablement",
        "external_alert_delivery",
        "route_promotion",
        "schema_migration_persisted_data",
        "runtime_provider_call",
        "answer_assertion_high_risk",
    ),
)
def test_high_blast_radius_operations_are_human_in_the_loop(operation: str) -> None:
    decision = classify_human_oversight(operation)

    assert decision.oversight_level is HumanOversightLevel.HUMAN_IN_THE_LOOP
    assert decision.requires_explicit_approval is True


def test_hidden_backend_api_risk_is_hard_stop() -> None:
    decision = classify_human_oversight(
        "adapter_development",
        risk_flags=("hidden_backend_api",),
    )

    assert decision.oversight_level is HumanOversightLevel.HARD_STOP
    assert decision.hard_stop_reasons == ("hidden_backend_api",)
