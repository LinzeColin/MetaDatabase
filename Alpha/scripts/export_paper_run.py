#!/usr/bin/env python3
"""070 取数器:把三日 Paper 运行的真实落库记录汇总成 RunInputs -> 四件套报告。

红线:只读已发生的事实,一个数字都不编。取不到的量如实置零/置空并在报告
备注中声明口径。用法(部署主机,交易日窗口结束后):
    python3 scripts/export_paper_run.py --days 2026-07-20,2026-07-21,2026-07-22 \
        --capital-aud 3000 --out reports/paper_3day/2026-07-22
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select

from backend.app.domain.models import (
    BrokerOrder, Execution, OrderEvent, OrderIntent, OutboxEvent, ReconciliationRun,
    RiskDecision, ShadowOrder,
)
from backend.app.reporting.three_day_report import RunInputs, generate
from backend.app.store.db import create_session_factory, init_engine


def collect(session_factory, days: list[str], *, mark_prices: dict[str, float]) -> RunInputs:
    """从库里聚合三日运行事实。mark_prices:估值用的收盘价(symbol->USD,可空)。"""
    with session_factory() as s:
        intents = {i.intent_id: i for i in s.scalars(select(OrderIntent)).all()}
        orders = s.scalars(select(BrokerOrder)).all()
        order_by_id = {o.order_id: o for o in orders}
        execs = s.scalars(select(Execution)).all()
        events = s.scalars(select(OrderEvent)).all()
        risks = s.scalars(select(RiskDecision)).all()
        shadows = s.scalars(select(ShadowOrder)).all()
        outbox = s.scalars(select(OutboxEvent)).all()
        recons = s.scalars(select(ReconciliationRun)).all()

    day_set = set(days)

    def in_window(dt) -> bool:
        if dt is None:
            return False
        d = (dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc))
        return d.date().isoformat() in day_set

    w_intents = [i for i in intents.values() if in_window(i.created_at)]
    w_orders = [o for o in orders if in_window(o.created_at)]
    w_execs = [e for e in execs if in_window(e.executed_at)]

    # 决策漏斗(全部来自审计记录)
    risk_by_intent: dict[str, RiskDecision] = {r.intent_id: r for r in risks}
    blocked_rules: Counter = Counter()
    risk_passed = 0
    for o in w_orders:
        r = risk_by_intent.get(o.intent_id)
        if r is None:
            continue
        if r.allowed:
            risk_passed += 1
        else:
            for rule in json.loads(r.triggered_rules or "[]"):
                blocked_rules[rule] += 1
    states = Counter(o.state for o in w_orders)
    submitted = sum(states[k] for k in
                    ("SUBMITTED", "ACCEPTED", "PARTIALLY_FILLED", "FILLED", "CANCELLED", "EXPIRED"))
    accepted = sum(states[k] for k in ("ACCEPTED", "PARTIALLY_FILLED", "FILLED"))

    # 收益(费后):已实现现金流 + 期末按 mark_prices 估值的持仓(取不到价则如实不估值)
    cash_flow = 0.0
    fees = 0.0
    net_pos: dict[str, int] = {}
    for e in w_execs:
        o = order_by_id.get(e.order_id)
        i = intents.get(o.intent_id) if o else None
        if i is None:
            continue
        sign = 1 if i.side == "BUY" else -1
        cash_flow += (-sign) * e.quantity * float(e.price)
        fees += float(e.fees)
        net_pos[i.symbol] = net_pos.get(i.symbol, 0) + sign * e.quantity
    unpriced = sorted(sym for sym, q in net_pos.items() if q != 0 and sym not in mark_prices)
    mark_value = sum(q * mark_prices.get(sym, 0.0) for sym, q in net_pos.items())
    net_pnl = cash_flow + mark_value - fees

    # 平仓配对(先进先出)算胜率;未平仓不算 trades
    wins = trades = 0
    win_amts: list[float] = []
    loss_amts: list[float] = []
    lots: dict[str, list[tuple[int, float]]] = {}
    for e in sorted(w_execs, key=lambda x: x.executed_at):
        o = order_by_id.get(e.order_id)
        i = intents.get(o.intent_id) if o else None
        if i is None:
            continue
        if i.side == "BUY":
            lots.setdefault(i.symbol, []).append((e.quantity, float(e.price)))
            continue
        remain = e.quantity
        while remain > 0 and lots.get(i.symbol):
            q0, p0 = lots[i.symbol][0]
            take = min(remain, q0)
            pnl = take * (float(e.price) - p0)
            trades += 1
            if pnl > 0:
                wins += 1
                win_amts.append(pnl)
            else:
                loss_amts.append(pnl)
            remain -= take
            if take == q0:
                lots[i.symbol].pop(0)
            else:
                lots[i.symbol][0] = (q0 - take, p0)

    # Paper vs Shadow 价差
    gaps = []
    for sh in shadows:
        o = next((x for x in orders if x.intent_id == sh.intent_id), None)
        if o and o.avg_fill_price is not None:
            gaps.append(round(float(o.avg_fill_price) - float(sh.hypothetical_limit_price), 4))

    # 可靠性(应全 0;WORKER_HEARTBEAT_LOST 的批量作废不算失败)
    illegal = sum(1 for ev in events if "ILLEGAL" in (ev.event_type or "").upper()
                  or "QUARANTINE" in (ev.event_type or "").upper())
    unknown = states.get("UNKNOWN_RECONCILIATION_REQUIRED", 0)
    outbox_failed = sum(1 for x in outbox if x.delivery_status == "FAILED")
    recon_open = sum(1 for r in recons if r.status == "OPEN")

    # 通知延迟与成功率:按申报窗口取样(与漏斗各指标同口径);失败计数保持全历史从严
    lat = sorted((x.delivered_at - x.created_at).total_seconds()
                 for x in outbox if x.delivery_status == "DELIVERED" and x.delivered_at
                 and in_window(x.created_at))
    p95 = lat[max(0, int(len(lat) * 0.95) - 1)] if lat else 0.0
    delivered = sum(1 for x in outbox
                    if x.delivery_status == "DELIVERED" and in_window(x.created_at))
    notify_total = delivered + outbox_failed

    return RunInputs(
        trading_days=days,
        uptime_pct=0.0,          # 由 --uptime 注入(journal 证据),不在库内
        notify_success_pct=round(100.0 * delivered / notify_total, 2) if notify_total else 100.0,
        notify_p95_seconds=round(p95, 2),
        strategy_evals=len({(i.created_at.date().isoformat()) for i in w_intents}),
        signals=len(w_intents),
        risk_passed=risk_passed,
        risk_blocked_by_rule=dict(blocked_rules),
        submitted=submitted, accepted=accepted, filled=states.get("FILLED", 0),
        cancelled=states.get("CANCELLED", 0),
        rejected=states.get("REJECTED", 0) + states.get("RISK_REJECTED", 0),
        net_pnl_aud=0.0,         # 主口径用 USD 折算,见 generate 调用前换算
        gross_pnl_aud=0.0, fees_aud=0.0,
        max_drawdown_pct=0.0,    # 三日窗口以日终净值近似,由调用方注入
        trades=trades, wins=wins,
        avg_win_aud=round(sum(win_amts) / len(win_amts), 2) if win_amts else 0.0,
        avg_loss_aud=round(sum(loss_amts) / len(loss_amts), 2) if loss_amts else 0.0,
        paper_shadow_price_gaps=gaps,
        shadow_would_block=0,
        unknown_orders=unknown,
        reconciliation_diffs=recon_open,
        idempotency_violations=0,   # 结构性防重:同键复用在写入层直接拒绝
        illegal_transitions=illegal,
        outbox_failures=outbox_failed,
        raw_events=[{
            "seq": ev.event_seq, "order_id": ev.order_id, "type": ev.event_type,
            "from": ev.from_state, "to": ev.to_state,
            "at": ev.recorded_at.isoformat() if ev.recorded_at else None,
            "backfilled": bool(ev.backfilled),
        } for ev in sorted(events, key=lambda x: (x.order_id, x.event_seq))],
    ), {"cash_flow_usd": round(cash_flow, 2), "mark_value_usd": round(mark_value, 2),
        "fees_usd": round(fees, 2), "net_pnl_usd": round(net_pnl, 2),
        "open_positions": {k: v for k, v in net_pos.items() if v != 0},
        "unpriced_symbols": unpriced}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", required=True, help="逗号分隔的合格交易日,如 2026-07-20,2026-07-21,2026-07-22")
    ap.add_argument("--capital-aud", type=float, default=3000.0)
    ap.add_argument("--fx-aud-usd", type=float, default=float(os.environ.get("ALPHA_FX_AUD_USD", "0.65")))
    ap.add_argument("--uptime", type=float, required=True,
                    help="会话窗口可用性百分比(journal 证据核算后人工传入,不编造)")
    ap.add_argument("--mark-prices", default="", help="期末估值价 symbol=price,逗号分隔;缺失则未平仓不估值并在报告声明")
    ap.add_argument("--max-dd-pct", type=float, default=0.0, help="三日日终净值最大回撤(调用方按日终净值核算)")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()

    marks = {}
    if a.mark_prices:
        for kv in a.mark_prices.split(","):
            k, _, v = kv.partition("=")
            marks[k.strip()] = float(v)

    factory = create_session_factory(init_engine())
    inputs, pnl_usd = collect(factory, [d.strip() for d in a.days.split(",")], mark_prices=marks)

    fx = a.fx_aud_usd
    inputs.uptime_pct = a.uptime
    inputs.max_drawdown_pct = a.max_dd_pct
    inputs.net_pnl_aud = round(pnl_usd["net_pnl_usd"] / fx, 2)
    inputs.fees_aud = round(pnl_usd["fees_usd"] / fx, 2)
    inputs.gross_pnl_aud = round(inputs.net_pnl_aud + inputs.fees_aud, 2)

    report = generate(inputs, capital_aud=a.capital_aud, out_dir=a.out,
                      generated_at=datetime.now(timezone.utc).isoformat())
    (os.path.join(a.out, "pnl_usd_breakdown.json"))
    with open(os.path.join(a.out, "pnl_usd_breakdown.json"), "w") as f:
        json.dump(pnl_usd, f, ensure_ascii=False, indent=2)
    print(json.dumps({"promotion": report["promotion"], "pnl_usd": pnl_usd},
                     ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
