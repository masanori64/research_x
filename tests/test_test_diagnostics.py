from pathlib import Path

from research_x.cli import main
from research_x.test_diagnostics import (
    TestDiagnosticResult,
    format_test_diagnostic_results,
    parse_pytest_collect_nodeids,
)


def test_parse_pytest_collect_nodeids_ignores_summary_lines() -> None:
    output = "\n".join(
        [
            "tests/test_memory.py::test_a",
            "tests/test_memory.py::TestThing::test_b",
            "82 tests collected in 0.32s",
            "",
        ]
    )

    assert parse_pytest_collect_nodeids(output) == [
        "tests/test_memory.py::test_a",
        "tests/test_memory.py::TestThing::test_b",
    ]


def test_format_test_diagnostic_results_marks_timeout() -> None:
    text = format_test_diagnostic_results(
        [
            TestDiagnosticResult(
                target="tests/test_memory.py::test_slow",
                status="timeout",
                returncode=None,
                elapsed_seconds=10.1,
                timed_out=True,
                stdout_tail="running",
                stderr_tail="",
            )
        ]
    )

    assert "timeout" in text
    assert "tests/test_memory.py::test_slow" in text
    assert "summary: timeout=1" in text


def test_test_diagnose_cli_uses_diagnostic_runner(monkeypatch, capsys) -> None:
    captured = {}

    def fake_diagnose_pytest(**kwargs):
        captured.update(kwargs)
        return [
            TestDiagnosticResult(
                target="tests/test_memory.py",
                status="passed",
                returncode=0,
                elapsed_seconds=1.0,
                timed_out=False,
                stdout_tail="",
                stderr_tail="",
            )
        ]

    monkeypatch.setattr("research_x.test_diagnostics.diagnose_pytest", fake_diagnose_pytest)

    assert (
        main(
            [
                "test-diagnose",
                "tests/test_memory.py",
                "--mode",
                "tests",
                "--timeout-seconds",
                "5",
                "--pytest-arg=-q",
            ]
        )
        == 0
    )

    assert captured["targets"] == [str(Path("tests/test_memory.py"))]
    assert captured["mode"] == "tests"
    assert captured["timeout_seconds"] == 5
    assert captured["pytest_args"] == ("-q",)
    assert "pytest diagnostic" in capsys.readouterr().out
