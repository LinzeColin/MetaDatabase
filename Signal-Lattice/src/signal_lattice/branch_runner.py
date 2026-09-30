"""分支隔离运行器：每个分支一个独立子进程、独立临时目录、受限资源，只读同一份不可变快照，互相看不到对方输出。

北极星合同：向所有 Active Skill 分发同一快照；每个 Skill 在独立子进程、独立临时目录和受限资源中执行，
不可读取其他 Skill 输出；收集 PASS / ABSTAIN / FAILED 收据。

做法：
- 子进程：`python -m signal_lattice.branch_worker`，cwd = 只属于该分支的私有临时目录（0700，分支结束立即删除），
  环境变量清空到只剩 PATH/PYTHONPATH/TMPDIR；只收到快照路径与快照 hash，不收到任何别的分支的路径；
- 资源：子进程启动第一件事 setrlimit（CPU 秒数、core=0，Linux 上另加地址空间上限）；父进程另有看门狗：墙钟超时 SIGKILL 整个进程组，
  内存（RSS）超限 SIGKILL（macOS 的 RLIMIT_AS 不可靠，所以 RSS 看门狗是所有平台的统一强制手段）；
- 输出：分支把结论写进自己的私有目录，父进程在分支结束后读走字节并删除该目录；所有分支都跑完后父进程才把各分支结论
  写进 out_dir——任何一个分支运行期间，磁盘上不存在别的分支的输出（默认 max_parallel=1；并行时各分支的私有目录同时存在，
  隔离强度只到「不传路径 + 0700 目录」，同一操作系统用户下不是安全边界，文档里如实写明）；
- 收据：{branch_id, status, snapshot_hash, params_version, params_sha256, skill_version, started_at, finished_at, verdicts_file,
  verdicts_sha256, verdict_counts, limits, peak_rss_mb, reason}。status：PASS=分支正常完成并给出结论，
  ABSTAIN=分支正常完成但声明本轮不出结论（写明原因），FAILED=崩溃/超时/超内存/快照对不上/没有产出。
一个分支崩溃、超时、被杀，都只让它自己记 FAILED，不影响其他分支。
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Dict, List, Mapping, Optional, Sequence, Tuple

from .evidence_snapshot import EvidenceSnapshot, SnapshotError, load_snapshot

STATUS_PASS, STATUS_ABSTAIN, STATUS_FAILED = "PASS", "ABSTAIN", "FAILED"
RESULT_NAME = "branch-result.json"
VERDICTS_NAME = "verdicts.json"
POLL_SECONDS = 0.4
STATUS_MEANING = {
    "PASS": "分支正常完成并给出了逐标的结论（逐标的的 PASS/ABSTAIN/FAILED 见 verdict_counts）",
    "ABSTAIN": "分支正常完成，但声明本轮不出结论（原因见 reason）",
    "FAILED": "分支崩溃/超时/超内存/快照对不上/没有产出",
}


@dataclass(frozen=True)
class BranchSpec:
    branch_id: str                          # registry id
    entry: str                              # "包.模块:函数"，由子进程导入
    verify_data: Tuple[str, ...] = ()       # 子进程读之前要核对 hash 的快照数据项（facts_db/events_db/bars/structure）
    memory_mb: int = 1536
    cpu_seconds: int = 3600
    timeout_seconds: int = 5400


@dataclass
class BranchReceipt:
    branch_id: str
    status: str
    reason: Optional[str]
    snapshot_hash: str
    params_version: Optional[str]
    params_sha256: Optional[str]
    skill_version: Optional[str]
    started_at: str
    finished_at: str
    duration_seconds: float
    exit_code: Optional[int]
    verdicts_file: Optional[str] = None
    verdicts_sha256: Optional[str] = None
    verdict_counts: Dict[str, int] = field(default_factory=dict)
    limits: Dict[str, object] = field(default_factory=dict)
    peak_rss_mb: Optional[float] = None
    stderr_tail: Optional[str] = None
    branch_reasons: List[str] = field(default_factory=list)
    status_meaning: str = ""

    def to_dict(self) -> dict:
        return dict(self.__dict__)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _rss_mb(pid: int) -> Optional[float]:
    try:
        out = subprocess.run(["ps", "-o", "rss=", "-p", str(pid)], capture_output=True, text=True, timeout=5).stdout.strip()
        return int(out) / 1024.0 if out else None
    except (OSError, ValueError, subprocess.SubprocessError):
        return None


def _kill_group(process: subprocess.Popen) -> None:
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError, OSError):
        try:
            process.kill()
        except OSError:
            pass


def _tail(path: Path, limit: int = 2000) -> Optional[str]:
    try:
        data = path.read_bytes()
    except OSError:
        return None
    return data[-limit:].decode("utf-8", errors="replace") or None


def worker_environment(tmp: Path, extra: Optional[Mapping[str, str]] = None) -> Dict[str, str]:
    """子进程环境：清空，只留解释器需要的几项；TMPDIR/HOME 都指向私有目录。"""
    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "TMPDIR": str(tmp), "HOME": str(tmp), "LANG": "C.UTF-8",
           "PYTHONDONTWRITEBYTECODE": "1"}
    # PYTHONPATH 里的相对路径在子进程（cwd=私有目录）里会失效：一律转绝对路径，并保证本包所在目录一定在内
    paths = [str(Path(p).resolve()) for p in os.environ.get("PYTHONPATH", "").split(os.pathsep) if p]
    package_parent = str(Path(__file__).resolve().parents[1])
    if package_parent not in paths:
        paths.append(package_parent)
    env["PYTHONPATH"] = os.pathsep.join(paths)
    env.update(extra or {})
    return env


@dataclass
class _Outcome:
    receipt: BranchReceipt
    verdicts_bytes: Optional[bytes]


def _run_one(spec: BranchSpec, snapshot: EvidenceSnapshot, work_root: Path, python: str,
             extra_env: Optional[Mapping[str, str]], log: Callable[[str], None]) -> _Outcome:
    started = time.time()
    started_at = _now()
    tmp = Path(tempfile.mkdtemp(prefix="sl-%s-" % spec.branch_id.replace("/", "_")[:24], dir=str(work_root)))
    os.chmod(tmp, 0o700)
    stdout_path, stderr_path = tmp / "worker.stdout", tmp / "worker.stderr"
    params = snapshot.document["params"]["skills"].get(spec.branch_id) or {}
    limits = {"memory_mb": spec.memory_mb, "cpu_seconds": spec.cpu_seconds, "timeout_seconds": spec.timeout_seconds}
    status, reason, exit_code, peak = STATUS_FAILED, None, None, 0.0
    verdict_bytes: Optional[bytes] = None
    result: dict = {}
    try:
        command = [python, "-m", "signal_lattice.branch_worker", "--branch", spec.branch_id, "--entry", spec.entry,
                   "--snapshot", str(snapshot.path), "--expect-sha", snapshot.sha256, "--cpu-seconds", str(spec.cpu_seconds),
                   "--memory-mb", str(spec.memory_mb), "--verify", ",".join(spec.verify_data)]
        with open(stdout_path, "wb") as out, open(stderr_path, "wb") as err:
            process = subprocess.Popen(command, cwd=str(tmp), env=worker_environment(tmp, extra_env), stdin=subprocess.DEVNULL,
                                       stdout=out, stderr=err, start_new_session=True)
            deadline = started + spec.timeout_seconds
            while True:
                code = process.poll()
                if code is not None:
                    exit_code = code
                    break
                rss = _rss_mb(process.pid)
                if rss is not None:
                    peak = max(peak, rss)
                    if rss > spec.memory_mb:
                        _kill_group(process)
                        process.wait()
                        exit_code, reason = process.returncode, "MEMORY_LIMIT_EXCEEDED:rss=%.0fMB>%dMB" % (rss, spec.memory_mb)
                        break
                if time.time() > deadline:
                    _kill_group(process)
                    process.wait()
                    exit_code, reason = process.returncode, "TIMEOUT:%ds" % spec.timeout_seconds
                    break
                time.sleep(POLL_SECONDS)
            _kill_group(process)            # 收尾：不留孙进程
        limits["peak_rss_mb"] = round(peak, 1)
        result_path = tmp / RESULT_NAME
        if reason is None and exit_code != 0:
            if exit_code is not None and exit_code < 0 and -exit_code == signal.SIGXCPU:
                reason = "CPU_LIMIT_EXCEEDED:%ds" % spec.cpu_seconds
            else:
                reason = "CRASH:exit=%s" % exit_code
        if reason is None:
            try:
                result = json.loads(result_path.read_text("utf-8"))
            except (OSError, ValueError):
                reason = "NO_RESULT_FILE"
        if reason is None:
            if result.get("snapshot_sha256") != snapshot.sha256:
                reason = "SNAPSHOT_MISMATCH:%s" % result.get("snapshot_sha256")
            else:
                try:
                    verdict_bytes = (tmp / VERDICTS_NAME).read_bytes()
                except OSError:
                    reason = "NO_VERDICTS_FILE"
        if reason is None and result.get("branch_status") in (STATUS_PASS, STATUS_ABSTAIN):
            status, reason = result["branch_status"], (result.get("branch_reasons") or [None])[0]
        elif reason is None:
            reason = "BAD_BRANCH_STATUS:%r" % result.get("branch_status")
        counts: Dict[str, int] = {}
        if verdict_bytes is not None and status != STATUS_FAILED:
            try:
                for verdict in json.loads(verdict_bytes.decode("utf-8")).get("verdicts", []):
                    counts[verdict.get("verdict", "?")] = counts.get(verdict.get("verdict", "?"), 0) + 1
            except ValueError:
                status, reason, verdict_bytes = STATUS_FAILED, "VERDICTS_NOT_JSON", None
        if status == STATUS_FAILED:
            verdict_bytes = None
        receipt = BranchReceipt(
            branch_id=spec.branch_id, status=status, reason=reason, snapshot_hash=snapshot.sha256,
            params_version=params.get("params_version"), params_sha256=params.get("params_sha256"),
            skill_version=params.get("registry_version"), started_at=started_at, finished_at=_now(),
            duration_seconds=round(time.time() - started, 2), exit_code=exit_code,
            verdicts_sha256=hashlib.sha256(verdict_bytes).hexdigest() if verdict_bytes is not None else None,
            verdict_counts=counts, limits=limits, peak_rss_mb=round(peak, 1) if peak else None,
            stderr_tail=_tail(stderr_path) if status == STATUS_FAILED else None,
            branch_reasons=list(result.get("branch_reasons") or []), status_meaning=STATUS_MEANING[status])
        log("branch %s -> %s %s (%.1fs, peak %.0f MB)" % (spec.branch_id, status, reason or "", receipt.duration_seconds, peak))
        return _Outcome(receipt, verdict_bytes)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)       # 私有目录随分支结束消失：后面的分支不可能读到它


def run_branches(snapshot_path: Path, specs: Sequence[BranchSpec], out_dir: Path, *, work_root: Optional[Path] = None,
                 python: Optional[str] = None, max_parallel: int = 1, extra_env: Optional[Mapping[str, str]] = None,
                 log: Callable[[str], None] = print) -> List[BranchReceipt]:
    """对同一份快照依次（或有限并行）运行各分支；返回按 specs 顺序的收据，并把各分支结论与收据落到 out_dir。"""
    snapshot = load_snapshot(snapshot_path)          # 快照自身 hash 对不上就直接抛错：链路不完整，一个分支都不启动
    work_root = Path(work_root) if work_root else Path(tempfile.gettempdir())
    work_root.mkdir(parents=True, exist_ok=True)
    python = python or sys.executable
    lock = threading.Lock()

    def guarded(spec: BranchSpec) -> _Outcome:
        try:
            return _run_one(spec, snapshot, work_root, python, extra_env, log)
        except Exception as exc:                      # 运行器自己的意外错误也只让该分支 FAILED
            with lock:
                log("branch %s runner error %s" % (spec.branch_id, exc))
            now = _now()
            params = snapshot.document["params"]["skills"].get(spec.branch_id) or {}
            return _Outcome(BranchReceipt(spec.branch_id, STATUS_FAILED, "RUNNER_ERROR:%s" % type(exc).__name__, snapshot.sha256,
                                          params.get("params_version"), params.get("params_sha256"), params.get("registry_version"),
                                          now, now, 0.0, None, status_meaning=STATUS_MEANING[STATUS_FAILED]), None)

    if max_parallel > 1:
        with ThreadPoolExecutor(max_workers=max_parallel) as pool:
            outcomes = list(pool.map(guarded, specs))
    else:
        outcomes = [guarded(spec) for spec in specs]

    out_dir = Path(out_dir)
    for spec, outcome in zip(specs, outcomes):         # 所有分支跑完之后才落盘
        receipt = outcome.receipt
        if outcome.verdicts_bytes is not None:
            target = out_dir / spec.branch_id / ("verdicts-%s.json" % snapshot.sha256[:12])
            target.parent.mkdir(parents=True, exist_ok=True)
            temporary = target.with_suffix(".tmp")
            temporary.write_bytes(outcome.verdicts_bytes)
            temporary.replace(target)
            receipt.verdicts_file = str(target)
        receipt_path = out_dir / spec.branch_id / ("receipt-%s.json" % snapshot.sha256[:12])
        receipt_path.parent.mkdir(parents=True, exist_ok=True)
        receipt_path.write_text(json.dumps(receipt.to_dict(), ensure_ascii=False, indent=1, sort_keys=True), "utf-8")
    return [o.receipt for o in outcomes]
