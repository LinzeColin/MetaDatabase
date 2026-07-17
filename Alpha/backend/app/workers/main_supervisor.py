"""监督进程入口(systemd: alpha-supervisor)。"""

from __future__ import annotations

import time

from backend.app.workers.main_common import build_runtime
from backend.app.workers.supervisor import Supervisor

INTERVAL_SECONDS = 30.0


def build_supervisor() -> Supervisor:
    rt = build_runtime()
    return Supervisor(
        heartbeats=rt["heartbeats"],
        outbox=rt["outbox"],
        kill_switch=rt["kill_switch"],
        expected_workers=("trading-worker", "notify-worker"),
    )


def main() -> None:  # pragma: no cover - 长驻进程入口
    sup = build_supervisor()
    while True:
        sup.check_once()
        time.sleep(INTERVAL_SECONDS)


if __name__ == "__main__":  # pragma: no cover
    main()
