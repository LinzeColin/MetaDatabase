"""监督进程(ALPHA-LIVE-040):心跳判活 + 失败关闭处置 + 告警 + 受限自愈。

掉线语义(DEPLOY_RUNBOOK 第 5 节恒真):任何组件失联 -> 告警邮件 ->
失败关闭(拍杀开关停新单)。自愈分两层:进程崩溃由 systemd Restart 拉起;
「活着但卡死」由看门狗与本进程的受限重启权兜底(2026-07-23 事故补课:
网关闪断后重启的进程卡死初始化 7 小时,当时谁都无权拉它)。
自动收闸只限「本进程自己拍下的闸」且须连续多拍健康,owner 拍的闸永不自动解。
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
#: 失联持续多久后动用受限重启权(给 systemd 自身的 Restart 留足先手)
RESTART_AFTER_SECONDS = 300.0
#: 两次自动重启之间的最小间隔(防抖:绝不允许重启风暴)
RESTART_COOLDOWN_SECONDS = 1800.0
#: 失联组件 -> 需要按序重启的服务单元(先网关后进程:卡死多因网关半死)
RESTART_UNITS = {
    "trading-worker": ("alpha-opend", "alpha-trading-worker"),
    "notify-worker": ("alpha-notify-worker",),
}


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
        restart_fn: Optional[Callable[[str], bool]] = None,   # 受限重启权;None=关闭(默认)
        restart_after_seconds: float = RESTART_AFTER_SECONDS,
        restart_cooldown_seconds: float = RESTART_COOLDOWN_SECONDS,
        auto_clear_after_checks: Optional[int] = None,        # 自动收闸;None=关闭(默认)
    ) -> None:
        self._hb = heartbeats
        self._outbox = outbox
        self._kill = kill_switch
        self._expected = tuple(expected_workers)
        self._stale_after = stale_after_seconds
        self._engage_on_loss = engage_kill_switch_on_loss
        self._realert = realert_interval_seconds
        self._now = now_fn
        self._restart_fn = restart_fn
        self._restart_after = restart_after_seconds
        self._restart_cooldown = restart_cooldown_seconds
        self._auto_clear_after = auto_clear_after_checks
        # 告警去重状态(进程内;监督进程自身重启后最多多发一封,方向安全)
        self._last_lost_sig: tuple = ()
        self._last_alert_at: Optional[datetime] = None
        self._lost_since: Optional[datetime] = None
        self._last_restart_at: Optional[datetime] = None
        self._healthy_streak = 0

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
            self._healthy_streak = 0
            if self._lost_since is None:
                self._lost_since = now
            # 告警去重:故障组合变化才告警;同一持续故障按间隔提醒。杀开关逻辑不受影响。
            is_new = lost_sig != self._last_lost_sig
            overdue = (self._last_alert_at is not None
                       and (now - self._last_alert_at).total_seconds() >= self._realert)
            if is_new or overdue:
                self._outbox.enqueue(
                    event_type="WORKER_HEARTBEAT_LOST",
                    payload={"stale": stale, "missing": missing,
                             "stale_after_seconds": self._stale_after,
                             "action": "失败关闭:已触发杀开关停新单;看门狗与守护自愈负责拉起,恢复后对账清零才可重新下单"},
                )
                self._last_alert_at = now
            if self._engage_on_loss and not self._kill.active():
                self._kill.engage(
                    reason=f"心跳丢失: stale={stale} missing={missing}",
                    source="supervisor",
                )
                engaged = True
            # 受限自愈:失联持续超过阈值且过了冷却期,按序重启对应服务单元
            if (self._restart_fn is not None
                    and (now - self._lost_since).total_seconds() >= self._restart_after
                    and (self._last_restart_at is None
                         or (now - self._last_restart_at).total_seconds() >= self._restart_cooldown)):
                units: list[str] = []
                for name in lost:
                    for u in RESTART_UNITS.get(name, ()):
                        if u not in units:
                            units.append(u)
                results = {u: bool(self._restart_fn(u)) for u in units}
                self._last_restart_at = now
                self._outbox.enqueue(
                    event_type="WORKER_RESTARTED",
                    payload={"units": results, "lost": lost,
                             "note": "守护进程动用受限重启权按序拉起;若仍失联将按冷却间隔再试并持续告警"},
                )
        else:
            if self._last_lost_sig != ():
                self._outbox.enqueue(
                    event_type="WORKER_RECOVERED",
                    payload={"recovered": list(self._expected),
                             "note": "全部组件心跳恢复;守护自己拍的闸将在连续健康确认后自动解除,owner 拍的闸永不自动解"},
                )
                self._last_alert_at = None
            self._lost_since = None
            self._healthy_streak += 1
            # 条件自动收闸:只解「本进程自己拍的闸」,且须连续多拍健康
            if (self._auto_clear_after is not None
                    and self._kill.active()
                    and self._healthy_streak >= self._auto_clear_after):
                detail = self._kill.detail() or {}
                if detail.get("source") == "supervisor":
                    self._kill.clear()
                    self._outbox.enqueue(
                        event_type="KILL_SWITCH_CLEARED",
                        payload={"healthy_checks": self._healthy_streak,
                                 "cleared_reason": detail.get("reason", ""),
                                 "note": "守护确认连续健康后解除自己拍下的刹车;交易在下一拍恢复"},
                    )
        self._last_lost_sig = lost_sig if lost else ()

        return SupervisionReport(
            healthy=tuple(healthy), stale=tuple(stale), missing=tuple(missing),
            kill_switch_engaged=engaged or self._kill.active(),
        )
