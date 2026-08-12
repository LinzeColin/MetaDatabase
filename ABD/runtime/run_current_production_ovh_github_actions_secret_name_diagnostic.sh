#!/bin/sh
set -eu

if [ "$#" -ne 0 ]; then
  printf '%s\n' 'usage: run_current_production_ovh_github_actions_secret_name_diagnostic.sh' >&2
  exit 64
fi

PYTHONDONTWRITEBYTECODE=1 python3 - <<'PY'
from __future__ import annotations

import json
import shutil
import subprocess
from datetime import datetime, timezone


REPOSITORY = "LinzeColin/MetaDatabase"
TIMEOUT_SECONDS = 10
SECRET_GROUPS = (
    ("OVH_ENDPOINT", "OVH_APPLICATION_KEY", "OVH_APPLICATION_SECRET", "OVH_CONSUMER_KEY", ("OVH_SERVICE_NAME", "OVH_VPS_SERVICE_NAME")),
    ("ABD_OVH_ENDPOINT", "ABD_OVH_APPLICATION_KEY", "ABD_OVH_APPLICATION_SECRET", "ABD_OVH_CONSUMER_KEY", ("ABD_OVH_SERVICE_NAME", "ABD_OVH_VPS_SERVICE_NAME")),
)


def facts() -> dict[str, object]:
    return {
        "schema_version": "1.0.0",
        "observation_type": "ABD_REDACTED_CURRENT_PRODUCTION_OVH_GITHUB_ACTIONS_SECRET_NAME_DIAGNOSTIC",
        "observed_on": datetime.now(timezone.utc).date().isoformat(),
        "github_actions_access": "UNAVAILABLE_REDACTED",
        "secret_name_group_state": "GITHUB_ACTIONS_UNAVAILABLE_REDACTED",
        "secret_name_group_ready": False,
        "provider_api_requests": 0,
        "secret_value_read_or_emitted": False,
        "github_actions_workflow_created_updated_or_dispatched": False,
        "browser_login_submitted": False,
    }


def group_complete(names: set[str]) -> bool:
    for endpoint, application_key, application_secret, consumer_key, service_names in SECRET_GROUPS:
        if {endpoint, application_key, application_secret, consumer_key}.issubset(names) and any(name in names for name in service_names):
            return True
    return False


def names_only(payload: object) -> set[str] | None:
    if not isinstance(payload, list):
        return None
    names: set[str] = set()
    for item in payload:
        if not isinstance(item, dict) or set(item) != {"name"} or not isinstance(item["name"], str):
            return None
        names.add(item["name"])
    return names


result = facts()
gh = shutil.which("gh")
if gh is None:
    print(json.dumps(result, ensure_ascii=True, sort_keys=True, separators=(",", ":")))
    raise SystemExit(0)
try:
    query = subprocess.run(
        [gh, "secret", "list", "--repo", REPOSITORY, "--app", "actions", "--json", "name"],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        check=False,
        timeout=TIMEOUT_SECONDS,
    )
except (OSError, subprocess.TimeoutExpired):
    print(json.dumps(result, ensure_ascii=True, sort_keys=True, separators=(",", ":")))
    raise SystemExit(0)
if query.returncode != 0:
    print(json.dumps(result, ensure_ascii=True, sort_keys=True, separators=(",", ":")))
    raise SystemExit(0)
try:
    names = names_only(json.loads(query.stdout.decode("utf-8")))
except (UnicodeDecodeError, json.JSONDecodeError):
    names = None
if names is None:
    print(json.dumps(result, ensure_ascii=True, sort_keys=True, separators=(",", ":")))
    raise SystemExit(0)
result["github_actions_access"] = "AVAILABLE"
result["secret_name_group_ready"] = group_complete(names)
result["secret_name_group_state"] = "COMPLETE_LEGACY_AUTH_TARGET_SECRET_GROUP" if result["secret_name_group_ready"] else "NO_COMPLETE_LEGACY_SECRET_GROUP_REDACTED"
print(json.dumps(result, ensure_ascii=True, sort_keys=True, separators=(",", ":")))
PY
