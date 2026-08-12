#!/bin/sh
set -eu

usage() {
  printf '%s\n' 'usage: run_current_production_ovh_provider_api_diagnostic.sh --protected-auth-target-json <regular-file>'
}

if [ "$#" -ne 2 ] || [ "$1" != "--protected-auth-target-json" ]; then
  usage >&2
  exit 64
fi

PYTHONDONTWRITEBYTECODE=1 python3 - "$2" <<'PY'
from __future__ import annotations

import hashlib
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener


def facts() -> dict[str, Any]:
    return {
        "schema_version": "1.0.0",
        "observation_type": "ABD_REDACTED_CURRENT_PRODUCTION_OVH_PROVIDER_API_DIAGNOSTIC",
        "observed_on": datetime.now(timezone.utc).date().isoformat(),
        "protected_credential_state": "UNAVAILABLE_REDACTED",
        "current_production_target_state": "UNAVAILABLE_REDACTED",
        "provider_api_access": "CREDENTIAL_SOURCE_UNAVAILABLE_REDACTED",
        "provider_api_requests": 0,
        "resource_presence": "NOT_OBSERVED",
        "power_state": "NOT_OBSERVED",
        "network_state": "NOT_OBSERVED",
        "credential_material_emitted_or_persisted": False,
        "target_mapping_emitted_or_persisted": False,
        "raw_provider_response_emitted_or_persisted": False,
        "browser_login_submitted": False,
    }


def load_protected_source(path: Path) -> dict[str, str]:
    if not path.is_file() or path.is_symlink():
        raise ValueError("protected source is unavailable")
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or set(raw) != {"endpoint", "application_key", "application_secret", "consumer_key", "service_name"}:
        raise ValueError("protected source schema is invalid")
    values = {key: value for key, value in raw.items() if isinstance(value, str) and value}
    if set(values) != set(raw):
        raise ValueError("protected source values are invalid")
    parsed = urlsplit(values["endpoint"])
    if parsed.scheme != "https" or parsed.port is not None or not parsed.hostname or not (parsed.hostname == "api.ovh.com" or parsed.hostname.endswith(".api.ovh.com")) or parsed.path.rstrip("/") != "/1.0" or parsed.query or parsed.fragment:
        raise ValueError("protected endpoint is invalid")
    if any(character not in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789._-" for character in values["service_name"]):
        raise ValueError("protected service mapping is invalid")
    return values


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        return None


def power_state(payload: dict[str, Any]) -> str:
    state = str(payload.get("state", payload.get("status", ""))).strip().lower()
    if state in {"running", "active", "up", "ok"}:
        return "POWERED_ON"
    if state in {"stopped", "off", "down", "suspended"}:
        return "POWERED_OFF"
    return "UNKNOWN"


def network_state(payload: dict[str, Any]) -> str:
    state = str(payload.get("networkState", "")).strip().lower()
    if state in {"ready", "running", "active", "up", "ok"}:
        return "NETWORK_READY"
    if state in {"down", "degraded", "error", "failed"}:
        return "NETWORK_DEGRADED"
    return "UNKNOWN"


result = facts()
try:
    secret = load_protected_source(Path(sys.argv[1]))
except (OSError, UnicodeDecodeError, ValueError, json.JSONDecodeError):
    print(json.dumps(result, ensure_ascii=True, sort_keys=True, separators=(",", ":")))
    raise SystemExit(0)

result["protected_credential_state"] = "AVAILABLE_IN_MEMORY"
result["current_production_target_state"] = "RESOLVED_IN_MEMORY"
result["provider_api_access"] = "REQUEST_FAILED_REDACTED"
path = "/vps/" + quote(secret["service_name"], safe="")
url = secret["endpoint"].rstrip("/") + path
timestamp = str(int(time.time()))
signature_input = "+".join((secret["application_secret"], secret["consumer_key"], "GET", url, "", timestamp))
signature = "$1$" + hashlib.sha1(signature_input.encode("utf-8")).hexdigest()
request = Request(
    url,
    method="GET",
    headers={
        "Accept": "application/json",
        "X-Ovh-Application": secret["application_key"],
        "X-Ovh-Consumer": secret["consumer_key"],
        "X-Ovh-Signature": signature,
        "X-Ovh-Timestamp": timestamp,
    },
)
result["provider_api_requests"] = 1
try:
    with build_opener(NoRedirect()).open(request, timeout=10) as response:
        payload = json.loads(response.read().decode("utf-8"))
except HTTPError as exc:
    result["provider_api_access"] = "ACCESS_DENIED_REDACTED" if exc.code in {401, 403} else "REQUEST_FAILED_REDACTED"
except (OSError, URLError, TimeoutError, UnicodeDecodeError):
    result["provider_api_access"] = "REQUEST_FAILED_REDACTED"
except json.JSONDecodeError:
    result["provider_api_access"] = "RESPONSE_INVALID_REDACTED"
else:
    if not isinstance(payload, dict):
        result["provider_api_access"] = "RESPONSE_INVALID_REDACTED"
    else:
        result["provider_api_access"] = "QUERY_PASS"
        result["resource_presence"] = "PRESENT"
        result["power_state"] = power_state(payload)
        result["network_state"] = network_state(payload)

print(json.dumps(result, ensure_ascii=True, sort_keys=True, separators=(",", ":")))
PY
