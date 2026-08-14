#!/bin/sh
set -eu

if [ "$#" -ne 0 ]; then
  printf '%s\n' 'usage: run_current_production_ovh_github_actions_environment_name_diagnostic.sh' >&2
  exit 64
fi

PYTHONDONTWRITEBYTECODE=1 python3 - <<'PY'
from __future__ import annotations

import json
import shutil
import subprocess
from datetime import datetime, timezone


OWNER = "LinzeColin"
REPOSITORY = "MetaDatabase"
CANONICAL_ENVIRONMENT_NAME = "production"
TIMEOUT_SECONDS = 10
QUERY = """
query($owner: String!, $repository: String!, $environmentName: String!) {
  repository(owner: $owner, name: $repository) {
    environment(name: $environmentName) {
      name
    }
  }
}
"""


def facts() -> dict[str, object]:
    return {
        "schema_version": "1.0.0",
        "observation_type": "ABD_REDACTED_CURRENT_PRODUCTION_OVH_GITHUB_ACTIONS_ENVIRONMENT_NAME_DIAGNOSTIC",
        "observed_on": datetime.now(timezone.utc).date().isoformat(),
        "github_actions_access": "UNAVAILABLE_REDACTED",
        "environment_name_scope_state": "GITHUB_ACTIONS_ENVIRONMENT_LOOKUP_UNAVAILABLE_REDACTED",
        "canonical_production_environment_observed": False,
        "github_graphql_query_requests": 0,
        "environment_names_read_in_memory_only": True,
        "environment_values_read_or_emitted": False,
        "github_actions_environment_secret_name_or_value_read_or_emitted": False,
        "github_graphql_mutation_executed": False,
        "github_actions_workflow_created_updated_or_dispatched": False,
        "provider_api_requests": 0,
        "browser_login_submitted": False,
    }


result = facts()
gh = shutil.which("gh")
if gh is None:
    print(json.dumps(result, ensure_ascii=True, sort_keys=True, separators=(",", ":")))
    raise SystemExit(0)
result["github_graphql_query_requests"] = 1
try:
    query = subprocess.run(
        [
            gh,
            "api",
            "graphql",
            "-F",
            "owner=%s" % OWNER,
            "-F",
            "repository=%s" % REPOSITORY,
            "-F",
            "environmentName=%s" % CANONICAL_ENVIRONMENT_NAME,
            "-f",
            "query=%s" % QUERY,
            "--jq",
            ".data.repository.environment.name // empty",
        ],
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
    environment_name = query.stdout.decode("utf-8").strip()
except UnicodeDecodeError:
    result["github_actions_access"] = "AVAILABLE"
    result["environment_name_scope_state"] = "GITHUB_ACTIONS_ENVIRONMENT_RESPONSE_INVALID_REDACTED"
    print(json.dumps(result, ensure_ascii=True, sort_keys=True, separators=(",", ":")))
    raise SystemExit(0)
result["github_actions_access"] = "AVAILABLE"
if environment_name == CANONICAL_ENVIRONMENT_NAME:
    result["environment_name_scope_state"] = "CANONICAL_PRODUCTION_ENVIRONMENT_PRESENT"
    result["canonical_production_environment_observed"] = True
elif environment_name == "":
    result["environment_name_scope_state"] = "CANONICAL_PRODUCTION_ENVIRONMENT_NOT_OBSERVED_REDACTED"
else:
    result["environment_name_scope_state"] = "GITHUB_ACTIONS_ENVIRONMENT_RESPONSE_INVALID_REDACTED"
print(json.dumps(result, ensure_ascii=True, sort_keys=True, separators=(",", ":")))
PY
