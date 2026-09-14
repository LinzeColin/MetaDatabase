"""S2 超卖反弹。

来源：``Alpha/backend/app/strategies/s2_meanrev.py``；参数逐值来自
``Alpha/configs/strategies/s2_meanrev.yaml``。本副本不读取 Alpha 的 YAML。
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import date
import re
from typing import Mapping, Optional, Sequence

from .bars import assert_ascending, closes, highs, lows, slice_until
from .indicators import atr, ibs, rsi_wilder, sma
from ..marketdata.models import Bar


DEFAULT_S2_CONFIG: dict[str, object] = {
    "strategy_id": "S2_OVERSOLD_REBOUND",
    "version": "1.0.0",
    "enabled_pending_backtest": True,
    "universe": {"core": ["SPY", "QQQ"]},
    "entry": {
        "trend_filter": "close > SMA200",
        "rsi": {"period": 2, "threshold": 8, "smoothing": "wilder"},
        "ibs": {"threshold": 0.2},
        "volatility_floor": "ATR14 / close > 1.5%",
        "order": {"type": "LIMIT", "price": "prev_close * 0.995", "time_in_force": "DAY"},
    },
    "exit": {"take_profit": "close > SMA5", "time_stop_trading_days": 10, "stop_loss_pct": 4.0},
    "concurrency": {"max_open_trades": 2},
}


def default_s2_config(overrides: Mapping[str, object] | None = None) -> dict[str, object]:
    """返回 Alpha 参数的可覆盖副本。"""
    config = deepcopy(DEFAULT_S2_CONFIG)
    if overrides:
        for key, value in overrides.items():
            if isinstance(value, Mapping) and isinstance(config.get(key), dict):
                config[key].update(value)  # type: ignore[index,union-attr]
            else:
                config[key] = value
    return config


def volatility_floor_ratio(entry_config: Mapping[str, object]) -> float:
    """优先读取训练窗落盘的精确百分比，兼容既有可读的百分比文本。"""
    explicit = entry_config.get("volatility_floor_pct")
    if isinstance(explicit, (int, float)):
        return float(explicit) / 100.0
    match = re.search(r"([0-9]+(?:\.[0-9]+)?)%", str(entry_config.get("volatility_floor", "")))
    return float(match.group(1)) / 100.0 if match else 0.015


@dataclass(frozen=True)
class S2Entry:
    symbol: str
    limit_price: float
    time_in_force: str
    order_type: str
    diagnostics: Mapping[str, float]


@dataclass(frozen=True)
class S2OpenTrade:
    symbol: str
    entry_price: float
    entry_day: date
    trading_days_held: int


def evaluate_s2_entries(
    bars_by_symbol: Mapping[str, Sequence[Bar]],
    config: Mapping[str, object],
    as_of: date,
    open_trades: Sequence[S2OpenTrade] = (),
) -> list[S2Entry]:
    entry_config = config["entry"]  # type: ignore[index]
    rsi_period = int(entry_config["rsi"]["period"])  # type: ignore[index]
    rsi_threshold = float(entry_config["rsi"]["threshold"])  # type: ignore[index]
    ibs_threshold = float(entry_config["ibs"]["threshold"])  # type: ignore[index]
    volatility_floor = volatility_floor_ratio(entry_config)
    max_open = int(config["concurrency"]["max_open_trades"])  # type: ignore[index]
    slots = max_open - len(open_trades)
    if slots <= 0:
        return []
    held = {trade.symbol for trade in open_trades}
    signals: list[S2Entry] = []
    for symbol in list(config["universe"]["core"]):  # type: ignore[index]
        if symbol in held:
            continue
        symbol_bars = slice_until(bars_by_symbol.get(symbol, ()), as_of)
        if not symbol_bars:
            continue
        assert_ascending(symbol_bars)
        close_values, high_values, low_values = closes(symbol_bars), highs(symbol_bars), lows(symbol_bars)
        average = sma(close_values, 200)
        rsi = rsi_wilder(close_values, rsi_period)
        close_location = ibs(high_values[-1], low_values[-1], close_values[-1])
        average_range = atr(high_values, low_values, close_values, 14)
        if average is None or rsi is None or close_location is None or average_range is None:
            continue
        diagnostics = {
            "close": close_values[-1],
            "sma200": average,
            "rsi2": rsi,
            "ibs": close_location,
            "atr_ratio": average_range / close_values[-1],
        }
        if (
            close_values[-1] > average
            and rsi < rsi_threshold
            and close_location < ibs_threshold
            and diagnostics["atr_ratio"] > volatility_floor
        ):
            signals.append(S2Entry(symbol, round(close_values[-1] * 0.995, 2), "DAY", "LIMIT", diagnostics))
        if len(signals) >= slots:
            break
    return signals


def s2_enabled(config: Mapping[str, object], backtest_promotion_passed: Optional[bool]) -> bool:
    """自建回测门尚未通过时只产生研究结论，不参与投资方向汇总。"""
    return not bool(config.get("enabled_pending_backtest", True)) or backtest_promotion_passed is True
