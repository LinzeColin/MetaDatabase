"""交易 Worker 入口(systemd: alpha-trading-worker)。

优先装配 070 实盘循环(行情->策略->组合->风控->网关);装配失败(无 SDK/无账户/探针未过)
则以 BLOCKED_ON_OPEND 诚实空转心跳,绝不伪造——**但会持续重试装配,不再永久空转**。

2026-07-28 事故教训:开机时 OpenD 尚未就绪,build_live_cycle 抛「账户不在券商列表」,
worker 落入 idle_cycle 后**再也不会重建**,连喂 15 小时心跳却一次评估都没做,把当天的
交易窗口整个空过。一次 systemctl restart 即恢复——说明它本该自愈却不会自愈。
"""

from __future__ import annotations

import time
from typing import Callable, Optional

from backend.app.workers.main_common import build_runtime
from backend.app.workers.trading_worker import TradingWorker, WORKER_NAME

#: 装配失败后的重试间隔(秒)。60s = 每两拍试一次:足够快到不会错过交易窗口,
#: 又不至于把 OpenD 打爆。
BUILD_RETRY_SECONDS = 60.0


def make_self_healing_cycle(
    build: Callable[[], Callable[[], dict]],
    *,
    retry_seconds: float = BUILD_RETRY_SECONDS,
    clock: Callable[[], float] = time.monotonic,
) -> Callable[[], dict]:
    """把"一次性装配"包成"装不上就按间隔重试"的自愈循环(纯函数,可注入时钟测试)。

    - 装配成功:此后直接跑真实循环,零额外开销;
    - 装配失败:如实回 BLOCKED_ON_OPEND + 原因 + retrying=True,并在 retry_seconds 后再试;
    - 已装配成功后运行期抛错:照旧上抛(交给看门狗/守护处理),不在此吞掉。
    """
    state: dict = {"cycle": None, "reason": "", "next_at": 0.0, "attempts": 0}

    def cycle() -> dict:
        if state["cycle"] is None:
            now = clock()
            if now >= state["next_at"]:
                state["attempts"] += 1
                try:
                    state["cycle"] = build()
                    state["reason"] = ""
                except Exception as exc:      # 失败关闭:如实报因,绝不冒充在交易
                    state["reason"] = f"{type(exc).__name__}: {exc}"[:150]
                    state["next_at"] = now + retry_seconds
            if state["cycle"] is None:
                return {"status": "BLOCKED_ON_OPEND", "note": state["reason"],
                        "retrying": True, "build_attempts": state["attempts"]}
        return state["cycle"]()

    return cycle


def build_worker(*, retry_seconds: float = BUILD_RETRY_SECONDS,
                 clock: Optional[Callable[[], float]] = None) -> TradingWorker:
    rt = build_runtime()

    def _build() -> Callable[[], dict]:
        from backend.app.workers.live_cycle import build_live_cycle
        return build_live_cycle(factory=rt["factory"], kill_switch=rt["kill_switch"])

    cycle = make_self_healing_cycle(
        _build, retry_seconds=retry_seconds,
        **({"clock": clock} if clock else {}))

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
