#!/bin/sh
set -eu

if [ "$#" -ne 0 ]; then
  printf '%s\n' 'usage: run_current_production_ovh_process_auth_source_diagnostic.sh' >&2
  exit 64
fi

PYTHONDONTWRITEBYTECODE=1 python3 - <<'PY'
from __future__ import annotations

import json
import os
import shutil
import subprocess
from datetime import datetime, timezone
from typing import Callable


TIMEOUT_SECONDS = 3
FIELD_GROUPS = (
    ("OVH_ENDPOINT", "OVH_APPLICATION_KEY", "OVH_APPLICATION_SECRET", "OVH_CONSUMER_KEY", ("OVH_SERVICE_NAME", "OVH_VPS_SERVICE_NAME")),
    ("ABD_OVH_ENDPOINT", "ABD_OVH_APPLICATION_KEY", "ABD_OVH_APPLICATION_SECRET", "ABD_OVH_CONSUMER_KEY", ("ABD_OVH_SERVICE_NAME", "ABD_OVH_VPS_SERVICE_NAME")),
)


def facts() -> dict[str, object]:
    return {
        "schema_version": "1.0.0",
        "observation_type": "ABD_REDACTED_CURRENT_PRODUCTION_OVH_PROCESS_AUTH_SOURCE_DIAGNOSTIC",
        "observed_on": datetime.now(timezone.utc).date().isoformat(),
        "current_process_source_state": "NO_COMPLETE_LEGACY_GROUP_REDACTED",
        "user_launchd_source_state": "UNAVAILABLE_REDACTED",
        "auth_target_source_ready": False,
        "provider_api_requests": 0,
        "environment_value_emitted_or_persisted": False,
        "browser_login_submitted": False,
    }


def group_complete(present: Callable[[str], bool]) -> bool:
    for endpoint, application_key, application_secret, consumer_key, service_names in FIELD_GROUPS:
        if all(present(name) for name in (endpoint, application_key, application_secret, consumer_key)) and any(present(name) for name in service_names):
            return True
    return False


def current_process_present(name: str) -> bool:
    return bool(os.environ.get(name))


def launchd_present_getter(binary: str) -> Callable[[str], bool]:
    cache: dict[str, bool] = {}

    def present(name: str) -> bool:
        if name not in cache:
            try:
                result = subprocess.run(
                    [binary, "getenv", name],
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                    check=False,
                    timeout=TIMEOUT_SECONDS,
                )
            except (OSError, subprocess.TimeoutExpired):
                cache[name] = False
            else:
                cache[name] = result.returncode == 0 and bool(result.stdout.strip())
        return cache[name]

    return present


result = facts()
result["current_process_source_state"] = "COMPLETE_LEGACY_AUTH_TARGET_FIELDS" if group_complete(current_process_present) else "NO_COMPLETE_LEGACY_GROUP_REDACTED"
launchctl = shutil.which("launchctl")
if launchctl is not None:
    try:
        session = subprocess.run(
            [launchctl, "print", "gui/%s" % os.getuid()],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
            timeout=TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired):
        session = None
    if session is not None and session.returncode == 0:
        result["user_launchd_source_state"] = "COMPLETE_LEGACY_AUTH_TARGET_FIELDS" if group_complete(launchd_present_getter(launchctl)) else "NO_COMPLETE_LEGACY_GROUP_REDACTED"

complete = "COMPLETE_LEGACY_AUTH_TARGET_FIELDS"
result["auth_target_source_ready"] = complete in {result["current_process_source_state"], result["user_launchd_source_state"]}
print(json.dumps(result, ensure_ascii=True, sort_keys=True, separators=(",", ":")))
PY
