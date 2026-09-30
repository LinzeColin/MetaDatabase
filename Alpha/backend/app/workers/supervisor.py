"""监督进程(ALPHA-LIVE-040):心跳判活 + 业务健康 + 失败关闭处置 + 告警 + 受限自愈。

掉线语义(DEPLOY_RUNBOOK 第 5 节恒真):任何组件失联 -> 失败关闭(拍杀开关停新单)-> 告警。
自愈分三层:进程崩溃由 systemd Restart 拉起;「活着但卡死」由看门狗与本进程的受限重启权兜底
(2026-07-23 事故补课);漏评估由本进程写补评估标记,在当天补评估窗里补做(复盘 R2)。
自动收闸只限「本进程自己拍下的闸」且须连续多拍健康,owner 拍的闸永不自动解。

告警一律经 AlertBook:同一 key 只在状态变化时发一封(转坏/恢复),状态持久化,
守护自己重启也不重发(实机教训:每拍都入队曾积压 4626 条陈旧告警)。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional, Sequence

from backend.app import health, truth
from backend.app.notify.outbox import AlertBook, Outbox
from backend.app.workers.heartbeat import HeartbeatStore
from backend.app.workers.killswitch import KillSwitch

DEFAULT_STALE_SECONDS = 90.0
#: 失联持续多久后动用受限重启权(给 systemd 自身的 Restart 留足先手)
RESTART_AFTER_SECONDS = 300.0
#: 两次自动重启之间的最小间隔(防抖:绝不允许重启风暴)
RESTART_COOLDOWN_SECONDS = 1800.0
#: 失联组件 -> 需要按序重启的服务单元(先网关后进程:卡死多因网关半死)
RESTART_UNITS = {
    "trading-worker": ("alpha-opend", "alpha-trading-worker"),
    "notify-worker": ("alpha-notify-worker",),
}
WORKER_CN = {"trading-worker": "交易主循环", "notify-worker": "邮件投递", "supervisor": "守护监督"}
#: 带日期的告警键:新一期接手后,旧一期静默收回(不发「已恢复」冒充修好)
DATED_PREFIXES = ("eval_missed:", "eval_blocked:")


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
        now_fn: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
        restart_fn: Optional[Callable[[str], bool]] = None,   # 受限重启权;None=关闭(默认)
        restart_after_seconds: float = RESTART_AFTER_SECONDS,
        restart_cooldown_seconds: float = RESTART_COOLDOWN_SECONDS,
        auto_clear_after_checks: Optional[int] = None,        # 自动收闸;None=关闭(默认)
        alerts: Optional[AlertBook] = None,
        health_fn: Optional[Callable[..., list]] = None,
        thresholds: Optional[dict] = None,
        runtime_dir: Optional[Path] = None,
    ) -> None:
        self._hb = heartbeats
        self._outbox = outbox
        self._kill = kill_switch
        self._expected = tuple(expected_workers)
        self._stale_after = stale_after_seconds
        self._engage_on_loss = engage_kill_switch_on_loss
        self._now = now_fn
        self._restart_fn = restart_fn
        self._restart_after = restart_after_seconds
        self._restart_cooldown = restart_cooldown_seconds
        self._auto_clear_after = auto_clear_after_checks
        self._alerts = alerts or AlertBook(outbox.session_factory, now_fn=now_fn)
        self._health_fn = health_fn or health.evaluate_health
        self._th = thresholds or health.load_thresholds()
        self._runtime_dir = runtime_dir
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
        # 心跳告警:每个组件一个键;抖动 1 拍不发,连续 raise_after 拍才发,连续 clear_after 拍好才发恢复
        for name in self._expected:
            self._alerts.observe(
                f"hb:{name}", name in lost, event_type="WORKER_HEARTBEAT_LOST",
                payload={"title": f"{WORKER_CN.get(name, name)}失联",
                         "stale": stale, "missing": missing,
                         "stale_after_seconds": self._stale_after,
                         "action": "失败关闭:已触发杀开关停新单;看门狗与守护自愈负责拉起,恢复后对账清零才可重新下单"},
                raise_after=int(self._th["raise_after_checks"]),
                clear_after=int(self._th["clear_after_checks"]))
        if lost:
            self._healthy_streak = 0
            if self._lost_since is None:
                self._lost_since = now
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
                for u in units:
                    self._alerts.observe(
                        f"restart:{u}", True, event_type="WORKER_RESTARTED",
                        payload={"title": f"守护自动重启 {u}", "units": results, "lost": lost},
                        raise_after=1)
        else:
            self._lost_since = None
            self._alerts.retire_stale("restart:", set())   # 全部恢复:重启告警随心跳恢复一并收回
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

        self._check_business(now)
        return SupervisionReport(
            healthy=tuple(healthy), stale=tuple(stale), missing=tuple(missing),
            kill_switch_engaged=engaged or self._kill.active(),
        )

    def _check_business(self, now: datetime) -> None:
        """业务健康逐项过状态簿;今天漏评估刚转红时写补评估标记(R2)。"""
        try:
            items = self._health_fn(
                session_factory=self._outbox.session_factory, heartbeats=self._hb,
                kill_switch=self._kill, now=now, runtime_dir=self._runtime_dir,
                thresholds=self._th, alerts=self._alerts)
        except Exception as exc:     # 判据自身出错也要让人知道,但不拖垮心跳监督
            self._alerts.observe("health_check", True, payload={
                "title": "健康判据自身出错", "detail": f"{type(exc).__name__}: {exc}"[:300],
                "action": "需要代理排查;心跳监督与刹车不受影响。"})
            return
        self._alerts.observe("health_check", False)
        keys = set()
        for item in items:
            keys.add(item.key)
            state = self._alerts.observe(
                item.key, item.bad, hold_seconds=item.hold_seconds,
                payload={"title": item.title, "detail": item.detail, "action": item.action})
            if state == "RAISED" and item.key.startswith("eval_missed:"):
                self._arm_makeup(item.key.split(":", 1)[1], now)
        for prefix in DATED_PREFIXES:
            self._alerts.retire_stale(prefix, keys)

    def _arm_makeup(self, due_tag: str, now: datetime) -> None:
        """今天的评估漏了且今天还没开始评估 -> 写补评估标记(当天 10:30-11:30 ET 补做)。

        只改「何时执行」,不碰任何风控。当天开始标记已写过 = 评估中途崩溃,为防重复下单不补。
        """
        from backend.app.workers.live_cycle import ET

        today = now.astimezone(ET).date().isoformat()
        if due_tag != today:
            return
        rt = self._runtime_dir if self._runtime_dir is not None else truth.runtime_dir()
        makeup, marker = rt / "makeup_eval.txt", rt / "last_s1_eval.txt"
        if makeup.exists():
            return
        if marker.exists() and marker.read_text().strip() == today:
            return
        rt.mkdir(parents=True, exist_ok=True)
        makeup.write_text(today)
