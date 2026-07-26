#!/usr/bin/env python3
"""Capture host resource metrics and select a fail-closed CyberBoss profile."""

from __future__ import annotations

import argparse
import json
import math
import os
import shlex
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


MIB = 1024 * 1024
PROFILE_ORDER = ("constrained", "tiny", "standard")
PROFILES: dict[str, dict[str, int]] = {
    "constrained": {
        "memory_high_mb": 768,
        "memory_max_mb": 1152,
        "tasks_max": 256,
        "queue_limit": 20,
        "workspace_target_mb": 4096,
        "log_target_mb": 150,
        "snapshot_target_mb": 512,
    },
    "tiny": {
        "memory_high_mb": 1100,
        "memory_max_mb": 1600,
        "tasks_max": 384,
        "queue_limit": 50,
        "workspace_target_mb": 8192,
        "log_target_mb": 300,
        "snapshot_target_mb": 1024,
    },
    "standard": {
        "memory_high_mb": 1800,
        "memory_max_mb": 2600,
        "tasks_max": 512,
        "queue_limit": 100,
        "workspace_target_mb": 12288,
        "log_target_mb": 500,
        "snapshot_target_mb": 2048,
    },
}
DISK_TARGETS_MB = {
    "release": 1536,
    "cache": 2048,
    "state": 2048,
}
DISK_MINIMUMS_MB = {
    "release": 512,
    "workspace": 2048,
    "cache": 256,
    "state": 512,
    "log": 100,
    "snapshot": 256,
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def read_meminfo(path: Path = Path("/proc/meminfo")) -> dict[str, int]:
    values: dict[str, int] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        key, _, tail = raw.partition(":")
        if not tail:
            continue
        token = tail.strip().split()[0]
        if token.isdigit():
            values[key] = int(token) // 1024
    required = ("MemTotal", "MemAvailable", "SwapTotal", "SwapFree")
    missing = [key for key in required if key not in values]
    if missing:
        raise ValueError(f"meminfo_missing:{','.join(missing)}")
    return {
        "total_mb": values["MemTotal"],
        "available_mb": values["MemAvailable"],
        "swap_total_mb": values["SwapTotal"],
        "swap_free_mb": values["SwapFree"],
    }


def current_cgroup_v2_root(
    mount_root: Path = Path("/sys/fs/cgroup"),
    proc_self_cgroup: Path = Path("/proc/self/cgroup"),
) -> Path:
    if not proc_self_cgroup.is_file():
        return mount_root
    for raw in proc_self_cgroup.read_text(encoding="utf-8").splitlines():
        if not raw.startswith("0::"):
            continue
        relative = Path(raw.removeprefix("0::").lstrip("/"))
        if ".." in relative.parts:
            return mount_root
        candidate = mount_root / relative
        if (candidate / "memory.current").is_file():
            return candidate
    return mount_root


def read_cgroup_v2(
    root: Path | None = None,
    mount_root: Path = Path("/sys/fs/cgroup"),
) -> dict[str, Any]:
    root = root or current_cgroup_v2_root(mount_root)

    def read_bytes(level: Path, name: str) -> int | None:
        path = level / name
        if not path.is_file():
            return None
        raw = path.read_text(encoding="utf-8").strip()
        if raw == "max":
            return None
        if not raw.isdigit():
            raise ValueError(f"cgroup_value_invalid:{name}")
        return int(raw)

    try:
        root.relative_to(mount_root)
    except ValueError:
        levels = [root]
    else:
        levels = []
        level = root
        while True:
            levels.append(level)
            if level == mount_root:
                break
            level = level.parent

    readable_levels = [
        level
        for level in levels
        if (level / "memory.current").is_file()
        and (level / "memory.max").is_file()
    ]
    if not readable_levels:
        return {"version": "unavailable"}

    level_values = [
        {
            name: read_bytes(level, name)
            for name in (
                "memory.current",
                "memory.max",
                "memory.high",
                "memory.swap.current",
                "memory.swap.max",
            )
        }
        for level in readable_levels
    ]
    memory_limits = [
        value["memory.max"]
        for value in level_values
        if value["memory.max"] is not None
    ]
    memory_highs = [
        value["memory.high"]
        for value in level_values
        if value["memory.high"] is not None
    ]
    memory_headrooms = [
        max(0, value["memory.max"] - value["memory.current"])
        for value in level_values
        if value["memory.max"] is not None
        and value["memory.current"] is not None
    ]
    swap_limits = [
        value["memory.swap.max"]
        for value in level_values
        if value["memory.swap.max"] is not None
    ]
    swap_headrooms = [
        max(0, value["memory.swap.max"] - value["memory.swap.current"])
        for value in level_values
        if value["memory.swap.max"] is not None
        and value["memory.swap.current"] is not None
    ]
    current_values = level_values[0]
    return {
        "version": 2,
        "hierarchy_levels_checked": len(readable_levels),
        "memory_current_bytes": current_values["memory.current"],
        "memory_max_bytes": min(memory_limits) if memory_limits else None,
        "memory_high_bytes": min(memory_highs) if memory_highs else None,
        "memory_headroom_bytes": (
            min(memory_headrooms) if memory_headrooms else None
        ),
        "swap_current_bytes": current_values["memory.swap.current"],
        "swap_max_bytes": min(swap_limits) if swap_limits else None,
        "swap_headroom_bytes": min(swap_headrooms) if swap_headrooms else None,
    }


def apply_cgroup_memory_limit(
    host_memory: dict[str, int],
    cgroup: dict[str, Any],
) -> dict[str, Any]:
    effective: dict[str, Any] = {
        **host_memory,
        "host_total_mb": host_memory["total_mb"],
        "host_available_mb": host_memory["available_mb"],
        "host_swap_total_mb": host_memory["swap_total_mb"],
        "host_swap_free_mb": host_memory["swap_free_mb"],
        "scope": "host",
    }
    if cgroup.get("version") != 2:
        return effective

    memory_max = cgroup.get("memory_max_bytes")
    memory_current = cgroup.get("memory_current_bytes")
    memory_headroom = cgroup.get("memory_headroom_bytes")
    if isinstance(memory_max, int) and isinstance(memory_current, int):
        limit_mb = memory_max // MIB
        available_bytes = (
            memory_headroom
            if isinstance(memory_headroom, int)
            else max(0, memory_max - memory_current)
        )
        available_mb = available_bytes // MIB
        effective["total_mb"] = min(host_memory["total_mb"], limit_mb)
        effective["available_mb"] = min(
            host_memory["available_mb"],
            available_mb,
        )
        effective["cgroup_memory_max_mb"] = limit_mb
        effective["cgroup_memory_current_mb"] = math.ceil(memory_current / MIB)
        effective["scope"] = "effective_cgroup"

    swap_max = cgroup.get("swap_max_bytes")
    swap_current = cgroup.get("swap_current_bytes")
    swap_headroom = cgroup.get("swap_headroom_bytes")
    if isinstance(swap_max, int) and isinstance(swap_current, int):
        swap_limit_mb = swap_max // MIB
        swap_available_bytes = (
            swap_headroom
            if isinstance(swap_headroom, int)
            else max(0, swap_max - swap_current)
        )
        swap_free_mb = swap_available_bytes // MIB
        effective["swap_total_mb"] = min(
            host_memory["swap_total_mb"],
            swap_limit_mb,
        )
        effective["swap_free_mb"] = min(
            host_memory["swap_free_mb"],
            swap_free_mb,
        )
        effective["cgroup_swap_max_mb"] = swap_limit_mb
        effective["cgroup_swap_current_mb"] = math.ceil(swap_current / MIB)
    return effective


def capture_live_measurements() -> dict[str, Any]:
    if not Path("/proc/meminfo").is_file():
        raise RuntimeError("live_measurement_requires_linux_procfs")
    cgroup = read_cgroup_v2()
    memory = apply_cgroup_memory_limit(read_meminfo(), cgroup)
    disk = shutil.disk_usage("/")
    stat = os.statvfs("/")
    inode_total = stat.f_files
    inode_used = inode_total - stat.f_ffree if inode_total else 0
    return {
        "schema_version": 1,
        "source": "live",
        "captured_at": utc_now(),
        "memory": memory,
        "cgroup": cgroup,
        "load": {
            "one_minute": round(os.getloadavg()[0], 3),
            "cpu_count": os.cpu_count() or 1,
        },
        "storage": {
            "root": {
                "free_mb": disk.free // MIB,
                "used_percent": round((disk.used / disk.total) * 100, 1)
                if disk.total
                else 0,
                "inode_used_percent": round((inode_used / inode_total) * 100, 1)
                if inode_total
                else 0,
            }
        },
        "queue": {
            "depth": int(os.environ.get("CB_PREFLIGHT_QUEUE_DEPTH", "0")),
        },
    }


def numeric(value: Any, name: str, *, integer: bool = False) -> float | int:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"measurement_not_numeric:{name}")
    if not math.isfinite(float(value)) or value < 0:
        raise ValueError(f"measurement_out_of_range:{name}")
    return int(value) if integer else float(value)


def normalize_measurements(raw: dict[str, Any]) -> dict[str, Any]:
    memory = raw.get("memory") or {}
    load = raw.get("load") or {}
    root = (raw.get("storage") or {}).get("root") or {}
    queue = raw.get("queue") or {}
    normalized = {
        "schema_version": 1,
        "source": str(raw.get("source") or "fixture"),
        "captured_at": str(raw.get("captured_at") or "fixture"),
        "memory": {
            "total_mb": numeric(memory.get("total_mb"), "memory.total_mb", integer=True),
            "available_mb": numeric(
                memory.get("available_mb"), "memory.available_mb", integer=True
            ),
            "swap_total_mb": numeric(
                memory.get("swap_total_mb"), "memory.swap_total_mb", integer=True
            ),
            "swap_free_mb": numeric(
                memory.get("swap_free_mb"), "memory.swap_free_mb", integer=True
            ),
            "scope": (
                memory.get("scope")
                if memory.get("scope") in {"host", "effective_cgroup", "provided"}
                else "provided"
            ),
        },
        "load": {
            "one_minute": numeric(load.get("one_minute"), "load.one_minute"),
            "cpu_count": numeric(load.get("cpu_count"), "load.cpu_count", integer=True),
        },
        "storage": {
            "root": {
                "free_mb": numeric(root.get("free_mb"), "storage.root.free_mb", integer=True),
                "used_percent": numeric(
                    root.get("used_percent"), "storage.root.used_percent"
                ),
                "inode_used_percent": numeric(
                    root.get("inode_used_percent"),
                    "storage.root.inode_used_percent",
                ),
            }
        },
        "queue": {
            "depth": numeric(queue.get("depth", 0), "queue.depth", integer=True),
        },
    }
    mem = normalized["memory"]
    if mem["available_mb"] > mem["total_mb"]:
        raise ValueError("measurement_available_exceeds_total")
    if mem["swap_free_mb"] > mem["swap_total_mb"]:
        raise ValueError("measurement_swap_free_exceeds_total")
    if normalized["load"]["cpu_count"] < 1:
        raise ValueError("measurement_cpu_count_below_one")
    for name in ("used_percent", "inode_used_percent"):
        if normalized["storage"]["root"][name] > 100:
            raise ValueError(f"measurement_percent_above_100:{name}")
    return normalized


def downgrade(profile: str) -> str:
    index = PROFILE_ORDER.index(profile)
    return PROFILE_ORDER[max(0, index - 1)]


def calculate_disk_caps(profile: str, free_mb: int) -> dict[str, Any]:
    policy = PROFILES[profile]
    targets = {
        "release": DISK_TARGETS_MB["release"],
        "workspace": policy["workspace_target_mb"],
        "cache": DISK_TARGETS_MB["cache"],
        "state": DISK_TARGETS_MB["state"],
        "log": policy["log_target_mb"],
        "snapshot": policy["snapshot_target_mb"],
    }
    reserve_mb = max(4096, math.ceil(free_mb * 0.15))
    allocatable_mb = max(0, free_mb - reserve_mb)
    target_total_mb = sum(targets.values())
    minimum_total_mb = sum(DISK_MINIMUMS_MB.values())
    if allocatable_mb >= minimum_total_mb:
        additional_targets = {
            name: targets[name] - DISK_MINIMUMS_MB[name] for name in targets
        }
        additional_total = sum(additional_targets.values())
        remaining_mb = allocatable_mb - minimum_total_mb
        additional_scale = (
            min(1.0, remaining_mb / additional_total) if additional_total else 0
        )
        caps_mb = {
            name: DISK_MINIMUMS_MB[name]
            + math.floor(additional_targets[name] * additional_scale)
            for name in targets
        }
    else:
        minimum_scale = allocatable_mb / minimum_total_mb if minimum_total_mb else 0
        caps_mb = {
            name: math.floor(value * minimum_scale)
            for name, value in DISK_MINIMUMS_MB.items()
        }
    scale = min(1.0, allocatable_mb / target_total_mb) if target_total_mb else 0
    minimums_met = all(
        caps_mb[name] >= minimum for name, minimum in DISK_MINIMUMS_MB.items()
    )
    return {
        "host_reserve_mb": reserve_mb,
        "allocatable_mb": allocatable_mb,
        "target_total_mb": target_total_mb,
        "scale": round(scale, 4),
        "caps_mb": caps_mb,
        "minimums_met": minimums_met,
    }


def guard_state(measurements: dict[str, Any], queue_limit: int) -> dict[str, Any]:
    memory = measurements["memory"]
    root = measurements["storage"]["root"]
    load = measurements["load"]
    queue_depth = measurements["queue"]["depth"]
    memory_used = (
        ((memory["total_mb"] - memory["available_mb"]) / memory["total_mb"]) * 100
        if memory["total_mb"]
        else 100
    )
    load_limit = max(3.5, load["cpu_count"] * 1.5)
    queue_warn_depth = math.floor(queue_limit * 0.8)
    protect: list[str] = []
    warn: list[str] = []

    if memory["available_mb"] < 512 or memory_used >= 92:
        protect.append("memory")
    elif memory["available_mb"] < 768 or memory_used >= 85:
        warn.append("memory")
    if root["used_percent"] >= 90:
        protect.append("disk")
    elif root["used_percent"] >= 80:
        warn.append("disk")
    if root["inode_used_percent"] >= 90:
        protect.append("inode")
    elif root["inode_used_percent"] >= 80:
        warn.append("inode")
    if load["one_minute"] > load_limit:
        protect.append("load")
    elif load["one_minute"] > load_limit * 0.75:
        warn.append("load")
    if queue_depth >= queue_limit:
        protect.append("queue")
    elif queue_depth >= queue_warn_depth:
        warn.append("queue")

    state = "protect" if protect else ("warn" if warn else "recover")
    return {
        "state": state,
        "protect_reasons": protect,
        "warn_reasons": warn,
        "memory_used_percent": round(memory_used, 1),
        "max_load_1m": round(load_limit, 2),
        "protect_min_free_memory_mb": 512,
        "recover_min_free_memory_mb": 768,
        "protect_disk_used_percent": 90,
        "recover_disk_used_percent": 80,
        "protect_inode_used_percent": 90,
        "recover_inode_used_percent": 80,
        "protect_queue_depth": queue_limit,
        "recover_queue_depth": max(0, queue_warn_depth - 1),
    }


def select_profile(raw: dict[str, Any]) -> dict[str, Any]:
    measurements = normalize_measurements(raw)
    memory = measurements["memory"]
    root = measurements["storage"]["root"]
    load = measurements["load"]
    swap_used_percent = (
        ((memory["swap_total_mb"] - memory["swap_free_mb"]) / memory["swap_total_mb"])
        * 100
        if memory["swap_total_mb"]
        else 0
    )

    if (
        memory["total_mb"] < 2048
        or memory["available_mb"] < 768
        or root["free_mb"] < 4096
    ):
        profile = "constrained"
    elif (
        memory["total_mb"] < 6144
        or memory["available_mb"] < 2048
        or root["free_mb"] < 16384
    ):
        profile = "tiny"
    else:
        profile = "standard"

    pressure_downgrade = (
        swap_used_percent >= 25
        or root["used_percent"] >= 85
        or root["inode_used_percent"] >= 85
        or load["one_minute"] > max(3.5, load["cpu_count"] * 1.5)
    )
    if pressure_downgrade:
        profile = downgrade(profile)

    memory_reserve_mb = max(512, math.ceil(memory["total_mb"] * 0.10))
    safe_runtime_budget_mb = max(0, memory["available_mb"] - memory_reserve_mb)
    while (
        profile != "constrained"
        and PROFILES[profile]["memory_max_mb"] > safe_runtime_budget_mb
    ):
        profile = downgrade(profile)

    policy = PROFILES[profile]
    disk = calculate_disk_caps(profile, root["free_mb"])
    guard = guard_state(measurements, policy["queue_limit"])
    block_reasons: list[str] = []
    if policy["memory_max_mb"] > safe_runtime_budget_mb:
        block_reasons.append("insufficient_memory_safety_reserve")
    if not disk["minimums_met"]:
        block_reasons.append("insufficient_disk_for_minimum_active_set")
    if guard["state"] == "protect":
        block_reasons.extend(f"protect_{item}" for item in guard["protect_reasons"])

    return {
        "schema_version": 1,
        "measurements": measurements,
        "profile": profile,
        "profile_policy": policy,
        "memory": {
            "effective_safety_reserve_mb": memory_reserve_mb,
            "safe_runtime_budget_mb": safe_runtime_budget_mb,
            "swap_used_percent": round(swap_used_percent, 1),
        },
        "disk": disk,
        "guard": guard,
        "activation_safe": not block_reasons,
        "block_reasons": sorted(set(block_reasons)),
        "predicates": {
            "protect": (
                "available_memory_mb<512 OR memory_used_percent>=92 OR "
                "disk_used_percent>=90 OR inode_used_percent>=90 OR "
                f"load_1m>{guard['max_load_1m']} OR "
                f"queue_depth>={policy['queue_limit']}"
            ),
            "recover": (
                "available_memory_mb>=768 AND memory_used_percent<85 AND "
                "disk_used_percent<80 AND inode_used_percent<80 AND "
                f"load_1m<={round(guard['max_load_1m'] * 0.75, 2)} AND "
                f"queue_depth<={guard['recover_queue_depth']}"
            ),
        },
    }


def render_env(result: dict[str, Any]) -> str:
    measurements = result["measurements"]
    memory = measurements["memory"]
    load = measurements["load"]
    root = measurements["storage"]["root"]
    policy = result["profile_policy"]
    disk = result["disk"]
    caps = disk["caps_mb"]
    guard = result["guard"]
    values = {
        "CB_RESOURCE_PROFILE": result["profile"],
        "CB_MEASUREMENT_MEMORY_SCOPE": memory["scope"],
        "CB_MEASURED_TOTAL_MEMORY_MB": memory["total_mb"],
        "CB_MEASURED_AVAILABLE_MEMORY_MB": memory["available_mb"],
        "CB_MEASURED_SWAP_TOTAL_MB": memory["swap_total_mb"],
        "CB_MEASURED_SWAP_FREE_MB": memory["swap_free_mb"],
        "CB_MEASURED_FREE_DISK_MB": root["free_mb"],
        "CB_MEASURED_DISK_USED_PERCENT": root["used_percent"],
        "CB_MEASURED_INODE_USED_PERCENT": root["inode_used_percent"],
        "CB_MEASURED_LOAD_1M": load["one_minute"],
        "CB_MEASURED_CPU_COUNT": load["cpu_count"],
        "CB_SYSTEMD_MEMORY_HIGH": f"{policy['memory_high_mb']}M",
        "CB_SYSTEMD_MEMORY_MAX": f"{policy['memory_max_mb']}M",
        "CB_SYSTEMD_TASKS_MAX": policy["tasks_max"],
        "CB_QUEUE_LIMIT": policy["queue_limit"],
        "CB_EFFECTIVE_MEMORY_SAFETY_RESERVE_MB": result["memory"][
            "effective_safety_reserve_mb"
        ],
        "CB_SAFE_RUNTIME_BUDGET_MB": result["memory"]["safe_runtime_budget_mb"],
        "CB_HOST_FREE_DISK_RESERVE_BYTES": disk["host_reserve_mb"] * MIB,
        "CB_MAX_RELEASE_BYTES": caps["release"] * MIB,
        "CB_MAX_WORKSPACE_BYTES": caps["workspace"] * MIB,
        "CB_MAX_CACHE_BYTES": caps["cache"] * MIB,
        "CB_MAX_STATE_BYTES": caps["state"] * MIB,
        "CB_MAX_LOG_BYTES": caps["log"] * MIB,
        "CB_MAX_LOCAL_SNAPSHOT_BYTES": caps["snapshot"] * MIB,
        "CB_RESOURCE_GUARD_STATE": guard["state"],
        "CB_RESOURCE_ACTIVATION_SAFE": str(result["activation_safe"]).lower(),
        "CB_RESOURCE_BLOCK_REASONS": ",".join(result["block_reasons"]) or "none",
        "CB_RESOURCE_PROTECT_PREDICATE": result["predicates"]["protect"],
        "CB_RESOURCE_RECOVER_PREDICATE": result["predicates"]["recover"],
    }
    return "\n".join(
        ["# Generated from one measured snapshot; safe to regenerate."]
        + [f"{key}={shlex.quote(str(value))}" for key, value in values.items()]
    )


def atomic_write(path: Path, content: str, mode: int) -> None:
    if not path.is_absolute():
        raise ValueError(f"output_path_must_be_absolute:{path}")
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o750)
    temp = path.with_name(f"{path.name}.tmp-{os.getpid()}")
    temp.write_text(content, encoding="utf-8")
    os.chmod(temp, mode)
    os.replace(temp, path)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--measurements", type=Path)
    parser.add_argument("--capture-only", action="store_true")
    parser.add_argument("--format", choices=("env", "json"), default="env")
    parser.add_argument("--write", type=Path)
    parser.add_argument("--systemd-dropin", type=Path)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    if args.capture_only:
        if any((args.measurements, args.write, args.systemd_dropin, args.check)):
            parser.error("--capture-only cannot be combined with other actions")
        print(json.dumps(capture_live_measurements(), separators=(",", ":")))
        return 0
    if args.check and any((args.write, args.systemd_dropin)):
        parser.error("--check is read-only and cannot write outputs")

    raw = (
        json.loads(args.measurements.read_text(encoding="utf-8"))
        if args.measurements
        else capture_live_measurements()
    )
    result = select_profile(raw)
    rendered = (
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True)
        if args.format == "json"
        else render_env(result)
    )
    print(rendered)
    print(
        f"PROFILE=PASS selected={result['profile']} "
        f"guard={result['guard']['state']} "
        f"activation_safe={str(result['activation_safe']).lower()}"
    )
    if args.check:
        print("PROFILE_CHECK=PASS")

    if (args.write or args.systemd_dropin) and not result["activation_safe"]:
        print(
            "PROFILE_WRITE=HAZARD_BLOCKED reasons="
            + ",".join(result["block_reasons"]),
            file=sys.stderr,
        )
        return 3
    if args.write:
        atomic_write(args.write, render_env(result) + "\n", 0o640)
    if args.systemd_dropin:
        policy = result["profile_policy"]
        dropin = (
            "[Service]\n"
            f"MemoryHigh={policy['memory_high_mb']}M\n"
            f"MemoryMax={policy['memory_max_mb']}M\n"
            f"TasksMax={policy['tasks_max']}\n"
        )
        atomic_write(args.systemd_dropin, dropin, 0o644)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
