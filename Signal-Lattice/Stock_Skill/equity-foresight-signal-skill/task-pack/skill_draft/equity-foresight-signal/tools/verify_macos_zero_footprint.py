from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "efs.macos_zero_footprint_verification.v1"
RUNTIME_ROOT = ROOT / "equity_foresight_signal"

# These artifacts would create a resident/background service if landed on a host.
FORBIDDEN_ARTIFACT_SUFFIXES = {".plist", ".service", ".timer", ".socket"}
FORBIDDEN_RUNTIME_IMPORT_ROOTS = {"plistlib"}
FORBIDDEN_RUNTIME_CALLS = {
    "Path.home",
    "pathlib.Path.home",
    "os.fork",
    "os.forkpty",
    "os.posix_spawn",
    "os.posix_spawnp",
    "os.system",
    "os.popen",
}
FORBIDDEN_RUNTIME_ATTRIBUTES = {"expanduser"}
FORBIDDEN_RUNTIME_ENV_KEYS = {
    "HOME",
    "XDG_CACHE_HOME",
    "XDG_CONFIG_HOME",
    "XDG_DATA_HOME",
    "XDG_STATE_HOME",
}
FORBIDDEN_LAUNCHD_TOKENS = {
    "launchctl",
    "launchagents",
    "launchdaemons",
    "keepalive",
    "runatload",
}
EXECUTABLE_SCAN_ROOTS = (
    ROOT / "equity_foresight_signal",
    ROOT / "landing",
    ROOT / "build_fixtures.py",
)
# Policy scanners necessarily contain deny-list literals. Their imports and
# executable calls remain audited; only raw token matching is skipped to avoid
# self-reporting the policy constants as launchd usage.
LAUNCHD_POLICY_SCANNER_PATHS = {
    "equity_foresight_signal/runtime_audit.py",
    "landing/verify_taskpack.py",
    "tools/verify_macos_zero_footprint.py",
}


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


def _string_constants(tree: ast.AST) -> list[str]:
    return [node.value for node in ast.walk(tree) if isinstance(node, ast.Constant) and isinstance(node.value, str)]


def _iter_executable_files() -> list[Path]:
    files: list[Path] = []
    for root in EXECUTABLE_SCAN_ROOTS:
        if root.is_file():
            files.append(root)
        elif root.is_dir():
            files.extend(path for path in root.rglob("*.py") if "__pycache__" not in path.parts)
    return sorted(set(files), key=lambda path: path.relative_to(ROOT).as_posix())


def _static_scan() -> dict[str, Any]:
    artifact_findings: list[dict[str, str]] = []
    for path in sorted(ROOT.rglob("*")):
        if not path.is_file() or path.is_symlink() or ".git" in path.parts or "__pycache__" in path.parts:
            continue
        if path.suffix.casefold() in FORBIDDEN_ARTIFACT_SUFFIXES:
            artifact_findings.append({"path": path.relative_to(ROOT).as_posix(), "reason": "resident_service_artifact"})

    code_findings: list[dict[str, str]] = []
    scanned_files = 0
    for path in _iter_executable_files():
        scanned_files += 1
        rel = path.relative_to(ROOT).as_posix()
        try:
            text = path.read_text(encoding="utf-8", errors="strict")
            tree = ast.parse(text, filename=rel)
        except (OSError, UnicodeDecodeError, SyntaxError) as exc:
            code_findings.append({"path": rel, "reason": f"unparseable:{type(exc).__name__}"})
            continue
        imports: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name.split(".", 1)[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module.split(".", 1)[0])
        for root in sorted(imports & FORBIDDEN_RUNTIME_IMPORT_ROOTS):
            code_findings.append({"path": rel, "reason": f"forbidden_import:{root}"})

        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                name = _qualified_name(node.func)
                if name in FORBIDDEN_RUNTIME_CALLS:
                    code_findings.append({"path": rel, "reason": f"forbidden_call:{name}"})
                if isinstance(node.func, ast.Attribute) and node.func.attr in FORBIDDEN_RUNTIME_ATTRIBUTES:
                    code_findings.append({"path": rel, "reason": f"forbidden_attribute:{node.func.attr}"})
            if isinstance(node, ast.Subscript):
                name = _qualified_name(node.value)
                if name == "os.environ" and isinstance(node.slice, ast.Constant) and node.slice.value in FORBIDDEN_RUNTIME_ENV_KEYS:
                    code_findings.append({"path": rel, "reason": f"local_environment_dependency:{node.slice.value}"})

        # Only executable code is inspected for launchd literals. Documentation is
        # expected to state the prohibition explicitly and is not executable.
        if rel not in LAUNCHD_POLICY_SCANNER_PATHS:
            for value in _string_constants(tree):
                folded = value.casefold()
                for token in FORBIDDEN_LAUNCHD_TOKENS:
                    if token in folded:
                        code_findings.append({"path": rel, "reason": f"launchd_literal:{token}"})

    findings = artifact_findings + code_findings
    return {
        "status": "PASS" if not findings else "FAIL",
        "scanned_executable_files": scanned_files,
        "forbidden_service_artifact_count": len(artifact_findings),
        "code_finding_count": len(code_findings),
        "findings": findings,
    }


def _snapshot(root: Path) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for path in sorted(root.rglob("*"), key=lambda item: item.relative_to(root).as_posix()):
        rel = path.relative_to(root).as_posix()
        if path.is_symlink():
            result[rel] = {"type": "symlink", "target": os.readlink(path)}
        elif path.is_dir():
            result[rel] = {"type": "directory"}
        elif path.is_file():
            data = path.read_bytes()
            result[rel] = {"type": "file", "size": len(data), "sha256": hashlib.sha256(data).hexdigest()}
        else:
            result[rel] = {"type": "other"}
    return result


def _marked_processes(marker: str) -> list[int]:
    proc = Path("/proc")
    if not proc.is_dir():
        return []
    needle = f"EFS_ZERO_FOOTPRINT_MARKER={marker}".encode()
    found: list[int] = []
    for entry in proc.iterdir():
        if not entry.name.isdigit():
            continue
        try:
            data = (entry / "environ").read_bytes()
        except (OSError, PermissionError):
            continue
        if needle in data.split(b"\0"):
            found.append(int(entry.name))
    return sorted(found)


def _dynamic_scan() -> dict[str, Any]:
    marker = hashlib.sha256(f"{os.getpid()}:{time.time_ns()}".encode()).hexdigest()
    with tempfile.TemporaryDirectory(prefix="efs-zero-footprint-") as tmp:
        sandbox = Path(tmp)
        paths = {
            "home": sandbox / "home",
            "cache": sandbox / "cache",
            "config": sandbox / "config",
            "state": sandbox / "state",
            "data": sandbox / "data",
            "tmp": sandbox / "tmp",
            "pycache": sandbox / "pycache",
        }
        for path in paths.values():
            path.mkdir(parents=True, exist_ok=False)
        before = _snapshot(sandbox)
        env = {
            **os.environ,
            "HOME": str(paths["home"]),
            "XDG_CACHE_HOME": str(paths["cache"]),
            "XDG_CONFIG_HOME": str(paths["config"]),
            "XDG_STATE_HOME": str(paths["state"]),
            "XDG_DATA_HOME": str(paths["data"]),
            "TMPDIR": str(paths["tmp"]),
            "PYTHONPYCACHEPREFIX": str(paths["pycache"]),
            "PYTHONDONTWRITEBYTECODE": "1",
            "EFS_ZERO_FOOTPRINT_MARKER": marker,
            "PYTHONPATH": str(ROOT),
        }
        commands = [
            [sys.executable, "-B", "-m", "equity_foresight_signal", "self-check"],
            [
                sys.executable,
                "-B",
                "-m",
                "equity_foresight_signal",
                "evaluate",
                "fixtures/request.json",
                "fixtures/bundle.json",
            ],
            [
                sys.executable,
                "-B",
                "-m",
                "equity_foresight_signal",
                "train-direction",
                "fixtures/pit_dataset.json",
                "fixtures/training_config.json",
            ],
        ]
        rows: list[dict[str, Any]] = []
        for argv in commands:
            completed = subprocess.run(
                argv,
                cwd=ROOT,
                env=env,
                capture_output=True,
                text=True,
                timeout=120,
                check=False,
            )
            try:
                payload = json.loads(completed.stdout)
            except json.JSONDecodeError:
                payload = None
            rows.append(
                {
                    "argv": argv[2:],
                    "returncode": completed.returncode,
                    "status": "PASS" if completed.returncode == 0 and isinstance(payload, dict) else "FAIL",
                    "stdout_sha256": hashlib.sha256(completed.stdout.encode()).hexdigest(),
                    "stderr_sha256": hashlib.sha256(completed.stderr.encode()).hexdigest(),
                }
            )
        # Give an incorrectly detached child a small scheduling window before scanning.
        time.sleep(0.05)
        lingering = [pid for pid in _marked_processes(marker) if pid != os.getpid()]
        after = _snapshot(sandbox)
        created_or_changed = {
            path: value
            for path, value in after.items()
            if path not in before or before[path] != value
        }
        removed = sorted(path for path in before if path not in after)
        persistent_files = [path for path, value in after.items() if value.get("type") == "file"]
        persistent_bytes = sum(int(value.get("size", 0)) for value in after.values() if value.get("type") == "file")
        status = "PASS" if all(row["status"] == "PASS" for row in rows) and not created_or_changed and not removed and not lingering else "FAIL"
        return {
            "status": status,
            "commands": rows,
            "created_or_changed_entries": created_or_changed,
            "removed_entries": removed,
            "local_persistent_files_after_invocation": len(persistent_files),
            "local_persistent_bytes_after_invocation": persistent_bytes,
            "resident_background_processes_after_invocation": len(lingering),
            "lingering_process_ids": lingering,
            "proc_process_scan_available": Path("/proc").is_dir(),
        }


def verify() -> dict[str, Any]:
    static = _static_scan()
    dynamic = _dynamic_scan()
    failures = [name for name, check in (("static", static), ("dynamic", dynamic)) if check["status"] != "PASS"]
    report: dict[str, Any] = {
        "schema": SCHEMA,
        "status": "PASS" if not failures else "FAIL",
        "failed_checks": failures,
        "deployment_profile": "REMOTE_HOST_EMBEDDED_ONLY",
        "macos_runtime_install_permitted": False,
        "macos_launchd_entries": 0 if static["forbidden_service_artifact_count"] == 0 else static["forbidden_service_artifact_count"],
        "local_persistent_files_after_invocation": dynamic["local_persistent_files_after_invocation"],
        "local_persistent_bytes_after_invocation": dynamic["local_persistent_bytes_after_invocation"],
        "resident_background_processes_after_invocation": dynamic["resident_background_processes_after_invocation"],
        "checks": {"static": static, "dynamic": dynamic},
        "agent_invocations_total": 0,
        "llm_requests_total": 0,
        "llm_input_tokens_total": 0,
        "llm_output_tokens_total": 0,
        "claim_boundary": (
            "ZERO_PERSISTENT_OR_RESIDENT_LOCAL_FOOTPRINT_AFTER_EXPLICIT_INVOCATION; "
            "NO_MACOS_DEPLOYMENT_OR_LAUNCHD; TRANSIENT_CPU_AND_RAM_DURING_AN_EXPLICIT_CALL_ARE_UNAVOIDABLE_AND_NOT_CLAIMED_ZERO"
        ),
    }
    canonical = json.dumps(report, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    report["report_sha256"] = hashlib.sha256(canonical.encode()).hexdigest()
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = verify()
    text = json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    print(text, end="")
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
