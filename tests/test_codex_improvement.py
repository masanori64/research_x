from __future__ import annotations

import json

from research_x.codex_improvement.cli import main
from research_x.codex_improvement.pipeline import (
    capture_signal,
    create_candidate_reports,
    format_triage_report,
    read_jsonl,
    triage_signals,
    validate_candidate_dir,
    validate_signal,
    validate_triage_record,
    write_jsonl,
)


def test_capture_signal_validation_and_jsonl_roundtrip(tmp_path) -> None:
    signal = capture_signal(
        signal_id="sig_unit",
        created_at="2026-06-10T00:00:00+00:00",
        source_type="provider_gate_violation",
        source_ref="tests/unit",
        severity="high",
        project_scope="research_x",
        symptom="Codex attempted a real provider call during provider freeze",
        root_cause_hypothesis="provider gate was not checked",
        affected_artifacts=("AGENTS.md", ".agents/skills/research-x-provider-gate/SKILL.md"),
        proposed_change_type="provider_policy_update",
        evidence=({"kind": "test", "ref": "tests/test_provider_gate.py"},),
        privacy_level="project_private",
        tags=("provider", "freeze"),
    )

    assert validate_signal(signal.as_dict()) == []
    path = tmp_path / "signals.jsonl"
    write_jsonl(path, [signal.as_dict()])

    rows = read_jsonl(path)
    assert rows == [signal.as_dict()]


def test_triage_security_signal_requires_review_and_no_provider_gate() -> None:
    signal = capture_signal(
        signal_id="sig_provider",
        created_at="2026-06-10T00:00:00+00:00",
        source_type="provider_gate_violation",
        source_ref="workflow:1",
        severity="blocker",
        project_scope="research_x",
        symptom="Real OpenAI provider quota would be consumed",
        proposed_change_type="no_change",
        evidence=({"kind": "trace", "ref": "runs/workflow.jsonl"},),
        privacy_level="project_private",
    )

    decision = triage_signals([signal.as_dict()])[0]

    assert decision.triage_category == "security_budget_blocker"
    assert decision.proposed_change_type == "security_review"
    assert decision.disposition == "candidate_report"
    assert decision.human_review_required is True
    assert decision.security_review_required is True
    assert decision.provider_freeze_touched is True
    assert "no_provider_calls" in decision.gates


def test_no_change_signal_goes_to_rejected_buffer() -> None:
    signal = capture_signal(
        signal_id="sig_noise",
        created_at="2026-06-10T00:00:00+00:00",
        source_type="manual",
        source_ref="note",
        severity="low",
        project_scope="research_x",
        symptom="One-off note without durable signal",
        proposed_change_type="no_change",
        evidence=({"kind": "note", "ref": "manual"},),
        privacy_level="project_private",
    )

    decision = triage_signals([signal.as_dict()])[0]

    assert decision.triage_category == "no_change"
    assert decision.disposition == "rejected"


def test_candidate_reports_are_proposal_only(tmp_path) -> None:
    signal = capture_signal(
        signal_id="sig_doc",
        created_at="2026-06-10T00:00:00+00:00",
        source_type="doc_drift",
        source_ref="docs",
        severity="medium",
        project_scope="research_x",
        symptom="PROJECT.md contains detailed architecture instead of tracker state",
        proposed_change_type="docs_update",
        evidence=({"kind": "file", "ref": "PROJECT.md"},),
        privacy_level="project_private",
    )
    decision = triage_signals([signal.as_dict()])[0]

    paths = create_candidate_reports([decision], tmp_path / "candidates")

    assert len(paths) == 1
    text = paths[0].read_text(encoding="utf-8")
    assert "Proposal Only" in text
    assert "Do not auto-apply" in text
    assert "Fault Localization" in text
    assert "Replay" in text
    assert "Qualifier" in text
    assert validate_candidate_dir(tmp_path / "candidates") == []


def test_qualifier_fields_roundtrip_into_triage_and_candidate_report(tmp_path) -> None:
    signal = capture_signal(
        signal_id="sig_qualifier",
        created_at="2026-06-22T00:00:00+00:00",
        source_type="skill_route_miss",
        source_ref="transcript:route",
        severity="high",
        project_scope="research_x",
        symptom="Skill route missed a provider-gated embedding request",
        root_cause_hypothesis="route wording did not match the Skill trigger",
        affected_artifacts=(".agents/skills/research-x-provider-gate/SKILL.md",),
        proposed_change_type="skill_update",
        evidence=({"kind": "transcript", "ref": "turn-4"},),
        privacy_level="project_private",
        fault_step="compare the request wording with provider-gate trigger coverage",
        responsible_artifact=".agents/skills/research-x-provider-gate/SKILL.md",
        candidate_diff_ref=".codex/improvement/candidates/sig_qualifier.diff",
        replay_result={"status": "passed", "ref": "tests/test_skill_manifest.py"},
        qualifier_result={"status": "passed", "ref": "scripts/validate_skill_manifest.py"},
        human_decision="pending",
    )

    assert validate_signal(signal.as_dict()) == []
    decision = triage_signals([signal.as_dict()])[0]

    assert validate_triage_record(decision.as_dict()) == []
    assert decision.fault_step == "compare the request wording with provider-gate trigger coverage"
    assert decision.responsible_artifact == ".agents/skills/research-x-provider-gate/SKILL.md"
    assert decision.candidate_diff_ref == ".codex/improvement/candidates/sig_qualifier.diff"
    assert decision.replay_result["status"] == "passed"
    assert decision.qualifier_result["status"] == "passed"
    assert decision.human_decision == "pending"

    report = format_triage_report([decision])
    assert "Qualifier |" in report
    assert "Replay result: `status=passed, ref=tests/test_skill_manifest.py`" in report

    paths = create_candidate_reports([decision], tmp_path / "candidates")
    text = paths[0].read_text(encoding="utf-8")
    assert "Candidate diff reference" in text
    assert "- Status: `passed`" in text
    assert "- Ref: `scripts/validate_skill_manifest.py`" in text
    assert validate_candidate_dir(tmp_path / "candidates") == []


def test_invalid_qualifier_fields_are_rejected() -> None:
    signal = capture_signal(
        signal_id="sig_bad_qualifier",
        created_at="2026-06-22T00:00:00+00:00",
        source_type="manual",
        source_ref="manual",
        severity="medium",
        project_scope="research_x",
        symptom="Invalid replay status should not be accepted",
        proposed_change_type="code_change",
        evidence=({"kind": "note", "ref": "manual"},),
        privacy_level="project_private",
        replay_result={"status": "maybe"},
        human_decision="auto_apply",
    )

    errors = validate_signal(signal.as_dict())

    assert "sig_bad_qualifier: invalid replay_result.status 'maybe'" in errors
    assert "sig_bad_qualifier: invalid human_decision 'auto_apply'" in errors


def test_triage_report_marks_proposal_only() -> None:
    signal = capture_signal(
        signal_id="sig_eval",
        created_at="2026-06-10T00:00:00+00:00",
        source_type="eval_failure",
        source_ref="eval:route",
        severity="medium",
        project_scope="research_x",
        symptom="Skill route false positive was not covered",
        proposed_change_type="eval_case",
        evidence=({"kind": "eval", "ref": "route_cases.jsonl"},),
        privacy_level="project_private",
    )

    report = format_triage_report(triage_signals([signal.as_dict()]))

    assert "proposal-only" in report
    assert "sig_eval" in report
    assert "evaluation_gap" in report


def test_cli_capture_triage_propose_validate_roundtrip(tmp_path, capsys) -> None:
    signals = tmp_path / "signals.jsonl"
    triage_report = tmp_path / "triage.md"
    triage_jsonl = tmp_path / "triage.jsonl"
    rejected = tmp_path / "rejected.jsonl"
    candidates = tmp_path / "candidates"

    assert (
        main(
            [
                "capture",
                "--out",
                str(signals),
                "--signal-id",
                "sig_cli",
                "--created-at",
                "2026-06-10T00:00:00+00:00",
                "--source-type",
                "skill_route_miss",
                "--source-ref",
                "prompt:1",
                "--symptom",
                "Provider gate skill did not fire for embedding request",
                "--proposed-change-type",
                "skill_update",
                "--affected-artifact",
                ".agents/skills/research-x-provider-gate/SKILL.md",
                "--fault-step",
                "compare provider request with skill trigger",
                "--responsible-artifact",
                ".agents/skills/research-x-provider-gate/SKILL.md",
                "--candidate-diff-ref",
                ".codex/improvement/candidates/sig_cli.diff",
                "--replay-result",
                '{"status":"passed","ref":"tests/test_skill_manifest.py"}',
                "--qualifier-result",
                '{"status":"passed","ref":"scripts/validate_skill_manifest.py"}',
                "--evidence",
                "transcript=turn-1",
            ]
        )
        == 0
    )
    assert signals.exists()

    assert (
        main(
            [
                "triage",
                "--signals",
                str(signals),
                "--out",
                str(triage_report),
                "--triage-jsonl",
                str(triage_jsonl),
                "--rejected-jsonl",
                str(rejected),
            ]
        )
        == 0
    )
    assert triage_report.exists()
    assert triage_jsonl.exists()

    assert main(["propose", "--triage-jsonl", str(triage_jsonl), "--out-dir", str(candidates)]) == 0
    assert (candidates / "sig_cli.md").exists()

    assert (
        main(
            [
                "validate",
                "--signals",
                str(signals),
                "--triage-jsonl",
                str(triage_jsonl),
                "--candidate-dir",
                str(candidates),
            ]
        )
        == 0
    )
    assert "validation ok" in capsys.readouterr().out

    rows = [json.loads(line) for line in triage_jsonl.read_text(encoding="utf-8").splitlines()]
    assert rows[0]["human_review_required"] is True
    assert rows[0]["replay_result"]["status"] == "passed"
    assert rows[0]["qualifier_result"]["status"] == "passed"
