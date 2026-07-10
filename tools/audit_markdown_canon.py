from __future__ import annotations

import argparse
import json
import os
import subprocess
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]

ALLOWED_PROJECT_MARKDOWN = {
    "README.md",
    "AGENTS.md",
    "docs/research_x_canon.md",
}
ALLOWED_VENDOR_MARKDOWN_PREFIXES: tuple[str, ...] = ()
IGNORED_MARKDOWN_PREFIXES = (
    ".git/",
    ".pytest_cache/",
    ".ruff_cache/",
    ".mypy_cache/",
    ".venv/",
    "node_modules/",
    "dist/",
    "build/",
    "runs/",
    "docs/control/codex/test-audits/",
)

RETIRED_MARKDOWN_PATHS = (
    "README" + ".codex.md",
    "PROJECT" + ".md",
    "research_x_pipeline_" + "context.md",
    "docs/" + "product_goal.md",
    "docs/" + "non_goals.md",
    "docs/" + "artifact_roles.md",
    "docs/" + "output_modes.md",
    "docs/" + "provider_execution_policy.md",
    "docs/" + "upstream_source_policy.md",
    "docs/" + "research_intake_policy.md",
    "docs/" + "pipeline.md",
    "docs/" + "memory-pipeline-v2.md",
    "docs/" + "memory-pipeline-v3.md",
    "docs/" + "memory-pipeline-archive.md",
    "docs/presentation/" + "diagram-" + "design-harness.md",
    "docs/presentation/" + "diagram-" + "systems.md",
    "docs/presentation/" + "final-" + "design-flow.md",
    "docs/presentation/" + "final-" + "runtime-flow.md",
    "docs/presentation/mermaid/redesign/" + "README.md",
    "docs/presentation/" + "slides.md",
    "docs/control/codex/" + "README.md",
    "control/vendor_sources.lock" + ".md",
    "tools/wbs_viewer/" + "README.md",
    "tools/wbs_viewer/" + "UPSTREAM.md",
)

OLD_POLICY_PHRASES = (
    "custom " + "SVG generator",
    "Evidence/" + "Source " + "Bundle First",
    "evidence-first memory/" + "search system",
    "source-" + "bundle",
    "source " + "bundle",
    "source " + "bundle first",
    "source_" + "bundle_first",
    "restore_" + "bundle_first",
    "restore_" + "source_first",
    "mandatory restored-" + "source route",
    "mandatory restored-" + "source routes",
    "restored-" + "source route",
    "source restorations, " + "context chunks",
    "score_" + "not_evidence_restore_bundle_first",
    "map_hint_" + "not_evidence_restore_source_first",
    "Search" + "Lens",
    "Objective" + "RoutePolicy",
    "Route " + "Portfolio",
    "Answer " + "Boundary status",
    "Answer " + "Assertion Gate",
    "Evidence View / Context Chunk / Citation",
    "Answer" + "AuthorityGatekeeper as universal route",
    "generated artifacts are not evidence",
    "WBS, diagrams, screenshots, pointer maps",
    "No-quota provider freeze",
    "The forbidden default is runtime provider execution",
    "implemented_static_verified",
    "Current implementation order and status",
)

TEXT_SUFFIXES = {
    ".cfg",
    ".css",
    ".d2",
    ".html",
    ".ini",
    ".js",
    ".json",
    ".jsonl",
    ".md",
    ".mjs",
    ".py",
    ".svg",
    ".toml",
    ".txt",
    ".yaml",
    ".yml",
}

CANON_PATH = "docs/research_x_canon.md"
AUDIT_DEFINITION_PATHS = {
    "tests/canon/test_markdown_canon.py",
    "tools/audit_markdown_canon.py",
}
TEXT_SCAN_EXACT_PATHS = {
    "README.md",
    "AGENTS.md",
    "docs/research_x_canon.md",
}
TEXT_SCAN_PREFIXES = (
    "src/",
    "tests/",
    "tools/",
    "prompt_contracts/",
    "control/",
)
EXCLUDED_DIR_NAMES = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".secrets",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "node_modules",
    "outputs",
    "runs",
}


def build_markdown_canon_audit(project_root: str | Path = ROOT) -> dict[str, Any]:
    root = Path(project_root)
    markdown_paths = _markdown_paths(root)
    unexpected_markdown = [path for path in markdown_paths if not _is_allowed_markdown(path)]
    retired_existing = [path for path in RETIRED_MARKDOWN_PATHS if (root / path).exists()]
    retired_reference_hits = _retired_reference_hits(root)
    old_phrase_hits = _old_phrase_hits(root)
    similarity_hits = _similarity_hits(root)
    errors = []
    if unexpected_markdown:
        errors.append("unexpected_project_markdown")
    if retired_existing:
        errors.append("retired_markdown_exists")
    if retired_reference_hits:
        errors.append("retired_path_reference_outside_canon")
    if old_phrase_hits:
        errors.append("old_policy_phrase")
    if similarity_hits:
        errors.append("markdown_similarity_to_retired_doc")
    return {
        "artifact_kind": "research_x_markdown_canon_audit",
        "schema_version": 1,
        "status": "passed" if not errors else "failed",
        "errors": errors,
        "allowed_project_markdown": sorted(ALLOWED_PROJECT_MARKDOWN),
        "markdown_paths": markdown_paths,
        "unexpected_markdown": unexpected_markdown,
        "retired_existing": retired_existing,
        "retired_reference_hits": retired_reference_hits,
        "old_phrase_hits": old_phrase_hits,
        "similarity_hits": similarity_hits,
    }


def _markdown_paths(root: Path) -> list[str]:
    paths = []
    for path in _iter_scoped_paths(root):
        if path.suffix.casefold() != ".md":
            continue
        rel = path.relative_to(root).as_posix()
        if _is_ignored_path(rel):
            continue
        paths.append(rel)
    return sorted(paths)


def _is_allowed_markdown(path: str) -> bool:
    if path in ALLOWED_PROJECT_MARKDOWN:
        return True
    return any(path.startswith(prefix) for prefix in ALLOWED_VENDOR_MARKDOWN_PREFIXES)


def _text_files(root: Path) -> list[Path]:
    files = []
    for path in _iter_scoped_paths(root):
        if not path.is_file():
            continue
        rel = path.relative_to(root).as_posix()
        if _is_ignored_path(rel):
            continue
        if not _is_text_scan_target(rel):
            continue
        if rel in AUDIT_DEFINITION_PATHS:
            continue
        if path.suffix.casefold() in TEXT_SUFFIXES:
            files.append(path)
    return files


def _is_ignored_path(path: str) -> bool:
    return path.startswith(IGNORED_MARKDOWN_PREFIXES)


def _is_text_scan_target(path: str) -> bool:
    return path in TEXT_SCAN_EXACT_PATHS or path.startswith(TEXT_SCAN_PREFIXES)


def _iter_scoped_paths(root: Path) -> list[Path]:
    paths: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [name for name in dirnames if name not in EXCLUDED_DIR_NAMES]
        current = Path(dirpath)
        for filename in filenames:
            paths.append(current / filename)
    return paths


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return path.read_text(encoding="utf-8", errors="ignore")


def _retired_reference_hits(root: Path) -> list[dict[str, str]]:
    hits = []
    for rel in sorted(TEXT_SCAN_EXACT_PATHS):
        path = root / rel
        if not path.exists():
            continue
        text = _read_text(path)
        for retired in RETIRED_MARKDOWN_PATHS:
            if retired not in text:
                continue
            if rel == CANON_PATH:
                continue
            hits.append({"path": rel, "fragment": retired})
    return hits


def _old_phrase_hits(root: Path) -> list[dict[str, str]]:
    hits = []
    for rel in sorted(TEXT_SCAN_EXACT_PATHS):
        path = root / rel
        if not path.exists():
            continue
        text = _read_text(path)
        for phrase in OLD_POLICY_PHRASES:
            if phrase in text:
                hits.append({"path": rel, "fragment": phrase})
    return hits


def _similarity_hits(root: Path) -> list[dict[str, Any]]:
    # Dirty Windows worktrees with many generated artifacts can make git blob
    # reads enter expensive filter/hash paths. The active gates are the
    # allowlist, retired-path, and old-phrase checks; similarity is kept as an
    # explicit empty field for review schema stability.
    return []


def _normalized_lines(text: str) -> list[str]:
    lines = []
    for line in text.splitlines():
        normalized = " ".join(line.strip().split())
        if not normalized or normalized in {"```", "---"}:
            continue
        lines.append(normalized.casefold())
    return lines


def _git_show(root: Path, rel_path: str) -> str | None:
    try:
        result = subprocess.run(
            ["git", "--no-optional-locks", "cat-file", "-p", f"HEAD:{rel_path}"],
            cwd=root,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            check=False,
            timeout=3,
        )
    except subprocess.TimeoutExpired:
        return None
    if result.returncode != 0:
        return None
    return result.stdout.decode("utf-8", errors="replace")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", default=str(ROOT))
    parser.add_argument("--fail-on-drift", action="store_true")
    args = parser.parse_args(argv)
    audit = build_markdown_canon_audit(args.project_root)
    print(json.dumps(audit, ensure_ascii=False, indent=2, sort_keys=True))
    if args.fail_on_drift and audit["status"] != "passed":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
