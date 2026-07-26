#!/usr/bin/env python3
"""Prefix-locked OCI Object Storage adapter with a deterministic mock backend."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import shutil
import sys
from pathlib import Path
from typing import Any

from scope_policy import (
    ScopeViolation,
    load_policy,
    validate_attestation,
    validate_object_scope,
)


class ObjectAdapterError(RuntimeError):
    pass


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _md5_base64(path: Path) -> str:
    digest = hashlib.md5(usedforsecurity=False)
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return base64.b64encode(digest.digest()).decode("ascii")


def _mock_path(root: Path, bucket: str, key: str) -> Path:
    base = (root / bucket).resolve()
    target = (base / key).resolve()
    if target != base and base not in target.parents:
        raise ScopeViolation("mock:path_escape")
    return target


def mock_operation(
    operation: str,
    root: Path,
    bucket: str,
    key: str,
    source: Path | None,
    destination: Path | None,
) -> dict[str, Any]:
    target = _mock_path(root, bucket, key)
    if operation == "list":
        base = (root / bucket).resolve()
        keys = []
        if base.is_dir():
            keys = [
                path.relative_to(base).as_posix()
                for path in base.rglob("*")
                if path.is_file()
                and path.relative_to(base).as_posix().startswith(key.rstrip("/"))
            ]
        return {"action": "listed", "count": len(keys), "keys": sorted(keys)}
    if operation == "put":
        if source is None or not source.is_file():
            raise ObjectAdapterError("source_unreadable")
        if target.exists():
            if _sha256(target) == _sha256(source):
                return {
                    "action": "already_present",
                    "sha256": _sha256(source),
                    "immutable": True,
                }
            raise ObjectAdapterError("immutable_key_conflict")
        target.parent.mkdir(parents=True, exist_ok=True, mode=0o750)
        shutil.copyfile(source, target)
        os.chmod(target, 0o440)
        return {"action": "created", "sha256": _sha256(target), "immutable": True}
    if operation == "get":
        if destination is None:
            raise ObjectAdapterError("destination_required")
        if not target.is_file():
            raise ObjectAdapterError("object_missing")
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(target, destination)
        os.chmod(destination, 0o600)
        return {"action": "downloaded", "sha256": _sha256(destination)}
    raise ObjectAdapterError("unsupported_operation")


def real_operation(
    operation: str,
    config_file: Path,
    profile: str,
    bucket: str,
    key: str,
    source: Path | None,
    destination: Path | None,
) -> dict[str, Any]:
    try:
        import oci
    except ImportError as error:
        raise ObjectAdapterError("activation_pending:oci_sdk_missing") from error
    config = oci.config.from_file(str(config_file), profile)
    client = oci.object_storage.ObjectStorageClient(config)
    namespace = client.get_namespace().data
    if operation == "list":
        response = client.list_objects(namespace, bucket, prefix=key)
        return {"action": "listed", "count": len(response.data.objects)}
    if operation == "put":
        if source is None or not source.is_file():
            raise ObjectAdapterError("source_unreadable")
        expected_md5 = _md5_base64(source)
        try:
            existing = client.head_object(namespace, bucket, key)
        except oci.exceptions.ServiceError as error:
            if error.status != 404:
                raise
        else:
            actual_md5 = existing.headers.get("content-md5")
            if actual_md5 == expected_md5:
                return {
                    "action": "already_present",
                    "sha256": _sha256(source),
                    "immutable": True,
                }
            raise ObjectAdapterError("immutable_key_conflict")
        with source.open("rb") as handle:
            client.put_object(
                namespace,
                bucket,
                key,
                handle,
                content_md5=expected_md5,
            )
        return {"action": "created", "sha256": _sha256(source), "immutable": True}
    if operation == "get":
        if destination is None:
            raise ObjectAdapterError("destination_required")
        response = client.get_object(namespace, bucket, key)
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open("wb") as handle:
            for block in response.data.raw.stream(1024 * 1024, decode_content=False):
                handle.write(block)
        os.chmod(destination, 0o600)
        return {"action": "downloaded", "sha256": _sha256(destination)}
    raise ObjectAdapterError("unsupported_operation")


def main() -> int:
    kit = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--policy",
        type=Path,
        default=kit / "config/identity-scope.policy.json",
    )
    parser.add_argument("--backend", choices=["mock", "oci-sdk"], default="mock")
    parser.add_argument("--bucket")
    parser.add_argument("--configured-bucket")
    parser.add_argument("--mock-root", type=Path)
    parser.add_argument("--config-file", type=Path)
    parser.add_argument("--profile", default="DEFAULT")
    parser.add_argument("--scope-attestation", type=Path)
    parser.add_argument("--execute-real", action="store_true")
    sub = parser.add_subparsers(dest="operation", required=True)
    sub.add_parser("plan")
    listing = sub.add_parser("list")
    listing.add_argument("key", nargs="?")
    put = sub.add_parser("put")
    put.add_argument("key")
    put.add_argument("source", type=Path)
    get = sub.add_parser("get")
    get.add_argument("key")
    get.add_argument("destination", type=Path)
    args = parser.parse_args()

    try:
        policy = load_policy(args.policy)
        prefix = policy["oci"]["object_prefix"]
        if args.operation == "plan":
            print(
                json.dumps(
                    {
                        "schema_version": 1,
                        "status": "activation_pending",
                        "real_write": False,
                        "bucket": "slot:oci-bucket-name",
                        "object_prefix": prefix,
                        "operations": ["list", "put", "get"],
                        "forbidden_operations": ["delete", "overwrite", "create_bucket"],
                        "required_attestation": True,
                    },
                    indent=2,
                    sort_keys=True,
                )
            )
            return 0

        if not args.bucket or not args.configured_bucket:
            raise ObjectAdapterError("bucket_and_configured_bucket_required")
        key = args.key if getattr(args, "key", None) else prefix
        validate_object_scope(
            policy, "oci", args.bucket, key, args.configured_bucket
        )
        source = getattr(args, "source", None)
        destination = getattr(args, "destination", None)
        if args.backend == "mock":
            if args.mock_root is None:
                raise ObjectAdapterError("mock_root_required")
            action = mock_operation(
                args.operation,
                args.mock_root,
                args.bucket,
                key,
                source,
                destination,
            )
            result = {
                "schema_version": 1,
                "status": "simulator_verified",
                "real_provider": False,
                "bucket_scope_verified": True,
                "prefix_scope_verified": True,
                **action,
            }
        else:
            if not args.execute_real:
                raise ObjectAdapterError("hazard_blocked:execute_real_flag_required")
            if args.config_file is None or args.scope_attestation is None:
                raise ObjectAdapterError("activation_pending:config_or_attestation_missing")
            attestation = json.loads(
                args.scope_attestation.read_text(encoding="utf-8")
            )
            validate_attestation(
                policy,
                attestation,
                "oci",
                "objects",
                f"bucket:{args.configured_bucket}",
            )
            if attestation.get("bucket") != args.configured_bucket:
                raise ScopeViolation("attestation:oci_bucket")
            result = {
                "schema_version": 1,
                "status": "verified",
                "real_provider": True,
                "bucket_scope_verified": True,
                "prefix_scope_verified": True,
                **real_operation(
                    args.operation,
                    args.config_file,
                    args.profile,
                    args.bucket,
                    key,
                    source,
                    destination,
                ),
            }
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    except (
        OSError,
        KeyError,
        json.JSONDecodeError,
        ScopeViolation,
        ObjectAdapterError,
    ) as error:
        print(f"OCI_OBJECT_ADAPTER=FAIL reason={error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
