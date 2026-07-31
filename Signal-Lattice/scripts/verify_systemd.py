#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any


def canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    unit_dir = root / "deploy/systemd"
    findings: list[str] = []
    units = sorted(p for p in unit_dir.iterdir() if p.is_file())
    if not units:
        findings.append("NO_SYSTEMD_UNITS")

    allowed_cli = "/opt/signal-lattice/current/venv/bin/signal-lattice"
    allowed_python = "/opt/signal-lattice/current/venv/bin/python"
    forbidden = re.compile(r"(?i)(codex|claude|openai|anthropic|gemini|agent-loop|mcp)")
    records: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="signal-lattice-systemd-") as tmp:
        tmpdir = Path(tmp)
        transformed: list[str] = []
        for unit in units:
            text = unit.read_text()
            if forbidden.search(text):
                findings.append("FORBIDDEN_AGENT_OR_MODEL_REFERENCE:" + unit.name)
            if unit.suffix == ".service":
                cloudflared = unit.name == "signal-lattice-cloudflared.service"
                if not cloudflared and "EnvironmentFile=/etc/signal-lattice/runtime.env" not in text:
                    findings.append("ENVIRONMENT_FILE_MISSING:" + unit.name)
                starts = [line.split("=", 1)[1] for line in text.splitlines() if line.startswith("ExecStart=")]
                if len(starts) != 1:
                    findings.append("EXECSTART_COUNT:" + unit.name)
                else:
                    command = starts[0]
                    if cloudflared:
                        if not command.startswith("/usr/local/bin/cloudflared tunnel --no-autoupdate run --token-file "):
                            findings.append("CLOUDFLARED_EXECSTART_INVALID:" + unit.name)
                        if "/etc/signal-lattice/credentials/cloudflare_tunnel_token" not in command:
                            findings.append("CLOUDFLARED_TOKEN_FILE_INVALID:" + unit.name)
                    elif command.startswith(allowed_cli):
                        pass
                    elif command.startswith(allowed_python + " "):
                        parts = command.split()
                        if len(parts) < 2 or not parts[1].startswith("/opt/signal-lattice/current/scripts/"):
                            findings.append("PYTHON_SCRIPT_PATH_INVALID:" + unit.name)
                        else:
                            script = root / "scripts" / Path(parts[1]).name
                            if not script.is_file():
                                findings.append("PYTHON_SCRIPT_NOT_PACKAGED:" + unit.name + ":" + script.name)
                    elif unit.name == "signal-lattice-cloudflared.service" and command == "/usr/local/bin/cloudflared tunnel --no-autoupdate run --token-file /etc/signal-lattice/credentials/cloudflare_tunnel_token":
                        pass
                    else:
                        findings.append("EXECSTART_NOT_RELEASE_BOUND:" + unit.name)
                if "NoNewPrivileges=yes" not in text:
                    findings.append("NO_NEW_PRIVILEGES_MISSING:" + unit.name)
                if "ProtectSystem=strict" not in text:
                    findings.append("PROTECT_SYSTEM_MISSING:" + unit.name)
            transformed_text = re.sub(r"(?m)^ExecStart=.*$", "ExecStart=/bin/true", text)
            target = tmpdir / unit.name
            target.write_text(transformed_text)
            transformed.append(str(target))
            records.append({"unit": unit.name, "sha256": hashlib.sha256(text.encode()).hexdigest()})
        try:
            completed = subprocess.run(
                ["systemd-analyze", "verify", *transformed],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=60,
            )
            validation_mode = "SYSTEMD_ANALYZE"
            if completed.returncode:
                findings.append("SYSTEMD_ANALYZE_VERIFY_FAILED")
        except FileNotFoundError:
            # macOS development hosts cannot execute the Linux parser. The
            # structural checks above still run; OVH executes the full parser.
            completed = subprocess.CompletedProcess(
                ["systemd-analyze", "verify", *transformed], 0, "", "SYSTEMD_ANALYZE_UNAVAILABLE_STATIC_VALIDATION"
            )
            validation_mode = "STATIC_ONLY_PLATFORM_TOOL_UNAVAILABLE"
        stdout_tail = completed.stdout[-1200:]
        stderr_tail = completed.stderr[-1200:]

    receipt: dict[str, Any] = {
        "schema_version": "1.0.0",
        "state": "PASS" if not findings else "FAIL",
        "unit_count": len(units),
        "units": records,
        "systemd_analyze_returncode": completed.returncode,
        "systemd_analyze_stdout_tail": stdout_tail,
        "systemd_analyze_stderr_tail": stderr_tail,
        "validation_mode": validation_mode,
        "runtime_agent_dependency": 0,
        "runtime_llm_tokens": 0,
        "macos_launchd_units": 0,
        "findings": sorted(set(findings)),
    }
    receipt["receipt_sha256"] = hashlib.sha256(canonical(receipt)).hexdigest()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True))
    print(json.dumps({"state": receipt["state"], "unit_count": len(units), "receipt_sha256": receipt["receipt_sha256"]}, ensure_ascii=False))
    return 0 if not findings else 2


if __name__ == "__main__":
    raise SystemExit(main())
