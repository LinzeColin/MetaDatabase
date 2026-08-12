#!/bin/sh
set -eu

usage() {
  printf '%s\n' 'usage: run_current_production_core_config_semantic_preflight.sh --host <ssh-target>'
}

if [ "$#" -ne 2 ] || [ "$1" != "--host" ]; then
  usage >&2
  exit 64
fi

host=$2
case "$host" in
  ''|*[!A-Za-z0-9._:-]*)
    printf '%s\n' 'ssh target contains unsupported characters' >&2
    exit 65
    ;;
esac

local_failure() {
  observed_on=$(date -u +%F)
  python3 - "$observed_on" <<'PY'
import json
import sys

print(json.dumps({
    "schema_version": "1.0.0",
    "observation_type": "ABD_REDACTED_CURRENT_PRODUCTION_CORE_CONFIG_SEMANTIC_PREFLIGHT",
    "observed_on": sys.argv[1],
    "current_target": "UNKNOWN",
    "config_file_kind": "unknown_access",
    "rebuild_file_kind": "unknown_access",
    "frozen_check": {
        "invoked": False,
        "status": "NOT_RUN",
        "activation_gate": "NOT_EMITTED",
        "secret_values_read": "NOT_EMITTED",
        "error_category": "FROZEN_CHECK_TRANSPORT_UNAVAILABLE_REDACTED",
    },
}, ensure_ascii=True, sort_keys=True, separators=(",", ":")))
PY
}

if ! facts=$(ssh -o BatchMode=yes -o ConnectTimeout=10 "$host" 'sudo -n sh -s' 2>/dev/null <<'REMOTE'
set -eu
PYTHONDONTWRITEBYTECODE=1 python3 - <<'PY'
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from subprocess import DEVNULL, PIPE, TimeoutExpired, run

BLUE_RELEASE = "/opt/abd/releases/blue"
CURRENT_RELEASE = "/opt/abd/current"
CONFIG = "/etc/abd/config.json"
ALLOWED_GATES = {
    "READY_FOR_EXPLICIT_P03_ACTIVATION",
    "BLOCKED_RUNTIME_PREREQUISITES_NOT_VERIFIED",
}


def file_kind(value: str) -> str:
    try:
        path = Path(value)
        if path.is_symlink():
            return "symlink"
        if path.is_file():
            return "regular"
        if path.is_dir():
            return "directory"
        if path.exists():
            return "other"
        return "missing"
    except OSError:
        return "unknown_access"


def target_kind() -> str:
    try:
        target = os.path.realpath(CURRENT_RELEASE)
    except OSError:
        return "UNKNOWN"
    if target == BLUE_RELEASE:
        return "BLUE_SHADOW_RELEASE"
    if target.startswith("/opt/abd/releases/"):
        return "OTHER_MANAGED_RELEASE"
    return "UNKNOWN"


target = target_kind()
config_kind = file_kind(CONFIG)
rebuild = BLUE_RELEASE + "/infra/rebuild.sh"
rebuild_kind = file_kind(rebuild)
frozen_check = {
    "invoked": False,
    "status": "NOT_RUN",
    "activation_gate": "NOT_EMITTED",
    "secret_values_read": "NOT_EMITTED",
    "error_category": "FROZEN_CHECK_PRECONDITION_FAILED_REDACTED",
}

if target == "BLUE_SHADOW_RELEASE" and config_kind == "regular" and rebuild_kind == "regular":
    try:
        completed = run(
            [rebuild, "check", "--config", CONFIG],
            cwd=BLUE_RELEASE,
            stdin=DEVNULL,
            stdout=PIPE,
            stderr=PIPE,
            check=False,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
            timeout=15,
        )
    except TimeoutExpired:
        frozen_check = {
            "invoked": True,
            "status": "FAIL",
            "activation_gate": "NOT_EMITTED",
            "secret_values_read": "NOT_EMITTED",
            "error_category": "FROZEN_CHECK_TIMEOUT_REDACTED",
        }
    else:
        if completed.returncode != 0:
            frozen_check = {
                "invoked": True,
                "status": "FAIL",
                "activation_gate": "NOT_EMITTED",
                "secret_values_read": "NOT_EMITTED",
                "error_category": "FROZEN_CHECK_FAILED_REDACTED",
            }
        else:
            try:
                value = json.loads(completed.stdout.decode("utf-8"))
                valid = (
                    isinstance(value, dict)
                    and set(value) == {"status", "activation_gate", "secret_values_read"}
                    and value["status"] == "PASS"
                    and value["activation_gate"] in ALLOWED_GATES
                    and value["secret_values_read"] is False
                )
            except (UnicodeDecodeError, json.JSONDecodeError, TypeError, KeyError):
                valid = False
            if valid:
                frozen_check = {
                    "invoked": True,
                    "status": "PASS",
                    "activation_gate": value["activation_gate"],
                    "secret_values_read": False,
                    "error_category": "NONE",
                }
            else:
                frozen_check = {
                    "invoked": True,
                    "status": "FAIL",
                    "activation_gate": "NOT_EMITTED",
                    "secret_values_read": "NOT_EMITTED",
                    "error_category": "FROZEN_CHECK_OUTPUT_MALFORMED_REDACTED",
                }

print(json.dumps({
    "schema_version": "1.0.0",
    "observation_type": "ABD_REDACTED_CURRENT_PRODUCTION_CORE_CONFIG_SEMANTIC_PREFLIGHT",
    "observed_on": datetime.now(timezone.utc).date().isoformat(),
    "current_target": target,
    "config_file_kind": config_kind,
    "rebuild_file_kind": rebuild_kind,
    "frozen_check": frozen_check,
}, ensure_ascii=True, sort_keys=True, separators=(",", ":")))
PY
REMOTE
); then
  local_failure
  exit 0
fi

printf '%s\n' "$facts"
