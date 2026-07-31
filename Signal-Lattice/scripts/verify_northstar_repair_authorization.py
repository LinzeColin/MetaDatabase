#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

EXPECTED_VERSION = "0.0.0.1.41"
EXPECTED_URL = "https://signal-lattice.linzezhang.com"
EXPECTED_SCOPE = "NORTHSTAR_WEBSITE_DEPLOYMENT_REPAIR"


def canonical(payload: dict) -> bytes:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--receipt", type=Path, default=Path("evidence/repair/northstar_repair_authorization.json"))
    parser.add_argument("--version", default=EXPECTED_VERSION)
    args = parser.parse_args()
    findings: list[str] = []
    try:
        data = json.loads(args.receipt.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(json.dumps({"state": "BLOCKED", "findings": ["AUTHORIZATION_RECEIPT_UNREADABLE:" + type(exc).__name__]}, sort_keys=True))
        return 2
    expected = data.get("receipt_sha256")
    body = dict(data); body.pop("receipt_sha256", None)
    if expected != hashlib.sha256(canonical(body)).hexdigest(): findings.append("AUTHORIZATION_RECEIPT_HASH_MISMATCH")
    if data.get("authorized") is not True: findings.append("OWNER_AUTHORIZATION_MISSING")
    if data.get("scope") != EXPECTED_SCOPE: findings.append("AUTHORIZATION_SCOPE_INVALID")
    if data.get("version") != args.version or args.version != EXPECTED_VERSION: findings.append("AUTHORIZATION_VERSION_INVALID")
    if data.get("public_url") != EXPECTED_URL: findings.append("AUTHORIZATION_PUBLIC_URL_INVALID")
    if data.get("production_side_effect_authorization") is not True: findings.append("PRODUCTION_SIDE_EFFECT_NOT_AUTHORIZED")
    if data.get("formal_release_pass_claimed") is not False: findings.append("PREMATURE_RELEASE_PASS_CLAIM")
    result = {"state": "PASS" if not findings else "BLOCKED", "findings": findings, "version": args.version, "public_url": EXPECTED_URL}
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if not findings else 2


if __name__ == "__main__":
    raise SystemExit(main())
