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


@dataclass(frozen=True)
class ProviderSdkImport:
    path: str
    line: int
    module_name: str
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

PROVIDER_SDK_MODULES = {
    "anthropic",
    "cohere",
    "google.genai",
    "google.generativeai",
    "jina",
    "mistralai",
    "openai",
    "voyageai",
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


def test_provider_sdk_imports_are_absent_from_runtime_sources() -> None:
    imports = _provider_sdk_imports()

    assert imports == []


def test_network_call_kind_detects_guard_bypass_primitives() -> None:
    assert _call_kind("requests.get('https://api.openai.com/v1/models')") == "requests_request"
    assert _call_kind("requests.post('https://api.openai.com/v1/models')") == "requests_request"
    assert _call_kind("requests.request('GET', url)") == "requests_request"
    assert _call_kind("requests.Session()") == "requests_session"
    assert _call_kind("aiohttp.ClientSession()") == "aiohttp_client_session"
    assert _call_kind("urllib3.PoolManager()") == "urllib3_pool_manager"
    assert _call_kind("http.client.HTTPSConnection('api.openai.com')") == (
        "http_client_https_connection"
    )
    assert _call_kind("subprocess.run(['curl', 'https://api.openai.com'])") == (
        "subprocess_network_tool"
    )
    assert _call_kind("subprocess.Popen(['wget', 'https://api.openai.com'])") == (
        "subprocess_network_tool"
    )


def test_provider_sdk_import_kind_detects_direct_imports() -> None:
    assert _provider_sdk_imports_from_source("import openai\n") == [
        ProviderSdkImport(
            path="<fixture>",
            line=1,
            module_name="openai",
            expression="import openai",
        )
    ]
    assert _provider_sdk_imports_from_source("from google import genai\n")[0].module_name == (
        "google.genai"
    )
    assert _provider_sdk_imports_from_source("from google import generativeai\n")[
        0
    ].module_name == "google.generativeai"


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
    if expr in {
        "requests.get",
        "requests.post",
        "requests.request",
        "requests.put",
        "requests.patch",
        "requests.delete",
    }:
        return "requests_request"
    if expr == "requests.Session":
        return "requests_session"
    if expr in {"aiohttp.ClientSession", "ClientSession"}:
        return "aiohttp_client_session"
    if expr in {"urllib3.PoolManager", "PoolManager"}:
        return "urllib3_pool_manager"
    if expr in {"http.client.HTTPSConnection", "HTTPSConnection"}:
        return "http_client_https_connection"
    if _is_subprocess_network_tool_call(node, expr):
        return "subprocess_network_tool"
    if expr in {"httpx.AsyncClient", "AsyncClient"}:
        return "httpx_async_client"
    if expr in {"httpx.Client", "Client"}:
        return "httpx_client"
    if expr == "_read_url":
        return "internal_read_url"
    if expr == "_post_json_unbudgeted":
        return "internal_post_json_unbudgeted"
    return None


def _is_subprocess_network_tool_call(node: ast.Call, expr: str) -> bool:
    if expr not in {
        "subprocess.run",
        "subprocess.Popen",
        "asyncio.create_subprocess_exec",
        "create_subprocess_exec",
    }:
        return False
    command_parts = _literal_command_parts(node)
    if not command_parts:
        return False
    executable = Path(command_parts[0]).name.lower()
    if executable in {"curl", "curl.exe", "wget", "wget.exe"}:
        return True
    if executable in {"powershell", "powershell.exe", "pwsh", "pwsh.exe"}:
        return any(
            part.lower() in {"invoke-webrequest", "iwr", "invoke-restmethod", "irm"}
            for part in command_parts[1:]
        )
    return False


def _literal_command_parts(node: ast.Call) -> list[str]:
    if not node.args:
        return []
    first = node.args[0]
    if isinstance(first, ast.Constant) and isinstance(first.value, str):
        parts = [first.value]
        for arg in node.args[1:]:
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                parts.append(arg.value)
        return parts
    if isinstance(first, (ast.List, ast.Tuple)):
        parts: list[str] = []
        for element in first.elts:
            if isinstance(element, ast.Constant) and isinstance(element.value, str):
                parts.append(element.value)
            else:
                return []
        return parts
    return []


def _provider_sdk_imports() -> list[ProviderSdkImport]:
    imports: list[ProviderSdkImport] = []
    for path in sorted(SRC_ROOT.rglob("*.py")):
        relative = path.relative_to(PROJECT_ROOT).as_posix()
        imports.extend(
            _provider_sdk_imports_from_source(
                path.read_text(encoding="utf-8"),
                path_label=relative,
            )
        )
    return imports


def _provider_sdk_imports_from_source(
    source: str,
    *,
    path_label: str = "<fixture>",
) -> list[ProviderSdkImport]:
    tree = ast.parse(source, filename=path_label)
    imports: list[ProviderSdkImport] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                module_name = _provider_sdk_module_name(alias.name)
                if module_name is not None:
                    imports.append(
                        ProviderSdkImport(
                            path=path_label,
                            line=node.lineno,
                            module_name=module_name,
                            expression=f"import {alias.name}",
                        )
                    )
        if isinstance(node, ast.ImportFrom):
            base_module = node.module or ""
            for alias in node.names:
                full_name = f"{base_module}.{alias.name}" if base_module else alias.name
                module_name = _provider_sdk_module_name(full_name)
                if module_name is None:
                    module_name = _provider_sdk_module_name(base_module)
                if module_name is not None:
                    imports.append(
                        ProviderSdkImport(
                            path=path_label,
                            line=node.lineno,
                            module_name=module_name,
                            expression=f"from {base_module} import {alias.name}",
                        )
                    )
    return imports


def _provider_sdk_module_name(module_name: str) -> str | None:
    for provider_module in sorted(PROVIDER_SDK_MODULES, key=len, reverse=True):
        if module_name == provider_module or module_name.startswith(f"{provider_module}."):
            return provider_module
    return None


def _call_kind(source: str) -> str | None:
    tree = ast.parse(source, mode="eval")
    assert isinstance(tree.body, ast.Call)
    return _network_call_kind(tree.body)


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
