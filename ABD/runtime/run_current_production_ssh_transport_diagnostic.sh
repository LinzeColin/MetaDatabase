#!/bin/sh
set -eu

usage() {
  printf '%s\n' 'usage: run_current_production_ssh_transport_diagnostic.sh --host <ssh-target>'
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

PYTHONDONTWRITEBYTECODE=1 python3 - "$host" <<'PY'
from __future__ import annotations

import errno
import json
import socket
import subprocess
import sys
from datetime import datetime, timezone


host = sys.argv[1]
base = [
    "ssh",
    "-o", "BatchMode=yes",
    "-o", "ConnectTimeout=10",
    "-o", "StrictHostKeyChecking=yes",
    "-o", "PasswordAuthentication=no",
    "-o", "KbdInteractiveAuthentication=no",
]
facts = {
    "schema_version": "1.0.0",
    "observation_type": "ABD_REDACTED_CURRENT_PRODUCTION_SSH_TRANSPORT_DIAGNOSTIC",
    "observed_on": datetime.now(timezone.utc).date().isoformat(),
    "ssh_config_state": "UNAVAILABLE_REDACTED",
    "route": "UNKNOWN",
    "name_resolution": "NOT_ATTEMPTED",
    "tcp_connectivity": "NOT_ATTEMPTED",
    "ssh_authentication": "NOT_ATTEMPTED",
    "noninteractive_sudo": "NOT_ATTEMPTED",
}


def classify_ssh(result: subprocess.CompletedProcess[str]) -> str:
    if result.returncode == 0:
        return "PASS"
    message = result.stderr.lower()
    if "permission denied" in message:
        return "AUTH_FAILED_REDACTED"
    if "host key verification failed" in message or "no hostkey" in message:
        return "HOST_KEY_FAILED_REDACTED"
    if "connection timed out" in message or "operation timed out" in message or "no route to host" in message or "connection refused" in message:
        return "TRANSPORT_FAILED_REDACTED"
    return "OTHER_FAILED_REDACTED"


def run_ssh(command: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [*base, host, command],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )


try:
    config = subprocess.run(
        ["ssh", "-G", host],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        check=False,
    )
    values: dict[str, str] = {}
    if config.returncode == 0:
        for line in config.stdout.splitlines():
            key, separator, value = line.partition(" ")
            if separator and key in {"hostname", "port", "proxycommand", "proxyjump"}:
                values[key] = value.strip()
    hostname = values.get("hostname", "")
    port = int(values.get("port", "0"))
    if not hostname or not 1 <= port <= 65535:
        raise ValueError("SSH configuration is incomplete")
except (OSError, ValueError):
    print(json.dumps(facts, ensure_ascii=True, sort_keys=True, separators=(",", ":")))
    raise SystemExit(0)

proxy = values.get("proxycommand", "none") != "none" or values.get("proxyjump", "none") != "none"
facts["ssh_config_state"] = "RESOLVED"
facts["route"] = "PROXY" if proxy else "DIRECT"

if proxy:
    facts["name_resolution"] = "NOT_APPLICABLE_PROXY"
    facts["tcp_connectivity"] = "NOT_APPLICABLE_PROXY"
else:
    try:
        socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)
    except socket.gaierror:
        facts["name_resolution"] = "FAILED_REDACTED"
    else:
        facts["name_resolution"] = "PASS"
        try:
            with socket.create_connection((hostname, port), timeout=3):
                pass
        except TimeoutError:
            facts["tcp_connectivity"] = "CONNECT_TIMEOUT_REDACTED"
        except OSError as exc:
            facts["tcp_connectivity"] = "CONNECTION_REFUSED_REDACTED" if exc.errno == errno.ECONNREFUSED else "OTHER_FAILED_REDACTED"
        else:
            facts["tcp_connectivity"] = "PASS"

if facts["route"] == "PROXY" or facts["tcp_connectivity"] == "PASS":
    ssh_result = run_ssh("true")
    facts["ssh_authentication"] = classify_ssh(ssh_result)
    if facts["ssh_authentication"] == "PASS":
        sudo_result = run_ssh("sudo -n true")
        facts["noninteractive_sudo"] = "PASS" if sudo_result.returncode == 0 else "UNAVAILABLE_REDACTED"

print(json.dumps(facts, ensure_ascii=True, sort_keys=True, separators=(",", ":")))
PY
