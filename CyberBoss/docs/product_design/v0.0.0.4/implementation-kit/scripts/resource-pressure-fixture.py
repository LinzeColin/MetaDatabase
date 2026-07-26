#!/usr/bin/env python3
"""Bounded, immediate resource-pressure fixture for AC-064."""

from __future__ import annotations

import argparse
import gc
import importlib.util
import json
import os
import resource
import sys
import tempfile
from collections import deque
from pathlib import Path
from typing import Any


MIB = 1024 * 1024
SCRIPT_DIR = Path(__file__).resolve().parent
PROFILE_SPEC = importlib.util.spec_from_file_location(
    "resource_profile", SCRIPT_DIR / "resource_profile.py"
)
assert PROFILE_SPEC and PROFILE_SPEC.loader
RESOURCE_PROFILE = importlib.util.module_from_spec(PROFILE_SPEC)
PROFILE_SPEC.loader.exec_module(RESOURCE_PROFILE)


def rss_kib() -> int:
    value = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return int(value / 1024) if sys.platform == "darwin" else int(value)


def cgroup_snapshot() -> dict[str, Any] | None:
    root = Path("/sys/fs/cgroup")
    required = ("memory.current", "memory.max", "memory.events")
    if not all((root / name).is_file() for name in required):
        return None

    def text(name: str) -> str | None:
        path = root / name
        return path.read_text(encoding="utf-8").strip() if path.is_file() else None

    events: dict[str, int] = {}
    for line in (text("memory.events") or "").splitlines():
        key, _, value = line.partition(" ")
        if value.isdigit():
            events[key] = int(value)
    values: dict[str, Any] = {
        "memory_current": text("memory.current"),
        "memory_peak": text("memory.peak"),
        "memory_max": text("memory.max"),
        "pids_current": text("pids.current"),
        "pids_max": text("pids.max"),
        "memory_events": events,
    }
    return values


def measurements(
    *,
    available: int = 3000,
    disk_used: float = 40,
    inode_used: float = 10,
    queue: int = 0,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "source": "pressure_fixture",
        "captured_at": "fixture",
        "memory": {
            "total_mb": 4096,
            "available_mb": available,
            "swap_total_mb": 1024,
            "swap_free_mb": 1024,
        },
        "load": {"one_minute": 0.5, "cpu_count": 2},
        "storage": {
            "root": {
                "free_mb": 25000,
                "used_percent": disk_used,
                "inode_used_percent": inode_used,
            }
        },
        "queue": {"depth": queue},
    }


def evaluate_ladder() -> list[dict[str, Any]]:
    cases = [
        ("baseline", measurements(), "recover"),
        ("queue_burst", measurements(queue=40), "warn"),
        ("memory_protect", measurements(available=400), "protect"),
        ("disk_protect", measurements(disk_used=92), "protect"),
        ("inode_protect", measurements(inode_used=92), "protect"),
        ("queue_protect", measurements(queue=50), "protect"),
        ("recovered", measurements(), "recover"),
    ]
    results: list[dict[str, Any]] = []
    for name, fixture, expected in cases:
        selected = RESOURCE_PROFILE.select_profile(fixture)
        actual = selected["guard"]["state"]
        if actual != expected:
            raise AssertionError(f"guard_state:{name}:expected={expected}:actual={actual}")
        results.append(
            {
                "step": name,
                "expected": expected,
                "actual": actual,
                "profile": selected["profile"],
                "protect_reasons": selected["guard"]["protect_reasons"],
                "warn_reasons": selected["guard"]["warn_reasons"],
            }
        )
    return results


def atomic_write(path: Path, value: dict[str, Any]) -> None:
    if not path.is_absolute():
        raise ValueError("output_path_must_be_absolute")
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f"{path.name}.tmp-{os.getpid()}")
    temp.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.chmod(temp, 0o640)
    os.replace(temp, path)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--memory-mb", type=int, default=16)
    parser.add_argument("--disk-mb", type=int, default=8)
    parser.add_argument("--queue-items", type=int, default=100)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    if not 1 <= args.memory_mb <= 64:
        parser.error("--memory-mb must be between 1 and 64")
    if not 1 <= args.disk_mb <= 64:
        parser.error("--disk-mb must be between 1 and 64")
    if not 1 <= args.queue_items <= 1000:
        parser.error("--queue-items must be between 1 and 1000")

    before_rss = rss_kib()
    cgroup_before = cgroup_snapshot()
    with tempfile.TemporaryDirectory(prefix="cyberboss-pressure-") as temp:
        allocation = bytearray(args.memory_mb * MIB)
        for offset in range(0, len(allocation), 4096):
            allocation[offset] = 1
        queue = deque(range(args.queue_items))
        disk_path = Path(temp) / "bounded-pressure.bin"
        chunk = b"\0" * MIB
        with disk_path.open("wb") as handle:
            for _ in range(args.disk_mb):
                handle.write(chunk)
            handle.flush()
            os.fsync(handle.fileno())
        during_rss = rss_kib()
        cgroup_during = cgroup_snapshot()
        disk_bytes = disk_path.stat().st_size
        queue_depth = len(queue)
        del allocation
        queue.clear()
        del queue
        gc.collect()
    cgroup_after = cgroup_snapshot()

    ladder = evaluate_ladder()
    finite_memory_max = (
        cgroup_before is not None
        and str(cgroup_before.get("memory_max") or "") not in {"", "max"}
    )
    before_oom_kill = (
        (cgroup_before or {}).get("memory_events", {}).get("oom_kill", 0)
    )
    after_oom_kill = (
        (cgroup_after or {}).get("memory_events", {}).get("oom_kill", 0)
    )
    oom_kill_delta = after_oom_kill - before_oom_kill
    oom_observed = oom_kill_delta > 0
    cgroup_verified = finite_memory_max and not oom_observed
    result = {
        "schema_version": 1,
        "result": "fail" if oom_observed else "pass",
        "mode": "bounded_local_process_fixture",
        "no_sleep": True,
        "oom_observed": oom_observed,
        "hard_caps": {
            "memory_mb_max": 64,
            "disk_mb_max": 64,
            "queue_items_max": 1000,
        },
        "induced_snapshot": {
            "memory_allocated_bytes": args.memory_mb * MIB,
            "disk_written_bytes": disk_bytes,
            "queue_items": queue_depth,
            "rss_before_kib": before_rss,
            "rss_peak_kib": during_rss,
        },
        "guard_ladder": ladder,
        "cgroup_evidence": {
            "state": (
                "verified_bounded_local_container"
                if cgroup_verified
                else "activation_pending"
            ),
            "reason": (
                "finite_cgroup_memory_limit_and_no_oom_kill"
                if cgroup_verified
                else "authorized_ovh_host_required"
            ),
            "before": cgroup_before,
            "during": cgroup_during,
            "after": cgroup_after,
            "oom_kill_delta": oom_kill_delta,
            "claimed_as_live_host_evidence": False,
        },
    }
    if args.output:
        atomic_write(args.output, result)
    print(
        f"RESOURCE_PRESSURE={'FAIL' if oom_observed else 'PASS'} "
        f"memory_mb={args.memory_mb} disk_mb={args.disk_mb} "
        f"queue_items={args.queue_items} ladder_steps={len(ladder)} "
        f"oom={str(oom_observed).lower()} no_sleep=true "
        f"cgroup={result['cgroup_evidence']['state']}"
    )
    return 1 if oom_observed else 0


if __name__ == "__main__":
    raise SystemExit(main())
