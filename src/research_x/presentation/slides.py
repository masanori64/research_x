from __future__ import annotations

import json
import re
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from research_x.presentation.facts import load_presentation_facts, validate_presentation_facts

DEFAULT_SLIDES_PATH = Path("docs/presentation/slides.md")
_CLAIM_MARKER = re.compile(r"<!--\s*claim:\s*([A-Za-z0-9_.:-]+)\s*-->")
_MARKDOWN_IMAGE = re.compile(r"!\[[^\]]*]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
_HTML_SRC = re.compile(r"\bsrc=[\"']([^\"']+)[\"']")


@dataclass(frozen=True)
class PresentationSlidesValidation:
    slides_path: str
    ok: bool
    errors: tuple[str, ...]
    warnings: tuple[str, ...]
    summary: dict[str, object]

    def as_dict(self) -> dict[str, object]:
        return {
            "slides_path": self.slides_path,
            "ok": self.ok,
            "errors": list(self.errors),
            "warnings": list(self.warnings),
            "summary": self.summary,
        }


def validate_presentation_slides(
    slides_path: str | Path = DEFAULT_SLIDES_PATH,
    *,
    facts_path: str | Path = "docs/presentation/project-facts.json",
    repo_root: str | Path | None = None,
    allow_missing_assets: bool = False,
    require_slide_candidates: bool = True,
) -> PresentationSlidesValidation:
    root = Path(repo_root or Path.cwd()).resolve()
    slides = Path(slides_path)
    errors: list[str] = []
    warnings: list[str] = []

    facts_result = validate_presentation_facts(facts_path, repo_root=root)
    if not facts_result.ok:
        errors.extend(f"facts: {error}" for error in facts_result.errors)
        return _result(slides, "", errors, warnings, used_claim_ids=[], asset_paths=[])

    if not slides.exists():
        return _result(
            slides,
            "",
            [f"slides file not found: {slides.as_posix()}"],
            warnings,
            used_claim_ids=[],
            asset_paths=[],
        )

    text = slides.read_text(encoding="utf-8")
    facts = load_presentation_facts(facts_path)
    claim_ids = _claim_ids(facts)
    slide_candidate_ids = _slide_candidate_claim_ids(facts)
    used_claim_ids = _CLAIM_MARKER.findall(text)
    asset_paths = _asset_references(text)

    if "marp: true" not in text:
        errors.append("slides must include Marp frontmatter with marp: true")
    if not used_claim_ids:
        errors.append("slides must include at least one <!-- claim: claim-id --> marker")

    unknown_markers = sorted(set(used_claim_ids) - claim_ids)
    if unknown_markers:
        errors.append("slides reference unknown claim ids: " + ", ".join(unknown_markers))

    if require_slide_candidates:
        missing = sorted(slide_candidate_ids - set(used_claim_ids))
        if missing:
            errors.append("slides are missing slide_candidate claim ids: " + ", ".join(missing))

    duplicate_markers = sorted(_duplicates(used_claim_ids))
    if duplicate_markers:
        warnings.append("duplicate claim markers: " + ", ".join(duplicate_markers))

    for raw_asset in asset_paths:
        _validate_asset_reference(
            raw_asset,
            slides_path=slides,
            repo_root=root,
            errors=errors,
            allow_missing_assets=allow_missing_assets,
        )

    return _result(
        slides,
        text,
        errors,
        warnings,
        used_claim_ids=used_claim_ids,
        asset_paths=asset_paths,
    )


def format_presentation_slides_validation(result: PresentationSlidesValidation) -> str:
    if result.ok:
        return (
            "presentation slides ok: "
            f"slides={result.summary['slides']} "
            f"claim_markers={result.summary['claim_markers']} "
            f"assets={result.summary['assets']}"
        )
    lines = ["presentation slides invalid:"]
    lines.extend(f"- {error}" for error in result.errors)
    if result.warnings:
        lines.append("warnings:")
        lines.extend(f"- {warning}" for warning in result.warnings)
    return "\n".join(lines)


def _claim_ids(facts: dict[str, Any]) -> set[str]:
    return {
        claim["id"]
        for claim in facts.get("claims", [])
        if isinstance(claim, dict) and isinstance(claim.get("id"), str)
    }


def _slide_candidate_claim_ids(facts: dict[str, Any]) -> set[str]:
    return {
        claim["id"]
        for claim in facts.get("claims", [])
        if isinstance(claim, dict)
        and isinstance(claim.get("id"), str)
        and claim.get("slide_candidate") is True
    }


def _asset_references(text: str) -> list[str]:
    refs = [match.group(1) for match in _MARKDOWN_IMAGE.finditer(text)]
    refs.extend(match.group(1) for match in _HTML_SRC.finditer(text))
    return refs


def _validate_asset_reference(
    raw_asset: str,
    *,
    slides_path: Path,
    repo_root: Path,
    errors: list[str],
    allow_missing_assets: bool,
) -> None:
    if "://" in raw_asset:
        errors.append(f"slides must not reference external assets: {raw_asset}")
        return
    clean = raw_asset.strip().replace("\\", "/")
    if clean.startswith("/") or re.match(r"^[A-Za-z]:", clean):
        errors.append(f"slides asset must be relative: {raw_asset}")
        return
    pure = PurePosixPath(clean)
    if ".." in pure.parts:
        errors.append(f"slides asset must not traverse parents: {raw_asset}")
        return

    absolute = (repo_root / slides_path.parent / Path(*pure.parts)).resolve()
    try:
        relative = absolute.relative_to(repo_root).as_posix()
    except ValueError:
        errors.append(f"slides asset escapes repository root: {raw_asset}")
        return
    if not relative.startswith("docs/presentation/assets/"):
        errors.append(f"slides asset must live under docs/presentation/assets: {relative}")
    if not allow_missing_assets and not absolute.is_file():
        errors.append(f"slides asset not found: {relative}")


def _duplicates(values: Iterable[str]) -> set[str]:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for value in values:
        if value in seen:
            duplicates.add(value)
        seen.add(value)
    return duplicates


def _result(
    slides_path: Path,
    text: str,
    errors: Iterable[str],
    warnings: Iterable[str],
    *,
    used_claim_ids: list[str],
    asset_paths: list[str],
) -> PresentationSlidesValidation:
    error_tuple = tuple(errors)
    warning_tuple = tuple(warnings)
    return PresentationSlidesValidation(
        slides_path=slides_path.as_posix(),
        ok=not error_tuple,
        errors=error_tuple,
        warnings=warning_tuple,
        summary={
            "slides": _slide_count(text),
            "claim_markers": len(used_claim_ids),
            "claim_ids": sorted(set(used_claim_ids)),
            "assets": len(asset_paths),
            "asset_paths": asset_paths,
        },
    )


def _slide_count(text: str) -> int:
    if not text.strip():
        return 0
    separators = len(re.findall(r"(?m)^---\s*$", text))
    if text.lstrip().startswith("---"):
        return max(1, separators - 1)
    return max(1, separators)


def slides_validation_json(result: PresentationSlidesValidation) -> str:
    return json.dumps(result.as_dict(), ensure_ascii=False, indent=2, sort_keys=True)
