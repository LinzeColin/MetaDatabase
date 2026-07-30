from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .receipts import atomic_json


@dataclass(frozen=True)
class CheckoutInspection:
    state: str
    reason: str | list[str] | None
    path: str
    expected_commit: str
    actual_commit: str | None = None
    root_tree: str | None = None
    clean: bool | None = None
    shallow: bool | None = None
    object_format: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            key: value
            for key, value in {
                "state": self.state,
                "reason": self.reason,
                "path": self.path,
                "expected_commit": self.expected_commit,
                "actual_commit": self.actual_commit,
                "root_tree": self.root_tree,
                "clean": self.clean,
                "shallow": self.shallow,
                "object_format": self.object_format,
            }.items()
            if value is not None
        }


def canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git_env(home: Path | None = None) -> dict[str, str]:
    resolved_home = home or Path(tempfile.gettempdir()) / "signal-lattice-git-home"
    resolved_home.mkdir(parents=True, exist_ok=True)
    return {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": str(resolved_home),
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_ASKPASS": "/bin/false",
        "SSH_ASKPASS": "/bin/false",
        "PAGER": "cat",
        "GIT_PAGER": "cat",
    }


def run_git(
    cwd: Path,
    *args: str,
    timeout: int = 120,
    check: bool = True,
    home: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        ["git", *args],
        cwd=cwd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
        env=git_env(home),
    )
    if check and completed.returncode:
        raise RuntimeError(completed.stderr.strip() or f"git {' '.join(args)} failed")
    return completed


def inspect_checkout(path: Path, expected_commit: str) -> CheckoutInspection:
    path = path.resolve()
    if not path.is_dir():
        return CheckoutInspection("BLOCKED", "CHECKOUT_PATH_NOT_DIRECTORY", str(path), expected_commit)
    try:
        inside = run_git(path, "rev-parse", "--is-inside-work-tree").stdout.strip()
        actual = run_git(path, "rev-parse", "HEAD").stdout.strip()
        tree = run_git(path, "rev-parse", "HEAD^{tree}").stdout.strip()
        shallow = run_git(path, "rev-parse", "--is-shallow-repository").stdout.strip() == "true"
        dirty = bool(run_git(path, "status", "--porcelain=v1", "--untracked-files=all").stdout.strip())
        object_format = run_git(path, "rev-parse", "--show-object-format").stdout.strip()
        run_git(path, "cat-file", "-e", f"{expected_commit}^{{commit}}")
        run_git(path, "cat-file", "-e", f"{expected_commit}^{{tree}}")
    except Exception as exc:
        return CheckoutInspection(
            "BLOCKED",
            f"INVALID_GIT_CHECKOUT:{type(exc).__name__}",
            str(path),
            expected_commit,
        )
    reasons: list[str] = []
    if inside != "true":
        reasons.append("NOT_A_GIT_WORKTREE")
    if actual != expected_commit:
        reasons.append("COMMIT_MISMATCH")
    if dirty:
        reasons.append("DIRTY_CHECKOUT")
    # A shallow checkout is accepted only when the exact commit and complete tree/blob graph
    # needed for the frozen snapshot are locally present. build_upstream_seal re-verifies every
    # tracked object, so history depth is not a correctness prerequisite for a point-in-time seal.
    if shallow:
        missing = run_git(path, "fsck", "--connectivity-only", "--no-dangling", check=False)
        if missing.returncode:
            reasons.append("SHALLOW_CHECKOUT_MISSING_OBJECTS")
    if object_format != "sha1":
        reasons.append("UNSUPPORTED_GIT_OBJECT_FORMAT")
    return CheckoutInspection(
        "PASS" if not reasons else "BLOCKED",
        None if not reasons else reasons,
        str(path),
        expected_commit,
        actual,
        tree,
        not dirty,
        shallow,
        object_format,
    )


def _verify_bundle(bundle: Path, expected_commit: str, work_dir: Path) -> dict[str, Any]:
    bundle = bundle.resolve()
    if not bundle.is_file():
        raise RuntimeError("BUNDLE_NOT_FILE")
    verify = run_git(work_dir, "bundle", "verify", str(bundle), timeout=180, check=False)
    if verify.returncode:
        raise RuntimeError("BUNDLE_VERIFY_FAILED:" + (verify.stderr.strip() or verify.stdout.strip()))
    return {
        "bundle_path": str(bundle),
        "bundle_size": bundle.stat().st_size,
        "bundle_sha256": file_sha256(bundle),
        "expected_commit": expected_commit,
        "verify_stdout_sha256": hashlib.sha256(verify.stdout.encode()).hexdigest(),
        "verify_stderr_sha256": hashlib.sha256(verify.stderr.encode()).hexdigest(),
    }


def materialize_input(
    input_path: Path,
    expected_commit: str,
    destination: Path,
    *,
    source_name: str,
) -> dict[str, Any]:
    input_path = input_path.resolve()
    if input_path.is_dir():
        inspection = inspect_checkout(input_path, expected_commit)
        if inspection.state != "PASS":
            raise RuntimeError(f"{source_name}_CHECKOUT_INVALID:{inspection.reason}")
        return {
            "source_name": source_name,
            "input_kind": "EXACT_GIT_CHECKOUT_OR_WORKTREE",
            "input_path": str(input_path),
            "materialized_path": str(input_path),
            "ephemeral": False,
            "inspection": inspection.as_dict(),
        }
    if not input_path.is_file() or input_path.suffix != ".bundle":
        raise RuntimeError(f"{source_name}_INPUT_UNSUPPORTED")
    destination = destination.resolve()
    if destination.exists():
        shutil.rmtree(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    bundle = _verify_bundle(input_path, expected_commit, destination.parent)
    clone = run_git(
        destination.parent,
        "clone",
        "--no-checkout",
        "--no-tags",
        "--",
        str(input_path),
        str(destination),
        timeout=600,
        check=False,
        home=destination.parent / ".git-home",
    )
    if clone.returncode:
        raise RuntimeError(f"{source_name}_BUNDLE_CLONE_FAILED:{clone.stderr.strip()}")
    run_git(destination, "checkout", "--detach", expected_commit, timeout=300)
    # Remove the local bundle remote so the formal checkout cannot later be used as a
    # mutable transport or accidentally fetch a different ref.
    run_git(destination, "remote", "remove", "origin", check=False)
    fsck = run_git(destination, "fsck", "--strict", "--full", "--no-reflogs", timeout=600, check=False)
    if fsck.returncode:
        raise RuntimeError(f"{source_name}_BUNDLE_FSCK_FAILED:{fsck.stderr.strip()}")
    inspection = inspect_checkout(destination, expected_commit)
    if inspection.state != "PASS":
        raise RuntimeError(f"{source_name}_MATERIALIZED_CHECKOUT_INVALID:{inspection.reason}")
    return {
        "source_name": source_name,
        "input_kind": "VERIFIED_EXACT_OFFLINE_GIT_BUNDLE",
        "input_path": str(input_path),
        "materialized_path": str(destination),
        "ephemeral": True,
        "bundle": bundle,
        "fsck_stdout_sha256": hashlib.sha256(fsck.stdout.encode()).hexdigest(),
        "fsck_stderr_sha256": hashlib.sha256(fsck.stderr.encode()).hexdigest(),
        "inspection": inspection.as_dict(),
    }


def export_bundle(checkout: Path, expected_commit: str, output: Path, *, source_name: str) -> dict[str, Any]:
    inspection = inspect_checkout(checkout, expected_commit)
    if inspection.state != "PASS":
        raise RuntimeError(f"{source_name}_CHECKOUT_INVALID:{inspection.reason}")
    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    temp_output = output.with_name("." + output.name + ".tmp")
    temp_output.unlink(missing_ok=True)
    # HEAD is required because git bundle exposes refs, not arbitrary object IDs. The
    # inspection above guarantees HEAD is the exact frozen commit.
    created = run_git(checkout, "bundle", "create", str(temp_output), "HEAD", timeout=1200, check=False)
    if created.returncode:
        raise RuntimeError(f"{source_name}_BUNDLE_CREATE_FAILED:{created.stderr.strip()}")
    os.replace(temp_output, output)
    with tempfile.TemporaryDirectory(prefix="signal-lattice-bundle-verify-") as tmp:
        materialized = Path(tmp) / "checkout"
        receipt = materialize_input(output, expected_commit, materialized, source_name=source_name)
    return {
        "source_name": source_name,
        "state": "PASS",
        "expected_commit": expected_commit,
        "root_tree": inspection.root_tree,
        "bundle_path": str(output),
        "bundle_size": output.stat().st_size,
        "bundle_sha256": file_sha256(output),
        "roundtrip_checkout_state": receipt["inspection"]["state"],
        "upstream_write_allowed": False,
        "network_required_for_consumption": False,
    }


def write_self_hashed(path: Path, payload: dict[str, Any]) -> dict[str, Any]:
    body = dict(payload)
    body["receipt_sha256"] = hashlib.sha256(canonical(body)).hexdigest()
    atomic_json(path, body)
    return body
