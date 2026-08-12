from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "runtime"
if str(RUNTIME) not in sys.path:
    sys.path.insert(0, str(RUNTIME))

from host_capacity_gate import (
    MAX_SWAP_USED_KIB,
    MIN_MEMORY_KIB,
    MIN_PHYSICAL_DISK_BYTES,
    MIN_VCPU,
    HostCapacityGateError,
    collect_host_facts,
    evaluate_host_facts,
)


def _facts(**overrides: int) -> dict[str, int]:
    values = {
        "vcpu": MIN_VCPU,
        "memory_kib": MIN_MEMORY_KIB,
        "physical_disk_bytes": MIN_PHYSICAL_DISK_BYTES,
        "swap_used_kib": MAX_SWAP_USED_KIB,
    }
    values.update(overrides)
    return values


def test_exact_capacity_and_no_active_swap_boundary_passes() -> None:
    result = evaluate_host_facts(_facts())

    assert result["status"] == "PASS"
    assert result["activation_allowed"] is True
    assert result["failure_codes"] == []
    assert result["secret_values_read"] is False
    assert result["external_network_accessed"] is False


@pytest.mark.parametrize(
    ("field", "value", "failure_code"),
    [
        ("vcpu", MIN_VCPU - 1, "MIN_VCPU"),
        ("memory_kib", MIN_MEMORY_KIB - 1, "MIN_MEMORY_KIB"),
        ("physical_disk_bytes", MIN_PHYSICAL_DISK_BYTES - 1, "MIN_PHYSICAL_DISK_BYTES"),
        ("swap_used_kib", 1, "SWAP_USAGE_ZERO"),
    ],
)
def test_each_resource_or_swap_failure_closes_activation(field: str, value: int, failure_code: str) -> None:
    result = evaluate_host_facts(_facts(**{field: value}))

    assert result["status"] == "FAIL"
    assert result["activation_allowed"] is False
    assert result["failure_codes"] == [failure_code]


def test_collect_host_facts_uses_the_parent_physical_disk_and_unused_configured_swap(tmp_path: Path) -> None:
    proc = tmp_path / "proc"
    proc.mkdir()
    (proc / "meminfo").write_text(
        "MemTotal:        4194304 kB\nSwapTotal:       1048576 kB\nSwapFree:        1048576 kB\n",
        encoding="utf-8",
    )
    calls: list[tuple[str, ...]] = []

    def run(arguments: tuple[str, ...]) -> str:
        calls.append(arguments)
        responses = {
            ("findmnt", "-n", "-o", "SOURCE", "/"): "/dev/sda1\n",
            ("lsblk", "-n", "-o", "PKNAME", "/dev/sda1"): "sda\n",
            ("lsblk", "-b", "-d", "-n", "-o", "SIZE", "/dev/sda"): "%d\n" % MIN_PHYSICAL_DISK_BYTES,
        }
        return responses[arguments]

    assert collect_host_facts(proc_root=proc, cpu_count=MIN_VCPU, run=run) == _facts()
    assert calls[-1] == ("lsblk", "-b", "-d", "-n", "-o", "SIZE", "/dev/sda")


def test_malformed_or_extra_host_facts_are_rejected() -> None:
    with pytest.raises(HostCapacityGateError):
        evaluate_host_facts({**_facts(), "unexpected": 0})
    with pytest.raises(HostCapacityGateError):
        evaluate_host_facts(_facts(memory_kib=-1))


def test_guard_contract_and_installer_do_not_start_a_service() -> None:
    contract = json.loads((RUNTIME / "host_bundle_contract.json").read_text(encoding="utf-8"))
    dropin = (RUNTIME / "systemd/10-host-capacity-gate.conf").read_text(encoding="utf-8")
    installer = (RUNTIME / "install_host_capacity_gate.sh").read_text(encoding="utf-8")

    assert contract["post_freeze_activation_guard"] == {
        "script": "runtime/host_capacity_gate.py",
        "systemd_drop_in": "runtime/systemd/10-host-capacity-gate.conf",
        "installer": "runtime/install_host_capacity_gate.sh",
        "minimum_vcpu": MIN_VCPU,
        "minimum_memory_kib": MIN_MEMORY_KIB,
        "minimum_physical_disk_bytes": MIN_PHYSICAL_DISK_BYTES,
        "maximum_swap_used_kib": MAX_SWAP_USED_KIB,
        "failure_mode": "FAIL_CLOSED_NO_SERVICE_START",
    }
    assert dropin == "[Service]\nExecStartPre=/usr/local/lib/abd/host_capacity_gate.py\n"
    assert "systemctl daemon-reload" in installer
    assert "systemctl start" not in installer
    assert "systemctl enable" not in installer
