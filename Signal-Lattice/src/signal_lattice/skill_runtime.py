from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

from .config import Settings


def canonical_bytes(payload: object) -> bytes:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sha(payload: object) -> str:
    return hashlib.sha256(canonical_bytes(payload)).hexdigest()


def run_isolated_skill(
    skill: dict[str, Any],
    snapshot: dict[str, Any],
    settings: Settings,
    deadline_seconds: float | None = None,
) -> dict[str, Any]:
    manifest = dict(skill.get("manifest") or {})
    manifest.setdefault("skill_id", skill["skill_id"])
    manifest.setdefault("skill_version", skill["skill_version"])
    manifest.setdefault("runtime_profile", skill["runtime_profile"])
    manifest.setdefault("source_commit", skill["source_commit"])
    request = {
        "manifest": manifest,
        "snapshot": snapshot,
        "memory_mb": settings.skill_memory_mb,
        "cpu_seconds": settings.skill_timeout_seconds,
    }
    input_bytes = canonical_bytes(request)
    input_sha = hashlib.sha256(input_bytes).hexdigest()
    timeout = float(settings.skill_timeout_seconds)
    if deadline_seconds is not None:
        timeout = max(0.5, min(timeout, deadline_seconds))
    env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "TZ": "UTC",
        "PYTHONUNBUFFERED": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
        "HOME": "/nonexistent",
        "PYTHONPATH": str(Path(__file__).resolve().parents[1]),
    }
    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix=f"sl-{skill['skill_id'][:24]}-") as temp:
        try:
            completed = subprocess.run(
                [sys.executable, "-m", "signal_lattice.skill_process"],
                input=input_bytes,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=temp,
                env=env,
                timeout=timeout,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return {
                "state": "TIMEOUT",
                "skill_id": skill["skill_id"],
                "input_sha256": input_sha,
                "duration_ms": int((time.monotonic() - started) * 1000),
                "error_code": "SKILL_TIMEOUT",
                "output": None,
                "output_sha256": None,
            }
    duration_ms = int((time.monotonic() - started) * 1000)
    if len(completed.stdout) > 20_000_000:
        return {
            "state": "FAILED", "skill_id": skill["skill_id"], "input_sha256": input_sha,
            "duration_ms": duration_ms, "error_code": "SKILL_OUTPUT_TOO_LARGE",
            "output": None, "output_sha256": None,
        }
    try:
        output = json.loads(completed.stdout.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        output = None
    if completed.returncode != 0 or not isinstance(output, dict) or output.get("state") == "FAILED":
        error_code = "SKILL_PROCESS_FAILED"
        if isinstance(output, dict) and output.get("error_code"):
            error_code = str(output["error_code"])
        return {
            "state": "FAILED", "skill_id": skill["skill_id"], "input_sha256": input_sha,
            "duration_ms": duration_ms, "error_code": error_code,
            "output": output, "output_sha256": sha(output) if output is not None else None,
            "stderr": completed.stderr.decode("utf-8", errors="replace")[:1000],
        }
    state = str(output.get("state", "FAILED"))
    if state not in {"PASS", "ABSTAIN"}:
        state = "FAILED"
    return {
        "state": state,
        "skill_id": skill["skill_id"],
        "input_sha256": input_sha,
        "duration_ms": duration_ms,
        "error_code": None if state in {"PASS", "ABSTAIN"} else "SKILL_OUTPUT_STATE_INVALID",
        "output": output,
        "output_sha256": sha(output),
    }
