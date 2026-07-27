from __future__ import annotations

import ast
import hashlib
import sys
from pathlib import Path
from typing import Any, Iterable

from .canonical import sha256_hex
from .errors import EFSError

RUNTIME_AUDIT_SCHEMA = "efs.runtime_static_audit.v3"

AGENT_LLM_IMPORTS = {
    "openai",
    "anthropic",
    "langchain",
    "llama_index",
    "autogen",
    "crewai",
    "semantic_kernel",
    "mcp",
}
NETWORK_IMPORTS = {"socket", "requests", "httpx", "aiohttp", "websockets", "grpc"}
PROCESS_IMPORTS = {"subprocess"}
UNSAFE_MODEL_IMPORTS = {"pickle", "joblib", "cloudpickle", "dill"}
PERSISTENCE_IMPORTS = {"sqlite3", "shelve", "dbm"}
DYNAMIC_CODE_CALLS = {"eval", "exec", "compile", "__import__"}
LOCAL_PERSISTENCE_CALLS = {
    "Path.home", "pathlib.Path.home", "os.makedirs", "os.mkdir",
    "os.remove", "os.rename", "os.replace", "os.unlink",
    "os.open", "os.symlink", "os.link",
    "shutil.copy", "shutil.copy2", "shutil.copyfile", "shutil.copytree",
    "shutil.move", "shutil.rmtree",
    "logging.FileHandler", "logging.handlers.RotatingFileHandler",
    "logging.handlers.TimedRotatingFileHandler",
}
LOCAL_PERSISTENCE_ATTRIBUTES = {
    "expanduser", "mkdir", "touch", "unlink", "rename", "symlink_to", "hardlink_to",
    "write_text", "write_bytes",
}
LOCAL_ENV_KEYS = {
    "HOME", "XDG_CACHE_HOME", "XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_STATE_HOME",
}
WRITE_MODE_CHARS = {"w", "a", "x", "+"}

ALLOWED_EXTERNAL_IMPORTS: set[str] = set()
# Python 3.10+ exposes sys.stdlib_module_names. The fallback keeps the audit
# deterministic on Python 3.9 without importing inspected modules.
STDLIB_FALLBACK_ROOTS = {
    "__future__", "argparse", "ast", "base64", "copy", "csv", "dataclasses",
    "datetime", "decimal", "hashlib", "io", "itertools", "json", "os",
    "pathlib", "re", "sys", "typing", "unicodedata",
}
MAX_SOURCE_FILES = 512
MAX_SOURCE_BYTES = 5_000_000


def _root_name(module: str) -> str:
    return module.split(".", 1)[0]


def _qualified_name(node: ast.AST) -> str | None:
    parts: list[str] = []
    current = node
    while isinstance(current, ast.Attribute):
        parts.append(current.attr)
        current = current.value
    if isinstance(current, ast.Name):
        parts.append(current.id)
        return ".".join(reversed(parts))
    return None


def _open_writes(node: ast.Call) -> bool:
    name = _qualified_name(node.func)
    if name != "open" and not (isinstance(node.func, ast.Attribute) and node.func.attr == "open"):
        return False
    mode: object = None
    if len(node.args) >= 2 and isinstance(node.args[1], ast.Constant):
        mode = node.args[1].value
    for keyword in node.keywords:
        if keyword.arg == "mode" and isinstance(keyword.value, ast.Constant):
            mode = keyword.value.value
    return isinstance(mode, str) and any(char in mode for char in WRITE_MODE_CHARS)


def _scan_file(path: Path, root: Path) -> dict[str, Any]:
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise EFSError("INPUT_IO_ERROR", f"cannot read runtime source: {path}") from exc
    if len(data) > MAX_SOURCE_BYTES:
        raise EFSError("RESOURCE_LIMIT", f"runtime source exceeds byte limit: {path.name}")
    try:
        text = data.decode("utf-8", errors="strict")
        tree = ast.parse(text, filename=str(path))
    except (UnicodeDecodeError, SyntaxError) as exc:
        raise EFSError("CONTRACT_INVALID", f"runtime source cannot be parsed: {path.name}") from exc

    imports: set[str] = set()
    nodes = list(ast.walk(tree))
    for node in nodes:
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module)
    roots = {_root_name(item) for item in imports}
    forbidden_calls: set[str] = set()
    local_persistence_calls: set[str] = set()
    local_environment_dependencies: set[str] = set()
    for node in nodes:
        if not isinstance(node, ast.Call):
            continue
        name = _qualified_name(node.func)
        if name in DYNAMIC_CODE_CALLS:
            forbidden_calls.add(name)
        if name in LOCAL_PERSISTENCE_CALLS:
            local_persistence_calls.add(name)
        if _open_writes(node):
            local_persistence_calls.add("open(write_mode)")
        if isinstance(node.func, ast.Attribute) and node.func.attr in LOCAL_PERSISTENCE_ATTRIBUTES:
            local_persistence_calls.add(node.func.attr)
        if not name:
            continue
        root_name = _root_name(name)
        if (
            (root_name in roots and root_name in NETWORK_IMPORTS | PROCESS_IMPORTS)
            or (root_name == "urllib" and any(item.startswith("urllib") for item in imports))
            or name in {"os.system", "os.popen", "importlib.import_module"}
        ):
            forbidden_calls.add(name)
    for node in nodes:
        if isinstance(node, ast.Subscript) and _qualified_name(node.value) == "os.environ":
            if isinstance(node.slice, ast.Constant) and node.slice.value in LOCAL_ENV_KEYS:
                local_environment_dependencies.add(str(node.slice.value))
        if isinstance(node, ast.Call) and _qualified_name(node.func) in {"os.environ.get", "os.getenv"}:
            if node.args and isinstance(node.args[0], ast.Constant) and node.args[0].value in LOCAL_ENV_KEYS:
                local_environment_dependencies.add(str(node.args[0].value))
    rel = path.relative_to(root).as_posix()
    return {
        "path": rel,
        "sha256": hashlib.sha256(data).hexdigest(),
        "imports": sorted(imports),
        "agent_llm_imports": sorted(roots & AGENT_LLM_IMPORTS),
        "network_imports": sorted(roots & NETWORK_IMPORTS),
        "process_imports": sorted(roots & PROCESS_IMPORTS),
        "unsafe_model_imports": sorted(roots & UNSAFE_MODEL_IMPORTS),
        "persistence_imports": sorted(roots & PERSISTENCE_IMPORTS),
        "forbidden_calls": sorted(forbidden_calls),
        "local_persistence_calls": sorted(local_persistence_calls),
        "local_environment_dependencies": sorted(local_environment_dependencies),
    }


def audit_runtime_source(
    package_root: str | Path,
    *,
    excluded_files: Iterable[str] = (),
) -> dict[str, Any]:
    """Statically audit a Python runtime package for Agent/LLM/network fallbacks.

    This is one evidence layer only. OS-level network and process isolation are
    verified by separate bounded oracles and are never inferred from this scan.
    """
    root = Path(package_root).resolve()
    if not root.is_dir():
        raise EFSError("INPUT_IO_ERROR", "runtime package root must be a directory")
    excluded = set(excluded_files)
    files = [path for path in root.rglob("*.py") if path.name not in excluded and "__pycache__" not in path.parts]
    files.sort(key=lambda item: item.relative_to(root).as_posix())
    if not files:
        raise EFSError("CONTRACT_INVALID", "runtime package contains no Python source")
    if len(files) > MAX_SOURCE_FILES:
        raise EFSError("RESOURCE_LIMIT", "runtime source file count exceeds limit")
    scans = [_scan_file(path, root) for path in files]
    package_modules = {path.stem for path in files} | {root.name}
    stdlib_roots = set(getattr(sys, "stdlib_module_names", ())) | STDLIB_FALLBACK_ROOTS
    imported_roots = {
        _root_name(item)
        for scan in scans
        for item in scan["imports"]
    }
    external_imports = sorted(imported_roots - package_modules - stdlib_roots)
    undeclared_external_imports = sorted(set(external_imports) - ALLOWED_EXTERNAL_IMPORTS)
    agent_llm = sorted({item for scan in scans for item in scan["agent_llm_imports"]})
    network = sorted({item for scan in scans for item in scan["network_imports"]})
    process = sorted({item for scan in scans for item in scan["process_imports"]})
    unsafe = sorted({item for scan in scans for item in scan["unsafe_model_imports"]})
    persistence_imports = sorted({item for scan in scans for item in scan["persistence_imports"]})
    calls = sorted({item for scan in scans for item in scan["forbidden_calls"]})
    local_persistence = sorted({item for scan in scans for item in scan["local_persistence_calls"]})
    local_environment = sorted({item for scan in scans for item in scan["local_environment_dependencies"]})
    blockers = []
    if agent_llm:
        blockers.append("AGENT_OR_LLM_IMPORT_PRESENT")
    if network:
        blockers.append("NETWORK_IMPORT_PRESENT")
    if process:
        blockers.append("PROCESS_IMPORT_PRESENT")
    if unsafe:
        blockers.append("UNSAFE_MODEL_LOADER_PRESENT")
    if persistence_imports:
        blockers.append("LOCAL_PERSISTENCE_IMPORT_PRESENT")
    if calls:
        blockers.append("FORBIDDEN_RUNTIME_CALL_PRESENT")
    if undeclared_external_imports:
        blockers.append("UNDECLARED_RUNTIME_DEPENDENCY_PRESENT")
    if local_persistence:
        blockers.append("LOCAL_PERSISTENCE_CALL_PRESENT")
    if local_environment:
        blockers.append("LOCAL_HOME_OR_XDG_DEPENDENCY_PRESENT")
    report: dict[str, Any] = {
        "schema": RUNTIME_AUDIT_SCHEMA,
        "status": "PASS" if not blockers else "FAIL",
        "package_root_name": root.name,
        "source_file_count": len(scans),
        "source_set_sha256": sha256_hex([{"path": item["path"], "sha256": item["sha256"]} for item in scans]),
        "files": scans,
        "blocking_reasons": blockers,
        "agent_llm_imports": agent_llm,
        "network_imports": network,
        "process_imports": process,
        "unsafe_model_imports": unsafe,
        "persistence_imports": persistence_imports,
        "forbidden_runtime_calls": calls,
        "external_runtime_imports": external_imports,
        "allowed_external_imports": sorted(ALLOWED_EXTERNAL_IMPORTS),
        "undeclared_external_imports": undeclared_external_imports,
        "local_persistence_calls": local_persistence,
        "local_environment_dependencies": local_environment,
        "deployment_profile": "REMOTE_HOST_EMBEDDED_ONLY",
        "macos_runtime_install_permitted": False,
        "macos_launchd_permitted": False,
        "dependency_boundary": {
            "research_shadow_core": "PYTHON_STANDARD_LIBRARY_ONLY",
            "decision_support_adapter": "NOT_INCLUDED_IN_V0_0_0_1",
        },
        "zero_agent_static_claim": not agent_llm,
        "zero_llm_token_static_claim": not agent_llm,
        "zero_network_static_claim": not network and not calls,
        "zero_local_persistence_static_claim": not persistence_imports and not local_persistence and not local_environment,
        "zero_macos_launchd_static_claim": not process and not any(
            call in {"os.system", "os.popen"} or call.startswith("subprocess.") for call in calls
        ),
        "os_network_isolation_status": "NOT_PROVEN_BY_STATIC_AUDIT",
        "os_process_isolation_status": "NOT_PROVEN_BY_STATIC_AUDIT",
        "agent_invocations_total": 0,
        "llm_requests_total": 0,
        "llm_input_tokens_total": 0,
        "llm_output_tokens_total": 0,
        "network_requests_total": 0,
    }
    report["report_sha256"] = sha256_hex(report)
    return report
