#!/usr/bin/env python3
"""Fail-closed CyberBoss identity, data and object scope checks."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path, PurePosixPath
from typing import Any


class ScopeViolation(ValueError):
    """The requested operation is outside the locked CyberBoss scope."""


def load_policy(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    validate_policy(value)
    return value


def _expect(condition: bool, code: str) -> None:
    if not condition:
        raise ScopeViolation(code)


def _safe_relative(value: str, code: str) -> PurePosixPath:
    _expect(bool(value), f"{code}:empty")
    _expect("\\" not in value and "\x00" not in value, f"{code}:invalid_character")
    path = PurePosixPath(value)
    _expect(not path.is_absolute(), f"{code}:absolute")
    _expect(".." not in path.parts and "." not in path.parts, f"{code}:traversal")
    return path


def validate_policy(policy: dict[str, Any]) -> None:
    _expect(policy.get("schema_version") == 1, "policy_schema")
    code = policy.get("code") or {}
    _expect(code.get("repository") == "LinzeColin/MetaDatabase", "code_repository")
    _expect(code.get("project_subpath") == "CyberBoss", "code_subpath")
    _expect(code.get("workspace_alias") == "cyberboss", "workspace_alias")
    _expect(code.get("execution_identity") == "cyberboss", "code_identity")
    _expect(code.get("allowed_write_globs") == ["CyberBoss/**"], "write_globs")
    _expect(code.get("root_integration_enabled") is False, "root_integration")
    _expect(code.get("new_repository_allowed") is False, "new_repository")

    data = policy.get("data") or {}
    _expect(data.get("repository") == "LinzeColin/Private-Database", "data_repository")
    _expect(data.get("branch") == "main", "data_branch")
    _expect(data.get("area") == "Private-MetaDatabase", "data_area")
    _expect(data.get("domain") == "CyberBoss", "data_domain")
    _expect(data.get("access_mode") == "no_clone_client", "data_access_mode")
    _expect(data.get("execution_identity") == "cyberboss-data", "data_identity")
    _expect(
        data.get("credential_config_dir") == "/var/lib/cyberboss-data/.config/gh",
        "data_credential_dir",
    )
    _expect(
        data.get("client_path")
        == "/opt/cyberboss-cloud/shared/private_db_client.py",
        "data_client_path",
    )
    _expect(
        data.get("safe_wrapper_path")
        == "/opt/cyberboss-cloud/shared/private_db_client_safe.py",
        "data_wrapper_path",
    )
    _expect(data.get("client_basename") == "private_db_client.py", "data_client")
    _expect(
        data.get("allowed_operations") == ["ingest", "get", "list", "verify"],
        "data_allowed_operations",
    )
    _expect(
        set(data.get("forbidden_operations") or []) == {"clone", "put", "delete"},
        "data_forbidden_operations",
    )
    separation = policy.get("identity_separation") or {}
    _expect(
        separation.get("code_identity_can_execute_data_client") is False,
        "identity_code_data_client",
    )
    _expect(
        separation.get("data_identity_can_modify_code_workspace") is False,
        "identity_data_code_write",
    )
    _expect(
        separation.get("shared_secret_material") is False,
        "identity_shared_secret",
    )

    cloudflare = policy.get("cloudflare") or {}
    _expect(cloudflare.get("zone") == "linzezhang.com", "cloudflare_zone")
    _expect(
        cloudflare.get("hostname") == "cyberboss.linzezhang.com",
        "cloudflare_hostname",
    )
    access = cloudflare.get("access") or {}
    _expect(access.get("application_type") == "self_hosted", "access_type")
    _expect(access.get("deny_by_default") is True, "access_default_deny")
    _expect(
        access.get("service_auth_api_decision") == "non_identity",
        "access_service_decision",
    )
    _expect(
        access.get("service_auth_selector") == "service_token",
        "access_service_selector",
    )
    _expect(access.get("forbidden_decisions") == ["bypass"], "access_bypass")
    _expect(
        "everyone" in (access.get("forbidden_include_rules") or []),
        "access_everyone",
    )
    dns = cloudflare.get("dns") or {}
    _expect(dns.get("name") == cloudflare.get("hostname"), "dns_hostname")
    _expect(dns.get("proxied") is True, "dns_proxy")
    _expect(
        dns.get("activation_after") == ["access_application", "access_policy"],
        "dns_activation_order",
    )
    r2 = cloudflare.get("r2") or {}
    _expect(r2.get("bucket") == "cyberboss-cold", "r2_bucket")
    _expect(
        r2.get("object_prefix") == "ovh-singapore-vps-1/",
        "r2_prefix",
    )
    _expect(r2.get("public_access") is False, "r2_public")

    oci = policy.get("oci") or {}
    _expect(oci.get("bucket_slot") == "oci-bucket-name", "oci_bucket_slot")
    _expect(
        oci.get("object_prefix")
        == "cyberboss-cold-backup/ovh-singapore-vps-1/",
        "oci_prefix",
    )
    _expect(oci.get("public_access") is False, "oci_public")
    _expect(
        set(oci.get("allowed_permissions") or [])
        == {"OBJECT_INSPECT", "OBJECT_READ", "OBJECT_CREATE"},
        "oci_allowed_permissions",
    )
    _expect("OBJECT_DELETE" in (oci.get("forbidden_permissions") or []), "oci_delete")

    activation = policy.get("activation") or {}
    _expect(
        activation.get("real_write_requires_exact_scope_attestation") is True,
        "scope_attestation",
    )
    _expect(
        activation.get("broad_account_write_is_hazard_blocked") is True,
        "broad_write",
    )


def validate_code_scope(
    policy: dict[str, Any],
    repository: str,
    subpath: str,
    alias: str,
    write_paths: list[str],
) -> None:
    code = policy["code"]
    _expect(repository == code["repository"], "scope:repository")
    _expect(subpath == code["project_subpath"], "scope:subpath")
    _expect(alias == code["workspace_alias"], "scope:alias")
    project = PurePosixPath(code["project_subpath"])
    for value in write_paths:
        candidate = _safe_relative(value, "scope:write_path")
        _expect(
            candidate == project or project in candidate.parents,
            f"scope:write_path:{value}",
        )


def validate_data_scope(
    policy: dict[str, Any],
    repository: str,
    branch: str,
    area: str,
    domain: str,
    operation: str,
) -> None:
    data = policy["data"]
    _expect(repository == data["repository"], "scope:data_repository")
    _expect(branch == data["branch"], "scope:data_branch")
    _expect(area == data["area"], "scope:data_area")
    _expect(domain == data["domain"], "scope:data_domain")
    _expect(operation in data["allowed_operations"], f"scope:data_operation:{operation}")
    _expect(operation not in data["forbidden_operations"], "scope:data_forbidden")


def validate_object_scope(
    policy: dict[str, Any],
    provider: str,
    bucket: str,
    key: str,
    configured_oci_bucket: str | None = None,
) -> None:
    _expect(provider in {"r2", "oci"}, f"scope:provider:{provider}")
    object_path = _safe_relative(key, "scope:object_key")
    normalized = object_path.as_posix()
    if provider == "r2":
        config = policy["cloudflare"]["r2"]
        _expect(bucket == config["bucket"], "scope:r2_bucket")
    else:
        config = policy["oci"]
        _expect(bool(configured_oci_bucket), "scope:oci_bucket_unconfigured")
        _expect(bucket == configured_oci_bucket, "scope:oci_bucket")
    prefix = config["object_prefix"]
    _expect(
        normalized == prefix.rstrip("/") or normalized.startswith(prefix),
        f"scope:{provider}_prefix",
    )


def validate_attestation(
    policy: dict[str, Any],
    attestation: dict[str, Any],
    provider: str,
    resource: str,
    expected_resource: str,
) -> None:
    _expect(attestation.get("schema_version") == 1, "attestation:schema")
    _expect(attestation.get("provider") == provider, "attestation:provider")
    _expect(attestation.get("resource") == resource, "attestation:resource")
    _expect(
        attestation.get("resource_scope") == expected_resource,
        "attestation:resource_scope",
    )
    _expect(
        attestation.get("broad_account_write") is False,
        "attestation:broad_account_write",
    )
    _expect(
        attestation.get("unrelated_write_permissions") == [],
        "attestation:unrelated_write",
    )
    permissions = set(attestation.get("permissions") or [])
    if provider == "cloudflare":
        required = {
            "access": {"Access: Apps and Policies Write"},
            "dns": {"DNS Write"},
            "r2": {"Workers R2 Storage Write"},
        }[resource]
        _expect(permissions == required, "attestation:permissions")
    else:
        allowed = set(policy["oci"]["allowed_permissions"])
        forbidden = set(policy["oci"]["forbidden_permissions"])
        _expect(bool(permissions), "attestation:permissions_empty")
        _expect(permissions <= allowed, "attestation:permissions_broad")
        _expect(not permissions & forbidden, "attestation:permissions_forbidden")
        _expect(
            attestation.get("object_prefix") == policy["oci"]["object_prefix"],
            "attestation:oci_prefix",
        )


def main() -> int:
    default_policy = Path(__file__).resolve().parents[1] / "config/identity-scope.policy.json"
    parser = argparse.ArgumentParser()
    parser.add_argument("--policy", type=Path, default=default_policy)
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("validate")

    code = sub.add_parser("code")
    code.add_argument("--repository", required=True)
    code.add_argument("--subpath", required=True)
    code.add_argument("--alias", required=True)
    code.add_argument("--write-path", action="append", default=[])

    data = sub.add_parser("data")
    data.add_argument("--repository", required=True)
    data.add_argument("--branch", required=True)
    data.add_argument("--area", required=True)
    data.add_argument("--domain", required=True)
    data.add_argument("--operation", required=True)

    obj = sub.add_parser("object")
    obj.add_argument("--provider", required=True)
    obj.add_argument("--bucket", required=True)
    obj.add_argument("--key", required=True)
    obj.add_argument("--configured-oci-bucket")

    args = parser.parse_args()
    try:
        policy = load_policy(args.policy)
        if args.command == "code":
            validate_code_scope(
                policy,
                args.repository,
                args.subpath,
                args.alias,
                args.write_path,
            )
        elif args.command == "data":
            validate_data_scope(
                policy,
                args.repository,
                args.branch,
                args.area,
                args.domain,
                args.operation,
            )
        elif args.command == "object":
            validate_object_scope(
                policy,
                args.provider,
                args.bucket,
                args.key,
                args.configured_oci_bucket,
            )
    except (OSError, json.JSONDecodeError, ScopeViolation) as error:
        print(f"SCOPE_POLICY=FAIL reason={error}", file=sys.stderr)
        return 2
    print(f"SCOPE_POLICY=PASS command={args.command}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
