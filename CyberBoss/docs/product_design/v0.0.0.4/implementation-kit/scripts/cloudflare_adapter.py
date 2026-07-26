#!/usr/bin/env python3
"""Idempotent, scope-attested Cloudflare activation adapter for CyberBoss."""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from scope_policy import ScopeViolation, load_policy, validate_attestation


class ProviderError(RuntimeError):
    pass


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_slot(path: str, secret: bool) -> str:
    candidate = Path(path)
    if not candidate.is_file():
        raise ProviderError(f"activation_pending:missing_slot:{candidate.name}")
    mode = candidate.stat().st_mode & 0o777
    if mode & 0o007:
        raise ProviderError(f"hazard_blocked:world_accessible_slot:{candidate.name}")
    value = candidate.read_text(encoding="utf-8").strip()
    if not value or "\n" in value or "\r" in value:
        raise ProviderError(f"hazard_blocked:invalid_slot:{candidate.name}")
    if secret and len(value) < 12:
        raise ProviderError(f"hazard_blocked:short_secret:{candidate.name}")
    return value


class ApiClient:
    def __init__(self, base_url: str, token: str = "fixture-token-value") -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token

    def request(
        self,
        method: str,
        path: str,
        body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        data = json.dumps(body).encode() if body is not None else None
        request = urllib.request.Request(
            self.base_url + path,
            data=data,
            method=method,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json",
                "User-Agent": "CyberBoss-CB020-Activation/1.0",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                result = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            raise ProviderError(f"provider_http_error:{error.code}") from error
        except (OSError, ValueError) as error:
            raise ProviderError(f"provider_transport_error:{type(error).__name__}") from error
        if not isinstance(result, dict) or result.get("success") is not True:
            count = len(result.get("errors") or []) if isinstance(result, dict) else 0
            raise ProviderError(f"provider_api_error_count:{count}")
        return result


def access_body(policy: dict[str, Any], owner: str, service_token_id: str) -> dict[str, Any]:
    access = policy["cloudflare"]["access"]
    return {
        "name": access["application_name"],
        "domain": policy["cloudflare"]["hostname"],
        "type": access["application_type"],
        "session_duration": access["session_duration"],
        "policies": [
            {
                "name": "CyberBoss owner",
                "decision": "allow",
                "precedence": 1,
                "include": [{"email": {"email": owner}}],
            },
            {
                "name": "CyberBoss status collector",
                "decision": access["service_auth_api_decision"],
                "precedence": 2,
                "include": [
                    {"service_token": {"token_id": service_token_id}}
                ],
            },
        ],
    }


def build_plan(policy: dict[str, Any]) -> dict[str, Any]:
    cloudflare = policy["cloudflare"]
    return {
        "schema_version": 1,
        "real_write": False,
        "hostname": cloudflare["hostname"],
        "steps": [
            {
                "order": 1,
                "id": "access_application",
                "method": "GET then POST or PUT",
                "endpoint": "/accounts/{account_id}/access/apps",
                "idempotency_key": "domain",
            },
            {
                "order": 2,
                "id": "access_policy",
                "method": "declarative replacement within application",
                "deny_by_default": True,
                "forbidden": ["bypass", "everyone", "any_valid_service_token"],
            },
            {
                "order": 3,
                "id": "r2_bucket",
                "method": "GET then POST if absent",
                "endpoint": "/accounts/{account_id}/r2/buckets",
                "bucket": cloudflare["r2"]["bucket"],
                "public_access": False,
            },
            {
                "order": 4,
                "id": "analytics",
                "method": "dashboard automatic setup review",
                "status": "activation_pending",
                "forbidden_fields": cloudflare["analytics"]["forbidden_fields"],
            },
            {
                "order": 5,
                "id": "dns",
                "method": "GET then POST or PUT",
                "endpoint": "/zones/{zone_id}/dns_records",
                "name": cloudflare["dns"]["name"],
                "proxied": True,
                "requires_completed": ["access_application", "access_policy"],
            },
        ],
    }


def _result_list(response: dict[str, Any]) -> list[dict[str, Any]]:
    result = response.get("result")
    if not isinstance(result, list):
        raise ProviderError("provider_result_not_list")
    return [item for item in result if isinstance(item, dict)]


def ensure_access(
    api: ApiClient,
    account_id: str,
    body: dict[str, Any],
) -> str:
    query = urllib.parse.urlencode({"domain": body["domain"], "per_page": 50})
    items = _result_list(api.request("GET", f"/accounts/{account_id}/access/apps?{query}"))
    matches = [item for item in items if item.get("domain") == body["domain"]]
    if len(matches) > 1:
        raise ProviderError("hazard_blocked:duplicate_access_app")
    if not matches:
        api.request("POST", f"/accounts/{account_id}/access/apps", body)
        return "created"
    identifier = str(matches[0].get("id") or "")
    if not identifier:
        raise ProviderError("provider_access_app_missing_id")
    api.request("PUT", f"/accounts/{account_id}/access/apps/{identifier}", body)
    return "reconciled"


def ensure_r2(api: ApiClient, account_id: str, policy: dict[str, Any]) -> str:
    config = policy["cloudflare"]["r2"]
    items = _result_list(api.request("GET", f"/accounts/{account_id}/r2/buckets?per_page=50"))
    matches = [item for item in items if item.get("name") == config["bucket"]]
    if len(matches) > 1:
        raise ProviderError("hazard_blocked:duplicate_r2_bucket")
    if matches:
        return "already_present"
    api.request(
        "POST",
        f"/accounts/{account_id}/r2/buckets",
        {
            "name": config["bucket"],
            "locationHint": "apac",
            "storageClass": config["storage_class"],
        },
    )
    return "created"


def ensure_dns(
    api: ApiClient,
    zone_id: str,
    origin: str,
    policy: dict[str, Any],
) -> str:
    config = policy["cloudflare"]["dns"]
    query = urllib.parse.urlencode(
        {"type": config["type"], "name": config["name"], "per_page": 50}
    )
    items = _result_list(api.request("GET", f"/zones/{zone_id}/dns_records?{query}"))
    matches = [
        item
        for item in items
        if item.get("type") == config["type"] and item.get("name") == config["name"]
    ]
    if len(matches) > 1:
        raise ProviderError("hazard_blocked:duplicate_dns_record")
    body = {
        "type": config["type"],
        "name": config["name"],
        "content": origin,
        "proxied": config["proxied"],
        "ttl": config["ttl"],
        "comment": "CyberBoss CB-020 governed route",
    }
    if not matches:
        api.request("POST", f"/zones/{zone_id}/dns_records", body)
        return "created"
    identifier = str(matches[0].get("id") or "")
    if not identifier:
        raise ProviderError("provider_dns_record_missing_id")
    api.request("PUT", f"/zones/{zone_id}/dns_records/{identifier}", body)
    return "reconciled"


def real_inputs(
    policy: dict[str, Any], activation: dict[str, Any]
) -> dict[str, str]:
    config = activation["cloudflare"]
    account_id = _read_slot(config["account_id_file"], False)
    zone_id = _read_slot(config["zone_id_file"], False)
    values = {
        "account_id": account_id,
        "zone_id": zone_id,
        "origin": _read_slot(config["origin_hostname_file"], False),
        "owner": _read_slot(config["owner_identity_file"], True),
        "service_token_id": _read_slot(config["status_service_token_file"], True),
        "access_token": _read_slot(config["access_token_file"], True),
        "dns_token": _read_slot(config["dns_token_file"], True),
        "r2_token": _read_slot(config["r2_token_file"], True),
    }
    attestations = {
        "access": _read_json(Path(config["access_scope_attestation_file"])),
        "dns": _read_json(Path(config["dns_scope_attestation_file"])),
        "r2": _read_json(Path(config["r2_scope_attestation_file"])),
    }
    validate_attestation(
        policy, attestations["access"], "cloudflare", "access", f"account:{account_id}"
    )
    validate_attestation(
        policy, attestations["dns"], "cloudflare", "dns", "zone:linzezhang.com"
    )
    validate_attestation(
        policy, attestations["r2"], "cloudflare", "r2", "bucket:cyberboss-cold"
    )
    return values


def apply(
    policy: dict[str, Any],
    base_url: str,
    values: dict[str, str],
    real_write: bool,
) -> dict[str, Any]:
    access = ensure_access(
        ApiClient(base_url, values["access_token"]),
        values["account_id"],
        access_body(policy, values["owner"], values["service_token_id"]),
    )
    r2 = ensure_r2(
        ApiClient(base_url, values["r2_token"]), values["account_id"], policy
    )
    dns = ensure_dns(
        ApiClient(base_url, values["dns_token"]),
        values["zone_id"],
        values["origin"],
        policy,
    )
    return {
        "schema_version": 1,
        "status": "verified" if real_write else "simulator_verified",
        "real_write": real_write,
        "simulator_must_not_claim_real_activation": not real_write,
        "step_order": [
            "access_application",
            "access_policy",
            "r2_bucket",
            "analytics",
            "dns",
        ],
        "actions": {
            "access_application": access,
            "access_policy": "deny_by_default_reconciled",
            "r2_bucket": r2,
            "analytics": "activation_pending_manual_control_plane",
            "dns": dns,
        },
    }


def main() -> int:
    kit = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--policy",
        type=Path,
        default=kit / "config/identity-scope.policy.json",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("plan")
    apply_parser = sub.add_parser("apply")
    apply_parser.add_argument("--transport", choices=["mock", "real"], required=True)
    apply_parser.add_argument("--api-base-url")
    apply_parser.add_argument("--activation-config", type=Path)
    args = parser.parse_args()

    try:
        policy = load_policy(args.policy)
        if args.command == "plan":
            print(json.dumps(build_plan(policy), indent=2, sort_keys=True))
            return 0
        if args.transport == "mock":
            if not args.api_base_url:
                raise ProviderError("mock_api_base_url_required")
            values = {
                "account_id": "fixture-account",
                "zone_id": "fixture-zone",
                "origin": "origin.cyberboss.invalid",
                "owner": "owner@cyberboss.invalid",
                "service_token_id": "00000000-0000-4000-8000-000000000020",
                "access_token": "fixture-access-token-value",
                "dns_token": "fixture-dns-token-value",
                "r2_token": "fixture-r2-token-value",
            }
            result = apply(policy, args.api_base_url, values, False)
        else:
            if not args.activation_config:
                raise ProviderError("activation_config_required")
            activation = _read_json(args.activation_config)
            values = real_inputs(policy, activation)
            base_url = activation["cloudflare"]["api_base_url"]
            if base_url != "https://api.cloudflare.com/client/v4":
                raise ProviderError("hazard_blocked:unexpected_real_api_base")
            result = apply(policy, base_url, values, True)
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    except (OSError, KeyError, json.JSONDecodeError, ScopeViolation, ProviderError) as error:
        print(f"CLOUDFLARE_ADAPTER=FAIL reason={error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
