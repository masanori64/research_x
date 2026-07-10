from __future__ import annotations

import json
import re
import tomllib
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

DEFAULT_FACTS_PATH = Path("docs/presentation/project-facts.json")

_EVIDENCE_LIST_KEYS = {"evidence", "source_files"}
_FORBIDDEN_EVIDENCE_PREFIXES = (
    ".codex/",
    "docs/pdg/",
    "docs/presentation/assets/",
    "docs/presentation/diagrams/",
    "docs/presentation/dist/",
    "outputs/",
    "runs/",
    "tools/pdgkit_canary/",
)
_FORBIDDEN_EVIDENCE_EXACT = {
    "docs/presentation/project-facts.json",
    "docs/presentation/deck.marp",
}
_FORBIDDEN_EVIDENCE_SUFFIXES = {
    ".d2",
    ".gif",
    ".html",
    ".jpeg",
    ".jpg",
    ".pdf",
    ".png",
    ".pptx",
    ".svg",
    ".webp",
}
_DRIVE_PREFIX = re.compile(r"^[A-Za-z]:")


@dataclass(frozen=True)
class PresentationFactsValidation:
    facts_path: str | None
    ok: bool
    errors: tuple[str, ...]
    warnings: tuple[str, ...]
    summary: dict[str, object]

    def as_dict(self) -> dict[str, object]:
        return {
            "facts_path": self.facts_path,
            "ok": self.ok,
            "errors": list(self.errors),
            "warnings": list(self.warnings),
            "summary": self.summary,
        }


def load_presentation_facts(path: str | Path = DEFAULT_FACTS_PATH) -> dict[str, Any]:
    facts_path = Path(path)
    data = json.loads(facts_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{facts_path} must contain a JSON object")
    return data


def validate_presentation_facts(
    path: str | Path = DEFAULT_FACTS_PATH,
    *,
    repo_root: str | Path | None = None,
) -> PresentationFactsValidation:
    facts_path = Path(path)
    root = Path(repo_root or Path.cwd()).resolve()
    if not facts_path.exists():
        return _validation_result(
            facts_path=facts_path,
            errors=[f"facts file not found: {facts_path.as_posix()}"],
            warnings=[],
            evidence_files=[],
            data={},
        )
    try:
        data = load_presentation_facts(facts_path)
    except (json.JSONDecodeError, ValueError) as exc:
        return _validation_result(
            facts_path=facts_path,
            errors=[f"invalid facts JSON: {exc}"],
            warnings=[],
            evidence_files=[],
            data={},
        )
    return validate_presentation_facts_data(data, repo_root=root, facts_path=facts_path)


def validate_presentation_facts_data(
    data: Mapping[str, Any],
    *,
    repo_root: str | Path | None = None,
    facts_path: str | Path | None = None,
) -> PresentationFactsValidation:
    root = Path(repo_root or Path.cwd()).resolve()
    errors: list[str] = []
    warnings: list[str] = []
    evidence_files: set[str] = set()

    _validate_required_shape(data, errors)
    _validate_claims(data, errors)
    _validate_unknowns(data, errors)
    _validate_evidence_lists(data, repo_root=root, errors=errors, evidence_files=evidence_files)
    _validate_pyproject_alignment(data, repo_root=root, errors=errors)
    _validate_package_alignment(data, repo_root=root, errors=errors)

    return _validation_result(
        facts_path=Path(facts_path) if facts_path is not None else None,
        errors=errors,
        warnings=warnings,
        evidence_files=sorted(evidence_files),
        data=data,
    )


def format_presentation_facts_validation(result: PresentationFactsValidation) -> str:
    if result.ok:
        return (
            "presentation facts ok: "
            f"claims={result.summary['claims']} "
            f"slide_candidates={result.summary['slide_candidates']} "
            f"unknowns={result.summary['unknowns']} "
            f"evidence_files={result.summary['evidence_files']}"
        )

    lines = ["presentation facts invalid:"]
    lines.extend(f"- {error}" for error in result.errors)
    if result.warnings:
        lines.append("warnings:")
        lines.extend(f"- {warning}" for warning in result.warnings)
    return "\n".join(lines)


def _validate_required_shape(data: Mapping[str, Any], errors: list[str]) -> None:
    if data.get("schema_version") != 1:
        errors.append("/schema_version must be 1")

    project = data.get("project")
    if not isinstance(project, Mapping):
        errors.append("/project must be an object")
    else:
        for key in ("name", "one_liner", "purpose", "audience", "scope"):
            _require_non_empty_string(project, key, f"/project/{key}", errors)

    runtime = data.get("runtime_surfaces")
    if not isinstance(runtime, Mapping):
        errors.append("/runtime_surfaces must be an object")
    else:
        if not isinstance(runtime.get("python"), Mapping):
            errors.append("/runtime_surfaces/python must be an object")
        if not isinstance(runtime.get("node"), Mapping):
            errors.append("/runtime_surfaces/node must be an object")

    database = data.get("database")
    if not isinstance(database, Mapping):
        errors.append("/database must be an object")
    elif not isinstance(database.get("exists"), bool):
        errors.append("/database/exists must be a boolean")

    for key in (
        "tech_stack",
        "entrypoints",
        "modules",
        "boundaries",
        "data_stores",
        "external_dependencies",
        "key_flows",
        "claims",
        "unknowns",
    ):
        value = data.get(key)
        if not isinstance(value, list):
            errors.append(f"/{key} must be a list")
        elif not value and key != "unknowns":
            errors.append(f"/{key} must not be empty")


def _validate_claims(data: Mapping[str, Any], errors: list[str]) -> None:
    claims = data.get("claims")
    if not isinstance(claims, list):
        return

    seen: set[str] = set()
    unknown_ids = {
        item.get("id")
        for item in data.get("unknowns", [])
        if isinstance(item, Mapping) and isinstance(item.get("id"), str)
    }
    for index, claim in enumerate(claims):
        pointer = f"/claims/{index}"
        if not isinstance(claim, Mapping):
            errors.append(f"{pointer} must be an object")
            continue
        claim_id = claim.get("id")
        if not isinstance(claim_id, str) or not claim_id.strip():
            errors.append(f"{pointer}/id must be a non-empty string")
        elif claim_id in seen:
            errors.append(f"{pointer}/id duplicates claim id {claim_id}")
        else:
            seen.add(claim_id)
        _require_non_empty_string(claim, "claim", f"{pointer}/claim", errors)
        if not isinstance(claim.get("slide_candidate"), bool):
            errors.append(f"{pointer}/slide_candidate must be a boolean")
        evidence = claim.get("evidence")
        if not isinstance(evidence, list) or not evidence:
            errors.append(f"{pointer}/evidence must list repository-file evidence")
        if claim.get("unknown_id") in unknown_ids or claim_id in unknown_ids:
            errors.append(f"{pointer} promotes unknown {claim.get('unknown_id') or claim_id}")


def _validate_unknowns(data: Mapping[str, Any], errors: list[str]) -> None:
    unknowns = data.get("unknowns")
    if not isinstance(unknowns, list):
        return

    seen: set[str] = set()
    for index, unknown in enumerate(unknowns):
        pointer = f"/unknowns/{index}"
        if not isinstance(unknown, Mapping):
            errors.append(f"{pointer} must be an object")
            continue
        unknown_id = unknown.get("id")
        if not isinstance(unknown_id, str) or not unknown_id.strip():
            errors.append(f"{pointer}/id must be a non-empty string")
        elif unknown_id in seen:
            errors.append(f"{pointer}/id duplicates unknown id {unknown_id}")
        else:
            seen.add(unknown_id)
        _require_non_empty_string(unknown, "question", f"{pointer}/question", errors)
        _require_non_empty_string(unknown, "reason", f"{pointer}/reason", errors)
        if unknown.get("promoted_to_claim") is not False:
            errors.append(f"{pointer}/promoted_to_claim must be false")


def _validate_evidence_lists(
    data: Mapping[str, Any],
    *,
    repo_root: Path,
    errors: list[str],
    evidence_files: set[str],
) -> None:
    for pointer, values in _iter_named_lists(data, _EVIDENCE_LIST_KEYS):
        if not isinstance(values, list):
            errors.append(f"{pointer} must be a list")
            continue
        if not values:
            errors.append(f"{pointer} must not be empty")
            continue
        for index, raw_path in enumerate(values):
            normalized = _validate_evidence_path(
                raw_path,
                pointer=f"{pointer}/{index}",
                repo_root=repo_root,
                errors=errors,
            )
            if normalized is not None:
                evidence_files.add(normalized)


def _validate_evidence_path(
    raw_path: object,
    *,
    pointer: str,
    repo_root: Path,
    errors: list[str],
) -> str | None:
    if not isinstance(raw_path, str) or not raw_path.strip():
        errors.append(f"{pointer} must be a non-empty repository-relative path")
        return None
    candidate = raw_path.replace("\\", "/").strip()
    if "://" in candidate:
        errors.append(f"{pointer} must not be a URL: {raw_path}")
        return None
    if candidate.startswith("/") or _DRIVE_PREFIX.match(candidate):
        errors.append(f"{pointer} must be repository-relative: {raw_path}")
        return None

    posix_path = PurePosixPath(candidate)
    if ".." in posix_path.parts:
        errors.append(f"{pointer} must not traverse parents: {raw_path}")
        return None
    normalized = posix_path.as_posix()
    if _is_forbidden_evidence(normalized):
        errors.append(f"{pointer} uses generated/control artifact as evidence: {normalized}")
        return None

    absolute = (repo_root / Path(*posix_path.parts)).resolve()
    try:
        absolute.relative_to(repo_root)
    except ValueError:
        errors.append(f"{pointer} escapes repository root: {raw_path}")
        return None
    if not absolute.is_file():
        errors.append(f"{pointer} evidence file not found: {normalized}")
        return None
    return normalized


def _is_forbidden_evidence(path: str) -> bool:
    if path in _FORBIDDEN_EVIDENCE_EXACT:
        return True
    if any(path.startswith(prefix) for prefix in _FORBIDDEN_EVIDENCE_PREFIXES):
        return True
    return PurePosixPath(path).suffix.lower() in _FORBIDDEN_EVIDENCE_SUFFIXES


def _validate_pyproject_alignment(
    data: Mapping[str, Any],
    *,
    repo_root: Path,
    errors: list[str],
) -> None:
    pyproject_path = repo_root / "pyproject.toml"
    if not pyproject_path.exists():
        return
    pyproject = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))
    project = pyproject.get("project", {})
    runtime_python = _mapping(data, "runtime_surfaces", "python")
    if runtime_python:
        declared_requires = runtime_python.get("requires")
        actual_requires = project.get("requires-python")
        if declared_requires != actual_requires:
            errors.append(
                "/runtime_surfaces/python/requires must match pyproject.toml "
                f"requires-python ({actual_requires})"
            )

    entrypoints = data.get("entrypoints")
    if not isinstance(entrypoints, list):
        return
    by_name = {
        item.get("name"): item
        for item in entrypoints
        if isinstance(item, Mapping) and isinstance(item.get("name"), str)
    }
    for name, target in project.get("scripts", {}).items():
        entrypoint = by_name.get(name)
        if not isinstance(entrypoint, Mapping):
            errors.append(f"/entrypoints must include pyproject script {name}")
            continue
        if entrypoint.get("target") != target:
            errors.append(
                f"/entrypoints/{name}/target must match pyproject.toml target {target}"
            )


def _validate_package_alignment(
    data: Mapping[str, Any],
    *,
    repo_root: Path,
    errors: list[str],
) -> None:
    package_path = repo_root / "package.json"
    if not package_path.exists():
        return
    package = json.loads(package_path.read_text(encoding="utf-8"))
    node = _mapping(data, "runtime_surfaces", "node")
    if not node:
        return

    declared_scripts = set(_string_items(node.get("scripts")))
    actual_scripts = set(package.get("scripts", {}))
    if not actual_scripts <= declared_scripts:
        missing = ", ".join(sorted(actual_scripts - declared_scripts))
        errors.append(f"/runtime_surfaces/node/scripts missing package scripts: {missing}")

    declared_dependencies = set(_string_items(node.get("dependencies")))
    actual_dependencies = set(package.get("devDependencies", {}))
    if not actual_dependencies <= declared_dependencies:
        missing = ", ".join(sorted(actual_dependencies - declared_dependencies))
        errors.append(
            "/runtime_surfaces/node/dependencies missing package dependencies: "
            f"{missing}"
        )


def _validation_result(
    *,
    facts_path: Path | None,
    errors: Iterable[str],
    warnings: Iterable[str],
    evidence_files: Iterable[str],
    data: Mapping[str, Any],
) -> PresentationFactsValidation:
    claims = data.get("claims", []) if isinstance(data, Mapping) else []
    unknowns = data.get("unknowns", []) if isinstance(data, Mapping) else []
    claim_items = claims if isinstance(claims, list) else []
    unknown_items = unknowns if isinstance(unknowns, list) else []
    slide_candidates = sum(
        1 for claim in claim_items if isinstance(claim, Mapping) and claim.get("slide_candidate")
    )
    evidence_file_list = list(evidence_files)
    error_tuple = tuple(errors)
    warning_tuple = tuple(warnings)
    return PresentationFactsValidation(
        facts_path=facts_path.as_posix() if facts_path is not None else None,
        ok=not error_tuple,
        errors=error_tuple,
        warnings=warning_tuple,
        summary={
            "claims": len(claim_items),
            "slide_candidates": slide_candidates,
            "unknowns": len(unknown_items),
            "evidence_files": len(evidence_file_list),
            "evidence_file_paths": evidence_file_list,
        },
    )


def _iter_named_lists(
    value: Any,
    keys: set[str],
    *,
    pointer: str = "",
) -> Iterable[tuple[str, Any]]:
    if isinstance(value, Mapping):
        for key, child in value.items():
            child_pointer = f"{pointer}/{key}"
            if key in keys:
                yield child_pointer, child
            yield from _iter_named_lists(child, keys, pointer=child_pointer)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from _iter_named_lists(child, keys, pointer=f"{pointer}/{index}")


def _mapping(data: Mapping[str, Any], *keys: str) -> Mapping[str, Any]:
    current: Any = data
    for key in keys:
        if not isinstance(current, Mapping):
            return {}
        current = current.get(key)
    return current if isinstance(current, Mapping) else {}


def _string_items(value: object) -> Iterable[str]:
    if not isinstance(value, list):
        return ()
    return (item for item in value if isinstance(item, str))


def _require_non_empty_string(
    data: Mapping[str, Any],
    key: str,
    pointer: str,
    errors: list[str],
) -> None:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        errors.append(f"{pointer} must be a non-empty string")
