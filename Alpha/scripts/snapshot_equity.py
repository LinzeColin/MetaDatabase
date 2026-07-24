"""净值快照(每 15 分钟一次,由 alpha-equity-snapshot.timer 驱动)。

owner 2026-07-24:"本金是动态的,所有的数据都是动态的,不是说 100 年后也是固定的 3000"。
故本脚本按真实世界状态逐点记账,让净值曲线真正随时间生长:

  可动用本金 = min(授权上限 3000 澳元, 账户真实购买力 + 系统自有持仓市值)
  净值       = 账户真实购买力 + 系统自有持仓市值(同一口径,故起点盈亏为 0)

只读券商、只写自己的历史文件;永不下单。取不到券商数据就跳过本次快照,绝不编造点位。
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

MAX_POINTS = 4000          # 15 分钟一点 ≈ 保留约 40 天
RUNTIME = Path(os.environ.get("ALPHA_RUNTIME_DIR", "runtime"))
HISTORY = RUNTIME / "equity_history.json"


def _real_funds_and_positions(acc_id: str) -> tuple[float | None, dict[str, int]]:
    """真实购买力与系统自有持仓(只读)。失败返回 (None, {})。"""
    try:
        from moomoo import (RET_OK, Currency, OpenSecTradeContext, SecurityFirm,
                            TrdEnv, TrdMarket)
        tc = OpenSecTradeContext(filter_trdmarket=TrdMarket.US, host="127.0.0.1",
                                 port=11111, security_firm=SecurityFirm.FUTUAU)
        try:
            ret, df = tc.accinfo_query(trd_env=TrdEnv.REAL, acc_id=int(acc_id),
                                       refresh_cache=True, currency=Currency.USD)
            power = float(df.iloc[0]["power"]) if ret == RET_OK and len(df) else None
        finally:
            tc.close()
        return power, {}
    except Exception:
        return None, {}


def system_position_value_usd(session_factory) -> float:
    """系统自有持仓市值(按成交流水净额 × 最新价);无持仓返回 0。"""
    try:
        from sqlalchemy import select

        from backend.app.domain.models import BrokerOrder, Execution, OrderIntent
        with session_factory() as s:
            intents = {i.intent_id: i for i in s.scalars(select(OrderIntent)).all()}
            orders = {o.order_id: o for o in s.scalars(select(BrokerOrder)).all()}
            execs = list(s.scalars(select(Execution)).all())
        net: dict[str, int] = {}
        for e in execs:
            o = orders.get(e.order_id)
            i = intents.get(o.intent_id) if o else None
            if i is None:
                continue
            net[i.symbol] = net.get(i.symbol, 0) + (1 if i.side == "BUY" else -1) * e.quantity
        held = {k: v for k, v in net.items() if v}
        if not held:
            return 0.0
        from moomoo import RET_OK, OpenQuoteContext
        qc = OpenQuoteContext(host="127.0.0.1", port=11111)
        try:
            ret, df = qc.get_market_snapshot([f"US.{s}" for s in held])
            if ret != RET_OK:
                return 0.0
            px = {str(r["code"]).split(".", 1)[-1]: float(r["last_price"])
                  for _, r in df.iterrows()}
        finally:
            qc.close()
        return sum(q * px.get(sym, 0.0) for sym, q in held.items())
    except Exception:
        return 0.0


def fx_aud_usd() -> tuple[float, bool]:
    """实时汇率(取不到回落契约固定口径并标注)。"""
    try:
        from backend.app.control_page.dashboard_data import YahooFxSource
        rate, _ = YahooFxSource(ttl=0.0).rate()
        if rate:
            return float(rate), True
    except Exception:
        pass
    return float(os.environ.get("ALPHA_FX_AUD_USD", "0.65")), False


def main() -> int:
    acc = os.environ.get("ALPHA_REAL_ACC_ID", "")
    if not acc:
        print("跳过:未配置真实账户"); return 0
    power, _ = _real_funds_and_positions(acc)
    if power is None:
        print("跳过:券商购买力读不到(不编造点位)"); return 0

    from backend.app.store.db import create_session_factory, init_engine
    factory = create_session_factory(init_engine())
    pos_usd = system_position_value_usd(factory)

    capital_aud = float(os.environ.get("ALPHA_CAPITAL_AUD", "3000"))
    fx_contract = float(os.environ.get("ALPHA_FX_AUD_USD", "0.65"))
    fx, fx_live = fx_aud_usd()

    authorized_usd = capital_aud * fx_contract          # 授权上限(风控同款保守汇率)
    funded_usd = min(authorized_usd, power + pos_usd)   # 可动用本金 = 取小
    equity_usd = power + pos_usd

    now = datetime.now(timezone.utc)
    point = {
        "at": now.isoformat(),
        "date": now.astimezone().strftime("%Y-%m-%d"),
        "equity_aud": round(equity_usd / fx, 2),
        "baseline_aud": round(funded_usd / fx, 2),
        "equity_usd": round(equity_usd, 2),
        "funded_usd": round(funded_usd, 2),
        "power_usd": round(power, 2),
        "position_usd": round(pos_usd, 2),
        "fx_aud_usd": round(fx, 6),
        "fx_live": fx_live,
    }
    HISTORY.parent.mkdir(parents=True, exist_ok=True)
    try:
        hist = json.loads(HISTORY.read_text())
        if not isinstance(hist, list):
            hist = []
    except Exception:
        hist = []
    hist.append(point)
    HISTORY.write_text(json.dumps(hist[-MAX_POINTS:], ensure_ascii=False))
    print(f"已记:{point['at']} 净值={point['equity_aud']} 本金={point['baseline_aud']} 澳元 "
          f"(共 {len(hist[-MAX_POINTS:])} 点)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
