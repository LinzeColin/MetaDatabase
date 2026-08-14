#!/bin/sh
set -eu

if [ "$#" -ne 0 ]; then
  printf '%s\n' 'usage: run_current_production_ovh_github_actions_environment_rest_name_diagnostic.sh' >&2
  exit 64
fi

PYTHONDONTWRITEBYTECODE=1 python3 - <<'PY'
from __future__ import annotations

import json
import shutil
import subprocess
from datetime import datetime, timezone


REPOSITORY = "LinzeColin/MetaDatabase"
ENDPOINT = "repos/LinzeColin/MetaDatabase/environments?per_page=100&page=1"
CANONICAL_ENVIRONMENT_NAME = "production"
TIMEOUT_SECONDS = 10
NAME_SELECTION = ".environments | map(.name)"


def facts() -> dict[str, object]:
    return {
        "schema_version": "1.0.0",
        "observation_type": "ABD_REDACTED_CURRENT_PRODUCTION_OVH_GITHUB_ACTIONS_ENVIRONMENT_REST_NAME_DIAGNOSTIC",
        "observed_on": datetime.now(timezone.utc).date().isoformat(),
        "github_actions_rest_access": "UNAVAILABLE_REDACTED",
        "environment_name_page_state": "GITHUB_ACTIONS_REST_ENVIRONMENT_LOOKUP_UNAVAILABLE_REDACTED",
        "canonical_production_environment_observed_in_first_page": False,
        "github_rest_get_requests": 0,
        "environment_names_read_in_memory_only": True,
        "github_rest_non_name_response_fields_emitted_or_persisted": False,
        "github_actions_environment_secret_name_or_value_read_or_emitted": False,
        "github_actions_workflow_created_updated_or_dispatched": False,
        "provider_api_requests": 0,
        "browser_login_submitted": False,
    }


def names_only(payload: object) -> set[str] | None:
    if not isinstance(payload, list):
        return None
    names: set[str] = set()
    for item in payload:
        if not isinstance(item, str):
            return None
        names.add(item)
    return names


result = facts()
gh = shutil.which("gh")
if gh is None:
    print(json.dumps(result, ensure_ascii=True, sort_keys=True, separators=(",", ":")))
    raise SystemExit(0)
result["github_rest_get_requests"] = 1
try:
    query = subprocess.run(
        [gh, "api", "--method", "GET", ENDPOINT, "--jq", NAME_SELECTION],
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
result["github_actions_rest_access"] = "AVAILABLE"
if names is None:
    result["environment_name_page_state"] = "GITHUB_ACTIONS_REST_ENVIRONMENT_RESPONSE_INVALID_REDACTED"
elif CANONICAL_ENVIRONMENT_NAME in names:
    result["environment_name_page_state"] = "CANONICAL_PRODUCTION_ENVIRONMENT_PRESENT_IN_FIRST_PAGE"
    result["canonical_production_environment_observed_in_first_page"] = True
else:
    result["environment_name_page_state"] = "CANONICAL_PRODUCTION_ENVIRONMENT_NOT_OBSERVED_IN_FIRST_PAGE_REDACTED"
print(json.dumps(result, ensure_ascii=True, sort_keys=True, separators=(",", ":")))
PY
