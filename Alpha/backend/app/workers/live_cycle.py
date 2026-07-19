"""070 实盘交易循环:行情 -> 策略(冠军配置)-> 组合差分 -> 风控 -> 网关(PAPER) -> 影子。

装配约束:
- 模式锁 PAPER(网关映射 SIMULATE 环境;REAL 结构性走不通);
- 启动即断言绑定账户在券商侧确为 SIMULATE,否则拒绝启动(失败关闭);
- 券商事实回灌走轮询:订单状态只允许「前进」,成交按券商成交号幂等入账一次;
- 评估节拍:冠军口径 = 周二开盘后 30-90 分钟窗口,每交易日至多评估一次,
  标记先落盘再下单(崩溃重启宁可错过当日,不重复下单);
- 任何异常向上抛,由 TradingWorker 失败关闭 + systemd 重启走 recover_in_flight。
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Callable, Optional
from zoneinfo import ZoneInfo

from backend.app.adapters.brokers.base import SystemMode
from backend.app.domain.state_machine import OrderState
from backend.app.risk.engine import RiskContext
from backend.app.strategies.bars import Bar
from backend.app.strategies.s1_momentum import evaluate_s1, load_s1_config

ET = ZoneInfo("America/New_York")

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


def plan_rebalance(
    target_weights: dict[str, float],
    positions: dict[str, int],
    prices: dict[str, float],
    *,
    capital_usd: float,
    threshold_pct: float,
) -> list[tuple[str, str, int]]:
    """目标权重 × 资金上限 -> 整股目标 -> 与现持仓差分 -> (side, symbol, qty) 列表。

    卖单在前(先腾现金);小于阈值(占资金 %)的差分忽略;买不起 1 股即跳过。
    """
    orders: list[tuple[str, str, int]] = []
    threshold_usd = capital_usd * threshold_pct / 100.0
    targets: dict[str, int] = {}
    for sym, w in target_weights.items():
        p = prices.get(sym)
        if p is None or p <= 0 or w <= 0:
            targets[sym] = 0
            continue
        targets[sym] = int(capital_usd * w // p)
    for sym in sorted(set(positions) | set(targets)):
        p = prices.get(sym)
        if p is None or p <= 0:
            continue
        delta = targets.get(sym, 0) - positions.get(sym, 0)
        if delta == 0 or abs(delta) * p < threshold_usd:
            continue
        orders.append(("SELL" if delta < 0 else "BUY", sym, abs(delta)))
    orders.sort(key=lambda o: 0 if o[0] == "SELL" else 1)
    return orders


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
    """依赖包(真机由 build_live_cycle 装配;测试可注入假件)。"""
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
    now_fn: Callable[[], datetime] = lambda: datetime.now(timezone.utc)


def run_live_cycle(d: LiveCycleDeps) -> dict:
    """单拍:回灌券商事实 -> (窗口内)评估下单 -> 摘要。异常上抛失败关闭。"""
    d.lease.renew()
    now_utc = d.now_fn()
    now_et = now_utc.astimezone(ET)
    summary: dict = {"mode": "PAPER", "et": now_et.strftime("%a %H:%M"),
                     "backfilled": 0, "fills": 0, "evaluated": False,
                     "submitted": 0, "rejected": 0, "skipped": 0}

    # ---- 1) 回灌券商事实(状态只前进;成交按成交号幂等) ----
    orders = d.trade_client.poll_orders()
    remark_by_broker_id: dict[str, str] = {}
    for row in orders:
        remark = row.get("remark", "")
        if not remark.startswith("S1-"):
            continue  # 非本系统单(如人工在 App 模拟盘手点)不回灌,对账器另管
        remark_by_broker_id[row["broker_order_id"]] = remark
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
    for deal in d.trade_client.poll_deals():
        exec_id = deal.get("broker_execution_id", "")
        if not exec_id or d.store.execution_exists(exec_id):
            continue
        remark = remark_by_broker_id.get(deal.get("broker_order_id", ""))
        if remark is None:
            continue
        d.gateway.on_fill(idempotency_key=remark, quantity=int(deal["quantity"]),
                          price=Decimal(str(deal["price"])),
                          broker_execution_id=exec_id)
        summary["fills"] += 1

    # ---- 2) 评估窗口判定(每交易日至多一次;标记先落盘) ----
    today_tag = now_et.date().isoformat()
    already = d.marker_path.exists() and d.marker_path.read_text().strip() == today_tag
    if not in_eval_window(now_et) or already:
        return summary

    d.marker_path.parent.mkdir(parents=True, exist_ok=True)
    d.marker_path.write_text(today_tag)   # 先落标记:崩溃重启宁可错过,不重复下单
    summary["evaluated"] = True

    universe = list(d.cfg["universe"])
    snapshot = d.read_client.get_snapshot(universe)
    prices = {s: v["price"] for s, v in snapshot.items() if v.get("price")}
    ages = [quote_age_seconds(v.get("update_time", ""), now_utc) for v in snapshot.values()]
    known_ages = [a for a in ages if a is not None]
    age = max(known_ages) if known_ages and len(known_ages) == len(ages) else None

    end = now_et.date().isoformat()
    start = date.fromordinal(now_et.date().toordinal() - 450).isoformat()
    bars_by_symbol = {}
    for sym in universe:
        rows = d.read_client.get_daily_bars(sym, start, end)
        bars_by_symbol[sym] = [
            Bar(day=date.fromisoformat(r["day"]), open=r["open"], high=r["high"],
                low=r["low"], close=r["close"])
            for r in rows if r.get("day")
        ]
    result = evaluate_s1(bars_by_symbol, d.cfg, now_et.date())

    acc_id = os.environ.get("ALPHA_EXPECTED_ACC_ID", "")
    positions = {p["symbol"]: int(p["quantity"])
                 for p in d.read_client.get_positions(acc_id)}
    gross_usd = sum(q * prices.get(s, 0.0) for s, q in positions.items())
    gross_aud = Decimal(str(gross_usd)) * d.fx_usd_aud

    plan = plan_rebalance(dict(result.target_weights), positions, prices,
                          capital_usd=d.capital_usd,
                          threshold_pct=float(d.cfg.get("rebalance_threshold_pct", 5)))
    summary["plan"] = [f"{s} {sym}x{q}" for s, sym, q in plan]

    for side, sym, qty in plan:
        px = prices[sym]
        limit = round(px * (1.001 if side == "BUY" else 0.999), 2)
        key = f"S1-{today_tag}-{sym}-{side}-{qty}"
        ctx = RiskContext(
            side=side, symbol=sym, market="US_ETF", quantity=qty,
            price_usd=Decimal(str(limit)), fx_usd_aud=d.fx_usd_aud, now=now_utc,
            current_gross_exposure_aud=gross_aud,
            quote_age_seconds=age,
            kill_switch_active=d.kill_switch.active(),
            reconciliation_open=d.store.halt_new_orders(),
            jurisdiction_verdict=d.store.latest_jurisdiction_verdict() or "DENY",
        )
        try:
            order_id = d.gateway.submit_intent(
                idempotency_key=key, symbol=sym, side=side, quantity=qty,
                currency="USD", strategy_source=str(d.cfg.get("strategy_id", "S1")),
                order_type="LIMIT", limit_price=Decimal(str(limit)), risk_ctx=ctx)
            state = d.store.get_state(order_id)
            if state is OrderState.RISK_REJECTED:
                summary["rejected"] += 1
            else:
                summary["submitted"] += 1
                d.shadow.record_decision(
                    intent_id=order_id,
                    hypothetical_limit_price=Decimal(str(limit)),
                    estimated_fees=Decimal(str(round(d.fee_estimate(side, qty, limit), 4))),
                    rationale={"as_of": today_tag, "side": side, "symbol": sym, "qty": qty})
        except Exception as exc:  # 单笔被闸(幂等已用/频控/租约)不拖垮整拍:如实计数
            summary["skipped"] += 1
            summary.setdefault("skip_reasons", []).append(f"{sym}:{type(exc).__name__}")
    return summary


def build_live_cycle(*, factory, kill_switch) -> Callable[[], dict]:
    """真机装配(部署主机;SDK/账户/探针缺任何一环都如实抛错拒绝启动)。"""
    import socket

    from backend.app.adapters.brokers.moomoo import build_real_opend_client
    from backend.app.adapters.brokers.moomoo_trade_bridge import build_simulate_trading_client
    from backend.app.backtest.fees import FeeModel
    from backend.app.execution.gateway import ExecutionGateway
    from backend.app.execution.lease import LeaseManager
    from backend.app.shadow.recorder import ShadowRecorder
    from backend.app.store.orders import OrderStore

    acc_id = os.environ.get("ALPHA_EXPECTED_ACC_ID", "")
    if not acc_id or "<" in acc_id:
        raise RuntimeError("ALPHA_EXPECTED_ACC_ID 未配置")
    firm = os.environ.get("MOOMOO_SECURITY_FIRM", "FUTUAU")

    read_client = build_real_opend_client()
    accs = {r["acc_id"]: r for r in read_client.get_acc_list()}
    if acc_id not in accs:
        raise RuntimeError(f"账户 {acc_id} 不在券商列表")
    if str(accs[acc_id].get("trd_env", "")).upper() != "SIMULATE":
        raise RuntimeError(f"账户 {acc_id} 非 SIMULATE 环境,070 拒绝启动(失败关闭)")

    store = OrderStore(factory)
    lease = LeaseManager(factory, holder_id=f"trading-worker@{socket.gethostname()}")
    lease.acquire()
    trade_client = build_simulate_trading_client(acc_id=acc_id, security_firm=firm)
    gateway = ExecutionGateway(store=store, client=trade_client, lease=lease,
                               mode=SystemMode.PAPER,
                               kill_switch_check=kill_switch.active)
    recover = gateway.recover_in_flight()

    fee_model = FeeModel.from_yaml()
    fx_aud_usd = float(os.environ.get("ALPHA_FX_AUD_USD", "0.65"))  # 保守汇率,资金上限只紧不松
    capital_aud = float(os.environ.get("ALPHA_CAPITAL_AUD", "3000"))
    deps = LiveCycleDeps(
        read_client=read_client, trade_client=trade_client, store=store,
        gateway=gateway, shadow=ShadowRecorder(factory), lease=lease,
        kill_switch=kill_switch, cfg=load_s1_config("configs/strategies/s1_gold_blend.yaml"),
        capital_usd=capital_aud * fx_aud_usd,
        fx_usd_aud=Decimal(str(round(1.0 / fx_aud_usd, 6))),
        marker_path=Path(os.environ.get("ALPHA_RUNTIME_DIR", "runtime")) / "last_s1_eval.txt",
        fee_estimate=lambda side, qty, px: fee_model.order_cost_usd(
            side=side, quantity=qty, price=px),
    )
    if recover.get("adopted") or recover.get("submit_failed"):
        pass  # recover 结果已由网关落审计;此处不加工
    return lambda: run_live_cycle(deps)
