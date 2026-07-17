"""S2 超卖反弹(卫星仓)——纯函数实现,逐条对应 configs/strategies/s2_meanrev.yaml。

进场三条件+波幅地板(收盘判定,次日挂单);三出口先到先执行;
唯一允许市价单的场景 = 止损离场。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Mapping, Optional, Sequence

import yaml

from backend.app.strategies.bars import Bar, assert_ascending, closes, highs, lows, slice_until
from backend.app.strategies.indicators import atr, ibs, rsi_wilder, sma


def load_s2_config(path: str | Path = "configs/strategies/s2_meanrev.yaml") -> dict:
    cfg = yaml.safe_load(Path(path).read_text())
    if cfg.get("strategy_id") != "S2_OVERSOLD_REBOUND":
        raise ValueError(f"非 S2 配置: {cfg.get('strategy_id')}")
    return cfg


@dataclass(frozen=True)
class S2Entry:
    symbol: str
    limit_price: float          # 前收盘 * 0.995
    time_in_force: str          # DAY
    order_type: str             # LIMIT
    diagnostics: Mapping[str, float]


@dataclass(frozen=True)
class S2OpenTrade:
    symbol: str
    entry_price: float
    entry_day: date
    trading_days_held: int


@dataclass(frozen=True)
class S2Exit:
    symbol: str
    reason: str                 # TAKE_PROFIT_SMA5 / TIME_STOP / STOP_LOSS
    order_type: str             # LIMIT(获利/超时) / MARKET(仅止损)


def evaluate_s2_entries(
    bars_by_symbol: Mapping[str, Sequence[Bar]],
    cfg: dict,
    as_of: date,
    open_trades: Sequence[S2OpenTrade] = (),
) -> list[S2Entry]:
    entry = cfg["entry"]
    rsi_period = int(entry["rsi"]["period"])
    rsi_threshold = float(entry["rsi"]["threshold"])
    ibs_threshold = float(entry["ibs"]["threshold"])
    sma_period = 200  # trend_filter: close > SMA200
    vol_floor = 1.5 / 100.0  # ATR14 / close > 1.5%
    atr_period = 14
    max_open = int(cfg["concurrency"]["max_open_trades"])

    slots = max_open - len(open_trades)
    if slots <= 0:
        return []
    held = {t.symbol for t in open_trades}

    signals: list[S2Entry] = []
    for symbol in list(cfg["universe"]["core"]):
        if symbol in held:
            continue
        bars = slice_until(bars_by_symbol.get(symbol, ()), as_of)
        if not bars:
            continue
        assert_ascending(bars)
        c, h, l = closes(bars), highs(bars), lows(bars)
        sma200 = sma(c, sma_period)
        r = rsi_wilder(c, rsi_period)
        i = ibs(h[-1], l[-1], c[-1])
        a = atr(h, l, c, atr_period)
        if sma200 is None or r is None or i is None or a is None:
            continue
        conditions = {
            "close": c[-1],
            "sma200": sma200,
            "rsi2": r,
            "ibs": i,
            "atr_ratio": a / c[-1],
        }
        if (
            c[-1] > sma200
            and r < rsi_threshold
            and i < ibs_threshold
            and (a / c[-1]) > vol_floor
        ):
            signals.append(
                S2Entry(
                    symbol=symbol,
                    limit_price=round(c[-1] * 0.995, 2),
                    time_in_force="DAY",
                    order_type="LIMIT",
                    diagnostics=conditions,
                )
            )
        if len(signals) >= slots:
            break
    return signals


def evaluate_s2_exits(
    bars_by_symbol: Mapping[str, Sequence[Bar]],
    cfg: dict,
    as_of: date,
    open_trades: Sequence[S2OpenTrade],
) -> list[S2Exit]:
    stop_loss_pct = float(cfg["exit"]["stop_loss_pct"]) / 100.0
    time_stop = int(cfg["exit"]["time_stop_trading_days"])

    exits: list[S2Exit] = []
    for trade in open_trades:
        bars = slice_until(bars_by_symbol.get(trade.symbol, ()), as_of)
        if not bars:
            continue
        c = closes(bars)
        last = c[-1]
        # 先到先执行的判定顺序:止损(保命)> 超时 > 获利
        if last <= trade.entry_price * (1.0 - stop_loss_pct):
            exits.append(S2Exit(trade.symbol, "STOP_LOSS", "MARKET"))  # 唯一市价场景
            continue
        if trade.trading_days_held >= time_stop:
            exits.append(S2Exit(trade.symbol, "TIME_STOP", "LIMIT"))
            continue
        sma5 = sma(c, 5)
        if sma5 is not None and last > sma5:
            exits.append(S2Exit(trade.symbol, "TAKE_PROFIT_SMA5", "LIMIT"))
    return exits


def s2_enabled(cfg: dict, backtest_promo_passed: Optional[bool]) -> bool:
    """启用前提:自建回测达标(文献口径不算数)。未跑回测 = 不启用。"""
    if not cfg.get("enabled_pending_backtest", True):
        return True
    return backtest_promo_passed is True
