#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
from pathlib import Path
from typing import Any


def canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def run_git(repo: Path, *args: str) -> str:
    env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_TERMINAL_PROMPT": "0",
    }
    completed = subprocess.run(
        ["git", "-C", str(repo), *args],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=30,
        env=env,
    )
    if completed.returncode:
        raise RuntimeError(completed.stderr.strip() or f"git {' '.join(args)} failed")
    return completed.stdout.strip()


def inspect_checkout(path: Path | None, expected_commit: str, name: str) -> dict[str, Any]:
    if path is None:
        return {
            "name": name,
            "state": "BLOCKED",
            "reason": "FIXED_CHECKOUT_NOT_PROVIDED",
            "expected_commit": expected_commit,
        }
    if not path.is_dir():
        return {
            "name": name,
            "state": "BLOCKED",
            "reason": "CHECKOUT_PATH_NOT_DIRECTORY",
            "path": str(path),
            "expected_commit": expected_commit,
        }
    try:
        inside = run_git(path, "rev-parse", "--is-inside-work-tree")
        actual = run_git(path, "rev-parse", "HEAD")
        shallow = run_git(path, "rev-parse", "--is-shallow-repository")
        dirty = run_git(path, "status", "--porcelain")
        root_tree = run_git(path, "rev-parse", "HEAD^{tree}")
    except Exception as exc:
        return {
            "name": name,
            "state": "BLOCKED",
            "reason": "INVALID_GIT_CHECKOUT",
            "detail": type(exc).__name__,
            "path": str(path),
            "expected_commit": expected_commit,
        }
    reasons: list[str] = []
    if inside != "true":
        reasons.append("NOT_A_GIT_WORKTREE")
    if actual != expected_commit:
        reasons.append("COMMIT_MISMATCH")
    if shallow == "true":
        reasons.append("SHALLOW_CHECKOUT")
    if dirty:
        reasons.append("DIRTY_CHECKOUT")
    return {
        "name": name,
        "state": "PASS" if not reasons else "BLOCKED",
        "reason": None if not reasons else reasons,
        "path": str(path),
        "expected_commit": expected_commit,
        "actual_commit": actual,
        "root_tree": root_tree,
        "clean": not bool(dirty),
        "shallow": shallow == "true",
    }


def has_valid_formal_seal(root: Path) -> bool:
    path = root / "evidence/upstream/upstream_seal.json"
    if not path.is_file():
        return False
    try:
        data = json.loads(path.read_text())
        recorded = data.pop("receipt_sha256")
        return data.get("state") == "PASS" and recorded == hashlib.sha256(canonical(data)).hexdigest()
    except (KeyError, OSError, TypeError, ValueError, json.JSONDecodeError):
        return False


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--agent", type=Path)
    parser.add_argument("--meta", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    root = args.root.resolve()
    baseline = json.loads((root / "machine/facts/upstream_baseline.json").read_text())
    results = [
        inspect_checkout(args.agent, baseline["agent_database"]["commit"], "AgentDatabase"),
        inspect_checkout(args.meta, baseline["meta_database"]["commit"], "MetaDatabase"),
    ]
    state = "PASS" if all(row["state"] == "PASS" for row in results) else "BLOCKED"
    formal_seal_present = has_valid_formal_seal(root)
    if formal_seal_present:
        reason_code = "FORMAL_UPSTREAM_SEAL_PRESENT"
    elif state == "PASS":
        reason_code = "FIXED_CHECKOUTS_READY_FOR_SEAL"
    else:
        reason_code = "FIXED_UPSTREAM_INPUT_UNAVAILABLE"

    receipt: dict[str, Any] = {
        "schema_version": "1.0.0",
        "state": state,
        "reason_code": reason_code,
        "baseline_sha256": hashlib.sha256(canonical(baseline)).hexdigest(),
        "required_sources": [
            {
                "name": "AgentDatabase",
                "repository": baseline["agent_database"]["repository"],
                "commit": baseline["agent_database"]["commit"],
            },
            {
                "name": "MetaDatabase",
                "repository": baseline["meta_database"]["repository"],
                "commit": baseline["meta_database"]["commit"],
            },
        ],
        "accepted_inputs": [
            "EXACT_CLEAN_FULL_GIT_CHECKOUT",
            "EXACT_CLEAN_GIT_WORKTREE",
            "VERIFIED_EXACT_OFFLINE_GIT_BUNDLE",
            "PUBLIC_HTTPS_EXACT_COMMIT_FETCH_WHEN_EXPLICITLY_ALLOWED",
        ],
        "repositories": results,
        "network_fetch_allowed_in_current_runtime": os.environ.get("SIGNAL_LATTICE_ALLOW_PUBLIC_GITHUB_FETCH") == "1",
        "network_fetch_attempted": False,
        "upstream_write_allowed": False,
        "developer_research_required": False,
        "resolution_command": (
            "python3 scripts/build_upstream_seal.py --root . "
            "--agent \"$AGENT_DATABASE_CHECKOUT\" --meta \"$META_DATABASE_CHECKOUT\" "
            "--output evidence/upstream"
        ),
        "formal_seal_present": formal_seal_present,
    }
    receipt["receipt_sha256"] = hashlib.sha256(canonical(receipt)).hexdigest()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True))
    print(json.dumps({"state": state, "reason_code": reason_code, "receipt_sha256": receipt["receipt_sha256"]}, ensure_ascii=False))
    return 0 if state == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
