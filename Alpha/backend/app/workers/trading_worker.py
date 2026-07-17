"""交易 Worker 循环骨架(ALPHA-LIVE-040)。

职责:按节拍执行「行情 -> 策略 -> 组合 -> 风控 -> 网关(SIMULATE/REAL)」周期函数,
每拍写心跳;任何未捕获异常 = 失败关闭方向(记录、心跳标 ERROR、退出循环,
由 systemd 拉起并走重启恢复)。周期函数以依赖注入进来——Worker 不认识券商,
它只认识节拍、心跳和「出错就停」。完整数据线在 070 Paper 运行期接通。
"""

from __future__ import annotations

import time
from typing import Callable, Optional

from backend.app.workers.heartbeat import HeartbeatStore
from backend.app.workers.killswitch import KillSwitch

WORKER_NAME = "trading-worker"


class TradingWorker:
    def __init__(
        self,
        *,
        heartbeats: HeartbeatStore,
        kill_switch: KillSwitch,
        run_cycle: Callable[[], dict],
        interval_seconds: float = 30.0,
        sleep_fn: Callable[[float], None] = time.sleep,
        max_cycles: Optional[int] = None,   # 测试用;生产 None=无限
    ) -> None:
        self._hb = heartbeats
        self._kill = kill_switch
        self._run_cycle = run_cycle
        self._interval = interval_seconds
        self._sleep = sleep_fn
        self._max_cycles = max_cycles
        self.cycles_run = 0
        self.last_error: Optional[str] = None

    def run(self) -> None:
        while self._max_cycles is None or self.cycles_run < self._max_cycles:
            if self._kill.active():
                # 杀开关期间:不执行任何决策周期,只心跳表明进程活着
                self._hb.beat(WORKER_NAME, status="HALTED", detail="杀开关触发,停决策循环")
            else:
                try:
                    summary = self._run_cycle()
                    self._hb.beat(WORKER_NAME, status="RUNNING", detail=str(summary)[:200])
                except Exception as exc:
                    # 失败关闭:记录、标 ERROR、退出(systemd 拉起后走 recover_in_flight)
                    self.last_error = str(exc)
                    self._hb.beat(WORKER_NAME, status="ERROR", detail=self.last_error[:200])
                    raise
            self.cycles_run += 1
            if self._max_cycles is None or self.cycles_run < self._max_cycles:
                self._sleep(self._interval)
