#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
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


def cgroup_for(pid: str) -> str:
    try:
        return (Path("/proc") / pid / "cgroup").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def is_signal_lattice_process(line: str, cgroup: str) -> bool:
    return "signal-lattice" in line.lower() or "signal-lattice" in cgroup.lower()


def process_record(line: str, process: str, in_scope: bool) -> dict[str, str]:
    parts = line.split(None, 2)
    argv = parts[2] if len(parts) > 2 else ""
    return {
        "process": process,
        "pid": parts[0] if parts else "UNKNOWN",
        "comm": parts[1] if len(parts) > 1 else "UNKNOWN",
        "argv_sha256": hashlib.sha256(argv.encode("utf-8", errors="replace")).hexdigest(),
        "scope": "signal-lattice" if in_scope else "external-host",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    checks: dict[str, bool] = {}
    details: dict[str, object] = {}

    services = ("signal-lattice-api.service", "signal-lattice-worker.service", "signal-lattice-cloudflared.service")
    for unit in services:
        result = run("systemctl", "is-active", unit)
        checks[f"unit:{unit}"] = result.returncode == 0 and result.stdout.strip() == "active"
    timers = (
        "signal-lattice-source-sync.timer", "signal-lattice-evolution.timer",
        "signal-lattice-outbox-sync.timer", "signal-lattice-status.timer", "signal-lattice-backup.timer",
    )
    for unit in timers:
        result = run("systemctl", "is-enabled", unit)
        checks[f"timer:{unit}"] = result.returncode == 0

    result = run("ps", "-eo", "pid=,comm=,args=")
    matches: list[dict[str, str]] = []
    external_matches: list[dict[str, str]] = []
    for line in (result.stdout or "").splitlines():
        lowered = line.lower()
        if "runtime_audit.py" in lowered:
            continue
        for name in FORBIDDEN_PROCESSES:
            if name in lowered:
                pid = line.split(None, 1)[0] if line.split(None, 1) else ""
                in_scope = is_signal_lattice_process(line, cgroup_for(pid))
                record = process_record(line, name, in_scope)
                (matches if in_scope else external_matches).append(record)
                break
    checks["no_agent_or_model_process"] = not matches
    details["forbidden_process_matches"] = matches
    details["external_forbidden_process_matches"] = external_matches

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
        "external_agent_process_count": len(external_matches),
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
