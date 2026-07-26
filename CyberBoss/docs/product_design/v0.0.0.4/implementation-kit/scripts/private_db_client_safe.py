#!/usr/bin/env python3
"""CyberBoss fail-closed wrapper for the shared no-clone Private DB client."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
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


def main() -> int:
    default_policy = Path(__file__).resolve().parents[1] / "config/identity-scope.policy.json"
    parser = argparse.ArgumentParser()
    parser.add_argument("--policy", type=Path, default=default_policy)
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

    result = subprocess.run(command, check=False)
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
