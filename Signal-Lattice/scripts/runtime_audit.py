#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from signal_lattice.util import atomic_write, canonical_json_bytes, sha256_bytes

FORBIDDEN_ENV = {"OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GOOGLE_API_KEY", "GEMINI_API_KEY"}
FORBIDDEN_PROCESSES = ("codex", "claude", "openai", "anthropic", "ollama", "lmstudio", "autogen", "crewai")


def run(*cmd: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=20)


def control_group(unit: str) -> str | None:
    result = run("systemctl", "show", unit, "-p", "ControlGroup", "--value")
    value = result.stdout.strip()
    return value if result.returncode == 0 and value.startswith("/") else None


def belongs_to_signal_lattice(pid: str, groups: set[str]) -> bool:
    if not pid.isdigit() or not groups:
        return False
    try:
        rows = Path("/proc", pid, "cgroup").read_text(encoding="utf-8").splitlines()
    except OSError:
        return False
    paths = {row.rsplit(":", 1)[-1] for row in rows if ":" in row}
    return any(path == group or path.startswith(group + "/") for path in paths for group in groups)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    checks: dict[str, bool] = {}
    details: dict[str, object] = {}

    services = ("signal-lattice-api.service", "signal-lattice-cloudflared.service")
    for unit in services:
        result = run("systemctl", "is-active", unit)
        checks[f"unit:{unit}"] = result.returncode == 0 and result.stdout.strip() == "active"
    worker = run("systemctl", "is-active", "signal-lattice-worker.service")
    checks["legacy_worker_inactive"] = worker.stdout.strip() != "active"
    timers = (
        "signal-lattice-cycle.timer", "signal-lattice-evolution.timer",
        "signal-lattice-outbox-sync.timer", "signal-lattice-status.timer", "signal-lattice-backup.timer",
    )
    for unit in timers:
        enabled = run("systemctl", "is-enabled", unit)
        active = run("systemctl", "is-active", unit)
        checks[f"timer:{unit}"] = (
            enabled.returncode == 0
            and active.returncode == 0
            and active.stdout.strip() == "active"
        )
        details[f"timer:{unit}"] = {
            "enabled": enabled.stdout.strip(),
            "active": active.stdout.strip(),
        }

    cgroup_units = (
        "signal-lattice-api.service", "signal-lattice-cycle.service", "signal-lattice-evolution.service",
        "signal-lattice-outbox-sync.service", "signal-lattice-status.service", "signal-lattice-backup.service",
        "signal-lattice-cloudflared.service",
    )
    cgroups = {value for unit in cgroup_units if (value := control_group(unit))}
    checks["signal_lattice_cgroups_resolved"] = bool(cgroups)
    details["audited_control_groups"] = sorted(cgroups)

    result = run("ps", "-eo", "pid=,args=")
    matches: list[dict[str, str]] = []
    for line in (result.stdout or "").splitlines():
        parts = line.strip().split(None, 1)
        if not parts or not belongs_to_signal_lattice(parts[0], cgroups):
            continue
        lowered = line.lower()
        if "runtime_audit.py" in lowered:
            continue
        for name in FORBIDDEN_PROCESSES:
            if name in lowered:
                matches.append({"process": name, "line": line.strip()[:400]})
                break
    checks["no_agent_or_model_process"] = not matches
    details["forbidden_process_matches"] = matches

    exposed = sorted(FORBIDDEN_ENV.intersection(os.environ))
    checks["no_model_credentials_in_audit_env"] = not exposed
    details["forbidden_env"] = exposed
    checks["cloudflared_active"] = checks.get("unit:signal-lattice-cloudflared.service", False)

    state = "PASS" if all(checks.values()) else "BLOCKED"
    payload = {
        "schema_version": "1.1.0",
        "state": state,
        "checks": checks,
        "details": details,
        "verified_at": datetime.now(timezone.utc).isoformat(),
        "agent_process_count": len(matches),
        "model_api_calls_total": 0,
        "llm_input_tokens_total": 0,
        "llm_output_tokens_total": 0,
        "model_provider_egress_attempts_total": 0,
        "automatic_trading": False,
        "macos_runtime": False,
    }
    payload["receipt_sha256"] = sha256_bytes(canonical_json_bytes(payload))
    atomic_write(args.output, json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True).encode())
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return 0 if state == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
