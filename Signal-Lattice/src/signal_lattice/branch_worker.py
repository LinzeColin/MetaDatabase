"""分支子进程入口：由 branch_runner 启动，在自己的私有临时目录（cwd）里运行一个分支。

只做四件事：先给自己加资源上限；按路径读快照并核对内容 hash（对不上立刻退出 5）；导入并运行分支入口；
把结论写进自己的 cwd（verdicts.json + branch-result.json）。不读别的分支、不联网取数、不写 cwd 以外的地方。
"""

from __future__ import annotations

import argparse
import importlib
import json
import os
import resource
import sys
import time
import traceback
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Sequence

from .evidence_snapshot import SnapshotError, load_snapshot

EXIT_SNAPSHOT_MISMATCH = 5
EXIT_ENTRY_ERROR = 6


def apply_limits(cpu_seconds: int, memory_mb: int) -> Dict[str, Any]:
    """CPU 秒数与 core=0 在 Linux/macOS 都生效；地址空间上限只在 Linux 设（macOS 的虚拟地址空间动辄几百 GB，设了会误杀），
    macOS 上内存上限由父进程的 RSS 看门狗强制。"""
    applied: Dict[str, Any] = {}
    resource.setrlimit(resource.RLIMIT_CPU, (cpu_seconds, cpu_seconds + 5))
    applied["cpu_seconds"] = resource.getrlimit(resource.RLIMIT_CPU)[0]
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    applied["core"] = 0
    if sys.platform.startswith("linux"):
        limit = int(memory_mb * 1024 * 1024 * 1.3)          # 留 30% 给解释器与映射，RSS 看门狗按 memory_mb 卡
        resource.setrlimit(resource.RLIMIT_AS, (limit, limit))
        applied["address_space_bytes"] = resource.getrlimit(resource.RLIMIT_AS)[0]
    else:
        applied["address_space_bytes"] = None
    return applied


def resolve(entry: str) -> Callable:
    module_name, _, function = entry.partition(":")
    return getattr(importlib.import_module(module_name), function)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="signal_lattice.branch_worker")
    parser.add_argument("--branch", required=True)
    parser.add_argument("--entry", required=True)
    parser.add_argument("--snapshot", required=True, type=Path)
    parser.add_argument("--expect-sha", required=True)
    parser.add_argument("--cpu-seconds", type=int, required=True)
    parser.add_argument("--memory-mb", type=int, required=True)
    parser.add_argument("--verify", default="")
    args = parser.parse_args(argv)
    applied = apply_limits(args.cpu_seconds, args.memory_mb)
    started = time.time()

    def log(message: str) -> None:
        print("%s [%s] %s" % (time.strftime("%H:%M:%S"), args.branch, message), file=sys.stderr, flush=True)

    try:
        snapshot = load_snapshot(args.snapshot, [k for k in args.verify.split(",") if k])
    except SnapshotError as exc:
        log("snapshot rejected: %s" % exc)
        return EXIT_SNAPSHOT_MISMATCH
    if snapshot.sha256 != args.expect_sha:
        log("snapshot hash %s != expected %s" % (snapshot.sha256, args.expect_sha))
        return EXIT_SNAPSHOT_MISMATCH
    try:
        output = resolve(args.entry)(snapshot, log)
    except Exception:                                                # 分支自己的异常：写进 stderr，退出码非 0，由父进程记 FAILED
        traceback.print_exc()
        return EXIT_ENTRY_ERROR
    params = dict(snapshot.document["params"]["skills"].get(args.branch) or {})
    verdict_doc = {"branch_id": args.branch, "snapshot_sha256": snapshot.sha256, "as_of": snapshot.as_of,
                   "branch_status": output["branch_status"], "branch_reasons": list(output.get("branch_reasons") or []),
                   "params": {k: params.get(k) for k in ("params_version", "params_sha256", "registry_version")},
                   "verdicts": output["verdicts"], "meta": output.get("meta", {})}
    Path("verdicts.json").write_text(json.dumps(verdict_doc, ensure_ascii=False, separators=(",", ":"), default=str), "utf-8")
    Path("branch-result.json").write_text(json.dumps({
        "branch_id": args.branch, "snapshot_sha256": snapshot.sha256, "branch_status": output["branch_status"],
        "branch_reasons": verdict_doc["branch_reasons"], "limits_applied": applied, "seconds": round(time.time() - started, 2),
        "cwd": os.getcwd(), "verdicts": len(output["verdicts"])}), "utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
