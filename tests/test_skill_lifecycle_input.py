from __future__ import annotations

from research_x.codex_improvement.skill_lifecycle import (
    format_skill_lifecycle_report,
    skill_lifecycle_gate_status,
    validate_skill_lifecycle_input,
)


def _record() -> dict[str, object]:
    return {
        "lifecycle_action": "refine",
        "trigger": "review_finding",
        "responsible_artifact": ".agents/skills/research-x-skillization-intake/SKILL.md",
        "candidate_diff_ref": ".codex/improvement/candidates/sig.diff",
        "examples_ref": "tests/fixtures/skill_lifecycle/example.json",
        "tests_ref": "tests/test_skill_lifecycle_input.py",
        "replay_result": {"status": "passed", "ref": "tests/test_skill_lifecycle_input.py"},
        "qualifier_result": {"status": "passed", "ref": "scripts/validate_skill_manifest.py"},
        "human_decision": "accepted",
        "source_review_required": False,
        "auto_apply_allowed": False,
        "source_origin": "repo_owned",
    }


def test_skill_lifecycle_input_accepts_proposal_only_gate_record() -> None:
    record = _record()

    assert validate_skill_lifecycle_input(record) == []
    assert skill_lifecycle_gate_status(record) == "accepted"

    report = format_skill_lifecycle_report(record)
    assert "Proposal Only" in report
    assert "Do not auto-apply" in report
    assert "Auto apply allowed: `false`" in report


def test_third_party_lifecycle_input_requires_source_review() -> None:
    record = _record()
    record["source_origin"] = "third_party"
    record["source_review_required"] = False

    errors = validate_skill_lifecycle_input(record)

    assert (
        ".agents/skills/research-x-skillization-intake/SKILL.md: "
        "third_party source requires source_review_required true"
    ) in errors


def test_auto_apply_allowed_is_rejected() -> None:
    record = _record()
    record["auto_apply_allowed"] = True

    errors = validate_skill_lifecycle_input(record)

    assert (
        ".agents/skills/research-x-skillization-intake/SKILL.md: "
        "auto_apply_allowed must be false"
    ) in errors


def test_refine_stays_pending_without_replay_qualifier_or_human_decision() -> None:
    record = _record()
    record["replay_result"] = {"status": "not_run"}
    record["qualifier_result"] = {"status": "passed"}
    record["human_decision"] = "accepted"
    assert skill_lifecycle_gate_status(record) == "pending"

    record = _record()
    record["human_decision"] = "pending"
    assert skill_lifecycle_gate_status(record) == "pending"
