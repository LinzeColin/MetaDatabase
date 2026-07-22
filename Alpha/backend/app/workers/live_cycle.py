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
from typing import Callable, Optional, Sequence
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
    single_order_cap_usd: Optional[float] = None,
) -> list[tuple[str, str, int]]:
    """目标权重 × 资金上限 -> 整股目标 -> 差分 -> 切片后的 (side, symbol, qty) 列表。

    卖单在前(先腾现金);小于阈值(占资金 %)的差分忽略;买不起 1 股即跳过。
    单笔名义超过 single_order_cap_usd 时切成多笔(实机 2026-07-21:QQQ 一笔 2172 澳元
    撞上 1800 澳元单笔硬上限被风控拒——法条不动,订单迁就法条)。
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


def _ensure_lease(lease) -> None:
    """续约;过期则尝试接管(同持有人/无人持有即成功)。他人有效持有仍抛错失败关闭。

    覆盖两类真实场景:杀开关 HALTED 期间数小时不续约;装配期慢活(SDK 建上下文+
    悬单恢复)吃掉整个 TTL——实机 2026-07-19 均已发生过。
    """
    try:
        lease.renew()
    except Exception:
        lease.acquire()


def run_live_cycle(d: LiveCycleDeps) -> dict:
    """单拍:回灌券商事实 -> (窗口内)评估下单 -> 摘要。异常上抛失败关闭。"""
    _ensure_lease(d.lease)
    now_utc = d.now_fn()
    now_et = now_utc.astimezone(ET)
    summary: dict = {"mode": "PAPER", "et": now_et.strftime("%a %H:%M"),
                     "backfilled": 0, "fills": 0, "evaluated": False,
                     "submitted": 0, "rejected": 0, "skipped": 0}

    # ---- 1) 回灌券商事实(状态只前进;成交按成交号幂等) ----
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
    # 成交回灌两条路:REAL 走成交明细;SIMULATE 环境无成交明细接口(实机 2026-07-19
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

    # ---- 2) 评估窗口判定(每交易日至多一次;标记先落盘) ----
    # 补评估:一次性文件写明日期(工程缺陷误伤当日决策后的窗口内补救,用后即焚,
    # 事故与补救均入报告)。正常节拍仍是周二;补评估不改变周频纪律本身。
    today_tag = now_et.date().isoformat()
    makeup = d.marker_path.parent / "makeup_eval.txt"
    makeup_today = makeup.exists() and makeup.read_text().strip() == today_tag
    minute = now_et.hour * 60 + now_et.minute
    in_window_any_day = (9 * 60 + 60) <= minute <= (9 * 60 + 120)
    trigger = in_eval_window(now_et) or (makeup_today and in_window_any_day
                                         and now_et.weekday() < 5)
    already = d.marker_path.exists() and d.marker_path.read_text().strip() == today_tag
    if not trigger or already:
        return summary
    if makeup_today:
        makeup.unlink(missing_ok=True)

    d.marker_path.parent.mkdir(parents=True, exist_ok=True)
    d.marker_path.write_text(today_tag)   # 先落标记:崩溃重启宁可错过,不重复下单
    summary["evaluated"] = True

    universe = list(d.cfg["universe"])
    snapshot = d.read_client.get_snapshot(universe)
    prices = {s: v["price"] for s, v in snapshot.items() if v.get("price")}
    # 鲜度按「所交易标的自己」判(实机 2026-07-21:货币基金 BIL 天然低频报价,
    # 用全池最陈旧年龄一票否决了 GLD/QQQ——误伤;冷门不参与交易就不该连坐)
    age_by_sym = {s: quote_age_seconds(v.get("update_time", ""), now_utc)
                  for s, v in snapshot.items()}

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

    # 单笔上限 = 风控单笔红线(3000 AUD × 60%)换算成 USD,再留 3% 价格滑动余量
    cap_usd = 3000.0 * 0.60 * 0.97 / float(d.fx_usd_aud)
    plan = plan_rebalance(dict(result.target_weights), positions, prices,
                          capital_usd=d.capital_usd,
                          threshold_pct=float(d.cfg.get("rebalance_threshold_pct", 5)),
                          single_order_cap_usd=cap_usd)
    summary["plan"] = [f"{s} {sym}x{q}" for s, sym, q in plan]

    part_seen: dict[tuple, int] = {}
    reserved_aud = Decimal("0")   # 本轮已发买单占用的敞口(逐笔累加给风控看)
    for side, sym, qty in plan:
        px = prices[sym]
        limit = round(px * (1.001 if side == "BUY" else 0.999), 2)
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
                    summary.setdefault("shadow_errors", []).append(
                        f"{sym}:{type(sexc).__name__}")
        except Exception as exc:  # 单笔被闸(幂等已用/频控/租约)不拖垮整拍:如实计数
            summary["skipped"] += 1
            summary.setdefault("skip_reasons", []).append(f"{sym}:{type(exc).__name__}")
    return summary


def resolve_mode(mode_name: str, acc_trd_env: str, *, live_flag: str,
                 auth_ok: bool, auth_reasons: Sequence[str]) -> SystemMode:
    """模式解析(纯函数,失败关闭):
    PAPER 必须绑 SIMULATE 账户;MICRO_LIVE 必须绑 REAL 账户 + 实盘总开关=1 +
    预签授权文件有效。任何不合规直接抛错拒绝启动,绝不静默降级。"""
    m = (mode_name or "PAPER").upper()
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
    raise RuntimeError(f"未知模式 {mode_name}(只认 PAPER/MICRO_LIVE)")


def build_live_cycle(*, factory, kill_switch) -> Callable[[], dict]:
    """真机装配(部署主机;SDK/账户/探针/授权缺任何一环都如实抛错拒绝启动)。"""
    import socket

    from backend.app.adapters.brokers.moomoo import build_real_opend_client
    from backend.app.adapters.brokers.moomoo_trade_bridge import (
        build_real_trading_client, build_simulate_trading_client,
    )
    from backend.app.backtest.fees import FeeModel
    from backend.app.execution.gates import validate_authorization
    from backend.app.execution.gateway import ExecutionGateway
    from backend.app.execution.lease import LeaseManager
    from backend.app.shadow.recorder import ShadowRecorder
    from backend.app.store.orders import OrderStore

    acc_id = os.environ.get("ALPHA_EXPECTED_ACC_ID", "")
    if not acc_id or "<" in acc_id:
        raise RuntimeError("ALPHA_EXPECTED_ACC_ID 未配置")
    firm = os.environ.get("MOOMOO_SECURITY_FIRM", "FUTUAU")
    mode_name = os.environ.get("ALPHA_MODE", "PAPER")

    read_client = build_real_opend_client()
    accs = {r["acc_id"]: r for r in read_client.get_acc_list()}
    if acc_id not in accs:
        raise RuntimeError(f"账户 {acc_id} 不在券商列表")

    auth_ok, auth_reasons = validate_authorization(
        os.environ.get("ALPHA_AUTHORIZATION_PATH", "runtime/LIVE_AUTHORIZATION.json"),
        policy_path="configs/trading_governor_policy.yaml",
        promotion_config_path="configs/strategy_promotion.yaml",
        now=datetime.now(timezone.utc))
    mode = resolve_mode(mode_name, str(accs[acc_id].get("trd_env", "")),
                        live_flag=os.environ.get("LIVE_TRADING_ENABLED", "0"),
                        auth_ok=auth_ok, auth_reasons=auth_reasons)

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
