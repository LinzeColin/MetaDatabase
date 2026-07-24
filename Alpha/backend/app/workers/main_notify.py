"""通知 Worker 入口(systemd: alpha-notify-worker):发件箱投递循环。"""

from __future__ import annotations

import os
import time

from backend.app.workers.heartbeat import HeartbeatStore
from backend.app.workers.main_common import build_runtime, build_smtp_sender

WORKER_NAME = "notify-worker"
# 投递延迟 p95≈轮询间隔:5.0s 时实测 4.98s,贴着晋级判定的 5s 红线 → 降到 1.5s
INTERVAL_SECONDS = float(os.environ.get("ALPHA_NOTIFY_INTERVAL_SECONDS", "1.5"))


def run_loop(max_cycles: int | None = None) -> None:  # pragma: no cover - 长驻进程
    rt = build_runtime()
    hb: HeartbeatStore = rt["heartbeats"]
    sender = build_smtp_sender()
    cycles = 0
    while max_cycles is None or cycles < max_cycles:
        report = rt["outbox"].process_once(sender)
        hb.beat(WORKER_NAME, status="RUNNING",
                detail=f"delivered={report.delivered} retried={report.retried} failed={report.failed_permanently}")
        cycles += 1
        time.sleep(INTERVAL_SECONDS)


def main() -> None:  # pragma: no cover
    run_loop()


if __name__ == "__main__":  # pragma: no cover
    main()
