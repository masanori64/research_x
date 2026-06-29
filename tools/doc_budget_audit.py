from __future__ import annotations

import argparse
import json
from pathlib import Path

from research_x.control_artifacts.doc_budget import build_doc_budget_audit


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Audit research_x Markdown and WBS budget contracts.",
    )
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    payload = build_doc_budget_audit(args.project_root)
    text = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
    print(text)
    return 2 if _has_blocking_violations(payload) else 0


def _has_blocking_violations(payload: dict[str, object]) -> bool:
    summary = payload.get("summary")
    wbs = payload.get("wbs")
    if not isinstance(summary, dict) or not isinstance(wbs, dict):
        return True
    return any(
        int(summary.get(key, 0)) > 0
        for key in (
            "document_hard_ceiling_violation_count",
            "document_missing_required_section_count",
            "document_forbidden_section_count",
            "document_missing_required_term_count",
            "document_banned_fragment_count",
            "document_ordered_fragment_violation_count",
            "document_target_review_marker_missing_count",
            "wbs_semantic_violation_count",
        )
    ) or any(
        int(wbs.get(key, 0)) > 0
        for key in (
            "not_evidence_violation_count",
            "answer_support_allowed_violation_count",
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
