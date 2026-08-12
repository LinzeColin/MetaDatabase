#!/bin/sh
set -eu

if [ "$#" -ne 0 ]; then
  printf '%s\n' 'usage: run_current_production_ovh_keychain_auth_source_diagnostic.sh' >&2
  exit 64
fi

PYTHONDONTWRITEBYTECODE=1 python3 - <<'PY'
from __future__ import annotations

import json
import shutil
import subprocess
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlsplit


CANONICAL_SERVICES = (
    "ABD_OVH_CURRENT_PRODUCTION_AUTH_TARGET",
    "ABD_OVH_CURRENT_PRODUCTION_API",
    "OVH_CURRENT_PRODUCTION_AUTH_TARGET",
    "OVH_CURRENT_PRODUCTION_API",
)
INTERNET_HOSTS = ("api.ovh.com", "eu.api.ovh.com", "sg.api.ovh.com")
TIMEOUT_SECONDS = 3


def facts() -> dict[str, Any]:
    return {
        "schema_version": "1.0.0",
        "observation_type": "ABD_REDACTED_CURRENT_PRODUCTION_OVH_KEYCHAIN_AUTH_SOURCE_DIAGNOSTIC",
        "observed_on": datetime.now(timezone.utc).date().isoformat(),
        "keychain_access": "UNAVAILABLE_REDACTED",
        "auth_target_source_state": "KEYCHAIN_UNAVAILABLE_REDACTED",
        "auth_target_source_ready": False,
        "provider_api_requests": 0,
        "credential_material_emitted_or_persisted": False,
        "target_mapping_emitted_or_persisted": False,
        "browser_login_submitted": False,
    }


def run_security(args: list[str], *, capture_password: bool) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        args,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE if capture_password else subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
        timeout=TIMEOUT_SECONDS,
    )


def strict_auth_target(raw: bytes) -> bool:
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return False
    if not isinstance(value, dict) or set(value) != {"endpoint", "application_key", "application_secret", "consumer_key", "service_name"}:
        return False
    if any(not isinstance(item, str) or not item for item in value.values()):
        return False
    endpoint = urlsplit(value["endpoint"])
    if endpoint.scheme != "https" or endpoint.port is not None or not endpoint.hostname or not (endpoint.hostname == "api.ovh.com" or endpoint.hostname.endswith(".api.ovh.com")) or endpoint.path.rstrip("/") != "/1.0" or endpoint.query or endpoint.fragment:
        return False
    return all(character in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789._-" for character in value["service_name"])


result = facts()
security = shutil.which("security")
if security is None:
    print(json.dumps(result, ensure_ascii=True, sort_keys=True, separators=(",", ":")))
    raise SystemExit(0)

try:
    available = run_security([security, "list-keychains", "-d", "user"], capture_password=False)
except (OSError, subprocess.TimeoutExpired):
    print(json.dumps(result, ensure_ascii=True, sort_keys=True, separators=(",", ":")))
    raise SystemExit(0)
if available.returncode != 0:
    print(json.dumps(result, ensure_ascii=True, sort_keys=True, separators=(",", ":")))
    raise SystemExit(0)

result["keychain_access"] = "AVAILABLE"
result["auth_target_source_state"] = "CANONICAL_SOURCE_NOT_RESOLVED_REDACTED"
for service in CANONICAL_SERVICES:
    try:
        metadata = run_security([security, "find-generic-password", "-s", service], capture_password=False)
    except (OSError, subprocess.TimeoutExpired):
        continue
    if metadata.returncode != 0:
        continue
    try:
        credential = run_security([security, "find-generic-password", "-s", service, "-w"], capture_password=True)
    except (OSError, subprocess.TimeoutExpired):
        result["auth_target_source_state"] = "CANONICAL_SOURCE_UNSTRUCTURED_REDACTED"
        break
    if credential.returncode == 0 and strict_auth_target(credential.stdout):
        result["auth_target_source_state"] = "CANONICAL_SOURCE_RESOLVED_IN_MEMORY"
        result["auth_target_source_ready"] = True
        break
    result["auth_target_source_state"] = "CANONICAL_SOURCE_UNSTRUCTURED_REDACTED"
    break
else:
    for host in INTERNET_HOSTS:
        try:
            item = run_security([security, "find-internet-password", "-s", host], capture_password=False)
        except (OSError, subprocess.TimeoutExpired):
            continue
        if item.returncode == 0:
            result["auth_target_source_state"] = "PROVIDER_KEYCHAIN_ENTRY_PRESENT_UNSCOPED_REDACTED"
            break

print(json.dumps(result, ensure_ascii=True, sort_keys=True, separators=(",", ":")))
PY
