#!/usr/bin/env python3
"""Fetch an anonymous public GitHub snapshot without shared authentication.

This is the only x2n path for future public-source research. It constructs a
minimal environment, disables Git config and credential helpers per command,
rejects URL userinfo/query/fragment, and never reads or changes shared auth.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import stat
import subprocess
import sys
from pathlib import Path
from typing import Optional
from urllib.parse import urlsplit


class SnapshotError(RuntimeError):
    pass


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise SnapshotError(message)


def validate_public_url(value: str) -> str:
    parsed = urlsplit(value)
    _require(parsed.scheme == "https" and parsed.hostname == "github.com" and parsed.port is None, "only public GitHub HTTPS URLs are allowed")
    _require(parsed.username is None and parsed.password is None, "URL userinfo is forbidden")
    _require(not parsed.query and not parsed.fragment, "URL query and fragment are forbidden")
    _require(re.fullmatch(r"/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+\.git", parsed.path) is not None, "repository URL path is invalid")
    return value


def validate_commit(value: str) -> str:
    _require(re.fullmatch(r"[0-9a-f]{40}", value) is not None, "exact 40-character commit is required")
    return value


def build_isolated_environment(isolation_home: Path, source: Optional[dict[str, str]] = None) -> dict[str, str]:
    inherited = source if source is not None else os.environ
    path_value = inherited.get("PATH")
    _require(bool(path_value), "PATH is required")
    environment = {
        "PATH": str(path_value),
        "HOME": str(isolation_home),
        "LC_ALL": "C",
        "LANG": "C",
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_ASKPASS": "/usr/bin/false",
        "SSH_ASKPASS": "/usr/bin/false",
    }
    if inherited.get("TMPDIR"):
        environment["TMPDIR"] = str(inherited["TMPDIR"])
    return environment


def build_git_commands(url: str, commit: str, destination: Path) -> list[list[str]]:
    validate_public_url(url)
    validate_commit(commit)
    prefix = ["git", "-c", "credential.helper=", "-c", "http.extraHeader=", "-c", "core.askPass=/usr/bin/false"]
    return [
        [*prefix, "clone", "--filter=blob:none", "--no-checkout", "--no-tags", url, str(destination)],
        [*prefix, "-C", str(destination), "fetch", "--depth=1", "origin", commit],
        [*prefix, "-C", str(destination), "checkout", "--detach", commit],
    ]


def resolve_private_root(value: Optional[str] = None) -> Path:
    raw_value = value if value is not None else os.environ.get("X2N_DATA_ROOT")
    _require(bool(raw_value), "X2N_DATA_ROOT is required")
    raw_root = Path(str(raw_value)).expanduser()
    _require(raw_root.is_dir() and not raw_root.is_symlink(), "private root is missing, invalid or symlinked")
    root = raw_root.resolve()
    _require(root.name == "xhs-douyin-2notion" and stat.S_IMODE(root.stat().st_mode) == 0o700, "private root identity or mode mismatch")
    return root


def snapshot(url: str, commit: str, run_id: str, destination_name: str, root: Path) -> Path:
    _require(re.fullmatch(r"RUN-X2N-[A-Z0-9-]+", run_id) is not None, "run id is invalid")
    _require(re.fullmatch(r"[A-Za-z0-9_.-]+", destination_name) is not None, "destination name is invalid")
    run_root = root / "downloads" / "external_research" / "runs" / run_id
    destination = run_root / "upstreams" / destination_name
    _require(destination.resolve().is_relative_to(root.resolve()), "snapshot destination escaped private root")
    _require(not destination.exists() and not destination.is_symlink(), "snapshot destination already exists")
    isolation_home = run_root / ".anonymous-git-home"
    isolation_home.mkdir(parents=True, mode=0o700, exist_ok=False)
    destination.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
    environment = build_isolated_environment(isolation_home)
    try:
        for command in build_git_commands(url, commit, destination):
            result = subprocess.run(command, env=environment, check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            _require(result.returncode == 0, "anonymous public snapshot command failed")
        result = subprocess.run(
            ["git", "-c", "credential.helper=", "-C", str(destination), "rev-parse", "HEAD"],
            env=environment,
            check=False,
            capture_output=True,
            text=True,
        )
        _require(result.returncode == 0 and result.stdout.strip() == commit, "snapshot commit verification failed")
        return destination
    finally:
        shutil.rmtree(isolation_home, ignore_errors=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--destination-name", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        destination = snapshot(args.url, args.commit, args.run_id, args.destination_name, resolve_private_root())
        print(json.dumps({
            "status": "PASS",
            "snapshot_ref": destination.name,
            "anonymous": True,
            "shared_auth_accessed": False,
            "credential_helpers_enabled": False,
            "cleanup_required_after_audit": True,
        }, sort_keys=True))
        return 0
    except (OSError, SnapshotError) as exc:
        message = "private filesystem or Git operation failed" if isinstance(exc, OSError) else str(exc)
        print(json.dumps({"status": "FAIL_CLOSED", "error": message}, sort_keys=True), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
