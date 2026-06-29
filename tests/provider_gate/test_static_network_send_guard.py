from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = PROJECT_ROOT / "src" / "research_x"


@dataclass(frozen=True)
class NetworkCall:
    path: str
    class_name: str | None
    function_name: str | None
    line: int
    kind: str
    expression: str


PROVIDER_TRANSPORT_HELPERS = {
    ("src/research_x/bookmark_classifier.py", "_post_json_unbudgeted"),
    ("src/research_x/memory/answer.py", "_post_json_unbudgeted"),
    ("src/research_x/memory/embeddings.py", "_post_json_unbudgeted"),
    ("src/research_x/memory/external.py", "_post_json_unbudgeted"),
    ("src/research_x/memory/llm_context.py", "_post_json_unbudgeted"),
    ("src/research_x/memory/rerank.py", "_post_json_unbudgeted"),
}

RAW_TRANSPORT_HELPERS_WITH_GUARDED_CALLERS = {
    ("src/research_x/memory/reader.py", "_read_url"),
}

NON_PROVIDER_NETWORK_ALLOWLIST = {
    (
        "src/research_x/adapters/bookmark_adapters.py",
        "_fetch",
        "httpx_async_client",
    ): "X bookmark acquisition adapter; external acquisition lane, not answer evidence",
    (
        "src/research_x/adapters/generic_url_adapters.py",
        "_fetch",
        "httpx_async_client",
    ): "generic URL acquisition adapter; explicit acquisition lane, not provider RAG",
    (
        "src/research_x/adapters/twscrape_raw_adapter.py",
        "_fetch_items_direct",
        "httpx_async_client",
    ): "X raw acquisition adapter; explicit acquisition lane, not provider RAG",
    (
        "src/research_x/adapters/twikit_adapter.py",
        "_fetch",
        "httpx_client",
    ): "X acquisition adapter over authenticated local browser/session state",
    (
        "src/research_x/x_store.py",
        "_download_media",
        "urllib_urlopen_send",
    ): "raw X media acquisition download; not model/provider evidence",
}


def test_provider_network_sends_are_guarded_or_explicitly_allowlisted() -> None:
    calls = _network_calls()
    problems: list[str] = []
    reader_call_sites: list[NetworkCall] = []

    for call in calls:
        if _is_provider_transport_helper(call):
            if not _function_calls_guard_before(call, "require_provider_transport_send_allowed"):
                problems.append(f"{_label(call)} lacks require_provider_transport_send_allowed")
            continue
        if _is_raw_transport_helper(call):
            continue
        if call.kind == "internal_read_url":
            reader_call_sites.append(call)
            if not _function_calls_guard_before(call, "require_provider_transport_send_allowed"):
                problems.append(f"{_label(call)} calls _read_url without transport guard")
            if not _function_calls_guard_before(call, "budgeted_api_call"):
                problems.append(f"{_label(call)} calls _read_url outside budgeted_api_call")
            continue
        if call.kind == "internal_post_json_unbudgeted":
            # The internal helper itself owns the transport guard.
            continue
        if _allowlisted_non_provider_network_call(call):
            continue
        problems.append(f"unclassified network/provider send: {_label(call)}")

    assert reader_call_sites, "_read_url call sites should be scanned"
    assert problems == []


def _network_calls() -> list[NetworkCall]:
    calls: list[NetworkCall] = []
    for path in sorted(SRC_ROOT.rglob("*.py")):
        relative = path.relative_to(PROJECT_ROOT).as_posix()
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=relative)
        parents: dict[ast.AST, ast.AST] = {}
        for parent in ast.walk(tree):
            for child in ast.iter_child_nodes(parent):
                parents[child] = parent
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            kind = _network_call_kind(node)
            if kind is None:
                continue
            function = _enclosing(node, parents, ast.FunctionDef, ast.AsyncFunctionDef)
            class_node = _enclosing(node, parents, ast.ClassDef)
            calls.append(
                NetworkCall(
                    path=relative,
                    class_name=class_node.name if class_node else None,
                    function_name=function.name if function else None,
                    line=node.lineno,
                    kind=kind,
                    expression=ast.unparse(node.func),
                )
            )
    return calls


def _network_call_kind(node: ast.Call) -> str | None:
    expr = ast.unparse(node.func)
    if expr in {"urlopen", "urllib.request.urlopen"} or expr.endswith(".urlopen"):
        return "urllib_urlopen_send"
    if expr in {"httpx.AsyncClient", "AsyncClient"}:
        return "httpx_async_client"
    if expr in {"httpx.Client", "Client"}:
        return "httpx_client"
    if expr == "_read_url":
        return "internal_read_url"
    if expr == "_post_json_unbudgeted":
        return "internal_post_json_unbudgeted"
    return None


def _is_provider_transport_helper(call: NetworkCall) -> bool:
    return (
        call.path,
        call.function_name or "",
    ) in PROVIDER_TRANSPORT_HELPERS and call.kind == "urllib_urlopen_send"


def _is_raw_transport_helper(call: NetworkCall) -> bool:
    return (
        call.path,
        call.function_name or "",
    ) in RAW_TRANSPORT_HELPERS_WITH_GUARDED_CALLERS and call.kind == "urllib_urlopen_send"


def _allowlisted_non_provider_network_call(call: NetworkCall) -> bool:
    return (
        call.path,
        call.function_name or "",
        call.kind,
    ) in NON_PROVIDER_NETWORK_ALLOWLIST


def _function_calls_guard_before(call: NetworkCall, function_name: str) -> bool:
    path = PROJECT_ROOT / call.path
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=call.path)
    parents: dict[ast.AST, ast.AST] = {}
    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(parent):
            parents[child] = parent
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if node.name != call.function_name:
            continue
        class_node = _enclosing(node, parents, ast.ClassDef)
        if (class_node.name if class_node else None) != call.class_name:
            continue
        return any(
            isinstance(child, ast.Call)
            and ast.unparse(child.func).endswith(function_name)
            and child.lineno < call.line
            for child in ast.walk(node)
        )
    return False


def _enclosing(
    node: ast.AST,
    parents: dict[ast.AST, ast.AST],
    *types: type[ast.AST],
) -> ast.AST | None:
    current = parents.get(node)
    while current is not None:
        if isinstance(current, types):
            return current
        current = parents.get(current)
    return None


def _label(call: NetworkCall) -> str:
    owner = ".".join(
        part for part in (call.class_name, call.function_name) if part
    ) or "<module>"
    return f"{call.path}:{call.line} {owner} {call.kind} {call.expression}"
