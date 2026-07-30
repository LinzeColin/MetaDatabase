#!/usr/bin/env python3
"""Public synthetic JSON worker for the A004 sidecar contract tests only."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any


UPSTREAM_REPOSITORY = "jiji262/douyin-downloader"
UPSTREAM_COMMIT = "ef3ad18c2b50e38e534f72aabe2b3fbb0b3fadd7"
UPSTREAM_TREE = "ff7774b618f269fcdc750e17dc63612f159b6b46"
UPSTREAM_VERSION = "2.0.0"
UPSTREAM_LICENSE = "MIT"
UPSTREAM_ENTRYPOINT = "douyin-dl=cli.main:main"
PROTOCOL_VERSION = "1.0.0"
HEALTH_SCHEMA = "x2n-douyin-sidecar-health-1.0"
BATCH_SCHEMA = "x2n-douyin-sidecar-batch-1.0"
ENVELOPE_SCHEMA = "x2n-douyin-sidecar-envelope-1.0"
INTEGRATION_LOCK_ID = "LOCK.X2N.DOUYIN-DOWNLOADER.001"
PROJECT_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_ROOT = PROJECT_ROOT / "packages/test-fixtures/adapters/v1/douyin_upstream"


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _file_digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _build() -> dict[str, str]:
    return {
        "executable_sha256": _file_digest(Path(__file__).resolve()),
        "resolved_lock_sha256": _file_digest(FIXTURE_ROOT / "resolved-lock.json"),
        "sbom_sha256": _file_digest(FIXTURE_ROOT / "sbom.cdx.json"),
        "scope": "ci_synthetic",
        "transitive_license_report_sha256": _file_digest(FIXTURE_ROOT / "transitive-licenses.json"),
    }


def _integration_contract_sha256() -> str:
    basis = {
        "batch_schema": BATCH_SCHEMA,
        "commit": UPSTREAM_COMMIT,
        "envelope_schema": ENVELOPE_SCHEMA,
        "health_schema": HEALTH_SCHEMA,
        "lock_id": INTEGRATION_LOCK_ID,
        "protocol_version": PROTOCOL_VERSION,
        "repository": UPSTREAM_REPOSITORY,
        "tree": UPSTREAM_TREE,
        "version": UPSTREAM_VERSION,
    }
    return hashlib.sha256(
        json.dumps(basis, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
    ).hexdigest()


def health_fixture() -> dict[str, Any]:
    return {
        "build": _build(),
        "capabilities": {"collections": True, "favorites": True, "likes": True, "max_items_per_action": 20},
        "execution": {
            "account_state_change": False,
            "automatic_pagination": False,
            "automatic_retry": False,
            "owner_action_only": True,
        },
        "integration_contract_sha256": _integration_contract_sha256(),
        "integration_lock_id": INTEGRATION_LOCK_ID,
        "protocol_version": PROTOCOL_VERSION,
        "schema_version": HEALTH_SCHEMA,
        "storage": {
            "cookies": False,
            "database": False,
            "json": False,
            "manifest": False,
            "media": False,
            "paths": False,
        },
        "upstream": {
            "commit": UPSTREAM_COMMIT,
            "entrypoint": UPSTREAM_ENTRYPOINT,
            "license": UPSTREAM_LICENSE,
            "repository": UPSTREAM_REPOSITORY,
            "tree": UPSTREAM_TREE,
            "version": UPSTREAM_VERSION,
        },
    }


def _collection(label: str) -> dict[str, str]:
    return {"key": f"x2ncol_{_digest(label)[:32]}", "name_private": f"合成收藏夹 {label[-1].upper()}"}


def _items(mode: str, count: int = 20) -> list[dict[str, Any]]:
    offset = 100 if mode == "favorites" else 200
    return [
        {
            "collection": _collection(f"collection_{index % 2}") if mode == "favorites" else None,
            "content_id": f"7310000000000000{offset + index:03d}",
            "content_type": "video" if index % 3 else "image_gallery",
            "title": f"合成抖音{('收藏' if mode == 'favorites' else '点赞')} {index:02d}",
        }
        for index in range(count)
    ]


def batch_fixture(request: Mapping[str, Any]) -> dict[str, Any]:
    mode = request.get("mode")
    if mode not in {"favorites", "likes"}:
        mode = "likes"
    sequence = request.get("sequence") if isinstance(request.get("sequence"), int) else 0
    max_items = request.get("max_items") if isinstance(request.get("max_items"), int) else 20
    return {
        "automatic_pagination": False,
        "completion_signal": "bounded_limit_reached",
        "errors": [],
        "items": _items(mode, min(20, max_items)),
        "max_items": max_items,
        "mode": mode,
        "schema_version": BATCH_SCHEMA,
        "sequence": sequence,
        "status": "ready",
    }


def response_for(request: Mapping[str, Any], case: str) -> dict[str, Any]:
    if request.get("action") == "health":
        value = health_fixture()
        if case == "version_mismatch":
            value["upstream"]["version"] = "2.0.1"
        return value
    envelope = {"batch": batch_fixture(request), "health": health_fixture(), "schema_version": ENVELOPE_SCHEMA}
    batch = envelope["batch"]
    if case == "missing_field":
        del batch["items"][0]["title"]
    elif case == "unknown_field":
        batch["items"][0]["new_upstream_field"] = "unexpected"
    elif case == "forbidden_field":
        batch["items"][0]["metadata"] = {"cover": "redacted"}
    elif case == "schema_drift":
        batch["schema_version"] = "x2n-douyin-sidecar-batch-2.0"
    elif case == "envelope_schema_drift":
        envelope["schema_version"] = "x2n-douyin-sidecar-envelope-2.0"
    elif case == "version_mismatch":
        envelope["health"]["upstream"]["version"] = "2.0.1"
    elif case == "commit_mismatch":
        envelope["health"]["upstream"]["commit"] = "0" * 40
    elif case == "tree_mismatch":
        envelope["health"]["upstream"]["tree"] = "0" * 40
    elif case == "license_mismatch":
        envelope["health"]["upstream"]["license"] = "UNKNOWN"
    elif case == "lock_mismatch":
        envelope["health"]["integration_lock_id"] = "LOCK.X2N.DOUYIN-DOWNLOADER.999"
    elif case == "contract_digest_mismatch":
        envelope["health"]["integration_contract_sha256"] = "0" * 64
    elif case == "attestation_mismatch":
        envelope["health"]["build"]["sbom_sha256"] = "0" * 64
    elif case == "persistence_enabled":
        envelope["health"]["storage"]["database"] = True
    elif case == "partial":
        batch["completion_signal"] = "unknown"
        batch["errors"] = [{"code": "PARTIAL_ITEM"}]
        batch["items"] = batch["items"][:19]
        batch["status"] = "partial"
    elif case == "auth_required":
        batch["completion_signal"] = "unknown"
        batch["errors"] = [{"code": "AUTH_EXPIRED"}]
        batch["items"] = []
        batch["status"] = "auth_required"
    elif case == "empty_unverified":
        batch["completion_signal"] = "unknown"
        batch["errors"] = [{"code": "EMPTY_UNVERIFIED"}]
        batch["items"] = []
        batch["status"] = "empty_unverified"
    elif case == "upstream_error":
        batch["completion_signal"] = "unknown"
        batch["errors"] = [{"code": "NETWORK_FAILED"}]
        batch["items"] = []
        batch["status"] = "upstream_error"
    elif case == "unknown_error":
        batch["completion_signal"] = "unknown"
        batch["errors"] = [{"code": "NEW_UPSTREAM_ERROR"}]
        batch["items"] = []
        batch["status"] = "upstream_error"
    return envelope


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--case", default="normal")
    parser.add_argument("--sentinel-argument")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    raw = sys.stdin.buffer.readline(16 * 1024 + 1)
    if len(raw) > 16 * 1024:
        return 65
    try:
        request = json.loads(raw)
    except json.JSONDecodeError:
        return 66
    if not isinstance(request, dict):
        return 67
    if args.case == "error_exit":
        return 17
    if args.case == "timeout":
        time.sleep(2)
    if args.case == "invalid_json":
        sys.stdout.write("not-json\n")
        return 0
    if args.case == "oversize":
        sys.stdout.write("x" * (300 * 1024))
        return 0
    response = response_for(request, args.case)
    sys.stdout.write(json.dumps(response, ensure_ascii=False, separators=(",", ":"), sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
