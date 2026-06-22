from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from research_x.codex_improvement.pipeline import (
    DEFAULT_CANDIDATES_DIR,
    DEFAULT_REJECTED_EDITS_PATH,
    DEFAULT_SIGNALS_PATH,
    DEFAULT_TRIAGE_JSONL_PATH,
    DEFAULT_TRIAGE_REPORT_PATH,
    capture_signal,
    create_candidate_reports,
    format_triage_report,
    read_jsonl,
    read_triage_jsonl,
    triage_signals,
    validate_candidate_dir,
    validate_signal,
    validate_triage_record,
    write_jsonl,
    write_text,
    write_triage_jsonl,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m research_x.codex_improvement",
        description="Local proposal-only ImprovementSignal pipeline.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    capture = subparsers.add_parser("capture", help="append one ImprovementSignal to JSONL")
    capture.add_argument("--out", type=Path, default=DEFAULT_SIGNALS_PATH)
    capture.add_argument("--source-type", required=True)
    capture.add_argument("--source-ref", required=True)
    capture.add_argument("--symptom", required=True)
    capture.add_argument("--root-cause-hypothesis", default="")
    capture.add_argument("--severity", default="medium")
    capture.add_argument("--project-scope", default="research_x")
    capture.add_argument("--proposed-change-type", default="no_change")
    capture.add_argument("--privacy-level", default="project_private")
    capture.add_argument("--status", default="new")
    capture.add_argument("--signal-id", default=None)
    capture.add_argument("--created-at", default=None)
    capture.add_argument("--affected-artifact", action="append", default=[])
    capture.add_argument("--fault-step", default="")
    capture.add_argument("--responsible-artifact", default="")
    capture.add_argument("--candidate-diff-ref", default="")
    capture.add_argument(
        "--replay-result",
        default=None,
        help='Replay result as a JSON object, for example {"status":"passed","ref":"tests"}',
    )
    capture.add_argument(
        "--qualifier-result",
        default=None,
        help='Qualifier result as a JSON object, for example {"status":"passed","ref":"manifest"}',
    )
    capture.add_argument("--human-decision", default="pending")
    capture.add_argument(
        "--evidence",
        action="append",
        default=[],
        help="Evidence as kind=ref or kind=ref#hash.",
    )
    capture.add_argument("--tag", action="append", default=[])

    triage = subparsers.add_parser("triage", help="triage ImprovementSignal JSONL")
    triage.add_argument("--signals", type=Path, default=DEFAULT_SIGNALS_PATH)
    triage.add_argument("--out", type=Path, default=DEFAULT_TRIAGE_REPORT_PATH)
    triage.add_argument("--triage-jsonl", type=Path, default=DEFAULT_TRIAGE_JSONL_PATH)
    triage.add_argument("--rejected-jsonl", type=Path, default=DEFAULT_REJECTED_EDITS_PATH)

    propose = subparsers.add_parser("propose", help="write proposal-only candidate reports")
    propose.add_argument("--triage-jsonl", type=Path, default=DEFAULT_TRIAGE_JSONL_PATH)
    propose.add_argument("--out-dir", type=Path, default=DEFAULT_CANDIDATES_DIR)

    validate = subparsers.add_parser("validate", help="validate signals, triage, and reports")
    validate.add_argument("--signals", type=Path, default=DEFAULT_SIGNALS_PATH)
    validate.add_argument("--triage-jsonl", type=Path, default=None)
    validate.add_argument("--candidate-dir", type=Path, default=None)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "capture":
        signal = capture_signal(
            source_type=args.source_type,
            source_ref=args.source_ref,
            symptom=args.symptom,
            root_cause_hypothesis=args.root_cause_hypothesis,
            severity=args.severity,
            project_scope=args.project_scope,
            proposed_change_type=args.proposed_change_type,
            privacy_level=args.privacy_level,
            status=args.status,
            affected_artifacts=tuple(args.affected_artifact),
            evidence=_parse_evidence_args(args.evidence),
            tags=tuple(args.tag),
            fault_step=args.fault_step,
            responsible_artifact=args.responsible_artifact,
            candidate_diff_ref=args.candidate_diff_ref,
            replay_result=_parse_json_object_arg(args.replay_result, "--replay-result"),
            qualifier_result=_parse_json_object_arg(args.qualifier_result, "--qualifier-result"),
            human_decision=args.human_decision,
            signal_id=args.signal_id,
            created_at=args.created_at,
        )
        errors = validate_signal(signal.as_dict())
        if errors:
            return _print_errors(errors)
        write_jsonl(args.out, [signal.as_dict()], append=True)
        print(f"captured {signal.signal_id} -> {args.out}")
        return 0

    if args.command == "triage":
        signals = read_jsonl(args.signals)
        errors = [error for signal in signals for error in validate_signal(signal)]
        if errors:
            return _print_errors(errors)
        decisions = triage_signals(signals)
        write_triage_jsonl(args.triage_jsonl, decisions)
        write_jsonl(
            args.rejected_jsonl,
            [
                decision.as_dict()
                for decision in decisions
                if decision.disposition == "rejected"
            ],
            append=True,
        )
        write_text(args.out, format_triage_report(decisions))
        print(
            f"triaged {len(decisions)} signals -> {args.out}, "
            f"{args.triage_jsonl}"
        )
        return 0

    if args.command == "propose":
        decisions = read_triage_jsonl(args.triage_jsonl)
        errors = [
            error
            for decision in decisions
            for error in validate_triage_record(decision.as_dict())
        ]
        if errors:
            return _print_errors(errors)
        paths = create_candidate_reports(decisions, args.out_dir)
        print(f"wrote {len(paths)} candidate reports -> {args.out_dir}")
        return 0

    if args.command == "validate":
        errors = []
        if args.signals.exists():
            errors.extend(
                error
                for signal in read_jsonl(args.signals)
                for error in validate_signal(signal)
            )
        else:
            errors.append(f"signals file missing: {args.signals}")
        if args.triage_jsonl is not None:
            if not args.triage_jsonl.exists():
                errors.append(f"triage file missing: {args.triage_jsonl}")
            else:
                errors.extend(
                    error
                    for decision in read_triage_jsonl(args.triage_jsonl)
                    for error in validate_triage_record(decision.as_dict())
                )
        if args.candidate_dir is not None:
            errors.extend(validate_candidate_dir(args.candidate_dir))
        if errors:
            return _print_errors(errors)
        print("improvement pipeline validation ok")
        return 0

    parser.error(f"unhandled command {args.command}")
    return 2


def _parse_evidence_args(values: list[str]) -> tuple[dict[str, str], ...]:
    evidence = []
    for value in values:
        if "=" not in value:
            raise SystemExit(f"--evidence must be kind=ref or kind=ref#hash: {value}")
        kind, ref_hash = value.split("=", 1)
        ref, sep, hash_value = ref_hash.partition("#")
        item = {"kind": kind, "ref": ref}
        if sep:
            item["hash"] = hash_value
        evidence.append(item)
    return tuple(evidence)


def _parse_json_object_arg(value: str | None, flag: str) -> dict[str, object] | None:
    if value is None:
        return None
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"{flag} must be a JSON object: {exc}") from exc
    if not isinstance(parsed, dict):
        raise SystemExit(f"{flag} must be a JSON object")
    return parsed


def _print_errors(errors: list[str]) -> int:
    for error in errors:
        print(f"ERROR: {error}", file=sys.stderr)
    return 1
