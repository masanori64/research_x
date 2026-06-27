from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1] / "memory"))

from test_operational_trace_persistence import _seed_memory_db

from research_x.cli import main
from research_x.tool_interface.memory_tool_contract import (
    validate_tool_output,
    validate_tool_output_against_db,
)


def test_memory_workflow_tool_json_store_requires_db_backed_restoration(
    tmp_path: Path,
    capsys,
) -> None:
    db_path = _seed_memory_db(tmp_path)

    assert (
        main(
            [
                "memory",
                "workflow",
                "--db",
                str(db_path),
                "--query",
                "強化学習 ロボット",
                "--answer-provider",
                "fake",
                "--store",
                "--allow-fixture-provider",
                "--tool-json",
            ]
        )
        == 0
    )

    payload = json.loads(capsys.readouterr().out)

    assert validate_tool_output(payload) == []
    assert validate_tool_output_against_db(payload, db_path) == []
    assert payload["status"] == "answer"
    assert payload["evidence_level"] == "citation_ready"
    assert payload["trace"]["db_backed_restoration_validation"] == {
        "status": "passed",
        "required_for_answer": True,
        "error_count": 0,
        "errors": [],
    }


def test_memory_workflow_tool_json_without_store_does_not_emit_answer(
    tmp_path: Path,
    capsys,
) -> None:
    db_path = _seed_memory_db(tmp_path)

    assert (
        main(
            [
                "memory",
                "workflow",
                "--db",
                str(db_path),
                "--query",
                "強化学習 ロボット",
                "--answer-provider",
                "fake",
                "--tool-json",
            ]
        )
        == 0
    )

    payload = json.loads(capsys.readouterr().out)

    assert validate_tool_output(payload) == []
    assert payload["status"] == "source_not_restored"
    assert payload["evidence_level"] == "context_chunk"
    assert payload["answer_text"] is None
    assert payload["trace"]["db_backed_restoration_validation"]["status"] == "failed"
    assert (
        payload["trace"]["db_backed_restoration_validation"]["required_for_answer"]
        is True
    )
