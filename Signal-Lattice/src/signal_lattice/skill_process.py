from __future__ import annotations

import json
import os
import resource
import socket
import sys
from typing import Any

from .builtin_skills import run_profile


class NetworkForbiddenError(RuntimeError):
    pass


def _deny_network(*args: object, **kwargs: object) -> None:
    raise NetworkForbiddenError("SKILL_NETWORK_FORBIDDEN")


def _apply_limits(memory_mb: int, cpu_seconds: int) -> None:
    memory = max(64, min(int(memory_mb), 2048)) * 1024 * 1024
    cpu = max(1, min(int(cpu_seconds), 60))
    for limit in (resource.RLIMIT_AS, resource.RLIMIT_DATA):
        try:
            resource.setrlimit(limit, (memory, memory))
        except (ValueError, OSError):
            pass
    try:
        resource.setrlimit(resource.RLIMIT_CPU, (cpu, cpu + 1))
    except (ValueError, OSError):
        pass
    try:
        resource.setrlimit(resource.RLIMIT_FSIZE, (8 * 1024 * 1024, 8 * 1024 * 1024))
    except (ValueError, OSError):
        pass
    try:
        resource.setrlimit(resource.RLIMIT_NOFILE, (64, 64))
    except (ValueError, OSError):
        pass
    socket.socket = _deny_network  # type: ignore[assignment]
    socket.create_connection = _deny_network  # type: ignore[assignment]


def main() -> int:
    raw = sys.stdin.buffer.read(25_000_000)
    if not raw or len(raw) >= 25_000_000:
        raise ValueError("SKILL_INPUT_SIZE_INVALID")
    request = json.loads(raw.decode("utf-8"))
    if not isinstance(request, dict):
        raise ValueError("SKILL_INPUT_OBJECT_REQUIRED")
    manifest = request.get("manifest")
    snapshot = request.get("snapshot")
    if not isinstance(manifest, dict) or not isinstance(snapshot, dict):
        raise ValueError("SKILL_MANIFEST_OR_SNAPSHOT_INVALID")
    _apply_limits(int(request.get("memory_mb", 256)), int(request.get("cpu_seconds", 8)))
    profile = str(manifest.get("runtime_profile", ""))
    outputs = run_profile(profile, manifest, snapshot)
    if not isinstance(outputs, list):
        raise ValueError("SKILL_OUTPUT_ARRAY_REQUIRED")
    abstained = sum(1 for item in outputs if item.get("abstain") is True)
    state = "ABSTAIN" if outputs and abstained == len(outputs) else "PASS"
    payload: dict[str, Any] = {
        "schema_version": "1.0.0",
        "state": state,
        "skill_id": manifest["skill_id"],
        "skill_version": manifest.get("skill_version", "UNKNOWN"),
        "source_commit": manifest.get("source_commit", "UNKNOWN"),
        "signals": outputs,
        "signal_count": len(outputs),
        "effective_signal_count": len(outputs) - abstained,
        "abstain_count": abstained,
        "runtime_agent_dependency": 0,
        "runtime_llm_tokens": 0,
        "network_allowed": False,
    }
    sys.stdout.write(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # child boundary: emit one safe error object
        sys.stdout.write(json.dumps({
            "schema_version": "1.0.0",
            "state": "FAILED",
            "error_code": type(exc).__name__,
            "error": str(exc)[:500],
            "runtime_agent_dependency": 0,
            "runtime_llm_tokens": 0,
        }, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
        raise SystemExit(2)
