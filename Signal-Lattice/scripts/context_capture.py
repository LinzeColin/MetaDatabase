#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

RULE_FILES = ("AGENTS.md", "CONTRIBUTING.md", "SECURITY.md", "README.md")
WORKFLOW_GLOBS = (".github/workflows/*.yml", ".github/workflows/*.yaml")


def canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def run(command: list[str], cwd: Path | None = None, timeout: int = 15) -> dict[str, Any]:
    try:
        result = subprocess.run(
            command,
            cwd=cwd,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            env={"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8", "PYTHONHASHSEED": "0"},
        )
        return {"returncode": result.returncode, "stdout": result.stdout[-12000:], "stderr": result.stderr[-4000:]}
    except Exception as exc:
        return {"returncode": 2, "stdout": "", "stderr": "ERROR:" + type(exc).__name__}


def redact_remote(value: str) -> str:
    value = value.strip()
    return re.sub(r"(https?://)[^/@\s]+@", r"\1<REDACTED>@", value)


def file_meta(path: Path, root: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    return {"path": path.relative_to(root).as_posix(), "size": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}


def capture_repo(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {"state": "NOT_BOUND"}
    root = path.resolve()
    if not root.is_dir():
        return {"state": "BLOCKED", "reason": "PATH_NOT_FOUND", "path": root.as_posix()}
    inside = run(["git", "rev-parse", "--is-inside-work-tree"], root)
    if inside["returncode"] != 0 or inside["stdout"].strip() != "true":
        return {"state": "BLOCKED", "reason": "NOT_GIT_WORKTREE", "path": root.as_posix()}
    head = run(["git", "rev-parse", "HEAD"], root)
    branch = run(["git", "symbolic-ref", "--short", "-q", "HEAD"], root)
    status = run(["git", "status", "--porcelain=v1", "--untracked-files=normal"], root)
    remote = run(["git", "remote", "get-url", "origin"], root)
    shallow = run(["git", "rev-parse", "--is-shallow-repository"], root)
    rules: list[dict[str, Any]] = []
    for name in RULE_FILES:
        candidate = root / name
        if candidate.is_file():
            rules.append(file_meta(candidate, root))
    workflows: list[dict[str, Any]] = []
    for pattern in WORKFLOW_GLOBS:
        for candidate in sorted(root.glob(pattern)):
            if candidate.is_file():
                workflows.append(file_meta(candidate, root))
    dirty_paths = []
    for line in status["stdout"].splitlines():
        if len(line) >= 4:
            dirty_paths.append(line[3:])
    return {
        "state": "PASS",
        "path": root.as_posix(),
        "head": head["stdout"].strip() if head["returncode"] == 0 else None,
        "branch": branch["stdout"].strip() if branch["returncode"] == 0 and branch["stdout"].strip() else "DETACHED",
        "origin": redact_remote(remote["stdout"]) if remote["returncode"] == 0 else None,
        "shallow": shallow["stdout"].strip() == "true",
        "dirty": bool(dirty_paths),
        "dirty_paths": dirty_paths,
        "rule_files": rules,
        "workflow_files": workflows,
        "contents_exported": False,
    }


def atomic_write(path: Path, payload: dict[str, Any]) -> None:
    body = dict(payload)
    body["receipt_sha256"] = hashlib.sha256(canonical(body)).hexdigest()
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix="." + path.name + ".", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(body, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(tmp_name, 0o600)
        os.replace(tmp_name, path)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--target-repo", type=Path)
    parser.add_argument("--status-root", type=Path)
    args = parser.parse_args()
    target = args.target_repo or (Path(os.environ["SIGNAL_LATTICE_TARGET_REPO"]) if os.environ.get("SIGNAL_LATTICE_TARGET_REPO") else None)
    status = args.status_root or (Path(os.environ["SIGNAL_LATTICE_STATUS_ROOT"]) if os.environ.get("SIGNAL_LATTICE_STATUS_ROOT") else None)
    disk = shutil.disk_usage("/")
    systemd = run(["systemctl", "--version"]) if shutil.which("systemctl") else {"returncode": 2, "stdout": "UNAVAILABLE", "stderr": ""}
    ports = run(["ss", "-lntup"]) if shutil.which("ss") else {"returncode": 2, "stdout": "UNAVAILABLE", "stderr": ""}
    units = run(["systemctl", "list-unit-files", "signal-lattice*", "--no-pager"]) if shutil.which("systemctl") else {"returncode": 2, "stdout": "UNAVAILABLE", "stderr": ""}
    payload = {
        "schema_version": "1.0.0",
        "state": "PASS",
        "host": {
            "platform": platform.platform(),
            "python": platform.python_version(),
            "cpu_count": os.cpu_count(),
            "disk_total": disk.total,
            "disk_used": disk.used,
            "disk_free": disk.free,
            "hostname": platform.node(),
            "systemd": systemd,
            "listening_ports": ports,
            "signal_lattice_units": units,
        },
        "target_repository": capture_repo(target),
        "status_repository": capture_repo(status),
        "secrets_collected": False,
        "environment_exported": False,
        "production_write_actions_performed": False,
        "developer_research_required": False,
    }
    atomic_write(args.output, payload)
    print(json.dumps({"state": "PASS", "output": args.output.as_posix()}, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
