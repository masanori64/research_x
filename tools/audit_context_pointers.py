from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from research_x.memory.context_budget import (
    PointerAuditReport,
    verify_offload_directory,
    verify_pointer_map,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Audit context offload pointers without using providers."
    )
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--offload-dir", type=Path)
    target.add_argument("--pointer-map", type=Path)
    parser.add_argument("--json", action="store_true", help="write JSON report")
    args = parser.parse_args(argv)

    if args.offload_dir is not None:
        report = verify_offload_directory(args.offload_dir, base_dir=Path.cwd())
    else:
        report = verify_pointer_map(args.pointer_map, base_dir=Path.cwd())

    if args.json:
        print(json.dumps(report.as_dict(), ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(_format_report(report))
    return 1 if report.status == "failed" else 0


def _format_report(report: PointerAuditReport) -> str:
    lines = [
        f"source: {report.source_path}",
        f"kind: {report.source_kind}",
        f"status: {report.status}",
    ]
    if report.skipped_reason:
        lines.append(f"skipped_reason: {report.skipped_reason}")
    if report.results:
        lines.append("pointers:")
        for result in report.results:
            line = f"  - {result.pointer_id or '<missing>'}: {result.status}"
            if result.issues:
                line += f" issues={','.join(result.issues)}"
            lines.append(line)
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
