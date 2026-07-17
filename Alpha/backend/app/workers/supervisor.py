"""监督进程(ALPHA-LIVE-040):心跳判活 + 失败关闭处置 + 告警。

掉线语义(DEPLOY_RUNBOOK 第 5 节恒真):任何组件失联 -> 告警邮件 ->
失败关闭(拍杀开关停新单)-> 自愈(systemd Restart=always 拉起进程,
恢复后对账清才可重新拿到下单资格)。Supervisor 自己不重启进程,
它负责「发现、停车、喊人」;拉起交给 systemd。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

from backend.app.notify.outbox import Outbox
from backend.app.workers.heartbeat import HeartbeatStore
from backend.app.workers.killswitch import KillSwitch

DEFAULT_STALE_SECONDS = 90.0


@dataclass(frozen=True)
class SupervisionReport:
    healthy: tuple[str, ...] = field(default_factory=tuple)
    stale: tuple[str, ...] = field(default_factory=tuple)
    missing: tuple[str, ...] = field(default_factory=tuple)
    kill_switch_engaged: bool = False


class Supervisor:
    def __init__(
        self,
        *,
        heartbeats: HeartbeatStore,
        outbox: Outbox,
        kill_switch: KillSwitch,
        expected_workers: Sequence[str] = ("trading-worker", "notify-worker"),
        stale_after_seconds: float = DEFAULT_STALE_SECONDS,
        engage_kill_switch_on_loss: bool = True,
    ) -> None:
        self._hb = heartbeats
        self._outbox = outbox
        self._kill = kill_switch
        self._expected = tuple(expected_workers)
        self._stale_after = stale_after_seconds
        self._engage_on_loss = engage_kill_switch_on_loss

    def check_once(self) -> SupervisionReport:
        healthy: list[str] = []
        stale: list[str] = []
        missing: list[str] = []
        for name in self._expected:
            age = self._hb.age_seconds(name)
            if age is None:
                missing.append(name)
            elif age > self._stale_after:
                stale.append(name)
            else:
                healthy.append(name)

        engaged = False
        lost = stale + missing
        if lost:
            self._outbox.enqueue(
                event_type="WORKER_HEARTBEAT_LOST",
                payload={"stale": stale, "missing": missing,
                         "stale_after_seconds": self._stale_after,
                         "action": "失败关闭:已触发杀开关停新单;systemd 负责拉起进程,恢复后须对账清零才可重新下单"},
            )
            if self._engage_on_loss and not self._kill.active():
                self._kill.engage(
                    reason=f"心跳丢失: stale={stale} missing={missing}",
                    source="supervisor",
                )
                engaged = True

        return SupervisionReport(
            healthy=tuple(healthy), stale=tuple(stale), missing=tuple(missing),
            kill_switch_engaged=engaged or self._kill.active(),
        )
