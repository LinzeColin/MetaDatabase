"""070 交易循环:行情 -> 策略(冠军配置)-> 组合差分 -> 风控 -> 网关 -> 影子记录。

装配约束:
- 按模式经 wiring 分发:SHADOW 走 shadow_cycle(本机模拟券商),PAPER/MICRO_LIVE 走
  build_broker_cycle(券商);其余模式无条目,装配失败关闭;
- 券商路径启动即断言绑定账户环境与模式一致,否则拒绝启动(失败关闭);
- 券商事实回灌走轮询:订单状态只允许「前进」,成交按券商成交号幂等入账一次(含费用);
- 评估节拍:冠军口径 = 周二开盘后 30-90 分钟窗口,每交易日至多评估一次;
  **取数齐全后才落标记**(取不齐按间隔重试),标记落下后才下单(崩溃重启宁可错过,不重复下单);
  信号口径 T-1(与回测一致);两段式下单:先卖、回灌后重算敞口、再买;
- 任何异常向上抛,由 TradingWorker 失败关闭 + systemd 重启走 recover_in_flight。
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Callable, Optional, Sequence
from zoneinfo import ZoneInfo

from backend.app import truth, wiring
from backend.app.adapters.brokers.base import SystemMode
from backend.app.domain.state_machine import OrderState
from backend.app.marketdata.guard import DEFAULT_FRESHNESS_THRESHOLD_SECONDS
from backend.app.risk.engine import RiskContext
from backend.app.strategies.bars import Bar, slice_until
from backend.app.strategies.s1_momentum import evaluate_s1, load_s1_config

ET = ZoneInfo("America/New_York")

#: 限价相对快照价的上浮(买)/下浮(卖)比例。下单与整股取整留余量共用这一个数。
LIMIT_MARKUP = 0.001
#: 补评估窗口(美东分钟):开盘 09:30 后 60-120 分钟 = 10:30-11:30
MAKEUP_WINDOW_MINUTES = (9 * 60 + 30 + 60, 9 * 60 + 30 + 120)
#: 评估拍取数阶段(快照+日线)的总预算(秒)。每次请求自带超时;总预算保证一拍不会久到
#: 超过守护的心跳陈旧阈值(supervisor.DEFAULT_STALE_SECONDS)。
FETCH_BUDGET_SECONDS = 45.0

#: 券商状态 -> 网关回调状态(None=本状态不经 on_order_event:成交走 on_fill,过程态跳过)
BROKER_STATUS_MAP: dict[str, Optional[str]] = {
    "SUBMITTING": None, "WAITING_SUBMIT": None,
    "SUBMITTED": "ACCEPTED",          # 券商已受理挂单 = 我方 ACCEPTED
    "FILLED_PART": None, "FILLED_ALL": None,
    "CANCELLED_PART": "CANCELLED", "CANCELLED_ALL": "CANCELLED",
    "FAILED": "REJECTED", "SUBMIT_FAILED": "REJECTED",
    "DISABLED": "REJECTED", "DELETED": "REJECTED",
    "TIMEOUT": "EXPIRED",
}

#: 状态推进秩(只允许向前回灌,杜绝轮询重复触发非法迁移)
_RANK = {
    OrderState.INTENT_CREATED: 0, OrderState.RISK_APPROVED: 1,
    OrderState.SUBMITTING: 2, OrderState.SUBMITTED: 3, OrderState.ACCEPTED: 4,
    OrderState.PARTIALLY_FILLED: 5, OrderState.FILLED: 9, OrderState.CANCELLED: 9,
    OrderState.REJECTED: 9, OrderState.EXPIRED: 9, OrderState.SUBMIT_FAILED: 9,
    OrderState.RISK_REJECTED: 9, OrderState.UNKNOWN_RECONCILIATION_REQUIRED: 9,
}
_TARGET_RANK = {"SUBMITTED": 3, "ACCEPTED": 4, "CANCELLED": 9,
                "REJECTED": 9, "EXPIRED": 9}


def rank_allows(current: OrderState, target_status: str) -> bool:
    """回灌闸:目标状态必须比当前状态更靠前推进,且当前非终态。"""
    cur = _RANK.get(current, 9)
    tgt = _TARGET_RANK.get(target_status)
    if tgt is None:
        return False
    return cur < 9 and tgt > cur


def in_eval_window(now_et: datetime, *, weekday: int = 1,
                   open_minute: int = 9 * 60 + 30,
                   window: tuple[int, int] = (30, 90)) -> bool:
    """冠军节拍:周二(weekday=1)开盘后 30-90 分钟。"""
    if now_et.weekday() != weekday:
        return False
    minute = now_et.hour * 60 + now_et.minute
    return open_minute + window[0] <= minute <= open_minute + window[1]


def market_open_now(now_et: datetime) -> bool:
    """美股常规交易时段(周一至周五 09:30-16:00 ET)。"""
    minute = now_et.hour * 60 + now_et.minute
    return now_et.weekday() < 5 and (9 * 60 + 30) <= minute <= (16 * 60)


def eval_trigger(now_et: datetime, *, force_exists: bool, makeup_today: bool) -> tuple[bool, bool]:
    """评估触发判定(纯函数,可脱离真实时间测试)。返回 (是否触发, 是否为强制触发)。

    三条通路:①周二常规窗;②FORCE_EVAL 立即触发(任意开市时刻,owner 说跑就跑);
    ③补评估(当日标记 + 开盘后 60-120 分钟 = 美东 10:30-11:30)。只决定"何时评估",绝不影响任何风控。
    """
    minute = now_et.hour * 60 + now_et.minute
    # 强制评估只改"哪一天",不改"一天里的哪一刻":沿用策略回测验证过的开盘后 30-90 分钟
    # 执行窗,避开开盘竞价的宽点差(9:30 瞬间成交质量最差)。
    in_exec_window = (9 * 60 + 60) <= minute <= (9 * 60 + 120)
    forced = force_exists and now_et.weekday() < 5 and in_exec_window
    makeup_ok = (makeup_today and now_et.weekday() < 5
                 and MAKEUP_WINDOW_MINUTES[0] <= minute <= MAKEUP_WINDOW_MINUTES[1])
    return (in_eval_window(now_et) or forced or makeup_ok), forced


#: 评估窗结束(美东分钟):开盘 09:30 + 90 分钟 = 11:00
EVAL_WINDOW_END_MINUTE = 9 * 60 + 30 + 90


def missed_evaluation(now_et: datetime, *, last_completed_tag: str, expects: bool,
                      since: Optional[datetime], weekday: int = 1) -> tuple[bool, str, str]:
    """业务级健康判据(纯函数):**最近一个评估窗已结束的周二,没有完成记录**。

    2026-07-28 事故的核心教训(根因 R3):心跳只证明"进程在转",不证明"业务在做事"。
    当时 worker 空转 15.9 小时、喂了 1904 次心跳、页面始终显示"✅ 系统正常运行中",
    而交易窗静默流逝、首单从未发生。**健康检查必须绑业务产出,不能只绑进程存活。**

    due = 今天是周二且过了 11:00 ET 就是今天,否则是上一个周二——所以周三、周四仍是红的。
    四条同时满足才判红:该模式应评估(expects)、部署时刻(since)不晚于 due 的窗口结束、
    完成记录(last_eval_result.json 的 date)早于 due。开始标记不算完成(评估中途崩溃也要红)。
    返回 (是否漏评估, 人话原因, due 日期)。
    """
    minute = now_et.hour * 60 + now_et.minute
    back = (now_et.weekday() - weekday) % 7
    if back == 0 and minute <= EVAL_WINDOW_END_MINUTE:
        back = 7
    due = now_et.date() - timedelta(days=back)
    due_tag = due.isoformat()
    if not expects:
        return False, "", due_tag
    window_end = datetime(due.year, due.month, due.day, EVAL_WINDOW_END_MINUTE // 60,
                          EVAL_WINDOW_END_MINUTE % 60, tzinfo=ET)
    if since is not None and window_end < since:          # 部署前就结束的窗口不算漏
        return False, "", due_tag
    if last_completed_tag >= due_tag:
        return False, "", due_tag
    return True, (f"{due_tag}(周二)的评估窗(开盘后30-90分钟)已于 "
                  f"{EVAL_WINDOW_END_MINUTE // 60}:{EVAL_WINDOW_END_MINUTE % 60:02d} ET 结束,"
                  f"但没有完成记录(最近一次完成:{last_completed_tag or '从未'})。"
                  "交易循环可能在空转——查心跳 detail 是否为 BLOCKED_*,"
                  "或评估中途崩溃(只有开始标记、没有完成记录)。"), due_tag


def plan_rebalance(
    target_weights: dict[str, float],
    positions: dict[str, int],
    prices: dict[str, float],
    *,
    capital_usd: float,
    threshold_pct: float,
    single_order_cap_usd: Optional[float] = None,
    reserve_ratio: float = 0.0,
    reserve_usd: float = 0.0,
) -> list[tuple[str, str, int]]:
    """目标权重 × 资金上限 -> 整股目标 -> 差分 -> 切片后的 (side, symbol, qty) 列表。

    取整前先从资金里扣留余量:reserve_ratio(限价上浮+滑点的比例)与 reserve_usd(整套计划的
    佣金与卖出费用)。否则整股市值与本金只差一两美元时,最后一笔会被总敞口上限或现金不足拒掉,
    一周最后一片仓位就空着。

    卖单在前(先腾现金);小于阈值(占资金 %)的差分忽略;买不起 1 股即跳过。
    单笔名义超过 single_order_cap_usd 时切成多笔(实机 2026-07-21:QQQ 一笔 2172 澳元
    撞上 1800 澳元单笔硬上限被风控拒——法条不动,订单迁就法条)。
    """
    orders: list[tuple[str, str, int]] = []
    threshold_usd = capital_usd * threshold_pct / 100.0
    budget_usd = max(0.0, capital_usd * (1.0 - reserve_ratio) - reserve_usd)
    targets: dict[str, int] = {}
    for sym, w in target_weights.items():
        p = prices.get(sym)
        if p is None or p <= 0 or w <= 0:
            targets[sym] = 0
            continue
        targets[sym] = int(budget_usd * w // p)
    for sym in sorted(set(positions) | set(targets)):
        p = prices.get(sym)
        if p is None or p <= 0:
            continue
        delta = targets.get(sym, 0) - positions.get(sym, 0)
        if delta == 0 or abs(delta) * p < threshold_usd:
            continue
        side, qty = ("SELL" if delta < 0 else "BUY"), abs(delta)
        if single_order_cap_usd and single_order_cap_usd > 0:
            max_per_order = max(1, int(single_order_cap_usd // p))
            while qty > max_per_order:
                orders.append((side, sym, max_per_order))
                qty -= max_per_order
        if qty > 0:
            orders.append((side, sym, qty))
    orders.sort(key=lambda o: 0 if o[0] == "SELL" else 1)
    return orders


def _write_json_atomic(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, default=str))
    os.replace(tmp, path)


def _freeze_start_capital(start_capital_usd: float) -> None:
    """把策略初始本金落盘冻结(已存在则不覆盖)。看盘据此把策略净值与 owner 隔离。

    原子写(写一半崩溃不会留下截断文件);券商路径在首笔交易时调用;
    影子盘在装配时调用并读回校验(本函数吞异常,影子盘不能吞)。
    """
    p = truth.runtime_dir() / "LIVE_START_CAPITAL.json"
    if p.exists():
        return
    try:
        _write_json_atomic(p, {
            "start_capital_usd": round(float(start_capital_usd), 2),
            "frozen_at": datetime.now(timezone.utc).isoformat(),
            "note": "策略期初可动用本金;净值基线,与 owner 自有交易/出入金隔离",
        })
    except Exception:
        pass


def quote_age_seconds(update_time: str, now_utc: datetime) -> Optional[float]:
    """快照 update_time(交易所东部时区)-> 距今秒数;解析失败如实 None(风控按缺失拒)。"""
    try:
        naive = datetime.fromisoformat(update_time)
        stamped = naive.replace(tzinfo=ET)
        return max(0.0, (now_utc - stamped.astimezone(timezone.utc)).total_seconds())
    except (ValueError, TypeError):
        return None




@dataclass
class LiveCycleDeps:
    """依赖包(真机由 build_*_cycle 装配;测试可注入假件)。"""
    read_client: object
    trade_client: object
    store: object
    gateway: object
    shadow: object
    lease: object
    kill_switch: object
    cfg: dict
    capital_usd: float
    fx_usd_aud: Decimal
    marker_path: Path
    fee_estimate: Callable[[str, int, float], float]
    slippage_bps: float          # 每边滑点(基点),整股取整留余量用;出处 FeeModel.slippage_bps
    mode: str                    # 真实运行模式,供心跳/看盘如实上报;必填,没有缺省
    now_fn: Callable[[], datetime] = lambda: datetime.now(timezone.utc)
    #: 非 None 时直接取资金(影子盘 = 模拟券商按账本算),异常上抛不吞;None 走券商只读查询
    funds_fn: Optional[Callable[[], dict]] = None
    #: 取数不齐时的重试间隔(秒);期间不落评估标记
    data_retry_seconds: float = 120
    data_retry_at: Optional[datetime] = None     # 下次允许重试取数的时刻(进程内存)
    closed_day: Optional[str] = None             # 已判定休市的评估日(进程内存,当天不再重复取数)
    fetch_budget_seconds: float = FETCH_BUDGET_SECONDS


def _ensure_lease(lease) -> None:
    """续约;过期则尝试接管(同持有人/无人持有即成功)。他人有效持有仍抛错失败关闭。

    覆盖两类真实场景:杀开关 HALTED 期间数小时不续约;装配期慢活(SDK 建上下文+
    悬单恢复)吃掉整个 TTL——实机 2026-07-19 均已发生过。
    """
    try:
        lease.renew()
    except Exception:
        lease.acquire()




def _backfill(d: LiveCycleDeps, summary: dict) -> None:
    """回灌券商事实:状态只前进;成交按成交号幂等入账(费用如实透传)。"""
    orders = d.trade_client.poll_orders()
    remark_by_broker_id: dict[str, str] = {}
    ours: list[dict] = []
    for row in orders:
        remark = row.get("remark", "")
        if not remark.startswith("S1-"):
            continue  # 非本系统单(如人工在 App 模拟盘手点)不回灌,对账器另管
        remark_by_broker_id[row["broker_order_id"]] = remark
        ours.append(row)
        target = BROKER_STATUS_MAP.get(row.get("status", ""), None)
        if target is None:
            continue
        order_id = d.store.find_order_by_idempotency_key(remark)
        if order_id is None:
            continue
        if rank_allows(d.store.get_state(order_id), target):
            d.gateway.on_order_event(idempotency_key=remark,
                                     broker_order_id=row["broker_order_id"],
                                     status=target)
            summary["backfilled"] += 1
    # 成交回灌两条路:REAL/LOCAL 走成交明细;SIMULATE 环境无成交明细接口(实机 2026-07-19
    # 报 "Paper trading does not support deal data")→ 用订单行 dealt_qty 增量派生,
    # 合成成交号含累计量 → execution_exists 天然幂等。两路互斥,绝不重复入账。
    deals: list[dict] = []
    deals_supported = True
    try:
        deals = d.trade_client.poll_deals()
    except Exception as exc:
        if "not support" not in str(exc).lower():
            raise
        deals_supported = False
    if deals_supported:
        for deal in deals:
            exec_id = deal.get("broker_execution_id", "")
            if not exec_id or d.store.execution_exists(exec_id):
                continue
            remark = remark_by_broker_id.get(deal.get("broker_order_id", ""))
            if remark is None:
                continue
            d.gateway.on_fill(idempotency_key=remark, quantity=int(deal["quantity"]),
                              price=Decimal(str(deal["price"])),
                              fees=Decimal(str(deal.get("fees", 0))),
                              broker_execution_id=exec_id)
            summary["fills"] += 1
    else:
        for row in ours:
            if row.get("status") not in ("FILLED_PART", "FILLED_ALL"):
                continue
            remark = row["remark"]
            order_id = d.store.find_order_by_idempotency_key(remark)
            if order_id is None:
                continue
            dealt = int(row.get("dealt_qty", 0))
            delta = dealt - d.store.get_filled_quantity(order_id)
            price = float(row.get("dealt_avg_price", 0.0))
            if delta <= 0 or price <= 0:
                continue
            exec_id = f"SIMFILL-{remark}-{dealt}"
            if d.store.execution_exists(exec_id):
                continue
            d.gateway.on_fill(idempotency_key=remark, quantity=delta,
                              price=Decimal(str(price)), broker_execution_id=exec_id)
            summary["fills"] += 1


def _data_complete(bars_by_symbol: dict, cfg: dict, as_of: date) -> str:
    """评估数据是否齐全;齐全返回空串,否则返回人话缺口(调用方据此不落标记、稍后重试)。"""
    need = max(max(int(x) for x in cfg["score"]["lookbacks_trading_days"]) + 1,
               int(cfg["absolute_momentum_filter"]["sma_period"]))
    gaps = []
    for sym in cfg["universe"]:
        bars = slice_until(bars_by_symbol.get(sym, ()), as_of)
        if len(bars) < need:
            gaps.append(f"{sym} 日线 {len(bars)}/{need} 根")
        elif (as_of - bars[-1].day).days > 5:
            gaps.append(f"{sym} 最后一根日线 {bars[-1].day} 距 {as_of} 超过 5 天")
    return "; ".join(gaps)


def _data_gap(d: LiveCycleDeps, summary: dict, now_utc: datetime, reason: str) -> dict:
    """数据不齐:不落标记,记下重试时刻(R1:取数失败不再让当周作废)。"""
    d.data_retry_at = now_utc + timedelta(seconds=d.data_retry_seconds)
    summary["data_error"] = reason[:200]
    summary["retry_at"] = d.data_retry_at.isoformat()
    return summary


def _quote_day(update_time: str) -> Optional[date]:
    """快照 update_time(美东无时区字符串)-> 行情所在美东日期;解析失败 None。"""
    try:
        return datetime.fromisoformat(update_time).date()
    except (ValueError, TypeError):
        return None


def _can_retry_in_window(d: LiveCycleDeps, now_et: datetime, *, regular: bool) -> bool:
    """本窗口内(距窗口结束还够再拍一次)是否还有重试机会。"""
    end_minute = EVAL_WINDOW_END_MINUTE if regular else MAKEUP_WINDOW_MINUTES[1]
    left = end_minute * 60 - (now_et.hour * 3600 + now_et.minute * 60 + now_et.second)
    return left > d.data_retry_seconds


def _market_closed(d: LiveCycleDeps, summary: dict, now_et: datetime, today_tag: str,
                   now_utc: datetime) -> dict:
    """休市评估日:写「休市顺延」完成记录(不算漏评估),下一个工作日补评估;当天不再重复取数。"""
    nxt = now_et.date() + timedelta(days=1)
    while nxt.weekday() >= 5:
        nxt += timedelta(days=1)
    rt = d.marker_path.parent
    (rt / "makeup_eval.txt").write_text(nxt.isoformat())
    _write_json_atomic(rt / "last_eval_result.json", {
        "date": today_tag, "mode": d.mode, "market_closed": True, "deferred_to": nxt.isoformat(),
        "started_at": now_utc.isoformat(), "completed_at": d.now_fn().isoformat(),
        "plan": [], "submitted": 0, "rejected": 0, "skipped": 0, "skip_reasons": [],
        "reject_rules": [],
    })
    d.closed_day = today_tag
    summary["market_closed"] = True
    summary["deferred_to"] = nxt.isoformat()
    return summary


def run_live_cycle(d: LiveCycleDeps) -> dict:
    """单拍:回灌 -> (窗口内)取数齐全 -> 落标记 -> 评估 -> 两段式下单 -> 完成记录。异常上抛失败关闭。"""
    _ensure_lease(d.lease)
    now_utc = d.now_fn()
    now_et = now_utc.astimezone(ET)
    summary: dict = {"mode": d.mode, "et": now_et.strftime("%a %H:%M"),
                     "backfilled": 0, "fills": 0, "evaluated": False,
                     "submitted": 0, "rejected": 0, "skipped": 0}

    # ---- 1) 回灌券商事实 ----
    _backfill(d, summary)

    # ---- 2) 评估窗口判定(每交易日至多一次) ----
    # 补评估:一次性文件写明日期(工程缺陷误伤当日决策后的窗口内补救,用后即焚,
    # 事故与补救均入报告)。正常节拍仍是周二;补评估不改变周频纪律本身。
    today_tag = now_et.date().isoformat()
    makeup = d.marker_path.parent / "makeup_eval.txt"
    if makeup.exists() and makeup.read_text().strip() < today_tag:
        makeup.unlink(missing_ok=True)      # 日期早于今天的旧标记永远用不上,清掉免得它挡住新的补评估
    makeup_today = makeup.exists() and makeup.read_text().strip() == today_tag
    # 立即评估开关(owner 2026-07-26:"不能用真实时间等待浪费"):放一个 FORCE_EVAL 文件,
    # 下一个开市时刻立刻评估并按纪律下单,不必枯等周二。用后即焚,只生效一次;
    # 只放宽"什么时候评估",绝不放宽任何风控——敞口/单笔/频控/行情新鲜度一律照旧。
    force = d.marker_path.parent / "FORCE_EVAL.txt"
    trigger, forced = eval_trigger(now_et, force_exists=force.exists(),
                                   makeup_today=makeup_today)
    already = d.marker_path.exists() and d.marker_path.read_text().strip() == today_tag
    if not trigger or already:
        return summary
    if d.closed_day == today_tag:
        summary["market_closed"] = True
        return summary
    if d.data_retry_at is not None and now_utc < d.data_retry_at:
        summary["data_error"] = "上次取数不齐,等待重试"
        summary["retry_at"] = d.data_retry_at.isoformat()
        return summary

    # ---- 3) 取数:放在落标记之前,取不齐不落标记,按间隔重试 ----
    universe = list(d.cfg["universe"])
    symbols = list(dict.fromkeys(universe + [d.cfg["cash_proxy"]]))  # 兜底标的也要有价才买得进
    as_of = now_et.date() - timedelta(days=1)     # 信号口径 T-1(与回测一致,不用当天未收盘日线)
    fetch_deadline = now_utc + timedelta(seconds=d.fetch_budget_seconds)
    try:
        snapshot = d.read_client.get_snapshot(symbols)
        start = (as_of - timedelta(days=450)).isoformat()
        bars_by_symbol = {}
        for sym in universe:
            if d.now_fn() > fetch_deadline:
                raise TimeoutError(f"取数超过总预算 {d.fetch_budget_seconds:g} 秒")
            rows = d.read_client.get_daily_bars(sym, start, as_of.isoformat())
            bars_by_symbol[sym] = [
                Bar(day=date.fromisoformat(r["day"]), open=r["open"], high=r["high"],
                    low=r["low"], close=r["close"])
                for r in rows if r.get("day")
            ]
    except Exception as exc:
        return _data_gap(d, summary, now_utc, f"取数失败 {type(exc).__name__}: {exc}")
    # 休市的评估日(如周二遇独立日):行情停在上一个交易日,不是「行情过旧」——
    # 不落标记、不算漏评估,顺延到下一个交易日按补评估处理。
    if snapshot and not any(_quote_day(v.get("update_time", "")) == now_et.date()
                            for v in snapshot.values()):
        return _market_closed(d, summary, now_et, today_tag, now_utc)
    gap = _data_complete(bars_by_symbol, d.cfg, as_of)
    if gap:
        return _data_gap(d, summary, now_utc, f"日线不齐: {gap}")
    prices = {s: float(v["price"]) for s, v in snapshot.items() if v.get("price")}
    # 鲜度按「所交易标的自己」判(实机 2026-07-21:货币基金 BIL 天然低频报价,
    # 用全池最陈旧年龄一票否决了 GLD/QQQ——误伤;冷门不参与交易就不该连坐)
    age_by_sym = {s: quote_age_seconds(v.get("update_time", ""), now_utc)
                  for s, v in snapshot.items()}
    result = evaluate_s1(bars_by_symbol, d.cfg, as_of)

    # 隔离铁律(owner 2026-07-24):调仓与敞口只认系统自己成交推导的净持仓,**绝不读整个
    # 券商账户**——否则 owner 自有的 TQQQ/SPCG、或 owner 自己买的策略池标的会被误当成系统仓
    # 去卖去调。此前靠"owner 标的不在行情表里被跳过"侥幸安全,现在改为设计安全。
    positions = d.store.net_positions()
    gross_usd = sum(q * prices.get(s, 0.0) for s, q in positions.items())

    # 单笔上限:比例与本金一律从权威配置读(backend/app/truth),**不在此写死**。
    cap_usd = truth.single_order_cap_usd()
    # 可动用本金 = min(授权上限, 真实购买力 + 已持有市值)。owner 2026-07-24 裁定按百分比
    # 理解敞口:授权额度只是天花板,真正能动的钱以实况为准——否则资金不足时会超买被拒。
    if d.funds_fn is not None:
        funds: Optional[dict] = d.funds_fn()      # 影子盘:按账本算,出错即上抛
    else:
        try:
            funds = d.read_client.get_funds(os.environ.get("ALPHA_EXPECTED_ACC_ID", ""))
        except Exception:
            funds = None      # 读不到就退回授权额度(保守方向由风控与券商余额兜底)
    effective_capital_usd = d.capital_usd
    if funds is not None:
        power = float(funds.get("power", funds.get("cash", 0.0)))
        effective_capital_usd = min(d.capital_usd, power + gross_usd)
    plan_args = dict(capital_usd=effective_capital_usd,
                     threshold_pct=float(d.cfg.get("rebalance_threshold_pct", 5)),
                     single_order_cap_usd=cap_usd)
    # 整股取整留余量:限价上浮 + 滑点按比例扣,整套计划的佣金与卖出费用(FeeModel)按额扣。
    # 先按无余量出初稿只为估费用,再按余量重排;否则整股市值贴着本金时最后一笔会被拒。
    draft = plan_rebalance(dict(result.target_weights), positions, prices, **plan_args)
    reserve_usd = sum(d.fee_estimate(side, qty, prices[sym]) for side, sym, qty in draft)
    plan = plan_rebalance(dict(result.target_weights), positions, prices, **plan_args,
                          reserve_ratio=LIMIT_MARKUP + d.slippage_bps / 10000.0,
                          reserve_usd=reserve_usd)
    # plan_rebalance 会静默跳过无价标的:目标标的与持仓标的缺价 = 数据不齐,不能带病评估
    needed = {s for s, w in result.target_weights.items() if w > 0} | set(positions)
    missing = sorted(s for s in needed if not prices.get(s))
    if missing:
        return _data_gap(d, summary, now_utc, f"缺实时价: {missing}")
    # 行情年龄与风控同一常量;过旧不落标记(否则整周作废),按间隔重试,直到窗口最后一次机会
    # 才放行(此时落标记、由风控拒并告警,不再无限等)。
    stale = sorted(s for s in needed
                   if age_by_sym.get(s) is None
                   or not 0.0 <= age_by_sym[s] <= DEFAULT_FRESHNESS_THRESHOLD_SECONDS)
    if stale and _can_retry_in_window(d, now_et, regular=in_eval_window(now_et) or forced):
        return _data_gap(d, summary, now_utc, f"行情过旧: {stale}")

    # ---- 4) 数据齐了:消耗一次性开关,先落标记再下单(崩溃重启宁可错过,不重复下单) ----
    d.data_retry_at = None
    if makeup_today:
        makeup.unlink(missing_ok=True)
    if forced:
        force.unlink(missing_ok=True)       # 用后即焚:绝不因残留文件反复触发
        summary["forced_eval"] = True
    started_at = now_utc
    d.marker_path.parent.mkdir(parents=True, exist_ok=True)
    d.marker_path.write_text(today_tag)
    summary["evaluated"] = True
    summary["capital_usd"] = round(effective_capital_usd, 2)
    summary["plan"] = [f"{s} {sym}x{q}" for s, sym, q in plan]

    # 首笔交易时冻结策略初始本金:此后看盘净值只随策略自己的买卖变动,与 owner 账户活动隔离。
    if plan:
        _freeze_start_capital(effective_capital_usd)

    # 影子盘不连券商,辖区探针不适用;不伪造探针记录。券商模式仍按探针,缺省 DENY。
    jurisdiction = ("ALLOW" if d.mode == SystemMode.SHADOW.value
                    else (d.store.latest_jurisdiction_verdict() or "DENY"))
    part_seen: dict[tuple, int] = {}
    reserved_aud = Decimal("0")   # 本轮已发买单占用的敞口(逐笔累加给风控看)
    reject_rules: set[str] = set()

    def submit(side: str, sym: str, qty: int, gross_aud: Decimal) -> bool:
        nonlocal reserved_aud
        px = prices[sym]
        limit = round(px * (1 + LIMIT_MARKUP if side == "BUY" else 1 - LIMIT_MARKUP), 2)
        n = part_seen.get((sym, side), 0) + 1
        part_seen[(sym, side)] = n
        key = f"S1-{today_tag}-{sym}-{side}-{qty}" + (f"-p{n}" if n > 1 else "")
        ctx = RiskContext(
            side=side, symbol=sym, market="US_ETF", quantity=qty,
            price_usd=Decimal(str(limit)), fx_usd_aud=d.fx_usd_aud, now=now_utc,
            current_gross_exposure_aud=gross_aud,
            pending_buy_reserved_aud=reserved_aud,
            quote_age_seconds=age_by_sym.get(sym),
            kill_switch_active=d.kill_switch.active(),
            reconciliation_open=d.store.halt_new_orders(),
            jurisdiction_verdict=jurisdiction,
        )
        try:
            # 取数慢会吃掉租约 TTL(30 秒);提交前续约,免得网关因租约过期把整拍单子当 skipped 吞掉
            _ensure_lease(d.lease)
            order_id = d.gateway.submit_intent(
                idempotency_key=key, symbol=sym, side=side, quantity=qty,
                currency="USD", strategy_source=str(d.cfg.get("strategy_id", "S1")),
                order_type="LIMIT", limit_price=Decimal(str(limit)), risk_ctx=ctx)
        except Exception as exc:  # 单笔被闸(幂等已用/频控/租约/模拟券商拒)不拖垮整拍:如实计数
            summary["skipped"] += 1
            code = getattr(exc, "raw_code", None)
            summary.setdefault("skip_reasons", []).append(
                f"{sym}:{type(exc).__name__}" + (f":{code}" if code else ""))
            return False
        if d.store.get_state(order_id) is OrderState.RISK_REJECTED:
            summary["rejected"] += 1
            reject_rules.update(d.store.get_risk_rules(order_id))
            return False
        summary["submitted"] += 1
        if side == "BUY":
            reserved_aud += Decimal(str(limit)) * qty * d.fx_usd_aud
        # 影子记录独立 try:影子失败绝不污染下单账目(实机教训:外键传错时
        # 三笔成交被误计成 skipped;且影子键是意图号不是订单号)
        try:
            d.shadow.record_decision(
                intent_id=d.store.get_intent_id(order_id) or order_id,
                hypothetical_limit_price=Decimal(str(limit)),
                estimated_fees=Decimal(str(round(d.fee_estimate(side, qty, limit), 4))),
                rationale={"as_of": today_tag, "side": side, "symbol": sym, "qty": qty})
        except Exception as sexc:
            summary.setdefault("shadow_errors", []).append(f"{sym}:{type(sexc).__name__}")
        return True

    # 两段式:先卖;卖单提交过就再回灌一次、按新持仓重算敞口,再下买单。
    # 否则换仓周的买单按"卖前持仓"算敞口,必撞 RULE_GROSS_EXPOSURE_CAP,一周白过。
    # (券商路径卖单若未即时成交,买单仍按旧敞口被拒——与此前一样保守。)
    gross_aud = Decimal(str(gross_usd)) * d.fx_usd_aud
    sold = [submit(side, sym, qty, gross_aud) for side, sym, qty in plan if side == "SELL"]
    buys = [(side, sym, qty) for side, sym, qty in plan if side == "BUY"]
    if buys and any(sold):
        _backfill(d, summary)
        after = d.store.net_positions()
        gross_aud = Decimal(str(sum(q * prices.get(s, 0.0) for s, q in after.items()))) * d.fx_usd_aud
    for side, sym, qty in buys:
        submit(side, sym, qty, gross_aud)

    # ---- 5) 完成记录(「开始」看 last_s1_eval.txt,「完成」看这份) ----
    _write_json_atomic(d.marker_path.parent / "last_eval_result.json", {
        "date": today_tag, "mode": d.mode,
        "started_at": started_at.isoformat(), "completed_at": d.now_fn().isoformat(),
        "as_of": as_of.isoformat(), "selected": list(result.selected),
        "target_weights": dict(result.target_weights), "plan": summary["plan"],
        "submitted": summary["submitted"], "rejected": summary["rejected"],
        "skipped": summary["skipped"], "skip_reasons": summary.get("skip_reasons", []),
        "reject_rules": sorted(reject_rules),
    })
    return summary


def resolve_mode(mode_name: str, acc_trd_env: str, *, live_flag: str,
                 auth_ok: bool, auth_reasons: Sequence[str]) -> SystemMode:
    """模式解析(纯函数,失败关闭):
    PAPER 必须绑 SIMULATE 账户;MICRO_LIVE 必须绑 REAL 账户 + 实盘总开关=1 +
    预签授权文件有效。任何不合规直接抛错拒绝启动,绝不静默降级。"""
    m = (mode_name or "").upper()
    env = (acc_trd_env or "").upper()
    if m == "PAPER":
        if env != "SIMULATE":
            raise RuntimeError(f"PAPER 模式必须绑 SIMULATE 账户,实为 {env}(失败关闭)")
        return SystemMode.PAPER
    if m == "MICRO_LIVE":
        if env != "REAL":
            raise RuntimeError(f"MICRO_LIVE 必须绑 REAL 账户,实为 {env}(失败关闭)")
        if live_flag != "1":
            raise RuntimeError("实盘总开关(环境值)不为 1,MICRO_LIVE 拒绝启动")
        if not auth_ok:
            raise RuntimeError(f"预签授权无效: {list(auth_reasons)}")
        return SystemMode.MICRO_LIVE
    raise RuntimeError(f"未知或缺失的模式 {mode_name!r}(只认 PAPER/MICRO_LIVE)")




def make_deps(*, factory, read_client, trade_client, store, gateway, lease, kill_switch,
              mode: SystemMode, capital_usd: float, fee_model, **extra) -> LiveCycleDeps:
    """两条装配路径(影子盘/券商)共用的依赖包装配:汇率折算、标记路径、费用估计只在这里算一次。"""
    from backend.app.shadow.recorder import ShadowRecorder

    return LiveCycleDeps(
        read_client=read_client, trade_client=trade_client, store=store, gateway=gateway,
        shadow=ShadowRecorder(factory), lease=lease, kill_switch=kill_switch,
        cfg=load_s1_config(truth.strategy_config_path()),
        capital_usd=capital_usd, fx_usd_aud=truth.fx_usd_aud(),
        marker_path=truth.runtime_dir() / "last_s1_eval.txt",
        fee_estimate=lambda side, qty, px: fee_model.order_cost_usd(
            side=side, quantity=qty, price=px),
        slippage_bps=fee_model.slippage_bps, mode=mode.value, **extra)


def build_live_cycle(*, factory, kill_switch, **overrides) -> Callable[[], dict]:
    """按模式经 wiring 分发装配。模式无条目(DISABLED/HALTED/缺失/拼错)即失败关闭。

    overrides 只供测试注入假件(行情、时钟),生产不传。
    """
    m = truth.mode()
    build = wiring.resolve(m, "cycle")
    if build is None:
        raise RuntimeError(f"模式 {m.value} 不运行交易循环(失败关闭)")
    return build(factory=factory, kill_switch=kill_switch, **overrides)


def build_broker_cycle(*, factory, kill_switch) -> Callable[[], dict]:
    """券商路径真机装配(PAPER/MICRO_LIVE;SDK/账户/探针/授权缺任何一环都如实抛错拒绝启动)。"""
    import socket

    from backend.app.adapters.brokers.moomoo import build_real_opend_client
    from backend.app.adapters.brokers.moomoo_trade_bridge import (
        build_real_trading_client, build_simulate_trading_client,
    )
    from backend.app.backtest.fees import FeeModel
    from backend.app.execution.gates import validate_authorization
    from backend.app.execution.gateway import ExecutionGateway
    from backend.app.execution.lease import LeaseManager
    from backend.app.store.ledger_stamp import claim_ledger
    from backend.app.store.orders import OrderStore

    acc_id = os.environ.get("ALPHA_EXPECTED_ACC_ID", "")
    if not acc_id or "<" in acc_id:
        raise RuntimeError("ALPHA_EXPECTED_ACC_ID 未配置")
    firm = os.environ.get("MOOMOO_SECURITY_FIRM", "FUTUAU")

    read_client = build_real_opend_client()
    accs = {r["acc_id"]: r for r in read_client.get_acc_list()}
    if acc_id not in accs:
        raise RuntimeError(f"账户 {acc_id} 不在券商列表")

    auth_ok, auth_reasons = validate_authorization(
        os.environ.get("ALPHA_AUTHORIZATION_PATH", "runtime/LIVE_AUTHORIZATION.json"),
        policy_path="configs/trading_governor_policy.yaml",
        promotion_config_path="configs/strategy_promotion.yaml",
        now=datetime.now(timezone.utc))
    mode = resolve_mode(truth.mode().value, str(accs[acc_id].get("trd_env", "")),
                        live_flag=os.environ.get("LIVE_TRADING_ENABLED", "0"),
                        auth_ok=auth_ok, auth_reasons=auth_reasons)

    # 账本与运行目录必须属于本模式:影子盘/模拟盘的账不能被真单沿用(戳不符即拒绝装配)
    claim_ledger(factory, mode, truth.runtime_dir())
    store = OrderStore(factory)
    lease = LeaseManager(factory, holder_id=f"trading-worker@{socket.gethostname()}")
    if mode is SystemMode.MICRO_LIVE:
        trade_client = build_real_trading_client(acc_id=acc_id, security_firm=firm)
    else:
        trade_client = build_simulate_trading_client(acc_id=acc_id, security_firm=firm)
    gateway = ExecutionGateway(store=store, client=trade_client, lease=lease,
                               mode=mode,
                               kill_switch_check=kill_switch.active)
    recover = gateway.recover_in_flight()
    lease.acquire()   # 慢活(SDK 上下文+悬单恢复)全部完成后才拿租约,避免拿了就过期

    deps = make_deps(
        factory=factory, read_client=read_client, trade_client=trade_client, store=store,
        gateway=gateway, lease=lease, kill_switch=kill_switch, mode=mode,
        capital_usd=truth.capital_aud() * truth.contract_fx_aud_usd(),   # 契约保守汇率,资金上限只紧不松
        fee_model=FeeModel.from_yaml())
    if recover.get("adopted") or recover.get("submit_failed"):
        pass  # recover 结果已由网关落审计;此处不加工
    return lambda: run_live_cycle(deps)
