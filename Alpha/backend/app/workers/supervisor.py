"""监督进程(ALPHA-LIVE-040):心跳判活 + 失败关闭处置 + 告警。

掉线语义(DEPLOY_RUNBOOK 第 5 节恒真):任何组件失联 -> 告警邮件 ->
失败关闭(拍杀开关停新单)-> 自愈(systemd Restart=always 拉起进程,
恢复后对账清才可重新拿到下单资格)。Supervisor 自己不重启进程,
它负责「发现、停车、喊人」;拉起交给 systemd。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, Optional, Sequence

from backend.app.notify.outbox import Outbox
from backend.app.workers.heartbeat import HeartbeatStore
from backend.app.workers.killswitch import KillSwitch

DEFAULT_STALE_SECONDS = 90.0
#: 同一持续故障的重复提醒间隔(实机教训:每拍都入队曾积压 4626 条陈旧告警)
REALERT_INTERVAL_SECONDS = 6 * 3600.0


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
        realert_interval_seconds: float = REALERT_INTERVAL_SECONDS,
        now_fn: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ) -> None:
        self._hb = heartbeats
        self._outbox = outbox
        self._kill = kill_switch
        self._expected = tuple(expected_workers)
        self._stale_after = stale_after_seconds
        self._engage_on_loss = engage_kill_switch_on_loss
        self._realert = realert_interval_seconds
        self._now = now_fn
        # 告警去重状态(进程内;监督进程自身重启后最多多发一封,方向安全)
        self._last_lost_sig: tuple = ()
        self._last_alert_at: Optional[datetime] = None

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
        now = self._now()
        lost_sig = (tuple(sorted(stale)), tuple(sorted(missing)))
        if lost:
            # 告警去重:故障组合变化才告警;同一持续故障按间隔提醒。杀开关逻辑不受影响。
            is_new = lost_sig != self._last_lost_sig
            overdue = (self._last_alert_at is not None
                       and (now - self._last_alert_at).total_seconds() >= self._realert)
            if is_new or overdue:
                self._outbox.enqueue(
                    event_type="WORKER_HEARTBEAT_LOST",
                    payload={"stale": stale, "missing": missing,
                             "stale_after_seconds": self._stale_after,
                             "action": "失败关闭:已触发杀开关停新单;systemd 负责拉起进程,恢复后须对账清零才可重新下单"},
                )
                self._last_alert_at = now
            if self._engage_on_loss and not self._kill.active():
                self._kill.engage(
                    reason=f"心跳丢失: stale={stale} missing={missing}",
                    source="supervisor",
                )
                engaged = True
        elif self._last_lost_sig != ():
            self._outbox.enqueue(
                event_type="WORKER_RECOVERED",
                payload={"recovered": list(self._expected),
                         "note": "全部组件心跳恢复;若杀开关仍在,须人工/运维确认后解除"},
            )
            self._last_alert_at = None
        self._last_lost_sig = lost_sig if lost else ()

        return SupervisionReport(
            healthy=tuple(healthy), stale=tuple(stale), missing=tuple(missing),
            kill_switch_engaged=engaged or self._kill.active(),
        )
