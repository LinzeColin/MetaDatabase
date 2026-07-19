"""交易 Worker 入口(systemd: alpha-trading-worker)。

优先装配 070 实盘循环(行情->策略->组合->风控->网关 PAPER);装配失败
(无 SDK/无账户/探针未过)则以 BLOCKED_ON_OPEND 诚实空转心跳,绝不伪造。
"""

from __future__ import annotations

from backend.app.workers.main_common import build_runtime
from backend.app.workers.trading_worker import TradingWorker, WORKER_NAME


def build_worker() -> TradingWorker:
    rt = build_runtime()

    try:
        from backend.app.workers.live_cycle import build_live_cycle
        cycle = build_live_cycle(factory=rt["factory"], kill_switch=rt["kill_switch"])
    except Exception as exc:  # 失败关闭:如实报原因空转,不冒充在交易
        reason = f"{type(exc).__name__}: {exc}"[:150]

        def idle_cycle() -> dict:
            return {"status": "BLOCKED_ON_OPEND", "note": reason}

        cycle = idle_cycle

    return TradingWorker(
        heartbeats=rt["heartbeats"],
        kill_switch=rt["kill_switch"],
        run_cycle=cycle,
        interval_seconds=30.0,
    )


def main() -> None:  # pragma: no cover - 长驻进程入口
    build_worker().run()


if __name__ == "__main__":  # pragma: no cover
    main()
