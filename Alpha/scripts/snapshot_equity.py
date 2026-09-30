"""净值快照(每 15 分钟一次,由 alpha-equity-snapshot.timer 驱动)。

让净值曲线随时间生长:每 15 分钟按真实世界状态记一个净值点。

  期初本金(基准)= 固定 3000 澳元,永不浮动(owner:"本金基准是期初本金 3000,不能搞错")
  已冻结本金:净值 = 冻结本金 + 系统自有现金流(含手续费)+ 系统自有持仓 × 最新价
             ——只由本系统成交推导(fold_own_executions),从不读任何券商余额(R4 隔离)
  未冻结本金(仅券商模式,尚未首笔成交):净值 = 券商真实购买力 + 自有持仓市值

行情源按模式经 wiring 取(影子盘 = Yahoo);无持仓时也探一次 SPY,顺带记录行情源健康
(facts/quote_feed.json,连续失败由健康判据告警)。持仓标的取不到价就不记这个点,绝不编造。
只写自己的历史文件;永不下单。
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

MAX_POINTS = 4000          # 15 分钟一点 ≈ 保留约 40 天
PROBE_SYMBOL = "SPY"       # 空仓时的行情探针


def fx_aud_usd() -> tuple[float, bool]:
    """实时汇率(取不到回落契约固定口径并标注)。"""
    from backend.app import truth
    try:
        from backend.app.control_page.dashboard_data import YahooFxSource
        rate, _ = YahooFxSource(ttl=0.0).rate()
        if rate:
            return float(rate), True
    except Exception:
        pass
    return truth.contract_fx_aud_usd(), False


def _record_feed(ok: bool, now: datetime, error: str) -> None:
    """行情源健康:成功清零并记 last_ok_at,失败累加 consecutive_failures。"""
    from backend.app import truth
    path = truth.facts_dir() / "quote_feed.json"
    try:
        feed = json.loads(path.read_text())
    except Exception:
        feed = {}
    if ok:
        feed.update(consecutive_failures=0, last_ok_at=now.isoformat(), last_error="")
    else:
        feed.update(consecutive_failures=int(feed.get("consecutive_failures", 0)) + 1,
                    last_error=error[:200])
    feed["at"] = now.isoformat()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(feed, ensure_ascii=False))


def main(*, quotes=None, fx: tuple[float, bool] | None = None,
         now: datetime | None = None) -> int:
    from backend.app import truth, wiring
    from backend.app.store.db import create_session_factory, init_engine
    from backend.app.store.orders import OrderStore

    now = now or datetime.now(timezone.utc)
    m = truth.mode()
    rt = truth.runtime_dir()
    factory = create_session_factory(init_engine())
    book = OrderStore(factory).own_book()
    held = sorted(book.net)

    if quotes is None:
        quotes_cls = wiring.resolve(m, "quotes")
        if quotes_cls is None:
            print(f"跳过:模式 {m.value} 不运行交易,无行情源"); return 0
        quotes = quotes_cls()
    probe = held or [PROBE_SYMBOL]
    try:
        snap = quotes.snapshots(probe) or {}
        err = ""
    except Exception as exc:
        snap, err = {}, f"{type(exc).__name__}: {exc}"
    missing = [s for s in probe if s not in snap]
    _record_feed(not missing, now, err or f"取不到 {missing}")
    if any(s in missing for s in held):
        print(f"跳过:持仓 {missing} 取不到价(不编造点位)"); return 0
    pos_usd = sum(q * float(snap[s]["price"]) for s, q in book.net.items())

    capital_aud = truth.capital_aud()
    authorized_usd = capital_aud * truth.contract_fx_aud_usd()   # 授权上限(风控同款保守汇率)
    fx_rate, fx_live = fx or fx_aud_usd()
    try:
        start_cap = float(json.loads((rt / "LIVE_START_CAPITAL.json").read_text())["start_capital_usd"])
    except Exception:
        start_cap = None
    if start_cap is not None:
        cash_usd = start_cap + book.cash_flow_usd
        equity_usd = cash_usd + pos_usd
        funded_usd = min(authorized_usd, start_cap)
        # 本金以澳元记账,只有交易盈亏过实时汇率(与看盘同口径;否则本金汇率往返会造出假盈亏)
        equity_aud = truth.equity_aud(capital_aud=capital_aud,
                                      trading_pnl_usd=equity_usd - start_cap, fx_aud_usd=fx_rate)
    else:
        funds_cls = wiring.resolve(m, "funds")
        if funds_cls is None:
            print("跳过:尚未冻结期初本金"); return 0
        power = funds_cls().power_usd()
        if power is None:
            print("跳过:券商购买力读不到(不编造点位)"); return 0
        cash_usd = power
        equity_usd = power + pos_usd
        funded_usd = min(authorized_usd, power + pos_usd)
        equity_aud = equity_usd / fx_rate

    point = {
        "at": now.isoformat(),
        "date": now.astimezone().strftime("%Y-%m-%d"),
        "equity_aud": round(equity_aud, 2),
        "baseline_aud": round(capital_aud, 2),   # 期初本金固定 3000,不随可用资金浮动
        "equity_usd": round(equity_usd, 2),
        "funded_usd": round(funded_usd, 2),
        "cash_usd": round(cash_usd, 2),
        "position_usd": round(pos_usd, 2),
        "fx_aud_usd": round(fx_rate, 6),
        "fx_live": fx_live,
    }
    history = rt / "equity_history.json"
    history.parent.mkdir(parents=True, exist_ok=True)
    try:
        hist = json.loads(history.read_text())
        if not isinstance(hist, list):
            hist = []
    except Exception:
        hist = []
    hist.append(point)
    history.write_text(json.dumps(hist[-MAX_POINTS:], ensure_ascii=False))
    print(f"已记:{point['at']} 净值={point['equity_aud']} 本金={point['baseline_aud']} 澳元 "
          f"(共 {len(hist[-MAX_POINTS:])} 点)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
