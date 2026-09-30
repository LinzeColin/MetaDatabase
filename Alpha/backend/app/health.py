"""业务健康判据(唯一出处):守护、体检、摘要、盘前自检都调 evaluate_health 这一个函数。

2026-07-28 复盘根因 R3:心跳只证明进程在转,不证明业务在做事。这里每一条判据都绑业务产出
(评估是否完成、成交是否入账、净值是否在长、行情是否取得到、邮件是否发得出去)。
阈值只从 configs/notify.yaml 读;判据只产出 HealthItem,发不发信由 AlertBook 按状态变化决定。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from backend.app import truth
from backend.app.adapters.brokers.base import SystemMode

NOTIFY_CONFIG = "configs/notify.yaml"
_MODE_RE = re.compile(r"'mode': '([A-Z_]+)'")
_BLOCKED_RE = re.compile(r"BLOCKED_[A-Z_]+")


@dataclass(frozen=True)
class HealthItem:
    key: str              # 去重键(固定机器码)
    bad: bool             # 这次检查是否异常
    title: str            # 人话标题
    detail: str           # 这是什么意思
    action: str           # 要不要你动手
    hold_seconds: float = 0.0    # 异常需持续多久才算红(卡在空转用)
    held_seconds: float = 0.0    # 这一轮异常已持续多久(读自告警状态簿)

    @property
    def red(self) -> bool:
        return self.bad and self.held_seconds >= self.hold_seconds


def load_thresholds(path: str = NOTIFY_CONFIG) -> dict:
    """告警与健康阈值(alerting + health 两段合并);读不到直接抛错,不猜默认值。"""
    import yaml

    cfg = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    return {**cfg["alerting"], **cfg["health"]}


def heartbeat_mode(detail: str) -> Optional[str]:
    """交易心跳 detail 里上报的运行模式(形如 {'mode': 'SHADOW', ...});没有返回 None。"""
    m = _MODE_RE.search(detail or "")
    return m.group(1) if m else None


def heartbeat_blocked(detail: str) -> Optional[str]:
    """交易心跳是否在报 BLOCKED_* 空转;返回空转标签或 None。"""
    m = _BLOCKED_RE.search(detail or "")
    return m.group(0) if m else None


def _read_json(path: Path) -> Optional[dict | list]:
    try:
        return json.loads(path.read_text())
    except Exception:
        return None


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def frozen_at(runtime_dir: Path) -> Optional[datetime]:
    """期初本金冻结时刻(= 本模式开始记账的时刻);未冻结 None。"""
    rec = _read_json(runtime_dir / "LIVE_START_CAPITAL.json")
    try:
        return _aware(datetime.fromisoformat(rec["frozen_at"]))
    except Exception:
        return None


def last_eval_result(runtime_dir: Path) -> Optional[dict]:
    """最近一次评估的完成记录(交易循环拍末原子写入)。"""
    rec = _read_json(runtime_dir / "last_eval_result.json")
    return rec if isinstance(rec, dict) else None


def eval_fill_count(session_factory, date_tag: str) -> int:
    """某评估日本系统订单里已有成交入账的笔数(幂等键 S1-<日期>- 开头)。"""
    from sqlalchemy import func, select

    from backend.app.domain.models import BrokerOrder, Execution, OrderIntent
    with session_factory() as s:
        return int(s.scalar(
            select(func.count(func.distinct(BrokerOrder.order_id)))
            .join(OrderIntent, OrderIntent.intent_id == BrokerOrder.intent_id)
            .join(Execution, Execution.order_id == BrokerOrder.order_id)
            .where(OrderIntent.idempotency_key.startswith(f"S1-{date_tag}-"))) or 0)


def evaluate_health(*, session_factory, heartbeats, kill_switch, now: datetime,
                    runtime_dir: Optional[Path] = None, thresholds: Optional[dict] = None,
                    alerts=None) -> list[HealthItem]:
    """全部业务判据,每条都产出(好也产出,供状态簿判恢复)。只读。"""
    rt = Path(runtime_dir) if runtime_dir is not None else truth.runtime_dir()
    th = thresholds or load_thresholds()
    now = _aware(now)
    m = truth.mode()
    expects = truth.expects_evaluation(m)
    hb = heartbeats.snapshot() if heartbeats is not None else {}
    items: list[HealthItem] = []

    # ---- 漏评估(R3):最近一个窗口已结束的周二,没有完成记录 ----
    from backend.app.workers.live_cycle import ET, missed_evaluation
    result = last_eval_result(rt)
    missed, why, due = missed_evaluation(
        now.astimezone(ET), last_completed_tag=str((result or {}).get("date", "")),
        expects=expects, since=frozen_at(rt))
    if missed and kill_switch is not None and kill_switch.active():
        why += " 另:紧急刹车当前处于拉下状态。"
    items.append(HealthItem(
        key=f"eval_missed:{due}", bad=missed,
        title=f"漏评估:{due} 周二该做的评估没有完成", detail=why or "按时完成",
        action=("先不用:若是当天,守护会自动安排补评估(美东 10:30-11:30);"
                "过了当天仍红,说明交易循环有问题,需要代理排查。")))

    # ---- 评估被拦:有计划却 0 单,或有提交却迟迟没成交 ----
    if expects and result is not None and result.get("date"):
        date_tag = str(result["date"])
        plan = list(result.get("plan") or [])
        submitted = int(result.get("submitted", 0))
        blocked_n = int(result.get("rejected", 0)) + int(result.get("skipped", 0))
        reasons = list(result.get("reject_rules") or []) + list(result.get("skip_reasons") or [])
        unfilled = 0
        try:
            done = _aware(datetime.fromisoformat(str(result.get("completed_at"))))
        except Exception:
            done = now
        if submitted > 0 and now - done >= timedelta(minutes=float(th["eval_fill_grace_minutes"])):
            unfilled = max(0, submitted - eval_fill_count(session_factory, date_tag))
        bad = bool(plan) and (submitted == 0 or blocked_n > 0 or unfilled > 0)
        items.append(HealthItem(
            key=f"eval_blocked:{date_tag}", bad=bad,
            title=f"评估被拦:{date_tag} 有调仓计划但没有全部成交",
            detail=(f"计划 {len(plan)} 笔({'、'.join(plan)}),提交 {submitted} 笔,"
                    f"被拦 {blocked_n} 笔,提交后未成交 {unfilled} 笔;"
                    f"原因:{'、'.join(reasons) or '无记录'}"),
            action="不用立刻动手;常见原因是行情过旧或现金不足,代理会复盘。"))

    # ---- 卡在空转:交易心跳报 BLOCKED_* 持续超过阈值 ----
    tw = hb.get("trading-worker", {})
    blocked = heartbeat_blocked(tw.get("detail", "")) if tw.get("status") == "RUNNING" else None
    key = "blocked:trading-worker"
    since = alerts.bad_since(key) if (alerts is not None and blocked) else None
    items.append(HealthItem(
        key=key, bad=blocked is not None,
        title=f"交易循环卡在空转({blocked or '无'})",
        detail=(f"交易进程在报 {blocked},正在按间隔自动重试装配:{str(tw.get('detail', ''))[:160]}"
                if blocked else "交易循环正常"),
        action="先不用:会每 60 秒自动重试;持续不恢复需要代理排查(影子盘多为行情源取不到)。",
        hold_seconds=float(th["blocked_minutes"]) * 60,
        held_seconds=(now - since).total_seconds() if since else 0.0))

    # ---- 净值快照停更 ----
    hist = _read_json(rt / "equity_history.json")
    last_at = None
    if isinstance(hist, list) and hist:
        try:
            last_at = _aware(datetime.fromisoformat(str(hist[-1]["at"])))
        except Exception:
            last_at = None
    limit = float(th["equity_stale_minutes"])
    age_min = (now - last_at).total_seconds() / 60 if last_at else None
    items.append(HealthItem(
        key="equity_stale", bad=expects and (age_min is None or age_min > limit),
        title="净值快照停更",
        detail=(f"最后一个净值点在 {age_min:.0f} 分钟前(阈值 {limit:g} 分钟)" if age_min is not None
                else "还没有任何净值点"),
        action="不用:定时任务会继续尝试;持续红说明快照任务或行情源有问题,代理会排查。"))

    # ---- 行情源连续失败(净值快照写入) ----
    facts = truth.facts_dir() if runtime_dir is None else rt / "facts"
    feed = _read_json(facts / "quote_feed.json") or {}
    fails = int(feed.get("consecutive_failures", 0)) if isinstance(feed, dict) else 0
    items.append(HealthItem(
        key="quote_feed", bad=fails >= int(th["quote_fail_threshold"]),
        title="行情源连续取不到",
        detail=(f"净值快照连续 {fails} 次取不到行情;最后一次成功:{feed.get('last_ok_at') or '从未'};"
                f"最近错误:{str(feed.get('last_error', ''))[:120]}"),
        action="不用:行情恢复后自动转绿;取不到行情期间模拟券商不会成交任何单。"))

    # ---- 发件箱发不出去 ----
    from sqlalchemy import func, select

    from backend.app.domain.models import OutboxEvent
    with session_factory() as s:
        failed = int(s.scalar(select(func.count()).select_from(OutboxEvent).where(
            OutboxEvent.delivery_status == "FAILED",
            OutboxEvent.created_at >= now - timedelta(hours=24))) or 0)
        stuck = int(s.scalar(select(func.count()).select_from(OutboxEvent).where(
            OutboxEvent.delivery_status == "PENDING",
            OutboxEvent.created_at < now - timedelta(minutes=float(th["outbox_stale_minutes"]))))
            or 0)
    items.append(HealthItem(
        key="outbox_broken", bad=failed > 0 or stuck > 0,
        title="邮件发不出去",
        detail=f"近 24 小时永久失败 {failed} 封,积压超过 {th['outbox_stale_minutes']} 分钟 {stuck} 封",
        action="需要代理检查邮件中继;这期间告警可能也收不到,请以看盘页为准。"))

    # ---- 模式漂移:运行中的进程报告的模式与配置不一致(被自动升级会落到这里) ----
    drift = []
    for name, h in sorted(hb.items()):
        reported = heartbeat_mode(h.get("detail", "")) if h.get("status") == "RUNNING" else None
        if reported is not None and reported != m.value:
            drift.append(f"{name} 报告 {reported}")
    items.append(HealthItem(
        key="mode_drift", bad=bool(drift),
        title="运行模式与配置不一致",
        detail=(f"{'、'.join(drift)},而配置模式是 {m.value}" if drift else f"一致({m.value})"),
        action="需要你确认:系统绝不自动升级模式;请告诉我是否你改过配置。"))

    # ---- 影子账对不上(仅影子盘):模拟券商簿 vs 本系统账本 ----
    mismatch = ""
    if m is SystemMode.SHADOW:
        mismatch = _shadow_ledger_gap(session_factory, rt, now)
    items.append(HealthItem(
        key="ledger_mismatch", bad=bool(mismatch),
        title="影子账对不上",
        detail=mismatch or "模拟券商簿与账本一致",
        action="需要代理对账:差异原因查清前,不要据此判断策略表现。"))
    return items


#: 模拟成交后多久仍未回灌入账算「对不上」(交易循环每 30 秒一拍,回灌在拍首)
LEDGER_SETTLE_SECONDS = 120


def _shadow_ledger_gap(session_factory, rt: Path, now: datetime) -> str:
    """模拟券商簿(券商侧真相)与本系统账本逐项核对;一致返回空串,否则返回人话差异。"""
    from sqlalchemy import select

    from backend.app.adapters.brokers.sim_broker import FILLED, SimBroker
    from backend.app.domain.models import SimOrder
    from backend.app.store.orders import OrderStore

    with session_factory() as s:
        rows = list(s.scalars(select(SimOrder).where(SimOrder.status == FILLED)))
    if not rows:
        return ""
    store = OrderStore(session_factory)
    settled = [r for r in rows
               if (now - _aware(r.created_at)).total_seconds() > LEDGER_SETTLE_SECONDS]
    missing = [r.remark for r in settled if not store.execution_exists(f"DEAL-{r.sim_order_id}")]
    if missing:
        return f"模拟成交超过 {LEDGER_SETTLE_SECONDS} 秒仍未入账:{'、'.join(missing)}"
    if len(settled) < len(rows):
        return ""          # 还有刚成交、尚未回灌的单,本拍不比总账
    rec = _read_json(rt / "LIVE_START_CAPITAL.json")
    try:
        start = float(rec["start_capital_usd"])
    except Exception:
        return "有模拟成交,但期初本金冻结文件读不到,无法对账"
    sim = SimBroker(session_factory, quotes=None, fee_model=None,
                    start_capital_usd=start, now_fn=lambda: now)
    book = store.own_book()
    gaps = []
    if sim.positions() != book.net:
        gaps.append(f"持仓 簿 {sim.positions()} / 账 {book.net}")
    if abs(float(sim.cash()) - (start + book.cash_flow_usd)) > 0.01:
        gaps.append(f"现金 簿 {float(sim.cash()):.2f} / 账 {start + book.cash_flow_usd:.2f}")
    return ";".join(gaps)
