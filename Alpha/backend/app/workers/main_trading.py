"""交易 Worker 入口(systemd: alpha-trading-worker)。

部署日前 OpenD 桥接未联调:本入口以 BLOCKED_ON_OPEND 状态空转心跳——
诚实呈现「未接通」,绝不伪造交易循环。OpenD 桥接联调完成后,
run_cycle 替换为真实「行情->策略->组合->风控->网关」周期(070 接线)。
"""

from __future__ import annotations

from backend.app.workers.main_common import build_runtime
from backend.app.workers.trading_worker import TradingWorker, WORKER_NAME


def build_worker() -> TradingWorker:
    rt = build_runtime()

    def idle_cycle() -> dict:
        return {"status": "BLOCKED_ON_OPEND", "note": "OpenD 桥接待部署日联调;不伪造循环"}

    return TradingWorker(
        heartbeats=rt["heartbeats"],
        kill_switch=rt["kill_switch"],
        run_cycle=idle_cycle,
        interval_seconds=30.0,
    )


def main() -> None:  # pragma: no cover - 长驻进程入口
    build_worker().run()


if __name__ == "__main__":  # pragma: no cover
    main()
