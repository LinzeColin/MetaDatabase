#!/usr/bin/env python3
"""Fail-closed physical host gate for an ABD systemd start."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence


MIN_VCPU = 2
MIN_MEMORY_KIB = 4096 * 1024
MIN_PHYSICAL_DISK_BYTES = 40 * 1024 * 1024 * 1024
EXPECTED_SWAP_ENTRIES = 0
PASS_DECISION = "HOST_CAPACITY_AND_SWAP_GATE_PASS"
FAIL_DECISION = "HOST_CAPACITY_OR_SWAP_GATE_FAIL_CLOSED"
UNAVAILABLE_DECISION = "HOST_CAPACITY_GATE_INPUT_UNAVAILABLE_FAIL_CLOSED"


class HostCapacityGateError(ValueError):
    """Raised when direct host facts cannot be parsed safely."""


CommandRunner = Callable[[Sequence[str]], str]


def _nonnegative_int(value: Any, field: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise HostCapacityGateError("%s must be a non-negative integer" % field)
    return value


def _read_memtotal_kib(text: str) -> int:
    for line in text.splitlines():
        fields = line.split()
        if len(fields) == 3 and fields[0] == "MemTotal:" and fields[2] == "kB":
            return _nonnegative_int(int(fields[1]), "memory_kib")
    raise HostCapacityGateError("MemTotal is unavailable")


def _read_swap_entries(text: str) -> int:
    rows = [line for line in text.splitlines() if line.strip()]
    if not rows or rows[0].split()[0] != "Filename":
        raise HostCapacityGateError("/proc/swaps header is unavailable")
    return len(rows) - 1


def _run_command(arguments: Sequence[str]) -> str:
    completed = subprocess.run(arguments, check=True, capture_output=True, text=True)
    return completed.stdout.strip()


def _read_physical_root_disk_bytes(run: CommandRunner) -> int:
    root_source = run(("findmnt", "-n", "-o", "SOURCE", "/")).strip()
    if not root_source.startswith("/dev/"):
        raise HostCapacityGateError("root filesystem does not expose a block-device source")
    parent_name = run(("lsblk", "-n", "-o", "PKNAME", root_source)).strip()
    block_device = "/dev/%s" % parent_name if parent_name else root_source
    output = run(("lsblk", "-b", "-d", "-n", "-o", "SIZE", block_device)).strip()
    values = [line.strip() for line in output.splitlines() if line.strip()]
    if len(values) != 1:
        raise HostCapacityGateError("physical root disk size is ambiguous")
    try:
        return _nonnegative_int(int(values[0]), "physical_disk_bytes")
    except ValueError as exc:
        raise HostCapacityGateError("physical root disk size is invalid") from exc


def collect_host_facts(
    *,
    proc_root: Path = Path("/proc"),
    cpu_count: int | None = None,
    run: CommandRunner = _run_command,
) -> dict[str, int]:
    observed_cpu_count = os.cpu_count() if cpu_count is None else cpu_count
    return {
        "vcpu": _nonnegative_int(observed_cpu_count, "vcpu"),
        "memory_kib": _read_memtotal_kib((proc_root / "meminfo").read_text(encoding="utf-8")),
        "physical_disk_bytes": _read_physical_root_disk_bytes(run),
        "swap_entries": _read_swap_entries((proc_root / "swaps").read_text(encoding="utf-8")),
    }


def evaluate_host_facts(facts: Mapping[str, Any]) -> dict[str, Any]:
    required = ("vcpu", "memory_kib", "physical_disk_bytes", "swap_entries")
    if set(facts) != set(required):
        raise HostCapacityGateError("host facts must contain exactly the required direct observations")
    actual = {field: _nonnegative_int(facts[field], field) for field in required}
    checks = [
        {"id": "MIN_VCPU", "passed": actual["vcpu"] >= MIN_VCPU, "actual": actual["vcpu"], "minimum": MIN_VCPU},
        {
            "id": "MIN_MEMORY_KIB",
            "passed": actual["memory_kib"] >= MIN_MEMORY_KIB,
            "actual": actual["memory_kib"],
            "minimum": MIN_MEMORY_KIB,
        },
        {
            "id": "MIN_PHYSICAL_DISK_BYTES",
            "passed": actual["physical_disk_bytes"] >= MIN_PHYSICAL_DISK_BYTES,
            "actual": actual["physical_disk_bytes"],
            "minimum": MIN_PHYSICAL_DISK_BYTES,
        },
        {
            "id": "SWAP_ENTRIES_ZERO",
            "passed": actual["swap_entries"] == EXPECTED_SWAP_ENTRIES,
            "actual": actual["swap_entries"],
            "expected": EXPECTED_SWAP_ENTRIES,
        },
    ]
    failures = [row["id"] for row in checks if not row["passed"]]
    passed = not failures
    return {
        "schema_version": "1.0.0",
        "status": "PASS" if passed else "FAIL",
        "decision": PASS_DECISION if passed else FAIL_DECISION,
        "activation_allowed": passed,
        "facts": actual,
        "checks": checks,
        "failure_codes": failures,
        "secret_values_read": False,
        "external_network_accessed": False,
    }


def _unavailable_result(error: Exception) -> dict[str, Any]:
    return {
        "schema_version": "1.0.0",
        "status": "FAIL",
        "decision": UNAVAILABLE_DECISION,
        "activation_allowed": False,
        "facts": {},
        "checks": [],
        "failure_codes": ["HOST_FACTS_UNAVAILABLE"],
        "error_type": type(error).__name__,
        "secret_values_read": False,
        "external_network_accessed": False,
    }


def main() -> int:
    try:
        result = evaluate_host_facts(collect_host_facts())
    except (OSError, subprocess.SubprocessError, HostCapacityGateError, ValueError) as exc:
        result = _unavailable_result(exc)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
