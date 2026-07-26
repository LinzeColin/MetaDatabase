#!/usr/bin/env python3
"""CyberBoss fail-closed wrapper for the shared no-clone Private DB client."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from scope_policy import ScopeViolation, load_policy, validate_data_scope


def client_contract(path: Path) -> dict[str, Any]:
    if path.name != "private_db_client.py" or not path.is_file():
        raise ScopeViolation("client:identity")
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(path))
    constants: dict[str, Any] = {}
    for node in tree.body:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        if isinstance(target, ast.Name) and target.id in {"REPO", "BRANCH", "AREAS"}:
            constants[target.id] = ast.literal_eval(node.value)
    if constants.get("REPO") != "LinzeColin/Private-Database":
        raise ScopeViolation("client:repository")
    if constants.get("BRANCH") != "main":
        raise ScopeViolation("client:branch")
    if "Private-MetaDatabase" not in (constants.get("AREAS") or set()):
        raise ScopeViolation("client:area")
    for operation in ("ingest", "get", "list", "verify"):
        if f'add_parser("{operation}")' not in source:
            raise ScopeViolation(f"client:missing_operation:{operation}")
    return {
        "basename": path.name,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "repository": constants["REPO"],
        "branch": constants["BRANCH"],
        "area_supported": True,
    }


def pinned_client_hash(path: Path) -> str:
    value = json.loads(path.read_text(encoding="utf-8"))
    if (
        value.get("schema_version") != 1
        or value.get("task_id") != "CB-120"
        or value.get("private_db_client", {}).get("access_mode")
        != "no_clone_client"
    ):
        raise ScopeViolation("client:version_policy")
    expected = value["private_db_client"].get("sha256")
    if not isinstance(expected, str) or len(expected) != 64:
        raise ScopeViolation("client:version_hash")
    return expected


def main() -> int:
    source_config = Path(__file__).resolve().parents[1] / "config"
    config_root = source_config if source_config.is_dir() else Path("/etc/cyberboss")
    default_policy = config_root / "identity-scope.policy.json"
    default_versions = config_root / "no-clone-client-versions.json"
    parser = argparse.ArgumentParser()
    parser.add_argument("--policy", type=Path, default=default_policy)
    parser.add_argument("--versions", type=Path, default=default_versions)
    parser.add_argument("--client", type=Path, required=True)
    parser.add_argument("--domain", required=True)
    parser.add_argument("--execute", action="store_true")
    sub = parser.add_subparsers(dest="operation", required=True)

    ingest = sub.add_parser("ingest")
    ingest.add_argument("area")
    ingest.add_argument("local_file")
    ingest.add_argument("--batch")

    get = sub.add_parser("get")
    get.add_argument("area")
    get.add_argument("relative_path")
    get.add_argument("output")

    listing = sub.add_parser("list")
    listing.add_argument("area")
    listing.add_argument("prefix", nargs="?")

    verify = sub.add_parser("verify")
    verify.add_argument("area")

    args = parser.parse_args()
    try:
        policy = load_policy(args.policy)
        validate_data_scope(
            policy,
            policy["data"]["repository"],
            policy["data"]["branch"],
            args.area,
            args.domain,
            args.operation,
        )
        contract = client_contract(args.client)
        if contract["sha256"] != pinned_client_hash(args.versions):
            raise ScopeViolation("client:sha256")
    except (OSError, SyntaxError, ValueError, ScopeViolation) as error:
        print(f"PRIVATE_DB_SCOPE=FAIL reason={error}", file=sys.stderr)
        return 2

    command = [sys.executable, str(args.client), args.operation, args.area]
    if args.operation == "ingest":
        command.extend([args.local_file, "--domain", args.domain])
        if args.batch:
            command.extend(["--batch", args.batch])
    elif args.operation == "get":
        command.extend([args.relative_path, args.output])
    elif args.operation == "list" and args.prefix:
        command.append(args.prefix)

    if not args.execute:
        print(
            json.dumps(
                {
                    "status": "plan_only",
                    "real_data_operation": False,
                    "no_clone": True,
                    "operation": args.operation,
                    "area": args.area,
                    "domain": args.domain,
                    "client": contract,
                    "argument_count": len(command),
                },
                sort_keys=True,
            )
        )
        return 0

    gh_command = os.environ.get("CB_PRIVATE_DB_GH_COMMAND", "")
    gh_config_dir = os.environ.get("CB_PRIVATE_DB_GH_CONFIG_DIR", "")
    if gh_command != "/opt/cyberboss-cloud/shared/toolchains/bin/gh":
        print("PRIVATE_DB_SCOPE=FAIL reason=runtime:gh_command", file=sys.stderr)
        return 2
    if gh_config_dir != "/var/lib/cyberboss-data/.config/gh":
        print("PRIVATE_DB_SCOPE=FAIL reason=runtime:gh_config_dir", file=sys.stderr)
        return 2
    gh_path = Path(gh_command)
    config_path = Path(gh_config_dir)
    if not gh_path.is_file() or not os.access(gh_path, os.X_OK):
        print("PRIVATE_DB_SCOPE=FAIL reason=runtime:gh_unavailable", file=sys.stderr)
        return 2
    if not config_path.is_dir() or config_path.is_symlink():
        print("PRIVATE_DB_SCOPE=FAIL reason=runtime:gh_config_unavailable", file=sys.stderr)
        return 2
    execution_env = dict(os.environ)
    execution_env["PATH"] = f"{gh_path.parent}:/usr/bin:/bin"
    execution_env["GH_CONFIG_DIR"] = gh_config_dir
    result = subprocess.run(command, check=False, env=execution_env)
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
