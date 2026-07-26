#!/usr/bin/env python3
"""Measure and fail-close the bounded CyberBoss workspace budget."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any


GIB = 1024 * 1024 * 1024
MAX_ALLOWED_WORKSPACE_BYTES = 8 * GIB


class BudgetViolation(ValueError):
    """The policy or measured workspace is outside the accepted boundary."""


def load_policy(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    validate_policy(value)
    return value


def validate_policy(policy: dict[str, Any]) -> None:
    expect(policy.get("schema_version") == 1, "policy_schema")
    expect(policy.get("profile") == "constrained", "policy_profile")
    expect(policy.get("workspace_alias") == "cyberboss", "policy_alias")
    expect(
        policy.get("workspace_root") == "/srv/cyberboss-workspaces/cyberboss",
        "policy_workspace_root",
    )
    expect(
        policy.get("cache_root") == "/var/lib/cyberboss/cache",
        "policy_cache_root",
    )
    numeric_keys = (
        "workspace_max_bytes",
        "repository_objects_max_bytes",
        "worktree_max_bytes",
        "cache_max_bytes",
        "host_reserve_min_bytes",
        "hard_stop_workspace_bytes",
    )
    for key in numeric_keys:
        expect(
            isinstance(policy.get(key), int)
            and not isinstance(policy.get(key), bool)
            and policy[key] > 0,
            f"policy_numeric:{key}",
        )
    expect(
        policy["workspace_max_bytes"] <= MAX_ALLOWED_WORKSPACE_BYTES,
        "policy_workspace_above_8_gib",
    )
    expect(
        policy["hard_stop_workspace_bytes"] == MAX_ALLOWED_WORKSPACE_BYTES,
        "policy_hard_stop",
    )
    thresholds = policy.get("thresholds") or {}
    recover = thresholds.get("recover_ratio")
    warn = thresholds.get("warn_ratio")
    protect = thresholds.get("protect_ratio")
    expect(
        all(isinstance(value, (int, float)) for value in (recover, warn, protect)),
        "policy_threshold_type",
    )
    expect(0 < recover < warn < protect < 1, "policy_threshold_order")
    commands = policy.get("cleanup_commands")
    expect(isinstance(commands, list) and len(commands) == 3, "policy_cleanup_commands")
    expect(
        all(isinstance(command, str) and command.strip() for command in commands),
        "policy_cleanup_command",
    )
    serialized = json.dumps(commands)
    expect("--prune=now" not in serialized, "policy_destructive_prune")
    expect(
        policy.get("forbidden_cleanup_flags") == ["--prune=now"],
        "policy_forbidden_cleanup",
    )


def expect(condition: bool, code: str) -> None:
    if not condition:
        raise BudgetViolation(code)


def measured_usage(
    policy: dict[str, Any],
    workspace_root: Path,
    cache_root: Path,
) -> dict[str, int]:
    configured_workspace = Path(policy["workspace_root"])
    configured_cache = Path(policy["cache_root"])
    expect(workspace_root.is_absolute(), "workspace_path_absolute")
    expect(cache_root.is_absolute(), "cache_path_absolute")
    expect(workspace_root == configured_workspace, "workspace_path_mismatch")
    expect(cache_root == configured_cache, "cache_path_mismatch")
    expect(workspace_root.exists(), "workspace_missing")
    expect(not workspace_root.is_symlink(), "workspace_symlink")
    real_workspace = workspace_root.resolve(strict=True)
    expect(real_workspace == configured_workspace, "workspace_realpath_mismatch")
    git_dir = resolve_git_dir(real_workspace)
    workspace_bytes = tree_bytes(real_workspace)
    repository_objects_bytes = tree_bytes(git_dir / "objects")
    cache_bytes = tree_bytes(cache_root) if cache_root.exists() else 0
    return {
        "workspace_bytes": workspace_bytes,
        "repository_objects_bytes": repository_objects_bytes,
        "worktree_bytes": max(0, workspace_bytes - tree_bytes(git_dir)),
        "cache_bytes": cache_bytes,
        "host_available_bytes": shutil.disk_usage(real_workspace).free,
    }


def resolve_git_dir(workspace_root: Path) -> Path:
    result = subprocess.run(
        ["git", "-C", str(workspace_root), "rev-parse", "--absolute-git-dir"],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        env={**os.environ, "GIT_OPTIONAL_LOCKS": "0"},
    )
    expect(result.returncode == 0, "workspace_not_git")
    git_dir = Path(result.stdout.strip()).resolve(strict=True)
    expect(git_dir == workspace_root / ".git", "workspace_git_dir_external")
    return git_dir


def tree_bytes(root: Path) -> int:
    if not root.exists() and not root.is_symlink():
        return 0
    total = 0
    stack = [root]
    while stack:
        candidate = stack.pop()
        stats = candidate.lstat()
        total += stats.st_size
        if stats and candidate.is_dir() and not candidate.is_symlink():
            stack.extend(candidate.iterdir())
    return total


def evaluate(policy: dict[str, Any], usage: dict[str, Any]) -> dict[str, Any]:
    limits = {
        "workspace_bytes": policy["workspace_max_bytes"],
        "repository_objects_bytes": policy["repository_objects_max_bytes"],
        "worktree_bytes": policy["worktree_max_bytes"],
        "cache_bytes": policy["cache_max_bytes"],
    }
    normalized: dict[str, int] = {}
    ratios: dict[str, float] = {}
    reasons: list[str] = []
    state = "recover"
    thresholds = policy["thresholds"]

    for metric, limit in limits.items():
        value = usage.get(metric)
        expect(
            isinstance(value, int) and not isinstance(value, bool) and value >= 0,
            f"usage_invalid:{metric}",
        )
        normalized[metric] = value
        ratio = value / limit
        ratios[metric] = round(ratio, 6)
        if metric == "workspace_bytes" and value > policy["hard_stop_workspace_bytes"]:
            state = "stop"
            reasons.append("workspace_above_8_gib")
        elif ratio >= thresholds["protect_ratio"] and state != "stop":
            state = "protect"
            reasons.append(f"{metric}_protect")
        elif ratio >= thresholds["warn_ratio"] and state == "recover":
            state = "guard"
            reasons.append(f"{metric}_guard")

    available = usage.get("host_available_bytes")
    expect(
        isinstance(available, int)
        and not isinstance(available, bool)
        and available >= 0,
        "usage_invalid:host_available_bytes",
    )
    normalized["host_available_bytes"] = available
    if available < policy["host_reserve_min_bytes"] and state != "stop":
        state = "protect"
        reasons.append("host_reserve_protect")

    return {
        "schema_version": 1,
        "result": "fail" if state == "stop" else "pass",
        "state": state,
        "usage": normalized,
        "limits": limits,
        "ratios": ratios,
        "reasons": reasons,
        "hard_stop_workspace_bytes": policy["hard_stop_workspace_bytes"],
        "cleanup_commands": policy["cleanup_commands"],
        "no_prune_now": True,
    }


def atomic_write(path: Path, value: dict[str, Any]) -> None:
    expect(path.is_absolute(), "output_path_absolute")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.tmp-{os.getpid()}")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.chmod(temporary, 0o640)
    os.replace(temporary, path)


def main() -> int:
    default_policy = Path(__file__).resolve().parents[1] / "config/workspace-budget.json"
    parser = argparse.ArgumentParser()
    parser.add_argument("--policy", type=Path, default=default_policy)
    parser.add_argument("--workspace-root", type=Path)
    parser.add_argument("--cache-root", type=Path)
    parser.add_argument("--usage-fixture", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    try:
        policy = load_policy(args.policy)
        if args.usage_fixture:
            usage = json.loads(args.usage_fixture.read_text(encoding="utf-8"))
            evidence_scope = "deterministic_fixture"
        else:
            usage = measured_usage(
                policy,
                args.workspace_root or Path(policy["workspace_root"]),
                args.cache_root or Path(policy["cache_root"]),
            )
            evidence_scope = "live_filesystem"
        result = evaluate(policy, usage)
        result["evidence_scope"] = evidence_scope
        result["workspace_alias"] = policy["workspace_alias"]
        if args.output:
            atomic_write(args.output, result)
    except (OSError, json.JSONDecodeError, BudgetViolation) as error:
        print(f"WORKSPACE_BUDGET=FAIL reason={error}", file=sys.stderr)
        return 2

    print(
        f"WORKSPACE_BUDGET={'PASS' if result['result'] == 'pass' else 'FAIL'} "
        f"state={result['state']} scope={evidence_scope} "
        f"workspace_bytes={result['usage']['workspace_bytes']} "
        "hard_stop_bytes=8589934592 no_prune_now=true"
    )
    return 0 if result["result"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
