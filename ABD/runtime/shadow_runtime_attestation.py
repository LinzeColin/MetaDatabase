#!/usr/bin/env python3
"""Emit a one-shot, no-secret attestation for the ABD loopback shadow runtime."""

from __future__ import annotations

import json
import subprocess
import sys
from http.client import HTTPConnection
from typing import Any, Callable, Mapping, Sequence


SHADOW_LABEL = "com.linze.abd.runtime-role=candidate-shadow"
CORE_LABEL = "com.linze.abd.phase=S04-P01"
EXPECTED_MEMORY_BYTES = 512 * 1024 * 1024
EXPECTED_PORT_MAPPING = "127.0.0.1:8081"
EXPECTED_STATUS_PAYLOAD: dict[str, Any] = {
    "service": "ABD",
    "version": "0.0.0.1",
    "mode": "SHADOW_READ_ONLY",
    "decision": "NO_RECOMMENDATION_NO_ORDER",
    "ready": True,
    "recommendation_enabled": False,
    "order_submission_enabled": False,
    "market_or_account_connected": False,
    "gmail_or_tab_connected": False,
}
PASS_DECISION = "SHADOW_RUNTIME_ATTESTATION_PASS"
FAIL_DECISION = "SHADOW_RUNTIME_ATTESTATION_FAIL_CLOSED"
UNAVAILABLE_DECISION = "SHADOW_RUNTIME_ATTESTATION_INPUT_UNAVAILABLE_FAIL_CLOSED"


class ShadowRuntimeAttestationError(ValueError):
    """Raised when a bounded shadow-runtime observation is malformed."""


CommandRunner = Callable[[Sequence[str]], str]
StatusProbe = Callable[[str, int], Mapping[str, Any]]


def _nonnegative_int(value: Any, field: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ShadowRuntimeAttestationError("%s must be a non-negative integer" % field)
    return value


def _optional_nonnegative_int(value: Any, field: str) -> int | None:
    if value is None:
        return None
    return _nonnegative_int(value, field)


def _line_values(value: str) -> tuple[str, ...]:
    return tuple(line.strip() for line in value.splitlines() if line.strip())


def _read_memory_pair(value: str) -> tuple[int, int]:
    pieces = value.strip().split("/")
    if len(pieces) != 2:
        raise ShadowRuntimeAttestationError("container memory pair is malformed")
    try:
        memory = _nonnegative_int(int(pieces[0]), "memory_limit_bytes")
        memory_swap = _nonnegative_int(int(pieces[1]), "memory_swap_limit_bytes")
    except ValueError as exc:
        raise ShadowRuntimeAttestationError("container memory pair is malformed") from exc
    return memory, memory_swap


def _run_command(arguments: Sequence[str]) -> str:
    completed = subprocess.run(arguments, check=True, capture_output=True, text=True)
    return completed.stdout.strip()


def _probe_loopback_status(host: str = "127.0.0.1", port: int = 8081) -> Mapping[str, Any]:
    connection = HTTPConnection(host, port, timeout=2)
    try:
        connection.request("GET", "/status", headers={"Connection": "close"})
        response = connection.getresponse()
        if response.status != 200:
            raise ShadowRuntimeAttestationError("shadow status did not return HTTP 200")
        payload = json.loads(response.read())
    finally:
        connection.close()
    if not isinstance(payload, Mapping):
        raise ShadowRuntimeAttestationError("shadow status payload is not an object")
    return payload


def collect_shadow_runtime_facts(
    *,
    run: CommandRunner = _run_command,
    probe: StatusProbe = _probe_loopback_status,
) -> dict[str, Any]:
    """Observe only Docker metadata and the fixed local status endpoint."""

    shadow_ids = _line_values(run(("docker", "ps", "-q", "--filter", "label=" + SHADOW_LABEL)))
    core_ids = _line_values(run(("docker", "ps", "-q", "--filter", "label=" + CORE_LABEL)))
    facts: dict[str, Any] = {
        "shadow_container_count": len(shadow_ids),
        "core_container_count": len(core_ids),
        "shadow_running": None,
        "memory_limit_bytes": None,
        "memory_swap_limit_bytes": None,
        "port_mapping": None,
        "status_payload_matches": False,
    }
    if len(shadow_ids) != 1:
        return facts

    container = shadow_ids[0]
    facts["shadow_running"] = run(("docker", "inspect", "--format", "{{.State.Running}}", container)).strip() == "true"
    memory_limit, memory_swap_limit = _read_memory_pair(
        run(("docker", "inspect", "--format", "{{.HostConfig.Memory}}/{{.HostConfig.MemorySwap}}", container))
    )
    facts["memory_limit_bytes"] = memory_limit
    facts["memory_swap_limit_bytes"] = memory_swap_limit
    facts["port_mapping"] = run(("docker", "port", container, "8080/tcp")).strip()
    facts["status_payload_matches"] = dict(probe("127.0.0.1", 8081)) == EXPECTED_STATUS_PAYLOAD
    return facts


def evaluate_shadow_runtime_facts(facts: Mapping[str, Any]) -> dict[str, Any]:
    """Evaluate a shadow-only snapshot without exposing runtime identities or secrets."""

    required = {
        "shadow_container_count",
        "core_container_count",
        "shadow_running",
        "memory_limit_bytes",
        "memory_swap_limit_bytes",
        "port_mapping",
        "status_payload_matches",
    }
    if set(facts) != required:
        raise ShadowRuntimeAttestationError("shadow runtime facts have an unexpected shape")

    shadow_count = _nonnegative_int(facts["shadow_container_count"], "shadow_container_count")
    core_count = _nonnegative_int(facts["core_container_count"], "core_container_count")
    shadow_running = facts["shadow_running"]
    if shadow_running is not None and not isinstance(shadow_running, bool):
        raise ShadowRuntimeAttestationError("shadow_running must be boolean or null")
    memory_limit = _optional_nonnegative_int(facts["memory_limit_bytes"], "memory_limit_bytes")
    memory_swap_limit = _optional_nonnegative_int(facts["memory_swap_limit_bytes"], "memory_swap_limit_bytes")
    port_mapping = facts["port_mapping"]
    if port_mapping is not None and not isinstance(port_mapping, str):
        raise ShadowRuntimeAttestationError("port_mapping must be a string or null")
    status_payload_matches = facts["status_payload_matches"]
    if not isinstance(status_payload_matches, bool):
        raise ShadowRuntimeAttestationError("status_payload_matches must be boolean")

    checks = [
        {"id": "EXACTLY_ONE_SHADOW_CONTAINER", "passed": shadow_count == 1},
        {"id": "CORE_RUNTIME_ABSENT", "passed": core_count == 0},
        {"id": "SHADOW_CONTAINER_RUNNING", "passed": shadow_running is True},
        {"id": "SHADOW_MEMORY_LIMIT_512_MIB", "passed": memory_limit == EXPECTED_MEMORY_BYTES},
        {
            "id": "SHADOW_NO_ADDITIONAL_SWAP",
            "passed": memory_limit is not None and memory_limit > 0 and memory_swap_limit == memory_limit,
        },
        {"id": "LOOPBACK_PORT_MAPPING", "passed": port_mapping == EXPECTED_PORT_MAPPING},
        {"id": "SAFE_STATUS_PAYLOAD", "passed": status_payload_matches},
    ]
    failure_codes = [check["id"] for check in checks if not check["passed"]]
    passed = not failure_codes
    return {
        "schema_version": "1.0.0",
        "status": "PASS" if passed else "FAIL",
        "decision": PASS_DECISION if passed else FAIL_DECISION,
        "attestation_valid": passed,
        "checks": checks,
        "failure_codes": failure_codes,
        "observed": {
            "shadow_container_count": shadow_count,
            "core_container_count": core_count,
            "shadow_running": shadow_running,
            "memory_limit_bytes": memory_limit,
            "memory_swap_limit_bytes": memory_swap_limit,
            "port_mapping": "HOST_LOOPBACK_ONLY" if port_mapping == EXPECTED_PORT_MAPPING else "UNVERIFIED",
            "status_payload_exact": status_payload_matches,
            "additional_container_swap_allowed": False
            if memory_limit is not None and memory_limit > 0 and memory_swap_limit == memory_limit
            else None,
        },
        "secret_values_read": False,
        "config_or_secret_file_read": False,
        "external_network_accessed": False,
        "runtime_state_changed": False,
        "real_time_soak_waited": False,
        "continuous_monitoring_created": False,
    }


def _unavailable_result(error: Exception) -> dict[str, Any]:
    return {
        "schema_version": "1.0.0",
        "status": "FAIL",
        "decision": UNAVAILABLE_DECISION,
        "attestation_valid": False,
        "checks": [],
        "failure_codes": ["SHADOW_RUNTIME_ATTESTATION_INPUT_UNAVAILABLE"],
        "error_type": type(error).__name__,
        "secret_values_read": False,
        "config_or_secret_file_read": False,
        "external_network_accessed": False,
        "runtime_state_changed": False,
        "real_time_soak_waited": False,
        "continuous_monitoring_created": False,
    }


def main() -> int:
    try:
        result = evaluate_shadow_runtime_facts(collect_shadow_runtime_facts())
    except (OSError, subprocess.SubprocessError, ShadowRuntimeAttestationError, ValueError) as exc:
        result = _unavailable_result(exc)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
