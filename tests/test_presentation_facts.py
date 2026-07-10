from __future__ import annotations

import json
from pathlib import Path

from research_x.cli import main
from research_x.presentation import validate_presentation_facts

FACTS = Path("docs/presentation/project-facts.json")
FIXTURES = Path("tests/fixtures/presentation")


def test_project_facts_validate_locally() -> None:
    result = validate_presentation_facts(FACTS)

    assert result.ok, result.errors
    assert result.summary["claims"] >= 6
    assert result.summary["slide_candidates"] >= 6
    evidence_paths = set(result.summary["evidence_file_paths"])
    assert "docs/research_x_canon.md" in evidence_paths
    assert "src/research_x/presentation/facts.py" in evidence_paths
    assert not any(path.startswith(".codex/") for path in evidence_paths)
    assert not any(path.startswith("tools/wbs_viewer/") for path in evidence_paths)


def test_valid_fixture_passes_schema_and_alignment_checks() -> None:
    result = validate_presentation_facts(FIXTURES / "project-facts.valid.json")

    assert result.ok, result.errors


def test_claim_without_repository_evidence_is_rejected() -> None:
    result = validate_presentation_facts(FIXTURES / "project-facts.missing-evidence.json")

    assert not result.ok
    assert any("/claims/0/evidence" in error for error in result.errors)


def test_generated_or_control_artifacts_cannot_be_claim_evidence() -> None:
    result = validate_presentation_facts(FIXTURES / "project-facts.generated-evidence.json")

    assert not result.ok
    assert any("generated/control artifact" in error for error in result.errors)


def test_unknowns_cannot_be_silently_promoted_to_claims() -> None:
    result = validate_presentation_facts(FIXTURES / "project-facts.unknown-promoted.json")

    assert not result.ok
    assert any("promoted_to_claim must be false" in error for error in result.errors)
    assert any("promotes unknown" in error for error in result.errors)


def test_pyproject_runtime_drift_is_rejected(tmp_path: Path) -> None:
    data = json.loads((FIXTURES / "project-facts.valid.json").read_text(encoding="utf-8"))
    data["runtime_surfaces"]["python"]["requires"] = ">=3.12"
    path = tmp_path / "project-facts.json"
    path.write_text(json.dumps(data), encoding="utf-8")

    result = validate_presentation_facts(path)

    assert not result.ok
    assert any("requires-python" in error for error in result.errors)


def test_presentation_validate_facts_cli_json(capsys) -> None:
    exit_code = main(["presentation", "validate-facts", "--facts", str(FACTS), "--json"])

    output = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert output["ok"] is True
    assert output["summary"]["claims"] >= 6
