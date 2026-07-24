"""监督进程入口(systemd: alpha-supervisor)。"""

from __future__ import annotations

import os
import subprocess
import time

from backend.app.workers.main_common import build_runtime
from backend.app.workers.supervisor import Supervisor

INTERVAL_SECONDS = 30.0


def _restart_unit(unit: str) -> bool:
    """受限重启:仅 sudoers 白名单里的两个单元;sudo -n 无授权即失败返回 False。"""
    try:
        r = subprocess.run(["sudo", "-n", "systemctl", "restart", unit],
                           capture_output=True, timeout=120)
        return r.returncode == 0
    except Exception:
        return False


def build_supervisor() -> Supervisor:
    rt = build_runtime()
    self_heal = os.environ.get("ALPHA_SUPERVISOR_SELF_HEAL", "1") == "1"
    return Supervisor(
        heartbeats=rt["heartbeats"],
        outbox=rt["outbox"],
        kill_switch=rt["kill_switch"],
        expected_workers=("trading-worker", "notify-worker"),
        restart_fn=_restart_unit if self_heal else None,
        auto_clear_after_checks=6 if self_heal else None,   # 连续 6 拍(约 3 分钟)健康才收闸
    )


def main() -> None:  # pragma: no cover - 长驻进程入口
    sup = build_supervisor()
    while True:
        report = sup.check_once()
        # 守护自身也要留痕:否则看门狗死了、页面照样"全绿",无人知晓(2026-07-24 owner 抓到)
        try:
            sup._hb.beat(
                "supervisor", status="RUNNING",
                detail=f"healthy={len(report.healthy)} stale={len(report.stale)} "
                       f"missing={len(report.missing)}")
        except Exception:
            pass
        time.sleep(INTERVAL_SECONDS)


if __name__ == "__main__":  # pragma: no cover
    main()
