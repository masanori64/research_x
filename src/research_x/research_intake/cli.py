from __future__ import annotations

import argparse
import sys
from dataclasses import replace
from pathlib import Path

from research_x.research_intake.pipeline import (
    ALLOWED_NETWORK_MODES,
    DEFAULT_BRIEF_PATH,
    DEFAULT_PROFILE_PATH,
    DEFAULT_REGISTRY_PATH,
    DEFAULT_RUN_PATH,
    discover_candidates,
    format_research_brief,
    load_profile,
    load_registry,
    read_run_json,
    validate_configuration,
    validate_run,
    write_run_json,
    write_text,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m research_x.research_intake",
        description="Local-only dry-run research intake.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate = subparsers.add_parser("validate", help="validate profile and source registry")
    validate.add_argument("--profile", type=Path, default=DEFAULT_PROFILE_PATH)
    validate.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY_PATH)

    discover = subparsers.add_parser(
        "discover",
        help="produce dry-run candidates and metadata-only snapshots",
    )
    discover.add_argument("--profile", type=Path, default=DEFAULT_PROFILE_PATH)
    discover.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY_PATH)
    discover.add_argument("--out", type=Path, default=DEFAULT_RUN_PATH)
    discover.add_argument("--limit", type=int, default=10)
    discover.add_argument("--created-at", default=None)
    discover.add_argument(
        "--network-mode",
        choices=sorted(ALLOWED_NETWORK_MODES),
        default=None,
        help="override profile network_mode without enabling network or provider calls",
    )

    brief = subparsers.add_parser("brief", help="write a review brief from a discovery run")
    brief.add_argument("--run", type=Path, default=DEFAULT_RUN_PATH)
    brief.add_argument("--out", type=Path, default=DEFAULT_BRIEF_PATH)
    brief.add_argument("--objective", default="")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "validate":
        profile = load_profile(args.profile)
        registry = load_registry(args.registry)
        errors = validate_configuration(profile, registry)
        if errors:
            return _print_errors(errors)
        print("research intake configuration ok")
        return 0

    if args.command == "discover":
        profile = load_profile(args.profile)
        if args.network_mode is not None:
            profile = replace(profile, network_mode=args.network_mode)
        registry = load_registry(args.registry)
        errors = validate_configuration(profile, registry)
        if errors:
            return _print_errors(errors)
        try:
            run = discover_candidates(
                profile,
                registry,
                limit=args.limit,
                created_at=args.created_at,
            )
        except ValueError as exc:
            return _print_errors([str(exc)])
        run_errors = validate_run(run)
        if run_errors:
            return _print_errors(run_errors)
        write_run_json(args.out, run)
        print(
            f"wrote {len(run.candidates)} dry-run candidates -> {args.out}; "
            "provider_calls=0 network_calls=0"
        )
        return 0

    if args.command == "brief":
        run = read_run_json(args.run)
        errors = validate_run(run)
        if errors:
            return _print_errors(errors)
        text = format_research_brief(run, objective=args.objective)
        write_text(args.out, text)
        print(f"wrote research brief -> {args.out}")
        return 0

    parser.error(f"unhandled command {args.command}")
    return 2


def _print_errors(errors: list[str]) -> int:
    for error in errors:
        print(f"ERROR: {error}", file=sys.stderr)
    return 1
