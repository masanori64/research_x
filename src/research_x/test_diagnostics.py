from __future__ import annotations

import json
import os
import signal
import subprocess
import time
from collections.abc import Iterable, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from shutil import which


@dataclass(frozen=True)
class TestDiagnosticResult:
    __test__ = False

    target: str
    status: str
    returncode: int | None
    elapsed_seconds: float
    timed_out: bool
    stdout_tail: str
    stderr_tail: str


def diagnose_pytest(
    *,
    targets: Sequence[str],
    mode: str = "files",
    timeout_seconds: float = 120.0,
    collect_timeout_seconds: float = 60.0,
    pytest_args: Sequence[str] = (),
    max_output_chars: int = 4000,
    stop_on_fail: bool = False,
) -> list[TestDiagnosticResult]:
    """Run pytest in bounded units so slow or hanging tests are visible."""
    if mode not in {"files", "tests"}:
        raise ValueError("mode must be 'files' or 'tests'")
    units = list(targets) if mode == "files" else collect_pytest_nodeids(
        targets,
        timeout_seconds=collect_timeout_seconds,
        max_output_chars=max_output_chars,
    )
    if not units:
        return [
            TestDiagnosticResult(
                target=" ".join(targets) or "tests",
                status="collect_empty",
                returncode=5,
                elapsed_seconds=0.0,
                timed_out=False,
                stdout_tail="",
                stderr_tail="pytest collection returned no runnable units",
            )
        ]

    results: list[TestDiagnosticResult] = []
    for unit in units:
        result = run_pytest_unit(
            unit,
            timeout_seconds=timeout_seconds,
            pytest_args=pytest_args,
            max_output_chars=max_output_chars,
        )
        results.append(result)
        if stop_on_fail and result.status != "passed":
            break
    return results


def collect_pytest_nodeids(
    targets: Sequence[str],
    *,
    timeout_seconds: float,
    max_output_chars: int = 4000,
) -> list[str]:
    result = _run_command(
        _pytest_command([*targets, "--collect-only", "-q"]),
        timeout_seconds=timeout_seconds,
        max_output_chars=max(max_output_chars, 1_000_000),
    )
    if result.timed_out:
        raise RuntimeError(f"pytest collect timed out after {timeout_seconds:g}s")
    if result.returncode not in {0, 5}:
        raise RuntimeError(
            "pytest collect failed\n"
            f"stdout:\n{result.stdout_tail}\n"
            f"stderr:\n{result.stderr_tail}"
        )
    return parse_pytest_collect_nodeids(result.stdout_tail)


def run_pytest_unit(
    target: str,
    *,
    timeout_seconds: float,
    pytest_args: Sequence[str] = (),
    max_output_chars: int = 4000,
) -> TestDiagnosticResult:
    result = _run_command(
        _pytest_command([target, *pytest_args]),
        timeout_seconds=timeout_seconds,
        max_output_chars=max_output_chars,
    )
    if result.timed_out:
        status = "timeout"
    elif result.returncode == 0:
        status = "passed"
    else:
        status = "failed"
    return TestDiagnosticResult(
        target=target,
        status=status,
        returncode=result.returncode,
        elapsed_seconds=result.elapsed_seconds,
        timed_out=result.timed_out,
        stdout_tail=result.stdout_tail,
        stderr_tail=result.stderr_tail,
    )


def parse_pytest_collect_nodeids(output: str) -> list[str]:
    nodeids: list[str] = []
    for raw_line in output.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("="):
            continue
        if line.endswith(" collected") or " collected " in line:
            continue
        if "::" not in line:
            continue
        nodeids.append(line)
    return nodeids


def format_test_diagnostic_results(results: Sequence[TestDiagnosticResult]) -> str:
    if not results:
        return "pytest diagnostic: no units"
    lines = ["pytest diagnostic:"]
    for result in results:
        elapsed = f"{result.elapsed_seconds:.2f}s"
        lines.append(f"- {result.status:7} {elapsed:>9} {result.target}")
        if result.status != "passed":
            if result.stdout_tail:
                lines.append(_indent_block("stdout", result.stdout_tail))
            if result.stderr_tail:
                lines.append(_indent_block("stderr", result.stderr_tail))
    summary: dict[str, int] = {}
    for result in results:
        summary[result.status] = summary.get(result.status, 0) + 1
    summary_text = ", ".join(f"{key}={value}" for key, value in sorted(summary.items()))
    lines.append(f"summary: {summary_text}")
    return "\n".join(lines)


def test_diagnostic_results_json(results: Sequence[TestDiagnosticResult]) -> str:
    return json.dumps([asdict(result) for result in results], ensure_ascii=False, indent=2)


@dataclass(frozen=True)
class _CommandResult:
    returncode: int | None
    elapsed_seconds: float
    timed_out: bool
    stdout_tail: str
    stderr_tail: str


def _pytest_command(args: Sequence[str]) -> list[str]:
    uv = which("uv") or "uv"
    return [uv, "run", "pytest", *args]


def _run_command(
    command: Sequence[str],
    *,
    timeout_seconds: float,
    max_output_chars: int,
) -> _CommandResult:
    started = time.monotonic()
    process = subprocess.Popen(  # noqa: S603
        list(command),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        creationflags=_windows_process_group_flags(),
        start_new_session=os.name != "nt",
    )
    try:
        stdout, stderr = process.communicate(timeout=timeout_seconds)
        timed_out = False
    except subprocess.TimeoutExpired:
        _terminate_process_tree(process.pid)
        stdout, stderr = process.communicate()
        timed_out = True
    elapsed = time.monotonic() - started
    return _CommandResult(
        returncode=process.returncode,
        elapsed_seconds=elapsed,
        timed_out=timed_out,
        stdout_tail=_tail(stdout, max_output_chars),
        stderr_tail=_tail(stderr, max_output_chars),
    )


def _windows_process_group_flags() -> int:
    if os.name != "nt":
        return 0
    return subprocess.CREATE_NEW_PROCESS_GROUP


def _terminate_process_tree(pid: int) -> None:
    if os.name == "nt":
        subprocess.run(  # noqa: S603
            ["taskkill", "/PID", str(pid), "/T", "/F"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        return
    try:
        os.killpg(pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    deadline = time.monotonic() + 3.0
    while time.monotonic() < deadline:
        try:
            os.killpg(pid, 0)
        except ProcessLookupError:
            return
        time.sleep(0.1)
    try:
        os.killpg(pid, signal.SIGKILL)
    except ProcessLookupError:
        return


def _tail(text: str | None, max_chars: int) -> str:
    if not text:
        return ""
    if len(text) <= max_chars:
        return text
    return text[-max_chars:]


def _indent_block(label: str, text: str) -> str:
    indented = "\n".join(f"    {line}" for line in text.rstrip().splitlines())
    return f"  {label}:\n{indented}"


def normalize_targets(values: Iterable[str] | None) -> list[str]:
    targets = [str(Path(value)) for value in values or () if value]
    return targets or ["tests"]
